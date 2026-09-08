# Ensemble starter repertoire review

Reviewed 7–8 September 2026 for issue #64. File-level redistribution permission,
arrangement completeness, expression and instrument assignment were checked
separately. The quality thresholds were not relaxed.

## Two additional complete movements

The starter catalog now contains **18 files, including three ensemble entries**:
the existing Bach Air and Donizetti Quartet No. 18 movements I and IV.
The two new files pass `complete-listening-v2`. They are full movements, not the
complete four-movement quartet, and their titles say so.

| Movement | Duration | Notes | Written velocity values by part | GM programs (one-based) |
| --- | ---: | ---: | --- | --- |
| I | 746.5 seconds | 9,027 | 17 / 22 / 9 / 16 | 41 / 41 / 42 / 43 |
| IV | 360 seconds | 5,081 | 17 / 15 / 4 / 3 | 41 / 41 / 42 / 43 |

[Mutopia item 342](https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=342)
identifies the quartet edition, composer, instrumentation, source and Public
Domain status. Its [editor's notes](https://www.mutopiaproject.org/ftp/DonizettiG/quart18/)
explain corrections, articulations and dynamics. Attribution is retained in the
per-file manifest, even though the publisher does not require it for this edition.

The publisher's full-score LilyPond source assigns `cello` to the staff named
`viola`. Its separate viola export uses the correct Viola program. Comparing the
complete sets of note pitches, attacks and releases confirms they are the same
viola part (simultaneous chord order and instrument-scaled velocities differ).

OpenOrchestrion ships **explicit derivatives** that correct the viola track's two
initial program messages and its instrument-name metadata. Every other decoded
event, including notes, velocity, tempo, controllers and delta times, is identical
to the publisher's full-score export. No randomization or invented expression was
added; source originals were not overwritten.

- [Source/derived hashes, exact changes and all 20 ZIP members](../music/starter/donizetti-derivation.json)
- [Qualification facts and publisher evidence](evidence/repertoire/donizetti-quality.json)
- [Offline reproduction script](../scripts/prepare-donizetti-starter.py)

Reproduce from the publisher-linked `quart18-mids.zip` using the script; its
hardcoded researched archive digest rejects changed inputs. Output to a scratch
directory for comparison. Source LilyPond ZIP SHA-256:
`0326f177b0ea5970414a6983c32b835a137b92f5c3afb89aecf4ed7645794800`.

Playback uses two violins, viola and cello on four GM channels. No vendor bank,
external soundfont or second keyboard is required. Qualification is structural and
source-based, not a human listening certificate or a guarantee of acoustic timbre.

## Candidates not admitted

| Candidate | Result |
| --- | --- |
| Bach, Sheep May Safely Graze | Publisher identifies flutes/voice/continuo; MIDI defaults to piano sounds and has insufficient expression. Not admitted. |
| Pachelbel Gigue | Four parts present; insufficient expression. Not admitted. |
| Pachelbel Canon bundle | All five members audited: one full arrangement and four individual practice parts. Full arrangement has one velocity per part and constant volume; parts are incomplete as whole-song arrangements. None admitted. |
| Donizetti movements II and III | Full score exports have insufficient expression under the existing policy. Their separate practice parts are not substitutes. Not admitted. |

These are findings about exact tested exports, not blanket judgments about a
composition or publisher. Canon bundle SHA-256:
`d05d47d19130688728d43476ee30d7e6c41dfc5369e40f2a1dd50a69d389b29c`.

## ZIP workflow is now supported

`openorchestrion-inspect-bundle` audits every member without extracting archive
paths or publishing music. It requires the archive digest and applies member,
compressed/uncompressed byte limits, path/duplicate/symlink and corruption checks.

```sh
openorchestrion-inspect-bundle candidate.zip --expected-sha256 <archive-digest> --output audit.json
```

The existing `openorchestrion-stage-candidate` additionally accepts
`--archive-member`, `--archive-sha256`, `--expected-sha256` (the member digest),
and `--filename`, alongside its normal per-file rights evidence. It audits all
members, stages only the explicitly selected file, and keeps the bundle audit.
It does not combine parts, infer sibling rights, or automatically admit a readable
file as high-quality music. Invalid/empty MIDI siblings block staging until resolved.
