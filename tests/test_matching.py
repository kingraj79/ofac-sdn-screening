import pytest

from app.matching import account_names, classify, name_similarity, normalize, screen
from app.sdn import SdnEntry, parse_dob


def entry(**kw):
    defaults = dict(uid="1", names={"JOHN SMITH"}, dob_full={"1970-03-15"}, dob_years={1970})
    return SdnEntry(**{**defaults, **kw})


def account(first="John", last="Smith", dob="1970-03-15", middle="", account_id="A1"):
    return {"account_id": account_id, "first_name": first, "middle_name": middle,
            "last_name": last, "dob": dob}


@pytest.mark.parametrize("raw,expected", [
    ("AL-SAMAHY", "AL SAMAHY"),
    ("  José   Núñez ", "JOSE NUNEZ"),
    ("O'Brien, Pat", "O BRIEN PAT"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_name_similarity_threshold():
    assert name_similarity("Robert Mugabe", "ROBERT MUGABE") == 1.0
    assert name_similarity("Roboert Mugabe", "Robert Mugabe") >= 0.90
    assert name_similarity("James Lee", "Robert Mugabe") < 0.90


def test_account_names_include_middle_variant():
    assert account_names(account(middle="Q")) == {"JOHN SMITH", "JOHN Q SMITH"}
    assert account_names(account()) == {"JOHN SMITH"}


@pytest.mark.parametrize("text,full,years", [
    ("21 Feb 1924", "1924-02-21", {1924}),
    ("Feb 1924", None, {1924}),
    ("1924", None, {1924}),
    ("circa 1960", None, {1960}),
    ("1960 to 1962", None, {1960, 1961, 1962}),
    ("", None, set()),
])
def test_parse_dob(text, full, years):
    assert parse_dob(text) == (full, years)


@pytest.mark.parametrize("exact,dob,confidence,types", [
    (False, "1999-01-01", "LOW", ["NAME_FUZZY"]),
    (False, "1970-01-01", "MED", ["NAME_FUZZY", "DOB_YEAR"]),
    (False, "1970-03-15", "HIGH", ["NAME_FUZZY", "DOB_FULL"]),
    (True, "1970-01-01", "HIGH", ["NAME_EXACT", "DOB_YEAR"]),
    (True, "1970-03-15", "HIGH", ["NAME_EXACT", "DOB_FULL"]),
    (True, "1999-01-01", "LOW", ["NAME_EXACT"]),
    (True, "", "LOW", ["NAME_EXACT"]),
])
def test_classify(exact, dob, confidence, types):
    assert classify(exact, dob, entry()) == (confidence, types)


def test_screen_fuzzy_and_exact():
    results = screen([account(first="Jon"), account(), account(first="Maria", last="Lopez")], [entry()])
    assert results[0]["matches"] == [
        {"uid": "1", "confidence": "HIGH", "match_types": ["NAME_FUZZY", "DOB_FULL"]}]
    assert results[1]["matches"][0]["match_types"] == ["NAME_EXACT", "DOB_FULL"]
    assert results[2] == {"account_id": "A1", "matches": []}


def test_screen_matches_alias_and_prefers_exact():
    e = entry(names={"JOHN SMITH", "JOHNNY SMYTHE"})
    results = screen([account(first="Johnny", last="Smythe", dob="1970-06-06")], [e])
    assert results[0]["matches"] == [
        {"uid": "1", "confidence": "HIGH", "match_types": ["NAME_EXACT", "DOB_YEAR"]}]


def test_screen_sorts_highest_confidence_first():
    entries = [entry(uid="5", dob_full=set(), dob_years=set()), entry(uid="9")]
    matches = screen([account()], entries)[0]["matches"]
    assert [(m["uid"], m["confidence"]) for m in matches] == [("9", "HIGH"), ("5", "LOW")]


def test_screen_requires_surname_agreement():
    e = entry(names={"ALEXANDER KOZLOV"}, surnames={"ALEXANDER KOZLOV": "KOZLOV"})
    assert name_similarity("Alexander Lopez", "Alexander Kozlov") >= 0.90
    assert screen([account(first="Alexander", last="Lopez")], [e])[0]["matches"] == []
    assert screen([account(first="Aleksander", last="Kozlov")], [e])[0]["matches"] != []
