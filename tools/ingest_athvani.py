#!/usr/bin/env python3
"""
Multi-variant athvani ingestion tool.

Usage:
    python3 tools/ingest_athvani.py <source.docx> [--about <lineage_member>]

Behavior (per RFC-002 §6-7):
  1. Convert docx -> clean markdown via pandoc.
  2. Segment into candidate stories using conservative markers
     (emoji dividers, numbered headings, prominent bold headings).
  3. For each candidate: extract one_line summary, probable key_people,
     locations, fingerprint phrases.
  4. Score against 03_catalog/story_index.yaml:
        score = 2*about_member_match + 1*key_people_overlap(>=2)
                + 1*location_overlap(>=1) + 1*fingerprint_hits(>=2)
        score >= 4 -> HIGH  (merge as variant)
        score in 2,3 -> MEDIUM (review queue)
        score in 0,1 -> LOW (create new story)
  5. Persist story_index.yaml after EVERY candidate so a crash mid-run
     is recoverable.

Outputs land under:
  02_aggregated/athvani/about_<member>/stories/<slug>/
        meta.yaml
        mr/variants/<source_id>_<index>.md

Review-queue path:
  03_catalog/review_queue.yaml
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
STORY_INDEX_PATH = REPO_ROOT / "03_catalog" / "story_index.yaml"
REVIEW_QUEUE_PATH = REPO_ROOT / "03_catalog" / "review_queue.yaml"
ATHVANI_ROOT = REPO_ROOT / "02_aggregated" / "athvani"

LINEAGE_MEMBERS = {
    "nimbargi_maharaj",
    "bhausaheb_maharaj",
    "amburao_maharaj",
    "gurudev_ranade",
    "kakasaheb_tulpule",
    "other_devotees",
}

# Known locations / signal words (English + Marathi/Devanagari variants).
# IMPORTANT: nimbal (निंबाळ — Gurudev's village) and nimbargi (निंबरगी —
# Nimbargi Maharaj's village) are DIFFERENT places. Do not collapse them.
KNOWN_LOCATIONS = {
    "nimbal": ["nimbal", "निंबाळ", "निंबाळचे", "निंबाळला", "निंबाळास"],
    "nimbargi": ["nimbargi", "निंबरगी", "निबरगी"],
    "allahabad": ["allahabad", "अलाहाबाद", "इलाहाबाद", "prayag", "प्रयाग"],
    "dharwad": ["dharwad", "धारवाड"],
    "pune": ["pune", "poona", "पुणे", "पुण्या"],
    "inchgeri": ["inchgeri", "इंचगेरी", "इंचगिरी"],
    "umadi": ["umdi", "umadi", "उमदी"],
    "sangli": ["sangli", "सांगली"],
    "jamkhandi": ["jamkhandi", "जमखंडी", "जमखिंडी"],
    "vijapur": ["vijapur", "bijapur", "विजापूर"],
    "solapur": ["solapur", "सोलापूर"],
    "alandi": ["alandi", "आळंदी"],
    "bombay": ["bombay", "mumbai", "मुंबई"],
}

# Known proper nouns appearing across the lineage corpus. Used to extract
# key_people from text. (Stored as kebab-case ids; each id has detection terms.)
KNOWN_PEOPLE = {
    "shri-gurudev-ranade": ["गुरुदेव", "रानडे", "ranade", "gurudev", "r.d. ranade", "रामभाऊ"],
    "bhausaheb-maharaj": ["भाऊसाहेब", "bhausaheb"],
    "nimbargi-maharaj": ["निंबरगी महाराज", "निबरगी महाराज", "nimbargi maharaj"],
    "amburao-maharaj": ["अंबूराव", "अमबूराव", "amburao"],
    "kakasaheb-tulpule": ["काकासाहेब", "तुळपुळे", "tulpule", "kakasaheb"],
    "sonopant-dandekar": ["सोनोपंत", "सोनपंत", "दांडेकर", "dandekar", "मामासाहेब"],
    "jog-maharaj": ["जोग महाराज", "जोगमहाराज", "jog maharaj"],
    "yuvraj-of-sangli": ["युवराज", "सांगली", "sangli yuvraj"],
    "shankarrao-dharmadhikari": ["शंकरराव धर्माधिकारी", "धर्माधिकारी"],
    "krishnarao-gajendragadkar": ["कृष्णराव", "गजेंद्रगडकर"],
    "radhakrishnan": ["राधाकृष्णन", "radhakrishnan"],
    "lokmanya-tilak": ["लोकमान्य", "टिळक", "tilak"],
    "vijaya-apte": ["विजया आपटे", "vijaya apte"],
    "dada-tendulkar": ["दादा तेंडुलकर", "तेंडुलकर"],
    "bhaurao-nimbargi": ["भाऊराव", "bhaurao"],
    "nagappa-nimbargi": ["नागप्पा", "nagappa"],
}

# Devanagari digits -> int.
DEV_DIGITS = "०१२३४५६७८९"


def to_int(s: str) -> int | None:
    try:
        out = 0
        for c in s:
            if c in DEV_DIGITS:
                out = out * 10 + DEV_DIGITS.index(c)
            elif c.isdigit():
                out = out * 10 + int(c)
            else:
                return None
        return out
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers: yaml round-trip preserving Devanagari (unicode allow_unicode)
# ---------------------------------------------------------------------------
def yaml_load(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def yaml_dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )


# ---------------------------------------------------------------------------
# pandoc extraction
# ---------------------------------------------------------------------------
def docx_to_markdown(src: Path) -> str:
    """Run pandoc; return markdown_strict text."""
    pandoc = os.environ.get("PANDOC", "pandoc")
    # Try a couple of likely paths if 'pandoc' is not on PATH.
    candidates = [pandoc, "/opt/homebrew/bin/pandoc", "/Users/neharepal/opt/anaconda3/bin/pandoc"]
    last_err = None
    for cand in candidates:
        try:
            r = subprocess.run(
                [cand, "-t", "markdown_strict", str(src)],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode == 0:
                return r.stdout
            last_err = r.stderr
        except FileNotFoundError as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"pandoc failed: {last_err}")


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------
# Strong dividers (line at start of line, after stripping).
EMOJI_DIVIDER_RE = re.compile(r"^\s*🌸{3,}\s*$")
ASTERISK_DIVIDER_RE = re.compile(r"^\s*\*\s*\*\s*\*\s*$")
NUMBERED_HEADING_RE = re.compile(r"^([०-९]+|[1-9]\d?)[\)\.]\s*\S")
PARENS_NUMBERED_RE = re.compile(r"^\*?\(?([०-९]+|[1-9]\d?)\)\*?\s*\S")


def segment_into_candidates(text: str) -> list[dict]:
    """Return list of {raw_text, heading, start_line, end_line} dicts.

    Conservative: split on emoji dividers first; if none, on '***'; if none,
    on numbered headings at line start. Always at least one candidate (the
    whole text) so we never lose content.
    """
    lines = text.split("\n")
    n = len(lines)

    # 1. Emoji-divider split (strongest signal — explicit author-placed end marker).
    emoji_positions = [i for i, ln in enumerate(lines) if EMOJI_DIVIDER_RE.match(ln)]
    if emoji_positions:
        boundaries: list[int] = [0]
        for p in emoji_positions:
            boundaries.append(p + 1)
        boundaries.append(n)
        segs = _segments_from_boundaries(lines, boundaries)
        if len(segs) >= 2:
            return segs

    # 2. '***' divider split.
    asterisk_positions = [i for i, ln in enumerate(lines) if ASTERISK_DIVIDER_RE.match(ln)]
    if len(asterisk_positions) >= 1:
        boundaries = [0]
        for p in asterisk_positions:
            boundaries.append(p + 1)
        boundaries.append(n)
        segs = _segments_from_boundaries(lines, boundaries)
        if len(segs) >= 2:
            return segs

    # 3. Numbered-heading split — only if at least 2 sequential headings.
    nh_positions: list[tuple[int, int | None]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if NUMBERED_HEADING_RE.match(s) or PARENS_NUMBERED_RE.match(s):
            # extract number
            m = re.match(r"^\*?\(?([०-९]+|[1-9]\d?)[\)\.]", s)
            num = to_int(m.group(1)) if m else None
            nh_positions.append((i, num))
    if len(nh_positions) >= 3:
        boundaries = [0] + [p for p, _ in nh_positions] + [n]
        # dedupe & sort
        boundaries = sorted(set(boundaries))
        segs = _segments_from_boundaries(lines, boundaries)
        if len(segs) >= 2:
            return segs

    # 4. Fallback: one candidate, the whole document.
    return [
        {
            "raw_text": text.strip(),
            "heading": _first_nonempty_line(lines),
            "start_line": 0,
            "end_line": n,
        }
    ]


def _segments_from_boundaries(lines: list[str], boundaries: list[int]) -> list[dict]:
    segs: list[dict] = []
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        chunk_lines = lines[a:b]
        raw = "\n".join(chunk_lines).strip()
        if len(raw) < 200:
            # Skip trivial chunks (likely just a separator + blank lines).
            continue
        segs.append(
            {
                "raw_text": raw,
                "heading": _first_nonempty_line(chunk_lines),
                "start_line": a,
                "end_line": b,
            }
        )
    return segs


def _first_nonempty_line(lines: list[str]) -> str:
    for ln in lines:
        s = ln.strip()
        # strip markdown bold/italic markers
        s = re.sub(r"^[\*_]+|[\*_]+$", "", s).strip()
        if s and len(s) < 250:
            return s
    return ""


# ---------------------------------------------------------------------------
# Per-candidate feature extraction
# ---------------------------------------------------------------------------
def extract_one_line(raw_text: str, heading: str) -> str:
    """First non-empty paragraph (<= ~250 chars), prefer heading if substantive."""
    if heading and len(heading) >= 15 and len(heading) <= 200:
        return heading.strip()
    for para in re.split(r"\n\s*\n", raw_text):
        s = para.strip()
        s = re.sub(r"\s+", " ", s)
        if len(s) >= 30:
            return s[:240]
    return heading[:240] if heading else raw_text[:240]


def extract_key_people(raw_text: str) -> list[str]:
    found = []
    lower = raw_text.lower()
    for pid, terms in KNOWN_PEOPLE.items():
        for t in terms:
            if t.lower() in lower:
                found.append(pid)
                break
    return sorted(set(found))


def extract_locations(raw_text: str) -> list[str]:
    found = []
    lower = raw_text.lower()
    for loc, terms in KNOWN_LOCATIONS.items():
        for t in terms:
            if t.lower() in lower:
                found.append(loc)
                break
    return sorted(set(found))


# fingerprint = distinctive medium-length sentence containing rare proper nouns or quoted phrases
def extract_fingerprint_phrases(raw_text: str, max_n: int = 5) -> list[str]:
    """Pick 3-5 distinctive sentences/phrases as a content-fingerprint."""
    # Strip leading whitespace, asterisks, line-break markdown.
    cleaned = re.sub(r"[*_>]", "", raw_text)
    # Split sentences on Devanagari/Latin sentence terminators.
    sentences = re.split(r"(?<=[.!?।])\s+|\n+", cleaned)

    scored: list[tuple[int, str]] = []
    for s in sentences:
        s = s.strip()
        if not (40 <= len(s) <= 180):
            continue
        score = 0
        # contains a Marathi proper-noun-like term
        if re.search(r"[A-Z][a-zA-Z]{3,}", s):
            score += 1
        # contains quotes
        if '"' in s or "'" in s or "“" in s or "”" in s or "‘" in s or "’" in s:
            score += 1
        # contains a Devanagari proper noun-ish run (>=4 char Devanagari word followed by non-blank)
        if re.search(r"[ऀ-ॿ]{4,}", s):
            score += 1
        # rare characters / English-Latin word
        if re.search(r"[A-Za-z]{4,}", s):
            score += 1
        scored.append((score, s))

    # Diversify: prefer high-score, then earliest occurrences.
    scored.sort(key=lambda x: -x[0])
    picked: list[str] = []
    seen_prefix: set[str] = set()
    for _, s in scored:
        pref = s[:30]
        if pref in seen_prefix:
            continue
        seen_prefix.add(pref)
        picked.append(s)
        if len(picked) >= max_n:
            break
    return picked


# ---------------------------------------------------------------------------
# Matching algorithm (Deliverable 3)
# ---------------------------------------------------------------------------
def find_match(candidate: dict, story_index: dict) -> tuple[list[str], str, dict]:
    """
    Returns (matched_story_ids, bucket, score_details).
    Bucket is 'HIGH' | 'MEDIUM' | 'LOW'.
    If multiple stories tie at MEDIUM, they are all surfaced.
    Empty list with bucket LOW means no match -> new story.
    """
    scores: list[tuple[str, int, dict]] = []
    cand_about = candidate.get("about_member")
    cand_people = set(candidate.get("key_people", []))
    cand_locs = set(candidate.get("locations", []))
    cand_text = candidate.get("raw_text", "")

    for sid, sentry in (story_index.get("stories") or {}).items():
        details: dict = {}
        score = 0
        # about-member match: 2 pts
        about_match = (
            cand_about
            and sentry.get("about_member")
            and cand_about == sentry["about_member"]
        )
        details["about_match"] = bool(about_match)
        if about_match:
            score += 2
        # key_people overlap >= 2: 1 pt
        people_overlap = cand_people & set(sentry.get("key_people", []) or [])
        details["people_overlap"] = sorted(people_overlap)
        if len(people_overlap) >= 2:
            score += 1
        # location overlap >= 1: 1 pt
        loc_overlap = cand_locs & set(sentry.get("locations", []) or [])
        details["location_overlap"] = sorted(loc_overlap)
        if len(loc_overlap) >= 1:
            score += 1
        # fingerprint phrase substring hit count >= 2 in candidate text: 1 pt
        hits = 0
        hit_phrases: list[str] = []
        for phrase in sentry.get("fingerprint_phrases", []) or []:
            if phrase and phrase in cand_text:
                hits += 1
                hit_phrases.append(phrase)
        details["fingerprint_hits"] = hits
        details["fingerprint_hit_phrases"] = hit_phrases
        if hits >= 2:
            score += 1
        details["score"] = score
        scores.append((sid, score, details))

    if not scores:
        return ([], "LOW", {})

    # Pick the best score.
    max_score = max(s for _, s, _ in scores)
    tops = [(sid, sc, det) for sid, sc, det in scores if sc == max_score]

    # TUNED 2026-06-13: HIGH classification now requires the best match to have
    # at least 1 fingerprint phrase hit. Reason: the about_member signal gives
    # 2 free points to any candidate about the same lineage member, and a
    # candidate easily reaches score=4 from about+people+location even when
    # its content is entirely unrelated to the matched story. Requiring a
    # fingerprint hit ensures real textual overlap, not just metadata coincidence.
    if max_score >= 4:
        # Find best by people overlap among tops first (consistent tiebreak).
        if len(tops) > 1:
            tops.sort(
                key=lambda t: (-len(t[2].get("people_overlap", [])), t[0])
            )
        best_sid, _, best_det = tops[0]
        if best_det.get("fingerprint_hits", 0) >= 1:
            return ([best_sid], "HIGH", best_det)
        # No textual overlap — demote to MEDIUM regardless of metadata score.
        # Surface all tied tops so the reviewer sees the candidates.
        return ([sid for sid, _, _ in tops], "MEDIUM", {sid: det for sid, _, det in tops})
    if max_score >= 2:
        return ([sid for sid, _, _ in tops], "MEDIUM", {sid: det for sid, _, det in tops})
    return ([], "LOW", {})


# ---------------------------------------------------------------------------
# Slug & helpers
# ---------------------------------------------------------------------------
def slugify(text: str, max_words: int = 8) -> str:
    """Make a kebab-case English-ish slug from text. Falls back to transliteration-free."""
    if not text:
        return "untitled-story"
    # Strip markdown / punctuation, take English-letter words preferentially.
    en = re.findall(r"[A-Za-z][A-Za-z0-9]+", text)
    if len(en) >= 3:
        words = [w.lower() for w in en[:max_words]]
        return "-".join(words)[:80] or "untitled-story"
    # Otherwise use a sanitized Devanagari (only filename safety). Devanagari folder
    # names are allowed but per RFC-002 §8 we prefer English. For unknown Devanagari
    # headings we use a hash-ish fallback derived from the candidate ordinal.
    # Strip punctuation, keep Devanagari letters + spaces.
    safe = re.sub(r"[^ऀ-ॿa-zA-Z0-9 \-]", "", text)
    safe = safe.strip().replace(" ", "-").lower()
    safe = re.sub(r"-+", "-", safe).strip("-")
    return (safe[:60] or "untitled-story")


def now_iso() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def write_variant_file(
    *,
    story_dir: Path,
    candidate: dict,
    source_work_id: str,
    raw_source_rel: str,
    received_in_batch: str,
    variant_basename: str,
) -> Path:
    """Write a variant markdown file with YAML frontmatter."""
    mr_variants = story_dir / "mr" / "variants"
    mr_variants.mkdir(parents=True, exist_ok=True)
    out_path = mr_variants / f"{variant_basename}.md"

    frontmatter = {
        "story_id": story_dir.name,
        "about_member": candidate.get("about_member"),
        "language": "mr",
        "source_work": source_work_id,
        "narrator": candidate.get("narrator") or "unknown",
        "compiler": candidate.get("compiler") or "unknown",
        "extracted_from": raw_source_rel,
        "extracted_via": "pandoc markdown_strict",
        "received_in_batch": received_in_batch,
        "segment_heading": candidate.get("heading", ""),
        "segment_lines": f"{candidate.get('start_line')}-{candidate.get('end_line')}",
    }
    fm_yaml = yaml.safe_dump(
        frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    body = candidate.get("raw_text", "").strip() + "\n"
    out_path.write_text(f"---\n{fm_yaml}---\n\n{body}", encoding="utf-8")
    return out_path


def write_or_update_meta(
    *,
    story_dir: Path,
    canonical_title: str,
    title_en: str,
    about_member: str,
    one_line: str,
    locations: list[str],
    key_people: list[str],
    new_variant_entry: dict,
) -> None:
    """Create or extend a story meta.yaml."""
    meta_path = story_dir / "meta.yaml"
    meta = yaml_load(meta_path)
    if not meta:
        meta = {
            "id": story_dir.name,
            "title": canonical_title,
            "title_translit": "",
            "title_en": title_en,
            "about_member": about_member,
            "languages_available": ["mr"],
            "themes": [],
            "people_involved": key_people,
            "subject_focus": one_line,
            "estimated_date_range": "",
            "location": (locations[0] if locations else ""),
            "variants": [],
            "consolidated": {
                "status": "single_variant",
                "notes": "Auto-ingested; consolidation deferred.",
            },
            "notes": "Auto-created by tools/ingest_athvani.py.",
        }
    # Append variant (idempotent on file path).
    existing_files = {v.get("file") for v in (meta.get("variants") or [])}
    if new_variant_entry["file"] not in existing_files:
        meta.setdefault("variants", []).append(new_variant_entry)
    # Refresh people_involved with the union.
    union_people = sorted(set((meta.get("people_involved") or []) + key_people))
    meta["people_involved"] = union_people
    # Multi-variant status.
    if len(meta.get("variants", [])) >= 2:
        meta.setdefault("consolidated", {})["status"] = "partial"
    yaml_dump(meta_path, meta)


def update_story_index(
    story_index: dict,
    sid: str,
    *,
    canonical_title: str,
    title_en: str,
    about_member: str,
    one_line: str,
    key_people: list[str],
    locations: list[str],
    fingerprint_phrases: list[str],
    variant_rel_path: str,
) -> None:
    """Append a variant to an index entry.

    Rule: once an index entry is seeded, its key_people / locations /
    fingerprint_phrases are NOT mutated by future variants. Mutating them
    would let candidate evidence leak into the matching signal and bias
    subsequent matches. Only variant_count / variant_files grow.
    """
    story_index.setdefault("stories", {})
    entry = story_index["stories"].get(sid)
    seeding = entry is None
    if seeding:
        entry = {
            "canonical_title": canonical_title,
            "title_en": title_en,
            "about_member": about_member,
            "one_line": one_line,
            "key_people": list(key_people),
            "locations": list(locations),
            "period": "",
            "fingerprint_phrases": list(fingerprint_phrases),
            "variant_count": 0,
            "variant_files": [],
        }
        story_index["stories"][sid] = entry
    if variant_rel_path not in entry["variant_files"]:
        entry["variant_files"].append(variant_rel_path)
        entry["variant_count"] = len(entry["variant_files"])
    story_index["last_updated"] = now_iso()


def append_review_queue(entry: dict) -> None:
    rq = yaml_load(REVIEW_QUEUE_PATH)
    rq.setdefault("version", 1)
    rq["last_updated"] = now_iso()
    rq.setdefault("items", []).append(entry)
    yaml_dump(REVIEW_QUEUE_PATH, rq)


# ---------------------------------------------------------------------------
# Cross-MEDIUM duplicate detection (TUNED 2026-06-13)
# ---------------------------------------------------------------------------
def find_cross_match(candidate: dict, review_queue: dict) -> list[dict]:
    """Find review-queue items that look like duplicates of this candidate.

    The original matcher only matched candidates against story_index entries.
    When two files have near-identical content (common case for athvani
    compilations re-pasted across collections), neither candidate matches a
    seeded story, so both go to LOW or MEDIUM independently — and the
    duplication is lost.

    This pass compares the candidate against already-queued items in two ways:
      (a) **exact fingerprint phrase overlap** — strong signal that the
          candidates are about the same incident
      (b) **one_line Jaccard similarity >= 0.5** — weaker signal but catches
          near-duplicate compilations even when fingerprint extraction varied

    Returns list of {queue_index, queue_item, reason} for human review.
    """
    cand_fps = set(candidate.get("fingerprint_phrases", []) or [])
    cand_one_line = (candidate.get("one_line", "") or "").lower()
    cand_words = set(re.findall(r"[ऀ-ॿA-Za-z0-9]+", cand_one_line))

    matches: list[dict] = []
    for idx, item in enumerate(review_queue.get("items", []) or [], start=1):
        # Only consider items from same about_member to keep scope sane
        if item.get("about_member") != candidate.get("about_member"):
            continue
        # (a) exact fingerprint overlap
        item_fps = set(item.get("fingerprint_phrases", []) or [])
        shared = cand_fps & item_fps
        if shared:
            matches.append(
                {"queue_index": idx, "reason": "fingerprint_overlap", "shared": sorted(shared)[:3]}
            )
            continue
        # (b) one_line Jaccard
        item_ol = (item.get("one_line", "") or "").lower()
        item_words = set(re.findall(r"[ऀ-ॿA-Za-z0-9]+", item_ol))
        if cand_words and item_words:
            jacc = len(cand_words & item_words) / max(len(cand_words | item_words), 1)
            if jacc >= 0.5:
                matches.append(
                    {"queue_index": idx, "reason": "one_line_jaccard", "jaccard": round(jacc, 2)}
                )
    return matches


# ---------------------------------------------------------------------------
# Main per-file pipeline
# ---------------------------------------------------------------------------
def process_file(
    src: Path, about_member: str, batch_id: str
) -> list[dict]:
    md_text = docx_to_markdown(src)
    segments = segment_into_candidates(md_text)
    raw_rel = str(src.resolve().relative_to(REPO_ROOT))
    source_work_id = src.stem
    # Try to derive a usable filename token: prefer ASCII chars in the stem;
    # otherwise transliterate-by-substitution; otherwise fall back to a stable
    # hash of the source path so different sources never collide.
    ascii_token = re.sub(r"[^A-Za-z0-9]+", "_", source_work_id).strip("_")
    if ascii_token:
        source_basename = ascii_token[:40]
    else:
        import hashlib
        h = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:8]
        source_basename = f"src-{h}"

    summary: list[dict] = []

    for idx, seg in enumerate(segments, start=1):
        candidate = {
            "about_member": about_member,
            "raw_text": seg["raw_text"],
            "heading": seg["heading"],
            "start_line": seg["start_line"],
            "end_line": seg["end_line"],
            "key_people": extract_key_people(seg["raw_text"]),
            "locations": extract_locations(seg["raw_text"]),
            "fingerprint_phrases": extract_fingerprint_phrases(seg["raw_text"]),
            "one_line": extract_one_line(seg["raw_text"], seg["heading"]),
        }

        story_index = yaml_load(STORY_INDEX_PATH)
        matched_ids, bucket, score_details = find_match(candidate, story_index)

        result: dict[str, Any] = {
            "candidate_index": idx,
            "heading": seg["heading"],
            "bucket": bucket,
            "matched_ids": matched_ids,
            "score_details": score_details,
            "key_people": candidate["key_people"],
            "locations": candidate["locations"],
        }

        if bucket == "HIGH" and matched_ids:
            sid = matched_ids[0]
            story_dir = ATHVANI_ROOT / f"about_{about_member}" / "stories" / sid
            variant_basename = f"{source_basename}_seg{idx:02d}"
            variant_path = write_variant_file(
                story_dir=story_dir,
                candidate=candidate,
                source_work_id=source_work_id,
                raw_source_rel=raw_rel,
                received_in_batch=batch_id,
                variant_basename=variant_basename,
            )
            variant_rel = str(variant_path.resolve().relative_to(REPO_ROOT))
            variant_entry = {
                "source_work_id": source_work_id,
                "source_work_title": source_work_id,
                "narrator": "unknown",
                "language": "mr",
                "file": str(variant_path.relative_to(story_dir)),
                "page_or_section": f"segment {idx}",
                "raw_source": raw_rel,
                "received_in_batch": batch_id,
                "distinctive_details": candidate["one_line"],
            }
            existing_entry = story_index["stories"][sid]
            write_or_update_meta(
                story_dir=story_dir,
                canonical_title=existing_entry.get("canonical_title", sid),
                title_en=existing_entry.get("title_en", sid),
                about_member=about_member,
                one_line=existing_entry.get("one_line", candidate["one_line"]),
                locations=existing_entry.get("locations", candidate["locations"]),
                key_people=candidate["key_people"],
                new_variant_entry=variant_entry,
            )
            update_story_index(
                story_index,
                sid,
                canonical_title=existing_entry.get("canonical_title", sid),
                title_en=existing_entry.get("title_en", sid),
                about_member=about_member,
                one_line=existing_entry.get("one_line", candidate["one_line"]),
                key_people=candidate["key_people"],
                locations=candidate["locations"],
                fingerprint_phrases=existing_entry.get("fingerprint_phrases", candidate["fingerprint_phrases"]),
                variant_rel_path=variant_rel,
            )
            yaml_dump(STORY_INDEX_PATH, story_index)
            result["action"] = "merged_as_variant"
            result["variant_file"] = variant_rel
            result["story_id"] = sid

        elif bucket == "MEDIUM":
            # Cross-MEDIUM pass: surface other queue items that look like the
            # same incident. The reviewer can resolve a cluster in one decision.
            review_queue = yaml_load(REVIEW_QUEUE_PATH)
            cross = find_cross_match(candidate, review_queue)
            append_review_queue(
                {
                    "source_file": raw_rel,
                    "candidate_index": idx,
                    "heading": seg["heading"],
                    "about_member": about_member,
                    "matched_story_ids": matched_ids,
                    "score_details": score_details,
                    "one_line": candidate["one_line"],
                    "key_people": candidate["key_people"],
                    "locations": candidate["locations"],
                    "fingerprint_phrases": candidate["fingerprint_phrases"],
                    "raw_excerpt": candidate["raw_text"][:600],
                    "queued_on": now_iso(),
                    "similar_queue_items": cross,
                }
            )
            result["action"] = "queued_for_review"
            result["cross_matches"] = cross

        else:  # LOW
            # Before creating a new story, check whether this candidate looks
            # like a duplicate of something already in the review queue. If so,
            # demote to MEDIUM (creating new stories blindly creates duplicates
            # that humans then have to merge — better to surface to review).
            review_queue = yaml_load(REVIEW_QUEUE_PATH)
            cross = find_cross_match(candidate, review_queue)
            if cross:
                append_review_queue(
                    {
                        "source_file": raw_rel,
                        "candidate_index": idx,
                        "heading": seg["heading"],
                        "about_member": about_member,
                        "matched_story_ids": [],
                        "score_details": {"note": "demoted from LOW by cross-MEDIUM"},
                        "one_line": candidate["one_line"],
                        "key_people": candidate["key_people"],
                        "locations": candidate["locations"],
                        "fingerprint_phrases": candidate["fingerprint_phrases"],
                        "raw_excerpt": candidate["raw_text"][:600],
                        "queued_on": now_iso(),
                        "similar_queue_items": cross,
                    }
                )
                result["action"] = "queued_for_review_via_cross_match"
                result["cross_matches"] = cross
                summary.append(result)
                continue

        if bucket == "LOW" and not result.get("action"):  # LOW → new story (no cross-match found)
            new_sid = _new_story_slug(seg["heading"], candidate, src, idx)
            # Avoid clobbering an existing story slug.
            stories_map = story_index.get("stories", {})
            base = new_sid
            n = 2
            while new_sid in stories_map:
                new_sid = f"{base}-{n}"
                n += 1
            story_dir = ATHVANI_ROOT / f"about_{about_member}" / "stories" / new_sid
            variant_basename = f"{source_basename}_seg{idx:02d}"
            variant_path = write_variant_file(
                story_dir=story_dir,
                candidate=candidate,
                source_work_id=source_work_id,
                raw_source_rel=raw_rel,
                received_in_batch=batch_id,
                variant_basename=variant_basename,
            )
            variant_rel = str(variant_path.resolve().relative_to(REPO_ROOT))
            variant_entry = {
                "source_work_id": source_work_id,
                "source_work_title": source_work_id,
                "narrator": "unknown",
                "language": "mr",
                "file": str(variant_path.relative_to(story_dir)),
                "page_or_section": f"segment {idx}",
                "raw_source": raw_rel,
                "received_in_batch": batch_id,
                "distinctive_details": candidate["one_line"],
            }
            write_or_update_meta(
                story_dir=story_dir,
                canonical_title=seg["heading"] or new_sid,
                title_en=new_sid.replace("-", " ").title(),
                about_member=about_member,
                one_line=candidate["one_line"],
                locations=candidate["locations"],
                key_people=candidate["key_people"],
                new_variant_entry=variant_entry,
            )
            update_story_index(
                story_index,
                new_sid,
                canonical_title=seg["heading"] or new_sid,
                title_en=new_sid.replace("-", " ").title(),
                about_member=about_member,
                one_line=candidate["one_line"],
                key_people=candidate["key_people"],
                locations=candidate["locations"],
                fingerprint_phrases=candidate["fingerprint_phrases"],
                variant_rel_path=variant_rel,
            )
            yaml_dump(STORY_INDEX_PATH, story_index)
            result["action"] = "created_new_story"
            result["story_id"] = new_sid
            result["variant_file"] = variant_rel

        summary.append(result)

    return summary


def _new_story_slug(heading: str, candidate: dict, src: Path, idx: int) -> str:
    # Prefer slugify(heading). Fall back to src-stem + idx.
    s = slugify(heading)
    if s and s != "untitled-story":
        return s
    base = re.sub(r"[^A-Za-z0-9]+", "-", src.stem).strip("-").lower() or "story"
    return f"{base}-seg{idx:02d}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest an athvani .docx into the corpus."
    )
    parser.add_argument("source", help="Path to .docx file")
    parser.add_argument(
        "--about",
        default="gurudev_ranade",
        choices=sorted(LINEAGE_MEMBERS),
        help="Which lineage member this athvani is about.",
    )
    parser.add_argument(
        "--batch",
        default="drive_dump_2026-06-11",
        help="Receive-batch identifier (matches raw folder name).",
    )
    args = parser.parse_args(argv)

    src = Path(args.source).expanduser().resolve()
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2

    print(f"\n== Ingesting {src.name}")
    print(f"   about_member: {args.about}")
    print(f"   batch:        {args.batch}")

    results = process_file(src, args.about, args.batch)

    print(f"\n  Segmented into {len(results)} candidate(s):")
    for r in results:
        head = (r.get("heading") or "")[:60].replace("\n", " ")
        action = r.get("action", "?")
        bucket = r.get("bucket")
        story_id = r.get("story_id") or (
            r.get("matched_ids", [""])[0] if r.get("matched_ids") else ""
        )
        print(
            f"    [{r['candidate_index']:02d}] {bucket:<6} {action:<20} "
            f"story={story_id!r} head={head!r}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
