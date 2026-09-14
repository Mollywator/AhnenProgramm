# Ahnenprogramm

**Version 1.8.0** · by Mollywator · MIT licence

Reads a genealogy report PDF and turns it into **one self-contained HTML page**
that works offline and can be passed around a family — plus a small Windows
program for keeping that page up to date.

The page loads nothing from the network. The data, the portraits and the manual
are all inside it, and the fonts are ones that ship with Windows and macOS.
Nobody who opens it phones anywhere.

## What you end up with

| | For | What it is |
|---|---|---|
| `Stammbaum.html` | the family | one file, a few megabytes. Double-click it, or attach it to an email as it is. Read only. |
| `Stammbaum.exe` | whoever keeps the tree | the same page in a window of its own, with the editing built in. |

The page carries its own manual in German — the **Anleitung** button — for the
relatives who get sent the file.

## Getting started

You need Python 3.11 or newer.

```sh
pip install pymupdf pillow          # reading the PDF, resizing portraits
python tools/edit_server.py         # start it once - it makes its data folder
```

The program prints where it put that folder, and the editor shows it under
**Stammbäume → Wo alles liegt**, where it can also be moved.

**Starting with an empty tree** is a perfectly good way in: enter one person and
build outwards — parents, marriage, children. Click a box in the diagram and
four **＋** appear on its edges: a parent above, a child below, a sibling to
either side. Relationships are worked out from that; nobody has to be told they
are somebody's cousin.

**Starting from a report** takes one more step. Copy
`tools/report.beispiel.json` into the tree's folder as `report.json`, fill it
in, put the PDF into that folder's `source/`, and run:

```sh
build.cmd
```

Three steps: read the PDF, build and check the data, write the page.

## Making the program a double-clickable window

Double click `Stammbaum bauen.bat`, or do the same by hand:

```sh
pip install pyinstaller
python tools/build_exe.py
```

That produces `Stammbaum.exe`, which needs no Python on the machine it runs on.
The exe is built out of the code lying next to it, so in a worktree it is that
branch's version, and it is written into that worktree rather than the main
folder.

## Where your things are kept

Not in this folder. The trees, the report, the portraits and the exports live in
a data folder of their own, so that nothing of a family is anywhere near the
program's own files. The program finds it in this order, first hit wins:

| | |
|---|---|
| `AHNEN_DATEN` | an environment variable, for scripts |
| `datenordner.txt` next to the program | a deliberate, portable setup — a memory stick |
| `datenordner.txt` in the user's app data | what the editor writes when you change it |
| `Stammbaum-Daten` next to the program | the default, when that can be written to |
| the user's app data | last resort, always works |

Inside it, **one folder per tree**, named after the family:

```
<data folder>/
  einstellungen.json                 which tree was open, and where each one lives
  Stammbäume in diesem Ordner.txt    the same thing, for whoever opens the folder
  SB_Hemken/                         one family, everything of it together
  SB_Rodenberg/
```

What makes a folder a tree is the `baum.json` in it, not its name — a folder
somebody hands over keeps whatever they called it. The settings file is a
convenience rather than a register: delete it and every tree is still found.

To move everything somewhere else — an external disk, a synced folder — use
**Stammbäume → Wo alles liegt** in the editor. *Umziehen* takes the trees along,
*Zeigen* leaves them and opens whatever is already at the new place.

## Bringing a tree in

**Importieren** takes either a file or a folder.

| What you have | What to give it | What happens |
|---|---|---|
| a `.baum` from this program, or a GEDCOM from any other | the file | read in as a tree of its own, or merged into the open one |
| a data folder from an earlier installation, another machine, a backup disk | the folder | *Dorthin zeigen* — nothing is copied, the program works there from now on and every tree in it is there at once |
| one family's folder, handed over on a stick | that one folder | *Hierher kopieren* — a copy joins the trees already here, the original is untouched, and the folders beside it are not even looked at |

Point at anything and the dialog says what it found — the families by name, and
how many people are in each — before a button is pressed.

## When something does not work

| What you see | What it usually is |
|---|---|
| **"Der Datenordner laesst sich nicht beschreiben"** on start | The folder is read-only, or it is on a drive that is not connected. Delete `datenordner.txt` to fall back to the default, or point it somewhere writable. |
| **The window opens empty**, no tree | Nothing has been entered yet, or the program is looking at a different data folder than you expect. It prints the path on start — check that first. |
| **`build.cmd` stops at step 1** | `pip install pymupdf pillow` has not run, or the PDF is not in the tree's `source/` folder. |
| **The page is missing people you just entered** | `build.cmd` builds from the *report*, on purpose. For the page as you keep it, run `python tools/build_site.py` with no arguments, or use **Exportieren** in the editor. |
| **"Foto fehlt" while exporting** | A portrait a person points at is not in the tree's `fotos/` folder. Open that person and attach the picture again. |
| **The parser got something wrong** | `data/validation-report.txt` inside the tree's folder lists everything that did not add up. It is the first place to look. |
| **The exported PDF is empty or missing** | The export drives Edge to print. `Export/Druck-Protokoll.txt` records what Edge said. |

Nothing the program does is destructive: every save keeps the previous twenty in
the tree's `sicherung/` folder, and removing a tree moves it to `_geloescht/`
rather than deleting it.

## Nobody in the middle

The page opens on **no one**. A family has no natural middle, and writing one
into the file would put that person in front of every reader, on every open.

A fresh page shows the whole tree, nothing marked, everyone drawn alike. A
centre appears when a reader picks one: clicking a box does it for a look
around, **Das bin ich** in the person sheet does it for good. In the file handed
to the family that choice lives in the reader's own browser and travels nowhere.

## Privacy

A finished page contains photographs, birth dates and addresses of living
people, including children. It is meant for one family.

**Do not put it on a public web server.** Hand it over the way you would hand
over a photo album — to people, not to an address anybody can type in.

## Licence

MIT — see [`LICENSE`](LICENSE).
