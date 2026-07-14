# OCR Quality Audit — 2026-07-14

Audited all 26 OCR-derived works in the corpus (identified via `text_extraction_method` containing tesseract/surya/ocr/vision/scan) by sampling 3-4 passages at ~15%/45%/75% through each `text.md`. **15 of 26 (58%) are GARBLED and should be re-sourced or re-OCR'd**, 10 are MINOR (readable, imperfect), 1 is CLEAN. The dominant failure mode is `tesseract`-on-Devanagari inserting spurious spaces *inside* words at matra/conjunct boundaries — almost every garbled Marathi/Hindi work shows the same signature (e.g. "वि " / "नि " / "कि " / "सि " / "दि " split from the syllable that follows: पारमार्थिक → "पारमार्थि क", निंबरगी → "नि ंबरगी"). English-only tesseract works are comparatively reliable (mostly MINOR — missing spaces, stray characters, but intact meaning). `ocrmypdf+tesseract` and plain `ocr-tesseract` both produce this failure on Devanagari; the one `ocr-surya` work (amrutavalli) and one `vision-llm-claude-sonnet` work (hindi-parmarth-sopan) are markedly cleaner, while the other vision-LLM work (pawanbhumi-jamkhandi) fails differently — hallucinated/incoherent Marathi captions rather than spacing corruption, alongside clean English/Kannada in the same document.

## Should re-source (garbled) — 15 works, worst first

| Work ID | Language(s) | Severity | Example | Extraction method |
|---|---|---|---|---|
| jivandarshan-deshpande | Marathi + Sanskrit/English quotes | GARBLED | "पारमाथि क", "नि मि त्ताने"; degenerates to mojibake in places: "10१202८ (9142 82818 ऋ" | ocr-tesseract |
| kannada-sahityatil-punyasmruti | Marathi (Devanagari — despite title, no actual Kannada script found in file) | GARBLED | "वि जापुरात मूत्रपि ंडाचा", "नि रोप गुरुदेवांनी दि ला"; 15% sample disintegrates into vertical character fragments ("नां / ाआ / स् / धी / व ह") | ocr-tesseract |
| vindication-of-indian-philosophy | English, with garbage Devanagari/symbol intrusions | GARBLED | "a champio Dayal—a sight for the Gods to look on" (word split/reflowed); garbage line "नाक (3 नन ... आय 20762 कह 5 क 094 107 मई" | ocr-tesseract |
| sadhakbodh | Marathi (letters) | GARBLED | "आ    च ार  प  ाहू न ,  स ाध  ू म्हण  व  न" (आचार पाहून, साधू म्हणवून) — severe and constant | ocr-tesseract |
| javak-patre-tipane | Marathi (letters) | GARBLED | "वडि लांप्रत वि शेष काही लि हि णे बालकास शक्य नाही" — pervasive throughout | ocrmypdf+tesseract (eng+mar+hin+san) |
| gurudev-paramarthik-shikvan | Marathi + Sanskrit quotes | GARBLED | "गुरुदेव रानडे : पारमाथि क शि कवण"; also nonsense English insertions ("meats", "fereaa") standing in for real words | ocrmypdf+tesseract (eng+mar+hin+san) |
| sonari-pane-2000 | Marathi | GARBLED | "पारमार्थि क अनुभवांची", "नि ंबरगी महाराजांच्या", "लि हि लेले पत्र" — nearly every matra/conjunct word affected | ocrmypdf+tesseract (eng+mar+hin+san) |
| kushal-pradhyapak | Marathi | GARBLED | "गुरुबंधू कि ंबा गुरुभगि नी होत", "सि द्धांतांचे वि वरण करतांना" | ocrmypdf+tesseract (eng+mar+hin+san) |
| allahabad-days-mr | Marathi | GARBLED | "कि ती", "वि द्यापीठाच्या", "पारमार्थि क", "सि टि ंग", "नामांकि त" — heavy, page-wide | ocrmypdf+tesseract (eng+mar+hin+san) |
| kannad-parmarth-sopan | Marathi + Kannada bhajans (transliterated into Devanagari, not Kannada script) | GARBLED | "वातवि ध्वेसि नी", "इंद्रि यांना जि कणे" | ocrmypdf+tesseract (eng+mar+hin+san) |
| parmartha-mandir | Marathi + Kannada bhajans (Devanagari transliteration) | GARBLED | "गुपि त मंत्रव वर गुरुगळ"; also pure-noise lines like "AR AR AR   A   RA" | ocrmypdf+tesseract (eng+mar+hin+san) |
| swanandacha-gabha | Marathi | GARBLED | "साक्षात्कारी agen पाहिलेले"; English fragments ("TACT") injected mid-Marathi sentence | tesseract mar+san+eng @300dpi |
| acpr-silver-jubilee-vol1 | English | GARBLED | "we shall attain silvation after death... in the Arman" (salvation/Atman); Devanagari digit mojibake mid-word: "the vision of the Light of the 171६7" | ocrmypdf+tesseract (eng+mar+hin+san) |
| acpr-silver-jubilee-vol2 | English | GARBLED | "end the mise                    ry from this world", "perpetual chan                    ge" — justified-column layout splits words with huge internal gaps | ocrmypdf+tesseract (eng+mar+hin+san) |
| pawanbhumi-jamkhandi | Trilingual: English/Kannada clean, Marathi captions garbled | GARBLED (Marathi portion only) | "महाराज उपकीसामील योगियांच्या..." — semantically incoherent/hallucinated Marathi caption, vs. fluent parallel English/Kannada in the same document | vision-llm-claude |

## Acceptable but imperfect (minor) — 10 works

| Work ID | Language(s) | Severity | Example | Extraction method |
|---|---|---|---|---|
| philosophical-and-other-essays | English + Greek transliteration, stray Devanagari intrusions | MINOR | "τλ light of such severe criticisms it would be better to ल्व." (random Devanagari glyph injected mid-English) | ocrmypdf+tesseract (eng+mar+hin+san) |
| pathway-to-god-in-the-vedas | English body + Sanskrit citation footnotes | MINOR (body); citation layer is GARBLED | body: "who 30075 the sacrificial halls"; citations: "हस्ते वि भ्रद्‌ भेषजा वार्या णि" — garbling confined to the Devanagari footnote layer | ocrmypdf+tesseract (eng+mar+hin+san) |
| nimbargi-maharaj-biography-en | English + embedded Devanagari/Kannada proverbs | MINOR (one embedded proverb unreadable) | "inthe second rate heroes" (merged words); proverb line is pure noise: "9७0०००३२०७ २०४९, ; जठरा 29०९," | ocr-tesseract |
| constructive-survey-of-upanishadic-philosophy | English + Sanskrit transliteration | MINOR | "Yajiiavalkya" (Yajñavalkya); irregular excess whitespace, not word-splitting | ocrmypdf+tesseract (eng+mar+hin+san) |
| creative-period | English + Sanskrit transliteration | MINOR | "22, THE Gops 45 THEY FARE" (Gods, AS) | ocrmypdf+tesseract (eng+mar+hin+san) |
| critical-constructive-aspects | English | MINOR | "we havea confluence", "smal]" (small) | ocrmypdf+tesseract (eng+mar+hin+san) |
| kakanchi-pravachane | Marathi (vols 1-3 pdftotext, vols 4-5 tesseract) | MINOR | pdftotext section: "इतकी पण्ु याई घालन\nू करतो" (matra reordered/split at line wrap); tesseract section is essentially clean | pdftotext -layout (v1-3) / tesseract mar+san+eng (v4-5) |
| amrutavalli | Marathi | MINOR | header/page-number garble "१४ । अमृतवही" (should read अमृतवल्ली consistently); body text well-segmented, no in-word spacing failure | ocr-surya |
| allahabad-days-en | English | MINOR | "misey" (misery); inserted Devanagari digit mid-word: "0८528 (opinion)" (doxa) | ocrmypdf+tesseract (eng+mar+hin+san) |
| ranade-and-his-spiritual-lineage | English | MINOR | "except      Kerosene" (stray spacing); "T / do not think" (I misread as T) | ocr-tesseract |

## Clean — 1 work

| Work ID | Language(s) | Severity | Example | Extraction method |
|---|---|---|---|---|
| hindi-parmarth-sopan | Hindi + English commentary, Sanskrit quotations | CLEAN | "संतप्तायसि संस्थितस्य पयसो नामापि न ज्ञायते । मुक्ताकारतया तदेव नलिनीपत्रस्थितं राजते ॥" — no spurious spaces, no substitutions, across all sample points | vision-llm-claude-sonnet |

## Notes for the operator

- The GARBLED-tier fix is unlikely to come from better tesseract tuning — every `ocrmypdf+tesseract` and plain `ocr-tesseract` Devanagari work shows the same failure, regardless of DPI or language-pack combination. The two non-tesseract methods in this corpus (`ocr-surya` on amrutavalli, `vision-llm-claude-sonnet` on hindi-parmarth-sopan) were both clean/minor — worth prioritizing vision-LLM or Surya re-extraction over hunting for new tesseract settings.
- `kannad-parmarth-sopan` and `parmartha-mandir` are not Kannada-script OCR failures — both are Marathi commentary plus Kannada *bhajans transliterated into Devanagari*, so re-sourcing should look for the same Devanagari edition, not a Kannada-script one. Likewise `kannada-sahityatil-punyasmruti`'s content is pure Devanagari despite its title.
- `pawanbhumi-jamkhandi` and `pathway-to-god-in-the-vedas` are the two "partial" cases — most of the document is fine; only a specific layer (Marathi captions in one, Sanskrit citations in the other) needs re-sourcing/re-OCR, so a full re-scan may not be necessary.
