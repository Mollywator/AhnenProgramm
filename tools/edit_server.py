# -*- coding: utf-8 -*-
"""The editing program: a window, and a back end that may write to disk.

`Stammbaum.html` is meant to be opened by double click and mailed around, which
means it runs from `file://` - and a page loaded that way is not allowed to
write anything.  So the editor is the same page with a small local back end
behind it: this script serves the file over `127.0.0.1`, opens it in a window
of its own without an address bar, and shuts everything down again when that
window is closed.

It writes nothing into the project: everything lives in the program's own data
folder, one folder per tree, and `store.py` is the only thing that touches it.
The page itself is rendered here from whichever tree is open rather than read
off the disk, through the same `page_html` the pipeline uses for the copy handed
to the family - so the two can never drift apart.

Built into `Stammbaum.exe` by `build_exe.py`; `tools/Editor ohne exe starten.cmd`
does the same wherever Python is installed.
"""
from __future__ import annotations

import base64
import http.server
import json
import mimetypes
import os
import re
import secrets
import select
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baum as baum_lib  # noqa: E402
import build_site  # noqa: E402
import gedcom  # noqa: E402
import edits as person_lib  # noqa: E402
import export as export_lib  # noqa: E402
import format as schema  # noqa: E402  - "format" is a builtin, hence the rename
import store  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# Kept in step with VERSION in tools/template.html and build_exe.py.  Shown in
# the options, and named in the message a tree from a newer program produces.
VERSION = "1.0"
# Where a newer version would come from.  The program itself never asks it
# anything - it hands the address to the browser and stops there.  See the
# options dialog for why that line is where it is.
REPO_URL = "https://github.com/Mollywator/AhnenProgramm"
# As a script the program folder is one above tools/; as a built exe it is the
# folder the exe itself sits in, next to Stammbaum.html and data/.
ROOT = (os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, "frozen", False) else os.path.dirname(HERE))
# Exports carry the whole tree, so they belong with the data, not beside the
# program.  Resolved on each use rather than once, because the folder can be
# moved while the program is running.
def export_dir() -> str:
    return store.export_dir()

# A scan of a certificate is the biggest thing anybody will hand this, and the
# body arrives base64 encoded, so the ceiling is generous rather than tight.
MAX_UPLOAD = 40 * 1024 * 1024

TOKEN = secrets.token_urlsafe(18)

# How the program knows it is still wanted.  Not a timer: the page holds an
# open connection, and the operating system tells us the moment it goes away.
# A timer was the first attempt and was wrong - browsers slow timers down to
# once a minute in windows that have been in the background for a while, so
# working in another window shut the program down underneath its own window.
FIRST_CALL_WITHIN = 120      # the window has this long to show up at all
GONE_FOR = 6                 # no connection for this long: nobody is looking
KEEPALIVE_EVERY = 20         # a blank line down the wire, for a peer that vanished

WATCHERS = 0                 # how many windows are holding the line open
WATCHER_LOCK = threading.Lock()
LAST_SEEN = 0.0              # when the last one let go
SEEN_ANYTHING = False

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# A file name has to survive being put straight into a path, so anything that
# could climb out of the folder is replaced rather than rejected - a rejection
# in the middle of filing twenty scans is far more annoying than a renamed file.
SAFE_NAME = re.compile(r"[^A-Za-z0-9._ äöüÄÖÜß+-]")


def safe_name(name: str, fallback: str = "datei") -> str:
    name = os.path.basename(name or "").strip()
    name = SAFE_NAME.sub("_", name).lstrip(".")
    return name or fallback


def free_name(folder: str, name: str) -> str:
    """Never overwrite: a second `Urkunde.pdf` becomes `Urkunde (2).pdf`."""
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while os.path.exists(os.path.join(folder, candidate)):
        n += 1
        candidate = "%s (%d)%s" % (stem, n, ext)
    return candidate


def pick_folder(start: str = "") -> str:
    """Ask Windows for a folder and hand back the path, or "" if cancelled.

    Wanted because the page cannot ask: a file picker in a browser hands over
    bytes and withholds the path, and a folder has no bytes to hand over at
    all.  This process is on the machine the folder is on, so it can ask.

    Through the shell's own dialog rather than tkinter: tkinter would work in
    four lines and put roughly ten megabytes of GUI toolkit into a program
    whose whole point is that it is one file somebody double clicks.  The
    dependency rule in CLAUDE.md is what decided it.

    Returns "" wherever the answer is "no folder", including on a system with
    no shell to ask - the typed field beside the button covers that case, and
    an import dialog is not the place to explain an operating system.
    """
    if sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes

    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [("hwndOwner", wintypes.HWND),
                    ("pidlRoot", ctypes.c_void_p),
                    ("pszDisplayName", wintypes.LPWSTR),
                    ("lpszTitle", wintypes.LPCWSTR),
                    ("ulFlags", wintypes.UINT),
                    ("lpfn", ctypes.c_void_p),
                    ("lParam", wintypes.LPARAM),
                    ("iImage", ctypes.c_int)]

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    user32 = ctypes.windll.user32
    # ctypes returns a C int unless told otherwise, and a window handle is a
    # pointer: on 64 bit the top half is cut off and what is left is not a
    # window.  The dialog then refuses to open and says nothing about why.
    user32.GetForegroundWindow.restype = wintypes.HWND
    # The new-style dialog is a COM control and refuses to appear without an
    # apartment; the older one would come up regardless and look it.
    ole32.CoInitialize(None)
    try:
        name = ctypes.create_unicode_buffer(260)
        info = BROWSEINFOW()
        # The window in front belongs to the browser showing the editor, which
        # is a different process - owning the dialog to it is what keeps it
        # from opening behind the page somebody just clicked in.
        #
        # The price is worth knowing: an owned dialog is modal to its owner, so
        # whatever is in front when this runs cannot be typed in until the
        # dialog is answered. Through the editor that window is always the page
        # the button was clicked on, which is what should be blocked. Called any
        # other way it will lock whatever happens to be in front - found out by
        # calling this from a script while something else had focus.
        info.hwndOwner = user32.GetForegroundWindow()
        info.pszDisplayName = ctypes.cast(name, wintypes.LPWSTR)
        info.lpszTitle = "Ordner mit dem Stammbaum wählen"
        # NEWDIALOGSTYLE: resizable, with a "new folder" button.
        # EDITBOX: a line to paste a path into, which is how a path arrives
        # from an Explorer address bar.
        # RETURNONLYFSDIRS: no printers and no control panel.
        info.ulFlags = 0x00000040 | 0x00000010 | 0x00000001
        shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
        if not pidl:
            return ""
        path = ctypes.create_unicode_buffer(1024)
        shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
        got = shell32.SHGetPathFromIDListW(pidl, path)
        ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        return path.value if got else ""
    finally:
        ole32.CoUninitialize()


# The rendered page, kept until the tree changes.  Building it means base64
# encoding every portrait, which is a second or so - fine once, silly on every
# reload while somebody is working.
PAGE_CACHE: dict = {"stamp": None, "html": None}


def zu_neu_seite(err: store.ZuNeu) -> str:
    """A page of its own for a tree this version must not touch.

    Its own page rather than a message inside the editor, because the editor is
    built around a tree it has just read - and there is none.  Saying it plainly
    on an empty page is also the honest shape of the situation: there is exactly
    one thing to do, and it is not in this program.
    """
    import html as _html
    titel = _html.escape(err.titel or "Dieser Stammbaum")
    return """<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Programm ist zu alt</title>
<style>
 body{margin:0;background:#f4f1ea;color:#2b2724;
      font:16px/1.6 "Segoe UI",system-ui,sans-serif;
      display:flex;min-height:100vh;align-items:center;justify-content:center}
 main{max-width:34em;padding:34px 38px;background:#fbf9f4;border:1px solid #ddd6c8}
 h1{font-size:22px;margin:0 0 6px;font-weight:600}
 .k{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8a8377}
 p{margin:14px 0}
 table{border-collapse:collapse;margin:18px 0;font-size:15px}
 td{padding:3px 18px 3px 0}
 td:first-child{color:#8a8377}
 a{color:#8a3b2e}
 .rand{margin-top:22px;padding-top:16px;border-top:1px solid #e4ddd0;
       font-size:14px;color:#6d675e}
</style></head><body><main>
 <div class="k">Achtung</div>
 <h1>Das Programm ist zu alt für diesen Stammbaum</h1>
 <p><b>%s</b> wurde mit einer neueren Fassung gespeichert. Diese hier kennt die
    neuen Felder nicht &ndash; sie würde die Familie zwar anzeigen, aber beim
    ersten Speichern alles wegwerfen, was sie nicht versteht. Deshalb wird der
    Stammbaum gar nicht erst geöffnet.</p>
 <table>
  <tr><td>Der Stammbaum ist in</td><td>Format %d</td></tr>
  <tr><td>Dieses Programm kann</td><td>Format %d</td></tr>
 </table>
 <p>Was hilft: die neuere Fassung des Programms holen.</p>
 <p><a href="%s/releases" target="_blank" rel="noopener">%s/releases</a></p>
 <div class="rand">An den Daten ist nichts kaputt und es wurde nichts
   verändert. Dieses Fenster kann einfach geschlossen werden.</div>
</main></body></html>""" % (titel, err.hat, err.kann, REPO_URL, REPO_URL)


def read_state(tree: dict) -> dict:
    """What the page needs to know about the program behind it."""
    return {
        "token": TOKEN,
        "nextId": store.next_id(tree),
        "firstNewId": person_lib.FIRST_NEW_ID,
        "extraFields": list(person_lib.EXTRA_FIELDS),
        "datenordner": store.data_dir(),
        "datenordner_grund": store.where_from(),
        "leer": not tree.get("people"),
        "uebernehmbar": store.old_layout(),
        "umzug": store.pending_move(),
        "ordner": os.path.basename(store.tree_dir(create=False)),
        "gespeichert": (tree.get("meta") or {}).get("gespeichert"),
        "offen": store.open_slug(),
        "baeume": store.listing(),
        "programmversion": VERSION,
        "format": schema.FORMAT,
        "repo": REPO_URL,
        "umgewandelt": (tree.get("meta") or {}).get("umgewandelt"),
    }


def current_tree() -> dict:
    return store.load()


def render_page(tree: dict) -> str:
    """The page with this tree in it, cached until the tree is written again.

    The cache is keyed by which tree as well as when: switching between two
    families must not hand back the one that was drawn a moment ago.
    """
    slug = store.open_slug()
    # The template counts as part of the stamp so that editing the page and
    # reloading shows the change - otherwise the cache would sit on the old one
    # until somebody happened to save a person.
    template = build_site.template_path()
    stamp = (slug,
             os.path.getmtime(store.tree_path(slug)) if store.has_tree(slug) else None,
             os.path.getmtime(template) if os.path.exists(template) else None)
    if PAGE_CACHE["stamp"] == stamp and PAGE_CACHE["html"]:
        return PAGE_CACHE["html"]
    html = build_site.page_html(tree, store.photo_dir(slug, create=False))
    PAGE_CACHE["stamp"], PAGE_CACHE["html"] = stamp, html
    return html


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Stammbaum/1.0"

    # ------------------------------------------------------------- plumbing
    def log_message(self, fmt, *args):  # noqa: A003 - quiet by design
        pass

    def send_json(self, payload: dict, status: int = 200) -> None:
        blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def send_blob(self, blob: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def fail(self, status: int, message: str) -> None:
        self.send_json({"ok": False, "fehler": message}, status)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD * 2:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def authorised(self, query: dict) -> bool:
        """Only this window may write.

        The server listens on the loopback address, so nothing off the machine
        can reach it, but another page open in the same browser could still
        fire a POST at it.  The token is handed to the page in its own markup
        and never leaves the machine.
        """
        given = (query.get("k") or [None])[0] or self.headers.get("X-Stammbaum-Token")
        return secrets.compare_digest(str(given or ""), TOKEN)

    # ------------------------------------------------------------------ GET
    def do_GET(self):  # noqa: N802
        global LAST_SEEN, SEEN_ANYTHING
        parsed = urllib.parse.urlparse(self.path)
        route = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            LAST_SEEN, SEEN_ANYTHING = time.time(), True
            return self.serve_page()
        if route == "/api/alive":
            if not self.authorised(query):
                return self.fail(403, "Kein Zugang")
            LAST_SEEN, SEEN_ANYTHING = time.time(), True
            return self.send_json({"ok": True})
        if route == "/api/anwesend":
            if not self.authorised(query):
                return self.fail(403, "Kein Zugang")
            return self.hold_open()
        if route == "/api/ping":
            return self.send_json({"ok": True})
        if route == "/api/state":
            if not self.authorised(query):
                return self.fail(403, "Kein Zugang")
            return self.send_json({"ok": True, **read_state(current_tree())})
        if route.startswith("/foto/"):
            return self.serve_file(store.photo_dir(), route[len("/foto/"):])
        if route.startswith("/datei/"):
            rest = route[len("/datei/"):].split("/", 1)
            if len(rest) != 2:
                return self.fail(404, "Nicht gefunden")
            return self.serve_file(store.docs_dir(safe_name(rest[0], "0")), rest[1])
        return self.fail(404, "Nicht gefunden")

    def hold_open(self) -> None:
        """Keep a connection open for as long as the window is there.

        Nothing is sent down it that matters - a blank comment line now and
        then, only so that a peer that went away without saying so is noticed
        when the write fails.  What counts is that the connection exists.
        """
        global WATCHERS, LAST_SEEN, SEEN_ANYTHING
        with WATCHER_LOCK:
            WATCHERS += 1
            SEEN_ANYTHING = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b": da\n\n")
            self.wfile.flush()
            waited = 0
            while True:
                # Waiting on the socket rather than on a clock: a closed window
                # makes it readable at end of stream, and that is noticed as it
                # happens instead of at the next write.
                ready, _, _ = select.select([self.connection], [], [], 1.0)
                if ready and not self.connection.recv(1, socket.MSG_PEEK):
                    break                              # the window is gone
                waited += 1
                if waited >= KEEPALIVE_EVERY:
                    waited = 0
                    self.wfile.write(b": da\n\n")
                    self.wfile.flush()
        except Exception:                              # noqa: BLE001
            pass                                       # the window is gone
        finally:
            with WATCHER_LOCK:
                WATCHERS -= 1
                LAST_SEEN = time.time()

    def serve_page(self) -> None:
        """Build the page out of whatever tree is open, and say it may be edited.

        The same `page_html` the pipeline uses for the file handed to the
        family, so the two can never drift apart.  The editing flag goes into
        the head: the page's own script reads it while setting itself up, so it
        may not arrive afterwards.
        """
        try:
            tree = current_tree()
        except store.ZuNeu as err:
            return self.send_blob(zu_neu_seite(err).encode("utf-8"),
                                  "text/html; charset=utf-8")
        html = render_page(tree)
        boot = ("<script>window.STAMMBAUM_EDIT=" +
                json.dumps(read_state(tree), ensure_ascii=False) + ";</script>")
        html = html.replace("</head>", boot + "</head>", 1)
        self.send_blob(html.encode("utf-8"), "text/html; charset=utf-8")

    def serve_file(self, folder: str, name: str) -> None:
        name = safe_name(urllib.parse.unquote(name))
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            return self.fail(404, "Datei nicht gefunden")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            self.send_blob(fh.read(), ctype)

    # ----------------------------------------------------------------- POST
    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = urllib.parse.unquote(parsed.path)
        if not self.authorised(urllib.parse.parse_qs(parsed.query)):
            return self.fail(403, "Kein Zugang")
        try:
            if route == "/api/save":
                return self.api_save()
            if route == "/api/upload":
                return self.api_upload()
            if route == "/api/remove-file":
                return self.api_remove_file()
            if route == "/api/export":
                return self.api_export()
            if route == "/api/new":
                return self.api_new()
            if route == "/api/take-over":
                return self.api_take_over()
            if route == "/api/import":
                return self.api_import()
            if route == "/api/import-folder":
                return self.api_import_folder()
            if route == "/api/waehle-ordner":
                return self.api_pick_folder()
            if route == "/api/open-tree":
                return self.api_open_tree()
            if route == "/api/rename-tree":
                return self.api_rename_tree()
            if route == "/api/discard-tree":
                return self.api_discard_tree()
            if route == "/api/set-root":
                return self.api_set_root()
            if route == "/api/set-data-dir":
                return self.api_set_data_dir()
            if route == "/api/pruefen":
                return self.api_pruefen()
            if route == "/api/umziehen":
                return self.api_umziehen()
            if route == "/api/open-folder":
                return self.api_open_folder()
            if route == "/api/updates":
                return self.api_updates()
            if route == "/api/quit":
                self.send_json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if route == "/api/bye":
                # A goodbye is only a hint - a reload fires it too, and a second
                # window may still be open.  The held connections decide.
                return self.send_json({"ok": True})
        except Exception as err:                      # noqa: BLE001
            return self.fail(500, "%s: %s" % (type(err).__name__, err))
        return self.fail(404, "Nicht gefunden")

    def api_save(self) -> None:
        """Write the records the editor sends into the tree.

        The editor always sends whole person records, and it sends every person
        whose links changed alongside the one being edited - so a save is never
        half a relationship.  `store.save` sorts the links out afterwards and
        keeps the previous tree.
        """
        payload = self.body()
        people = payload.get("people") or {}
        if not isinstance(people, dict):
            return self.fail(400, "Ungueltige Daten")

        tree = current_tree()
        by_id = {p["id"]: p for p in tree["people"]}

        for key, record in people.items():
            pid = int(key)
            record = person_lib.fill_missing({**record, "id": pid})
            if pid in by_id:
                by_id[pid].update(record)
            else:
                tree["people"].append(record)
                by_id[pid] = record

        for raw in payload.get("removed") or []:
            pid = int(raw)
            tree["people"] = [p for p in tree["people"] if p["id"] != pid]
            tree["marriages"] = [m for m in tree.get("marriages") or []
                                 if pid not in [int(x) for x in m.get("people", [])]]
            by_id.pop(pid, None)

        # Deliberately no automatic centre here.  An empty tree that quietly
        # adopts its first person makes that person the middle of the family
        # for good, which is exactly what this program stopped doing.

        store.save(tree)
        self.send_json({"ok": True, "saved": tree["meta"].get("gespeichert"),
                        "nextId": store.next_id(tree),
                        "count": len(tree["people"])})

    def api_set_root(self) -> None:
        """Remember which person the owner of this file counts as themselves.

        This is the editor's own setting and it stays here: the HTML that is
        handed around the family ignores `meta.root` and lets every reader pick
        their own place in the tree, in their own browser.  Sending null clears
        it, and the tree opens with nobody in the middle again.
        """
        raw = self.body().get("id")
        tree = current_tree()
        if raw is None:
            tree["meta"]["root"] = None
        else:
            try:
                pid = int(raw)
            except (TypeError, ValueError):
                return self.fail(400, "Keine gueltige Person")
            if not any(p["id"] == pid for p in tree["people"]):
                return self.fail(404, "Diese Person gibt es nicht.")
            tree["meta"]["root"] = pid
        store.save(tree)
        self.send_json({"ok": True, "root": tree["meta"]["root"]})

    def api_set_data_dir(self) -> None:
        """Point the program at another folder, and optionally take the data along.

        Two different wishes hide behind one dialog, so they are asked apart:
        *move* is for somebody tidying up, and carries the trees to the new
        place; *use what is there* is for somebody pointing a second machine at
        a folder that already holds a family.  Guessing between them would
        eventually overwrite one family's data with another's.
        """
        payload = self.body()
        wanted = (payload.get("pfad") or "").strip()
        if not wanted:
            return self.fail(400, "Ohne Pfad geht es nicht.")

        target = os.path.abspath(os.path.expandvars(os.path.expanduser(wanted)))
        if os.path.isfile(target):
            return self.fail(400, "Das ist eine Datei, kein Ordner.")

        # What has actually been pointed at?  Somebody who knows where their
        # family is should not have to know which of three nested folders the
        # program calls the data folder - it can see that itself.
        was = store.identify(target)
        if was["art"] in ("baum", "baeume"):
            target = was["ordner"]
        elif was["art"] == "fehlt":
            return self.fail(400, "Diesen Ordner gibt es nicht: " + target)

        if not store.writable(target):
            return self.fail(400, "Dorthin kann nicht geschrieben werden: " + target)
        if os.path.abspath(store.data_dir()) == target:
            return self.send_json({"ok": True, "ordner": target, "verschoben": [],
                                   "erkannt": was})

        try:
            if payload.get("verschieben"):
                moved = store.move_data(target)
            else:
                store.write_pointer(target)
                moved = []
        except ValueError as err:
            return self.fail(400, str(err))
        self.send_json({"ok": True, "ordner": target, "verschoben": moved,
                        "erkannt": was})

    def api_pruefen(self) -> None:
        """Say what a folder is, without touching anything.

        Called while the person is still typing, so the dialog can say "data
        folder with three trees" before they press anything at all.
        """
        wanted = (self.body().get("pfad") or "").strip()
        self.send_json({"ok": True, "erkannt": store.identify(wanted)})

    def api_new(self) -> None:
        """Start an empty tree - what another family sees on their first day."""
        title = (self.body().get("titel") or "").strip() or "Neuer Stammbaum"
        slug = store.create(title)
        self.send_json({"ok": True, "offen": slug})

    def api_open_tree(self) -> None:
        """Switch to another tree that is already in the folder."""
        slug = (self.body().get("slug") or "").strip()
        if slug not in store.all_slugs():
            return self.fail(404, "Diesen Stammbaum gibt es nicht.")
        store.set_open(slug)
        self.send_json({"ok": True, "offen": slug})

    def api_rename_tree(self) -> None:
        """Name and origin of a tree - the two lines a person fills in."""
        payload = self.body()
        slug = (payload.get("slug") or "").strip() or store.open_slug()
        title = (payload.get("titel") or "").strip()
        author = payload.get("autor")
        if not title:
            return self.fail(400, "Ohne Namen geht es nicht.")
        if slug not in store.all_slugs():
            return self.fail(404, "Diesen Stammbaum gibt es nicht.")
        store.describe(slug, title=title,
                       author="" if author is None else str(author))
        self.send_json({"ok": True})

    def api_discard_tree(self) -> None:
        slug = (self.body().get("slug") or "").strip()
        try:
            where = store.discard(slug)
        except ValueError as err:
            return self.fail(404, str(err))
        self.send_json({"ok": True, "verschoben_nach": where,
                        "offen": store.open_slug()})

    def api_take_over(self) -> None:
        """Take a tree out of the arrangement this program replaces."""
        old = store.old_layout()
        if not old:
            return self.fail(400, "Es liegt kein alter Datenordner neben dem Programm.")
        slug, tree = store.take_over(old)
        self.send_json({"ok": True, "offen": slug, "personen": len(tree["people"])})

    def api_import(self) -> None:
        """Read a tree somebody sent, either instead of or beside this one.

        Two ways in: this program's own `.baum`, and GEDCOM, which is what
        every other genealogy program speaks.  Which one it is comes from the
        file, not from the name.
        """
        payload = self.body()
        name = safe_name(payload.get("name"), "import")
        blob = payload.get("data") or ""
        # "neu" is the ordinary case now: a tree that arrives becomes a tree of
        # its own, and is simply there afterwards.  Merging is the deliberate
        # step of putting two families into one.
        mode = payload.get("modus") or "neu"
        try:
            raw = base64.b64decode(blob, validate=True)
        except Exception:                              # noqa: BLE001
            return self.fail(400, "Die Datei konnte nicht gelesen werden.")
        if not raw:
            return self.fail(400, "Die Datei ist leer.")

        # A tree of its own needs its folder before the file is unpacked, because
        # the portraits inside it are copied straight into that folder.
        title = (payload.get("titel") or "").strip() or os.path.splitext(name)[0]
        target_slug = store.open_slug()
        if mode == "neu":
            target_slug = store.create(title)

        try:
            with tempfile.TemporaryDirectory(prefix="stammbaum-import-") as work:
                path = os.path.join(work, name)
                with open(path, "wb") as fh:
                    fh.write(raw)
                try:
                    if zipfile.is_zipfile(path):
                        incoming = baum_lib.read(path)
                        art = "Stammbaum-Datei"
                    else:
                        incoming = gedcom.read_file(path)
                        art = "GEDCOM"
                except Exception as err:               # noqa: BLE001
                    raise ValueError("Die Datei liess sich nicht einlesen: %s" % err)

            if not incoming.get("people"):
                raise ValueError("In der Datei steht keine einzige Person.")
        except ValueError as err:
            if mode == "neu":
                store.discard(target_slug)             # do not leave an empty one behind
            return self.fail(400, str(err))

        twins: list = []
        if mode == "neu":
            merged = incoming
            merged.setdefault("meta", {})["title"] = title
        else:
            here = current_tree()
            if mode == "dazu" and here.get("people"):
                merged, twins = baum_lib.merge(here, incoming)
            else:
                merged = incoming
            # A tree is only renamed where somebody renames it.  Reading a file
            # into an existing tree would otherwise quietly relabel it with
            # whatever the file was called - and the name on the folder was
            # chosen on purpose.
            kept = (here.get("meta") or {}).get("title")
            if kept:
                merged.setdefault("meta", {})["title"] = kept
        store.save(merged, target_slug)
        store.set_open(target_slug)

        self.send_json({"ok": True, "art": art, "modus": mode, "offen": target_slug,
                        "titel": (merged.get("meta") or {}).get("title"),
                        "gelesen": len(incoming["people"]),
                        "gesamt": len(merged["people"]),
                        "doppelverdaechtig": twins[:40],
                        "doppelt": len(twins)})

    def api_import_folder(self) -> None:
        """Read a folder rather than a file - the other half of importing.

        Three things somebody can be holding, and the difference matters
        enough that it is asked rather than guessed:

        *zeigen* is putting an installation back.  The trees are already in a
        folder somewhere and nothing should be copied anywhere - the program
        is simply told to work there from now on.  Nothing is written except
        the note saying where to look.

        *kopieren* is somebody handing over their family.  The folder stays
        theirs and untouched; what arrives here is a copy, beside the trees
        that are already here rather than instead of them.

        Which trees, finally, is `nur`: pointing at one tree folder takes that
        one and does not go looking at its neighbours, which is the whole
        difference between "here is my family" and "here is my data folder".
        """
        payload = self.body()
        wanted = (payload.get("pfad") or "").strip()
        mode = (payload.get("modus") or "kopieren").strip()
        if not wanted:
            return self.fail(400, "Ohne Ordner geht es nicht.")

        was = store.identify(wanted)
        if was["art"] == "fehlt":
            return self.fail(400, "Diesen Ordner gibt es nicht: " + was["gefragt"])
        if was["art"] == "leer":
            return self.fail(400, "In diesem Ordner liegt kein Stammbaum.")

        if mode == "zeigen":
            # The folder to point at is the one holding the trees, not the tree
            # itself - that distinction is `identify`'s whole job.
            target = was["ordner"]
            if not store.writable(target):
                return self.fail(400, "Dorthin kann nicht geschrieben werden: " + target)
            store.write_pointer(target)
            return self.send_json({"ok": True, "modus": mode, "ordner": target,
                                   "erkannt": was, "gefunden": len(was["baeume"])})

        only = payload.get("nur") or None
        try:
            if was["art"] == "baum":
                slugs = [store.adopt_folder(was["gefragt"])]
            else:
                where = was["gefragt"]
                if not store.holds_trees(where):
                    where = os.path.join(where, store.TREES_DIRNAME)
                slugs = store.adopt_all(where, only)
        except (ValueError, OSError) as err:
            return self.fail(400, "Nicht übernommen: %s" % err)

        if slugs:
            store.set_open(slugs[0])
        self.send_json({"ok": True, "modus": mode, "erkannt": was,
                        "offen": store.open_slug(),
                        "uebernommen": [{"slug": s, "titel": store.heading_title(s),
                                         "personen": store.heading(s)["personen"]}
                                        for s in slugs]})

    def api_pick_folder(self) -> None:
        """Let Windows ask the question, so nobody has to copy a path by hand.

        The page cannot do this: a browser hands over a file's bytes and never
        its path, and a folder has no bytes at all.  The server can, because it
        is running on the machine the folder is on.

        Done with the shell's own dialog through ctypes rather than tkinter,
        which would put ten megabytes of GUI toolkit into the exe for one
        question.  The typed field stays either way - this only saves the trip
        through the address bar.
        """
        start = (self.body().get("start") or "").strip()
        try:
            picked = pick_folder(start)
        except Exception as err:                       # noqa: BLE001
            return self.fail(500, "Der Ordner-Dialog liess sich nicht öffnen: %s" % err)
        self.send_json({"ok": True, "pfad": picked,
                        "erkannt": store.identify(picked) if picked else None})

    def api_umziehen(self) -> None:
        """Give every tree a folder of its own, on a click and not before.

        The plan was shown to the person before they pressed this: it moves a
        family's portraits and papers, and finding that already done on start
        is not a pleasant surprise, however correct the result.
        """
        plan = store.pending_move()
        if not plan:
            return self.fail(400, "Es liegt nichts mehr in der alten Ablage.")
        out = store.do_move()
        if out.get("fehler"):
            return self.fail(500, "Teilweise umgezogen (%d), gescheitert: %s"
                             % (out["verschoben"], "; ".join(out["fehler"][:4])))
        self.send_json({"ok": True, "verschoben": out["verschoben"],
                        "ordner": os.path.basename(store.tree_dir(create=False))})

    def api_upload(self) -> None:
        """Store one portrait or one document, sent as base64 in the body."""
        payload = self.body()
        kind = payload.get("kind")
        blob = payload.get("data") or ""
        if "," in blob and blob.startswith("data:"):
            blob = blob.split(",", 1)[1]
        try:
            raw = base64.b64decode(blob, validate=True)
        except Exception:                              # noqa: BLE001
            return self.fail(400, "Die Datei konnte nicht gelesen werden.")
        if not raw:
            return self.fail(400, "Die Datei ist leer.")
        if len(raw) > MAX_UPLOAD:
            return self.fail(413, "Die Datei ist groesser als %d MB." % (MAX_UPLOAD // (1024 * 1024)))

        pid = int(payload.get("person") or 0)
        name = safe_name(payload.get("name"), "datei")

        if kind == "foto":
            # portraits of hand added people are kept apart from the ones the
            # PDF gave up, so a re-extraction cannot quietly replace one
            folder, name = store.photo_dir(), "eigen_%d_%s" % (pid, name)
        else:
            folder = store.docs_dir(pid)

        os.makedirs(folder, exist_ok=True)
        name = free_name(folder, name)
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(raw)

        url = ("/foto/" + urllib.parse.quote(name) if kind == "foto"
               else "/datei/%d/%s" % (pid, urllib.parse.quote(name)))
        self.send_json({"ok": True, "file": name, "url": url, "size": len(raw)})

    def api_remove_file(self) -> None:
        """Take a document out of the way without destroying it.

        Deleting somebody's only scan of a birth certificate because of a
        mis-click is not a risk worth taking, so the file is moved into
        `data/dokumente/_geloescht/` and stays there.
        """
        payload = self.body()
        pid = int(payload.get("person") or 0)
        name = safe_name(payload.get("file"))
        source = os.path.join(store.docs_dir(pid), name)
        if not os.path.isfile(source):
            return self.send_json({"ok": True, "note": "war schon weg"})
        bin_dir = store.docs_dir("_geloescht")
        os.makedirs(bin_dir, exist_ok=True)
        shutil.move(source, os.path.join(bin_dir, free_name(bin_dir, "%d_%s" % (pid, name))))
        self.send_json({"ok": True, "moved": True})


    def api_export(self) -> None:
        """Write out whatever the export dialog ticked.

        The diagram arrives already drawn, as SVG, because only the page knows
        where it put every box; everything else is done here, where there is a
        file system and a printer.
        """
        order = self.body()
        merged = current_tree()
        by_id = {p["id"]: p for p in merged["people"]}
        centre = by_id.get(int(order.get("mittelpunkt") or 0), {})
        target = export_dir()
        written = export_lib.run(merged, order, target, centre.get("name") or "")
        if not written:
            return self.fail(400, "Es war nichts zum Schreiben angehakt.")
        self.send_json({"ok": True, "dateien": written, "ordner": target})

    def api_open_folder(self) -> None:
        wohin = (self.body().get("was") or "").strip()
        ziel = store.data_dir() if wohin == "daten" else export_dir()
        subprocess.Popen(["explorer", os.path.normpath(ziel)])
        self.send_json({"ok": True})

    def api_updates(self) -> None:
        """Hand the releases page to the browser, and nothing else.

        The program asks GitHub nothing.  It has never made a request off this
        machine and the README says so, which is a property worth keeping in a
        program that holds birth dates and photographs of living children: a
        version check is a request that says "this copy exists, here, now",
        every time it starts.

        Opening a page instead puts the person in front of the answer with
        their own browser and their own session - which also happens to be the
        only thing that works while the repository is private, where an
        unauthenticated request would see nothing at all.  If it ever becomes
        public, a real check belongs here and nowhere else.
        """
        webbrowser.open(REPO_URL + "/releases")
        self.send_json({"ok": True, "geoeffnet": REPO_URL + "/releases"})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def open_window(url: str) -> subprocess.Popen | None:
    """Open the page as its own window, without browser chrome around it.

    `--app` gives a plain window with its own taskbar entry and no address bar,
    and the throwaway profile keeps it clear of whatever Edge the user already
    has open.  What this process then does is not worth watching: Edge hands the
    window to a browser process of its own and this one returns immediately.
    The page's heartbeat is what says whether anybody is still looking.
    """
    for exe in EDGE_CANDIDATES:
        if os.path.exists(exe):
            profile = tempfile.mkdtemp(prefix="stammbaum-fenster-")
            return subprocess.Popen([
                exe, "--app=" + url,
                "--user-data-dir=" + profile,
                "--no-first-run", "--no-default-browser-check",
                "--window-size=1560,980",
            ])
    print("Hinweis: Edge nicht gefunden - die Seite wird im Standardbrowser geoeffnet.")
    print("         Zum Beenden dieses Fenster schliessen.")
    webbrowser.open(url)
    return None


def watch_window(httpd: socketserver.TCPServer) -> None:
    """Serve until the last window lets go of its connection.

    A page reload drops the connection and opens a new one, so a few seconds of
    nobody holding the line is normal and does not end anything.
    """
    global LAST_SEEN
    LAST_SEEN = time.time()
    try:
        while True:
            time.sleep(1)
            with WATCHER_LOCK:
                held, quiet = WATCHERS, time.time() - LAST_SEEN
            if held:
                continue
            if quiet > (GONE_FOR if SEEN_ANYTHING else FIRST_CALL_WITHIN):
                break
    except KeyboardInterrupt:
        pass
    httpd.shutdown()


def main() -> None:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    # Nothing has to exist for the program to start any more.  It makes its own
    # folder, and an empty tree is a legitimate state - that is what a family
    # who has just been handed the program begins with.
    # Checked before anything else needs it.  A folder that cannot be written
    # to used to surface as a PyInstaller stack trace in a message box, which
    # tells the person holding the mouse exactly nothing.
    ordner = store.data_dir()
    # A chosen folder is written down a second time, outside the program folder,
    # so that replacing or deleting that folder does not lose the way back to
    # the trees.
    store.anchor_pointer()
    # The empty shell of the older arrangement, taken away once it is empty.
    store.tidy_old_layout()
    if not store.writable(ordner):
        complain(
            "Der Datenordner laesst sich nicht beschreiben:\n\n"
            "    %s\n\n"
            "Dort liegen die Stammbaeume. Moegliche Gruende: der Ordner ist\n"
            "schreibgeschuetzt, das Laufwerk ist nicht verbunden, oder in\n"
            "%s steht ein Pfad, den es nicht mehr gibt.\n\n"
            "Diese Datei loeschen setzt den Ordner auf den Standard zurueck:\n"
            "    %s"
            % (ordner, store.POINTER_FILE,
               "\n    ".join(store.pointer_files())))
        return
    print("Datenordner: %s" % ordner)

    # Two switches for working on the program itself: a fixed port so a browser
    # already pointed at it keeps working across restarts, and no window of its
    # own so the page can be driven from somewhere else.
    args = sys.argv[1:]
    port = 0
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    silent = "--kein-fenster" in args

    with Server(("127.0.0.1", port), Handler) as httpd:
        port = httpd.server_address[1]
        url = "http://127.0.0.1:%d/?k=%s" % (port, TOKEN)
        print("Stammbaum-Editor laeuft auf %s" % url)
        print("Aenderungen gehen nach data/edits.json - tree.json bleibt unberuehrt.")

        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        if silent:
            try:
                thread.join()
            except KeyboardInterrupt:
                httpd.shutdown()
        else:
            open_window(url)
            watch_window(httpd)
    print("Beendet.")


def complain(text: str) -> None:
    """Say something when there is no console to say it to."""
    if sys.stdout is not None and not getattr(sys, "frozen", False):
        print(text)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Stammbaum", 0x10)
    except Exception:                                  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit as stop:
        if stop.code:
            complain(str(stop.code))
    except Exception as err:                           # noqa: BLE001
        import traceback
        complain("Das Programm konnte nicht starten.\n\n%s: %s\n\n%s"
                 % (type(err).__name__, err, traceback.format_exc()[-1200:]))
