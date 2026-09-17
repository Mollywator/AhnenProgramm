"""Was ein Zweig über sich selbst weiß - und im Hauptordner schweigt.

Ein Worktree ist eine zweite Arbeitsfassung desselben Programms, die neben dem
Hauptordner läuft. Von außen sehen die Fenster gleich aus, und genau das ist das
Problem: wer zwei davon offen hat, weiß nach dem dritten Wechsel nicht mehr,
welches Fenster welchen Stand zeigt. Also sagt es der Fenstertitel.

Der Hauptordner bekommt davon nichts ab. `info()` gibt dort `None` zurück, und
alles, was daran hängt, fällt still weg - kein Zusatz im Titel, kein Übungsbaum,
keine Spur. Das ist der ganze Sinn dieser Datei: das Zweig-Werkzeug lebt im
Programm, wird aber nur dort sichtbar, wo tatsächlich ein Zweig läuft.

Die Kennung ist ein Hash über den Inhalt der Quelldateien, nicht über die
Git-Historie: derselbe Code ergibt dieselbe Kennung, geänderter Code eine neue -
auch ohne Commit. Damit beantwortet der Titel die Frage, um die es geht: zeigt
dieses Fenster den Stand, über den gerade geredet wird?
"""

import functools
import os
import subprocess

# Was nicht zum Programm gehört und die Kennung darum nicht ändern darf.
# Dokumentation, Konfiguration, Werkzeugordner: wer ein Komma in einer README
# verschiebt, hat das Programm nicht angefasst.
#
# Diese Liste ist absichtlich Zeichen für Zeichen dieselbe wie die im
# Entwicklungswerkzeug, das im Chat dieselbe Kennung ausgibt - sonst stünden im
# Fenster und im Chat zwei verschiedene Zahlen für denselben Stand, und die
# Kennung wäre wertlos. Wer hier etwas ändert, ändert dort mit.
AUSSEN = [
    "*.md", "LICENSE",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "*.lock",
    "tsconfig*.json", "jest.config.*", "vitest.config.*", "*.config.*",
    ".editorconfig", ".gitignore", ".gitattributes",
    ".prettierrc*", ".eslintrc*", "eslint.config.*", ".env*",
    "dist/", "build/", "out/", ".next/", ".nuxt/", ".cache/",
    ".claude/", ".vscode/", ".idea/", "node_modules/",
    "BUILDLOG.md",
]


def _git(args: list[str], ordner: str, eingabe: str | None = None) -> str | None:
    """Git aufrufen und bei jedem Ärger `None` zurückgeben.

    Ohne Git, ohne Repo oder mit einem Git, das gerade etwas anderes vorhat,
    läuft das Programm ganz normal weiter - nur ohne Kennung. Eine Zeile im
    Fenstertitel ist nichts, wofür ein Start scheitern darf.

    Geschrieben und gelesen wird in Bytes, nicht im Textmodus: der übersetzt
    beim Schreiben jedes \\n in ein \\r\\n, und da hier Zeilen gehasht werden,
    käme dabei eine andere Kennung heraus als überall sonst.
    """
    try:
        fertig = subprocess.run(
            ["git"] + args, cwd=ordner, capture_output=True, timeout=10,
            input=None if eingabe is None else eingabe.encode("utf-8"),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if fertig.returncode != 0:
        return None
    return fertig.stdout.decode("utf-8", "replace").strip()


def ist_zweig(ordner: str) -> bool:
    """Läuft das Programm aus einem Worktree statt aus dem Hauptordner?

    Gefragt wird Git selbst: ein Worktree hat ein eigenes `.git`-Verzeichnis,
    das auf das gemeinsame zeigt - im Hauptordner sind beide dasselbe. Das ist
    verlässlicher als ein Blick auf den Pfad, der nur zufällig "worktrees" heißt.
    """
    eigen = _git(["rev-parse", "--absolute-git-dir"], ordner)
    gemeinsam = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], ordner)
    if not eigen or not gemeinsam:
        return False
    return os.path.normcase(os.path.normpath(eigen)) != \
        os.path.normcase(os.path.normpath(gemeinsam))


def kennung(ordner: str) -> str | None:
    """Sieben Zeichen über den Inhalt aller Quelldateien.

    Erst die Dateiliste, dann je Datei ein Hash aus dem Arbeitsverzeichnis, dann
    ein Hash über diese Hashes. Gelesen wird, was auf der Platte liegt - nicht,
    was zuletzt eingecheckt wurde, denn genau der ungespeicherte Umbau ist das,
    was man im Fenster sehen will.
    """
    ausschluss = [":(exclude)" + muster for muster in AUSSEN]
    liste = _git(["ls-files", "--cached", "--others", "--exclude-standard", "--", "."]
                 + ausschluss, ordner)
    if liste is None:
        return None
    dateien = sorted(z for z in liste.splitlines() if z.strip())
    if not dateien:
        return None
    hashes = _git(["hash-object", "--stdin-paths"], ordner, eingabe="\n".join(dateien))
    if not hashes:
        return None
    ganz = _git(["hash-object", "--stdin"], ordner, eingabe=hashes)
    if not ganz:
        return None
    return ganz[:7]


"""Der Übungsbaum.

Wer am Programm arbeitet, braucht etwas zum Anklicken - und das darf nicht die
eigene Familie sein. Ein Zweig bekommt darum einen eigenen Datenordner, und der
ist beim ersten Start leer. Diese zwölf Personen füllen ihn.

Sie heißen "Person 1" bis "Person 12", und das ist Absicht: über einen Fehler
lässt sich dann reden, ohne dass jemand raten muss, wer gemeint ist - "bei
Person 4 auf das Plus gedrückt, dann stand Person 7 an der falschen Stelle" ist
eine vollständige Fehlermeldung. Erfundene Namen wären hübscher und würden genau
das kaputtmachen.

Der Zuschnitt hat einen Grund je Person: vier Generationen, damit sich beim
Wechsel des Mittelpunkts wirklich etwas umsortiert; ein Paar mit drei Kindern,
damit Geschwister nebeneinander stehen; eine angeheiratete Linie, damit nicht
alles Blutsverwandtschaft ist; und eine Person mit nur einem Elternteil, an der
sich das Angebot "gehört mit dazu" ausprobieren lässt.
"""

# (Nummer, Geschlecht, Geburtsjahr, Eltern, Ehe)
UEBUNGSLEUTE = [
    (1,  "m", 1900, [],      [2]),      # Urgroßeltern
    (2,  "w", 1903, [],      [1]),
    (3,  "m", 1928, [1, 2],  [5]),      # deren Sohn, verheiratet
    (4,  "w", 1931, [1, 2],  []),       # dessen Schwester, ohne Anhang
    (5,  "w", 1930, [12],    [3]),      # eingeheiratet, mit eigenem Vater
    (6,  "m", 1955, [3, 5],  [9]),
    (7,  "w", 1957, [3, 5],  []),
    (8,  "m", 1960, [3],     []),       # nur ein Elternteil - zum Ausprobieren
    (9,  "w", 1956, [],      [6]),      # eingeheiratet, Herkunft unbekannt
    (10, "m", 1982, [6, 9],  []),
    (11, "w", 1985, [6, 9],  []),
    (12, "m", 1902, [],      []),       # der angeheiratete Zweig
]


def uebungsbaum() -> list[dict]:
    """Die zwölf Personen als fertige Datensätze.

    Die Kinderlisten werden nicht mitgeschrieben: das Programm hält Eltern und
    Kinder beim Speichern selbst in beide Richtungen deckungsgleich, und eine
    zweite Quelle für dieselbe Wahrheit ist eine, die irgendwann abweicht.
    """
    import edits as person_lib

    leute = []
    for nummer, geschlecht, jahr, eltern, ehe in UEBUNGSLEUTE:
        p = person_lib.blank_person(nummer)
        p["name"] = "Person %d" % nummer
        p["given"] = "Person"
        p["surname"] = str(nummer)
        p["sex"] = geschlecht
        p["parents"] = list(eltern)
        p["spouses"] = list(ehe)
        # Diese zwölf sind verheiratet - so heißen sie ja auch ("Ehefrau").
        # Ausgeschrieben statt dem Stillschweigen überlassen, damit der
        # Übungsbaum zeigt, was ein gepflegter Baum enthält.
        p["spouse_kind"] = {str(x): "marriage" for x in ehe}
        p["birth"] = {"year": jahr, "day": None, "month": None,
                      "place": None, "text": str(jahr)}
        # Zwei Bilder je Geschlecht, abwechselnd - genug, dass nebeneinander
        # stehende Kästen verschieden aussehen.
        gleiche = sum(1 for x in leute if x["sex"] == geschlecht)
        p["photo"] = STRICHMAENNCHEN[geschlecht][gleiche % 2]
        leute.append(p)
    return leute


STRICHMAENNCHEN = {"m": ["strichmann-1.jpg", "strichmann-2.jpg"],
                   "w": ["strichfrau-1.jpg", "strichfrau-2.jpg"]}


def strichmaennchen(ordner: str) -> None:
    """Die vier Porträts des Übungsbaums in `ordner` zeichnen.

    Zur Laufzeit gezeichnet statt als Bilddateien mitgeliefert: vier Strichmännchen
    sind ein paar Zeilen, und ein Übungsbaum ohne Bilder zeigt nicht, wie ein
    Kasten mit Porträt aussieht.
    """
    from PIL import Image, ImageDraw

    os.makedirs(ordner, exist_ok=True)
    tinte = (60, 52, 44)
    hintergruende = [(214, 228, 240), (240, 226, 204), (238, 214, 222), (220, 236, 214)]
    namen = STRICHMAENNCHEN["m"] + STRICHMAENNCHEN["w"]
    for nummer, name in enumerate(namen):
        bild = Image.new("RGB", (240, 300), hintergruende[nummer])
        d = ImageDraw.Draw(bild)
        frau = name.startswith("strichfrau")
        # Kopf und Gesicht
        d.ellipse((85, 40, 155, 110), outline=tinte, width=6)
        d.ellipse((104, 66, 112, 74), fill=tinte)
        d.ellipse((128, 66, 136, 74), fill=tinte)
        d.arc((102, 72, 138, 98), 20, 160, fill=tinte, width=4)
        if frau:
            # lange Haare und ein Kleid als Dreieck
            d.line((88, 70, 72, 140), fill=tinte, width=6)
            d.line((152, 70, 168, 140), fill=tinte, width=6)
            d.polygon([(120, 110), (70, 240), (170, 240)], outline=tinte, width=6)
            d.line((105, 240, 100, 285), fill=tinte, width=6)
            d.line((135, 240, 140, 285), fill=tinte, width=6)
            if nummer % 2:
                d.ellipse((140, 30, 170, 55), outline=tinte, width=5)       # Schleife
        else:
            d.line((120, 110, 120, 210), fill=tinte, width=6)
            d.line((120, 210, 85, 285), fill=tinte, width=6)
            d.line((120, 210, 155, 285), fill=tinte, width=6)
            if nummer % 2:
                d.rectangle((92, 18, 148, 44), fill=tinte)                  # Hut
                d.line((75, 44, 165, 44), fill=tinte, width=6)
            else:
                d.line((106, 90, 134, 90), fill=tinte, width=5)             # Schnurrbart
        # Arme, winkend
        d.line((120, 140, 70, 110 if nummer % 2 else 170), fill=tinte, width=6)
        d.line((120, 140, 175, 100), fill=tinte, width=6)
        bild.save(os.path.join(ordner, name), "JPEG", quality=90)


@functools.lru_cache(maxsize=4)
def info(ordner: str) -> dict | None:
    """Name und Kennung des Zweigs - oder `None`, wenn keiner läuft.

    Einmal je Start beantwortet: die drei Git-Aufrufe kosten spürbar Zeit, und
    der Stand ändert sich nicht, während das Fenster offen steht. Wer nach einer
    Änderung die neue Kennung sehen will, startet neu - und genau dann will man
    ohnehin wissen, ob der neue Stand angekommen ist.
    """
    if not ist_zweig(ordner):
        return None
    return {
        "name": os.path.basename(ordner.rstrip("\\/")),
        "ast": _git(["rev-parse", "--abbrev-ref", "HEAD"], ordner) or "",
        "kennung": kennung(ordner) or "",
    }
