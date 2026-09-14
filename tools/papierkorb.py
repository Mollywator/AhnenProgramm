# -*- coding: utf-8 -*-
"""The Papierkorb: what was merged, and how to take it back, for 60 days.

Kept as `papierkorb.json` in the tree's own folder, beside `baum.json`.  Each
entry is what `zusammenfuehren.ausfuehren()` returned - both records as they
were, what changed on every relative, which files moved - plus, once taken
back, when and under which number.

Entries older than 60 days are dropped whenever the file is read.  After that a
merge can only be undone from the rolling backups in `sicherung/`.

Losing the file loses the way back, not the family's data: the merged tree is
in `baum.json` either way.  So a broken file is read as an empty one.
"""
from __future__ import annotations

import datetime
import json
import os

NAME = "papierkorb.json"
TAGE = 60


def leer() -> dict:
    return {"version": 1, "eintraege": []}


def _tag(eintrag: dict) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(eintrag.get("am") or "")[:10])
    except ValueError:
        return None


def tage_uebrig(eintrag: dict, heute: datetime.date | None = None) -> int:
    tag = _tag(eintrag)
    if tag is None:
        return 0
    return TAGE - ((heute or datetime.date.today()) - tag).days


def bereinigen(roh, heute: datetime.date | None = None) -> dict:
    out = leer()
    if not isinstance(roh, dict):
        return out
    for e in roh.get("eintraege") or []:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str):
            continue
        if not isinstance(e.get("behalten"), int) or not isinstance(e.get("entfernt"), int):
            continue
        if not isinstance(e.get("vorher"), dict) or tage_uebrig(e, heute) < 0:
            continue
        out["eintraege"].append(e)
    return out


def laden(ordner: str, heute: datetime.date | None = None) -> dict:
    try:
        with open(os.path.join(ordner, NAME), encoding="utf-8") as fh:
            return bereinigen(json.load(fh), heute)
    except (OSError, ValueError):
        return leer()


def speichern(ordner: str, daten) -> dict:
    daten = bereinigen(daten)
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, NAME)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, pfad)
    return daten


def hinzufuegen(ordner: str, eintrag: dict) -> dict:
    daten = laden(ordner)
    daten["eintraege"].append(eintrag)
    return speichern(ordner, daten)


def finden(daten: dict, eintrag_id: str) -> dict | None:
    return next((e for e in daten.get("eintraege") or [] if e.get("id") == eintrag_id), None)
