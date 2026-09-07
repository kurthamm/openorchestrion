"""Curated tags for the BitMidi set from file names and play counts."""

import csv
import json
import re
import sys
import collections
from pathlib import Path

S = Path(sys.argv[1])
B = S / "staged/bitmidi"
tags = list(csv.DictReader(open(B / "tags.csv")))
index = {e["id"]: e for e in json.load(open(B / "index.json"))}
man = {r["sha256"]: r for r in csv.DictReader(open(B / "catalog.csv"))}
GAME = r"mario|zelda|pok[ée]mon|final fantasy|sonic|tetris|mega ?man|castlevania|kirby|donkey kong|metroid|street fighter|chrono|halo|doom|zelda|earthbound|animal crossing|minecraft|undertale|pikmin|star fox|metal gear|kingdom hearts|dragon quest|secret of mana|banjo|f-zero|smash bros|wii|nintendo|sega|megaman|touhou|persona|pac-?man|duck tales|ducktales|contra|tekken|mortal kombat|portal|skyrim|elder scrolls|warcraft|starcraft|diablo|guild wars|runescape|terraria|silent hill|resident evil|bomberman|kid icarus|yoshi|wario|luigi"
FILM = r"star wars|titanic|pirates of the caribbean|harry potter|indiana jones|jurassic|lord of the rings|hobbit|mission impossible|james bond|godfather|rocky|top gun|batman|superman|spider-?man|ghostbusters|back to the future|jaws|e\.t\.|et theme|forrest gump|gladiator|braveheart|schindler|lion king|aladdin|beauty and the beast|little mermaid|frozen|disney|pocahontas|mulan|toy story|nightmare before|halloween|psycho|exorcist|matrix|terminator|alien|predator|star trek|dr\.? who|x-?files|twilight zone|simpsons|family guy|south park|futurama|friends|seinfeld|cheers|mash|muppet|sesame|flintstones|jetsons|scooby|looney|pink panther|inspector gadget|knight rider|a-team|magnum|miami vice|dallas|dynasty|twin peaks|game of thrones|sopranos|west wing|law & order|er theme|amelie|cinema paradiso|godfather|chariots of fire|moon river|somewhere over the rainbow|singin. in the rain|my heart will go on|circle of life|hakuna|can you feel the love|whole new world|let it go|beauty and the beast|colors of the wind|sound of music|mary poppins|wizard of oz|willy wonka|grease|dirty dancing|footloose|flashdance|fame\b|ghost\b|unchained melody|top gun|danger zone|eye of the tiger|axel f|beverly hills|ninja turtles|power rangers|transformers|thundercats|he-man|pokemon theme|anime|naruto|dragon ?ball|sailor moon|evangelion|cowboy bebop|ghibli|totoro|spirited away|howl"
XMAS = r"christmas|xmas|jingle|silent night|noel|santa|rudolph|frosty|deck the hall|joy to the world|hark|o holy night|little drummer|sleigh|winter wonderland|let it snow|white christmas|feliz navidad|carol|wenceslas|adeste|o come|silver bells|nutcracker"
CLASSICAL = r"beethoven|mozart|bach|chopin|tchaikovsky|vivaldi|handel|haydn|schubert|brahms|liszt|debussy|ravel|satie|grieg|dvorak|dvořák|mendelssohn|schumann|rachmaninoff|rachmaninov|strauss|wagner|verdi|puccini|rossini|bizet|pachelbel|elgar|holst|mussorgsky|rimsky|prokofiev|shostakovich|stravinsky|mahler|bruckner|sibelius|saint-saens|offenbach|paganini|scarlatti|albinoni|purcell|orff|barber|copland|gershwin|joplin|sousa|khachaturian|borodin|glinka|smetana|faure|fauré|massenet|delibes|gounod|ponchielli|boccherini|clementi|czerny|telemann|corelli|monteverdi|palestrina|tallis|byrd|canon in d|moonlight sonata|fur elise|für elise|ode to joy|eine kleine|nocturne|symphony|concerto|sonata|prelude|fugue|etude|waltz of the flowers|blue danube|william tell|1812|swan lake|ride of the valkyries|hallelujah chorus|ave maria|clair de lune|gymnopedie|bolero|carmina|air on|toccata|pomp and circumstance|adagio|requiem|carmen|la traviata|nessun dorma|barber of seville|figaro|magic flute|habanera|hungarian|polovtsian|sabre dance|flight of the bumble|peer gynt|hall of the mountain|finlandia|planets|pictures at an exhibition|night on bald|scheherazade|four seasons|brandenburg|goldberg|well-tempered|jesu|sheep may|arioso|minuet|sarabande|gavotte|rondo|turkish march|alla turca|appassionata|pathetique|waldstein|tempest|emperor|eroica|pastoral|jupiter|unfinished|new world|trout|winterreise|erlk|liebestraum|campanella|rhapsody|polonaise|mazurka|ballade|scherzo|impromptu|fantaisie|revolutionary|raindrop|minute waltz|heroic|military|funeral|nutcracker|sugar plum|dance of the|hebrides|wedding march|spring song|songs without words|rhapsody in blue|american in paris|entertainer|maple leaf|rag\b"
JAZZ = r"jazz|blues|swing|boogie|ellington|glenn miller|sinatra|armstrong|basie|benny goodman|coltrane|miles davis|monk|brubeck|take five|gershwin|cole porter|irving berlin|nat king cole|ella fitzgerald|billie holiday|dave brubeck|herbie|charlie parker|dizzy|mingus|bossa|jobim|girl from ipanema|autumn leaves|fly me to the moon|summertime|misty|satin doll|in the mood|sing sing sing|caravan|mack the knife|what a wonderful world|georgia on my mind|ain.t misbehavin|stormy weather|all of me|blue moon|body and soul|round midnight|so what|take the a train|moonlight serenade|chattanooga|string of pearls|pennsylvania 6|american patrol|little brown jug"
COUNTRY = r"johnny cash|garth brooks|shania|dolly parton|willie nelson|hank williams|patsy cline|kenny rogers|alan jackson|george strait|reba|brooks & dunn|dixie chicks|tim mcgraw|faith hill|toby keith|kenny chesney|alabama|country|bluegrass|achy breaky|jolene|ring of fire|folsom|country roads|rhinestone|stand by your man|crazy\b|friends in low places|boot scootin|cotton eye joe|devil went down"
LATIN = r"tango|salsa|samba|bossa|mambo|cha cha|merengue|bachata|cumbia|santana|ricky martin|shakira|gipsy kings|buena vista|besame|la bamba|macarena|livin. la vida|guantanamera|oye como va|smooth|maria maria|la cucaracha|cielito|quizas|desafinado|mas que nada|lambada|copacabana|conga|gloria estefan|selena|julio iglesias|enrique"
ROCK = r"beatles|rolling stones|led zeppelin|pink floyd|queen|nirvana|metallica|ac.?dc|guns n|aerosmith|bon jovi|u2|coldplay|radiohead|oasis|green day|foo fighters|red hot chili|pearl jam|soundgarden|alice in chains|van halen|def leppard|kiss\b|deep purple|black sabbath|iron maiden|judas priest|rush\b|yes\b|genesis|eagles|fleetwood|dire straits|bruce springsteen|tom petty|bob dylan|neil young|the who|kinks|doors|hendrix|cream|clapton|zz top|lynyrd|allman|journey|boston|kansas|foreigner|styx|reo|toto|chicago|steely dan|police|sting|elvis|chuck berry|buddy holly|beach boys|creedence|ccr|santana|scorpions|europe\b|whitesnake|motley|poison|skid row|weezer|blink|offspring|sum 41|linkin park|limp bizkit|korn|slipknot|system of a down|rammstein|muse|arctic monkeys|killers|strokes|white stripes|black keys|kings of leon|evanescence|nickelback|3 doors|creed|smashing pumpkins|stone temple|bush\b|live\b|collective soul|hootie|goo goo|matchbox|third eye|counting crows|wallflowers|semisonic|fastball|barenaked|blur|pulp|suede|verve|stone roses|smiths|cure|depeche|new order|joy division|siouxsie|echo|simple minds|tears for fears|duran|spandau|human league|eurythmics|culture club|wham|a-ha|alphaville|modern talking|bangles|go-go|blondie|talking heads|ramones|clash|sex pistols|buzzcocks|jam\b|specials|madness|police|dexys|soft cell|yazoo|omd|ultravox|visage|japan\b|roxy|bowie|t\. ?rex|slade|sweet|mud|bay city|abba|boney|bee gees|carpenters|bread|america\b|crosby|simon|garfunkel|cat stevens|james taylor|carole king|joni|don mclean|american pie|hotel california|stairway|bohemian|smoke on the water|sweet child|november rain|nothing else matters|enter sandman|wonderwall|creep|zombie|losing my religion|everybody hurts|with or without you|one\b|beautiful day|yellow|clocks|fix you|smells like teen|come as you are|jeremy|black\b|alive|even flow|hey jude|let it be|yesterday|imagine|here comes the sun|something|come together|help|satisfaction|paint it black|angie|wild horses|comfortably numb|wish you were here|another brick|money|time\b|us and them|great gig|brain damage|eclipse|shine on|echoes|dogs|sheep|pigs|hey you|mother|goodbye blue|run like hell|final cut|learning to fly|high hopes|kashmir|whole lotta|black dog|rock and roll|immigrant|since i.ve been|ramble on|going to california|over the hills|the rain song|no quarter|the ocean|ten years gone|achilles|nobody.s fault|in the evening|fool in the rain|all my love"
POP = r"michael jackson|madonna|prince|whitney|mariah|celine|elton john|billy joel|phil collins|george michael|lionel richie|stevie wonder|marvin gaye|diana ross|supremes|temptations|four tops|jackson 5|earth, wind|kool|chic\b|donna summer|gloria gaynor|village people|bee gees|abba|cher\b|tina turner|janet|paula abdul|debbie gibson|tiffany|new kids|backstreet|nsync|n sync|britney|christina|spice girls|take that|boyzone|westlife|robbie|savage garden|hanson|ace of base|roxette|no doubt|alanis|sheryl|jewel|sarah mclachlan|natalie|fiona|tori|sinead|dido|nelly furtado|shakira|beyonce|beyoncé|destiny|tlc|en vogue|boyz ii|all-4-one|color me badd|bobby brown|new edition|jodeci|r\. kelly|usher|brandy|monica|aaliyah|toni braxton|babyface|boyz|rihanna|lady gaga|katy perry|taylor swift|adele|bruno mars|justin|ed sheeran|maroon 5|coldplay|onerepublic|imagine dragons|twenty one|lorde|sia\b|ellie|calvin harris|avicii|david guetta|daft punk|chemical brothers|prodigy|fatboy|moby|underworld|faithless|orbital|basement jaxx|groove armada|jamiroquai|robert miles|children\b|sandstorm|darude|scooter|vengaboys|aqua\b|barbie girl|eiffel 65|blue\b|whigfield|corona|2 unlimited|snap|culture beat|haddaway|what is love|la bouche|real mccoy|dr\. alban|ace of base|rednex|cotton eye|mr\. president|coco jamboo|lou bega|mambo no|las ketchup|o-zone|dragostea|crazy frog|gigi|cascada|basshunter|dj sammy|alice deejay|atb|9pm|paul van dyk|tiesto|tiësto|armin|ferry corsten|above & beyond|kylie|jason donovan|rick astley|never gonna|stock aitken|bananarama|mel & kim|sonia|big fun|brother beyond|pet shop|erasure|bronski|communards|frankie goes|relax\b|two tribes|power of love|holly johnson|dead or alive|you spin me|kajagoogoo|too shy|nik kershaw|howard jones|paul young|nick heyward|haircut|thompson twins|blancmange|heaven 17|abc\b|the look of love|spandau|true\b|gold\b|through the barricades"


def classify(name, plays):
    t = name.lower()
    genres, themes, moods = [], [], []

    def add(lst, x):
        if x not in lst:
            lst.append(x)

    add(genres, "popular")
    if re.search(GAME, t):
        add(genres, "video game")
        add(themes, "game night")
        add(themes, "kids")
    if re.search(FILM, t):
        add(genres, "film & tv")
        add(themes, "movie night")
    if re.search(XMAS, t):
        add(genres, "christmas")
        add(themes, "christmas")
        add(moods, "festive")
    if re.search(CLASSICAL, t):
        add(genres, "classical")
        add(themes, "dinner")
    if re.search(JAZZ, t):
        add(genres, "jazz")
        add(themes, "cocktail")
        add(moods, "cool")
    if re.search(COUNTRY, t):
        add(genres, "country")
        add(themes, "road trip")
    if re.search(LATIN, t):
        add(genres, "latin")
        add(themes, "party")
        add(moods, "lively")
    if re.search(ROCK, t):
        add(genres, "rock")
        add(themes, "party")
    if re.search(POP, t):
        add(genres, "pop")
        add(themes, "party")
    if re.search(r"disney", t):
        add(genres, "disney")
        add(themes, "kids")
    if re.search(r"anthem|national", t):
        add(genres, "anthem")
        add(themes, "patriotic")
    if re.search(r"hymn|gospel|amazing grace|how great thou|praise|worship|jesus|hallelujah", t):
        add(genres, "hymn")
        add(themes, "church")
        add(moods, "reverent")
    if re.search(r"wedding|bridal|canon in d|ave maria|here comes the bride", t):
        add(themes, "wedding")
    if re.search(r"love|heart|kiss|tonight|baby|forever|romance|romantic", t):
        add(moods, "romantic")
    if re.search(r"happy|fun|party|dance|celebrat|jump|shake", t):
        add(moods, "upbeat")
    if re.search(r"sad|tears|cry|goodbye|lonely|alone|blue\b", t):
        add(moods, "melancholy")
    if len(genres) == 1:
        add(themes, "background")
    if not moods:
        add(moods, "upbeat" if re.search(r"dance|rock|party", t) else "easygoing")
    fam = 5 if plays > 100000 else 4 if plays > 20000 else 3 if plays > 5000 else 2
    return genres, moods, themes, fam


out = []
for r in tags:
    entry = index.get(str(Path(man[r["sha256"]]["path"]).stem), {"name": r["title"], "plays": 0})
    genres, moods, themes, fam = classify(entry["name"], int(entry.get("plays") or 0))
    composer = r["composer"]
    artist = r["artist"]
    m = re.search(CLASSICAL.split("|nocturne")[0], entry["name"].lower())
    if "classical" in genres and not composer and artist:
        composer, artist = artist, ""
    out.append(
        dict(
            sha256=r["sha256"],
            title=r["title"],
            composer=composer,
            artist=artist,
            era="",
            performance_type="MULTI_INSTRUMENT",
            genres=",".join(genres),
            moods=",".join(moods),
            themes=",".join(themes),
            instrumentation="",
            familiarity=str(fam),
            energy="",
            quality_grade="B",
        )
    )
with open(B / "tags-curated.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
c = collections.Counter(g for o in out for g in o["genres"].split(","))
print(len(out), "rows; genres:", c.most_common(14))
print(
    "themes:",
    collections.Counter(g for o in out for g in o["themes"].split(",") if g).most_common(10),
)
