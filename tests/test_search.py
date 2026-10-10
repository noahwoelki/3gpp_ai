from specdelta.search.bm25 import BM25Index, tokenize
from specdelta.search.hybrid import Hit, SearchFilters, fuse, one_hit_per_table, resolve_scope


def test_tokenize_keeps_identifiers_and_their_parts():
    tokens = tokenize("The CA_n3A-n78A configuration, see TS 38.300.")
    assert "ca_n3a-n78a" in tokens
    assert {"ca", "n3a", "n78a"} <= set(tokens)
    assert "38.300" in tokens
    assert "the" not in tokens


def test_bm25_ranks_matching_documents_first():
    index = BM25Index(
        [
            ("dtx", "Cell DTX reduces gNB energy consumption with cell DTX patterns."),
            ("paging", "Paging allows the network to reach UEs in RRC_IDLE."),
            ("ca", "CA_n3A-n78A is an inter-band CA configuration."),
        ]
    )
    assert index.search("cell DTX energy", top_k=3)[0][0] == "dtx"
    assert index.search("CA_n3A-n78A", top_k=1)[0][0] == "ca"
    assert [doc for doc, _ in index.search("n78A", top_k=3)] == ["ca"]
    assert index.search("paging", top_k=3, allowed={"dtx", "ca"}) == []


def test_fuse_prefers_chunks_found_by_both():
    chunks = {cid: {"chunk_id": cid, "content": ""} for cid in "abcd"}
    hits = fuse(["a", "b", "c"], ["c", "d"], chunks)
    assert hits[0].chunk["chunk_id"] == "c"  # rank 3 + rank 1 beats rank 1 alone
    assert hits[0].found_by == "both"
    by_id = {h.chunk["chunk_id"]: h for h in hits}
    assert by_id["a"].found_by == "vector" and by_id["d"].found_by == "keyword"
    assert by_id["b"].keyword_rank is None


def test_resolve_scope_defaults_to_latest_release():
    available = {"38.300": ["Rel-17", "Rel-18"], "21.905": ["Rel-19"]}
    assert resolve_scope(SearchFilters(), available) == {("38.300", "Rel-18"), ("21.905", "Rel-19")}
    assert resolve_scope(SearchFilters(specs=["38.300"], releases=["Rel-17"]), available) == {
        ("38.300", "Rel-17")
    }
    assert resolve_scope(SearchFilters(releases=["Rel-17", "Rel-18"]), available) == {
        ("38.300", "Rel-17"),
        ("38.300", "Rel-18"),
    }
    assert resolve_scope(SearchFilters(specs=["38.321"]), available) == set()


def test_one_hit_per_table():
    def hit(chunk_id, table_id):
        chunk = {
            "chunk_id": chunk_id,
            "spec": "38.101-1",
            "release": "Rel-18",
            "table_id": table_id,
        }
        return Hit(chunk, 1, None, 0.0)

    hits = [hit("a", "6.2/1"), hit("b", "6.2/1"), hit("c", None), hit("d", "6.2/2"), hit("e", None)]
    assert [h.chunk["chunk_id"] for h in one_hit_per_table(hits, top_k=3)] == ["a", "c", "d"]
