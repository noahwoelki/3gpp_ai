from specdelta.tools.spec_tools import matching_rows


def test_matching_rows_includes_continuation_rows():
    data = [
        ["CA_n1A-n3A-n105A", "n1", "5, 10"],
        ["", "n3", "5, 10"],
        ["", "n105", "5, 10"],
        ["CA_n1A-n5A-n7A", "n1", "5"],
        ["", "n5", "5"],
        ["CA_n2A-n105A-n66A", "n2", "5"],
    ]
    assert matching_rows(data, "n105a") == [0, 1, 2, 5]
    assert matching_rows(data, "n5") == [3, 4]  # the match is in a continuation row
    assert matching_rows(data, "n99") == []
