from specdelta.diff.clause_diff import compare_texts, diff_clauses, in_scope, normalize_line
from specdelta.ingest.parse_docx import Clause


def clause(clause_id, title, text):
    return Clause("38.300", "Rel-x", "0.0.0", clause_id, title, path=[], text=text)


def by_id(diffs):
    return {d.clause_id: d for d in diffs}


def test_statuses():
    old = [
        clause("1", "Scope", "This spec covers NR."),
        clause("2", "References", "TS 38.304 [20]: idle mode."),
        clause("3", "Paging", "Paging uses P-RNTI.\nThe UE monitors one PO."),
        clause("4", "Old feature", "Something that was dropped."),
    ]
    new = [
        clause("1", "Scope", "This spec covers NR."),
        # only the reference number and spacing differ
        clause("2", "References", "TS 38.304 [21]:  idle mode ."),
        clause("3", "Paging", "Paging uses P-RNTI.\nThe UE monitors one or more POs."),
        clause("5", "Energy saving", "Cell DTX/DRX is supported."),
    ]
    diffs = by_id(diff_clauses(old, new))

    assert diffs["1"].status == "unchanged"
    assert diffs["2"].status == "unchanged"
    assert diffs["3"].status == "changed"
    assert diffs["3"].lines_added == 1 and diffs["3"].lines_removed == 1
    assert diffs["3"].changed_words == 3  # "PO." -> "or more POs."
    assert "+The UE monitors one or more POs." in diffs["3"].diff
    assert diffs["4"].status == "removed"
    assert diffs["5"].status == "added"


def test_renumbered_clause_is_matched_by_title_and_text():
    text = "The MAC entity shall apply the logical channel prioritization procedure."
    old = [clause("5.22.1", "Logical channel prioritization", text)]
    new = [clause("5.31", "Logical channel prioritization", text + " Also for SL-PRS.")]
    diffs = diff_clauses(old, new)

    assert len(diffs) == 1
    assert diffs[0].status == "changed"
    assert diffs[0].old_clause_id == "5.22.1"


def test_same_generic_title_with_different_text_is_not_matched():
    old = [clause("5.1", "General", "Random access is initiated by PDCCH order.")]
    new = [clause("7.1", "General", "Cell DTX can be activated by DCI or MAC CE.")]
    statuses = sorted(d.status for d in diff_clauses(old, new))
    assert statuses == ["added", "removed"]


def test_normalize_line():
    assert (
        normalize_line("see  TS 38.304 [20], [21]  “quoted” – x") == 'see TS 38.304, "quoted" - x'
    )


def test_compare_ignores_punctuation_only_changes():
    assert compare_texts("TS38.340, defines", "TS 38.340 defines")[-1] == ""


def test_in_scope():
    assert in_scope("15.4", "15.4")
    assert in_scope("15.4.2.3", "15.4")
    assert not in_scope("15.40", "15.4")
    assert in_scope("anything", "")
