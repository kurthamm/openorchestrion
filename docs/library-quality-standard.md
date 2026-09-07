# MIDI listening quality: definition and evidence

Research date: 7 September 2026. This is the project's quality definition and
implementation specification. It does **not** certify the current 20,549 admitted
files or silently replace the deployed `household-listening-v1` admission policy.

## What qualifies as a quality file

For this listening library, a quality MIDI file represents a **complete, coherent
performance of its stated arrangement**, contains the musical detail appropriate
to that arrangement, and has a documented playback path that preserves its
essential parts, timing and expression on the intended keyboard.

These are separate requirements. A technically valid file can be an isolated
viola part. An excellent performance can depend on a sound the WK-220 cannot
reproduce faithfully. A complete score export can have mechanically rendered
phrasing. A small, single-channel piano file can be an excellent performance.
File size, channel count, instrument count and controller count are not quality
scores. There is no target collection size.

| Dimension | Required evidence | What prevents qualification |
| --- | --- | --- |
| Integrity | Verified bytes, supported timeline, meaningful notes, deterministic event order and endings | Corruption, unsupported timing, truncated stream, unresolved hanging-note behavior |
| Arrangement completeness | Identified intended arrangement; source/score/related exports agree with the material present | Isolated practice part presented as the whole work, missing essential melody/accompaniment, unexplained truncation |
| Performance detail | Timing, articulation, dynamics and controllers appropriate to the instrument/style | Demonstrably mechanical or damaged rendering where those details are essential; adding random variation does not repair this |
| Sound realization | Per-part program/bank/drum requirements and necessary controls mapped to the selected device | Unresolved essential sound dependency, omitted essential part, known controller loss that materially changes the performance |
| Identity and provenance | Traceable source and arrangement identity; claims backed by evidence | Conflicting work/version identity; unsupported claims that a part is a complete performance |

Missing composer, lyrics, copyright text or an explicit program change does not
by itself make the music poor. Record metadata and rights confidence separately
from musical quality. Do not invent those fields to make a record look complete.

## What can be inside a MIDI file

A Standard MIDI File stores timed musical instructions rather than the sampled
audio of a piano or orchestra. It can contain several tracks, and tracks can
share channels. Track structure is not a reliable count of musical instruments
or performers. The MIDI Association describes the SMF's timing, sequence, track
and descriptive metadata facilities in its [SMF overview](https://midi.org/standard-midi-files).

| Information | Examples | Why the library and engine need it |
| --- | --- | --- |
| Notes and timing | Pitch, note-on velocity, releases, delta times, tick resolution, tempo map | Pitch correctness, articulation, rhythm, duration and expression |
| Sound selection | Program changes, bank MSB/LSB, changes during a channel's performance | Which sound must be selected before each note, including vendor dependencies |
| Performance controls | Sustain, sostenuto, soft pedal, expression, modulation, breath, pitch bend, pressure | Preserve performance detail; presence alone does not prove useful musical application |
| Mix and effects | Channel volume, pan, reverb/chorus sends | Part balance and intended spatial/effect settings |
| Parameter controls | RPN/NRPN selection and data entry, pitch-bend sensitivity, tuning | Interpret bends and sound edits correctly; device support varies |
| Device setup | SysEx, GM/vendor initialization, device/port hints | Identify external dependencies and unsupported routing/setup |
| Musical/descriptive metadata | Track/instrument names, text, copyright notices, lyrics, markers, cues, meter and key | Better identification, navigation and arrangement evidence; not inherently playback commands |
| Packaging/timing structure | SMF format 0/1/2, track endings, tick or SMPTE division | Correct parsing and supported playback; format 2 sequences cannot simply be assumed synchronous |

The Association's [message table](https://midi.org/expanded-midi-1-0-messages-list)
documents note, program, pressure and channel messages; its
[controller table](https://midi.org/midi-1-0-control-change-messages) identifies
bank select, volume, pan, expression, pedals, effects and parameter controls.
Release velocity and pressure may be encoded even if the target instrument does
not use them. Lyrics are text, not a recorded vocal. A program number is not a
sound sample. [General MIDI](https://midi.org/general-midi) improves agreement
about instrument selections, but does not guarantee identical timbre across
keyboards or compatibility with arbitrary vendor banks.

Absence must be interpreted in context. Rubato can be encoded in note timings
while the tempo meta value stays constant. Organ music need not vary attack
velocity. A dry arrangement may intentionally omit reverb or sustain. Repeated
controller messages with one value are initialization/redundancy, not evidence
of expressive development. Large velocity ranges can come from unrelated parts
or accidental extremes; assess distributions and phrases per part.

## Research on this collection

The [full inventory](evidence/library-compatibility/2026-09-07.json) examines the
existing validated sounding facts for all 20,549 admitted files. A separate
[raw-event study](evidence/library-compatibility/content-research-2026-09-07.json)
hash-verifies and parses 76 actual files: a deterministic sample of 24 each from
BitMidi, Mutopia and MAESTRO, the sole Wikimedia file, and three targeted examples.
This is **not** a statistical certification of each source or a listening test.
The targeted cases are excluded from source-summary counts.

| Observed feature | BitMidi sample (24) | Mutopia sample (24) | MAESTRO sample (24) |
| --- | ---: | ---: | ---: |
| More than one note velocity | 20 | 11 | 24 |
| More than one tempo value | 9 | 4 | 0 |
| Sustain CC64 present | 10 | 1 | 24 |
| Sostenuto CC66 present | 2 | 0 | 6 |
| Soft pedal CC67 present | 1 | 0 | 22 |
| Expression CC11 present | 7 | 0 | 0 |
| Pitch bend present | 11 | 0 | 0 |
| SysEx present | 9 | 0 | 0 |
| Lyrics present | 4 | 4 | 0 |

MAESTRO's publisher documents Disklavier recordings of competition performances,
including velocities and three pedal types. Its v3 release also removed six
recordings with unrepresented string-quartet accompaniment. That is a useful
example of **completeness being distinct from recording fidelity**.
[MAESTRO dataset documentation](https://magenta.tensorflow.org/datasets/maestro)
supports this source context; our sample independently shows why tempo-change
counts and missing lyrics/embedded copyright cannot determine quality.

Mutopia's [contribution instructions](https://www.mutopiaproject.org/contribute.html)
describe LilyPond sources and MIDI generation. LilyPond documents MIDI as useful
for checking notation aurally, and has explicit controls for dynamics,
articulation and instruments. Therefore score correctness and expressive
playback must be assessed separately. Its documented fallback to acoustic grand
for an unrecognized instrument explains why a piano patch is weak evidence of
arrangement identity. [MIDI output](https://lilypond.org/doc/v2.24/Documentation/notation/creating-midi-output),
[instrument selection](https://lilypond.org/doc/v2.24/Documentation/notation/using-midi-instruments).
This does not imply all Mutopia files lack expression.

BitMidi's creator describes a heterogeneous archive assembled for browsing and
playback, not a certification process for complete keyboard arrangements.
[BitMidi's own account](https://bitmidi.com/about). Source membership is therefore
context, not a pass/fail decision; the sample contains useful controller-rich
arrangements as well as simpler material.

Three concrete cases demonstrate the required distinctions:

* **Kyosuke I**, asset `0006b7e4…`: one sounding channel, explicit acoustic piano,
  843 attacks and 59 velocities, no pedal controllers. This supports an encoded
  piano arrangement; no sustain alone does not establish a defect. Completeness
  still requires arrangement evidence beyond the program number.
* **Haydn Op.76 No.6: viola-1**, asset `037b5447…`: 327 attacks on one channel,
  ten velocities, no program change, repeated constant CC7 only. The record's
  identity specifies a viola part, while the player defaults it to piano.
  The [upstream work directory](https://www.mutopiaproject.org/ftp/HaydnFJ/O76/op76-n6/)
  provides score/source and MIDI bundles. This file must not be called a complete
  quartet or a proven piano arrangement. Source-bundle comparison is the next
  evidence step for repair or isolation.
* **Ocarina of Time - Gerudo Theme**, asset `2f6b9ef0…`: 593 attacks, all on
  channel 10, with eight velocities and a non-default kit request. The
  [source page](https://bitmidi.com/zelda-ocarina-of-time-gerudo-theme-mid) does not
  document a percussion study. Treat it as a suspected incomplete or wrongly
  mapped rendition, not a qualified full-theme performance; confirm the source
  and channel assignment before claiming which.

Across the full inventory, 4,343 `MULTI_INSTRUMENT` records have one sounding
channel: 2,347 explicit acoustic-piano palettes, 313 default-piano palettes,
1,521 other single-instrument palettes, 25 changing/multiple palettes, 132
device-dependent palettes and five percussion-only files. These observations
do not justify a mass deletion or a mass `SOLO_PIANO` rewrite.

## Keyboard compatibility and current software gaps

The WK-220 implementation states that bank LSB is ignored and bank selection
takes effect with Program Change. It also distinguishes melodic and drum timbres;
some controls differ between them. [Casio MIDI implementation, sections 9.1,
9.7 and 11](https://support.casio.com/pdf/008/nil%20(MIDI_074M_E_1110A).pdf).
The all-file inventory finds 642 sources with LSB requests and 4,209 with other
unverified bank/kit requests; these sets overlap. Unknown mappings remain unknown
until checked against the exact tone table, not assumed unsupported or silently
replaced. A quality source may remain conditionally compatible on this keyboard.

The current player retains timed channel events and applies selected program
overrides. It blocks SysEx. Its What will play summary exposes sustain and pitch
bend but not the complete controller inventory, sostenuto/soft-pedal behavior,
pressure, RPN/NRPN interpretation, note-release defects, or acoustic realization.
Its simultaneous-note estimate does not model sostenuto, release tails or sample
layers. Those are analysis gaps, not evidence that the underlying files lack
the information or that the engine drops every unlisted controller.

Piano Only changes timbres and suppresses percussion; it does **not** compose a
playable piano reduction or reconstruct missing accompaniment. A better keyboard
can improve sound generation and capacity, but cannot recover notes or musical
parts absent from a file. No fidelity claim is made for the unavailable CT-X700.

## Autonomous decision procedure to implement

Use separately recorded outcomes, with rule/version, evidence references and
confidence, rather than an opaque weighted score:

1. Validate bytes and timing; retain original objects and hashes. Analyze note
   lifecycles with pedal/channel-mode semantics, not a naive note-on/off tally.
2. Identify arrangement intent from source metadata, names and score/source
   bundles. Distinguish full work/movement, piano reduction, accompaniment,
   practice part, loop, exercise and percussion piece. Filename hints alone
   create candidates; corroborated source structure makes decisions.
3. Compare expected essential roles and sections with actual note-bearing parts
   and timelines. Check abrupt endings and long gaps against phrase/score context.
   Do not require drums in classical music or multiple channels in piano music.
4. Assess expression per part and phrase: attack distributions, durations,
   overlaps, timing variation, useful controller changes and pedals. Steady
   timing is valid for some styles; random humanization is not a quality repair.
5. Resolve sound requirements against a versioned device profile. Record what
   is encoded, what the engine sends, what the device supports, and the resulting
   loss separately. A verified alternate mapping can make a source suitable
   without overwriting its original MIDI.
6. Where matching reference score/audio exists, compare arrangement coverage and
   boundaries. A software render can expose silence, balance and truncation,
   but cannot certify the physical Casio's sound. Document which evidence was used.
7. Assign **qualified** only when all essential dimensions have sufficient
   evidence; **conditional** for identified device/arrangement dependencies;
   **unresolved** when evidence is insufficient; **excluded from full-song
   listening** for confirmed fragments, faults or redundant identical playback.
   Preserve distinct expressive performances of the same composition.
8. Keep unresolved/conditional work in an autonomous investigation backlog,
   not a user audition queue. Publish changed admission only from a reproducible,
   reversible manifest; never present unresolved files as verified high quality.

Before deploying a revised cull, run this procedure over both active and archived
material. The old 30-second/64-attack and flat-piano thresholds are household
preferences, not proof of defects, and can produce false exclusions. Calibrate
against identified short complete works, expressive piano, deliberate mechanical
styles, organ, ensemble and confirmed isolated-part examples. Publish decision
changes and reason counts, with no numerical target for the surviving library.

The next implementation work is the expanded controller/note-lifecycle extractor,
source-bundle completeness matching and reasoned per-file decision manifest.
The compatibility preview in this change is useful groundwork, not completion
of that quality-certification pipeline. It leaves the other developer's playlist,
queue, playback-mode, seek, sleep and persistence work untouched.

Reproduce this study with repository dependencies and read access to the library:

```sh
python scripts/audit-library-compatibility.py /path/to/library/catalog.db
python scripts/research-midi-content.py /path/to/library/catalog.db --per-source 24
```

Both scripts are read-only and fail on inspection errors rather than inventing a
quality verdict. The second report contains source URLs and measured facts, not
copied MIDI performances or lyrical text.
