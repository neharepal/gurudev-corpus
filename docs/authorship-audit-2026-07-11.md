# Authorship audit — 2026-07-11

Front-matter/preface review of all 66 ingested works with text (RFC-009 Step 4 authorship
verification). Triggered by `amar-sandesh-sudha` being mis-attributed to Gurudev. Method:
6 parallel readers, each reading title page + preface/प्रस्तावना + colophon.

## Corrections needed (21)

### A. Over-attributed to `gurudev_ranade` → actually about/compiled/edited by others
| id | should be author | nature | evidence |
|---|---|---|---|
| allahabad-days-en | B. R. Kulkarni (ed.) | biography | "A GLANCE AT HIS ALLAHABAD…DAYS…EDITOR B. R. KULKARNI, 1997" |
| allahabad-days-mr | Padya Kulkarni (trans.) | biography | Marathi anuvad of the above |
| amar-sandesh-sudha | Dadasaheb Deshpande (per operator; text: unnamed devotee) | compilation | devotee noted Gurudev's sayings from 1934, dedicated to Amburav Maharaj |
| contemporary-indian-philosophy | S. Radhakrishnan & J. H. Muirhead (eds.) | OTHER/anthology | 24-author anthology; Ranade = one contributor |
| devotees | Dilip R. Naik (compiler) | biography | "संकलन : श्री. दिलीप र. नाईक" |
| dhyangita-anvayarth | unattributed (compilation) | compilation | Gita shlokas + Marathi anvayarth; no Ranade claim |
| glimpses-of-sri-gurudev | B. R. Kulkarni (ed.) | compilation | "Editor B. R. Kulkarni"; reminiscences about Ranade |
| how-nimbal-was-chosen | unknown devotee | biography | 3rd-person account of Rambhau selecting Nimbal |
| jivandarshan-deshpande | Dadasaheb Deshpande | biography | preface signed "दादासाहेब देशपांडे" |
| kannad-parmarth-sopan | Padma Kulkarni (trans.) | OTHER | Marathi bhavanuvad of Kannada padas, 1992 |
| kannada-sahityatil-punyasmruti | anon devotee ("साधक") | athvani | Kannada disciples' memories, signed "- साधक" |
| kushal-pradhyapak | B. R. Kulkarni / Padma Kulkarni (trans.) | biography | "Ranade as a Teacher and Author" Marathi anuvad |
| pawanbhumi-jamkhandi | Gurudeo Ranade Paramarth Mandir Trust | biography | 125th-birthday birthplace booklet |
| punyasmruti | unnamed devotee compiler | compilation | "collected sayings and incidents of Shri Gurudev" |
| ranade-and-his-spiritual-lineage | V. H. Date | biography | "R. D. RANADE AND HIS SPIRITUAL LINEAGE / By V. H. DATE / 1982" |
| shri-gurudevanchya-athvani-2024 | devotees (compiler unnamed) | athvani | "गुरुदेवांची आठवण" anecdotes |
| shri-gurudevanchya-athvani-pustak | disciple narrator | athvani | 1st-person disciple recollections |

### B. Over-attributed to `nimbargi_maharaj` → actually about him
| id | should be author | nature | evidence |
|---|---|---|---|
| devotee | compilers (संकलक रावसाहेब शिंदे) | biography | "Charitra va Athvani" about Nimbargi |
| nimbargi-maharaj-biography-en | Disciples / ACPR Belgaum | biography | "'Disciples', ACPR Belgaum, 1978" |
| nimbargi-maharaj-charitra-athavani-mr | Disciples/compilers | athvani | reminiscences about Nimbargi |

### C. UNDER-attributed → actually Gurudev
| id | current | should be | evidence |
|---|---|---|---|
| studies-in-indian-philosophy | other_authors | gurudev_ranade (ed. B. R. Kulkarni) | "The Notes left by Gurudev R. D. Ranade…Editor can only add a foot-note" |

## Refine named author (currently generic `other_devotees`; not wrong, just vague)
- gurusamarpit-jivan → Moreshwar Shankar Rabade (bio of V. H. Date)
- sonari-pane-2000 → Padma Kulkarni
- radhabai-limaye-charitra → G. V. Tulpule

## Verified OK — genuine own-works (no change)
Gurudev: bhagavadgita-as-pathway, constructive-survey, creative-period (w/ Belvalkar),
essays-and-reflections, evolution-of-my-own-thought, gandhi-and-other-indian-saints,
herakleitos, hindi-parmarth-sopan, lachyan-sandesh, mysticism-in-maharashtra,
opportunities-of-college-life, parmartha-mandir (Gurudev = named संकलनकार), parmartha-sopan,
pathway-to-god-in-hindi-literature, pathway-to-god-in-kannada-literature,
philosophical-and-other-essays, reflections, vedant, vindication-of-indian-philosophy, gurudeos-abhang.
Kakasaheb: maharajachi-sutre, kakanchi-charcha, kakanchi-pravachane, bhagvadgeeta, sadhakbodh,
sadhakachi-atmakatha, gurudev-paramarthik-shikvan, sukhasahita-dukharahita.
Others (correct): bodhsudha (Nimbargi), javak-patre-tipane (Bhausaheb), critical-constructive-aspects
(B.R. Kulkarni), pathway-to-god-in-the-vedas (Sangoram/Kulkarni), patankar-pravachan-3,
n-g-damle-pravachan, sevenfold-stream, studies…(see C), matoshri-sharakka, amrutavalli, swanandacha-gabha, charitra-tatvajnan-tulpule, guru-ha-parabrahma-kewal, acpr-silver-jubilee-vol1/2.

## Note on compilations (amar-sandesh-sudha, punyasmruti, dhyangita-anvayarth, glimpses)
These contain Gurudev's actual words/sayings compiled by a devotee. Per SYSTEM_PROMPT_QA
("athvani recording a master's spoken teaching count as primary for that teaching"), the
CONTENT stays quotable as Gurudev's teaching — but `author` = the compiler, so "who wrote
this" answers correctly. Same principle as the arthasahit retrieve-vs-cite decision.
