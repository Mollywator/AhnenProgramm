# -*- coding: utf-8 -*-
"""What the background check has looked at, and what was decided about it.

The editor checks the whole tree in the background for a parent who died too
long before a child was born.  This file is its memory, kept as `pruefung.json`
in the tree's own folder, beside `baum.json` and never inside it:

  * the family's data is not touched by the check - no new field, no format
    version, no conversion.  An older program still opens the tree.
  * a person already checked, with the same dates, is not checked again.
  * a finding already reported is not announced again on the next start.
  * a decision about a finding - "geprueft" (looked at, it is right) or
    "verworfen" (cannot be verified, e.g. a record from 1600 copied as it
    stood) - is kept for exactly the dates it was made about.

Losing the file loses nothing but those decisions: the check simply runs again
and asks again.  So a broken file is read as an empty one, never as an error.

    {
      "version": 1,
      "personen": {"<id>": {"sig": "...", "funde": [{"eltern": 2, "print": "..."}]}},
      "entscheidungen": {"<parent id>:<child id>": {"print": "...", "art": "geprueft", "am": "2026-09-14"}}
    }

`sig` and `print` are fingerprints written by the page.  They are compared,
never interpreted: when a date changes the fingerprint no longer matches, and
the person is checked and the finding reported again.
"""
from __future__ import annotations

import json
import os

NAME = "pruefung.json"
ARTEN = ("geprueft", "verworfen")


def leer() -> dict:
    return {"version": 1, "personen": {}, "entscheidungen": {}}


def _zahl(wert) -> int | None:
    text = str(wert)
    return int(text) if text.lstrip("-").isdigit() else None


def bereinigen(roh) -> dict:
    """Keep what has the right shape and drop the rest, quietly."""
    out = leer()
    if not isinstance(roh, dict):
        return out
    for key, rec in (roh.get("personen") or {}).items():
        pid = _zahl(key)
        if pid is None or not isinstance(rec, dict) or not isinstance(rec.get("sig"), str):
            continue
        funde = []
        for fund in rec.get("funde") or []:
            if isinstance(fund, dict) and _zahl(fund.get("eltern")) is not None \
                    and isinstance(fund.get("print"), str):
                funde.append({"eltern": _zahl(fund["eltern"]), "print": fund["print"]})
        out["personen"][str(pid)] = {"sig": rec["sig"], "funde": funde}
    for key, rec in (roh.get("entscheidungen") or {}).items():
        teile = str(key).split(":")
        if len(teile) != 2 or any(_zahl(t) is None for t in teile):
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("print"), str) \
                or rec.get("art") not in ARTEN:
            continue
        out["entscheidungen"]["%d:%d" % (_zahl(teile[0]), _zahl(teile[1]))] = {
            "print": rec["print"], "art": rec["art"], "am": str(rec.get("am") or "")[:10]}
    return out


def laden(ordner: str) -> dict:
    try:
        with open(os.path.join(ordner, NAME), encoding="utf-8") as fh:
            return bereinigen(json.load(fh))
    except (OSError, ValueError):
        return leer()


def speichern(ordner: str, daten) -> dict:
    """Write the file via a temporary one, so a crash cannot leave half of it."""
    daten = bereinigen(daten)
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, NAME)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, pfad)
    return daten
