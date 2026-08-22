/**
 * Progress interpolation.
 *
 * Implements docs/api-contract.md D1. The server pushes a position anchor only
 * when playback state changes; the client draws a smooth bar between anchors.
 *
 * The anchor is taken at LOCAL RECEIPT TIME. The server's `server_time` is
 * never subtracted from the browser clock: the two clocks are independent, and
 * a phone that has not synced NTP can be minutes out, which would put the bar
 * in the wrong place or run it backwards. `server_time` is for ordering and
 * diagnostics only.
 */

/** Anchor a server position reading against the local monotonic clock. */
export function anchor(position, now = performance.now()) {
  if (!position) return null;
  return {
    positionMs: position.position_ms ?? 0,
    durationMs: position.duration_ms ?? null,
    rate: typeof position.rate === 'number' ? position.rate : 1,
    receivedAt: now, // performance.now(): monotonic, immune to clock changes
  };
}

/** Position in ms at `now`, clamped to the track length when known. */
export function positionAt(anchored, now = performance.now()) {
  if (!anchored) return 0;
  const elapsed = Math.max(0, now - anchored.receivedAt);
  const projected = anchored.positionMs + elapsed * anchored.rate;
  if (anchored.durationMs === null) return Math.max(0, projected);
  return Math.min(Math.max(0, projected), anchored.durationMs);
}

/** Completed fraction 0..1, or null when the track length is unknown. */
export function progressAt(anchored, now = performance.now()) {
  if (!anchored || !anchored.durationMs) return null;
  return positionAt(anchored, now) / anchored.durationMs;
}

/** `m:ss`, or `h:mm:ss` past an hour. Used for both elapsed and remaining. */
export function formatClock(ms) {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const total = Math.floor(ms / 1000);
  const seconds = total % 60;
  const minutes = Math.floor(total / 60) % 60;
  const hours = Math.floor(total / 3600);
  const pad = (value) => String(value).padStart(2, '0');
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

export function formatSeconds(seconds) {
  return formatClock((seconds ?? 0) * 1000);
}

/**
 * Drive a per-frame callback while playing.
 *
 * Stops when the rate is zero so a paused kiosk is not repainting sixty times a
 * second for no reason.
 */
export function createTicker(callback) {
  let handle = null;
  let running = false;

  const frame = () => {
    if (!running) return;
    callback();
    handle = requestAnimationFrame(frame);
  };

  return {
    start() {
      if (running) return;
      running = true;
      handle = requestAnimationFrame(frame);
    },
    stop() {
      running = false;
      if (handle !== null) cancelAnimationFrame(handle);
      handle = null;
    },
    get running() {
      return running;
    },
  };
}
