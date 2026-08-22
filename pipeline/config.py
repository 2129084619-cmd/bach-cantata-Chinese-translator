# -*- coding: utf-8 -*-
"""Pipeline configuration — URL templates, paths, constants."""

import os

# ── Workspace root ──
WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# ── Translation output locations ──
# Final translation results (docx/txt) are written under "raw data & all translations",
# NOT the workspace root. "latest translations" mirrors the newest docx + txt.
TRANSLATIONS_DIR = os.path.join(WORKSPACE, 'raw data & all translations')
LATEST_TRANSLATIONS_DIR = os.path.join(WORKSPACE, 'latest translations')

# ── URL Templates ──
URL_BACHCANTATA_TEXTS = 'https://bachcantatatexts.org/BWV{bwv}'
URL_BACH_CANTATAS_BG = 'https://www.bach-cantatas.com/Texts/BWV{bwv}-Eng3.htm'

# Bachipedia (J.S. Bach-Stiftung St. Gallen) — German-language background/readings
URL_BACHIPEDIA = 'https://www.bachipedia.org/werke/bwv-{bwv}/'

# hymnary.org — authoritative chorale metadata (scriptural sources).
# NOTE: protected by an anti-bot challenge; used via WebFetch (AI), not plain requests.
URL_HYMNARY_SEARCH = 'https://hymnary.org/search?qu={query}'

# BibleGateway Luther 1545
URL_BIBLEGATEWAY_LUTHER = (
    'https://www.biblegateway.com/passage/'
    '?search={book_german}+{chapter}%3A{verse}&version=LUTH1545'
)

# BiblePortal Chinese Union Version (CUNPSS)
URL_BIBLEPORTAL_CUV = (
    'https://bibleportal.com/zh-Hans/verse-topic'
    '?v={book}%20{chapter}%3A{verses}&version=CUNPSS'
)

# ── Book name mappings (English reference → German for Luther lookup) ──
BOOK_GERMAN_MAP = {
    'Genesis': '1 Mose', 'Exodus': '2 Mose', 'Leviticus': '3 Mose',
    'Numbers': '4 Mose', 'Deuteronomy': '5 Mose',
    'Joshua': 'Josua', 'Judges': 'Richter', 'Ruth': 'Rut',
    '1 Samuel': '1 Samuel', '2 Samuel': '2 Samuel',
    '1 Kings': '1 Koenige', '2 Kings': '2 Koenige',
    '1 Chronicles': '1 Chronik', '2 Chronicles': '2 Chronik',
    'Ezra': 'Esra', 'Nehemiah': 'Nehemia', 'Esther': 'Ester',
    'Job': 'Hiob', 'Psalms': 'Psalm', 'Psalm': 'Psalm',
    'Proverbs': 'Sprueche', 'Ecclesiastes': 'Prediger',
    'Song of Solomon': 'Hohelied', 'Song of Songs': 'Hohelied',
    'Isaiah': 'Jesaja', 'Jeremiah': 'Jeremia',
    'Lamentations': 'Klagelieder', 'Ezekiel': 'Hesekiel',
    'Daniel': 'Daniel',
    'Hosea': 'Hosea', 'Joel': 'Joel', 'Amos': 'Amos',
    'Obadiah': 'Obadja', 'Jonah': 'Jona', 'Micah': 'Micha',
    'Nahum': 'Nahum', 'Habakkuk': 'Habakuk',
    'Zephaniah': 'Zephanja', 'Haggai': 'Haggai',
    'Zechariah': 'Sacharja', 'Malachi': 'Maleachi',
    'Matthew': 'Matthaeus', 'Mark': 'Markus', 'Luke': 'Lukas',
    'John': 'Johannes', 'Acts': 'Apostelgeschichte',
    'Romans': 'Roemer', '1 Corinthians': '1 Korinther',
    '2 Corinthians': '2 Korinther', 'Galatians': 'Galater',
    'Ephesians': 'Epheser', 'Philippians': 'Philipper',
    'Colossians': 'Kolosser', '1 Thessalonians': '1 Thessalonicher',
    '2 Thessalonians': '2 Thessalonicher',
    '1 Timothy': '1 Timotheus', '2 Timothy': '2 Timotheus',
    'Titus': 'Titus', 'Philemon': 'Philemon',
    'Hebrews': 'Hebraeer', 'James': 'Jakobus',
    '1 Peter': '1 Petrus', '2 Peter': '2 Petrus',
    '1 John': '1 Johannes', '2 John': '2 Johannes',
    '3 John': '3 Johannes', 'Jude': 'Judas',
    'Revelation': 'Offenbarung',
}

# ── German book names (with umlauts, as used by bachipedia.org) → English ──
BOOK_GERMAN_REVERSE_MAP = {
    '1 Mose': 'Genesis', '2 Mose': 'Exodus', '3 Mose': 'Leviticus',
    '4 Mose': 'Numbers', '5 Mose': 'Deuteronomy',
    '1. Mose': 'Genesis', '2. Mose': 'Exodus', '3. Mose': 'Leviticus',
    '4. Mose': 'Numbers', '5. Mose': 'Deuteronomy',
    'Josua': 'Joshua', 'Richter': 'Judges', 'Rut': 'Ruth', 'Ruth': 'Ruth',
    '1 Samuel': '1 Samuel', '2 Samuel': '2 Samuel',
    '1 Könige': '1 Kings', '2 Könige': '2 Kings',
    '1 Koenige': '1 Kings', '2 Koenige': '2 Kings',
    '1 Chronik': '1 Chronicles', '2 Chronik': '2 Chronicles',
    'Esra': 'Ezra', 'Nehemia': 'Nehemiah', 'Ester': 'Esther',
    'Hiob': 'Job', 'Psalm': 'Psalms', 'Psalmen': 'Psalms',
    'Sprüche': 'Proverbs', 'Sprueche': 'Proverbs',
    'Prediger': 'Ecclesiastes', 'Hohelied': 'Song of Solomon',
    'Jesaja': 'Isaiah', 'Jeremia': 'Jeremiah',
    'Klagelieder': 'Lamentations', 'Hesekiel': 'Ezekiel',
    'Daniel': 'Daniel',
    'Hosea': 'Hosea', 'Joel': 'Joel', 'Amos': 'Amos',
    'Obadja': 'Obadiah', 'Jona': 'Jonah', 'Micha': 'Micah',
    'Nahum': 'Nahum', 'Habakuk': 'Habakkuk',
    'Zephanja': 'Zephaniah', 'Haggai': 'Haggai',
    'Sacharja': 'Zechariah', 'Maleachi': 'Malachi',
    'Matthäus': 'Matthew', 'Matthaeus': 'Matthew',
    'Markus': 'Mark', 'Lukas': 'Luke', 'Johannes': 'John',
    'Apostelgeschichte': 'Acts',
    'Römer': 'Romans', 'Roemer': 'Romans',
    '1 Korinther': '1 Corinthians', '2 Korinther': '2 Corinthians',
    'Galater': 'Galatians', 'Epheser': 'Ephesians',
    'Philipper': 'Philippians', 'Kolosser': 'Colossians',
    '1 Thessalonicher': '1 Thessalonians', '2 Thessalonicher': '2 Thessalonians',
    '1 Timotheus': '1 Timothy', '2 Timotheus': '2 Timothy',
    'Titus': 'Titus', 'Philemon': 'Philemon',
    'Hebräer': 'Hebrews', 'Hebraeer': 'Hebrews',
    'Jakobus': 'James', '1 Petrus': '1 Peter', '2 Petrus': '2 Peter',
    '1 Johannes': '1 John', '2 Johannes': '2 John', '3 Johannes': '3 John',
    'Judas': 'Jude', 'Offenbarung': 'Revelation',
}

# ── Chinese book names for BiblePortal lookup ──
BOOK_CHINESE_MAP = {
    'Genesis': '创世记', 'Exodus': '出埃及记', 'Leviticus': '利未记',
    'Numbers': '民数记', 'Deuteronomy': '申命记',
    'Joshua': '约书亚记', 'Judges': '士师记', 'Ruth': '路得记',
    '1 Samuel': '撒母耳记上', '2 Samuel': '撒母耳记下',
    '1 Kings': '列王纪上', '2 Kings': '列王纪下',
    '1 Chronicles': '历代志上', '2 Chronicles': '历代志下',
    'Ezra': '以斯拉记', 'Nehemiah': '尼希米记', 'Esther': '以斯帖记',
    'Job': '约伯记', 'Psalms': '诗篇', 'Psalm': '诗篇',
    'Proverbs': '箴言', 'Ecclesiastes': '传道书',
    'Song of Solomon': '雅歌', 'Song of Songs': '雅歌',
    'Isaiah': '以赛亚书', 'Jeremiah': '耶利米书',
    'Lamentations': '耶利米哀歌', 'Ezekiel': '以西结书',
    'Daniel': '但以理书',
    'Hosea': '何西阿书', 'Joel': '约珥书', 'Amos': '阿摩司书',
    'Obadiah': '俄巴底亚书', 'Jonah': '约拿书', 'Micah': '弥迦书',
    'Nahum': '那鸿书', 'Habakkuk': '哈巴谷书',
    'Zephaniah': '西番雅书', 'Haggai': '哈该书',
    'Zechariah': '撒迦利亚书', 'Malachi': '玛拉基书',
    'Matthew': '马太福音', 'Mark': '马可福音', 'Luke': '路加福音',
    'John': '约翰福音', 'Acts': '使徒行传',
    'Romans': '罗马书', '1 Corinthians': '哥林多前书',
    '2 Corinthians': '哥林多后书', 'Galatians': '加拉太书',
    'Ephesians': '以弗所书', 'Philippians': '腓立比书',
    'Colossians': '歌罗西书', '1 Thessalonians': '帖撒罗尼迦前书',
    '2 Thessalonians': '帖撒罗尼迦后书',
    '1 Timothy': '提摩太前书', '2 Timothy': '提摩太后书',
    'Titus': '提多书', 'Philemon': '腓利门书',
    'Hebrews': '希伯来书', 'James': '雅各书',
    '1 Peter': '彼得前书', '2 Peter': '彼得后书',
    '1 John': '约翰一书', '2 John': '约翰二书',
    '3 John': '约翰三书', 'Jude': '犹大书',
    'Revelation': '启示录',
}

# ── HTTP request settings ──
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,de;q=0.8,zh-CN;q=0.7,zh;q=0.6',
}
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# ── Dialogue Cantata Role Names ──
# Comprehensive list of characters/roles appearing in Bach's dialogue cantatas,
# secular cantatas, and Passions (German names as they appear in lyrics).
# When ANY of these names is detected as a standalone line in the German lyrics,
# the work is treated as a dialogue cantata.
DIALOGUE_ROLE_NAMES = frozenset({
    # === Sacred Dialogue — Soul-Jesus ===
    'Seele',        # Soul (Soprano) — BWV 21, 32, 49, 57, 58, 140, 152
    'Jesus',        # Jesus/Christ (Bass) — all dialogues + Passions
    'Heiland',      # Savior (Bass, alternate for Jesus)
    'Bräutigam',    # Bridegroom (Bass, alternate for Jesus)
    'Braut',        # Bride (Soprano, alternate for Soul)
    'Anima',        # Soul (Latin variant)

    # === Sacred Dialogue — Fear/Hope ===
    'Furcht',       # Fear (Alto) — BWV 60, 66
    'Hoffnung',     # Hope (Tenor) — BWV 60, 66

    # === Sacred — Vox Dei/Christi (voice of God/Christ) ===
    'Vox Dei',      # Voice of God (Bass) — BWV 60
    'Vox Christi',  # Voice of Christ (Bass) — BWV 60, Passions

    # === Passions ===
    'Evangelist',   # Evangelist/Narrator (Tenor) — BWV 244, 245, 247
    'Pilatus',      # Pilate (Bass) — Passions
    'Petrus',       # Peter (Bass) — Passions
    'Ancilla',      # Maid (Soprano) — Passions
    'Servus',       # Servant (Tenor) — Passions
    'Judas',        # Judas (Bass) — Passions
    'Pontifex',     # High Priest — Passions
    'Uxor',         # Pilate's Wife (Soprano) — BWV 244

    # === Secular — BWV 201 (Phoebus and Pan) ===
    'Phoebus',      # Apollo — Bass I
    'Pan',          # Pan — Bass II
    'Momus',        # Momus — Soprano
    'Mercurius',    # Mercury — Alto
    'Tmolus',       # Tmolus — Tenor I
    'Midas',        # Midas — Tenor II

    # === Secular — BWV 205 (Aeolus Placated) ===
    'Pallas',       # Pallas Athena — Soprano
    'Pomona',       # Pomona — Alto
    'Zephyrus',     # Zephyrus — Tenor
    'Zephyr',       # Zephyr (alternate)
    'Aeolus',       # Aeolus — Bass
    'Äolus',        # Aeolus (German spelling)

    # === Secular — BWV 206 (River Cantata) ===
    'Pleisse',      # River Pleiße — Soprano
    'Donau',        # Danube — Alto
    'Elbe',         # Elbe — Tenor
    'Weichsel',     # Vistula — Bass

    # === Secular — BWV 207 / 207a ===
    'Fleiß',        # Industry — Tenor
    'Ehre',         # Honor — Bass
    'Glück',        # Fortune — Soprano
    'Dankbarkeit',  # Gratitude — Alto

    # === Secular — BWV 211 (Coffee Cantata) ===
    'Lieschen',     # Lieschen — Soprano
    'Liesgen',      # Liesgen (alternate)
    'Schlendrian',  # Schlendrian (Father) — Bass

    # === Secular — BWV 213 (Hercules at the Crossroads) ===
    'Herkules',     # Hercules — Alto
    'Tugend',       # Virtue — Tenor
    'Wollust',      # Pleasure — Soprano

    # === Secular — BWV 214 ===
    'Bellona',      # Bellona — Soprano
    'Irene',        # Irene — Alto
    'Fama',         # Fama (Fame) — Tenor

    # === Secular — BWV 216a (Apollo and Mercurius) ===
    'Apollo',       # Apollo
    'Apoll',        # Apollo (alternate)

    # === Secular — BWV 249a (Shepherd Cantata) ===
    'Schäfer',      # Shepherd
    'Schaefer',     # Shepherd (alternate)

    # === Secular — BWV 249b (Celebration of Genius) ===
    'Genius',       # Genius
})

# ── Oratorio / Passion works ──
# Bach's oratorios and Passions use an Evangelist (narrator) and, in the
# Passions, a Christ/character bass. Their UAlberta lyrics mark role labels
# with <em> (voice markers like "Tenor"/"beide") but expose no Persons:
# role→voice map, so step1 supplies a default voice→role map for these works.
ORATORIO_PASSION_BWV = frozenset({
    '11',    # Lobet Gott in seinen Reichen — Ascension Oratorio
    '248',   # Christmas Oratorio (six parts)
    '249',   # Easter Oratorio
    '244',   # St Matthew Passion
    '245',   # St John Passion
})

# Default voice→role map for oratorio/Passion works (when no Persons: map).
# The narrator (Evangelist) is always the Tenor. The Passions' Bass for
# Jesus/Christ is left to DIALOGUE_ROLE_NAMES standalone-name detection rather
# than a blanket voice→role rule — the Oratorios' Bass is a lyric soloist.
ORATORIO_PASSION_VOICE_ROLE = {
    'Tenor': 'Evangelist',
}
