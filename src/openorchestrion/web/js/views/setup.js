import { h, notice, render } from '../dom.js';

function statusCard(title, good, summary, detail) {
  return h(
    'article',
    { class: `setup-card ${good ? 'setup-card-ok' : 'setup-card-warn'}` },
    h('div', { class: 'setup-card-head' },
      h('strong', { text: title }),
      h('span', { class: `setup-badge ${good ? 'setup-badge-ok' : 'setup-badge-warn'}`, text: good ? 'Ready' : 'Needs attention' }),
    ),
    h('p', { class: 'setup-summary', text: summary }),
    detail ? h('p', { class: 'setup-detail', text: detail }) : null,
  );
}

function aiSummary(ai) {
  if (!ai) return ['Unknown', 'Concierge status has not loaded yet.'];
  if (ai.reason?.includes('no_provider_configured')) {
    return ['Offline interpreter', 'Hosted AI is optional. Natural-language control still works locally.'];
  }
  if (ai.reason) {
    return [ai.provider || 'Hosted provider', ai.reason.replaceAll('_', ' ')];
  }
  return [ai.provider || 'Concierge ready', 'Natural-language requests are available.'];
}

export function renderSetup(node, state, handlers) {
  const setup = state.setup || {};
  if (setup.loading && !setup.data) {
    render(node, notice('info', 'Checking appliance setup…', 'Reading local readiness state.'));
    return;
  }
  if (setup.error && !setup.data) {
    render(
      node,
      notice('bad', 'Setup status is unavailable.', setup.error.message || 'Try again.'),
      h('button', { class: 'btn', type: 'button', onclick: handlers.refreshSetup, text: 'Retry' }),
    );
    return;
  }

  const data = setup.data;
  if (!data) return;
  const outputs = data.outputs || { ready: false, devices: [] };
  const library = data.library || { indexed: false, assets: 0 };
  const [aiTitle, aiDetail] = aiSummary(data.ai);
  const libraryReady = Boolean(library.indexed && library.assets > 0);
  const currentAddress = globalThis.location?.host || 'this appliance';

  const intro = data.complete
    ? 'Setup has been marked complete. This checklist remains available whenever the appliance changes.'
    : data.ready
      ? 'The core appliance is ready. Review the checklist, then mark setup complete.'
      : 'A few pieces still need attention before the appliance can play music normally.';

  const nextSteps = (data.next_steps || []).map((step) => h('li', { text: step }));
  const command = '/opt/openorchestrion/venv/bin/openorchestrion-configure --show';

  render(
    node,
    h('div', { class: 'setup-heading' },
      h('div', {},
        h('h2', { class: 'setup-title', text: 'Appliance setup' }),
        h('p', { class: 'setup-intro', text: intro }),
      ),
      h('span', {
        class: `setup-ready ${data.ready ? 'setup-ready-ok' : 'setup-ready-warn'}`,
        text: data.ready ? 'Core ready' : 'Setup needed',
      }),
    ),
    h('div', { class: 'setup-grid' },
      statusCard(
        'MIDI output',
        outputs.ready,
        outputs.ready ? `${outputs.devices.length} output${outputs.devices.length === 1 ? '' : 's'} available` : 'No playable MIDI output',
        outputs.ready ? (outputs.devices.join(', ') || 'Output ready') : 'Connect a keyboard/sound engine, or use virtual MIDI for diagnostics.',
      ),
      statusCard(
        'Music library',
        libraryReady,
        libraryReady ? `${library.assets} indexed asset${library.assets === 1 ? '' : 's'}` : (library.indexed ? 'Catalog is empty' : 'Catalog has not been built'),
        libraryReady ? `${library.compositions || 0} compositions indexed.` : 'Import MIDI and run openorchestrion-reindex on the Pi.',
      ),
      statusCard(
        'Music Concierge',
        !data.ai?.reason || data.ai?.reason?.includes('no_provider_configured'),
        aiTitle,
        aiDetail,
      ),
      statusCard(
        'Household access',
        true,
        currentAddress,
        'If the installer was given --hostname openorchestrion, mDNS-capable devices can also use openorchestrion.local.',
      ),
    ),
    h('section', { class: 'setup-next' },
      h('h3', { text: 'What to do next' }),
      h('ul', {}, ...nextSteps),
    ),
    h('section', { class: 'setup-admin' },
      h('h3', { text: 'Private configuration stays on the Pi' }),
      h('p', { text: 'API keys and system settings are never accepted by this browser. Run the local administrator command on the appliance:' }),
      h('code', { class: 'setup-command', text: command }),
    ),
    h('div', { class: 'setup-actions' },
      data.complete
        ? h('button', { class: 'btn', type: 'button', onclick: handlers.resetSetup, text: 'Show first-run guidance again' })
        : h('button', { class: 'btn btn-primary', type: 'button', onclick: handlers.completeSetup, text: data.ready ? 'Mark setup complete' : 'Dismiss setup for now' }),
      h('button', { class: 'btn', type: 'button', onclick: handlers.refreshSetup, text: 'Refresh' }),
    ),
  );
}
