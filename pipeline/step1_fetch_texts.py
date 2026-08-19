# -*- coding: utf-8 -*-
"""Step 1: Fetch structured data from bachcantatatexts.org JSON API.

Uses the JSON endpoint (e.g., https://bachcantatatexts.org/BWV1.json)
which returns perfectly structured data including:
  - bwv_num, work_name, work_occasion, work_author, work_translators
  - movements[] with de/en text per movement
  - notes[] with numbered footnotes

This is much more reliable than HTML parsing.
"""

import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

from . import config
from .logger import get_logger

log = get_logger()


def _fetch_json(bwv_number):
    """Fetch structured JSON data from bachcantatatexts.org."""
    url = f'https://bachcantatatexts.org/BWV{bwv_number}.json'
    log.info(f"[Step 1] Fetching JSON from {url}")

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=config.HEADERS,
                                timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            log.info(f"[Step 1] JSON loaded: {data.get('work_name', '?')}, "
                     f"{len(data.get('movements', []))} movements, "
                     f"{len(data.get('notes', []))} notes")
            return data
        except (requests.RequestException, json.JSONDecodeError) as e:
            log.warning(f"[Step 1] Attempt {attempt} failed: {e}")
            if attempt < config.MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Failed to fetch {url}: {e}")


# English role-name remnants that bachcantatatexts.org leaves as standalone
# lines in the English text (e.g. "Fear", "Hope", "Soul", "Jesus"). These are
# NOT lyrics — they are the English translation of a dialogue role label.
# They must be stripped so line_footnote_ids aligns with the German lyric lines.
_ENGLISH_ROLE_REMNANTS = frozenset({
    'Soul', 'Jesus', 'Christ', 'Savior', 'Bridegroom', 'Bride', 'Anima',
    'Fear', 'Hope', 'Death', 'Satan',
    'Evangelist', 'Pilate', 'Peter', 'Maid', 'Servant', 'Judas',
})


def _is_english_role_remnant(text):
    """Return True if `text` is a standalone English role-name remnant line.

    Handles both single role names ("Soul", "Jesus") and composite duet
    markers ("Soul & Jesus", "Soul, Jesus") that bachcantatatexts.org emits
    for dialogue duets. Composite markers were previously missed because the
    old check only accepted a single word — causing footnote misalignment
    (e.g. BWV 140 Mvt 6, fn20/21/22/23).
    """
    t = (text or '').strip()
    if not t:
        return False
    # Split composite markers on commas/ampersands ("Soul & Jesus", "Soul, Jesus").
    parts = [p.strip() for p in re.split(r'\s*[,&]\s*', t) if p.strip()]
    if not parts:
        return False
    return all(
        len(p.split()) == 1 and p in _ENGLISH_ROLE_REMNANTS
        for p in parts
    )


def _extract_html_note_parts(html):
    """Split an HTML text block into [(clean_text, [note_ids]), ...] by <br>.

    Footnote markers come as <sup>N</sup> (or [N]) inside each line's HTML.
    """
    if not html:
        return []
    parts = re.split(r'<br\s*/?\s*>', html, flags=re.IGNORECASE)
    result = []
    for part in parts:
        clean = BeautifulSoup(part, 'html.parser').get_text().strip()
        if not clean:
            continue
        ids = [int(m.group(1)) for m in re.finditer(r'<sup>(\d+)</sup>', part)]
        if not ids:
            ids = [int(m.group(1)) for m in re.finditer(r'\[(\d+)\]', part)]
        result.append((clean, ids))
    return result


def _is_role_remnant_line(de_text, en_text):
    """Return True if a de/en line pair is a dialogue role-label remnant.

    bachcantatatexts.org emits role labels as standalone lines in BOTH the
    German text (e.g. "Furcht", "[Vox Dei/Christi]") and the English text
    (e.g. "Fear", "[Voice of God/Christ]"). These are not lyrics and carry no
    line_footnote_ids — they must be skipped so the footnote list aligns 1:1
    with the actual lyric lines.
    """
    dt = (de_text or '').strip()
    et = (en_text or '').strip()
    if dt.startswith('[') and dt.endswith(']'):
        return True
    if et.startswith('[') and et.endswith(']'):
        return True
    if dt:
        parts = [p.strip() for p in re.split(r'\s*[,&]\s*', dt) if p.strip()]
        if parts and all(p.lower() in _get_known_roles_lower() for p in parts):
            return True
    if _is_english_role_remnant(et):
        return True
    return False


def _parse_json_to_structured(data):
    """Convert raw JSON into our standardized internal format.

    The JSON from bachcantatatexts.org has this structure:
      {
        "bwv_num": 1,
        "work_name": "\"Wie schön leuchtet der Morgenstern\" BWV 1",
        "work_occasion": "Annunciation",
        "work_author": "Philipp Nicolai (1599)",
        "work_translators": "Michael Marissen and Daniel R. Melamed",
        "movements": [
          {
            "mvt_num": 1,
            "mvt_text_type": "chorale",
            "mvt_texts": [
              {"text_language": "de", "text_plain": "..."},
              {"text_language": "en", "text_plain": "..."}
            ]
          },
          ...
        ],
        "notes": [
          {"note_num": 0, "note_text_plain": "GENERAL NOTE: ..."},
          {"note_num": 1, "note_text_plain": "..."},
          ...
        ]
      }
    """
    movements = []
    for raw_mv in data.get('movements', []):
        mv_num = int(raw_mv.get('mvt_num', 0))
        mv_type = raw_mv.get('mvt_text_type', '')
        texts = raw_mv.get('mvt_texts', [])

        de_plain = ''
        de_html = ''
        en_plain = ''
        en_html = ''

        for text_block in texts:
            lang = text_block.get('text_language', '')
            plain = text_block.get('text_plain', '')
            html = text_block.get('text_html', '')
            if lang == 'de':
                # BWV 17-style API bug: a second "de" block that is actually English
                if de_plain:
                    candidate_lines = [l.strip() for l in plain.split('\n') if l.strip()]
                    german_chars = sum(1 for c in ' '.join(candidate_lines) if c in 'äöüßÄÖÜ')
                    eng_indicators = any(w in ' '.join(candidate_lines).lower()
                                        for w in ['the', 'and', 'have', 'like', 'lord', 'god'])
                    if german_chars == 0 and eng_indicators:
                        en_plain = plain
                        en_html = html
                        continue
                de_plain = plain
                de_html = html
            elif lang == 'en':
                en_plain = plain
                en_html = html

        german_lines = [l.strip() for l in de_plain.split('\n') if l.strip()] if de_plain else []
        english_lines = [l.strip() for l in en_plain.split('\n') if l.strip()] if en_plain else []
        # Strip English role-name remnants so english aligns with German lyric lines
        english_lines = [l for l in english_lines if not _is_english_role_remnant(l)]

        # Merge per-line footnote markers from BOTH de and en HTML blocks.
        # The de block carries German-specific notes (spelling variants etc.);
        # the en block carries translation notes. The two blocks are line-aligned
        # (en is a line-by-line translation of de), so merge by line position and
        # drop role-label remnant lines (their notes carry to the next lyric line).
        de_parts = _extract_html_note_parts(de_html)
        en_parts = _extract_html_note_parts(en_html)

        line_footnote_ids = []
        annotation_ids = []
        pending_ids = []  # notes on role-label lines, carried to the next lyric line
        n = max(len(de_parts), len(en_parts))
        for i in range(n):
            de_text, de_ids = de_parts[i] if i < len(de_parts) else ('', [])
            en_text, en_ids = en_parts[i] if i < len(en_parts) else ('', [])
            merged = sorted(set(de_ids + en_ids))
            if _is_role_remnant_line(de_text, en_text):
                pending_ids.extend(merged)
                continue
            merged = sorted(set(merged + pending_ids))
            pending_ids = []
            annotation_ids.extend(merged)
            line_footnote_ids.append(merged)
        annotation_ids = sorted(set(annotation_ids + pending_ids))

        movements.append({
            'number': mv_num,
            'type': mv_type,
            'german': german_lines,
            'english': english_lines,
            'annotation_ids': annotation_ids,
            'line_footnote_ids': line_footnote_ids,
        })

    # Post-process: detect dialogue cantata role labels and pipe-separated duet lines
    _parse_dialogue_movements(movements)

    # Determine if this is a dialogue cantata (any role detected in any movement)
    is_dialogue = any(
        any(mv.get('line_is_role_label', []))
        for mv in movements
    )

    # Parse notes
    footnotes = {}
    general_note = ''
    for note in data.get('notes', []):
        num = note.get('note_num')
        if num is None:
            continue
        text = note.get('note_text_plain', '')
        if num == 0:
            general_note = text
        else:
            footnotes[str(num)] = text

    # Extract Bible references from footnotes
    bible_refs = _extract_bible_references(footnotes)

    # Extract Luther citations from footnotes
    luther_citations = _extract_luther_citations(footnotes)

    # Get translator info
    translator = data.get('work_translators', '')

    return {
        'bwv': data.get('bwv_num'),
        'title': data.get('work_name', ''),
        'occasion': data.get('work_occasion', ''),
        'author': data.get('work_author', ''),
        'translator': translator,
        'general_note': general_note,
        'movements': movements,
        'footnotes': footnotes,
        'bible_references': bible_refs,
        'luther_citations': luther_citations,
        'is_dialogue_cantata': is_dialogue,
    }


# ═══════════════════════════════════════════════════════════════
# DIALOGUE CANTATA DETECTION
# ═══════════════════════════════════════════════════════════════

# Known Baroque cantata role/character names — imported from config.py
def _get_known_roles_lower():
    """Return lowercase set of all known dialogue role names from config."""
    return frozenset(name.lower() for name in config.DIALOGUE_ROLE_NAMES)

# Common German nouns that should NEVER be detected as role labels,
# even if they appear as isolated short capitalized words in lyric texts.
_NOUN_BLACKLIST_LOWER = frozenset({
    'lebenslang', 'herrlichkeit',  # BWV 1 false positives
})


def _parse_dialogue_movements(movements):
    """Post-process: detect role labels and pipe-separated duet lines.

    Analyzes each movement's german/english line arrays to identify:
    - Role labels (e.g., "Seele", "Jesus", "Seele, Jesus", "Seele & Jesus")
    - Pipe-separated duet lines (e.g., "Ich will|du sollst mit dir|mir ...")

    Appends new per-line fields to each movement:
    - is_role_label: bool
    - role_name: str or null (e.g., "Seele", "Seele, Jesus")
    - is_duet_line: bool
    - role_texts: dict {role: text} for pipe-separated lines

    Skips movements whose german lines already contain dict-type role labels
    (set by primary source step1_uofa) to avoid double-processing.
    """
    # Skip if role labels already set by primary source
    if any(isinstance(line, dict) for mv in movements for line in mv.get('german', [])):
        return

    for mv in movements:
        de_lines = mv.get('german', [])
        en_lines = mv.get('english', [])

        role_labels = []  # [(line_index, is_role_label, role_name)]
        is_duet = []      # [bool per line]
        role_texts_map = []  # [dict or None per line]

        for i, de_line in enumerate(de_lines):
            # Detect role labels
            is_role, role_name = _detect_role_label(de_line)
            role_labels.append((i, is_role, role_name))

            # Detect pipe-separated duet text
            has_pipe, rt_map = _detect_pipe_text(de_line, en_lines[i] if i < len(en_lines) else '')
            is_duet.append(has_pipe)
            role_texts_map.append(rt_map)

        # Attach to movement
        is_role_list = []
        role_name_list = []
        for _, is_r, rn in role_labels:
            is_role_list.append(is_r)
            role_name_list.append(rn)

        mv['line_is_role_label'] = is_role_list
        mv['line_role_name'] = role_name_list
        mv['line_is_duet'] = is_duet
        mv['line_role_texts'] = role_texts_map

        has_any_role = any(is_role_list)
        if has_any_role:
            log.debug(f"[Step 1] Mvt {mv['number']}: {sum(is_role_list)} role labels detected")


def _detect_role_label(text):
    """Detect if a line is a role/character label.

    Returns (is_role, role_name).
    Uses the comprehensive DIALOGUE_ROLE_NAMES set from config.py
    (sourced from bach-cantatas.com dialogue cantata + secular + passion lists).

    Examples: "Seele" → (True, "Seele"),
              "Seele, Jesus" → (True, "Seele, Jesus"),
              "Seele & Jesus" → (True, "Seele & Jesus")
    """
    t = text.strip()
    if not t:
        return (False, None)

    known = _get_known_roles_lower()

    # Split on comma or & to get individual role names
    parts = re.split(r'\s*[,&]\s*', t)
    cleaned = [p.strip() for p in parts if p.strip()]

    if not cleaned:
        return (False, None)

    # All parts must be known roles
    if all(p.lower() in known for p in cleaned):
        return (True, t)

    # Fallback: very short isolated line (2-8 chars), capitalized, no umlauts/punctuation
    # This catches role names that might not yet be in the config set.
    # Heuristic is intentionally tight to avoid false positives from German lyric words
    # like "Lebenslang" or "Herrlichkeit".
    words = t.split()
    if len(words) == 1 and 2 <= len(words[0]) <= 10:
        w = words[0]
        if (w[0].isupper() and
            not re.search(r'[.!?,;:()\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]', w) and
            not re.search(r'\d', w) and
            w.lower() not in _NOUN_BLACKLIST_LOWER):
            return (True, t)

    return (False, None)


def _detect_pipe_text(de_line, en_line):
    """Detect if a line contains pipe-separated role-specific text.

    Text like "Eröffne|Ich öffne den Saal" indicates alternating
    singing between two characters.

    Returns (is_pipe_line, role_text_map).
    role_text_map: dict or None, e.g.:
        {"de": {"part1": "...", "part2": "..."},
         "en": {"part1": "...", "part2": "..."}}
    """
    if '|' not in de_line:
        return (False, None)

    # Split on pipe
    de_parts = [p.strip() for p in de_line.split('|') if p.strip()]
    en_parts = [p.strip() for p in en_line.split('|') if p.strip()] if en_line else []

    if len(de_parts) < 2:
        return (False, None)

    # Build role_text map
    rt = {'de': {}, 'en': {}}
    for j, dp in enumerate(de_parts):
        rt['de'][f'part{j+1}'] = dp
    for j, ep in enumerate(en_parts):
        rt['en'][f'part{j+1}'] = ep

    return (True, rt)


def _extract_bible_references(footnotes):
    """Extract all Bible references from footnote texts.

    Uses precise book name matching to avoid capturing context words.
    """
    refs = []
    seen = set()

    # Precise list of known Bible book names (English)
    KNOWN_BOOKS = (
        r'Genesis|Exodus|Leviticus|Numbers|Deuteronomy|'
        r'Joshua|Judges|Ruth|'
        r'1\s*Samuel|2\s*Samuel|1\s*Kings|2\s*Kings|'
        r'1\s*Chronicles|2\s*Chronicles|Ezra|Nehemiah|Esther|'
        r'Job|Psalms?|Proverbs|Ecclesiastes|Song\s+of\s+(?:Solomon|Songs)|'
        r'Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|'
        r'Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|'
        r'Zephaniah|Haggai|Zechariah|Malachi|'
        r'Matthew|Mark|Luke|John|Acts|'
        r'Romans|1\s*Corinthians|2\s*Corinthians|Galatians|'
        r'Ephesians|Philippians|Colossians|'
        r'1\s*Thessalonians|2\s*Thessalonians|'
        r'1\s*Timothy|2\s*Timothy|Titus|Philemon|'
        r'Hebrews|James|1\s*Peter|2\s*Peter|'
        r'1\s*John|2\s*John|3\s*John|Jude|'
        r'Revelation'
    )

    pattern = re.compile(
        rf'({KNOWN_BOOKS})\s+(\d+):(\d+(?:-\d+)?)',
        re.IGNORECASE
    )

    for fnum, ftext in footnotes.items():
        for match in pattern.finditer(ftext):
            book = match.group(1).strip()
            chapter = int(match.group(2))
            verse = match.group(3)
            # Normalize book names
            book = re.sub(r'\s+', ' ', book).strip()
            # Normalize Psalms -> Psalm
            if book.lower() == 'psalms':
                book = 'Psalm'
            key = (book, chapter, verse)
            if key not in seen:
                seen.add(key)
                refs.append({
                    'book': book,
                    'chapter': chapter,
                    'verse': verse,
                    'footnote_id': int(fnum),
                })

    # Deduplicate by (book, chapter, verse) ignoring footnote_id
    unique_refs = []
    unique_keys = set()
    for ref in refs:
        key = (ref['book'], ref['chapter'], ref['verse'])
        if key not in unique_keys:
            unique_keys.add(key)
            unique_refs.append(ref)

    return unique_refs


def _extract_luther_citations(footnotes):
    """Extract Luther Bible German quotations from footnotes."""
    citations = []
    for fnum, ftext in footnotes.items():
        # German quotes in curly quotes
        german_quotes = re.findall(r'\u201c([^\u201d]+)\u201d', ftext)
        for quote in german_quotes:
            if re.search(r'[äöüßÄÖÜ]', quote) and len(quote) > 20:
                citations.append({
                    'footnote_id': int(fnum),
                    'luther_text': quote.strip(),
                })
    return citations


def run(bwv_number, json_data=None):
    """Execute Step 1: fetch and parse bachcantatatexts.org data.

    Args:
        bwv_number: int or str, the BWV number.
        json_data: Optional pre-fetched JSON dict (if None, fetches from web).

    Returns:
        dict: Structured data with movements, footnotes, references.
    """
    if json_data is None:
        json_data = _fetch_json(str(bwv_number))

    result = _parse_json_to_structured(json_data)

    log.info(f"[Step 1] Parsed {len(result['movements'])} movements, "
             f"{len(result['footnotes'])} footnotes, "
             f"{len(result['bible_references'])} unique Bible refs, "
             f"{len(result['luther_citations'])} Luther citations")

    return result


def save(data, folder_path):
    """Save parsed data as JSON files."""
    data_dir = os.path.join(folder_path, 'data')

    # Save texts.json (without bulky footnotes)
    texts_data = {k: v for k, v in data.items() if k != 'footnotes'}
    with open(os.path.join(data_dir, 'texts.json'), 'w', encoding='utf-8') as f:
        json.dump(texts_data, f, ensure_ascii=False, indent=2)
    log.info("[Step 1] Saved texts.json")

    # Save footnotes separately
    with open(os.path.join(data_dir, 'footnotes.json'), 'w', encoding='utf-8') as f:
        json.dump(data['footnotes'], f, ensure_ascii=False, indent=2)
    log.info(f"[Step 1] Saved footnotes.json ({len(data['footnotes'])} entries)")
