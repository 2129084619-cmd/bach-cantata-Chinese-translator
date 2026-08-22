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
from . import step1_fetch_texts

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


def _is_brace_role_marker(text):
    """Return True if `text` is a standalone brace-enclosed role/voice marker.

    UAlberta marks dialogue-duet lines with a brace line listing the two
    speakers, e.g. "{Seele, Bass}" (later "{Seele, Jesus}" after voice
    substitution). These are role labels, NOT lyrics — they must not occupy a
    lyric-line slot, or line_footnote_ids will misalign (BWV 140 Mvt 6,
    fn20/21/22/23).
    """
    t = (text or '').strip()
    if not (t.startswith('{') and t.endswith('}')):
        return False
    inner = t[1:-1].strip()
    if not inner:
        return False
    from .config import DIALOGUE_ROLE_NAMES
    known = set(DIALOGUE_ROLE_NAMES) | set(_VOICE_MARKERS)
    parts = [p.strip() for p in re.split(r'[,/]', inner) if p.strip()]
    return bool(parts) and all(p in known for p in parts)


def _apply_role_labels(movements, voice_to_role):
    """Post-process: replace voice markers (Alt, Tenor, Bass, Soprano)
    with character role names (Furcht, Hoffnung, Jesus, Seele, etc.).

    Handles:
      1. Standalone voice marker → role-label dict
      2. Inline voice marker in text (e.g. "{Sopran, Bass}") → regex substitution
      3. Duet markers ("beide"/"beiden", brace-enclosed "{Role, Role}") → role-label
         dict so they do not occupy a lyric-line slot (keeps line_footnote_ids aligned)
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

            # Duet "both" marker ("beide"/"beiden") → role-label dict
            if text in ('beide', 'beiden'):
                new_german.append({'text': text, 'line_is_role_label': True})
            # Case 1: standalone voice marker → role-label dict
            elif text in v2r:
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
                # A bare "{Role, Role}" line (after substitution) is a duet marker
                if _is_brace_role_marker(replaced):
                    new_german.append({'text': replaced, 'line_is_role_label': True})
                else:
                    new_german.append(replaced)
            # Case 3: bare "{Role, Role}" line with no voice markers
            elif _is_brace_role_marker(text):
                new_german.append({'text': text, 'line_is_role_label': True})
            else:
                new_german.append(line)
        mvt['german'] = new_german

    return movements


# ═══════════════════════════════════════════════════════════════
# UAlberta parser
# ═══════════════════════════════════════════════════════════════

def _extract_title(soup):
    """Extract the cantata title from the page's 'BWV N ...' line."""
    text = soup.get_text('\n')
    lines = [l.rstrip() for l in text.split('\n')]
    for line in lines[:5]:
        ls = line.strip()
        if ls and ls.startswith('BWV '):
            t = re.match(r'BWV\s+\d+\w*\s+(.+)', ls)
            if t:
                raw = t.group(1).strip()
                raw = re.split(r'\s*\*\s*\*', raw)[0].strip()
                raw = re.split(r'\s*\|\s*', raw)[0].strip()
                raw = re.sub(r'\s*,?\s*$', '', raw)
                return raw
    return ''


def _classify_mvt_type(mvt_type_raw):
    """Classify a UAlberta movement header's type string into a standard keyword.

    UAlberta uses 'Coro' for a genuine CHORUS (sung by the full choir), NOT as an
    ambiguous chorus/chorale marker — a closing four-part chorale is labelled
    'Choral' instead (e.g. BWV 3 Mvt 6 "6. Choral"), and a flexible-scoring
    chorale stanza is labelled 'Versus' (e.g. BWV 4). 'has_chorale' is therefore
    NOT derived from this type string — it comes from bold chorale-text detection.

    Returns '' for an unrecognised keyword (caller marks it type='unknown').
    """
    if 'Coro' in mvt_type_raw or 'Chorus' in mvt_type_raw:
        return 'Chorus'
    if 'Recitativo' in mvt_type_raw or 'Recitative' in mvt_type_raw:
        return 'Recitative'
    if 'Aria' in mvt_type_raw:
        return 'Aria'
    if 'Choral' in mvt_type_raw or 'Chorale' in mvt_type_raw:
        return 'chorale'
    if 'Sinfonia' in mvt_type_raw:
        return 'Sinfonia'
    if 'Duetto' in mvt_type_raw or 'Duet' in mvt_type_raw:
        return 'Duet'
    if 'Versus' in mvt_type_raw:
        return 'Versus'
    return ''


def _extract_voices(mvt_type_raw):
    """Extract solo-voice abbreviations from a movement header string.

    e.g. 'Recitativo T B' → 'Tenor, Bass'; 'Aria A' → 'Alto';
    'Coro' → '' (a chorus carries no solo-voice suffix on UAlberta).
    Used to label sub-numbered movements (7a/7b/7c) whose voices are absent
    from bach-cantatas.com movement_info.
    """
    tokens = re.findall(r'\b([ABTS])\b', mvt_type_raw)
    if not tokens:
        return ''
    names = {'A': 'Alto', 'T': 'Tenor', 'B': 'Bass', 'S': 'Soprano'}
    return ', '.join(names.get(t, t) for t in tokens)


def _parse_text_cell(cell):
    """Parse a UAlberta <td class='text'> cell into structured lines.

    UAlberta renders chorale text (Bach-set chorale verses) in <b>/<strong>, and
    voice/role markers in <em>/<i>. Lines are separated by <br>. Returns a list
    of {'text': str, 'is_bold': bool, 'is_em': bool} dicts, one per line — bold
    signals chorale text, em signals a voice/role marker.
    """
    from bs4 import NavigableString, Tag
    lines = []

    def _walk(node, in_bold, in_em, buf):
        # buf holds (text_segment, is_bold, is_em) tuples for the current line
        for child in node.children:
            if isinstance(child, NavigableString):
                s = str(child)
                # Whitespace segments carry no bold/em state — otherwise a
                # trailing newline inside <b> (after its <br>) would leak bold
                # onto the following <em> voice-marker line.
                buf.append((s, in_bold and bool(s.strip()),
                            in_em and bool(s.strip())))
            elif isinstance(child, Tag):
                if child.name == 'br':
                    text = ''.join(seg[0] for seg in buf).strip()
                    if text:
                        lines.append({
                            'text': text,
                            'is_bold': any(seg[1] for seg in buf),
                            'is_em': any(seg[2] for seg in buf),
                        })
                    buf.clear()
                elif child.name in ('b', 'strong'):
                    _walk(child, True, in_em, buf)
                elif child.name in ('em', 'i'):
                    _walk(child, in_bold, True, buf)
                else:
                    _walk(child, in_bold, in_em, buf)

    buf = []
    _walk(cell, False, False, buf)
    text = ''.join(seg[0] for seg in buf).strip()
    if text:
        lines.append({
            'text': text,
            'is_bold': any(seg[1] for seg in buf),
            'is_em': any(seg[2] for seg in buf),
        })
    return lines


def _fetch_uofa(bwv):
    """Fetch and parse German text from UAlberta cantata page.

    For dialogue/secular/passion works: detects role→voice mappings from
    page top / movement headers, then replaces voice abbreviations (Alt,
    Tenor, Bass, Sopran) in the lyrics body with actual character names.

    Chorale detection: UAlberta renders chorale verses in <b>. Bold lines are
    marked 'is_chorale' and the movement's 'has_chorale' flag is derived from
    their presence — a reliable signal independent of the type keyword (which
    may be 'Coro', 'Aria', 'Recitativo', etc.).
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

    title = _extract_title(soup)

    title = _extract_title(soup)

    # ── Step B: Parse movements from the HTML table structure ──
    # Each movement is a <tr> with a <td class="movement"> (header + instruments)
    # and a <td class="text"> (lyrics). Bold (<b>) lyric lines are chorale text;
    # <em> lines are voice/role markers.
    movements = []
    header_pattern = re.compile(r'^\s*(\d+)([a-z]?)\.\s+(.+?)\s*$')

    for mv_cell in soup.find_all('td', class_='movement'):
        b_tag = mv_cell.find('b')
        header_text = (b_tag.get_text(' ', strip=True) if b_tag
                       else mv_cell.get_text(' ', strip=True))
        m = header_pattern.match(header_text)
        if not m:
            continue
        mvt_num, mv_label = step1_fetch_texts._parse_mvt_number(
            m.group(1) + (m.group(2) or ''))
        mvt_type_raw = m.group(3).strip()
        mvt_type = _classify_mvt_type(mvt_type_raw)

        tr = mv_cell.find_parent('tr')
        text_cell = tr.find('td', class_='text') if tr else None
        parsed = _parse_text_cell(text_cell) if text_cell else []

        german = []
        has_chorale = False
        for line in parsed:
            text = line['text']
            if line['is_bold']:
                has_chorale = True
                german.append({'text': text, 'is_chorale': True})
            elif line['is_em']:
                if '(' in text and re.match(r'^\S+\s*\([ABTSabts]\)', text):
                    continue
                # Scene marker starting with a role name
                # (e.g. "Evangelist, zwei Männer in weißen Kleidern") → role-label
                first_word = text.split(',')[0].strip()
                if first_word in DIALOGUE_ROLE_NAMES:
                    german.append({'text': text, 'line_is_role_label': True})
                    continue
                german.append(text)
            else:
                if text in _SECTION_MARKERS:
                    continue
                german.append(text)

        from .config import DIALOGUE_ROLE_NAMES
        german = [
            {'text': g, 'line_is_role_label': True}
            if isinstance(g, str) and g in DIALOGUE_ROLE_NAMES else g
            for g in german
        ]

        mv_dict = {
            'number': mvt_num,
            'mvt_label': mv_label,
            'type': mvt_type if mvt_type else 'unknown',
            'german': german,
            'english': [],
            'annotation_ids': [],
            'line_footnote_ids': [],
            'has_chorale': has_chorale,
            'voices': _extract_voices(mvt_type_raw),
        }
        if not mvt_type:
            mv_dict['mv_type_raw'] = mvt_type_raw
            mv_dict['is_uncertain_type'] = True
        movements.append(mv_dict)

    # ── Step C: Post-process ─ replace voice markers with role names ──
    # Oratorio/Passion works (BWV 11/248/249/244/245) have no explicit
    # role→voice map on UAlberta; the narrator (Evangelist) is always the
    # Tenor. Supply the default map so "Tenor"/"beide" markers become role
    # labels instead of plain lyric lines.
    if not voice_to_role and str(bwv) in config.ORATORIO_PASSION_BWV:
        voice_to_role = config.ORATORIO_PASSION_VOICE_ROLE
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
            mv_num, mv_label = step1_fetch_texts._parse_mvt_number(raw_mv.get('mvt_num', 0))
            english_lines = []
            for tb in raw_mv.get('mvt_texts', []):
                if tb.get('text_language') == 'en':
                    english_lines = [l.strip() for l in tb.get('text_plain', '').split('\n') if l.strip()]
                    break
            movements.append({
                'number': mv_num,
                'mvt_label': mv_label,
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
        mv_num, mv_label = step1_fetch_texts._parse_mvt_number(raw_mv.get('mvt_num', 0))
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
            'mvt_label': mv_label,
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
        non_role_idx = 0  # english/lfn index (aligned to lyric lines only)
        n = len(german)
        while i < n:
            cur = german[i]
            # Role-label dict (line_is_role_label): keep as-is, not a lyric line.
            # A chorale dict (is_chorale) IS a lyric line — it may still merge.
            if isinstance(cur, dict) and cur.get('line_is_role_label'):
                new_german.append(cur)
                i += 1
                continue
            cur_text = cur.get('text', '') if isinstance(cur, dict) else cur
            cur_word = _short_word(cur_text)
            merged = False
            if cur_word and i + 1 < n:
                nxt = german[i + 1]
                if not (isinstance(nxt, dict) and nxt.get('line_is_role_label')):
                    nxt_text = nxt.get('text', '') if isinstance(nxt, dict) else nxt
                    if _short_word(nxt_text) == cur_word:
                        merged_text = cur_text.rstrip() + ' ' + nxt_text.lstrip()
                        if isinstance(cur, dict) or isinstance(nxt, dict):
                            new_german.append({'text': merged_text, 'is_chorale': True})
                        else:
                            new_german.append(merged_text)
                        # Merge English (annotation-only, index-aligned)
                        if english:
                            if non_role_idx < len(english) and non_role_idx + 1 < len(english):
                                new_english.append(
                                    english[non_role_idx].rstrip() + ' ' + english[non_role_idx + 1].lstrip())
                            elif non_role_idx < len(english):
                                new_english.append(english[non_role_idx])
                        # Merge footnote ids for the merged line
                        fn = []
                        if non_role_idx < len(lfn):
                            fn.extend(lfn[non_role_idx] or [])
                        if non_role_idx + 1 < len(lfn):
                            fn.extend(lfn[non_role_idx + 1] or [])
                        new_lfn.append(fn)
                        i += 2
                        non_role_idx += 2
                        merged = True
            if not merged:
                new_german.append(cur)
                if english:
                    new_english.append(english[non_role_idx] if non_role_idx < len(english) else '')
                if lfn:
                    new_lfn.append(lfn[non_role_idx] if non_role_idx < len(lfn) else [])
                i += 1
                non_role_idx += 1

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
