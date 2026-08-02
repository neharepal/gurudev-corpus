"""Phase 5 — assemble the canonical kakanchi-pravachane text.md from 5 v2 files.

Structure of output:

  ---
  work_id: kakanchi-pravachane
  author: kakasaheb_tulpule
  work_type: lecture
  language: mr
  title_en: "Kakanchi Pravachane"
  sources:
    - kakanchi-pravachane-vol1.pdf
    - kakanchi-pravachane-vol2.pdf
    ...
  extracted_via: "Surya OCR-2 (2026-07-30) + Phase 3 cleanup + Phase 3.5 targeted fixes + Phase 5 assembly"
  extracted_on: 2026-08-01
  has_toc: true
  chapter_count: 47
  ---

  ## भाग १
  ### पुष्प १ — वैकुंठचतुर्दशीनिमित्त
  <body>

  ### पुष्प २ — अखंड कंठी गुरु धारियेले
  <body>

  ...

  ## भाग २
  ...

Backup:
  If canonical text.md exists, save as text.md.pre-vols123-surya-2026-08-01.bak
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from datetime import date

STAGING = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging')
CANONICAL_DIR = Path('/Users/neharepal/gurudev-corpus/01_canonical/kakasaheb_tulpule/lectures/kakanchi-pravachane/mr')
CANONICAL_MD = CANONICAL_DIR / 'text.md'
INDEX_JSON = STAGING / 'kakanchi-pravachane.index.json'


def chapter_heading(vol: int, no, title: str) -> str:
    """Build the markdown ### heading — title only.

    Citation decision (from Neha, Aug 2026): the citable identity is the
    chapter's title text alone. Volume-internal numbering (पुष्प N / N. / N))
    is metadata for retrieval/chunk attribution, not part of the display
    heading. Appendices keep their `परिशिष्ट - १` prefix because the printed
    book uses that as the actual title.
    """
    return f'### {title}'


def strip_marker_lines(body: list[str], vol: int, title: str) -> list[str]:
    """Remove the plain-text chapter-marker lines from a chapter's body so the
    markdown heading isn't duplicated by the original text.

    Strategy: pop leading lines that match any known chapter-marker pattern
    OR that literally repeat the chapter title, OR blank lines interspersed.
    Stop as soon as we hit a "real" body line (long paragraph, or a line that
    isn't a marker/title/blank).
    """
    result = list(body)
    while result:
        s = result[0].strip()
        # Blank line — always pop
        if not s:
            result.pop(0); continue
        # Vol 1, 2 पुष्प marker line: "पुष्प N" or "पुष्प N — <title>"
        if re.match(r'^पुष्प\s+[०-९\d]+\s*(?:[-–—]\s*.+)?\s*$', s):
            result.pop(0); continue
        # Vol 4, 5 numbered heading: "N. <title>"
        if re.match(r'^[०-९\d]{1,2}\.\s+.{3,80}\s*$', s):
            result.pop(0); continue
        # Vol 3 sub-part: "N) <title>"
        if re.match(r'^[०-९]\)\s*.{3,80}\s*$', s):
            result.pop(0); continue
        # Vol 4 subtitle line like "भाग १" or "भाग २"
        if re.match(r'^भाग\s+[०-९\d]+\s*$', s):
            result.pop(0); continue
        # Vol 2 title-line for तुकाराम sections: "तुकाराम ( भाग - १ )"
        if re.match(r'^तुकाराम\s*\(\s*भाग.*\)\s*$', s):
            result.pop(0); continue
        # Vol 4/5 appendix header: "परिशिष्ट - १"
        if re.match(r'^परिशिष्ट\s*[-–—]\s*[०-९\d]+.*$', s) and len(s) < 60:
            result.pop(0); continue
        # Vol 4/5 appendix inner heading: "हौदाची उपमा -"
        if s.startswith('हौदाची उपमा') and len(s) < 40:
            result.pop(0); continue
        # Literal repeat of chapter title (short line matching title[:20])
        if title and title[:20] in s and len(s) < len(title) + 20:
            result.pop(0); continue
        # Everything else — chapter body proper
        break
    return result


def assemble_vol(vol: int, chapters: list[dict]) -> str:
    """Build the markdown section for one volume."""
    v2 = STAGING / f'kakanchi-pravachane-vol{vol}.v2.md'
    lines = v2.read_text(encoding='utf-8').splitlines()

    # Skip vol-title lines and front matter — start assembling from chapter 1's line
    if not chapters:
        return ''
    first_line = chapters[0]['line_in_v2'] - 1  # 0-indexed

    out = [f'## भाग {["०","१","२","३","४","५"][vol]}\n']

    # For each chapter, extract body between this chapter's line and next chapter's line
    for i, ch in enumerate(chapters):
        start = ch['line_in_v2'] - 1
        end = chapters[i + 1]['line_in_v2'] - 1 if i + 1 < len(chapters) else len(lines)
        body = lines[start:end]
        body = strip_marker_lines(body, vol, ch['title'])
        heading = chapter_heading(vol, ch['no'], ch['title'])
        out.append(heading)
        out.append('')
        out.append('\n'.join(body).rstrip())
        out.append('')

    return '\n'.join(out).rstrip() + '\n'


def main():
    index = json.loads(INDEX_JSON.read_text(encoding='utf-8'))

    # Build frontmatter
    fm_lines = [
        '---',
        'work_id: kakanchi-pravachane',
        'author: kakasaheb_tulpule',
        'work_type: lecture',
        'language: mr',
        'title_en: "Kakanchi Pravachane"',
        'sources:',
        '  - kakanchi-pravachane-vol1.pdf',
        '  - kakanchi-pravachane-vol2.pdf',
        '  - kakanchi-pravachane-vol3.pdf',
        '  - kakanchi-pravachane-vol4.pdf',
        '  - kakanchi-pravachane-vol5.pdf',
        'extracted_via: "Surya OCR-2 + Phase 3 cleanup + Phase 3.5 targeted fixes + Phase 5 assembly (RFC-020)"',
        f'extracted_on: {date.today().isoformat()}',
        'has_toc: true',
        f'chapter_count: {sum(len(index[f"vol{v}"]) for v in (1,2,3,4,5))}',
        '---',
        '',
    ]

    # Assemble all vols
    body_parts = []
    for vol in (1, 2, 3, 4, 5):
        chapters = index[f'vol{vol}']
        body_parts.append(assemble_vol(vol, chapters))

    full = '\n'.join(fm_lines) + '\n\n'.join(body_parts)

    # Backup existing
    if CANONICAL_MD.exists():
        bak = CANONICAL_MD.parent / f'text.md.pre-vols123-surya-{date.today().isoformat()}.bak'
        shutil.copy2(CANONICAL_MD, bak)
        print(f'Backed up existing → {bak.name}')

    # Write new canonical
    CANONICAL_MD.write_text(full, encoding='utf-8')
    print(f'Wrote {CANONICAL_MD}')
    print(f'  size: {len(full):,} chars')
    print(f'  lines: {full.count(chr(10)):,}')
    # Verify chapter counts
    print(f'  ## भाग markers: {full.count(chr(10) + "## भाग")}')
    print(f'  ### chapter markers: {full.count(chr(10) + "### ")}')


if __name__ == '__main__':
    main()
