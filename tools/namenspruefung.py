# -*- coding: utf-8 -*-
"""Looks for names from the family trees in this repository - without ever saying one.

    python tools/namenspruefung.py              check, print file:line for every hit
    python tools/namenspruefung.py --ersetzen   replace every hit in place with "Person N"
    python tools/namenspruefung.py --ordner X   check another checkout instead of this one

The rule that outranks every other in this repository is that no family data and
no real name enters it, examples in comments included.  The names to look for
cannot be written down here - that list would BE the leak - so they are read at
run time from the trees in the data folder, the one `store.data_dir()` resolves.
Nothing is cached: a person entered today is looked for on the next run.

What it prints is deliberately poor: a file, a line, a placeholder.  Never the
word that matched.  Whoever runs it - a person, a build log, an AI assistant -
learns where to look and nothing about the family, and `--ersetzen` makes even
looking unnecessary.

Exit codes: 0 no names, 1 names found (or replaced), 2 no data folder to check against.
"""
from __future__ import annotations

import json
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
sys.path.insert(0, HIER)

# Everything a reader of this repository ever sees.  Binary and generated files
# are left out: they carry no prose, and the built page is not committed.
GEPRUEFT = (".py", ".html", ".md", ".cmd", ".bat", ".txt", ".json", ".yml", ".gitignore")

# Folders that are not the repository's own content.
UEBERSPRUNGEN = {".git", ".claude", ".work", "__pycache__", ".pytest_cache", "docs/concepts"}

# Words that are names in a family and ordinary words in prose.  A hit on one of
# these says nothing, so they never count.  Kept short on purpose: every entry
# here is a hole in the check.
HARMLOS = {
    # "löschen" is the verb this program uses for deleting a person, and it is
    # also a surname.  Only the verb forms are excused.
    "löschen", "loeschen", "gelöscht", "geloescht", "lösche", "loesche",
    # The program's own placeholders: it writes these into a tree itself, for a
    # title ("Stammbaum ...", "Familie ...") or a person nobody has named yet.
    "stammbaum", "familie", "unbekannt", "frau", "herr",
    # English and German words the code and comments cannot do without:
    # a footnote mark, an HTTP POST, a colour theme.
    "mark", "post", "rose", "lila",
}

MIN_LAENGE = 4          # shorter than this and a name is a substring of prose

PLATZHALTER = "Person %d"


def namen_aus_dem_datenordner() -> set[str]:
    """Every name the program has written into a tree on this machine.

    Returns an empty set when there is no data folder - the normal state
    everywhere except the machine the family is kept on.
    """
    try:
        import store
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
    # `Namensliste.txt` carries a heading and prose, and taking every word from
    # it turned ordinary German into "names".  A check that cries wolf is worse
    # than none.
    for wurzel, verzeichnisse, dateien in os.walk(ordner):
        verzeichnisse[:] = [d for d in verzeichnisse if d not in ("sicherung", "_geloescht")]
        if store.TREE_FILE not in dateien:
            continue
        try:
            with open(os.path.join(wurzel, store.TREE_FILE), encoding="utf-8") as fh:
                baum = json.load(fh)
        except (OSError, ValueError):
            continue
        for person in baum.get("people") or []:
            for feld in ("name", "given", "surname", "birth_name", "call_name"):
                zerlegen(person.get(feld) or "")
        # The tree's own name is a family name too.
        zerlegen((baum.get("meta") or {}).get("title") or "")
    return namen


def muster_fuer(namen: set[str]) -> re.Pattern | None:
    """One pattern for all names, longest first, on word boundaries.

    Word boundaries, so a surname does not match inside a place or an unrelated
    German compound.
    """
    if not namen:
        return None
    return re.compile(
        r"\b(" + "|".join(re.escape(n) for n in sorted(namen, key=len, reverse=True)) + r")\b",
        re.IGNORECASE)


def dateien(wurzel: str = WURZEL):
    for ort, verzeichnisse, namen in os.walk(wurzel):
        rel = os.path.relpath(ort, wurzel).replace("\\", "/")
        verzeichnisse[:] = [
            d for d in verzeichnisse
            if d not in UEBERSPRUNGEN and (rel + "/" + d).lstrip("./") not in UEBERSPRUNGEN
        ]
        for name in namen:
            if name.endswith(GEPRUEFT):
                yield os.path.join(ort, name)


class Ersetzer:
    """Swaps names for numbered placeholders, the same name for the same number."""

    def __init__(self, muster: re.Pattern):
        self.muster = muster
        self.nummern: dict[str, int] = {}

    def platzhalter(self, treffer: re.Match) -> str:
        schluessel = treffer.group(0).casefold()
        if schluessel not in self.nummern:
            self.nummern[schluessel] = len(self.nummern) + 1
        return PLATZHALTER % self.nummern[schluessel]

    def text(self, inhalt: str) -> tuple[str, int]:
        return self.muster.subn(self.platzhalter, inhalt)


def pruefen(wurzel: str, muster: re.Pattern, ersetzen: bool = False) -> list[str]:
    """Every hit as "file:line", after replacing it when asked to."""
    ersetzer = Ersetzer(muster)
    funde: list[str] = []
    for pfad in sorted(dateien(wurzel)):
        try:
            with open(pfad, encoding="utf-8", newline="") as fh:
                inhalt = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(pfad, wurzel).replace("\\", "/")
        zeilen = inhalt.splitlines(keepends=True)
        geaendert = False
        for nr, zeile in enumerate(zeilen, 1):
            if not muster.search(zeile):
                continue
            if ersetzen:
                neu, _ = ersetzer.text(zeile)
                zeilen[nr - 1] = neu
                geaendert = True
                funde.append("%s:%d  -> Platzhalter gesetzt" % (rel, nr))
            else:
                funde.append("%s:%d" % (rel, nr))
        if geaendert:
            with open(pfad, "w", encoding="utf-8", newline="") as fh:
                fh.write("".join(zeilen))
    return funde


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ersetzen = "--ersetzen" in argv
    wurzel = WURZEL
    if "--ordner" in argv:
        wurzel = os.path.abspath(argv[argv.index("--ordner") + 1])

    muster = muster_fuer(namen_aus_dem_datenordner())
    if muster is None:
        print("Kein Datenordner mit Stammbaeumen gefunden - nichts geprueft.")
        return 2

    funde = pruefen(wurzel, muster, ersetzen)
    if not funde:
        print("Keine Namen vorhanden.")
        return 0
    if ersetzen:
        print("Namen ersetzt an %d Stellen:" % len(funde))
    else:
        print("ACHTUNG: Namen vorhanden an %d Stellen "
              "(der Name wird absichtlich nicht genannt):" % len(funde))
    for fund in funde:
        print("  " + fund)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
