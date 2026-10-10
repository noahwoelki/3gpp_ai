from specdelta.ingest import chunk as chunk_module
from specdelta.ingest.chunk import chunk_clause, split_notes, table_chunks
from specdelta.ingest.parse_docx import Clause
from specdelta.ingest.tables import frequency_range, strip_notes


def paragraph(text):
    return {"type": "paragraph", "style": "Normal", "text": text}


def band_table(row_count):
    rows = [["Band", "Duplex"]]
    rows += [[f"n{i}" + (" (note 2)" if i == 3 else ""), "FDD"] for i in range(1, row_count + 1)]
    rows.append(["NOTE 1: Only for band n1. NOTE 2: Restricted band."] * 2)
    return {
        "type": "table",
        "table_id": "5.2/1",
        "caption": "Table 5.2-1: Bands",
        "header_rows": 1,
        "rows": rows,
    }


def test_table_chunks_repeat_header_and_only_needed_notes(monkeypatch):
    monkeypatch.setattr(chunk_module, "TABLE_MAX_WORDS", 0)  # forces the 100 word minimum
    chunks = table_chunks(band_table(60))

    assert len(chunks) > 1
    for row_start, row_end, content in chunks:
        lines = content.split("\n")
        assert lines[0].startswith("Table 5.2-1: Bands (rows ")
        assert lines[1] == "Band | Duplex"
        assert row_start <= row_end

    first_content = chunks[0][2]
    assert "n3 (note 2) | FDD" in first_content
    assert "NOTE 2: Restricted band." in first_content
    assert "NOTE 1" not in first_content  # no row in this chunk mentions note 1
    assert "NOTE 2" not in chunks[-1][2]


def test_small_table_is_one_chunk_without_row_range_label():
    chunks = table_chunks(band_table(3))
    assert len(chunks) == 1
    row_start, row_end, content = chunks[0]
    assert (row_start, row_end) == (1, 3)
    assert content.split("\n")[0] == "Table 5.2-1: Bands"


def test_continuation_rows_stay_with_their_entry(monkeypatch):
    monkeypatch.setattr(chunk_module, "TABLE_MAX_WORDS", 0)
    rows = [["Band", "SCS", "Bandwidth"]]
    for band in range(1, 30):
        rows += [[f"n{band}", "15", "5, 10, 15, 20"], ["", "30", "10, 15, 20"]]
    table = {"type": "table", "table_id": "x/1", "caption": "", "header_rows": 1, "rows": rows}
    for row_start, _, _ in table_chunks(table):
        assert rows[row_start][0] != ""  # every chunk starts at a band, not a continuation


def test_split_notes():
    notes = split_notes([["NOTE 1: First. NOTE 12: Twelfth."], ["NOTE: Unnumbered."]])
    assert notes == {"1": "NOTE 1: First.", "12": "NOTE 12: Twelfth.", "": "NOTE: Unnumbered."}


def test_chunk_clause_text_and_table():
    blocks = [
        paragraph("Bands are listed below, see clause 5.3."),
        paragraph("Table 5.2-1: Bands"),
        band_table(3),
        paragraph("More text after the table."),
    ]
    clause = Clause("38.101-1", "Rel-18", "18.15.0", "5.2", "Operating bands", [], blocks=blocks)
    chunks = chunk_clause(clause)
    assert [c.kind for c in chunks] == ["text", "table"]

    text, table = chunks
    assert text.header == "[38.101-1 Rel-18 §5.2 Operating bands]"
    # The caption paragraph stands in for the table, so there is no extra placeholder
    assert text.content == (
        "Bands are listed below, see clause 5.3.\nTable 5.2-1: Bands\nMore text after the table."
    )
    assert text.referenced_clauses == ["5.3"]
    assert (text.block_start, text.block_end) == (0, 3)
    assert (table.table_id, table.block_start, table.row_start, table.row_end) == ("5.2/1", 2, 1, 3)
    assert text.chunk_id != table.chunk_id


def test_long_text_is_split_with_overlap(monkeypatch):
    monkeypatch.setattr(chunk_module, "MAX_WORDS", 10)
    blocks = [paragraph(f"para {i} " + "word " * 4) for i in range(6)]
    clause = Clause("38.300", "Rel-18", "18.11.0", "9", "Title", [], blocks=blocks)
    chunks = chunk_clause(clause)
    assert len(chunks) > 1
    # The last paragraph of one chunk is repeated at the start of the next
    assert chunks[0].content.split("\n")[-1] == chunks[1].content.split("\n")[0]


def test_typed_table_helpers():
    assert strip_notes("n102 (note 13), (note 14)") == "n102"
    assert frequency_range("1626.5 MHz – 1660.5 MHz") == (1626.5, 1660.5)
    assert frequency_range("N/A") == (None, None)


def test_large_table_chunks_are_not_embedded(monkeypatch):
    monkeypatch.setattr(chunk_module, "TABLE_MAX_WORDS", 0)
    small = band_table(3)
    large = dict(band_table(200), table_id="5.2/2")  # 200 rows give more than 3 chunks
    clause = Clause("38.101-1", "Rel-18", "18.15.0", "5.2", "Bands", [], blocks=[small, large])
    chunks = chunk_clause(clause)
    assert all(c.embed for c in chunks if c.table_id == "5.2/1")
    assert not any(c.embed for c in chunks if c.table_id == "5.2/2")
