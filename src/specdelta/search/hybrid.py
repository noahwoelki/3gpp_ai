"""Hybrid search over the chunks (F1).

1. Vector search in BigQuery (VECTOR_SEARCH, cosine) on the embedded chunks.
2. BM25 keyword search in memory over all chunks, including the keyword-only row chunks
   of large tables.
3. Merge both rankings with reciprocal rank fusion.
4. Rerank the merged candidates with the Vertex AI ranking API.
5. Keep one hit per table. If the whole table fits FULL_TABLE_MAX_WORDS, the hit carries
   the full table instead of the matched chunk, so the LLM sees all rows and notes.
   Bigger tables keep the matched chunk and are marked as partial.

Searches are limited to a set of specs and releases (SearchFilters). Without a release
filter, each spec is searched in its latest release only.

The chunk texts are loaded from BigQuery once (a few MB) and kept in memory, both for
BM25 and to return the hits without a second query.
"""

import json
from dataclasses import dataclass

from google.cloud import bigquery

from specdelta import config
from specdelta.ingest.embed import embed, make_client
from specdelta.ingest.parse_docx import table_as_text
from specdelta.search.bm25 import BM25Index
from specdelta.search.rerank import rerank

CANDIDATES = 30  # per retriever, and the number of merged results sent to the reranker
RRF_K = 60  # standard constant, keeps the top ranks from dominating too much
FULL_TABLE_MAX_WORDS = 1500  # about 2000 tokens, 95% of all tables fit


@dataclass
class SearchFilters:
    specs: list[str] | None = None  # None means all specs
    releases: list[str] | None = None  # None means the latest release of each spec


@dataclass
class Hit:
    chunk: dict  # the chunk row without its embedding
    vector_rank: int | None
    keyword_rank: int | None
    rrf_score: float
    rerank_score: float | None = None
    content: str = ""  # what the LLM gets: the chunk content, or the full table
    full_table: bool | None = None  # None for text hits, False if only part of the table

    @property
    def found_by(self) -> str:
        if self.vector_rank and self.keyword_rank:
            return "both"
        return "vector" if self.vector_rank else "keyword"

    @property
    def table_key(self) -> tuple[str, str, str] | None:
        if self.chunk["table_id"] is None:
            return None
        return (self.chunk["spec"], self.chunk["release"], self.chunk["table_id"])


def release_number(release: str) -> int:
    return int(release.removeprefix("Rel-"))


def resolve_scope(filters: SearchFilters, available: dict[str, list[str]]) -> set[tuple[str, str]]:
    """The (spec, release) pairs to search in."""
    scope = set()
    for spec, releases in available.items():
        if filters.specs is not None and spec not in filters.specs:
            continue
        if filters.releases is None:
            scope.add((spec, max(releases, key=release_number)))
        else:
            scope.update((spec, r) for r in releases if r in filters.releases)
    return scope


class Searcher:
    def __init__(self):
        self.bq = bigquery.Client(project=config.PROJECT_ID)
        self.genai = make_client()
        self.dataset = f"{config.PROJECT_ID}.{config.BQ_DATASET}"
        rows = self.bq.query(f"SELECT * EXCEPT (embedding) FROM `{self.dataset}.chunks`").result()
        self.chunks = {row["chunk_id"]: dict(row) for row in rows}
        self.bm25 = BM25Index(
            [(cid, f"{c['header']}\n{c['content']}") for cid, c in self.chunks.items()]
        )
        # Specs and their releases in the corpus, e.g. {"38.300": ["Rel-17", "Rel-18"]},
        # also what a UI would offer as filter choices
        self.available: dict[str, list[str]] = {}
        for c in self.chunks.values():
            releases = self.available.setdefault(c["spec"], [])
            if c["release"] not in releases:
                releases.append(c["release"])
        for releases in self.available.values():
            releases.sort(key=release_number)
        self.full_tables: dict[tuple[str, str, str], str | None] = {}  # cache, None = too big

    def vector_search(self, query: str, scope: set[tuple[str, str]]) -> list[str]:
        vector = embed(self.genai, query, "RETRIEVAL_QUERY")
        sql = f"""
            SELECT base.chunk_id
            FROM VECTOR_SEARCH(
              (SELECT chunk_id, embedding FROM `{self.dataset}.chunks`
               WHERE embed AND CONCAT(spec, '|', release) IN UNNEST(@scope)),
              'embedding',
              (SELECT @query_embedding AS embedding),
              top_k => {CANDIDATES},
              distance_type => 'COSINE')
            ORDER BY distance
        """
        params = [
            bigquery.ArrayQueryParameter("query_embedding", "FLOAT64", vector),
            bigquery.ArrayQueryParameter("scope", "STRING", [f"{s}|{r}" for s, r in scope]),
        ]
        job = self.bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
        return [row["chunk_id"] for row in job.result()]

    def keyword_search(self, query: str, scope: set[tuple[str, str]]) -> list[str]:
        allowed = {cid for cid, c in self.chunks.items() if (c["spec"], c["release"]) in scope}
        return [cid for cid, _ in self.bm25.search(query, CANDIDATES, allowed)]

    def load_full_tables(self, keys: set[tuple[str, str, str]]) -> None:
        """Fetch tables from spec_tables into the cache, as caption + all rows as text."""
        missing = [k for k in keys if k not in self.full_tables]
        if not missing:
            return
        sql = f"""
            SELECT spec, release, table_id, caption, table_rows
            FROM `{self.dataset}.spec_tables`
            WHERE CONCAT(spec, '|', release, '|', table_id) IN UNNEST(@keys)
        """
        params = [bigquery.ArrayQueryParameter("keys", "STRING", ["|".join(k) for k in missing])]
        job = self.bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
        for row in job.result():
            rows = json.loads(row["table_rows"])
            text = f"{row['caption']}\n{table_as_text(rows)}".strip()
            too_big = len(text.split()) > FULL_TABLE_MAX_WORDS
            self.full_tables[(row["spec"], row["release"], row["table_id"])] = (
                None if too_big else text
            )

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        top_k: int = 8,
        use_reranker: bool = True,
    ) -> list[Hit]:
        scope = resolve_scope(filters or SearchFilters(), self.available)
        if not scope:
            return []
        vector_ids = self.vector_search(query, scope)
        keyword_ids = self.keyword_search(query, scope)
        hits = fuse(vector_ids, keyword_ids, self.chunks)[:CANDIDATES]

        if use_reranker:
            records = [(h.chunk["chunk_id"], h.chunk["header"], h.chunk["content"]) for h in hits]
            scores = rerank(query, records)
            for hit in hits:
                hit.rerank_score = scores.get(hit.chunk["chunk_id"], 0.0)
            hits.sort(key=lambda h: h.rerank_score, reverse=True)

        hits = one_hit_per_table(hits, top_k)
        self.load_full_tables({h.table_key for h in hits if h.table_key})
        for hit in hits:
            if hit.table_key:
                full = self.full_tables.get(hit.table_key)
                hit.full_table = full is not None
                hit.content = full if full is not None else hit.chunk["content"]
        return hits


def fuse(vector_ids: list[str], keyword_ids: list[str], chunks: dict[str, dict]) -> list[Hit]:
    """Reciprocal rank fusion: each list adds 1 / (RRF_K + rank) for every chunk it found."""
    vector_rank = {cid: rank for rank, cid in enumerate(vector_ids, start=1)}
    keyword_rank = {cid: rank for rank, cid in enumerate(keyword_ids, start=1)}
    hits = []
    for cid in vector_rank.keys() | keyword_rank.keys():
        score = sum(
            1 / (RRF_K + ranks[cid]) for ranks in (vector_rank, keyword_rank) if cid in ranks
        )
        chunk = chunks[cid]
        hits.append(
            Hit(chunk, vector_rank.get(cid), keyword_rank.get(cid), score, content=chunk["content"])
        )
    hits.sort(key=lambda h: h.rrf_score, reverse=True)
    return hits


def one_hit_per_table(hits: list[Hit], top_k: int) -> list[Hit]:
    """Keep the best hit of each table (hits are sorted best first), up to top_k hits.
    The table itself is attached later, so further chunks of it add nothing."""
    result = []
    seen_tables = set()
    for hit in hits:
        if hit.table_key:
            if hit.table_key in seen_tables:
                continue
            seen_tables.add(hit.table_key)
        result.append(hit)
        if len(result) == top_k:
            break
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid search over the spec chunks")
    parser.add_argument("query")
    parser.add_argument("--spec", action="append", help="repeat for several specs")
    parser.add_argument("--release", action="append", help="default: latest release per spec")
    parser.add_argument("--show", action="store_true", help="print the content of each hit")
    args = parser.parse_args()

    filters = SearchFilters(specs=args.spec, releases=args.release)
    for hit in Searcher().search(args.query, filters):
        c = hit.chunk
        table = {None: "", True: " (full table)", False: " (partial table)"}[hit.full_table]
        print(
            f"{hit.rerank_score:.2f} {hit.found_by:7s} {c['spec']} {c['release']} "
            f"§{c['clause_id']} [{c['kind']}]{table} {c['title'][:60]}"
        )
        if args.show:
            print("    " + hit.content[:1500].replace("\n", "\n    ") + "\n")


if __name__ == "__main__":
    main()
