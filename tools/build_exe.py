# -*- coding: utf-8 -*-
"""Turn the editor into `Stammbaum.exe`, a program to double click.

The point of this step is that nobody else in the family should have to install
Python, open a console or read a command.  The result is one file next to
`Stammbaum.html`; starting it opens the tree in a window of its own.

The exe is only the program: it carries the page template and nothing else, and
knows no family.  On first start it makes itself a `Stammbaum-Daten` folder
beside itself and keeps every tree in there.  So two files are enough to hand
somebody - this one, and a `.baum` file with a tree in it.

Needs PyInstaller:

    pip install pyinstaller
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, ".work", "pyinstaller")
ENTRY = os.path.join(HERE, "edit_server.py")
RESULT = os.path.join(ROOT, "Stammbaum.exe")

# Out of the page template, the one place the number is written down.  Windows
# shows it in the file properties, which is the only place an exe found again in
# five years can be asked what it is - and it has to agree with what the program
# says about itself when it runs.
sys.path.insert(0, HERE)
import build_site  # noqa: E402

VERSION = build_site.version()
VERSION_TUPLE = tuple(int(part) for part in
                      ([p for p in VERSION.split(".") if p.isdigit()] +
                       ["0", "0", "0", "0"])[:4])


def version_resource() -> str:
    """Write the version block PyInstaller stamps into the exe, return its path."""
    text = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)s, prodvers=%(t)s, mask=0x3f, flags=0x0,
                    OS=0x4, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable("040704b0", [
      StringStruct("FileDescription", "Stammbaum - Familienstammbaum ansehen und pflegen"),
      StringStruct("FileVersion", "%(v)s"),
      StringStruct("InternalName", "Stammbaum"),
      StringStruct("OriginalFilename", "Stammbaum.exe"),
      StringStruct("ProductName", "Stammbaum"),
      StringStruct("ProductVersion", "%(v)s"),
    ])]),
    VarFileInfo([VarStruct("Translation", [1031, 1200])]),
  ]
)
""" % {"t": VERSION_TUPLE, "v": VERSION}
    path = os.path.join(WORK, "version.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit("ABBRUCH: PyInstaller fehlt.  Bitte 'pip install pyinstaller' laufen lassen.")

    if os.path.exists(RESULT):
        os.remove(RESULT)
    os.makedirs(WORK, exist_ok=True)

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",            # one file, so there is nothing to unpack by hand
        "--noconsole",          # no black window behind the program
        "--name", "Stammbaum",
        "--version-file", version_resource(),
        "--distpath", ROOT,
        "--workpath", os.path.join(WORK, "bau"),
        "--specpath", WORK,
        # edits.py is pulled in at run time through sys.path, which PyInstaller
        # cannot see by reading the source - so it is named here by hand
        "--paths", HERE,
        "--hidden-import", "edits",
        # Pillow is only reached through build_site's photo resizing, and that
        # step never fires: portraits are already shrunk in the browser before
        # they are sent.  Leaving it out takes 18 MB off the program.
        # the page template travels inside the exe, so that a folder without
        # tools/ can still write an HTML export
        "--add-data", os.path.join(HERE, "template.html") + os.pathsep + ".",
        "--exclude-module", "PIL",
        "--exclude-module", "pymupdf",
        "--exclude-module", "fitz",
        ENTRY,
    ]
    print("PyInstaller laeuft - das dauert etwa eine Minute ...")
    done = subprocess.run(command, cwd=ROOT)
    if done.returncode != 0:
        raise SystemExit("ABBRUCH: PyInstaller ist ausgestiegen.")

    if not os.path.exists(RESULT):
        raise SystemExit("ABBRUCH: Stammbaum.exe wurde nicht geschrieben.")

    shutil.rmtree(os.path.join(WORK, "bau"), ignore_errors=True)
    size = os.path.getsize(RESULT) / (1024 * 1024)
    print()
    print("Fertig: Stammbaum.exe %s (%.1f MB)" % (VERSION, size))
    print("Doppelklick startet das Programm.  Es braucht nichts weiter neben sich:")
    print("beim ersten Start legt es sich den Ordner Stammbaum-Daten selbst an.")


if __name__ == "__main__":
    main()
