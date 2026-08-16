# -*- coding: utf-8 -*-
"""Step 1: Fetch German text from kantate.info (NBA-based), fallback to UAlberta.

Primary source:
  http://www.kantate.info/cantata_text_e.htm → PDF index (near-complete coverage)
  
Fallback within kantate.info:
  HTML index column (partial, ~18 BWVs activated)

The PDF column provides BWV → (grouped PDF file, page number) for ~193 cantatas.
PDFs are text-searchable (not scanned images), generated from the NBA critical edition.
PDF text layout mirrors the NBA: movement headers numbered, clear line breaks, umlauts intact.

UAlberta is the final fallback if kantate.info has no source for a BWV.

URL pattern for PDF:  cantata_text{N}-{M}.pdf#page={P}
URL pattern for HTML: cantata_text{N}-{M}.htm#{BWV}
"""

import re
import os
import json
import io
import requests
from bs4 import BeautifulSoup

from . import config

KANTATE_BASE = "http://www.kantate.info"
KANTATE_INDEX = f"{KANTATE_BASE}/cantata_text_e.htm"


# ═══════════════════════════════════════════════════════════════
# Index: BWV → source mapping (PDF preferred, HTML fallback)
# ═══════════════════════════════════════════════════════════════

def _build_bwv_index():
    """Fetch the index page and build BWV → source mapping.

    Scans both columns. PDF is preferred (full coverage, ~191 BWVs),
    HTML as backup (partial, ~18 BWVs).
    """
    try:
        resp = requests.get(KANTATE_INDEX, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'iso-8859-1'
    except requests.RequestException:
        return {}

    raw = resp.text
    index = {}

    # ── PDF column: all links active ──
    for m in re.finditer(
        r'<a\s+href="(cantata_text[\d\-]+\.pdf)#page=(\d+)"[^>]*>\s*(\d+[a-z]?)\s*</a>',
        raw, re.IGNORECASE
    ):
        pdf_file = m.group(1)
        page_num = int(m.group(2))
        bwv = m.group(3).strip()
        bwv_num = re.sub(r'[a-z]$', '', bwv)
        if bwv_num not in index:
            index[bwv_num] = {
                'type': 'pdf',
                'file': pdf_file,
                'page': page_num,
            }

    # ── HTML column: only non-commented links ──
    raw_no_comments = re.sub(r'<!--.*?-->', '', raw, flags=re.DOTALL)
    soup_active = BeautifulSoup(raw_no_comments, 'html.parser')
    for a in soup_active.find_all('a', href=True):
        href = a['href'].strip()
        m = re.match(r'cantata_text[\d\-]+\.htm#(\d+[a-z]?)\s*$', href)
        if m:
            bwv_anchor = m.group(1)
            bwv_num = re.sub(r'[a-z]$', '', bwv_anchor)
            if bwv_num not in index:
                index[bwv_num] = {
                    'type': 'html',
                    'file': href.split('#')[0],
                    'anchor': bwv_anchor,
                }

    return index


# ═══════════════════════════════════════════════════════════════
# PDF text extraction
# ═══════════════════════════════════════════════════════════════

def _fetch_pdf_page(pdf_file, page_num):
    """Download PDF and extract text using two-column layout detection.

    kantate.info PDFs use a two-column layout: left column (x<midpoint)
    and right column. A single cantata may span both columns (e.g., Mvts 1-3
    in left, Mvts 4-6 in right). We extract both columns and merge them.
    """
    url = f"{KANTATE_BASE}/{pdf_file}"
    try:
        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        }, timeout=30)
        resp.raise_for_status()
        if len(resp.content) < 100:
            print(f"  [KANTATE-PDF] Empty response from {url}")
            return None
    except requests.RequestException as e:
        print(f"  [KANTATE-PDF] Failed to fetch {url}: {e}")
        return None

    try:
        import pdfplumber
        from collections import defaultdict
        pdf = pdfplumber.open(io.BytesIO(resp.content))
        if page_num < 1 or page_num > len(pdf.pages):
            pdf.close()
            return None
        page = pdf.pages[page_num - 1]

        words = page.extract_words()
        if not words:
            pdf.close()
            return None

        # Detect column split: find the largest X-gap in the page
        xs = sorted((w['x0'] + w['x1']) / 2 for w in words)
        best_gap, best_mid = 0, page.width / 2
        for i in range(1, len(xs)):
            gap = xs[i] - xs[i - 1]
            if gap > best_gap:
                best_gap = gap
                best_mid = (xs[i - 1] + xs[i]) / 2

        # Use detected split (fallback to page midpoint if gap < 30px)
        if best_gap < 30:
            best_mid = page.width / 2

        # Split words into left/right columns
        left_words = defaultdict(list)
        right_words = defaultdict(list)
        for w in words:
            if (w['x0'] + w['x1']) / 2 < best_mid:
                left_words[int(round(w['top']))].append(w)
            else:
                right_words[int(round(w['top']))].append(w)

        # Reconstruct text per column
        def col_to_lines(col_words):
            lines = []
            for y in sorted(col_words.keys()):
                ws = sorted(col_words[y], key=lambda w: w['x0'])
                text = ' '.join(w['text'] for w in ws).strip()
                if text and not re.match(r'.*NBA I/', text) and 'Sämtliche' not in text:
                    lines.append(text)
            return lines

        left_text = col_to_lines(left_words)
        right_text = col_to_lines(right_words)

        pdf.close()

        # Merge columns: interleave by Y-position
        # For BWV header detection, concatenate left then right works
        # since left column usually starts text first
        merged_text = '\n'.join(left_text + right_text)
        return merged_text

    except ImportError:
        print("  [KANTATE-PDF] pdfplumber not installed")
        return None
    except Exception as e:
        print(f"  [KANTATE-PDF] Error: {e}")
        return None


def _parse_pdf_text(text, bwv_str):
    """Parse column-separated PDF text into movements.

    The two-column PDF layout interleaves BWV movements:
    left column has Mvts 1-N/2, right column has Mvts N/2+1-M.
    We scan for movement headers (N. Type or bare N.) across columns.
    """
    lines = text.split('\n')
    all_movements = []
    seen_numbers = set()
    title = f'BWV {bwv_str}'

    # Detect cantata title: lines starting with BWV N
    bwv_pattern = re.compile(r'^BWV\s+' + re.escape(bwv_str) + r'\b')

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        # Skip page headers
        if re.match(r'^\d+/\d+/\d{4}$', line) or re.match(r'.*NBA I/', line):
            i += 1; continue

        # Detect movement header: N. or N. Type
        mvt_match = re.match(r'(\d+)\.[\s]*(.*)', line)
        if mvt_match:
            mvt_num = int(mvt_match.group(1))
            mvt_type_raw = mvt_match.group(2).strip() if mvt_match.group(2) else ''
            if mvt_num in seen_numbers:
                i += 1; continue

            # Try next line for type if current is empty
            if not mvt_type_raw and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.match(r'\d+\.', next_line) and not re.match(r'BWV\s', next_line):
                    mvt_type_raw = next_line
                    i += 1

            mvt_type = _normalize_mvt_type(mvt_type_raw)
            seen_numbers.add(mvt_num)

            # Collect lines until next header or BWV marker
            mvt_lines = []
            j = i + 1
            while j < len(lines):
                nl = lines[j].strip()
                if not nl:
                    j += 1; continue
                if re.match(r'^\d+/\d+/\d{4}$', nl) or re.match(r'.*NBA I/', nl):
                    j += 1; continue
                if re.match(r'BWV\s+\d+', nl):
                    break
                if re.match(r'\d+\.', nl):
                    # Check if this is a new movement header
                    pm = re.match(r'(\d+)\.\s*(.*)', nl)
                    if pm:
                        pn = int(pm.group(1))
                        pt = pm.group(2).strip() if pm.group(2) else ''
                        if pn not in seen_numbers and _is_mvt_header(pt, nl):
                            break
                mvt_lines.append(nl)
                j += 1

            if mvt_lines:
                all_movements.append({
                    'number': mvt_num,
                    'type': mvt_type,
                    'german': mvt_lines,
                    'english': [],
                    'annotation_ids': [],
                    'line_footnote_ids': [],
                })
            i = j - 1
        i += 1

    return {
        'title': title,
        'movements': all_movements,
        'footnotes': {},
        'bible_references': [],
        'luther_citations': [],
        'source_german': 'kantate.info (NBA PDF)',
    }


def _is_mvt_header(type_text, full_line):
    """Heuristic: is this likely a new movement header?"""
    if not type_text:
        return True
    if len(full_line) < 80:
        tl = type_text.lower()
        if any(kw in tl for kw in ['chor', 'recit', 'aria', 'ouvertur',
                                    'duetto', 'arioso', 'sinfonia', 'choral']):
            return True
    return False


def _is_mvt_header(type_text, full_line):
    """Heuristic: is this line likely a new movement header?

    A movement header is: short (<60 chars), contains type keywords,
    or is a bare number followed by possible type on next line.
    """
    if not type_text:
        return True  # bare "N." is a header
    if len(full_line) < 60:
        type_lower = type_text.lower()
        type_keywords = ['chor', 'recit', 'aria', 'ouvertur', 'duetto',
                        'arioso', 'sinfonia', 'choral']
        if any(kw in type_lower for kw in type_keywords):
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# HTML text parsing
# ═══════════════════════════════════════════════════════════════

def _fetch_page(page_url):
    """Fetch a kantate.info HTML text page."""
    url = f"{KANTATE_BASE}/{page_url}"
    try:
        resp = requests.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'iso-8859-1'
        return resp.text
    except requests.RequestException as e:
        print(f"  [KANTATE-HTML] Failed to fetch {url}: {e}")
        return None


def _parse_html_text(html, bwv_anchor):
    """Parse single BWV text from grouped HTML page."""
    soup = BeautifulSoup(html, 'html.parser')

    anchor = soup.find('hr', id=bwv_anchor)
    if not anchor:
        return None

    title = ''
    main_p = None

    for sibling in anchor.next_siblings:
        if isinstance(sibling, str):
            continue
        if sibling.name == 'hr':
            break
        if sibling.name == 'h2' and not title:
            title = sibling.get_text(strip=True)
            title = re.sub(r'\s*BWV\s+\d+.*$', '', title).strip()
        if sibling.name == 'p' and sibling.find('strong'):
            main_p = sibling
            break

    if not main_p:
        return None

    inner = main_p.decode_contents()
    inner = re.sub(r'<div[^>]*floatr[^>]*>.*?</div>', '', inner, flags=re.DOTALL)

    headers = list(re.finditer(r'<strong>\s*(\d+)[\.\)]\s*(.+?)\s*</strong>', inner, re.DOTALL))
    if not headers:
        return None

    movements = []
    for hi, hm in enumerate(headers):
        mvt_num = int(hm.group(1))
        mvt_type_raw = hm.group(2).strip()
        mvt_type = _normalize_mvt_type(mvt_type_raw)

        start = hm.end()
        end = headers[hi + 1].start() if hi + 1 < len(headers) else len(inner)
        block = inner[start:end]
        lines = _extract_html_lines(block)

        movements.append({
            'number': mvt_num,
            'type': mvt_type,
            'german': lines,
            'english': [],
            'annotation_ids': [],
            'line_footnote_ids': [],
        })

    return {
        'title': title or f'BWV {bwv_anchor}',
        'movements': movements,
        'footnotes': {},
        'bible_references': [],
        'luther_citations': [],
        'source_german': 'kantate.info (NBA HTML)',
    }


def _extract_html_lines(html_block):
    """Extract plain German text lines from an HTML block."""
    lines = []
    soup = BeautifulSoup(html_block, 'html.parser')
    for child in soup.children:
        if isinstance(child, str):
            continue
        if hasattr(child, 'name'):
            if child.name == 'b':
                for line in child.get_text('\n').split('\n'):
                    line = line.strip()
                    if line:
                        lines.append(line)
            elif child.name != 'br':
                text = child.get_text('\n').strip()
                if text:
                    lines.append(text)

    if not lines:
        parts = re.split(r'<br\s*/?\s*>', html_block, flags=re.IGNORECASE)
        for part in parts:
            clean = BeautifulSoup(part.strip(), 'html.parser').get_text().strip()
            if clean and not re.match(r'^\d+[\.\)]', clean):
                lines.append(clean)

    return [l for l in lines if l]


def _normalize_mvt_type(raw_type):
    """Normalize movement type string."""
    r = raw_type.lower()
    if 'choral' in r:
        return 'chorale'
    if 'recitativo' in r or 'recitative' in r:
        return 'Recitative'
    if 'aria' in r:
        return 'Aria'
    if 'ouvertur' in r or 'coro' in r or 'chorus' in r:
        return 'Chorus'
    if 'duetto' in r or 'duet' in r:
        return 'Duet'
    if 'arioso' in r:
        return 'Arioso'
    if 'sinfonia' in r:
        return 'Sinfonia'
    return raw_type


# ═══════════════════════════════════════════════════════════════
# Cached index + public API
# ═══════════════════════════════════════════════════════════════

_kantate_index = None


def _get_index():
    global _kantate_index
    if _kantate_index is None:
        _kantate_index = _build_bwv_index()
    return _kantate_index


def is_available(bwv):
    """Check if kantate.info has this BWV (PDF or HTML)."""
    return str(bwv) in _get_index()


def available_bwvs():
    """Return set of BWV numbers available on kantate.info."""
    return set(_get_index().keys())


def source_type(bwv):
    """Return 'pdf', 'html', or None."""
    entry = _get_index().get(str(bwv))
    return entry['type'] if entry else None


def run(bwv):
    """Fetch and parse German text from kantate.info.

    Tries PDF first (two-column extraction), falls back to HTML.
    """
    bwv_str = str(bwv)
    entry = _get_index().get(bwv_str)
    if not entry:
        return None

    if entry['type'] == 'pdf':
        print(f"  [KANTATE] PDF {entry['file']}#page={entry['page']}")
        text = _fetch_pdf_page(entry['file'], entry['page'])
        if text:
            result = _parse_pdf_text(text, bwv_str)
            if result and result.get('movements'):
                print(f"  [KANTATE] PDF parsed {len(result['movements'])} movements")
                return result
        print(f"  [KANTATE] PDF failed, trying HTML fallback...")

    if entry['type'] == 'html':
        print(f"  [KANTATE] HTML {entry['file']}#{entry['anchor']}")
        html = _fetch_page(entry['file'])
        if html:
            result = _parse_html_text(html, entry['anchor'])
            if result and result.get('movements'):
                print(f"  [KANTATE] HTML parsed {len(result['movements'])} movements")
                return result

    return None
