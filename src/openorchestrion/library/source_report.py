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
* for a page, the **lines that mention terms** — licence, copyright, permission,
  attribution and related evidence;
* separately, the **lines that mention instrumentation/arrangement**, so an
  ensemble score can be distinguished from a keyboard reduction without letting
  scoring text masquerade as rights evidence;
* for a page, the **links that lead to item records or MIDI files**, because
  finding the record is the step before reading it and a browse listing carries
  that entirely in its markup.

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
from urllib.parse import urljoin

from openorchestrion.midi.analyzer import analyze_midi

#: Words that mark a line as worth a curator's attention when researching terms.
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

#: Scoring/arrangement clues. Kept out of TERM_KEYWORDS deliberately: a page that
#: says only ``Instrument(s): Piano`` has told us nothing about redistribution.
INSTRUMENTATION_KEYWORDS: tuple[str, ...] = (
    "instrument",
    "scored for",
    "arrangement",
    "arranged",
    "for orchestra",
    "voice",
)

#: Link targets worth showing: an item record to read, or a file to fetch.
#:
#: A browse listing is almost entirely navigation, so an unfiltered link dump is
#: as unreadable as the raw page. These are the two things a curator is ever
#: looking for on the way to a claim.
LINK_PATTERNS: tuple[str, ...] = (
    "piece-info",
    "/ftp/",
    "file:",
    ".mid",
    ".midi",
)

_SCRIPTISH = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
_BLOCK_END = re.compile(r"</(p|div|tr|li|h[1-6]|table|br)\s*>|<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t ]+")
_VOICE_WORD = re.compile(r"\bvoices?\b", re.IGNORECASE)

DEFAULT_MAX_LINES = 60
DEFAULT_MAX_LINKS = 40


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


def _matches_keyword(lowered: str, keyword: str) -> bool:
    # ``voice`` is a normal English word rather than an intentional stem. A
    # substring check would classify ``invoice`` as instrumentation and could
    # consume a capped report slot. Plural ``voices`` remains useful evidence.
    if keyword == "voice":
        return _VOICE_WORD.search(lowered) is not None
    return keyword in lowered


def _matching_lines(
    lines: list[str],
    keywords: tuple[str, ...],
    *,
    max_lines: int,
) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        lowered = line.casefold()
        if not any(_matches_keyword(lowered, keyword) for keyword in keywords):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        kept.append(line)
        if len(kept) >= max_lines:
            break
    return kept


def term_lines(lines: list[str], *, max_lines: int = DEFAULT_MAX_LINES) -> list[str]:
    """Lines relevant to rights/provenance research, without repeats.

    Instrumentation is intentionally excluded. Its own extract cannot suppress
    the no-rights warning or consume this quota before a later copyright line.
    """
    return _matching_lines(lines, TERM_KEYWORDS, max_lines=max_lines)


def instrumentation_lines(
    lines: list[str],
    *,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[str]:
    """Lines that describe scoring/arrangement, independently capped."""
    return _matching_lines(lines, INSTRUMENTATION_KEYWORDS, max_lines=max_lines)


def item_links(
    payload: bytes,
    *,
    base_url: str | None = None,
    max_links: int = DEFAULT_MAX_LINKS,
) -> list[str]:
    """Links on a page that lead to an item record or a MIDI file.

    Resolved against ``base_url`` when one is given, because a listing states its
    links relatively and a curator has to be able to dispatch the next fetch with
    what the report printed, not with a path they have to reassemble by hand.
    """
    text = payload.decode("utf-8", errors="replace")
    seen: set[str] = set()
    found: list[str] = []
    for match in _HREF.finditer(text):
        href = html.unescape(next(group for group in match.groups() if group is not None)).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        lowered = href.casefold()
        if not any(pattern in lowered for pattern in LINK_PATTERNS):
            continue
        resolved = urljoin(base_url, href) if base_url else href
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append(resolved)
        if len(found) >= max_links:
            break
    return found


def summarize(
    payload: bytes,
    *,
    url: str | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_links: int = DEFAULT_MAX_LINKS,
) -> str:
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

    terms = term_lines(lines, max_lines=max_lines)
    if terms:
        report.append("")
        report.append(f"lines mentioning terms ({len(terms)}):")
        report.extend(f"  | {line}" for line in terms)
    else:
        report.append("")
        report.append(
            "no line mentions licence, copyright or permission. That is not a "
            "clean result — it usually means the terms live on a linked page, or "
            "this is not the item record."
        )

    instrumentation = instrumentation_lines(lines, max_lines=max_lines)
    if instrumentation:
        report.append("")
        report.append(f"lines mentioning instrumentation ({len(instrumentation)}):")
        report.extend(f"  | {line}" for line in instrumentation)

    links = item_links(payload, base_url=url, max_links=max_links)
    if links:
        report.append("")
        report.append(f"links to item records or files ({len(links)}):")
        report.extend(f"  - {link}" for link in links)

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
        help=f"Cap on each extracted terms/instrumentation section (default {DEFAULT_MAX_LINES})",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=DEFAULT_MAX_LINKS,
        help=f"Cap on reported links (default {DEFAULT_MAX_LINKS})",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    source = Path(args.file)
    if not source.is_file():
        print(f"error: {source} does not exist", file=sys.stderr)
        raise SystemExit(2)
    print(
        summarize(
            source.read_bytes(),
            url=args.url,
            max_lines=args.max_lines,
            max_links=args.max_links,
        )
    )


if __name__ == "__main__":
    main()
