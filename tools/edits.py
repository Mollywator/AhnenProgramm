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
        "spouse_kind": {}, "parent_kind": {}, "spouse_info": {},
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

    The two role maps are cleaned up along with the lists they describe.  A
    role for a tie that no longer exists is dropped rather than kept: it would
    come back to life, silently and wrongly, the day that same pair is joined
    again for a different reason.
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

    normalise_roles(people)


# What a tie may be called.  Anything else in the file is treated as unsaid -
# a typo must not turn a marriage into something the program then draws.
SPOUSE_KINDS = ("marriage", "engaged", "partner")
PARENT_KINDS = ("blood", "step")

# Where two records disagree about a couple, the stronger claim wins: somebody
# writes "marriage" on purpose, nobody writes "partner" on purpose about one.
KIND_STRENGTH = {"partner": 1, "engaged": 2, "marriage": 3}

# How a tie ended, if it did.  Being widowed is not in here: it follows from a
# death date, and a second place to say it would be a second place to be wrong.
TIE_ENDS = ("separated", "divorced")

# Stations in a life story that describe a couple.  The key is the station's
# name as typed, folded to lower case; the value says which end of the tie it
# is and what it says about it.
STATION_START = {"heirat": "marriage", "hochzeit": "marriage", "trauung": "marriage",
                 "eheschließung": "marriage", "eheschliessung": "marriage",
                 "verlobung": "engaged", "partnerschaft": "partner"}
STATION_END = {"scheidung": "divorced", "trennung": "separated"}


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def clean_date(raw) -> dict | None:
    """A date as a tie carries it: day, month, year, and whether it is only about."""
    if not isinstance(raw, dict):
        return None
    out = {k: _as_int(raw.get(k)) for k in ("year", "month", "day")}
    if not any(out.values()):
        return None
    out["approx"] = bool(raw.get("approx"))
    return out


def clean_tie(raw) -> dict | None:
    """One entry of `spouse_info`, with anything unreadable dropped. None if empty."""
    if not isinstance(raw, dict):
        return None
    text = lambda v: (str(v).strip() or None) if v not in (None, "") else None
    end = raw.get("end") if raw.get("end") in TIE_ENDS else None
    out = {"since": clean_date(raw.get("since")), "place": text(raw.get("place")),
           "end": end, "until": clean_date(raw.get("until")) if end else None,
           "note": text(raw.get("note"))}
    return out if any(v is not None for v in out.values()) else None


def _weight(tie: dict | None) -> int:
    return sum(1 for v in (tie or {}).values() if v is not None)


def station_role(kind) -> tuple[str, str] | None:
    """("start", "marriage") for a "Heirat", ("end", "divorced") for a "Scheidung"."""
    k = (kind or "").strip().lower() if isinstance(kind, str) else ""
    if k in STATION_START:
        return "start", STATION_START[k]
    if k in STATION_END:
        return "end", STATION_END[k]
    return None


def adopt_stations(people: list[dict], by_id: dict) -> None:
    """Tie the stations a life story already has to the couple they are about.

    A "Heirat" typed into the life story before a tie could carry a date - or
    brought in by a GEDCOM, or read out of the report - is the same fact as the
    wedding date on the tie.  It is linked rather than copied: the station gets
    a `tie` naming the partner, and the tie takes the date only where it had
    none.  The station itself is never rewritten; what somebody entered stays
    exactly as they entered it.

    Linked only where there is no doubt which partner is meant: the station
    names them, or names nobody and there is only one partner to mean.
    """
    order = {"marriage": 0, "divorced": 1, "separated": 2, "engaged": 3, "partner": 4}
    for person in people:
        me = int(person["id"])
        spouses = person["spouses"]
        if not spouses:
            continue
        events = [e for e in person.get("events") or []
                  if isinstance(e, dict) and e.get("tie") is None and station_role(e.get("kind"))]
        # The wedding first, so an engagement beside it cannot claim the start.
        events.sort(key=lambda e: order[station_role(e.get("kind"))[1]])
        for ev in events:
            part, says = station_role(ev.get("kind"))
            named = [i for i in (_as_int(x) for x in ev.get("with") or []) if i is not None]
            hits = [s for s in named if s in spouses]
            if len(hits) == 1:
                spouse = hits[0]
            elif not named and len(spouses) == 1:
                spouse = spouses[0]
            else:
                continue
            ev["tie"] = {"with": spouse, "part": part, "auto": None}
            if not named:
                ev["with"] = [spouse]

            other = by_id[spouse]
            kind = person["spouse_kind"].get(str(spouse)) or other["spouse_kind"].get(str(me))
            tie = clean_tie(person["spouse_info"].get(str(spouse))
                            or other["spouse_info"].get(str(me))) or {
                "since": None, "place": None, "end": None, "until": None, "note": None}
            date = clean_date(ev)
            if part == "start":
                if says == "marriage" or (says == "engaged" and kind == "partner"):
                    kind = says
                if says == (kind or "marriage"):
                    if tie["since"] is None:
                        tie["since"] = date
                    if tie["place"] is None and ev.get("place"):
                        tie["place"] = str(ev["place"]).strip() or None
            else:
                if tie["end"] is None:
                    tie["end"] = says
                if tie["end"] == says and tie["until"] is None:
                    tie["until"] = date
            for a, b in ((person, spouse), (other, me)):
                if kind:
                    a["spouse_kind"][str(b)] = kind
                cleaned = clean_tie(tie)
                if cleaned:
                    a["spouse_info"][str(b)] = json.loads(json.dumps(cleaned))


def normalise_roles(people: list[dict]) -> None:
    """Keep the role maps in step with `spouses` and `parents`, in place.

    Whether a couple is married is a fact about the couple, not about one of
    them, so `spouse_kind` is written on both records and the two must agree.
    Where they disagree - only reachable through a hand-edited file or a save
    that crossed another - the stronger claim wins: somebody wrote "marriage"
    on purpose, nobody writes "partner" on purpose about a marriage.

    `spouse_info` - when, where, how it ended - is about the couple too and is
    kept the same way.  Where the two records disagree the fuller one wins, and
    between two equally full ones the lower number, so the answer does not
    depend on which record happened to be read first.

    Being a step-parent is not symmetric in the same way; it is recorded on the
    child, whose record is the one that says how it came by its parents.
    """
    by_id = {int(p["id"]): p for p in people}

    for person in people:
        raw = person.get("spouse_kind") or {}
        person["spouse_kind"] = {
            str(k): v for k, v in raw.items()
            if str(k).lstrip("-").isdigit() and int(k) in person["spouses"]
            and v in SPOUSE_KINDS}
        raw = person.get("parent_kind") or {}
        person["parent_kind"] = {
            str(k): v for k, v in raw.items()
            if str(k).lstrip("-").isdigit() and int(k) in person["parents"]
            and v in PARENT_KINDS}
        raw = person.get("spouse_info")
        info = {}
        for k, v in (raw.items() if isinstance(raw, dict) else ()):
            if _as_int(k) in person["spouses"]:
                tie = clean_tie(v)
                if tie:
                    info[str(_as_int(k))] = tie
        person["spouse_info"] = info
        # A station tied to somebody who is no longer a partner keeps its text
        # and loses only the tie.
        for ev in person.get("events") or []:
            if not isinstance(ev, dict) or "tie" not in ev:
                continue
            tie = ev["tie"]
            if not (isinstance(tie, dict) and _as_int(tie.get("with")) in person["spouses"]
                    and tie.get("part") in ("start", "end")):
                ev.pop("tie", None)

    for person in people:
        me = int(person["id"])
        for spouse in person["spouses"]:
            other = by_id[spouse]
            mine = person["spouse_kind"].get(str(spouse))
            theirs = other["spouse_kind"].get(str(me))
            if mine == theirs:
                continue
            agreed = max((k for k in (mine, theirs) if k), key=KIND_STRENGTH.get, default=None)
            if agreed is None:
                continue
            person["spouse_kind"][str(spouse)] = agreed
            other["spouse_kind"][str(me)] = agreed

    for person in people:
        me = int(person["id"])
        for spouse in person["spouses"]:
            other = by_id[spouse]
            mine = person["spouse_info"].get(str(spouse))
            theirs = other["spouse_info"].get(str(me))
            if mine == theirs:
                continue
            take = mine if (_weight(mine), -me) > (_weight(theirs), -spouse) else theirs
            person["spouse_info"][str(spouse)] = json.loads(json.dumps(take))
            other["spouse_info"][str(me)] = json.loads(json.dumps(take))

    adopt_stations(people, by_id)


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
