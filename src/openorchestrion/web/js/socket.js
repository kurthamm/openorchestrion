/**
 * WebSocket state synchronisation.
 *
 * Implements the client half of docs/api-contract.md §5:
 *  - every server message carries a monotonically increasing `seq`;
 *  - a gap means resync, never patch;
 *  - a snapshot arrives on connect, deltas after that.
 *
 * The `not_implemented` branch remains only for compatibility with an older
 * backend. Current #14 servers send a real snapshot immediately.
 */

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
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
        return;
      }
      this.handle(envelope);
    });

    socket.addEventListener('close', () => {
      if (this.closed) return;
      // A legacy not_implemented close is "not yet", not a network outage.
      this.onConnectionChange(this.pending ? 'pending' : 'offline');
      this.scheduleReconnect();
    });

    // 'error' is followed by 'close'; reconnect is handled there.
    socket.addEventListener('error', () => {});
  }

  handle(envelope) {
    // Sequence bookkeeping applies to *all* server envelopes, including errors.
    // Otherwise an error at seq N followed by state at N+1 looks like a gap and
    // forces a needless snapshot request.
    if (typeof envelope.seq === 'number') {
      if (envelope.type === 'state.snapshot') {
        // A snapshot is authoritative by definition and may follow a resync
        // request after expectedSeq was deliberately cleared.
        this.expectedSeq = envelope.seq + 1;
      } else {
        const expected = this.expectedSeq;
        if (expected !== null && envelope.seq !== expected) {
          this.requestSnapshot();
          return;
        }
        this.expectedSeq = envelope.seq + 1;
      }
    }

    if (envelope.type === 'error') {
      const code = envelope.payload?.code;
      if (code === 'not_implemented') {
        this.pending = true;
        this.onConnectionChange('pending', envelope.payload);
        return;
      }
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
