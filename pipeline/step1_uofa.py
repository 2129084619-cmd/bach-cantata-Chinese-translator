# -*- coding: utf-8 -*-
"""Step 1: Fetch German text from UAlberta (primary), footnotes from bachcantatatexts.org.

Primary source (always available):
  https://sites.ualberta.ca/~wfb/cantatas/{BWV}.html
  Clean, consistent format: movement headers (**N. Type Voice**), instrumentation
  in italics, German text with bold for chorale verses.
  For dialogue/secular/passion works: role names appear at page top
  (e.g. "Furcht (A), Hoffnung (T)") while the lyrics body uses voice
  abbreviations (Alt, Tenor, Bass). This module detects the role→voice
  mapping and replaces voice markers with actual role names.

Secondary source (when available):
  https://bachcantatatexts.org/BWV{N}.json
  Provides footnotes, English translations, Bible references.

Auxiliary references (not primary data sources, used for cross-verification):
  http://www.kantate.info/cantata_text_e.htm  (NBA-critical text, partial coverage)
  https://www.bach-cantatas.com/Texts/BWV{N}-Eng3.htm  (role lists, background)
"""

import re
import json
import os
import time
import requests
from bs4 import BeautifulSoup

from . import config

UOF_A_URL = 'https://sites.ualberta.ca/~wfb/cantatas/{bwv}.html'
BCT_URL = 'https://bachcantatatexts.org/BWV{bwv}.json'


def run(bwv_number):
    """Fetch and parse cantata data from primary + secondary sources.

    Returns:
        dict: structured data with movements, footnotes, references, title
    """
    bwv = str(bwv_number)
    data = {
        'bwv_num': int(bwv),
        'title': '',
        'work_name': '',
        'movements': [],
        'footnotes': {},
        'bible_references': [],
        'luther_citations': [],
        'source_german': 'ualberta.ca',
        'source_footnotes': '',
    }

    # ── Source 1: UAlberta German text ──
    movements, title = _fetch_uofa(bwv)
    if movements:
        data['movements'] = movements
        data['title'] = title
        data['work_name'] = title

    # ── Source 2: bachcantatatexts.org footnotes / English ──
    # Per project policy (2026-08-16): bachcantatatexts.org English translations and
    # footnotes are used ONLY as annotation material to translate. They do NOT drive
    # (a) translation reference nor (b) cantata→Bible scripture search.
    #   - English lines are still stored (annotation reference) but excluded from the
    #     AI translation context in step4.
    #   - bible_references is left EMPTY here; it is populated later from the
    #     background sources (bach-cantatas.com / bachipedia.org) + chorale fuzzy search.
    bct_data = _fetch_bct(bwv)
    if bct_data:
        data['source_footnotes'] = 'bachcantatatexts.org'
        # Merge English text into movements (annotation-only, not translation reference)
        bct_movements = _parse_bct_movements(bct_data)
        _merge_english(data['movements'], bct_movements)
        # Extract footnotes (translated as annotations; "内容仅供参考" is appended)
        data['footnotes'] = _parse_bct_footnotes(bct_data)
        # Deliberately NOT extracting bible_references from bachcantatatexts.org.
        data['bible_references'] = []
        data['luther_citations'] = _parse_bct_luther_refs(bct_data)
        # Use BCT title if UAlberta didn't provide one
        if not data['title']:
            data['title'] = bct_data.get('work_name', '')
            data['work_name'] = data['title']

    # ── Fallback: no UAlberta data → use BCT German ──
    if not data['movements'] and bct_data:
        data['source_german'] = 'bachcantatatexts.org (fallback)'
        data['movements'] = _parse_bct_german_movements(bct_data)
        if not data['title']:
            data['title'] = bct_data.get('work_name', '')
            data['work_name'] = data['title']

    # ── Merge paired exclamations (UAlberta "Amen!"/"Amen!" → "Amen! Amen!") ──
    # Keeps chorale line breaks consistent with the chorale subsystem so that
    # chorale-translation reuse (step45) aligns correctly.
    if data['movements']:
        _merge_paired_exclamations(data['movements'])

    return data


# ═══════════════════════════════════════════════════════════════
# UAlberta parser
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Role → Voice mapping (for dialogue / secular / passion works)
# ═══════════════════════════════════════════════════════════════

# Voice abbreviation → full name
_VOICE_ABBREV = {'A': 'Alt', 'T': 'Tenor', 'B': 'Bass', 'S': 'Soprano'}

# Voice markers used in UAlberta lyrics (not role names, will be replaced)
_VOICE_MARKERS = {'Alt', 'Tenor', 'Bass', 'Soprano', 'Sopran'}

# Section/part markers in multi-part cantatas (should NOT be treated as lyrics)
_SECTION_MARKERS = frozenset({
    'Erster Teil', 'Zweiter Teil', 'Anderer Teil', 'Dritter Teil',
    'Erster Theil', 'Zweiter Theil', 'Anderer Theil', 'Dritter Theil',
    'Prima Pars', 'Secunda Pars', 'Tertia Pars',
    'Pars Prima', 'Pars Secunda', 'Pars Tertia',
    'Erster Satz', 'Zweiter Satz',
})


def _extract_role_voice_map(soup):
    """Extract role→voice mappings from UAlberta page HTML.

    Scans two locations:
      1. Page top: subtitle row followed by <em>Role (V), Role (V)</em>
         e.g. "Furcht (A), Hoffnung (T), Christus (B)"
      2. Movement-level: <em>Role (V), Role (V)</em> inside td.text cells
         e.g. "Seele (S), Jesus (B)" at Mvt 3 of BWV 140

    Returns dict: {'Alt': 'Furcht', 'Tenor': 'Hoffnung', 'Bass': 'Christus', ...}
    """
    mappings = {}

    def _parse_role_line(text):
        """Parse 'Furcht (A), Hoffnung (T)' → {'Alt': 'Furcht', 'Tenor': 'Hoffnung'}"""
        local = {}
        for part in re.split(r'[,;]\s*', text):
            m = re.match(r'(\S+)\s*\(([ABTSabts])\)', part.strip())
            if m:
                role = m.group(1).strip()
                # Skip if it looks like a voice marker, not a character role
                if role in _VOICE_MARKERS or role in {'beide', 'beiden', 'Coro'}:
                    continue
                if re.match(r'^[IV]+$', role):
                    continue  # Roman numerals (e.g. "I", "II")
                voice_abbrev = m.group(2).upper()
                voice_full = _VOICE_ABBREV.get(voice_abbrev, voice_abbrev)
                local[voice_full] = role
        return local

    # ── 1. Top-level: subtitle="Dialogus" (or similar) → next row ──
    for tag in soup.find_all(['td', 'span'], class_=lambda c:
                              c and any(kw in c.lower()
                                       for kw in ['subtitle', 'dialog', 'passion'])):
        row = tag.find_parent('tr')
        if not row:
            continue
        # Scan subsequent rows for the role line
        for next_row in row.find_next_siblings('tr', limit=3):
            text_cell = next_row.find('td', class_='text')
            if text_cell:
                em_tags = text_cell.find_all('em')
                for em in em_tags:
                    em_text = em.get_text(strip=True)
                    if '(' in em_text and ')' in em_text:
                        mappings.update(_parse_role_line(em_text))
                if mappings:
                    break

    # ── 2. Movement-level: <em>Role (V), Role (V)</em> in any text cell ──
    for text_cell in soup.find_all('td', class_='text'):
        for em in text_cell.find_all('em'):
            em_text = em.get_text(strip=True)
            if re.search(r'\([ABTSabts]\)', em_text):
                mappings.update(_parse_role_line(em_text))

    # Normalize: ensure Sopran→Soprano consistency
    if 'Sopran' in mappings:
        if 'Soprano' not in mappings:
            mappings['Soprano'] = mappings['Sopran']
        del mappings['Sopran']

    return mappings


def _apply_role_labels(movements, voice_to_role):
    """Post-process: replace voice markers (Alt, Tenor, Bass, Soprano)
    with character role names (Furcht, Hoffnung, Jesus, Seele, etc.).

    Handles two cases:
      1. Standalone voice marker → role-label dict
      2. Inline voice marker in text (e.g. "{Sopran, Bass}") → regex substitution
    """
    if not voice_to_role:
        return movements

    # Normalize: ensure Sopran→Soprano alias exists
    v2r = dict(voice_to_role)
    if 'Soprano' in v2r and 'Sopran' not in v2r:
        v2r['Sopran'] = v2r['Soprano']

    # Build regex pattern for inline substitution
    voice_pattern = re.compile(
        r'\b(' + '|'.join(re.escape(v) for v in _VOICE_MARKERS) + r')\b'
    )

    for mvt in movements:
        new_german = []
        for line in mvt.get('german', []):
            # If already a role-label dict, pass through
            if isinstance(line, dict):
                new_german.append(line)
                continue

            text = str(line)

            # Case 1: standalone voice marker → role-label dict
            if text in v2r:
                new_german.append({
                    'text': v2r[text],
                    'line_is_role_label': True,
                })
            # Case 2: text with inline voice markers → regex replacement
            elif any(v in text for v in _VOICE_MARKERS):
                replaced = voice_pattern.sub(
                    lambda m: v2r.get(m.group(), m.group()),
                    text
                )
                new_german.append(replaced)
            else:
                new_german.append(line)
        mvt['german'] = new_german

    return movements


# ═══════════════════════════════════════════════════════════════
# UAlberta parser
# ═══════════════════════════════════════════════════════════════

def _fetch_uofa(bwv):
    """Fetch and parse German text from UAlberta cantata page.

    For dialogue/secular/passion works: detects role→voice mappings from
    page top / movement headers, then replaces voice abbreviations (Alt,
    Tenor, Bass, Sopran) in the lyrics body with actual character names.
    """
    url = UOF_A_URL.format(bwv=bwv)
    try:
        resp = requests.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except requests.RequestException as e:
        print(f"  [WARN] UAlberta fetch failed: {e}")
        return [], ''

    soup = BeautifulSoup(resp.text, 'html.parser')

    # ── Step A: Extract role→voice mapping from HTML structure ──
    voice_to_role = _extract_role_voice_map(soup)
    if voice_to_role:
        roles_str = ', '.join(f'{r}({v})' for v, r in voice_to_role.items())
        print(f"  [UAlberta] Detected roles: {roles_str}")

    # ── Step B: Extract text from table structure ──
    # Use get_text('\\n') for reliable line-by-line extraction,
    # then detect role markers in the post-processing pass.
    text = soup.get_text('\n')
    lines = [l.rstrip() for l in text.split('\n')]

    # Extract title
    title = ''
    for line in lines[:5]:
        ls = line.strip()
        if ls and ls.startswith('BWV '):
            t = re.match(r'BWV\s+\d+\w*\s+(.+)', ls)
            if t:
                raw = t.group(1).strip()
                raw = re.split(r'\s*\*\s*\*', raw)[0].strip()
                raw = re.split(r'\s*\|\s*', raw)[0].strip()
                raw = re.sub(r'\s*,?\s*$', '', raw)
                title = raw
            break

    # Parse movements
    movements = []
    current_mvt = None
    header_pattern = re.compile(r'\*?\*?\s*(\d+)\.\s+(.+?)(?:\s+\*?\*?)?$')
    instr_keywords = ['Oboe', 'Violin', 'Viola', 'Continuo', 'Corno', 'Flauto',
                      'Tromba', 'Trombone', 'Organo', 'Cembalo', 'Fagotto',
                      'Travers', 'Timpani', 'Violoncello']

    for line in lines:
        ls = line.strip()
        if not ls:
            continue

        # Check for movement header
        m = header_pattern.search(ls)
        if m and ('Coro' in ls or 'Recitativo' in ls or 'Aria' in ls
                  or 'Choral' in ls or 'Chorus' in ls or 'Sinfonia' in ls
                  or 'Duetto' in ls or 'Arioso' in ls):
            mvt_num = int(m.group(1))
            mvt_type_raw = m.group(2).strip()
            if 'Coro' in mvt_type_raw or 'Chorus' in mvt_type_raw:
                mvt_type = 'Chorus'
            elif 'Recitativo' in mvt_type_raw or 'Recitative' in mvt_type_raw:
                mvt_type = 'Recitative'
            elif 'Aria' in mvt_type_raw:
                mvt_type = 'Aria'
            elif 'Choral' in mvt_type_raw or 'Chorale' in mvt_type_raw:
                mvt_type = 'chorale'
            elif 'Sinfonia' in mvt_type_raw:
                mvt_type = 'Sinfonia'
            elif 'Duetto' in mvt_type_raw or 'Duet' in mvt_type_raw:
                mvt_type = 'Duet'
            else:
                mvt_type = mvt_type_raw

            current_mvt = {
                'number': mvt_num,
                'type': mvt_type,
                'german': [],
                'english': [],
                'annotation_ids': [],
                'line_footnote_ids': [],
                # Flag mixed-type movements (e.g. "Aria T e Choral A" in BWV 60)
                'has_chorale': bool(
                    mvt_type != 'chorale' and
                    ('Choral' in mvt_type_raw or 'Chorale' in mvt_type_raw)
                ),
            }
            movements.append(current_mvt)
            continue

        if not current_mvt:
            continue

        # Skip instrumentation lines
        if any(kw in ls for kw in instr_keywords):
            if ',' in ls or '/' in ls:
                continue
            words = ls.split()
            if len(words) <= 3 and not any(c in 'äöüß' for c in ls):
                continue

        # Skip footer section
        if ls.startswith('* * *') or ls.startswith('Besetzung'):
            break

        # Clean bold / italic markers, collect text
        cleaned = re.sub(r'\*\*', '', ls).strip()
        cleaned = re.sub(r'^\*\s*|\s*\*$', '', cleaned).strip()
        if cleaned:
            # Skip section/part markers in multi-part cantatas
            # (e.g. BWV 195 "Erster Teil" / "Zweiter Teil")
            if cleaned in _SECTION_MARKERS:
                continue
            # Skip role-mapping annotation lines like "Seele (S), Jesus (B)"
            if re.match(r'^\S+\s*\([ABTSabts]\)', cleaned) and '(' in cleaned:
                continue
            # Detect standalone role names (e.g. "Seele" in BWV 140 Mvt 6)
            from .config import DIALOGUE_ROLE_NAMES
            if cleaned in DIALOGUE_ROLE_NAMES:
                current_mvt['german'].append({
                    'text': cleaned,
                    'line_is_role_label': True,
                })
            else:
                current_mvt['german'].append(cleaned)

    # ── Step C: Post-process — replace voice markers with role names ──
    if voice_to_role:
        _apply_role_labels(movements, voice_to_role)

    return movements, title


# ═══════════════════════════════════════════════════════════════
# bachcantatatexts.org parser (footnotes, English, fallback German)
# ═══════════════════════════════════════════════════════════════

def _fetch_bct(bwv):
    """Fetch JSON data from bachcantatatexts.org. Returns None if not found."""
    url = BCT_URL.format(bwv=bwv)
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=config.HEADERS,
                              timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            if attempt < config.MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                print(f"  [INFO] BWV {bwv} not on bachcantatatexts.org")
                return None
    return None


def _parse_bct_movements(bct_data):
    """Parse bachcantatatexts.org JSON into movement dicts with English lines.

    Reuses the existing step1_fetch_texts parser for accuracy.
    """
    try:
        from . import step1_fetch_texts
        result = step1_fetch_texts.run(None, json_data=bct_data)
        return result['movements']
    except Exception:
        # Fallback: simple English extraction
        movements = []
        for raw_mv in bct_data.get('movements', []):
            mv_num = int(raw_mv.get('mvt_num', 0))
            english_lines = []
            for tb in raw_mv.get('mvt_texts', []):
                if tb.get('text_language') == 'en':
                    english_lines = [l.strip() for l in tb.get('text_plain', '').split('\n') if l.strip()]
                    break
            movements.append({
                'number': mv_num,
                'type': raw_mv.get('mvt_text_type', ''),
                'german': [],
                'english': english_lines,
                'annotation_ids': [],
                'line_footnote_ids': [],
            })
        return movements


def _parse_bct_german_movements(bct_data):
    """Parse bachcantatatexts.org JSON into movement dicts with German lines (fallback)."""
    movements = []
    for raw_mv in bct_data.get('movements', []):
        mv_num = int(raw_mv.get('mvt_num', 0))
        mv_type = raw_mv.get('mvt_text_type', '')
        german_lines = []
        english_lines = []
        for tb in raw_mv.get('mvt_texts', []):
            lang = tb.get('text_language', '')
            lines = [l.strip() for l in tb.get('text_plain', '').split('\n') if l.strip()]
            if lang == 'de':
                german_lines = lines
            elif lang == 'en':
                english_lines = lines
        # BWV 17-style bug: second "de" is actually English
        if english_lines == [] and len(raw_mv.get('mvt_texts', [])) >= 2:
            second = raw_mv['mvt_texts'][1]
            if second.get('text_language') == 'de':
                s_lines = [l.strip() for l in second.get('text_plain', '').split('\n') if l.strip()]
                if not any(c in 'äöüß' for c in ' '.join(s_lines)):
                    english_lines = s_lines
        movements.append({
            'number': mv_num,
            'type': mv_type,
            'german': german_lines,
            'english': english_lines,
            'annotation_ids': [],
            'line_footnote_ids': [],
        })
    return movements


def _parse_bct_footnotes(bct_data):
    """Extract footnotes from bachcantatatexts.org JSON."""
    footnotes = {}
    for note in bct_data.get('notes', []):
        num = note.get('note_num')
        text = note.get('note_text_plain', '')
        if num is not None and num != 0:
            footnotes[str(num)] = text
    return footnotes


def _parse_bct_bible_refs(bct_data):
    """Extract Bible references."""
    refs = []
    for mv in bct_data.get('movements', []):
        for tb in mv.get('mvt_texts', []):
            for ref in tb.get('bible_refs', []):
                ref_str = f"{ref.get('book', '')} {ref.get('chapter', '')}:{ref.get('verses', '')}"
                if ref_str.strip() not in refs:
                    refs.append(ref_str.strip())
    return refs


def _parse_bct_luther_refs(bct_data):
    """Extract Luther citations."""
    refs = []
    for mv in bct_data.get('movements', []):
        for tb in mv.get('mvt_texts', []):
            for ref in tb.get('luther_cits', []):
                ref_str = ref.get('text', '')[:200]
                if ref_str not in refs:
                    refs.append(ref_str)
    return refs


def _merge_english(uofa_movements, bct_movements):
    """Merge English text from BCT into UAlberta movement dicts."""
    bct_by_num = {m['number']: m for m in bct_movements}
    for mvt in uofa_movements:
        bct_mvt = bct_by_num.get(mvt['number'])
        if bct_mvt and bct_mvt.get('english'):
            mvt['english'] = bct_mvt['english']
        if bct_mvt:
            mvt['annotation_ids'] = bct_mvt.get('annotation_ids', [])
            mvt['line_footnote_ids'] = bct_mvt.get('line_footnote_ids', [])


def _short_word(s):
    """Return the single lowercase word in `s` (stripped of punctuation) if it
    is a short standalone exclamation (e.g. 'Amen!', 'Eia,', 'Ja!'), else None."""
    m = re.match(r'^[^a-zäöüß]*([a-zäöüß]{1,10})[^a-zäöüß]*$', s.lower())
    return m.group(1) if m else None


def _merge_paired_exclamations(movements):
    """Merge consecutive duplicate exclamation lines into one line.

    UAlberta splits paired exclamations across two <br> lines ("Amen!" / "Amen!"),
    while the chorale subsystem (bach-cantatas.com) keeps them together
    ("Amen! Amen!"). Merging them here keeps the two sources' line breaks
    consistent so that chorale-translation reuse aligns correctly.

    Synchronises german / english / line_footnote_ids (all index-aligned).
    """
    for mvt in movements:
        german = mvt.get('german', [])
        english = mvt.get('english', [])
        lfn = mvt.get('line_footnote_ids', [])

        new_german, new_english, new_lfn = [], [], []
        i = 0
        n = len(german)
        while i < n:
            cur = german[i]
            if isinstance(cur, dict):
                # Role-label dict: keep as-is (not a lyric exclamation)
                new_german.append(cur)
                i += 1
                continue
            cur_word = _short_word(cur)
            merged = False
            if cur_word and i + 1 < n:
                nxt = german[i + 1]
                if isinstance(nxt, str) and _short_word(nxt) == cur_word:
                    new_german.append(cur.rstrip() + ' ' + nxt.lstrip())
                    # Merge English (annotation-only, index-aligned)
                    if english:
                        if i < len(english) and i + 1 < len(english):
                            new_english.append(
                                english[i].rstrip() + ' ' + english[i + 1].lstrip())
                        elif i < len(english):
                            new_english.append(english[i])
                    # Merge footnote ids for the merged line
                    fn = []
                    if i < len(lfn):
                        fn.extend(lfn[i] or [])
                    if i + 1 < len(lfn):
                        fn.extend(lfn[i + 1] or [])
                    new_lfn.append(fn)
                    i += 2
                    merged = True
            if not merged:
                new_german.append(cur)
                if english:
                    new_english.append(english[i] if i < len(english) else '')
                if lfn:
                    new_lfn.append(lfn[i] if i < len(lfn) else [])
                i += 1

        mvt['german'] = new_german
        if english:
            mvt['english'] = new_english
        if lfn:
            mvt['line_footnote_ids'] = new_lfn
    return movements


def _german_text(line):
    """Extract plain German text from a german list entry (str or role-label dict)."""
    if isinstance(line, dict):
        return line.get('text', '')
    return str(line) if line else ''


# ═══════════════════════════════════════════════════════════════
# Save / I/O
# ═══════════════════════════════════════════════════════════════

def save(data, folder_path):
    """Save parsed data as JSON files (texts.json + footnotes.json)."""
    data_dir = os.path.join(folder_path, 'data')
    os.makedirs(data_dir, exist_ok=True)

    footnotes = data.pop('footnotes', {})

    # Save texts.json (without footnotes for smaller file)
    with open(os.path.join(data_dir, 'texts.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Save footnotes.json separately
    with open(os.path.join(data_dir, 'footnotes.json'), 'w', encoding='utf-8') as f:
        json.dump(footnotes, f, ensure_ascii=False, indent=2)

    # Put footnotes back in data dict
    data['footnotes'] = footnotes

    print(f"  [Step1] Saved {len(data.get('movements', []))} movements, "
          f"{len(footnotes)} footnotes")
