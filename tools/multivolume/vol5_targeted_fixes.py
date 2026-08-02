"""Vol 5 targeted fixes — Phase 3.5 per QA report (RFC-020).

Reads   staging/kakanchi-pravachane-vol5.clean.md
Writes  staging/kakanchi-pravachane-vol5.v2.md
Writes  staging/vol5_changes.md    (per-fix change log with counts)

Every fix uses a context-anchored old->new pair with an expected occurrence
count. If count doesn't match, we log a WARN and skip that fix — never a
silent partial-apply.

Class A: 23 unambiguous find/replace (citations, typos, punctuation)
Class A+: 4 verse-block reformats (multi-line restructures)
Class C : TOC block replacement + 12 chapter-end blessing normalizations
"""
from __future__ import annotations
from pathlib import Path

SRC = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol5.clean.md')
DST = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol5.v2.md')
LOG = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/vol5_changes.md')

log_lines: list[str] = ['# Vol 5 — Phase 3.5 change log\n']
applied = 0
skipped = 0


def do(text: str, tag: str, old: str, new: str, expected: int, note: str = '') -> str:
    """Apply an exact-string replacement. Warn + skip if count != expected."""
    global applied, skipped
    n = text.count(old)
    if n != expected:
        log_lines.append(
            f'### {tag} — ⚠ SKIPPED (expected {expected} matches, found {n})\n'
            f'- **Old:** `{old!r}`\n'
            f'- **New:** `{new!r}`\n'
            f'{"- **Note:** " + note if note else ""}\n'
        )
        skipped += 1
        return text
    applied += 1
    log_lines.append(
        f'### {tag} — ✓ {n}× ({note or ""})\n'
        f'- **Old:** `{old}`\n'
        f'- **New:** `{new}`\n'
    )
    return text.replace(old, new)


text = SRC.read_text(encoding='utf-8')
orig_bytes = len(text.encode('utf-8'))
orig_lines = text.count('\n')

# ─── Class A: unambiguous find/replace ────────────────────────────────

# F2: doubled period on ch 11 heading
text = do(text, 'F2', 'दसवें द्वारे ताली लागी..', 'दसवें द्वारे ताली लागी.', 2,
          'ch 11 heading — appears in TOC and body')

# F3: गीता 9.34 wrongly cited as 1.34 — 3 distinct forms in the file
text = do(text, 'F3a', 'मामैवष्यसि युक्त्वैवमात्मानं मत्परायणः ॥१.३४',
          'मामैवष्यसि युक्त्वैवमात्मानं मत्परायणः ॥ गी. ९.३४', 1,
          'L629: cite ॥१.३४ → गी. ९.३४')
text = do(text, 'F3b', 'मामेवैष्यसि युक्तवैवमात्मानं मत्परायणः॥ गी.१.३४',
          'मामेवैष्यसि युक्तवैवमात्मानं मत्परायणः॥ गी.९.३४', 1,
          'L1207: 1.34 → 9.34')
text = do(text, 'F3c', 'मामेवैश्यसि युक्त्वैवं आत्मानं मत्परायणः ॥ - गी.१.३४',
          'मामेवैश्यसि युक्त्वैवं आत्मानं मत्परायणः ॥ - गी.९.३४', 1,
          'L1528: 1.34 → 9.34')

# F4: मामिच्छामुं → मामिच्छाप्तुं (QA reported 3, actual 4 — all same wrong form)
text = do(text, 'F4', 'मामिच्छामुं', 'मामिच्छाप्तुं', 4,
          'Gita 12.9 correct form — 4th occurrence found by count check')

# F5: two mistakes in Gita 6.28
text = do(text, 'F5a', 'युज्जननेवं सदात्मानं', 'युञ्जन्नेवं सदात्मानं', 1)
text = do(text, 'F5b', 'संस्पर्शमत्यन्तं सुखमश्रुते', 'संस्पर्शमत्यन्तं सुखमश्नुते', 1)

# F6: स्थितेन दुःखेन → स्थितो न दुःखेन + drop errant danda
text = do(text, 'F6', 'यस्मिन् स्थितेन दुःखेन । गुरुणापि विचाल्यते ॥',
          'यस्मिन् स्थितो न दुःखेन गुरुणापि विचाल्यते ॥', 1,
          'Gita 6.22')

# F7: यत्स्येन्द्रियाणि → यस्येन्द्रियाणि
text = do(text, 'F7', 'वशेहि यत्स्येन्द्रियाणि', 'वशे हि यस्येन्द्रियाणि', 1,
          'Gita 2.61 — fixes conjunct + splits वशेहि')

# F8: गी.१.५५ → गी.२.५५ (Stitāprajña shloka)
text = do(text, 'F8', 'स्थितः प्रज्ञस्तदोच्यते ॥ गी.१.५५',
          'स्थितः प्रज्ञस्तदोच्यते ॥ गी.२.५५', 1)

# F9: ज्ञा. १.५११ → ज्ञा. ९.५१९
text = do(text, 'F9', 'बोलिजत असें॥ ज्ञा. १.५११',
          'बोलिजत असें॥ ज्ञा. ९.५१९', 1)

# F10: ज्ञा.१२.१९ → ज्ञा.१२.१००
text = do(text, 'F10', 'मी तू ऐसे उरे ॥- ज्ञा.१२.१९',
          'मी तू ऐसे उरे ॥- ज्ञा.१२.१००', 1)

# F11: ज्ञा.१२.१०६ → ज्ञा.१२.१०९ (only the L1424 occurrence — cited context)
text = do(text, 'F11', 'हळूहळू पांडुसुता मीचि होईल ॥ ज्ञा.१२.१०६',
          'हळूहळू पांडुसुता मीचि होईल ॥ ज्ञा.१२.१०९', 1,
          'L1424: preserve other १२.१०६ citations elsewhere')

# F12: सच्चिदापनंद → सच्चिदानंद
text = do(text, 'F12', 'सच्चिदापनंद', 'सच्चिदानंद', 1)

# F13: तेसद्धा → तेसुद्धा; ब्रह्मचआहे → ब्रह्मच आहे
text = do(text, 'F13a', 'तेसद्धा ब्रह्मच', 'ते सुद्धा ब्रह्मच', 1)
text = do(text, 'F13b', 'अग्नीही ब्रह्मचआहे', 'अग्नीही ब्रह्मच आहे', 1)

# F14: पूजा आवश्य आहे → पूजा आवश्यक आहे
text = do(text, 'F14', 'ही पूजा आवश्य आहे', 'ही पूजा आवश्यक आहे', 1)

# F15: कशामधे → कशामध्ये
text = do(text, 'F15', 'कशामधे झालं', 'कशामध्ये झालं', 1)

# F16: विषयां पेक्षा → विषयांपेक्षा
text = do(text, 'F16', 'विषयां पेक्षा', 'विषयांपेक्षा', 1)

# F17: आधिक → अधिक (only in specific L511 context to avoid false positives)
text = do(text, 'F17a', 'नामस्मरण आधिक झालं', 'नामस्मरण अधिक झालं', 1)
# F17: drop stray comma after अशा,
text = do(text, 'F17b', 'अशा, वृत्तीमध्ये जे सुचतं', 'अशा वृत्तीमध्ये जे सुचतं', 1)
# NOTE: आतंतेने left untouched — Class B, needs Neha's call

# F18: विसरत नाह; → विसरत नाही;
text = do(text, 'F18', 'देवाला विसरत नाह; परमेश्वराशी',
          'देवाला विसरत नाही; परमेश्वराशी', 1)

# F19: !तुका.बारा → ॥ तुका. बारा (abhang closing)
text = do(text, 'F19', 'मायाजाळी!तुका.बारा',
          'मायाजाळी ॥ तुका. बारा', 1)

# F20: नाही' → नाही. (stray closing quote)
text = do(text, 'F20', 'तो मूळचा नाही\' आम्ही',
          'तो मूळचा नाही. आम्ही', 1)

# F21: Kabir doha at L122 — insert pada danda
text = do(text, 'F21', 'सूरत शब्द मेला भया काल रहा गही मौन। प. सो.',
          'सूरत शब्द मेला भया । काल रहा गही मौन ॥ प. सो.', 1)

# F22: Kabir doha at L2097 — insert pada danda
text = do(text, 'F22', 'बिन बाजा झनकार उठै जहाँ समुझि परै जब ध्यान धरै॥',
          'बिन बाजा झनकार उठै जहाँ । समुझि परै जब ध्यान धरै ॥', 1)

# F23: drop errant danda between आत्मानम् and पश्यन्
text = do(text, 'F23', 'यत्र चैवात्मनात्मानम्। पश्यन् आत्मनि तुष्यति ॥',
          'यत्र चैवात्मनात्मानं पश्यन् आत्मनि तुष्यति ॥', 1)

# ─── Class A+: verse-block reformatting (multi-line restructures) ────

# F24: at L353 — Marathi abhang + Hindi doha jammed with किंवा hinge
old_f24 = 'एक मन आहे तुझ्या भांडवला। वाटिता ते तुला येईल कैसे। किंवा आप है तो हरि नहि। हरि है तो आप नहि।।'
new_f24 = (
    'एक मन आहे तुझ्या भांडवला ।\n'
    'वाटिता ते तुला येईल कैसे ॥\n\n'
    'किंवा\n\n'
    'आप है तो हरि नहि ।\n'
    'हरि है तो आप नहि ॥'
)
text = do(text, 'F24', old_f24, new_f24, 1, 'L353 verse block restructured')

# F25: at L391 — two Ramdas quotations glued with किंवा
old_f25 = 'जगी थोरला देव तो चोरलासे। किंवा नर्मदा गंडकातीरी देव पडले कोट्यानवेरी। त्यांची गणना कोण करी असंख्यात गोटे।'
new_f25 = (
    'जगी थोरला देव तो चोरलासे ॥\n\n'
    'किंवा\n\n'
    'नर्मदा गंडकातीरी देव पडले कोट्यानवेरी ।\n'
    'त्यांची गणना कोण करी असंख्यात गोटे ॥'
)
text = do(text, 'F25', old_f25, new_f25, 1, 'L391 two Ramdas fragments split')

# F26: at L483 — shloka + citation + commentary jammed
old_f26 = 'एकमेव परा पूजा सर्वावस्थासु सर्वदा एकबुद्ध्या तु देवेश विधेया ब्रह्मवित्तमैः । परापूजा ९ जे ज्ञानी लोक आहेत'
new_f26 = (
    'एकमेव परा पूजा सर्वावस्थासु सर्वदा ।\n'
    'एकबुद्ध्या तु देवेश विधेया ब्रह्मवित्तमैः ॥\n'
    '- परापूजा ९\n\n'
    'जे ज्ञानी लोक आहेत'
)
text = do(text, 'F26', old_f26, new_f26, 1,
          'L483 shloka + citation + commentary broken into blocks')

# F28: at L459 — full Tukaram abhang collapsed. Break 6 padas onto their own lines.
old_f28 = (
    'संतांचिया गावी प्रेमाचा सुकाळ । नाही हळहळ दुःख लेश । म्हणनिया त्यांचा होईन याचक । '
    'घालतील भीक तेचि मज । संतांचिये गावी वरो भांडवल । अवघा विठ्ठल धन वित्त । '
    'संतांचिये गावी अमृताचे पान । करिती कीर्तन सर्व काळ । संतांचिये गावी उपदेशाची पेठ । '
    'प्रेम सुख साट देती घेती । तुका म्हणे तेथे आणिक नाही परी । म्हणोनि भिकारी झालो त्यांचा ॥'
)
new_f28 = (
    'संतांचिया गावी प्रेमाचा सुकाळ । नाही हळहळ दुःख लेश ।\n'
    'म्हणनिया त्यांचा होईन याचक । घालतील भीक तेचि मज ।\n'
    'संतांचिये गावी वरो भांडवल । अवघा विठ्ठल धन वित्त ।\n'
    'संतांचिये गावी अमृताचे पान । करिती कीर्तन सर्व काळ ।\n'
    'संतांचिये गावी उपदेशाची पेठ । प्रेम सुख साट देती घेती ।\n'
    'तुका म्हणे तेथे आणिक नाही परी । म्हणोनि भिकारी झालो त्यांचा ॥'
)
text = do(text, 'F28', old_f28, new_f28, 1,
          'L459 Tukaram abhang — 6 pada-pairs each on own line')

# ─── Class C: TOC full normalization + chapter-end blessing normalization ───

# C29: replace the entire TOC block with a normalized version matching body forms
old_toc = (
    'श्रीगुरूदेवांचा साधनमार्ग.\n\n'
    'साधकाची वृत्ती व आचार.\n\n'
    'नामसाधनेचे महत्त्व १.\n\n'
    'नामसाधनेचे महत्त्व २.\n\n'
    'मनुष्याच्या नैसर्गिक शक्ती व नरदेहाचे महत्त्व.\n\n'
    'भगवद्गीतेवरील प्रवचन - १ भगवद्गीतेवरील प्रवचन - २ नामस्मरणाबद्दल विशेष.\n\n'
    'नामस्मरणाने वासनानाश.\n\n'
    'आत्मानंदवाद (ब्रह्मसंस्पर्श).\n\n'
    'दसवें द्वारे ताली लागी.\n\n'   # AFTER F2 fix, single period
    'स्वरूपसाक्षात्कार\n\n'
    'परिशिष्ट १ - हौदाची उपमा'
)
new_toc = (
    '१. श्रीगुरुदेवांचा साधन मार्ग\n\n'
    '२. साधकाची वृत्ती व आचार\n\n'
    '३. नामसाधनेचे महत्त्व - १\n\n'
    '४. नामसाधनेचे महत्त्व - २\n\n'
    '५. मनुष्याच्या नैसर्गिक शक्ती व नरदेहाचे महत्त्व\n\n'
    '६. भगवद्गीतेवरील प्रवचन - १\n\n'
    '७. भगवद्गीतेवरील प्रवचन - २\n\n'
    '८. नामस्मरणाबद्दल विशेष\n\n'
    '९. नामस्मरणाने वासना नाश\n\n'
    '१०. आत्मानंदवाद (ब्रह्मसंस्पर्श)\n\n'
    '११. दसवें द्वारे ताली लागी\n\n'
    '१२. स्वरूपसाक्षात्कार\n\n'
    'परिशिष्ट - १  हौदाची उपमा'
)
text = do(text, 'C29', old_toc, new_toc, 1,
          'TOC rewritten to match normalized body titles with numeric prefixes')

# C30: normalize all 12 chapter-end blessings to one canonical form.
# Existing variants seen (from grep):
#   ॥राजाधिराज सद्गुरु नाथ महाराज की जय॥    (chs 1, 8, 10, 12, and more)
#   ॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥   (chs 2, 3, canonical)
#   ॥राजाधिराज सद्गुरुनाथ महाराज की जय॥     (chs 4, 5, 6, 7, 9)
#   ॥राजाधिराज सद्गुरुनाथ महाराज की जय ॥    (ch 11)
canonical_bless = '॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥'
for tag, old_bless, count_hint in [
    ('C30a', '॥राजाधिराज सद्गुरु नाथ महाराज की जय॥', 5),   # var with `सद्गुरु नाथ` split, no outer space
    ('C30b', '॥राजाधिराज सद्गुरुनाथ महाराज की जय॥', 4),    # fused word, no outer space (actual count = 4, not 5)
    ('C30c', '॥राजाधिराज सद्गुरुनाथ महाराज की जय ॥', 1),   # trailing outer space, no leading
]:
    text = do(text, tag, old_bless, canonical_bless, count_hint,
              'C30 blessing normalization')

# ─── Write output + log ──────────────────────────────────────────────────

DST.write_text(text, encoding='utf-8')
new_bytes = len(text.encode('utf-8'))
new_lines = text.count('\n')

log_lines.insert(1,
    f'**Applied:** {applied} fixes\n'
    f'**Skipped (mismatched count):** {skipped}\n'
    f'**Bytes:** {orig_bytes:,} → {new_bytes:,} ({new_bytes - orig_bytes:+,})\n'
    f'**Lines:** {orig_lines:,} → {new_lines:,} ({new_lines - orig_lines:+,})\n'
    f'\n---\n'
)
LOG.write_text('\n'.join(log_lines), encoding='utf-8')

print(f'Applied {applied}, skipped {skipped}. Wrote {DST} and {LOG}.')
