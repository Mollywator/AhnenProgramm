# -*- coding: utf-8 -*-
"""The shape a tree is written in, and how an older one is brought forward.

A tree lives longer than the program that wrote it.  The trees on this machine
were entered over months, they are backed up, they are handed to relatives on
sticks, and a copy of one will still be lying about in five years when the
program has been rewritten twice.  So the file has to say which shape it is in,
and the program has to be able to read every shape it ever wrote.

That is the whole of this file:

    FORMAT          the shape this program writes
    version(tree)   the shape a tree in hand is in
    umwandeln(tree) every step from that shape up to this one, in order

## Why it exists before it is needed

There is exactly one format today and therefore nothing to convert.  Writing
this now rather than when the second one appears is the point: the moment a
field changes, the old shape is only knowable from files that already exist,
and reconstructing it from a backup is guesswork.  A version number that has
been in the file since the beginning costs nothing and removes that guess.

## The rules the conversions follow

**Every step is from one number to the next.**  A tree three versions behind is
brought forward by running three steps in order, not by a special case that
knows how to jump.  That way a new step only has to be right about the version
before it.

**Nothing is thrown away in a step that could still be wanted.**  Where a field
is replaced, the old one is left in place unless keeping it would confuse the
program.  Disk is cheap and a lost birth date is not recoverable.

**The tree is backed up before the first step runs**, by `store.load`, into a
place that is never cleaned up automatically.  The ordinary backups are pruned
after a couple of dozen saves; a pre-conversion copy is the only thing that
leads back if a conversion turns out to be wrong six months later, and it must
still be there then.

**A tree from a newer program is not opened.**  It would render, mostly, and
then the first save would quietly drop every field this version does not know
about.  Refusing is the only answer that cannot lose anything.

## Adding a conversion

Raise `FORMAT`, append one entry to `SCHRITTE`, and write down what changed in
`docs/FORMAT.md` - a new section, never an edit to an old one.  The
documentation of a shape outlives the conversion out of it: a conversion may be
dropped once no file on earth is that old, but what version 1 looked like stays
true for ever and is what makes an old backup readable at all.
"""
from __future__ import annotations

# The shape this program writes.  Raised by one whenever the shape changes.
FORMAT = 2

# The oldest shape that can still be brought forward.  Everything below this is
# refused rather than mangled - see the note about dropping conversions above.
AELTESTE = 1


def version(tree: dict) -> int:
    """Which shape a tree is in.

    A tree with no version at all is version 1: the field was introduced with
    the machinery, and everything written before that is by definition the shape
    that existed then.  Anything unreadable is treated the same way, because a
    broken version field is not a reason to refuse a family.
    """
    raw = (tree.get("meta") or {}).get("format")
    try:
        got = int(raw)
    except (TypeError, ValueError):
        return 1
    return got if got > 0 else 1


def stempeln(tree: dict) -> dict:
    """Write this program's version into the tree. Called on every save."""
    tree.setdefault("meta", {})["format"] = FORMAT
    return tree


def zu_neu(tree: dict) -> bool:
    return version(tree) > FORMAT


def veraltet(tree: dict) -> bool:
    return AELTESTE <= version(tree) < FORMAT


def zu_alt(tree: dict) -> bool:
    return version(tree) < AELTESTE


# ------------------------------------------------------------------- steps
# One entry per step, in order, each from `von` to `von + 1`.  `was` is shown to
# the person whose tree is being converted, so it says what changed to their
# family rather than what changed in the code.
#
# A step takes the tree and changes it in place.  It may assume the tree is
# exactly in shape `von` - that is what running them in order buys.
def _von_1_auf_2(tree: dict) -> None:
    """Give every person the empty `link` field.

    Nothing is computed and nothing can go wrong: a tree written before links
    existed has no linked people by definition, so the honest value everywhere
    is "not linked".  The step exists so that every record has the same shape
    afterwards - a reader may then ask `person["link"]` without guarding.
    """
    for person in tree.get("people") or []:
        person.setdefault("link", None)


SCHRITTE: list[dict] = [
    {"von": 1, "was": "Jede Person bekommt das Feld für die Verknüpfung in "
                      "einen anderen Stammbaum (leer)",
     "tun": _von_1_auf_2},
]


def _schritt_fuer(von: int) -> dict | None:
    for schritt in SCHRITTE:
        if schritt["von"] == von:
            return schritt
    return None


def umwandeln(tree: dict) -> list[str]:
    """Bring a tree up to this program's shape. Returns what was done.

    Raises `ValueError` where a step is missing, which can only happen if
    `FORMAT` was raised without a step being added - a programming mistake, and
    one that must stop rather than write a half-converted family.
    """
    getan: list[str] = []
    while True:
        jetzt = version(tree)
        if jetzt >= FORMAT:
            break
        schritt = _schritt_fuer(jetzt)
        if schritt is None:
            raise ValueError(
                "Für Format %d ist keine Umwandlung hinterlegt - "
                "das Programm kann diesen Stammbaum nicht sauber übernehmen." % jetzt)
        schritt["tun"](tree)
        tree.setdefault("meta", {})["format"] = jetzt + 1
        getan.append("Format %d → %d: %s" % (jetzt, jetzt + 1, schritt["was"]))
    return getan
