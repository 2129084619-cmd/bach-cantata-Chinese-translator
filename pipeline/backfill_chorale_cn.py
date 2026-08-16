# -*- coding: utf-8 -*-
"""Backfill: import existing Chinese translations from Chorale docx files into JSON.

Parses ChoraleNNN_德中对照译文.docx to extract per-verse Chinese translations
and writes them to ChoraleNNN.json under the 'chinese_text' field.

Usage:
    python -m pipeline.backfill_chorale_cn --chorale-id Chorale026
    python -m pipeline.backfill_chorale_cn --chorale-ids Chorale012,Chorale015
    python -m pipeline.backfill_chorale_cn --all
    python -m pipeline.backfill_chorale_cn --all --dry-run
"""

import json
import os
import re
import sys
from datetime import datetime


def _get_paths():
    """Resolve paths for the chorale subsystem."""
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chorale_dir = os.path.join(workspace, '巴赫康塔塔中的众赞歌')
    return workspace, chorale_dir


def _has_chinese(text):
    """Check if a string contains Chinese characters."""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _parse_docx_translations(docx_path, json_path):
    """Extract Chinese translations from a chorale docx file.

    The docx structure is:
        [heading: 德语原文]
        [para: "1."]  ← verse heading
          [German line 1]
          [Chinese line 1]  ← we extract this
          [German line 2]
          [Chinese line 2]
          ...
        [empty para]
        [para: "2."]
          ...

    Returns:
        dict: {verse_num (str): {'lines': [chinese_lines], ...}}
        or empty dict if no translations found
    """
    from docx import Document

    # Load JSON to get verse structure
    if not os.path.exists(json_path):
        print(f"  [WARN] JSON not found: {json_path}")
        return {}

    with open(json_path, 'r', encoding='utf-8') as f:
        chorale_data = json.load(f)

    german_text = chorale_data.get('german_text', {})
    if not german_text:
        print(f"  [WARN] No german_text in JSON")
        return {}

    # Pre-count lines per verse for validation (keys: str verse numbers)
    verse_line_counts = {
        str(vnum): len(vdata.get('lines', []))
        for vnum, vdata in german_text.items()
    }

    doc = Document(docx_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs]

    # Find the "德语原文" heading
    german_section_start = None
    for i, pt in enumerate(paragraphs):
        if '德语原文' in pt or 'German Text' in pt:
            german_section_start = i
            break

    if german_section_start is None:
        print(f"  [WARN] No German Text section found in docx")
        return {}

    # Iterate through paragraphs to find verse headings and collect Chinese lines
    chinese_text = {}
    current_verse = None
    current_lines = []

    for i in range(german_section_start + 1, len(paragraphs)):
        pt = paragraphs[i]

        if not pt:
            # Empty line — finalize verse if we have data
            if current_verse is not None and current_lines:
                expected = verse_line_counts.get(str(current_verse), 0)
                if len(current_lines) == expected:
                    chinese_text[str(current_verse)] = {
                        'lines': current_lines,
                        'translator': 'AI (manual review)',
                        'translated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                    }
                current_verse = None
                current_lines = []
            continue

        # Check for verse heading (e.g., "1.", "2.") — but NOT "10." in German text
        verse_match = re.match(r'^(\d+)\.$', pt)
        if verse_match and not _has_chinese(pt):
            vnum = int(verse_match.group(1))
            if vnum <= 20:  # reasonable upper bound for verse numbers
                # Save previous verse
                if current_verse is not None and current_lines:
                    expected = verse_line_counts.get(str(current_verse), 0)
                    if len(current_lines) == expected:
                        chinese_text[str(current_verse)] = {
                            'lines': current_lines,
                            'translator': 'AI (manual review)',
                            'translated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                        }
                current_verse = vnum
                current_lines = []
                continue

        # Skip placeholder lines
        if pt == '【待翻译】':
            continue

        # Collect Chinese lines within the current verse
        if current_verse is not None:
            if _has_chinese(pt):
                current_lines.append(pt)
            # Non-Chinese lines (German) are skipped — we're only collecting CN lines

    # Handle last verse at end of document
    if current_verse is not None and current_lines:
        expected = verse_line_counts.get(str(current_verse), 0)
        if len(current_lines) == expected:
            chinese_text[str(current_verse)] = {
                'lines': current_lines,
                'translator': 'AI (manual review)',
                'translated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            }

    return chinese_text


def run(chorale_ids=None, all_chorales=False, dry_run=False):
    """Main entry point for backfill.

    Args:
        chorale_ids: list of chorale IDs (e.g., ['Chorale026', 'Chorale012'])
        all_chorales: if True, process all available ChoraleNNN docx files
        dry_run: if True, only report without writing
    """
    workspace, chorale_dir = _get_paths()
    docx_dir = os.path.join(chorale_dir, 'latest translation')
    data_dir = os.path.join(chorale_dir, 'data')

    if all_chorales:
        # Find all docx files
        pattern = re.compile(r'(Chorale\d+)_德中对照译文\.docx')
        chorale_ids = []
        if os.path.exists(docx_dir):
            for fname in os.listdir(docx_dir):
                m = pattern.match(fname)
                if m:
                    chorale_ids.append(m.group(1))

    if not chorale_ids:
        print("No chorales specified. Use --chorale-id, --chorale-ids, or --all")
        return

    results = {'processed': 0, 'backfilled': 0, 'skipped': 0, 'errors': []}

    for cid in chorale_ids:
        docx_path = os.path.join(docx_dir, f'{cid}_德中对照译文.docx')
        json_path = os.path.join(data_dir, f'{cid}.json')

        if not os.path.exists(docx_path):
            print(f"  [SKIP] {cid}: docx not found")
            results['skipped'] += 1
            continue

        if not os.path.exists(json_path):
            print(f"  [SKIP] {cid}: JSON not found")
            results['skipped'] += 1
            continue

        print(f"  [PARSE] {cid}: extracting translations from docx...")
        try:
            chinese_text = _parse_docx_translations(docx_path, json_path)
        except Exception as e:
            print(f"  [ERROR] {cid}: {e}")
            results['errors'].append(f'{cid}: {e}')
            continue

        if not chinese_text:
            print(f"  [SKIP] {cid}: no translations found (docx may still have placeholders)")
            results['skipped'] += 1
            continue

        results['processed'] += 1

        if dry_run:
            for vnum, vdata in chinese_text.items():
                lines_preview = ' | '.join(vdata['lines'][:2])
                print(f"    Verse {vnum}: {len(vdata['lines'])} lines → {lines_preview}...")
            print(f"  [DRY RUN] Would write {len(chinese_text)} verses to {json_path}")
        else:
            # Write to JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                chorale_data = json.load(f)
            chorale_data['chinese_text'] = chinese_text
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(chorale_data, f, ensure_ascii=False, indent=2)
            print(f"  [SAVED] {len(chinese_text)} verses → {json_path}")
            results['backfilled'] += 1

    print(f"\n  Done: {results['processed']} processed, "
          f"{results['backfilled']} backfilled, {results['skipped']} skipped")
    if results['errors']:
        print(f"  Errors: {len(results['errors'])}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Backfill chorale Chinese translations from docx to JSON')
    parser.add_argument('--chorale-id', type=str, help='Single chorale ID (e.g., Chorale026)')
    parser.add_argument('--chorale-ids', type=str, help='Comma-separated chorale IDs')
    parser.add_argument('--all', action='store_true', help='Process all available chorales')
    parser.add_argument('--dry-run', action='store_true', help='Report without writing')
    args = parser.parse_args()

    ids = None
    if args.chorale_id:
        ids = [args.chorale_id]
    elif args.chorale_ids:
        ids = [cid.strip() for cid in args.chorale_ids.split(',')]

    run(chorale_ids=ids, all_chorales=args.all, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
