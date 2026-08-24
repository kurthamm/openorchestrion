"""``openorchestrion-inspect-source`` — read an archive item record without committing anything.

Establishing a file's terms means reading the page that states them. When the
machine doing the curation cannot reach the archive, those terms cannot be read
at all — and guessing them is the one thing curation must never do. A plausible
licence written into a manifest looks exactly like a verified one.

This is the read-only half of :mod:`openorchestrion.library.acquire`. The fetch
job downloads a candidate and writes a branch; this one downloads a page and
writes nothing, so it can run with ``contents: read`` and produce evidence a
curator transcribes by hand rather than anything the repository acts on
automatically.

Nothing here touches the network either. Given bytes, it reports what a curator
needs to see before making a claim:

* the **digest and size**, so the researched file and the fetched file can be
  tied together later;
* whether the bytes are **readable MIDI with notes**, since archives serve error
  pages with ``.mid`` names when a link rots;
* for a page, the **lines that mention terms** — licence, copyright, permission —
  because an item record is mostly navigation and the four lines that matter are
  buried in it.

The extract is a reading aid, never a verdict. It cannot tell whether a licence
applies to the file or to the engraving beside it, so it deliberately reports
lines rather than concluding anything: a human still reads them and decides.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from pathlib import Path

from openorchestrion.midi.analyzer import analyze_midi

#: Words that mark a line as worth a curator's attention on an item record.
#:
#: Deliberately broad. A missed line costs a second look at the page; a filter
#: tuned so finely that it drops the one sentence reserving rights would leave a
#: curator reading a clean-looking extract of a page that is not clean at all.
TERM_KEYWORDS: tuple[str, ...] = (
    "licen",  # licence, license, licensed, licensing
    "copyright",
    "public domain",
    "creative commons",
    "cc0",
    "cc by",
    "cc-by",
    "share-alike",
    "sharealike",
    "attribution",
    "all rights reserved",
    "non-commercial",
    "noncommercial",
    "permission",
    "may not",
    "free for",
    "personal use",
    "typeset",
    "maintainer",
    "composer",
    "date of composition",
    "source edition",
    "publisher",
)

_SCRIPTISH = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_END = re.compile(r"</(p|div|tr|li|h[1-6]|table|br)\s*>|<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t ]+")

DEFAULT_MAX_LINES = 60


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def looks_binary(payload: bytes) -> bool:
    """Whether these bytes are a file rather than a page.

    A NUL byte in the first block is the practical test: text/HTML does not
    contain one, and every binary format this project cares about does.
    """
    return b"\x00" in payload[:8192]


def text_lines(payload: bytes) -> list[str]:
    """Readable lines from a page, with markup and blank runs removed."""
    text = payload.decode("utf-8", errors="replace")
    text = _SCRIPTISH.sub(" ", text)
    text = _BLOCK_END.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)

    lines: list[str] = []
    for raw in text.splitlines():
        line = _SPACES.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return lines


def term_lines(lines: list[str], *, max_lines: int = DEFAULT_MAX_LINES) -> list[str]:
    """The subset of lines that mention terms, in page order and without repeats.

    Repeats are dropped because archive pages state the same licence in a
    sidebar, a footer and a metadata table; three copies of one sentence pushes
    the sentence that differs off the end of a capped extract.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        lowered = line.casefold()
        if not any(keyword in lowered for keyword in TERM_KEYWORDS):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        kept.append(line)
        if len(kept) >= max_lines:
            break
    return kept


def summarize(payload: bytes, *, url: str | None = None, max_lines: int = DEFAULT_MAX_LINES) -> str:
    """A curator-facing report on downloaded bytes: what they are, and what they say."""
    report: list[str] = []
    if url:
        report.append(f"url:      {url}")
    report.append(f"sha256:   {_digest(payload)}")
    report.append(f"size:     {len(payload)} bytes")

    if not payload:
        report.append("content:  empty response — nothing was served")
        return "\n".join(report)

    if looks_binary(payload):
        report.append("content:  binary")
        report.extend(_music_report(payload))
        return "\n".join(report)

    report.append("content:  text")
    lines = text_lines(payload)
    report.append(f"lines:    {len(lines)} readable")

    found = term_lines(lines, max_lines=max_lines)
    if found:
        report.append("")
        report.append(f"lines mentioning terms ({len(found)}):")
        report.extend(f"  | {line}" for line in found)
    else:
        report.append("")
        report.append(
            "no line mentions licence, copyright or permission. That is not a "
            "clean result — it usually means the terms live on a linked page, or "
            "this is not the item record."
        )

    report.append("")
    report.append(
        "Read these lines yourself before recording a claim. They are an extract, "
        "not a verdict: an item record often states terms for the engraving, the "
        "score and the MIDI separately, and only one of those is the file."
    )
    return "\n".join(report)


def _music_report(payload: bytes) -> list[str]:
    """What the bytes are as music, if they are music at all."""
    import tempfile

    with tempfile.TemporaryDirectory() as workspace:
        scratch = Path(workspace) / "payload.mid"
        scratch.write_bytes(payload)
        try:
            analysis = analyze_midi(scratch)
        except Exception as exc:  # noqa: BLE001 - any parse failure is the same answer
            return [f"midi:     not readable as MIDI ({type(exc).__name__}: {exc})"]

    if not analysis.note_count:
        return ["midi:     parses, but contains no notes"]
    return [
        f"midi:     {analysis.note_count} notes, {analysis.duration_seconds:.1f}s, "
        f"peak {analysis.peak_simultaneous_notes} voices"
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-inspect-source",
        description=(
            "Report what a downloaded archive page or file contains, so a curator can "
            "read the terms that apply to it. Writes nothing and decides nothing."
        ),
    )
    parser.add_argument("--file", required=True, help="The downloaded payload to report on")
    parser.add_argument("--url", help="Where it came from, echoed into the report")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Cap on extracted term lines (default {DEFAULT_MAX_LINES})",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    source = Path(args.file)
    if not source.is_file():
        print(f"error: {source} does not exist", file=sys.stderr)
        raise SystemExit(2)
    print(summarize(source.read_bytes(), url=args.url, max_lines=args.max_lines))


if __name__ == "__main__":
    main()
