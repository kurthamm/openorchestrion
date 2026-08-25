"""Reading an archive item record well enough to record a claim from it.

The report exists because the alternative to reading a licence page is guessing
at it, and a guessed licence is indistinguishable from a verified one once it is
written into a manifest. So the interesting cases here are not the happy path but
the ways an extract could mislead: a restrictive sentence dropped because a
sidebar repeated a permissive one, a page whose terms are simply absent reported
as though it were clean, or an error page treated as music.

Like the staging tests, none of these touch a network. The report is a pure
function of bytes; only the download is in the job.
"""

from __future__ import annotations

from pathlib import Path

from openorchestrion.library.source_report import (
    instrumentation_lines,
    item_links,
    looks_binary,
    summarize,
    term_lines,
    text_lines,
)
from openorchestrion.testing.midi_fixtures import generate_suite

ITEM_RECORD = b"""<html>
  <head><title>Piece Info</title><style>.x { color: red }</style></head>
  <body>
    <script>var licence = "not this one";</script>
    <table>
      <tr><td>Composer:</td><td>Johann Sebastian Bach</td></tr>
      <tr><td>Date of composition:</td><td>1722</td></tr>
      <tr><td>Typeset by:</td><td>A. Contributor</td></tr>
      <tr><td>Copyright:</td><td>Creative Commons Attribution-ShareAlike 4.0</td></tr>
    </table>
    <p>Navigation, unrelated text, and a search box.</p>
    <div>Copyright: Creative Commons Attribution-ShareAlike 4.0</div>
    <p>The recording on this page is &copy; 2019 and all rights reserved.</p>
  </body>
</html>
"""


def test_markup_and_scripts_do_not_reach_the_reader() -> None:
    lines = text_lines(ITEM_RECORD)
    joined = "\n".join(lines)

    assert "<td>" not in joined
    assert "var licence" not in joined, "script bodies are not page text"
    assert "color: red" not in joined, "style bodies are not page text"
    assert "Composer: Johann Sebastian Bach" in joined


def test_block_boundaries_keep_fields_apart() -> None:
    # Without splitting on block ends, a whole table collapses into one line and
    # a capped extract shows a single unreadable smear instead of four fields.
    lines = text_lines(ITEM_RECORD)
    assert any(line.startswith("Date of composition:") for line in lines)
    assert any(line.startswith("Typeset by:") for line in lines)


def test_repeated_statements_are_shown_once() -> None:
    found = term_lines(text_lines(ITEM_RECORD))
    copyright_lines = [line for line in found if "ShareAlike" in line]
    assert len(copyright_lines) == 1


def test_a_reservation_of_rights_is_not_dropped_behind_a_permissive_line() -> None:
    # The failure that matters: a page that says both things, extracted so that
    # only the reassuring half survives.
    found = "\n".join(term_lines(text_lines(ITEM_RECORD)))
    assert "all rights reserved" in found.casefold()


def test_the_extract_is_capped_without_silently_pretending_to_be_complete() -> None:
    page = b"<p>" + b"</p><p>".join(
        f"Licence note number {index}".encode() for index in range(50)
    ) + b"</p>"
    found = term_lines(text_lines(page), max_lines=5)
    assert len(found) == 5


def test_a_page_stating_no_terms_is_reported_as_a_problem_not_a_pass() -> None:
    report = summarize(b"<html><body><p>Search results for Bach</p></body></html>")
    assert "no line mentions licence" in report
    assert "not a clean result" in report


def test_binary_is_detected_and_reported_as_music(tmp_path: Path) -> None:
    generate_suite(tmp_path)
    payload = sorted(tmp_path.glob("*.mid"))[0].read_bytes()

    assert looks_binary(payload)
    report = summarize(payload, url="https://example.invalid/x.mid")
    assert "content:  binary" in report
    assert "notes," in report
    assert "peak" in report


def test_an_error_page_named_mid_is_not_mistaken_for_music() -> None:
    # Archives serve HTML with .mid names when a link rots. Reported as text with
    # no terms, which is exactly what it is.
    report = summarize(b"<html><body>404 Not Found</body></html>")
    assert "content:  text" in report
    assert "midi:" not in report


def test_truncated_midi_reports_the_parse_failure_rather_than_a_note_count() -> None:
    report = summarize(b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0MTrk\x00\x00\x00")
    assert "not readable as MIDI" in report


def test_the_digest_is_reported_so_research_can_be_tied_to_bytes() -> None:
    report = summarize(b"hello")
    # sha256("hello")
    assert "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" in report


def test_the_report_says_it_is_an_extract_rather_than_a_verdict() -> None:
    report = summarize(ITEM_RECORD)
    assert "not a verdict" in report


def test_an_empty_response_is_named_as_such() -> None:
    assert "empty response" in summarize(b"")


LISTING = b"""<html><body>
  <a href="#top">Skip</a>
  <a href="/cgibin/piece-info.cgi?id=931">Fur Elise</a>
  <a href='/cgibin/piece-info.cgi?id=1778'>Clair de lune</a>
  <a href="/cgibin/piece-info.cgi?id=931">Fur Elise (again, in a sidebar)</a>
  <a href="/ftp/BachJS/BWV846/prelude/prelude.mid">Download MIDI</a>
  <a href="/about.html">About this archive</a>
  <a href="javascript:void(0)">Menu</a>
</body></html>
"""


def test_links_to_records_and_files_are_reported() -> None:
    links = item_links(LISTING, base_url="https://www.mutopiaproject.org/browse.html")

    assert "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=931" in links
    assert "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1778" in links
    assert "https://www.mutopiaproject.org/ftp/BachJS/BWV846/prelude/prelude.mid" in links


def test_navigation_is_not_reported_as_a_candidate() -> None:
    links = item_links(LISTING, base_url="https://www.mutopiaproject.org/browse.html")

    assert not any("about.html" in link for link in links)
    assert not any(link.startswith("javascript") for link in links)
    assert not any(link.endswith("#top") for link in links)


def test_a_repeated_link_is_listed_once() -> None:
    links = item_links(LISTING, base_url="https://www.mutopiaproject.org/browse.html")
    assert sum(1 for link in links if link.endswith("id=931")) == 1


def test_links_are_absolute_so_the_next_dispatch_needs_no_reassembly() -> None:
    # A relative href printed as-is cannot be handed to the fetch workflow, whose
    # host allowlist requires a full HTTPS URL.
    links = item_links(LISTING, base_url="https://www.mutopiaproject.org/browse.html")
    assert all(link.startswith("https://") for link in links)


def test_the_link_list_is_capped() -> None:
    page = b"".join(
        f'<a href="/cgibin/piece-info.cgi?id={index}">x</a>'.encode() for index in range(100)
    )
    assert len(item_links(page, max_links=7)) == 7


def test_a_listing_reports_its_links_in_the_summary() -> None:
    report = summarize(LISTING, url="https://www.mutopiaproject.org/browse.html")
    assert "links to item records or files" in report
    assert "piece-info.cgi?id=1778" in report


ENSEMBLE_RECORD = b"""<html><body>
  <table>
    <tr><td>Title:</td><td>Air</td></tr>
    <tr><td>Instrument(s):</td><td>2 Violins, Viola, Cello, Continuo</td></tr>
    <tr><td>Arrangement:</td><td>original scoring, not a keyboard reduction</td></tr>
    <tr><td>Copyright:</td><td>Public Domain</td></tr>
  </table>
</body></html>
"""


def test_instrumentation_is_reported_separately_from_terms() -> None:
    lines = text_lines(ENSEMBLE_RECORD)
    instrumentation = "\n".join(instrumentation_lines(lines))
    terms = "\n".join(term_lines(lines))

    assert "2 Violins, Viola, Cello, Continuo" in instrumentation
    assert "not a keyboard reduction" in instrumentation
    assert "Public Domain" not in instrumentation
    assert "Public Domain" in terms


def test_instrumentation_only_does_not_suppress_the_no_rights_warning() -> None:
    page = b"<html><body><p>Instrument(s): Piano</p></body></html>"
    report = summarize(page)

    assert "lines mentioning instrumentation" in report
    assert "Instrument(s): Piano" in report
    assert "no line mentions licence" in report
    assert "not a clean result" in report


def test_instrumentation_cannot_crowd_out_a_later_rights_line() -> None:
    page = b"""<html><body>
      <p>Instrument(s): Violin</p>
      <p>Arrangement: orchestra</p>
      <p>Scored for voices and strings</p>
      <p>Copyright: Public Domain</p>
    </body></html>"""
    report = summarize(page, max_lines=1)

    assert "Copyright: Public Domain" in report
    assert "lines mentioning terms (1)" in report
    assert "lines mentioning instrumentation (1)" in report


def test_voice_matches_as_a_word_not_inside_invoice() -> None:
    lines = ["Invoice number 42", "Voices: soprano and alto"]
    found = instrumentation_lines(lines)

    assert "Invoice number 42" not in found
    assert "Voices: soprano and alto" in found
