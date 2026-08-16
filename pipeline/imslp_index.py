# -*- coding: utf-8 -*-
"""IMSLP Bach vocal works index builder.

Scrapes imslp.org's Bach works table (wikitable) to build a
BWV→vocal-work index for pre-translation validation.
"""

import json
import os
import re
import requests
from bs4 import BeautifulSoup

INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "bach_vocal_index.json")
IMSLP_URL = "https://imslp.org/wiki/List_of_works_by_Johann_Sebastian_Bach"


def _fetch_table():
    """Fetch and parse the main works table from IMSLP."""
    try:
        resp = requests.get(IMSLP_URL, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }, timeout=30)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except requests.RequestException as e:
        print(f"  [ERROR] IMSLP fetch failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    tables = soup.find_all('table')

    # Find the main works table (wikitable with BWV header)
    for t in tables:
        header = t.find('tr')
        if not header:
            continue
        hcells = [c.get_text(' ', strip=True) for c in header.find_all(['td', 'th'])]
        if 'BWV' in hcells and 'Genre' in hcells:
            return t

    return None


def build_index(force=False):
    """Scrape IMSLP and build vocal works index.

    Returns dict with 'bwv_set' (set of vocal BWV strings) and 'entries'.
    """
    if not force and os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['bwv_set'] = set(data.get('bwv_list', []))
        return data

    print(f"  [IMSLP] Fetching {IMSLP_URL} ...")
    table = _fetch_table()
    if table is None:
        print("  [ERROR] Could not find works table on IMSLP")
        return None

    rows = table.find_all('tr')[1:]  # skip header
    vocal_entries = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) == 0:
            continue
        # Section headers span single cell
        if len(cells) == 1:
            continue

        cts = [c.get_text(' ', strip=True) for c in cells]
        if len(cts) < 7:
            continue

        genre = cts[6]
        if 'Vocal' not in genre:
            continue

        bwv_raw = cts[0].strip().lstrip('0').strip() or '0'
        # Handle Anh / appendix entries
        if not bwv_raw or bwv_raw in ('—', ''):
            continue

        # Handle sub-numbers like "208/1"
        bwv_main = bwv_raw.split('/')[0].split()[0]

        # Normalize Anh entries
        if 'Anh' in bwv_raw:
            bwv_main = bwv_raw

        vocal_entries.append({
            'bwv': bwv_raw,
            'bwv_main': bwv_main,
            'bc': cts[1] if len(cts) > 1 else '',
            'title': cts[2] if len(cts) > 2 else '',
            'forces': cts[3] if len(cts) > 3 else '',
            'key': cts[4] if len(cts) > 4 else '',
            'date': cts[5] if len(cts) > 5 else '',
            'genre': genre,
            'notes': cts[7] if len(cts) > 7 else '',
        })

    # Build unique BWV list
    bwv_list = sorted(set(e['bwv_main'] for e in vocal_entries if e['bwv_main']), key=int)

    result = {
        'bwv_list': bwv_list,
        'entries': vocal_entries,
        'total_vocal': len(vocal_entries),
        'unique_bwv': len(bwv_list),
        'source': IMSLP_URL,
    }

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        serializable = dict(result)
        serializable['bwv_set'] = list(bwv_list)  # for JSON
        json.dump(serializable, f, ensure_ascii=False, indent=2)

    result['bwv_set'] = set(bwv_list)
    print(f"  [IMSLP] Index built: {len(vocal_entries)} vocal entries, {len(bwv_list)} unique BWV numbers")
    return result


def is_vocal(bwv):
    """Check if a BWV number corresponds to a known vocal work.

    Args:
        bwv: int or str

    Returns:
        bool
    """
    if not os.path.exists(INDEX_PATH):
        build_index()

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    bwv_str = str(bwv)
    bwv_set = set(data.get('bwv_list', []) or [])
    return bwv_str in bwv_set


def assert_vocal(bwv):
    """Raise ValueError if BWV is not a known vocal work."""
    if not is_vocal(bwv):
        raise ValueError(
            f"BWV {bwv} 不是巴赫声乐作品。"
            f"根据 IMSLP 索引，该编号对应非声乐作品或不存在。"
            f"如确认该作品为声乐作品，请运行 python -m pipeline.imslp_index --force 重建索引。"
        )


def load_index():
    """Load the vocal index from disk."""
    if not os.path.exists(INDEX_PATH):
        return build_index()
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['bwv_set'] = set(data.get('bwv_list', []))
    return data


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='IMSLP Bach Vocal Index Builder')
    ap.add_argument('--force', action='store_true', help='Force rebuild index')
    ap.add_argument('--check', type=str, help='Check if BWV is vocal')
    ap.add_argument('--list', type=int, nargs='?', const=30, help='List first N vocal BWV numbers')
    args = ap.parse_args()

    if args.check:
        try:
            assert_vocal(args.check)
            print(f"BWV {args.check}: ✓ Vocal work")
        except ValueError as e:
            print(f"BWV {args.check}: ✗ {e}")

    elif args.list:
        idx = load_index()
        for bwv in sorted(idx['bwv_set'], key=int)[:args.list]:
            print(bwv)

    else:
        build_index(force=args.force)
