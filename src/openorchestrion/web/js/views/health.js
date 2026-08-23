/**
 * Appliance health.
 *
 * Every degradable subsystem reports itself explicitly (contract D6), so this
 * renders what the server said rather than inferring anything from missing
 * data. "No library yet" and "AI answering offline" are normal states with
 * useful next steps, not errors.
 */

import { h, render } from '../dom.js';

const CONNECTION_LABEL = {
  connecting: ['warn', 'Connecting'],
  live: ['ok', 'Live'],
  offline: ['bad', 'Reconnecting'],
  pending: ['warn', 'Playback unavailable'],
};

function pill(tone, label, title) {
  return h('span', { class: `pill pill-${tone}`, title: title || label }, label);
}

export function renderHealth(node, state) {
  const parts = [];
  const [tone, label] = CONNECTION_LABEL[state.connection] || ['warn', 'Unknown'];
  parts.push(pill(tone, label, connectionTitle(state.connection)));

  const status = state.status;
  if (status) {
    const outputs = status.outputs || {};
    if (outputs.ready) {
      const count = outputs.devices.length;
      parts.push(pill('ok', count === 1 ? '1 output' : `${count} outputs`, outputs.devices.join(', ')));
    } else {
      parts.push(
        pill(
          'warn',
          'No sound engine',
          outputs.reason === 'no_midi_output'
            ? 'No MIDI output device is connected.'
            : outputs.reason || 'No MIDI output available.',
        ),
      );
    }

    const ai = status.ai || {};
    if (ai.enabled && ai.reason === 'no_provider_configured_using_offline_interpreter') {
      parts.push(pill('warn', 'Offline interpreter', 'No AI provider configured; requests are understood locally.'));
    } else if (ai.enabled) {
      parts.push(pill('ok', 'Concierge', ai.provider || 'ready'));
    } else {
      parts.push(pill('bad', 'Concierge off', ai.reason || 'Natural language is unavailable.'));
    }

    const library = status.library || {};
    if (!library.indexed) {
      parts.push(pill('bad', 'No library', 'Import MIDI files, then rebuild the catalog.'));
    } else if (!library.compositions) {
      parts.push(
        pill('warn', `${library.assets} untitled`, 'Files are indexed but have no descriptive metadata yet.'),
      );
    } else {
      parts.push(pill('ok', `${library.assets} pieces`, `${library.compositions} compositions`));
    }
  }

  render(node, parts);
}

function connectionTitle(connection) {
  switch (connection) {
    case 'live':
      return 'Receiving live state from the appliance.';
    case 'offline':
      return 'Lost contact with the appliance. Retrying.';
    case 'pending':
      return 'This backend reported that live playback state is not available.';
    default:
      return 'Contacting the appliance.';
  }
}
