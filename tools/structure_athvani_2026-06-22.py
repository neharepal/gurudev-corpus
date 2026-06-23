#!/usr/bin/env python
"""RFC-009 Step 5/6 for the athvani books of batch drive_dump_2026-06-22.

Splits each recollection book into individual athvani STORIES (per operator: story
granularity feeds pravachan mode). Slices the verbatim OCR text by the per-unit
start-line boundaries produced by the segmentation agents (no LLM paraphrase of the
citation text), writes per-story meta.yaml + variant files, and merges entries into
03_catalog/story_index.yaml and 03_catalog/catalog.yaml (stories:).

Idempotent: rewrites story folders + re-merges index entries by id.
"""
import json, pathlib, re, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEG = pathlib.Path("/Users/neharepal/.claude/jobs/bccb3cba/tmp")
EXT = ROOT / "00_raw/drive_dump_2026-06-22/_extracted"
STORIES = ROOT / "02_aggregated/athvani/about_gurudev_ranade/stories"
BATCH = "drive_dump_2026-06-22"

BOOKS = [
  dict(prefix="smruti", seg="seg-smruti.json", md="smruti-sangam.md",
       work_id="smruti-sangam", work_title="स्मृति-संगम (Smruti Sangam)",
       raw="00_raw/drive_dump_2026-06-22/Neha 2/Copy of Smruti SangamTHE FINAL PRESS COPY  2020.docx"),
  dict(prefix="santsabha", seg="seg-santsabha.json", md="santsabha-sittings-vamanrao-kulkarni.md",
       work_id="santsabha-sittings", work_title="संतसभा — गुरुदेवांच्या सिटींग्ज (Vamanrao Kulkarni)",
       raw="00_raw/drive_dump_2026-06-22/Neha 2/Copy of संतसभा परमपूज्य गुरुदेवांच्या सीटींग्ज, वामनराव कुलकर्णी.pdf"),
  dict(prefix="dada-tendulkar", seg="seg-dada.json", md="dada-tendulkar-shesh-ruperi-pane.md",
       work_id="dada-tendulkar-shesh-ruperi-pane", work_title="शेष रुपेरी पाने (Dada Tendulkar)",
       raw="00_raw/drive_dump_2026-06-22/Neha 2/Copy of दादा तेंडुलकर आठवणी शेष रुपेरी पाने.pdf"),
]

def kebab(s, n=45):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:n].strip("-") or "story"

def main():
    story_index = {}   # slug -> entry
    catalog_stories = []
    total = 0
    for b in BOOKS:
        units = json.load(open(SEG / b["seg"]))
        # Split on "\n" ONLY (not str.splitlines, which also breaks on form-feed
        # \x0c and other unicode separators present in the OCR text). The
        # segmentation agents numbered lines by \n, so str.splitlines would drift
        # the slice boundaries past every page-break char.
        lines = (EXT / b["md"]).read_text(encoding="utf-8", errors="replace").split("\n")
        N = len(lines)
        for i, u in enumerate(units):
            start = u["start_line"]
            end = units[i + 1]["start_line"] if i + 1 < len(units) else N + 1
            body = "\n".join(lines[start - 1: end - 1]).replace("\f", "").strip()
            if not body:
                continue
            seq = u["seq"]
            lang = "en" if u.get("language") == "en" else "mr"
            slug = f"{b['prefix']}-{seq:03d}-{kebab(u.get('title_en'))}"
            sd = STORIES / slug
            vdir = sd / lang / "variants"
            vdir.mkdir(parents=True, exist_ok=True)
            vfile = f"{lang}/variants/{b['prefix']}_seg{seq:03d}.md"
            (sd / vfile).write_text(body + "\n", encoding="utf-8")
            title = u.get("title_mr") or u.get("title_en") or slug
            meta = {
                "id": slug,
                "title": title,
                "title_en": u.get("title_en", ""),
                "title_translit": "",
                "about_member": "gurudev_ranade",
                "languages_available": [lang],
                "themes": u.get("themes", []),
                "people_involved": u.get("key_people", []),
                "subject_focus": u.get("one_line", ""),
                "location": "",
                "variants": [{
                    "source_work_id": b["work_id"],
                    "source_work_title": b["work_title"],
                    "narrator": u.get("narrator", "unknown"),
                    "language": lang,
                    "file": vfile,
                    "page_or_section": f"unit {seq}",
                    "raw_source": b["raw"],
                    "received_in_batch": BATCH,
                    "distinctive_details": u.get("one_line", ""),
                }],
                "consolidated": {"status": "single_variant",
                                 "notes": f"Auto-segmented {BATCH} from {b['work_title']} via tools/structure_athvani_2026-06-22.py."},
                "notes": f"Story unit {seq} of {b['work_title']} (narrator: {u.get('narrator','unknown')}).",
            }
            (sd / "meta.yaml").write_text(
                yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
            story_index[slug] = {
                "canonical_title": title,
                "title_en": u.get("title_en", ""),
                "about_member": "gurudev_ranade",
                "one_line": u.get("one_line", ""),
                "narrator": u.get("narrator", "unknown"),
                "key_people": u.get("key_people", []),
                "themes": u.get("themes", []),
                "source_work": b["work_id"],
                "language": lang,
                "variant_count": 1,
                "variant_files": [str((sd / vfile).relative_to(ROOT))],
            }
            catalog_stories.append({
                "id": slug,
                "path": str(sd.relative_to(ROOT)) + "/",
                "about_member": "gurudev_ranade",
                "title": title,
                "title_en": u.get("title_en", ""),
                "themes": u.get("themes", []),
                "languages_available": [lang],
                "variant_count": 1,
            })
            total += 1

    # merge into story_index.yaml
    si_path = ROOT / "03_catalog/story_index.yaml"
    si = yaml.safe_load(si_path.read_text()) or {}
    si.setdefault("stories", {})
    si["stories"].update(story_index)
    si["last_updated"] = "2026-06-23"
    si_path.write_text(yaml.safe_dump(si, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # merge into catalog.yaml (stories:) by id
    cat_path = ROOT / "03_catalog/catalog.yaml"
    cat = yaml.safe_load(cat_path.read_text()) or {}
    existing = {s["id"]: s for s in (cat.get("stories") or [])}
    for s in catalog_stories:
        existing[s["id"]] = s
    cat["stories"] = list(existing.values())
    cat_path.write_text(yaml.safe_dump(cat, allow_unicode=True, sort_keys=False), encoding="utf-8")

    print(f"Created {total} story folders across {len(BOOKS)} books.")
    print(f"story_index.yaml stories: {len(si['stories'])}; catalog stories: {len(cat['stories'])}")

if __name__ == "__main__":
    main()
