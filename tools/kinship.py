# -*- coding: utf-8 -*-
"""Relationship maths, used here to check the parsed graph against the report.

The report prints a relationship label behind every name, always relative to
the one person it was written for.  Those labels are an independent statement about the shape of the
tree, so they make a good end-to-end test: walk the parent links this parser
extracted, work out what the label ought to be, and complain when the two
disagree.

The same rules are implemented again in JavaScript inside the finished page,
where the centre of the tree can be any person.  Keep the two in step.
"""
from __future__ import annotations

import re

# "Jans 3 x Ur-Großvater" -> four generations up plus three, i.e. five.
ANCESTOR = re.compile(
    r"^(?:\w+s)\s+(?:(?P<mult>\d+)\s*x\s*)?(?P<word>Ur-?Gro(?:ß|ss)(?:vater|mutter)"
    r"|Urgro(?:ß|ss)(?:vater|mutter)|Gro(?:ß|ss)(?:vater|mutter)|Vater|Mutter)$",
    re.I)
DESCENDANT = re.compile(
    r"^(?:\w+s)\s+(?:(?P<mult>\d+)\s*x\s*)?(?P<word>Ur-?Enkel(?:in)?|Urenkel(?:in)?"
    r"|Enkel(?:in)?|Sohn|Tochter)$", re.I)
SIBLING = re.compile(r"^(?:\w+s)\s+(?:Bruder|Schwester)$", re.I)
# "Jans 2 x Ur-Großonkel" - a sibling of an ancestor four generations up.
# The variants ending in "N. Grades" follow a different convention and are left
# alone here.
AUNT_UNCLE = re.compile(
    r"^(?:\w+s)\s+(?:(?P<mult>\d+)\s*x\s*)?(?P<word>Ur-?Gro(?:ß|ss)(?:onkel|tante)"
    r"|Urgro(?:ß|ss)(?:onkel|tante)|Gro(?:ß|ss)(?:onkel|tante)|Onkel|Tante)$",
    re.I)


def ancestors(people: dict[int, dict], start: int, limit: int = 30) -> dict[int, int]:
    """Every ancestor of `start` with the shortest number of steps up to it."""
    out = {start: 0}
    frontier = [start]
    depth = 0
    while frontier and depth < limit:
        depth += 1
        nxt = []
        for pid in frontier:
            for parent in people.get(pid, {}).get("parents", []):
                if parent in people and parent not in out:
                    out[parent] = depth
                    nxt.append(parent)
        frontier = nxt
    return out


def expected_steps(label: str) -> tuple[str, int] | None:
    """Turn a printed label into ('auf'|'ab'|'geschwister', generations)."""
    if not label:
        return None
    label = label.strip().rstrip(".")
    if SIBLING.match(label):
        return ("geschwister", 1)
    match = ANCESTOR.match(label)
    if match:
        word = match.group("word").lower().replace("ss", "ß").replace("-", "")
        mult = int(match.group("mult") or 0)
        if word in ("vater", "mutter"):
            base = 1
        elif word.startswith("urgroß"):
            base = 3
        else:                                  # großvater / großmutter
            base = 2
        return ("auf", base + max(0, mult - 1) if mult else base)
    match = AUNT_UNCLE.match(label)
    if match:
        word = match.group("word").lower().replace("ss", "ß").replace("-", "")
        mult = int(match.group("mult") or 0)
        if word in ("onkel", "tante"):
            base = 1
        elif word.startswith("urgroß"):
            base = 3
        else:
            base = 2
        return ("seitlich", base + max(0, mult - 1) if mult else base)
    match = DESCENDANT.match(label)
    if match:
        word = match.group("word").lower().replace("-", "")
        mult = int(match.group("mult") or 0)
        if word in ("sohn", "tochter"):
            base = 1
        elif word.startswith("urenkel"):
            base = 3
        else:
            base = 2
        return ("ab", base + max(0, mult - 1) if mult else base)
    return None


def check_against_report(people: dict[int, dict], root: int) -> list[str]:
    """Compare every checkable label with the parent links we extracted."""
    problems: list[str] = []
    up_from_root = ancestors(people, root)
    root_parents = set(people[root]["parents"]) if root in people else set()

    for pid, person in sorted(people.items()):
        if pid == root:
            continue
        expectation = expected_steps(person.get("relation") or "")
        if not expectation:
            continue
        kind, steps = expectation
        label = "%s (#%d)" % (person["name"], pid)

        if kind == "auf":
            actual = up_from_root.get(pid)
            if actual is None:
                problems.append("%s ist laut Bericht '%s', taucht in der Ahnenlinie von "
                                "#%d aber gar nicht auf." % (label, person["relation"], root))
            elif actual != steps:
                problems.append("%s ist laut Bericht '%s' (%d Generationen), ueber die "
                                "Elternangaben sind es aber %d."
                                % (label, person["relation"], steps, actual))
        elif kind == "ab":
            down = ancestors(people, pid).get(root)
            if down is None:
                problems.append("%s ist laut Bericht '%s', stammt ueber die Elternangaben "
                                "aber nicht von #%d ab." % (label, person["relation"], root))
            elif down != steps:
                problems.append("%s ist laut Bericht '%s' (%d Generationen), ueber die "
                                "Elternangaben sind es aber %d."
                                % (label, person["relation"], steps, down))
        elif kind == "seitlich":
            # a sibling of somebody who is `steps` generations above the root
            line = {a for a, dist in up_from_root.items() if dist == steps}
            mine = set(person["parents"])
            if not mine:
                problems.append("%s ist laut Bericht '%s', hat im Bericht aber keine "
                                "Eltern, ueber die sich das pruefen liesse."
                                % (label, person["relation"]))
            elif not any(mine & set(people[a]["parents"]) for a in line if a in people):
                problems.append("%s ist laut Bericht '%s', teilt aber mit keinem Vorfahren "
                                "der %d. Generation von #%d einen Elternteil."
                                % (label, person["relation"], steps, root))
        else:
            shared = root_parents & set(person["parents"])
            if not shared:
                problems.append("%s ist laut Bericht '%s', teilt mit #%d aber keinen "
                                "Elternteil." % (label, person["relation"], root))
    return problems
