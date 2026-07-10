import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import chunk_quality as cq

# Real prose (Marathi) scores high
MR_PROSE = ("रामभाऊंनी बांधलेल्या 'कार्लाइल कॉटेज' चा उल्लेख मागें आलाच आहे. "
            "'कार्लाइल कॉटेज' हौसेची असली तरी बेताची होती. त्यामुळे प्रकृतीला "
            "मानवेल व ध्यानधारणेला सोयीची होईल, अशी एखादी निवांत जागा त्यांना पाहिजे होती.")
# Real prose (English) must ALSO score high — corpus is trilingual
EN_PROSE = ("Bhakti does not consist in religious ceremonials, pilgrimages, or "
            "formal idol-worship; it consists in love to God, and through the love "
            "of God, in the love of man. This is the foundation of his teaching.")

def test_real_marathi_prose_high():
    assert cq.quality_score(MR_PROSE) >= 0.7
    assert cq.is_junk(MR_PROSE) is False

def test_real_english_prose_high():
    # The report's Devanagari-ratio heuristic would wrongly flag this; ours must not.
    assert cq.quality_score(EN_PROSE) >= 0.7
    assert cq.is_junk(EN_PROSE) is False

def test_heading_marker_is_junk():
    assert cq.is_junk("## Part 13") is True
    assert cq.is_junk("<!-- page 025 -->  (2)") is True
    assert cq.is_junk("काकांची चर्चा") is True  # bare title, <100 chars

def test_village_digit_list_is_junk():
    lst = "२० मोजे डि कसाळ  ३१ मोजे कागनरी  २१ मोजे कात्राळ  ३२ मौजे गुरवि नाळ  २२ मोजे करनाळ  ३३ मौजे करोळी"
    assert cq.is_junk(lst) is True  # high digit ratio + no stopwords

def test_symbol_garble_is_junk():
    assert cq.is_junk("aataziga ळटपवृक्षवन्जयु काणि रय्य ( राग-पुरि या धनाध्रि ; तार") is True
