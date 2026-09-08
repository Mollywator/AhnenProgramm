# -*- coding: utf-8 -*-
"""The overlay that keeps hand edits alive across a rebuild.

`build_data.py` rewrites `data/tree.json` from scratch every time it runs, so
anything typed into the editor would be gone the moment a new report PDF is
read.  Hand edits therefore never touch `tree.json`.  They live in their own
file, `data/edits.json`, and are folded on top of the parsed tree afterwards -
by the edit server while editing, and by `build_site.py` when the page for the
family is written.

The overlay stores whole person records rather than field level patches.  What
the editor last showed is what is on disk, which makes the file readable and
makes a bad merge impossible.

Two link rules run through everything here, and the editor in the page follows
the same ones:

  * `parents` is the truth about descent.  `children` is *derived* from it, in
    `normalise_links`, exactly the way `build_data.py` derives it from the
    report.  Cutting a parent link therefore cannot leave the child hanging in
    somebody's child list.
  * `spouses` is symmetric and cannot be derived from anything, so both sides
    are written and both sides are repaired here.
"""
from __future__ import annotations

import datetime
import json
import os

# Ids 1 to 326 belong to the report - they are the superscripts printed behind
# the names.  Everything added by hand starts well above that, so re-reading a
# newer PDF can never collide with a person typed in here.
FIRST_NEW_ID = 1001

EDITS_NAME = "edits.json"
DOCS_DIRNAME = "dokumente"

# Fields the report itself fills in.  A hand written record carries them too so
# that every person in the merged tree has the same shape.
BASE_FIELDS = (
    "id", "name", "given", "surname", "sex", "relation", "tree",
    "parents", "spouses", "children", "occupation", "extra", "bio",
    "note_text", "source_text", "notes", "sources", "photo", "events",
    "page", "birth", "death",
)

# Fields that exist only because of the editor.  `build_data.py` never writes
# them, so a person coming straight out of the PDF simply has them empty.
EXTRA_FIELDS = (
    "call_name",    # Rufname - what the person was actually called
    "birth_name",   # Geburtsname / maiden name
    "title",        # academic or noble title
    "religion",     # Konfession
    "burial",       # {year, month, day, place} - Beerdigung
    "residences",   # [{place, address, from, to, note}] - Wohnorte
    "contact",      # {phone, mobile, email, address, note} - living people only
    "freetext",     # the free note field under the sheet
    "documents",    # [{file, title, kind, added}] - scans in data/dokumente/<id>
    "edited",       # ISO timestamp of the last save
    "link",         # the same person in another tree - see verknuepfung.py
)

ALL_FIELDS = BASE_FIELDS + EXTRA_FIELDS


def edits_path(data_dir: str) -> str:
    return os.path.join(data_dir, EDITS_NAME)


def docs_dir(data_dir: str, person_id: int | str | None = None) -> str:
    base = os.path.join(data_dir, DOCS_DIRNAME)
    return base if person_id is None else os.path.join(base, str(person_id))


def empty_edits() -> dict:
    return {"version": 1, "people": {}, "removed": [], "saved": None}


def load_edits(data_dir: str) -> dict:
    """Read the overlay, or hand back an empty one if nobody has edited yet."""
    path = edits_path(data_dir)
    if not os.path.exists(path):
        return empty_edits()
    with open(path, encoding="utf-8") as fh:
        stored = json.load(fh)
    out = empty_edits()
    out.update(stored)
    out["people"] = {str(k): v for k, v in (stored.get("people") or {}).items()}
    out["removed"] = [int(i) for i in (stored.get("removed") or [])]
    return out


def save_edits(data_dir: str, edits: dict) -> None:
    """Write the overlay, via a temporary file so a crash cannot truncate it."""
    edits["saved"] = datetime.datetime.now().isoformat(timespec="seconds")
    path = edits_path(data_dir)
    tmp = path + ".tmp"
    os.makedirs(data_dir, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(edits, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def blank_person(person_id: int) -> dict:
    """A record with every field present and nothing filled in."""
    return {
        "id": int(person_id),
        "name": "", "given": "", "surname": "", "sex": None,
        "relation": None, "tree": None,
        "parents": [], "spouses": [], "children": [],
        "occupation": None, "extra": None,
        "bio": None, "note_text": None, "source_text": None,
        "notes": [], "sources": [], "photo": None,
        "events": [], "page": None,
        "birth": None, "death": None,
        "call_name": None, "birth_name": None, "title": None,
        "religion": None, "burial": None,
        "residences": [], "contact": None, "freetext": None,
        "documents": [], "edited": None, "link": None,
    }


def fill_missing(person: dict) -> dict:
    """Give a record from the PDF the editor's own fields, all empty."""
    out = blank_person(person.get("id", 0))
    out.update(person)
    return out


def next_id(tree: dict, edits: dict) -> int:
    used = {int(p["id"]) for p in tree.get("people", [])}
    used |= {int(k) for k in edits.get("people", {})}
    return max([FIRST_NEW_ID - 1] + [i for i in used if i >= FIRST_NEW_ID]) + 1


def normalise_links(people: list[dict]) -> None:
    """Make the link fields agree with each other, in place.

    `children` is thrown away and rebuilt from `parents`, which is what makes
    cutting a descent link work from either end.  `spouses` is unioned in both
    directions.  Links pointing at somebody who is not in the tree are dropped;
    they would otherwise draw wires to nowhere.
    """
    by_id = {int(p["id"]): p for p in people}

    for person in people:
        person["parents"] = [i for i in dict.fromkeys(int(x) for x in person.get("parents") or [])
                             if i in by_id and i != int(person["id"])]
        person["spouses"] = [i for i in dict.fromkeys(int(x) for x in person.get("spouses") or [])
                             if i in by_id and i != int(person["id"])]
        person["children"] = []

    for person in people:
        for parent in person["parents"]:
            kids = by_id[parent]["children"]
            if int(person["id"]) not in kids:
                kids.append(int(person["id"]))

    for person in people:
        for spouse in list(person["spouses"]):
            other = by_id[spouse]["spouses"]
            if int(person["id"]) not in other:
                other.append(int(person["id"]))


def apply_edits(tree: dict, edits: dict) -> dict:
    """Fold the overlay onto a parsed tree and hand back the merged copy.

    The input is left alone: `build_site.py` and the edit server both keep the
    untouched parse around, and a caller that mutated it by accident would be
    very hard to debug.
    """
    merged = json.loads(json.dumps(tree))
    removed = {int(i) for i in edits.get("removed") or []}
    overlay = edits.get("people") or {}

    people = [fill_missing(p) for p in merged.get("people", [])
              if int(p["id"]) not in removed]
    by_id = {int(p["id"]): p for p in people}

    for key, record in overlay.items():
        pid = int(key)
        if pid in removed:
            continue
        record = fill_missing({**record, "id": pid})
        if pid in by_id:
            by_id[pid].update(record)
        else:
            people.append(record)
            by_id[pid] = record

    people.sort(key=lambda p: int(p["id"]))
    normalise_links(people)

    merged["people"] = people
    merged["meta"] = dict(merged.get("meta") or {})
    merged["meta"]["count"] = len(people)
    merged["meta"]["edited"] = edits.get("saved")
    merged["meta"]["edited_people"] = len(overlay)

    if removed:
        merged["marriages"] = [m for m in merged.get("marriages") or []
                               if not (set(int(x) for x in m.get("people", [])) & removed)]
    return merged


def load_merged(data_dir: str) -> tuple[dict, dict]:
    """The usual entry point: parsed tree plus overlay, already folded."""
    with open(os.path.join(data_dir, "tree.json"), encoding="utf-8") as fh:
        tree = json.load(fh)
    edits = load_edits(data_dir)
    return apply_edits(tree, edits), edits
