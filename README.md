# OFAC SDN Screening Service

A small FastAPI service that screens the customer accounts in `data/accounts.csv`
against the individuals on the U.S. Treasury OFAC SDN list (`data/sdn.xml`).

## Setup & run

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn --factory app.main:create_app
```

`data/accounts.csv` (the accounts file supplied with the assessment) is not in
this repository; copy it into `data/` before starting the service.

`data/sdn.xml` is the SDN list published 10/05/2026. To refresh it:

```bash
curl -L -o data/sdn.xml https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML
```

The file locations can be overridden with the `SDN_PATH` and `ACCOUNTS_PATH`
environment variables.

## API

| Action | Method & path | Notes |
|---|---|---|
| Bulk screening | `POST /screenings` | Screens every row of `accounts.csv`. Returns one object per account, including accounts with no matches (`"matches": []`). Add `?matches_only=true` to return only accounts with at least one match. |
| Single account | `GET /screenings/{account_id}` | Returns one object; `404` if the account id is not in the CSV. |

```bash
curl -X POST "localhost:8000/screenings?matches_only=true"
curl localhost:8000/screenings/1001
```

```json
{"account_id": "1001", "matches": [{"uid": "30962", "confidence": "HIGH", "match_types": ["NAME_EXACT", "DOB_FULL"]}]}
```

Matches are ordered highest confidence first. Interactive docs are at `/docs`.

## Tests

```bash
.venv/bin/python -m pytest
```

`tests/test_matching.py` unit-tests normalization, DOB parsing, the confidence
table, and the matcher. `tests/test_api.py` runs both endpoints against a small
fixture SDN file and CSV.

## Design choices

**Layout.** `app/sdn.py` parses the XML, `app/matching.py` holds all matching
rules, `app/main.py` is the HTTP layer. The SDN list is parsed once at startup;
`accounts.csv` is re-read on each request so edits are picked up.

**Only individuals are screened.** Accounts are people, and only `Individual`
SDN entries carry dates of birth, so entities, vessels and aircraft are skipped
(7,492 of 19,363 entries are kept).

**Name normalization.** Uppercase, accents stripped, punctuation turned into
spaces, whitespace collapsed, so `AL-SAMAHY` equals `Al Samahy`.

**Which names are compared.**
- Account: `first last`, and `first middle last` when a middle name exists.
- SDN: the primary name and every alias (a.k.a., strong and weak), each as
  `firstName lastName`, plus a `first given name + lastName` variant. SDN first
  names usually include middle names (`Robert Gabriel`), which accounts often omit.

The best-scoring pair of variants decides the match.

**Fuzzy match.** Jaro-Winkler similarity ≥ 0.90 on the normalized full name
(`rapidfuzz`), **and** Jaro-Winkler ≥ 0.90 on the surname. The surname condition
is an addition to the brief: full-name Jaro-Winkler alone scores
`Alexander Lopez` vs `Alexander Kozlov` at 0.92, and without it about 7,400 of
the 50,000 accounts were flagged; with it, 889 are. It is skipped for aliases
that OFAC publishes as a single field with no first/last split.

**Exact match.** Normalized names are identical. Because of the variants above,
an account `Robert Mugabe` is an exact match for SDN `Robert Gabriel MUGABE`.

**Dates of birth.** SDN dates are free text. `21 Feb 1924` is a full date;
`Feb 1924`, `1924` and `circa 1924` give a year only; `1960 to 1962` covers each
year in the range. An entry may list several dates, and any of them can match.

**Confidence.**

| Name | DOB | Confidence | `match_types` |
|---|---|---|---|
| fuzzy | none | LOW | `NAME_FUZZY` |
| fuzzy | year | MED | `NAME_FUZZY`, `DOB_YEAR` |
| fuzzy | full | HIGH | `NAME_FUZZY`, `DOB_FULL` |
| exact | year | HIGH | `NAME_EXACT`, `DOB_YEAR` |
| exact | full | HIGH | `NAME_EXACT`, `DOB_FULL` |
| exact | none | LOW | `NAME_EXACT` |

The last row is not in the brief; an exact name with no DOB support is reported
as LOW rather than dropped. Each match reports only its strongest name type and
strongest DOB type.

**Performance.** The 50,000 accounts contain about 15,000 distinct names, so
each distinct name is scored once against the ~26,000 SDN names using
`rapidfuzz.process.cdist` in batches. Bulk screening takes about 2 seconds.

## Results on the provided data

889 accounts have at least one match: 2 HIGH (accounts 1001 and 17620), 15 MED
and 898 LOW matches in total.

## Known limitations

- The 0.90 threshold misses some close variants, e.g. account 1002
  `Ala Al Samahy` scores 0.88 against `Allaa AL-SAMAHY`.
- `country` and `employer` are not used.
- Name order is assumed to be given-name-first; reordered names are not matched.
- Bulk results are recomputed on every request (no caching or persistence).
- Robert Mugabe, who appears in the sample accounts, is no longer on the SDN
  list, so those rows do not match him.

## AI tools used

Built with Claude Code (Anthropic, Claude Opus model), which wrote the code,
tests and this README.
