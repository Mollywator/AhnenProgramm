# -*- coding: utf-8 -*-
"""Back and forward between people, the way a browser does it.

The two arrows live in the line under the tree's name, and three ways lead to
the same `navGo`: the arrows, the side buttons of a mouse, and Alt+arrow.  What
is held open here is that each of those is still wired, that both places a
person is looked at - the centre and the sheet - still leave a step behind, and
that the arrows did not wander off into the tools on the right.

Like `test_verknuepfen_knopf.py` this reads the template rather than a browser.

    python tools/test_zurueck.py
"""
from __future__ import annotations

import os
import re
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")


def vorlage() -> str:
    with open(VORLAGE, encoding="utf-8") as fh:
        return fh.read()


def funktion(s: str, name: str) -> str:
    m = re.search(r"function " + name + r"\(.*?\n\}", s, re.S)
    assert m, "function %s is gone" % name
    return m.group(0)


class TestZurueck(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_pfeile_stehen_unter_dem_namen(self):
        kopf = re.search(r'<h1 id="mastTitle"></h1>(.*?)<div class="tools">', self.s, re.S)
        self.assertIsNotNone(kopf)
        self.assertIn('id="navBack"', kopf.group(1))
        self.assertIn('id="navFwd"', kopf.group(1))
        self.assertIn('id="sub"', kopf.group(1))
        self.assertLess(kopf.group(1).index('id="navBack"'), kopf.group(1).index('id="sub"'),
                        "die Pfeile gehoeren links vor den Text")

    def test_mittelpunkt_und_blatt_hinterlassen_einen_schritt(self):
        self.assertIn("navRecord(", funktion(self.s, "setCentre"))
        self.assertIn("navRecord(", funktion(self.s, "openSheet"))

    def test_zurueckgehen_schreibt_keinen_neuen_schritt(self):
        self.assertIn("nav.busy = true", funktion(self.s, "navGo"))
        self.assertIn("if(nav.busy", funktion(self.s, "navRecord"))

    def test_ungespeichertes_fragt_zuerst(self):
        self.assertIn("editGuard(go)", funktion(self.s, "navGo"))

    def test_alle_drei_wege_sind_verdrahtet(self):
        self.assertRegex(self.s, r'getElementById\("navBack"\)\.addEventListener\("click", \(\) => navGo\(-1\)\)')
        self.assertRegex(self.s, r'getElementById\("navFwd"\)\.addEventListener\("click", \(\) => navGo\(1\)\)')
        self.assertIn("e.button !== 3 && e.button !== 4", self.s)
        self.assertIn('e.key === "BrowserBack"', self.s)
        self.assertIn('e.altKey && (e.key === "ArrowLeft"', self.s)


if __name__ == "__main__":
    unittest.main()
