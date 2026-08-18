#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bach Cantata Pipeline — Main Orchestrator.

Usage:
    python main.py <BWV_number> [--skip-step=N] [--force]

Example:
    python main.py 1
    python main.py 1 --force        # Force re-fetch, ignore cache

The pipeline:
    Step 0  — Create BWV_N folder under "raw data & all translations"
    Step 1  — Fetch German (UAlberta) + footnotes (bachcantatatexts.org)
    Step 2  — Fetch background metadata from bach-cantatas.com + bachipedia.org
    Step 2.5 — Generate glossary, Luther 1545 verification, update term DB
    Step 3.5 — Chorale → Bible scripture fuzzy search
    Step 3  — Build Chinese Bible passage manifest
    Step 4  — Prepare translation context, generate combined Docx (info table + translation)
    Step 4.5 — Chorale reuse detection

Output:
    raw data & all translations/BWV_N/
        data/                    — All intermediate JSON data
        BWVN_德中对照译文.docx    — Combined Docx: basic info table + German-Chinese parallel
        BWVN_中文译文.txt         — Plain Chinese text export (generated in Step E3 by AI)
    latest translations/BWV_N/    — Mirror of the newest docx + txt (Step E)
"""

import argparse
import json
import os
import sys
import importlib.util

from . import step0_setup, step1_fetch_texts, step2_fetch_bg
from . import step25_glossary, step3_fetch_bible, step4_translate
from . import config
from .logger import setup_logger, get_logger


log = get_logger()


def _roles_match(german_role, english_role):
    """Check if a German role name matches an English role name.

    Handles common pairs: Furcht↔Fear, Hoffnung↔Hope,
    Christus↔Christ, Seele↔Soul, Jesus↔Jesus, etc.
    """
    if not german_role or not english_role:
        return False
    gl = german_role.lower()
    el = english_role.lower()
    # Direct match
    if gl == el:
        return True
    # Known pairs
    pairs = [
        ('furcht', 'fear'), ('hoffnung', 'hope'), ('christus', 'christ'),
        ('seele', 'soul'), ('braut', 'bride'), ('bräutigam', 'bridegroom'),
        ('heiland', 'savior'), ('evangelist', 'evangelist'),
        ('pilatus', 'pilate'), ('petrus', 'peter'), ('judas', 'judas'),
        ('phoebus', 'phoebus'), ('pan', 'pan'), ('momus', 'momus'),
    ]
    for de, en in pairs:
        if gl == de and el == en:
            return True
    return False


def _supplement_role_labels_from_bc(movements, bc_role_map, metadata=None):
    """Cross-validate: use bach-cantatas.com Persons: map to add role labels
    where UAlberta missed them.

    Uses metadata.json movement_info (from bach-cantatas.com) to resolve
    voice assignments within each movement.

    **Critical**: bc_role_map has English names (Fear, Hope). We cross-reference
    with existing German role labels (Furcht, Hoffnung) from UAlberta to produce
    German role names in the output.
    """
    if not bc_role_map:
        return 0

    VOICE_MARKERS = {'Alt', 'Tenor', 'Bass', 'Soprano', 'Sopran'}
    VOICE_ABBREV = {'A': 'Alto', 'T': 'Tenor', 'B': 'Bass', 'S': 'Soprano'}

    # Build voice→German_role from existing UAlberta labels in other movements
    # e.g., in Mvt 2: ['Furcht'(role), 'O schwerer Gang...', 'Hoffnung'(role), ...]
    # → Alt→Furcht, Tenor→Hoffnung
    voice_to_german = {}
    for mv in movements:
        german = mv.get('german', [])
        # Collect sequences of [role_label, text_line, ...]
        for i in range(len(german)):
            if isinstance(german[i], dict) and german[i].get('line_is_role_label'):
                german_role = german[i]['text']
                # Try to map this German role to a voice in bc_role_map
                # Compare: German "Furcht" ↔ English "Fear", "Hoffnung" ↔ "Hope"
                for en_voice, en_role in bc_role_map.items():
                    if _roles_match(german_role, en_role):
                        # Normalize voice name
                        norm_voice = en_voice if en_voice in VOICE_MARKERS else en_voice.title()
                        if norm_voice == 'Alto':
                            norm_voice = 'Alt'
                        if norm_voice not in voice_to_german:
                            voice_to_german[norm_voice] = german_role

    # If cross-reference found German roles, use them; otherwise fall back to English
    effective_role_map = {}
    for en_voice, en_role in bc_role_map.items():
        norm_voice = 'Alt' if en_voice == 'Alto' else en_voice
        effective_role_map[norm_voice] = voice_to_german.get(norm_voice, en_role)
    # Also add normalized alias
    if 'Alt' in effective_role_map and 'Alto' not in effective_role_map:
        effective_role_map['Alto'] = effective_role_map['Alt']

    supplemented = 0

    # Build movement info lookup from metadata
    mv_info = {}
    if metadata:
        for mi in metadata.get('movement_info', []):
            mv_info[mi.get('number', 0)] = mi

    for mv in movements:
        mvt_num = mv.get('number', 0)
        german = mv.get('german', [])

        # Already has role labels? Skip
        if any(isinstance(l, dict) and l.get('line_is_role_label') for l in german):
            continue

        # Case 1: german lines contain voice markers → replace with roles
        new_german = []
        voice_found = False
        for line in german:
            text = line.get('text', '') if isinstance(line, dict) else str(line)
            if text in VOICE_MARKERS and text in effective_role_map:
                new_german.append({'text': effective_role_map[text], 'line_is_role_label': True})
                voice_found = True
            elif text == 'Sopran' and 'Soprano' in effective_role_map:
                new_german.append({'text': effective_role_map['Soprano'], 'line_is_role_label': True})
                voice_found = True
            else:
                new_german.append(line)

        if voice_found:
            mv['german'] = new_german
            supplemented += 1
            continue

        # Case 2: No voice markers, use metadata's movement type for voice info
        mi = mv_info.get(mvt_num)
        if not mi:
            continue

        mi_type = mi.get('type', '')
        mi_voices = mi.get('voices', '')

        # Parse voice assignments from movement type/voices
        # "Chorale [Alto] and Aria [Tenor]" → Alto=chorale, Tenor=aria
        # "Recitative [Alto, Tenor]" → both voices
        # "Aria (Duet) [Alto, Tenor]" → both voices
        new_german = _annotate_mixed_movement_v2(
            german, mi_type, mi_voices, effective_role_map, VOICE_ABBREV
        )
        if new_german != german:
            mv['german'] = new_german
            supplemented += 1

    return supplemented


def _annotate_mixed_movement_v2(german_lines, mi_type, mi_voices, bc_role_map, voice_abbrev):
    """Add role labels using bach-cantatas.com's movement type info.

    Parses movement type like "Chorale [Alto] and Aria [Tenor]" to determine
    which role sings which part. Then uses has_chorale info to split lines:
    chorale lines (those used in the cantata's chorale verse) vs aria lines.
    """
    import re, os, json
    if not german_lines:
        return german_lines

    # Parse movement type for voice assignments
    chorale_m = re.search(r'Chorale?\s*(?:\[([^\]]+)\])?', mi_type, re.IGNORECASE)
    if not chorale_m:
        # May also be "Aria T e Choral A" style (UAlberta preserves this in voices)
        alt_m = re.search(r'e\s+Chorale?\s*\[?([ABTSabts])\]?', mi_voices or '', re.IGNORECASE)
        if alt_m:
            chorale_voice_raw = alt_m.group(1)
        else:
            return german_lines
    else:
        chorale_voice_raw = (chorale_m.group(1) or mi_voices or '').strip()

    # Also extract aria voice
    aria_m = re.search(r'Aria\s*(?:\([^)]+\))?\s*(?:\[([^\]]+)\])?', mi_type, re.IGNORECASE)
    aria_voice_raw = ''
    if aria_m:
        aria_voice_raw = (aria_m.group(1) or '').strip()
    # Fallback: if mi_type has no aria voice, check mi_voices
    if not aria_voice_raw and mi_voices:
        voices_parsed = re.findall(r'([ABTSabts])', mi_voices)
        if len(voices_parsed) == 2 and chorale_m:
            # "Alto, Tenor" → first is Alto, second is Tenor; which one is aria?
            aria_voice_raw = voices_parsed[1]  # assume Tenor=aria in chorale+aria mix

    chorale_voice = voice_abbrev.get(chorale_voice_raw.upper()[:1], chorale_voice_raw)
    aria_voice = voice_abbrev.get(aria_voice_raw.upper()[:1], aria_voice_raw) if aria_voice_raw else None

    chorale_role = bc_role_map.get(chorale_voice) if chorale_voice else None
    aria_role = bc_role_map.get(aria_voice) if aria_voice else None

    if not chorale_role:
        return german_lines

    # Split: chorale text first (bold in UAlberta), aria text last (plain)
    # Use chorale verse info from step45 if available, otherwise heuristics
    chorale_end = _detect_chorale_boundary(german_lines)

    new_german = []
    for i, line in enumerate(german_lines):
        role = chorale_role if i < chorale_end else (aria_role if aria_role else chorale_role)
        if role:
            new_german.append({'text': role, 'line_is_role_label': True})
        new_german.append(line)

    return new_german


def _detect_chorale_boundary(german_lines):
    """Detect where chorale text ends and aria/solo text begins.

    Uses multiple heuristics:
    1. Last line without German special chars (äöüß) is the aria line
    2. If all lines have special chars, last line is aria (common in mixed movements)
    3. Fallback: last line is aria
    """
    # Try to read chorale_reuse_manifest.json for exact verse line count
    if len(german_lines) <= 1:
        return len(german_lines)

    # Heuristic: scan backwards for a line without äöüß
    for i in range(len(german_lines) - 1, max(0, len(german_lines) - 4), -1):
        line = german_lines[i]
        text = line.get('text', '') if isinstance(line, dict) else str(line)
        if not any(c in text for c in 'äöüß'):
            return i

    # Fallback: last line is aria
    return len(german_lines) - 1


def run_pipeline(bwv_number, skip_steps=None, force=False):
    """Run the full pipeline for a given BWV number.

    Args:
        bwv_number: int or str, the BWV catalog number
        skip_steps: set of step names to skip (e.g., {'step1', 'step3'})
        force: if True, ignore cached data and re-fetch

    Returns:
        dict with results from each step.
    """
    bwv = str(bwv_number)
    skip_steps = skip_steps or set()
    results = {}

    log.info(f"{'='*60}")
    log.info(f"Bach Cantata Pipeline — BWV {bwv}")
    log.info(f"{'='*60}")

    # ── Pre-check: IMSLP vocal works validation ──
    try:
        from pipeline.imslp_index import assert_vocal
        assert_vocal(bwv)
    except ImportError:
        log.warning("[Pipeline] IMSLP index not available, skipping vocal check")
    except ValueError as e:
        log.error(f"[Pipeline] BWV {bwv} is not a vocal work: {e}")
        return {'bwv': bwv, 'error': str(e), 'step': 'pre_check'}

    # ── Step 0: Setup ──
    folder_path = step0_setup.run(bwv_number)
    results['folder'] = folder_path
    log.info(f"[Pipeline] Output directory: {folder_path}")

    # ── Step 1: Fetch German text (UAlberta primary) + footnotes (bachcantatatexts.org) ──
    texts_data = None
    texts_json = os.path.join(folder_path, 'data', 'texts.json')
    footnotes_json = os.path.join(folder_path, 'data', 'footnotes.json')

    if 'step1' not in skip_steps:
        if force or not (os.path.exists(texts_json) and os.path.exists(footnotes_json)):
            log.info("[Pipeline] --- Step 1: UAlberta (German) + bachcantatatexts.org (notes) ---")
            try:
                from pipeline.step1_uofa import run as uofa_run, save as step1_save
                from pipeline.step1_kantate import is_available as kantate_available, run as kantate_run

                # Primary: UAlberta (complete BWV coverage)
                raw_data = uofa_run(bwv)

                # If UAlberta returned no movements, try kantate.info as fallback
                if not raw_data.get('movements') and kantate_available(bwv):
                    log.info(f"[Pipeline] Step 1: UAlberta empty, falling back to kantate.info")
                    raw_data = kantate_run(bwv) or raw_data

                step1_save(raw_data, folder_path)
                texts_data = raw_data
                results['step1'] = 'ok'
                has_footnotes = len(texts_data.get('footnotes', {})) > 0
                log.info(f"[Pipeline] Step 1: {len(texts_data.get('movements',[]))} mvts, "
                         f"{'with' if has_footnotes else 'no'} footnotes")
            except Exception as e:
                log.error(f"[Pipeline] Step 1 failed: {e}")
                results['step1'] = f'error: {e}'
                if os.path.exists(texts_json):
                    log.warning("[Pipeline] Falling back to cached texts.json")
        else:
            log.info("[Pipeline] Step 1: Using cached data")
            with open(texts_json, 'r', encoding='utf-8') as f:
                texts_data = json.load(f)
            results['step1'] = 'cached'
    else:
        log.info("[Pipeline] Step 1: Skipped")
        if os.path.exists(texts_json):
            with open(texts_json, 'r', encoding='utf-8') as f:
                texts_data = json.load(f)

    if texts_data is None:
        if 'step1' in skip_steps:
            # Degraded mode: step1 intentionally skipped, provide minimal data
            log.warning("[Pipeline] Step 1 skipped, using minimal texts data (degraded pipeline)")
            texts_data = {
                'title': metadata.get('title', f'BWV {bwv}'),
                'movements': [],
                'footnotes': {},
                'bible_references': [],
                'luther_citations': [],
                'work_name': metadata.get('title', f'BWV {bwv}'),
            }
        else:
            log.error("[Pipeline] Cannot proceed without texts data. Aborting.")
            return results

    # ── Step 1.5: Dialogue cantata role label detection ──
    if texts_data and texts_data.get('movements'):
        try:
            total_roles = 0
            for mv in texts_data['movements']:
                german = mv.get('german', [])
                # Check format: dict-based (from step1_uofa) or plain-string (from step1_fetch_texts)
                has_dict_roles = any(isinstance(l, dict) and l.get('line_is_role_label') for l in german)
                
                if has_dict_roles:
                    # step1_uofa format: extract role arrays from dict entries
                    is_role_list = []
                    role_name_list = []
                    for line in german:
                        if isinstance(line, dict) and line.get('line_is_role_label'):
                            is_role_list.append(True)
                            role_name_list.append(line.get('text', ''))
                        else:
                            is_role_list.append(False)
                            role_name_list.append(None)
                    mv['line_is_role_label'] = is_role_list
                    mv['line_role_name'] = role_name_list
                    total_roles += sum(is_role_list)
                else:
                    # Plain-string format: use _parse_dialogue_movements detection
                    # Normalize to string list if mixed dict/string
                    str_german = []
                    for l in german:
                        if isinstance(l, dict):
                            str_german.append(l.get('text', ''))
                        else:
                            str_german.append(l)
                    # Run detection on string copy
                    temp_mv = {**mv, 'german': str_german}
                    step1_fetch_texts._parse_dialogue_movements([temp_mv])
                    mv['line_is_role_label'] = temp_mv['line_is_role_label']
                    mv['line_role_name'] = temp_mv['line_role_name']
                    total_roles += sum(temp_mv['line_is_role_label'])

            is_dialogue = total_roles > 0
            texts_data['is_dialogue_cantata'] = is_dialogue
            if is_dialogue:
                log.info(f"[Pipeline] Step 1.5: Dialogue cantata detected — "
                         f"{total_roles} role labels across {len(texts_data['movements'])} movements")
            # Re-save texts.json with role label fields
            with open(texts_json, 'w', encoding='utf-8') as f:
                json.dump(texts_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[Pipeline] Step 1.5 (dialogue detection) non-fatal: {e}")

    # ── Step 2: Fetch background metadata ──
    metadata = None
    metadata_json = os.path.join(folder_path, 'data', 'metadata.json')

    if 'step2' not in skip_steps:
        if force or not os.path.exists(metadata_json):
            log.info("[Pipeline] --- Step 2: bach-cantatas.com ---")
            try:
                metadata = step2_fetch_bg.run(bwv)
                step2_fetch_bg.save(metadata, folder_path)
                results['step2'] = 'ok'
            except Exception as e:
                log.error(f"[Pipeline] Step 2 failed: {e}")
                results['step2'] = f'error: {e}'
                metadata = {}
        else:
            log.info("[Pipeline] Step 2: Using cached data")
            with open(metadata_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            results['step2'] = 'cached'
    else:
        log.info("[Pipeline] Step 2: Skipped")
        if os.path.exists(metadata_json):
            with open(metadata_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = {}

    # ── Step 1.7: Cross-validate movement types (UAlberta ↔ bach-cantatas.com) ──
    # When step1 can't recognise a movement header's type keyword, it stashes the
    # movement as type='unknown' (is_uncertain_type=True). Here we fill the type
    # back in from bach-cantatas.com movement_info so every movement ends up with
    # a standard keyword (Chorus/Aria/Recitative/Chorale/Sinfonia/...).
    if texts_data and texts_data.get('movements') and metadata:
        try:
            mv_info = {mi.get('number', 0): mi
                       for mi in metadata.get('movement_info', [])}
            fixed = 0
            for mv in texts_data['movements']:
                if mv.get('type') != 'unknown' and not mv.get('is_uncertain_type'):
                    continue
                mi = mv_info.get(mv.get('number', 0))
                if not mi or not mi.get('type'):
                    continue
                mv['type'] = mi['type']
                mv.pop('is_uncertain_type', None)
                mv.pop('mv_type_raw', None)
                fixed += 1
            if fixed:
                with open(texts_json, 'w', encoding='utf-8') as f:
                    json.dump(texts_data, f, ensure_ascii=False, indent=2)
                log.info(f"[Pipeline] Step 1.7: Cross-validated {fixed} movement "
                         f"type(s) from bach-cantatas.com")
        except Exception as e:
            log.warning(f"[Pipeline] Step 1.7 (movement type cross-validation) "
                        f"non-fatal: {e}")

    # ── Step 1.6: Cross-validate role assignments (UAlberta ↔ bach-cantatas.com) ──
    if texts_data and texts_data.get('movements') and metadata:
        try:
            bc_role_map = metadata.get('persons_role_map', {})
            if bc_role_map:
                # Re-read texts.json (may have been updated by step1.5)
                with open(texts_json, 'r', encoding='utf-8') as f:
                    td = json.load(f)

                supplemented = _supplement_role_labels_from_bc(
                    td['movements'], bc_role_map, metadata
                )
                if supplemented:
                    td['is_dialogue_cantata'] = True
                    with open(texts_json, 'w', encoding='utf-8') as f:
                        json.dump(td, f, ensure_ascii=False, indent=2)
                    texts_data = td
                    log.info(f"[Pipeline] Step 1.6: Supplemented role labels from "
                             f"bach-cantatas.com ({supplemented} movements)")
        except Exception as e:
            log.warning(f"[Pipeline] Step 1.6 (role cross-validation) non-fatal: {e}")

    # ── Step 2.5: Glossary, Luther verification, term DB update ──
    if 'step25' not in skip_steps:
        log.info("[Pipeline] --- Step 2.5: Glossary + Luther + Term DB ---")
        try:
            movements = texts_data.get('movements', [])
            footnotes = texts_data.get('footnotes', {})
            translator = texts_data.get('translator', '')
            general_note = texts_data.get('general_note', '')

            # Merge footnotes from separate file if needed
            if not footnotes and os.path.exists(footnotes_json):
                with open(footnotes_json, 'r', encoding='utf-8') as f:
                    footnotes = json.load(f)

            s25 = step25_glossary.run(
                bwv, movements, footnotes, translator,
                general_note, metadata, folder_path
            )
            results['step25'] = 'ok'
            results['glossary'] = s25.get('glossary')
            results['luther_verify'] = s25.get('luther_verify')
            results['term_db_updated'] = s25.get('term_db_updated', {})
        except Exception as e:
            log.error(f"[Pipeline] Step 2.5 failed: {e}")
            results['step25'] = f'error: {e}'

    # ── Step 3.5: Chorale → Bible scripture fuzzy search ──
    chorale_bible_refs = []
    try:
        from . import step35_chorale_bible
        chorale_bible_refs = step35_chorale_bible.run(bwv, metadata=metadata, folder_path=folder_path)
        results['step35'] = f'{len(chorale_bible_refs)} refs'
        if chorale_bible_refs:
            log.info(f"[Pipeline] Step 3.5: chorale scripture search → "
                     f"{len(chorale_bible_refs)} refs")
    except Exception as e:
        log.warning(f"[Pipeline] Step 3.5 (chorale scripture) non-fatal: {e}")
        results['step35'] = f'error: {e}'

    # ── Step 3: Chinese Bible passage manifest ──
    bible_manifest = {}
    bible_manifest_json = os.path.join(folder_path, 'data', 'bible_cn_manifest.json')

    if 'step3' not in skip_steps:
        if force or not os.path.exists(bible_manifest_json):
            log.info("[Pipeline] --- Step 3: Bible passage manifest ---")
            try:
                # Bible references now come from background sources
                # (bach-cantatas.com Epistle/Gospel + bachipedia.org) and the
                # chorale scripture fuzzy search — NOT from bachcantatatexts.org.
                bible_refs = step3_fetch_bible.collect_bible_references(
                    metadata, chorale_bible_refs
                )
                bible_manifest = step3_fetch_bible.run(bible_refs)
                step3_fetch_bible.save(bible_manifest, folder_path)
                log.info(f"[Pipeline] Step 3: {len(bible_manifest)} passages in manifest, "
                         f"ready for AI-assisted retrieval")
                results['step3'] = 'ok'
            except Exception as e:
                log.error(f"[Pipeline] Step 3 failed: {e}")
                results['step3'] = f'error: {e}'
        else:
            log.info("[Pipeline] Step 3: Using cached manifest")
            with open(bible_manifest_json, 'r', encoding='utf-8') as f:
                bible_manifest = json.load(f)
            results['step3'] = 'cached'
    else:
        log.info("[Pipeline] Step 3: Skipped")
        if os.path.exists(bible_manifest_json):
            with open(bible_manifest_json, 'r', encoding='utf-8') as f:
                bible_manifest = json.load(f)

    # ── Step 4: Translation context + Combined Docx ──
    if 'step4' not in skip_steps:
        log.info("[Pipeline] --- Step 4: Translation context + Combined Docx ---")
        try:
            movements = texts_data.get('movements', [])
            footnotes = texts_data.get('footnotes', {})
            glossary = results.get('glossary', [])
            luther_verify = results.get('luther_verify', {})

            # Load footnote data if not in texts_data
            if not footnotes and os.path.exists(footnotes_json):
                with open(footnotes_json, 'r', encoding='utf-8') as f:
                    footnotes = json.load(f)
            if not glossary:
                glossary_json = os.path.join(folder_path, 'data', 'glossary.json')
                if os.path.exists(glossary_json):
                    with open(glossary_json, 'r', encoding='utf-8') as f:
                        glossary = json.load(f)

            s4 = step4_translate.run(
                bwv, movements, footnotes, glossary,
                bible_manifest, luther_verify, metadata, folder_path,
                title=texts_data.get('title', '')
            )
            results['step4'] = 'ok'
            results['docx'] = s4.get('docx2_path')
            results['translation_context'] = s4.get('context')

            # ── Step 4.5: Chorale Reuse ──
            if 'step45' not in skip_steps:
                log.info("[Pipeline] --- Step 4.5: Chorale Reuse ---")
                try:
                    from . import step45_chorale_reuse
                    s45 = step45_chorale_reuse.run(bwv, folder_path)
                    results['step45'] = 'ok'
                    results['chorale_reuse'] = s45
                    s_summary = s45.get('summary', {})
                    log.info(
                        f"[Pipeline] Step 4.5: {s_summary.get('total', 0)} chorale movements, "
                        f"{s_summary.get('filled', 0)} filled, "
                        f"{s_summary.get('needs_translation', 0)} need translation"
                    )
                except Exception as e:
                    log.error(f"[Pipeline] Step 4.5 failed: {e}")
                    results['step45'] = f'error: {e}'

            # ── Chorale Integration: auto-process chorales for this BWV ──
            try:
                chorale_pkg = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    '巴赫康塔塔中的众赞歌'
                )
                if chorale_pkg not in sys.path:
                    sys.path.insert(0, os.path.dirname(chorale_pkg))
                spec = importlib.util.spec_from_file_location(
                    'chorale_integration',
                    os.path.join(chorale_pkg, 'chorale_integration.py')
                )
                cim = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cim)
                chorale_result = cim.process_bwv(bwv)
                results['chorales'] = chorale_result
                log.info(f"[Pipeline] Chorale integration: "
                         f"{chorale_result.get('docs_generated', 0)} new docs")
            except Exception as e:
                log.warning(f"[Pipeline] Chorale integration skipped: {e}")
                results['chorales'] = f'skipped: {e}'
        except Exception as e:
            log.error(f"[Pipeline] Step 4 failed: {e}")
            results['step4'] = f'error: {e}'

    # ── Summary ──
    log.info(f"{'='*60}")
    log.info(f"Pipeline complete for BWV {bwv}")
    log.info(f"  Results: {json.dumps({k: v for k, v in results.items() if k != 'glossary' and k != 'luther_verify' and k != 'translation_context'}, indent=2)}")
    log.info(f"{'='*60}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Bach Cantata Text Pipeline — Automated lyrics, translation & annotation'
    )
    parser.add_argument('bwv', type=int, help='BWV catalog number (e.g., 1)')
    parser.add_argument('--skip-step', action='append', default=[],
                        help='Skip specific step (e.g., --skip-step step3)')
    parser.add_argument('--force', action='store_true', default=True,
                        help='Force re-fetch, ignoring cached data (default: on). Use --no-force to use cache.')
    parser.add_argument('--no-force', action='store_false', dest='force',
                        help='Use cached data if available')

    args = parser.parse_args()

    setup_logger()
    skip_set = set(args.skip_step)

    results = run_pipeline(args.bwv, skip_steps=skip_set, force=args.force)

    # Print human-readable summary
    print("\n" + "=" * 60)
    print(f"  BWV {args.bwv} Pipeline Summary")
    print("=" * 60)
    for step, status in sorted(results.items()):
        if step in ('glossary', 'luther_verify', 'translation_context'):
            continue
        if step == 'folder':
            print(f"  Output:   {status}")
        elif step.startswith('step'):
            print(f"  {step}:     {status}")
        elif step == 'docx':
            print(f"  Docx:     {status}")
        elif step == 'term_db_updated':
            print(f"  Term DB:  {status.get('total', '?')} terms ({status.get('new', 0)} new)")
    print("=" * 60)

    return 0 if all(
        v == 'ok' or v == 'cached' or v == 'no_refs'
        for k, v in results.items()
        if k.startswith('step')
    ) else 1


if __name__ == '__main__':
    sys.exit(main())
