/**
 * Queue and recent history.
 *
 * The queue is rendered from server state and mutated by sending commands; the
 * client never keeps its own authoritative ordering (contract D3).
 */

import { h, notice, render } from '../dom.js';
import { formatSeconds } from '../position.js';

export function renderQueue(node, state, handlers) {
  if (!state.queueAvailable) {
    render(
      node,
      notice(
        'warn',
        'The queue lives in the playback engine',
        'Queueing arrives with issue #14. Station previews on the Listen tab already show what would play.',
      ),
    );
    return;
  }

  const { items, current_index: current } = state.queue;
  if (!items.length) {
    render(node, h('p', { class: 'muted', text: 'The queue is empty.' }));
    return;
  }

  render(
    node,
    h(
      'div',
      { class: 'queue-head' },
      h('h2', { text: `${items.length} queued` }),
      h('span', { class: 'muted', text: formatSeconds(state.queue.total_duration_seconds) }),
    ),
    h(
      'ol',
      { class: 'queue-list' },
      items.map((item, index) =>
        h(
          'li',
          { class: `queue-item${index === current ? ' is-current' : ''}` },
          h(
            'div',
            { class: 'queue-main' },
            h('span', { class: 'queue-title', text: item.title }),
            h('span', { class: 'queue-sub', text: item.composer || 'Unknown' }),
          ),
          h('span', { class: 'queue-time', text: formatSeconds(item.duration_seconds) }),
          h(
            'div',
            { class: 'queue-actions' },
            h('button', {
              class: 'icon-btn',
              type: 'button',
              'aria-label': `Move ${item.title} up`,
              disabled: index === 0,
              onClick: () => handlers.reorder(item.asset_id, index - 1),
              text: '↑',
            }),
            h('button', {
              class: 'icon-btn',
              type: 'button',
              'aria-label': `Move ${item.title} down`,
              disabled: index === items.length - 1,
              onClick: () => handlers.reorder(item.asset_id, index + 1),
              text: '↓',
            }),
            h('button', {
              class: 'icon-btn icon-btn-danger',
              type: 'button',
              'aria-label': `Remove ${item.title} from the queue`,
              onClick: () => handlers.removeFromQueue(item.asset_id),
              text: '×',
            }),
          ),
        ),
      ),
    ),
  );
}

export function renderHistory(node, state) {
  const { items, loading, error } = state.history;

  if (loading) {
    render(node, h('div', { class: 'thinking' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Loading…'));
    return;
  }
  if (error) {
    render(node, notice('bad', 'Could not load history', error.message));
    return;
  }
  if (!items.length) {
    render(
      node,
      h('p', { class: 'muted', text: 'Nothing has been played yet. History fills in once playback runs.' }),
    );
    return;
  }

  render(
    node,
    h(
      'ul',
      { class: 'results-list' },
      items.map((entry) =>
        h(
          'li',
          { class: 'result' },
          h(
            'div',
            { class: 'result-main' },
            h('span', { class: 'result-title', text: entry.asset_id.replace(/^sha256:/, '').slice(0, 12) }),
            h('span', { class: 'result-sub', text: playedSummary(entry) }),
          ),
          h('span', { class: 'result-time', text: relativeTime(entry.last_played_at) }),
        ),
      ),
    ),
  );
}

function playedSummary(entry) {
  const plays = entry.qualifying_play_count === 1 ? '1 play' : `${entry.qualifying_play_count} plays`;
  const finished = entry.completed_count ? `${entry.completed_count} completed` : null;
  return [plays, finished].filter(Boolean).join(' · ');
}

function relativeTime(iso) {
  if (!iso) return '';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(0, (Date.now() - then) / 1000);
  if (seconds < 90) return 'just now';
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}
