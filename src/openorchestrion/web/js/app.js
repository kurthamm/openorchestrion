/** Listening-room shell. Navigation, catalog and player update independently.
 * Future capabilities belong in separate routes/modules; no concierge is mounted.
 */
import { api, commandId } from './api.js?v=playback-readiness-1';
import { playbackNotes } from './playback-notes.js';
import { h, render } from './dom.js';
import { anchor, createTicker, positionAt, progressAt, formatClock, formatSeconds } from './position.js';
import { StateSocket } from './socket.js';
import { loadRenderingPreference, renderingPayload } from './rendering.js';
import { mountRenderingControls } from './views/rendering.js';

const $ = (id) => document.getElementById(id);
const names = { discover: 'Discover', library: 'Music library', favorites: 'Favorites', queue: 'Play queue', recent: 'Recently played', settings: 'Playback & devices' };
const filterKeys = ['genre', 'mood', 'era', 'arrangement', 'composer', 'source'];
const state = { status: null, queue: { items: [] }, playback: {}, collections: [], connection: 'connecting' };
const assets = new Map();
const selectedQueueItems = new Set();
const pendingFavorites = new Set();
let view = 'discover', params = new URLSearchParams(), catalogRequest, routeVersion = 0;
let positionAnchor = null, queueBusy = false, facets = null, detailVersion = 0;
let pendingCommandId = null;
const number = (value) => Number(value || 0).toLocaleString();
const readable = (value) => { const text = (value || 'Not specified').replaceAll('_', ' '); return text === text.toUpperCase() ? text.charAt(0) + text.slice(1).toLowerCase() : text; };
const ready = () => state.connection === 'live' && Boolean(state.status?.outputs?.ready);
const button = (text, onClick, props = {}) => h('button', { type: 'button', class: 'btn', text, onClick, ...props });
const identityCredit = item => item.composer || item.artist || (item.source_context ? `Context: ${item.source_context}` : 'Creator not documented');
const icon = (glyph, label, onClick, props = {}) => button(glyph, onClick, { class: 'icon-btn', 'aria-label': label, title: label, ...props });
function toast(message, bad = false) {
  const el = h('div', { class: `toast${bad ? ' bad' : ''}`, text: message });
  $('toasts').append(el);
  setTimeout(() => el.remove(), 5500);
}
function empty(node, title, message, action = () => go('library'), label = 'Explore the library') {
  render(node, h('div', { class: 'empty' }, h('h2', { text: title }), h('p', { text: message }), action ? button(label, action) : null));
}
function failure(node, error, retry) { empty(node, 'Something interrupted that.', error.message, retry, 'Try again'); }
function linkHash(page, values = {}) {
  const q = new URLSearchParams(values).toString();
  return `#${page}${q ? '?' + q : ''}`;
}
function go(page, values = {}) {
  const next = linkHash(page, values);
  if (location.hash === next) route(); else location.hash = next;
}
function changeFilter(key, value) {
  const next = new URLSearchParams(params); next.delete('offset');
  if (value) next.set(key, value); else next.delete(key);
  go(view === 'favorites' ? 'favorites' : 'library', Object.fromEntries(next));
}
function route() {
  const [page, query = ''] = location.hash.slice(1).split('?');
  view = names[page] ? page : 'discover'; params = new URLSearchParams(query);
  routeVersion++; catalogRequest?.abort();
  document.title = `${names[view]} · OpenOrchestrion`;
  $('breadcrumb').textContent = `Your music / ${names[view]}`;
  document.querySelectorAll('[data-nav]').forEach(a => a.setAttribute('aria-current', a.dataset.nav === view ? 'page' : 'false'));
  document.querySelectorAll('[data-page]').forEach(s => { s.hidden = s.dataset.page !== (view === 'favorites' ? 'library' : view); });
  $('search-input').value = params.get('text') || '';
  if (view === 'library' || view === 'favorites') {
    $('library-heading').textContent = names[view];
    $('library-intro').textContent = view === 'favorites' ? 'The performances you want to come back to. Use the heart on any piece to save it here.' : 'A world of music, ready to discover. Open any performance to explore its instruments.';
    for (const key of filterKeys) if ($(`filter-${key}`)) $(`filter-${key}`).value = params.get(key) || '';
    $('sort').value = params.get('sort') || 'title';
    void loadLibrary();
  } else if (view === 'queue') { drawQueue(); void refreshQueue(); }
  else if (view === 'recent') void loadHistory();
  else if (view === 'settings') { void drawAcquisition(); drawDevices(); mountRenderingControls($('rendering-panel')); void loadOperations(); }
  window.scrollTo({ top: 0 });
}
function favoriteButton(item) {
  return icon(item.favorite ? '♥' : '♡', `${item.favorite ? 'Remove' : 'Save'} ${item.title} ${item.favorite ? 'from' : 'to'} favorites`, () => toggleFavorite(item.asset_id), { 'aria-pressed': String(Boolean(item.favorite)), 'data-favorite': item.asset_id, disabled: pendingFavorites.has(item.asset_id) });
}
function row(item, index = 0, queueIndex = null) {
  assets.set(item.asset_id, { ...assets.get(item.asset_id), ...item });
  const queued = queueIndex !== null;
  return h('article', { class: `music-row${queued && queueIndex === state.queue.current_index ? ' current' : ''}` },
    h('div', { class: 'track-main' }, h('span', { class: 'track-art', 'aria-hidden': 'true', text: queued ? String(index + 1).padStart(2, '0') : '♫' }),
      h('div', {}, button(item.title || 'Untitled performance', () => openDetail(item.asset_id), { class: 'track-title' }), item.title_status === 'unresolved' ? h('small', { class: 'track-sub', text: 'Identity unresolved' }) : null, h('span', { class: 'track-sub', text: [identityCredit(item), item.source_label].filter(Boolean).join(' · ') }))),
    h('span', { class: 'track-arrangement', text: queued ? (queueIndex === state.queue.current_index ? 'Current performance' : readable(item.rendering?.mode || 'Queued')) : readable(item.performance_type) }),
    h('span', { class: 'track-time', text: formatSeconds(item.duration_seconds) }),
    h('div', { class: 'track-actions' }, queued ? [
      h('input', { type: 'checkbox', 'aria-label': `Select ${item.title}`, checked: selectedQueueItems.has(item.asset_id), onChange: e => { if (e.target.checked) selectedQueueItems.add(item.asset_id); else selectedQueueItems.delete(item.asset_id); drawQueue(); } }),
      icon('⇥', `Play ${item.title} next`, () => mutateQueue(() => api.playNext(item.asset_id))),
      icon('↑', `Move ${item.title} up`, () => mutateQueue(() => api.reorderQueue(item.asset_id, index - 1)), { disabled: index === 0 }),
      icon('↓', `Move ${item.title} down`, () => mutateQueue(() => api.reorderQueue(item.asset_id, index + 1)), { disabled: index === state.queue.items.length - 1 }),
      icon('×', `Remove ${item.title} from queue`, () => mutateQueue(() => api.removeFromQueue(item.asset_id))),
    ] : [favoriteButton(item), icon('+', `Add ${item.title} to queue`, () => add(item)), icon('↗', `Details for ${item.title}`, () => openDetail(item.asset_id))]));
}
function drawRows(node, items) { render(node, items.map((item, index) => row(item, index))); }
async function toggleFavorite(id) {
  if (pendingFavorites.has(id)) return;
  const item = assets.get(id); if (!item) return;
  const next = !item.favorite; pendingFavorites.add(id);
  document.querySelectorAll('[data-favorite]').forEach(b => { if (b.dataset.favorite === id) b.disabled = true; });
  try {
    await api.setFavorite(id, next); item.favorite = next;
    document.querySelectorAll('[data-favorite]').forEach(b => {
      if (b.dataset.favorite !== id) return;
      b.textContent = next ? '♥' : '♡'; b.setAttribute('aria-pressed', String(next));
      const label = `${next ? 'Remove' : 'Save'} ${item.title} ${next ? 'from' : 'to'} favorites`;
      b.setAttribute('aria-label', label); b.title = label;
    });
    toast(next ? 'Saved to favorites.' : 'Removed from favorites.');
    if (view === 'favorites' && !next) void loadLibrary();
  } catch (error) { toast(error.message, true); }
  finally { pendingFavorites.delete(id); document.querySelectorAll('[data-favorite]').forEach(b => { if (b.dataset.favorite === id) b.disabled = false; }); }
}
async function loadLibrary() {
  catalogRequest?.abort(); const controller = new AbortController(); catalogRequest = controller;
  const requestVersion = routeVersion;
  $('result-summary').textContent = 'Finding your music…'; $('results').setAttribute('aria-busy', 'true');
  render($('pagination'));
  const offset = Math.max(0, Number.parseInt(params.get('offset') || '0', 10) || 0);
  const values = Object.fromEntries([...params].filter(([k]) => [...filterKeys, 'text', 'sort'].includes(k)));
  if (!['title', 'composer', 'duration', 'newest'].includes(values.sort)) values.sort = 'title';
  try {
    const result = await api.browse({ ...values, favorite: view === 'favorites', offset, limit: 40 }, controller.signal);
    if (requestVersion !== routeVersion || controller.signal.aborted) return;
    $('result-summary').textContent = `${number(result.total)} performance${result.total === 1 ? '' : 's'}${values.text ? ` matching “${values.text}”` : ''}`;
    if (result.items.length) drawRows($('results'), result.items);
    else empty($('results'), offset ? 'You’ve reached the end.' : view === 'favorites' && !params.size ? 'Keep the ones you love.' : 'No performances found.', offset ? 'Return to the first page of these results.' : 'Try a different search or clear your filters.', () => go(view, offset ? { ...values } : {}), offset ? 'First page' : 'Clear search & filters');
    if (view === 'favorites' && result.total === 0 && !params.size) empty($('results'), 'Keep the ones you love.', 'Save a performance with its heart button. Your favorites will appear here.');
    if (result.total || offset) render($('pagination'), button('← Previous', () => changeFilter('offset', String(Math.max(0, offset - 40))), { disabled: offset === 0 }), h('span', { text: `${result.total ? offset + 1 : 0}–${Math.min(offset + result.items.length, result.total)} of ${number(result.total)}` }), button('Next →', () => changeFilter('offset', String(offset + 40)), { disabled: !result.has_more }));
  } catch (error) {
    if (error.name === 'AbortError' || requestVersion !== routeVersion) return;
    $('result-summary').textContent = 'Library unavailable'; failure($('results'), error, loadLibrary);
  } finally { if (catalogRequest === controller) $('results').removeAttribute('aria-busy'); }
}
function drawFilters() {
  const specs = [['genre', 'Style', 'genres'], ['mood', 'Mood', 'moods'], ['era', 'Era', 'eras'], ['arrangement', 'Arrangement', 'arrangements'], ['composer', 'Composer', 'composers'], ['source', 'Collection / source', 'sources']];
  render($('filters'), specs.map(([key, label, list]) => {
    const options = facets[list] || [];
    // A searchable datalist keeps thousands of composers reachable without a giant menu.
    const control = key === 'composer' ? h('input', { id: `filter-${key}`, list: 'composer-options', placeholder: 'All composers', value: params.get(key) || '', onChange: e => changeFilter(key, e.target.value) }) : h('select', { id: `filter-${key}`, onChange: e => changeFilter(key, e.target.value) }, h('option', { value: '', text: `All ${label.toLowerCase()}` }), options.map(o => h('option', { value: o.value, text: `${readable(o.value)} (${number(o.count)})`, selected: o.value === params.get(key) })));
    return h('label', { class: 'filter-label' }, label, control, key === 'composer' ? h('datalist', { id: 'composer-options' }, options.map(o => h('option', { value: o.value }))) : null);
  }));
}
async function loadDiscover() {
  try {
    facets = await api.browseFacets(); drawFilters(); $('library-total').textContent = number(facets.total);
    const suggestions = [['genres', 'genre', /classical/i, 'The classics', '𝄞'], ['genres', 'genre', /jazz/i, 'A little jazz', '♭'], ['moods', 'mood', /calm|relax|gentle|peace/i, 'Take it slowly', '∿'], ['genres', 'genre', /game|soundtrack|film/i, 'Other worlds', '✧']];
    const used = new Set();
    const collections = suggestions.map(([list, key, match, title, glyph]) => {
      const facet = facets[list]?.find(f => match.test(f.value) && !used.has(`${key}:${f.value}`)) || facets[list]?.find(f => !used.has(`${key}:${f.value}`));
      if (!facet) return null; used.add(`${key}:${facet.value}`);
      if (!match.test(facet.value)) title = readable(facet.value);
      return h('a', { class: 'collection', href: linkHash('library', { [key]: facet.value }) }, h('div', { class: 'collection-art', 'aria-hidden': 'true', text: glyph }), h('div', { class: 'collection-copy' }, h('div', {}, h('strong', { text: title }), h('small', { text: `${number(facet.count)} performances · ${readable(facet.value)}` })), h('span', { 'aria-hidden': 'true', text: '↗' })));
    });
    render($('collections'), collections);
    const composer = facets.composers.filter(f => /beethoven/i.test(f.value)).sort((a, b) => b.count - a.count)[0];
    const values = composer ? { composer: composer.value } : {};
    $('featured-title').textContent = composer ? 'A moment with Beethoven' : 'In the library';
    $('featured-link').href = linkHash('library', values);
    const result = await api.browse({ ...values, limit: 5 });
    if (result.items.length) drawRows($('featured'), result.items);
    else empty($('featured'), 'Your library is quiet.', 'Imported performances will appear here when the catalog is ready.', null);
  } catch (error) { failure($('featured'), error, loadDiscover); }
}
async function confirmAction(title, message, label) {
  if ($('confirm').open) return false;
  $('confirm-title').textContent = title; $('confirm-message').textContent = message; $('confirm-accept').textContent = label;
  return new Promise(resolve => {
    const dialog = $('confirm');
    $('confirm-accept').onclick = () => dialog.close('yes');
    $('confirm-cancel').onclick = () => dialog.close('no');
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'yes'), { once: true });
    dialog.returnValue = ''; dialog.showModal(); $('confirm-cancel').focus();
  });
}
async function mutateQueue(action, message) {
  if (queueBusy) return; queueBusy = true;
  document.body.setAttribute('aria-busy', 'true');
  try { state.queue = await action(); drawQueue(); updatePlayer(); if (message) toast(message); }
  catch (error) { toast(error.message, true); }
  finally { queueBusy = false; document.body.removeAttribute('aria-busy'); }
}
async function add(item) { if (state.queue.items.some(i => i.asset_id === item.asset_id)) { toast('This performance is already in your queue.'); return; } await mutateQueue(() => api.replaceQueue({ assetIds: [item.asset_id], mode: 'append' }), `Added “${item.title}” to your queue.`); }
async function playNow(item) {
  if (!ready()) { toast('Connect a MIDI instrument before starting playback.', true); return; }
  if (state.queue.items.length && !await confirmAction('Start a new listening session?', `Play “${item.title}” now and replace the current queue of ${state.queue.items.length} performances.`, 'Replace & play')) return;
  if (queueBusy) return;
  await mutateQueue(async () => {
    const queue = await api.replaceQueue({ assetIds: [item.asset_id] }); state.queue = queue;
    try { applyPlayback(await api.transport('play')); } catch (error) { toast(`Queued, but playback did not start: ${error.message}`, true); }
    return queue;
  });
}
async function editSongPreference(item) {
  try {
    const saved = await api.songPreference(item.asset_id);
    const tempo = Number(prompt('Tempo percent (50–200):', String(saved?.tempo_percent || 100)));
    if (!tempo) return;
    const volume = Number(prompt('Song volume percent (0–150):', String(saved?.volume_percent ?? 100)));
    if (!Number.isFinite(volume)) return;
    await api.saveSongPreference(item.asset_id, { tempo_percent: tempo, volume_percent: volume, rendering: renderingPayload(loadRenderingPreference()) });
    toast(`Saved playback settings for “${item.title}”.`);
  } catch (error) { toast(error.message, true); }
}
async function resetSongPreference(item) {
  try { await api.deleteSongPreference(item.asset_id); toast(`Reset playback settings for “${item.title}”.`); }
  catch (error) { toast(error.message, true); }
}
function drawQueue() {
  $('queue-count').textContent = number(state.queue.items.length);
  $('queue-summary').textContent = `${number(state.queue.items.length)} performance${state.queue.items.length === 1 ? '' : 's'} · ${formatSeconds(state.queue.total_duration_seconds)} total`;
  $('start-queue').disabled = !ready() || !state.queue.items.length;
  $('clear-queue').disabled = !state.queue.items.length;
  $('save-queue').disabled = !state.queue.items.length;
  $('remove-selected').disabled = !selectedQueueItems.size;
  if ($('undo-queue')) $('undo-queue').disabled = !state.queue.can_undo;
  $('repeat-mode').value = state.queue.repeat_mode || 'off';
  $('shuffle-mode').checked = Boolean(state.queue.shuffle);
  $('continuous-mode').checked = Boolean(state.queue.continuous);
  if (view !== 'queue') return;
  if (!state.queue.items.length) empty($('queue-list'), 'Make yourself a listening session.', 'Use + beside any performance to add it here. Build your queue before connecting an instrument.');
  else render($('queue-list'), state.queue.items.map((item, index) => row(item, index, index)));
}
async function refreshCollections() {
  try {
    const result = await api.collections(); state.collections = result.items;
    render($('saved-collections'), h('option', { value: '', text: 'Saved…' }), result.items.map(item => h('option', { value: item.id, text: `${item.kind === 'station' ? 'Station' : 'Playlist'} · ${item.name}` })));
  } catch (error) { toast(error.message, true); }
}
async function savePlaylist() {
  const name = prompt('Name this playlist:')?.trim(); if (!name) return;
  try { await api.saveCollection({ name, kind: 'playlist' }); await refreshCollections(); toast(`Saved “${name}”.`); } catch (error) { toast(error.message, true); }
}
async function saveStation() {
  const intent = { mode: 'station' };
  const map = { genre: 'genres', mood: 'moods', era: 'eras', composer: 'composers', arrangement: 'performance_types', source: 'include_tags' };
  for (const [filter, field] of Object.entries(map)) if (params.get(filter)) intent[field] = [params.get(filter)];
  const name = prompt('Name this station:')?.trim(); if (!name) return;
  try { await api.saveCollection({ name, kind: 'station', intent }); await refreshCollections(); toast(`Saved station “${name}”.`); } catch (error) { toast(error.message, true); }
}
async function refreshQueue() { try { state.queue = await api.queue(); drawQueue(); updatePlayer(); } catch (error) { toast(error.message, true); } }
async function loadHistory() {
  const version = routeVersion;
  render($('history'), h('p', { text: 'Loading your listening history…' }));
  try {
    const result = await api.history({ limit: 30 });
    // Resolve readable identities in small batches; unavailable archived entries stay explicit.
    const items = [];
    for (let i = 0; i < result.items.length; i += 5) {
      if (version !== routeVersion) return;
      items.push(...await Promise.all(result.items.slice(i, i + 5).map(async entry => {
        try { return { ...await api.asset(entry.asset_id), last_played_at: entry.last_played_at }; }
        catch (error) { return { asset_id: entry.asset_id, title: error.status === 404 ? 'Performance no longer available' : 'Performance details temporarily unavailable', unavailable: true, last_played_at: entry.last_played_at }; }
      })));
    }
    if (version !== routeVersion) return;
    if (!items.length) empty($('history'), 'Your listening story starts here.', 'Once a performance has played for long enough, you can find it again here.');
    else render($('history'), items.map(item => h('div', {}, item.unavailable ? h('p', { text: item.title }) : row(item), h('p', { class: 'track-sub', text: item.last_played_at ? `Last played ${new Date(item.last_played_at).toLocaleString()}` : 'Play time not recorded' }))));
  } catch (error) { if (version === routeVersion) failure($('history'), error, loadHistory); }
}
const soundLabels = { AUTO: 'Automatic voicing', ORIGINAL: 'Original arrangement', PIANO_ONLY: 'Piano only', OVERRIDE: 'Instrument overrides' };
async function openDetail(id) {
  const version = ++detailVersion;
  render($('detail-content'), h('h1', { id: 'detail-title', class: 'detail-title', text: 'Opening performance…' }));
  if (!$('detail').open) $('detail').showModal();
  try {
    const [item, facts, preview] = await Promise.all([api.asset(id), api.performance(id),
      Promise.resolve().then(() => api.performancePreview(id)).catch(error => ({ error: error.message }))]);
    if (version !== detailVersion || !$('detail').open) return;
    assets.set(id, item);
    const stat = (value, label) => h('div', {}, h('strong', { text: value }), h('span', { text: label }));
    const factList = (pairs) => h('dl', { class: 'facts' }, pairs.flatMap(([label, value]) => [h('dt', { text: label }), h('dd', { text: value === null || value === undefined || value === '' ? 'Not documented' : String(value) })]));
    const tags = [...new Set([...(item.genres || []), ...(item.moods || []), ...(item.instrumentation || [])])];
    render($('detail-content'), h('p', { class: 'eyebrow', text: 'PERFORMANCE NOTES' }), h('h1', { id: 'detail-title', class: 'detail-title', text: item.title }), h('p', { class: 'detail-sub', text: identityCredit(item) }),
      h('div', { class: 'detail-actions' }, button('▶ Play now', () => playNow(item), { class: 'btn btn-primary', disabled: !ready(), 'data-needs-output': 'true', title: ready() ? 'Replace the queue and play this performance' : 'Connect a MIDI instrument to play' }), button('+ Add to queue', () => add(item)), button('Playback settings', () => editSongPreference(item)), button('Reset playback settings', () => resetSongPreference(item)), favoriteButton(item)),
      h('div', { class: 'detail-stats' }, stat(formatSeconds(item.duration_seconds), 'Duration'), stat(number(item.track_count), 'MIDI tracks'), stat(number(facts.channels.length), 'Channels'), stat(number(item.note_count), 'Notes')),
      h('div', { class: 'tags' }, tags.map(tag => h('span', { class: 'tag', text: readable(tag) }))),
      h('section', { class: 'detail-section' }, h('h2', { text: 'How this will play' }), h('p', { text: `Next addition: ${soundLabels[loadRenderingPreference().mode]}. ${ready() ? 'A MIDI output is connected.' : 'Connect a MIDI instrument to hear this performance.'}` }), h('a', { class: 'text-btn', href: '#settings', onClick: () => $('detail').close(), text: 'Change sound & device settings →' }), h('p', { class: 'technical-note', text: 'Encoded instruments below describe the MIDI file. Automatic voicing or your chosen overrides can change the programs sent to the keyboard. Banks, drum kits and available sounds depend on the device. SysEx messages are not sent to hardware.' })),
      playbackNotes(preview),
      h('details', { class: 'detail-section' }, h('summary', { text: 'Original file: encoded instrument changes' }), h('p', { text: 'Channels and General MIDI programs use human-readable numbering (1–16 and 1–128). These source changes may be replaced by the sound setting previewed above. Percussion program numbers select drum kits, not pitched instruments.' }),
        facts.instruments.length ? h('div', { class: 'table-scroll' }, h('table', { class: 'instrument-table' }, h('thead', {}, h('tr', {}, ['Channel', 'Instrument', 'Program', 'Bank MSB / LSB'].map(text => h('th', { scope: 'col', text })))), h('tbody', {}, facts.instruments.map(p => h('tr', {}, h('td', { text: p.channel }), h('td', { text: p.channel === 10 ? 'Drum kit selection' : p.gm_name }), h('td', { text: p.gm_program_number }), h('td', { text: `${p.bank_msb} / ${p.bank_lsb}` })))))) : h('p', { text: 'No program changes are encoded. Before applying your sound setting, the player resets pitched channels to Acoustic Grand Piano and channel 10 to its default drum kit.' }),
        h('p', { text: `Active channels: ${facts.channels.map(c => `${c.channel}${c.is_percussion ? ' (percussion)' : ''}`).join(', ') || 'None'}.` })),
      h('section', { class: 'detail-section' }, h('h2', { text: 'Performance & expression' }), factList([['Catalog arrangement', readable(item.performance_type)], ['Sustain pedal', facts.sustain_used ? 'Encoded' : 'Not encoded'], ['Pitch bend', facts.pitch_bend_used ? 'Encoded' : 'Not encoded'], ['Velocity range', `${facts.velocity_min ?? '—'}–${facts.velocity_max ?? '—'}`], ['Peak notes at once', facts.peak_simultaneous_notes], ['MIDI note range', `${facts.note_min ?? '—'}–${facts.note_max ?? '—'}`], ['General MIDI assessment', readable(facts.gm_assessment)], ['SysEx messages', `${facts.sysex_count} in the file; blocked during playback`]])),
      h('section', { class: 'detail-section' }, h('h2', { text: 'About this version' }), factList([['Collection / source', facts.source_label], ['Source reference', facts.source_reference], ['Composer', item.composer], ['Artist', item.artist], ['Source context', item.source_context], ['Title evidence', item.title_status === 'embedded_metadata' ? 'Embedded MIDI metadata' : item.title_status === 'unresolved' ? 'Identity unresolved' : item.title_status ? 'Publisher / upload label' : null], ['Identity notes', item.metadata_note], ['Original source title', item.source_title], ['Era', readable(item.era)], ['Original filename', item.original_filename], ['Rights status', readable(facts.rights_status)], ['License', facts.license], ['Attribution', facts.attribution]])));
  } catch (error) { if (version === detailVersion) { render($('detail-content'), h('h1', { id: 'detail-title', text: 'Details unavailable' })); $('detail-content').append(h('p', { text: error.message }), button('Try again', () => openDetail(id))); } }
}
function drawDevices() {
  const outputs = state.status?.outputs;
  const online = state.connection === 'live';
  $('connection').textContent = online ? '● Connected to your player' : '○ Reconnecting to your player…';
  $('device-notice').hidden = ready();
  render($('device-notice'), h('span', { text: !online ? 'Reconnecting to the player. Your library view stays open.' : 'No MIDI instrument connected. You can still explore and build a queue.' }), h('a', { href: '#settings', text: 'Playback & devices →' }));
  render($('device-settings'), h('p', { text: outputs?.ready ? `Connected: ${(outputs.devices || []).join(', ') || 'MIDI output available'}` : 'No MIDI output is ready. Connect and power on your USB MIDI keyboard or sound module.' }), h('p', { text: 'Audio comes from your connected instrument, not this browser. Keep its own speakers or audio output connected.' }));
  document.querySelectorAll('[data-needs-output]').forEach(b => { b.disabled = !ready(); });
}
function updateProgress() {
  const elapsed = positionAt(positionAnchor);
  const duration = positionAnchor?.durationMs ?? (state.playback.now_playing?.duration_seconds || 0) * 1000;
  $('elapsed').textContent = formatClock(elapsed); $('duration').textContent = formatClock(duration);
  const percent = Math.round((progressAt(positionAnchor) || 0) * 100);
  $('progress-fill').style.width = `${percent}%`; $('progress').setAttribute('aria-valuenow', percent);
  $('progress').setAttribute('aria-valuetext', `${formatClock(elapsed)} of ${formatClock(duration)}`);
}
const ticker = createTicker(updateProgress);
function updatePlayer() {
  const track = state.playback.now_playing, playing = state.playback.state === 'playing';
  $('np-title').textContent = track?.title || 'Your room is quiet.';
  $('np-sub').textContent = track ? `${playing ? 'Playing' : readable(state.playback.state)} · ${track.composer || 'Creator not documented'}` : 'Add something you love to the queue.';
  $('play').textContent = playing ? 'Ⅱ' : '▶'; $('play').setAttribute('aria-label', playing ? 'Pause playback' : 'Play queue');
  $('play').disabled = !ready() || (!track && !state.queue.items.length);
  $('skip').disabled = !state.queue.items.length || state.connection !== 'live';
  for (const id of ['volume', 'settings-volume']) if (document.activeElement !== $(id)) $(id).value = state.playback.volume ?? 100;
  $('volume').setAttribute('aria-valuetext', `${state.playback.volume ?? 100} percent`);
  const remaining = state.playback.sleep_timer_remaining_seconds;
  const scheduled = state.playback.scheduled_start_remaining_seconds;
  $('timer-status').textContent = state.playback.stop_after_current ? 'Playback will stop after the current performance.' : remaining != null ? `Playback stops in ${formatSeconds(remaining)}.` : scheduled != null ? `Queue starts in ${formatSeconds(scheduled)}.` : 'No timer is active.';
  updateProgress(); if (playing) ticker.start(); else ticker.stop();
}
function applyPlayback(value) { if (value.command_id === pendingCommandId) pendingCommandId = null; state.playback = value; positionAnchor = anchor(value.position); updatePlayer(); }
async function transport(action) {
  if ((queueBusy || pendingCommandId) && action !== 'panic') return;
  const id = commandId(); pendingCommandId = id;
  try { const result = await api.transport(action, id); if (pendingCommandId === id) applyPlayback(result); }
  catch (error) { if (pendingCommandId === id) toast(error.message, true); }
  finally { if (pendingCommandId === id) pendingCommandId = null; }
}
async function refreshStatus() { try { state.status = await api.status(); drawDevices(); updatePlayer(); drawQueue(); } catch (error) { toast(error.message, true); } }
async function loadOperations() {
  const node = $('operations-status'); if (!node) return;
  try {
    const value = await api.operations();
    const gigabytes = bytes => `${(bytes / 1073741824).toFixed(1)} GB`;
    render(node, h('p', { text: `Version ${value.service_version} · Up ${formatSeconds(value.uptime_seconds)}` }), h('p', { text: `${gigabytes(value.disk_free_bytes)} free of ${gigabytes(value.disk_total_bytes)} · ${value.library_assets.toLocaleString()} library items · ${value.queue_length} queued` }), h('p', { text: `Cloudflare tunnel: ${readable(value.tunnel_status)} · MIDI: ${value.outputs.ready ? 'Ready' : readable(value.outputs.reason)}` }), h('p', { text: value.backup ? `Backup: ${readable(value.backup.status)}${value.backup.finished_at ? ` · ${new Date(value.backup.finished_at).toLocaleString()}` : ''}` : 'Backup status not recorded yet.' }), value.recent_playback_failures.length ? h('details', {}, h('summary', { text: `${value.recent_playback_failures.length} recent playback failure(s)` }), value.recent_playback_failures.map(failure => h('p', { text: `${failure.asset_id}: ${failure.error}` }))) : h('p', { text: 'No playback failures since service start.' }));
  } catch (error) { render(node, h('p', { text: error.message })); }
}
const socket = new StateSocket({ onConnectionChange: connection => { state.connection = connection; drawDevices(); updatePlayer(); drawQueue(); }, onMessage: envelope => {
  const p = envelope.payload;
  if (envelope.type === 'state.snapshot') { state.status = p.status; state.queue = p.queue; applyPlayback(p.playback); drawDevices(); drawQueue(); }
  else if (envelope.type === 'state.playback') applyPlayback(p);
  else if (envelope.type === 'state.queue') { state.queue = p; drawQueue(); updatePlayer(); }
  else if (envelope.type === 'state.devices') { state.status = { ...state.status, outputs: p }; drawDevices(); updatePlayer(); drawQueue(); }
  else if (envelope.type === 'state.library') { void loadDiscover(); if (view === 'library' || view === 'favorites') void loadLibrary(); }
  else if (envelope.type === 'error') toast(p?.error?.message || p?.message || 'Player reported an error.', true);
} });
$('search-form').addEventListener('submit', e => { e.preventDefault(); const next = ['library', 'favorites'].includes(view) ? Object.fromEntries(params) : {}; delete next.offset; next.text = $('search-input').value.trim(); go(view === 'favorites' ? 'favorites' : 'library', next); });
$('sort').onchange = e => changeFilter('sort', e.target.value);
$('clear-filters').onclick = () => go(view === 'favorites' ? 'favorites' : 'library');
$('save-station').onclick = saveStation;
$('close-detail').onclick = () => $('detail').close();
$('detail').addEventListener('close', () => { detailVersion++; });
$('refresh-status').onclick = refreshStatus;
$('refresh-status').after(button('Play test note', async () => { try { await api.testNote(); toast('Test note sent to connected outputs.'); } catch (error) { toast(error.message, true); } }));
$('start-queue').onclick = () => transport('play');
$('start-queue').after(button('Undo', () => mutateQueue(() => api.undoQueue(), 'Queue change undone.'), { id: 'undo-queue', disabled: true }));
const startDelay = h('select', { id: 'start-delay', 'aria-label': 'Delayed start' }, h('option', { value: '', text: 'Start timer…' }), [5, 15, 30, 60].map(value => h('option', { value: value * 60, text: `${value} minutes` })));
$('start-queue').parentElement.append(startDelay, button('Schedule start', async () => { try { const seconds = Number(startDelay.value) || null; applyPlayback(await api.scheduleStart(seconds)); toast(seconds ? 'Queue start scheduled.' : 'Scheduled start cleared.'); } catch (error) { toast(error.message, true); } }));
$('clear-queue').onclick = async () => { if (await confirmAction('Clear your queue?', 'This ends the current listening session and removes every queued performance.', 'Clear queue')) await mutateQueue(() => api.clearQueue()); };
$('save-queue').onclick = savePlaylist;
$('load-collection').onclick = async () => { const id = $('saved-collections').value; if (id) await mutateQueue(() => api.loadCollection(id), 'Loaded saved collection.'); };
$('delete-collection').onclick = async () => { const id = $('saved-collections').value; if (!id) return; const item = state.collections.find(value => value.id === id); if (await confirmAction('Delete saved collection?', `Delete “${item?.name || 'this collection'}”?`, 'Delete')) { try { await api.deleteCollection(id); await refreshCollections(); toast('Deleted saved collection.'); } catch (error) { toast(error.message, true); } } };
$('remove-selected').onclick = async () => { const ids = [...selectedQueueItems]; if (!ids.length) return; await mutateQueue(async () => { const result = await api.removeManyFromQueue(ids); selectedQueueItems.clear(); return result; }, 'Removed selected performances.'); };
async function updateModes() { await mutateQueue(() => api.setPlaybackModes({ repeatMode: $('repeat-mode').value, shuffle: $('shuffle-mode').checked, continuous: $('continuous-mode').checked })); }
$('repeat-mode').onchange = updateModes; $('shuffle-mode').onchange = updateModes; $('continuous-mode').onchange = updateModes;
$('set-sleep').onclick = async () => { try { const minutes = Number($('sleep-minutes').value); applyPlayback(await api.sleepTimer({ seconds: minutes ? minutes * 60 : null })); toast(minutes ? `Sleep timer set for ${minutes} minutes.` : 'Sleep timer cleared.'); } catch (error) { toast(error.message, true); } };
$('stop-after-current').onclick = async () => { try { applyPlayback(await api.sleepTimer({ afterCurrent: !state.playback.stop_after_current })); } catch (error) { toast(error.message, true); } };
$('progress').onclick = async e => { const duration = state.playback.now_playing?.duration_seconds; if (!duration) return; const box = $('progress').getBoundingClientRect(); const fraction = Math.max(0, Math.min(1, (e.clientX - box.left) / box.width)); try { applyPlayback(await api.seek(duration * fraction)); } catch (error) { toast(error.message, true); } };
$('play').onclick = () => transport(state.playback.state === 'playing' ? 'pause' : 'play');
$('stop').onclick = () => transport('stop'); $('skip').onclick = () => transport('skip'); $('panic').onclick = () => transport('panic');
$('volume').onchange = $('settings-volume').onchange = async e => { try { applyPlayback(await api.setVolume(Number(e.target.value))); } catch (error) { toast(error.message, true); updatePlayer(); } };
window.addEventListener('hashchange', route);
document.querySelector('.skip').addEventListener('click', event => { event.preventDefault(); $('main').focus(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') void refreshStatus(); });
document.querySelector('.settings-grid').append(h('article', { class: 'settings-card' }, h('h2', { text: 'System health' }), h('div', { id: 'operations-status' }), button('Refresh system health', loadOperations)));
// Device settings remain reachable on narrow screens even when no warning is shown.
$('search-form').after(h('a', { href: '#settings', class: 'icon-btn settings-shortcut', 'aria-label': 'Playback and devices', text: '⚙' }));
route(); void loadDiscover(); void refreshStatus(); void refreshCollections(); socket.connect();

async function drawAcquisition() {
  const node = $('acquisition-status');
  try {
    const response = await fetch('/api/library/acquisition');
    if (!response.ok) throw new Error('The last acquisition report could not be loaded.');
    const report = await response.json();
    render(node,
      h('p', { text: report.finished_at ? `Last completed check: ${new Date(report.finished_at * 1000).toLocaleString()}. ${report.counts?.admitted || 0} new performances added.` : 'No completed automatic check has been recorded yet.' }),
      h('p', { text: report.error || (report.status === 'running' ? 'Checking sources now; completed source results appear below.' : report.status === 'degraded' ? 'Some sources were unavailable. Other sources were checked; details are below.' : 'Existing songs and playback are left in place while new candidates are assessed.') }),
      h('details', {}, h('summary', { text: 'Source results' }),
        (report.sources || []).map(source => h('p', { text: `${source.source}: ${source.status}. ${source.error || source.reason || (source.retry_at ? `Retry after ${new Date(source.retry_at * 1000).toLocaleString()}` : `${source.counts?.admitted || 0} added`)}` }))));
  } catch (error) { render(node, h('p', { text: error.message })); }
}
