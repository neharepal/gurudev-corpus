#!/usr/bin/env python3
"""
Build a self-contained HTML corpus browser for authenticity testing.

Usage:
    python3 tools/build_corpus_browser.py

Output: tools/corpus_browser.html

The browser surfaces, for every canonical work and athvani story:
  1. The meta.yaml (what we CLAIM the content is)
  2. The extracted markdown (what the chat will quote)
  3. A direct path back to the raw source file (for spot-check)

Read-only inspection tool. Re-run anytime the corpus changes.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tools" / "corpus_browser.html"


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------
def safe_yaml_load(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return {"_load_error": str(e)}


def first_n_chars(path: Path, n: int = 1200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    # Skip YAML frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4 :]
    return text.strip()[:n]


def word_count(path: Path) -> int:
    try:
        return len(re.findall(r"\S+", path.read_text(encoding="utf-8", errors="replace")))
    except Exception:
        return 0


def scan_canonical() -> list[dict]:
    """Enumerate all canonical works."""
    results = []
    root = REPO / "01_canonical"
    if not root.exists():
        return results

    for author_dir in sorted(root.iterdir()):
        if not author_dir.is_dir():
            continue
        author = author_dir.name
        for type_dir in sorted(author_dir.iterdir()):
            if not type_dir.is_dir():
                continue
            work_type = type_dir.name  # books | lectures | letters
            for work_dir in sorted(type_dir.iterdir()):
                if not work_dir.is_dir():
                    continue
                meta_path = work_dir / "meta.yaml"
                meta = safe_yaml_load(meta_path) if meta_path.exists() else {}

                languages: list[dict] = []
                for lang_dir in sorted(work_dir.iterdir()):
                    if not lang_dir.is_dir():
                        continue
                    if lang_dir.name in {"chapters", "drafts"}:
                        continue
                    text_md = lang_dir / "text.md"
                    sources = [
                        p.name
                        for p in lang_dir.iterdir()
                        if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".txt"}
                    ]
                    languages.append(
                        {
                            "lang": lang_dir.name,
                            "source_files": sources,
                            "source_dir": str(lang_dir.relative_to(REPO)),
                            "has_text_md": text_md.exists(),
                            "text_md_path": (
                                str(text_md.relative_to(REPO)) if text_md.exists() else None
                            ),
                            "text_preview": first_n_chars(text_md) if text_md.exists() else "",
                            "word_count": word_count(text_md) if text_md.exists() else 0,
                        }
                    )

                results.append(
                    {
                        "kind": "canonical",
                        "author": author,
                        "work_type": work_type,
                        "work_slug": work_dir.name,
                        "path": str(work_dir.relative_to(REPO)),
                        "meta_path": str(meta_path.relative_to(REPO))
                        if meta_path.exists()
                        else None,
                        "meta": meta,
                        "languages": languages,
                    }
                )
    return results


def scan_athvani() -> list[dict]:
    """Enumerate all athvani stories."""
    results = []
    root = REPO / "02_aggregated" / "athvani"
    if not root.exists():
        return results

    for about_dir in sorted(root.iterdir()):
        if not about_dir.is_dir() or not about_dir.name.startswith("about_"):
            continue
        member = about_dir.name[len("about_") :]
        stories_dir = about_dir / "stories"
        if not stories_dir.exists():
            continue
        for story_dir in sorted(stories_dir.iterdir()):
            if not story_dir.is_dir():
                continue
            meta_path = story_dir / "meta.yaml"
            meta = safe_yaml_load(meta_path) if meta_path.exists() else {}

            variants_data: list[dict] = []
            consolidated_data: dict | None = None
            for lang_dir in sorted(story_dir.iterdir()):
                if not lang_dir.is_dir():
                    continue
                lang = lang_dir.name
                cons_path = lang_dir / "consolidated.md"
                if cons_path.exists():
                    consolidated_data = {
                        "lang": lang,
                        "path": str(cons_path.relative_to(REPO)),
                        "preview": first_n_chars(cons_path),
                        "word_count": word_count(cons_path),
                    }
                variants_subdir = lang_dir / "variants"
                if variants_subdir.exists():
                    for vfile in sorted(variants_subdir.iterdir()):
                        if vfile.is_file() and vfile.suffix == ".md":
                            variants_data.append(
                                {
                                    "lang": lang,
                                    "file": vfile.name,
                                    "path": str(vfile.relative_to(REPO)),
                                    "preview": first_n_chars(vfile),
                                    "word_count": word_count(vfile),
                                    "frontmatter": _extract_frontmatter(vfile),
                                }
                            )

            results.append(
                {
                    "kind": "athvani",
                    "about_member": member,
                    "story_slug": story_dir.name,
                    "path": str(story_dir.relative_to(REPO)),
                    "meta_path": str(meta_path.relative_to(REPO))
                    if meta_path.exists()
                    else None,
                    "meta": meta,
                    "consolidated": consolidated_data,
                    "variants": variants_data,
                    "variant_count": len(variants_data),
                }
            )
    return results


def scan_biography() -> list[dict]:
    results = []
    root = REPO / "02_aggregated" / "biography"
    if not root.exists():
        return results
    for about_dir in sorted(root.iterdir()):
        if not about_dir.is_dir() or not about_dir.name.startswith("about_"):
            continue
        member = about_dir.name[len("about_") :]
        for work_dir in sorted(about_dir.iterdir()):
            if not work_dir.is_dir():
                continue
            meta_path = work_dir / "meta.yaml"
            meta = safe_yaml_load(meta_path) if meta_path.exists() else {}
            languages: list[dict] = []
            for lang_dir in sorted(work_dir.iterdir()):
                if not lang_dir.is_dir():
                    continue
                text_md = lang_dir / "text.md"
                sources = [
                    p.name
                    for p in lang_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".txt"}
                ]
                languages.append(
                    {
                        "lang": lang_dir.name,
                        "source_files": sources,
                        "source_dir": str(lang_dir.relative_to(REPO)),
                        "has_text_md": text_md.exists(),
                        "text_md_path": str(text_md.relative_to(REPO))
                        if text_md.exists()
                        else None,
                        "text_preview": first_n_chars(text_md) if text_md.exists() else "",
                        "word_count": word_count(text_md) if text_md.exists() else 0,
                    }
                )
            results.append(
                {
                    "kind": "biography",
                    "about_member": member,
                    "work_slug": work_dir.name,
                    "path": str(work_dir.relative_to(REPO)),
                    "meta_path": str(meta_path.relative_to(REPO))
                    if meta_path.exists()
                    else None,
                    "meta": meta,
                    "languages": languages,
                }
            )
    return results


def scan_review_queue() -> dict:
    rq_path = REPO / "03_catalog" / "review_queue.yaml"
    if not rq_path.exists():
        return {"items": []}
    rq = safe_yaml_load(rq_path)
    return rq


def scan_story_index() -> dict:
    si_path = REPO / "03_catalog" / "story_index.yaml"
    if not si_path.exists():
        return {"stories": {}}
    return safe_yaml_load(si_path)


def _extract_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Compute statistics
# ---------------------------------------------------------------------------
def compute_stats(canonical: list[dict], athvani: list[dict], biography: list[dict]) -> dict:
    stats: dict = {}

    # Canonical stats
    by_author: Counter = Counter()
    canon_with_text: int = 0
    canon_without_text: int = 0
    total_canon_words = 0
    canon_languages: Counter = Counter()
    for w in canonical:
        by_author[w["author"]] += 1
        for lang in w["languages"]:
            canon_languages[lang["lang"]] += 1
            if lang["has_text_md"]:
                canon_with_text += 1
                total_canon_words += lang["word_count"]
            else:
                canon_without_text += 1
    stats["canonical"] = {
        "total_works": len(canonical),
        "by_author": dict(by_author),
        "works_with_text_md": canon_with_text,
        "works_without_text_md": canon_without_text,
        "total_words": total_canon_words,
        "by_language": dict(canon_languages),
    }

    # Athvani stats
    by_member: Counter = Counter()
    total_variants = 0
    multi_variant_stories = 0
    consolidated_stories = 0
    total_athvani_words = 0
    for s in athvani:
        by_member[s["about_member"]] += 1
        total_variants += s["variant_count"]
        if s["variant_count"] >= 2:
            multi_variant_stories += 1
        if s.get("consolidated"):
            consolidated_stories += 1
            total_athvani_words += s["consolidated"]["word_count"]
        for v in s["variants"]:
            total_athvani_words += v["word_count"]
    stats["athvani"] = {
        "total_stories": len(athvani),
        "by_member": dict(by_member),
        "total_variants": total_variants,
        "multi_variant_stories": multi_variant_stories,
        "consolidated_stories": consolidated_stories,
        "total_words": total_athvani_words,
    }

    # Biography stats
    bio_by_member: Counter = Counter()
    bio_with_text = 0
    bio_without_text = 0
    bio_words = 0
    for b in biography:
        bio_by_member[b["about_member"]] += 1
        for lang in b["languages"]:
            if lang["has_text_md"]:
                bio_with_text += 1
                bio_words += lang["word_count"]
            else:
                bio_without_text += 1
    stats["biography"] = {
        "total_works": len(biography),
        "by_member": dict(bio_by_member),
        "works_with_text_md": bio_with_text,
        "works_without_text_md": bio_without_text,
        "total_words": bio_words,
    }

    stats["total_words_extracted"] = total_canon_words + total_athvani_words + bio_words

    return stats


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Corpus Browser — Gurudev Sangrah</title>
<style>
  :root {
    --bg-page:        #F8F2E4;
    --bg-surface:     #FCF8EC;
    --bg-panel:       #F4ECD8;
    --text-primary:   #2D2924;
    --text-secondary: #6E665B;
    --text-tertiary:  #8E8472;
    --accent-maroon:  #7A2E2A;
    --accent-gold:    #A88556;
    --border-soft:    #D8CDB5;
    --border-stronger:#B8AB8A;
    --warning:        #B85A00;
    --success:        #4F7A4A;

    --font-serif:    'Lora','Charter','Georgia','Noto Serif Devanagari',serif;
    --font-mono:     'Iosevka Slab','IBM Plex Mono','Courier New',monospace;
  }
  * { box-sizing: border-box; }
  html,body { margin: 0; padding: 0; }
  body {
    font-family: var(--font-serif);
    background: var(--bg-page);
    color: var(--text-primary);
    line-height: 1.55;
    font-size: 16px;
  }

  /* Sticky header */
  header.top {
    position: sticky;
    top: 0;
    z-index: 20;
    background: var(--bg-page);
    border-bottom: 1px solid var(--border-soft);
    padding: 16px 28px;
    backdrop-filter: blur(4px);
  }
  header.top h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  header.top .subtitle {
    color: var(--text-secondary);
    font-size: 14px;
    margin-top: 4px;
  }
  header.top .built-at {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: 6px;
  }

  /* Tabs */
  nav.tabs {
    position: sticky;
    top: 78px;
    z-index: 19;
    background: var(--bg-page);
    border-bottom: 1px solid var(--border-soft);
    padding: 10px 28px;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  nav.tabs button {
    background: transparent;
    border: 1px solid var(--border-soft);
    color: var(--text-secondary);
    font-family: var(--font-serif);
    font-size: 14px;
    padding: 6px 14px;
    border-radius: 999px;
    cursor: pointer;
    transition: all 200ms ease;
  }
  nav.tabs button:hover {
    color: var(--text-primary);
    border-color: var(--border-stronger);
  }
  nav.tabs button.active {
    background: var(--accent-maroon);
    color: var(--bg-surface);
    border-color: var(--accent-maroon);
  }
  nav.tabs .count {
    font-family: var(--font-mono);
    font-size: 12px;
    margin-left: 4px;
    opacity: 0.7;
  }

  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 28px 80px;
  }

  /* Stats panel */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-soft);
    border-radius: 6px;
    padding: 14px 16px;
  }
  .stat-card .label {
    font-size: 12px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .stat-card .value {
    font-size: 26px;
    color: var(--accent-maroon);
    font-weight: 600;
    margin-top: 4px;
    font-family: var(--font-mono);
  }
  .stat-card .breakdown {
    margin-top: 8px;
    font-size: 13px;
    color: var(--text-secondary);
  }
  .stat-card .breakdown div {
    display: flex;
    justify-content: space-between;
    padding: 1px 0;
  }

  /* Item cards */
  .item-list { display: flex; flex-direction: column; gap: 10px; }
  .item {
    background: var(--bg-surface);
    border: 1px solid var(--border-soft);
    border-left: 3px solid var(--border-soft);
    border-radius: 4px;
    overflow: hidden;
  }
  .item.has-text { border-left-color: var(--accent-gold); }
  .item.missing-text { border-left-color: var(--warning); }
  .item.multi-variant { border-left-color: var(--accent-maroon); }
  .item.deferred { border-left-color: var(--text-tertiary); }

  .item-summary {
    padding: 12px 16px;
    cursor: pointer;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    transition: background 200ms ease;
  }
  .item-summary:hover { background: var(--bg-panel); }
  .item.open .item-summary { background: var(--bg-panel); }
  .item-title {
    font-weight: 600;
    flex: 1;
    min-width: 0;
    word-break: break-word;
  }
  .item-tags {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .tag {
    font-family: var(--font-mono);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--bg-panel);
    color: var(--text-secondary);
    border: 1px solid var(--border-soft);
  }
  .tag.author { background: #E8DCFA; color: #4B2A6B; border-color: #C9B0F5; }
  .tag.lang { background: #DCEFE0; color: #2A5C36; border-color: #88dab1; }
  .tag.type { background: #E0E8FA; color: #2A4570; border-color: #A8C2F5; }
  .tag.warning { background: #F8E5C9; color: #7A4500; border-color: #DEB373; }
  .tag.maroon { background: #F0D9D6; color: #5A1F1B; border-color: #C98E89; }

  .item-detail {
    display: none;
    padding: 0 16px 16px;
    border-top: 1px solid var(--border-soft);
  }
  .item.open .item-detail { display: block; }
  .item-section {
    margin-top: 16px;
  }
  .item-section h4 {
    font-family: var(--font-serif);
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--accent-maroon);
    margin: 0 0 8px;
  }

  pre {
    background: #FAF3DE;
    border: 1px solid var(--border-soft);
    border-radius: 4px;
    padding: 10px 12px;
    font-family: var(--font-mono);
    font-size: 12.5px;
    color: var(--text-primary);
    margin: 0;
    overflow-x: auto;
    max-height: 320px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .preview {
    background: var(--bg-panel);
    border-left: 3px solid var(--accent-maroon);
    border-radius: 0 4px 4px 0;
    padding: 12px 16px;
    font-size: 15px;
    line-height: 1.6;
    max-height: 320px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .path {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-secondary);
    padding: 6px 10px;
    background: var(--bg-panel);
    border-radius: 4px;
    display: inline-block;
    margin: 0 6px 6px 0;
    border: 1px solid var(--border-soft);
    cursor: copy;
    transition: all 200ms ease;
  }
  .path:hover {
    background: var(--accent-gold);
    color: var(--bg-surface);
    border-color: var(--accent-gold);
  }
  .path-row { margin-bottom: 8px; }

  .lang-block {
    margin-top: 14px;
    padding: 10px;
    border: 1px solid var(--border-soft);
    border-radius: 4px;
    background: var(--bg-surface);
  }
  .lang-block .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    gap: 8px;
  }
  .lang-block .lang-name {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--accent-maroon);
  }
  .lang-block .word-count {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-secondary);
  }

  /* Review queue */
  .queue-item {
    background: var(--bg-surface);
    border: 1px solid var(--border-soft);
    border-left: 3px solid var(--accent-gold);
    border-radius: 4px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  .queue-item.has-cross { border-left-color: var(--warning); }
  .queue-item .qheader { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .queue-item .qheader .one-line {
    flex: 1;
    min-width: 0;
    word-break: break-word;
    color: var(--text-primary);
  }
  .queue-item .meta {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 8px;
  }
  .queue-item .excerpt {
    margin-top: 8px;
    padding: 8px 12px;
    background: var(--bg-panel);
    border-radius: 4px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
  }
  .queue-item .similar {
    margin-top: 8px;
    padding: 8px 12px;
    background: #F8E5C9;
    border-radius: 4px;
    font-size: 12px;
    color: #7A4500;
  }

  .empty-state {
    padding: 40px 20px;
    text-align: center;
    color: var(--text-tertiary);
    font-style: italic;
  }

  .search-row {
    margin-bottom: 16px;
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .search-row input {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid var(--border-soft);
    border-radius: 4px;
    background: var(--bg-surface);
    font-family: var(--font-serif);
    font-size: 15px;
    color: var(--text-primary);
  }
  .search-row input:focus {
    outline: none;
    border-color: var(--accent-maroon);
  }

  @media (max-width: 700px) {
    main { padding: 16px; }
    header.top, nav.tabs { padding-left: 16px; padding-right: 16px; }
    nav.tabs { top: 90px; }
  }
</style>
</head>
<body>

<header class="top">
  <h1>Corpus Browser — गुरुदेव संग्रह</h1>
  <div class="subtitle">Authenticity testing surface. Click any item to inspect meta + extracted text + source path.</div>
  <div class="built-at">Built BUILT_AT_PLACEHOLDER</div>
</header>

<nav class="tabs" id="tabs"></nav>

<main id="main"></main>

<script>
const DATA = __DATA_PLACEHOLDER__;

let activeTab = 'overview';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'canonical', label: 'Canonical works', countKey: 'canonical' },
  { id: 'athvani', label: 'Athvani stories', countKey: 'athvani' },
  { id: 'biography', label: 'Biography', countKey: 'biography' },
  { id: 'queue', label: 'Review queue', countKey: 'queue' },
];

function fmtNum(n) {
  if (!n) return '0';
  return n.toLocaleString('en-US');
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderTabs() {
  const counts = {
    canonical: DATA.canonical.length,
    athvani: DATA.athvani.length,
    biography: DATA.biography.length,
    queue: (DATA.review_queue.items || []).length,
  };
  const html = TABS.map(t => {
    const c = t.countKey ? `<span class="count">${counts[t.countKey] || 0}</span>` : '';
    return `<button class="${activeTab === t.id ? 'active' : ''}" onclick="setTab('${t.id}')">${t.label}${c}</button>`;
  }).join('');
  document.getElementById('tabs').innerHTML = html;
}

function setTab(id) {
  activeTab = id;
  renderTabs();
  renderMain();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderMain() {
  const main = document.getElementById('main');
  if (activeTab === 'overview') main.innerHTML = renderOverview();
  else if (activeTab === 'canonical') main.innerHTML = renderCanonical();
  else if (activeTab === 'athvani') main.innerHTML = renderAthvani();
  else if (activeTab === 'biography') main.innerHTML = renderBiography();
  else if (activeTab === 'queue') main.innerHTML = renderQueue();
}

function renderOverview() {
  const s = DATA.stats;
  const c = s.canonical;
  const a = s.athvani;
  const b = s.biography;
  return `
    <div class="stats-grid">
      <div class="stat-card">
        <div class="label">Canonical works</div>
        <div class="value">${fmtNum(c.total_works)}</div>
        <div class="breakdown">
          ${Object.entries(c.by_author).map(([k, v]) => `<div><span>${escapeHtml(k)}</span><span>${v}</span></div>`).join('')}
        </div>
      </div>
      <div class="stat-card">
        <div class="label">Canonical text extracted</div>
        <div class="value">${fmtNum(c.works_with_text_md)}<span style="font-size:18px; color: var(--text-tertiary);">/${c.works_with_text_md + c.works_without_text_md}</span></div>
        <div class="breakdown">
          <div><span>Total words</span><span>${fmtNum(c.total_words)}</span></div>
          <div><span>Missing text.md</span><span>${c.works_without_text_md}</span></div>
        </div>
      </div>
      <div class="stat-card">
        <div class="label">Athvani stories</div>
        <div class="value">${fmtNum(a.total_stories)}</div>
        <div class="breakdown">
          ${Object.entries(a.by_member).map(([k, v]) => `<div><span>${escapeHtml(k)}</span><span>${v}</span></div>`).join('')}
        </div>
      </div>
      <div class="stat-card">
        <div class="label">Athvani variants</div>
        <div class="value">${fmtNum(a.total_variants)}</div>
        <div class="breakdown">
          <div><span>Multi-variant stories</span><span>${a.multi_variant_stories}</span></div>
          <div><span>Consolidated</span><span>${a.consolidated_stories}</span></div>
          <div><span>Total words</span><span>${fmtNum(a.total_words)}</span></div>
        </div>
      </div>
      <div class="stat-card">
        <div class="label">Biography works</div>
        <div class="value">${fmtNum(b.total_works)}</div>
        <div class="breakdown">
          <div><span>Words</span><span>${fmtNum(b.total_words)}</span></div>
          <div><span>Missing text.md</span><span>${b.works_without_text_md}</span></div>
        </div>
      </div>
      <div class="stat-card">
        <div class="label">Review queue</div>
        <div class="value">${fmtNum((DATA.review_queue.items || []).length)}</div>
        <div class="breakdown">
          <div><span>Cross-match flagged</span><span>${(DATA.review_queue.items || []).filter(x => (x.similar_queue_items || []).length).length}</span></div>
        </div>
      </div>
      <div class="stat-card">
        <div class="label">Total words extracted</div>
        <div class="value">${fmtNum(s.total_words_extracted)}</div>
        <div class="breakdown" style="font-style: italic;">Across canonical + athvani + biography</div>
      </div>
    </div>

    <h3 style="margin-top: 28px;">How to use this browser</h3>
    <p style="color: var(--text-secondary); max-width: 720px; line-height: 1.7;">
      Each tab lists items in a category. Click any item to expand and see its meta.yaml,
      the extracted markdown preview, and the path back to the raw source file.
      <strong>To spot-check authenticity:</strong> pick an item, read the extracted text preview,
      then open the source file (path shown in the detail) and compare. They should match.
    </p>
  `;
}

function renderCanonical() {
  return `
    <div class="search-row">
      <input type="text" id="search-canon" placeholder="Filter by title, author, slug..." oninput="filterList('canon')">
    </div>
    <div class="item-list" id="canon-list">
      ${DATA.canonical.map((w, idx) => renderCanonItem(w, idx)).join('')}
    </div>
  `;
}

function renderCanonItem(w, idx) {
  const title = (w.meta && (w.meta.title_en || w.meta.title)) || w.work_slug;
  const langs = w.languages.map(l => `<span class="tag lang">${l.lang}${l.has_text_md ? '✓' : '!'}</span>`).join('');
  const hasText = w.languages.some(l => l.has_text_md);
  const classes = ['item', 'canon', hasText ? 'has-text' : 'missing-text'].join(' ');
  const sourceWordCount = w.languages.reduce((s, l) => s + (l.word_count || 0), 0);
  return `
    <div class="${classes}" data-search="${escapeHtml((title + ' ' + w.author + ' ' + w.work_slug).toLowerCase())}">
      <div class="item-summary" onclick="toggleItem(this)">
        <div class="item-title">${escapeHtml(title)}</div>
        <div class="item-tags">
          <span class="tag author">${escapeHtml(w.author)}</span>
          <span class="tag type">${escapeHtml(w.work_type)}</span>
          ${langs}
          ${sourceWordCount > 0 ? `<span class="tag">${fmtNum(sourceWordCount)} words</span>` : '<span class="tag warning">no text.md</span>'}
        </div>
      </div>
      <div class="item-detail">
        ${renderLangs(w.languages)}
        ${renderMeta(w.meta)}
        ${w.meta_path ? `<div class="path-row"><strong>meta:</strong> <span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(w.meta_path)}</span></div>` : ''}
      </div>
    </div>
  `;
}

function renderLangs(languages) {
  if (!languages || !languages.length) return '<div class="item-section"><em>No language subfolders.</em></div>';
  return languages.map(l => `
    <div class="lang-block">
      <div class="header">
        <div class="lang-name">${escapeHtml(l.lang)}</div>
        <div class="word-count">${l.has_text_md ? `${fmtNum(l.word_count)} words` : '<em style="color: var(--warning);">no text.md yet</em>'}</div>
      </div>
      <div class="path-row">
        <strong>Source files:</strong>
        ${l.source_files.map(f => `<span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(l.source_dir)}/${escapeHtml(f)}</span>`).join('') || '<em style="color: var(--text-tertiary);">none</em>'}
      </div>
      ${l.has_text_md ? `
        <div class="path-row">
          <strong>Extracted:</strong>
          <span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(l.text_md_path)}</span>
        </div>
        <div class="item-section">
          <h4>Preview (first ~1.2K chars)</h4>
          <div class="preview">${escapeHtml(l.text_preview)}</div>
        </div>
      ` : ''}
    </div>
  `).join('');
}

function renderMeta(meta) {
  if (!meta || Object.keys(meta).length === 0) {
    return '<div class="item-section"><h4>meta.yaml</h4><em>missing</em></div>';
  }
  let dump;
  try {
    dump = JSON.stringify(meta, null, 2);
  } catch {
    dump = String(meta);
  }
  return `
    <div class="item-section">
      <h4>meta.yaml (parsed)</h4>
      <pre>${escapeHtml(dump)}</pre>
    </div>
  `;
}

function renderAthvani() {
  return `
    <div class="search-row">
      <input type="text" id="search-athvani" placeholder="Filter by title, member, slug, location..." oninput="filterList('athvani')">
    </div>
    <div class="item-list" id="athvani-list">
      ${DATA.athvani.map((s, idx) => renderAthvaniItem(s, idx)).join('')}
    </div>
  `;
}

function renderAthvaniItem(s, idx) {
  const title = (s.meta && (s.meta.title_en || s.meta.title)) || s.story_slug;
  const oneLine = s.meta && s.meta.subject_focus || '';
  const isMulti = s.variant_count >= 2;
  const classes = ['item', 'athvani', isMulti ? 'multi-variant' : ''].join(' ');
  const searchable = [title, s.about_member, s.story_slug, (s.meta && s.meta.themes || []).join(' '), oneLine].join(' ').toLowerCase();
  return `
    <div class="${classes}" data-search="${escapeHtml(searchable)}">
      <div class="item-summary" onclick="toggleItem(this)">
        <div class="item-title">
          ${escapeHtml(title)}
          ${oneLine ? `<div style="color: var(--text-secondary); font-size: 13px; font-weight: 400; margin-top: 4px;">${escapeHtml(oneLine.slice(0, 120))}</div>` : ''}
        </div>
        <div class="item-tags">
          <span class="tag author">${escapeHtml(s.about_member)}</span>
          <span class="tag">${s.variant_count} variant${s.variant_count !== 1 ? 's' : ''}</span>
          ${s.consolidated ? '<span class="tag maroon">consolidated</span>' : ''}
          ${isMulti ? '<span class="tag maroon">multi-variant</span>' : ''}
        </div>
      </div>
      <div class="item-detail">
        ${renderVariants(s.variants)}
        ${s.consolidated ? renderConsolidated(s.consolidated) : ''}
        ${renderMeta(s.meta)}
        ${s.meta_path ? `<div class="path-row"><strong>meta:</strong> <span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(s.meta_path)}</span></div>` : ''}
      </div>
    </div>
  `;
}

function renderVariants(variants) {
  if (!variants.length) return '<div class="item-section"><em>No variants yet.</em></div>';
  return `
    <div class="item-section">
      <h4>Variants (${variants.length})</h4>
      ${variants.map(v => `
        <div class="lang-block">
          <div class="header">
            <div class="lang-name">${escapeHtml(v.lang)} · ${escapeHtml(v.file)}</div>
            <div class="word-count">${fmtNum(v.word_count)} words</div>
          </div>
          ${v.frontmatter && Object.keys(v.frontmatter).length ? `
            <div class="path-row">
              ${v.frontmatter.narrator ? `<span class="tag">narrator: ${escapeHtml(v.frontmatter.narrator)}</span>` : ''}
              ${v.frontmatter.source_work ? `<span class="tag">source: ${escapeHtml(v.frontmatter.source_work)}</span>` : ''}
            </div>
          ` : ''}
          ${v.frontmatter && v.frontmatter.extracted_from ? `
            <div class="path-row">
              <strong>Raw source:</strong>
              <span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(v.frontmatter.extracted_from)}</span>
            </div>
          ` : ''}
          <div class="path-row">
            <strong>Variant path:</strong>
            <span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(v.path)}</span>
          </div>
          <div class="item-section">
            <h4>Preview</h4>
            <div class="preview">${escapeHtml(v.preview)}</div>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderConsolidated(c) {
  return `
    <div class="item-section">
      <h4>Consolidated (${c.lang}) — ${fmtNum(c.word_count)} words</h4>
      <div class="path-row">
        <span class="path" onclick="copyPath(this)" title="click to copy path">${escapeHtml(c.path)}</span>
      </div>
      <div class="preview">${escapeHtml(c.preview)}</div>
    </div>
  `;
}

function renderBiography() {
  if (!DATA.biography.length) {
    return '<div class="empty-state">No biography works in the corpus yet.</div>';
  }
  return `
    <div class="search-row">
      <input type="text" id="search-bio" placeholder="Filter biography..." oninput="filterList('bio')">
    </div>
    <div class="item-list" id="bio-list">
      ${DATA.biography.map((b, idx) => renderBioItem(b, idx)).join('')}
    </div>
  `;
}

function renderBioItem(b, idx) {
  const title = (b.meta && (b.meta.title_en || b.meta.title)) || b.work_slug;
  const langs = b.languages.map(l => `<span class="tag lang">${l.lang}${l.has_text_md ? '✓' : '!'}</span>`).join('');
  const hasText = b.languages.some(l => l.has_text_md);
  const classes = ['item', 'bio', hasText ? 'has-text' : 'missing-text'].join(' ');
  const searchable = [title, b.about_member, b.work_slug].join(' ').toLowerCase();
  return `
    <div class="${classes}" data-search="${escapeHtml(searchable)}">
      <div class="item-summary" onclick="toggleItem(this)">
        <div class="item-title">${escapeHtml(title)}</div>
        <div class="item-tags">
          <span class="tag author">about: ${escapeHtml(b.about_member)}</span>
          <span class="tag type">biography</span>
          ${langs}
        </div>
      </div>
      <div class="item-detail">
        ${renderLangs(b.languages)}
        ${renderMeta(b.meta)}
      </div>
    </div>
  `;
}

function renderQueue() {
  const items = DATA.review_queue.items || [];
  if (!items.length) {
    return '<div class="empty-state">Review queue is empty.</div>';
  }
  return `
    <div class="search-row">
      <input type="text" id="search-q" placeholder="Filter queue..." oninput="filterList('q')">
    </div>
    <p style="color: var(--text-secondary); margin-bottom: 16px;">
      The matcher couldn't auto-assign these candidates with confidence. Items with a yellow left border
      have been flagged as likely duplicates of earlier queue items (cross-match worked).
    </p>
    <div class="item-list" id="q-list">
      ${items.map((q, idx) => renderQueueItem(q, idx + 1)).join('')}
    </div>
  `;
}

function renderQueueItem(q, num) {
  const hasCross = (q.similar_queue_items || []).length > 0;
  const cls = ['queue-item', hasCross ? 'has-cross' : ''].join(' ');
  const oneLine = q.one_line || q.heading || '(no heading)';
  const searchable = [q.heading, q.one_line, q.source_file, (q.key_people || []).join(' ')].join(' ').toLowerCase();
  return `
    <div class="${cls}" data-search="${escapeHtml(searchable)}">
      <div class="qheader">
        <strong>#${num}</strong>
        <div class="one-line">${escapeHtml(oneLine.slice(0, 200))}</div>
        <span class="tag author">${escapeHtml(q.about_member || '?')}</span>
      </div>
      <div class="meta">
        <div><strong>source:</strong> ${escapeHtml(q.source_file || '?')}</div>
        ${q.matched_story_ids && q.matched_story_ids.length ? `<div><strong>matched (MEDIUM):</strong> ${escapeHtml((q.matched_story_ids || []).join(', '))}</div>` : ''}
        ${q.key_people && q.key_people.length ? `<div><strong>key people:</strong> ${escapeHtml((q.key_people || []).join(', '))}</div>` : ''}
        ${q.locations && q.locations.length ? `<div><strong>locations:</strong> ${escapeHtml((q.locations || []).join(', '))}</div>` : ''}
      </div>
      ${q.raw_excerpt ? `<div class="excerpt">${escapeHtml(q.raw_excerpt)}</div>` : ''}
      ${hasCross ? `<div class="similar">
        <strong>⚐ Likely duplicate of:</strong>
        ${q.similar_queue_items.map(s => `queue #${s.queue_index} (${s.reason})`).join(', ')}
      </div>` : ''}
    </div>
  `;
}

function toggleItem(elt) {
  const item = elt.parentElement;
  item.classList.toggle('open');
}

function copyPath(elt) {
  const txt = elt.textContent.trim();
  navigator.clipboard?.writeText(txt);
  const orig = elt.textContent;
  elt.textContent = '✓ copied';
  setTimeout(() => { elt.textContent = orig; }, 1000);
}

function filterList(prefix) {
  const inputId = `search-${prefix === 'canon' ? 'canon' : prefix === 'athvani' ? 'athvani' : prefix === 'bio' ? 'bio' : 'q'}`;
  const listId = prefix === 'canon' ? 'canon-list' : prefix === 'athvani' ? 'athvani-list' : prefix === 'bio' ? 'bio-list' : 'q-list';
  const q = document.getElementById(inputId).value.toLowerCase().trim();
  const list = document.getElementById(listId);
  if (!list) return;
  Array.from(list.children).forEach(child => {
    const tag = child.dataset.search || '';
    child.style.display = (!q || tag.includes(q)) ? '' : 'none';
  });
}

renderTabs();
renderMain();
</script>

</body>
</html>
"""


def main():
    print("Scanning corpus...")
    canonical = scan_canonical()
    athvani = scan_athvani()
    biography = scan_biography()
    review_queue = scan_review_queue()
    story_index = scan_story_index()
    stats = compute_stats(canonical, athvani, biography)

    print(f"  Canonical works:  {len(canonical)}")
    print(f"  Athvani stories:  {len(athvani)}")
    print(f"  Biography works:  {len(biography)}")
    print(f"  Review queue:     {len(review_queue.get('items', []))}")

    data = {
        "canonical": canonical,
        "athvani": athvani,
        "biography": biography,
        "review_queue": review_queue,
        "story_index": story_index,
        "stats": stats,
    }

    def _default(obj):
        # YAML can load `date: 2026-06-11` as datetime.date — JSON can't.
        from datetime import date, datetime as _dt
        if isinstance(obj, (date, _dt)):
            return obj.isoformat()
        return str(obj)

    html = HTML_TEMPLATE.replace(
        "BUILT_AT_PLACEHOLDER", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ).replace(
        "__DATA_PLACEHOLDER__", json.dumps(data, ensure_ascii=False, default=_default)
    )

    OUT.write_text(html, encoding="utf-8")
    print(f"\n✓ Wrote {OUT}")
    print(f"  Size: {OUT.stat().st_size / 1024:.1f} KB")
    print(f"\nOpen with:")
    print(f"  open {OUT}")


if __name__ == "__main__":
    main()
