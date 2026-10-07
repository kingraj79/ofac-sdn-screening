"""Parse the OFAC SDN XML into the small shape the matcher needs."""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

from .matching import normalize

YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


@dataclass
class SdnEntry:
    uid: str
    names: set[str] = field(default_factory=set)  # normalized primary name + aliases
    surnames: dict[str, str] = field(default_factory=dict)  # name -> its surname, when known
    dob_full: set[str] = field(default_factory=set)  # ISO dates, e.g. "1924-02-21"
    dob_years: set[int] = field(default_factory=set)


def parse_dob(text: str) -> tuple[str | None, set[int]]:
    """Return (full ISO date or None, years) for an SDN date of birth string.

    SDN dates are free text: "21 Feb 1924", "Feb 1924", "1924", "circa 1924",
    "1960 to 1962". Only the first form is a full date; a range covers every
    year in it.
    """
    text = text.strip()
    try:
        d = datetime.strptime(text, "%d %b %Y").date()
        return d.isoformat(), {d.year}
    except ValueError:
        pass
    years = [int(y) for y in YEAR_RE.findall(text)]
    if len(years) == 2 and " to " in text.lower():
        return None, set(range(min(years), max(years) + 1))
    return None, set(years)


def _strip_namespaces(root: ET.Element) -> None:
    for el in root.iter():
        el.tag = el.tag.rsplit("}", 1)[-1]


def _add_names(entry: SdnEntry, el: ET.Element) -> None:
    """Add the full name, plus "first given name + last name" since SDN first names
    often carry middle names ("Robert Gabriel") that accounts leave out."""
    first = normalize(el.findtext("firstName") or "")
    last = normalize(el.findtext("lastName") or "")
    if not first:  # single-field alias: the surname can't be told apart
        if last:
            entry.names.add(last)
        return
    for name in (f"{first} {last}".strip(), f"{first.split()[0]} {last}".strip()):
        entry.names.add(name)
        if last:
            entry.surnames[name] = last


def load_sdn(path: str) -> list[SdnEntry]:
    """Load SDN entries of type Individual (accounts are people, and only people have DOBs)."""
    root = ET.parse(path).getroot()
    _strip_namespaces(root)

    entries = []
    for node in root.iter("sdnEntry"):
        if node.findtext("sdnType") != "Individual":
            continue
        entry = SdnEntry(uid=node.findtext("uid"))
        for name_el in [node, *node.iter("aka")]:
            _add_names(entry, name_el)
        for dob_el in node.iter("dateOfBirth"):
            full, years = parse_dob(dob_el.text or "")
            if full:
                entry.dob_full.add(full)
            entry.dob_years |= years
        entries.append(entry)
    return entries
