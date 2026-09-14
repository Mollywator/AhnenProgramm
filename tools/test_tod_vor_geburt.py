# -*- coding: utf-8 -*-
"""A parent who died long before the child cannot be its birth parent.

A mother has to live to the birth.  A father may have died up to eleven months
before it - that much a pregnancy allows - and not a day more.  The rule exists
twice: in `build_data.py`, for the report read from a PDF, and in the editor
page, which checks the whole tree in the background.  Both copies are run
against the same table here, so they cannot drift apart.

What the page does with a finding is checked too: it stays quiet while typing,
announces only what is new, and keeps what it looked at and what was decided in
`pruefung.json` beside the tree - never in `baum.json`, so the check needs no
new file format and an older program still opens the tree.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

import build_data  # noqa: E402
import format as schema  # noqa: E402
import pruefung  # noqa: E402

VORLAGE = os.path.join(HIER, "temp" + "late.html")


def datum(jahr, monat=None, tag=None, ungefaehr=False):
    return {"year": jahr, "month": monat, "day": tag, "approx": ungefaehr}


# (sex of the parent, death of the parent, birth of the child, impossible?)
FAELLE = [
    ("m", datum(1900, 3, 15), datum(1901, 1, 10), False),   # ten months
    ("m", datum(1900, 3, 15), datum(1901, 2, 15), False),   # eleven, exactly
    ("m", datum(1900, 3, 15), datum(1901, 3, 1), True),     # eleven and a half
    ("m", datum(1900), datum(1901), False),                 # could be Jan/Dec
    ("m", datum(1900), datum(1902), True),
    (None, datum(1900), datum(1902), True),                 # unknown sex: father's rule
    (None, datum(1900, 3), datum(1901, 2), False),
    ("w", datum(1900, 5, 1), datum(1900, 5, 1), False),     # died in childbirth
    ("w", datum(1900, 5, 1), datum(1900, 5, 2), True),
    ("w", datum(1900), datum(1900), False),
    ("w", datum(1900), datum(1901), True),
    ("w", datum(1900, 5), datum(1900, 5, 20), False),       # month only: any day of it
    ("w", datum(1900, 5), datum(1900, 6), True),
    ("m", datum(1900, ungefaehr=True), datum(1903), False),  # "um 1900" reaches 1902
    ("m", datum(1900, ungefaehr=True), datum(1904), True),
    ("w", datum(1900), datum(1903, ungefaehr=True), True),   # "um 1903" starts in 1901
    ("w", datum(1900), datum(1902, ungefaehr=True), False),
    ("m", None, datum(1950), False),                        # no death, nothing to say
    ("w", datum(1900), None, False),
]


def als_personen(fall):
    sex, tod, geburt, _ = fall
    return {"sex": sex, "death": tod}, {"birth": geburt}


def vorlage() -> str:
    with open(VORLAGE, encoding="utf-8") as fh:
        return fh.read()


def teil(s: str, muster: str) -> str:
    treffer = re.search(muster, s, re.S)
    if treffer is None:
        raise AssertionError("nicht mehr in der Seite: " + muster)
    return treffer.group(0)


class TestRegelPython(unittest.TestCase):

    def test_die_tabelle(self):
        for fall in FAELLE:
            eltern, kind = als_personen(fall)
            with self.subTest(fall=fall):
                self.assertEqual(build_data.died_before_child(eltern, kind), fall[3])


class TestRegelSeite(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_dieselbe_tabelle_im_browser(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht gefunden")
        code = "\n".join([
            teil(self.s, r"const FATHER_GRACE_MONTHS = \d+;"),
            teil(self.s, r"function dateSpan\(d\)\{.*?\n\}"),
            teil(self.s, r"function diedBeforeChild\(parent, child\)\{.*?\n\}"),
            "const faelle = " + json.dumps([[*als_personen(f), f[3]] for f in FAELLE]) + ";",
            "const falsch = faelle.map((f, i) => [i, diedBeforeChild(f[0], f[1]), f[2]])"
            ".filter(r => r[1] !== r[2]);",
            "console.log(JSON.stringify(falsch));",
        ])
        lauf = subprocess.run([node, "-e", code], capture_output=True, text=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        falsch = json.loads(lauf.stdout)
        self.assertEqual(falsch, [], "die Seite urteilt anders als build_data: "
                         + "; ".join("%s -> %s" % (FAELLE[i], ist) for i, ist, _ in falsch))

    def test_beide_kennen_dieselbe_frist(self):
        frist = int(re.search(r"const FATHER_GRACE_MONTHS = (\d+);", self.s).group(1))
        self.assertEqual(frist, build_data.FATHER_GRACE_MONTHS)


class TestHintergrundpruefung(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_ein_toter_ehepartner_wird_nicht_als_elternteil_angeboten(self):
        """The old fault: the mother's late first husband, one click away."""
        f = teil(self.s, r"function spouseSuggestions\(role, taken\)\{.*?\n\}")
        self.assertIn("diedBeforeChild(lookup(mate), draft)", f)

    def test_beim_bearbeiten_meldet_sich_nichts(self):
        for f in (r"function linkSection\(role, title, ids, hint\)\{.*?\n\}",
                  r"function openMenu\(picker\)\{.*?\n\}",
                  r"async function saveDraft\(\)\{.*?\n\}"):
            self.assertNotIn("deathCheck", teil(self.s, f))
            self.assertNotIn("diedBeforeChild", teil(self.s, f))

    def test_laeuft_nach_dem_laden_und_nach_jedem_speichern(self):
        self.assertIn("scheduleDeathCheck();",
                      teil(self.s, r"function refreshGraph\(\)\{.*?\n\}"))
        self.assertIn("scheduleDeathCheck();",
                      teil(self.s, r"\(function nameThePage\(\)\{.*?\n\}\)\(\);"))

    def test_nur_im_editor(self):
        self.assertIn("if(!EDIT) return;",
                      teil(self.s, r"function scheduleDeathCheck\(\)\{.*?\n\}"))

    def test_bekannte_personen_werden_uebersprungen(self):
        f = teil(self.s, r"function runDeathCheck\(\)\{.*?\n\}")
        self.assertIn("seedDeathCheck()", f)
        self.assertIn("deathSeen.get(p.id) !== deathSignature(p)", f)
        seed = teil(self.s, r"function seedDeathCheck\(\)\{.*?\n\}")
        self.assertIn("deathSignature(p) !== rec.sig", seed)

    def test_nur_neue_funde_melden_sich_zehn_sekunden(self):
        f = teil(self.s, r"function finishDeathCheck\(\)\{.*?\n\}")
        self.assertIn("if(!fresh.length) return;", f)
        self.assertIn("deathKnown", f)
        self.assertIn("10000", f)

    def test_eine_entscheidung_gilt_fuer_genau_diese_daten(self):
        f = teil(self.s, r"function deathCheck\(parentId, childId\)\{.*?\n\}")
        self.assertIn("said.print === print", f)
        self.assertIn('=== "step"', f, "Stiefeltern werden nicht gemessen")

    def test_pruefen_und_verwerfen_stehen_im_bericht(self):
        f = teil(self.s, r"function deathReportHTML\(\)\{.*?\n\}")
        self.assertIn("Geprüft – passt so", f)
        self.assertIn("Nicht nachprüfbar – ausblenden", f)
        self.assertIn("data-decide-all", f)
        self.assertIn("deathReportHTML()", teil(self.s, r"function openCheckSheet\(\)\{.*?\n\}"))

    def test_die_zahl_steht_rot_am_knopf(self):
        self.assertIn("pruefzahl", teil(self.s, r"function updateCheckButton\(\)\{.*?\n\}"))

    def test_die_baumdaten_werden_nicht_angefasst(self):
        """The whole point of pruefung.json."""
        self.assertNotIn("parent_checked", self.s)
        self.assertIn("/api/pruefung?k=", teil(self.s, r"function savePruefung\(\)\{.*?\n\}"))
        self.assertNotIn("/api/save", teil(self.s, r"function savePruefung\(\)\{.*?\n\}"))
        self.assertEqual(schema.FORMAT, 3, "fuer die Pruefung braucht es kein neues Format")


class TestPruefungsdatei(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_ohne_datei_ist_sie_leer(self):
        self.assertEqual(pruefung.laden(self.tmp.name), pruefung.leer())

    def test_eine_kaputte_datei_ist_kein_fehler(self):
        with open(os.path.join(self.tmp.name, pruefung.NAME), "w", encoding="utf-8") as fh:
            fh.write("{ nicht json")
        self.assertEqual(pruefung.laden(self.tmp.name), pruefung.leer())

    def test_hin_und_zurueck(self):
        daten = {"personen": {"4": {"sig": "s", "funde": [{"eltern": 1, "print": "p"}]},
                              "6": {"sig": "t", "funde": []}},
                 "entscheidungen": {"1:4": {"print": "p", "art": "verworfen", "am": "2026-09-14"}}}
        pruefung.speichern(self.tmp.name, daten)
        wieder = pruefung.laden(self.tmp.name)
        self.assertEqual(wieder["personen"], daten["personen"])
        self.assertEqual(wieder["entscheidungen"], daten["entscheidungen"])

    def test_unsinn_faellt_weg(self):
        roh = {"personen": {"x": {"sig": "s"}, "5": {"sig": 3}, "7": {"sig": "ok", "funde": ["?"]}},
               "entscheidungen": {"1:4": {"print": "p", "art": "vielleicht"},
                                  "kaputt": {"print": "p", "art": "geprueft"},
                                  "2:5": {"print": "q", "art": "geprueft"}}}
        sauber = pruefung.bereinigen(roh)
        self.assertEqual(sauber["personen"], {"7": {"sig": "ok", "funde": []}})
        self.assertEqual(list(sauber["entscheidungen"]), ["2:5"])

    def test_der_server_gibt_und_nimmt_sie(self):
        with open(os.path.join(HIER, "edit_server.py"), encoding="utf-8") as fh:
            server = fh.read()
        self.assertIn('"pruefung": pruefung.laden(', server)
        self.assertIn('route == "/api/pruefung"', server)


if __name__ == "__main__":
    unittest.main(verbosity=2)
