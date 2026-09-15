# -*- coding: utf-8 -*-
"""An export for the whole family puts nobody in the middle.

The dialog asks "Mit Mittelpunkt" or "Ohne Mittelpunkt".  Ohne means: the same
people, but no box marked, no label "Mittelpunkt", no "Onkel" or "Cousine"
measured from one person - in the drawing, in the book and in the page.

The drawing is made by the page, so that half is read off the template; the
book and the page are made here and are checked as they come out.

The names are invented.

    python tools/test_ohne_mittelpunkt.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edits as person_lib          # noqa: E402
import export                       # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")

# what the report printed beside a name - seen from whoever it was written for
BERICHT_ANGABE = "Großonkel mütterlicherseits"


def baum() -> dict:
    a = person_lib.fill_missing({"id": 1, "name": "Tamo Wiebking", "sex": "m",
                                 "surname": "Wiebking", "spouses": [2],
                                 "birth": {"year": 1950}})
    b = person_lib.fill_missing({"id": 2, "name": "Ilka Dornbusch", "sex": "w",
                                 "surname": "Dornbusch", "spouses": [1],
                                 "relation": BERICHT_ANGABE})
    return {"meta": {"title": "Testbaum", "root": 1, "count": 2},
            "people": [a, b], "marriages": [], "checks": []}


ALLE_FELDER = {key: True for key in export.FIELD_GROUPS}


class TestBuchUndSeite(unittest.TestCase):

    def test_buch_ohne_mittelpunkt_nennt_keinen(self):
        buch = export.book_body(baum(), {}, ALLE_FELDER, "")
        self.assertNotIn("Mittelpunkt", buch)

    def test_buch_mit_mittelpunkt_nennt_ihn_wie_bisher(self):
        buch = export.book_body(baum(), {}, ALLE_FELDER, "Tamo Wiebking")
        self.assertIn("Mittelpunkt der Verwandtschaftsangaben: <b>Tamo Wiebking</b>", buch)

    def test_neutral_nimmt_bericht_angabe_und_eigenen_mittelpunkt(self):
        aus = export.neutral(baum())
        self.assertIsNone(aus["meta"]["root"])
        self.assertTrue(all(not p.get("relation") for p in aus["people"]))
        self.assertEqual([p["id"] for p in aus["people"]], [1, 2],
                         "ohne Mittelpunkt darf niemand wegfallen")

    def test_seite_ohne_mittelpunkt_traegt_keine_relative_angabe(self):
        order = {"formate": ["html"], "felder": ALLE_FELDER, "personen": [1, 2]}
        with tempfile.TemporaryDirectory() as ziel:
            namen = export.run(baum(), order, ziel, "")
            with open(os.path.join(ziel, namen[0]), encoding="utf-8") as fh:
                seite = fh.read()
        self.assertNotIn(BERICHT_ANGABE, seite)
        self.assertNotIn("Tamo Wiebking - ", namen[0])

    def test_seite_mit_mittelpunkt_bleibt_wie_bisher(self):
        order = {"formate": ["html"], "felder": ALLE_FELDER, "personen": [1, 2]}
        with tempfile.TemporaryDirectory() as ziel:
            namen = export.run(baum(), order, ziel, "Tamo Wiebking")
            with open(os.path.join(ziel, namen[0]), encoding="utf-8") as fh:
                seite = fh.read()
        self.assertIn(BERICHT_ANGABE, seite)
        self.assertIn("Tamo Wiebking", namen[0])


class TestDialogUndZeichnung(unittest.TestCase):

    def setUp(self):
        with open(VORLAGE, encoding="utf-8") as fh:
            self.s = fh.read()

    def funktion(self, kopf: str) -> str:
        f = re.search(re.escape(kopf) + r"(.*?)\n\}", self.s, re.S)
        self.assertIsNotNone(f, "%s gibt es nicht mehr" % kopf)
        return f.group(1)

    def test_die_wahl_steht_vor_inhalt(self):
        dialog = self.funktion("function exportHTML(){")
        wahl = dialog.find('id="expCentreWithout"')
        self.assertGreater(wahl, -1, "im Export-Dialog fehlt 'Ohne Mittelpunkt'")
        self.assertLess(wahl, dialog.find("<h3>Inhalt</h3>"),
                        "die Wahl steht nicht ganz oben")

    def test_ohne_mittelpunkt_in_der_ansicht_steht_die_wahl_fest(self):
        dialog = self.funktion("function exportHTML(){")
        self.assertIn('centreName ? "" : " checked disabled"', dialog)
        self.assertIn('centreName ? " checked" : " disabled"', dialog)

    def test_ohne_wird_als_kein_mittelpunkt_geschickt(self):
        lauf = self.funktion("async function runExport(){")
        self.assertIn("diagramSVG(bilder, !withCentre)", lauf)
        self.assertIn("mittelpunkt: withCentre ? centre : null", lauf)
        self.assertNotIn("mittelpunkt: centre,", lauf)

    def test_neutrale_zeichnung_hebt_nichts_hervor(self):
        zeichnung = self.funktion("function diagramSVG(bilder, neutral = false){")
        self.assertIn('!neutral && box.classList.contains("centre")', zeichnung)
        self.assertIn('neutral && shownTag.classList.contains("rel")', zeichnung,
                      "Verwandtschaftsangaben und 'Mittelpunkt' bleiben am Kasten")
        self.assertIn('const title = neutral ? ""', zeichnung,
                      "Titel und Fusszeile nennen weiter einen Mittelpunkt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
