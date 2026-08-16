# -*- coding: utf-8 -*-
"""Chorale index builder — parses bach-cantatas.com chorale text index.

The index page uses old-school HTML tables: each chorale entry is a
<TR><TD><P>...</P></TD></TR> row. Letter sections (A-Z) are marked
by <A NAME="A"> anchors.

Supports progressive building: each letter section is parsed independently
and saved atomically. Interrupted builds resume from the next incomplete letter.
"""

import json
import os
import re
import time
import traceback

import requests
from bs4 import BeautifulSoup

from . import chorale_config as cfg


# ═══════════════════════════════════════════════════════════════
# URL helpers
# ═══════════════════════════════════════════════════════════════

def _abs_url(path):
    """Convert a relative URL to absolute."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return cfg.URL_CHORALE_BASE + path


# ═══════════════════════════════════════════════════════════════
# Index loading / saving
# ═══════════════════════════════════════════════════════════════

def load_index():
    """Load existing chorale_index.json. Returns dict with expected keys."""
    if not os.path.exists(cfg.INDEX_FILE):
        return {
            'chorales': [],
            'bwv_lookup': {},
            'build_state': {
                'letters_completed': [],
                'last_completed_letter': None,
                'total_entries_so_far': 0,
            }
        }
    with open(cfg.INDEX_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('chorales', [])
    data.setdefault('bwv_lookup', {})
    data.setdefault('build_state', {})
    bs = data['build_state']
    bs.setdefault('letters_completed', [])
    bs.setdefault('last_completed_letter', None)
    bs.setdefault('total_entries_so_far', 0)
    return data


def save_index(data):
    """Atomically save index data to chorale_index.json."""
    data['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    tmp = cfg.INDEX_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, cfg.INDEX_FILE)


def lookup_by_bwv(bwv_number):
    """Return list of chorale entries matching a BWV number.

    Uses bwv_lookup (fast) with a cross-reference fallback across ALL
    chorales' bwv_usages entries (catches indexer omissions).
    """
    data = load_index()
    bwv_str = str(bwv_number)
    bwv_norm = re.sub(r'\s+', '', bwv_str)

    # ── Primary: bwv_lookup ──
    indices = set(data.get('bwv_lookup', {}).get(bwv_str, []))
    if not indices:
        indices = set(data.get('bwv_lookup', {}).get(bwv_norm, []))

    # ── Fallback: full-index bwv_usages cross-reference ──
    for ci, entry in enumerate(data.get('chorales', [])):
        for usage in entry.get('bwv_usages', []):
            u_bwv = str(usage.get('bwv', '')).strip()
            u_norm = re.sub(r'\s+', '', u_bwv)
            if u_bwv == bwv_str or u_norm == bwv_norm:
                indices.add(ci)
                break

    result = []
    for idx in sorted(indices):
        if idx < len(data.get('chorales', [])):
            result.append(data['chorales'][idx])
    return result


# ═══════════════════════════════════════════════════════════════
# Index page fetching
# ═══════════════════════════════════════════════════════════════

def _fetch_html():
    """Fetch the chorale text index page HTML."""
    for attempt in range(1, cfg.MAX_RETRIES + 1):
        try:
            resp = requests.get(
                cfg.URL_CHORALE_INDEX,
                headers=cfg.HEADERS,
                timeout=cfg.REQUEST_TIMEOUT,
                verify=False,
            )
            resp.raise_for_status()
            # Force UTF-8 — the page declares windows-1255 but content is actually
            # mostly ASCII with some Latin-1 characters
            resp.encoding = 'latin-1'
            html = resp.text
            # Re-encode to get proper UTF-8
            return html
        except requests.RequestException as e:
            print(f"  [WARN] Attempt {attempt} failed: {e}")
            if attempt < cfg.MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(
                    f"Failed to fetch {cfg.URL_CHORALE_INDEX}: {e}"
                ) from e


# ═══════════════════════════════════════════════════════════════
# BWV usage extraction
# ═══════════════════════════════════════════════════════════════

def _extract_bwv_usages(text):
    """Parse 'Bach's Works: BWV 4/2-8; BWV 253; BWV Anh 4a/5' into list."""
    usages = []
    # Allow optional spaces around slashes: "BWV 6 /3" or "BWV 6/3"
    pattern = re.compile(
        r'BWV\s+(Anh\s+)?(\d+[a-z]?)\s*(?:/\s*(\d+(?:-\d+)?))?',
        re.IGNORECASE
    )
    for m in pattern.finditer(text):
        prefix = (m.group(1) or '').strip()
        num = m.group(2)
        bwv = f'{prefix}{num}'.strip() if prefix else num
        movements = m.group(3) or None
        usages.append({'bwv': bwv, 'movements': movements})
    return usages


# ═══════════════════════════════════════════════════════════════
# Table-based HTML parsing
# ═══════════════════════════════════════════════════════════════

def _parse_index_html(html):
    """Parse the index HTML into a structured dict of letter → entries.

    The page uses <TR><TD><P> rows for each entry, with <A NAME="X">
    markers for letter section boundaries.
    """
    soup = BeautifulSoup(html, 'html.parser')
    result = {}
    current_letter = None

    # Find all tables
    all_tables = soup.find_all('table')

    if not all_tables:
        return result

    # Find the table with the most chorale content
    target_table = None
    max_chorale_rows = 0
    for tbl in all_tables:
        count = 0
        for row in tbl.find_all('tr'):
            td = row.find('td')
            if not td:
                continue
            text_parts = td.get_text() or ''
            if any(phrase in text_parts.lower() for phrase in
                   ('author', "bach's works", 'chorale melody')):
                count += 1
        if count > max_chorale_rows:
            max_chorale_rows = count
            target_table = tbl

    if not target_table:
        print("  [WARN] Could not find chorale content table")
        return result

    # Parse rows
    all_rows = target_table.find_all('tr')
    processed = 0

    for row in all_rows:
        td = row.find('td')
        if not td:
            continue

        row_html = str(row)

        # Check for letter section marker
        letter_match = re.search(r'<[aA]\s+[nN][aA][mM][eE]\s*=\s*"([A-Z])"', row_html)
        if letter_match:
            letter = letter_match.group(1)
            if letter != current_letter:
                current_letter = letter
                result.setdefault(letter, [])
            continue

        # Get paragraph content
        pt = td.find('p')
        entry_html = str(pt) if pt else str(td)
        entry_text = pt.get_text(separator=' ') if pt else td.get_text(separator=' ')

        entry_text = entry_text.strip()
        if not entry_text or len(entry_text) < 10:
            continue

        # Skip non-chorale lines (navigation, headers, descriptions)
        low = entry_text.lower()[:60]
        skip_phrases = (
            'choral', 'index', 'back to', 'terms of',
            'prepared by', 'last update', 'copyright',
            'this section of the bach cantatas website',
            'home page', 'recordings/discussions', 'introduction',
            'chorales bwv 250', 'details and recordings',
            'individual recordings', 'chorales text used',
            'texts & english translations',
        )
        if any(phrase in low for phrase in skip_phrases):
            continue

        # Parse the entry
        entry = _parse_entry_from_td(entry_html)
        if entry and current_letter:
            result.setdefault(current_letter, []).append(entry)
            processed += 1

    print(f"  [PARSE] Found {processed} entries across {len(result)} letter sections")
    return result


def _parse_entry_from_td(td_html):
    """Parse a single chorale entry from a <P> inside a <TD>.

    BeautifulSoup's get_text() splits inline <a> tags into separate lines,
    so we parse the HTML structure directly: title text from the first line,
    then join all subsequent content as a single metadata block.
    """
    soup = BeautifulSoup(td_html, 'html.parser')

    pt = soup.find('p')
    if not pt:
        return None

    # Extract all text — use space separator to keep inline elements together
    full_text = pt.get_text(separator=' ').strip()
    # Collapse multiple spaces
    full_text = re.sub(r'\s+', ' ', full_text)

    if not full_text or len(full_text) < 10:
        return None

    title_line = full_text

    # ── Cross-reference entry (supports both '>' and '&gt;') ──
    cross_ref_match = re.match(r'^(.+?)\s*(?:>|&gt;)\s*(.+)$', title_line)
    if cross_ref_match:
        return {
            'is_cross_reference': True,
            'title': cross_ref_match.group(1).strip(),
            'target_title': cross_ref_match.group(2).strip(),
            'detail_available': False,
            'detail_url': None,
        }

    # ── Standard entry ──
    entry = {
        'title': title_line,
        'detail_url': None,
        'detail_available': False,
        'chorale_id': None,
        'author': '',
        'melody': '',
        'composer': '',
        'ekg': '',
        'bwv_usages': [],
        'is_cross_reference': False,
    }

    # Extract detail URL from the first chorale link
    for a in pt.find_all('a', href=True):
        href = a['href']
        m = re.search(r'(Chorale\d+(?:-\d+)?)-Eng3\.htm', href)
        if m:
            chorale_id = m.group(1)
            actual_url = href if href.startswith('http') else f'{cfg.URL_CHORALE_BASE}{href}'
            entry['detail_url'] = actual_url
            entry['detail_available'] = True
            entry['chorale_id'] = chorale_id
            break

    # Parse metadata from the full text (all lines joined as one string)
    # Author: "Authors: Philipp Melanchthon / Nikolaus Selnecker"
    author_match = re.search(
        r'(?:Author|Authors)\s*:\s*(.+?)(?:\s*\|\s*Bach|$)', full_text, re.IGNORECASE
    )
    if author_match:
        raw = author_match.group(1).strip()
        # Clean excessive whitespace from inline tags
        raw = re.sub(r'\s*/\s*', ' / ', raw)
        raw = re.sub(r'\s+', ' ', raw)
        entry['author'] = raw.strip()

    # Bach's Works: "Bach's Works: BWV 6 /3; BWV 253 ; BWV Anh 4a /5"
    works_match = re.search(
        r"Bach'?s\s+Works?\s*:\s*(.+)$", full_text, re.IGNORECASE
    )
    if works_match:
        raw = works_match.group(1).strip()
        # Normalize spaces: "BWV 6 /3" → "BWV 6/3", "BWV 253" stays
        # Remove spaces around slashes and semicolons
        entry['bwv_usages'] = _extract_bwv_usages(raw)

    # Chorale Melody
    melody_match = re.search(
        r'(?:Chorale\s+)?Melody\s*:\s*(.+?)(?:\s*\||$)', full_text, re.IGNORECASE
    )
    if melody_match:
        entry['melody'] = melody_match.group(1).strip()

    # Composer
    composer_match = re.search(
        r'Composer\s*:\s*(.+?)(?:\s*\||$)', full_text, re.IGNORECASE
    )
    if composer_match:
        entry['composer'] = composer_match.group(1).strip()

    # Extract EKG
    m = re.search(r'\(EKG\s+(\d+(?:,\s*\d+)*)\)', title_line)
    if m:
        entry['ekg'] = m.group(1)

    # Extract EG (Evangelisches Gesangbuch)
    m = re.search(r'\(EG\s+(\d+(?:,\s*\d+)*)\)', title_line)
    if m and not entry['ekg']:
        entry['ekg'] = m.group(1)

    # Status markers
    if re.search(r'(\[missing translation\]|\[partial translation\])', title_line, re.IGNORECASE):
        entry['status'] = 'missing_or_partial'
    if re.search(r'\bNEW\b', title_line):
        entry['status'] = 'NEW'
    if re.search(r'\bUPDATE\b', title_line):
        entry['status'] = 'UPDATE'

    # Not used by Bach
    if re.search(r'Not used by J\.S\.\s*Bach', full_text, re.IGNORECASE):
        entry['not_used_by_bach'] = True

    return entry


# ═══════════════════════════════════════════════════════════════
# Progressive build
# ═══════════════════════════════════════════════════════════════

def build_index_progressive(from_scratch=False, max_letters=None):
    """Build or continue building the chorale index progressively.

    Args:
        from_scratch: clear existing progress and start from A
        max_letters: maximum letters to process this run (None = all)

    Returns:
        dict with keys: new_entries, letters_processed, total_entries
    """
    data = load_index()

    if from_scratch:
        data['chorales'] = []
        data['bwv_lookup'] = {}
        data['build_state'] = {
            'letters_completed': [],
            'last_completed_letter': None,
            'total_entries_so_far': 0,
            'started_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        save_index(data)
        print("  [INFO] Cleared previous index, starting from A")

    completed = set(data['build_state'].get('letters_completed', []))
    letters_to_process = [l for l in cfg.ALPHABET if l not in completed]

    if not letters_to_process:
        print("  [INFO] Index is already complete (all A-Z processed)")
        return {
            'new_entries': 0,
            'letters_processed': 0,
            'total_entries': len(data['chorales']),
        }

    if max_letters:
        letters_to_process = letters_to_process[:max_letters]

    print(f"  [INFO] Fetching index page...")
    html = _fetch_html()
    print(f"  [INFO] Page fetched ({len(html)} bytes)")

    # Parse all letter sections
    parsed = _parse_index_html(html)

    new_entries = 0
    letters_done = 0

    for letter in letters_to_process:
        if letter not in parsed:
            # No entries for this letter — mark as complete anyway
            completed.add(letter)
            data['build_state']['letters_completed'] = sorted(completed)
            data['build_state']['last_completed_letter'] = letter
            save_index(data)
            continue

        entries = parsed[letter]
        print(f"  [BUILD] Letter '{letter}': {len(entries)} entries")

        for entry in entries:
            if entry.get('is_cross_reference'):
                continue

            chorale_id = entry.get('chorale_id')
            entry_id = chorale_id or re.sub(
                r'[^a-zA-Z0-9]', '_', entry.get('title', 'unknown')
            )[:50]

            # Deduplicate
            existing_ids = {e.get('id', '') for e in data['chorales']}
            if entry_id in existing_ids:
                continue

            entry['id'] = entry_id

            # Add to list
            idx = len(data['chorales'])
            data['chorales'].append(entry)

            # Update BWV lookup
            for usage in entry.get('bwv_usages', []):
                bwv_str = str(usage['bwv'])
                data['bwv_lookup'].setdefault(bwv_str, [])
                if idx not in data['bwv_lookup'][bwv_str]:
                    data['bwv_lookup'][bwv_str].append(idx)

            new_entries += 1

        letters_done += 1
        completed.add(letter)
        data['build_state']['letters_completed'] = sorted(completed)
        data['build_state']['last_completed_letter'] = letter
        data['build_state']['total_entries_so_far'] = len(data['chorales'])

        # Save after each letter
        save_index(data)
        print(f"  [SAVED] Letter '{letter}' done. "
              f"Total: {len(data['chorales'])}, "
              f"BWV maps: {len(data['bwv_lookup'])}")

        time.sleep(0.5)

    data['built_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    save_index(data)

    print(f"\n  [DONE] {letters_done} letters, {new_entries} new. "
          f"Total: {len(data['chorales'])} chorales indexed.")

    return {
        'new_entries': new_entries,
        'letters_processed': letters_done,
        'total_entries': len(data['chorales']),
    }


# ═══════════════════════════════════════════════════════════════
# Status helper
# ═══════════════════════════════════════════════════════════════

def print_index_status():
    """Print current index status."""
    data = load_index()
    total = len(data['chorales'])
    completed = data['build_state'].get('letters_completed', [])
    print(f"Chorale Index Status:")
    print(f"  Total entries:  {total}")
    print(f"  Letters done:   {', '.join(completed) if completed else '(none)'}")
    print(f"  BWV mappings:   {len(data['bwv_lookup'])}")
    bwvs = sorted(data['bwv_lookup'].keys(),
                  key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
    if bwvs:
        preview = ', '.join(bwvs[:30])
        suffix = '...' if len(bwvs) > 30 else ''
        print(f"  BWV numbers:    {preview}{suffix}")
