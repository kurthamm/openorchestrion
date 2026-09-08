"""Conservative source-label cleanup, separate from musical qualification.

Never guesses a composer, translates titles, drops numeric version suffixes, or
uses a first instrument/track name as the work title. Original labels survive.
"""
from __future__ import annotations

import html
import re
import unicodedata

IDENTITY_FIELDS = ("source_title", "source_context", "title_status", "metadata_note")
_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);")
_ESCAPES = re.compile(r"(?:%[0-9a-fA-F]{2})+")


def decode_label(value: str) -> str:
    def percent(match):
        raw = bytes.fromhex(match[0].replace("%", ""))
        for encoding in ("utf-8", "cp1252"):
            try:
                decoded = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            if all(unicodedata.category(c) not in {"Cc", "Cs"} for c in decoded):
                return decoded
        return match[0]

    for _ in range(3):
        previous = value
        value = _ENTITY.sub(lambda m: html.unescape(m[0]), value)
        value = _ESCAPES.sub(percent, value)
        if value == previous:
            break
    # Retain international scripts, accents and literal plus signs.
    value = "".join(" " if unicodedata.category(c) == "Cc" else c for c in value)
    return unicodedata.normalize("NFC", " ".join(value.split()))


def source_identity(title: str, *, source: str = "") -> dict[str, str]:
    """Format a publisher/upload label without upgrading identity confidence."""
    original = title
    title = decode_label(title)
    context = ""
    if source.casefold() == "bitmidi":
        title = re.sub(r"\.midi?$", "", title, flags=re.I).replace("_", " ")
        prefix = re.match(r"^(.{2,60}?)\s+-\s+(.+)$", title)
        dotted = re.match(r"^([A-Z][A-Z0-9 &'’.\-]{1,55})\.([A-Z][a-z].+)$", title)
        if prefix or dotted:
            context, title = (prefix or dotted).groups()
        # A run of filename delimiters is distinguishable from a single compound
        # hyphen. Numeric titles/ranges and spaced separators remain intact.
        if len(re.findall(r"(?<=\S)-(?=\S)", title)) >= 2 and len(re.findall(r"[A-Za-z]{2,}", title)) >= 2:
            protected = {}
            for i, match in enumerate(re.finditer(r"(?i)\b(?:Ob-La-Di|Ob-La-Da|Doo-Wop|Jean-Michel|Saint-Saëns)\b", title)):
                protected[f"\ue000{i}\ue001"] = match[0]
            for token, word in protected.items():
                title = title.replace(word, token)
            # Preserve an upload suffix visibly; it is not a new arrangement claim.
            title = re.sub(r"-(\d+)$", r" [\1]", title)
            title = re.sub(r"(?<=\S)-(?=\S)", " ", title)
            for token, word in protected.items():
                title = title.replace(token, word)
        elif re.match(r"^'[Ntnt]-[A-Za-z]", title):
            title = title.replace("-", " ", 1)
        title = re.sub(r"^(\d{1,3},\d{3})(?=[A-Za-z]{3})", r"\1 ", title)
    title = decode_label(title)
    unresolved = bool(
        not title or re.fullmatch(r"[\d\W_]+", title)
        or re.match(r"^\d{6}[- (]", title)
        or re.match(r"^\d+-[A-Za-z]", title)
        or re.match(r"^[\d-]{3,}-[A-Za-z]", title)
        or re.fullmatch(r"(?i)(?:untitled|unknown|track\s*\d*|unnamed|nameless)", title)
    )
    result = {"title": title or "Unidentified performance", "source_title": original,
              "title_status": "unresolved" if unresolved else "source_label"}
    if context:
        result["source_context"] = decode_label(context)
    if unresolved:
        result["metadata_note"] = "Source label retained; work identity is not established."
    return result
