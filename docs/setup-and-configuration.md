# First-run setup and local configuration

OpenOrchestrion is a household LAN appliance, not an Internet account service. The first-run
Setup screen therefore tells the operator what is ready and what still needs attention, but it
**does not accept system settings or provider secrets from a browser**.

That division is intentional. The FastAPI service is reachable by other devices on the trusted
LAN and currently has no user-authentication layer. Giving that browser surface permission to
write `/etc`, change the system hostname, or set an API key would turn onboarding convenience
into a privilege-escalation interface for anyone on the same network.

## The two setup surfaces

### Setup screen

The existing responsive web application includes a **Setup** tab. It reports:

- whether a MIDI output is available and which outputs are active;
- whether `catalog.db` exists and how many assets/compositions are indexed;
- whether the Music Concierge is using the deterministic offline interpreter, a ready hosted
  provider, or a hosted provider that needs local administrator attention;
- the address through which the current browser reached the appliance plus guidance for the
  optional `openorchestrion.local` name;
- concrete next steps for a degraded first boot.

On the first load, the application automatically opens Setup only when the wizard has not been
completed **and** the core appliance is not ready. A ready appliance is never forced into an
onboarding screen merely because the marker is absent.

The Setup screen can be revisited at any time. Marking setup complete writes only a tiny marker
under the durable state root. Resetting it deletes only that marker. Neither operation gates
playback, the queue, library access, or any other API.

The reference marker is:

```text
/var/lib/openorchestrion/setup.json
```

It records the wizard version and completion time. It is a UX preference, not an authorization
or security control. If a future wizard version changes, the old marker becomes incomplete so
new guidance can be shown without discarding any actual appliance configuration.

## Local administrator command

Privileged configuration is performed on the Raspberry Pi with:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure --show
```

`--show` displays the effective EnvironmentFile values but redacts values whose names identify
credentials, including `OPENAI_API_KEY`.

### Hosted AI

Enable the hosted OpenAI provider and configure the normal, non-secret settings:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure \
  --ai-provider openai \
  --ai-model gpt-5.6-luna \
  --ai-timeout 15
```

Set the API key without putting it in shell history or the process argument list:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure --set-openai-key
```

The command prompts with terminal echo disabled. For local automation, a root-controlled
one-line file may be used instead:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure \
  --openai-key-file /root/openai-key
```

Clear the stored key with:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure --clear-openai-key
```

The key remains in `/etc/openorchestrion/openorchestrion.secrets.env`, owned for the service and
mode `0640` on the reference install. It is never returned by `/api/setup`, `/api/status`, or any
other browser endpoint.

Disable hosted AI while retaining the deterministic local interpreter:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure --ai-provider off
```

### Virtual MIDI diagnostics

Virtual MIDI is useful before a physical keyboard is attached:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure --virtual-midi on
```

Return to physical outputs with:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure --virtual-midi off
```

## Restart behavior

A successful change restarts `openorchestrion.service` by default so the new configuration takes
effect. For scripted maintenance that will restart once after several edits:

```bash
sudo /opt/openorchestrion/venv/bin/openorchestrion-configure \
  --ai-timeout 12 \
  --no-restart
```

The configuration is validated before either EnvironmentFile is replaced. The two files are
updated as one local transaction: if the second write or permission step fails, the first file
is rolled back rather than leaving the appliance half-configured. Existing comments, ordering,
and unknown/future keys are preserved.

## Library setup

The browser does not accept arbitrary import paths. Library administration remains local because
it operates on files owned by the appliance:

```bash
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-import-midi \
  /path/to/music \
  --library-root /var/lib/openorchestrion/library

sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-reindex \
  /var/lib/openorchestrion/library
```

After importing or attaching MIDI hardware, press **Refresh** on Setup or reload the application.
The screen uses authoritative server state, so there is no separate browser configuration cache
to reconcile.

## Setup API

The browser uses three deliberately narrow endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/setup` | Read readiness and next-step guidance |
| `POST` | `/api/setup/complete` | Write the harmless setup marker |
| `POST` | `/api/setup/reset` | Remove the harmless setup marker |

The two POST endpoints have **no request body**. They cannot accept an API key, filesystem path,
hostname, package name, shell command, or arbitrary setting. System configuration remains a local
administrator operation by design.

## Readiness semantics

The core appliance is considered ready when:

1. at least one MIDI output is usable; and
2. a non-empty library catalog is indexed.

Hosted AI is not a readiness requirement because the deterministic Concierge is always available
offline. The wizard may still report a hosted-provider configuration problem as something worth
fixing, but Internet access never becomes a prerequisite for local playback.
