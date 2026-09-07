// Behavioral tests for browser state. No npm dependencies or production build.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../../src/openorchestrion/web/js/favorites.js', import.meta.url), 'utf8');
const { favoriteValue, toggleFavorite } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function harness(items, save) {
  let state = { search: { items }, localFavorites: new Map(), pendingFavorites: new Set() };
  return { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; }, save };
}

const calls = [];
const saved = harness([{ asset_id: 'a', favorite: true }], async (asset_id, favorite) => {
  calls.push(favorite);
  return { asset_id, favorite };
});
assert.equal(await toggleFavorite('a', saved), false);
assert.deepEqual(calls, [false], 'first click removes an existing saved favorite');
assert.equal(favoriteValue(saved.getState(), saved.getState().search.items[0]), false);
assert.equal(await toggleFavorite('a', saved), true);

let release;
const pending = harness([{ asset_id: 'a', favorite: true }], () => new Promise((resolve) => { release = resolve; }));
const request = toggleFavorite('a', pending);
assert.equal(favoriteValue(pending.getState(), pending.getState().search.items[0]), false);
assert.equal(await toggleFavorite('a', pending), null, 'duplicate clicks are ignored while saving');
release({ asset_id: 'a', favorite: false });
await request;
assert.equal(pending.getState().pendingFavorites.size, 0);

const failed = harness([{ asset_id: 'a', favorite: true }], async () => { throw new Error('offline'); });
await assert.rejects(toggleFavorite('a', failed), /offline/);
assert.equal(favoriteValue(failed.getState(), failed.getState().search.items[0]), true);
assert.equal(failed.getState().pendingFavorites.size, 0);

const legacy = harness([{ asset_id: 'a', favorite: true }], async () => {
  throw Object.assign(new Error('not implemented'), { pending: true });
});
await assert.rejects(toggleFavorite('a', legacy));
assert.equal(favoriteValue(legacy.getState(), legacy.getState().search.items[0]), false);
console.log('Browser favorites: reload, optimistic removal, duplicate click, rollback, legacy fallback passed.');
