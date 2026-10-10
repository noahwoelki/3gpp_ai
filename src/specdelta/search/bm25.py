"""BM25 keyword ranking over the chunk texts, in memory.

BigQuery SEARCH only says whether a row matches, it gives no score, so keyword ranking
happens here. The corpus is small (a few thousand chunks, a few MB of text).

The tokenizer keeps 3GPP identifiers whole and also adds their parts, so
"CA_n3A-n78A" gives the tokens "ca_n3a-n78a", "ca", "n3a" and "n78a". A query for the
exact identifier then scores high, and a query for just "n78a" still matches.
"""

import math
import re
from collections import Counter, defaultdict

K1 = 1.5
B = 0.75

WORD = re.compile(r"[a-z0-9]+(?:[_\-./][a-z0-9]+)*")
STOPWORDS = set(
    "a an and are as at be by can do does for from has have how if in into is it its "
    "may of on or shall should that the their then there these this to was what when "
    "where which while who why will with".split()
)


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in WORD.findall(text.lower()):
        if word in STOPWORDS:
            continue
        tokens.append(word)
        parts = re.split(r"[_\-./]", word)
        if len(parts) > 1:
            tokens += [p for p in parts if p and p not in STOPWORDS]
    return tokens


class BM25Index:
    """Inverted index with BM25 scoring. Documents are (doc_id, text) pairs."""

    def __init__(self, documents: list[tuple[str, str]]):
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)  # token -> (doc, tf)
        self.doc_ids = []
        self.lengths = []
        for index, (doc_id, text) in enumerate(documents):
            counts = Counter(tokenize(text))
            self.doc_ids.append(doc_id)
            self.lengths.append(sum(counts.values()))
            for token, count in counts.items():
                self.postings[token].append((index, count))
        self.average_length = sum(self.lengths) / max(len(self.lengths), 1)

    def idf(self, token: str) -> float:
        df = len(self.postings.get(token, []))
        n = len(self.doc_ids)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(
        self, query: str, top_k: int, allowed: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """Best (doc_id, score) pairs. If allowed is given, only those doc ids are returned."""
        scores: dict[int, float] = defaultdict(float)
        for token in set(tokenize(query)):
            idf = self.idf(token)
            for index, tf in self.postings.get(token, []):
                norm = K1 * (1 - B + B * self.lengths[index] / self.average_length)
                scores[index] += idf * tf * (K1 + 1) / (tf + norm)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        results = []
        for index, score in ranked:
            doc_id = self.doc_ids[index]
            if allowed is None or doc_id in allowed:
                results.append((doc_id, score))
                if len(results) == top_k:
                    break
        return results
