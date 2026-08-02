"""Vol 2 targeted fixes — Phase 3.5 per QA report (RFC-020).

Reads   staging/kakanchi-pravachane-vol2.clean.md
Writes  staging/kakanchi-pravachane-vol2.v2.md
Writes  staging/vol2_changes.md    (per-fix change log with counts)

Every fix uses a context-anchored old->new pair with an expected occurrence
count. If count doesn't match, we log a WARN and skip that fix — never a
silent partial-apply.

Class A : unambiguous find/replace (year, OCR nonwords, punctuation)
Class A+: structural insertion — the missing `पुष्प २` chapter marker
Class B : items requiring human judgment (listed at the bottom, unchanged)
Class C : chapter-end blessing normalization to the canonical form
"""
from __future__ import annotations
from pathlib import Path

SRC = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol2.clean.md')
DST = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol2.v2.md')
LOG = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/vol2_changes.md')

log_lines: list[str] = ['# Vol 2 — Phase 3.5 change log\n']
applied = 0
skipped = 0


def do(text: str, tag: str, old: str, new: str, expected: int, note: str = '') -> str:
    """Apply an exact-string replacement. Warn + skip if count != expected."""
    global applied, skipped
    n = text.count(old)
    if n != expected:
        log_lines.append(
            f'### {tag} — SKIPPED (expected {expected} matches, found {n})\n'
            f'- **Old:** `{old!r}`\n'
            f'- **New:** `{new!r}`\n'
            f'{"- **Note:** " + note if note else ""}\n'
        )
        skipped += 1
        return text
    applied += 1
    log_lines.append(
        f'### {tag} — OK {n}x ({note or ""})\n'
        f'- **Old:** `{old}`\n'
        f'- **New:** `{new}`\n'
    )
    return text.replace(old, new)


text = SRC.read_text(encoding='utf-8')
orig_bytes = len(text.encode('utf-8'))
orig_lines = text.count('\n')

# ─── Class A+: HIGH-SEVERITY structural fix — missing पुष्प २ marker ──
#
# QA F1: chapter marker for पुष्प २ was dropped entirely. Content between
# ~L129 and ~L371 is the second discourse (Bhausaheb Maharaj's letters /
# sutras — `आठव तो ब्रह्म` etc.) but the chapter header is missing.
#
# Anchor uses the pre-normalization blessing text at line 127 immediately
# followed by the opening prose at line 129 — this pair is unique in the
# file, so we can wedge the header cleanly between them. We do this BEFORE
# the C-blessing normalization so the anchor is still intact.
#
# Header format follows the `पुष्प ४ - साधकबोध` pattern (dash + title).
old_f1 = (
    '। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।\n'
    '\n'
    'श्रीभाऊसाहेब महाराजांची पत्रे'
)
new_f1 = (
    '। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।\n'
    '\n'
    'पुष्प २ - श्रीभाऊसाहेब महाराजांची पत्रे\n'
    '\n'
    'श्रीभाऊसाहेब महाराजांची पत्रे'
)
text = do(text, 'F1', old_f1, new_f1, 1,
          'HIGH: insert missing chapter-2 header between L127 blessing and L129 prose')

# ─── Class A: unambiguous find/replace ────────────────────────────────

# F2: OCR read ९ as ० in the year "१९२१"
text = do(text, 'F2', 'कारण १०२१ च्या', 'कारण १९२१ च्या', 1,
          'L27: OCR ० → ९ in year 1921 (parallel passage L443 confirms)')

# F5: not-a-word अधुनिक → आधुनिक (both instances on L53)
text = do(text, 'F5', 'अधुनिक', 'आधुनिक', 2,
          'L53: two occurrences of the OCR nonword')

# F7: glyph-reordered िमागावी → मागावी
text = do(text, 'F7', 'मला िमागावी लागत', 'मला मागावी लागत', 1,
          'L1044: matra `ि` was detached and placed before the base consonant')

# F8a: मी-माई → मी-माझी (matches every other occurrence in the file)
# NOTE: F8b (`ढव` fragment on same line) is Class B — logged below.
text = do(text, 'F8a', 'सगळे मी-माई यांचे', 'सगळे मी-माझी यांचे', 1,
          'L280: OCR ई → झी; parallel usage L335, L355, L653, L655 confirms')

# F9: stray Latin `M ` embedded in Devanagari
text = do(text, 'F9', 'प्रणवादि M ओंकार', 'प्रणवादि ओंकार', 1,
          'L246: OCR artifact — bare Latin M inside a Marathi word')

# F10: leftover page-marker `५४ अंक` on its own line between prose paragraphs
text = do(text, 'F10',
          'तास दोन तास तरी\n\n५४ अंक\n\nआपण देवाकरता',
          'तास दोन तास तरी आपण देवाकरता', 1,
          'L296: page-marker leaked through the page-number strip')

# F11: garbled अशात्केने → अशा तऱ्हेने (used consistently elsewhere)
text = do(text, 'F11', 'अशात्केने परमेश्वराचं', 'अशा तऱ्हेने परमेश्वराचं', 1,
          'L367: garbled — parallel L121, L415, L1038, L1136 use `अशा तऱ्हेने`')

# F13: quote-in-prose left unclosed. Insert closing quote + period after तन्मयता.
text = do(text, 'F13',
          "म्हटलेलं आहे की 'वेधेचि तन्मयता अनुभव देवाचा",
          "म्हटलेलं आहे की 'वेधेचि तन्मयता'. अनुभव देवाचा", 1,
          'L313: close the quote after `तन्मयता` — next clause is fresh prose')

# F14: garbled कृपीकडे → कृतीकडे (paragraph earlier uses कृतीत)
text = do(text, 'F14', 'कृपीकडे झाला पाहिजे', 'कृतीकडे झाला पाहिजे', 1,
          'L729: OCR त → प; sentence 2 lines earlier uses `कृती`')

# F17: garbled झदिशी → चटदिशी (author uses चटदिशी elsewhere — L15, L713, L1207)
text = do(text, 'F17', 'दिसतं. झदिशी आपण', 'दिसतं. चटदिशी आपण', 1,
          'L1227: OCR चट → झ')

# F18: bare citation prefix `इ.` → `जा.` (matches L521 parallel citation)
text = do(text, 'F18', 'मीचि होईल | (इ. १२-१०२)', 'मीचि होईल | (जा. १२-१०९)', 1,
          'L1317: bare `इ.` not used anywhere else; L521 has `(जा १२-१०९)` for same ovi')

# F19a: ताव्हा → तेव्हा (OCR e→a)
text = do(text, 'F19a', 'आहे. ताव्हा देवाला', 'आहे. तेव्हा देवाला', 1,
          'L1333: OCR ते → ता')
# F19b: माही. → माहित नाही. (truncated word restored)
text = do(text, 'F19b', 'दुसऱ्या कोणाला माही.', 'दुसऱ्या कोणाला माहित नाही.', 1,
          'L1333: truncated — context requires `माहित नाही.`')

# F20a: साखवेळा → लाखवेळा (goes with हजारवेळा; OCR ल → स)
text = do(text, 'F20a', 'हजारवेळा, साखवेळा जेव्हा', 'हजारवेळा, लाखवेळा जेव्हा', 1,
          'L1337: OCR ल → स')
# F20b: stray `म ` before जगातल्या
text = do(text, 'F20b', 'असं होत गेलं म्हणजे म जगातल्या',
          'असं होत गेलं म्हणजे जगातल्या', 1,
          'L1335: stray Devanagari `म` — OCR artifact')

# F21: काहा → काही
text = do(text, 'F21', 'काहा दोष झाले तरी', 'काही दोष झाले तरी', 1,
          'L683: OCR ी → ा')

# F22: जोरा → जोर (same paragraph uses जोर correctly)
text = do(text, 'F22', 'कोणी कोणावर जोरा केलाय', 'कोणी कोणावर जोर केलाय', 1,
          'L1239: extra ा')

# F23: पता → पत्ता (Hindi form → Marathi form in an all-Marathi paragraph)
text = do(text, 'F23', 'पता आहे का आपला', 'पत्ता आहे का आपला', 1,
          'L501: OCR त्त → त')

# F24: missing period after आहे between two sentences
text = do(text, 'F24',
          'रहिमत खाँ सारखा गवई आहे एकदा जरी गाताना',
          'रहिमत खाँ सारखा गवई आहे. एकदा जरी गाताना', 1,
          'L564: insert missing sentence-boundary period')

# F25: stray `-a )` fragment inside the English footnote quotation
text = do(text, 'F25', 'spiritual -a ) achievement.', 'spiritual achievement.', 1,
          "L103: OCR broke `spiritual achievement`, leaving `-a )` stub inside quote")

# F26: straight double quote `?"` → single closing quote `?'` for consistency
text = do(text, 'F26', 'त्याला काय सांगायचं ?" असं आहे ते.',
          "त्याला काय सांगायचं ?' असं आहे ते.", 1,
          'L1098: straight `"` breaks the surrounding single-quote dialogue style')

# F28: बोधले → बोधरवी (glosses the preceding verse `प्रचंड तो बोधरवी उदेला`)
text = do(text, 'F28',
          'बोधले म्हणजे बौद्धिक ज्ञान नाही. बोधले म्हणजे प्रत्यक्ष दर्शन.',
          'बोधरवी म्हणजे बौद्धिक ज्ञान नाही. बोधरवी म्हणजे प्रत्यक्ष दर्शन.', 1,
          'L610: 2x — glosses the shloka word `बोधरवी` (L606), not the OCR ghost `बोधले`')

# ─── Class A (bad_rejoin): sentence fragment reordering ──────────────

# F3: word chunks `अनाकलनीय आहेत.` and `नाही.` swapped positions
# Original:   ... आकलन मुळीच झालं अनाकलनीय आहेत. नाही. इतक्या त्या
# Corrected:  ... आकलन मुळीच झालं नाही. इतक्या त्या अनाकलनीय आहेत.
text = do(text, 'F3',
          'याचं आकलन मुळीच झालं अनाकलनीय आहेत. नाही. इतक्या त्या',
          'याचं आकलन मुळीच झालं नाही. इतक्या त्या अनाकलनीय आहेत.', 1,
          'L79: bad_rejoin — clean reordering of two adjacent fragments')

# F4: `आहे.` was pulled forward into the second clause
# Original:   ... मनाचाच संबंध मनुष्य चिंतन केल्याशिवाय, विचार आहे. केल्याशिवाय राहत नाही.
# Corrected:  ... मनाचाच संबंध आहे. मनुष्य चिंतन केल्याशिवाय, विचार केल्याशिवाय राहत नाही.
text = do(text, 'F4',
          'मनाचाच संबंध मनुष्य चिंतन केल्याशिवाय, विचार आहे. केल्याशिवाय राहत नाही.',
          'मनाचाच संबंध आहे. मनुष्य चिंतन केल्याशिवाय, विचार केल्याशिवाय राहत नाही.', 1,
          'L226: bad_rejoin — `आहे.` restored to first clause')

# ─── Class C: chapter-end blessing normalization to one canonical form ──
#
# Task-specified canonical: `॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥`
# (double danda + outer spaces, no `श्री`, `सद्गुरुनाथ` fused with short `ु`)
#
# Vol 2 variants observed (grep):
#   `। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।`    — 3 occurrences (L127, L657, L747)
#   `॥ राजाधिराज श्रीसद्गुरूनाथ महाराज की जय ॥`   — 1 occurrence  (L371) [long ू]
#   `|राजाधिराज श्रीसद्गुरुनाथ महाराज की जय |`     — 1 occurrence  (L1167) [pipes]
canonical_bless = '॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥'
for tag, old_bless, count_hint, note in [
    ('C_a', '। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।', 3,
     'single danda, extra श्री'),
    ('C_b', '॥ राजाधिराज श्रीसद्गुरूनाथ महाराज की जय ॥', 1,
     'long-ू variant, extra श्री'),
    ('C_c', '|राजाधिराज श्रीसद्गुरुनाथ महाराज की जय |', 1,
     'ASCII pipes, no outer spaces, extra श्री'),
]:
    text = do(text, tag, old_bless, canonical_bless, count_hint,
              f'blessing normalization — {note}')

# ─── Write output + log ──────────────────────────────────────────────────

DST.write_text(text, encoding='utf-8')
new_bytes = len(text.encode('utf-8'))
new_lines = text.count('\n')

# ─── Class B: findings left UNCHANGED (need human judgment) ────────────
#
# These items appear in the QA report but require reviewer decisions that
# cannot be made from surrounding context alone. Listed here for the log so
# a human reviewer can track what remains.
log_lines.append('\n---\n\n## Class B — LEFT UNCHANGED (human review needed)\n')
log_lines.append(
    '- **F6 (L647)**: scrambled sentence with multiple missing/dropped words '
    '(`भजी नाही. खाणं...`). QA explicitly says "Unclear — human reviewer '
    'needed." Reconstruction requires knowing the original text.\n'
)
log_lines.append(
    '- **F8b (L280)**: truncated fragment `ढव` inside `वाढवीत, वाढवीत, ढव सगळे`. '
    'QA suggests either delete or expand to `वाढवीत` — ambiguous. `मी-माई` on '
    'the same line was fixed (F8a).\n'
)
log_lines.append(
    '- **F12 (L39, L443)**: `खटे` used twice for bedsores/pits. QA suggests '
    '`खड्डे` or `खटले` but is not certain — human reviewer needed.\n'
)
log_lines.append(
    '- **F15 (L1032)**: `जीवाही अगोज पडती आघात` — `अगोज` is not a word. QA '
    'flags this abhang line as needing a Tukaram-gatha edition check.\n'
)
log_lines.append(
    '- **F16 (L982)**: `असा आनंद ला पाहिजे` — a verb is missing before '
    '`ला पाहिजे`. Candidates: `लागला`, `मिळाला`, `लाभला`. Human reviewer needed.\n'
)
log_lines.append(
    '- **F27 (L1146, L1148, L1152)**: same abhang word spelled `डवरली` in '
    'prose gloss but `डौरली` in the abhang line. QA says human reviewer to '
    'check a canonical abhang edition before normalizing either direction.\n'
)

# ─── Known source-truncation NOT fixed ────────────────────────────────
log_lines.append('\n---\n\n## Known source truncation (not fixed)\n')
log_lines.append(
    '- File ends at line 1337 mid-sentence with `...बुद्धीने हे समजून`. This is '
    'the underlying PDF truncation and is out of scope for QA text fixes.\n'
)

log_lines.insert(1,
    f'**Applied:** {applied} fixes\n'
    f'**Skipped (mismatched count):** {skipped}\n'
    f'**Bytes:** {orig_bytes:,} → {new_bytes:,} ({new_bytes - orig_bytes:+,})\n'
    f'**Lines:** {orig_lines:,} → {new_lines:,} ({new_lines - orig_lines:+,})\n'
    f'\n---\n'
)
LOG.write_text('\n'.join(log_lines), encoding='utf-8')

print(f'Applied {applied}, skipped {skipped}. Wrote {DST} and {LOG}.')
