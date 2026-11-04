import math
import re
import unicodedata
from collections import Counter

from project_memory.domain.models import Evidence, ProviderUnavailable, SearchResult
from project_memory.domain.ports import Embedder, MemoryStore

STOP_WORDS = frozenset(
    [
        "ve",
        "veya",
        "bir",
        "bu",
        "şu",
        "için",
        "ile",
        "mi",
        "mı",
        "mu",
        "mü",
        "ne",
        "neden",
        "nasıl",
        "hangi",
        "olarak",
        "the",
        "a",
        "an",
        "is",
        "of",
        "to",
        "and",
        "why",
        "how",
        "what",
    ]
)


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold().replace("ı", "i"))
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9_]+", normalized) if t not in STOP_WORDS]


def bm25(query: list[str], documents: list[list[str]]) -> list[float]:
    if not documents:
        return []
    avg_length = sum(len(d) for d in documents) / len(documents) or 1
    frequencies = Counter(t for document in documents for t in set(document))
    scores: list[float] = []
    for document in documents:
        counts = Counter(document)
        score = 0.0
        for term in set(query):
            frequency = counts[term]
            if frequency:
                inverse = math.log(
                    1 + (len(documents) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
                )
                score += (
                    inverse
                    * frequency
                    * 2.2
                    / (frequency + 1.2 * (0.25 + 0.75 * len(document) / avg_length))
                )
        scores.append(score)
    return scores


class Retriever:
    def __init__(
        self, store: MemoryStore, embedder: Embedder | None = None, minimum_dense_score: float = 0.4
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.minimum_dense_score = minimum_dense_score

    def search(self, project_id: str, question: str, limit: int = 5) -> SearchResult:
        candidates = self.store.chunks(project_id)
        if not candidates:
            return SearchResult((), "lexical")
        lexical = bm25(tokenize(question), [tokenize(c.title + " " + c.text) for c in candidates])
        ranks = [
            sorted(
                (i for i, score in enumerate(lexical) if score > 0),
                key=lambda i: lexical[i],
                reverse=True,
            )
        ]
        warnings: list[str] = []
        mode = "lexical"
        if self.embedder:
            try:
                batch = self.embedder.embed([question])
                vector = batch.vectors[0]
                stored_scores = self.store.dense_scores(project_id, batch.space, vector)
                dense = {
                    i: stored_scores[c.id]
                    for i, c in enumerate(candidates)
                    if c.id in stored_scores
                }
                semantic = sorted(
                    (i for i, score in dense.items() if score >= self.minimum_dense_score),
                    key=lambda i: dense[i],
                    reverse=True,
                )
                if semantic:
                    ranks.append(semantic)
                    mode = "hybrid"
                elif not dense:
                    warnings.append(
                        "Bu model sürümünde indekslenmiş kaynak yok; sözcük araması kullanıldı."
                    )
                else:
                    warnings.append("Anlamsal eşleşme eşiği aşılmadı; sözcük araması kullanıldı.")
            except ProviderUnavailable:
                warnings.append("Embedding modeli erişilemiyor; sözcük araması kullanıldı.")
        fused: dict[int, float] = {}
        for ranking in ranks:
            for rank, index in enumerate(ranking[:20], start=1):
                fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
        top = sorted(fused, key=lambda i: fused[i], reverse=True)[:limit]
        return SearchResult(
            tuple(Evidence(candidates[i], fused[i]) for i in top), mode, tuple(warnings)
        )
