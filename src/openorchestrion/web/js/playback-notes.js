import { h } from './dom.js';

/** A read-only preview: opening details never queues or plays anything. */
export function playbackNotes(preview) {
  if (preview.error) return h('section', { class: 'detail-section' },
    h('h2', { text: 'What will play' }),
    h('p', { role: 'status', text: `Instrument preview unavailable: ${preview.error}. Reopen these details to retry.` }));
  const r = preview.readiness;
  return h('section', { class: 'detail-section' },
    h('h2', { text: 'What will play' }),
    h('p', { class: 'readiness-summary', text: `${r.parts.length} sounding ${r.parts.length === 1 ? 'part' : 'parts'} · up to ${r.peak_notes} simultaneous MIDI notes` }),
    h('p', { text: r.status === 'caution' ? 'Playback has compatibility concerns listed below.' : 'No structural playback blocker found. Musical completeness and sound quality are not certified.' }),
    r.source_palette ? h('p', {}, h('strong', { text: 'In the file: ' }), r.source_palette.label, '. This describes encoded sounds, not the number of musicians or a quality grade.') : null,
    r.playback_palette && r.playback_palette.kind !== r.source_palette?.kind ? h('p', {}, h('strong', { text: 'With your sound setting: ' }), r.playback_palette.label) : null,
    r.flags.length ? h('ul', { class: 'readiness-flags' }, r.flags.map(f => h('li', { class: f.severity }, h('strong', { text: f.severity === 'warning' ? 'Check sound: ' : 'Playback note: ' }), f.message))) : null,
    h('div', { class: 'sounding-parts' }, r.parts.map(p => h('article', { class: 'sounding-part' },
      h('p', { class: 'eyebrow', text: `CHANNEL ${p.channel}${p.percussion ? ' · PERCUSSION' : ''}${p.changed ? ' · REVOICED' : ''}` }),
      h('h3', { text: [...new Set(p.sounds.map(s => s.name))].join(' / ') }),
      ...[...new Set(p.sounds.map(s => s.mapping_note).filter(Boolean))].map(text => h('p', { class: 'technical-note', text })),
      h('p', { text: `${p.note_count.toLocaleString()} notes · peak ${p.peak_notes} · velocity ${p.velocity_min}–${p.velocity_max}` }),
      h('p', { text: `${p.sustain ? 'Sustain encoded' : 'No sustain encoded'}${p.pitch_bend ? ' · pitch bend encoded' : ''}` }),
      h('details', {}, h('summary', { text: 'Source tracks & MIDI settings' }),
        h('p', { text: p.tracks.map(t => `Track ${t.index + 1}${t.name ? `: ${t.name}` : ''}`).join('; ') }),
        h('ul', {}, p.sounds.map(s => h('li', { text: `${s.name}: program ${s.program}, bank ${s.bank_msb}/${s.bank_lsb}${s.implicit ? ' (player default)' : ''}; ${s.note_count.toLocaleString()} notes` }))),
        h('p', { text: `MIDI note range ${p.note_min}–${p.note_max}. Tracks sharing this channel share instrument and controller state.` }))
    ))),
    h('p', { class: 'technical-note', text: r.reference_device }),
    h('p', { class: 'technical-note', text: r.limitation }),
    h('p', { class: 'technical-note', text: 'This previews your next queue addition. It does not alter songs already queued. Instrument names describe requested GM programs; device-specific sounds and acoustic output are not measured.' }));
}
