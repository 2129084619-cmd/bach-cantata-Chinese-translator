# -*- coding: utf-8 -*-
"""Step 2: Extract background metadata from bach-cantatas.com.

Extracts:
  - Event / liturgical occasion
  - Bible readings (Epistle, Gospel)
  - Librettist info
  - Composition date
  - Movement instrumentation (per movement)
  - Chorale text info
"""

import json
import os
import re
import time
import urllib3

# ═══════════════════════════════════════════════════════════════
# Hardcoded composition year fallback
# Some BWV pages lack a "Composed:" line; this provides a backstop.
# Sources: Bach-Werke-Verzeichnis, Bach Cantatas Website.
# ═══════════════════════════════════════════════════════════════
BWV_COMPOSED_FALLBACK = {
    '71': '1708 (Mühlhausen)',
    '140': '1731 (Leipzig)',
}

import requests

# Suppress SSL warnings for bach-cantatas.com
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from . import config
from .logger import get_logger

log = get_logger()


def _fetch_page(bwv_number):
    """Fetch the interlinear format page from bach-cantatas.com."""
    url = config.URL_BACH_CANTATAS_BG.format(bwv=bwv_number)
    log.info(f"[Step 2] Fetching {url}")

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=config.HEADERS,
                                timeout=config.REQUEST_TIMEOUT, verify=False)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or 'utf-8'
            log.info(f"[Step 2] Fetched {len(resp.text)} bytes")
            return resp.text
        except requests.RequestException as e:
            log.warning(f"[Step 2] Attempt {attempt} failed: {e}")
            if attempt < config.MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Failed to fetch {url}: {e}")


def _strip_html_structured(html):
    """Strip HTML while preserving structural breaks.

    Replaces block-level breaks (<BR>, </P>, </DIV>, </TD>, </TR>)
    with newlines before removing remaining tags.
    """
    # 1. Replace structural breaks with newlines
    for tag in [r'<BR\s*/?>', r'</P>', r'</DIV>', r'</TD>', r'</TR>',
                r'<P[^>]*>', r'<HR[^>]*>']:
        html = re.sub(tag, '\n', html, flags=re.IGNORECASE)

    # 2. Strip remaining inline HTML tags
    html = re.sub(r'<[^>]+>', ' ', html)

    # 3. Decode entities
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&amp;', '&')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&quot;', '"')

    # 4. Normalize: collapse spaces (preserve newlines), trim each line
    lines = []
    for line in html.split('\n'):
        line = re.sub(r'[ \t]+', ' ', line).strip()
        if line:
            lines.append(line)

    return '\n'.join(lines)


def _extract_metadata(html_text):
    """Parse metadata from the page using structured HTML stripping."""
    text = _strip_html_structured(html_text)
    lines = text.split('\n')

    metadata = {
        'occasion': '',
        'occasion_cn': '',
        'readings': {
            'epistle': {},
            'gospel': {},
        },
        'composed': '',
        'librettist': '',
        'chorale_text': '',
        'movement_info': [],
    }

    # ── Line-by-line parsing for metadata keys ──
    # Each metadata field is typically on its own line:
    #   Event: Cantata for the Town Council Inauguration
    #   Text: Psalm 74: 12 (Mvt. 1); ...
    # Several lines may belong to one field (continuation lines
    # start without a key: prefix)
    current_key = None
    buffer = []

    # Known metadata key patterns
    KEY_PATTERNS = {
        'occasion': re.compile(r'^Event\s*:\s*(.*)', re.IGNORECASE),
        'librettist': re.compile(r'^Text\s*:\s*(.*)', re.IGNORECASE),
        'chorale_text': re.compile(r'^Chorale\s*Text\s*:\s*(.*)', re.IGNORECASE),
        'composed_date': re.compile(r'^Compos(?:ed|\.)\s*:\s*(.*)', re.IGNORECASE),
    }

    def _flush():
        nonlocal current_key, buffer
        if current_key and buffer:
            value = ' '.join(buffer).strip()
            if current_key == 'occasion' and not metadata['occasion']:
                metadata['occasion'] = value
            elif current_key == 'librettist' and not metadata['librettist']:
                metadata['librettist'] = value
            elif current_key == 'chorale_text' and not metadata['chorale_text']:
                metadata['chorale_text'] = value
            elif current_key == 'composed_date' and not metadata['composed']:
                metadata['composed'] = value
        current_key = None
        buffer = []

    for line in lines:
        matched = False
        for key_name, pattern in KEY_PATTERNS.items():
            m = pattern.match(line)
            if m:
                _flush()
                current_key = key_name
                val = m.group(1).strip()
                if val:
                    buffer = [val]
                matched = True
                break

        if not matched:
            # Multi-word continuation detection: lines that look like
            # " Readings: Isaiah 7:10-16" or start a new section
            # Stop buffering if the line looks like a new section header
            if re.match(r'^(Readings|Epistle|Gospel|Biblical|Commentary|Perform|First|English|Interlinear|Translations)\b', line, re.IGNORECASE):
                _flush()
            elif re.match(r'^\d+\s+(Chorus|Recitative|Aria|Chorale|Duet|Sinfonia)\b', line, re.IGNORECASE):
                _flush()
            elif re.match(r'^BWV\b|^Cantata BWV\b|^[A-Z][a-z]+ quotations\b|^Note on the text\b', line, re.IGNORECASE):
                _flush()
            elif current_key:
                # Stop appending if buffer already has content that looks complete
                # (avoid capturing page footer/header text)
                if len(buffer) >= 5:
                    _flush()
                else:
                    buffer.append(line)

    _flush()

    # ── Extract Readings ──
    m_ep = re.search(
        r'Epistle:\s*(\d?\s*[A-Za-z]+)\s+(\d+)\s*:\s*(\d+(?:-\d+)?)',
        text, re.IGNORECASE
    )
    if m_ep:
        metadata['readings']['epistle'] = {
            'book': m_ep.group(1).strip(),
            'chapter': int(m_ep.group(2)),
            'verses': m_ep.group(3),
        }

    m_gosp = re.search(
        r'Gospel:\s*(\d?\s*[A-Za-z]+)\s+(\d+)\s*:\s*(\d+(?:-\d+)?)',
        text, re.IGNORECASE
    )
    if m_gosp:
        metadata['readings']['gospel'] = {
            'book': m_gosp.group(1).strip(),
            'chapter': int(m_gosp.group(2)),
            'verses': m_gosp.group(3),
        }

    # ── Extract movement info (multi-line table format + single-line) ──
    # Some cantata pages (like BWV 71) put movement number, type,
    # and instruments on separate lines inside a TABLE.

    # Strategy 1: Multi-line — look for a solo number line followed by type
    for i, line in enumerate(lines):
        m_num = re.match(r'^(\d+)$', line.strip())
        if m_num and i + 1 < len(lines):
            mv_num = int(m_num.group(1))
            next_line = lines[i + 1].strip()
            m_type = re.match(
                r'^(Chorus|Recitative|Aria|Chorale|Duet|Sinfonia|Arioso)'
                r'(?:\s*\[([^\]]*)\])?\s*(.*)$',
                next_line, re.IGNORECASE
            )
            if m_type:
                mv_type = m_type.group(1).strip()
                voices = m_type.group(2).strip() if m_type.group(2) else ''
                extra = m_type.group(3).strip() if m_type.group(3) else ''
                # Build full type string for display
                if extra:
                    mv_type = f'{mv_type} [{voices}] {extra}' if voices else f'{mv_type} {extra}'
                elif voices:
                    pass  # Keep mv_type as base type, voices stored separately

                # Next line might be instruments
                instruments = ''
                if i + 2 < len(lines):
                    inst_line = lines[i + 2].strip()
                    # Check if it looks like instruments (not lyrics)
                    if re.match(
                        r'^(?:Tromba|Timpani|Corno|Oboe|Flauto|Violino|Viola|'
                        r'Violoncello|Continuo|Organo|Cembalo|Fagotto|Violone|'
                        r'Traversa|Clarino|Taille|Trombone|Harfe|Lute)\b',
                        inst_line, re.IGNORECASE
                    ):
                        # Clean up — stop at first lyric word
                        idx_cont = inst_line.rfind('Continuo')
                        if idx_cont >= 0:
                            instruments = inst_line[:idx_cont + len('Continuo')].strip().rstrip(',').strip()
                        else:
                            instruments = inst_line

                # Avoid duplicates for the same movement number
                if not any(mi['number'] == mv_num for mi in metadata['movement_info']):
                    metadata['movement_info'].append({
                        'number': mv_num,
                        'type': mv_type,
                        'voices': voices,
                        'instruments': instruments,
                    })

    # Strategy 2: Single-line fallback (BWV 1 format)
    mv_pattern_single = re.compile(
        r'(\d+)\s+(Chorus|Recitative|Aria|Chorale|Duet|Sinfonia)\s*'
        r'(?:\[([^\]]+)\])?\s*'
        r'((?:(?:Tromba|Timpani|Corno|Oboe|Flauto|Violino|Viola|Violoncello|'
        r'Continuo|Organo|Cembalo|Fagotto|Violone|Traversa|Clarino|Taille|'
        r'Trombone)[^,]*,?\s*)+)',
        re.IGNORECASE
    )

    for line in lines:
        for m in mv_pattern_single.finditer(line):
            mv_num = int(m.group(1))
            # Skip if already found via multi-line strategy
            if any(mi['number'] == mv_num for mi in metadata['movement_info']):
                continue
            instruments_raw = m.group(4).strip().rstrip(',')
            idx = instruments_raw.rfind('Continuo')
            if idx >= 0:
                instruments_clean = instruments_raw[:idx + len('Continuo')].strip().rstrip(',').strip()
            else:
                instruments_clean = instruments_raw

            metadata['movement_info'].append({
                'number': mv_num,
                'type': m.group(2).strip(),
                'voices': m.group(3).strip() if m.group(3) else '',
                'instruments': instruments_clean,
            })

    # Strategy 3: chorale-cantata "Versus N [voices]" single-line format
    # (e.g. BWV 4). bach-cantatas.com lists these with the stanza number
    # embedded — no separate movement-number line. The movement number is
    # N+1 because the opening Sinfonia is movement 1.
    for i, line in enumerate(lines):
        m_v = re.match(
            r'^Versus\s+(\d+)\s*(.*)$',
            line.strip(), re.IGNORECASE
        )
        if not m_v:
            continue
        stanza = int(m_v.group(1))
        mv_num = stanza + 1
        # Voices may be bracketed ("[S, A, T, B]") or bare ("S A T B")
        voices = m_v.group(2).strip()
        voices = voices.strip('[]').strip()
        # Instruments on the following line
        instruments = ''
        if i + 1 < len(lines):
            inst_line = lines[i + 1].strip()
            if re.match(
                r'^(?:Tromba|Timpani|Corno|Oboe|Flauto|Violino|Viola|'
                r'Violoncello|Continuo|Organo|Cembalo|Fagotto|Violone|'
                r'Traversa|Clarino|Taille|Trombone|Cornetto)\b',
                inst_line, re.IGNORECASE
            ):
                idx_cont = inst_line.rfind('Continuo')
                if idx_cont >= 0:
                    instruments = inst_line[:idx_cont + len('Continuo')].strip().rstrip(',').strip()
                else:
                    instruments = inst_line
        # Avoid duplicates for the same movement number
        if not any(mi['number'] == mv_num for mi in metadata['movement_info']):
            metadata['movement_info'].append({
                'number': mv_num,
                'type': 'Chorale',
                'voices': voices,
                'instruments': instruments,
            })

    log.info(f"[Step 2] Extracted metadata: occasion={metadata['occasion'][:40]}..., "
             f"{len(metadata['movement_info'])} movements info")

    # Post-process: extract voices from type field when voices is empty
    # E.g., "Aria (Duet) [Soprano (Soul), Bass (Jesus)]" → type="Aria", voices="(Duet) Soprano (Soul), Bass (Jesus)"
    for mi in metadata['movement_info']:
        mtype = mi.get('type', '')
        voices = mi.get('voices', '')
        if not voices and mtype:
            # Extract voices from type string: everything after the base type
            m = re.match(r'^(Chorus|Recitative|Aria|Chorale|Duet|Sinfonia|Arioso)\s*(.*)', mtype, re.IGNORECASE)
            if m and m.group(2).strip():
                mi['voices'] = m.group(2).strip()
                mi['type'] = m.group(1)

    return metadata


def _extract_chorale_links(html_text):
    """Extract Chorale ID links from bach-cantatas.com page.

    Scans for patterns like:
      <a href="...Texts/Chorale007-Eng3.htm">
      /Texts/Chorale053-Eng3.htm

    Returns list of chorale IDs (e.g. ['Chorale007', 'Chorale053']).
    """
    ids = set()
    for m in re.finditer(r'/Texts/(Chorale\d{3,4})-Eng3\.htm', html_text, re.IGNORECASE):
        ids.add(m.group(1))
    for m in re.finditer(r'href="[^"]*(Chorale\d{3,4})-Eng3\.htm', html_text, re.IGNORECASE):
        ids.add(m.group(1))
    return sorted(ids)


def _extract_persons_role_map(html_text):
    """Extract role→voice mapping from bach-cantatas.com Persons: line.

    Parses patterns like:
      Persons: Fear (Alto), Hope (Tenor), Christ (Bass)

    Returns dict: {'Alto': 'Fear', 'Tenor': 'Hope', 'Bass': 'Christ'}
    Empty dict if no Persons line found.
    """
    # Voice abbreviation → full name (bach-cantatas.com uses full names)
    VOICE_FULL = {'alto': 'Alto', 'tenor': 'Tenor', 'bass': 'Bass',
                  'soprano': 'Soprano', 'sopran': 'Soprano'}
    role_map = {}

    m = re.search(r'Persons?:?\s*</B>?\s*(.+?)</TD>', html_text, re.IGNORECASE)
    if not m:
        return role_map

    persons_text = m.group(1)
    # Strip HTML tags
    persons_text = re.sub(r'<[^>]+>', ' ', persons_text)
    persons_text = re.sub(r'&nbsp;', ' ', persons_text)

    # Parse "Role (Voice), Role (Voice), ..."
    for part in re.split(r'[,;]\s*', persons_text):
        rm = re.match(r'(\S[\s\S]*?)\s*\(([^)]+)\)', part.strip())
        if rm:
            role = rm.group(1).strip()
            voice_raw = rm.group(2).strip().lower()
            voice_full = VOICE_FULL.get(voice_raw, voice_raw.title())
            role_map[voice_full] = role

    return role_map


# ═══════════════════════════════════════════════════════════════
# Bachipedia.org (J.S. Bach-Stiftung) — supplementary German readings
# ═══════════════════════════════════════════════════════════════

def _fetch_bachipedia(bwv):
    """Fetch the bachipedia.org work page for a BWV. Returns text or None."""
    url = config.URL_BACHIPEDIA.format(bwv=bwv)
    try:
        resp = requests.get(url, headers=config.HEADERS,
                            timeout=config.REQUEST_TIMEOUT, verify=False)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


# German book-name tokens used by bachipedia.org, longest-first so compound
# names (e.g. "Apostelgeschichte") match before shorter ones.
_BACHIPEDIA_BOOK_TOKENS = sorted(
    config.BOOK_GERMAN_REVERSE_MAP.keys(), key=len, reverse=True
)

_BACHIPEDIA_BOOK_PATTERN = re.compile(
    r'(?<![A-Za-z])('
    + '|'.join(re.escape(t) for t in _BACHIPEDIA_BOOK_TOKENS)
    + r')\s+(\d+)\s*(?:[,:]\s*(\d+(?:\s*[–-]\s*\d+)?))?'
)


def _extract_bachipedia_readings(html_text):
    """Extract Bible references from bachipedia.org prose (German book names).

    bachipedia.org articles embed references in prose like:
      "…die Verheissung des Messias … aus Jesaja 7 und die Ankündigung …
       aus Lukas 1."  /  "Offenbarung 22, 16: «Ich bin …»"

    Returns a list of reference dicts:
      [{'book': 'Isaiah', 'chapter': 7, 'verse': '', 'source': 'bachipedia'}, ...]
    """
    if not html_text:
        return []

    # Strip HTML tags, decode basic entities for readable prose.
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = re.sub(r'&nbsp;|&amp;|&quot;', ' ', text)

    refs = []
    seen = set()
    for m in _BACHIPEDIA_BOOK_PATTERN.finditer(text):
        book_de = m.group(1)
        book_en = config.BOOK_GERMAN_REVERSE_MAP.get(book_de)
        if not book_en:
            continue
        chapter = int(m.group(2))
        verse = (m.group(3) or '').replace(' ', '')
        key = (book_en, chapter, verse)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            'book': book_en,
            'chapter': chapter,
            'verse': verse,
            'source': 'bachipedia',
            'footnote_id': None,
        })

    return refs


def run(bwv_number, html_text=None):
    """Execute Step 2: extract background metadata.

    Args:
        bwv_number: int or str.
        html_text: Optional pre-fetched HTML.

    Returns:
        dict: metadata
    """
    bwv = str(bwv_number)
    if html_text is None:
        html_text = _fetch_page(bwv)
    metadata = _extract_metadata(html_text)

    # ── Extract chorale IDs from bach-cantatas.com links ──
    metadata['chorale_ids'] = _extract_chorale_links(html_text)
    if metadata['chorale_ids']:
        log.info(f"[Step 2] Extracted chorale links: {', '.join(metadata['chorale_ids'])}")

    # ── Extract Persons: role→voice mapping for dialogue works ──
    metadata['persons_role_map'] = _extract_persons_role_map(html_text)
    if metadata['persons_role_map']:
        log.info(f"[Step 2] Persons role map: {metadata['persons_role_map']}")

    # ── Supplementary readings from bachipedia.org ──
    bachipedia_html = _fetch_bachipedia(bwv)
    bachipedia_refs = _extract_bachipedia_readings(bachipedia_html)
    metadata['readings']['bachipedia'] = bachipedia_refs
    if bachipedia_refs:
        log.info(f"[Step 2] bachipedia.org readings: {len(bachipedia_refs)} refs")

    # Apply hardcoded fallback for missing fields
    if not metadata.get('composed') and bwv in BWV_COMPOSED_FALLBACK:
        metadata['composed'] = BWV_COMPOSED_FALLBACK[bwv]
        log.info(f"[Step 2] Composed date set from fallback: {metadata['composed']}")

    return metadata


def save(metadata, folder_path):
    """Save metadata as JSON."""
    data_dir = os.path.join(folder_path, 'data')
    with open(os.path.join(data_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    log.info("[Step 2] Saved metadata.json")
