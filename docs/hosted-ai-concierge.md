# Hosted AI Music Concierge

OpenOrchestrion always has a deterministic offline Music Concierge. A hosted
provider is an **optional interpretation layer**, never a playback dependency.
The first concrete provider uses OpenAI's Responses API structured-output path to
produce the same validated `PlaybackIntent` that the rest of the application
already consumes.

## Architecture boundary

```text
natural-language request
        │
        ├── configured hosted provider ──► validated PlaybackIntent
        │             │ failure/refusal/timeout
        │             ▼
        └──── deterministic offline interpreter
                      │
                      ▼
              validated PlaybackIntent
                      │
              deterministic station selector
                      │
                 playback engine
```

The hosted model never receives a MIDI handle, playback engine, shell, catalog
mutation API, or tool access. It interprets preferences only. The deterministic
selector still decides which real library assets exist and are eligible, and the
server-owned playback engine remains authoritative.

## What leaves the appliance

When a hosted provider is enabled, the following are sent to that provider:

- the user's natural-language music request;
- the current validated `PlaybackIntent` when the request is a conversational
  refinement;
- the fixed provider contract describing the allowed intent schema.

The MIDI library, filenames, sidecars, listening history, device list, queue,
MIDI events, and audio do **not** need to be sent to interpret a request.

Leave hosted AI disabled if even the request text must remain local.

## Install the optional OpenAI support

A normal appliance installation deliberately does not install the OpenAI SDK.
That keeps the offline build smaller and proves hosted AI is not a boot
dependency.

From the exported appliance installer:

```bash
sudo ./install-appliance.sh --package . --mode kiosk --kiosk-user "$USER" --with-openai
```

For a development checkout:

```bash
python -m pip install -e '.[openai]'
```

## Configure the provider

Non-secret settings live in the normal appliance configuration:

```text
/etc/openorchestrion/openorchestrion.env
```

Set:

```bash
OPENORCHESTRION_AI_PROVIDER=openai
OPENORCHESTRION_AI_MODEL=gpt-5.6-luna
OPENORCHESTRION_AI_TIMEOUT_SECONDS=15
```

Provider enablement is explicit. Merely placing an API key on the Pi does not
cause OpenOrchestrion to begin sending requests to a hosted service.

### API key

The API key belongs in the service-only file:

```text
/etc/openorchestrion/openorchestrion.secrets.env
```

For example:

```bash
OPENAI_API_KEY=your-project-key-here
```

The reference installer creates this file as `root:openorchestrion` mode `0640`.
The Chromium kiosk does not read it. Do not put API keys in
`openorchestrion.env`, which is intentionally readable by the desktop kiosk and
smoke tools.

After editing configuration:

```bash
sudo systemctl restart openorchestrion.service
curl http://127.0.0.1:8000/api/status
```

## Model choice

The reference default is `gpt-5.6-luna`. This task is short structured intent
interpretation rather than long-form reasoning, so the cost-sensitive GPT-5.6
variant is the appropriate default. The model is configuration, not an
architectural dependency, and can be changed without modifying application code.

At the standard API rates published when this integration was implemented
(2026-08-23), a short request with roughly 1,000 input tokens and a few hundred
structured output tokens is far below one US cent on the reference model. Treat
that only as an order-of-magnitude example; provider pricing changes and current
pricing should be checked before budgeting sustained usage.

## Structured output

The adapter uses the current OpenAI Responses API SDK parse path, but it does not
hand the public `PlaybackIntent` model directly to the provider:

```python
response = await client.responses.parse(
    model=model,
    instructions=provider_contract,
    input=[...],
    text_format=OpenAIPlaybackIntent,
)
```

`OpenAIPlaybackIntent` is an internal transport schema. OpenAI Structured Outputs
requires every object to be closed (`additionalProperties: false`) and every
field to be required, with nullable fields used for optional values. The public
application model intentionally has defaults and a free-form
`routing_preferences: dict[str, str]`, which is useful inside OpenOrchestrion but
is not a suitable strict provider schema.

The transport therefore represents routing preferences as a required array of
closed `{key, value}` objects. After the provider response is parsed, that array
is converted losslessly back to the public mapping and the resulting object is
validated again as `PlaybackIntent`. The public REST/API/domain contract does not
change merely to satisfy a hosted provider's schema restrictions.

A CI test walks the generated transport JSON Schema and asserts that every object
is closed and every declared property is required. It also round-trips real
routing preferences and rejects duplicate keys.

The converted `PlaybackIntent` then passes through OpenOrchestrion's existing
provider boundary again. Unknown fields remain forbidden, and conversational
refinements cannot silently drop existing hard include/exclude tags.

No legacy "please output JSON" prompting is used.

## Failure behavior

Any hosted-provider problem falls back to the deterministic interpreter for that
request:

- no API key;
- optional SDK not installed;
- network failure;
- timeout;
- provider exception;
- safety refusal;
- no parsed structured output;
- invalid provider transport or `PlaybackIntent`;
- dropped hard include/exclude constraints during refinement.

The Concierge response exposes `provider`, `fallback_used`, and a non-secret
`primary_error` string so the UI can say when an offline interpretation was used.
Playback, browsing, queue control, stations from an existing intent, and all MIDI
functions remain available without Internet access.

## Testing

CI never uses a live provider key. The adapter accepts an injected async client,
so tests exercise the exact Responses API call shape, strict structured schema,
refusals, timeout fallback, refinement preservation, and status behavior with
in-memory fakes.

The normal non-editable wheel smoke test continues to install **without** the
OpenAI extra and boot with no key. That is a deliberate regression test for the
local-first architecture.
