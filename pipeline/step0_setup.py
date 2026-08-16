# -*- coding: utf-8 -*-
"""Step 0: Create BWV_{N}/ folder with data/ subdirectory and __init__.py."""

import os

from . import config
from .logger import get_logger

log = get_logger()


def run(bwv_number):
    """Create the output directory structure for a given BWV number.

    The folder is created under "raw data & all translations" (NOT the
    workspace root), per the 2026-08-16 output-location rule.

    Args:
        bwv_number: int or str, the BWV number (e.g. 1, '1')

    Returns:
        str: Absolute path to the created BWV folder.
    """
    bwv = str(bwv_number)
    folder_name = f'BWV_{bwv}'
    folder_path = os.path.join(config.TRANSLATIONS_DIR, folder_name)
    data_path = os.path.join(folder_path, 'data')

    # Also pre-create the mirror folder under "latest translations".
    latest_path = os.path.join(config.LATEST_TRANSLATIONS_DIR, folder_name)

    os.makedirs(data_path, exist_ok=True)
    os.makedirs(latest_path, exist_ok=True)
    log.info(f"[Step 0] Created folder structure: {folder_path}")
    log.info(f"[Step 0]   data/  subdirectory ready")
    log.info(f"[Step 0]   latest translations mirror: {latest_path}")

    return folder_path
