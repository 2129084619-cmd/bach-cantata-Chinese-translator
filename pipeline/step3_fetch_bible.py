# -*- coding: utf-8 -*-
"""Step 3: Generate Chinese Bible passage manifest for AI-assisted retrieval.

Since both BiblePortal and BibleGateway serve Chinese Bibles via JavaScript
(not accessible via plain HTTP requests), this step generates a structured
manifest of needed passages. The AI assistant then uses WebFetch to retrieve
each passage, which can render JavaScript pages.

The manifest includes:
  - Structured list of Bible references with Chinese book names
  - Direct URLs for both BiblePortal and BibleGateway CUVS
  - Target format for the retrieved data
"""

import json
import os

from . import config
from .logger import get_logger

log = get_logger()


def collect_bible_references(metadata, chorale_bible_refs=None):
    """Collect Bible references from background metadata readings + chorale sources.

    This is the canonical entry point for the cantata→Bible mapping (per policy
    of 2026-08-16): references come from the basic-info sources (bach-cantatas.com
    Epistle/Gospel, bachipedia.org prose) and from the chorale scripture fuzzy
    search (step35), NOT from bachcantatatexts.org footnotes.

    Args:
        metadata: dict from step2 (contains 'readings' → epistle/gospel/bachipedia)
        chorale_bible_refs: optional list of reference dicts from step35.

    Returns:
        list of reference dicts: {book, chapter, verse, source, footnote_id}
    """
    refs = []
    seen = set()
    readings = (metadata or {}).get('readings', {}) or {}

    def _normalize_verse(verse):
        """归一化节号中的破折号：en-dash（–）/em-dash（—）→ 连字符（-）。

        bachipedia.org 用 en-dash（如 "Luke 14:16–24"）而 bach-cantatas.com
        用连字符（"Luke 14:16-24"），若不归一化会生成重复条目。
        """
        return (verse or '').replace('\u2013', '-').replace('\u2014', '-')

    def _add(book, chapter, verse, source, footnote_id=None):
        if not book:
            return
        verse = _normalize_verse(verse)
        key = (book, int(chapter), verse)
        if key in seen:
            return
        seen.add(key)
        refs.append({
            'book': book,
            'chapter': int(chapter),
            'verse': verse,
            'source': source,
            'footnote_id': footnote_id,
        })

    ep = readings.get('epistle', {}) or {}
    if ep.get('book'):
        _add(ep['book'], ep.get('chapter'), ep.get('verses', ''), 'epistle')
    gos = readings.get('gospel', {}) or {}
    if gos.get('book'):
        _add(gos['book'], gos.get('chapter'), gos.get('verses', ''), 'gospel')
    for r in readings.get('bachipedia', []) or []:
        _add(r.get('book'), r.get('chapter'), r.get('verse', ''), 'bachipedia')
    for r in (chorale_bible_refs or []):
        _add(r.get('book'), r.get('chapter'), r.get('verse', ''),
             r.get('source', 'chorale'))

    return refs


def run(bible_references):
    """Generate a manifest of Chinese Bible passages to fetch.

    Args:
        bible_references: list of dicts, each with book/chapter/verse/footnote_id
                          (and optionally 'source')

    Returns:
        dict: {reference_key: passage_info}
    """
    log.info(f"[Step 3] Generating Bible manifest for {len(bible_references)} references...")

    manifest = {}
    seen = set()

    for ref in bible_references:
        book = ref['book']
        chapter = ref['chapter']
        verses = ref.get('verse', '') or ''
        key = f'{book} {chapter}:{verses}' if verses else f'{book} {chapter}'

        if key in seen:
            if ref.get('footnote_id') is not None and ref['footnote_id'] not in manifest[key].get('footnote_ids', []):
                manifest[key]['footnote_ids'].append(ref['footnote_id'])
            continue

        seen.add(key)
        book_cn = config.BOOK_CHINESE_MAP.get(book, book)

        # Build URLs for both sources (chapter-only reference has no verse suffix)
        search_term = f'{book}+{chapter}' if not verses else f'{book}+{chapter}%3A{verses}'
        bg_url = 'https://www.biblegateway.com/passage/' f'?search={search_term}&version=CUVS'
        bp_url = (
            'https://bibleportal.com/zh-Hans/verse-topic'
            f'?v={book}%20{chapter}%3A{verses}&version=CUNPSS'
        )

        manifest[key] = {
            'reference': key,
            'book_en': book,
            'book_cn': book_cn,
            'chapter': chapter,
            'verses': verses,
            'footnote_ids': [ref.get('footnote_id')] if ref.get('footnote_id') is not None else [],
            'source': ref.get('source', ''),
            'urls': {
                'biblegateway_cuvs': bg_url,
                'bibleportal_cunpss': bp_url,
            },
            'verses_text': None,  # To be filled by AI assistant
            'retrieved': False,
        }

    log.info(f"[Step 3] Manifest: {len(manifest)} unique passages ready for retrieval")

    return manifest


def save(manifest, folder_path):
    """Save Bible manifest as JSON."""
    data_dir = os.path.join(folder_path, 'data')
    with open(os.path.join(data_dir, 'bible_cn_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log.info(f"[Step 3] Saved bible_cn_manifest.json ({len(manifest)} passages)")


def fill_verse(manifest, reference_key, verse_text):
    """Fill in a verse text for a specific reference.

    Args:
        manifest: The manifest dict
        reference_key: e.g., 'John 1:14'
        verse_text: str, the Chinese verse text

    Returns:
        Updated manifest dict (in-place update as well)
    """
    if reference_key in manifest:
        manifest[reference_key]['verses_text'] = verse_text
        manifest[reference_key]['retrieved'] = True
        return manifest
    return manifest
