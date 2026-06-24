#!/usr/bin/env python
"""RFC-009 Step 5 — structure batch drive_dump_2026-06-22 works into the corpus tree.

Data-driven + idempotent: re-run as more works finish OCR. For each spec it:
  - creates <dest>/<lang>/ and writes text.md from the extracted draft,
  - writes meta.yaml (canonical or biography schema),
  - references the immutable raw PDF via raw_path (ADR-005 — no PDF duplication).

Only works listed in SPECS run; add entries as their extraction lands. Existing
folders (stub-completions / upgrades) are handled with placement only when
`existing: true`, and never overwrite text.md unless `overwrite: true`.
"""
import pathlib, hashlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAWDIR = ROOT / "00_raw/drive_dump_2026-06-22/Neha 2"
EXT = ROOT / "00_raw/drive_dump_2026-06-22/_extracted"
BATCH = "drive_dump_2026-06-22"
RECEIVED = "2026-06-22"

def sha256(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()

# Each spec: one work. raw = source PDF filename in RAWDIR; ext = <slug>.md in EXT.
SPECS = [
  # ---- canonical / gurudev_ranade ----
  dict(slug="herakleitos", kind="canonical", dest="01_canonical/gurudev_ranade/books/herakleitos",
       lang="en", author="gurudev_ranade", work_type="book",
       title="Herakleitos", title_en="Herakleitos",
       raw="Copy of Herakleitos.pdf", ext="herakleitos.md",
       extraction="pdf-text-layer", publisher="", year="",
       qnotes="Born-digital text layer with light OCR artifacts (Greek terms garbled)."),
  dict(slug="evolution-of-my-own-thought", kind="canonical", dest="01_canonical/gurudev_ranade/books/evolution-of-my-own-thought",
       lang="en", author="gurudev_ranade", work_type="essay",
       title="The Evolution of My Own Thought", title_en="The Evolution of My Own Thought",
       raw="Copy of The Evolution Of My Own Thought 1.pdf", ext="evolution-of-my-own-thought.md",
       extraction="pdf-text-layer", publisher="", year="",
       qnotes="Autobiographical/philosophical essay."),
  dict(slug="vindication-of-indian-philosophy", kind="canonical", dest="01_canonical/gurudev_ranade/books/vindication-of-indian-philosophy",
       lang="en", author="gurudev_ranade", work_type="essay",
       title="A Vindication of Indian Philosophy", title_en="A Vindication of Indian Philosophy",
       raw="Copy of A Vindication Of Indian Philosophy_.pdf", ext="vindication-of-indian-philosophy.md",
       extraction="ocr-tesseract", publisher="", year="",
       qnotes="OCR from scan; not yet line-checked against a published source."),
  dict(slug="gandhi-and-other-indian-saints", kind="canonical", dest="01_canonical/gurudev_ranade/books/gandhi-and-other-indian-saints",
       lang="en", author="gurudev_ranade", work_type="book",
       title="Spiritual Awakening in Gandhi and Other Indian Saints", title_en="Spiritual Awakening in Gandhi and Other Indian Saints",
       raw="Copy of Gandhi and other Hindi Saints.pdf", ext="gandhi-and-other-indian-saints.md",
       extraction="pdf-text-layer", publisher="Sarva Seva Sangh Prakashan, Rajghat, Varanasi", year="2003",
       qnotes="Clean EN text layer. 2nd edition, Sept 2003; foreword by Arun Gandhi."),
  # ---- biography ----
  dict(slug="ranade-and-his-spiritual-lineage", kind="biography", dest="02_aggregated/biography/about_gurudev_ranade/ranade-and-his-spiritual-lineage",
       lang="en", about_member="gurudev_ranade", work_type="biography",
       title="R. D. Ranade and His Spiritual Lineage", title_en="R. D. Ranade and His Spiritual Lineage",
       raw="Copy of Date Spiritual Lineage 2015.117278.R-D-Ranade-And-His-Spiritual-Lineage.pdf",
       ext="ranade-and-his-spiritual-lineage.md", extraction="ocr-tesseract", publisher="", year="2015",
       qnotes="OCR clean (642K chars). Tail carries a Ramdas abhang."),
  dict(slug="nimbargi-maharaj-biography-en", kind="biography", dest="02_aggregated/biography/about_nimbargi_maharaj/nimbargi-maharaj-biography-en",
       lang="en", about_member="nimbargi_maharaj", work_type="biography",
       title="Nimbargi Maharaj — A Biography", title_en="Nimbargi Maharaj — A Biography",
       raw="Copy of Nimbargi Maharaj Biography_.pdf", ext="nimbargi-maharaj-biography-en.md",
       extraction="ocr-tesseract", publisher="Academy of Comparative Philosophy and Religion, Belgaum", year="",
       qnotes="OCR from scan."),
  dict(slug="kannada-sahityatil-punyasmruti", kind="biography", dest="02_aggregated/biography/about_gurudev_ranade/kannada-sahityatil-punyasmruti",
       lang="mr", about_member="gurudev_ranade", work_type="biography",
       title="कन्नड साहित्यातील गुरुदेव रानडे यांच्या पुण्यस्मृती", title_en="Gurudev Ranade's Memorial in Kannada Literature",
       raw="Copy of कन्नड साहित्यातील गुरुदेव रानडे यांच्या पुण्यस्मृती.pdf", ext="kannada-sahityatil-punyasmruti.md",
       extraction="ocr-tesseract", publisher="", year="",
       qnotes="OCR clean Marathi (398K chars). Distinct from existing 'punyasmruti' anthology."),
  dict(slug="jivandarshan-deshpande", kind="biography", dest="02_aggregated/biography/about_gurudev_ranade/jivandarshan-deshpande",
       lang="mr", about_member="gurudev_ranade", work_type="biography",
       title="गुरुदेव रानडे — जीवनदर्शन", title_en="Gurudev Ranade — Jivandarshan (by S. N. Deshpande)",
       raw="Copy of गुरुदेव रानडे-जीवनदर्शन ले-शा-नी-देशपांडे 28-Jan-2022 13-14-24.pdf", ext="jivandarshan-deshpande.md",
       extraction="ocr-tesseract", publisher="", year="2022",
       qnotes="By S. N. Deshpande. OCR usable but layout-noisy (1.48M chars); verify before publish."),
  dict(slug="nimbargi-maharaj-charitra-athavani-mr", kind="biography", dest="02_aggregated/biography/about_nimbargi_maharaj/nimbargi-maharaj-charitra-athavani-mr",
       lang="mr", about_member="nimbargi_maharaj", work_type="biography",
       title="परमपूज्य श्रीनिम्बर्गी महाराज चरित्र व आठवणी", title_en="Nimbargi Maharaj — Life and Recollections",
       raw="Copy of परमपूज्य श्रीनिम्बर्गी महाराज चरित्र व आठवणी.docx", ext="nimbargi-maharaj-charitra-athavani-mr.md",
       extraction="docx-xml", publisher="", year="",
       qnotes="Charitra + athavani. Marathi body with some English front matter."),
  # ---- re-OCR'd works (2c) — added 2026-06-23 ----
  dict(slug="amrutavalli", kind="biography", dest="02_aggregated/biography/about_other_devotees/amrutavalli",
       lang="mr", about_member="other_devotees", work_type="biography",
       title="अमृतवल्ली — श्री. दादासाहेब देशपांडे यांचे आठवणीमय जीवनचरित्र",
       title_en="Amrutavalli — Memoir of Shri Dadasaheb Deshpande",
       raw="Copy of अमृतवल्ली_.pdf", ext="amrutavalli.surya.md",
       extraction="ocr-surya", publisher="Gayatri Sahitya, Pune", year="2010",
       qnotes="Re-OCR'd with Surya (tesseract failed on the 150 DPI scan). Clean Marathi (229K chars). Memoir of Dadasaheb Deshpande (Inchageri lineage) by Sou. Rama Inamdar; verify subject/lineage placement."),
  dict(slug="pawanbhumi-jamkhandi", kind="biography", dest="02_aggregated/biography/about_gurudev_ranade/pawanbhumi-jamkhandi",
       lang="en", about_member="gurudev_ranade", work_type="souvenir",
       title="Pawanbhumi Jamkhandi (Sacred Land of Jamkhandi)",
       title_en="Pawanbhumi Jamkhandi (Sacred Land of Jamkhandi)",
       raw="Copy of Pawanbhumi_Jamkhandi_v2.pdf", ext="pawanbhumi-jamkhandi.vision.md",
       extraction="vision-llm-claude", publisher="", year="",
       qnotes="Trilingual souvenir brochure (English/Marathi/Kannada) on Gurudev's birthplace Jamkhandi and its shrines. Vision-LLM transcription of the 12pp brochure (tesseract failed on the multi-column/photo layout). languages_available widened to [en, mr, kn] post-generation."),
]

CANON_META = """id: {slug}
title: {title!r}
title_en: {title_en!r}
title_translit: ""
author: {author}
co_authors: []
work_type: {work_type}
original_language: {lang}
languages_available: [{lang}]
year_first_published: ""
year_this_edition: {year!r}
publisher: {publisher!r}
edition: ""
isbn: ""
sources:
  - raw_path: {raw_path}
    received_on: {received}
    received_in_batch: {batch}
    checksum_sha256: {sha}
tags: []
subject_persons: []
related_works: []
status: extracted
text_extraction_method: {extraction}
quality_notes: {qnotes!r}
notes: |
  Ingested {received} from batch {batch} (Drive 'Dump 3.zip').
external_verification:
  verified: false
  reason: extracted_not_yet_verified_against_published_source
"""

BIO_META = """id: {slug}
title: {title!r}
title_en: {title_en!r}
title_translit: ""
about_member: {about_member}
author: ""
co_authors: []
kind: biography
work_type: biography
original_language: {lang}
languages_available: [{lang}]
year_first_published: ""
year_this_edition: {year!r}
publisher: {publisher!r}
edition: ""
isbn: ""
sources:
  - raw_path: {raw_path}
    received_on: {received}
    received_in_batch: {batch}
    checksum_sha256: {sha}
tags: []
subject_persons: []
related_works: []
status: extracted
text_extraction_method: {extraction}
quality_notes: {qnotes!r}
notes: |
  Ingested {received} from batch {batch} (Drive 'Dump 3.zip').
external_verification:
  verified: false
  reason: extracted_not_yet_verified_against_published_source
"""

def main():
    for s in SPECS:
        dest = ROOT / s["dest"]
        langdir = dest / s["lang"]
        langdir.mkdir(parents=True, exist_ok=True)
        rawpath = RAWDIR / s["raw"]
        extpath = EXT / s["ext"]
        if not extpath.exists():
            print(f"SKIP {s['slug']}: extraction {s['ext']} not found yet"); continue
        sha = sha256(rawpath) if rawpath.exists() else ""
        # place text.md
        textmd = langdir / "text.md"
        shutil.copyfile(extpath, textmd)
        # meta.yaml
        fields = dict(s, raw_path=f"00_raw/{BATCH}/Neha 2/{s['raw']}", received=RECEIVED,
                      batch=BATCH, sha=sha)
        tmpl = CANON_META if s["kind"] == "canonical" else BIO_META
        (dest / "meta.yaml").write_text(tmpl.format(**fields))
        print(f"OK  {s['slug']:42} -> {s['dest']}/{s['lang']}/text.md  ({textmd.stat().st_size} B, sha {sha[:8]})")

if __name__ == "__main__":
    main()
