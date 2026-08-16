# -*- coding: utf-8 -*-
"""Step 3.5: Chorale → Bible scripture fuzzy search.

Goal (per policy 2026-08-16): for each chorale used in a cantata, determine the
chorale's scriptural writing source (e.g. "Ach Gott, vom Himmel sieh darein" ←
Psalm 12; "Wie schön leuchtet der Morgenstern" ← Psalm 45 / Song of Songs), and
feed those references into the Bible manifest.

Resolution order (fast → slow):
  1. Local curated table `CHORALE_SCRIPTURE_MAP` (instant, no network).
  2. Regex parse of the chorale data `author`/`description` fields
     (e.g. "Philipp Nicolai, based on Psalm 45").
  3. Cross-search bach-cantatas.com chorale detail pages for "based on Psalm N"
     (one cached HTTP request per unknown chorale).
  4. hymnary.org (authoritative) is protected by an anti-bot challenge, so it is
     NOT fetched here; the AI may use WebFetch as a last-resort fallback.

All resolved sources are cached to
`巴赫康塔塔中的众赞歌/chorale_bible_sources.json` so subsequent runs are cheap.
"""

import json
import os
import re

import requests
import urllib3

from . import config
from .logger import get_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = get_logger()

# Cache file lives in the chorale subsystem data directory (relative to workspace)
_CHORALE_DIR = os.path.join(config.WORKSPACE, '巴赫康塔塔中的众赞歌')
_CACHE_PATH = os.path.join(_CHORALE_DIR, 'chorale_bible_sources.json')


# ═══════════════════════════════════════════════════════════════
# 1. Curated scriptural-source table (well-known Bach chorales)
#    Key = normalized distinctive title substring (lowercase).
# ═══════════════════════════════════════════════════════════════
CHORALE_SCRIPTURE_MAP = {
    'wie schön leuchtet der morgenstern': [
        ('Psalms', 45, '1-17'), ('Song of Solomon', 1, '1-17'),
    ],
    'ach gott vom himmel sieh darein': [('Psalms', 12, '1-8')],
    'wachet auf ruft uns die stimme': [
        ('Matthew', 25, '1-13'), ('Song of Solomon', 5, '2'),
    ],
    'jesu meine freude': [('Romans', 8, '1-39')],
    'christ lag in todesbanden': [('1 Corinthians', 5, '7'), ('Luke', 24, '1-12')],
    'ein feste burg ist unser gott': [('Psalms', 46, '1-11')],
    'es ist genug': [('1 Kings', 19, '4')],
    'herzlich lieb hab ich dich o herr': [('Psalms', 18, '1-50')],
    'wer nur den lieben gott lässt walten': [('Psalms', 55, '22')],
    'was mein gott will das gscheh allzeit': [('Matthew', 26, '39')],
    'mit fried und freud ich fahr dahin': [('Luke', 2, '29-32')],
    'allein gott in der höh sei ehr': [('Luke', 2, '14')],
    'komm heiliger geist herre gott': [('Acts', 2, '1-4')],
    'nun bitten wir den heiligen geist': [('Acts', 2, '1-4')],
    'aus tiefer not schrei ich zu dir': [('Psalms', 130, '1-8')],
    'ach herr mich armen sünder': [('Psalms', 6, '1-10')],
    'befiehl du deine wege': [('Psalms', 37, '5')],
    'gelobet seist du jesu christ': [('Luke', 2, '1-20')],
    'o haupt voll blut und wunden': [('Matthew', 27, '27-31')],
    'christus der uns selig macht': [('Matthew', 26, '1-75')],
    'nun komm der heiden heiland': [
        ('Isaiah', 7, '14'), ('Matthew', 1, '18-25'), ('Luke', 1, '26-38'),
    ],
    'vater unser im himmelreich': [('Matthew', 6, '9-13')],
    'herr jesu christ du höchstes gut': [('Psalms', 51, '1-19')],
    'werde munter mein gemüte': [('Psalms', 42, '1-11')],
    'machs mit mir gott nach deiner güt': [('Psalms', 51, '1-19')],
    'was frag ich nach der welt': [('1 John', 2, '15-17')],
    'ich bin ein rechter weinstock': [('John', 15, '1-8')],
    'wenn wir in höchsten nöten sein': [('Psalms', 130, '1-8')],
    'komm gott schöpfer heiliger geist': [('Genesis', 1, '1-2'), ('Acts', 2, '1-4')],
    'nun lob mein seel den herren': [('Psalms', 103, '1-22')],
    'o lamm gottes unschuldig': [('John', 1, '29')],
    'christe du lamm gottes': [('John', 1, '29')],
    'herr wie du willst so schicks mit mir': [('Matthew', 26, '39')],
    'warum betrübst du dich mein herz': [('Psalms', 42, '1-11')],
    'wär gott nicht mit uns diese zeit': [('Psalms', 124, '1-8')],
    'war gott nicht mit uns diese zeit': [('Psalms', 124, '1-8')],
    'wo gott der herr nicht bei uns hält': [('Psalms', 124, '1-8')],
    'ich ruf zu dir herr jesu christ': [('Psalms', 130, '1-8')],
    'schmücke dich o liebe seele': [('Luke', 14, '16-24')],
    'du friedenfürst herr jesu christ': [('Isaiah', 9, '6')],
    'o gott du frommer gott': [('Psalms', 145, '1-21')],
    'nun freut euch lieben christen gmein': [('Romans', 3, '21-28')],
    'erhalt uns herr bei deinem wort': [('2 Thessalonians', 3, '1-3')],
    'o heiliger geist kehr bei uns ein': [('John', 14, '16-17')],
    'herr gott dich loben wir': [('Isaiah', 6, '1-3')],
    'nun danket alle gott': [('Psalms', 107, '1')],
}


# ═══════════════════════════════════════════════════════════════
# 2. Normalization + regex extraction
# ═══════════════════════════════════════════════════════════════

def _normalize(title):
    """Normalize a title for matching: lowercase, strip punctuation/diacritics."""
    if not title:
        return ''
    t = title.lower()
    # Transliterate common German umlauts / ß for matching robustness
    for a, b in [('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 'ss'),
                 ('é', 'e'), ('è', 'e'), ('â', 'a')]:
        t = t.replace(a, b)
    # Collapse any non-alphanumeric run to a single space
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return ' '.join(t.split())


def _lookup_curated(title):
    """Return curated scripture refs for a title via substring matching."""
    norm = _normalize(title)
    if not norm:
        return []
    for key, refs in CHORALE_SCRIPTURE_MAP.items():
        nkey = _normalize(key)
        if nkey in norm or norm in nkey:
            return [{'book': b, 'chapter': c, 'verse': v, 'source': 'chorale:curated'}
                    for b, c, v in refs]
    return []


# "based on / after / nach / auf Psalm 12" — chapter-only or chapter:verse
_PSALM_RE = re.compile(
    r'(?:based\s+on|after|from|nach|auf|nach\s+d.|nach\s+dem)\s+'
    r'(?:dem\s+|den\s+)?(?:Psalm|Psalter)\s+(\d+)\s*(?:[:.,]\s*(\d+(?:\s*[-–]\s*\d+)?))?',
    re.IGNORECASE
)
# Generic "based on <Book> N:M" (English book names)
_GENERIC_BASED_RE = re.compile(
    r'(?:based\s+on|after|from)\s+'
    r'(1\s*Corinthians|2\s*Corinthians|1\s*Samuel|2\s*Samuel|1\s*Kings|2\s*Kings|'
    r'Song\s+of\s+(?:Solomon|Songs)|Revelation|Isaiah|Jeremiah|Matthew|Mark|Luke|'
    r'John|Acts|Romans|Genesis|Exodus|Psalms?)'
    r'\s+(\d+)\s*:\s*(\d+(?:\s*[-–]\s*\d+)?)',
    re.IGNORECASE
)


def _extract_from_text(text):
    """Extract scripture references from arbitrary text (author/description)."""
    if not text:
        return []
    refs = []
    seen = set()

    def _add(book, chapter, verse):
        key = (book, int(chapter), verse or '')
        if key in seen:
            return
        seen.add(key)
        refs.append({'book': book, 'chapter': int(chapter), 'verse': verse or '',
                     'source': 'chorale:author'})

    for m in _PSALM_RE.finditer(text):
        _add('Psalms', m.group(1), m.group(2) or '')
    for m in _GENERIC_BASED_RE.finditer(text):
        book = m.group(1).strip()
        if book.lower() in ('psalm', 'psalms'):
            book = 'Psalms'
        _add(book, m.group(2), m.group(3))

    return refs


# ═══════════════════════════════════════════════════════════════
# 3. Persistent cache
# ═══════════════════════════════════════════════════════════════

def _load_cache():
    if os.path.exists(_CACHE_PATH):
        try:
            with open(_CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# 4. Cross-search bach-cantatas.com chorale detail page
# ═══════════════════════════════════════════════════════════════

def _fetch_bachcantatas_chorale(chorale_id, detail_url=None):
    """Fetch a bach-cantatas.com chorale detail page and extract scripture hints.

    The detail pages carry an "Author:" line like
      "Author: Philipp Nicolai, based on Psalm 45"
    which is a reliable scriptural-source signal.
    """
    url = detail_url or f'https://www.bach-cantatas.com/Texts/{chorale_id}-Eng3.htm'
    try:
        resp = requests.get(url, headers=config.HEADERS,
                            timeout=config.REQUEST_TIMEOUT, verify=False)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'
    except requests.RequestException:
        return []

    text = re.sub(r'<[^>]+>', ' ', resp.text)
    text = re.sub(r'&nbsp;|&amp;', ' ', text)
    return _extract_from_text(text)


# ═══════════════════════════════════════════════════════════════
# 5. Resolution + entry point
# ═══════════════════════════════════════════════════════════════

def _load_chorale_data(chorale_id):
    path = os.path.join(_CHORALE_DIR, 'data', f'{chorale_id}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def resolve_chorale_scripture(chorale_id, chorale_data=None, title=None, detail_url=None):
    """Resolve the scriptural writing source(s) of a single chorale.

    Returns list of ref dicts: {book, chapter, verse, source}.
    """
    if chorale_data is None:
        chorale_data = _load_chorale_data(chorale_id)

    title = title or (chorale_data or {}).get('title', '')
    detail_url = detail_url or (chorale_data or {}).get('source_url', '')

    cache = _load_cache()
    if chorale_id in cache:
        return cache[chorale_id]

    refs = _lookup_curated(title)
    if not refs:
        author = (chorale_data or {}).get('author', '') or ''
        description = (chorale_data or {}).get('description', '') or ''
        refs = _extract_from_text(author + ' | ' + description)
    if not refs and detail_url:
        refs = _fetch_bachcantatas_chorale(chorale_id, detail_url)

    cache[chorale_id] = refs
    _save_cache(cache)
    return refs


def _find_chorale_ids(bwv):
    """Find the chorale IDs used by a BWV via chorale_index.json bwv_lookup."""
    index_path = os.path.join(_CHORALE_DIR, 'chorale_index.json')
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            idx = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    bwv_str = str(bwv)
    chorales = idx.get('chorales', [])
    # Prefer explicit bwv_lookup; fall back to scanning bwv_usages.
    ids = []
    for i in idx.get('bwv_lookup', {}).get(bwv_str, []):
        if i < len(chorales):
            ids.append(chorales[i].get('chorale_id', ''))
    if not ids:
        for c in chorales:
            for u in c.get('bwv_usages', []):
                if str(u.get('bwv', '')) == bwv_str:
                    ids.append(c.get('chorale_id', ''))
                    break
    return [i for i in dict.fromkeys(ids) if i]


def run(bwv, metadata=None, folder_path=None):
    """Execute Step 3.5: resolve chorale scriptural sources → Bible references.

    Args:
        bwv: int or str
        metadata: optional dict from step2 (may contain 'chorale_ids')
        folder_path: optional, unused (kept for API symmetry)

    Returns:
        list of reference dicts {book, chapter, verse, source}
    """
    bwv_str = str(bwv)
    chorale_ids = (metadata or {}).get('chorale_ids', []) or []
    if not chorale_ids:
        chorale_ids = _find_chorale_ids(bwv_str)
    if not chorale_ids:
        return []

    refs = []
    seen = set()
    for cid in chorale_ids:
        cdata = _load_chorale_data(cid)
        for r in resolve_chorale_scripture(cid, cdata):
            key = (r['book'], r['chapter'], r.get('verse', ''))
            if key in seen:
                continue
            seen.add(key)
            refs.append(r)

    log.info(f"[Step 3.5] Chorale scripture: {len(chorale_ids)} chorales → "
             f"{len(refs)} Bible references")
    return refs
