"""Reviewed public source adapters and bounded, host-restricted HTTP access."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import posixpath
import re
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote, quote, urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

AGENT = "OpenOrchestrion/0.1 (+https://github.com/kurthamm/openorchestrion; personal-library acquisition)"


@dataclass(frozen=True)
class Source:
    key: str
    label: str
    seeds: tuple[str, ...]
    hosts: tuple[str, ...]
    prefixes: tuple[str, ...]
    genre: str
    license: str = "unknown"
    license_url: str = ""
    disabled: str = ""


SOURCES = (
    Source(
        "smd",
        "Saarland Music Data v2",
        ("https://www.audiolabs-erlangen.de/resources/MIR/SMD/midi",),
        ("www.audiolabs-erlangen.de",),
        ("/resources/MIR/SMD/", "/content/resources/MIR/SMD/02_midi/data/midi/"),
        "classical",
        "CC-BY-NC-SA-3.0",
        "https://www.audiolabs-erlangen.de/resources/MIR/SMD/midi",
    ),
    Source(
        "classical-archives",
        "Classical Archives — Pierre R. Schwob free collection",
        ("https://www.classicalarchives.com/prs/free.html",),
        ("www.classicalarchives.com",),
        ("/prs/free.html", "/prs/midi_free/"),
        "classical",
        "unknown",
        "https://www.classicalarchives.com/prs/free.html",
    ),
    Source(
        "vgmusic",
        "VGMusic",
        (
            "https://www.vgmusic.com/music/",
            "https://www.vgmusic.com/music/other/miscellaneous/piano/",
        ),
        ("www.vgmusic.com",),
        ("/music/",),
        "game",
        license_url="https://www.vgmusic.com/music/",
    ),
    Source(
        "bitmidi",
        "BitMidi",
        (),
        ("bitmidi.com",),
        ("/",),
        "popular",
        license_url="https://bitmidi.com/about",
        disabled="The download directory /uploads/ is disallowed by the publisher robots policy.",
    ),
    Source(
        "mutopia",
        "Mutopia Project",
        ("https://www.mutopiaproject.org/latestadditions.rss",),
        ("www.mutopiaproject.org",),
        ("/latestadditions.rss", "/cgibin/piece-info.cgi", "/ftp/"),
        "classical",
        license_url="https://www.mutopiaproject.org/",
    ),
    Source(
        "commons",
        "Wikimedia Commons",
        (),
        ("commons.wikimedia.org", "upload.wikimedia.org"),
        ("/w/api.php", "/wikipedia/commons/"),
        "",
        license_url="https://commons.wikimedia.org/wiki/Category:MIDI_files",
        disabled="The tested API route is disallowed by robots policy; previous acquisition also recorded HTTP 429. An approved API access route is required.",
    ),
    Source(
        "midkar",
        "MIDKAR",
        (
            "https://midkar.com/Blues/Blues_MIDIs.html",
            "https://midkar.com/Pop_Rock/Pop_Rock_A_to_Z.html",
        ),
        ("midkar.com", "www.midkar.com"),
        ("/Blues/", "/Pop_Rock/"),
        "popular",
        license_url="https://midkar.com/",
    ),
    Source(
        "piano-midi",
        "Piano MIDI",
        ("https://www.piano-midi.de/",),
        ("www.piano-midi.de",),
        ("/",),
        "classical",
        disabled="TLS certificate verification failed on the Pi; certificates are not bypassed.",
    ),
    Source(
        "kunstderfuge",
        "Kunst der Fuge",
        ("https://kunstderfuge.com/",),
        ("kunstderfuge.com",),
        ("/",),
        "classical",
        disabled="Subscription and daily download limits; not enabled for unattended bulk acquisition.",
    ),
)


def checked_url(source: Source, url: str) -> str:
    p = urlsplit(url)
    if p.scheme == "http" and p.hostname in source.hosts:
        p = p._replace(scheme="https")
    if (
        p.scheme != "https"
        or p.hostname not in source.hosts
        or p.username
        or p.password
        or p.port not in (None, 443)
    ):
        raise ValueError("URL outside reviewed source hosts")
    decoded = unquote(p.path)
    if "\\" in decoded or any(part == ".." for part in decoded.split("/")):
        raise ValueError("unsafe source path")
    if decoded != "/robots.txt" and not any(
        decoded.startswith(prefix) for prefix in source.prefixes
    ):
        raise ValueError("URL outside reviewed source paths")
    return urlunsplit(
        ("https", p.netloc.lower(), quote(decoded, safe="/:@-._~!$&'()*+,;="), p.query, "")
    )


class Redirects(HTTPRedirectHandler):
    def __init__(self, source):
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(
            req, fp, code, msg, headers, checked_url(self.source, newurl)
        )


class Client:
    def __init__(self, source, delay=1.0):
        self.source, self.delay = source, delay
        self.last = 0.0
        self.robots = {}
        self.opener = build_opener(Redirects(source))

    def _request(self, url, limit):
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        with self.opener.open(Request(url, headers={"User-Agent": AGENT}), timeout=20) as response:
            checked_url(self.source, response.url) if not url.endswith("/robots.txt") else None
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("response exceeds size budget")
        return raw

    def get(self, url, limit=4 * 1024 * 1024):
        url = checked_url(self.source, url)
        p = urlsplit(url)
        if p.hostname not in self.robots:
            robots = RobotFileParser()
            try:
                raw = self._request(f"https://{p.netloc}/robots.txt", 65536)
                robots.parse(raw.decode("utf-8", "replace").splitlines())
            except HTTPError as exc:
                if 400 <= exc.code < 500 and exc.code != 429:
                    # RFC 9309: unavailable robots (4xx) does not prohibit access.
                    robots.parse([])
                else:
                    raise
            self.robots[p.hostname] = robots
            self.delay = max(self.delay, robots.crawl_delay(AGENT) or robots.crawl_delay("*") or 0)
        if not self.robots[p.hostname].can_fetch(AGENT, url):
            raise PermissionError("source robots policy disallows this path")
        return self._request(url, limit)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href, self.text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join("".join(self.text).split())))
            self.href = None


def page_links(source, url, raw):
    if source.key == "mutopia" and url.endswith(".rss"):
        links = [
            (i.findtext("link", ""), i.findtext("title", ""))
            for i in ET.fromstring(raw).findall("./channel/item")
        ]
    else:
        parser = Links()
        parser.feed(raw.decode("utf-8", "replace"))
        links = parser.links
    result = []
    for href, title in links[:10000]:
        try:
            target = checked_url(source, urljoin(url, href))
        except ValueError:
            continue
        path = urlsplit(target).path.lower()
        if path.endswith((".mid", ".midi", ".kar")):
            kind = "midi"
        elif path.endswith(("/", ".htm", ".html", ".shtml", ".rss")) or (
            source.key == "mutopia" and "/piece-info.cgi" in path
        ):
            kind = "page"
        else:
            continue
        # Avoid search forms, comments, uploads and arbitrary query-state crawls.
        if urlsplit(target).query and not (
            source.key == "mutopia" and re.fullmatch(r"id=\d+", urlsplit(target).query)
        ):
            continue
        if title.lower() in {"mid", "midi", "download", ""}:
            title = (
                posixpath.basename(unquote(urlsplit(target).path))
                .rsplit(".", 1)[0]
                .replace("_", " ")
            )
        result.append({"url": target, "kind": kind, "title": title[:200], "reference": url})
    return result


def api_page(source, client, cursor):
    if source.key == "bitmidi":
        page = int(cursor or "0")
        url = f"https://bitmidi.com/api/midi/all?page={page}&pageSize=100"
        result = json.loads(client.get(url))["result"]
        items = [
            {
                "url": checked_url(source, urljoin(url, row["downloadUrl"])),
                "kind": "midi",
                "title": row["name"].rsplit(".", 1)[0][:200],
                "reference": urljoin(url, row["url"]),
            }
            for row in result["results"]
        ]
        return items, str(page + 1 if page < result["pageTotal"] else 0), url
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": "Category:MIDI files",
        "gcmtype": "file",
        "gcmlimit": 50,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "format": "json",
    }
    if cursor:
        params["gcmcontinue"] = cursor
    url = "https://commons.wikimedia.org/w/api.php?" + urlencode(params)
    result = json.loads(client.get(url))
    if "error" in result:
        raise ValueError("Commons API: " + str(result["error"]))
    items = []
    for row in result.get("query", {}).get("pages", {}).values():
        for info in row.get("imageinfo", []):
            if urlsplit(info["url"]).path.lower().endswith((".mid", ".midi")):
                items.append(
                    {
                        "url": checked_url(source, info["url"]),
                        "kind": "midi",
                        "title": row["title"].removeprefix("File:").rsplit(".", 1)[0][:200],
                        "reference": info.get("descriptionurl", url),
                    }
                )
    return items, result.get("continue", {}).get("gcmcontinue", ""), url
