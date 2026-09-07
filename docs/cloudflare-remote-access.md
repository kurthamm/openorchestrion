# Cloudflare remote access

The reference Raspberry Pi is reachable at `https://piano.hamm.me` through a
dedicated Cloudflare Tunnel. Cloudflare Access protects the hostname before a
request reaches OpenOrchestrion; port 8000 is not forwarded through the router
or exposed directly to the Internet.

## Deployed configuration

The deployment created on 7 September 2026 uses:

| Setting | Value |
| --- | --- |
| Public hostname | `piano.hamm.me` |
| Tunnel name | `openorchestrion-piano` |
| Tunnel ID | `33695eb9-a508-4412-84c4-3a72ef5b779b` |
| Origin | `http://127.0.0.1:8000` |
| Connector host | Raspberry Pi `openOrchestrion` |
| Connector service | `cloudflared.service` |
| Access application | `OpenOrchestrion Piano` |
| Access session | 24 hours |
| Login method | Cloudflare one-time PIN by email |

The Access allow policy contains two exact addresses: `kurt@hamm.me` and
`stacey@hammfamily.com`. Do not replace these with whole-domain rules. An
unlisted address must not receive access even if it belongs to either domain.

## Files and secret boundary

The Pi stores the local tunnel configuration at:

```text
/etc/cloudflared/config.yml
```

The matching tunnel credential is a root-readable JSON file under
`/etc/cloudflared/`. It is intentionally not committed to this repository.
Likewise, Cloudflare API tokens belong in an external secret store and must
never appear in the application environment, browser, documentation, or Git.

The non-secret ingress structure is:

```yaml
tunnel: 33695eb9-a508-4412-84c4-3a72ef5b779b
credentials-file: /etc/cloudflared/33695eb9-a508-4412-84c4-3a72ef5b779b.json

ingress:
  - hostname: piano.hamm.me
    service: http://127.0.0.1:8000
  - service: http_status:404
```

The final catch-all is required. It prevents the connector from forwarding
unexpected hostnames to the player.

## Operations

Inspect the connector without restarting playback:

```bash
sudo systemctl status cloudflared --no-pager
sudo journalctl -u cloudflared -n 100 --no-pager
cloudflared tunnel ingress validate --config /etc/cloudflared/config.yml
cloudflared tunnel ingress rule https://piano.hamm.me/ \
  --config /etc/cloudflared/config.yml
```

Restarting `cloudflared.service` does not restart `openorchestrion.service`, but
remote browser sessions will disconnect briefly and reconnect after the tunnel
returns.

## Verification

An unauthenticated request must redirect to the account's Cloudflare Access
login hostname rather than return the OpenOrchestrion UI or API response:

```bash
curl -sS -o /dev/null -D - https://piano.hamm.me/
curl -sS -o /dev/null -D - https://piano.hamm.me/api/health
```

Both should return an HTTP redirect whose `Location` is under
`kurthamm.cloudflareaccess.com`. After entering an allowed email address,
Cloudflare sends a single-use PIN. Successful authentication sets the Access
session cookie and permits the browser's ordinary HTTP and WebSocket traffic.

Verify the complete player manually after authentication: load the library,
open song details, prepare a queue, observe live playback state, and exercise a
non-disruptive control. Do not use an Access bypass rule for health checks;
service monitoring on the Pi should continue to use the loopback origin.

## Recovery and security

- If the public hostname returns a Cloudflare origin error, confirm both
  `cloudflared.service` and `openorchestrion.service` are active.
- If login succeeds but the player does not update, inspect browser WebSocket
  traffic and the connector journal before changing the allow policy.
- Keep the policy limited to exact email addresses. Never add `Everyone`, an
  email-domain wildcard, or a general one-time-PIN login-method allow rule.
- Rotate a tunnel credential by replacing the credential on the Pi and
  restarting only `cloudflared.service`.
- Rotate API tokens independently; the running connector does not need an API
  token.
- Deleting the Access application makes the hostname public again. Disable the
  DNS route or stop the connector first if Access must be removed for repair.

