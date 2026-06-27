#!/usr/bin/env python3
"""
Garble Phase 2 MAINTENANCE tool — apply queued text corrections to source files.

Reads pending correction entries from 03_catalog/flag_queue.yaml, shows diffs,
and (with --apply) patches the source text.md files in-place.  After applying,
prints the exact re-embed command for the affected works (and optionally runs it
with --reembed).

Usage:
    # List pending corrections
    python tools/apply_flags.py --list

    # Dry-run: show what would be changed (no writes)
    python tools/apply_flags.py --apply --dry-run

    # Apply with interactive confirm per correction
    python tools/apply_flags.py --apply

    # Apply without interactive confirm (batch / CI)
    python tools/apply_flags.py --apply --yes

    # Apply and immediately re-embed affected works
    python tools/apply_flags.py --apply --yes --reembed

Env:
    GURUDEV_REPO   optional override for the repo root (default: parent of this file)
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------

REPO: Path = Path(os.environ.get("GURUDEV_REPO", "")).resolve() or Path(__file__).resolve().parent.parent
FLAG_QUEUE_PATH: Path = REPO / "03_catalog" / "flag_queue.yaml"
LEGACY_JSONL_PATH: Path = REPO / "logs" / "issue_reports.jsonl"


# ---------------------------------------------------------------------------
# Path resolution — mirrors _resolve_text_path() in server.py
# ---------------------------------------------------------------------------

def resolve_text_path(slug: str, lang: Optional[str]) -> Optional[Path]:
    """Return the resolved text.md path for (slug, lang), or None if not found.

    Mirrors the lookup logic used by server.py _resolve_text_path() so the
    same file is located here without duplicating catalog loading in hot paths.

    Priority:
      1. catalog.yaml `path` field (authoritative)
      2. Filesystem scan of common canonical/aggregated patterns (fallback for
         works on disk that haven't been catalogued yet)
    """
    catalog_path = REPO / "03_catalog" / "catalog.yaml"
    work_meta = None
    try:
        with open(catalog_path, encoding="utf-8") as f:
            catalog = yaml.safe_load(f)
        for w in (catalog.get("works") or []):
            if w.get("id") == slug:
                work_meta = w
                break
    except Exception:
        pass

    if work_meta is None:
        # Fallback: scan common directory patterns (mirrors server.py read_work fallback)
        candidate_dirs = [
            REPO / "01_canonical" / "gurudev_ranade" / "books" / slug,
            REPO / "01_canonical" / "bhausaheb_maharaj" / "letters" / slug,
            REPO / "01_canonical" / "kakasaheb_tulpule" / "books" / slug,
            REPO / "01_canonical" / "nimbargi_maharaj" / "books" / slug,
            REPO / "01_canonical" / "other_authors" / "books" / slug,
            REPO / "02_aggregated" / "biography" / "about_gurudev_ranade" / slug,
        ]
        work_dir: Optional[Path] = None
        for d in candidate_dirs:
            if d.exists():
                work_dir = d
                break
        if work_dir is None:
            return None
        langs_on_disk = sorted(
            d.name for d in work_dir.iterdir()
            if d.is_dir() and (d / "text.md").exists()
        )
        resolved_lang = (
            lang if lang and lang in langs_on_disk
            else (langs_on_disk[0] if langs_on_disk else None)
        )
        if resolved_lang is None:
            return None
        return work_dir / resolved_lang / "text.md"

    # Catalog hit
    available_langs: List[str] = work_meta.get("languages", ["en"])
    resolved_lang = (
        lang if lang and lang in available_langs
        else available_langs[0]
    )
    work_path_str: str = work_meta.get("path", "")
    if not work_path_str:
        return None
    text_path = REPO / work_path_str.rstrip("/") / resolved_lang / "text.md"
    return text_path if text_path.exists() else None


# ---------------------------------------------------------------------------
# Flag queue helpers
# ---------------------------------------------------------------------------

def load_queue() -> List[Dict[str, Any]]:
    """Load all entries from the flag queue YAML.  Returns [] if file missing."""
    if not FLAG_QUEUE_PATH.exists():
        return []
    try:
        raw = yaml.safe_load(FLAG_QUEUE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
        return []
    except Exception as exc:
        print(f"WARNING: could not parse {FLAG_QUEUE_PATH}: {exc}", file=sys.stderr)
        return []


def save_queue(entries: List[Dict[str, Any]]) -> None:
    """Atomically rewrite the flag queue YAML, preserving all entries."""
    FLAG_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = FLAG_QUEUE_PATH.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.dump(entries, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(FLAG_QUEUE_PATH)


def pending_corrections(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return entries that are kind=correction, status=approved, and not yet applied.

    `status` missing is treated as "pending" (not approved), so legacy entries
    without a status field are NOT applied until explicitly approved via the
    dashboard.  Entries already applied (applied_at set) are also excluded.
    """
    return [
        e for e in entries
        if e.get("kind") == "correction"
        and e.get("status") == "approved"
        and e.get("applied_at") is None
        and e.get("slug") and e.get("original") is not None and e.get("corrected") is not None
    ]


# ---------------------------------------------------------------------------
# Text replacement
# ---------------------------------------------------------------------------

def apply_correction_to_text(source: str, original: str, corrected: str) -> Optional[str]:
    """Return the patched string if `original` is found exactly, else None.

    Never modifies source if `original` is absent (drift guard).
    """
    if original not in source:
        return None
    return source.replace(original, corrected, 1)


def _make_diff(a: str, b: str, label_a: str = "original", label_b: str = "corrected") -> str:
    """Return a human-readable unified diff of the two strings."""
    lines_a = a.splitlines(keepends=True)
    lines_b = b.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b))
    if not diff_lines:
        return "  (no visible change)"
    return "".join(diff_lines)


# ---------------------------------------------------------------------------
# --list command
# ---------------------------------------------------------------------------

def cmd_list() -> int:
    """Print all correction entries (all statuses) with readable diff and status."""
    entries = load_queue()
    corrections = [
        e for e in entries
        if e.get("kind") == "correction"
        and e.get("slug") and e.get("original") is not None and e.get("corrected") is not None
    ]

    if not corrections:
        print("No corrections in the flag queue.")
        return 0

    print(f"Corrections in queue: {len(corrections)}\n")
    for i, entry in enumerate(corrections, 1):
        slug = entry.get("slug", "?")
        page = entry.get("page", "?")
        paragraph = entry.get("paragraph", "?")
        lang = entry.get("lang", "")
        flagged_at = entry.get("flagged_at", "?")
        status = entry.get("status", "pending")
        applied_at = entry.get("applied_at")
        original = entry.get("original", "")
        corrected = entry.get("corrected", "")
        entry_id = entry.get("id", "?")

        print(
            f"[{i}] id={entry_id!r}  slug={slug!r}  page={page}  para={paragraph}  "
            f"lang={lang!r}  status={status!r}  flagged={flagged_at}"
        )
        if applied_at:
            print(f"     applied_at={applied_at}")
        diff = _make_diff(original, corrected, label_a=f"original (slug={slug})", label_b="corrected")
        # Indent the diff for readability
        for line in diff.splitlines():
            print("    " + line)
        print()

    return 0


# ---------------------------------------------------------------------------
# --apply command
# ---------------------------------------------------------------------------

def cmd_apply(*, dry_run: bool, yes: bool, reembed: bool) -> int:
    """Apply pending corrections to source text.md files."""
    entries = load_queue()
    corrections = pending_corrections(entries)

    if not corrections:
        print("No pending corrections in the flag queue.")
        return 0

    print(f"Found {len(corrections)} pending correction(s).\n")

    applied_slugs: List[str] = []
    skipped_count = 0
    error_count = 0

    for i, entry in enumerate(corrections, 1):
        slug = entry.get("slug", "")
        page = entry.get("page", "?")
        paragraph = entry.get("paragraph", "?")
        lang = entry.get("lang") or None
        original: str = entry.get("original", "")
        corrected: str = entry.get("corrected", "")
        flagged_at = entry.get("flagged_at", "?")

        print(f"--- Correction [{i}/{len(corrections)}] ---")
        print(f"  work:      {slug!r}")
        print(f"  page:      {page}  para: {paragraph}  lang: {lang!r}")
        print(f"  flagged:   {flagged_at}")
        print()

        # Show diff
        diff = _make_diff(original, corrected)
        for line in diff.splitlines():
            print("  " + line)
        print()

        # Resolve text.md path
        text_path = resolve_text_path(slug, lang)
        if text_path is None:
            print(f"  SKIP: cannot resolve text.md for slug={slug!r} lang={lang!r}\n")
            skipped_count += 1
            continue

        print(f"  source:    {text_path.relative_to(REPO)}")

        # Read source
        try:
            source = text_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"  ERROR: could not read {text_path}: {exc}\n")
            error_count += 1
            continue

        # Check original text is present
        patched = apply_correction_to_text(source, original, corrected)
        if patched is None:
            print(
                f"  SKIP: `original` text not found in source file (text may have drifted).\n"
                f"  Cannot apply without exact match.\n"
            )
            skipped_count += 1
            continue

        if dry_run:
            print("  [dry-run] Would write patched text to file.")
            print()
            continue

        # Interactive confirm
        if not yes:
            prompt = "  Apply this correction? [y/N]: "
            try:
                answer = input(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted by user.")
                return 1
            if answer not in ("y", "yes"):
                print("  Skipped (user declined).\n")
                skipped_count += 1
                continue

        # Write atomically with .bak backup
        bak_path = text_path.with_suffix(".md.bak")
        shutil.copy2(text_path, bak_path)
        tmp_path = text_path.with_suffix(".md.tmp")
        try:
            tmp_path.write_text(patched, encoding="utf-8")
            tmp_path.replace(text_path)
        except Exception as exc:
            print(f"  ERROR: write failed: {exc}")
            # Restore from backup
            if bak_path.exists():
                shutil.copy2(bak_path, text_path)
            error_count += 1
            continue

        print(f"  OK: wrote patched text.md  (backup: {bak_path.relative_to(REPO)})")

        # Mark applied in the entries list — find this exact entry by identity
        entry["applied_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        applied_slugs.append(slug)
        print()

    # Persist updated queue (with applied_at timestamps)
    if applied_slugs:
        save_queue(entries)
        print(f"Marked {len(applied_slugs)} correction(s) as applied in {FLAG_QUEUE_PATH.relative_to(REPO)}\n")

    # Summary
    print("--- Summary ---")
    print(f"  Applied:  {len(applied_slugs)}")
    print(f"  Skipped:  {skipped_count}")
    print(f"  Errors:   {error_count}")
    print()

    if applied_slugs:
        _print_reembed_instructions(list(dict.fromkeys(applied_slugs)), reembed=reembed)

    return 0 if error_count == 0 else 1


# ---------------------------------------------------------------------------
# Re-embed instructions / runner
# ---------------------------------------------------------------------------

def _print_reembed_instructions(slugs: List[str], *, reembed: bool) -> None:
    """Print the exact re-embed command.  If reembed=True, runs it too."""
    python = sys.executable
    chunker_cmd = f"{python} tools/chunker.py"
    embedder_cmd = f"{python} tools/embedder.py"
    reload_note = "curl -s -X POST http://localhost:8765/admin/reload | python3 -m json.tool"

    print("--- Re-embed ---")
    print(f"Corrected work(s): {', '.join(slugs)}")
    print()
    print("The embedding index must be rebuilt to reflect the source changes.")
    print("Run the following from the repo root:\n")
    print(f"  # 1. Re-chunk the corpus (fast; produces 04_processed/chunks.jsonl)")
    print(f"  {chunker_cmd}\n")
    print(f"  # 2. Re-embed — ADR-012 carry-over means only changed chunks are re-encoded")
    print(f"  {embedder_cmd}\n")
    print(f"  # 3. Hot-reload the live server (if running) to pick up new embeddings:")
    print(f"  {reload_note}\n")

    if reembed:
        import subprocess
        print("Running chunker + embedder now (--reembed flag)...\n")
        for label, cmd in [("chunker", chunker_cmd), ("embedder", embedder_cmd)]:
            print(f"[{label}] {cmd}")
            result = subprocess.run(cmd, shell=True, cwd=str(REPO))
            if result.returncode != 0:
                print(f"  ERROR: {label} exited with code {result.returncode}", file=sys.stderr)
                sys.exit(result.returncode)
            print(f"  [{label}] done.\n")
        print("Re-embed complete.  Run /admin/reload to hot-swap into the live server.")


# ---------------------------------------------------------------------------
# Legacy migration: logs/issue_reports.jsonl → 03_catalog/flag_queue.yaml
# ---------------------------------------------------------------------------

def cmd_migrate_legacy(
    *,
    legacy_path: Optional[Path] = None,
    queue_path: Optional[Path] = None,
) -> int:
    """Convert entries in logs/issue_reports.jsonl into 03_catalog/flag_queue.yaml.

    Idempotent: entries already present in the queue (matched by `flagged_at` +
    `slug` + `paragraph`) are skipped.  New entries are appended with a generated
    `id` and default `status: "pending"`.

    Usage:
        python tools/apply_flags.py --migrate-legacy
    """
    src = legacy_path or LEGACY_JSONL_PATH
    dst = queue_path or FLAG_QUEUE_PATH

    if not src.exists():
        print(f"Legacy file not found: {src}  (nothing to migrate).")
        return 0

    # Read legacy jsonl
    legacy_entries: List[Dict[str, Any]] = []
    with open(src, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                legacy_entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"WARNING: skipping line {lineno} (invalid JSON): {exc}", file=sys.stderr)

    if not legacy_entries:
        print("Legacy file is empty — nothing to migrate.")
        return 0

    # Load existing queue (backfill ids as needed)
    existing: List[Dict[str, Any]] = []
    if dst.exists():
        try:
            raw = yaml.safe_load(dst.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                existing = raw
        except Exception as exc:
            print(f"WARNING: could not parse existing queue: {exc}", file=sys.stderr)

    # Build a dedup key set from the existing queue
    def _dedup_key(e: Dict[str, Any]) -> tuple:
        return (
            e.get("flagged_at") or e.get("timestamp", ""),
            e.get("slug", ""),
            e.get("paragraph", ""),
        )

    existing_keys = {_dedup_key(e) for e in existing}

    # Map jsonl fields to the YAML schema
    added = 0
    for raw in legacy_entries:
        # jsonl uses "timestamp" not "flagged_at"
        flagged_at = raw.get("timestamp") or raw.get("flagged_at", "")
        slug = raw.get("slug", "")
        paragraph = raw.get("paragraph", "")

        key = (flagged_at, slug, paragraph)
        if key in existing_keys:
            print(f"  SKIP (already imported): slug={slug!r}  para={paragraph}  flagged_at={flagged_at}")
            continue

        entry: Dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "flagged_at": flagged_at,
            "status": "pending",
            "kind": raw.get("kind", "correction"),
            "question": raw.get("question", ""),
            "mode": raw.get("mode", "reading"),
            "citations": raw.get("citations", []),
            "category": raw.get("category", ""),
            "note": raw.get("note", ""),
            "lang": raw.get("lang", ""),
        }
        # Correction-specific fields
        if slug:
            entry["slug"] = slug
        if raw.get("page") is not None:
            entry["page"] = raw["page"]
        if paragraph != "":
            entry["paragraph"] = paragraph
        if raw.get("original") is not None:
            entry["original"] = raw["original"]
        if raw.get("corrected") is not None:
            entry["corrected"] = raw["corrected"]

        existing.append(entry)
        existing_keys.add(key)
        added += 1
        print(f"  IMPORT: slug={slug!r}  para={paragraph}  flagged_at={flagged_at}")

    if added:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".yaml.tmp")
        tmp.write_text(
            yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        tmp.replace(dst)
        print(f"\nMigrated {added} entry/entries → {dst}")
    else:
        print("No new entries to migrate.")

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="apply_flags",
        description="Garble Phase 2 maintenance: apply queued text corrections to corpus source files.",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--list",
        action="store_true",
        help="List all corrections (all statuses) with diff and status.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply approved corrections (status=approved) to source text.md files.",
    )
    mode.add_argument(
        "--migrate-legacy",
        action="store_true",
        help=(
            "One-time migration: convert entries from logs/issue_reports.jsonl "
            "into 03_catalog/flag_queue.yaml (idempotent)."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="With --apply: show what would be done without writing anything.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="With --apply: skip interactive confirm and apply all corrections.",
    )
    p.add_argument(
        "--reembed",
        action="store_true",
        help=(
            "With --apply: after writing corrections, run tools/chunker.py and "
            "tools/embedder.py to rebuild the embedding index."
        ),
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return cmd_list()

    if args.apply:
        if args.reembed and args.dry_run:
            parser.error("--reembed and --dry-run are mutually exclusive")
        return cmd_apply(dry_run=args.dry_run, yes=args.yes, reembed=args.reembed)

    if getattr(args, "migrate_legacy", False):
        return cmd_migrate_legacy()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
