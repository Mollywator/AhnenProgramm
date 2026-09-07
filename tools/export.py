# -*- coding: utf-8 -*-
"""Writing the tree out: a page, a picture, a printed book.

Three things make this more than a file copy.

**Not everything may leave the house.**  The page gets forwarded through a
family, so the export is a list of tick boxes rather than a button.  Contact
details and scanned documents start unticked, and what is not ticked is cut out
of the data before anything is written - not hidden by CSS, actually removed.

**A poster is not an A4 page.**  The diagram keeps its own page, as wide as it
needs, up to the 190 inch a PDF reader will still open.  The person book is
ordinary A4.  Chromium understands named page rules, so both come out of one
print run rather than out of two files that then have to be merged - which is
what keeps this module free of pymupdf and the program small.

**Printing is done by Edge.**  It is already required for the program window,
it renders the same CSS the page does, and it can print without a dialog.  That
is far better typography than anything worth writing by hand here.
"""
from __future__ import annotations

import base64
import datetime
import html as html_mod
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baum as baum_lib  # noqa: E402
import build_site  # noqa: E402
import gedcom  # noqa: E402

# Which person fields each tick box on the dialog stands for.  Name, sex and
# number are not in here: they are what makes an entry an entry.
FIELD_GROUPS = {
    "lebensdaten": ("birth", "death", "burial"),
    "orte": (),                      # handled inside the two above plus residences
    "familie": ("parents", "spouses", "children"),
    "beruf": ("occupation", "religion"),
    "lebenslauf": ("events",),
    "fotos": ("photo",),
    "notizen": ("freetext", "notes", "extra", "note_text"),
    "bericht": ("bio", "source_text", "sources", "relation", "tree", "page"),
    "kontakt": ("contact",),
    "unterlagen": ("documents",),
}

PLACE_KEYS = ("place",)

# A PDF reader stops opening pages somewhere past 200 inch; staying under that
# with a margin means the poster still prints at a shop.
MAX_PAGE_IN = 190.0
DPI = 96.0


def edge() -> str | None:
    for path in build_site_edge_candidates():
        if os.path.exists(path):
            return path
    return None


def build_site_edge_candidates() -> list[str]:
    # kept next to the server's own list rather than imported, so that this
    # module works on its own from a shell as well
    return [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]


def safe_part(text: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join(" " if ch in bad else ch for ch in str(text))
    return " ".join(out.split()).strip(" .") or "Stammbaum"


def trim(data: dict, fields: dict) -> dict:
    """Take out every field whose group was not ticked."""
    out = json.loads(json.dumps(data))
    drop: set[str] = set()
    for group, keys in FIELD_GROUPS.items():
        if not fields.get(group):
            drop.update(keys)
    if not fields.get("orte"):
        drop.add("residences")

    for person in out["people"]:
        for key in drop:
            if key in ("parents", "spouses", "children", "events", "notes",
                       "sources", "documents", "residences"):
                person[key] = []
            else:
                person[key] = None
        # A place is part of a date field rather than a field of its own, so
        # it has to be cut out from inside.
        if not fields.get("orte"):
            for key in ("birth", "death", "burial"):
                if isinstance(person.get(key), dict):
                    person[key] = {k: v for k, v in person[key].items() if k not in PLACE_KEYS}
            for event in person.get("events") or []:
                event.pop("place", None)
    return out


def only(data: dict, ids) -> dict:
    """Keep the people the open view shows, and nobody else.

    The diagram was always right: it arrives already drawn by the page, which
    knows exactly whom it put on the stage.  The book and the HTML page are
    built here instead, out of whatever `data` holds - and that was the whole
    tree no matter which view was open.  A "Ganze Linie" of 23 people came out
    as a hundred page book of all 326, with names in it that were deliberately
    not on the stage.  The view was a picture frame, not a filter.

    Taking people out leaves references pointing at nobody, so every list of
    ids is cut down to the survivors as well: somebody with no entry in the
    export is not named in it either.  This does happen - the parents of a
    married-in partner sit one step outside "Ganze Linie" - and a name in an
    `Eltern:` line with no entry of its own is exactly the leak this closes.

    What cannot be cut is prose.  A life story or a source note is a sentence,
    and it names whoever it names; those live in the `notizen` and `bericht`
    boxes, which is why both start unticked.
    """
    if not ids:
        return data
    keep = {int(i) for i in ids}
    out = json.loads(json.dumps(data))
    out["people"] = [p for p in out["people"] if p["id"] in keep]
    # what actually survived, so a stale list from the page cannot leave behind
    # a reference to somebody who never made it into the file
    keep = {p["id"] for p in out["people"]}

    for person in out["people"]:
        for key in ("parents", "spouses", "children"):
            person[key] = [i for i in person.get(key) or [] if i in keep]
        for event in person.get("events") or []:
            if event.get("with"):
                event["with"] = [i for i in event["with"] if i in keep]

    out["marriages"] = [m for m in out.get("marriages") or []
                        if all(i in keep for i in m.get("people") or [])]
    # the check report names people as "#id"; a line about somebody outside the
    # export has nothing to say to whoever receives it
    out["checks"] = [c for c in out.get("checks") or []
                     if all(int(n) in keep
                            for n in re.findall(r"#(\d+)", c.get("text") or ""))]
    return out


def restate_meta(data: dict) -> None:
    """Put the heading numbers back in line with what is really in the file.

    A page that says "326 Personen" above 23 entries is wrong in the first
    place anybody looks, and the span would still name a century that no
    longer appears.  Run after the fields are trimmed, so that a portrait cut
    out by the tick boxes is not counted either.
    """
    people = data["people"]
    meta = data["meta"]
    meta["count"] = len(people)
    meta["photos"] = sum(1 for p in people if p.get("photo"))
    years = sorted(y for p in people
                   for y in ((p.get("birth") or {}).get("year"),
                             (p.get("death") or {}).get("year")) if y)
    meta["span"] = "%d bis %d" % (years[0], years[-1]) if years else ""
    if meta.get("root") is not None and meta["root"] not in {p["id"] for p in people}:
        meta["root"] = None


# ------------------------------------------------------------------ the page
def write_html(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_site.page_html(data))


# --------------------------------------------------------------- the picture
def write_svg(svg: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)


def write_png(blob64: str, path: str) -> None:
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(blob64))


# ------------------------------------------------------------------- the PDF
PRINT_TIMEOUT = 300


def to_pdf(html_path: str, pdf_path: str) -> None:
    """Print one page through Edge, on a profile of this print run's own.

    Without `--user-data-dir` the print run wants the profile the user's own
    Edge is sitting in.  When that one holds the lock - a window open, an
    update running - the second Edge hands its command line to the first and
    ends straight away: return code 0, nothing on stderr, and no PDF.  That
    silence is what the export ran into, and it is the same reason the program
    window already gets a throwaway profile of its own.

    A second attempt costs a few seconds and covers a browser that was busy
    starting up; what both attempts said is kept, because a print that failed
    twice has to be able to say why.
    """
    browser = edge()
    if not browser:
        raise RuntimeError("Zum Drucken wird Microsoft Edge gebraucht, es wurde aber keines gefunden.")
    source = pathlib.Path(html_path).resolve().as_uri()
    target = str(pathlib.Path(pdf_path).resolve())
    notes: list[str] = []

    for attempt in (1, 2):
        with tempfile.TemporaryDirectory(prefix="stammbaum-druckprofil-") as profile:
            command = [browser, "--headless=new", "--disable-gpu",
                       "--no-pdf-header-footer",
                       "--user-data-dir=" + profile,
                       "--no-first-run", "--no-default-browser-check",
                       "--disable-extensions",
                       "--print-to-pdf=" + target, source]
            try:
                done = subprocess.run(command, capture_output=True, text=True,
                                      timeout=PRINT_TIMEOUT)
            except subprocess.TimeoutExpired:
                notes.append("Versuch %d: Edge hat nach %d Minuten nicht geantwortet."
                             % (attempt, PRINT_TIMEOUT // 60))
                continue
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return
        notes.append("Versuch %d: Edge endete mit Rueckgabecode %s.\n%s"
                     % (attempt, done.returncode,
                        (done.stderr or "").strip()[-600:] or "Edge hat nichts dazu gesagt."))

    raise RuntimeError("Edge hat keine PDF geschrieben.\n\n%s\n\nEdge: %s\nSeite: %s"
                       % ("\n\n".join(notes), browser, html_path))


# ----------------------------------------------------------- printable pages
def esc(text) -> str:
    return html_mod.escape("" if text is None else str(text), quote=False)


MONTHS = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


def date_text(d: dict | None) -> str:
    if not d:
        return ""
    bits = []
    if d.get("day") and d.get("month"):
        bits.append("%d. %s" % (d["day"], MONTHS[d["month"]]))
    elif d.get("month"):
        bits.append(MONTHS[d["month"]])
    if d.get("year"):
        bits.append(str(d["year"]))
    out = " ".join(bits)
    if d.get("approx") and out:
        out = "um " + out
    if out and d.get("place"):
        out += ", " + d["place"]
    return out or (d.get("place") or "")


def lifespan(person: dict) -> str:
    born = (person.get("birth") or {}).get("year")
    died = (person.get("death") or {}).get("year")
    if born and died:
        return "%s–%s" % (born, died)
    if born:
        return "* %s" % born
    if died:
        return "† %s" % died
    return ""


PRINT_CSS_BODY = """
*{box-sizing:border-box}
body{margin:0;font-family:Constantia,"Palatino Linotype",Georgia,serif;
     font-size:10.5pt;line-height:1.5;color:#1d1a16;background:#fff}
.sans{font-family:"Franklin Gothic Book",Corbel,"Segoe UI",sans-serif}
h1{font-family:"Franklin Gothic Book",Corbel,"Segoe UI",sans-serif;
   font-size:26pt;letter-spacing:.12em;text-transform:uppercase;margin:0 0 6mm}
h1 em{font-style:normal;color:#8f2f22}
.titel{page-break-after:always;padding-top:60mm}
.titel p{color:#5d564a;max-width:120mm}
.gruppe{font-family:"Franklin Gothic Book",Corbel,"Segoe UI",sans-serif;
        font-size:9pt;letter-spacing:.2em;text-transform:uppercase;color:#8b8375;
        border-bottom:1px solid #d5cdbb;padding-bottom:2mm;margin:8mm 0 4mm;
        page-break-after:avoid}
.person{page-break-inside:avoid;margin:0 0 7mm;padding-bottom:5mm;
        border-bottom:1px solid #e6e0d2;display:grid;
        grid-template-columns:22mm minmax(0,1fr);gap:6mm}
.person.ohnebild{grid-template-columns:minmax(0,1fr)}
.person img{width:22mm;height:28mm;object-fit:cover;box-shadow:0 0 0 .3mm #c2b8a2}
.person h2{margin:0;font-size:14pt;font-weight:500}
.person .leben{font-family:"Franklin Gothic Book",Corbel,"Segoe UI",sans-serif;
               font-size:8.5pt;letter-spacing:.08em;color:#8b8375;margin:1mm 0 3mm}
dl{margin:0;display:grid;grid-template-columns:30mm minmax(0,1fr);gap:1mm 4mm}
dt{font-family:"Franklin Gothic Book",Corbel,"Segoe UI",sans-serif;font-size:8pt;
   letter-spacing:.1em;text-transform:uppercase;color:#8b8375;padding-top:.6mm}
dd{margin:0;color:#3d382f}
.frei{margin:3mm 0 0;color:#5d564a;white-space:pre-wrap}
.lauf{margin:3mm 0 0;padding:0;list-style:none}
.lauf li{display:grid;grid-template-columns:18mm 26mm minmax(0,1fr);gap:3mm;
         border-bottom:.2mm dotted #d5cdbb;padding:.8mm 0}
.lauf .jahr{color:#8f2f22}
.lauf .was{font-family:"Franklin Gothic Book",Corbel,"Segoe UI",sans-serif;
           font-size:8pt;letter-spacing:.08em;text-transform:uppercase;color:#5d564a}
"""


def person_entry(person: dict, photos: dict, by_id: dict, fields: dict) -> str:
    name = person.get("name") or "Ohne Namen"
    shot = photos.get(str(person["id"])) if fields.get("fotos") else None

    rows: list[tuple[str, str]] = []
    if person.get("title"):
        rows.append(("Titel", person["title"]))
    if person.get("call_name"):
        rows.append(("Rufname", person["call_name"]))
    if person.get("birth_name"):
        rows.append(("Geburtsname", person["birth_name"]))
    if person.get("birth"):
        rows.append(("Geboren", date_text(person["birth"])))
    if person.get("death"):
        rows.append(("Gestorben", date_text(person["death"])))
    if (person.get("death") or {}).get("cause"):
        rows.append(("Todesursache", person["death"]["cause"]))
    if person.get("burial"):
        rows.append(("Beerdigt", date_text(person["burial"])))
    if person.get("occupation"):
        rows.append(("Beruf", person["occupation"]))
    if person.get("religion"):
        rows.append(("Konfession", person["religion"]))

    for label, key in (("Eltern", "parents"), ("Ehe", "spouses"), ("Kinder", "children")):
        names = [by_id[i]["name"] for i in person.get(key) or [] if i in by_id]
        if names:
            rows.append((label, ", ".join(names)))

    for spot in person.get("residences") or []:
        when = "–".join(str(x) for x in (spot.get("from"), spot.get("to")) if x)
        where = ", ".join(x for x in (spot.get("place"), spot.get("address")) if x)
        rows.append(("Wohnort" + (" " + when if when else ""), where or "—"))

    contact = person.get("contact") or {}
    for label, key in (("Telefon", "phone"), ("Mobil", "mobile"),
                       ("E-Mail", "email"), ("Anschrift", "address")):
        if contact.get(key):
            rows.append((label, contact[key]))

    for doc in person.get("documents") or []:
        rows.append(("Unterlage", doc.get("title") or doc.get("file")))

    rows.append(("Nummer", "#%d" % person["id"]))

    # Birth, death and burial are already spelled out above; repeating them as
    # the only three lines of a life story makes every entry look padded.
    said = set()
    if person.get("birth"):
        said.add("geburt")
    if person.get("death"):
        said.add("tod")
    if person.get("burial"):
        said.add("beerdigung")
    story = [e for e in person.get("events") or []
             if (e.get("kind") or "").strip().lower() not in said or e.get("text")]
    story.sort(key=lambda e: e.get("year") or 9999)
    lauf = ""
    if story:
        lauf = '<ul class="lauf">' + "".join(
            '<li><span class="jahr">%s</span><span class="was">%s</span><span>%s</span></li>' % (
                esc(("um " if e.get("approx") else "") + str(e["year"]) if e.get("year") else "—"),
                esc(e.get("kind") or ""),
                esc(" · ".join(x for x in (date_text({k: e.get(k) for k in ("day", "month", "place")}),
                                           e.get("text")) if x)))
            for e in story) + "</ul>"

    frei = person.get("freetext")
    notes = "\n".join(person.get("notes") or [])
    free_block = ""
    if frei or notes:
        free_block = '<p class="frei">%s</p>' % esc("\n".join(x for x in (frei, notes) if x))

    body = ("<h2>%s</h2><p class='leben'>%s</p><dl>%s</dl>%s%s" % (
        esc(name),
        esc(lifespan(person) or "Lebensdaten unbekannt"),
        "".join("<dt>%s</dt><dd>%s</dd>" % (esc(a), esc(b)) for a, b in rows if b),
        lauf, free_block))

    if shot:
        return '<div class="person"><img src="%s" alt=""><div>%s</div></div>' % (shot, body)
    return '<div class="person ohnebild"><div>%s</div></div>' % body


def book_body(data: dict, photos: dict, fields: dict, centre_name: str) -> str:
    people = sorted(data["people"],
                    key=lambda p: (p.get("surname") or "ZZZ", p.get("given") or "",
                                   (p.get("birth") or {}).get("year") or 0))
    by_id = {p["id"]: p for p in data["people"]}
    meta = data["meta"]

    blocks, letter = [], None
    for person in people:
        first = (person.get("surname") or "?")[:1].upper()
        if first != letter:
            letter = first
            blocks.append('<p class="gruppe">%s</p>' % esc(letter))
        blocks.append(person_entry(person, photos, by_id, fields))

    today = datetime.datetime.now().strftime("%d.%m.%Y")
    return """<div class="titel">
  <h1>%(titel_html)s</h1>
  <p class="sans" style="letter-spacing:.14em;text-transform:uppercase;font-size:9pt;color:#8b8375">
    Personenbuch · %(anzahl)d Personen · %(spanne)s</p>
  <p style="margin-top:12mm">%(quelle)s</p>
  <p>Mittelpunkt der Verwandtschaftsangaben: <b>%(mittelpunkt)s</b>.</p>
  <p>Gedruckt am %(datum)s.</p>
</div>
%(inhalt)s""" % {
        "titel_html": esc(meta.get("title") or "Stammbaum"),
        "anzahl": len(people),
        "spanne": esc(meta.get("span") or ""),
        "quelle": esc(meta.get("source_note") or ""),
        "mittelpunkt": esc(centre_name),
        "datum": today,
        "inhalt": "\n".join(blocks),
    }


def poster_size(svg: str) -> tuple[float, float]:
    """How big a page the drawing wants, in inches, within what a reader opens."""
    m = re.search(r'width="([\d.]+)"\s+height="([\d.]+)"', svg)
    width = float(m.group(1)) if m else 1200.0
    height = float(m.group(2)) if m else 800.0
    w_in, h_in = width / DPI, height / DPI
    shrink = min(1.0, MAX_PAGE_IN / max(w_in, h_in))
    return w_in * shrink, h_in * shrink


def print_document(title: str, svg: str | None, book: str | None) -> str:
    """One printable HTML - poster page, book pages, or both in that order.

    With both, the two page sizes are told apart by name.  Named page rules are
    a recent thing in Chromium; the two single cases stay on a plain `@page` so
    that the common export does not depend on them.
    """
    rules, blocks = [], []
    named = bool(svg) and bool(book)

    if svg:
        w_in, h_in = poster_size(svg)
        rules.append("@page %s{size:%.3fin %.3fin;margin:0}"
                     % ("poster" if named else "", w_in, h_in))
        # line-height 0 on the wrapper: an inline SVG otherwise sits on a text
        # baseline, and those few stray pixels spill onto a second, empty page
        rules.append(".posterseite{%smargin:0;line-height:0;overflow:hidden}"
                     % ("page:poster;" if named else ""))
        rules.append("svg.baum{display:block;width:%.3fin;height:%.3fin}" % (w_in, h_in))
        blocks.append('<div class="posterseite">%s</div>'
                      % svg.replace("<svg ", '<svg class="baum" ', 1))

    if book:
        rules.append("@page %s{size:A4;margin:18mm 16mm}" % ("buch" if named else ""))
        if named:
            rules.append(".buchteil{page:buch;page-break-before:always}")
        rules.append(PRINT_CSS_BODY)
        blocks.append('<div class="buchteil">%s</div>' % book)

    return """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<title>%(titel)s</title><style>
html,body{margin:0;padding:0;background:#fff}
%(css)s
</style></head><body>%(inhalt)s</body></html>""" % {
        "titel": esc(title), "css": "\n".join(rules), "inhalt": "\n".join(blocks)}


FAILURE_FILE = "Druck-Protokoll.txt"


def note_failure(out_dir: str, err: Exception, wanted: str, page: str) -> str:
    """Write down why a print failed and hand back the one line to show.

    The page that was to be printed is kept as well.  It is a finished document
    that only wants a printer, so opening it and pressing Strg+P still gets the
    PDF out - otherwise it would go with the temporary folder.
    """
    stamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    rescue = "Nicht gedruckt - " + wanted.rsplit(".", 1)[0] + ".html"
    try:
        shutil.copyfile(page, os.path.join(out_dir, rescue))
    except OSError:
        rescue = ""
    try:
        with open(os.path.join(out_dir, FAILURE_FILE), "a", encoding="utf-8") as fh:
            fh.write("%s\nGewollt: %s\n%s\n" % (stamp, wanted, err))
            if rescue:
                fh.write("Die Seite selbst liegt als \"%s\" daneben - im Browser "
                         "oeffnen und mit Strg+P drucken.\n" % rescue)
            fh.write("%s\n\n" % ("-" * 60))
    except OSError:
        return str(err)
    return ("%s  Einzelheiten stehen im Ordner Export in %s."
            % (str(err).splitlines()[0], FAILURE_FILE))


# --------------------------------------------------------------------- entry
def run(data: dict, order: dict, out_dir: str, centre_name: str) -> list[str]:
    """Do what the dialog asked for and hand back the file names written."""
    os.makedirs(out_dir, exist_ok=True)
    fields = order.get("felder") or {}
    formats = set(order.get("formate") or [])
    want_diagram = bool(order.get("diagramm"))
    want_book = bool(order.get("buch"))
    svg = order.get("svg")

    views = {"nah": "Nahe Familie", "ahnen": "Ahnentafel",
             "blut": "Ganze Linie", "alle": "Alle"}
    view = views.get(order.get("ansicht"), order.get("ansicht") or "Ansicht")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    title = data["meta"].get("title") or "Stammbaum"
    # Without a centre there is no "um wen" to put in the name, and writing
    # one in anyway is how a file ends up called "... - Alle - Stammbaum - ...".
    stem = safe_part("%s - %s - %s - %s" % (title, view, centre_name, stamp)
                     if centre_name else "%s - %s - %s" % (title, view, stamp))
    # The data formats are the whole tree, not the view that happens to be open,
    # so naming them after it would be a lie on the file name.
    data_stem = safe_part("%s - %s" % (title, stamp))

    # Two datasets, because the dialog promises two different things.  What is
    # a picture of the tree - the book, the page - shows the view that is open
    # and nobody else.  The two data formats say in the dialog that they are
    # always the whole tree, which is what makes them useful for handing the
    # tree itself to somebody, so they keep it.
    slim = trim(only(data, order.get("personen")), fields)
    restate_meta(slim)
    whole = trim(data, fields) if {"baum", "gedcom"} & formats else slim
    photos = build_site.encode_photos(slim["people"]) if fields.get("fotos") else {}
    written: list[str] = []

    def target(suffix: str) -> str:
        return os.path.join(out_dir, stem + suffix)

    def data_target(suffix: str) -> str:
        return os.path.join(out_dir, data_stem + suffix)

    if "svg" in formats and want_diagram and svg:
        write_svg(svg, target(".svg"))
        written.append(stem + ".svg")

    if "png" in formats and want_diagram and order.get("png"):
        write_png(order["png"], target(".png"))
        written.append(stem + ".png")

    if "html" in formats:
        write_html(slim, target(".html"))
        written.append(stem + ".html")

    # The two that are data rather than a picture of data.  A PDF is for
    # looking at; these are for handing the tree itself to somebody.
    if "baum" in formats:
        baum_lib.write(whole, data_target(baum_lib.SUFFIX),
                       with_documents=bool(fields.get("unterlagen")),
                       title=title)
        written.append(data_stem + baum_lib.SUFFIX)

    if "gedcom" in formats:
        with open(data_target(".ged"), "w", encoding="utf-8", newline="") as fh:
            fh.write(gedcom.write(whole))
        written.append(data_stem + ".ged")

    if "pdf" in formats:
        poster = svg if (want_diagram and svg) else None
        book = book_body(slim, photos, fields, centre_name) if want_book else None

        # Either everything asked for goes into one document, or each half gets
        # its own - both cases are one print run per file, no merging.
        if poster and book and not order.get("zusammen"):
            jobs = [(" - Diagramm.pdf", poster, None), (" - Personenbuch.pdf", None, book)]
        elif poster or book:
            jobs = [(".pdf", poster, book)]
        else:
            jobs = []

        with tempfile.TemporaryDirectory(prefix="stammbaum-druck-") as work:
            for n, (suffix, part_svg, part_book) in enumerate(jobs):
                page = os.path.join(work, "druck%d.html" % n)
                with open(page, "w", encoding="utf-8") as fh:
                    fh.write(print_document(stem, part_svg, part_book))
                pdf = os.path.join(work, "druck%d.pdf" % n)
                try:
                    to_pdf(page, pdf)
                except RuntimeError as err:
                    # The window can only show one line of this.  A failed print
                    # that says nothing is what made the last one hard to look
                    # into, so the whole account goes into the export folder.
                    raise RuntimeError(note_failure(out_dir, err, stem + suffix, page)) from err
                shutil.move(pdf, target(suffix))
                written.append(stem + suffix)

    return written
