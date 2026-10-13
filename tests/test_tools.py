from specdelta.tools.spec_tools import matching_rows, search_terms

DATA = [
    ["CA_n1A-n3A-n105A", "n1", "5, 10"],
    ["", "n3", "5, 10"],
    ["", "n105", "5, 10"],
    ["CA_n1A-n5A-n78A", "n1", "5"],
    ["", "n5", "5"],
    ["", "n78", "10"],
    ["CA_n2A-n78A-n105A", "n2", "5"],
    ["", "n78", "10"],
    ["", "n105", "5"],
]


def test_single_term_returns_whole_entries():
    assert matching_rows(DATA, "n105a") == [0, 1, 2, 6, 7, 8]
    assert matching_rows(DATA, "n5") == [3, 4, 5]  # the match is in a continuation row
    assert matching_rows(DATA, "n99") == []


def test_all_terms_must_be_in_the_same_entry():
    assert matching_rows(DATA, "n78 and n105") == [6, 7, 8]
    assert matching_rows(DATA, "n78, n5") == [3, 4, 5]
    assert matching_rows(DATA, "") == []


def test_search_terms():
    assert search_terms("n78 and n105") == ["n78", "n105"]
    assert search_terms(" CA_n3A-n78A ") == ["CA_n3A-n78A"]
