"""Name / DOB matching and confidence rules."""
import re
import unicodedata

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

FUZZY_THRESHOLD = 0.90
CHUNK = 1000  # account names scored per batch, keeps the score matrix small

_RANK = {"HIGH": 0, "MED": 1, "LOW": 2}


def normalize(name: str) -> str:
    """Uppercase, strip accents, turn punctuation into spaces, collapse whitespace."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", name.upper()).split())


def name_similarity(a: str, b: str) -> float:
    return JaroWinkler.normalized_similarity(normalize(a), normalize(b))


def is_fuzzy(a: str, b: str) -> bool:
    return JaroWinkler.normalized_similarity(a, b) >= FUZZY_THRESHOLD


def account_names(account: dict) -> set[str]:
    """Normalized "first last" and, when present, "first middle last"."""
    first, middle, last = (account.get(k) or "" for k in ("first_name", "middle_name", "last_name"))
    names = {normalize(f"{first} {last}")}
    if middle.strip():
        names.add(normalize(f"{first} {middle} {last}"))
    names.discard("")
    return names


def classify(exact: bool, dob: str, entry) -> tuple[str, list[str]]:
    """Confidence and match_types for an account/SDN pair whose names already match."""
    types = ["NAME_EXACT" if exact else "NAME_FUZZY"]
    if dob and dob in entry.dob_full:
        return "HIGH", types + ["DOB_FULL"]
    if dob[:4].isdigit() and int(dob[:4]) in entry.dob_years:
        return ("HIGH" if exact else "MED"), types + ["DOB_YEAR"]
    return "LOW", types


def screen(accounts: list[dict], entries: list) -> list[dict]:
    """Screen accounts against SDN entries; one result per account, in input order."""
    sdn_names, sdn_surnames, sdn_owner = [], [], []
    for i, entry in enumerate(entries):
        for name in entry.names:
            sdn_names.append(name)
            sdn_surnames.append(entry.surnames.get(name))
            sdn_owner.append(i)

    # Many accounts share a name, so score each distinct (name, surname) once.
    by_name: dict[tuple[str, str], list[int]] = {}
    for i, account in enumerate(accounts):
        surname = normalize(account.get("last_name") or "")
        for name in account_names(account):
            by_name.setdefault((name, surname), []).append(i)
    queries = list(by_name)

    # (account index, entry index) -> True if any name variant matched exactly
    hits: dict[tuple[int, int], bool] = {}
    for start in range(0, len(queries), CHUNK):
        chunk = queries[start:start + CHUNK]
        scores = process.cdist(
            [name for name, _ in chunk], sdn_names,
            scorer=JaroWinkler.normalized_similarity,
            score_cutoff=FUZZY_THRESHOLD,
            workers=-1,
        )
        for q, s in zip(*np.nonzero(scores)):
            name, surname = chunk[q]
            # Full-name similarity alone pairs "Alexander Lopez" with "Alexander
            # Kozlov" (shared first name + prefix bonus), so the surnames must agree too.
            if sdn_surnames[s] and not is_fuzzy(surname, sdn_surnames[s]):
                continue
            exact = name == sdn_names[s]
            for a in by_name[chunk[q]]:
                key = (a, sdn_owner[s])
                hits[key] = hits.get(key, False) or exact

    results = [{"account_id": a["account_id"], "matches": []} for a in accounts]
    for (a, e), exact in hits.items():
        confidence, types = classify(exact, accounts[a].get("dob") or "", entries[e])
        results[a]["matches"].append(
            {"uid": entries[e].uid, "confidence": confidence, "match_types": types}
        )
    for result in results:
        result["matches"].sort(key=lambda m: (_RANK[m["confidence"]], int(m["uid"])))
    return results
