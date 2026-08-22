/**
 * WebSocket state synchronisation.
 *
 * Implements the client half of docs/api-contract.md §5:
 *  - every message carries a monotonically increasing `seq`;
 *  - a gap means resync, never patch — the client asks for a fresh snapshot
 *    and replaces its state wholesale;
 *  - a snapshot arrives on connect, deltas after that.
 *
 * Until issue #14 lands the server accepts the connection and immediately
 * reports `not_implemented`. That is treated as a normal, renderable state, not
 * as a connection failure, so the reconnect path is exercised now rather than
 * written blind later.
 */

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
// The server currently answers `not_implemented` and closes. That is a settled
// state, not a fault, so it gets a slow retry — enough to pick up the playback
// engine once it ships, without hammering the appliance in the meantime.
const PENDING_RETRY_MS = 60000;

export class StateSocket {
  constructor({ onMessage, onConnectionChange }) {
    this.onMessage = onMessage;
    this.onConnectionChange = onConnectionChange;
    this.socket = null;
    this.expectedSeq = null;
    this.backoff = MIN_BACKOFF_MS;
    this.timer = null;
    this.closed = false;
    this.pending = false;
  }

  url() {
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${scheme}//${location.host}/api/ws`;
  }

  connect() {
    if (this.closed) return;
    clearTimeout(this.timer);

    let socket;
    try {
      socket = new WebSocket(this.url());
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.addEventListener('open', () => {
      this.backoff = MIN_BACKOFF_MS;
      this.expectedSeq = null;
      this.pending = false;
      this.onConnectionChange('live');
    });

    socket.addEventListener('message', (event) => {
      let envelope;
      try {
        envelope = JSON.parse(event.data);
      } catch {
        return; // unparseable frame: ignore rather than tear down the socket
      }
      this.handle(envelope);
    });

    socket.addEventListener('close', () => {
      if (this.closed) return;
      // A close that follows `not_implemented` is the server saying "not yet",
      // not a lost connection. Reporting it as offline would flap the health
      // indicator and hide the real reason from the user.
      this.onConnectionChange(this.pending ? 'pending' : 'offline');
      this.scheduleReconnect();
    });

    // 'error' is always followed by 'close'; reconnect is handled there.
    socket.addEventListener('error', () => {});
  }

  handle(envelope) {
    if (envelope.type === 'error') {
      const code = envelope.payload?.code;
      if (code === 'not_implemented') {
        // Expected until #14. Not a fault, and not worth retrying hard.
        this.pending = true;
        this.onConnectionChange('pending', envelope.payload);
        return;
      }
      this.onMessage(envelope);
      return;
    }

    if (typeof envelope.seq === 'number') {
      const expected = this.expectedSeq;
      if (expected !== null && envelope.seq !== expected) {
        // A gap means we missed state. Patching from here would silently
        // diverge, so ask for the whole picture instead.
        this.requestSnapshot();
        if (envelope.type !== 'state.snapshot') return;
      }
      this.expectedSeq = envelope.seq + 1;
    }

    this.onMessage(envelope);
  }

  requestSnapshot() {
    this.expectedSeq = null;
    this.send({ type: 'state.request_snapshot' });
  }

  send(message) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  scheduleReconnect() {
    clearTimeout(this.timer);
    const base = this.pending ? PENDING_RETRY_MS : this.backoff;
    // Jitter keeps several household clients from reconnecting in lockstep
    // after the appliance restarts.
    const jitter = Math.random() * (base * 0.25);
    this.timer = setTimeout(() => this.connect(), base + jitter);
    if (!this.pending) this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
  }

  close() {
    this.closed = true;
    clearTimeout(this.timer);
    this.socket?.close();
  }
}
