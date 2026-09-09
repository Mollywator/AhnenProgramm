# -*- coding: utf-8 -*-
"""A short, readable list of who is in which tree, and under which number.

Two jobs, and the second is the reason it exists at all.

The first is for people: everybody in a family tree has a number, and it is the
only thing that tells two people with the same name apart.  "In the family tree
I am number 13" is a sentence somebody should be able to say, so the
numbers are printed first and the list is ordered by them.

The second is for the backup.  The trees themselves are megabytes of JSON;
this is twenty kilobytes of text, and a `git diff` of it says in one screen who
was added, who was removed and who was renamed since the last time.  The heavy
files are kept as well, but reading them is not how anybody finds out what
changed.

Written on every save, so it is never one edit behind.
"""
from __future__ import annotations

import datetime
import io
import os

LIST_FILE = "Namensliste.txt"


def _lifespan(person: dict) -> str:
    def year(field: str) -> str:
        value = person.get(field)
        if isinstance(value, dict):
            return str(value.get("year") or "")
        return ""

    born, died = year("birth"), year("death")
    if born and died:
        return "*%s †%s" % (born, died)
    if born:
        return "*%s" % born
    if died:
        return "†%s" % died
    return ""


def _sortable(name: str) -> str:
    return (name or "").lower()


def write(store, slug: str | None = None, tree: dict | None = None) -> str:
    """Write the list of one tree, into that tree's own folder.

    One file per tree rather than one for all of them: the list belongs to a
    family the way the portraits do, and a folder handed to a relative should
    carry its own index rather than a list naming three other households.

    `tree` is the tree to describe.  `save` passes the one it has just written,
    and that is not an optimisation: reading it back from here is what let
    `save` reach itself.  Loading it is kept for a caller who has no tree in
    hand, and only for that.
    """
    slug = slug or store.open_slug()
    root = store.tree_dir(slug, create=False)
    path = os.path.join(root, LIST_FILE)

    lines: list[str] = []
    lines.append("Namensliste")
    lines.append("Stand %s" % datetime.datetime.now().strftime("%d.%m.%Y um %H:%M"))
    lines.append("")
    lines.append("Jede Person hat eine Nummer. Sie ist das Einzige, was zwei")
    lines.append("gleichnamige Menschen auseinanderhaelt - „im Stammbaum X bin")
    lines.append("ich Nummer 13“ ist damit eine eindeutige Angabe.")
    lines.append("")
    lines.append("Diese Datei wird bei jedem Speichern neu geschrieben.")
    lines.append("=" * 66)

    if tree is None:
        try:
            tree = store.load(slug)
        except Exception:                                   # noqa: BLE001
            return path
    meta = tree.get("meta") or {}
    people = tree.get("people") or []

    lines.append("")
    lines.append("")
    lines.append("%s   (Ordner: %s)" % (meta.get("title") or slug,
                                        os.path.basename(root)))
    lines.append("-" * 66)
    lines.append("%d Personen%s" % (
        len(people),
        "   zuletzt gespeichert %s" % str(meta.get("gespeichert") or "")[:16].replace("T", " ")
        if meta.get("gespeichert") else ""))
    if meta.get("source_author"):
        lines.append("Daten zusammengetragen von %s" % meta["source_author"])
    lines.append("")

    if not people:
        lines.append("   (noch niemand darin)")
    else:
        lines.append("   Nr.  Name                                        Lebensdaten")
        for person in sorted(people, key=lambda p: p.get("id") or 0):
            lines.append("  %4s  %-42s  %s" % (
                person.get("id", "?"),
                (person.get("name") or "ohne Namen")[:42],
                _lifespan(person)))

    # What has been built out of the trees, so the list also says what is there.
    lines.append("")
    lines.append("")
    lines.append("Gebaute Dateien")
    lines.append("-" * 66)
    for name in ("Stammbaum.html", os.path.join("data", "tree.json")):
        full = os.path.join(root, name)
        if os.path.isfile(full):
            size = os.path.getsize(full) / 1048576
            when = datetime.datetime.fromtimestamp(os.path.getmtime(full))
            lines.append("  %-24s %6.1f MB   %s"
                         % (name, size, when.strftime("%d.%m.%Y %H:%M")))
        else:
            lines.append("  %-24s  fehlt" % name)

    export = os.path.join(root, "Export")
    if os.path.isdir(export):
        files = sorted(f for f in os.listdir(export)
                       if os.path.isfile(os.path.join(export, f)))
        lines.append("")
        lines.append("  Export: %d Datei(en)" % len(files))
        for name in files:
            lines.append("    %s" % name)

    text = "\n".join(lines) + "\n"
    tmp = path + ".neu"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)

    uebersicht(store)
    return path


UEBERSICHT_FILE = "Stammbäume in diesem Ordner.txt"


def uebersicht(store) -> str:
    """One page saying what is in this data folder, for whoever opens it.

    The program does not need it: it finds the trees by looking for a
    `baum.json` in every folder, which is why the folders may be called
    anything and why a settings file that goes missing costs nothing.  A person
    opening the folder in five years has no such method, and `einstellungen.json`
    is not written for them.

    So this is written for them, and named the way they would ask the question.
    Rewritten on every save, like the per-tree list, and never worth losing a
    save over.
    """
    root = store.data_dir()
    path = os.path.join(root, UEBERSICHT_FILE)

    lines = ["Stammbäume in diesem Ordner",
             "Stand %s" % datetime.datetime.now().strftime("%d.%m.%Y um %H:%M"),
             "",
             "Jeder Ordner hier drin ist ein Stammbaum. Was ihn dazu macht,",
             "ist die baum.json darin - nicht sein Name. Der Ordner darf",
             "heissen, wie du willst, und darf auch woanders hin: dem Programm",
             "wird einmal gesagt, wo dieser Ordner liegt, und es findet alles",
             "Weitere von selbst.",
             "",
             "Diese Datei wird bei jedem Speichern neu geschrieben.",
             "=" * 66,
             ""]

    slugs = store.all_slugs()
    if not slugs:
        lines.append("")
        lines.append("   (noch kein Stammbaum darin)")
    for slug in slugs:
        ordner = store.tree_dir(slug, create=False)
        kopf = store.heading(slug)
        lines.append("")
        lines.append("%s" % (kopf.get("titel") or slug))
        lines.append("-" * 66)
        lines.append("  Ordner    %s" % os.path.basename(ordner))
        lines.append("  Personen  %d" % (kopf.get("personen") or 0))
        if kopf.get("fotos"):
            lines.append("  Portraits %d" % kopf["fotos"])
        if kopf.get("gespeichert"):
            lines.append("  Zuletzt   %s"
                         % str(kopf["gespeichert"])[:16].replace("T", " "))
        liste = os.path.join(ordner, LIST_FILE)
        if os.path.isfile(liste):
            lines.append("  Wer darin steht: %s\\%s"
                         % (os.path.basename(ordner), LIST_FILE))

    text = "\n".join(lines) + "\n"
    tmp = path + ".neu"
    try:
        with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except OSError:
        return ""
    return path
