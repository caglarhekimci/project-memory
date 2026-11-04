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


def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    denominator = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / denominator if denominator else 0.0


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
    def __init__(self, store: MemoryStore, embedder: Embedder | None = None) -> None:
        self.store = store
        self.embedder = embedder

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
                dense = {
                    i: cosine(vector, c.embedding)
                    for i, c in enumerate(candidates)
                    if c.embedding is not None and c.embedding_space == batch.space
                }
                semantic = sorted(
                    (i for i, score in dense.items() if score >= 0.5),
                    key=lambda i: dense[i],
                    reverse=True,
                )
                if dense:
                    ranks.append(semantic)
                    mode = "hybrid"
                else:
                    warnings.append(
                        "Bu model sürümünde indekslenmiş kaynak yok; sözcük araması kullanıldı."
                    )
            except ProviderUnavailable:
                warnings.append("Embedding modeli erişilemiyor; sözcük araması kullanıldı.")
        fused: Counter[int] = Counter()
        for ranking in ranks:
            for rank, index in enumerate(ranking[:20], start=1):
                fused[index] += 1 / (60 + rank)
        top = sorted(fused, key=lambda i: fused[i], reverse=True)[:limit]
        return SearchResult(
            tuple(Evidence(candidates[i], fused[i]) for i in top), mode, tuple(warnings)
        )
