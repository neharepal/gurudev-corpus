# Phase 2 Small-to-Big Chunking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-chunk the corpus into parent (section) + child (sentence/verse) units so a buried sentence is retrievable, while the answer model still gets the parent for context; fold in the arthasahit verse/meaning split via a per-child `cite_text`. (RFC-017.)

**Architecture:** `tools/chunker.py` emits parent rows (`kind:"parent"`, excluded from embedding) and child rows (embedded). Each child has `parent_id`, `text` (the sentence/verse), `embed_text` (sentence + neighbor window), and `cite_text` (what a citation may quote; absent ⇒ retrieval-only). Retrieval ranks children then expands to distinct parents for the answer. Splice/Read-in-full anchor on `cite_text`/parent.

**Tech Stack:** Python 3.8, numpy, BGE-M3 (embedder), FastAPI, pytest.

## Global Constraints

- Python: `/Users/neharepal/opt/anaconda3/bin/python`. Run Devanagari-touching commands under `LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8`.
- Existing suite is green at **286**; keep it green.
- Child id scheme: `f"{work_id}--{lang}--{parent_index:04d}--{child_index:03d}"`. Parent id: `f"{work_id}--{lang}--{parent_index:04d}"` (unchanged from today's chunk id, so parents keep stable ids).
- Only children are embedded. `embedder.py` must skip rows with `kind == "parent"`.
- Chunker constants `TARGET_CHARS`, `MAX_CHARS`, `OVERLAP_CHARS` unchanged (parents = today's chunks).
- The 7 arthasahit work_ids: `tukaram-vachanamrut, eknath-vachanamrut, ramdas-vachanamrut, sant-vachanamrut, jnaneshwar-vachanamrut, eknathi-bhagvat-vachanamrut, dhyanopakarani-gita`.

---

### Task 1: Child splitter (`tools/childsplit.py`)

**Files:**
- Create: `tools/childsplit.py`
- Test: `tools/tests/test_childsplit.py`

**Interfaces:**
- Produces: `split_into_children(section_text: str, *, window: int = 1) -> list[dict]` → list of `{"text": str, "embed_text": str}`. Splits prose on sentence boundaries (reusing the chunker's `SENTENCE_END_RE` semantics) and Devanagari verse on line/`।`/`॥` boundaries. `embed_text` = the child plus ±`window` neighboring children joined by a space.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_childsplit.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from childsplit import split_into_children


def test_prose_splits_into_sentences():
    txt = "Bhakti is the soul. Namasmaran is its practice. Grace descends."
    kids = split_into_children(txt, window=0)
    assert [k["text"] for k in kids] == [
        "Bhakti is the soul.", "Namasmaran is its practice.", "Grace descends."]


def test_embed_text_includes_neighbor_window():
    txt = "One. Two. Three."
    kids = split_into_children(txt, window=1)
    # middle child's embed_text carries its neighbors for signal
    mid = [k for k in kids if k["text"] == "Two."][0]
    assert "One." in mid["embed_text"] and "Three." in mid["embed_text"]


def test_devanagari_verse_splits_on_dandas():
    verse = "गुरु गोविंद दोऊ खड़े । काके लागूं पाय ॥ बलिहारी गुरु आपने ॥"
    kids = split_into_children(verse, window=0)
    assert len(kids) >= 2
    assert any("गुरु गोविंद" in k["text"] for k in kids)


def test_single_sentence_returns_one_child():
    kids = split_into_children("Only one sentence here.", window=1)
    assert len(kids) == 1
    assert kids[0]["text"] == kids[0]["embed_text"] == "Only one sentence here."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_childsplit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'childsplit'`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/childsplit.py
"""Split a parent section into child units (sentence / verse) for small-to-big
retrieval (RFC-017). embed_text carries a neighbor window so short children still
embed with signal; text is the citable/raw unit."""
from __future__ import annotations
import re

SENTENCE_END_RE = re.compile(r"(?<=[.!?।॥])\s+")
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_VERSE_BOUNDARY_RE = re.compile(r"(?<=[।॥])\s*")


def _is_verse(text: str) -> bool:
    # Verse if Devanagari-heavy AND uses danda punctuation.
    deva = len(DEVANAGARI_RE.findall(text))
    return deva / max(len(text), 1) > 0.3 and ("।" in text or "॥" in text)


def split_into_children(section_text: str, *, window: int = 1) -> list[dict]:
    text = (section_text or "").strip()
    if not text:
        return []
    if _is_verse(text):
        parts = [p.strip() for p in _VERSE_BOUNDARY_RE.split(text) if p.strip()]
    else:
        parts = [p.strip() for p in SENTENCE_END_RE.split(text) if p.strip()]
    if not parts:
        parts = [text]
    out = []
    for i, p in enumerate(parts):
        lo = max(0, i - window)
        hi = min(len(parts), i + window + 1)
        embed = " ".join(parts[lo:hi]) if window > 0 else p
        out.append({"text": p, "embed_text": embed})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_childsplit.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/childsplit.py tools/tests/test_childsplit.py
git commit -m "chunker: child splitter (sentence/verse + embed window) for small-to-big (RFC-017)"
```

---

### Task 2: Arthasahit verse/meaning parse (`tools/arthasahit_parse.py`)

**Files:**
- Create: `tools/arthasahit_parse.py`
- Test: `tools/tests/test_arthasahit_parse.py`

**Interfaces:**
- Produces: `split_verse_meaning(entry: str) -> tuple[str, str | None]` → `(verse, meaning)`. Splits at the first strong meaning marker (`अर्थ` line, or an English gloss in parens). Returns `(verse, None)` when NO confident boundary is found — caller treats `meaning is None` as "the whole thing is verse, but mark cite_text uncertain" per Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_arthasahit_parse.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arthasahit_parse import split_verse_meaning


def test_splits_at_artha_marker():
    entry = "करीं धंदा परि आवडती पाय ॥१॥\nअर्थ - या अभंगात तुकाराम म्हणतात..."
    verse, meaning = split_verse_meaning(entry)
    assert "करीं धंदा" in verse
    assert meaning is not None and "तुकाराम म्हणतात" in meaning
    assert "अर्थ" not in verse


def test_splits_at_english_gloss():
    entry = "माझिया मीपणावरी पडो पाषाण ॥१॥\n(Cursed be my egoism.)"
    verse, meaning = split_verse_meaning(entry)
    assert "पाषाण" in verse
    assert meaning is not None and "Cursed be my egoism" in meaning


def test_no_confident_boundary_returns_none_meaning():
    entry = "गुरु गोविंद दोऊ खड़े । काके लागूं पाय ॥"
    verse, meaning = split_verse_meaning(entry)
    assert verse == entry.strip()
    assert meaning is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_arthasahit_parse.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/arthasahit_parse.py
"""Split one arthasahit entry into (verse, meaning). The verse is Gurudev's
selection (citable); the meaning is sadhak-authored (retrieval-only). Boundary
markers vary per book; return meaning=None when no confident split exists so the
caller can mark the child retrieval-only rather than mis-cite the meaning. (RFC-017.)"""
from __future__ import annotations
import re

# Strongest boundary: a line that begins the meaning with 'अर्थ' (± number/dash).
_ARTHA_RE = re.compile(r"(?m)^\s*अर्थ\b.*")
# Next: an English gloss in parentheses (the trilingual editions' translation).
_ENGLISH_GLOSS_RE = re.compile(r"\([^)]*[A-Za-z][^)]*\)")


def split_verse_meaning(entry: str) -> tuple[str, str | None]:
    e = (entry or "").strip()
    if not e:
        return "", None
    m = _ARTHA_RE.search(e)
    if m and m.start() > 0:
        return e[:m.start()].strip(), e[m.start():].strip()
    g = _ENGLISH_GLOSS_RE.search(e)
    if g and g.start() > 0:
        return e[:g.start()].strip(), e[g.start():].strip()
    return e, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_arthasahit_parse.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Refine against real data + commit**

Run against a real book to sanity-check the split rate (aim: most entries split, uncertain ones fall back cleanly):
```bash
LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -c "
import sys; sys.path.insert(0,'tools'); from arthasahit_parse import split_verse_meaning
t=open('00_raw/drive_dump_2026-07-10/_extracted/tukaram-vachanamrut.extracted.md',encoding='utf-8').read()
import re; entries=[e for e in re.split(r'\n\n', t) if e.strip()][:30]
n=sum(1 for e in entries if split_verse_meaning(e)[1] is not None)
print(f'{n}/{len(entries)} sample entries split verse|meaning')"
```
```bash
git add tools/arthasahit_parse.py tools/tests/test_arthasahit_parse.py
git commit -m "chunker: arthasahit verse/meaning parse w/ conservative fallback (RFC-017; folds in #35)"
```

---

### Task 3: Parent + child emission in the chunker

**Files:**
- Modify: `tools/chunker.py` (`emit_chunks_for_source`)
- Test: `tools/tests/test_chunker_parent_child.py`

**Interfaces:**
- Consumes: `childsplit.split_into_children` (Task 1).
- Produces: `emit_chunks_for_source` now yields, per parent section: one **parent** row `{... , "kind_level":"parent", "text": section, "id": "<wid>--<lang>--<pi:04d>"}` then N **child** rows `{... , "parent_id": <parent id>, "text": child, "embed_text": ..., "cite_text": child, "id": "<wid>--<lang>--<pi:04d>--<ci:03d>"}`. (Use `kind_level` — NOT `kind`, which is the canonical/biography tier used by chunk_tier.)

**Context to read first:** `tools/chunker.py` `emit_chunks_for_source` (~line 250) and `chunk_text`. Keep `chunk_text` as the parent producer.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_chunker_parent_child.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import chunker

def test_emits_parent_then_children():
    base = {"work_id": "demo", "language": "en", "kind": "canonical"}
    rows = list(chunker.emit_chunks_for_source(Path("x/text.md"),
        "Bhakti is the soul. Namasmaran is its practice.\n\nGrace descends fully.", base))
    parents = [r for r in rows if r.get("kind_level") == "parent"]
    children = [r for r in rows if r.get("parent_id")]
    assert parents and children
    # every child points at a real parent id
    pids = {p["id"] for p in parents}
    assert all(c["parent_id"] in pids for c in children)
    # child ids nest under parent ids
    assert all(c["id"].startswith(c["parent_id"] + "--") for c in children)
    # children carry embed_text + cite_text
    assert all("embed_text" in c and "cite_text" in c for c in children)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_chunker_parent_child.py -q`
Expected: FAIL (no `kind_level`/`parent_id` on rows yet).

- [ ] **Step 3: Rewrite `emit_chunks_for_source`**

```python
def emit_chunks_for_source(source_path, body_text, base_meta):
    """Yield one parent row per section + its child rows (RFC-017 small-to-big).

    Parents (kind_level="parent") carry the full section text and are the context
    unit; they are NOT embedded (embedder skips them). Children are the retrieval
    unit: sentence/verse, with embed_text (neighbor window) and cite_text.
    """
    import childsplit
    sections = chunk_text(body_text)
    total = len(sections)
    work_id = base_meta.get("work_id") or base_meta.get("id") or source_path.stem
    lang = base_meta.get("language", "unk")
    spath = str(source_path.relative_to(REPO))
    for pi, sec in enumerate(sections):
        pid = f"{work_id}--{lang}--{pi:04d}"
        parent = dict(base_meta)
        parent.update({
            "id": pid, "kind_level": "parent", "chunk_index": pi, "chunk_total": total,
            "char_start": sec["char_start"], "char_end": sec["char_end"],
            "text": sec["text"], "token_estimate": estimate_tokens(sec["text"]),
            "source_path": spath,
        })
        yield parent
        for ci, kid in enumerate(childsplit.split_into_children(sec["text"], window=1)):
            child = dict(base_meta)
            child.update({
                "id": f"{pid}--{ci:03d}", "kind_level": "child", "parent_id": pid,
                "chunk_index": pi, "chunk_total": total, "source_path": spath,
                "text": kid["text"], "embed_text": kid["embed_text"],
                "cite_text": kid["text"], "token_estimate": estimate_tokens(kid["text"]),
            })
            yield child
```

- [ ] **Step 4: Run test to verify it passes**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_chunker_parent_child.py tools/tests -q`
Expected: PASS. (Existing chunker tests that assumed one row per chunk may need updating to filter `kind_level=="child"`; fix them to match the new shape.)

- [ ] **Step 5: Commit**

```bash
git add tools/chunker.py tools/tests/test_chunker_parent_child.py
git commit -m "chunker: emit parent section rows + sentence/verse child rows (RFC-017)"
```

---

### Task 4: Arthasahit children use cite_text = verse only

**Files:**
- Modify: `tools/chunker.py` (`emit_chunks_for_source` child loop)
- Test: `tools/tests/test_chunker_arthasahit.py`

**Interfaces:**
- Consumes: `arthasahit_parse.split_verse_meaning` (Task 2).
- Produces: for the 7 arthasahit work_ids, each child's `embed_text` = `verse + " " + meaning` (when a meaning was split) and `cite_text` = the verse. When `split_verse_meaning` returns `meaning=None`, the child is emitted **without** a `cite_text` key (retrieval-only).

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_chunker_arthasahit.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import chunker

def test_arthasahit_child_cites_verse_embeds_meaning():
    base = {"work_id": "tukaram-vachanamrut", "language": "mr", "kind": "canonical"}
    entry = "करीं धंदा परि आवडती पाय ॥१॥\nअर्थ - तुकाराम म्हणतात हे भक्तीचे वर्णन आहे."
    rows = list(chunker.emit_chunks_for_source(Path("x/text.md"), entry, base))
    kids = [r for r in rows if r.get("kind_level") == "child"]
    assert kids
    c = kids[0]
    assert "करीं धंदा" in c["cite_text"]              # verse is citable
    assert "अर्थ" not in c["cite_text"]                # meaning excluded from citation
    assert "म्हणतात" in c["embed_text"]                 # but meaning IS embedded for recall

def test_uncertain_split_is_retrieval_only():
    base = {"work_id": "sant-vachanamrut", "language": "mr", "kind": "canonical"}
    rows = list(chunker.emit_chunks_for_source(Path("x/text.md"),
        "गुरु गोविंद दोऊ खड़े । काके लागूं पाय ॥", base))
    kids = [r for r in rows if r.get("kind_level") == "child"]
    assert kids and all("cite_text" not in c for c in kids)   # never citable
```

- [ ] **Step 2: Run test to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_chunker_arthasahit.py -q`
Expected: FAIL (arthasahit branch not implemented; cite_text always set).

- [ ] **Step 3: Add the arthasahit branch to the child loop**

At the top of `chunker.py` add the set and import:
```python
import arthasahit_parse
_ARTHASAHIT_WORK_IDS = frozenset({
    "tukaram-vachanamrut", "eknath-vachanamrut", "ramdas-vachanamrut",
    "sant-vachanamrut", "jnaneshwar-vachanamrut", "eknathi-bhagvat-vachanamrut",
    "dhyanopakarani-gita",
})
```
Replace the child loop body (from Task 3) with a branch. **For arthasahit works the child unit is a full ENTRY (a verse+meaning paragraph), NOT a childsplit sentence** — `split_verse_meaning` needs the verse and meaning together; splitting into sentences first would put verse and meaning in *separate* children and the parse could never pair them. So iterate the section's paragraphs (`PARA_SPLIT_RE`) as arthasahit children; use `childsplit` only for normal works:
```python
        if work_id in _ARTHASAHIT_WORK_IDS:
            # child = one entry (verse + its meaning). Embed the whole entry
            # (meaning boosts recall); cite ONLY the verse; retrieval-only when
            # no confident verse/meaning split (verse empty or no marker).
            units = [p.strip() for p in PARA_SPLIT_RE.split(sec["text"]) if p.strip()]
            for ci, para in enumerate(units):
                verse, meaning = arthasahit_parse.split_verse_meaning(para)
                child = dict(base_meta)
                child.update({
                    "id": f"{pid}--{ci:03d}", "kind_level": "child", "parent_id": pid,
                    "chunk_index": pi, "chunk_total": total, "source_path": spath,
                    "text": para, "embed_text": para,
                    "token_estimate": estimate_tokens(para),
                })
                if meaning is not None and verse.strip():
                    child["cite_text"] = verse          # cite the verse only
                # else: no cite_text key ⇒ retrieval-only (never cited)
                yield child
        else:
            for ci, kid in enumerate(childsplit.split_into_children(sec["text"], window=1)):
                child = dict(base_meta)
                child.update({
                    "id": f"{pid}--{ci:03d}", "kind_level": "child", "parent_id": pid,
                    "chunk_index": pi, "chunk_total": total, "source_path": spath,
                    "text": kid["text"], "embed_text": kid["embed_text"],
                    "cite_text": kid["text"], "token_estimate": estimate_tokens(kid["text"]),
                })
                yield child
```
(`PARA_SPLIT_RE` and `estimate_tokens` are module-level in chunker.py already.)

- [ ] **Step 4: Run test to verify it passes**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_chunker_arthasahit.py tools/tests -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/chunker.py tools/tests/test_chunker_arthasahit.py
git commit -m "chunker: arthasahit children embed meaning, cite verse only; uncertain=retrieval-only (RFC-017 #35)"
```

---

### Task 5: Embedder embeds children only; uses embed_text

**Files:**
- Modify: `tools/embedder.py` (chunk load + text selection)
- Test: `tools/tests/test_embedder_children.py`

**Interfaces:**
- Produces: the embedder builds the id→vec map and encodes only rows with `kind_level != "parent"`, and embeds each child's `embed_text` (falling back to `text`). Parent rows are written to `chunks_meta.jsonl` unchanged (for context lookup) but excluded from `embeddings.npy`. Row-alignment invariant becomes: `embeddings.npy` rows == the CHILD rows in order; `chunks_meta.jsonl` may hold parents interleaved — **decision (open q 2): write a separate `parents.jsonl` and keep `chunks_meta.jsonl` children-only** so row-alignment stays 1:1. Implement that: children → `chunks.jsonl`/`chunks_meta.jsonl`; parents → `parents.jsonl`.

**Context to read first:** `tools/embedder.py` `load_chunks`, `write_meta`, and the encode loop; `tools/chunker.py`'s final write of `chunks.jsonl` (split parent rows into `parents.jsonl`).

- [ ] **Step 1: Write the failing test** (encode uses embed_text; parents excluded)

```python
# tools/tests/test_embedder_children.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import embedder

def test_text_for_embedding_prefers_embed_text():
    assert embedder.text_for_embedding({"text": "raw", "embed_text": "raw + window"}) == "raw + window"
    assert embedder.text_for_embedding({"text": "only"}) == "only"
```

- [ ] **Step 2: Run to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_embedder_children.py -q`
Expected: FAIL — `text_for_embedding` undefined.

- [ ] **Step 3: Implement**

In `tools/chunker.py` main write path: route rows where `kind_level == "parent"` to `04_processed/parents.jsonl` and rows where `kind_level == "child"` to `04_processed/chunks.jsonl` (children only). In `tools/embedder.py` add:
```python
def text_for_embedding(chunk: dict) -> str:
    return chunk.get("embed_text") or chunk.get("text") or ""
```
and in the encode loop use `text_for_embedding(chunk)` instead of `chunk["text"]`. (chunks.jsonl is already children-only after the chunker change, so no parent filtering is needed in the embedder.)

- [ ] **Step 4: Run tests**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/chunker.py tools/embedder.py tools/tests/test_embedder_children.py
git commit -m "embed: children-only index (parents→parents.jsonl); embed embed_text (RFC-017)"
```

---

### Task 6: Retrieval — expand children → parents

**Files:**
- Modify: `tools/server.py` (`_retrieve`: after MMR/ranking, group children by `parent_id`, load parent text, cap per parent)
- Test: `tools/tests/test_expand_parents.py`

**Interfaces:**
- Produces: `expand_children_to_parents(ranked_child_idxs, metas, parents_by_id, *, max_per_parent, top_k) -> list[dict]` returning, per distinct parent (in child-rank order), `{parent_id, parent_text, children:[{cite_text/text, child_idx}...]}`. The `label_to_chunk` fed to the answer LLM maps a passage label → the PARENT text (context) with its matched children marked as the anchors to quote.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_expand_parents.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server

def test_expand_groups_by_parent_and_caps():
    metas = [
        {"id":"w--en--0000--000","parent_id":"w--en--0000","cite_text":"c0","kind_level":"child"},
        {"id":"w--en--0000--005","parent_id":"w--en--0000","cite_text":"c5","kind_level":"child"},
        {"id":"w--en--0001--002","parent_id":"w--en--0001","cite_text":"d2","kind_level":"child"},
    ]
    parents = {"w--en--0000":{"text":"PARENT-0"}, "w--en--0001":{"text":"PARENT-1"}}
    groups = server.expand_children_to_parents([0,1,2], metas, parents, max_per_parent=2, top_k=8)
    assert [g["parent_id"] for g in groups] == ["w--en--0000","w--en--0001"]
    assert groups[0]["parent_text"] == "PARENT-0"
    assert len(groups[0]["children"]) == 2      # both children of parent 0, capped at 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_expand_parents.py -q`
Expected: FAIL — `expand_children_to_parents` undefined.

- [ ] **Step 3: Implement `expand_children_to_parents` in server.py**

```python
def expand_children_to_parents(ranked_idxs, metas, parents_by_id, *, max_per_parent, top_k):
    """Group ranked child rows into their distinct parents (child-rank order).
    Returns [{parent_id, parent_text, children:[{...}]}] — the parent is the
    context the answer model reads; children are the precise anchors to quote."""
    groups, order = {}, []
    for idx in ranked_idxs:
        m = metas[idx]
        pid = m.get("parent_id")
        if pid is None:
            continue
        if pid not in groups:
            if len(order) >= top_k:
                continue
            groups[pid] = {"parent_id": pid,
                           "parent_text": (parents_by_id.get(pid) or {}).get("text", ""),
                           "children": []}
            order.append(pid)
        g = groups[pid]
        if len(g["children"]) < max_per_parent:
            g["children"].append({"child_idx": int(idx),
                                  "text": m.get("cite_text") or m.get("text", "")})
    return [groups[p] for p in order]
```
Then wire `_retrieve` to: load `parents.jsonl` once into `STATE.parents_by_id` at startup; after the existing MMR/candidate ranking over children, call `expand_children_to_parents(...)`; build `label_to_chunk` so each passage label's text is the parent (with the matched children listed). The prompt already asks the model to quote by reference — quoting anchors on the children's `cite_text`.

- [ ] **Step 4: Run tests**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/server.py tools/tests/test_expand_parents.py
git commit -m "retrieval: expand ranked children to distinct parents for answer context (RFC-017)"
```

---

### Task 7: Splice / Read-in-full anchor on cite_text + parent

**Files:**
- Modify: `tools/schemas.py` (`splice_qa_citations` / `splice_quote_dict` — use the child's `cite_text` as the quotable body source) and `tools/server.py` (`_enrich_citation_readpage` — match the parent section).
- Test: `tools/tests/test_splice_cite_text.py`

**Interfaces:**
- Consumes: child rows with `cite_text`; parents (Task 6).
- Produces: a spliced citation body is taken only from `cite_text` (so arthasahit citations quote the verse, never the meaning); `readPage` resolves via the parent section text.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_splice_cite_text.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import schemas

def test_splice_body_comes_from_cite_text_only():
    # a child whose cite_text is the verse but whose text/embed includes the meaning
    label_to_chunk = {"A": {"meta": {"work_id":"tukaram-vachanamrut","cite_text":"करीं धंदा परि आवडती पाय",
                                     "workId":"tukaram-vachanamrut","kind":"canonical"}}}
    tool_input = {"citations":[{"quote":{"passage":"A","quoteStart":"करीं धंदा","quoteEnd":"पाय"}}]}
    schemas.splice_qa_citations(tool_input, label_to_chunk)
    body = tool_input["citations"][0]["quote"]["body"]
    assert "करीं धंदा" in body and "अर्थ" not in body
```

- [ ] **Step 2: Run to verify it fails**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_splice_cite_text.py -q`
Expected: FAIL — splice reads `text`, not `cite_text` (body includes meaning or mismatches).

- [ ] **Step 3: Implement**

In `splice_qa_citations`/`splice_quote_dict`, change the source of the verbatim span from `meta["text"]` to `meta.get("cite_text") or meta.get("text")`. A child with NO `cite_text` (retrieval-only) must be **non-quotable**: if a citation references such a passage, drop that citation (it was retrieval-only) rather than splice. In `_enrich_citation_readpage` (server.py), resolve the page against the parent section text (look up `parent_id` → `parents_by_id` → its text/source_path) via the existing `reading_page_for_body`.

- [ ] **Step 4: Run tests**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/schemas.py tools/server.py tools/tests/test_splice_cite_text.py
git commit -m "splice: quote from cite_text (verse-only for arthasahit); readPage via parent (RFC-017)"
```

---

### Task 8: Eval gold cases (recall + arthasahit)

**Files:**
- Modify: `tools/eval_retrieval.py` (gold cases)

- [ ] **Step 1: Add gold cases**

Add to the gold list: the lightning incident — query `"the incident when lightning struck Gurudev's house"`, expect a child of a `punyasmruti`/`guru-ha-parabrahma-kewal`/`१९२७-१९५७` parent whose text contains `वीज पडली` in the top-k. Add 3 existing doctrinal cases as no-regression guards. Add an arthasahit assertion: a citation for a `tukaram-vachanamrut` passage has a `cite_text` with no `अर्थ`.

- [ ] **Step 2: Run the eval (after re-embed, Task 9)**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python tools/eval_retrieval.py`
Expected: the lightning case now PASSES (its child surfaces); doctrinal cases still PASS.

- [ ] **Step 3: Commit**

```bash
git add tools/eval_retrieval.py
git commit -m "eval: small-to-big recall (lightning) + arthasahit cite-verse gold cases (RFC-017)"
```

---

### Task 9: Re-chunk + GPU re-embed runbook

**Files:**
- Create: `docs/RUNBOOK-phase2-reembed.md`

- [ ] **Step 1: Re-chunk locally**

Run: `LC_ALL=en_US.UTF-8 /Users/neharepal/opt/anaconda3/bin/python tools/chunker.py` → rewrites `04_processed/chunks.jsonl` (children only) + `04_processed/parents.jsonl`. Sanity: child count ~60–100k; every child's `parent_id` present in `parents.jsonl`; arthasahit children present.

- [ ] **Step 2: Write the runbook** documenting the GPU embed:
  - Provision a GPU instance (e.g. a cheap cloud GPU with PyTorch + CUDA).
  - `pip install sentence-transformers`; copy `chunks.jsonl` up.
  - Run `tools/embedder.py --restart` (full rebuild — all child ids are new). Confirm `embeddings.npy` rows == child count, aligned to `chunks_meta.jsonl`.
  - Download `embeddings.npy` + `chunks_meta.jsonl`; run `tools/build_chunk_quality.py`; verify alignment with the local `parents.jsonl`.
  - Smoke-test: `tools/eval_retrieval.py` (Task 8) + a few live queries; confirm the lightning child surfaces and arthasahit citations quote verses only.
  - Commit the index artifacts / update `CORPUS_CHANGELOG.md`.

- [ ] **Step 3: Commit the runbook**

```bash
git add docs/RUNBOOK-phase2-reembed.md
git commit -m "docs: Phase 2 re-chunk + GPU re-embed runbook (RFC-017)"
```

---

## Self-review notes

- **Spec coverage:** parent/child model → Tasks 1,3; child schema → Task 3; arthasahit split (#35) → Tasks 2,4,7; embedder children-only → Task 5; retrieval expansion → Task 6; splice/Read-in-full on cite_text → Task 7; eval → Task 8; GPU re-embed → Task 9. All RFC-017 sections mapped.
- **Open questions resolved in-plan:** window=1 (Task 1, tunable); parent storage = separate `parents.jsonl` (Task 5) to keep `embeddings.npy` 1:1 with children; flag-gate not used (full cutover after eval passes — the re-embed is a clean rebuild, and eval gates it).
- **Ordering risk:** Task 8's eval only meaningfully runs after Task 9's re-embed; its gold cases are written earlier but assert against the rebuilt index.
- **Downstream to watch:** `chunk_tier` reads `kind` (unchanged) — the new `kind_level` is a separate field, so tier weighting/dual-retrieval (ADR-017) are unaffected. `max_per_source` → `max_per_parent` semantics change in `_retrieve` (Task 6).
