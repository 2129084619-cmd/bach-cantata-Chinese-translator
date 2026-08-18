# -*- coding: utf-8 -*-
"""Step 4.5 — Chorale Reuse Detection

Detects chorale-type movements in a cantata, matches them to verses
in the chorale subsystem, and checks whether Chinese translations already
exist (Case 1: reuse / Case 2: needs translation).

Generates a `chorale_reuse_manifest.json` for the AI translation step.
Does NOT modify the cantata docx directly — that is done by the AI step.
"""

import json
import os
import re
import sys
from datetime import datetime


def _get_chorale_subsystem_path():
    """Resolve absolute path to the chorale subsystem directory."""
    pipe_dir = os.path.dirname(os.path.abspath(__file__))
    workspace = os.path.dirname(pipe_dir)
    return os.path.join(workspace, '巴赫康塔塔中的众赞歌')


def _load_chorale_module():
    """Load necessary chorale subsystem functions via importlib."""
    chorale_dir = _get_chorale_subsystem_path()
    if chorale_dir not in sys.path:
        sys.path.insert(0, chorale_dir)
    # The chorale package is a subdirectory of workspace; ensure workspace is in path
    workspace = os.path.dirname(chorale_dir)
    if workspace not in sys.path:
        sys.path.insert(0, workspace)
    from importlib import import_module
    return import_module


def _load_index():
    """Load chorale_index.json. Returns dict or {} on failure."""
    chorale_dir = _get_chorale_subsystem_path()
    index_path = os.path.join(chorale_dir, 'chorale_index.json')
    if not os.path.exists(index_path):
        return {}
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _find_chorale_movements(texts_path):
    """Scan texts.json, return all movements containing chorale text.

    Detects four patterns:
      1. type == 'chorale'            (pure chorale, e.g. BWV 60/5)
      2. type contains 'chor'/'Choral' (mixed, e.g. "Aria T e Choral A")
      3. type contains 'Versus'        (chorale-cantata stanza, e.g. BWV 4 "Versus 2 S A")
      4. has_chorale == True           (flag set by step1_uofa)
    """
    if not os.path.exists(texts_path):
        return []
    with open(texts_path, 'r', encoding='utf-8') as f:
        texts_data = json.load(f)

    result = []
    for mv in texts_data.get('movements', []):
        mv_type = mv.get('type', '')
        has_chorale_flag = mv.get('has_chorale', False)
        # Detect chorale: type == 'chorale', or type contains 'Choral'/'Chorale'
        # (but NOT 'Chorus' — that's a regular chorus), or a 'Versus' stanza.
        mv_lower = mv_type.lower()
        is_chorale = (
            mv_lower == 'chorale'
            or 'choral' in mv_lower  # matches "Choral" / "Chorale", NOT "Chorus"
            or 'versus' in mv_lower  # chorale-cantata stanza, e.g. BWV 4 "Versus 2 S A"
            or has_chorale_flag
        )
        if is_chorale:
            german_lines = []
            for line in mv.get('german', []):
                if isinstance(line, dict):
                    german_lines.append(line.get('text', ''))
                elif isinstance(line, str):
                    german_lines.append(line)
            result.append({
                'movement': mv.get('number', mv.get('mv_num', 0)),
                'type': mv_type,
                'chorale_type': 'embedded' if mv_type.lower() != 'chorale' else 'pure',
                'german_lines': german_lines,
            })
    return result


def _parse_movements_field(movements_str):
    """Parse a movements string from chorale index bwv_usages.

    Handles formats: "1", "1-6", "1,6", "1,~2-3,4", null/None

    Returns sorted list of unique int movement numbers.
    """
    if movements_str is None or movements_str == '':
        return None  # signal: entire chorale used

    result = set()
    parts = movements_str.split(',')
    for part in parts:
        part = part.strip().lstrip('~')  # strip tilde prefix (paraphrased)
        if '-' in part:
            try:
                lo, hi = part.split('-', 1)
                lo_num = int(lo.strip())
                hi_num = int(hi.strip())
                for n in range(lo_num, hi_num + 1):
                    result.add(n)
            except (ValueError, TypeError):
                continue
        else:
            try:
                result.add(int(part.strip()))
            except (ValueError, TypeError):
                continue
    return sorted(result) if result else None


def _parse_mvt_number(mvt_str):
    """Parse movement number from a Mvt string like 'Mvt. 2', 'Mvt. 8' etc."""
    if not mvt_str:
        return None
    m = re.search(r'Mvt\.?\s*(\d+)', str(mvt_str), re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Try just digits
    m = re.search(r'(\d+)', str(mvt_str))
    if m:
        return int(m.group(1))
    return None


def _build_verse_mapping(chorale_data, bwv_str):
    """Build {movement_number: verse_number} mapping from vocal_works.

    Supports both table-format vocal_works (ver/work/mvt) and
    text-line-format (bwv/movement/verse) entries.
    """
    mapping = {}
    for vw in chorale_data.get('vocal_works', []):
        # ── Table-format entry ──
        ver_str = vw.get('ver', '')
        work = vw.get('work', '')
        mvt_str = vw.get('mvt', '')
        if ver_str and ver_str not in ('-', '') and work:
            if f'BWV {bwv_str}' in work or f'BWV{bwv_str}' in work:
                try:
                    ver_num = int(ver_str)
                    m_num = _parse_mvt_number(mvt_str)
                    if m_num and ver_num:
                        mapping[m_num] = ver_num
                except (ValueError, TypeError):
                    pass
                continue  # already matched by table format

        # ── Text-line-format entry ──
        bwv_ref = vw.get('bwv', '')
        verse_str = vw.get('verse', '')
        mvt_num = vw.get('movement', '')
        if bwv_ref and verse_str:
            # Normalize BWV reference comparison
            v_ref = bwv_ref.strip()
            v_target = bwv_str.strip()
            # Allow "Anh 199" vs "Anh199" differences
            v_ref_norm = re.sub(r'\s+', '', v_ref)
            v_target_norm = re.sub(r'\s+', '', v_target)
            if v_ref_norm == v_target_norm:
                try:
                    ver_num = int(verse_str)
                    m_num = int(mvt_num) if mvt_num else None
                    if m_num and ver_num:
                        mapping[m_num] = ver_num
                except (ValueError, TypeError):
                    pass

    return mapping


def _ensure_chorale_scraped(chorale_id):
    """Auto-scrape chorale detail data if JSON doesn't exist yet."""
    chorale_dir = _get_chorale_subsystem_path()
    json_path = os.path.join(chorale_dir, 'data', f'{chorale_id}.json')
    if os.path.exists(json_path):
        return

    workspace = os.path.dirname(chorale_dir)
    if workspace not in sys.path:
        sys.path.insert(0, workspace)
    try:
        from importlib import import_module
        scraper = import_module('巴赫康塔塔中的众赞歌.chorale_scraper')
        data = scraper.scrape_chorale_detail(chorale_id)
        scraper.save_chorale_data(chorale_id, data)
        print(f"  [step45] Auto-scraped {chorale_id}")
    except Exception as e:
        print(f"  [step45] WARN: Failed to auto-scrape {chorale_id}: {e}")


def _normalize_line(s):
    """Normalize a German lyric line for comparison (lowercase, strip punctuation)."""
    return re.sub(r'\s+', ' ', re.sub(r'[^a-zäöüß\s]', ' ', s.lower())).strip()


def _align_chorale_translation(chorale_de_lines, cn_lines, cantata_de_lines):
    """Re-align a chorale's Chinese translation to a cantata movement's German lines.

    The chorale subsystem (bach-cantatas.com) and UAlberta may split the *same*
    chorale text into different line breaks. E.g.:

      chorale:   "Amen! Amen!"            (1 line)   vs  UAlberta: "Amen!" "Amen!" (2 lines)
      chorale:   "Komm, ..." "Bleib ..."  (2 lines)  vs  UAlberta: "Komm, ... bleib ..." (1 line)

    Simply copying `cn_lines` position-by-position therefore misaligns the
    translation. This function does a word-level sequence alignment (difflib)
    between the two German lineings and re-maps each Chinese line to the
    cantata's line boundaries.

    Rules:
      - identical line counts + exact per-line match  -> return cn_lines as-is
      - merge (chorale N lines -> cantata 1 line)     -> join CN lines with 「，」
      - split (chorale 1 line -> cantata N lines)     -> full CN on the first
                                                          matched line, later lines blank
    Returns a list of Chinese lines with the same length as `cantata_de_lines`.
    """
    n_c = len(chorale_de_lines)
    n_k = len(cantata_de_lines)
    cn_lines = list(cn_lines)

    # Fast path: identical line counts and every line matches verbatim.
    if n_c == n_k and all(
        _normalize_line(a) == _normalize_line(b)
        for a, b in zip(chorale_de_lines, cantata_de_lines)
    ):
        return cn_lines

    def _tokens(s):
        return re.findall(r'[a-zäöüß]+', s.lower())

    c_tokens, c_li = [], []
    for li, line in enumerate(chorale_de_lines):
        for tok in _tokens(line):
            c_tokens.append(tok)
            c_li.append(li)
    k_tokens, k_li = [], []
    for li, line in enumerate(cantata_de_lines):
        for tok in _tokens(line):
            k_tokens.append(tok)
            k_li.append(li)

    if not c_tokens or not k_tokens:
        # Cannot align by words; fall back to positional copy (best effort).
        return cn_lines + [''] * (n_k - n_c) if n_c <= n_k else cn_lines[:n_k]

    import difflib
    from collections import defaultdict
    sm = difflib.SequenceMatcher(a=c_tokens, b=k_tokens, autojunk=False)

    # cantata line -> {chorale line: matched-word-count}
    k2c = defaultdict(lambda: defaultdict(int))
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                k2c[k_li[j1 + k]][c_li[i1 + k]] += 1

    result = [''] * n_k
    assigned_c = set()  # chorale lines already consumed (for split de-dup)
    for kl in range(n_k):
        c_map = k2c.get(kl, {})
        if not c_map:
            continue
        parts = []
        for cl in sorted(c_map.keys()):
            if cl in assigned_c:
                continue
            if cl < n_c:
                parts.append(cn_lines[cl])
                assigned_c.add(cl)
        if parts:
            if len(parts) == 1:
                result[kl] = parts[0]
            else:
                # Join merged CN lines, stripping stray trailing punctuation
                # so "…冠冕，" + "切莫耽延，" -> "…冠冕，切莫耽延，"
                cleaned = [p.strip('，、；,; ') for p in parts if p.strip('，、；,; ')]
                result[kl] = '，'.join(cleaned) + '，'
    return result


def _match_chorale_movements(chorale_movements, chorale_data_dir, bwv_str):
    """Match each chorale movement to its verse in the chorale subsystem.

    Uses the chorale index bwv_lookup + chorale JSON vocal_works table
    to map movement numbers to verse numbers.

    Fallback: if bwv_lookup misses entries, scans ALL chorales' bwv_usages
    for this BWV number (cross-reference with full index).
    """
    index = _load_index()
    if not index:
        return []

    bwv_lookup = index.get('bwv_lookup', {})
    chorales = index.get('chorales', [])
    if not chorales:
        return []

    # ── Build full BWV→chorale index from ALL chorales' bwv_usages ──
    full_bwv_to_chorales = {}
    for ci, entry in enumerate(chorales):
        for usage in entry.get('bwv_usages', []):
            u_bwv = str(usage.get('bwv', '')).strip()
            u_bwv_norm = re.sub(r'\s+', '', u_bwv)  # Normalize "Anh 199" → "Anh199"
            if u_bwv not in full_bwv_to_chorales:
                full_bwv_to_chorales[u_bwv] = set()
            full_bwv_to_chorales[u_bwv].add(ci)
            if u_bwv_norm != u_bwv:
                if u_bwv_norm not in full_bwv_to_chorales:
                    full_bwv_to_chorales[u_bwv_norm] = set()
                full_bwv_to_chorales[u_bwv_norm].add(ci)

    # ── Resolve chorale indices for this BWV ──
    lookup_key = bwv_str
    lookup_key_norm = re.sub(r'\s+', '', lookup_key)

    indices = bwv_lookup.get(lookup_key, [])
    if not indices:
        indices = bwv_lookup.get(lookup_key_norm, [])

    # Fallback: if bwv_lookup missed entries, add from full index
    fb_indices = full_bwv_to_chorales.get(lookup_key, set())
    if not fb_indices:
        fb_indices = full_bwv_to_chorales.get(lookup_key_norm, set())
    indices = list(set(indices) | fb_indices)  # merge & dedup

    if not indices:
        return []

    results = []

    for cm in chorale_movements:
        mvt_num = cm['movement']
        matched = False

        for idx in indices:
            if idx >= len(chorales):
                continue
            entry = chorales[idx]

            chorale_id = entry.get('chorale_id') or entry.get('id')
            if not chorale_id:
                continue

            chorale_json_path = os.path.join(chorale_data_dir, f'{chorale_id}.json')
            if not os.path.exists(chorale_json_path):
                # Auto-scrape missing chorale data
                try:
                    _ensure_chorale_scraped(chorale_id)
                except Exception:
                    continue
                if not os.path.exists(chorale_json_path):
                    continue

            with open(chorale_json_path, 'r', encoding='utf-8') as f:
                chorale_data = json.load(f)

            # Build verse mapping from vocal_works
            verse_map = _build_verse_mapping(chorale_data, bwv_str)

            # If vocal_works has no mapping, try sequential fallback
            verse_num = verse_map.get(mvt_num)
            if verse_num is None:
                mapped_keys = sorted(verse_map.keys())
                if mapped_keys:
                    # Sequential fallback: if cantata uses chorale from mvt X onwards
                    min_mvt = min(mapped_keys)
                    verse_num = mvt_num - min_mvt + 1
                    if verse_num < 1 or verse_num > len(chorale_data.get('german_text', {})):
                        verse_num = None

            if verse_num is None:
                continue

            # Check for existing Chinese translation
            chinese_text = chorale_data.get('chinese_text', {})
            verse_key = str(verse_num)
            cn_verse = chinese_text.get(verse_key)

            if cn_verse:
                # Handle both formats: dict {'lines': [...], ...}  and list [...]
                if isinstance(cn_verse, dict):
                    cn_lines = cn_verse.get('lines', [])
                elif isinstance(cn_verse, list):
                    cn_lines = cn_verse
                else:
                    cn_lines = None

                if cn_lines:
                    # Re-align the chorale's translation to this movement's
                    # German line breaks (chorale subsystem vs UAlberta may
                    # split the same text differently, e.g. "Amen! Amen!").
                    chorale_verse_data = chorale_data.get('german_text', {}).get(verse_key)
                    if isinstance(chorale_verse_data, dict):
                        chorale_de_lines = chorale_verse_data.get('lines', [])
                    elif isinstance(chorale_verse_data, list):
                        chorale_de_lines = chorale_verse_data
                    else:
                        chorale_de_lines = []
                    if chorale_de_lines:
                        cn_lines = _align_chorale_translation(
                            chorale_de_lines, cn_lines, cm['german_lines']
                        )

                    results.append({
                        'movement': mvt_num,
                        'chorale_id': chorale_id,
                        'chorale_title': chorale_data.get('title', entry.get('title', '')),
                        'chorale_verse': verse_num,
                        'status': 'filled',
                        'chinese_lines': cn_lines,
                        'source': f'{chorale_id}.json verse {verse_num}',
                    })
            else:
                results.append({
                    'movement': mvt_num,
                    'chorale_id': chorale_id,
                    'chorale_title': chorale_data.get('title', entry.get('title', '')),
                    'chorale_verse': verse_num,
                    'status': 'needs_translation',
                    'chinese_lines': None,
                    'source': None,
                })
            matched = True
            break  # Found match for this movement

        if not matched:
            results.append({
                'movement': mvt_num,
                'chorale_id': None,
                'chorale_title': None,
                'chorale_verse': None,
                'status': 'no_match',
                'chinese_lines': None,
                'source': 'Could not match chorale_index entry',
            })

    return results


def _write_manifest(bwv_dir, bwv_number, matched_results):
    """Write chorale_reuse_manifest.json to BWV_N/data/.

    Returns path to the manifest file.
    """
    data_dir = os.path.join(bwv_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)

    filled = [r for r in matched_results if r['status'] == 'filled']
    needs = [r for r in matched_results if r['status'] == 'needs_translation']
    no_match = [r for r in matched_results if r['status'] == 'no_match']

    manifest = {
        'bwv': str(bwv_number),
        'generated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'chorale_movements': matched_results,
        'summary': {
            'total': len(matched_results),
            'filled': len(filled),
            'needs_translation': len(needs),
            'no_match': len(no_match),
        },
    }

    manifest_path = os.path.join(data_dir, 'chorale_reuse_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest_path


# ═══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def run(bwv_number, bwv_dir):
    """Main entry point for chorale reuse detection.

    Args:
        bwv_number: int or str
        bwv_dir: str, path to BWV_N/ directory

    Returns:
        dict with chorale_movements, filled, needs_translation, manifest_path, summary
    """
    bwv_str = str(bwv_number)
    chorale_subsystem = _get_chorale_subsystem_path()
    chorale_data_dir = os.path.join(chorale_subsystem, 'data')

    # 1. Find chorale-type movements
    texts_path = os.path.join(bwv_dir, 'data', 'texts.json')
    chorale_movements = _find_chorale_movements(texts_path)

    if not chorale_movements:
        # No chorale movements to process
        manifest = {
            'bwv': bwv_str,
            'generated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'chorale_movements': [],
            'summary': {'total': 0, 'filled': 0, 'needs_translation': 0, 'no_match': 0},
        }
        manifest_path = os.path.join(bwv_dir, 'data', 'chorale_reuse_manifest.json')
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return {
            'chorale_movements': [],
            'filled': [],
            'needs_translation': [],
            'manifest_path': manifest_path,
            'summary': manifest['summary'],
        }

    # 2. Cross-reference with metadata.json chorale_ids (from bach-cantatas.com links)
    metadata_path = os.path.join(bwv_dir, 'data', 'metadata.json')
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            bc_chorale_ids = meta.get('chorale_ids', [])
            if bc_chorale_ids:
                print(f"  [step45] bach-cantatas.com chorale links: {', '.join(bc_chorale_ids)}")
        except Exception:
            bc_chorale_ids = []
    else:
        bc_chorale_ids = []

    # 3. Match to chorale subsystem
    matched = _match_chorale_movements(chorale_movements, chorale_data_dir, bwv_str)

    # 4. Fallback: if any movements are unmatched, try metadata chorale_ids
    unmatched = [r for r in matched if r['status'] == 'no_match']
    if unmatched and bc_chorale_ids:
        # Direct lookup by chorale_id from bach-cantatas.com
        for cm in unmatched:
            # Find which chorale in the index corresponds to this movement
            for cid in bc_chorale_ids:
                chorale_json_path = os.path.join(chorale_data_dir, f'{cid}.json')
                if not os.path.exists(chorale_json_path):
                    try:
                        _ensure_chorale_scraped(cid)
                    except Exception:
                        continue
                if os.path.exists(chorale_json_path):
                    with open(chorale_json_path, 'r', encoding='utf-8') as f:
                        cd = json.load(f)
                    # Use first verse by default if vocal_works has no movement mapping
                    vm = _build_verse_mapping(cd, bwv_str)
                    verse_num = vm.get(cm['movement'], 1)
                    cn = cd.get('chinese_text', {})
                    cv = cn.get(str(verse_num))
                    if isinstance(cv, dict):
                        cn_lines = cv.get('lines', [])
                    elif isinstance(cv, list):
                        cn_lines = cv
                    else:
                        cn_lines = None

                    status = 'filled' if cn_lines else 'needs_translation'
                    cm['status'] = status
                    cm['chorale_id'] = cid
                    cm['chorale_title'] = cd.get('title', '')
                    cm['chorale_verse'] = verse_num
                    cm['chinese_lines'] = cn_lines
                    cm['source'] = f'{cid}.json v{verse_num} (from metadata)' if cn_lines else 'metadata fallback'
                    break

    # 5. Write manifest
    manifest_path = _write_manifest(bwv_dir, bwv_str, matched)

    # 4. Split results
    filled = [r for r in matched if r['status'] == 'filled']
    needs = [r for r in matched if r['status'] == 'needs_translation']

    summary = {
        'total': len(matched),
        'filled': len(filled),
        'needs_translation': len(needs),
        'no_match': len([r for r in matched if r['status'] == 'no_match']),
    }

    return {
        'chorale_movements': chorale_movements,
        'filled': filled,
        'needs_translation': needs,
        'manifest_path': manifest_path,
        'summary': summary,
    }
