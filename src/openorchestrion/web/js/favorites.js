/** Server-backed favorites with explicit optimistic true/false values. */
export function favoriteValue(state, item) {
  return state.localFavorites.has(item.asset_id)
    ? state.localFavorites.get(item.asset_id)
    : Boolean(item.favorite);
}

export async function toggleFavorite(assetId, { getState, setState, save }) {
  const state = getState();
  if (state.pendingFavorites.has(assetId)) return null;
  const item = state.search.items.find((row) => row.asset_id === assetId);
  if (!item) return null;
  const next = !favoriteValue(state, item);
  const hadOverride = state.localFavorites.has(assetId);
  const previous = state.localFavorites.get(assetId);
  const overrides = new Map(state.localFavorites);
  overrides.set(assetId, next);
  setState({
    localFavorites: overrides,
    pendingFavorites: new Set([...state.pendingFavorites, assetId]),
  });
  try {
    const saved = await save(assetId, next);
    const current = getState();
    const localFavorites = new Map(current.localFavorites);
    localFavorites.delete(assetId);
    setState({
      localFavorites,
      search: {
        ...current.search,
        items: current.search.items.map((row) => row.asset_id === assetId
          ? { ...row, favorite: saved.favorite } : row),
      },
    });
    return saved.favorite;
  } catch (error) {
    // Older servers cannot persist favorites. Preserve their session-only
    // value; real failures restore only this asset, not other pending edits.
    if (!error.pending) {
      const localFavorites = new Map(getState().localFavorites);
      if (hadOverride) localFavorites.set(assetId, previous);
      else localFavorites.delete(assetId);
      setState({ localFavorites });
    }
    throw error;
  } finally {
    const pendingFavorites = new Set(getState().pendingFavorites);
    pendingFavorites.delete(assetId);
    setState({ pendingFavorites });
  }
}
