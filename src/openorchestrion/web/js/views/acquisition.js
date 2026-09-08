import { api } from '../api.js';
import { h, render } from '../dom.js';

export function acquisitionSummary(job) {
  const report = job.progress || {};
  const counts = report.counts || (report.sources || []).reduce((sum, source) => {
    for (const [key, value] of Object.entries(source.counts || {})) sum[key] = (sum[key] || 0) + value;
    return sum;
  }, {});
  return { added: counts.admitted || 0, rejected: counts.not_qualified || 0,
    duplicates: (counts.duplicate_bytes || 0) + (counts.duplicate_playback || 0) + (counts.known_source || 0),
    problems: (report.sources || []).filter(s => ['error', 'backoff'].includes(s.status)).length };
}

export function mountAcquisition(node, onComplete) {
  let disposed = false, timer, busy = false, completionSeen = null;
  const selected = new Set(['smd']);
  const choices = h('fieldset', {}, h('legend', { text: 'Choose your sources' }));
  const status = h('div', { role: 'status', 'aria-live': 'polite' });
  const start = h('button', { class: 'btn btn-primary', type: 'button', text: 'Find qualifying music', onClick: async () => {
    if (busy) return;
    busy = true; start.disabled = true;
    try { await api.startAcquisition([...selected]); await refresh(); }
    catch (error) { render(status, h('p', { text: error.message })); }
    finally { busy = false; }
  }});
  render(node, h('p', { text: 'Build a listening library from reviewed sources. Start with recorded piano performances, or choose other repertoire below.' }),
    h('p', { text: 'Each check assesses up to five candidates per source. Only qualifying, nonduplicate performances are added. Source access and musical quality vary; a check may add no songs.' }),
    choices, h('p', { text: 'Downloads are for your personal library under each source’s terms. They are not included in the public software release. This starts one check; it does not enable nightly downloads.' }),
    start, status, h('p', {}, h('a', { href: '#library', text: 'Browse your music →' })),
    h('p', { text: 'You can leave this page while the server works. Connecting a MIDI keyboard is required to hear your music.' }));
  let choicesLoaded = false;
  async function refresh() {
    clearTimeout(timer);
    try {
      const data = await api.acquisitionJob();
      if (disposed) return;
      if (!choicesLoaded) {
        for (const source of data.sources.filter(s => !s.disabled)) {
          const checkbox = h('input', { type: 'checkbox', checked: selected.has(source.key), onChange: e => {
            if (e.target.checked) selected.add(source.key); else selected.delete(source.key);
            start.disabled = busy || !selected.size;
          }});
          choices.append(h('div', { class: 'acquisition-source' }, h('label', {}, checkbox, ` ${source.label}`),
            h('p', { class: 'muted', text: source.key === 'smd' ? 'Recorded classical piano performances · recommended first check' : `${source.genre || 'Mixed repertoire'} · assessed individually` }),
            h('a', { href: source.reference, target: '_blank', rel: 'noopener noreferrer', text: 'Source and usage terms ↗' })));
        }
        choices.append(h('details', {}, h('summary', { text: 'Currently unavailable sources' }),
          data.sources.filter(s => s.disabled).map(s => h('p', { text: `${s.label}: ${s.disabled}` }))));
        choicesLoaded = true;
      }
      const job = data.job, summary = acquisitionSummary(job);
      const running = job.status === 'running';
      start.disabled = running || !data.supported || !selected.size;
      choices.disabled = running;
      start.textContent = running ? 'Checking sources…' : job.status === 'idle' ? 'Find qualifying music' : 'Check again';
      const heading = { idle: 'Ready when you are.', running: 'Finding and checking music', complete: summary.added ? 'Your new music is ready.' : 'Check finished — no new qualifying music.', failed: 'The check could not finish.', interrupted: 'The check was interrupted.' }[job.status] || job.status;
      render(status, h('h2', { text: heading }),
        !data.supported ? h('p', { text: 'Guided acquisition is available on the Linux appliance.' }) : null,
        job.status !== 'idle' ? h('p', { text: `${summary.added} added · ${summary.rejected} below the quality standard · ${summary.duplicates} duplicates skipped` }) : null,
        running ? h('p', { text: `Checking: ${job.progress?.active_source || 'preparing the library'}. This can take several minutes; there is a 30-minute limit.` }) : null,
        job.error ? h('p', { text: job.error }) : null,
        summary.problems ? h('p', { text: 'Some sources could not be checked. Available results are retained; retries respect the source’s waiting period.' }) : null,
        (job.progress?.sources || []).length ? h('details', {}, h('summary', { text: 'Results by source' }),
          job.progress.sources.map(s => h('p', { text: `${s.source}: ${s.status}. ${s.counts?.admitted || 0} added. ${s.error || s.reason || (s.retry_at ? `Retry after ${new Date(s.retry_at * 1000).toLocaleString()}.` : '')}` }))) : null);
      if (job.status === 'complete' && completionSeen !== job.finished_at) { completionSeen = job.finished_at; onComplete(); }
    } catch (error) {
      if (!disposed) { start.disabled = false; render(status, h('p', { text: `${error.message} Reconnecting to check progress…` })); }
    }
    if (!disposed) timer = setTimeout(refresh, 3000);
  }
  void refresh();
  return () => { disposed = true; clearTimeout(timer); };
}
