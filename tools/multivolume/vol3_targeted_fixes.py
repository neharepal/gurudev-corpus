"""Vol 3 targeted fixes — Phase 3.5 per QA report (RFC-020).

Vol 3 is the worst-condition volume in the trilogy, requiring the most care.
30 QA findings; 4 high-severity structural issues plus a mix of OCR nonwords,
verse fragmentations, page-join splices, and citation typos.

Reads   staging/kakanchi-pravachane-vol3.clean.md
Writes  staging/kakanchi-pravachane-vol3.v2.md
Writes  staging/vol3_changes.md    (per-fix change log with counts)

Every fix uses a context-anchored old->new pair with an expected occurrence
count. If count doesn't match, log a WARN and skip that fix — never a
silent partial-apply.

High-severity structural fixes:
  F1  TOC sub-parts merged onto one line — split into five lines
  F2  Duplicate `३. हिंदी परमार्थसोपान वरील प्रवचने` heading — remove second copy
  F3  Paragraph-scale duplication L670–678 (Vijapur intro)
  F4  Paragraph-scale duplication L1043–1049 (चिमणी/चैतन्य block)

Class B (LEFT ALONE, logged):
  F15 `जातील केवि` verse truncation — needs source-PDF lookup for missing word + citation
  F24 `ठी ठेवी` in जो अमृतासि ठी ठेवी — appears 3× identically; may be house-style
  F25 बहिन्याने / बहिन्यांनी variant — dialect vs. OCR unclear
  F30 मसी बोलू नका vs आता बोलो नका — needs source reconciliation
"""
from __future__ import annotations
from pathlib import Path

SRC = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol3.clean.md')
DST = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/kakanchi-pravachane-vol3.v2.md')
LOG = Path('/Users/neharepal/.claude/jobs/fcdd9f9d/tmp/staging/vol3_changes.md')

log_lines: list[str] = ['# Vol 3 — Phase 3.5 change log\n']
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
        f'### {tag} — applied {n}x ({note or ""})\n'
        f'- **Old:** `{old}`\n'
        f'- **New:** `{new}`\n'
    )
    return text.replace(old, new)


text = SRC.read_text(encoding='utf-8')
orig_bytes = len(text.encode('utf-8'))
orig_lines = text.count('\n')

# ══════════════════════════════════════════════════════════════════════
# HIGH-SEVERITY STRUCTURAL FIXES (F1–F4)
# ══════════════════════════════════════════════════════════════════════

# ─── F1: TOC sub-parts merged onto one line (L11) ─────────────────────
# Current: `१). परमार्थप्रवृत्तीची कारणे२). नैतिक तयारी३). देव-भक्तांचे नाते४). साधन विचार५). साक्षात्कार`
# Instructions specify the target form: `१) परमार्थ प्रवृत्तीची कारणे`, etc.
old_toc_merged = '१). परमार्थप्रवृत्तीची कारणे२). नैतिक तयारी३). देव-भक्तांचे नाते४). साधन विचार५). साक्षात्कार'
new_toc_split = (
    '१) परमार्थ प्रवृत्तीची कारणे\n\n'
    '२) नैतिक तयारी\n\n'
    '३) देव-भक्तांचे नाते\n\n'
    '४) साधन विचार\n\n'
    '५) साक्षात्कार'
)
text = do(text, 'F1', old_toc_merged, new_toc_split, 1,
          'HIGH SEV: TOC merged sub-parts split back onto five lines with proper spacing')

# ─── F2: Duplicate L3 chapter heading at L596 ─────────────────────────
# Line 583 has the heading; lines 585–594 are the 1978/79/80 सप्ताह intro block;
# line 596 re-emits the same heading; line 598 is the sub-part 1 heading.
# Fix: delete line 596 (the second occurrence), keeping the intro.
# Anchor on end of intro + L596 heading + blank + L598 heading, replace with
# end of intro + blank + L598 heading.
old_dup_heading = (
    'उपयुक्त ठरेल. हे साधकांच्यावर या दोघांचे किती उपकार आहेत !\n\n'
    '३. हिंदी परमार्थसोपान वरील प्रवचने\n\n'
    '१. परमार्थ प्रवृत्तीची कारणे (Incentives to spiritual life)'
)
new_dup_heading = (
    'उपयुक्त ठरेल. हे साधकांच्यावर या दोघांचे किती उपकार आहेत !\n\n'
    '१. परमार्थ प्रवृत्तीची कारणे (Incentives to spiritual life)'
)
text = do(text, 'F2', old_dup_heading, new_dup_heading, 1,
          'HIGH SEV: duplicate `३. हिंदी परमार्थसोपान वरील प्रवचने` at L596 removed; intro block kept, L583 head retained')

# ─── F3: Paragraph-scale duplication L670–678 (Vijapur intro) ─────────
# L672 ends "...ब्रह्म झालो आहोत. हे त्यांच्या तोंडून आपण ऐकलेलं आहे...ही श्रद्धा आपण घट्ट करून घेऊ."
# L674 starts "आत्तापर्यंत जे गुरुदेवांचं तत्त्वज्ञान..." but veers into "ही सर्व देव झाले त्याप्रमाणे...तोंडून आपण"
# L676 continues "ऐकलेलं आहे...ही श्रद्धा आपण घट्ट करून घेऊ."
# L678 is the clean version of the "आत्तापर्यंत" paragraph.
# Fix: delete L674 + L676 (the mis-spliced copy), keep L672 → L678 flow.
old_dup_para_1 = (
    'ही श्रद्धा आपण घट्ट करून घेऊ.\n\n'
    'आत्तापर्यंत जे गुरुदेवांचं तत्त्वज्ञान मी थोडक्यात सांगितलं ते कशाकरता तर श्रद्धा अनेक तऱ्हेनी दृढ होण्याकरता. आता त्यांची मांडणी कशी केली आहे आणि ती आपल्या श्रद्धेला कशी उपयोगी करून घ्यायची आहे, हे आपल्याला पाहायचं आहे. त्यांनी सिद्धांत सांगितले आहेत पण त्यांनी ते स्वतःचे म्हणून सांगितले नाहीत. त्यांनी उपनिषदांपासून ते शिवलिंगव्वांपर्यंत सर्व संतांची पदं घेऊन, सर्व सिद्ध करून दाखवलं आहे. अर्थात् त्यांनी म्हटलं आहे की, मी जरी दुसऱ्यांच्या शब्दात बोलत असलो तरी हे सांगण्यामध्ये माझे स्वतःचेच सिद्धांत मला सांगायचे आहेत. उपनिषदरहस्याबद्दल त्यांनी म्हटलं आहे, \'या ग्रंथामध्ये माझे स्वतःचे सिद्धांत असे मुद्दाम मी सांगितले नाही आहेत. परंतु हा ग्रंथ अथपासून इतिपर्यंत जे कोणी काळजीपूर्वक अभ्यासतील त्यांना माझी या विषयावरची मतं काय आहेत ती कळून येतील. तेव्हा आपण त्यांचे ग्रंथ वाचताना लक्षात ठेवायचं की, ही सर्व देव झाले त्याप्रमाणे महाराजांच्या कृपेनी अर्थात् त्यांनी सांगितलेले साधन उत्कटतेने करून आम्ही स्वतः ब्रह्म झालो आहोत. हे त्यांच्या तोंडून आपण\n\n'
    'ऐकलेलं आहे आणि अशा भाग्यवंतांची आपण लेकरे आहोत. तेव्हा परमेश्वराचा साक्षात्कार, त्यांनी सांगितलेलं साधन करून, हळूहळू अनेक जन्मसंसिद्ध का होईना, ब्रह्म होण्याचं सामर्थ्य त्यांनी आपल्याला दिलेलं आहे. ही श्रद्धा आपण घट्ट करून घेऊ.\n\n'
    'आत्तापर्यंत जे गुरुदेवांचं तत्त्वज्ञान'
)
new_dup_para_1 = (
    'ही श्रद्धा आपण घट्ट करून घेऊ.\n\n'
    'आत्तापर्यंत जे गुरुदेवांचं तत्त्वज्ञान'
)
text = do(text, 'F3', old_dup_para_1, new_dup_para_1, 1,
          'HIGH SEV: paragraph-scale duplication L674+L676 removed; clean flow L672 -> L678 preserved')

# ─── F4: Paragraph-scale duplication L1043–1049 (चिमणी/चैतन्य block) ──
# L1043 first copy: "पाश्चात्य तत्त्वज्ञानात Substance...चैतन्य...करुणामय आणि करुणाकर...शरणागतीच्या संबंधाचे आहेत."
# L1045 first "चिमणी" para
# L1047 second copy (partial): "म्हणून स्वतंत्र एक वस्तु आहे. चैतन्य...करुणामय आणि करुणाकर..."
# L1049 second "चिमणी" para (verbatim repeat)
# Fix: delete L1047 + L1049, keep L1043 + L1045, then L1051.
old_dup_para_2 = (
    'एक चिमणी झाडावर बसलेली आहे. खालच्या बाजूला पारधी हातामध्ये बाण घेऊन उभा आहे, वरती ससाणा फिरतो आहे आणि ती चिमणी अत्यंत काकुळतीने देवाला म्हणत आहे की, देवा ! हे दोन्ही बाजूनी संकट आहे. पारध्याच्या हातातून सुटून जावं म्हटलं तर वरती ससाणा आहे. आता तुझ्याशिवाय मला कोणी नाही. असं सर्वस्व देवावर टाकलं म्हणजे देव त्या दोन संकटांना छेद देतो. त्यांनी म्हटलं आहे की, पारध्याच्या पायाला साप चावला, तो मरून पडला आणि साप चावल्यामुळे त्याचा नेम चुकला आणि तो ससाण्याला लागला. परमेश्वराला शरण गेले तर दोन्ही संकटे याप्रमाणे दूर होतात. अर्थात् हा ऐहिक संकटांचा विचार झाला. हे घडेल का नाही, हे सांगणं कठीण आहे. परंतु, त्यांचा मुख्य मुद्दा हा की, जर प्रसंग आला तर माणसाच्या हातामध्ये एकच शस्त्र आहे. ते म्हणजे, काकुळतीने देवाची प्रार्थना करणे की, देवा! मला यातून सोडव. खाजगी बोलताना गुरुदेव असेच म्हणाले होते की, अत्यंत कळकळीने (प्रार्थना) करणं हे आपल्या हातामध्ये आहे. हा एक मार्ग आपल्याला मोकळा आहे. परमेश्वर ते करीलच असे मात्र कोणी म्हणू नये.\n\n'
    'म्हणून स्वतंत्र एक वस्तु आहे. चैतन्य हा शब्द आपण वापरतो. कोणाचं चैतन्य असं नव्हे, तर चैतन्य हीच वस्तु, हाच पदार्थ आहे आणि तो पदार्थ म्हणजेच परमेश्वर हा मुद्दा सांगण्याकरता करणामय आणि करणाकर या दोन गोष्टी त्यांनी सांगितल्या आहेत. पुढे आता जे विचार आहेत ते सर्व शरणागतीच्या संबंधाचे आहेत.\n\n'
    'एक चिमणी झाडावर बसलेली आहे. खालच्या बाजूला पारधी हातामध्ये बाण घेऊन उभा आहे, वरती ससाणा फिरतो आहे आणि ती चिमणी अत्यंत काकुळतीने देवाला म्हणत आहे की, देवा ! हे दोन्ही बाजूनी संकट आहे. पारध्याच्या हातातून सुटून जावं म्हटलं तर वरती ससाणा आहे. आता तुझ्याशिवाय मला कोणी नाही. असं सर्वस्व देवावर टाकलं म्हणजे देव त्या दोन संकटांना छेद देतो. त्यांनी म्हटलं आहे की, पारध्याच्या पायाला साप चावला, तो मरून पडला आणि साप चावल्यामुळे त्याचा नेम चुकला आणि तो ससाण्याला लागला. परमेश्वराला शरण गेले तर दोन्ही संकटे याप्रमाणे दूर होतात. अर्थात् हा ऐहिक संकटांचा विचार झाला. हे घडेल का नाही, हे सांगणं कठीण आहे. परंतु, त्यांचा मुख्य मुद्दा हा की, जर प्रसंग आला तर माणसाच्या हातामध्ये एकच शस्त्र आहे. ते म्हणजे, काकुळतीने देवाची प्रार्थना करणे की, देवा! मला यातून सोडव. खाजगी बोलताना गुरुदेव असेच म्हणाले होते की, अत्यंत कळकळीने (प्रार्थना) करणं हे आपल्या हातामध्ये आहे. हा एक मार्ग आपल्याला मोकळा आहे. परमेश्वर ते करीलच असे मात्र कोणी म्हणू नये.'
)
new_dup_para_2 = (
    'एक चिमणी झाडावर बसलेली आहे. खालच्या बाजूला पारधी हातामध्ये बाण घेऊन उभा आहे, वरती ससाणा फिरतो आहे आणि ती चिमणी अत्यंत काकुळतीने देवाला म्हणत आहे की, देवा ! हे दोन्ही बाजूनी संकट आहे. पारध्याच्या हातातून सुटून जावं म्हटलं तर वरती ससाणा आहे. आता तुझ्याशिवाय मला कोणी नाही. असं सर्वस्व देवावर टाकलं म्हणजे देव त्या दोन संकटांना छेद देतो. त्यांनी म्हटलं आहे की, पारध्याच्या पायाला साप चावला, तो मरून पडला आणि साप चावल्यामुळे त्याचा नेम चुकला आणि तो ससाण्याला लागला. परमेश्वराला शरण गेले तर दोन्ही संकटे याप्रमाणे दूर होतात. अर्थात् हा ऐहिक संकटांचा विचार झाला. हे घडेल का नाही, हे सांगणं कठीण आहे. परंतु, त्यांचा मुख्य मुद्दा हा की, जर प्रसंग आला तर माणसाच्या हातामध्ये एकच शस्त्र आहे. ते म्हणजे, काकुळतीने देवाची प्रार्थना करणे की, देवा! मला यातून सोडव. खाजगी बोलताना गुरुदेव असेच म्हणाले होते की, अत्यंत कळकळीने (प्रार्थना) करणं हे आपल्या हातामध्ये आहे. हा एक मार्ग आपल्याला मोकळा आहे. परमेश्वर ते करीलच असे मात्र कोणी म्हणू नये.'
)
text = do(text, 'F4', old_dup_para_2, new_dup_para_2, 1,
          'HIGH SEV: paragraph-scale duplication L1047+L1049 removed; L1043 + L1045 + L1051 preserved as clean flow')

# ══════════════════════════════════════════════════════════════════════
# F5: L3-5 opening `ज्ञ`-conjunct OCR run (L1942–1946)
# ══════════════════════════════════════════════════════════════════════
# Elsewhere in the file `ज्ञान` and `ज्ञानेश्वर` are correctly spelled.
# The `जान`/`जाता` words are also valid Marathi elsewhere ("goes/going"),
# so we anchor with enough context to only hit L1942–1946.

# `जाता, जेय, जान हे` — this exact 4-word sequence appears only at L1942.
text = do(text, 'F5a', 'जाता, जेय, जान हे', 'ज्ञाता, ज्ञेय, ज्ञान हे', 1,
          'F5 OCR: restore ज्ञ-conjunct in `ज्ञाता, ज्ञेय, ज्ञान`')

# `जानरूपी` — appears exclusively on L1942, twice.
text = do(text, 'F5b', 'जानरूपी', 'ज्ञानरूपी', 2,
          'F5 OCR: restore ज्ञ-conjunct in ज्ञानरूपी (2x on L1942)')

# `जानच त्याचं` — unique to L1942.
text = do(text, 'F5c', 'जानच त्याचं', 'ज्ञानच त्याचं', 1,
          'F5 OCR: restore ज्ञ-conjunct in ज्ञानच')

# `जानेश्वरांनी हीच उपमा` — L1942 unique context.
text = do(text, 'F5d', 'जानेश्वरांनी हीच उपमा', 'ज्ञानेश्वरांनी हीच उपमा', 1,
          'F5 OCR: restore ज्ञानेश्वर at L1942')

# `दुसरा जानेश्वरांनी` — L1946 unique context.
text = do(text, 'F5e', 'दुसरा जानेश्वरांनी', 'दुसरा ज्ञानेश्वरांनी', 1,
          'F5 OCR: restore ज्ञानेश्वर at L1946')

# ══════════════════════════════════════════════════════════════════════
# CLASS A: single-line find/replace fixes
# ══════════════════════════════════════════════════════════════════════

# ─── F6: OCR letter-split at L1752 ────────────────────────────────────
text = do(text, 'F6', 'सांगितल्याप्रमाणे क रावसं', 'सांगितल्याप्रमाणे करावसं', 1,
          'F6 OCR: rejoin `क रावसं` -> `करावसं` at L1752')

# ─── F7: Duplicated word at L147 page-join ────────────────────────────
text = do(text, 'F7', 'साक्षात्काराच्या साक्षात्काराच्या,',
          'साक्षात्काराच्या', 1,
          'F7 page-join: drop duplicated word + trailing comma at L147')

# ─── F8: Broken sentence at L319 page-join ────────────────────────────
# The tail "आहे." was rejoined onto the wrong side of "कारण,"; needs to sit
# at the end of "जायचं" to form "जायचं आहे."
text = do(text, 'F8', 'करायला पाहिजे. कारण, आहे. त्यांच्या पावलावर पाऊल ठेवून आपल्याला जायचं',
          'करायला पाहिजे. कारण, त्यांच्या पावलावर पाऊल ठेवून आपल्याला जायचं आहे.', 1,
          'F8 page-join: reorder `कारण, आहे.` scramble at L319')

# ─── F9: English quotation word-order scrambled at L385 ───────────────
text = do(text, 'F9',
          'the process identification with the Divine of constant',
          'the process of constant identification with the Divine', 1,
          'F9 page-join: fix scrambled English word-order at L385')

# ─── F10: Sentence broken across pages at L1073 ───────────────────────
text = do(text, 'F10',
          'त्यांनी आपल्याला मृत्यू केव्हा परमेश्वराजवळ मागणी केलेली आहे. यावा, याच्या संबंधानी',
          'त्यांनी परमेश्वराजवळ मृत्यू केव्हा यावा, याच्या संबंधानी मागणी केलेली आहे.', 1,
          'F10 page-join: reorder mangled sentence at L1073 per QA')

# ─── F11: Sanskrit shloka one-word-per-line at L1582–1596 ─────────────
# First cascade only: rejoin `अध्यायात, / ओमित्येकाक्षरं / ब्रह्म । / याच्याबद्दल / ज्ञानेश्वर / म्हणतात`
# into a single sentence.
old_f11 = (
    'अध्यायात,\n\n'
    'ओमित्येकाक्षरं\n\n'
    'ब्रह्म ।\n\n'
    'याच्याबद्दल\n\n'
    'ज्ञानेश्वर\n\n'
    'म्हणतात\n\n'
    'म्हणोनि प्रणवैकनाम'
)
new_f11 = (
    'अध्यायात, "ओमित्येकाक्षरं ब्रह्म ।" याच्याबद्दल ज्ञानेश्वर म्हणतात\n\n'
    'म्हणोनि प्रणवैकनाम'
)
text = do(text, 'F11', old_f11, new_f11, 1,
          'F11 bad-split: 6-word cascade around Gita 8 shloka rejoined into one line at L1582–1594')

# ─── F12: Verse pada कालः orphaned (L43–45) ───────────────────────────
text = do(text, 'F12', 'तत्रार्पिता नियमितः स्मरणे न\n\nकालः !',
          'तत्रार्पिता नियमितः स्मरणे न कालः !', 1,
          'F12 bad-split: rejoin `स्मरणे न कालः`')

# ─── F13: Verse pada नानुरागः orphaned (L47–49) ───────────────────────
# Also splits citation `नाममाहात्म्य` onto its own line.
text = do(text, 'F13', 'दुदैवमीदृशमिह अजनि\n\nनानुरागः !! नाममाहात्म्य',
          'दुदैवमीदृशमिह अजनि नानुरागः !!\n\nनाममाहात्म्य', 1,
          'F13 bad-split: rejoin `अजनि नानुरागः` and float citation')

# ─── F14: Colophon राजाधिराज glued to end of verse (L53) ──────────────
# Also fixes F28-a (citation `जा. ९.५१६` should be `जा. ९.५१५`).
text = do(text, 'F14',
          'जिया पावसी अव्यंग ! निजधाम माझें !! जा. ९.५१६ ! राजाधिराज\nश्रीसद्गुरुनाथमहाराज की जय !',
          'जिया पावसी अव्यंग ! निजधाम माझें !! जा. ९.५१५ !\n\n॥ राजाधिराज श्रीसद्गुरुनाथमहाराज की जय ॥', 1,
          'F14 + F28-a: split invocation onto own line at L53–54; also corrects जा.९.५१६ -> जा.९.५१५')

# ─── F16: 3-word cascade `समर्थांनी / एका / ठिकाणी` (L496–500) ─────────
text = do(text, 'F16',
          'समर्थांनी\n\nएका\n\nठिकाणी सांगितलं आहे,\n\nगुरुदेवांचीही',
          'समर्थांनी एका ठिकाणी सांगितलं आहे,\n\nगुरुदेवांचीही', 1,
          'F16 bad-split: rejoin 3-word cascade at L496–500')

# ─── F17: Stray closing `"` after single-quote (L402–403) ─────────────
text = do(text, 'F17',
          'तरीच महिमान कळो येई ।\'"',
          'तरीच महिमान कळो येई ।\'', 1,
          'F17 punctuation: strip stray double-quote after single-quote at L403')

# ─── F18: Stray closing `"` after अर्थातर (L398) ──────────────────────
text = do(text, 'F18', 'मनने अर्थातर काढी ।"', 'मनने अर्थातर काढी ।\'', 1,
          'F18 punctuation: change closing `"` to `\'` at L398')

# ─── F19: Word-break dashes injected mid-sentence ─────────────────────
# Only the three clearly-in-prose forms flagged in the QA; skip the ambiguous
# trailing-dash cases without a wider read of the printed original.
text = do(text, 'F19a', 'त्याला असमाधान - आहे.', 'त्याला असमाधान आहे.', 1,
          'F19 orphan-dash: L287')
text = do(text, 'F19b', 'याची माहिती - करून घेणं', 'याची माहिती करून घेणं', 1,
          'F19 orphan-dash: L313')
text = do(text, 'F19c', 'आत्तापर्यंत झाली ती - साधनाची',
          'आत्तापर्यंत झाली ती साधनाची', 1,
          'F19 orphan-dash: L361')

# ─── F20: OCR-dropped म in हणजे (L1103) ───────────────────────────────
text = do(text, 'F20', "'आपहि दरस दिखावे' हणजे", "'आपहि दरस दिखावे' म्हणजे", 1,
          'F20 OCR: restore leading म in `म्हणजे` at L1103')

# ─── F21: Citation typo `शा. २.२५९` -> `ज्ञा. २.२५९` (L1183) ──────────
text = do(text, 'F21', 'हें न करीं । शा. २.२५९', 'हें न करीं । ज्ञा. २.२५९', 1,
          'F21 OCR citation: `शा.` -> `ज्ञा.` at L1183')

# ─── F22: Two shlokas glued on one line at L1534 ──────────────────────
text = do(text, 'F22',
          'न बिभेति कदाचन । तै.उप.२-४ न बिभेति कुतश्चनेति । तै.उप.२-९',
          'न बिभेति कदाचन । तै.उप.२-४\nन बिभेति कुतश्चनेति । तै.उप.२-९', 1,
          'F22 formatting: insert line-break between two Taittiriya citations at L1534')

# ─── F23: Stray bullet `●` mid-prose (L287, L1458) ────────────────────
text = do(text, 'F23a', 'सांगितली आहेत. ● पहिलं', 'सांगितली आहेत. पहिलं', 1,
          'F23 formatting: drop mid-prose bullet at L287')
text = do(text, 'F23b', 'मोठ्यांदा नाम ● घेण्यात',
          'मोठ्यांदा नाम घेण्यात', 1,
          'F23 formatting: drop mid-prose bullet at L1458')

# ─── F26: `परमेश्वराच्या आनंदानी` fragment repeated (L1305–1307) ───────
text = do(text, 'F26',
          'परमेश्वराच्या आनंदानी\n\nसदा ते भरलेले असल्यामुळे, त्यांच्या मनामध्ये त्रास ( त्रास म्हणजे, गुरुदेव म्हणतात, कोणच्याही प्रकारचा विक्षेप येणं, आळस येणं, निष्क्रिय असणं) हे संभवतच नाही. कारण, परमेश्वराच्या आनंदानी ते भरलेले आहेत.',
          'परमेश्वराच्या आनंदानी सदा ते भरलेले असल्यामुळे, त्यांच्या मनामध्ये त्रास ( त्रास म्हणजे, गुरुदेव म्हणतात, कोणच्याही प्रकारचा विक्षेप येणं, आळस येणं, निष्क्रिय असणं) हे संभवतच नाही. कारण, ते भरलेले आहेत.',
          1,
          'F26 page-join: merge L1305 fragment into L1307; strip echoed phrase')

# ─── F27: Split `साक्षात्कारवाद - वादात` at L245 ──────────────────────
text = do(text, 'F27', 'साक्षात्कार - वादात', 'साक्षात्कारवादात', 1,
          'F27 OCR: rejoin split compound `साक्षात्कारवादात` at L245')

# ─── F28-b: Citation typo `जा. १.५१५` -> `जा. ९.५१५` at L510 ──────────
# (F28-a was folded into F14 above.)
text = do(text, 'F28b',
          'निजधाम माझें ॥ जा. १.५१५',
          'निजधाम माझें ॥ जा. ९.५१५', 1,
          'F28b OCR citation: 1.515 -> 9.515 at L510')

# ─── F29: OCR `सचिवदानंद` -> `सच्चिदानंद` at L1946 ────────────────────
text = do(text, 'F29', 'सचिवदानंदाचे', 'सच्चिदानंदाचे', 1,
          'F29 OCR: `सचिवदानंदाचे` -> `सच्चिदानंदाचे` at L1946')

# ══════════════════════════════════════════════════════════════════════
# CLASS C: chapter-end blessing normalization
# ══════════════════════════════════════════════════════════════════════
# Canonical form (per instructions): `॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥`.
# Vol 3 blessings frequently include the `श्री` prefix — the instructions
# EXPLICITLY say do not normalize that out. Only normalize danda spacing.
# Six blessing occurrences observed via grep:
#   L265  `। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।`   (single, with श्री)
#   L581  `। राजाधिराज सद्गुरुनाथ महाराज की जय ।`      (single, no श्री)
#   L804  `॥ राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ॥`  (already canonical form)
#   L925  `॥राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ॥`   (no leading space)
#   L1285 `॥राजाधिराज श्रीसद्गुरूनाथ महाराज की जय ॥`   (no leading space + श्रीसद्गुरू with दीर्घ ऊ)
#   L2252 `। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।`   (single, with श्री)

# C-with-श्री single-danda variant: appears at L265 and L2252, 2× identical.
text = do(text, 'C-a',
          '। राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ।',
          '॥ राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ॥', 2,
          'blessing normalization: single-danda -> double-danda; preserve श्री prefix (L265, L2252)')

# C-no-श्री single-danda variant: L581 only.
text = do(text, 'C-b',
          '। राजाधिराज सद्गुरुनाथ महाराज की जय ।',
          '॥ राजाधिराज सद्गुरुनाथ महाराज की जय ॥', 1,
          'blessing normalization: single-danda -> double-danda; no श्री on L581')

# C-with-श्री fused-danda: L925 has `॥राजाधिराज` (no leading space).
text = do(text, 'C-c',
          '॥राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ॥',
          '॥ राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ॥', 1,
          'blessing normalization: add space after leading ॥ at L925')

# C-with-श्री and दीर्घ-ऊ variant: L1285 uses `श्रीसद्गुरू` (long ū).
text = do(text, 'C-d',
          '॥राजाधिराज श्रीसद्गुरूनाथ महाराज की जय ॥',
          '॥ राजाधिराज श्रीसद्गुरुनाथ महाराज की जय ॥', 1,
          'blessing normalization: fix दीर्घ-ऊ to लघु-उ and add space at L1285')

# ══════════════════════════════════════════════════════════════════════
# CLASS B: findings intentionally left alone (logged for human review)
# ══════════════════════════════════════════════════════════════════════
log_lines.append(
    '### Class B (LEFT ALONE — needs human/source review)\n\n'
    '- **F15** `जातील केवि` at L1131 — final word + citation lost at page-break; '
    'restoring the pada requires the printed source.\n'
    '- **F24** `जो अमृतासि ठी ठेवी` at L818, L1231, L1690 — the `ठी` looks like a nonword, '
    'but the identical repetition across 3 sites suggests it may be a house-style rendering; '
    'standard reading of the ओवी is `अमृतासि उबगला`. Needs source check.\n'
    '- **F25** `बहिन्याने` (L210) vs `बहिन्यांनी` (L469) — same folk pada rendered two '
    'different ways; possibly dialectal, possibly OCR. Needs editor call.\n'
    '- **F30** `मसी बोलू नका` (L2040) vs `आता बोलो नका` (L668) — same तुकाराम अभंग '
    'rendered two ways in the same volume. Needs source-PDF cross-check.\n'
)

# ─── Write output + log ──────────────────────────────────────────────
DST.write_text(text, encoding='utf-8')
new_bytes = len(text.encode('utf-8'))
new_lines = text.count('\n')

log_lines.insert(1,
    f'**Applied:** {applied} fixes\n'
    f'**Skipped (count mismatch):** {skipped}\n'
    f'**Bytes:** {orig_bytes:,} -> {new_bytes:,} ({new_bytes - orig_bytes:+,})\n'
    f'**Lines:** {orig_lines:,} -> {new_lines:,} ({new_lines - orig_lines:+,})\n'
    f'\n---\n'
)
LOG.write_text('\n'.join(log_lines), encoding='utf-8')

print(f'Applied {applied}, skipped {skipped}. Wrote {DST} and {LOG}.')
