# -*- coding: utf-8 -*-
"""Step 3 of the pipeline: fold tree.json and the portraits into one HTML file.

The result is meant to be handed around the family, so it has to survive being
attached to an email and opened by double click on a machine with no internet
connection.  That rules out side car files: the data becomes an inline object
and every portrait an inline data URI.
"""
from __future__ import annotations

import base64
import datetime
import shutil
import subprocess
import tempfile
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edits as overlay_lib
import store

HERE = os.path.dirname(os.path.abspath(__file__))
# The template travels with the program; everything that is data comes out of
# the data folder, wherever the person running this put it.
FROZEN = getattr(sys, "frozen", False)
ROOT = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else os.path.dirname(HERE)
# Asked for, not created - see the note in build_data.py.
DATA_DIR = store.build_dir(create=False)
PHOTO_DIR = store.build_photo_dir(create=False)
OUTPUT = store.page_path()


def template_path() -> str:
    """The page template.

    Running from source it is the one next to this file, which is what makes
    editing the page and reloading the window work.  Inside a built program it
    is the copy baked into it, and nothing beside the exe can take its place.
    """
    # A built program uses the template inside it, full stop.  Preferring a
    # `tools/` folder that happens to lie beside the exe was meant to help while
    # working on the page; what it actually did was let a left over folder
    # silently override the program with an older page - the kind of fault
    # nobody can see, because the exe and the page both look right.
    if FROZEN:
        return os.path.join(getattr(sys, "_MEIPASS", HERE), "template.html")
    return os.path.join(HERE, "template.html")


def version() -> str:
    """The program's version number, from the one place it is written down.

    It has to be in the template regardless: the page handed to the family
    carries it in its footer and its manual, and that page is one file with no
    program behind it.  So the template is the source, and everything else asks
    here rather than keeping a copy.

    It was kept in three places for one afternoon - the template, the editor,
    the exe builder - which is exactly long enough for them to be able to
    disagree.  A window saying 1.1 while its own file properties say 1.0 is the
    kind of fault that costs an hour to believe.
    """
    try:
        with open(template_path(), encoding="utf-8") as fh:
            found = re.search(r'const\s+VERSION\s*=\s*"([^"]+)"', fh.read(200_000))
    except OSError:
        return "?"
    return found.group(1) if found else "?"

# Portraits are printed at roughly 50x66pt in the report; 300x400px is plenty
# for a screen and keeps the finished file in the low single digit megabytes.
MAX_WIDTH = 300
JPEG_QUALITY = 82

# Fields that stay out of the file handed to the family unless it is asked for
# explicitly.  Telephone numbers and the file names of scanned certificates are
# nobody else's business, and the page would otherwise carry them to everyone
# it is forwarded to.  `--alles` puts them back in.
PRIVATE_FIELDS = ("contact", "documents")



def check_script(html: str) -> None:
    """Refuse to ship a page whose JavaScript does not parse.

    The data and the photos are injected into one big inline script, so a
    single mangled character silently kills the whole page while the file
    still looks perfectly normal.  Node is used when it is around; without it
    the check is skipped and says so.
    """
    node = shutil.which("node")
    if not node:
        print("Hinweis  : node nicht gefunden, Syntaxpruefung uebersprungen")
        return
    start = html.rindex("<script>") + len("<script>")
    end = html.rindex("</script>")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(html[start:end])
        path = fh.name
    try:
        done = subprocess.run([node, "--check", path],
                              capture_output=True, text=True)
    finally:
        os.unlink(path)
    if done.returncode != 0:
        raise SystemExit("ABBRUCH: das Seitenskript ist fehlerhaft\n"
                         + done.stderr.strip())
    print("Syntax   : geprueft, in Ordnung")

def encode_photos(people: list[dict], folder: str | None = None) -> dict[str, str]:
    """Portraits as inline data URIs, keyed by person id.

    The folder is a parameter because the pipeline reads `data/photos` while
    the program reads its own store, and both render the same page.
    """
    try:
        from PIL import Image
    except ImportError:
        Image = None

    # Two folders, because a portrait can come from either place: the ones cut
    # out of the report land in `data/photos`, the ones added by hand in the
    # tree's own `fotos`.  Looking in only one of them is what produced
    # "Foto fehlt" for pictures that were sitting right there.
    folders = [folder] if folder else []
    for candidate in (store.photo_dir(create=False), PHOTO_DIR):
        if candidate not in folders:
            folders.append(candidate)

    out: dict[str, str] = {}
    for person in people:
        name = person.get("photo")
        if not name:
            continue
        path = next((os.path.join(f, name) for f in folders
                     if os.path.exists(os.path.join(f, name))), None)
        if not path:
            print("  Foto fehlt: %s" % name)
            continue
        if Image is not None:
            with Image.open(path) as img:
                img = img.convert("RGB")
                if img.width > MAX_WIDTH:
                    img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)),
                                     Image.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
                blob = buffer.getvalue()
        else:
            with open(path, "rb") as fh:
                blob = fh.read()
        out[str(person["id"])] = "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii")
    return out


def page_html(data: dict, photo_folder: str | None = None) -> str:
    """Fold a tree dict and its portraits into the finished page.

    Split out of `main` so that `export.py` can render a page whose data has
    already had the fields nobody may see cut out of it.
    """
    with open(template_path(), encoding="utf-8") as fh:
        template = fh.read()
    photos = encode_photos(data["people"], photo_folder)
    html = template
    html = html.replace("__TITLE__", data["meta"]["title"])
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__PHOTOS__", json.dumps(photos, separators=(",", ":")))
    html = html.replace("__BUILT__", datetime.datetime.now().strftime("%d.%m.%Y um %H:%M"))
    return html


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    keep_private = "--alles" in sys.argv[1:]
    from_report = "--aus-bericht" in sys.argv[1:]

    # The tree the editor keeps, not the parse of the PDF.  Those were two
    # piles for one family: whoever ran build.cmd after an afternoon in the
    # editor got a page without that afternoon in it, and nothing said so.
    # The report is where a tree begins; the editor is where it lives.
    slug = store.open_slug()
    if from_report or not store.has_tree(slug):
        data, _ = overlay_lib.load_merged(DATA_DIR)
        source = "dem Bericht"
        # The report is older than the editor's tree more often than not, and
        # the page is what gets sent to the family.  Said out loud with the
        # numbers, because "326" beside "341" needs no explaining.
        if store.has_tree(slug):
            kept = len((store.load(slug) or {}).get("people") or [])
            if kept > len(data.get("people") or []):
                print("  ACHTUNG: im Editor stehen %d Personen, im Bericht %d."
                      % (kept, len(data["people"])))
                print("  Diese Seite zeigt den Bericht. Ohne --aus-bericht")
                print("  wuerde sie aus dem gepflegten Baum gebaut.")
    else:
        data = store.load(slug)
        source = "dem gepflegten Baum"
    print("Gelesen aus: %s" % source)

    # The page does not need the raw source blobs of the report; they are long,
    # repetitive and already summarised in the per person fields.
    slim = json.loads(json.dumps(data))
    # Which tree this page IS.  A linked person lists every tree that carries
    # her, this one included, and without knowing its own name the page would
    # offer a note pointing at itself.  In the program the same answer comes
    # from the editing object; the family's copy has only this.
    slim.setdefault("meta", {})["slug"] = slug
    for person in slim["people"]:
        if person.get("source_text") and len(person["source_text"]) > 1200:
            person["source_text"] = person["source_text"][:1200].rstrip() + " …"
        if not keep_private:
            for field in PRIVATE_FIELDS:
                person.pop(field, None)

    html = page_html(slim)
    photos = encode_photos(slim["people"])

    check_script(html)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        fh.write(html)

    size = os.path.getsize(OUTPUT) / (1024 * 1024)
    print("Geschrieben: %s" % os.path.basename(OUTPUT))
    print("Personen   : %d" % len(data["people"]))
    print("Quelle     : %s" % source)
    print("Privates   : %s" % ("mit Kontakt und Unterlagen (--alles)" if keep_private
                               else "Kontaktdaten und Unterlagen weggelassen"))
    print("Portraits  : %d" % len(photos))
    print("Groesse    : %.1f MB" % size)


if __name__ == "__main__":
    main()
