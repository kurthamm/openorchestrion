/**
 * Browse and search.
 *
 * Manual browsing matters when the Concierge is unavailable or the user wants
 * explicit control, so this path never depends on AI.
 */

import { h, notice, render } from '../dom.js';
import { formatSeconds } from '../position.js';

export const FACETS = [
  { key: 'genre', value: 'classical', label: 'Classical' },
  { key: 'genre', value: 'ragtime', label: 'Ragtime' },
  { key: 'genre', value: 'jazz', label: 'Jazz' },
  { key: 'theme', value: 'christmas', label: 'Christmas' },
  { key: 'theme', value: 'dinner', label: 'Dinner' },
  { key: 'mood', value: 'relaxed', label: 'Relaxed' },
];

export function renderFacets(node, state, handlers) {
  render(
    node,
    FACETS.map((facet) => {
      const active = state.search.facet?.value === facet.value && state.search.facet?.key === facet.key;
      return h('button', {
        class: `chip${active ? ' is-active' : ''}`,
        type: 'button',
        'aria-pressed': active ? 'true' : 'false',
        onClick: () => handlers.searchFacet(active ? null : facet),
        text: facet.label,
      });
    }),
  );
}

export function renderResults(node, state, handlers) {
  const { items, loading, ran, error } = state.search;

  if (loading) {
    render(node, h('div', { class: 'thinking' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Searching…'));
    return;
  }

  if (error) {
    render(node, notice('bad', 'Search failed', error.message));
    return;
  }

  if (!ran) {
    render(node, h('p', { class: 'muted', text: 'Search the library, or pick a filter above.' }));
    return;
  }

  if (!items.length) {
    const library = state.status?.library;
    if (library && !library.indexed) {
      render(
        node,
        notice(
          'warn',
          'No library yet',
          'Import MIDI files with openorchestrion-import-midi, then run openorchestrion-reindex.',
        ),
      );
      return;
    }
    render(node, notice('warn', 'Nothing found', 'No pieces in the library match that.'));
    return;
  }

  render(
    node,
    h(
      'ul',
      { class: 'results-list' },
      items.map((item) => assetRow(item, state, handlers)),
    ),
  );
}

function assetRow(item, state, handlers) {
  const favorite = state.localFavorites.has(item.asset_id) || item.favorite;
  const unsaved = state.localFavorites.has(item.asset_id) && !state.favoritesPersist;

  return h(
    'li',
    { class: 'result' },
    h(
      'button',
      {
        class: `fav${favorite ? ' is-on' : ''}${unsaved ? ' is-unsaved' : ''}`,
        type: 'button',
        'aria-pressed': favorite ? 'true' : 'false',
        'aria-label': favorite ? `Remove ${item.title || 'this piece'} from favorites` : `Add ${item.title || 'this piece'} to favorites`,
        title: unsaved ? 'Saved on this device only — the appliance cannot store favorites yet.' : 'Favorite',
        onClick: () => handlers.toggleFavorite(item.asset_id),
        text: favorite ? '★' : '☆',
      },
    ),
    h(
      'div',
      { class: 'result-main' },
      h('span', { class: 'result-title', text: item.title || 'Untitled' }),
      h('span', { class: 'result-sub', text: subtitle(item) }),
    ),
    h('span', { class: 'result-time', text: formatSeconds(item.duration_seconds) }),
    h('button', {
      class: 'btn btn-small',
      type: 'button',
      onClick: () => handlers.playAsset(item.asset_id),
      text: 'Play',
    }),
  );
}

function subtitle(item) {
  const parts = [item.composer || item.artist || 'Unknown'];
  if (item.performance_type) parts.push(item.performance_type.replaceAll('_', ' ').toLowerCase());
  if (item.rights_status && item.rights_status !== 'verified-open') parts.push(item.rights_status);
  return parts.join(' · ');
}
