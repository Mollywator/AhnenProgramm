# -*- coding: utf-8 -*-
"""Two records of one person, made into one - by hand, and reversibly.

A report read from a PDF can carry the same person twice under two numbers.
Nothing here ever decides that on its own: the person using the editor picks
both entries, looks at every field side by side, settles every disagreement,
and confirms.  This module only carries out what was decided.

The rules, so that nothing is lost without somebody having said so:

  * a single value (birth, occupation, ...) that is the same, or present on one
    side only, is taken as it is.  Two different values are a question, and
    the merge refuses to run until the question has an answer.
  * a text from the report (bio, notes) may also be kept from both sides.
  * lists - events, residences, notes, sources, documents - are unioned.
  * parents and partners are unioned, and every relative that pointed at the
    number that goes away points at the one that stays.
  * documents are moved into the folder of the number that stays, renamed
    where a name is taken.

Everything needed to take it back - both records as they were, what was
changed on every relative, which files moved - is returned as one entry for
the Papierkorb (papierkorb.py), where it is kept for 60 days.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import shutil

import edits as person_lib

EINZELN, TEXT, LISTE, VERKNUEPFUNG = "einzeln", "text", "liste", "verknuepfung"

# (field, label, kind) - sent to the page too, so both sides agree on what a
# field is and neither can drift.
FELDER = (
    ("name", "Name", EINZELN),
    ("given", "Vornamen", EINZELN),
    ("surname", "Nachname", EINZELN),
    ("call_name", "Rufname", EINZELN),
    ("birth_name", "Geburtsname", EINZELN),
    ("title", "Titel", EINZELN),
    ("sex", "Geschlecht", EINZELN),
    ("birth", "Geburt", EINZELN),
    ("death", "Tod", EINZELN),
    ("burial", "Beerdigung", EINZELN),
    ("occupation", "Beruf", EINZELN),
    ("religion", "Konfession", EINZELN),
    ("relation", "Im Bericht geführt als", EINZELN),
    ("tree", "Stammbaum im Bericht", EINZELN),
    ("page", "Seite im Bericht", EINZELN),
    ("photo", "Portrait", EINZELN),
    ("contact", "Kontakt", EINZELN),
    ("bio", "Originaltext aus dem Bericht", TEXT),
    ("note_text", "Notiz aus dem Bericht", TEXT),
    ("source_text", "Quellentext aus dem Bericht", TEXT),
    ("extra", "Weitere Angaben", TEXT),
    ("freetext", "Eigene Notizen", TEXT),
    ("parents", "Eltern", VERKNUEPFUNG),
    ("spouses", "Ehe und Partnerschaft", VERKNUEPFUNG),
    ("events", "Lebenslauf", LISTE),
    ("residences", "Wohnorte", LISTE),
    ("notes", "Notizen", LISTE),
    ("sources", "Quellen", LISTE),
    ("documents", "Unterlagen", LISTE),
)
KINDS = ("parent_kind", "spouse_kind")
# Never compared when asking "was this record changed since?"
ABGELEITET = ("children", "edited")


def leer(wert) -> bool:
    return wert in (None, "", [], {})


def _gleich(a, b) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == \
        json.dumps(b, sort_keys=True, ensure_ascii=False)


def _ohne_abgeleitet(rec) -> dict:
    return {k: v for k, v in (rec or {}).items() if k not in ABGELEITET}


def geaenderte_felder(vorher, jetzt) -> list[str]:
    """Labels of the fields that differ - what a later edit would lose."""
    titel = {k: t for k, t, _ in FELDER}
    out = []
    for key in sorted(set(_ohne_abgeleitet(vorher)) | set(_ohne_abgeleitet(jetzt))):
        a, b = (vorher or {}).get(key), (jetzt or {}).get(key)
        if leer(a) and leer(b) or _gleich(a, b):
            continue
        out.append(titel.get(key, key))
    return out


def hindernis(tree: dict, behalten: int, entfernt: int) -> str | None:
    """Why these two cannot be merged, or None."""
    people = {int(p["id"]): p for p in tree.get("people") or []}
    if behalten == entfernt:
        return "Eine Person lässt sich nicht mit sich selbst zusammenführen."
    for pid in (behalten, entfernt):
        if pid not in people:
            return "Nummer #%d gibt es in diesem Stammbaum nicht." % pid
    pa, pb = people[behalten], people[entfernt]
    if entfernt in [int(x) for x in pa.get("parents") or []] \
            or behalten in [int(x) for x in pb.get("parents") or []]:
        return ("#%d und #%d sind als Elternteil und Kind verbunden – das kann nicht "
                "dieselbe Person sein." % (behalten, entfernt))
    if pb.get("link"):
        if pa.get("link"):
            return ("Beide Einträge stehen auch in einem anderen Stammbaum. Zusammenführen "
                    "würde diese Verknüpfungen zerreißen.")
        return ("#%d steht auch in einem anderen Stammbaum und muss deshalb die Nummer "
                "sein, die bleibt." % entfernt)
    return None


def _vereint(a, b) -> list:
    out = list(a or [])
    for x in b or []:
        if not any(_gleich(x, y) for y in out):
            out.append(x)
    return out


def _freier_name(ordner: str, name: str) -> str:
    stamm, endung = os.path.splitext(name)
    kandidat, n = name, 2
    while os.path.exists(os.path.join(ordner, kandidat)):
        kandidat = "%s (%d)%s" % (stamm, n, endung)
        n += 1
    return kandidat


def _pfad(base: str, rel: str) -> str:
    return os.path.join(base, *rel.split("/"))


def dateien_verschieben(base: str | None, paare: list, rueckwaerts: bool = False) -> list:
    """Move `von` -> `nach` for every pair (or back), skipping what is gone."""
    getan = []
    if not base:
        return getan
    for von, nach in paare:
        quelle, ziel = (nach, von) if rueckwaerts else (von, nach)
        if not os.path.isfile(_pfad(base, quelle)):
            continue
        os.makedirs(os.path.dirname(_pfad(base, ziel)), exist_ok=True)
        shutil.move(_pfad(base, quelle), _pfad(base, ziel))
        getan.append([von, nach])
    return getan


def _umnummern(p: dict, alt: int, neu: int) -> None:
    """Every reference to `alt` in one record becomes `neu`."""
    for key in ("parents", "spouses"):
        p[key] = list(dict.fromkeys(neu if int(x) == alt else int(x) for x in p.get(key) or []))
    for kind in KINDS:
        m = p.get(kind) or {}
        if str(alt) in m:
            m.setdefault(str(neu), m.pop(str(alt)))
    for ev in p.get("events") or []:
        if ev.get("with"):
            ev["with"] = list(dict.fromkeys(neu if int(x) == alt else int(x) for x in ev["with"]))


def ausfuehren(tree: dict, behalten, entfernt, wahl: dict | None,
               docs_base: str | None = None, jetzt: datetime.datetime | None = None) -> dict:
    """Merge `entfernt` into `behalten`, in place, and return the Papierkorb entry.

    `wahl` answers every disagreement: {"occupation": "behalten" | "entfernt"},
    and for a text also "beide".  A missing answer raises ValueError before
    anything - tree or file - has been touched.  The caller saves the tree; if
    that fails, `dateien_verschieben(base, eintrag["dateien"], rueckwaerts=True)`
    puts the files back.
    """
    a, b = int(behalten), int(entfernt)
    grund = hindernis(tree, a, b)
    if grund:
        raise ValueError(grund)
    wahl = wahl or {}
    jetzt = jetzt or datetime.datetime.now()
    people = tree["people"]
    by_id = {int(p["id"]): p for p in people}
    pa, pb = by_id[a], by_id[b]

    # ---- the one record, field by field (nothing is changed yet)
    neu = copy.deepcopy(pa)
    felder: dict[str, str] = {}
    for key, label, art in FELDER:
        va, vb = pa.get(key), pb.get(key)
        if leer(va) and leer(vb):
            continue
        if art in (EINZELN, TEXT):
            if _gleich(va, vb):
                felder[key] = "gleich"
            elif leer(vb):
                felder[key] = "nur_behalten"
            elif leer(va):
                neu[key] = copy.deepcopy(vb)
                felder[key] = "nur_entfernt"
            else:
                w = wahl.get(key)
                if w == "entfernt":
                    neu[key] = copy.deepcopy(vb)
                elif w == "beide" and art == TEXT:
                    neu[key] = str(va).rstrip() + "\n\n" + str(vb).lstrip()
                elif w != "behalten":
                    raise ValueError("Bei „%s“ fehlt noch die Entscheidung." % label)
                felder[key] = w
            continue
        felder[key] = "vereint" if not leer(va) and not leer(vb) \
            else ("nur_entfernt" if leer(va) else "nur_behalten")
        if art == VERKNUEPFUNG:
            ids = [a if int(x) == b else int(x) for x in _vereint(va, vb)]
            neu[key] = [i for i in dict.fromkeys(ids) if i != a]
        elif key != "documents":
            neu[key] = _vereint(va, vb)
    for kind in KINDS:
        m = dict(pb.get(kind) or {})
        m.update(pa.get(kind) or {})
        m.pop(str(a), None)
        m.pop(str(b), None)
        neu[kind] = m
    bekannt = {k for k, _, _ in FELDER} | set(KINDS) | {"id", "children", "edited", "link"}
    for key, wert in pb.items():
        if key not in bekannt and leer(neu.get(key)) and not leer(wert):
            neu[key] = copy.deepcopy(wert)
    _umnummern(neu, b, a)
    for ev in neu.get("events") or []:
        if ev.get("with"):
            ev["with"] = [x for x in ev["with"] if x != a]
    neu.update({"id": a, "children": [], "link": pa.get("link"),
                "edited": jetzt.isoformat(timespec="seconds")})

    vorher = {"behalten": copy.deepcopy(pa), "entfernt": copy.deepcopy(pb),
              "root": (tree.get("meta") or {}).get("root")}

    # ---- every relative that pointed at the number that goes away
    verwandte: dict[str, dict] = {}
    for p in people:
        pid = int(p["id"])
        if pid in (a, b):
            continue
        spuren: list = []
        davor = copy.deepcopy(p)
        for key in ("parents", "spouses"):
            liste = [int(x) for x in p.get(key) or []]
            if b in liste:
                if a in liste:
                    p[key] = [x for x in liste if x != b]
                    spuren.append([key, "entfernt"])
                else:
                    p[key] = [a if x == b else x for x in liste]
                    spuren.append([key, "ersetzt"])
        for kind in KINDS:
            m = p.get(kind) or {}
            if str(b) in m:
                hatte = str(a) in m
                wert = m.pop(str(b))
                m.setdefault(str(a), wert)
                p[kind] = m
                spuren.append([kind, wert, hatte])
        treffer = 0
        for ev in p.get("events") or []:
            if b in [int(x) for x in ev.get("with") or []]:
                ev["with"] = list(dict.fromkeys(a if int(x) == b else int(x) for x in ev["with"]))
                treffer += 1
        if treffer:
            spuren.append(["events_with", treffer])
        if spuren:
            verwandte[str(pid)] = {"name": p.get("name") or "", "vorher": davor, "spuren": spuren}

    ehen = []
    for m in tree.get("marriages") or []:
        ids = [int(x) for x in m.get("people") or []]
        if b in ids:
            davor = copy.deepcopy(m)
            m["people"] = [a if x == b else x for x in ids]
            ehen.append({"vorher": davor, "nachher": copy.deepcopy(m)})

    meta = tree.setdefault("meta", {})
    if meta.get("root") is not None and int(meta["root"]) == b:
        meta["root"] = a

    # ---- documents last: the only step that touches the disk
    dateien: list = []
    docs = list(pa.get("documents") or [])
    for d in pb.get("documents") or []:
        d = dict(d)
        datei = d.get("file") or ""
        if docs_base and datei and os.path.isfile(os.path.join(docs_base, str(b), datei)):
            name = _freier_name(os.path.join(docs_base, str(a)), datei)
            paar = ["%d/%s" % (b, datei), "%d/%s" % (a, name)]
            dateien.extend(dateien_verschieben(docs_base, [paar]))
            d["file"] = name
        if not any(_gleich(d, x) for x in docs):
            docs.append(d)
    neu["documents"] = docs

    pa.clear()
    pa.update(neu)
    tree["people"] = [p for p in people if int(p["id"]) != b]

    return {
        "id": "z-%s-%d-%d" % (jetzt.strftime("%Y%m%d%H%M%S"), a, b),
        "art": "zusammengefuehrt",
        "am": jetzt.isoformat(timespec="seconds"),
        "behalten": a, "entfernt": b,
        "namen": [vorher["behalten"].get("name") or "", vorher["entfernt"].get("name") or ""],
        "felder": felder, "vorher": vorher, "verwandte": verwandte,
        "ehen": ehen, "dateien": dateien,
    }


def nachher_merken(eintrag: dict, tree: dict) -> None:
    """The records as they were written, so an undo can tell what changed since."""
    by_id = {int(p["id"]): p for p in tree.get("people") or []}
    eintrag["nachher"] = {
        "behalten": copy.deepcopy(by_id.get(eintrag["behalten"])),
        "verwandte": {pid: copy.deepcopy(by_id.get(int(pid))) for pid in eintrag["verwandte"]},
    }


def _naechste_nummer(people: list) -> int:
    return max([person_lib.FIRST_NEW_ID - 1] + [int(p["id"]) for p in people]) + 1


def rueckgaengig(tree: dict, eintrag: dict, docs_base: str | None = None) -> dict:
    """Take a merge back, in place.  The caller saves the tree.

    Both records return as they were.  A relative that was not changed since
    returns exactly as it was; one that was changed keeps those changes and
    only gets the link back.  If the old number has been handed out in the
    meantime, the returning record gets a new one and says so.
    """
    a, b = int(eintrag["behalten"]), int(eintrag["entfernt"])
    people = tree["people"]
    by_id = {int(p["id"]): p for p in people}
    if a not in by_id:
        raise ValueError("#%d gibt es nicht mehr – das Zusammenführen lässt sich nicht "
                         "zurücknehmen." % a)
    nachher = eintrag.get("nachher") or {}
    hinweise: list[str] = []
    nb = b if b not in by_id else _naechste_nummer(people)
    if nb != b:
        hinweise.append("#%d ist inzwischen vergeben – der zurückgeholte Eintrag bekommt #%d."
                        % (b, nb))

    pa = by_id[a]
    spaeter = geaenderte_felder(nachher.get("behalten"), pa)
    if spaeter:
        hinweise.append("An #%d nach dem Zusammenführen geändert und jetzt zurückgesetzt: %s."
                        % (a, ", ".join(spaeter)))
    wieder_a = copy.deepcopy(eintrag["vorher"]["behalten"])
    wieder_a["link"] = pa.get("link")
    pa.clear()
    pa.update(wieder_a)
    if nb != b:
        _umnummern(pa, b, nb)
    wieder_b = copy.deepcopy(eintrag["vorher"]["entfernt"])
    wieder_b["id"] = nb
    people.append(wieder_b)

    for pid, rec in (eintrag.get("verwandte") or {}).items():
        p = by_id.get(int(pid))
        if p is None:
            continue
        if _gleich(_ohne_abgeleitet(p), _ohne_abgeleitet((nachher.get("verwandte") or {}).get(pid))):
            p.clear()
            p.update(copy.deepcopy(rec["vorher"]))
            if nb != b:
                _umnummern(p, b, nb)
            continue
        for spur in rec["spuren"]:
            art = spur[0]
            if art in ("parents", "spouses"):
                liste = [int(x) for x in p.get(art) or []]
                if spur[1] == "ersetzt" and a in liste and nb not in liste:
                    p[art] = [nb if x == a else x for x in liste]
                elif nb not in liste:
                    p[art] = liste + [nb]
            elif art in KINDS:
                m = p.get(art) or {}
                m[str(nb)] = spur[1]
                if not spur[2]:
                    m.pop(str(a), None)
                p[art] = m
            elif art == "events_with":
                hinweise.append("#%s wurde nach dem Zusammenführen geändert – dort sind nur die "
                                "Verknüpfungen zurückgesetzt, im Lebenslauf steht weiter #%d."
                                % (pid, a))

    for ehe in eintrag.get("ehen") or []:
        for i, m in enumerate(tree.get("marriages") or []):
            if _gleich(m, ehe["nachher"]):
                zurueck = copy.deepcopy(ehe["vorher"])
                zurueck["people"] = [nb if int(x) == b else int(x) for x in zurueck.get("people") or []]
                tree["marriages"][i] = zurueck
                break

    meta = tree.setdefault("meta", {})
    root_vorher = eintrag["vorher"].get("root")
    if root_vorher is not None and int(root_vorher) == b and meta.get("root") is not None \
            and int(meta["root"]) == a:
        meta["root"] = nb

    zurueck = [[nach, "%d/%s" % (nb, von.split("/", 1)[1])] for von, nach in eintrag.get("dateien") or []]
    verschoben = dateien_verschieben(docs_base, zurueck)
    return {"nummer": nb, "hinweise": hinweise, "verschoben": verschoben}


def felder_fuer_seite() -> list[dict]:
    return [{"feld": k, "titel": t, "art": art} for k, t, art in FELDER]
