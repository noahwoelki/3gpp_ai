"""Functions the agents (and later the MCP server) call to read the specs.

Every function returns a plain dict that can go straight into an LLM context. Problems
like an unknown clause come back as {"error": "..."} instead of an exception, so the
agent can read the message and try something else.
"""

import json
import re

from google.adk.tools import ToolContext
from google.cloud import bigquery

from specdelta import config
from specdelta.ingest.chunk import is_note_row, mentioned_notes, split_notes
from specdelta.ingest.parse_docx import table_as_text
from specdelta.search.hybrid import FULL_TABLE_MAX_WORDS, Searcher, SearchFilters

CLAUSE_MAX_CHARS = 20000  # a few clauses in 38.101-1 are far bigger (CA tables)
TABLE_PREVIEW_ROWS = 40
MATCHING_ROWS_MAX = 60

_searcher: Searcher | None = None
_bq: bigquery.Client | None = None


def searcher() -> Searcher:
    global _searcher
    if _searcher is None:
        _searcher = Searcher()
    return _searcher


def bq() -> bigquery.Client:
    global _bq
    if _bq is None:
        _bq = bigquery.Client(project=config.PROJECT_ID)
    return _bq


def citation(spec: str, release: str, clause_id: str) -> str:
    return f"[{spec} {release} §{clause_id}]"


def query_one(sql: str, **params: str) -> dict | None:
    """Run a query with string parameters and return the first row, or None."""
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter(k, "STRING", v) for k, v in params.items()]
    )
    rows = list(bq().query(sql, job_config=job_config).result())
    return dict(rows[0]) if rows else None


def search_specs(
    query: str,
    specs: list[str] | None = None,
    releases: list[str] | None = None,
    tool_context: ToolContext | None = None,
) -> dict:
    """Search the 3GPP specifications for passages relevant to a question.

    Args:
        query: The question or search terms, e.g. "How does cell DTX/DRX work?".
        specs: Optional list of spec numbers to search in, e.g. ["38.300", "38.321"].
        releases: Optional list of releases, e.g. ["Rel-17"]. If not given, the latest
            release of each spec is searched.

    Returns:
        The best matching passages, each with a citation like "[38.300 Rel-18 §15.4.2.3]"
        to use in the answer. Table results may hold the full table or only part of it
        (full_table false), in which case search_table_rows can find more rows.
    """
    # Filters chosen in the UI are a hard limit and replace what the agent asked for
    if tool_context is not None:
        ui_filters = tool_context.state.get("ui_filters") or {}
        specs = ui_filters.get("specs") or specs
        releases = ui_filters.get("releases") or releases
    hits = searcher().search(query, SearchFilters(specs=specs, releases=releases))
    results = []
    for hit in hits:
        c = hit.chunk
        results.append(
            {
                "citation": citation(c["spec"], c["release"], c["clause_id"]),
                "spec": c["spec"],
                "release": c["release"],
                "clause_id": c["clause_id"],
                "title": c["title"],
                "path": " > ".join(c["path"]),
                "kind": c["kind"],
                "table_id": c["table_id"],
                "full_table": hit.full_table,
                "found_by": hit.found_by,
                "rerank_score": round(hit.rerank_score or 0.0, 3),
                "content": hit.content,
                # Where the hit is in the clause, used by the UI to highlight it
                "chunk_id": c["chunk_id"],
                "block_start": c["block_start"],
                "block_end": c["block_end"],
                "row_start": c["row_start"],
                "row_end": c["row_end"],
            }
        )
    return {"results": results}


def get_clause(spec: str, release: str, clause_id: str) -> dict:
    """Get the full text of one clause of a spec.

    Args:
        spec: Spec number, e.g. "38.300".
        release: Release, e.g. "Rel-18".
        clause_id: Clause number, e.g. "15.4.2.3".

    Returns:
        Title, path and text of the clause. Very long clauses are cut off (truncated true).
    """
    row = query_one(
        f"""SELECT title, path, text FROM `{config.PROJECT_ID}.{config.BQ_DATASET}.clauses`
            WHERE spec = @spec AND release = @release AND clause_id = @clause_id""",
        spec=spec,
        release=release,
        clause_id=clause_id,
    )
    if row is None:
        return {"error": f"Clause {clause_id} not found in {spec} {release}."}
    text = row["text"] or "(this clause has no text of its own, see its subclauses)"
    return {
        "citation": citation(spec, release, clause_id),
        "title": row["title"],
        "path": " > ".join(row["path"]),
        "text": text[:CLAUSE_MAX_CHARS],
        "truncated": len(text) > CLAUSE_MAX_CHARS,
    }


def load_table(spec: str, release: str, table_id: str) -> dict | None:
    return query_one(
        f"""SELECT clause_id, caption, header_rows, table_rows
            FROM `{config.PROJECT_ID}.{config.BQ_DATASET}.spec_tables`
            WHERE spec = @spec AND release = @release AND table_id = @table_id""",
        spec=spec,
        release=release,
        table_id=table_id,
    )


def get_table(spec: str, release: str, table_id: str) -> dict:
    """Get a table from a spec. Large tables only return the header and the first rows,
    use search_table_rows to find specific rows in them.

    Args:
        spec: Spec number, e.g. "38.101-1".
        release: Release, e.g. "Rel-18".
        table_id: Table id as given in search results, e.g. "5.2/1".
    """
    table = load_table(spec, release, table_id)
    if table is None:
        return {"error": f"Table {table_id} not found in {spec} {release}."}
    rows = json.loads(table["table_rows"])
    text = table_as_text(rows)
    complete = len(text.split()) <= FULL_TABLE_MAX_WORDS
    if not complete:
        header, data = rows[: table["header_rows"]], rows[table["header_rows"] :]
        text = table_as_text(header + data[:TABLE_PREVIEW_ROWS])
    return {
        "citation": citation(spec, release, table["clause_id"]),
        "caption": table["caption"],
        "table": text,
        "complete": complete,
        "total_rows": len(rows) - table["header_rows"],
    }


def search_terms(text: str) -> list[str]:
    """Split "n78 and n105" or "n78, n105" into ["n78", "n105"]."""
    words = re.split(r"[\s,;]+", text.strip())
    return [w for w in words if w and w.lower() not in ("and", "or", "with")]


def matching_rows(data: list[list[str]], text: str) -> list[int]:
    """Indexes of the rows of all entries that contain every search term (case-insensitive).

    An entry is a row plus the rows that continue it: a row with an empty first cell
    belongs to the entry above, e.g. the other bands of the same CA configuration. So
    "n78 n105" finds configurations that have n78 in one row and n105 in another."""
    entries: list[list[int]] = []
    for index, row in enumerate(data):
        if row[0] == "" and entries:
            entries[-1].append(index)
        else:
            entries.append([index])

    terms = [term.lower() for term in search_terms(text)]
    matching = []
    for entry in entries:
        entry_text = " ".join(cell for i in entry for cell in data[i]).lower()
        if terms and all(term in entry_text for term in terms):
            matching += entry
    return matching


def search_table_rows(spec: str, release: str, table_id: str, text: str) -> dict:
    """Find the rows of a table that contain some text, e.g. a band or CA configuration.

    Args:
        spec: Spec number, e.g. "38.101-1".
        release: Release, e.g. "Rel-18".
        table_id: Table id as given in search results, e.g. "5.5A.3.2/1".
        text: One or more terms, case-insensitive, e.g. "n78", "CA_n3A-n78A" or
            "n78 n105". With several terms, an entry (a row plus the rows continuing it)
            matches only if it contains all of them.

    Returns:
        The header, the matching rows (plus the rows that continue them) and the notes
        these rows refer to.
    """
    table = load_table(spec, release, table_id)
    if table is None:
        return {"error": f"Table {table_id} not found in {spec} {release}."}
    rows = json.loads(table["table_rows"])
    header, data = rows[: table["header_rows"]], rows[table["header_rows"] :]
    notes = split_notes([row for row in data if is_note_row(row)])
    data = [row for row in data if not is_note_row(row)]

    matching = matching_rows(data, text)
    found = [data[i] for i in matching[:MATCHING_ROWS_MAX]]
    wanted = mentioned_notes(table_as_text(header + found)) | {""}
    return {
        "citation": citation(spec, release, table["clause_id"]),
        "caption": table["caption"],
        "header": table_as_text(header),
        "rows": table_as_text(found),
        "notes": [note for number, note in notes.items() if number in wanted],
        "matching_rows": len(matching),
        "truncated": len(matching) > MATCHING_ROWS_MAX,
    }


def lookup_term(term: str, spec: str | None = None) -> dict:
    """Look up an abbreviation or defined term, e.g. "SSB" or "CAG Cell".

    Args:
        term: The abbreviation or term, case-insensitive.
        spec: Optional spec number. Entries of this spec are listed first, because the
            same abbreviation can mean different things in different specs.
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("term", "STRING", term),
            bigquery.ScalarQueryParameter("spec", "STRING", spec),
        ]
    )
    sql = f"""
        SELECT spec, release, clause_id, kind, term, text
        FROM `{config.PROJECT_ID}.{config.BQ_DATASET}.glossary`
        WHERE LOWER(term) = LOWER(@term)
        ORDER BY spec = @spec DESC, spec = '21.905' DESC, release DESC
        LIMIT 10
    """
    rows = [dict(r) for r in bq().query(sql, job_config=job_config).result()]
    if not rows:
        return {"error": f"'{term}' is not in the glossary."}
    # The same entry often appears in Rel-17 and Rel-18, keep the first of each meaning
    entries, seen = [], set()
    for row in rows:
        key = (row["spec"], row["text"])
        if key not in seen:
            seen.add(key)
            row["citation"] = citation(row["spec"], row["release"], row["clause_id"])
            entries.append(row)
    return {"entries": entries}
