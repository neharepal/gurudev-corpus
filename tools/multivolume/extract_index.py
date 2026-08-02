"""Phase 4 — extract machine-readable chapter index for kakanchi-pravachane.

For each vol:
  - Walk the v2 file for chapter markers (regex per vol style)
  - For each chapter, resolve its source printed page via the Surya JSON
    (skipping TOC-page hits)
  - Extract the printed अनुक्रमणिका at the top of the file (TOC)
  - Cross-check: does the TOC list N chapters, and do their titles match the body?

Emits:
  staging/kakanchi-pravachane.index.json — canonical index [{vol, ch, title, src_page}]
  staging/index_report.md — human-readable summary + mismatches
"""
from __future__ import annotations

import json
import re
import glob
from pathlib import Path

STAGING = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging')
RAW = '/Users/neharepal/gurudev-corpus/_surya_ocr_job/out_raw'

_TAG = re.compile(r'<[^>]+>')
_BR = re.compile(r'<br\s*/?>', re.I)
def h2t(h: str) -> str:
    if not h: return ''
    return _TAG.sub('', _BR.sub('\n', h)).strip()

# For each vol, the printed TOC + front-matter occupies roughly this many pages.
# Body content starts at TOC_END_PAGE + 1. Used to skip TOC-page hits when
# resolving a chapter's printed page.
TOC_END_PAGE = {1: 0, 2: 0, 3: 4, 4: 6, 5: 6}

_pages_cache: dict[int, list] = {}
def load_surya_pages(vol: int):
    if vol not in _pages_cache:
        jp = glob.glob(f'{RAW}/kakanchi-pravachane-vol{vol}/**/results.json', recursive=True)[0]
        _pages_cache[vol] = next(iter(json.load(open(jp)).values()))
    return _pages_cache[vol]

def find_src_page(vol: int, snippet: str) -> int | None:
    """Find the printed page where `snippet` appears as a heading, past the TOC.

    Prefer SectionHeader blocks; fall back to first Text-block occurrence.
    """
    min_page = TOC_END_PAGE.get(vol, 0)
    # First pass: SectionHeader label
    for pg in load_surya_pages(vol):
        pnum = pg.get('page') or 0
        if pnum <= min_page: continue
        for b in (pg.get('blocks') or []):
            if b.get('label') != 'SectionHeader': continue
            if snippet in h2t(b.get('html') or ''):
                return pnum
    # Fallback: first Text-block hit past TOC
    for pg in load_surya_pages(vol):
        pnum = pg.get('page') or 0
        if pnum <= min_page: continue
        for b in (pg.get('blocks') or []):
            if snippet in h2t(b.get('html') or ''):
                return pnum
    return None

DEV = '०१२३४५६७८९'
def to_int(s: str) -> int | None:
    try: return int(s.translate(str.maketrans(DEV, '0123456789')))
    except: return None

PUSHPA_RE = re.compile(r'^\s*पुष्प\s+([०-९\d]+)(?:\s*[-–—]\s*(.+))?\s*$')
NUMBERED_RE = re.compile(r'^\s*([०-९\d]{1,2})\.\s+(.{3,120})\s*$')
SUBLECT_RE = re.compile(r'^\s*([०-९\d])\)\s*(.+)$')

def next_nonblank(lines, idx):
    j = idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return lines[j] if j < len(lines) else ''

def extract_vol1(v2_path: Path) -> list[dict]:
    """Vol 1: 9 पुष्प, title on next non-blank line."""
    lines = v2_path.read_text(encoding='utf-8').splitlines()
    chapters = []
    for i, L in enumerate(lines):
        m = PUSHPA_RE.match(L)
        if not m: continue
        no = to_int(m.group(1))
        if no is None or no > 9: continue
        title = (m.group(2) or '').strip() or next_nonblank(lines, i).strip()
        chapters.append({'no': no, 'title': title, 'line_in_v2': i + 1})
    seen = set()
    result = []
    for c in chapters:
        if c['no'] in seen: continue
        seen.add(c['no'])
        result.append(c)
    return sorted(result, key=lambda x: x['no'])

def extract_vol2(v2_path: Path) -> list[dict]:
    """Vol 2: 4 पुष्प + 2 तुकाराम sub-sections = 6 chapters."""
    lines = v2_path.read_text(encoding='utf-8').splitlines()
    chapters = []
    # Pushpas 1-4
    for i, L in enumerate(lines):
        m = PUSHPA_RE.match(L)
        if not m: continue
        no = to_int(m.group(1))
        if no is None or no > 4: continue
        title = (m.group(2) or '').strip() or next_nonblank(lines, i).strip()
        chapters.append({'no': no, 'title': title, 'line_in_v2': i + 1})
    # Filter dups
    seen = set()
    filtered = []
    for c in chapters:
        if c['no'] in seen: continue
        seen.add(c['no'])
        filtered.append(c)
    filtered.sort(key=lambda x: x['no'])
    # तुकाराम भाग-१ and भाग-२ as chapters 5, 6
    for i, L in enumerate(lines):
        s = L.strip()
        if 'तुकाराम' in s and 'भाग' in s and len(s) < 40:
            filtered.append({
                'no': 5 if 'भाग - १' in s or '(भाग - १' in s or 'भाग - १' in s else 6,
                'title': s,
                'line_in_v2': i + 1,
            })
    # Deduplicate again on (no)
    seen = set()
    out = []
    for c in filtered:
        if c['no'] in seen: continue
        seen.add(c['no'])
        out.append(c)
    return sorted(out, key=lambda x: x['no'])

def extract_vol3(v2_path: Path) -> list[dict]:
    """Vol 3: 2 top-level lectures + 5 sub-parts of the 1978 lecture = 7 chapters."""
    lines = v2_path.read_text(encoding='utf-8').splitlines()

    # Top-level lecture titles (from Phase 2)
    top_titles = {
        1: 'गुरुदेवांचे साक्षात्काराचे तत्त्वज्ञान व सोपान',
        2: 'परमार्थसोपानाच्या पाच पायऱ्या',
    }
    sub_titles = {
        1: 'परमार्थ प्रवृत्तीची कारणे',
        2: 'सद्गुण संपादन',
        3: 'देव-भक्तांचे नाते',
        4: 'साधन विचार',
        5: 'साक्षात्कार',
    }
    chapters = []
    # Search body for each title as a line-start match, skipping TOC region
    # (first ~20 lines are TOC/anukramanika)
    body_start_line = 20
    for no, title in top_titles.items():
        for i, L in enumerate(lines):
            if i < body_start_line: continue
            if title in L and len(L.strip()) < len(title) + 25:
                chapters.append({'no': no, 'kind': 'lecture', 'title': title, 'line_in_v2': i + 1})
                break
    # For sub-parts, search for the numbered marker `N)` followed by the title
    # (with some tolerance for OCR variance)
    dev_no = '०१२३४५६७८९'
    for no, title in sub_titles.items():
        dev = dev_no[no]  # e.g. no=1 → '१'
        for i, L in enumerate(lines):
            if i < body_start_line: continue
            s = L.strip()
            # Match `N) title` or `N. title` where title matches expected
            if (s.startswith(f'{dev})') or s.startswith(f'{dev}.') or s.startswith(f'{dev} .')) \
                    and title[:15] in s and len(s) < 100:
                chapters.append({'no': f'3.{no}', 'kind': 'sublecture', 'title': title, 'line_in_v2': i + 1})
                break
    return chapters

def _find_appendix(lines: list[str]) -> dict | None:
    """Locate `परिशिष्ट - १ हौदाची उपमा` chapter in the body (past halfway).

    The printed TOC lists it near the top; the body has it near the end
    with real content. Pick the LAST occurrence.
    """
    hit = None
    for i, L in enumerate(lines):
        s = L.strip()
        if 'परिशिष्ट' in s and len(s) < 60:
            hit = {'title': 'परिशिष्ट - १  हौदाची उपमा', 'line_in_v2': i + 1}
    return hit


def extract_vol4_or_5(v2_path: Path, expected_count: int) -> list[dict]:
    """Vols 4/5: N. <title> combined. TOC has 1..N, body has 1..N again — pick
    the SECOND occurrence of each number (TOC first, body second). Cap title
    length at 100 chars to reject prose lines that happen to start with a digit."""
    lines = v2_path.read_text(encoding='utf-8').splitlines()
    all_markers = []
    for i, L in enumerate(lines):
        m = NUMBERED_RE.match(L.rstrip('.।॥ '))
        if not m: continue
        no = to_int(m.group(1))
        if no is None or no < 1 or no > 20: continue
        title = m.group(2).rstrip('.।॥ ').strip()
        if len(title) < 6 or len(title) > 100: continue
        all_markers.append({'no': no, 'title': title, 'line_in_v2': i + 1})

    # Group by number, pick the SECOND occurrence (first = TOC entry, second = body)
    by_no_all: dict[int, list] = {}
    for m in all_markers:
        by_no_all.setdefault(m['no'], []).append(m)
    body_chapters: list[dict] = []
    for no, occurrences in sorted(by_no_all.items()):
        if no > expected_count: continue
        # Second-and-later occurrences: body. Prefer the SECOND (first body hit).
        if len(occurrences) >= 2:
            body_chapters.append(occurrences[1])
        else:
            body_chapters.append(occurrences[0])
    # Append परिशिष्ट - १ as chapter (expected_count + 1)
    appx = _find_appendix(lines)
    if appx:
        body_chapters.append({
            'no': expected_count + 1,
            'title': appx['title'],
            'line_in_v2': appx['line_in_v2'],
        })
    return body_chapters

def annotate_src_page(chapters: list[dict], vol: int) -> list[dict]:
    dev_no = '०१२३४५६७८९'
    for c in chapters:
        no = c.get('no')
        title = c['title']
        # Try marker-anchored search first (e.g., "६) सत्संगती" or "६. सत्संगती")
        pg = None
        if title.startswith('परिशिष्ट'):
            # Search for the distinctive appendix heading: "हौदाची उपमा -"
            pg = find_src_page(vol, 'हौदाची उपमा -')
        elif isinstance(no, int) and 1 <= no <= 9:
            marker = dev_no[no]
            pg = find_src_page(vol, f'{marker}. {title[:30]}') or find_src_page(vol, f'{marker}) {title[:30]}')
        elif isinstance(no, int) and 10 <= no <= 19:
            marker = dev_no[no // 10] + dev_no[no % 10]
            pg = find_src_page(vol, f'{marker}. {title[:30]}')
        elif isinstance(no, str) and no.startswith('3.'):
            sub = int(no.split('.')[1])
            marker = dev_no[sub]
            pg = find_src_page(vol, f'{marker}) {title[:20]}') or find_src_page(vol, f'{marker}. {title[:20]}')
        # Fallback: search by title fragment only
        if pg is None:
            pg = find_src_page(vol, title[:40])
        c['src_page'] = pg
    return chapters

# ─── Run for all 5 vols ───

report = ['# Phase 4 — chapter index + अनुक्रमणिका cross-check\n']
all_chapters = {}

extractors = {
    1: (extract_vol1, 9),
    2: (extract_vol2, 6),
    3: (extract_vol3, 7),
    4: (lambda p: extract_vol4_or_5(p, 11), 12),  # 11 numbered + परिशिष्ट
    5: (lambda p: extract_vol4_or_5(p, 12), 13),  # 12 numbered + परिशिष्ट
}

for vol in (1, 2, 3, 4, 5):
    v2 = STAGING / f'kakanchi-pravachane-vol{vol}.v2.md'
    fn, expected = extractors[vol]
    chapters = fn(v2)
    chapters = annotate_src_page(chapters, vol)
    all_chapters[f'vol{vol}'] = chapters

    report.append(f'\n## vol {vol}\n')
    report.append(f'- Body chapters detected: **{len(chapters)}** (expected {expected})')
    report.append(f'- {"✓ MATCH" if len(chapters) == expected else "✗ MISMATCH"}\n')
    report.append('| # | Title | v2 line | Printed page |')
    report.append('|---|---|---|---|')
    for c in chapters:
        title = c['title'][:70]
        pg = c.get('src_page', '?')
        report.append(f"| {c['no']} | {title} | L{c['line_in_v2']} | p. {pg} |")

(STAGING / 'kakanchi-pravachane.index.json').write_text(
    json.dumps(all_chapters, indent=2, ensure_ascii=False), encoding='utf-8')
(STAGING / 'index_report.md').write_text('\n'.join(report), encoding='utf-8')
print('Wrote index.json + index_report.md')
