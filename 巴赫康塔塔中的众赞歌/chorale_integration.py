# -*- coding: utf-8 -*-
"""Chorale pipeline integration — hooks into the main cantata pipeline.

After the main pipeline's step4 (translation context + docx generation) completes,
this module is called to:
1. Look up the BWV number in the chorale index
2. For each matching chorale: scrape details and generate docx (if not exists)
3. Update the shared terminology database with chorale-specific terms
"""

import os
import sys

from . import chorale_config as cfg
from . import chorale_index as idx


def process_bwv(bwv_number, force=False):
    """Process chorales associated with a BWV number after cantata translation.

    Called automatically after the main pipeline's Step 4 completes.

    Args:
        bwv_number: int or str
        force: if True, regenerate even if docx already exists

    Returns:
        dict: {'chorales_found': int, 'docx_generated': int, 'errors': list}
    """
    bwv_str = str(bwv_number)

    # Ensure index exists
    if not os.path.exists(cfg.INDEX_FILE):
        print(f"\n{'=' * 50}")
        print(f"  [CHORALE INTEGRATION] No chorale index found — building index first...")
        print(f"{'=' * 50}")
        from . import chorale_index
        chorale_index.build_index_progressive()

    # Look up chorales for this BWV
    entries = idx.lookup_by_bwv(bwv_str)

    result = {
        'bwv': bwv_str,
        'chorales_found': len(entries),
        'docx_generated': 0,
        'errors': [],
    }

    if not entries:
        print(f"\n  [CHORALE INTEGRATION] No chorales found for BWV {bwv_str}")
        return result

    print(f"\n{'=' * 50}")
    print(f"  [CHORALE INTEGRATION] Found {len(entries)} chorale(s) for BWV {bwv_str}")
    print(f"{'=' * 50}")

    for entry in entries:
        cid = entry.get('chorale_id')
        if not cid:
            result['errors'].append(
                f"No chorale_id for: {entry.get('title', '?')}"
            )
            continue

        docx_path = os.path.join(
            cfg.DOCX_DIR, f'{cid}_德中对照译文.docx'
        )

        if not force and os.path.exists(docx_path):
            print(f"  [SKIP] Docx already exists: {docx_path}")
            continue

        # Scrape and generate
        print(f"  [PROCESS] {entry.get('title', cid)} ({cid})")

        try:
            from . import chorale_scraper
            chorale_data = chorale_scraper.scrape_chorale_detail(cid)
            chorale_scraper.save_chorale_data(cid, chorale_data)

            from . import chorale_translator
            docx_path = chorale_translator.generate_chorale_docx(
                chorale_data, chorale_id=cid
            )
            result['docx_generated'] += 1

        except Exception as e:
            err_msg = f"Failed to process {cid}: {e}"
            print(f"  [ERROR] {err_msg}")
            result['errors'].append(err_msg)

    # Summary
    print(f"\n  [CHORALE INTEGRATION] Done: "
          f"{result['chorales_found']} found, "
          f"{result['docx_generated']} new docx generated, "
          f"{len(result['errors'])} errors")

    if result['errors']:
        for err in result['errors']:
            print(f"    - {err}")

    return result
