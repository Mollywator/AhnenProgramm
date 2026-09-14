# -*- coding: utf-8 -*-
"""The Prüfbericht names people by entry number, and a suspected double entry
can be looked at in the tree.

`linkIds` turns every number of an existing person into a button that opens
their sheet - "#12" as well as the older "Person 12".  `pairOf` picks the two
entries a duplicate finding is about; "X ist mit A und mit B verheiratet" is
about A and B, not X.  Both run here in node against the page's own code.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")


def vorlage() -> str:
    with open(VORLAGE, encoding="utf-8") as fh:
        return fh.read()


def teil(text: str, muster: str) -> str:
    treffer = re.search(muster, text, re.S)
    if not treffer:
        raise AssertionError("nicht gefunden: " + muster)
    return treffer.group(0)


FAELLE_PAAR = [
    ("Ilvi Feldkamp (#12, *1704) und Ilvi Feldkamp (#34, *1704) sind dieselbe Person, "
     "zweimal erfasst - gemeinsam: Zorbas Quendel (#5).", [12, 34]),
    ("Zorbas Quendel (#5) ist mit Ilvi Feldkamp (#12) und mit Ilvi Feldkamp (#34) verheiratet "
     "- das ist vermutlich derselbe Mensch, doppelt erfasst.", [12, 34]),
    ("Ilvi Feldkamp (#12) und Ilvi Feldkamp (#34): gleicher Name und Jahrgang, aber "
     "verschiedene Angehoerige - vermutlich zwei verschiedene Personen.", [12, 34]),
    ("Zorbas Quendel (#5): Lebensalter 106 Jahre (1700-1806).", None),
    ("Ilvi Feldkamp (#12) und Xaver Lindwurm (#99) sind dieselbe Person, zweimal erfasst.", None),
]


class TestSeite(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def lauf(self, code: str):
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht gefunden")
        out = subprocess.run([node, "-e", code], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_jede_nummer_ist_ein_knopf(self):
        code = "\n".join([
            "const BY_ID = new Map([[5, {}], [12, {}]]);",
            teil(self.s, r"function linkIds\(s\)\{.*?\n\}"),
            "console.log(JSON.stringify([",
            "  linkIds('Zorbas (#5) und Ilvi (#12)'),",
            "  linkIds('Person 12 (Ilvi): Erzaehltext'),",
            "  linkIds('Zorbas (#5) nennt Elternteil 12'),",
            "  linkIds('Personen-ID 7 fehlt, Kind #99 auch'),",
            "]));",
        ])
        mit_zwei, alt, eltern, fremd = self.lauf(code)
        self.assertEqual(mit_zwei.count('data-open="'), 2)
        self.assertIn('Person <button class="plink"', alt)
        self.assertIn('data-open="12">#12</button>', alt)
        self.assertIn('Elternteil <button class="plink"', eltern)
        self.assertEqual(fremd, "Personen-ID 7 fehlt, Kind #99 auch",
                         "wer nicht im Baum steht, bekommt keinen Knopf")

    def test_das_paar_einer_doppelung(self):
        code = "\n".join([
            "const BY_ID = new Map([[5, {}], [12, {}], [34, {}]]);",
            teil(self.s, r"function pairOf\(text, evenGone\)\{.*?\n\}"),
            "const faelle = " + json.dumps([f[0] for f in FAELLE_PAAR]) + ";",
            "console.log(JSON.stringify(faelle.map(t => pairOf(t))));",
        ])
        for (text, erwartet), ist in zip(FAELLE_PAAR, self.lauf(code)):
            with self.subTest(text=text):
                self.assertEqual(ist, erwartet)

    def test_der_knopf_steht_im_bericht(self):
        f = teil(self.s, r"function openCheckSheet\(\)\{.*?\n\}")
        self.assertIn("pairOf(c.text)", f)
        self.assertIn("Beide im Stammbaum zeigen", f)

    def test_beide_werden_markiert_ohne_den_baum_umzubauen(self):
        self.assertIn('spotlight.includes(id) ? " spot"',
                      teil(self.s, r"function boxHTML\(id, x, y, classes, tag\)\{.*?\n\}"))
        show = teil(self.s, r"function showPair\(ids\)\{.*?\n\}")
        for verboten in ("setMode", "centre =", "renderTree", "view.scale", "view.x"):
            self.assertNotIn(verboten, show, "markieren darf den Baum nicht verschieben")
        self.assertNotIn("fitSpot", self.s)
        self.assertIn('id="spotbar"', self.s)
        self.assertIn('id="spotarrows"', self.s)

    def test_pfeile_zeigen_wohin_und_verschieben_nur(self):
        self.assertIn("updateSpotArrows()", teil(self.s, r"function paint\(\)\{.*?\n\}"))
        go = teil(self.s, r"function goToSpot\(id\)\{.*?\n\}")
        self.assertNotIn("view.scale =", go, "nur schieben, nicht zoomen")
        bar = teil(self.s, r"function renderSpotbar\(\)\{.*?\n\}")
        self.assertIn('data-spot="alle"', bar, "nicht im Bild: Knopf, keine Automatik")

    def test_zusammenfuehren_nur_mit_zweitem_klick(self):
        merge = teil(self.s, r"function renderMerge\(\)\{.*?\n\}")
        self.assertIn('data-merge-ask="1"', merge)
        self.assertIn("Ja, zusammenführen", merge)
        self.assertIn("open ? ", merge, "offene Widersprüche sperren den Knopf")
        self.assertIn('data-merge-pick="${p.id}"',
                      teil(self.s, r"function sheetHTML\(p\)\{.*?\n\}"))
        f = teil(self.s, r"function openCheckSheet\(\)\{.*?\n\}")
        self.assertIn("mergedHTML()", f)
        self.assertIn("data-merge=", f)
        self.assertIn('askButton("merge-undo|"', teil(self.s, r"function mergedHTML\(\)\{.*?\n\}"))

    def test_todesfunde_nennen_beide_nummern(self):
        self.assertIn('" (#" + p.id + ")"',
                      teil(self.s, r"function deathCheck\(parentId, childId\)\{.*?\n\}"))
        self.assertIn("linkIds(esc(f.text))",
                      teil(self.s, r"function deathRowHTML\(f\)\{.*?\n\}"))


class TestBestaetigung(unittest.TestCase):
    """A suspected double entry can be confirmed as two people - two uncles
    born the same year under the same name do exist - but only with a second
    click, and it can be taken back."""

    def setUp(self):
        self.s = vorlage()

    def test_erst_fragen_dann_speichern(self):
        f = teil(self.s, r"function openCheckSheet\(\)\{.*?\n\}")
        self.assertIn('askButton("paar|"', f)
        self.assertIn("data-pair-ok=", f)
        ask = teil(self.s, r"function askButton\(value, label, doAttr, text\)\{.*?\n\}")
        self.assertIn('data-ask="${value}"', ask, "der erste Klick fragt nur")
        self.assertIn("Ja, bestätigen", ask)
        self.assertIn('data-ask=""', ask, "und laesst sich abbrechen")
        tod = teil(self.s, r"function deathRowHTML\(f\)\{.*?\n\}")
        self.assertIn('askButton("geprueft|"', tod)
        self.assertNotIn('data-decide="geprueft|${f.key}">', tod)

    def test_geprueft_steht_unten_und_ist_umkehrbar(self):
        f = teil(self.s, r"function openCheckSheet\(\)\{.*?\n\}")
        self.assertIn("+ confirmed + merged;", f)
        self.assertIn("pairConfirmed(p)", f, "bestaetigte Paare verlassen die offene Liste")
        geprueft = teil(self.s, r"function confirmedHTML\(\)\{.*?\n\}")
        self.assertIn("Geprüft ·", geprueft)
        self.assertIn("data-pair-undo=", geprueft)
        self.assertIn('f.decided === "geprueft"', geprueft)

    def test_paar_schluessel_und_fingerabdruck(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht gefunden")
        code = "\n".join([
            "const BY_ID = new Map([[3, {name: 'A', birth: {year: 1704}, parents: [2, 1]}],"
            " [6, {name: 'A', birth: {year: 1704}, parents: [1]}]]);",
            "const EDIT = {};",
            "const PRUEFUNG = {doppelt: {}};",
            teil(self.s, r"const pairKey = pair => [^\n]*;"),
            teil(self.s, r"function pairPrint\(pair\)\{.*?\n\}"),
            teil(self.s, r"function pairConfirmed\(pair\)\{.*?\n\}"),
            "const out = [pairKey([6, 3]), pairPrint([6, 3]) === pairPrint([3, 6]), pairConfirmed([3, 6])];",
            "PRUEFUNG.doppelt['3:6'] = {print: pairPrint([3, 6])};",
            "out.push(pairConfirmed([6, 3]));",
            "BY_ID.get(6).birth = {year: 1705};",
            "out.push(pairConfirmed([3, 6]));",
            "console.log(JSON.stringify(out));",
        ])
        lauf = subprocess.run([node, "-e", code], capture_output=True, text=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        self.assertEqual(json.loads(lauf.stdout), ["3:6", True, False, True, False],
                         "eine geaenderte Geburt fragt wieder")

    def test_datei_behaelt_bestaetigte_paare(self):
        import sys
        sys.path.insert(0, HIER)
        import pruefung
        sauber = pruefung.bereinigen({"doppelt": {
            "6:3": {"print": "p", "am": "2026-09-14T10:00"},
            "4:4": {"print": "p"}, "x:1": {"print": "p"}, "7:8": {"print": 1}}})
        self.assertEqual(sauber["doppelt"], {"3:6": {"print": "p", "am": "2026-09-14"}})
        self.assertEqual(pruefung.leer()["doppelt"], {})


if __name__ == "__main__":
    unittest.main()
