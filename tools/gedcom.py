# -*- coding: utf-8 -*-
"""GEDCOM in and out - the one format every genealogy program can read.

`.ged` is how family trees have been passed between programs since the
eighties.  MyHeritage writes it, Ancestry writes it, Gramps and Family Tree
Maker read it.  Supporting it is what makes this program worth handing to
somebody who already has their family somewhere else - and what makes sure this
family's work is not trapped in here if the program is ever gone.

**What is supported.**  The load bearing part of GEDCOM 5.5.1: people with
their names, sex, birth, christening, death and burial, occupation, religion,
residences, notes and portraits; families with marriage, divorce and children.
That is what a family tree is made of, and it is what other programs actually
write.

**What is not.**  Sources and citations as records of their own, LDS ordinances,
multimedia beyond a file name, submitters, and the older ANSEL character set.
Anything unrecognised is not silently dropped: it is kept verbatim under the
person as `gedcom_rest`, so a tree can go out again without having been
quietly thinned on the way through.

A line is `LEVEL [@XREF@] TAG [VALUE]`, and a value too long for one line is
continued with CONC (join) or CONT (new line).
"""
from __future__ import annotations

import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edits as person_lib  # noqa: E402

LINE = re.compile(r"^\s*(\d+)\s+(?:@([^@]+)@\s+)?([A-Za-z0-9_]+)(?:\s(.*))?$")

MONTHS_OUT = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTHS_IN = {name: n for n, name in enumerate(MONTHS_OUT) if name}
# German exports are not supposed to exist, but they do
MONTHS_IN.update({"MRZ": 3, "MAI": 5, "OKT": 10, "DEZ": 12})

# Anything but an exact date counts as approximate; the qualifier is kept in the
# note so nothing is lost when the tree goes out again.
FUZZY = ("ABT", "ABOUT", "CAL", "EST", "BEF", "AFT", "BET", "FROM", "TO", "CA")

# Facts that get a field of their own; everything else becomes a life event.
EVENT_TAGS = {
    "BIRT": "birth", "DEAT": "death", "BURI": "burial",
}
EVENT_NAMES = {
    "CHR": "Taufe", "BAPM": "Taufe", "CONF": "Konfirmation", "GRAD": "Schulabschluss",
    "EMIG": "Auswanderung", "IMMI": "Einwanderung", "NATU": "Einbürgerung",
    "CENS": "Volkszählung", "RETI": "Ruhestand", "EVEN": "Ereignis",
    "PROB": "Nachlass", "WILL": "Testament", "ADOP": "Adoption",
}


class Node:
    """One GEDCOM line with whatever was indented under it."""

    __slots__ = ("tag", "value", "xref", "kids")

    def __init__(self, tag: str, value: str = "", xref: str | None = None):
        self.tag, self.value, self.xref, self.kids = tag, value or "", xref, []

    def first(self, tag: str) -> "Node | None":
        for kid in self.kids:
            if kid.tag == tag:
                return kid
        return None

    def all(self, tag: str) -> list["Node"]:
        return [kid for kid in self.kids if kid.tag == tag]

    def text(self, tag: str) -> str:
        node = self.first(tag)
        return node.value.strip() if node else ""


# --------------------------------------------------------------------- read
def parse(raw: str) -> list[Node]:
    """Lines into a tree of nodes, CONC and CONT folded back into their value."""
    roots: list[Node] = []
    stack: list[Node] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        m = LINE.match(line)
        if not m:
            continue
        level, xref, tag, value = int(m.group(1)), m.group(2), m.group(3).upper(), m.group(4) or ""

        if tag in ("CONC", "CONT") and stack:
            owner = stack[-1] if level > len(stack) - 1 else stack[level - 1]
            owner.value += ("\n" if tag == "CONT" else "") + value
            continue

        node = Node(tag, value, xref)
        del stack[level:]
        if level == 0:
            roots.append(node)
        elif stack:
            stack[-1].kids.append(node)
        stack.append(node)
    return roots


def read_date(node: Node | None) -> dict:
    """A GEDCOM date into day, month, year and whether it is only about right."""
    if node is None:
        return {}
    raw = (node.text("DATE") or "").strip().upper()
    if not raw:
        return {}
    approx = any(raw.startswith(word + " ") or raw == word for word in FUZZY)
    cleaned = raw
    for word in FUZZY:
        cleaned = re.sub(r"\b%s\b" % word, " ", cleaned)
    cleaned = re.sub(r"\bAND\b", " ", cleaned).strip()

    out: dict = {}
    parts = cleaned.split()
    for part in parts:
        if part in MONTHS_IN:
            out["month"] = MONTHS_IN[part]
        elif part.isdigit():
            if len(part) == 4:
                out.setdefault("year", int(part))
            elif int(part) <= 31:
                out.setdefault("day", int(part))
    if approx:
        out["approx"] = True
    if not out and raw:
        out["note"] = raw.title()
    return out


def read_place(node: Node | None) -> str:
    if node is None:
        return ""
    place = node.text("PLAC")
    address = node.first("ADDR")
    if not place and address:
        bits = [address.value] + [k.value for k in address.kids if k.tag in ("CITY", "STAE", "CTRY")]
        place = ", ".join(b for b in bits if b)
    return place.strip()


def fact(node: Node | None) -> dict:
    """A birth, death or burial: date and place together."""
    if node is None:
        return {}
    out = read_date(node)
    place = read_place(node)
    if place:
        out["place"] = place
    cause = node.text("CAUS")
    if cause:
        out["cause"] = cause
    return out


def read(raw: str, first_id: int = 1) -> dict:
    """A GEDCOM text into a tree of the shape this program uses."""
    roots = parse(raw)

    people_nodes = [n for n in roots if n.tag == "INDI" and n.xref]
    family_nodes = [n for n in roots if n.tag == "FAM" and n.xref]

    # ids are handed out here rather than taken from the file: @I42@ means
    # nothing outside its own file, and an import must not collide with people
    # who are already in the tree
    id_of = {node.xref: first_id + n for n, node in enumerate(people_nodes)}

    people = []
    for node in people_nodes:
        person = person_lib.blank_person(id_of[node.xref])
        person["gedcom_id"] = node.xref

        name = node.first("NAME")
        if name:
            raw_name = name.value.strip()
            m = re.match(r"^(.*?)\s*/([^/]*)/\s*(.*)$", raw_name)
            if m:
                person["given"] = m.group(1).strip()
                person["surname"] = m.group(2).strip()
            else:
                bits = raw_name.split()
                person["given"] = " ".join(bits[:-1]) if len(bits) > 1 else raw_name
                person["surname"] = bits[-1] if len(bits) > 1 else ""
            # GIVN and SURN are the authority on the parts where they exist -
            # a given name can be "Knut, Dr." while the name reads "Knut Cordes"
            if name.text("GIVN"):
                person["given"] = name.text("GIVN")
            if name.text("SURN"):
                person["surname"] = name.text("SURN")
            # and the NAME line itself is the authority on how it is written
            person["name"] = raw_name.replace("/", " ").strip()
            person["name"] = " ".join(person["name"].split())
            if not person["name"]:
                person["name"] = (person["given"] + " " + person["surname"]).strip()
            if name.text("NICK"):
                person["call_name"] = name.text("NICK")
            if name.text("NPFX"):
                person["title"] = name.text("NPFX")

        sex = node.text("SEX").upper()[:1]
        person["sex"] = {"M": "m", "F": "w"}.get(sex)

        for tag, field in EVENT_TAGS.items():
            got = fact(node.first(tag))
            if got:
                person[field] = got

        person["occupation"] = node.text("OCCU") or None
        person["religion"] = node.text("RELI") or None

        for res in node.all("RESI"):
            spot = {"place": read_place(res) or None}
            when = read_date(res)
            if when.get("year"):
                spot["from"] = when["year"]
            if spot["place"] or spot.get("from"):
                person["residences"].append(spot)

        notes = [n.value.strip() for n in node.all("NOTE") if n.value.strip()]
        if notes:
            person["freetext"] = "\n\n".join(notes)

        for obj in node.all("OBJE"):
            f = obj.text("FILE")
            if f and not person["photo"]:
                person["photo"] = os.path.basename(f)

        for kid in node.kids:
            if kid.tag in EVENT_NAMES:
                event = {"kind": EVENT_NAMES[kid.tag], "with": []}
                event.update(read_date(kid))
                place = read_place(kid)
                if place:
                    event["place"] = place
                if kid.value.strip() and kid.tag == "EVEN":
                    event["text"] = kid.value.strip()
                person["events"].append(event)

        # everything not understood, kept so it can go out again
        known = set(EVENT_TAGS) | set(EVENT_NAMES) | {
            "NAME", "SEX", "OCCU", "RELI", "RESI", "NOTE", "OBJE", "FAMS", "FAMC", "CHAN"}
        rest = [dump(kid, 1) for kid in node.kids if kid.tag not in known]
        if rest:
            person["gedcom_rest"] = "\n".join(rest)

        people.append(person)

    by_id = {p["id"]: p for p in people}
    marriages = []

    for fam in family_nodes:
        husband = id_of.get((fam.text("HUSB") or "").strip("@"))
        wife = id_of.get((fam.text("WIFE") or "").strip("@"))
        children = [id_of[c.value.strip("@")] for c in fam.all("CHIL")
                    if c.value.strip("@") in id_of]

        if husband and wife:
            for a, b in ((husband, wife), (wife, husband)):
                if b not in by_id[a]["spouses"]:
                    by_id[a]["spouses"].append(b)

        parents = [p for p in (husband, wife) if p]
        for child in children:
            for parent in parents:
                if parent not in by_id[child]["parents"]:
                    by_id[child]["parents"].append(parent)

        wedding = fact(fam.first("MARR"))
        if wedding and parents:
            marriages.append({"people": parents, "year": wedding.get("year"),
                              "month": wedding.get("month"), "day": wedding.get("day"),
                              "place": wedding.get("place")})
            for person_id in parents:
                event = {"kind": "Heirat", "with": [p for p in parents if p != person_id]}
                event.update({k: v for k, v in wedding.items() if k != "cause"})
                by_id[person_id]["events"].append(event)

        divorce = fact(fam.first("DIV"))
        if divorce and parents:
            for person_id in parents:
                event = {"kind": "Scheidung", "with": [p for p in parents if p != person_id]}
                event.update({k: v for k, v in divorce.items() if k != "cause"})
                by_id[person_id]["events"].append(event)

    person_lib.normalise_links(people)

    head = next((n for n in roots if n.tag == "HEAD"), None)
    source = ""
    if head and head.first("SOUR"):
        source = head.first("SOUR").value.strip() or head.first("SOUR").text("NAME")

    years = [y for p in people for y in ((p.get("birth") or {}).get("year"),
                                         (p.get("death") or {}).get("year")) if y]
    return {
        "meta": {
            "title": "Eingelesener Stammbaum",
            "root": people[0]["id"] if people else None,
            "source": source or "GEDCOM",
            "source_note": "Aus einer GEDCOM-Datei eingelesen%s." % (
                " (erzeugt von %s)" % source if source else ""),
            "count": len(people),
            "photos": sum(1 for p in people if p.get("photo")),
            "span": "%d bis %d" % (min(years), max(years)) if years else "",
        },
        "people": people, "marriages": marriages, "source_titles": {}, "checks": [],
    }


def dump(node: Node, level: int) -> str:
    out = ["%d %s%s" % (level, node.tag, " " + node.value if node.value else "")]
    for kid in node.kids:
        out.append(dump(kid, level + 1))
    return "\n".join(out)


# -------------------------------------------------------------------- write
def marked_name(person: dict, given: str, surname: str) -> str:
    """The name as written, with the surname marked off the way GEDCOM wants.

    Written rather than assembled, because the two are not always the same:
    someone entered as "Knut Cordes" may carry the given name "Knut, Dr.", and
    putting the parts back together would rename them.
    """
    shown = (person.get("name") or "").strip()
    if shown and surname:
        at = shown.lower().rfind(surname.lower())
        if at >= 0:
            return "%s/%s/%s" % (shown[:at], shown[at:at + len(surname)],
                                 shown[at + len(surname):])
    if shown and not surname:
        return shown
    return "%s /%s/" % (given, surname)


def out_date(fact_dict: dict | None) -> str:
    if not fact_dict:
        return ""
    bits = []
    if fact_dict.get("day") and fact_dict.get("month"):
        bits.append(str(fact_dict["day"]))
    if fact_dict.get("month"):
        bits.append(MONTHS_OUT[fact_dict["month"]])
    if fact_dict.get("year"):
        bits.append(str(fact_dict["year"]))
    if not bits:
        return ""
    return ("ABT " if fact_dict.get("approx") else "") + " ".join(bits)


def long_value(level: int, tag: str, value: str) -> list[str]:
    """A value with line breaks in it, as GEDCOM wants it: CONT per line."""
    lines = str(value).split("\n")
    out = ["%d %s %s" % (level, tag, lines[0])]
    out += ["%d CONT %s" % (level + 1, rest) for rest in lines[1:]]
    return out


def couple_roles(parents: list[int], by_id: dict) -> list[str]:
    """Which of the two goes in the HUSB slot and which in the WIFE slot.

    GEDCOM 5.5.1 has exactly one of each, so the sexes cannot always decide it:
    two women, two men, or nobody's sex recorded, and picking by sex alone
    writes the same tag twice - which loses one of them on the way back in.
    The slot is a place in a record, not a claim about anybody, so where the
    sexes do not settle it, the order does.
    """
    sexes = [(by_id.get(p) or {}).get("sex") for p in parents]
    if len(parents) == 1:
        return ["WIFE" if sexes[0] == "w" else "HUSB"]
    if sexes.count("w") == 1:
        return ["WIFE" if sex == "w" else "HUSB" for sex in sexes]
    return ["HUSB", "WIFE"][:len(parents)]


def write(tree: dict, program: str = "Stammbaum") -> str:
    """The tree as a GEDCOM 5.5.1 text, UTF-8, ready to hand to any program."""
    people = tree.get("people") or []
    by_id = {p["id"]: p for p in people}
    lines: list[str] = []

    stamp = datetime.datetime.now()
    lines += [
        "0 HEAD",
        "1 SOUR %s" % program,
        "2 NAME %s" % (tree.get("meta") or {}).get("title", "Stammbaum"),
        "1 DATE %d %s %d" % (stamp.day, MONTHS_OUT[stamp.month], stamp.year),
        "1 GEDC", "2 VERS 5.5.1", "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
    ]

    # A family record per couple, plus one per single parent with children, so
    # that no descent link is lost - other programs only carry them through FAM.
    families: list[dict] = []
    seen_pairs: set[tuple] = set()
    for person in people:
        for spouse in person.get("spouses") or []:
            pair = tuple(sorted((person["id"], spouse)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            kids = sorted(set(person.get("children") or []) &
                          set(by_id.get(spouse, {}).get("children") or []))
            families.append({"parents": list(pair), "children": kids})

    placed = {c for fam in families for c in fam["children"]}
    for person in people:
        loose = [c for c in person.get("children") or [] if c not in placed]
        if loose:
            families.append({"parents": [person["id"]], "children": sorted(loose)})
            placed.update(loose)

    fam_of_child: dict[int, int] = {}
    fam_of_spouse: dict[int, list[int]] = {}
    for n, fam in enumerate(families, start=1):
        for child in fam["children"]:
            fam_of_child.setdefault(child, n)
        for parent in fam["parents"]:
            fam_of_spouse.setdefault(parent, []).append(n)

    for person in people:
        pid = person["id"]
        lines.append("0 @I%d@ INDI" % pid)
        given = person.get("given") or ""
        surname = person.get("surname") or ""
        lines.append("1 NAME %s" % marked_name(person, given, surname))
        if given:
            lines.append("2 GIVN %s" % given)
        if surname:
            lines.append("2 SURN %s" % surname)
        if person.get("call_name"):
            lines.append("2 NICK %s" % person["call_name"])
        if person.get("title"):
            lines.append("2 NPFX %s" % person["title"])
        if person.get("sex") in ("m", "w"):
            lines.append("1 SEX %s" % ("M" if person["sex"] == "m" else "F"))

        for tag, field in (("BIRT", "birth"), ("DEAT", "death"), ("BURI", "burial")):
            got = person.get(field) or {}
            if not got:
                continue
            lines.append("1 %s" % tag)
            when = out_date(got)
            if when:
                lines.append("2 DATE %s" % when)
            if got.get("place"):
                lines.append("2 PLAC %s" % got["place"])
            if got.get("cause"):
                lines.append("2 CAUS %s" % got["cause"])

        if person.get("occupation"):
            lines.append("1 OCCU %s" % person["occupation"])
        if person.get("religion"):
            lines.append("1 RELI %s" % person["religion"])

        for spot in person.get("residences") or []:
            lines.append("1 RESI")
            if spot.get("from"):
                lines.append("2 DATE %s" % spot["from"])
            if spot.get("place"):
                lines.append("2 PLAC %s" % spot["place"])
            if spot.get("address"):
                lines.append("2 ADDR %s" % spot["address"])

        for event in person.get("events") or []:
            kind = (event.get("kind") or "").strip()
            if kind in ("Geburt", "Tod", "Beerdigung", "Heirat", "Scheidung"):
                continue                       # already carried by their own tags
            lines.append("1 EVEN %s" % (event.get("text") or ""))
            lines.append("2 TYPE %s" % (kind or "Ereignis"))
            when = out_date(event)
            if when:
                lines.append("2 DATE %s" % when)
            if event.get("place"):
                lines.append("2 PLAC %s" % event["place"])

        notes = [n for n in [person.get("freetext"), person.get("extra")] if n]
        notes += [n for n in person.get("notes") or [] if n]
        if notes:
            lines += long_value(1, "NOTE", "\n\n".join(notes))

        if person.get("photo"):
            lines += ["1 OBJE", "2 FILE %s" % person["photo"], "2 FORM jpg"]

        if pid in fam_of_child:
            lines.append("1 FAMC @F%d@" % fam_of_child[pid])
        for n in fam_of_spouse.get(pid, []):
            lines.append("1 FAMS @F%d@" % n)

        if person.get("gedcom_rest"):
            lines += person["gedcom_rest"].split("\n")

    weddings = {tuple(sorted(int(x) for x in m.get("people", []))): m
                for m in tree.get("marriages") or []}
    for n, fam in enumerate(families, start=1):
        lines.append("0 @F%d@ FAM" % n)
        for parent, role in zip(fam["parents"], couple_roles(fam["parents"], by_id)):
            lines.append("1 %s @I%d@" % (role, parent))
        for child in fam["children"]:
            lines.append("1 CHIL @I%d@" % child)
        wedding = weddings.get(tuple(sorted(fam["parents"])))
        if wedding:
            lines.append("1 MARR")
            when = out_date(wedding)
            if when:
                lines.append("2 DATE %s" % when)
            if wedding.get("place"):
                lines.append("2 PLAC %s" % wedding["place"])

    lines.append("0 TRLR")
    return "\r\n".join(lines) + "\r\n"


def read_file(path: str, first_id: int = 1) -> dict:
    """Read a .ged from disk, whatever it claims to be encoded in."""
    with open(path, "rb") as fh:
        blob = fh.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return read(blob.decode(encoding), first_id)
        except UnicodeDecodeError:
            continue
    raise ValueError("Die Datei liess sich in keiner bekannten Zeichensatzform lesen.")
