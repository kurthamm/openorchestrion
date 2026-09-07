"""Rebuild descriptive metadata for every asset from analysis + source facts."""

import collections
import csv
import re
import sys
from pathlib import Path

S = Path(sys.argv[1])
rows = list(csv.DictReader(open(S / "oo-analysis.csv")))

# ---- composer dates ----
DATES = {}
for line in (S / "mutopia-composers.tsv").read_text().splitlines():
    code, name = line.split("\t", 1)
    m = re.search(r"\((\d{4}|[0-9?]+)\s*[–-]\s*(\d{4}|[0-9?]*)\)", name)
    b = int(m.group(1)) if m and m.group(1).isdigit() else None
    d = int(m.group(2)) if m and m.group(2).isdigit() else None
    DATES[re.sub(r"\s*\(.*\)\s*$", "", name).strip().lower()] = (b, d)
FULL = {
    "Johann Sebastian Bach": (1685, 1750),
    "Ludwig van Beethoven": (1770, 1827),
    "Wolfgang Amadeus Mozart": (1756, 1791),
    "Frédéric Chopin": (1810, 1849),
    "Scott Joplin": (1868, 1917),
    "Claude Debussy": (1862, 1918),
    "Erik Satie": (1866, 1925),
    "Franz Schubert": (1797, 1828),
    "Johannes Brahms": (1833, 1897),
    "Joseph Haydn": (1732, 1809),
    "George Frideric Handel": (1685, 1759),
    "Domenico Scarlatti": (1685, 1757),
    "Robert Schumann": (1810, 1856),
    "Franz Liszt": (1811, 1886),
    "Pyotr Ilyich Tchaikovsky": (1840, 1893),
    "Antonio Vivaldi": (1678, 1741),
    "Edvard Grieg": (1843, 1907),
    "Felix Mendelssohn": (1809, 1847),
    "Muzio Clementi": (1752, 1832),
    "Carl Czerny": (1791, 1857),
    "Anton Diabelli": (1781, 1858),
    "Maurice Ravel": (1875, 1937),
    "Henry Purcell": (1659, 1695),
    "François Couperin": (1668, 1733),
    "Jean-Philippe Rameau": (1683, 1764),
    "Georg Philipp Telemann": (1681, 1767),
    "Johann Pachelbel": (1653, 1706),
    "Friedrich Burgmüller": (1806, 1874),
    "Clara Schumann": (1819, 1896),
    "Antonín Dvořák": (1841, 1904),
    "George Gershwin": (1898, 1937),
    "Isaac Albéniz": (1860, 1909),
    "Enrique Granados": (1867, 1916),
    "John Field": (1782, 1837),
    "Stephen Heller": (1813, 1888),
    "Friedrich Kuhlau": (1786, 1832),
    "Fernando Sor": (1778, 1839),
    "Mikhail Ippolitov-Ivanov": (1859, 1935),
    "Nikolai Rimsky-Korsakov": (1844, 1908),
    "Camille Saint-Saëns": (1835, 1921),
    "Franz Xaver Gruber": (1787, 1863),
    "Alban Berg": (1885, 1935),
    "Alexander Scriabin": (1872, 1915),
    "Antonio Soler": (1729, 1783),
    "Carl Maria von Weber": (1786, 1826),
    "César Franck": (1822, 1890),
    "George Enescu": (1881, 1955),
    "Leoš Janáček": (1854, 1928),
    "Mily Balakirev": (1837, 1910),
    "Modest Mussorgsky": (1839, 1881),
    "Nikolai Medtner": (1880, 1951),
    "Orlando Gibbons": (1583, 1625),
    "Percy Grainger": (1882, 1961),
    "Sergei Rachmaninoff": (1873, 1943),
    "Mikhail Glinka": (1804, 1857),
    "Johann Strauss": (1825, 1899),
    "Georges Bizet": (1838, 1875),
    "Giuseppe Verdi": (1813, 1901),
    "Richard Wagner": (1813, 1883),
    "Niccolò Paganini": (1782, 1840),
}


def dates(composer):
    if not composer:
        return (None, None)
    if composer in FULL:
        return FULL[composer]
    return DATES.get(composer.lower(), (None, None))


def era_for(composer, style):
    if composer.lower() in ("anonymous", "traditional", ""):
        return (
            style
            if style in ("renaissance", "baroque", "classical", "romantic", "modern", "medieval")
            else "traditional"
        )
    b, d = dates(composer)
    if b is None and d is None:
        return (
            style
            if style in ("renaissance", "baroque", "classical", "romantic", "modern", "medieval")
            else ""
        )
    if b is None:
        b = d - 60
    if b < 1400:
        return "medieval"
    if b < 1560:
        return "renaissance"
    if b < 1700:
        return "baroque"
    if b < 1780:
        return "classical"
    if b < 1870:
        return "romantic"
    if b < 1930:
        return "modern"
    return "contemporary"


FORMS = [  # (regex on title, genre)
    (r"\bsonat", "sonata"),
    (r"\bpr[ée]lud", "prelude"),
    (r"\bfug|\bfuga", "fugue"),
    (r"\btoccat", "toccata"),
    (r"\b(etude|étude|study|studies|exercise|übung|technique)", "etude"),
    (r"\bnocturn|\bnotturn", "nocturne"),
    (r"\b(waltz|valse|walzer)", "waltz"),
    (r"\bmarch|\bmarcia|\bmarsch", "march"),
    (r"\b(minuet|menuet|menuett)", "minuet"),
    (r"\bpolonais", "polonaise"),
    (r"\bmazurk", "mazurka"),
    (
        r"\b(gigue|allemande|courante|sarabande|gavotte|bourr[ée]e|passepied|rigaudon)",
        "baroque dance",
    ),
    (r"\bsuite\b|\bpartita", "suite"),
    (r"\bvariation", "variations"),
    (r"\brondo", "rondo"),
    (r"\bscherzo", "scherzo"),
    (r"\bimpromptu", "impromptu"),
    (r"\bballad", "ballade"),
    (r"\bintermezzo", "intermezzo"),
    (r"\brhapsod", "rhapsody"),
    (r"\bfantas", "fantasia"),
    (r"\bcanon\b", "canon"),
    (r"\bchoral", "chorale"),
    (r"\bhymn|\bchorale prelude", "hymn"),
    (
        r"\b(carol|christmas|noel|noël|weihnacht|nativity|silent night|stille nacht|adeste)",
        "christmas",
    ),
    (
        r"\b(mass|missa|kyrie|gloria|credo|sanctus|agnus|magnificat|requiem|motet|cantata|oratorio|psalm|te deum|ave maria|stabat mater|anthem|jesu|alleluia|hallelujah)",
        "sacred",
    ),
    (r"\b(aria|arie|song|lied|lieder|chanson|canzon|air\b)", "song"),
    (r"\bopera|\bopéra|\bsingspiel", "opera"),
    (r"\b(symphon|sinfoni)", "symphony"),
    (r"\bconcert", "concerto"),
    (r"\b(overture|ouverture|ouvertüre)", "overture"),
    (r"\b(quartet|quartett|trio|quintet|quintett|sextet|octet)", "chamber"),
    (r"\brag\b|\bragtime|\brags\b", "ragtime"),
    (r"\bjazz|\bblues|\bswing|\bboogie", "jazz"),
    (r"\bfolk|\bvolkslied|\btraditional", "folk"),
    (r"\b(lullaby|berceuse|wiegenlied|cradle)", "lullaby"),
    (r"\bserenad", "serenade"),
    (r"\btango", "tango"),
    (r"\bpolka", "polka"),
    (r"\bbarcarol", "barcarolle"),
    (r"\b(funeral|funèbre|trauer|lament|elegy|élégie)", "elegy"),
    (r"\b(wedding|bridal|hochzeit)", "wedding"),
    (r"\binvention|\bsinfonia\b", "invention"),
    (r"\bgymnop|\bgnossien", "impressionist"),
]
FAMOUS = [
    r"f[üu]r elise",
    r"moonlight",
    r"clair de lune",
    r"canon in d|pachelbel",
    r"ode to joy",
    r"eine kleine",
    r"turkish|alla turca",
    r"gymnop[ée]die",
    r"maple leaf",
    r"entertainer",
    r"air on the g|bwv 1068",
    r"prelude in c|bwv 846",
    r"toccata and fugue|bwv 565",
    r"four seasons|spring|autumn|winter|summer",
    r"blue danube",
    r"nutcracker",
    r"hallelujah",
    r"jesu, joy|jesu joy",
    r"ave maria",
    r"minuet in g",
    r"swan lake",
    r"william tell",
    r"carmen",
    r"bol[ée]ro",
    r"path[ée]tique",
    r"appassionata",
    r"raindrop",
    r"minute waltz",
    r"fantaisie-impromptu",
    r"heroic|héroïque",
    r"revolutionary",
    r"la campanella",
    r"liebestraum",
    r"hungarian rhapsody",
    r"rhapsody in blue",
    r"trois gymnop",
    r"arabesque",
    r"rêverie|reverie",
    r"golliwog",
    r"dance of the sugar",
    r"flight of the bumble",
    r"in the hall of the mountain",
    r"morning mood",
    r"wedding march",
    r"bridal",
    r"greensleeves",
    r"scarborough",
    r"amazing grace",
    r"silent night|stille nacht",
    r"jingle bells",
    r"o holy night",
    r"joy to the world",
    r"hark",
    r"deck the hall",
    r"twinkle",
    r"happy birthday",
    r"star.spangled",
    r"la marseillaise",
    r"god save",
    r"pomp and circumstance",
    r"trumpet voluntary",
    r"spring song",
    r"solfeggietto",
    r"invention no. 1\b|bwv 772",
    r"goldberg",
    r"well.tempered",
    r"brandenburg",
    r"eroica",
    r"symphony no\.? 5\b",
    r"symphony no\.? 9\b",
    r"new world",
    r"unfinished",
    r"jupiter",
    r"surprise symphony",
    r"nocturne in e",
    r"op\. 9 no\. 2",
    r"islamey",
]
MAJOR = {
    "Johann Sebastian Bach",
    "Ludwig van Beethoven",
    "Wolfgang Amadeus Mozart",
    "Frédéric Chopin",
    "Scott Joplin",
    "Claude Debussy",
    "Franz Schubert",
    "Johannes Brahms",
    "Joseph Haydn",
    "George Frideric Handel",
    "Pyotr Ilyich Tchaikovsky",
    "Antonio Vivaldi",
    "Franz Liszt",
    "Robert Schumann",
    "Felix Mendelssohn",
    "Edvard Grieg",
    "Erik Satie",
    "Sergei Rachmaninoff",
    "Antonín Dvořák",
    "George Gershwin",
    "Maurice Ravel",
}


def keyboardish_hint(fam):
    return bool(fam) and set(fam) <= {"piano", "harpsichord", "guitar", "chamber", "strings"}


def families(instr, perf):
    t = (instr or "").lower()
    fam = []

    def add(x):
        if x not in fam:
            fam.append(x)

    if "orchestra" in t:
        add("orchestra")
    if re.search(r"\bpiano|pianoforte|fortepiano", t) or perf in (
        "SOLO_PIANO",
        "PIANO_DUET",
        "TWO_PIANO",
    ):
        add("piano")
    if "organ" in t:
        add("organ")
    if re.search(r"harpsichord|clavecin|cembalo|clavichord|virginal", t):
        add("harpsichord")
    if re.search(r"guitar|lute|theorbo|vihuela|mandolin", t):
        add("guitar")
    if re.search(r"violin|viola|cello|bass|gamba|string", t) and "orchestra" not in fam:
        add("strings")
    if (
        re.search(
            r"flute|recorder|oboe|clarinet|bassoon|piccolo|horn|trumpet|trombone|tuba|brass|wind", t
        )
        and "orchestra" not in fam
    ):
        add("winds")
    if re.search(r"voice|soprano|alto|tenor|bass\b|choir|chorus|satb|vocal|castrat|singer", t):
        add("voice")
    if re.search(r"quartet|trio|quintet|sextet|ensemble|consort", t) or (
        "strings" in fam and len(fam) > 1
    ):
        add("chamber")
    if re.search(r"drum|percussion|timpani", t):
        add("percussion")
    return fam or (["piano"] if perf else [])


out = []
for r in rows:
    title = r["title"] or ""
    tl = title.lower()
    composer = r["composer"] or ""
    src = r["source_label"]
    style = (r["era"] or "").lower()
    instr = r["instrumentation"] or ""
    perf = r["performance_type"] or ""
    era = era_for(composer, style)
    fam = families(instr, perf)
    genres = []

    def g(x):
        if x and x not in genres:
            genres.append(x)

    art = (
        src in ("Mutopia Project", "MAESTRO v3.0.0 (International Piano-e-Competition)")
        or composer in MAJOR
        or era in ("baroque", "classical", "romantic", "renaissance", "medieval", "modern")
    )
    if art:
        g("classical")
    for pat, genre in FORMS:
        if re.search(pat, tl):
            g(genre)
    if style in ("hymn", "folk", "march", "song", "jazz", "ragtime", "gospel"):
        g(style)
    if style == "popular / dance":
        g("popular")
        g("dance")
    if style == "technique":
        g("etude")
    if "orchestra" in fam:
        g("orchestral")
    if "chamber" in fam:
        g("chamber")
    if "voice" in fam:
        g("vocal")
    if (
        "organ" in fam
        and "sacred" not in genres
        and "hymn" not in genres
        and "chorale" not in genres
    ):
        g("organ music")
    if "guitar" in fam:
        g("guitar")
    if "piano" in fam and len(fam) == 1:
        g("solo piano" if perf == "SOLO_PIANO" else "piano")
    if "ragtime" in genres:
        g("jazz")
    if era in ("renaissance", "medieval"):
        g("early music")
    # energy from note density
    try:
        dur = float(r["duration_seconds"] or 0)
        notes = int(r["note_count"] or 0)
        dens = notes / dur if dur else 0
    except ValueError:
        dens = 0
    energy = 1 if dens < 2 else 2 if dens < 4 else 3 if dens < 7 else 4 if dens < 11 else 5
    if re.search(r"\b(adagio|largo|lento|andante|nocturn|lullaby|berceuse|pavan)", tl):
        energy = min(energy, 2)
    if re.search(r"\b(presto|vivace|allegro|toccata|rag\b|tarantell|galop)", tl):
        energy = max(energy, 4 if dens >= 4 else 3)
    moods = []

    def m(x):
        if x not in moods:
            moods.append(x)

    if energy <= 2:
        m("calm")
        m("relaxed")
        m("gentle")
    elif energy == 3:
        m("warm")
        m("flowing")
        if keyboardish_hint(fam):
            m("relaxed")
    elif energy == 4:
        m("lively")
        m("bright")
    else:
        m("fiery")
        m("exhilarating")
    if re.search(
        r"nocturn|lullaby|berceuse|adagio|largo|lento|r[êe]verie|clair de lune|gymnop", tl
    ):
        m("tender")
        m("dreamy")
    if "elegy" in genres or re.search(r"requiem|lament", tl):
        m("solemn")
        m("mournful")
    if "march" in genres:
        m("stately")
    if "christmas" in genres:
        m("festive")
    if re.search(r"minuet|menuet|gavotte|waltz|valse", tl):
        m("elegant")
    if "ragtime" in genres or "polka" in genres:
        m("playful")
    if "jazz" in genres and "ragtime" not in genres:
        m("cool")
    if "fugue" in genres or "toccata" in genres or "invention" in genres:
        m("intricate")
    if "sacred" in genres or "hymn" in genres or "chorale" in genres:
        m("reverent")
    if ("symphony" in genres or "overture" in genres or "concerto" in genres) and energy >= 3:
        m("majestic")
    themes = []

    def t_(x):
        if x not in themes:
            themes.append(x)

    keyboardish = fam and set(fam) <= {"piano", "harpsichord", "guitar", "chamber", "strings"}
    if art and keyboardish and energy <= 3:
        t_("dinner")
    if art and keyboardish and energy <= 2:
        t_("relax")
    if era in ("baroque", "classical") and keyboardish and energy <= 3:
        t_("study")
    if "ragtime" in genres or "jazz" in genres or "popular" in genres:
        t_("cocktail")
    if ("popular" in genres or "dance" in genres or "polka" in genres) and energy >= 4:
        t_("party")
    if "christmas" in genres:
        t_("christmas")
    if (
        "sacred" in genres
        or "hymn" in genres
        or "chorale" in genres
        or ("organ" in fam and "orchestra" not in fam)
    ):
        t_("church")
    if "wedding" in genres or re.search(
        r"canon in d|ave maria|air on the g|trumpet voluntary|bridal", tl
    ):
        t_("wedding")
    if (
        energy >= 5
        or "etude" in genres
        or "toccata" in genres
        or re.search(r"virtuos|campanella|islamey|transcendental", tl)
    ):
        t_("showpiece")
    if "lullaby" in genres or re.search(r"twinkle|nursery|children|kinder", tl):
        t_("kids")
    if re.search(r"anthem|national|star.spangled|marseillaise|god save|hymne", tl):
        t_("patriotic")
    if "orchestra" in fam or "symphony" in genres or "overture" in genres:
        t_("concert hall")
    if "MAESTRO" in src:
        t_("concert hall")
        t_("recital")
    fam_score = (
        5
        if any(re.search(p, tl) for p in FAMOUS)
        else (4 if composer in MAJOR and "MAESTRO" in src else 3 if composer in MAJOR else 2)
    )
    if "MAESTRO" in src:
        quality = "A"
    elif src == "Mutopia Project":
        quality = "C"
    else:
        quality = ""
    out.append(
        dict(
            sha256=r["sha256"],
            era=era,
            genres=",".join(genres),
            moods=",".join(moods),
            themes=",".join(themes),
            instrumentation=",".join(fam),
            familiarity=str(fam_score),
            energy=str(energy),
            quality_grade=quality,
        )
    )
with open(S / "tags-curated.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)

print(len(out), "rows")
for k in ("era", "genres", "moods", "themes", "instrumentation"):
    c = collections.Counter(v for o in out for v in o[k].split(",") if v)
    print(k, len(c), "values:", c.most_common(18))
print("energy:", collections.Counter(o["energy"] for o in out))
print("familiarity:", collections.Counter(o["familiarity"] for o in out))
