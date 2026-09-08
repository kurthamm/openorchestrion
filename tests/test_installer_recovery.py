"""Execute the actual installer with isolated filesystem and fake host services."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FAKE = r'''
import os, pathlib, shutil, sys
root = pathlib.Path(os.environ['FAKE_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
failure = os.environ.get('FAIL_AT', '')
with (root / 'calls').open('a') as log:
    log.write(name + ' ' + ' '.join(args) + '\n')
if name == 'id':
    print('0' if args == ['-u'] else 'openorchestrion')
elif name == 'getent':
    sys.exit(2)
elif name == 'systemctl':
    if args[:1] == ['is-active']:
        sys.exit(0 if (root / 'running').exists() else 3)
    if args[:1] == ['stop']:
        (root / 'running').unlink(missing_ok=True)
    if args[:1] == ['restart'] and args[-1] == 'openorchestrion.service':
        (root / 'running').touch()
    if args[:1] == ['cat']:
        sys.exit(1)
elif name == 'python3' or name == 'python':
    if args[:2] == ['-m', 'venv']:
        directory = pathlib.Path(args[2]); (directory / 'bin').mkdir(parents=True, exist_ok=True)
        for command in ['python', 'openorchestrion-deploy', 'openorchestrion-smoke']:
            shutil.copyfile(__file__, directory / 'bin' / command)
            (directory / 'bin' / command).chmod(0o755)
    elif 'wheel' in args:
        if failure == 'download': sys.exit(1)
        directory = pathlib.Path(args[args.index('--wheel-dir') + 1]); directory.mkdir()
        (directory / 'openorchestrion-0.1.0-py3-none-any.whl').touch()
    elif 'install' in args:
        (root / 'opt/venv/version').write_text('new')
        if failure == 'install': sys.exit(1)
elif name == 'openorchestrion-deploy':
    directory = pathlib.Path(args[args.index('--output-dir') + 1])
    for file in ['openorchestrion.service', 'openorchestrion-discovery.service', 'openorchestrion.env']:
        (directory / file).write_text('new template')
elif name == 'openorchestrion-smoke':
    sys.exit(1 if failure == 'health' else 0)
elif name == 'runuser':
    os.execv(args[args.index('--') + 1], args[args.index('--') + 1:])
elif name == 'install':
    # Keep real install behavior except ownership of a fictitious service user.
    clean = []; i = 0
    while i < len(args):
        if args[i] in ('-o', '-g'): i += 2
        else: clean.append(args[i]); i += 1
    os.execv('/usr/bin/install', ['install', *clean])
'''


@pytest.mark.skipif(os.name != "posix", reason="systemd installer runs on Linux")
@pytest.mark.parametrize("failure", ["download", "install", "health", ""])
def test_existing_installation_survives_failures_and_upgrades(tmp_path, failure):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = f"#!{sys.executable}\n" + FAKE
    for command in ["python3", "id", "getent", "systemctl", "install", "runuser", "sleep", "chown"]:
        executable = fake_bin / command
        executable.write_text(fake)
        executable.chmod(0o755)
    venv = tmp_path / "opt/venv"
    (venv / "bin").mkdir(parents=True)
    for command in ["python", "openorchestrion-deploy", "openorchestrion-smoke"]:
        shutil.copyfile(fake_bin / "python3", venv / "bin" / command)
        (venv / "bin" / command).chmod(0o755)
    (venv / "version").write_text("old")
    (tmp_path / "running").touch()
    units = tmp_path / "units"
    units.mkdir()
    (units / "openorchestrion.service").write_text("old unit")
    config = tmp_path / "config"
    config.mkdir()
    (config / "openorchestrion.env").write_text("user configuration")
    (config / "openorchestrion.secrets.env").write_text("user secret")
    state = tmp_path / "state"
    state.mkdir()
    (state / "durable-data").write_text("keep music and playlists")
    script = (ROOT / "src/openorchestrion/deployment/install-appliance.sh").read_text()
    for old, new in [("/opt/openorchestrion", tmp_path / "opt"),
                     ("/etc/openorchestrion", config), ("/var/lib/openorchestrion", state),
                     ("/etc/systemd/system", units),
                     ("/run/lock/openorchestrion-install.lock", tmp_path / "install.lock")]:
        script = script.replace(old, str(new))
    installer = tmp_path / "installer.sh"
    installer.write_text(script)
    result = subprocess.run(["sh", str(installer), "--package", "openorchestrion"],
                            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
                                 "FAKE_ROOT": str(tmp_path), "FAIL_AT": failure},
                            capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) == (not failure), result.stdout + result.stderr
    assert (venv / "version").read_text() == ("old" if failure else "new")
    assert (tmp_path / "running").exists()
    assert (config / "openorchestrion.env").read_text() == "user configuration"
    assert (config / "openorchestrion.secrets.env").read_text() == "user secret"
    assert (state / "durable-data").read_text() == "keep music and playlists"
    if failure:
        assert (units / "openorchestrion.service").read_text() == "old unit"
    if failure == "download":
        assert "systemctl stop" not in (tmp_path / "calls").read_text()
