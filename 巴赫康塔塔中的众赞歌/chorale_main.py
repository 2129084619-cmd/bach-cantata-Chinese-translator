# -*- coding: utf-8 -*-
"""Chorale management CLI — entry point for all chorale operations.

Usage:
    # Query chorales for a BWV number
    python -m 巴赫康塔塔中的众赞歌.chorale_main <BWV>

    # Regenerate: re-scrape + re-generate docx
    python -m 巴赫康塔塔中的众赞歌.chorale_main <BWV> --regenerate

    # AI translation mode: open docx for assistant translation
    python -m 巴赫康塔塔中的众赞歌.chorale_main <BWV> --edit

    # Open in local Office/WPS editor
    python -m 巴赫康塔塔中的众赞歌.chorale_main <BWV> --open-editor

    # Build/continue building index
    python -m 巴赫康塔塔中的众赞歌.chorale_main --rebuild-index

    # Full from-scratch rebuild
    python -m 巴赫康塔塔中的众赞歌.chorale_main --rebuild-index --from-scratch

    # Operate on specific chorale by ID
    python -m 巴赫康塔塔中的众赞歌.chorale_main --chorale-id Chorale012 --regenerate

    # Show index status
    python -m 巴赫康塔塔中的众赞歌.chorale_main --status
"""

import os
import sys
import subprocess

from . import chorale_config as cfg
from . import chorale_index as idx
from . import chorale_scraper as scraper
from . import chorale_translator as translator
from . import chorale_api as api


def cmd_status():
    """Show current index status."""
    idx.print_index_status()


def cmd_rebuild_index(from_scratch=False):
    """Build or continue building the chorale index."""
    print("=" * 60)
    print("  Chorale Index Builder")
    print("=" * 60)
    result = idx.build_index_progressive(from_scratch=from_scratch)
    print(f"\n  Result: {result['new_entries']} new entries, "
          f"{result['letters_processed']} letters processed, "
          f"{result['total_entries']} total entries")
    return result


def _get_chorale_ids_for_bwv(bwv_number):
    """Look up chorale IDs from the index for a given BWV number."""
    entries = idx.lookup_by_bwv(bwv_number)
    if not entries:
        print(f"  [INFO] No chorales found for BWV {bwv_number}")
        return []

    print(f"  [INFO] Found {len(entries)} chorale(s) for BWV {bwv_number}:")
    for entry in entries:
        info = f"    - {entry.get('title', '?')}"
        if entry.get('chorale_id'):
            info += f" ({entry['chorale_id']})"
        if entry.get('detail_available'):
            info += f" [detail available]"
        print(info)

    return entries


def cmd_regenerate(bwv_number=None, chorale_id=None):
    """Scrape detail pages and generate docx files.

    Can operate by BWV number (all matching chorales) or by single chorale ID.
    """
    if chorale_id:
        chorales = [{'id': chorale_id, 'chorale_id': chorale_id, 'title': chorale_id}]
    elif bwv_number:
        chorales = _get_chorale_ids_for_bwv(bwv_number)
        if not chorales:
            return
    else:
        print("Usage: --regenerate <BWV> or --chorale-id <ID> --regenerate")
        return

    for chorale_entry in chorales:
        cid = chorale_entry.get('chorale_id') or chorale_entry.get('id')
        if not cid:
            print(f"  [SKIP] No chorale ID for: {chorale_entry.get('title', '?')}")
            continue

        print(f"\n{'─' * 50}")
        print(f"  Processing: {chorale_entry.get('title', cid)} ({cid})")
        print(f"{'─' * 50}")

        # Check if already scraped
        existing = scraper.load_chorale_data(cid)
        if existing:
            overwrite = input(
                f"  Data for {cid} already exists. Overwrite? [y/N]: "
            ).strip().lower()
            if overwrite not in ('y', 'yes'):
                # Generate docx from existing data
                print(f"  [SKIP] Using existing data")
                translator.generate_chorale_docx(existing, chorale_id=cid)
                continue

        # Scrape detail page
        try:
            chorale_data = scraper.scrape_chorale_detail(cid)
        except Exception as e:
            print(f"  [ERROR] Failed to scrape {cid}: {e}")
            continue

        # Save data
        scraper.save_chorale_data(cid, chorale_data)

        # Generate docx
        docx_path = translator.generate_chorale_docx(chorale_data, chorale_id=cid)
        print(f"  [DONE] Upcoming: {docx_path}")


def cmd_edit(bwv_number=None, chorale_id=None):
    """AI translation mode with detection and overwrite.

    Uses run_translate_pipeline() which:
      1. [检测] Looks up BWV → chorale(s)
      2. [判断] FULL (overwrite) / TEMPLATE (continue) / NEW (fresh)
      3. [覆盖/新建] Regenerates docx with fresh placeholders
      4. [准备] Presents translation context
      5. Returns context for AI assistant to complete translation + write-back
    """
    if chorale_id:
        # Direct translation of a single chorale
        chorale_data = scraper.load_chorale_data(chorale_id)
        if not chorale_data:
            print(f"  [ERROR] No data found for {chorale_id}. Run --regenerate first.")
            return

        # Re-generate docx with fresh placeholders
        from . import chorale_translator
        docx_path = chorale_translator.generate_chorale_docx(
            chorale_data, chorale_id=chorale_id
        )
        # Build and present context
        ctx = api._build_translation_context(
            chorale_data, chorale_id, docx_path,
            api._count_placeholders(docx_path)
        )
        api._present_translation_context([ctx], chorale_id)
        return {
            'contexts': [ctx],
            'total_placeholders': ctx['placeholder_count'],
        }

    if bwv_number:
        # Full pipeline: detect → overwrite/new → present context
        return api.run_translate_pipeline(bwv_number)

    print("Usage: --edit <BWV> or --chorale-id <ID> --edit")


def cmd_open_editor(bwv_number=None, chorale_id=None):
    """Open the chorale .docx file in the local Office/WPS editor."""
    if chorale_id:
        docx_path = os.path.join(
            cfg.DOCX_DIR, f'{chorale_id}_德中对照译文.docx'
        )
        if os.path.exists(docx_path):
            _open_docx(docx_path)
        else:
            print(f"  [ERROR] Docx not found: {docx_path}")
        return

    if bwv_number:
        chorales = _get_chorale_ids_for_bwv(bwv_number)
        if not chorales:
            return
        for chorale_entry in chorales:
            cid = chorale_entry.get('chorale_id') or chorale_entry.get('id')
            if not cid:
                continue
            docx_path = os.path.join(
                cfg.DOCX_DIR, f'{cid}_德中对照译文.docx'
            )
            if os.path.exists(docx_path):
                _open_docx(docx_path)
            else:
                print(f"  [WARN] Docx not found for {cid}. Run --regenerate first.")
    else:
        print("Usage: --open-editor <BWV> or --chorale-id <ID> --open-editor")


def _open_docx(path):
    """Open a .docx file with the system default application."""
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])
    print(f"  [OPEN] {path}")


def cmd_query(bwv_number):
    """Query chorales for a BWV and open existing docx files."""
    result = api.query_chorale_docx(bwv_number)
    if not result['docs']:
        print(f"  [INFO] No chorales found for BWV {bwv_number}")

    for doc in result['docs']:
        if doc['exists']:
            print(f"  [OK] {doc['chorale_id']}: {doc['title'][:50]}")
        else:
            print(f"  [MISSING] {doc['chorale_id']}: need --regenerate")
    return result


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main(argv=None):
    """Main entry point. Parse arguments and dispatch commands."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Bach Cantata Chorale Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m 巴赫康塔塔中的众赞歌.chorale_main 4
  python -m 巴赫康塔塔中的众赞歌.chorale_main 4 --regenerate
  python -m 巴赫康塔塔中的众赞歌.chorale_main 4 --edit
  python -m 巴赫康塔塔中的众赞歌.chorale_main 4 --open-editor
  python -m 巴赫康塔塔中的众赞歌.chorale_main --rebuild-index
  python -m 巴赫康塔塔中的众赞歌.chorale_main --status
        """
    )
    parser.add_argument('bwv', nargs='?', help='BWV number to query/process')
    parser.add_argument('--regenerate', action='store_true',
                        help='Re-scrape and re-generate docx')
    parser.add_argument('--edit', action='store_true',
                        help='AI translation mode: fill Chinese translations')
    parser.add_argument('--open-editor', action='store_true',
                        help='Open docx in local Office/WPS editor')
    parser.add_argument('--rebuild-index', action='store_true',
                        help='Build/continue building chorale index')
    parser.add_argument('--from-scratch', action='store_true',
                        help='Used with --rebuild-index to start fresh')
    parser.add_argument('--status', action='store_true',
                        help='Show index status')
    parser.add_argument('--chorale-id', type=str,
                        help='Operate on specific chorale by ID (e.g., Chorale012)')

    args = parser.parse_args(argv)

    # Show status
    if args.status:
        cmd_status()
        return 0

    # Rebuild index
    if args.rebuild_index:
        cmd_rebuild_index(from_scratch=args.from_scratch)
        return 0

    # Chorale-specific operations
    if args.chorale_id:
        if args.regenerate:
            cmd_regenerate(chorale_id=args.chorale_id)
        elif args.edit:
            cmd_edit(chorale_id=args.chorale_id)
        elif args.open_editor:
            cmd_open_editor(chorale_id=args.chorale_id)
        else:
            print(f"  [INFO] Specify --regenerate, --edit, or --open-editor")
        return 0

    # BWV-based operations
    if not args.bwv:
        parser.print_help()
        return 1

    if args.regenerate:
        cmd_regenerate(bwv_number=args.bwv)
    elif args.edit:
        cmd_edit(bwv_number=args.bwv)
    elif args.open_editor:
        cmd_open_editor(bwv_number=args.bwv)
    else:
        # Default: query mode
        cmd_query(args.bwv)

    return 0


if __name__ == '__main__':
    sys.exit(main())
