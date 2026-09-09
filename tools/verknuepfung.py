# -*- coding: utf-8 -*-
"""One person, several trees, one shared identity.

The case this exists for: a wife's family should grow in *her* tree, not in
her husband's.  She herself has to stand in both - he needs her to draw his
own marriage, she needs herself to hang her parents off.  So she is one
person carried by two files.

## What a link is

Every linked person carries a `link` object.  Two of its fields are the same
in every tree that carries her, and the rest is local:

    "link": {
      "uid":    "p-3f8a1c204e7b",   the shared identity. Never reused, never
                                    changed. Two records with the same uid are
                                    the same human being.
      "trees":  [{"slug": "baum-a", "id": 42},
                 {"slug": "baum-b", "id": 7}],
                                    every tree carrying her, and her number in
                                    it. Kept in step on every save.
      "via":    "p-91be04c7d2f1" | null,
                                    she arrived here as a relative of that
                                    person rather than in her own right. This
                                    is what keeps a married-in family out of
                                    the big views - see `geliehen()`.
      "hidden": false,              hidden in THIS tree only. Local, never
                                    synchronised: a father-in-law somebody no
                                    longer wants to see is their business, not
                                    the other family's.
    }

`uid` and `trees` are the shared half, `via` and `hidden` the local one.
`einsammeln()` and `verteilen()` below are the only two functions that need to
know which is which.

## Why the record is copied rather than referenced

Because a tree has to survive alone.  It is handed to relatives on sticks, it
is backed up, it is opened in ten years.  A record that only points at another
file is a record that is empty the moment that file is missing - and removing a
tree from the program would then silently gut a second family.  So both files
carry the whole person, and saving writes to every tree that has her.

The cost is honest and worth naming: two copies can drift apart if a tree is
edited outside the program.  `zusammenfuehren()` is the answer to that, and it
merges rather than picks - see there.
"""
from __future__ import annotations

import secrets

# Fields that belong to the person and are therefore written to every tree
# carrying her.  Everything not in here is local to one tree: the id, the
# links to other people (they are numbers, and numbers differ per tree), what
# those links are called (`spouse_kind` and `parent_kind` are keyed by those
# same local numbers), the photo and the documents (files in that tree's
# folders).
GETEILT = (
    "name", "given", "surname", "call_name", "birth_name", "title",
    "sex", "occupation", "religion",
    "birth", "death", "burial",
    "residences", "events", "notes", "freetext", "extra",
    "contact",
)

# Lists that are unioned rather than chosen between when two trees disagree.
# A life is additive: one person enters the marriage, another the job, and
# both belong to her.  See `zusammenfuehren()`.
LISTEN = ("residences", "events", "notes")

# Single-value fields where two different values cannot both be true.  These
# are the only ones that ever produce a question.
EINZELN = ("name", "given", "surname", "call_name", "birth_name", "title",
           "sex", "occupation", "religion", "birth", "death", "burial",
           "freetext", "extra", "contact")


def neue_uid() -> str:
    """An identity that no other tree can have invented independently."""
    return "p-" + secrets.token_hex(6)


def link_von(person: dict) -> dict | None:
    link = person.get("link")
    return link if isinstance(link, dict) else None


def uid_von(person: dict) -> str | None:
    link = link_von(person)
    return (link or {}).get("uid")


def verknuepft(person: dict) -> bool:
    """Is this person carried by more than one tree?"""
    link = link_von(person)
    return bool(link and len(link.get("trees") or []) > 1)


def geliehen(person: dict) -> bool:
    """Did this person arrive as somebody else's relative?

    The married-in family.  They are in the file so the near view can draw
    them, but they are not part of this tree's own line, and the big views
    leave them out - which is the whole reason the two families were split up.
    """
    link = link_von(person)
    return bool(link and link.get("via"))


def versteckt(person: dict) -> bool:
    link = link_von(person)
    return bool(link and link.get("hidden"))


def andere_baeume(person: dict, slug: str) -> list[dict]:
    """Where else this person is kept - `[{"slug":…, "id":…}]`."""
    link = link_von(person)
    if not link:
        return []
    return [t for t in (link.get("trees") or []) if t.get("slug") != slug]


def eintrag_fuer(person: dict, slug: str) -> dict | None:
    link = link_von(person)
    if not link:
        return None
    for t in link.get("trees") or []:
        if t.get("slug") == slug:
            return t
    return None


# ------------------------------------------------------------ what travels
# The groups offered when a person is linked into another tree, in the order
# they are offered.  The order is a priority, not an alphabet: a partner and
# the children are what makes a person placeable at all in the other tree,
# parents and siblings are context.
#
# The second block is the same four seen from the partner's side - the family
# somebody marries into.  It is the case this whole feature exists for: the
# wife's parents are the husband's parents-in-law, and if he cannot take them
# along, her tree starts with her alone and every in-law has to be typed twice.
# They are offered unticked, because they are one step further out and taking
# them by default would carry a second family across on a click.
#
# Whole groups only.  Half a set of siblings is a decision nobody remembers
# taking, and "three of the four" is done by taking all four and removing one
# afterwards - which asks, per tree, what should happen.
#
# Third field: ticked when the dialog opens.
GRUPPEN = (
    ("spouses",         "Ehepartner",                True),
    ("children",        "Kinder",                    True),
    ("parents",         "Eltern",                    True),
    ("siblings",        "Geschwister",               True),
    ("spouse_children", "Kinder der Ehepartner",     False),
    ("spouse_parents",  "Schwiegereltern",           False),
    ("spouse_siblings", "Geschwister der Ehepartner", False),
)

# The groups that hang off a partner rather than off the person herself.
UEBER_EHEPARTNER = ("spouse_children", "spouse_parents", "spouse_siblings")


def mit_ehepartner(gruppen: list[str]) -> list[str]:
    """Whoever takes the in-laws takes the partner they hang off.

    Without this, ticking `Schwiegereltern` alone would drop two people into
    the other tree with no line to anybody: their child - the partner - stayed
    behind, and a link is only ever drawn when both ends travelled.  So the
    partner is added, and the dialog ticks the box to say so rather than doing
    it quietly.
    """
    if "spouses" not in gruppen and any(g in UEBER_EHEPARTNER for g in gruppen):
        return ["spouses"] + list(gruppen)
    return list(gruppen)


def _feld(by_id: dict, pid: int, feld: str) -> list[int]:
    return [int(x) for x in ((by_id.get(int(pid)) or {}).get(feld) or [])]


def _geschwister(by_id: dict, pid: int) -> list[int]:
    """Siblings are not stored; they are the other children of the parents."""
    out: list[int] = []
    for parent in _feld(by_id, pid, "parents"):
        for kid in _feld(by_id, parent, "children"):
            if kid != int(pid) and kid not in out:
                out.append(kid)
    return out


def gruppe_ids(tree: dict, person_id: int, gruppe: str) -> list[int]:
    """Who is in one of the groups, for the person in this tree."""
    by_id = {int(p["id"]): p for p in tree.get("people") or []}
    pid = int(person_id)
    if pid not in by_id:
        return []
    if gruppe == "siblings":
        return _geschwister(by_id, pid)
    if gruppe in UEBER_EHEPARTNER:
        # The same three questions, asked of each partner instead of of her.
        was = gruppe.split("_", 1)[1]
        out: list[int] = []
        for partner in _feld(by_id, pid, "spouses"):
            drin = (_geschwister(by_id, partner) if was == "siblings"
                    else _feld(by_id, partner, was))
            for anderer in drin:
                # She is her partner's partner's ... - and the partners
                # themselves are the `spouses` group, not this one.
                if anderer != pid and anderer not in out:
                    out.append(anderer)
        return out
    return _feld(by_id, pid, gruppe)


def vorschau(tree: dict, person_id: int, gruppen: list[str]) -> list[dict]:
    """Who would travel, by name - so the dialog can say it rather than imply it."""
    by_id = {int(p["id"]): p for p in tree.get("people") or []}
    gruppen = mit_ehepartner(gruppen)
    seen: list[int] = []
    out: list[dict] = []
    for gruppe, titel, _vorgabe in GRUPPEN:
        if gruppe not in gruppen:
            continue
        for pid in gruppe_ids(tree, person_id, gruppe):
            if pid in seen or pid == int(person_id):
                continue
            seen.append(pid)
            person = by_id.get(pid) or {}
            out.append({"id": pid, "name": person.get("name") or "", "gruppe": titel})
    return out


def schon_drueben(ziel: dict, namen: list[str]) -> list[dict]:
    """People of those names the target tree already has.

    Asked in both directions before anything is copied, because the answer
    changes what the dialog should offer: a wife's parents already entered in
    her own tree must not arrive a second time under new numbers, and the
    husband's side may already be there from an earlier link.

    Matched on name and year of birth, and only ever REPORTED - never merged.
    Joining two people by name is how a family file quietly acquires a wrong
    grandmother; the two who know they are the same person are the ones who
    say so.
    """
    wanted = {(n or "").strip().casefold() for n in namen if (n or "").strip()}
    out = []
    for p in ziel.get("people") or []:
        if (p.get("name") or "").strip().casefold() in wanted:
            jahr = ((p.get("birth") or {}) or {}).get("year")
            out.append({"id": int(p["id"]), "name": p.get("name") or "", "jahr": jahr})
    return out


# ------------------------------------------------------- keeping both sides
def einsammeln(person: dict) -> dict:
    """The half of a record that belongs to the person rather than the tree."""
    return {f: person.get(f) for f in GETEILT}


def verteilen(ziel: dict, geteilt: dict) -> bool:
    """Write the shared half onto a record in another tree.

    Returns whether anything actually changed, so a save that touched nobody
    does not rewrite a second family's file and does not spend a backup slot.
    """
    geaendert = False
    for feld, wert in geteilt.items():
        if ziel.get(feld) != wert:
            ziel[feld] = wert
            geaendert = True
    return geaendert


def zusammenfuehren(hier: dict, dort: dict) -> tuple[dict, list[str]]:
    """Merge two versions of the same person; report only real conflicts.

    Two rules, and the difference between them is the whole point:

    * **Lists are unioned, always, without asking.**  One person enters the
      marriage, another enters the job, and both belong to her.  A second
      marriage is another entry, not a contradiction.  Nothing is discarded.
    * **Single values are reported.**  Two different dates of birth cannot both
      be true, so the program says so and lets somebody who knows decide.  Two
      identical values are not a conflict and are never mentioned.

    Returns the merged record and the names of the fields that disagree.
    """
    out = dict(hier)
    streit: list[str] = []

    for feld in LISTEN:
        a = list(hier.get(feld) or [])
        b = list(dort.get(feld) or [])
        vereint = list(a)
        for eintrag in b:
            if eintrag not in vereint:
                vereint.append(eintrag)
        out[feld] = vereint

    for feld in EINZELN:
        a, b = hier.get(feld), dort.get(feld)
        if a in (None, "", [], {}):
            out[feld] = b
        elif b in (None, "", [], {}) or a == b:
            out[feld] = a
        else:
            out[feld] = a          # this tree stands until somebody decides
            streit.append(feld)

    return out, streit


# --------------------------------------------------------------- the linking
def _leer(person_id: int, blank) -> dict:
    p = blank(person_id)
    p["id"] = int(person_id)
    return p


def knuepfen(quelle: dict, quelle_slug: str, person_id: int,
             ziel: dict, ziel_slug: str, gruppen: list[str],
             blank, naechste_id) -> dict:
    """Copy a person - and the chosen groups around her - into another tree.

    Both trees are changed in place and handed back to the caller to save.
    What happens, in order:

    1. The person herself gets a `uid` if she has none, and both trees record
       each other in her `trees` list.  She is the anchor: her `via` stays
       `null`, because she is here in her own right.
    2. Everybody in a chosen group travels the same way, but with `via` set to
       her `uid` - that is what marks them as somebody else's family and keeps
       them out of the big views on the far side.
    3. The links BETWEEN the travellers are rebuilt with the target tree's own
       numbers.  A link is a number and numbers are local, so they cannot be
       copied; they are looked up through the uid map built on the way.

    Nobody is ever matched by name.  A person who already exists on the other
    side under a different number stays a second record until somebody says
    otherwise - `schon_drueben()` is what tells the dialog to say so, and a
    wrong grandmother written in by a name match is not recoverable.
    """
    hier = {int(p["id"]): p for p in quelle.get("people") or []}
    dort = {int(p["id"]): p for p in ziel.get("people") or []}
    anker = hier.get(int(person_id))
    if not anker:
        raise ValueError("Person %s gibt es in diesem Stammbaum nicht." % person_id)

    # Everyone already in the target tree, by uid, so a second link of the same
    # family updates the records that are there instead of doubling them.
    dort_nach_uid = {uid_von(p): p for p in dort.values() if uid_von(p)}

    reisende: list[tuple[int, str | None]] = [(int(person_id), None)]
    anker_uid = uid_von(anker) or neue_uid()
    gruppen = mit_ehepartner(gruppen)
    for gruppe, _titel, _vorgabe in GRUPPEN:
        if gruppe not in gruppen:
            continue
        for pid in gruppe_ids(quelle, person_id, gruppe):
            if pid != int(person_id) and pid not in [r[0] for r in reisende]:
                reisende.append((pid, anker_uid))

    uid_zu_dort: dict[str, int] = {}
    angelegt = 0

    for pid, via in reisende:
        person = hier.get(pid)
        if not person:
            continue
        uid = uid_von(person) or (anker_uid if pid == int(person_id) else neue_uid())

        zwilling = dort_nach_uid.get(uid)
        if zwilling is None:
            neue = _leer(naechste_id(ziel), blank)
            ziel.setdefault("people", []).append(neue)
            dort[int(neue["id"])] = neue
            zwilling = neue
            dort_nach_uid[uid] = neue
            angelegt += 1

        verteilen(zwilling, einsammeln(person))
        uid_zu_dort[uid] = int(zwilling["id"])

        beide = [{"slug": quelle_slug, "id": pid},
                 {"slug": ziel_slug, "id": int(zwilling["id"])}]
        alt = link_von(person) or {}
        fuer_alle = [t for t in (alt.get("trees") or [])
                     if t.get("slug") not in (quelle_slug, ziel_slug)] + beide

        person["link"] = {"uid": uid, "trees": fuer_alle,
                          "via": alt.get("via"), "hidden": bool(alt.get("hidden"))}
        drueben_alt = link_von(zwilling) or {}
        zwilling["link"] = {"uid": uid, "trees": fuer_alle,
                            "via": via if via else drueben_alt.get("via"),
                            "hidden": bool(drueben_alt.get("hidden"))}

    # The family links among the travellers, in the target tree's numbering.
    # Only links whose other end also travelled are drawn: a parent left behind
    # would otherwise become a wire to nobody.
    for pid, _via in reisende:
        person = hier.get(pid)
        if not person:
            continue
        uid = uid_von(person)
        neue = dort.get(uid_zu_dort.get(uid, -1))
        if not neue:
            continue
        for feld in ("parents", "spouses"):
            drueben = list(neue.get(feld) or [])
            for anderes in person.get(feld) or []:
                andere_person = hier.get(int(anderes))
                if not andere_person:
                    continue
                ziel_id = uid_zu_dort.get(uid_von(andere_person) or "")
                if ziel_id is not None and ziel_id not in drueben:
                    drueben.append(ziel_id)
            neue[feld] = drueben

    return {"uid": anker_uid, "angelegt": angelegt,
            "mitgenommen": len(reisende) - 1,
            "ziel_id": uid_zu_dort.get(anker_uid)}
