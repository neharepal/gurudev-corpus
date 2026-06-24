import intent


def test_doctrinal_cues():
    assert intent.classify_intent(
        "What is Gurudev's philosophy of self-surrender?", use_llm_fallback=False
    ) == "doctrinal"


def test_narrative_cues_english_and_marathi():
    assert intent.classify_intent(
        "Tell me an athvani about Bhausaheb Maharaj", use_llm_fallback=False
    ) == "narrative"
    assert intent.classify_intent(
        "महाराजांची एखादी आठवण सांगा", use_llm_fallback=False
    ) == "narrative"


def test_navigational_cues():
    assert intent.classify_intent(
        "Which works of Gurudev Ranade are in the corpus?", use_llm_fallback=False
    ) == "navigational"


def test_no_cues_without_fallback_is_unknown():
    assert intent.classify_intent("Hmm.", use_llm_fallback=False) == "unknown"


def test_heuristic_returns_none_when_ambiguous():
    assert intent._heuristic_intent("Hmm.") is None


def test_injected_fallback_used_for_ambiguous_query():
    called = {}

    def stub(q):
        called["q"] = q
        return "doctrinal"

    out = intent.classify_intent("Hmm tell me.", llm_fallback=stub)
    assert out == "doctrinal"
    assert called["q"] == "Hmm tell me."


def test_fallback_exception_resolves_to_unknown():
    def boom(q):
        raise RuntimeError("api down")

    assert intent.classify_intent("Hmm tell me.", llm_fallback=boom) == "unknown"


def test_fallback_bad_label_resolves_to_unknown():
    assert intent.classify_intent(
        "Hmm tell me.", llm_fallback=lambda q: "garbage"
    ) == "unknown"


def test_confident_query_never_calls_fallback():
    def boom(q):
        raise AssertionError("fallback must not run for a confident query")

    assert intent.classify_intent(
        "What is the philosophy of bhakti?", llm_fallback=boom
    ) == "doctrinal"


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResp:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


def _fake_client(reply_text):
    class _FakeClient:
        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            return _FakeResp(reply_text)

    return _FakeClient()


def test_default_fallback_parses_haiku_label(monkeypatch):
    monkeypatch.setattr(intent, "_get_client", lambda: _fake_client("narrative"))
    intent._default_llm_fallback.cache_clear()
    assert intent._default_llm_fallback("some genuinely ambiguous query") == "narrative"


def test_default_fallback_unrecognised_label_returns_none(monkeypatch):
    monkeypatch.setattr(intent, "_get_client", lambda: _fake_client("no idea at all"))
    intent._default_llm_fallback.cache_clear()
    assert intent._default_llm_fallback("another ambiguous query") is None
