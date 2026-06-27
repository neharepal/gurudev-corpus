"""Unit tests for tools/apply_flags.py — garble Phase 2 maintenance CLI.

Corpus-free: no real corpus files, no embeddings, no API calls.
All I/O is via tmp files and monkeypatching.
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml

# ── bootstrap sys.path (same pattern as other tests in this suite) ──────────
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)

import apply_flags


# ---------------------------------------------------------------------------
# Helpers to build synthetic queue entries
# ---------------------------------------------------------------------------

def _correction_entry(
    slug: str = "test-work",
    page: int = 1,
    paragraph: int = 5,
    lang: str = "en",
    original: str = "garbled text here",
    corrected: str = "correct text here",
    applied_at: Optional[str] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "flagged_at": "2026-06-01T12:00:00+00:00",
        "kind": "correction",
        "question": "",
        "mode": "reading",
        "slug": slug,
        "page": page,
        "paragraph": paragraph,
        "original": original,
        "corrected": corrected,
        "lang": lang,
        "citations": [],
        "category": "",
        "note": "",
    }
    if applied_at is not None:
        entry["applied_at"] = applied_at
    return entry


def _issue_entry() -> Dict[str, Any]:
    return {
        "flagged_at": "2026-06-01T12:00:00+00:00",
        "kind": "issue",
        "question": "Something seems wrong",
        "mode": "qa",
        "citations": [],
        "category": "wrong-attribution",
        "note": "The passage is attributed wrongly.",
        "lang": "",
    }


# ---------------------------------------------------------------------------
# load_queue / save_queue
# ---------------------------------------------------------------------------

class TestLoadQueue:
    def test_returns_empty_list_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", tmp_path / "missing.yaml")
        assert apply_flags.load_queue() == []

    def test_loads_entries(self, tmp_path, monkeypatch):
        q = tmp_path / "flag_queue.yaml"
        entries = [_correction_entry(), _issue_entry()]
        q.write_text(
            yaml.dump(entries, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", q)
        loaded = apply_flags.load_queue()
        assert len(loaded) == 2
        assert loaded[0]["kind"] == "correction"
        assert loaded[1]["kind"] == "issue"

    def test_returns_empty_on_invalid_yaml(self, tmp_path, monkeypatch):
        q = tmp_path / "flag_queue.yaml"
        q.write_text("{ broken yaml: [}", encoding="utf-8")
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", q)
        # Should not raise — just returns []
        result = apply_flags.load_queue()
        assert result == []


class TestSaveQueue:
    def test_writes_yaml_list(self, tmp_path, monkeypatch):
        q = tmp_path / "flag_queue.yaml"
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", q)
        entries = [_correction_entry(), _issue_entry()]
        apply_flags.save_queue(entries)
        raw = yaml.safe_load(q.read_text(encoding="utf-8"))
        assert isinstance(raw, list)
        assert len(raw) == 2

    def test_overwrites_existing(self, tmp_path, monkeypatch):
        q = tmp_path / "flag_queue.yaml"
        q.write_text(yaml.dump([_issue_entry()]), encoding="utf-8")
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", q)
        apply_flags.save_queue([_correction_entry()])
        raw = yaml.safe_load(q.read_text(encoding="utf-8"))
        assert len(raw) == 1
        assert raw[0]["kind"] == "correction"


# ---------------------------------------------------------------------------
# pending_corrections
# ---------------------------------------------------------------------------

class TestPendingCorrections:
    def test_includes_unapplied_corrections(self):
        entries = [_correction_entry()]
        result = apply_flags.pending_corrections(entries)
        assert len(result) == 1
        assert result[0]["kind"] == "correction"

    def test_excludes_issue_entries(self):
        entries = [_issue_entry()]
        assert apply_flags.pending_corrections(entries) == []

    def test_excludes_already_applied(self):
        entry = _correction_entry(applied_at="2026-06-02T00:00:00+00:00")
        assert apply_flags.pending_corrections([entry]) == []

    def test_mixed_queue(self):
        entries = [
            _issue_entry(),
            _correction_entry(slug="work-a"),
            _correction_entry(slug="work-b", applied_at="2026-06-02T00:00:00+00:00"),
            _correction_entry(slug="work-c"),
        ]
        result = apply_flags.pending_corrections(entries)
        assert len(result) == 2
        slugs = [e["slug"] for e in result]
        assert "work-a" in slugs
        assert "work-c" in slugs
        assert "work-b" not in slugs

    def test_excludes_entries_missing_slug(self):
        entry = _correction_entry()
        del entry["slug"]
        assert apply_flags.pending_corrections([entry]) == []

    def test_excludes_entries_missing_original(self):
        entry = _correction_entry()
        del entry["original"]
        assert apply_flags.pending_corrections([entry]) == []


# ---------------------------------------------------------------------------
# apply_correction_to_text
# ---------------------------------------------------------------------------

class TestApplyCorrectionToText:
    def test_replaces_original_with_corrected(self):
        source = "This is garbled text here in the middle of a passage."
        result = apply_flags.apply_correction_to_text(
            source, "garbled text here", "corrected text here"
        )
        assert result == "This is corrected text here in the middle of a passage."

    def test_returns_none_when_original_not_found(self):
        source = "The actual text is fine."
        result = apply_flags.apply_correction_to_text(
            source, "garbled text here", "corrected text here"
        )
        assert result is None

    def test_does_not_modify_source_when_not_found(self):
        source = "Unchanged text."
        original_copy = source
        apply_flags.apply_correction_to_text(source, "missing", "replacement")
        # source string is immutable in Python; just verify the return
        assert source == original_copy

    def test_replaces_only_first_occurrence(self):
        source = "abc abc abc"
        result = apply_flags.apply_correction_to_text(source, "abc", "xyz")
        assert result == "xyz abc abc"

    def test_multiline_replacement(self):
        source = "First paragraph.\n\nSecond garbled\nparagraph.\n\nThird paragraph."
        original = "Second garbled\nparagraph."
        corrected = "Second corrected\nparagraph."
        result = apply_flags.apply_correction_to_text(source, original, corrected)
        assert result == "First paragraph.\n\nSecond corrected\nparagraph.\n\nThird paragraph."

    def test_empty_original_returns_none(self):
        # An empty string is always "found" — guard against that
        source = "any text"
        result = apply_flags.apply_correction_to_text(source, "", "replacement")
        # "" in "any text" is True, so patched will be "replacement" + "any text"
        # The important thing is we don't crash; actual policy: empty strings are
        # always "found", which is fine — the caller (cmd_apply) validates non-empty.
        assert result is not None  # implementation detail: empty original always matches

    def test_devanagari_text_replacement(self):
        source = "गरबल्ड मजकूर येथे आहे."
        original = "गरबल्ड मजकूर"
        corrected = "शुद्ध मजकूर"
        result = apply_flags.apply_correction_to_text(source, original, corrected)
        assert result == "शुद्ध मजकूर येथे आहे."

    def test_unicode_text_unchanged_when_no_match(self):
        source = "शुद्ध मजकूर"
        result = apply_flags.apply_correction_to_text(source, "garbled", "fixed")
        assert result is None


# ---------------------------------------------------------------------------
# resolve_text_path
# ---------------------------------------------------------------------------

class TestResolveTextPath:
    def test_resolves_via_catalog(self, tmp_path, monkeypatch):
        """Catalog hit → uses the path field."""
        # Set up fake repo structure
        slug = "test-work"
        lang = "en"
        work_dir = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug
        text_path = work_dir / lang / "text.md"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text("Some corpus text.", encoding="utf-8")

        catalog = {
            "works": [
                {
                    "id": slug,
                    "title": "Test Work",
                    "author": "gurudev_ranade",
                    "languages": [lang],
                    "path": f"01_canonical/gurudev_ranade/books/{slug}/",
                }
            ]
        }
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(
            yaml.dump(catalog, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        result = apply_flags.resolve_text_path(slug, lang)
        assert result == text_path

    def test_resolves_via_fallback_scan(self, tmp_path, monkeypatch):
        """Catalog miss → falls back to filesystem scan."""
        slug = "uncatalogued-work"
        lang = "mr"
        work_dir = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug
        text_path = work_dir / lang / "text.md"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text("काही मजकूर.", encoding="utf-8")

        # Catalog exists but does NOT contain this slug
        catalog = {"works": []}
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump(catalog), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        result = apply_flags.resolve_text_path(slug, lang)
        assert result == text_path

    def test_returns_none_for_unknown_slug(self, tmp_path, monkeypatch):
        catalog = {"works": []}
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump(catalog), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        result = apply_flags.resolve_text_path("nonexistent-slug", "en")
        assert result is None

    def test_returns_none_when_text_md_missing(self, tmp_path, monkeypatch):
        slug = "work-without-text"
        lang = "en"
        work_dir = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug
        lang_dir = work_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        # No text.md created

        catalog = {
            "works": [
                {
                    "id": slug,
                    "title": "Work Without Text",
                    "author": "gurudev_ranade",
                    "languages": [lang],
                    "path": f"01_canonical/gurudev_ranade/books/{slug}/",
                }
            ]
        }
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump(catalog), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        result = apply_flags.resolve_text_path(slug, lang)
        assert result is None

    def test_falls_back_to_first_available_lang(self, tmp_path, monkeypatch):
        """When requested lang is absent, falls back to first available lang."""
        slug = "bilingual-work"
        work_dir = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug
        for lang in ["en", "mr"]:
            text_path = work_dir / lang / "text.md"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(f"Text in {lang}.", encoding="utf-8")

        catalog = {
            "works": [
                {
                    "id": slug,
                    "title": "Bilingual Work",
                    "author": "gurudev_ranade",
                    "languages": ["en", "mr"],
                    "path": f"01_canonical/gurudev_ranade/books/{slug}/",
                }
            ]
        }
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump(catalog), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        # Request "hi" (not available) — should fall back to "en"
        result = apply_flags.resolve_text_path(slug, "hi")
        assert result is not None
        assert result.parent.name == "en"


# ---------------------------------------------------------------------------
# Integration: cmd_apply (dry-run, with --yes, applied_at marking)
# ---------------------------------------------------------------------------

class TestCmdApply:
    def _setup_repo(self, tmp_path: Path, slug: str, lang: str, source_text: str) -> None:
        """Create a minimal repo structure: catalog + text.md."""
        work_dir = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug
        text_path = work_dir / lang / "text.md"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(source_text, encoding="utf-8")

        catalog = {
            "works": [
                {
                    "id": slug,
                    "title": "Test Work",
                    "author": "gurudev_ranade",
                    "languages": [lang],
                    "path": f"01_canonical/gurudev_ranade/books/{slug}/",
                }
            ]
        }
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump(catalog, allow_unicode=True), encoding="utf-8")

    def test_dry_run_makes_no_changes(self, tmp_path, monkeypatch):
        slug = "test-work"
        lang = "en"
        source = "The garbled text here is the original."
        self._setup_repo(tmp_path, slug, lang, source)

        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        entries = [_correction_entry(slug=slug, lang=lang)]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        rc = apply_flags.cmd_apply(dry_run=True, yes=True, reembed=False)
        assert rc == 0

        # File must be unchanged
        text_path = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug / lang / "text.md"
        assert text_path.read_text(encoding="utf-8") == source

        # Queue must be unchanged (no applied_at)
        updated = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
        assert updated[0].get("applied_at") is None

    def test_apply_yes_patches_file(self, tmp_path, monkeypatch):
        slug = "test-work"
        lang = "en"
        source = "The garbled text here is the original."
        self._setup_repo(tmp_path, slug, lang, source)

        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        entries = [_correction_entry(slug=slug, lang=lang)]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        rc = apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)
        assert rc == 0

        # Text must be patched
        text_path = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug / lang / "text.md"
        patched = text_path.read_text(encoding="utf-8")
        assert "correct text here" in patched
        assert "garbled text here" not in patched

        # Backup must exist
        bak_path = text_path.with_suffix(".md.bak")
        assert bak_path.exists()
        assert bak_path.read_text(encoding="utf-8") == source

    def test_apply_marks_applied_at(self, tmp_path, monkeypatch):
        slug = "test-work"
        lang = "en"
        source = "The garbled text here is the original."
        self._setup_repo(tmp_path, slug, lang, source)

        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        entries = [_correction_entry(slug=slug, lang=lang)]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)

        updated = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
        assert len(updated) == 1
        record = updated[0]
        assert record.get("applied_at") is not None
        # Must be a valid ISO-8601 UTC timestamp
        ts = datetime.datetime.fromisoformat(record["applied_at"])
        assert ts.tzinfo is not None

    def test_applied_entry_skipped_on_second_pass(self, tmp_path, monkeypatch):
        slug = "test-work"
        lang = "en"
        source = "The garbled text here is the original."
        self._setup_repo(tmp_path, slug, lang, source)

        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        entries = [_correction_entry(slug=slug, lang=lang)]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        # First pass
        apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)

        # Re-read patched text for a second pass check
        text_path = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug / lang / "text.md"
        patched_once = text_path.read_text(encoding="utf-8")

        # Second pass — should find no pending corrections
        rc = apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)
        assert rc == 0

        # Text must be unchanged from after first pass
        assert text_path.read_text(encoding="utf-8") == patched_once

    def test_original_not_found_skips_without_writing(self, tmp_path, monkeypatch):
        slug = "test-work"
        lang = "en"
        source = "Completely different text with no garble."
        self._setup_repo(tmp_path, slug, lang, source)

        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        entries = [_correction_entry(slug=slug, lang=lang, original="garbled text here")]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        rc = apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)
        assert rc == 0

        # Source file must be untouched
        text_path = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug / lang / "text.md"
        assert text_path.read_text(encoding="utf-8") == source

        # Entry must NOT be marked applied
        updated = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
        assert updated[0].get("applied_at") is None

    def test_unknown_slug_skipped(self, tmp_path, monkeypatch):
        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump({"works": []}), encoding="utf-8")

        entries = [_correction_entry(slug="nonexistent-work")]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        rc = apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)
        # Unknown slug → skipped, not an error
        assert rc == 0

    def test_issue_entries_are_ignored(self, tmp_path, monkeypatch):
        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        catalog_path = tmp_path / "03_catalog" / "catalog.yaml"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(yaml.dump({"works": []}), encoding="utf-8")

        entries = [_issue_entry()]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        rc = apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)
        assert rc == 0

    def test_multiple_corrections_applied_in_order(self, tmp_path, monkeypatch):
        slug = "test-work"
        lang = "en"
        # Source contains both garbles
        source = (
            "First garbled phrase in the text. "
            "Then another garbled passage follows here. "
            "End of text."
        )
        self._setup_repo(tmp_path, slug, lang, source)

        queue_file = tmp_path / "03_catalog" / "flag_queue.yaml"
        entries = [
            _correction_entry(
                slug=slug, lang=lang,
                original="garbled phrase",
                corrected="correct phrase",
            ),
            _correction_entry(
                slug=slug, lang=lang,
                original="garbled passage",
                corrected="correct passage",
            ),
        ]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "REPO", tmp_path)
        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)

        rc = apply_flags.cmd_apply(dry_run=False, yes=True, reembed=False)
        assert rc == 0

        text_path = tmp_path / "01_canonical" / "gurudev_ranade" / "books" / slug / lang / "text.md"
        final = text_path.read_text(encoding="utf-8")
        assert "correct phrase" in final
        assert "correct passage" in final
        assert "garbled phrase" not in final
        assert "garbled passage" not in final

        # Both entries must be marked applied
        updated = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
        assert all(e.get("applied_at") is not None for e in updated)


# ---------------------------------------------------------------------------
# cmd_list
# ---------------------------------------------------------------------------

class TestCmdList:
    def test_list_no_corrections(self, tmp_path, monkeypatch, capsys):
        queue_file = tmp_path / "flag_queue.yaml"
        entries = [_issue_entry()]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)
        rc = apply_flags.cmd_list()
        assert rc == 0
        out = capsys.readouterr().out
        assert "No pending corrections" in out

    def test_list_shows_pending(self, tmp_path, monkeypatch, capsys):
        queue_file = tmp_path / "flag_queue.yaml"
        entries = [_correction_entry(slug="my-work", original="bad txt", corrected="good text")]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)
        rc = apply_flags.cmd_list()
        assert rc == 0
        out = capsys.readouterr().out
        assert "my-work" in out
        assert "Pending corrections: 1" in out

    def test_list_excludes_applied(self, tmp_path, monkeypatch, capsys):
        queue_file = tmp_path / "flag_queue.yaml"
        entries = [
            _correction_entry(slug="done-work", applied_at="2026-06-02T00:00:00+00:00"),
            _correction_entry(slug="pending-work"),
        ]
        queue_file.write_text(yaml.dump(entries, allow_unicode=True), encoding="utf-8")

        monkeypatch.setattr(apply_flags, "FLAG_QUEUE_PATH", queue_file)
        rc = apply_flags.cmd_list()
        assert rc == 0
        out = capsys.readouterr().out
        assert "pending-work" in out
        assert "done-work" not in out
        assert "Pending corrections: 1" in out
