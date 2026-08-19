# -*- coding: utf-8 -*-
"""Chorale detail page scraper — extracts structured data from chorale detail pages.

Scrapes https://www.bach-cantatas.com/Texts/ChoraleNNN-Eng3.htm pages.
"""

import json
import os
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from . import chorale_config as cfg


def _fetch_html(url):
    """Fetch a chorale detail page. Returns BeautifulSoup object."""
    for attempt in range(1, cfg.MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=cfg.HEADERS,
                timeout=cfg.REQUEST_TIMEOUT,
                verify=False,
            )
            resp.raise_for_status()
            # bach-cantatas.com declares iso-8859-1 but uses windows-1252
            # (e-acute at 0xe9 is windows-1252, not latin-1).
            # Decode from raw bytes to preserve all characters.
            raw_html = resp.content.decode('windows-1252', errors='replace')
            return BeautifulSoup(raw_html, 'html.parser')
        except requests.RequestException as e:
            print(f"  [WARN] Attempt {attempt} failed: {e}")
            if attempt < cfg.MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Failed to fetch {url}: {e}") from e


def _extract_metadata(soup):
    """Extract metadata fields from the chorale detail page.

    Parses page text line-by-line, detecting labels (Author:, Melody:, etc.)
    and collecting subsequent non-label lines as values until the next label.

    Returns dict with keys: title, ekg, author, author_year, melody, composer,
    composer_year, theme, description
    """
    meta = {
        'title': '',
        'ekg': '',
        'author': '',
        'author_year': '',
        'melody': '',
        'composer': '',
        'composer_year': '',
        'theme': '',
        'description': '',
    }

    # Title: from page <title> element
    # Formats: "Chorale Text: XXXX - Text & English Translation" or "Chorale: XXXX -"
    title_elem = soup.find('title')
    if title_elem:
        title_text = title_elem.get_text(strip=True)
        m = re.match(r'Chorale\s*(?:Text)?:\s*(.+?)\s*-\s*(?:Text|English)', title_text)
        if m:
            meta['title'] = m.group(1).strip()

    # Fallback: find the bolded chorale title in the body
    if not meta['title']:
        for b in soup.find_all('b'):
            bt = b.get_text(strip=True)
            if 'Text and Translation of Chorale' in bt:
                m = re.search(
                    r'Vocal\s+Works\s*(.+?)\s*Text\s+and\s+Translation\s+of\s+Chorale',
                    bt, re.IGNORECASE
                )
                if m:
                    meta['title'] = m.group(1).strip()
                break

    # ── Line-by-line parsing ──
    # Use newline separator so each line is a logical unit
    full_text = soup.get_text(separator='\n')
    lines = [l.strip() for l in full_text.split('\n')]

    # Labels we care about, mapped to their meta key + year-sub-key
    LABELS = {
        'Author:':     ('author', 'author_year'),
        'Melody:':     ('melody', None),   # melody has no year sub-key
        'Composer:':   ('composer', 'composer_year'),
        'Theme:':      ('theme', None),
        'Description:': ('description', None),
    }
    # Extra labels that may appear bundled with Melody (from " (Zahn NNN) | Composer:")
    SUB_LABELS = ['Composer:', 'Melody:', 'Theme:', 'Description:']

    current_label = None
    current_value_lines = []

    def _finalize_value():
        """Save collected lines to meta dict."""
        if not current_label:
            return
        key, year_key = LABELS.get(current_label, (None, None))
        if not key:
            return

        value = ' '.join(current_value_lines).strip()

        # Split off trailing " | Composer:" or " Theme:" from melody/composer lines
        for sub_label in SUB_LABELS:
            pipe_idx = value.find(f' | {sub_label}')
            if pipe_idx >= 0:
                # Keep everything before the pipe
                value = value[:pipe_idx].strip()
                break

        # Extract year in parentheses: "(1599)", "(1597/99)", "(1597; published 1599)"
        if year_key:
            year_match = re.search(r'\((\d{4})(?:[/;][^)]*)?\)', value)
            if year_match:
                meta[year_key] = year_match.group(1)
                value = re.sub(r'\s*\(\d{4}[^)]*\)', '', value).strip()
            # Also check in collected lines
            if not meta[year_key]:
                for l in current_value_lines:
                    ym = re.search(r'\((\d{4})(?:[/;][^)]*)?\)', l)
                    if ym:
                        meta[year_key] = ym.group(1)
                        break

        meta[key] = value
        meta[key] = re.sub(r'\s+', ' ', meta[key]).strip()  # normalize whitespace

    for line in lines:
        if not line:
            # Empty line → possible section boundary
            if current_label is not None and current_value_lines:
                _finalize_value()
                current_label = None
                current_value_lines = []
            continue

        # Check if this line starts with a known label
        found_label = None
        for candidate_label in LABELS:
            if line.startswith(candidate_label):
                found_label = candidate_label
                break
        # Also check "EKG 48" or "EKG: 48" format
        ekg_match = re.search(r'EKG\s*:?\s*(\d+(?:\s*,\s*\d+)*)', line)
        if ekg_match:
            meta['ekg'] = ekg_match.group(1).strip()

        if found_label:
            # Save previous value
            if current_label is not None and current_value_lines:
                _finalize_value()

            current_label = found_label
            current_value_lines = []
            # Extract value on same line if present
            remainder = line[len(found_label):].strip()
            if remainder:
                current_value_lines.append(remainder)
        elif current_label is not None:
            # Continuation of current label's value
            # Stop if we hit an unrelated label
            if any(line.startswith(lb) for lb in LABELS):
                _finalize_value()
                current_label = None
                current_value_lines = []
                # Re-process this line as a potential new label
                for candidate_label in LABELS:
                    if line.startswith(candidate_label):
                        current_label = candidate_label
                        current_value_lines = []
                        remainder = line[len(candidate_label):].strip()
                        if remainder:
                            current_value_lines.append(remainder)
                        break
                continue

            # Check if this line contains a pipe-separated sub-label
            # e.g., " (Zahn 8359) | Composer:" → finalize current, switch to Composer
            pipe_label = None
            for sub_label in SUB_LABELS:
                if f' | {sub_label}' in line or f'| {sub_label}' in line:
                    pipe_label = sub_label
                    break

            if pipe_label:
                # Extract any text before the pipe as part of current value
                pipe_pos = line.find(f' | {pipe_label}')
                if pipe_pos < 0:
                    pipe_pos = line.find(f'| {pipe_label}')
                if pipe_pos >= 0:
                    pre_text = line[:pipe_pos].strip()
                    if pre_text:
                        current_value_lines.append(pre_text)
                _finalize_value()

                # Switch to the new label
                current_label = pipe_label
                current_value_lines = []
                remainder = line[pipe_pos + len(f' | {pipe_label}'):].strip()
                if remainder:
                    current_value_lines.append(remainder)
                continue

            current_value_lines.append(line)

    # Finalize last value
    if current_label is not None and current_value_lines:
        _finalize_value()

    return meta


def _extract_vocal_works(soup):
    """Extract the 'Vocal Works by J.S. Bach' table.

    Returns list of dicts with keys: ver, work, work_url, mvt, mvt_url, year,
    br, re_num, ke, di, bc, type
    """
    vocal_works = []

    # Find the table — it's after "Vocal Works by J.S. Bach:" text
    # Look for <table> elements
    tables = soup.find_all('table')

    target_table = None
    for table in tables:
        # Check if table contains vocal works headers
        table_text = table.get_text()
        if 'Ver' in table_text and 'Work' in table_text and 'Mvt.' in table_text:
            target_table = table
            break

    if not target_table:
        # Try to find by preceding text
        for elem in soup.find_all(string=re.compile(r'Vocal Works by J\.S\.\s*Bach', re.IGNORECASE)):
            # Find the following table
            table = elem.find_next('table')
            if table:
                target_table = table
                break

    if not target_table:
        return vocal_works

    # Parse table rows
    rows = target_table.find_all('tr')
    header_skipped = False

    for row in rows:
        cells = row.find_all(['td', 'th'])
        if not cells or len(cells) < 4:
            continue

        # Get cell text
        cell_texts = [c.get_text(strip=True) for c in cells]

        # Skip header row
        if not header_skipped:
            if cell_texts[0] in ('Ver', '') or 'Ver' in ' '.join(cell_texts):
                header_skipped = True
                continue

        # Skip empty or spacer rows
        if all(t == '' or t == '-' or t == '\xa0' for t in cell_texts):
            continue

        ver = cell_texts[0] if len(cell_texts) > 0 else ''
        if not ver or ver in ('Ver', '') or ver == '\xa0':
            continue

        # Extract work link
        work_elem = cells[1].find('a') if len(cells) > 1 else None
        work_text = cells[1].get_text(strip=True) if len(cells) > 1 else ''
        work_url = work_elem.get('href', '') if work_elem else ''

        # Extract mvt link
        mvt_elem = cells[2].find('a') if len(cells) > 2 else None
        mvt_text = cells[2].get_text(strip=True) if len(cells) > 2 else ''
        mvt_url = mvt_elem.get('href', '') if mvt_elem else ''

        entry = {
            'ver': ver,
            'work': work_text,
            'work_url': work_url,
            'mvt': mvt_text,
            'mvt_url': mvt_url,
            'year': cell_texts[3] if len(cell_texts) > 3 else '',
            'br': cell_texts[4] if len(cell_texts) > 4 else '',
            're_num': cell_texts[5] if len(cell_texts) > 5 else '',
            'ke': cell_texts[6] if len(cell_texts) > 6 else '',
            'di': cell_texts[7] if len(cell_texts) > 7 else '',
            'bc': cell_texts[8] if len(cell_texts) > 8 else '',
            'type': cell_texts[9] if len(cell_texts) > 9 else '',
        }
        vocal_works.append(entry)

    # Fallback: if table-based parse found nothing, try text-line parsing
    if not vocal_works:
        print(f"  [PARSE] Table format found 0 entries, trying table-row format...")
        vocal_works = _extract_vocal_works_from_text(soup)

    return vocal_works


def _extract_vocal_works_from_text(soup):
    """Fallback: parse vocal works from table rows when no dedicated table exists.

    Scans ALL tables for the 'Vocal Works by J.S. Bach' heading row, then parses
    each subsequent row as a vocal work entry until 'German Text' is reached.
    Returns the best result (most entries) across all candidate tables.
    """
    best_works = []

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 8:
            continue

        # Find row containing "Vocal Works by J.S. Bach"
        start_idx = None
        for i, row in enumerate(rows):
            row_text = row.get_text(' ', strip=True)
            if re.search(r'Vocal Works by J\.S\.\s*Bach\b', row_text, re.IGNORECASE):
                start_idx = i
                break

        if start_idx is None:
            continue

        # Parse subsequent rows
        candidate = []
        for i in range(start_idx + 1, min(start_idx + 20, len(rows))):
            row = rows[i]
            row_text = row.get_text(' ', strip=True)

            if not row_text:
                continue
            if re.match(r'German\s+Text\b', row_text, re.IGNORECASE):
                break
            if 'English Translation by' in row_text:
                break

            entry = _parse_vocal_work_line(row_text)
            if entry:
                candidate.append(entry)

        if len(candidate) > len(best_works):
            best_works = candidate

    return best_works


def _normalize_vocal_works(vocal_works):
    """Normalize vocal works entries to canonical field names.

    Two code paths produce different fields:
      - Table parser:  {'ver': '1', 'work': 'BWV 4', 'mvt': 'Mvt. 2', 'bc': 'A54:2', ...}
      - Text parser:   {'bwv': '4', 'movement': '2', 'verse': '1', 'bc': '', ...}

    Normalize both to: {'verse': str, 'bwv': str, 'movement': str, 'bc': str, ...}
    """
    for entry in vocal_works:
        # Normalize verse / ver
        if 'ver' in entry and 'verse' not in entry:
            entry['verse'] = entry.pop('ver')
        if 'verse' not in entry:
            entry['verse'] = ''

        # Normalize bwv / work ("BWV 4" → "4")
        if 'work' in entry and 'bwv' not in entry:
            raw = entry.pop('work', '')
            m = re.search(r'BWV\s*((?:Anh\.?\s*)?\d+)', raw)
            entry['bwv'] = m.group(1).strip() if m else raw
        if 'bwv' not in entry:
            entry['bwv'] = ''

        # Normalize movement / mvt ("Mvt. 2" → "2")
        if 'mvt' in entry and 'movement' not in entry:
            raw = entry.pop('mvt', '')
            m = re.search(r'Mvt\.\s*(\d+[ab]?)', raw)
            entry['movement'] = m.group(1) if m else raw
        if 'movement' not in entry:
            entry['movement'] = ''


def _parse_vocal_work_line(line):
    """Parse a single vocal work entry line into a structured dict.

    Handles formats:
      "Chorus Title (Mvt. 1) from Cantata BWV 1 (1725) (verse 1)"
      "Chorale Title, BWV 436"
      "Organ-chorale: BWV 739"
    """
    # Pattern 1: "(Mvt. N) from ... BWV N (YYYY)"
    # Spaces allowed inside parentheses — some pages use " ( Mvt. 1 ) "
    m = re.search(
        r'\(\s*Mvt\.\s*(\d+[ab]?)\s*\)\s+from\s+'
        r'(?:Cantata|Cantatas|cantata|Words|Chorale)\s+'
        r'BWV\s+((?:Anh\.?\s*)?\d+)\s*'
        r'(?:\(\s*(\d{4})\s*\))?'
        r'(?:\s*\(([^)]*)\))?',
        line, re.IGNORECASE
    )
    if m:
        # Extract type prefix from start of line
        type_match = re.match(
            r'^(Chorus|Chorale(?:\s+for\s+\S+(?:\s*&\s*\S+)?)?'
            r'|Aria(?:\s+for\s+\S+(?:\s+with\s+Chorale\s+for\s+\S+)?)?'
            r'|Recitative|Arioso|Sinfonia)',
            line, re.IGNORECASE
        )
        work_type = type_match.group(1) if type_match else ''

        # Title = everything before "(Mvt."
        title = re.sub(r'\s*\(Mvt\.\s*\d+[ab]?\).*$', '', line).strip()
        if work_type and title.lower().startswith(work_type.lower()):
            title = title[len(work_type):].strip()

        # Extract verse number
        verse_match = re.search(r'(?:last\s+.*?\s+)?verse\s*(\d+)', line, re.IGNORECASE)

        return {
            'bwv': m.group(2).strip(),
            'movement': m.group(1),
            'type': work_type,
            'title': title[:150],
            'verse': verse_match.group(1) if verse_match else '',
            'year': m.group(3) or '',
        }

    # Pattern 2: "Chorale Title, BWV NNN" (independent chorale)
    m2 = re.match(
        r'^(Chorale(?:-Chorus)?)\s+(.+?),?\s*BWV\s+(\d+)',
        line, re.IGNORECASE
    )
    if m2:
        return {
            'bwv': m2.group(3), 'movement': '', 'type': m2.group(1),
            'title': m2.group(2).strip()[:150], 'verse': '', 'year': '',
        }

    # Pattern 3: "Organ-chorale : BWV NNN" (colon may have leading space)
    m3 = re.match(r'^Organ-chorale\s*:\s*BWV\s+(\d+)', line, re.IGNORECASE)
    if m3:
        return {
            'bwv': m3.group(1), 'movement': '', 'type': 'Organ-chorale',
            'title': '', 'verse': '', 'year': '',
        }

    return None


def _extract_chorale_text(soup):
    """Extract German original text and English translation.

    The detail page uses a SINGLE large table. Within this table, the
    German/English text section appears as sequential cells:
      [GERMAN TEXT header] [ENGLISH TRANSLATION header]
      [1] [German verse 1] [English verse 1]
      [2] [German verse 2] [English verse 2]
      ...

    We find the main table, scan for the "German Text" cell, then parse
    consecutive triples of (verse_num, german, english).
    """
    german_text = {}
    english_text = {}

    # Find the main content table (the one with most cells)
    all_tables = soup.find_all('table')
    main_table = None
    max_cells = 0
    for tbl in all_tables:
        n_cells = len(tbl.find_all(['td', 'th']))
        if n_cells > max_cells:
            max_cells = n_cells
            main_table = tbl

    if not main_table:
        return {'german': german_text, 'english': english_text}

    # Collect all table cells in order
    all_rows = main_table.find_all('tr')
    all_cells = []
    for row in all_rows:
        cells = row.find_all(['td', 'th'])
        all_cells.extend(cells)

    # Find the start of the German Text section
    start_idx = None
    for i, cell in enumerate(all_cells):
        txt = cell.get_text(strip=True)
        if re.match(r'German\s+Text', txt, re.IGNORECASE):
            start_idx = i
            break

    if start_idx is None:
        return {'german': german_text, 'english': english_text}

    # The German Text cell is at start_idx.
    # Next: English Translation header (skip), then verse triples begin.
    # Each triple: (verse_number, german_text, english_text)
    idx = start_idx + 2  # Skip German Text cell, skip English Translation cell

    while idx + 2 < len(all_cells):
        verse_cell = all_cells[idx]
        german_cell = all_cells[idx + 1]
        english_cell = all_cells[idx + 2]

        verse_text = verse_cell.get_text(strip=True)

        # Stop conditions
        if verse_text in ('--', '---', ''):
            break
        if 'English Translation by' in verse_text:
            break
        if 'Contributed by' in verse_text:
            break
        if verse_text.startswith('Chorales BWV'):
            break
        if verse_text.startswith('Terms of'):
            break

        try:
            verse_num = int(verse_text)
        except (ValueError, TypeError):
            idx += 1
            continue

        # Extract German lines
        german_lines = _extract_verse_lines(german_cell)
        # Check if text is bold (set by Bach)
        german_has_bold = _cell_has_bold(german_cell)
        german_text[verse_num] = {'lines': german_lines, 'bold': german_has_bold}

        # Extract English lines
        english_lines = _extract_verse_lines(english_cell)
        eng_has_bold = _cell_has_bold(english_cell)
        english_text[verse_num] = {'lines': english_lines, 'bold': eng_has_bold}

        idx += 3

    # Fallback: if triple-cell format found 0 verses, try row-based format
    if not german_text:
        texts = _extract_chorale_text_row_format(soup)
        german_text = texts['german']
        english_text = texts['english']

    return {'german': german_text, 'english': english_text}


def _extract_chorale_text_row_format(soup):
    """Fallback parser: extract verses from table rows with 2 cells per verse.

    Some detail pages (e.g. Chorale015) put the German/English text in a main
    table where each verse is a <TR> with two <TD> cells (German, English),
    and the verse number is embedded in the German cell text.
    """
    german_text = {}
    english_text = {}

    # Find the main content table — table with most cells
    all_tables = soup.find_all('table')
    main_table = None
    max_cells = 0
    for tbl in all_tables:
        n_cells = len(tbl.find_all(['td', 'th']))
        if n_cells > max_cells:
            max_cells = n_cells
            main_table = tbl

    if not main_table:
        return {'german': german_text, 'english': english_text}

    rows = main_table.find_all('tr')

    # Locate the "German Text" / "English Translation" header row
    start_row = None
    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 2:
            txt0 = cells[0].get_text(strip=True)
            if re.match(r'German\s+Text', txt0, re.IGNORECASE):
                start_row = i
                break

    if start_row is None:
        return {'german': german_text, 'english': english_text}

    # Parse verse rows (header row + 1 onwards)
    for i in range(start_row + 1, len(rows)):
        row = rows[i]
        cells = row.find_all('td')
        if len(cells) < 2:
            continue

        ger_cell = cells[0]
        eng_cell = cells[1]

        ger_text = ger_cell.get_text(' ', strip=True)
        eng_text = eng_cell.get_text(' ', strip=True)

        # Stop conditions
        if not ger_text and not eng_text:
            break
        if 'English Translation by' in ger_text:
            break
        if 'Contributed by' in ger_text:
            break

        # Extract verse number from e.g. "1. Wie schön leuchtet..."
        vm = re.match(r'(\d+)\.\s', ger_text)
        if not vm:
            continue

        verse_num = int(vm.group(1))

        # Extract German lines (use <br>-based splitting)
        ger_lines = _extract_verse_lines_from_cell(ger_cell)
        # Strip leading verse number from the first line
        if ger_lines:
            m = re.match(r'\d+\.\s*(.*)', ger_lines[0])
            if m:
                ger_lines[0] = m.group(1).strip()

        german_has_bold = _cell_has_bold(ger_cell)
        german_text[verse_num] = {'lines': ger_lines, 'bold': german_has_bold}

        # Extract English lines
        eng_lines = _extract_verse_lines_from_cell(eng_cell)
        english_text[verse_num] = {'lines': eng_lines, 'bold': False}

    print(f"  [PARSE] Row-format: German verses={len(german_text)}, English verses={len(english_text)}")
    return {'german': german_text, 'english': english_text}


def _extract_verse_lines_from_cell(cell):
    """Extract verse lines from a cell that uses <br/> tags for line breaks.

    Gets the raw cell content, splits on <br/> tags, then cleans each line.
    More reliable than get_text() for cells with inline line breaks.
    """
    lines = []
    # Convert cell to string, then split by <br> (case-insensitive)
    html = str(cell)
    # Find the actual content (inside the <td> tag)
    # Remove opening <td...> and closing </td>
    content = re.sub(r'^<td[^>]*>', '', html, flags=re.IGNORECASE)
    content = re.sub(r'</td>$', '', content, flags=re.IGNORECASE)
    # Split by <br> or <br/>
    parts = re.split(r'<br\s*/?\s*>', content, flags=re.IGNORECASE)
    # Use BeautifulSoup to extract text from each part
    from bs4 import BeautifulSoup
    for part in parts:
        sub = BeautifulSoup(part.strip(), 'html.parser')
        line = sub.get_text(strip=True)
        if line and line not in (',', '.', ';', ':', '!', '?'):
            # Skip navigation/header fragments
            if line.startswith('BWV ') and len(line) < 15:
                continue
            if line.startswith('Chorales BWV'):
                continue
            if line.startswith('Terms of'):
                continue
            # Skip a bare stanza number (e.g. "18." embedded in the last cell)
            if re.match(r'^\d{1,3}\.?$', line):
                continue
            lines.append(line)
    return lines


def _cell_has_bold(cell):
    """Check if a cell has bold/strong tags marking it as set by Bach.

    Some pages (e.g. Chorale015 verse 3) use empty bold markers like
    ``<b> </b>`` — any presence of <b> or <strong> in the cell signals
    Bach's use of that verse.
    """
    return bool(cell.find(['b', 'strong']))


def _extract_verse_lines(cell):
    """Extract individual verse lines from a table cell.

    Lines are typically separated by <BR> tags within a <P> element.
    """
    text = cell.get_text(separator='\n').strip()
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        # Skip empty lines, solitary punctuation, navigation text
        if not line or line in (',', '.', ';', ':', '!', '?'):
            continue
        # Skip lines that look like navigation/header metadata
        if line.startswith('BWV ') and '/' not in line and len(line) < 15:
            continue
        if line.startswith('Chorales BWV'):
            continue
        if line.startswith('Terms of'):
            continue
        # Skip a bare stanza number (e.g. "18." embedded in the last cell)
        if re.match(r'^\d{1,3}\.?$', line):
            continue
        lines.append(line)
    # Filter out lines that are just BWV number links
    filtered = []
    for line in lines:
        if re.match(r'^BWV\s+\d+$', line) and len(line) < 12:
            continue
        filtered.append(line)
    return filtered


def _extract_translator_info(soup):
    """Extract translator and source information."""
    full_text = soup.get_text(separator='\n')
    info = {'translator': '', 'source_links': []}

    # Find translator line
    trans_match = re.search(
        r'English Translation by\s*(.+?)(?:\n|$)',
        full_text, re.IGNORECASE
    )
    if trans_match:
        info['translator'] = trans_match.group(1).strip()

    # Find source links
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        if any(domain in href for domain in
               ('hymnary.org', 'liederindex.de', 'monarchieliga.de', 'gutenberg.org')):
            info['source_links'].append({
                'text': text,
                'url': href,
            })

    return info


def scrape_chorale_detail(chorale_id):
    """Scrape a chorale detail page and return structured data.

    Args:
        chorale_id: str, e.g., "Chorale012" or "Chorale012"

    Returns:
        dict with all extracted fields

    Raises:
        RuntimeError: if the page cannot be fetched
    """
    url = cfg.URL_CHORALE_DETAIL.format(chorale_id=chorale_id)
    print(f"  [SCRAPE] Fetching {url}")

    soup = _fetch_html(url)

    data = {
        'chorale_id': chorale_id,
        'source_url': url,
        'scraped_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    }

    # Extract metadata
    print(f"  [PARSE] Extracting metadata...")
    meta = _extract_metadata(soup)
    data.update(meta)

    # Extract vocal works table
    print(f"  [PARSE] Extracting vocal works table...")
    data['vocal_works'] = _extract_vocal_works(soup)
    print(f"  [PARSE] Found {len(data['vocal_works'])} vocal works entries")
    # Normalize field names: two code paths (table vs text parser) produce different names
    _normalize_vocal_works(data['vocal_works'])

    # Extract text
    print(f"  [PARSE] Extracting German text and English translation...")
    texts = _extract_chorale_text(soup)
    data['german_text'] = texts['german']
    data['english_text'] = texts['english']

    # Count verses
    german_verses = len(data['german_text'])
    english_verses = len(data['english_text'])
    print(f"  [PARSE] German verses: {german_verses}, English verses: {english_verses}")

    # Which verses were set by Bach?
    bach_verses = [
        v for v, t in data['german_text'].items()
        if t.get('bold')
    ]
    data['bach_verses'] = bach_verses

    # Extract translator info
    trans_info = _extract_translator_info(soup)
    data['translator'] = trans_info['translator']
    data['source_links'] = trans_info['source_links']

    return data


def save_chorale_data(chorale_id, data):
    """Save scraped chorale data to data/ChoraleNNN.json.

    Preserves existing chinese_text if the new data doesn't contain translations.
    """
    filepath = os.path.join(cfg.DATA_DIR, f'{chorale_id}.json')

    # Preserve existing translations
    if not data.get('chinese_text') and os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if existing.get('chinese_text'):
                data['chinese_text'] = existing['chinese_text']
        except (json.JSONDecodeError, OSError):
            pass

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [SAVE] Saved to {filepath}")
    return filepath


def load_chorale_data(chorale_id):
    """Load previously scraped chorale data."""
    filepath = os.path.join(cfg.DATA_DIR, f'{chorale_id}.json')
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
