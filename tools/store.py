# -*- coding: utf-8 -*-
"""The program's own data folder - and the several trees that can live in it.

Until now `Stammbaum.exe` was a launcher for one particular tree: it read
`Stammbaum.html` and `data/` out of the folder it was sitting in, and without
them it showed an error.  That is fine for one household and wrong for a
program meant to be handed to another family, or published at all.

It keeps its own folder instead, makes it on first start, and knows nobody
until a tree is opened or made.  And it holds **several** trees rather than
one, because that is what actually happens: one for your side, one for your
wife's, one somebody sent you to look at.  Importing is then something you do
once - afterwards the tree is simply there, and switching between them is a
menu rather than a fresh import.

    <the data folder>/
      einstellungen.json     which tree was open, and where each one lives
      SB_Hemken/             one folder per tree, and everything of it inside
        baum.json            the people, the marriages, the heading
        fotos/               portraits, referenced by file name
        dokumente/<nr>/      scans belonging to that person
        sicherung/           the last saves, oldest thrown away
        source/              the genealogy report this tree was built from
        data/                what the parser made of it, and the portraits
        Export/              finished pages, diagrams and books
        Stammbaum.html       the page for the family
        report.json          what to read, and who gathered it
      SB_Rodenberg/
        ...

Keeping each tree whole in one folder is what makes the rest simple: deleting
one is deleting a folder, a portrait can never end up attached to somebody in
another family, and handing one tree to a relative is handing over one folder.

That was only half true before: the trees sat under `baeume/`, but the report,
the parsed data, the exports and the finished page lay loose in the data folder
and were shared by all of them.  Two trees meant one of them quietly overwrote
the other's page, and the editor and `build.cmd` read from different piles.
Everything belonging to a tree now lives under that tree.

The folder is named after the tree rather than after a slug - `SB_` and the
name, with a leading "Stammbaum" dropped, so "Stammbaum Hemken" becomes
`SB_Hemken`.  It is a folder a person opens in Explorer and has to recognise.
Which folder belongs to which tree is written down in `einstellungen.json`, so
renaming a tree can rename its folder without anything losing track of it.

## Where that folder is

Anywhere the person running the program says.  By default it sits next to the
program, so the whole thing travels on a stick; where that place cannot be
written to - a folder under Program Files, say - it goes to the user's own
application data instead.

It can also be put somewhere else entirely, and there is a good reason to:
**data next to the program is data inside the repository folder**, one careless
`git add -A` away from being published.  Moving it out is a structural
guarantee rather than a rule that has to hold.

The choice is looked for in this order, first hit wins:

    1  the AHNEN_DATEN environment variable        for scripts and automation
    2  datenordner.txt next to the program         a deliberate, portable setup
    3  datenordner.txt in the application data     what the editor writes
    4  Stammbaum-Daten next to the program         the default, if writable
    5  the user's application data                 last resort, always works

`data/tree.json` and `data/edits.json` from the old arrangement are not
abandoned: the first start finds them and offers to take them over.  Neither is
a single `baum.json` from the version before this one, which is moved into a
tree folder of its own the first time it is seen.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edits as person_lib  # noqa: E402

FOLDER_NAME = "Stammbaum-Daten"
APP_DIRNAME = "Ahnenprogramm"
POINTER_FILE = "datenordner.txt"
ENV_VAR = "AHNEN_DATEN"
TREES_DIRNAME = "baeume"          # where trees lived before; still read on start
TREE_PREFIX = "SB_"               # what a tree folder is called now
TREE_FILE = "baum.json"
SETTINGS_FILE = "einstellungen.json"
PHOTO_DIRNAME = "fotos"
DOCS_DIRNAME = "dokumente"
BACKUP_DIRNAME = "sicherung"
BIN_DIRNAME = "_geloescht"

# Everything of a tree that used to lie loose in the data folder, and the name
# it keeps inside the tree folder.  Read by the move on first start.
LOOSE = ("source", "data", "Export", "Stammbaum.html", "report.json",
         "Namensliste.txt")

# Of those, the ones a save or an export writes again from the tree.  A leftover
# of one of these is not worth a question on start: `source` and `data` hold a
# report somebody scanned and cannot be got back, these hold nothing that is
# not already in `baum.json`.
REBUILDABLE = ("Export", "Stammbaum.html", "Namensliste.txt")

# Enough saves to get back past a bad afternoon, few enough that the folder
# stays readable when somebody opens it looking for something.
KEEP_BACKUPS = 20


# ------------------------------------------------------------------- folders
def program_dir() -> str:
    """The folder the program lives in - the exe's own, or the project root."""
    here = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(here)


def writable(folder: str) -> bool:
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".schreibprobe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.unlink(probe)
        return True
    except OSError:
        return False


def app_dir() -> str:
    """The user's own place for this program, whatever else is going on."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIRNAME)


def pointer_files() -> list[str]:
    """The two places a chosen data folder can be written down.

    Beside the program first: somebody who puts a file there did it on purpose,
    and it is what makes a stick work.  The editor writes the second one,
    because the first is not always writable.
    """
    return [os.path.join(program_dir(), POINTER_FILE),
            os.path.join(app_dir(), POINTER_FILE)]


def read_pointer() -> str | None:
    for path in pointer_files():
        try:
            with open(path, encoding="utf-8") as fh:
                wanted = fh.read().strip()
        except OSError:
            continue
        if wanted:
            return os.path.abspath(os.path.expandvars(os.path.expanduser(wanted)))
    return None


def write_pointer(path: str | None) -> str:
    """Remember the chosen folder in **both** places, or forget it everywhere.

    Beside the program, so that the setting travels with it on a stick.  And in
    the user's application data, because the copy beside the program disappears
    with the program folder - somebody unpacking a new version over the old one,
    or deleting the folder and putting the program back.

    Writing only the first one, which is what this did, meant exactly that case
    ended with the program looking at an empty folder beside itself while the
    trees sat untouched where they had always been.  Nothing was lost, but
    nothing was found either, and the person is left thinking it was.
    """
    written = []
    for target in pointer_files():
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if path is None:
                if os.path.exists(target):
                    os.unlink(target)
                continue
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(os.path.abspath(path) + "\n")
            written.append(target)
        except OSError:
            continue
    return written[0] if written else ""


def anchor_pointer() -> None:
    """Write the folder in use down where losing the program cannot lose it.

    Called on start.  A folder that is not simply the default beside the
    program is a decision somebody made, and it should not have to be made
    twice because a folder was replaced.  The default itself is left alone -
    freezing that would tie the program to the disk it first ran from.
    """
    here = data_dir()
    if os.path.abspath(here) == os.path.abspath(
            os.path.join(program_dir(), FOLDER_NAME)):
        return
    if not os.path.isdir(here):
        return
    spare = os.path.join(app_dir(), POINTER_FILE)
    if os.path.isfile(spare):
        return
    try:
        os.makedirs(os.path.dirname(spare), exist_ok=True)
        with open(spare, "w", encoding="utf-8") as fh:
            fh.write(os.path.abspath(here) + "\n")
    except OSError:
        pass


def data_dir() -> str:
    """Where this copy of the program keeps everything.

    The order is documented at the top of this file.  Nothing here creates the
    folder except the last resort, which has to exist for the program to run at
    all; asking where the data would live must not leave folders behind.
    """
    chosen = os.environ.get(ENV_VAR) or ""
    if chosen.strip():
        return os.path.abspath(os.path.expandvars(os.path.expanduser(chosen.strip())))

    pointed = read_pointer()
    if pointed:
        return pointed

    beside = os.path.join(program_dir(), FOLDER_NAME)
    if os.path.isdir(beside) or writable(beside):
        return beside

    fallback = os.path.join(app_dir(), FOLDER_NAME)
    os.makedirs(fallback, exist_ok=True)
    return fallback


def where_from() -> str:
    """Which of the five rules decided the data folder - for the editor to show."""
    if (os.environ.get(ENV_VAR) or "").strip():
        return "Umgebungsvariable " + ENV_VAR
    for path in pointer_files():
        if os.path.isfile(path):
            return "eingestellt in " + path
    beside = os.path.join(program_dir(), FOLDER_NAME)
    if os.path.isdir(beside):
        return "neben dem Programm"
    return "Anwendungsdaten des Benutzers"


# ---- the folders of the pipeline, all hanging off one tree ------------------
# They used to hang off the data folder, which meant a second tree shared the
# first one's report, exports and page.  Each one now takes an optional slug so
# a script can ask about a tree other than the open one.
def report_dir(create: bool = True, slug: str | None = None) -> str:
    """Where the genealogy report PDF of this tree is looked for."""
    path = os.path.join(tree_dir(slug, create), "source")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def build_dir(create: bool = True, slug: str | None = None) -> str:
    """What the parser made of the report: tree.json, the portraits, the report."""
    path = os.path.join(tree_dir(slug, create), "data")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def raw_dir(create: bool = True, slug: str | None = None) -> str:
    path = os.path.join(build_dir(create, slug), "raw")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def build_photo_dir(create: bool = True, slug: str | None = None) -> str:
    path = os.path.join(build_dir(create, slug), "photos")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def export_dir(create: bool = True, slug: str | None = None) -> str:
    path = os.path.join(tree_dir(slug, create), "Export")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def page_path(slug: str | None = None) -> str:
    """The finished page for the family - data, so it lives with the tree."""
    return os.path.join(tree_dir(slug, create=False), "Stammbaum.html")


def report_config(slug: str | None = None) -> str:
    """The one file that knows a family. Never beside the program."""
    return os.path.join(tree_dir(slug, create=False), "report.json")


def trees_dir() -> str:
    """Where trees lived before they each got a folder of their own.

    Kept because the move on first start has to find them, and because a data
    folder that has not been opened by the new version yet still looks like
    this.  Nothing writes here any more.
    """
    return os.path.join(data_dir(), TREES_DIRNAME)


# ------------------------------------------------- where each tree is written
# The program keeps a note of which folder belongs to which tree, so that a
# folder can be named after the family - `SB_Hemken`, something a person
# recognises in Explorer - while the program goes on calling it by its slug.
# Rename a tree and the folder is renamed with it; nothing else has to know.
def registry() -> dict:
    """slug -> {"ordner": …, "titel": …} for every tree the program knows."""
    known = settings().get("baeume")
    return known if isinstance(known, dict) else {}


def register(slug: str, folder: str, title: str | None = None) -> None:
    known = registry()
    entry = dict(known.get(slug) or {})
    entry["ordner"] = folder
    if title is not None:
        entry["titel"] = title
    known[slug] = entry
    remember(baeume=known)


def forget(slug: str) -> None:
    known = registry()
    if known.pop(slug, None) is not None:
        remember(baeume=known)


FOLDER_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def folder_name(title: str, slug: str = "") -> str:
    """`SB_` and the family's name, as a person would write it on a box.

    The word "Stammbaum" is dropped where it leads - it is the same word on
    every folder and says nothing.  Umlauts stay: this is a folder somebody
    reads, and Windows has had no trouble with them for twenty years.  What
    cannot stay are the characters a path may not contain.
    """
    name = (title or slug or "Stammbaum").strip()
    low = name.lower()
    for word in ("stammbaum ", "stammbuch ", "familie "):
        if low.startswith(word):
            name = name[len(word):].strip()
            break
    name = FOLDER_BAD.sub(" ", name).strip(" .")
    name = re.sub(r"\s+", " ", name)[:60].strip()
    return TREE_PREFIX + (name or "Stammbaum")


def free_folder(title: str, slug: str = "") -> str:
    """A folder name nothing else is using."""
    base = folder_name(title, slug)
    taken = {(e or {}).get("ordner") for e in registry().values()}
    taken.discard((registry().get(slug) or {}).get("ordner"))
    root = data_dir()
    n, name = 2, base
    while name in taken or (name != (registry().get(slug) or {}).get("ordner")
                            and os.path.exists(os.path.join(root, name))):
        name = "%s %d" % (base, n)
        n += 1
    return name


def tree_dir(slug: str | None = None, create: bool = True) -> str:
    """The folder of one tree.

    `create` is off wherever the path is only being looked at.  Merely asking
    where a tree would live must not leave an empty folder behind - which is
    what a program started with nothing in it used to do.
    """
    slug = slug or open_slug()
    entry = registry().get(slug) or {}
    folder = entry.get("ordner")
    if not folder:
        # A tree nobody has written down yet: either it still sits in the old
        # `baeume/` folder, or it is about to be made.
        old = os.path.join(trees_dir(), slug)
        if os.path.isfile(os.path.join(old, TREE_FILE)):
            return old
        folder = free_folder(heading_title(slug), slug)
        register(slug, folder, heading_title(slug))
    path = os.path.join(data_dir(), folder)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def heading_title(slug: str) -> str:
    """The tree's own name, asked without loading it - the registry first."""
    entry = registry().get(slug) or {}
    return entry.get("titel") or slug


def photo_dir(slug: str | None = None, create: bool = True) -> str:
    path = os.path.join(tree_dir(slug, create), PHOTO_DIRNAME)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def docs_dir(person_id: int | str | None = None, slug: str | None = None) -> str:
    base = os.path.join(tree_dir(slug), DOCS_DIRNAME)
    path = base if person_id is None else os.path.join(base, str(person_id))
    os.makedirs(path, exist_ok=True)
    return path


def tree_path(slug: str | None = None) -> str:
    return os.path.join(tree_dir(slug, create=False), TREE_FILE)


# ------------------------------------------------------------------ settings
def settings() -> dict:
    path = os.path.join(data_dir(), SETTINGS_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def remember(**values) -> None:
    now = settings()
    now.update(values)
    path = os.path.join(data_dir(), SETTINGS_FILE)
    os.makedirs(data_dir(), exist_ok=True)
    tmp = path + ".neu"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(now, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------- naming a tree
SLUG_BAD = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """A folder name from a tree's name: readable, and safe on any disk."""
    # the umlauts have to go first: NFKD pulls them apart into a letter and a
    # mark, and stripping the mark afterwards turns "Böhme" into "bohme"
    flat = (title or "").lower()
    for umlaut, plain in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        flat = flat.replace(umlaut, plain)
    flat = unicodedata.normalize("NFKD", flat)
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return SLUG_BAD.sub("-", flat).strip("-")[:48] or "stammbaum"


def free_slug(title: str) -> str:
    base = slugify(title)
    taken = set(all_slugs()) | set(registry())
    if base not in taken:
        return base
    n = 2
    while "%s-%d" % (base, n) in taken:
        n += 1
    return "%s-%d" % (base, n)


# ------------------------------------------------------------- which is open
def all_slugs() -> list[str]:
    """Every tree this data folder holds, however it got there.

    Three places, because a data folder can be in any of three states: written
    down in the registry, sitting in a folder nobody has registered yet -
    somebody copied one in - or still under the old `baeume/`.

    What makes a folder a tree is the `baum.json` inside it, not its name.  It
    used to be the `SB_` prefix, and that quietly broke the one case this is
    for: somebody hands over the folder their family is in, it is called
    whatever they called it, the program reports finding it - `identify` never
    asked about the prefix - and then goes on not showing it.  A folder handed
    over is named by the person who hands it over, and the program has no
    business insisting on its own naming.
    """
    found: dict[str, str] = {}

    for slug, entry in registry().items():
        folder = (entry or {}).get("ordner")
        if folder and os.path.isfile(os.path.join(data_dir(), folder, TREE_FILE)):
            found[slug] = folder

    root = data_dir()
    known = set(found.values())
    for name in holds_trees(root):
        if name in known:
            continue
        # not free_slug: that asks all_slugs, and this is all_slugs
        bare = name[len(TREE_PREFIX):] if name.startswith(TREE_PREFIX) else name
        slug = slugify(bare or name)
        n, unique = 2, slug
        while unique in found:
            unique = "%s-%d" % (slug, n)
            n += 1
        register(unique, name, title_in(os.path.join(root, name)))
        found[unique] = name

    old = trees_dir()
    if os.path.isdir(old):
        for name in os.listdir(old):
            if name == BIN_DIRNAME or name in found:
                continue
            if os.path.isfile(os.path.join(old, name, TREE_FILE)):
                found[name] = ""          # still where it always was

    return sorted(found)


def open_slug() -> str:
    """The tree the program is currently showing.

    Falls back to whatever is there rather than to nothing: a settings file
    pointing at a folder somebody deleted by hand should not make the program
    look as though every tree were gone.
    """
    lift_single_tree()
    wanted = settings().get("offen")
    have = all_slugs()
    if wanted and wanted in have:
        return wanted
    if have:
        return have[0]
    return "stammbaum"


def set_open(slug: str) -> None:
    remember(offen=slug)


def heading(slug: str) -> dict:
    """Just enough about a tree to list it, without reading all of it."""
    path = tree_path(slug)
    out = {"slug": slug, "titel": slug, "personen": 0, "gespeichert": None}
    try:
        with open(path, encoding="utf-8") as fh:
            tree = json.load(fh)
    except (OSError, ValueError):
        return out
    meta = tree.get("meta") or {}
    out["titel"] = meta.get("title") or slug
    out["personen"] = len(tree.get("people") or [])
    out["gespeichert"] = meta.get("gespeichert")
    out["fotos"] = meta.get("photos") or 0
    return out


def listing() -> list[dict]:
    return [heading(slug) for slug in all_slugs()]


# ------------------------------------------------------------------ the tree
def empty_tree(title: str = "Neuer Stammbaum") -> dict:
    return {
        "meta": {"title": title, "root": None, "source": None, "source_note": None,
                 "source_author": None,
                 "count": 0, "photos": 0, "span": "",
                 "angelegt": datetime.datetime.now().isoformat(timespec="seconds")},
        "people": [], "marriages": [], "source_titles": {}, "checks": [],
    }


def has_tree(slug: str | None = None) -> bool:
    return os.path.exists(tree_path(slug))


def load(slug: str | None = None) -> dict:
    """The open tree, or an empty one when the program has never been used."""
    slug = slug or open_slug()
    if not has_tree(slug):
        return empty_tree()
    with open(tree_path(slug), encoding="utf-8") as fh:
        tree = json.load(fh)
    tree.setdefault("meta", {})
    tree["people"] = [person_lib.fill_missing(p) for p in tree.get("people") or []]
    tree.setdefault("marriages", [])
    tree.setdefault("source_titles", {})
    tree.setdefault("checks", [])
    person_lib.normalise_links(tree["people"])
    return tree


def save(tree: dict, slug: str | None = None) -> str:
    """Write a tree, keeping the previous one.

    The order matters and is the whole point: the new file is written beside the
    old one and only swapped in once it is complete, so a crash halfway through
    leaves the previous tree intact rather than half a family.
    """
    slug = slug or open_slug()
    person_lib.normalise_links(tree["people"])
    tree.setdefault("meta", {})
    tree["meta"]["count"] = len(tree["people"])
    # Counted from the folder, not from the records: a GEDCOM carries the file
    # name of a portrait but not the picture, so a tree read from one would
    # otherwise announce 95 portraits it does not have.
    have = set(os.listdir(photo_dir(slug)))   # created here if this is a first save
    tree["meta"]["photos"] = sum(1 for p in tree["people"] if (p.get("photo") or "") in have)
    tree["meta"]["gespeichert"] = datetime.datetime.now().isoformat(timespec="seconds")

    path = tree_path(slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        keep_backup(path, slug)

    tmp = path + ".neu"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)

    # A readable index of who is in which tree, refreshed on every save so it
    # is never one edit behind.  Never worth losing a save over, though.
    try:
        import namensliste
        namensliste.write(sys.modules[__name__], slug)
    except Exception:                                       # noqa: BLE001
        pass

    return slug


def keep_backup(path: str, slug: str) -> None:
    folder = os.path.join(tree_dir(slug), BACKUP_DIRNAME)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")
    shutil.copy2(path, os.path.join(folder, "baum %s.json" % stamp))
    old = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    for name in old[:-KEEP_BACKUPS]:
        try:
            os.unlink(os.path.join(folder, name))
        except OSError:
            pass


def next_id(tree: dict) -> int:
    used = [int(p["id"]) for p in tree.get("people") or []]
    return max([person_lib.FIRST_NEW_ID - 1] + used) + 1


# ----------------------------------------------------- making and unmaking
def create(title: str, tree: dict | None = None, open_it: bool = True) -> str:
    """Put a new tree in a folder of its own and hand back the name it got."""
    slug = free_slug(title)
    register(slug, free_folder(title, slug), title)
    tree = tree or empty_tree(title)
    tree.setdefault("meta", {})["title"] = title
    save(tree, slug)
    if open_it:
        set_open(slug)
    return slug


def describe(slug: str, title: str | None = None, author: str | None = None) -> None:
    """The two things about a tree that somebody writes by hand.

    `author` is who gathered the data - the person the family has to thank for
    it.  It is a property of the tree, not of the program, which is why it sits
    here and not in the page: a second tree has a second author.
    """
    tree = load(slug)
    meta = tree.setdefault("meta", {})
    if title is not None:
        meta["title"] = title
    if author is not None:
        meta["source_author"] = author.strip() or None
    save(tree, slug)
    if title is not None:
        rename_folder(slug, title)


def rename_folder(slug: str, title: str) -> str | None:
    """Carry the folder along when a tree is given a new name.

    A folder called `SB_Hemken` for a tree renamed to "Stammbaum Rodenberg" is
    a folder somebody will not find again.  Failing is allowed and quiet: the
    tree keeps working under its old folder, which the registry still names,
    and a locked folder is not worth an error message in the middle of a
    rename.
    """
    entry = registry().get(slug) or {}
    now = entry.get("ordner")
    if not now:
        register(slug, free_folder(title, slug), title)
        return None
    wanted = folder_name(title, slug)
    if wanted == now:
        register(slug, now, title)
        return None
    wanted = free_folder(title, slug)
    root = data_dir()
    try:
        os.rename(os.path.join(root, now), os.path.join(root, wanted))
    except OSError:
        register(slug, now, title)
        return None
    register(slug, wanted, title)
    return wanted


def discard(slug: str) -> str:
    """Take a tree out of the way without destroying it.

    Moved rather than deleted, and the folder it goes into says so: somebody
    who removes the wrong family should be able to get them back by dragging a
    folder, not by remembering a backup.
    """
    if slug not in all_slugs():
        raise ValueError("Diesen Stammbaum gibt es nicht.")
    here = tree_dir(slug, create=False)
    bin_dir = os.path.join(data_dir(), BIN_DIRNAME)
    os.makedirs(bin_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H%M%S")
    target = os.path.join(bin_dir, "%s %s" % (os.path.basename(here), stamp))
    shutil.move(here, target)
    forget(slug)
    rest = all_slugs()
    set_open(rest[0] if rest else "")
    return target


# --------------------------------------------------- taking a folder in
def adopt_folder(source: str) -> str:
    """Copy one tree folder into this data folder and hand back its slug.

    The other half of importing.  A `.baum` file is what somebody sends by
    mail; a folder is what somebody hands over on a stick, or what is left of
    an installation somebody is putting back - and until now the program had no
    answer for it at all except "point the whole program at that folder", which
    is the wrong answer when there are already trees here.

    Copied, never moved: the folder somebody handed over is theirs, and a
    program that empties a stick while reading it is a program nobody hands a
    stick to twice.  Everything in the folder comes along, the portraits and
    the papers included - what arrives is meant to be the same tree, not a
    thinner version of it that has to be rebuilt before it can be looked at.

    A folder already lying in this data folder is only written down, not
    copied.  Otherwise pointing at a tree that is already here would quietly
    make a second copy of a family.
    """
    source = os.path.abspath(os.path.expandvars(os.path.expanduser(source or "")))
    if not looks_like_tree(source):
        raise ValueError("In diesem Ordner liegt kein Stammbaum (%s fehlt)." % TREE_FILE)

    title = title_in(source) or os.path.basename(source) or "Stammbaum"
    root = data_dir()

    if os.path.dirname(source) == os.path.abspath(root):
        # already here - find out whether it is known, and write it down if not
        name = os.path.basename(source)
        for slug, entry in registry().items():
            if (entry or {}).get("ordner") == name:
                return slug
        slug = free_slug(title)
        register(slug, name, title)
        return slug

    if inside(root, source):
        raise ValueError("Dieser Ordner enthält den Datenordner - das ginge im Kreis.")

    slug = free_slug(title)
    folder = free_folder(title, slug)
    shutil.copytree(source, os.path.join(root, folder))
    register(slug, folder, title)

    # Saved once, so the tree is complete rather than merely present.  What a
    # folder carries is whatever the version that wrote it knew about: a tree
    # from an older one, or a folder somebody assembled by hand, has no count
    # and no portrait tally, and the page then says "undefined Personen" over a
    # family that is perfectly fine.  This also writes the name list and the
    # overview beside it, which is what makes the folder readable.
    try:
        save(load(slug), slug)
    except (OSError, ValueError, KeyError, TypeError):
        pass                                   # present and openable is enough
    return slug


def adopt_all(source: str, only: list[str] | None = None) -> list[str]:
    """Take every tree in a folder in, or just the ones named in `only`.

    The folder somebody points at holds one family or several, and which it is
    should not change what they have to do.  `only` exists because the dialog
    lists what it found and lets them tick it off.
    """
    source = os.path.abspath(os.path.expandvars(os.path.expanduser(source or "")))
    names = holds_trees(source)
    if only:
        wanted = set(only)
        names = [name for name in names if name in wanted]
    if not names:
        raise ValueError("In diesem Ordner liegt kein Stammbaum.")
    return [adopt_folder(os.path.join(source, name)) for name in names]


# ----------------------------------------------------------------- migration
# --------------------------------------------------------------- moving house
# What counts as data, and where it used to sit relative to the program.  The
# left side is the old place, the right side the name it gets inside the data
# folder.  `None` means the name does not change.
MOVABLE = [
    ("data", "data"),
    ("source", "source"),
    ("Export", "Export"),
    ("Stammbaum.html", "Stammbaum.html"),
    (os.path.join("tools", "report.json"), "report.json"),
]

NOTE_FILE = "WO DIE DATEN LIEGEN.txt"
NOTE_TEXT = """Die Daten dieses Programms liegen nicht mehr hier.

Sie sind umgezogen nach:

    %s

Warum: Daten neben dem Programm sind Daten im Repository-Ordner, einen
unachtsamen Befehl davon entfernt, veroeffentlicht zu werden. Ausserhalb kann
das gar nicht erst passieren.

Wo das Programm sucht, steht oben in tools/store.py. Geaendert wird es im
Editor unter Stammbaeume, oder durch die Datei %s.
"""


def looks_like_tree(path: str) -> bool:
    return os.path.isfile(os.path.join(path, TREE_FILE))


def title_in(path: str) -> str:
    """What a tree folder calls itself, read without loading the whole tree.

    Wanted before the folder is anybody's: the dialog asking whether to take a
    folder in should say the family's name, not the folder's - and a folder
    handed over is named by whoever handed it over.
    """
    try:
        with open(os.path.join(path, TREE_FILE), encoding="utf-8") as fh:
            title = (json.load(fh).get("meta") or {}).get("title")
    except (OSError, ValueError):
        return ""
    return (title or "").strip()


def count_in(path: str) -> int:
    """How many people are in that folder's tree - for the same dialog."""
    try:
        with open(os.path.join(path, TREE_FILE), encoding="utf-8") as fh:
            return len(json.load(fh).get("people") or [])
    except (OSError, ValueError):
        return 0


def holds_trees(path: str) -> list[str]:
    """The tree folders directly inside `path`, whatever they are called."""
    if not os.path.isdir(path):
        return []
    out = []
    for name in sorted(os.listdir(path)):
        if name in (BIN_DIRNAME,):
            continue
        if looks_like_tree(os.path.join(path, name)):
            out.append(name)
    return out


def identify(path: str) -> dict:
    """Work out what folder somebody has just pointed at.

    Asking a person for "the data folder" asks them to know a distinction the
    program invented.  They know where their family is - and that might be the
    data folder, the `baeume` folder inside it, or one single tree.  All three
    are the same answer at different depths, and the program can see which is
    which: a tree has a `baum.json`, a folder of trees has folders that do,
    and the data folder has `einstellungen.json` or trees beside it.

    Returns what was recognised, and which folder the program should actually
    use.  Recognising costs nothing and is done before anything moves - the
    alternative is what happened on 07.09.2026, when a tree folder was given as
    the data folder and the program set about moving the data folder into
    itself, one entry at a time, until it hit the one it could not.

    `inhalt` says who is in each of them - the family's own name and how many
    people are in it.  Reading that costs one file per tree and is what lets
    the dialog say what somebody is about to take in before they take it in.
    A folder name says nothing: the point of finding trees by their `baum.json`
    is that the folder may be called whatever its owner called it.
    """
    path = os.path.abspath(os.path.expandvars(os.path.expanduser(path or "")))
    out = {"gefragt": path, "ordner": path, "art": "unbekannt",
           "baeume": [], "inhalt": [], "hinweis": ""}

    if not path or not os.path.isdir(path):
        out["art"] = "fehlt"
        out["hinweis"] = "Diesen Ordner gibt es nicht."
        return out

    def details(root: str, names: list[str]) -> list[dict]:
        return [{"ordner": name,
                 "titel": title_in(os.path.join(root, name)) or name,
                 "personen": count_in(os.path.join(root, name))}
                for name in names]

    # A single tree: the data folder is one or two levels up
    if looks_like_tree(path):
        eltern = os.path.dirname(path)
        grosseltern = os.path.dirname(eltern)
        wurzel = grosseltern if os.path.basename(eltern) == TREES_DIRNAME else eltern
        name = os.path.basename(path)
        out.update({"art": "baum", "ordner": wurzel,
                    "baeume": holds_trees(wurzel) or holds_trees(
                        os.path.join(wurzel, TREES_DIRNAME)),
                    "inhalt": details(os.path.dirname(path), [name]),
                    "hinweis": "Ein einzelner Stammbaum: %s mit %d Personen."
                               % (title_in(path) or name, count_in(path))})
        return out

    drin = holds_trees(path)

    # The `baeume` folder of the older arrangement
    if os.path.basename(path) == TREES_DIRNAME and drin:
        out.update({"art": "baeume", "ordner": os.path.dirname(path), "baeume": drin,
                    "inhalt": details(path, drin),
                    "hinweis": "Das ist der Ordner mit den Stammbäumen. Der"
                               " Datenordner ist der Ordner darüber."})
        return out

    # The data folder itself: trees beside it, or its settings file, or both
    hat_einstellungen = os.path.isfile(os.path.join(path, SETTINGS_FILE))
    alt = holds_trees(os.path.join(path, TREES_DIRNAME))
    if drin or alt or hat_einstellungen:
        out.update({"art": "daten", "ordner": path, "baeume": drin or alt,
                    "inhalt": details(path if drin else os.path.join(path, TREES_DIRNAME),
                                      drin or alt)})
        anzahl = len(drin or alt)
        out["hinweis"] = ("Datenordner mit %s."
                          % ("einem Stammbaum" if anzahl == 1
                             else "%d Stammbäumen" % anzahl)) if anzahl else \
            "Datenordner - er ist noch leer."
        return out

    out.update({"art": "leer",
                "hinweis": "Hier liegt noch kein Stammbaum. Der Ordner kann"
                           " trotzdem benutzt werden - er wird dann angelegt."})
    return out


def inside(child: str, parent: str) -> bool:
    """Is `child` the same folder as `parent`, or somewhere inside it?"""
    child = os.path.abspath(child)
    parent = os.path.abspath(parent)
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:                       # different drives on Windows
        return False


def move_data(target: str) -> list[str]:
    """Move everything that is data into `target`, and remember it is there.

    Two sources are swept, and both matter:

      1. the folder the data is in *now* - which is the whole point when
         somebody moves house a second time.  Sweeping only the program folder
         would move the pointer and leave the family behind.
      2. the places the data used to sit beside the program, for the one-time
         migration out of a repository folder.

    Moved rather than copied, and one entry at a time, so a failure halfway
    leaves the rest where the program can still find it.  Anything already
    present at the target is left alone: the point is never to overwrite one
    family's data with another's.
    """
    target = os.path.abspath(target)

    # Asked before anything moves, because the answer used to arrive halfway
    # through: on 07.09.2026 a tree folder was given as the destination, and
    # the program carried three entries into it before reaching the one that
    # contained the destination itself. Those three stayed where they had been
    # put, and the person was left with a half-moved data folder and a message
    # about directories.
    current_now = os.path.abspath(data_dir())
    if inside(target, current_now) and target != current_now:
        raise ValueError(
            "Dieser Ordner liegt im Datenordner selbst - dorthin kann er nicht "
            "umziehen. Gemeint war vermutlich der Ordner darüber: %s" % current_now)

    os.makedirs(target, exist_ok=True)
    moved: list[str] = []
    done: list[tuple[str, str]] = []          # (from, to) for putting back

    def carry(source: str, name: str) -> None:
        destination = os.path.join(target, name)
        if not os.path.exists(source) or os.path.exists(destination):
            return
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        done.append((destination, source))
        moved.append(name)

    def put_back() -> None:
        """Undo what this call moved, newest first.

        A move that stops halfway is worse than one that never started: the
        person cannot tell what is where any more, and neither can the program.
        """
        for came_to, came_from in reversed(done):
            try:
                if os.path.exists(came_to) and not os.path.exists(came_from):
                    os.makedirs(os.path.dirname(came_from), exist_ok=True)
                    shutil.move(came_to, came_from)
            except OSError:
                continue

    try:
        # 1 - wherever the data lives at this moment
        current = os.path.abspath(data_dir())
        if os.path.isdir(current) and current != target:
            for name in sorted(os.listdir(current)):
                carry(os.path.join(current, name), name)
            if not os.listdir(current):
                os.rmdir(current)

        # 2 - the old places beside the program, for the first move out of a repo
        old_root = os.path.join(program_dir(), FOLDER_NAME)
        if os.path.isdir(old_root) and os.path.abspath(old_root) != target:
            for name in sorted(os.listdir(old_root)):
                carry(os.path.join(old_root, name), name)
            if not os.listdir(old_root):
                os.rmdir(old_root)

        for old_name, new_name in MOVABLE:
            carry(os.path.join(program_dir(), old_name), new_name)
    except (OSError, shutil.Error) as err:
        put_back()
        raise ValueError(
            "Der Umzug ist abgebrochen und wurde zurückgenommen - es liegt "
            "alles wieder, wo es war. Grund: %s" % err) from err

    write_pointer(target)

    # A folder that suddenly has no data in it needs to say where it went -
    # otherwise the next person to look assumes something was lost.
    try:
        with open(os.path.join(program_dir(), NOTE_FILE), "w", encoding="utf-8") as fh:
            fh.write(NOTE_TEXT % (target, POINTER_FILE))
    except OSError:
        pass

    return moved


def lift_single_tree() -> None:
    """Move the one tree of the previous version into a folder of its own.

    That version kept `baum.json` straight in the data folder.  Finding it there
    means this program has been used before several trees existed, and the tree
    is carried across silently - there is nothing for anybody to decide.
    """
    root = data_dir()
    loose = os.path.join(root, TREE_FILE)
    if not os.path.isfile(loose):
        return
    try:
        with open(loose, encoding="utf-8") as fh:
            title = (json.load(fh).get("meta") or {}).get("title") or "Stammbaum"
    except (OSError, ValueError):
        title = "Stammbaum"

    slug = free_slug(title)
    target = os.path.join(trees_dir(), slug)
    os.makedirs(target, exist_ok=True)
    shutil.move(loose, os.path.join(target, TREE_FILE))
    for name in (PHOTO_DIRNAME, DOCS_DIRNAME, BACKUP_DIRNAME):
        old = os.path.join(root, name)
        if os.path.isdir(old):
            shutil.move(old, os.path.join(target, name))
    remember(offen=slug)


# ------------------------------------- giving every tree a folder of its own
def pending_move() -> dict | None:
    """What still lies in the old arrangement, and where it would go.

    Asked on every start and answered without touching anything: the editor
    shows this list and the move happens on a click, because it moves a
    family's portraits and papers and nobody should find that already done.

    Returns None when there is nothing to move.
    """
    root = data_dir()
    if not os.path.isdir(root):
        return None

    trees, loose = [], []

    old_root = trees_dir()
    if os.path.isdir(old_root):
        for name in sorted(os.listdir(old_root)):
            here = os.path.join(old_root, name)
            if name == BIN_DIRNAME or not os.path.isfile(os.path.join(here, TREE_FILE)):
                continue
            title, people = name, 0
            try:
                with open(os.path.join(here, TREE_FILE), encoding="utf-8") as fh:
                    tree = json.load(fh)
                title = (tree.get("meta") or {}).get("title") or name
                people = len(tree.get("people") or [])
            except (OSError, ValueError):
                pass
            trees.append({"slug": name, "titel": title, "personen": people,
                          "von": os.path.join(TREES_DIRNAME, name),
                          "nach": free_folder(title, name)})

    for name in LOOSE:
        if os.path.exists(os.path.join(root, name)):
            loose.append(name)

    # Nothing left in the old `baeume/`: the move has already happened, and
    # what still lies at the root is its remains.  Most of that is rebuilt on
    # the next save or the next export anyway, and offering to move it asks a
    # question with no answer - there is no tree it demonstrably belongs to.
    # Left unchecked this fired on every single start, listed no trees, moved
    # nothing when it was answered, and came back on the next start.
    if not trees:
        loose = [name for name in loose if name not in REBUILDABLE]

    if not trees and not loose:
        return None

    # The loose folders were built from one report and belong to one tree: the
    # one that is open. Said out loud rather than guessed at silently.
    # Which tree do the loose folders belong to?  They were built from one
    # report, so the answer is the tree that report produced - and that is the
    # one with people in it, not whichever happens to be open.  "Open" is a
    # setting that moves: on 07.09.2026 a failed move left it pointing at an
    # empty tree, and going by it would have carried a family's report and
    # portraits into a folder belonging to nobody.
    owner = None
    if loose and trees:
        with_people = sorted(trees, key=lambda t: -t["personen"])
        owner = with_people[0] if with_people[0]["personen"] else None
        if owner is None:
            open_now = settings().get("offen")
            owner = next((t for t in trees if t["slug"] == open_now), trees[0])
    elif loose:
        # The trees are already in folders of their own and something
        # irreplaceable is still lying loose - the report, the parse of it.  It
        # belongs to the tree that has the people in it; where that is not
        # obvious, it stays where it is rather than being guessed into a folder.
        candidates = [{"slug": slug, "titel": heading_title(slug),
                       "personen": count_in(tree_dir(slug, create=False)),
                       "nach": (registry().get(slug) or {}).get("ordner") or ""}
                      for slug in all_slugs()]
        candidates = [c for c in candidates if c["personen"] and c["nach"]]
        if len(candidates) == 1:
            owner = candidates[0]
        else:
            return None

    return {"baeume": trees, "lose": loose,
            "gehoeren_zu": owner["titel"] if owner else None,
            "ziel": owner["nach"] if owner else None}


def do_move() -> dict:
    """Carry out what `pending_move` described. Only ever called on a click."""
    plan = pending_move()
    if not plan:
        return {"verschoben": 0}

    root = data_dir()
    moved, failed = 0, []

    for tree in plan["baeume"]:
        source = os.path.join(root, tree["von"])
        target = os.path.join(root, tree["nach"])
        try:
            if os.path.exists(target):
                failed.append(tree["nach"] + " gibt es schon")
                continue
            shutil.move(source, target)
            register(tree["slug"], tree["nach"], tree["titel"])
            moved += 1
        except OSError as err:
            failed.append("%s: %s" % (tree["von"], err))

    if plan["ziel"]:
        target = os.path.join(root, plan["ziel"])
        os.makedirs(target, exist_ok=True)
        for name in plan["lose"]:
            source = os.path.join(root, name)
            try:
                if os.path.exists(os.path.join(target, name)):
                    failed.append(name + " liegt dort schon")
                    continue
                shutil.move(source, os.path.join(target, name))
                moved += 1
            except OSError as err:
                failed.append("%s: %s" % (name, err))

    # An empty `baeume/` left behind reads like something is still in there.
    old_root = trees_dir()
    try:
        if os.path.isdir(old_root) and not os.listdir(old_root):
            os.rmdir(old_root)
    except OSError:
        pass

    return {"verschoben": moved, "fehler": failed}


def tidy_old_layout() -> None:
    """Take the empty shell of the old arrangement away once it is empty.

    After every tree has a folder of its own, `baeume/` holds nothing but the
    bin the program stopped writing to - `discard` puts a removed tree straight
    into the data folder now.  An empty folder called `baeume` sitting beside
    the trees reads as though something were still in it, and is the first
    place somebody looks for a tree they cannot find.

    Only ever moves the bin, only when nothing else is in there, and quietly:
    tidying up is not worth an error message, and a locked folder is a reason
    to leave it alone rather than to complain.
    """
    old_root = trees_dir()
    if not os.path.isdir(old_root):
        return
    try:
        inside_it = os.listdir(old_root)
    except OSError:
        return
    if any(name != BIN_DIRNAME for name in inside_it):
        return                                   # trees still there: not our call

    old_bin = os.path.join(old_root, BIN_DIRNAME)
    if os.path.isdir(old_bin):
        new_bin = os.path.join(data_dir(), BIN_DIRNAME)
        try:
            os.makedirs(new_bin, exist_ok=True)
            for name in os.listdir(old_bin):
                target = os.path.join(new_bin, name)
                n, stem = 2, target
                while os.path.exists(target):
                    target = "%s (%d)" % (stem, n)
                    n += 1
                shutil.move(os.path.join(old_bin, name), target)
            os.rmdir(old_bin)
        except OSError:
            return
    try:
        os.rmdir(old_root)
    except OSError:
        pass


def old_layout() -> str | None:
    """The `data/` folder of the arrangement this replaces, if it is still there."""
    old = os.path.join(program_dir(), "data")
    return old if os.path.exists(os.path.join(old, "tree.json")) else None


def take_over(old: str) -> tuple[str, dict]:
    """Move a tree from the old arrangement into a folder of its own.

    The two files of the old arrangement - the parse of the report and the hand
    edits laid over it - are folded together once, here, and from then on there
    is one tree.  The overlay existed because `build_data.py` rewrote
    `tree.json` on every run; the program's own folder is not written by that
    pipeline at all, so the split has no job left to do.
    """
    tree, _ = person_lib.load_merged(old)
    title = (tree.get("meta") or {}).get("title") or "Übernommener Stammbaum"
    slug = create(title, tree)

    old_photos = os.path.join(old, "photos")
    if os.path.isdir(old_photos):
        target = photo_dir(slug)
        for name in os.listdir(old_photos):
            source = os.path.join(old_photos, name)
            if os.path.isfile(source) and not os.path.exists(os.path.join(target, name)):
                shutil.copy2(source, os.path.join(target, name))

    old_docs = os.path.join(old, "dokumente")
    if os.path.isdir(old_docs):
        for person in os.listdir(old_docs):
            source = os.path.join(old_docs, person)
            if not os.path.isdir(source):
                continue
            target = docs_dir(person, slug)
            for name in os.listdir(source):
                one = os.path.join(source, name)
                if os.path.isfile(one) and not os.path.exists(os.path.join(target, name)):
                    shutil.copy2(one, os.path.join(target, name))

    # Saved once more now that the portraits are actually in the folder: the
    # count in the heading is taken from what is there, and the first save
    # happened before any of them had been copied.
    save(tree, slug)
    remember(uebernommen_aus=old,
             uebernommen_am=datetime.datetime.now().isoformat(timespec="seconds"))
    return slug, tree
