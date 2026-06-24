import retrieve


def test_canonical_kind_is_canonical_tier():
    assert retrieve.chunk_tier({"kind": "canonical"}) == "canonical"


def test_athvani_and_biography_are_recollections():
    assert retrieve.chunk_tier({"kind": "athvani"}) == "recollections"
    assert retrieve.chunk_tier({"kind": "biography"}) == "recollections"


def test_reference_kind_is_reference_tier():
    assert retrieve.chunk_tier({"kind": "reference"}) == "reference"


def test_unknown_or_missing_kind_defaults_to_recollections():
    assert retrieve.chunk_tier({"kind": "something-else"}) == "recollections"
    assert retrieve.chunk_tier({}) == "recollections"
