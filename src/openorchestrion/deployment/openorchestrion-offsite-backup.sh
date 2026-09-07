#!/bin/bash
set -euo pipefail

state_root=${OPENORCHESTRION_STATE_ROOT:-/var/lib/openorchestrion}
target=${OPENORCHESTRION_BACKUP_TARGET:?OPENORCHESTRION_BACKUP_TARGET is required}
status_file=$state_root/backup-status.json
temporary=$(mktemp /var/tmp/openorchestrion-offsite-backup.XXXXXX.zip)
export TMPDIR=/var/tmp
trap 'unlink "$temporary" 2>/dev/null || true' EXIT

failed() {
    code=$?
    printf '{"status":"failed","finished_at":"%s","exit_code":%d}\n' "$(date -u +%FT%TZ)" "$code" > "$status_file"
    exit "$code"
}
trap failed ERR
printf '{"status":"running","started_at":"%s"}\n' "$(date -u +%FT%TZ)" > "$status_file"

/opt/openorchestrion/venv/bin/openorchestrion-backup create "$temporary" >/dev/null
digest=$(sha256sum "$temporary" | cut -d' ' -f1)
name="$(date -u +%Y-%m-%dT%H%M%SZ)-${digest:0:12}.zip"
remote_dir=${target#*:}
remote_host=${target%%:*}

ssh -o BatchMode=yes -o ConnectTimeout=20 \
    -o UserKnownHostsFile=/var/lib/openorchestrion/.ssh/known_hosts "$remote_host" \
    "mkdir -p '$remote_dir/incoming' && umask 077 && cat > '$remote_dir/incoming/$name.part' && mv '$remote_dir/incoming/$name.part' '$remote_dir/$name' && printf '%s  %s\\n' '$digest' '$name' > '$remote_dir/$name.sha256'" \
    < "$temporary"

bytes=$(stat -c %s "$temporary")
printf '{"status":"ok","finished_at":"%s","filename":"%s","sha256":"%s","bytes":%s}\n' \
    "$(date -u +%FT%TZ)" "$name" "$digest" "$bytes" > "$status_file"
