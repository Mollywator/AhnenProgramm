# -*- coding: utf-8 -*-
"""The `.baum` file - one file that is the whole tree, to hand over and to keep.

Two files should be enough to give somebody: the program, and this.  So this
one carries everything the tree consists of - the people, the portraits, and
the scanned papers if they are allowed to travel.

Inside it is an ordinary ZIP.  That is deliberate: in twenty years, when this
program is gone, anybody can rename it to `.zip`, open it, and find readable
JSON and their family's photographs.  A format nobody can open without the
program that wrote it is not a way of keeping anything.

`LIES MICH.txt` inside says exactly that, in German, to whoever finds it.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edits as person_lib  # noqa: E402
import store  # noqa: E402

SUFFIX = ".baum"
TREE_NAME = "baum.json"
PHOTO_DIR = "fotos"
DOCS_DIR = "dokumente"
READ_ME = "LIES MICH.txt"

NOTE = """Stammbaum - Familiendaten

Diese Datei enthaelt einen Familienstammbaum: Personen, Verwandtschaften,
Fotos%s.

So kommt man an den Inhalt:

  Mit dem Programm   "Stammbaum.exe" starten und diese Datei importieren.
                     Dann ist alles wieder sichtbar und bearbeitbar.

  Ohne das Programm  Diese Datei in ".zip" umbenennen und wie einen normalen
                     Ordner oeffnen. Darin liegen die Fotos als gewoehnliche
                     Bilddateien und die Personen in "baum.json" - eine
                     Textdatei, die sich mit jedem Editor lesen laesst.

Der zweite Weg ist der wichtigere. Er funktioniert auch dann noch, wenn es das
Programm nicht mehr gibt.

Erstellt am %s.
Enthaelt %d Personen%s.
"""


def write(tree: dict, path: str, with_documents: bool = True,
          title: str | None = None) -> dict:
    """Pack a tree, its portraits and optionally its papers into one file."""
    people = tree.get("people") or []
    if title:
        tree = json.loads(json.dumps(tree))
        tree.setdefault("meta", {})["title"] = title

    photo_source = store.photo_dir()
    wanted = {p["photo"] for p in people if p.get("photo")}
    photos = [n for n in wanted if os.path.isfile(os.path.join(photo_source, n))]

    papers: list[tuple[str, str]] = []
    if with_documents:
        for person in people:
            for doc in person.get("documents") or []:
                one = os.path.join(store.docs_dir(person["id"]), doc.get("file", ""))
                if os.path.isfile(one):
                    papers.append((one, "%s/%d/%s" % (DOCS_DIR, person["id"], doc["file"])))
    else:
        # the papers stay behind, so the entries pointing at them go too -
        # a list of file names that are not in the file is worse than no list
        tree = json.loads(json.dumps(tree))
        for person in tree["people"]:
            person["documents"] = []

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".neu"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(TREE_NAME, json.dumps(tree, ensure_ascii=False, indent=1))
        for name in sorted(photos):
            zf.write(os.path.join(photo_source, name), "%s/%s" % (PHOTO_DIR, name))
        for source, inside in papers:
            zf.write(source, inside)
        zf.writestr(READ_ME, NOTE % (
            " und Urkunden" if papers else "",
            datetime.datetime.now().strftime("%d.%m.%Y"),
            len(people),
            ", %d Fotos, %d Unterlagen" % (len(photos), len(papers)) if papers
            else ", %d Fotos" % len(photos)))
    os.replace(tmp, path)

    return {"personen": len(people), "fotos": len(photos), "unterlagen": len(papers),
            "groesse": os.path.getsize(path)}


def read(path: str) -> dict:
    """Unpack a `.baum` and hand back the tree it holds.

    Portraits and papers are copied into the program's own folders on the way,
    because from here on they are looked up there.  Nothing already in those
    folders is overwritten: two trees can carry a file of the same name.
    """
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if TREE_NAME not in names:
            raise ValueError("Diese Datei enthaelt keinen Stammbaum "
                             "(es fehlt %s darin)." % TREE_NAME)
        tree = json.loads(zf.read(TREE_NAME).decode("utf-8"))

        photo_target = store.photo_dir()
        for inside in sorted(n for n in names if n.startswith(PHOTO_DIR + "/")):
            name = os.path.basename(inside)
            if not name:
                continue
            out = os.path.join(photo_target, name)
            if not os.path.exists(out):
                with zf.open(inside) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        for inside in sorted(n for n in names if n.startswith(DOCS_DIR + "/")):
            bits = inside.split("/")
            if len(bits) != 3 or not bits[2]:
                continue
            out = os.path.join(store.docs_dir(bits[1]), bits[2])
            if not os.path.exists(out):
                with zf.open(inside) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    tree.setdefault("meta", {})
    tree["people"] = [person_lib.fill_missing(p) for p in tree.get("people") or []]
    tree.setdefault("marriages", [])
    tree.setdefault("source_titles", {})
    tree.setdefault("checks", [])
    return tree


# --------------------------------------------------------------------- merge
def renumber(tree: dict, first_id: int) -> dict:
    """Give every person in a tree fresh ids, links and all."""
    out = json.loads(json.dumps(tree))
    order = sorted(p["id"] for p in out["people"])
    moved = {old: first_id + n for n, old in enumerate(order)}

    for person in out["people"]:
        person["id"] = moved[person["id"]]
        for field in ("parents", "spouses", "children"):
            person[field] = [moved[i] for i in person.get(field) or [] if i in moved]
        # the role maps are keyed by the same numbers, written as strings
        for field in ("spouse_kind", "parent_kind", "spouse_info"):
            person[field] = {str(moved[int(k)]): v for k, v in (person.get(field) or {}).items()
                             if str(k).lstrip("-").isdigit() and int(k) in moved}
        for event in person.get("events") or []:
            event["with"] = [moved[i] for i in event.get("with") or [] if i in moved]
            tie = event.get("tie")
            if isinstance(tie, dict) and tie.get("with") in moved:
                tie["with"] = moved[tie["with"]]
            elif "tie" in event:
                event.pop("tie")

    for marriage in out.get("marriages") or []:
        marriage["people"] = [moved[i] for i in marriage.get("people", []) if i in moved]

    if (out.get("meta") or {}).get("root") in moved:
        out["meta"]["root"] = moved[out["meta"]["root"]]
    return out


def look_alike(here: list[dict], there: list[dict]) -> list[dict]:
    """People who might be the same person in both trees.

    Only reported, never acted on.  Merging two people by name is how a family
    file quietly acquires a wrong grandmother, and no program should do it
    without being asked person by person.
    """
    def key(person):
        return ((person.get("name") or "").strip().lower(),
                (person.get("birth") or {}).get("year"))

    mine = {}
    for person in here:
        k = key(person)
        if k[0]:
            mine.setdefault(k, person)

    out = []
    for person in there:
        k = key(person)
        twin = mine.get(k)
        if twin and (k[1] or len(k[0].split()) > 1):
            out.append({"name": person.get("name"), "jahr": k[1],
                        "hier": twin["id"], "dazu": person["id"]})
    return out


def merge(base: dict, other: dict) -> tuple[dict, list[dict]]:
    """Put a second tree beside the first without joining anybody up.

    Everyone comes in with new numbers and keeps their own connections; the two
    families simply stand next to each other until somebody draws the marriage
    that links them.  Which is exactly the job: two people who married each
    other know which two they are, and no name matching does.
    """
    joined = json.loads(json.dumps(base))
    incoming = renumber(other, store.next_id(joined))
    twins = look_alike(joined["people"], incoming["people"])

    joined["people"].extend(incoming["people"])
    joined["marriages"] = (joined.get("marriages") or []) + (incoming.get("marriages") or [])
    person_lib.normalise_links(joined["people"])
    joined.setdefault("meta", {})["count"] = len(joined["people"])
    return joined, twins
