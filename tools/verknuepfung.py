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
      "mit":    ["identitaet", ...] what is kept in step, see `FELDGRUPPEN`.
                                    Shared: both trees read the same answer.
                                    Missing means everything, files included.
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
    "contact", "private",
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


# ------------------------------------------------------- what is kept in step
# The shared fields in groups a person can recognise.  The question somebody
# linking a wife into her own family asks is not "how much" - nobody can say
# which half of a record is half - but "which kind": her name, her dates, her
# life, what is private, and her pictures.
#
# `dateien` has no fields: a portrait and a scan are files in a tree's own
# folders, and `store.dateien_abgleichen()` is what carries them across.
FELDGRUPPEN = (
    ("identitaet", "Identität", ("name", "given", "surname", "call_name",
                                 "birth_name", "title", "sex", "private")),
    ("eckdaten",   "Eckdaten",  ("birth", "death", "burial")),
    ("leben",      "Leben",     ("occupation", "religion", "residences",
                                 "events", "extra")),
    ("privates",   "Privates",  ("notes", "freetext", "contact")),
    ("dateien",    "Portrait & Unterlagen", ()),
)
BEREICHE = tuple(g for g, _t, _f in FELDGRUPPEN)

# Without a name the copy over there is nobody, so this one is always kept.
IMMER = "identitaet"

# The levels offered before anybody has changed them.  "Alles" is the default
# everywhere and means the same person, one to one - fields and files alike.
STUFEN = (
    ("alles",    "Alles",        BEREICHE),
    ("standard", "Nur Standard", ("identitaet", "eckdaten", "leben")),
    ("name",     "Nur Name",     ("identitaet",)),
)


def bereiche(auswahl) -> list[str]:
    """A clean selection: known groups only, in their order, the name always."""
    gewollt = set(auswahl or ())
    gewollt.add(IMMER)
    return [b for b in BEREICHE if b in gewollt]


def bereiche_von(person: dict) -> list[str]:
    """What this link keeps in step.

    A link written before there was a choice has no `mit` and keeps everything,
    files included: it was made to be the same person in both trees, and
    holding back what the program could not carry at the time would be a limit
    nobody ever chose.
    """
    link = link_von(person)
    mit = (link or {}).get("mit")
    return bereiche(mit) if isinstance(mit, list) else list(BEREICHE)


def felder_fuer(auswahl) -> tuple[str, ...]:
    gewollt = set(bereiche(auswahl))
    return tuple(f for g, _t, felder in FELDGRUPPEN if g in gewollt for f in felder)


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
# Not every group can travel on its own: see `HAENGT_AN` below.  A group whose
# carrier stayed behind arrives on the far side with no line to anybody.
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

# What each group is reached through.  A link is only ever drawn when BOTH ends
# travelled, so a group whose carrier stayed behind arrives on the far side
# with no line to anybody - people standing loose in a tree, to be joined up by
# hand afterwards.
#
# Two carriers, and the second one is easy to miss: the married-in groups are
# reached through the partner, and SIBLINGS ARE REACHED THROUGH THE PARENTS.
# Siblings are not a field.  Nowhere in a record does it say who somebody's
# sister is - she is the other child of the same parents, and that is the only
# thing that makes her a sister.  Take her without them and she is not a
# sibling over there, she is a stranger.
HAENGT_AN = {
    "siblings":        "parents",
    "spouse_children": "spouses",
    "spouse_parents":  "spouses",
    "spouse_siblings": "spouse_parents",     # and through it, "spouses"
}


def traeger(gruppe: str) -> list[str]:
    """The chain a group hangs off, nearest first - `[]` if it stands alone."""
    kette: list[str] = []
    an = HAENGT_AN.get(gruppe)
    while an and an not in kette:
        kette.append(an)
        an = HAENGT_AN.get(an)
    return kette


def mit_traegern(gruppen: list[str]) -> list[str]:
    """Whoever takes a group takes what carries it.

    Ticking `Schwiegereltern` alone would drop two people into the other tree
    with no line to anybody: their child - the partner - stayed behind.  The
    same is true one level down and less obviously so: ticking `Geschwister`
    without `Eltern` sends a sister who is nobody's sister over there, because
    the parents that made her one did not travel.

    So the carriers are added, and the dialog ticks their boxes to say so
    rather than doing it quietly.
    """
    out = list(gruppen)
    for gruppe in gruppen:
        for an in traeger(gruppe):
            if an not in out:
                out.append(an)
    # Back into the order the groups are offered in, so a preview reads the
    # way the dialog does.
    reihe = [g for g, _t, _v in GRUPPEN]
    return sorted(out, key=lambda g: reihe.index(g) if g in reihe else len(reihe))


def mit_ehepartner(gruppen: list[str]) -> list[str]:
    """The old name, from when the partner was the only carrier there was."""
    return mit_traegern(gruppen)


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
    gruppen = mit_traegern(gruppen)
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
def einsammeln(person: dict, auswahl=None) -> dict:
    """The half of a record that belongs to the person rather than the tree.

    With `auswahl`, only the groups that link keeps in step.  A field outside
    them is simply not in the result - so `verteilen` never touches it on the
    far side, neither clearing it nor writing over it.
    """
    felder = GETEILT if auswahl is None else felder_fuer(auswahl)
    return {f: person.get(f) for f in felder}


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

    # A lock is never a disagreement: whichever tree holds it, she asked for it.
    out["private"] = _gesperrt(hier, dort)

    return out, streit


def _gesperrt(a: dict, b: dict) -> list[str]:
    """Every section locked on either record - a wish is never outvoted."""
    out: list[str] = []
    for rec in (a, b):
        for key in rec.get("private") if isinstance(rec.get("private"), list) else []:
            if key not in out:
                out.append(key)
    return out


# --------------------------------------------------------------- the linking
def _leer(person_id: int, blank) -> dict:
    p = blank(person_id)
    p["id"] = int(person_id)
    return p


def knuepfen(quelle: dict, quelle_slug: str, person_id: int,
             ziel: dict, ziel_slug: str, gruppen: list[str],
             blank, naechste_id, mit=None, mit_angehoerige=None) -> dict:
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

    `mit` is what is kept in step for her, `mit_angehoerige` for everybody who
    travels with her (the same as hers unless said otherwise; everything when
    neither is given).  It is written on the link in both trees, so both read
    the same answer and neither tree's setting can win over the other's.  The
    files are not copied here - this module never touches a folder - but the
    pairs that need them come back in `paare` for `store.dateien_abgleichen()`.

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
    gruppen = mit_traegern(gruppen)
    for gruppe, _titel, _vorgabe in GRUPPEN:
        if gruppe not in gruppen:
            continue
        for pid in gruppe_ids(quelle, person_id, gruppe):
            if pid != int(person_id) and pid not in [r[0] for r in reisende]:
                reisende.append((pid, anker_uid))

    uid_zu_dort: dict[str, int] = {}
    angelegt = 0
    mit_ihr = bereiche(BEREICHE if mit is None else mit)
    mit_den_anderen = mit_ihr if mit_angehoerige is None else bereiche(mit_angehoerige)
    paare: list[dict] = []

    for pid, via in reisende:
        person = hier.get(pid)
        if not person:
            continue
        uid = uid_von(person) or (anker_uid if pid == int(person_id) else neue_uid())

        zwilling = dort_nach_uid.get(uid)
        # `via` is local.  Somebody who already stands on the far side keeps
        # the standing they have there: a father who is at home in his own tree
        # does not become borrowed because his son's wife links her family in.
        schon_da = zwilling is not None
        if zwilling is None:
            neue = _leer(naechste_id(ziel), blank)
            ziel.setdefault("people", []).append(neue)
            dort[int(neue["id"])] = neue
            zwilling = neue
            dort_nach_uid[uid] = neue
            angelegt += 1

        auswahl = mit_ihr if pid == int(person_id) else mit_den_anderen
        verteilen(zwilling, einsammeln(person, auswahl))
        uid_zu_dort[uid] = int(zwilling["id"])
        paare.append({"hier": pid, "dort": int(zwilling["id"]),
                      "dateien": "dateien" in auswahl})

        beide = [{"slug": quelle_slug, "id": pid},
                 {"slug": ziel_slug, "id": int(zwilling["id"])}]
        alt = link_von(person) or {}
        fuer_alle = [t for t in (alt.get("trees") or [])
                     if t.get("slug") not in (quelle_slug, ziel_slug)] + beide

        person["link"] = {"uid": uid, "trees": fuer_alle,
                          "via": alt.get("via"), "hidden": bool(alt.get("hidden")),
                          "mit": list(auswahl)}
        drueben_alt = link_von(zwilling) or {}
        zwilling["link"] = {"uid": uid, "trees": fuer_alle,
                            "via": drueben_alt.get("via") if schon_da else via,
                            "hidden": bool(drueben_alt.get("hidden")),
                            "mit": list(auswahl)}

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
            "ziel_id": uid_zu_dort.get(anker_uid),
            "paare": paare}
