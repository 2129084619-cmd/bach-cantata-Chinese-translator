# -*- coding: utf-8 -*-
"""Chorale pipeline configuration — URL templates, paths, constants."""

import os
import sys

# ── Paths ──
CHORALE_ROOT = os.path.abspath(os.path.dirname(__file__))
WORKSPACE_ROOT = os.path.abspath(os.path.join(CHORALE_ROOT, '..'))
DATA_DIR = os.path.join(CHORALE_ROOT, 'data')
# Newest chorale translation docx files (single source of truth for reuse/query).
DOCX_DIR = os.path.join(CHORALE_ROOT, 'latest translation')
# Older translations are archived here, one subfolder per ChoraleNNN.
ARCHIVE_DIR = os.path.join(CHORALE_ROOT, 'translation archive')
INDEX_FILE = os.path.join(CHORALE_ROOT, 'chorale_index.json')

# Ensure subdirectories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOCX_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

# Add parent workspace to sys.path for term DB access
_ws = WORKSPACE_ROOT
if _ws not in sys.path:
    sys.path.insert(0, _ws)

# ── URL Templates ──
URL_CHORALE_INDEX = (
    'https://www.bach-cantatas.com/Texts/IndexTexts-Chorales-Title.htm'
)
URL_CHORALE_DETAIL = (
    'https://www.bach-cantatas.com/Texts/{chorale_id}-Eng3.htm'
)
URL_CHORALE_BASE = 'https://www.bach-cantatas.com'

# ── HTTP settings (mirror main pipeline) ──
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,de;q=0.8,zh-CN;q=0.7,zh;q=0.6',
}
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
FETCH_DELAY = 1.5  # seconds between requests (be polite)

# ── Alphabet sections ──
ALPHABET = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
