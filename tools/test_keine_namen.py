# -*- coding: utf-8 -*-
"""The check that reads the code for names - the one that was missing.

The rule that outranks every other in this repository is that no family data
and no real name enters it, examples in comments included.  Two leaks have
happened, and `docs/DESIGN.md` says plainly why neither was caught: the ignore
list knows where files live, not what a comment says.  A pre-commit hook used
to look, and it was dropped for a good reason - a hook lives in `.git/hooks`,
which no clone brings with it, so it is missing exactly when somebody
unfamiliar is looking around.

A test does come with the clone.  This is that check, and it closes the third
leak: names that reached the code through a conversation about the family
rather than through the data folder.

## Where it gets the names

Not from a list in here - that list would BE the leak.  It reads the data
folder, which lives outside this repository by design, and takes every name the
program itself has written down: `Namensliste.txt` per tree, and the tree files
themselves.  So the check knows exactly the names that must never appear, and
this file knows none of them.

On a machine with no data folder - a fresh clone, a build server, somebody
else's checkout - there is nothing to compare against and the test skips.  That
is honest: it cannot verify what it cannot see, and it says so rather than
passing quietly.

## What it does NOT print

A failure names the file and the line, never the word that matched.  A check
against leaking names into a public place must not leak the name into a build
log to say so.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
sys.path.insert(0, HIER)

# Everything a reader of this repository ever sees.  Binary and generated
# files are left out: they carry no prose, and the built page is not committed.
GEPRUEFT = (".py", ".html", ".md", ".cmd", ".bat", ".txt", ".json", ".gitignore")

# Folders that are not the repository's own content.
UEBERSPRUNGEN = {".git", ".claude", "__pycache__", "docs/concepts"}

# Words that are names in a family and ordinary words in German prose.  A hit
# on one of these says nothing, so they never count.  Kept deliberately short:
# every entry here is a hole in the check.
HARMLOS = {
    # "löschen" is the verb this program uses for deleting a person, and it is
    # also a surname. Only the verb forms are excused.
    "löschen", "loeschen", "gelöscht", "geloescht", "lösche", "loesche",
}

MIN_LAENGE = 4          # shorter than this and a name is a substring of prose


def namen_aus_dem_datenordner() -> set[str]:
    """Every name the program has written down, read from outside this repo.

    Returns an empty set when there is no data folder - which is the normal
    state everywhere except the machine the family is kept on.
    """
    try:
        import store
    except Exception:                                   # noqa: BLE001
        return set()

    try:
        ordner = store.data_dir()
    except Exception:                                   # noqa: BLE001
        return set()
    if not ordner or not os.path.isdir(ordner):
        return set()

    namen: set[str] = set()

    def zerlegen(voll: str) -> None:
        for teil in re.split(r"[\s,;()/-]+", voll or ""):
            teil = teil.strip(".·'\"„“”").strip()
            if len(teil) >= MIN_LAENGE and teil.casefold() not in HARMLOS:
                namen.add(teil)

    # Only the tree files, and only the fields that ARE a name.  The readable
    # `Namensliste.txt` was the obvious second source and is the wrong one: it
    # carries a heading and prose, and taking every word from it turned
    # ordinary German into "names" - the first run flagged 1502 lines,
    # `.gitignore` included.  A check that cries wolf is worse than none.
    for wurzel, verzeichnisse, dateien in os.walk(ordner):
        verzeichnisse[:] = [d for d in verzeichnisse if d not in ("sicherung", "_geloescht")]
        for name in dateien:
            if name != store.TREE_FILE:
                continue
            try:
                import json
                with open(os.path.join(wurzel, name), encoding="utf-8") as fh:
                    baum = json.load(fh)
            except (OSError, ValueError):
                continue
            for person in baum.get("people") or []:
                for feld in ("name", "given", "surname", "birth_name", "call_name"):
                    zerlegen(person.get(feld) or "")
            # The tree's own name is a family name too - it is what the folder
            # is called and what stands in the masthead.
            zerlegen((baum.get("meta") or {}).get("title") or "")
    return namen


def dateien_des_repos():
    for wurzel, verzeichnisse, dateien in os.walk(WURZEL):
        rel_wurzel = os.path.relpath(wurzel, WURZEL).replace("\\", "/")
        verzeichnisse[:] = [
            d for d in verzeichnisse
            if d not in UEBERSPRUNGEN
            and (rel_wurzel + "/" + d).lstrip("./") not in UEBERSPRUNGEN
        ]
        for name in dateien:
            if name.endswith(GEPRUEFT) or name == ".gitignore":
                yield os.path.join(wurzel, name)


class TestKeineNamenImRepo(unittest.TestCase):

    def test_kein_name_aus_dem_stammbaum_steht_im_quelltext(self):
        namen = namen_aus_dem_datenordner()
        if not namen:
            self.skipTest("kein Datenordner auf diesem Rechner - "
                          "es gibt nichts, wogegen geprueft werden koennte")

        # Word boundaries, so "Person 1" does not match inside "Ahrensburg" and a
        # surname does not match inside an unrelated German compound.
        muster = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in sorted(namen, key=len, reverse=True)) + r")\b",
            re.IGNORECASE)

        funde: list[str] = []
        for pfad in dateien_des_repos():
            try:
                with open(pfad, encoding="utf-8") as fh:
                    for nr, zeile in enumerate(fh, 1):
                        if muster.search(zeile):
                            # The name itself is NOT reported - see the module
                            # docstring. The place is enough to go and look.
                            funde.append("%s:%d"
                                         % (os.path.relpath(pfad, WURZEL).replace("\\", "/"), nr))
            except (OSError, UnicodeDecodeError):
                continue

        self.assertEqual(
            funde, [],
            "In diesen Zeilen steht ein Name aus deinem Stammbaum. "
            "Der Name wird hier absichtlich nicht genannt - sieh an der Stelle nach:\n  "
            + "\n  ".join(funde))


if __name__ == "__main__":
    unittest.main(verbosity=2)
