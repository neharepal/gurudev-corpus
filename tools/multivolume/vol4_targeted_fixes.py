"""Vol 4 targeted fixes — Phase 3.5 per QA report (RFC-020).

Reads   staging/kakanchi-pravachane-vol4.clean.md
Writes  staging/kakanchi-pravachane-vol4.v2.md
Writes  staging/vol4_changes.md    (per-fix change log with counts)

Every fix uses a context-anchored old->new pair with an expected occurrence
count. If count doesn't match, we log a WARN and skip that fix — never a
silent partial-apply.

Vol 4 is the verse-heaviest volume:
- F1  TOC collapsed at L33 — rebuild 11 chapter entries
- F2  seven `कीर्ती → कीती` misreads in one paragraph L205 + one `किती वाढावी`
- F3  Bodhasudha OCR block L2457-2471: सद्बुद्धी/सद्वासना misread as सद्गुळी/सद्गासना
- F7  four `खड्ग → खड.ग` (halant + ग OCR'd as literal period)
- F8  Gita 2.63 mangled sandhi (सम्मोहात्म्मृतिविभ्रमः → सम्मोहात्स्मृतिविभ्रमः)
- Verse restructures: Radhaswami पद L1748, Tukaram L1068, Eknath L554,
  Manache Shloka #127 L1778 and #128 L1892
- Class B (skipped for human review): F21 हे/ते नाम; F22 two Tukaram transcripts;
  F27 stray २१.२४; F28 Manache Shloka 145 canonical spelling.
- Class C: `सदुरु → सद्गुरु` normalization, F25/F30 citation fixes,
  chapter-end blessing normalization.
"""
from __future__ import annotations
from pathlib import Path

SRC = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol4.clean.md')
DST = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol4.v2.md')
LOG = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/vol4_changes.md')

log_lines: list[str] = ['# Vol 4 — Phase 3.5 change log\n']
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

# ─── F1: TOC block reconstruction ────────────────────────────────────────
# Current TOC has:
#   L31: संकटाच्या पायऱ्यांनी परमार्थसोपान चढणारे गुरुदेव.   (ch 1, alone)
#   L33: 10 chapter titles glued into one long line (chs 2-11)
#   L35: परिशिष्ट १ - हौदाची उपमा

old_toc = (
    'संकटाच्या पायऱ्यांनी परमार्थसोपान चढणारे गुरुदेव.\n\n'
    'गुरुदेवांचे तत्त्वज्ञान व परमार्थ सोपान नामसाधनाचा मानसशास्त्राच्या दृष्टीने विचार १ '
    'नामसाधनाचा मानसशास्त्राच्या दृष्टीने विचार २ नवविधा भक्ती सत्संगती '
    'श्रद्धावान् लभते ज्ञानम् -१ श्रद्धावान् लभते ज्ञानम् -२ मनाचे श्लोक भाग १ '
    'मनाचे श्लोक भाग २ श्री निबर्गी महाराजांची बोधसुधा\n\n'
    'परिशिष्ट १ - हौदाची उपमा'
)
new_toc = (
    '१. संकटाच्या पायऱ्यांनी परमार्थ सोपान चढणारे गुरुदेव\n\n'
    '२. गुरुदेवांचे तत्त्वज्ञान व परमार्थ सोपान\n\n'
    '३. नामसाधनाचा मानसशास्त्राच्या दृष्टीने विचार (भाग १)\n\n'
    '४. नामसाधनाचा मानसशास्त्राच्या दृष्टीने विचार (भाग २)\n\n'
    '५. नवविधा भक्ती\n\n'
    '६. सत्संगती\n\n'
    '७. श्रद्धावान् लभते ज्ञानम् -१\n\n'
    '८. श्रद्धावान् लभते ज्ञानम् -२\n\n'
    '९. मनाचे श्लोक - भाग १\n\n'
    '१०. मनाचे श्लोक - भाग २\n\n'
    '११. श्रीनिबर्गीमहाराजांची बोधसुधा\n\n'
    'परिशिष्ट - १  हौदाची उपमा'
)
text = do(text, 'F1', old_toc, new_toc, 1,
          'TOC L31-35 rebuilt: 11 chapter entries + appendix')

# ─── F2: कीर्ती mis-OCR'd as कीती (8x on L205 + 1x on L2429) ─────────────
# Use paragraph-scope anchoring so we only touch the affected sentence
# without clobbering the correct `कीती` on other lines (there aren't any
# elsewhere — grep -c कीती = 9; all 9 are misreads. But we still fix each
# with local context to be safe.)

# L205: the whole paragraph is one line, containing 7 x कीती + 1 x किती वाढावी
# Do it as one atomic swap on the entire paragraph.
old_f2 = (
    'महाराजांची किती वाढावी, देवाची कीती वाढावी, असे सामर्थ्य परमेश्वराने दिलेले आहे परंतु आयुष्यच जर उरलं नाही तर काय करायचे?\' त्यांना मृत्यूची भीती मुळीच नव्हती. त्यांना जगायचं काही कारणही नव्हतं. पण परमेश्वराचा आणखी आनंद घ्यावा एवढ्या करता एक जगायचं आणि दुसरे जगाला परमार्थ सांगण्याकरता जगायचं. तेव्हा सद्गुरूंची कीती वाढवणं, देवाची कीती वाढवणं याचे काय महत्त्व आहे हे मला कळत नव्हतं. पण पुढे असं सहजच कळून आलं की परमार्थाची कीती वाढवणं, देवाची कीती वाढवणं याचा अर्थ जगदुध्दाराचा मार्ग जगाला सांगणं. देवालाही कीती नको आहे, सद्गुरूंनाही कीती नको आहे. परंतु यांची कीती वाढवणे'
)
new_f2 = (
    'महाराजांची कीर्ती वाढावी, देवाची कीर्ती वाढावी, असे सामर्थ्य परमेश्वराने दिलेले आहे परंतु आयुष्यच जर उरलं नाही तर काय करायचे?\' त्यांना मृत्यूची भीती मुळीच नव्हती. त्यांना जगायचं काही कारणही नव्हतं. पण परमेश्वराचा आणखी आनंद घ्यावा एवढ्या करता एक जगायचं आणि दुसरे जगाला परमार्थ सांगण्याकरता जगायचं. तेव्हा सद्गुरूंची कीर्ती वाढवणं, देवाची कीर्ती वाढवणं याचे काय महत्त्व आहे हे मला कळत नव्हतं. पण पुढे असं सहजच कळून आलं की परमार्थाची कीर्ती वाढवणं, देवाची कीर्ती वाढवणं याचा अर्थ जगदुध्दाराचा मार्ग जगाला सांगणं. देवालाही कीर्ती नको आहे, सद्गुरूंनाही कीर्ती नको आहे. परंतु यांची कीर्ती वाढवणे'
)
text = do(text, 'F2a', old_f2, new_f2, 1,
          'L205: 7 कीती→कीर्ती + 1 किती वाढावी → कीर्ती वाढावी in one atomic swap')

# L2429: single `कीती प्रारब्ध बदलेल`
text = do(text, 'F2b',
          'किती भक्ती करून कीती प्रारब्ध बदलेल',
          'किती भक्ती करून किती प्रारब्ध बदलेल', 1,
          'L2429: this is the Marathi word "किती" (how much), not कीर्ती — OCR was fine here, QA misread. See below.')

# NOTE on F2b: on closer read, `किती भक्ती करून किती प्रारब्ध बदलेल` (how much
# devotion changes how much karma) is the natural reading. QA F2's suggestion
# that L2429's `कीती` = `कीर्ती` doesn't fit the sentence semantically. So
# we normalize `कीती → किती` (correct Marathi word) rather than to `कीर्ती`.

# ─── F3: Bodhasudha OCR block — सद्बुद्धी mis-read as सद्गुळी etc. ────
# Section L2457-2471. Also fix the heading label at L2457 (starts with
# "सद्गुळी – " which is the mis-OCR'd section header for `सद्बुद्धी –`).

# All 7 `सद्गुळी` → सद्बुद्धी (heading + inline uses)
text = do(text, 'F3a', 'सद्गुळी', 'सद्बुद्धी', 7,
          'सद्गुळी → सद्बुद्धी (7x incl. heading label at L2457)')

# 1x `सद्गुधि` (in Jnaneshvari citation L2459) → सद्बुध्दि
# (matches the correct form at L562: `तैसी दुर्लभ जे सद्बुध्दि`)
text = do(text, 'F3b', 'सद्गुधि', 'सद्बुध्दि', 1,
          'सद्गुधि → सद्बुध्दि (Jnaneshvari cite L2459, matches L562)')

# 1x `सद्गासना` (L2471) → सद्वासना
text = do(text, 'F3c', 'सद्गासना', 'सद्वासना', 1,
          'सद्गासना → सद्वासना (Jnaneshvari cite L2471)')

# 1x `दुर्बुळी` (L2457) → दुर्बुद्धी (parallel to सद्बुद्धी fix)
text = do(text, 'F3d', 'दुर्बुळी', 'दुर्बुद्धी', 1,
          'दुर्बुळी → दुर्बुद्धी (L2457 — parallel term)')

# ─── F5: L219 सतराव्या (17th) → एकसत्तराव्या (71st) + किर्तीचा → कीर्तीचा ────
# Context makes explicit this is the 71st year (amrut mahotsav). Fix both in
# one atomic anchor for safety.
text = do(text, 'F5',
          'सतराव्या वर्षी त्यांच्या किर्तीचा व यशाचा जणू काही कळस झाला',
          'एकसत्तराव्या वर्षी त्यांच्या कीर्तीचा व यशाचा जणू काही कळस झाला', 1,
          'L219: 17th → 71st + fix कीर्तीचा spelling')

# ─── F6: L2497 महाराजरवरवचन → महाराजवरवचन ────
text = do(text, 'F6', 'महाराजरवरवचन', 'महाराजवरवचन', 1,
          'L2497: extra र typo (title correct at L2336)')

# ─── F7: खड.ग → खड्ग (four occurrences near L2537-2543) ─────────────────
# The halant + ग got OCR'd as a literal period.
text = do(text, 'F7a', 'ध्यान खड.गानी', 'ध्यान खड्गानी', 1,
          'L2537: खड्ग restoration')
text = do(text, 'F7b', 'ध्यानाच्या खड.गाने', 'ध्यानाच्या खड्गाने', 1,
          'L2541: खड्ग restoration')
text = do(text, 'F7c', 'ध्यान खड.गाचा', 'ध्यान खड्गाचा', 1,
          'L2543: खड्ग restoration')

# ─── F8: Gita 2.63 mangled sandhi ────────────────────────────────────────
# सम्मोहात्म्मृतिविभ्रमः → सम्मोहात्स्मृतिविभ्रमः
text = do(text, 'F8', 'सम्मोहात्म्मृतिविभ्रमः', 'सम्मोहात्स्मृतिविभ्रमः', 1,
          'L501: Gita 2.63 correct sandhi')

# ─── F9: Gita 18.40 missing त् in sandhi + hyphen tag ────────────────────
text = do(text, 'F9',
          'यदेभिः स्यात्रिभिर्गुणैः ॥- गी.१८-४०',
          'यदेभिः स्यात्त्रिभिर्गुणैः ॥ गी.१८-४०', 1,
          'L2056: Gita 18.40 restoration')

# ─── F10: Kathopanishad citation garbled ─────────────────────────────────
# `मुंजात्इव ईषिकान् धैर्येण।कठ.६.१७` → `मुञ्जादिवेषीकां धैर्येण ॥ कठ.२.३.१७`
text = do(text, 'F10',
          'मुंजात्इव ईषिकान् धैर्येण।कठ.६.१७',
          'मुञ्जादिवेषीकां धैर्येण ॥ कठ.२.३.१७', 1,
          'L2499: Katha citation restored + correct verse ref')

# ─── F12: Tukaram abhang tu.gа.907 missing pada-break ────────────────────
text = do(text, 'F12',
          'षडउर्मी हृदयांत यांचा अंत पुरवूनि ।',
          'षडउर्मी हृदयांत । यांचा अंत पुरवूनि ।', 1,
          'L466: insert pada-break between हृदयांत and यांचा')

# ─── F18: Gita 2.64 punctuation `गी.२-६,४` → `॥ गी.२-६४` ─────────────────
text = do(text, 'F18',
          'प्रसादमधिगच्छति ॥गी.२-६,४',
          'प्रसादमधिगच्छति ॥ गी.२-६४', 1,
          'L510: Gita 2.64 comma→64 + space after ॥')

# ─── F20: कृतिपर्यवसाने[न/व] — normalize to whichever matches source ─────
# QA suggests `-नेव` (with व) is the correct sandhi; L343 has it correctly.
# L397 and L443 have `-नेन`. Normalize L397 & L443 to `-नेव`.
text = do(text, 'F20', 'कृतिपर्यवसानेन मता तीव्र मुमुक्षुता',
          'कृतिपर्यवसानेव मता तीव्र मुमुक्षुता', 2,
          'L397, L443: normalize to कृतिपर्यवसानेव (matches L343)')

# ─── F25: Gita 4.34 mis-cited as 2.34 at L1390 ───────────────────────────
text = do(text, 'F25',
          'ज्ञानिनस्तत्त्वदर्शिनः॥ गी.२.३४',
          'ज्ञानिनस्तत्त्वदर्शिनः॥ गी.४.३४', 1,
          'L1390: 2.34 → 4.34 (verse is Gita 4.34)')

# ─── F26: L1418 तत्त्वुदयः run-together + wrong reading ────────────────
# `तत्त्वुदयः तदात्मानः तन्निष्ठः तत्परायणः` → `तद्बुद्धयस्तदात्मानस्तन्निष्ठास्तत्परायणाः`
text = do(text, 'F26',
          'तत्त्वुदयः तदात्मानः तन्निष्ठः तत्परायणः',
          'तद्बुद्धयस्तदात्मानस्तन्निष्ठास्तत्परायणाः', 1,
          'L1418: Gita 5.17 correct reading')

# ─── F29: English "Unision" typo → "Union" ──────────────────────────────
text = do(text, 'F29', 'Unision', 'Union', 1, 'L2609: Unision → Union')

# ─── F30: Gita 4.38 mis-cited as 2.38 at L1396 ───────────────────────────
text = do(text, 'F30',
          'कालेनात्मनि विन्दति॥ गी.२.३८',
          'कालेनात्मनि विन्दति॥ गी.४.३८', 1,
          'L1396: 2.38 → 4.38')

# ─── Class A+ — verse-block reformatting (multi-line restructures) ──────

# F13: Eknath abhang at L554 collapsed to one prose line
old_f13 = 'माझ्या मनाचे जे मन चरणी ठेवावे बांधून । मग ते जाऊ न शके कोठे । राहे तुमच्या नेहटे। मनासी ते बळ देवा तुमचे केवळ। एका जनार्दनी देवा मन दृढ पायी ठेवा॥'
new_f13 = (
    'माझ्या मनाचे जे मन चरणी ठेवावे बांधून ।\n'
    'मग ते जाऊ न शके कोठे । राहे तुमच्या नेहटे ।\n'
    'मनासी ते बळ देवा तुमचे केवळ ।\n'
    'एका जनार्दनी देवा मन दृढ पायी ठेवा ॥'
)
text = do(text, 'F13', old_f13, new_f13, 1,
          'L554 Eknath abhang — split at each danda into padas')

# F14: Radhaswami पद at L1748 collapsed
old_f14 = 'यह तन पिंजरा कालका । क्या करें पराई आस । दस इंद्री के भोग की । तेरे पडी गले में फांस । नौ द्वारन में बंद रही । अब चैन नहीं एक स्वास । दसवीं खिडकी खोल री । कर परम विलास । राधास्वामी नाम भजो । होय कर्म सब नाश ॥'
new_f14 = (
    'यह तन पिंजरा कालका । क्या करें पराई आस ।\n'
    'दस इंद्री के भोग की । तेरे पडी गले में फांस ।\n'
    'नौ द्वारन में बंद रही । अब चैन नहीं एक स्वास ।\n'
    'दसवीं खिडकी खोल री । कर परम विलास ।\n'
    'राधास्वामी नाम भजो । होय कर्म सब नाश ॥'
)
text = do(text, 'F14', old_f14, new_f14, 1,
          'L1748 Radhaswami पद — 5 pada-pairs each on own line')

# F15: Manache Shloka #127 collapsed at L1778
old_f15 = 'जगी धन्य तो रामसूखें निवाला । कथा ऐकतां सर्व तल्लीन जाला॥ देहेभावना रामबोधे उडाली॥ मनोवासना रामरूपीं बुडाली॥ म.श्लो.१२७'
new_f15 = (
    'जगी धन्य तो रामसूखें निवाला । कथा ऐकतां सर्व तल्लीन जाला ॥\n'
    'देहेभावना रामबोधे उडाली । मनोवासना रामरूपीं बुडाली ॥ म.श्लो.१२७'
)
text = do(text, 'F15', old_f15, new_f15, 1,
          'L1778 Manache Shloka #127 — split into 2 lines')

# F16: Tukaram "संतांचिये गावी" abhang at L1068 collapsed
old_f16 = 'संतांचिये गावी प्रेमाचा सुकाळ । नाही तळमळ दुःखलेश । तेथे मी राहीन होऊनि याचक । घालितील भीक तेचि मज ॥ संतांचिये गावी वरो भांडवल । अवघा विठ्ठल घन वित्त । संतांचे भोजन अमृताचें पान । करिती कीर्तन सर्वकाळ ॥ संतांचा उदीम उपदेशाची पेठ । प्रेमसुख साटी घेती देती ॥ तुका म्हणे तेथे आणीक नाही परी । म्हणोनि भिकारी झालो त्यांचा ॥तु.गा.७१३.'
new_f16 = (
    'संतांचिये गावी प्रेमाचा सुकाळ । नाही तळमळ दुःखलेश ।\n'
    'तेथे मी राहीन होऊनि याचक । घालितील भीक तेचि मज ॥\n'
    'संतांचिये गावी वरो भांडवल । अवघा विठ्ठल घन वित्त ।\n'
    'संतांचे भोजन अमृताचें पान । करिती कीर्तन सर्वकाळ ॥\n'
    'संतांचा उदीम उपदेशाची पेठ । प्रेमसुख साटी घेती देती ॥\n'
    'तुका म्हणे तेथे आणीक नाही परी । म्हणोनि भिकारी झालो त्यांचा ॥\n'
    'तु.गा.७१३.'
)
text = do(text, 'F16', old_f16, new_f16, 1,
          'L1068 Tukaram abhang — 4 charans + closing tuka pada on own lines')

# F17: Manache Shloka #128 at L1892-1893 (spans two source lines with
# a hard-wrap mid-pada). Restore proper 4-pada layout.
old_f17 = 'मना वासना वासूदेवी वसो दे। मना कामना काम संगी नसो दे। मना\nकल्पना वाऊगी ते न कीजे। मना सज्जना सज्जनी वस्ती कीजे। म.श्लो.१२८'
new_f17 = (
    'मना वासना वासूदेवी वसो दे । मना कामना कामसंगी नसो दे ।\n'
    'मना कल्पना वाऊगी ते न कीजे । मना सज्जना सज्जनी वस्ती कीजे ॥ म.श्लो.१२८'
)
text = do(text, 'F17', old_f17, new_f17, 1,
          'L1892 Manache Shloka #128 — restore pada layout across the hard-wrap')

# ─── Class C: सदुरु → सद्गुरु normalization ─────────────────────────────
# grep found 6 occurrences of सदुरु across 4 lines (223, 229, 231, 1480).
# All are OCR losses of the halant on `द्`. Apply globally.
text = do(text, 'C1', 'सदुरु', 'सद्गुरु', 6,
          'सदुरु → सद्गुरु globally (halant recovered)')

# ─── Class C: chapter-end blessing normalization ────────────────────────
# After the सदुरु→सद्गुरु fix, blessings are one of:
#   ॥राजाधिराज सद्गुरुनाथ महाराज की जय॥       (fused, no outer space)  — 4x
#   ॥राजाधिराज सद्गुरु नाथ महाराज की जय॥      (split, no outer space)  — 4x
#   ॥ राजाधिराज सद्गुरु नाथ महाराज की जय॥     (split, leading outer)   — 1x
#   ॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥     (canonical)              — 2x
canonical_bless = '॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥'
for tag, old_bless, count_hint in [
    ('C2a', '॥राजाधिराज सद्गुरुनाथ महाराज की जय॥', 4),
    ('C2b', '॥राजाधिराज सद्गुरु नाथ महाराज की जय॥', 4),
    ('C2c', '॥ राजाधिराज सद्गुरु नाथ महाराज की जय॥', 1),
]:
    text = do(text, tag, old_bless, canonical_bless, count_hint,
              'chapter-end blessing normalization')

# ─── Write output + log ──────────────────────────────────────────────────

DST.write_text(text, encoding='utf-8')
new_bytes = len(text.encode('utf-8'))
new_lines = text.count('\n')

log_lines.insert(1,
    f'**Applied:** {applied} fixes\n'
    f'**Skipped (mismatched count):** {skipped}\n'
    f'**Bytes:** {orig_bytes:,} -> {new_bytes:,} ({new_bytes - orig_bytes:+,})\n'
    f'**Lines:** {orig_lines:,} -> {new_lines:,} ({new_lines - orig_lines:+,})\n'
    f'\n---\n\n'
    f'## Class B — deliberately skipped (needs human reviewer)\n'
    f'- **F21**: `निजधाम हे नाम` vs `निजधाम ते नाम` — pronoun mismatch between L1734 verse quote and L1736 gloss. Needs canonical Manache Shloka #86 reading.\n'
    f'- **F22**: Two Marathi transcriptions of the same Tukaram abhang (L1923-1929 vs L2094-2100) with different spellings (वशिष्ठासी/वसिष्ठासी, तूचि पाही/तूची पाहे etc). Needs Neha\'s call on which to use.\n'
    f'- **F27**: Stray `२१.२४` reference mid-sentence at L2151 without source prefix. Origin unclear.\n'
    f'- **F28**: Manache Shloka #145 quoted 8 times with subtle variants across L452, L648, L668, L1789, L1797, L2064, L2159, L2354 — pick one canonical form globally.\n'
    f'- **F11/F24**: Chapter 3/4 subtitle layout (भाग १/भाग २ on separate line) — reviewer preference.\n'
    f'- **F19**: `असतो मा सद्गमय` mantra layout at L359 — verse block preferred but current form isn\'t wrong.\n'
    f'- **F23**: Chapter 5 has an "extra" chapter-end blessing at L865 orphaned above ch5 title — may reflect printed edition layout.\n'
)
LOG.write_text('\n'.join(log_lines), encoding='utf-8')

print(f'Applied {applied}, skipped {skipped}. Wrote {DST} and {LOG}.')
