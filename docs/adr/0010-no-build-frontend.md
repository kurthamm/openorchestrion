# ADR-0010: The web application ships as source, with no frontend build step

- **Status:** Accepted
- **Decision:** The responsive web application is written as standard ES modules
  and CSS, served directly from the Python package. There is no bundler,
  transpiler, or Node.js toolchain in the repository or on the appliance.

## Context

ADR-0005 established one responsive web application for the kiosk, phone,
tablet, and desktop. It did not say how that application is produced.

The obvious default, React with Vite or an equivalent bundler, would add a Node
toolchain to a project that is otherwise pure Python, and would add a build
artifact that must be produced before the appliance can serve anything.

Three project commitments push against that:

1. **Recovery must be simple.** "Make hardware recovery simple through
   reproducible deployment plus off-device backups" is a stated goal, and
   `docs/backup-recovery.md` builds on it. A checkout that serves directly is
   recoverable; one that must first run `npm ci && npm run build` on a Pi is a
   second toolchain to install, pin, and repair under pressure.
2. **Reproducibility by hobbyists.** Every added toolchain is another thing a
   reader must have working before they see the project run.
3. **Local-first operation.** Core browsing and playback must work with no
   Internet. That already rules out CDN-hosted frameworks, CDN fonts, and
   remote source maps, so the usual convenience argument for a bundler is
   weaker here than it looks.

The application's own shape also matters. Per `docs/api-contract.md`, the
backend owns playback state, the queue, history, MIDI timing, and AI
interpretation. The frontend renders server state and sends commands. That is a
thin client, not a client-side application with its own domain model, so much of
the workload a heavier framework exists to manage does not exist here.

Chromium on Raspberry Pi OS supports ES modules, `import`, CSS custom
properties, and the browser APIs used by this application natively, so the
reference kiosk does not require transpilation.

## Decision

- Author the UI as ES modules under `src/openorchestrion/web/`, served by
  FastAPI as static files.
- Use the system font stack. No webfonts, no CDN, no external requests of any
  kind at runtime.
- Keep all API access behind a single client module, so the transport can change
  without touching view code.
- Keep DOM rendering in small render functions driven by a single store.
- Treat `/openapi.json` and `docs/api-contract.md` as the authoritative boundary;
  add contract regression tests when the frontend depends on a shape.

## Consequences

- `git clone` plus `pip install -e .` produces a running appliance, with no
  second toolchain and no frontend build artifact to keep in sync.
- CI can remain Python-only; no Node job is required for this surface.
- The UI is inspectable in the browser exactly as it exists in the repository,
  which suits a hobbyist project meant to be read and modified.
- No JSX, no TypeScript, and no npm ecosystem. Component composition and client
  typing are manual, so API contract tests carry more responsibility.
- If the administration surface later grows genuinely application-like
  complexity, such as multi-step editors or offline queues of pending edits,
  revisit this decision for that surface specifically rather than abandoning it
  wholesale.
- Contributors accustomed to React will find this unfamiliar. That cost is
  accepted in exchange for an appliance that has one runtime and one toolchain.
