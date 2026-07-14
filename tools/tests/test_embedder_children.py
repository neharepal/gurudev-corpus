import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import embedder

def test_text_for_embedding_prefers_embed_text():
    assert embedder.text_for_embedding({"text": "raw", "embed_text": "raw + window"}) == "raw + window"
    assert embedder.text_for_embedding({"text": "only"}) == "only"
