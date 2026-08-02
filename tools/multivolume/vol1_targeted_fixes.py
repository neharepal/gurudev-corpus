"""Vol 1 targeted fixes — Phase 3.5 per QA report (RFC-020).

Reads   staging/kakanchi-pravachane-vol1.clean.md
Writes  staging/kakanchi-pravachane-vol1.v2.md
Writes  staging/vol1_changes.md    (per-fix change log with counts)

Every fix uses a context-anchored old->new pair with an expected occurrence
count. If count doesn't match, we log a WARN and skip that fix — never a
silent partial-apply.

Vol 1 specific: F1 is a systemic issue — ~40 inline orphan page numbers
prepended to the first word of a paragraph. We do a regex sweep for those
first, with careful exclusions:
  * `१२ बिन बाजा` (Class B — F17, could be page-92 or stanza-num, needs
    human review)
  * `१८ व्या` (ordinal marker "18th" — legit content, not a page number)

Then Class A: unambiguous find/replace (OCR nonwords, split words, missing
letter, misspelled English)
Class A+: 3 verse-block reformats (Tukaram abhang collapsed, Kabir line
without close quote, verse-plus-citation-plus-prose splice)
Class B: 5 findings needing human judgment — listed at bottom of log
Class C: 8 chapter-end blessing normalizations to canonical form
"""
from __future__ import annotations
from pathlib import Path
import re

SRC = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol1.clean.md')
DST = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol1.v2.md')
LOG = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/vol1_changes.md')

log_lines: list[str] = ['# Vol 1 — Phase 3.5 change log\n']
applied = 0
skipped = 0


def do(text: str, tag: str, old: str, new: str, expected: int, note: str = '') -> str:
    """Apply an exact-string replacement. Warn + skip if count != expected."""
    global applied, skipped
    n = text.count(old)
    if n != expected:
        log_lines.append(
            f'### {tag} — WARN SKIPPED (expected {expected} matches, found {n})\n'
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

# ============================================================
# F1 (systemic): regex sweep for inline page numbers prepended
# to paragraph start. Pattern is Devanagari digits (1-3 chars,
# so we don't touch 4-digit years like १९०९) followed by
# whitespace/period, followed by a non-space non-digit char.
# Exclusions:
#   * `१२ बिन बाजा` — Class B (F17): could be page 92 or stanza
#     marker on Kabir verse; human review needed
#   * `१८ व्या` — legit "in the 18th chapter" ordinal
# ============================================================

lines = text.split('\n')
f1_hits = 0
f1_excluded = []
pat = re.compile(r'^([०-९]{1,3})[ .]+(?=\S)')
for i, line in enumerate(lines):
    m = pat.match(line)
    if not m:
        continue
    rest = line[m.end():]
    # Exclusion 1: Class B — `१२ बिन बाजा` on Kabir verse
    if m.group(1) == '१२' and rest.startswith('बिन बाजा'):
        f1_excluded.append(f'L{i+1}: kept `{m.group(0)}{rest[:15]}...` (Class B / F17)')
        continue
    # Exclusion 2: ordinal marker "व्या" (18th, 19th, etc.)
    if rest.startswith('व्या '):
        f1_excluded.append(f'L{i+1}: kept `{m.group(0)}{rest[:15]}...` (ordinal)')
        continue
    lines[i] = rest
    f1_hits += 1

text = '\n'.join(lines)

applied += 1
log_lines.append(
    f'### F1 — OK {f1_hits}x (systemic sweep of inline page numbers)\n'
    f'- **Regex:** `^([०-९]{{1,3}})[ .]+(?=\\S)` (line-anchored, 1-3 digits so years pass through)\n'
    f'- **Excluded:** {len(f1_excluded)} matches kept\n'
    + '\n'.join(f'  - {x}' for x in f1_excluded) + '\n'
)

# ============================================================
# F2: standalone `१०.` on L71 — page 10 orphan, splits a sentence
# ============================================================
text = do(text, 'F2',
    'कारण यावेळेला दुसरा कोणता आधारच\n\n१०.\n\nत्यांना उरला नव्हता.',
    'कारण यावेळेला दुसरा कोणता आधारच त्यांना उरला नव्हता.', 1,
    'L71 standalone १०. removed; adjacent sentence rejoined')

# F1-sub (orphan `१६.` on L112) — same pattern; QA lists under F1 systemic
text = do(text, 'F1b',
    'त्यावेळी ज्योतीवर त्यांना असं दिसलं की, महाराजांच्या मांडीवर ते लहान मूल होऊन खेळत होते. अशा रीतीने\n\n१६.\n\nत्यांचं साधन आणि त्यांचा अनुभव कसे वाढत गेले हे आपण पाहिलं.',
    'त्यावेळी ज्योतीवर त्यांना असं दिसलं की, महाराजांच्या मांडीवर ते लहान मूल होऊन खेळत होते. अशा रीतीने त्यांचं साधन आणि त्यांचा अनुभव कसे वाढत गेले हे आपण पाहिलं.', 1,
    'L112 standalone १६. removed; adjacent sentence rejoined')

# ============================================================
# F3: Latin-digit page marker `59/152` on L400 (standalone)
# Surrounding paragraphs are complete sentences — just delete
# ============================================================
text = do(text, 'F3',
    'आपल्या जीवनाचं परीक्षण करीत राहिलं पाहिजे.\n\n59/152\n\nआपण नामस्मरण करीत असताना',
    'आपल्या जीवनाचं परीक्षण करीत राहिलं पाहिजे.\n\nआपण नामस्मरण करीत असताना', 1,
    'L400 Latin-digit page marker removed')

# ============================================================
# Class A: unambiguous OCR nonword and split-word fixes
# ============================================================

# F25: मैंदू → मेंदू (line 17)
text = do(text, 'F25', 'ज्याच्या मैंदूमध्ये', 'ज्याच्या मेंदूमध्ये', 1,
    'L17: मैंदू (OCR nonword) → मेंदू (brain)')

# F4: साधन के → साधन केलं (line 148; verb truncated at rejoin)
text = do(text, 'F4', 'गुरुदेवांनी साधन के आणि', 'गुरुदेवांनी साधन केलं आणि', 1,
    'L148: truncated verb के → केलं')

# F9: निचिश्तपणे → निश्चितपणे (line 246; reordered cluster)
text = do(text, 'F9', 'निचिश्तपणे', 'निश्चितपणे', 1,
    'L246: निचिश्तपणे → निश्चितपणे (reordered cluster)')

# F10: देवाजळच → देवाजवळच (line 306; dropped व)
text = do(text, 'F10', 'देवाजळच', 'देवाजवळच', 1,
    'L306: देवाजळच → देवाजवळच (missing व)')

# F11: Consecreation → Consecration (line 316; English misspelling)
text = do(text, 'F11', 'Consecreation', 'Consecration', 1,
    'L316: English misspelling')

# F5: मोठं आ की → मोठं आहे की (line 330; verb truncated)
text = do(text, 'F5', 'इतकं मोठं आ की, माणसाची', 'इतकं मोठं आहे की, माणसाची', 1,
    'L330: आ (truncated) → आहे')

# F30: सांत दिवसात → सात दिवसात (line 336; anusvara spurious)
text = do(text, 'F30', 'सांत दिवसात', 'सात दिवसात', 1,
    'L336: सांत → सात (numeral seven)')

# F6: मला दिस आहे → मला दिसत आहे (line 336; verb truncated)
text = do(text, 'F6', 'असे मला दिस आहे.', 'असे मला दिसत आहे.', 1,
    'L336: दिस (truncated) → दिसत')

# F28: दाघांच्यामध्ये → दोघांच्यामध्ये (line 340)
text = do(text, 'F28', 'दाघांच्यामध्ये', 'दोघांच्यामध्ये', 1,
    'L340: दाघांच्यामध्ये (nonword) → दोघांच्यामध्ये (between the two)')

# F29: प्रख्यामुळे → प्रारब्धामुळे (line 398; based on doublet with संचित)
text = do(text, 'F29', 'आपल्या प्रख्यामुळे, संचितामुळे',
    'आपल्या प्रारब्धामुळे, संचितामुळे', 1,
    'L398: प्रख्यामुळे (nonword) → प्रारब्धामुळे (karma doublet)')

# F20: बाळायला → वाळायला (line 414; ब→व)
text = do(text, 'F20', 'पाणी तुटल्यामुळे बाळायला लागेल',
    'पाणी तुटल्यामुळे वाळायला लागेल', 1,
    'L414: बाळायला → वाळायला (dry up)')

# F16 + F15: `• सुन्न मंडल त्या टिकाणी` → `सुन्न मंडल त्या ठिकाणी` (line 676)
text = do(text, 'F15_16', '• सुन्न मंडल त्या टिकाणी',
    'सुन्न मंडल त्या ठिकाणी', 1,
    'L676: strip stray bullet + टिकाणी → ठिकाणी')

# F8: करालल → कराल (line 720; doubled ल)
text = do(text, 'F8', "'काल करालल निकट नही आवै'",
    "'काल कराल निकट नहि आवै'", 1,
    'L720: कराल doubled + नही→नहि (matches other Kabir citations)')

# F22: एकत नाही → ऐकत नाही (all 4 occurrences on L236 x2, L238, L244)
text = do(text, 'F22', 'एकत नाही', 'ऐकत नाही', 4,
    'L236 (x2), L238, L244: एकत (nonword) → ऐकत (listening)')

# F7: जा. २.१७० रमेश्वराची → citation break + परमेश्वराची (line 618)
text = do(text, 'F7',
    'ज्यालागीं विरक्त वनवासिये !! जा. २.१७० रमेश्वराची प्राप्ति अजून झालेली नाही.',
    'ज्यालागीं विरक्त वनवासिये ॥ जा. २.१७०\n\nपरमेश्वराची प्राप्ति अजून झालेली नाही.', 1,
    'L618: split citation from prose; restore lost `प` in परमेश्वराची')

# F14: duplicated sentence L436 (truncated fragment before L438 full para)
text = do(text, 'F14',
    'नामस्मरण फलद्रुप होत नाही. जीवनामध्ये महत्वाची गोष्ट कोणती तर प्रेम ही महत्वाची गोष्ट आहे.\n\nआपलं ज्याच्यावर प्रेम आहे त्याचं स्मरण आपल्याला आपोआप होतं. म्हणून प्रेम महत्वाचं आहे. ते जागृत करायचा\n\nआपलं ज्याच्यावर प्रेम आहे त्याचं स्मरण आपल्याला आपोआप होतं. म्हणून प्रेम महत्वाचं आहे. ते जागृत करायचा प्रयत्न करायचा.',
    'नामस्मरण फलद्रुप होत नाही. जीवनामध्ये महत्वाची गोष्ट कोणती तर प्रेम ही महत्वाची गोष्ट आहे.\n\nआपलं ज्याच्यावर प्रेम आहे त्याचं स्मरण आपल्याला आपोआप होतं. म्हणून प्रेम महत्वाचं आहे. ते जागृत करायचा प्रयत्न करायचा.', 1,
    'L436-437: delete truncated duplicate paragraph')

# ============================================================
# Class A+ : verse block reformats
# ============================================================

# F21: `कहै कबीर` line — close quote, split verse from prose (line 236)
# Also fixes `एकत` on this line via the F22 pass above (which runs earlier)
# So the current text after F22 is: `'कहै कबीर मैं कभी कभी हान्यो. सांगितलेलं कोणी ऐकत नाही.`
text = do(text, 'F21',
    "'कहै कबीर मैं कभी कभी हान्यो. सांगितलेलं कोणी ऐकत नाही.",
    "'कहै कबीर मैं कभी कभी हान्यो' ॥\n\nसांगितलेलं कोणी ऐकत नाही.",
    1, 'L236: close Kabir quote + split verse from prose commentary')

# F13 + F23: Tukaram abhang restructure (line 242) with पुंजाळा → पुजाया
text = do(text, 'F13_23',
    "'सांग सांगोनी दमलो पाठी जगाच्या लागलो जग ऐकेनासे झाले भूत पुंजाळा लागले.",
    "'सांग सांगोनी दमलो, पाठी जगाच्या लागलो ।\nजग ऐकेनासे झाले, भूत पुजाया लागले ॥'",
    1, 'L242: Tukaram abhang split into 2 lines with pada dandas + पुंजाळा → पुजाया (original Tukaram)')

# ============================================================
# Class C: chapter-end blessing normalization to canonical form
# `॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥`
#
# Variants found (spelling: सद्गुरुनाथ vs सद्गुरूनाथ, presence of श्री,
# `!` vs `!!` markers):
#   L136:  ! राजाधिराज सद्गुरूनाथ महाराज की जय !          (1)
#   L254:  ! राजाधिराज श्री सद्गुरूनाथ महाराज की जय        (1, no trailing !)
#   L354:  ! राजाधिराज सद्गुरूनाथ महाराज की जय !          (in count 1 above)
#   L474:  !! राजाधिराज श्री सद्गुरुनाथ महाराज की जय !!   (1)
#   L610:  ! राजाधिराज सद्गुरुनाथ महाराज की जय !          (1)
#   L808:  ! राजाधिराज सद्गुरूनाथ महाराज की जय !          (in count 1 above)
#   L952:  ! राजाधिराज श्री सद्गुरूनाथ महाराज की जय !!    (1)
#   L1094: !! राजाधिराज सद्गुरुनाथ महाराज की जय !         (1)
#   L1300: !राजाधिराज सद्गुरुनाथ महाराज की जय !           (1, no space after !)
# ============================================================

canonical_bless = '॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥'

# NOTE: order matters — longest/most-specific first, because some shorter
# patterns are substrings of longer ones (e.g. `! ... श्री ... !!` at L952
# has `! ... श्री ...` at L254 as a proper prefix). Apply the containing
# form first so the substring form only matches its own line afterwards.
for tag, old_bless, count in [
    # `!! ... श्री ... !!` — L474
    ('C1c', '!! राजाधिराज श्री सद्गुरुनाथ महाराज की जय !!', 1),
    # `! ... श्री ... !!` — L952 (must run before C1b which is its prefix)
    ('C1e', '! राजाधिराज श्री सद्गुरूनाथ महाराज की जय !!', 1),
    # `!! ... !` — L1094 (must run before C1d which is its `! ... !` suffix)
    ('C1f', '!! राजाधिराज सद्गुरुनाथ महाराज की जय !', 1),
    # `! ... !` with सद्गुरूनाथ (uu) — L136, L354, L808 = 3
    ('C1a', '! राजाधिराज सद्गुरूनाथ महाराज की जय !', 3),
    # `! ... श्री ...` (no trailing !) — L254 (after C1e ran)
    ('C1b', '! राजाधिराज श्री सद्गुरूनाथ महाराज की जय', 1),
    # `! ... !` with सद्गुरुनाथ (u) — L610 (after C1f ran)
    ('C1d', '! राजाधिराज सद्गुरुनाथ महाराज की जय !', 1),
    # `!राजाधिराज ...` with no space after opening ! — L1300
    ('C1g', '!राजाधिराज सद्गुरुनाथ महाराज की जय !', 1),
]:
    text = do(text, tag, old_bless, canonical_bless, count,
              'blessing normalized to canonical form')

# ============================================================
# Class B — findings deferred to human reviewer
# ============================================================
log_lines.append(
    '\n---\n\n'
    '## Class B — left unchanged (human review required)\n\n'
    '### F12: possible year typo `१९९६` (line 94)\n'
    '- Context: `१ वर्षाचा मुलगा १९९६ सालीच मरून गेला होता.` — surrounding narrative is 1920.\n'
    '- QA suggests very likely `१९१६` but says human must verify against source PDF.\n'
    '- **Skipped.** Source-check needed.\n\n'
    '### F17: orphan `१२` prefix on Kabir verse (line 678)\n'
    '- Context: `१२ बिन बाजा झनकार उठे जहँ !`\n'
    '- QA: could be page 92 (with ९ dropped) or a stanza number — human reviewer to check.\n'
    '- **Excluded from F1 regex sweep** so nothing was altered.\n\n'
    '### F18: stray `घ` before `धरली/धरलं/धरला/धरलेलं` (lines 520, 526, 584, 1144)\n'
    '- QA: almost certainly OCR of `घट्ट` (tight), but the position of the `घ` varies\n'
    '  (before verb vs. before noun `मुठीत`) so a mechanical replacement is unsafe.\n'
    '- **Skipped.** Needs pattern-specific decisions per occurrence.\n\n'
    '### F19: `नाम घ घ घ धर` (line 1092)\n'
    '- QA: likely `नाम घट्ट घट्ट घट्ट धर` (emphasized "hold tight, hold tight, hold tight")\n'
    '  but source verification needed.\n'
    '- **Skipped.**\n\n'
    '### F26: `पट्टिशी` / `चट्टिशी` (line 47), inconsistent with `चट्टदिशी` (line 412)\n'
    '- QA suggests normalizing to `चटदिशी` (or `चट्दिशी`) after checking source.\n'
    '- Judgment call on which normalized form to adopt.\n'
    '- **Skipped.**\n'
)

# ============================================================
# Write output + log
# ============================================================
DST.write_text(text, encoding='utf-8')
new_bytes = len(text.encode('utf-8'))
new_lines = text.count('\n')

log_lines.insert(1,
    f'**Applied:** {applied} fixes\n'
    f'**Skipped (mismatched count):** {skipped}\n'
    f'**F1 systemic sweep hits:** {f1_hits}\n'
    f'**F1 excluded (kept as-is):** {len(f1_excluded)}\n'
    f'**Bytes:** {orig_bytes:,} -> {new_bytes:,} ({new_bytes - orig_bytes:+,})\n'
    f'**Lines:** {orig_lines:,} -> {new_lines:,} ({new_lines - orig_lines:+,})\n'
    f'\n---\n'
)
LOG.write_text('\n'.join(log_lines), encoding='utf-8')

print(f'Applied {applied}, skipped {skipped}, F1 hits {f1_hits}. Wrote {DST} and {LOG}.')
