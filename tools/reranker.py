"""Cross-encoder reranker (BAAI/bge-reranker-v2-m3), lazy + fail-safe.

Retrieval is a bi-encoder: query and passage are embedded independently, so
relevance is never judged against the actual query. A cross-encoder scores
(query, passage) jointly with full attention and recomputes relevance from
scratch — the tool that rescues a buried-but-relevant passage (MMR cannot).

Loaded once, in-process, at first use. Any load/scoring failure disables the
reranker (available()==False, rerank()==[]) so the caller falls back to the
existing MMR ranking. `scorer`/`loader` hooks let tests avoid a model download.
"""
from __future__ import annotations
from typing import Callable, Optional

_MODEL = "BAAI/bge-reranker-v2-m3"


class Reranker:
    def __init__(
        self,
        *,
        scorer: Optional[Callable[[list], list]] = None,
        loader: Optional[Callable[[], Callable[[list], list]]] = None,
    ) -> None:
        self._scorer = scorer
        self._loader = loader or _default_loader
        self._tried = scorer is not None

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        try:
            self._scorer = self._loader()
        except Exception:
            self._scorer = None

    def available(self) -> bool:
        self._ensure()
        return self._scorer is not None

    def rerank(self, query: str, passages: list) -> list:
        """Return one relevance score per passage (higher = more relevant).

        Returns [] on unavailability/failure so the caller can detect it and
        fall back. Never raises.
        """
        if not passages:
            return []
        self._ensure()
        if self._scorer is None:
            return []
        try:
            pairs = [[query, p] for p in passages]
            scores = self._scorer(pairs)
            return [float(s) for s in scores]
        except Exception:
            return []


def _default_loader() -> Callable[[list], list]:
    """Load bge-reranker-v2-m3 via FlagEmbedding; return a pair-scoring fn."""
    from FlagEmbedding import FlagReranker
    fr = FlagReranker(_MODEL, use_fp16=True)  # auto-detects CUDA; CPU/MPS otherwise
    def score(pairs: list) -> list:
        out = fr.compute_score(pairs, normalize=True)
        return out if isinstance(out, list) else [out]
    return score


_singleton: Optional[Reranker] = None


def get_reranker() -> Reranker:
    global _singleton
    if _singleton is None:
        _singleton = Reranker()
    return _singleton
