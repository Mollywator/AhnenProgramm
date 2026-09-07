# -*- coding: utf-8 -*-
"""Step 2 of the pipeline: turn the extracted report lines into tree.json.

The report is prose, but it is machine generated prose, so it follows a small
and stable grammar.  Facts are taken from the most reliable place available:

    parents      from each person's own "als Sohn/Tochter von X{1} und Y{2}"
    children     derived by inverting the parent links, then cross-checked
                 against the child lists the report prints under each marriage
    couples      from shared children, from the event register's "Heirat von
                 A{1} und B{2}", and from the narrative's "heiratete"
    events       from the event register (section 11), which is already atomic
    residences   from the place register (section 10)
    names        from the way other entries refer to a person, because those
                 references are properly cased while the entry headings shout
    everything   the person's full narrative paragraph is kept verbatim as well,
                 so nothing that this parser misses is lost to the reader

Anything that does not add up is written to data/validation-report.txt rather
than silently dropped.
"""
from __future__ import annotations

import collections
import html
import json
import os
import re
import sys
import unicodedata

import kinship
import store

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Every path below hangs off the data folder, which the person running the
# program chooses - see the top of store.py.  Nothing here writes into the
# program folder any more, because that folder is a repository.
# Asked for, not created: importing this module must not touch the disk.  A
# path that cannot be written to is a thing to say a sentence about, not to
# crash an import over - which is exactly what it used to do.
RAW_DIR = store.raw_dir(create=False)
DATA_DIR = store.build_dir(create=False)
PHOTO_DIR = store.build_photo_dir(create=False)

# Everything that is true of one particular report and of no other lives in
# `tools/report.json`, never in this file.  The parser itself knows no family:
# it can be handed to anybody with a MyHeritage genealogy report, and it can be
# published without carrying somebody's relatives along in a regular expression.
REPORT = {
    # The heading the report repeats on every page.  Used only to recognise
    # that line as page furniture; empty means the report has none.
    "hauptperson": "",
    # What the finished tree is called, and where its contents come from.
    "titel": "Stammbaum",
    "quelle": "",
    "quellhinweis": "",
    # Who compiled the report.  Shown in the page as the origin of the data.
    "autor": "",
}
_config = store.report_config()
if os.path.exists(_config):
    with open(_config, encoding="utf-8") as _fh:
        REPORT.update(json.load(_fh))

MONTHS = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11,
    "Dezember": 12,
}
MONTH_RE = "|".join(MONTHS)

REF = re.compile(r"([A-ZÄÖÜ][^{}]{0,70}?)\{(\d+)\}")
HEADING = re.compile(r"^(\d+)\.\s+([A-ZÄÖÜ][A-ZÄÖÜßÉÈ'\.\s\-\(\),]*[A-ZÄÖÜß\)\.])\s*(\(|wurde|heiratete|und\b|$)")

# Lines that are page furniture rather than content.  The running head is the
# main person's name, which differs per report and therefore comes from the
# configuration rather than from here.
FURNITURE = re.compile(
    r"^(=== SEITE|Seite \d+$|Direkte Verwandte$"
    + (r"|%s$" % re.escape(REPORT["hauptperson"]) if REPORT["hauptperson"] else "")
    + r"|Indirekte Verwandte über |Verzeichnis der |Die väterlichen Vorfahren$"
    r"|Die mütterlichen Vorfahren$|Nachkommen$|Stammbäume$|Notizen$|Quellen$)"
)
GENERATION = re.compile(r"^(Generation von |Gleiche Generation|Vorherige Generation)")


# --------------------------------------------------------------------------- io

def load_lines() -> list[dict]:
    with open(os.path.join(RAW_DIR, "lines.json"), encoding="utf-8") as fh:
        return json.load(fh)


def find_sections(lines: list[dict]) -> dict[str, tuple[int, int]]:
    """Locate the top level report sections by their numbered headings."""
    wanted = [
        (re.compile(r"^1\.\s+DIE VÄTERLICHEN VORFAHREN$"), "ahnen_vater"),
        (re.compile(r"^2\.\s+DIE MÜTTERLICHEN VORFAHREN$"), "ahnen_mutter"),
        (re.compile(r"^3\.\s+NACHKOMMEN$"), "nachkommen"),
        (re.compile(r"^4\.\s+DIREKTE VERWANDTE$"), "direkt"),
        (re.compile(r"^5\.\s+INDIREKTE VERWANDTE"), "indirekt_a"),
        (re.compile(r"^6\.\s+INDIREKTE VERWANDTE"), "indirekt_b"),
        (re.compile(r"^7\.\s+STAMMBÄUME$"), "baeume"),
        (re.compile(r"^8\.\s+NOTIZEN$"), "notizen"),
        (re.compile(r"^9\.\s+QUELLEN$"), "quellen"),
        (re.compile(r"^10\.\s+VERZEICHNIS DER ORTE$"), "orte"),
        (re.compile(r"^11\.\s+VERZEICHNIS DER EREIGNISSE$"), "ereignisse"),
        (re.compile(r"^12\.\s+VERZEICHNIS DER PERSONEN$"), "personen"),
    ]
    starts: dict[str, int] = {}
    for i, rec in enumerate(lines):
        text = rec["text"].strip()
        for pattern, key in wanted:
            if key not in starts and pattern.match(text) and rec["page"] > 2:
                starts[key] = i
    order = [k for _, k in wanted if k in starts]
    out = {}
    for n, key in enumerate(order):
        end = starts[order[n + 1]] if n + 1 < len(order) else len(lines)
        out[key] = (starts[key], end)
    return out


# ------------------------------------------------------------------- narrative

def collect_entries(lines: list[dict], spans: list[tuple[int, int]]) -> dict[int, dict]:
    """Split sections 4-6 into one block of lines per person."""
    entries: dict[int, dict] = {}
    current = None
    for start, end in spans:
        for rec in lines[start:end]:
            text = rec["text"].strip()
            if not text or FURNITURE.match(text) or GENERATION.match(text):
                continue
            if re.match(r"^\d+\.\s+(DIREKTE|INDIREKTE) VERWANDTE", text):
                current = None
                continue
            match = HEADING.match(text)
            if match:
                pid = int(match.group(1))
                if pid in entries:            # a wrapped date such as "8. Juni 2018"
                    if current is not None:
                        entries[current]["lines"].append(text)
                    continue
                current = pid
                entries[pid] = {"id": pid, "page": rec["page"], "lines": [text]}
                continue
            if current is not None:
                entries[current]["lines"].append(text)
    return entries


CHILD_LINE = re.compile(r"^([^{}]{2,70})\{(\d+)\}\s*(?:(?:ungefähr |zirka |um )?(\d{4}))?\s*$")


def reflow(block: list[str]) -> tuple[str, list[tuple[str, int, str | None]]]:
    """Join the wrapped narrative back into a paragraph, pulling out child lists.

    Returns the reflowed prose and the list of children the report printed
    underneath the marriage sentences (name, id, year).
    """
    prose: list[str] = []
    children: list[tuple[str, int, str | None]] = []
    for raw in block:
        line = raw.strip()
        match = CHILD_LINE.match(line)
        if match and not line.startswith("•") and " heiratete" not in line:
            children.append((match.group(1).strip(), int(match.group(2)), match.group(3)))
            continue
        prose.append(line)
    text = " ".join(prose)
    text = html.unescape(html.unescape(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text, children


# ------------------------------------------------------------------ name table

# Everything up to and including the last of these belongs to the sentence, not
# to the name: "..., in Osterbrook, Suederfeld, als Sohn von Herrn Unbekannt{173}".
NAME_CUT = re.compile(
    # "M. Dreyer" and "(Egon) Kettler" must survive, so an initial's full stop and
    # a bracketed nickname do not count as boundaries.
    r"^.*(?:[,;:]\s+|(?<![A-ZÄÖÜ])\.\s+|\d\s+"
    r"|\bals (?:Sohn|Tochter) von\s+"
    r"|\bvon\s+(?=[A-ZÄÖÜ])"
    r"|\bund\s+|\bmit\s+|\bsiehe\s+|•\s*"
    r"|\b(?:Geburt|Tod|Taufe|Heirat|Heiratserlaubnis|Beerdigung|Bestattung|Wohnsitz"
    r"|Einwanderung|Volkszählung|Marriage|Konfirmation|Beruf|Notiz|Quelle)"
    r"(?:\s+von|\s*:)\s*)",
    re.DOTALL)


def clean_name_candidate(text: str) -> str | None:
    name = NAME_CUT.sub("", text.strip(" ,.;:•"))
    name = name.strip(" ,.;:• ")
    name = re.sub(r"^Herrn\b", "Herr", name)
    if not name or not name[0].isupper() or len(name) > 55:
        return None
    return name


def build_name_table(lines: list[dict], entries: dict[int, dict],
                     skip: tuple[int, int] | None = None) -> dict[int, str]:
    """Prefer the properly cased spelling other entries use for a person.

    Entry headings are printed in capitals, but every cross reference in the
    report spells the name normally, so the references are the better source.
    The lines are glued back together first, because the report wraps in the
    middle of a name often enough to make a per-line reading lose first names.
    The tree diagrams are skipped: their boxes are columns, not sentences.
    """
    parts = []
    for i, rec in enumerate(lines):
        if skip and skip[0] <= i < skip[1]:
            continue
        text = rec["text"].strip()
        if FURNITURE.match(text):
            parts.append(" . ")            # a page break is not a word break
        else:
            parts.append(text)
    blob = " ".join(parts)

    votes: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for raw, pid in REF.findall(blob):
        name = clean_name_candidate(raw)
        if name:
            votes[int(pid)][name] += 1

    table: dict[int, str] = {}
    for pid, counter in votes.items():
        best = max(counter.items(), key=lambda kv: (kv[1], len(kv[0])))
        table[pid] = best[0]
    for pid, entry in entries.items():
        if pid not in table:
            head = HEADING.match(entry["lines"][0])
            table[pid] = titlecase(head.group(2).strip()) if head else "Person %d" % pid
    return table


SMALL_WORDS = {"von", "van", "der", "de", "zu", "den", "auf", "und"}


def titlecase(text: str) -> str:
    parts = []
    for word in text.split():
        if word.lower() in SMALL_WORDS:
            parts.append(word.lower())
        elif "-" in word:
            parts.append("-".join(p.capitalize() for p in word.split("-")))
        else:
            parts.append(word.capitalize())
    return " ".join(parts)


# --------------------------------------------------------------- person index

# "SURNAME, Given (relationship)."  The surname half is set in capitals and may
# itself contain a comma ("GROTHAUS, VAN, Lisbeth Freese").  A row that repeats
# the previous surname prints a run of dots in its place, comma included.
INDEX_ROW = re.compile(
    r"^(?P<sur>[A-ZÄÖÜß][A-ZÄÖÜß\s,'\.\-\(\)]*?),\s*(?P<given>[A-ZÄÖÜ\.].*?)\s*\((?P<rel>[^()]+)\)\.?$")
INDEX_SAME = re.compile(r"^\.{3,}\s*(?P<given>.+?)\s*\((?P<rel>[^()]+)\)\.?$")


def parse_person_index(lines: list[dict], span: tuple[int, int]) -> dict[int, dict]:
    """Section 12: a three column table flattened into one cell per line."""
    out: dict[int, dict] = {}
    pending: list[int] = []
    last_surname = ""
    carry = ""
    for rec in lines[span[0]:span[1]]:
        text = rec["text"].strip()
        if not text or FURNITURE.match(text) or text in ("Verw.", "Baum", "Name (Beziehungen)"):
            continue
        if text.startswith("12. VERZEICHNIS"):
            continue
        if re.fullmatch(r"\d+", text):
            if carry:
                carry = ""
            pending.append(int(text))
            continue
        text = (carry + " " + text).strip() if carry else text
        carry = ""
        match = INDEX_ROW.match(text)
        same = None if match else INDEX_SAME.match(text)
        if not (match or same):
            if text.endswith((",", "-")) or "(" in text:
                carry = text            # the row wrapped, keep collecting
            else:
                pending = []
            continue
        if not pending:
            continue
        if match:
            last_surname = match.group("sur").strip()
            given, relation = match.group("given"), match.group("rel")
        else:
            given, relation = same.group("given"), same.group("rel")
        surname = last_surname
        particle = re.match(r"^([A-ZÄÖÜ]{2,5}),\s*(.+)$", given)
        if particle:                     # "GROTHAUS, VAN, Lisbeth" -> van Grothaus
            surname = "%s %s" % (particle.group(1), surname)
            given = particle.group(2)
        out[pending[0]] = {
            "surname": titlecase(surname),
            "given": given.strip(),
            "relation": relation.strip(),
            "tree": pending[1] if len(pending) > 1 else None,
        }
        pending = []
    return out


# ------------------------------------------------------------- event register

EVENT_VERBS = {
    "Geburt": "Geburt", "Tod": "Tod", "Taufe": "Taufe", "Heirat": "Heirat",
    "Heiratserlaubnis": "Heiratserlaubnis", "Beerdigung": "Beerdigung",
    "Bestattung": "Beerdigung", "Wohnsitz": "Wohnsitz",
    "Einwanderung": "Einwanderung", "Volkszählung": "Volkszählung",
    "Marriage": "Heirat", "Konfirmation": "Konfirmation", "Beruf": "Beruf",
}
# longest first, so "Heiratserlaubnis" is not swallowed by "Heirat"
EVENT_START = re.compile(r"^(%s)(?:\s+von\b|\s*:)"
                         % "|".join(sorted(EVENT_VERBS, key=len, reverse=True)))


def parse_events(lines: list[dict], span: tuple[int, int]) -> list[dict]:
    """Section 11, grouped by year headings; lines may wrap."""
    joined: list[tuple[str | None, str]] = []
    year: str | None = None
    buffer = ""
    for rec in lines[span[0]:span[1]]:
        text = rec["text"].strip()
        if not text or FURNITURE.match(text) or text.startswith("11. VERZEICHNIS"):
            continue
        if re.fullmatch(r"\d{4}", text):
            if buffer:
                joined.append((year, buffer))
                buffer = ""
            year = text
            continue
        if EVENT_START.match(text):
            if buffer:
                joined.append((year, buffer))
            buffer = text
        elif buffer:
            buffer += " " + text
    if buffer:
        joined.append((year, buffer))

    events: list[dict] = []
    for year, text in joined:
        text = re.sub(r"\s+", " ", text).strip().rstrip(".")
        verb_match = EVENT_START.match(text)
        if not verb_match:
            continue
        kind = EVENT_VERBS[verb_match.group(1)]
        rest = text[verb_match.end():].strip()
        people = [int(pid) for _, pid in REF.findall(rest)]
        if not people:
            continue
        tail = rest[rest.rfind("}") + 1:]
        day = month = None
        date_match = re.search(r"\bam (\d{1,2})\.\s*(%s)?" % MONTH_RE, tail)
        if date_match:
            day = int(date_match.group(1))
            month = MONTHS.get(date_match.group(2)) if date_match.group(2) else None
        else:
            month_match = re.search(r"\b(?:im )?(%s)\b" % MONTH_RE, tail)
            if month_match:
                month = MONTHS[month_match.group(1)]
        approx = bool(re.search(r"\b(ungefähr|zirka|um|vor|nach|bis)\b", tail))
        place_match = re.search(r",?\s*in ([^.]+?)\s*$", tail)
        place = place_match.group(1).strip() if place_match else None
        if place:
            place = re.sub(r"\s*\d{4}\s*$", "", place).strip(" ,")
        year_match = re.search(r"\b(\d{4})\b", tail)
        events.append({
            "kind": kind,
            "people": people,
            "year": int(year) if year else (int(year_match.group(1)) if year_match else None),
            "month": month,
            "day": day,
            "place": place or None,
            "approx": approx,
            "text": text,
        })
    return events


PLACE_HEADING = re.compile(r"^[^a-zäöü]{3,}$")


def parse_places(lines: list[dict], span: tuple[int, int]) -> list[dict]:
    """Section 10 has two halves that need different handling.

    First comes a run of residences with the place written inline and the year
    at the end.  After that the register switches to blocks grouped under an
    ALL CAPS place heading, where the event lines carry a full date but no
    place of their own - the heading is the place.
    """
    blocks: list[tuple[str | None, str]] = []
    heading: str | None = None
    buffer = ""
    for rec in lines[span[0]:span[1]]:
        text = rec["text"].strip()
        if not text or FURNITURE.match(text) or text.startswith("10. VERZEICHNIS"):
            continue
        if EVENT_START.match(text):
            if buffer:
                blocks.append((heading, buffer))
            buffer = text
        elif PLACE_HEADING.match(text) and not buffer.endswith(","):
            if buffer:
                blocks.append((heading, buffer))
                buffer = ""
            heading = text.strip().rstrip(".")
        elif buffer:
            buffer += " " + text
    if buffer:
        blocks.append((heading, buffer))

    out: list[dict] = []
    for heading, text in blocks:
        text = re.sub(r"\s+", " ", text).strip().rstrip(".")
        verb = EVENT_START.match(text)
        if not verb:
            continue
        kind = EVENT_VERBS[verb.group(1)]
        rest = text[verb.end():].strip()
        refs = [int(pid) for _, pid in REF.findall(rest)]
        if not refs:
            continue
        tail = rest[rest.rfind("}") + 1:]
        day = month = year = None
        date = re.search(r"\bam (\d{1,2})\.\s*(%s)?\s*(\d{4})?" % MONTH_RE, tail)
        if date:
            day = int(date.group(1))
            month = MONTHS.get(date.group(2)) if date.group(2) else None
            year = int(date.group(3)) if date.group(3) else None
        else:
            only_month = re.search(r"\b(%s)\b\s*(\d{4})?" % MONTH_RE, tail)
            if only_month:
                month = MONTHS[only_month.group(1)]
                year = int(only_month.group(2)) if only_month.group(2) else None
        if year is None:
            trailing = re.search(r"(\d{4})\s*$", tail)
            year = int(trailing.group(1)) if trailing else None
        inline = re.search(r"\bin (.+?)(?:\s{2,}(?:ungefähr |zirka |um )?\d{4})?\s*$", tail)
        place = inline.group(1).strip(" ,") if inline else None
        if place:
            place = re.sub(r"\s*(?:ungefähr|zirka|um)?\s*\d{4}$", "", place).strip(" ,")
        out.append({
            "kind": kind,
            "people": refs,
            "place": place or (titlecase_place(heading) if heading else None),
            "year": year,
            "month": month,
            "day": day,
            "approx": bool(re.search(r"\b(ungefähr|zirka|um|vor|nach|bis)\b", tail)),
            "text": text,
        })
    return out


def titlecase_place(text: str) -> str:
    """'SUEDERFELD, WINDLOH' -> 'Suederfeld, Windloh'."""
    parts = []
    for chunk in text.split(","):
        words = []
        for word in chunk.split():
            words.append(word if (len(word) <= 3 and word.isupper() and word.isalpha()
                                  and word in ("USA", "UK")) else word.capitalize())
        parts.append(" ".join(words))
    return ", ".join(p.strip() for p in parts if p.strip())


# ----------------------------------------------------------- notes and sources

def parse_notes(lines: list[dict], span: tuple[int, int]) -> dict[int, list[str]]:
    """Section 8: numbered notes plus 'Trifft zu auf: NAME{id}; ...'."""
    text = " ".join(r["text"].strip() for r in lines[span[0]:span[1]]
                    if r["text"].strip() and not FURNITURE.match(r["text"].strip()))
    text = html.unescape(text)
    out: dict[int, list[str]] = collections.defaultdict(list)
    chunks = re.split(r"(?:(?<=\.)|^)\s*(\d+)\.\s+", text)
    for i in range(1, len(chunks) - 1, 2):
        body = chunks[i + 1]
        parts = body.split("Trifft zu auf:")
        note = re.sub(r"\s+", " ", parts[0]).strip().rstrip(".")
        if not note or note.startswith("NOTIZEN"):
            continue
        for _, pid in REF.findall(parts[1] if len(parts) > 1 else ""):
            out[int(pid)].append(note)
    return dict(out)


def parse_sources(lines: list[dict], span: tuple[int, int]) -> tuple[dict[int, str], dict[int, list[int]]]:
    """Section 9: numbered sources plus the people each one backs."""
    text = " ".join(r["text"].strip() for r in lines[span[0]:span[1]]
                    if r["text"].strip() and not FURNITURE.match(r["text"].strip()))
    text = html.unescape(text)
    text = re.sub(r"^9\.\s*QUELLEN\s*", "", text)
    titles: dict[int, str] = {}
    used: dict[int, list[int]] = collections.defaultdict(list)
    chunks = re.split(r"(?:(?<=\.)|^)\s*(\d+)\.\s+(?=[\"„])", text)
    for i in range(1, len(chunks) - 1, 2):
        num = int(chunks[i])
        body = re.sub(r"\s+", " ", chunks[i + 1]).strip()
        head = body.split("Quellenangaben:")[0]
        titles[num] = head.strip().rstrip(".")
        for _, pid in REF.findall(body.split("Quellenangaben:")[-1] if "Quellenangaben:" in body else ""):
            used[int(pid)].append(num)
    return titles, dict(used)


# ------------------------------------------------------------------ narrative facts

# The relationship label the report prints behind every name is the cleanest
# statement of a person's sex, so it is consulted first.  Word boundaries keep
# "Cousine" out of "Cousin" and "Enkelin" out of "Enkel".
SEX_BY_RELATION = [
    (re.compile(r"^(?:Frau|Ehefrau|Partnerin|Witwe)\s+von\b", re.I), "w"),
    (re.compile(r"^(?:Mann|Ehemann|Partner|Witwer)\s+von\b", re.I), "m"),
    (re.compile(r"\b(?:Mutter|Tochter|Schwester|Tante|Nichte|Cousine|Enkelin|Frau"
                r"|Gro(?:ß|ss)mutter|Gro(?:ß|ss)tante|Gro(?:ß|ss)nichte"
                r"|Urgro(?:ß|ss)mutter|Urgro(?:ß|ss)tante"
                r"|Schwiegertochter|Schwaegerin|Schwägerin|Halbschwester"
                r"|Stiefmutter|Stieftochter|Stiefschwester)\b", re.I), "w"),
    (re.compile(r"\b(?:Vater|Sohn|Bruder|Onkel|Neffe|Cousin|Enkel|Mann"
                r"|Gro(?:ß|ss)vater|Gro(?:ß|ss)onkel|Gro(?:ß|ss)neffe"
                r"|Urgro(?:ß|ss)vater|Urgro(?:ß|ss)onkel"
                r"|Schwiegersohn|Schwager|Halbbruder"
                r"|Stiefvater|Stiefsohn|Stiefbruder)\b", re.I), "m"),
]

PARENTS_RE = re.compile(
    r"als (Sohn|Tochter) von ([^{}]{1,60})\{(\d+)\}(?: und ([^{}]{1,60})\{(\d+)\})?")
MARRIED_TO_RE = re.compile(r"war mit ((?:[^{}]{1,60}\{\d+\}(?:,? und |, )?)+) verheiratet")
MARRIAGE_RE = re.compile(
    r"(?:^|\.\s|\s)([A-ZÄÖÜ][^{}.]{1,60})(?:\{(\d+)\})? heiratete"
    r"(?:\s+(?:zweimal|dreimal|viermal))?"
    r"(?:,\s*im Alter von [^,]{1,40},)?"
    r"\s*([A-ZÄÖÜ][^{},.]{1,60})?(?:\{(\d+)\})?")


def guess_sex(entry_text: str, relation: str | None) -> str | None:
    if relation:
        for pattern, sex in SEX_BY_RELATION:
            if pattern.search(relation):
                return sex
    if re.search(r"\bals Sohn von", entry_text):
        return "m"
    if re.search(r"\bals Tochter von", entry_text):
        return "w"
    if re.search(r"\bEr (?:starb|wurde|lebt|war|arbeitete|wohnte|ist)\b", entry_text):
        return "m"
    if re.search(r"\bSie (?:starb|wurde|lebt|war|arbeitete|wohnte|ist)\b", entry_text):
        return "w"
    return None


def parse_narrative_facts(text: str) -> dict:
    facts: dict = {"parents": [], "spouses": [], "occupation": None, "extra": None}

    match = PARENTS_RE.search(text)
    if match:
        facts["sex"] = "m" if match.group(1) == "Sohn" else "w"
        facts["parents"].append(int(match.group(3)))
        if match.group(5):
            facts["parents"].append(int(match.group(5)))

    for group in MARRIED_TO_RE.findall(text):
        for _, pid in REF.findall(group):
            facts["spouses"].append(int(pid))

    for name_a, id_a, name_b, id_b in MARRIAGE_RE.findall(text):
        for pid in (id_a, id_b):
            if pid:
                facts["spouses"].append(int(pid))

    occ = re.search(r"\barbeitete als ([^.;]+)", text)
    if occ:
        facts["occupation"] = occ.group(1).strip()
    else:
        # "Jan wurde Fahrlehrer." - a bare capitalised noun after "wurde"
        occ = re.search(r"(?:^|\.\s)\S+ wurde ([A-ZÄÖÜ][\wäöüß\-]{3,30})\.", text)
        if occ and occ.group(1) not in MONTHS:
            facts["occupation"] = occ.group(1).strip()

    extra = re.search(r"Weitere Informationen über [^.]{1,40}\.\s*(.+?)(?:\s*(?:Quellenangabe|Diese Familie|Notiz:)|$)", text)
    if extra:
        facts["extra"] = extra.group(1).strip()

    return facts


def split_narrative(text: str) -> dict[str, str]:
    """Cut the entry paragraph into reader friendly chunks."""
    out: dict[str, str] = {}
    work = text

    note = re.search(r"(Notiz:\s.+?)(?=\s*(?:Quellenangabe|Diese Familie wird|Weitere Informationen|$))", work)
    if note:
        out["notiz"] = note.group(1).strip()
        work = work.replace(note.group(1), " ")

    src = re.search(r"(Quellenangabe[n]?:.*)$", work)
    if src:
        out["quellen"] = re.sub(r"\s+", " ", src.group(1)).strip()
        work = work[:src.start()]

    tree = re.search(r"(Diese Familie wird (?:im|innerhalb) Stammbaum \d+ dargestellt\.)", work)
    if tree:
        work = work.replace(tree.group(1), " ")

    out["bio"] = re.sub(r"\s+", " ", work).strip()
    return out


# ----------------------------------------------------------------- photo mapping

def map_photos(lines: list[dict], entries: dict[int, dict]) -> dict[int, str]:
    """A portrait sits directly under the heading line of its person."""
    with open(os.path.join(RAW_DIR, "photos.json"), encoding="utf-8") as fh:
        photos = json.load(fh)

    heads: list[tuple[int, float, int]] = []      # page, y, person id
    for rec in lines:
        match = HEADING.match(rec["text"].strip())
        if not match:
            continue
        pid = int(match.group(1))
        if pid in entries and entries[pid]["page"] == rec["page"]:
            heads.append((rec["page"], rec["y"], pid))
    heads.sort()

    out: dict[int, str] = {}
    for photo in photos:
        if photo["page"] == 1:                     # publisher logo on the title page
            continue
        candidates = [h for h in heads if h[0] == photo["page"] and h[1] <= photo["top"] + 2]
        if not candidates:
            continue
        pid = candidates[-1][2]
        out.setdefault(pid, photo["file"])
    return out


# ------------------------------------------------------------------------ main

def sortkey(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def report_subject(people: dict[int, dict]) -> int:
    """The person this report was written for.

    Every label in the document is measured from them, so the check needs to
    know who they are.  The report says so itself - it marks that one entry as
    the main person - and only if it does not, the lowest id has to do.
    """
    for pid, person in sorted(people.items()):
        if "hauptperson" in (person.get("relation") or "").lower():
            return pid
    return min(people)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lines = load_lines()
    sections = find_sections(lines)

    narrative_spans = [sections[k] for k in ("direkt", "indirekt_a", "indirekt_b") if k in sections]
    entries = collect_entries(lines, narrative_spans)
    names = build_name_table(lines, entries, skip=sections.get("baeume"))
    index = parse_person_index(lines, sections["personen"])
    events = parse_events(lines, sections["ereignisse"])
    places = parse_places(lines, sections["orte"])
    notes = parse_notes(lines, sections["notizen"])
    source_titles, source_use = parse_sources(lines, sections["quellen"])
    photos = map_photos(lines, entries)

    problems: list[tuple[str, str]] = []
    people: dict[int, dict] = {}

    for pid, entry in sorted(entries.items()):
        text, printed_children = reflow(entry["lines"])
        idx = index.get(pid, {})
        # The heading may carry a bracketed name variant before the relationship
        # ("UBBO TALJE BOHLKEN (TALJE - WILKENS) (Ubbo 4 x Ur-Grossvater)"),
        # so the person index is the more dependable source for the label.
        relation = idx.get("relation")
        if not relation:
            for candidate in re.findall(r"\(([^()]{3,80})\)", text[:250]):
                # A label is either a possessive first name ("Ubbo 4 x Ur-Grossvater")
                # or one of the report's fixed phrases.  Matching the possessive
                # by shape rather than by name keeps this parser family-agnostic.
                if re.match(r"^(?:[A-ZÄÖÜ][\wäöüß\-]+s\s|Die Hauptperson|Frau von"
                            r"|Mann von|Partnerin von|Partner von)", candidate):
                    relation = candidate.strip()
                    break
        # Drop the heading.  The name itself may contain brackets, so cut right
        # after the bracketed relationship rather than at the first bracket.
        body = text
        if relation and ("(%s)" % relation) in text:
            body = text.split("(%s)" % relation, 1)[1]
        else:
            body = re.sub(r"^\d+\.\s+[^(]*(?:\([^)]*\)[\s.]*)*", "", text)
        body = body.lstrip(" .").strip()

        facts = parse_narrative_facts(body)
        chunks = split_narrative(body)
        sex_from_prose = facts.get("sex")
        sex_from_label = guess_sex("", relation)
        sex = sex_from_prose or sex_from_label or guess_sex(body, None)
        if sex_from_prose and sex_from_label and sex_from_prose != sex_from_label:
            problems.append(("Pruefen", "Person %d (%s): Erzaehltext sagt '%s', die Beziehung "
                                        "'%s' sagt '%s'." % (pid, names.get(pid), sex_from_prose,
                                                             relation, sex_from_label)))

        people[pid] = {
            "id": pid,
            "name": names.get(pid, "Person %d" % pid),
            "given": idx.get("given"),
            "surname": idx.get("surname"),
            "sex": sex,
            "relation": relation or idx.get("relation"),
            "tree": idx.get("tree"),
            "parents": facts["parents"],
            "spouses": sorted(set(facts["spouses"]) - {pid}),
            "children": [],
            "occupation": facts.get("occupation"),
            "extra": facts.get("extra"),
            "bio": chunks.get("bio", ""),
            "note_text": chunks.get("notiz"),
            "source_text": chunks.get("quellen"),
            "notes": notes.get(pid, []),
            "sources": sorted(set(source_use.get(pid, []))),
            "photo": photos.get(pid),
            "events": [],
            "printed_children": [c[1] for c in printed_children],
            "page": entry["page"],
        }

    # -- children by inverting the parent links -----------------------------
    for pid, person in people.items():
        for parent in person["parents"]:
            if parent in people:
                people[parent]["children"].append(pid)
            else:
                problems.append(("Struktur", "Person %d nennt Elternteil %d, den es im Bericht nicht gibt." % (pid, parent)))
    for person in people.values():
        person["children"] = sorted(set(person["children"]),
                                    key=lambda c: (birth_year(people[c], events) or 9999, c))

    # -- couples: shared children, marriage events, narrative --------------
    for person in people.values():
        if len(person["parents"]) == 2:
            a, b = person["parents"]
            if a in people and b in people:
                people[a]["spouses"] = sorted(set(people[a]["spouses"]) | {b})
                people[b]["spouses"] = sorted(set(people[b]["spouses"]) | {a})

    marriages: list[dict] = []
    for event in events:
        if event["kind"] == "Heirat" and len(event["people"]) == 2:
            a, b = event["people"]
            if a in people and b in people:
                people[a]["spouses"] = sorted(set(people[a]["spouses"]) | {b})
                people[b]["spouses"] = sorted(set(people[b]["spouses"]) | {a})
                marriages.append({"people": [a, b], "year": event["year"],
                                  "month": event["month"], "day": event["day"],
                                  "place": event["place"]})

    for person in people.values():
        person["spouses"] = [s for s in person["spouses"] if s in people and s != person["id"]]

    # -- attach events -----------------------------------------------------
    # Sections 10 and 11 describe the same events from two angles: section 11
    # knows the year (from its heading) and often the place, section 10 knows
    # the full date.  Merge them per person into one record each.
    buckets: dict[int, dict[tuple, dict]] = collections.defaultdict(dict)
    for event in list(events) + list(places):
        for pid in event["people"]:
            if pid not in people:
                continue
            record = {
                "kind": event["kind"], "year": event["year"], "month": event["month"],
                "day": event["day"], "place": event["place"], "approx": event["approx"],
                "with": sorted(p for p in event["people"] if p != pid),
            }
            key = (record["kind"], record["year"], tuple(record["with"]))
            existing = buckets[pid].get(key)
            if existing is None:
                loose = (record["kind"], None, tuple(record["with"]))
                if record["year"] is not None and loose in buckets[pid]:
                    existing = buckets[pid].pop(loose)
                    buckets[pid][key] = existing
            if existing is None:
                buckets[pid][key] = record
                continue
            for field in ("month", "day", "place", "year"):
                if existing.get(field) is None and record.get(field) is not None:
                    existing[field] = record[field]
            if record["place"] and existing["place"] and len(record["place"]) > len(existing["place"]):
                existing["place"] = record["place"]
            existing["approx"] = existing["approx"] and record["approx"]

    for pid, person in people.items():
        person["events"] = sorted(
            buckets.get(pid, {}).values(),
            key=lambda e: (e["year"] or 9999, e["month"] or 0, e["day"] or 0, e["kind"]))
        person["birth"] = first_event(person["events"], "Geburt")
        person["death"] = first_event(person["events"], "Tod")

    # -- top up birth and death from the prose ------------------------------
    # The registers know dates, the narrative often knows the place and the
    # cause of death.  Take whichever field is present.
    for person in people.values():
        for field, reader in (("birth", birth_from_prose), ("death", death_from_prose)):
            prose = reader(person["bio"])
            if not prose:
                continue
            if not person[field]:
                person[field] = prose
                continue
            for key, value in prose.items():
                if value is not None and person[field].get(key) is None:
                    person[field][key] = value
        if person["death"] is None and re.search(r"(?:Er|Sie) lebt nicht mehr", person["bio"]):
            person["death"] = {"year": None, "month": None, "day": None,
                               "place": None, "approx": False, "note": "lebt nicht mehr"}

    # -- validation --------------------------------------------------------
    def who(pid: int) -> str:
        person = people[pid]
        year = (person.get("birth") or {}).get("year")
        return "%s (#%d%s)" % (person["name"], pid, ", *%s" % year if year else "")

    def note(kind: str, text: str) -> None:
        problems.append((kind, text))

    for pid, person in sorted(people.items()):
        # 1. the child lists the report prints must match the parent links
        for child in sorted(set(person["printed_children"])):
            if child not in people:
                note("Struktur", "%s fuehrt Kind #%d auf, das im Bericht fehlt." % (who(pid), child))
            elif child not in person["children"]:
                note("Struktur", "%s fuehrt %s als Kind auf, aber dessen Eintrag nennt als Eltern %s."
                     % (who(pid), who(child),
                        ", ".join(who(p) for p in people[child]["parents"]) or "niemanden"))
        # 2. structural sanity
        if len(person["parents"]) > 2:
            note("Struktur", "%s hat %d Elternteile: %s."
                 % (who(pid), len(person["parents"]), ", ".join(who(p) for p in person["parents"])))
        if pid in person["parents"] or pid in person["children"] or pid in person["spouses"]:
            note("Struktur", "%s ist mit sich selbst verknuepft." % who(pid))
        for parent in person["parents"]:
            if parent in people and pid in people[parent]["parents"]:
                note("Struktur", "%s und %s sind wechselseitig Elternteil." % (who(pid), who(parent)))
        if person["sex"] is None:
            note("Luecke", "%s: Geschlecht nicht bestimmbar." % who(pid))
        if len(person["parents"]) == 2:
            a, b = person["parents"]
            if a in people and b in people and people[a]["sex"] and people[a]["sex"] == people[b]["sex"]:
                note("Pruefen", "%s: beide Elternteile sind als '%s' gefuehrt (%s, %s)."
                     % (who(pid), people[a]["sex"], who(a), who(b)))

        # 3. dates
        birth, death = person["birth"], person["death"]
        by = (birth or {}).get("year")
        dy = (death or {}).get("year")
        if by and dy:
            if dy < by:
                note("Datum", "%s: Tod %d liegt vor der Geburt %d." % (who(pid), dy, by))
            elif dy - by > 105:
                note("Pruefen", "%s: Lebensalter %d Jahre (%d-%d)." % (who(pid), dy - by, by, dy))
        if by and (by < 1500 or by > 2026):
            note("Datum", "%s: Geburtsjahr %d liegt ausserhalb des plausiblen Bereichs." % (who(pid), by))
        for event in person["events"]:
            ey = event.get("year")
            if by and ey and ey < by and event["kind"] != "Geburt":
                note("Datum", "%s: Ereignis '%s' %d liegt vor der Geburt %d."
                     % (who(pid), event["kind"], ey, by))
            if dy and ey and ey > dy and event["kind"] not in ("Tod", "Beerdigung"):
                note("Datum", "%s: Ereignis '%s' %d liegt nach dem Tod %d."
                     % (who(pid), event["kind"], ey, dy))
            if event["kind"] == "Heirat" and by and ey and ey - by < 16:
                note("Pruefen", "%s: Heirat %d im Alter von %d Jahren." % (who(pid), ey, ey - by))

        # 4. generations
        for parent in person["parents"]:
            if parent not in people:
                continue
            pb = (people[parent].get("birth") or {}).get("year")
            pd = (people[parent].get("death") or {}).get("year")
            if pb and by:
                gap = by - pb
                if gap < 14:
                    note("Datum", "%s waere bei der Geburt von %s erst %d Jahre alt gewesen."
                         % (who(parent), who(pid), gap))
                elif gap > 60:
                    note("Pruefen", "%s waere bei der Geburt von %s schon %d Jahre alt gewesen."
                         % (who(parent), who(pid), gap))
            if pd and by and by > pd + 1 and people[parent]["sex"] == "m":
                note("Datum", "%s starb %d, das Kind %s kam aber %d zur Welt."
                     % (who(parent), pd, who(pid), by))
            elif pd and by and by > pd and people[parent]["sex"] == "w":
                note("Datum", "%s starb %d, das Kind %s kam aber %d zur Welt."
                     % (who(parent), pd, who(pid), by))

    # 5. the same person entered twice
    # Match on surname, birth year and first given name, because a duplicated
    # branch tends to spell the middle names slightly differently ("Meinhard
    # Reemts Oltmanns" against "Meinhard Reemt Oltmanns").  A match alone means
    # little - "Almuth Dreyer, 1704" was a common enough combination in one
    # village - so it only counts as one person when the two records also
    # share a spouse, a parent or a child.
    def dupe_key(person: dict) -> tuple | None:
        year = (person.get("birth") or {}).get("year")
        given = (person.get("given") or person["name"]).split()
        if not year or not person.get("surname") or not given:
            return None
        return (sortkey(person["surname"]), year, sortkey(given[0]))

    buckets_dupe: dict[tuple, list[int]] = collections.defaultdict(list)
    for pid, person in sorted(people.items()):
        key = dupe_key(person)
        if key:
            buckets_dupe[key].append(pid)

    def shared_kin(a: dict, b: dict) -> set:
        return (set(a["spouses"]) & set(b["spouses"])
                | set(a["parents"]) & set(b["parents"])
                | set(a["children"]) & set(b["children"]))

    for ids in sorted(buckets_dupe.values()):
        for i, first in enumerate(ids):
            for second in ids[i + 1:]:
                a, b = people[first], people[second]
                shared = shared_kin(a, b)
                if shared:
                    note("Struktur", "%s und %s sind dieselbe Person, zweimal erfasst - "
                                     "gemeinsam: %s."
                         % (who(first), who(second), ", ".join(who(s) for s in sorted(shared))))
                elif not a["parents"] and not b["parents"]:
                    note("Pruefen", "%s und %s: gleicher Name und Jahrgang, beide ohne Eltern "
                                    "im Bericht - moeglicherweise dieselbe Person."
                         % (who(first), who(second)))
                else:
                    note("Pruefen", "%s und %s: gleicher Name und Jahrgang, aber verschiedene "
                                    "Angehoerige - vermutlich zwei verschiedene Personen."
                         % (who(first), who(second)))

    # a partner recorded twice shows up as two near identical spouses
    for pid, person in sorted(people.items()):
        spouses = [s for s in person["spouses"] if s in people]
        for i, first in enumerate(spouses):
            for second in spouses[i + 1:]:
                if dupe_key(people[first]) and dupe_key(people[first]) == dupe_key(people[second]):
                    note("Struktur", "%s ist mit %s und mit %s verheiratet - das ist "
                                     "vermutlich derselbe Mensch, doppelt erfasst."
                         % (who(pid), who(first), who(second)))

    # 6. the report's own relationship labels versus the extracted parent links
    # The report's own labels are all measured from its main person, so the
    # check has to start there too - that is a property of the source document,
    # not a centre the finished page keeps.
    for text in kinship.check_against_report(people, report_subject(people)):
        note("Struktur", text)

    for pid in range(1, max(people) + 1):
        if pid not in people:
            note("Luecke", "Personen-ID %d fehlt im Bericht." % pid)

    unmatched = [p for p in os.listdir(PHOTO_DIR)
                 if p not in set(photos.values()) and not p.startswith("p001_")]
    for name in sorted(unmatched):
        note("Luecke", "Portrait %s liess sich keiner Person zuordnen." % name)

    for person in people.values():
        del person["printed_children"]

    # No centre.  A family tree has no natural middle, and writing one in here
    # would put that person in front of every reader on every open.  The page
    # starts with the whole tree on screen and lets the reader pick.
    data = {
        "meta": {
            "title": REPORT["titel"],
            "root": None,
            "source": REPORT["quelle"],
            "source_note": REPORT["quellhinweis"],
            "source_author": REPORT["autor"],
            "count": len(people),
            "photos": len(photos),
            "span": year_span(people),
        },
        "people": [people[k] for k in sorted(people, key=lambda k: (sortkey(people[k]["name"]), k))],
        "marriages": marriages,
        "source_titles": source_titles,
        "checks": [{"kind": k, "text": v} for k, v in problems],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "tree.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    with open(os.path.join(DATA_DIR, "validation-report.txt"), "w", encoding="utf-8") as fh:
        fh.write("Pruefbericht Stammbaum\n")
        fh.write("Quelle: %s\n" % data["meta"]["source"])
        fh.write("Personen: %d   Fotos zugeordnet: %d\n" % (len(people), len(photos)))
        fh.write("Ereignisse: %d   Ortsregister: %d   Quellen: %d\n" % (len(events), len(places), len(source_titles)))
        fh.write("Ohne Geburtsjahr: %d   ohne Eltern: %d   ohne Partner: %d\n\n"
                 % (sum(1 for p in people.values() if not (p["birth"] or {}).get("year")),
                    sum(1 for p in people.values() if not p["parents"]),
                    sum(1 for p in people.values() if not p["spouses"])))
        if not problems:
            fh.write("Keine Auffaelligkeiten.\n")
        else:
            fh.write("%d Auffaelligkeiten.\n" % len(problems))
            fh.write("  Struktur = Widerspruch in den Verwandtschaftsangaben\n")
            fh.write("  Datum    = zeitlich unmoeglich\n")
            fh.write("  Pruefen  = moeglich, aber ungewoehnlich\n")
            fh.write("  Luecke   = im Bericht nicht vorhanden\n")
            for kind in ("Struktur", "Datum", "Pruefen", "Luecke"):
                rows = [t for k, t in problems if k == kind]
                if not rows:
                    continue
                fh.write("\n%s (%d)\n%s\n" % (kind.upper(), len(rows), "-" * 60))
                for row in rows:
                    fh.write("  - %s\n" % row)

    print("Personen        : %d" % len(people))
    print("Fotos zugeordnet: %d" % len(photos))
    print("Ereignisse      : %d" % len(events))
    print("Wohnorte        : %d" % len(places))
    print("Auffaelligkeiten: %d  (siehe data/validation-report.txt)" % len(problems))


def year_span(people: dict[int, dict]) -> str:
    """Earliest and latest year mentioned anywhere, for the page's own blurb."""
    years = []
    for person in people.values():
        for event in person["events"]:
            if event.get("year"):
                years.append(event["year"])
        for key in ("birth", "death"):
            if person.get(key) and person[key].get("year"):
                years.append(person[key]["year"])
    return "%d bis %d" % (min(years), max(years)) if years else "unbekannt"


def first_event(events: list[dict], kind: str) -> dict | None:
    for ev in events:
        if ev["kind"] == kind:
            return {"year": ev["year"], "month": ev["month"], "day": ev["day"],
                    "place": ev["place"], "approx": ev["approx"]}
    return None


def birth_year(person: dict, events: list[dict]) -> int | None:
    if person.get("birth"):
        return person["birth"].get("year")
    return None


BIRTH_CLAUSE = re.compile(r"wurde\s+(.*?),?\s*geboren")
DEATH_CLAUSE = re.compile(
    r"starb\s*(?:\((?P<cause>[^)]*)\)\s*)?(?P<rest>.*?)"
    r"(?=\s(?:Er|Sie)\s|\sNotiz:|\sQuellenangabe|\sWeitere Informationen|\sDiese Familie|$)")


def _date_and_place(clause: str) -> dict:
    day = month = year = None
    date = re.search(r"\bam (\d{1,2})\.\s*(%s)\s*(\d{4})?" % MONTH_RE, clause)
    if date:
        day = int(date.group(1))
        month = MONTHS[date.group(2)]
        year = int(date.group(3)) if date.group(3) else None
    else:
        only_month = re.search(r"\bim (%s)\s*(\d{4})?" % MONTH_RE, clause)
        if only_month:
            month = MONTHS[only_month.group(1)]
            year = int(only_month.group(2)) if only_month.group(2) else None
    if year is None:
        any_year = re.search(r"\b(1\d{3}|20\d{2})\b", clause)
        year = int(any_year.group(1)) if any_year else None
    # the place is the last ", in ..." run, minus the parent clause
    body = re.split(r",?\s*als (?:Sohn|Tochter) von", clause)[0]
    body = re.sub(r",\s*im Alter von [^,]+,", ",", body)
    place = None
    hit = re.search(r",?\s*in ([^,].*)$", body)
    if hit:
        place = hit.group(1).strip(" ,.")
        place = re.sub(r"\s*(?:wie im Stammbaum \d+ gezeigt).*$", "", place).strip(" ,.")
    return {"year": year, "month": month, "day": day, "place": place or None,
            "approx": bool(re.search(r"\b(ungefähr|zirka|um|vor|nach)\b", clause))}


def birth_from_prose(text: str) -> dict | None:
    match = BIRTH_CLAUSE.search(text)
    if not match:
        return None
    result = _date_and_place(match.group(1))
    return result if (result["year"] or result["place"]) else None


def death_from_prose(text: str) -> dict | None:
    match = DEATH_CLAUSE.search(text)
    if not match:
        if re.search(r"(?:Er|Sie) lebt nicht mehr", text):
            return {"year": None, "month": None, "day": None, "place": None,
                    "approx": False, "note": "lebt nicht mehr"}
        return None
    result = _date_and_place(match.group("rest"))
    if match.group("cause"):
        result["cause"] = match.group("cause").strip()
    if not (result["year"] or result["place"] or result.get("cause")):
        return {"year": None, "month": None, "day": None, "place": None,
                "approx": False, "note": "lebt nicht mehr"} if "lebt nicht mehr" in text else None
    return result


if __name__ == "__main__":
    main()
