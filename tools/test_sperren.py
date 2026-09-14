# -*- coding: utf-8 -*-
"""The lock beside "Alle", and sheets whose explanation scrolls with the text.

Locked, a click on a box opens that person's sheet and leaves the centre where
it is, so a near family can be set up once and then clicked through.  And every
sheet keeps only its title in the sticky head: the explanations under it used
to ride along and cover half of a short window.

Like `test_zurueck.py` this reads the template rather than a browser.

    python tools/test_sperren.py
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


class TestSperren(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_knopf_steht_neben_alle(self):
        modes = self.s.index('<div class="modes" id="modes">')
        alle = self.s.index('data-mode="alle"', modes)
        knopf = self.s.index('id="lockBtn"')
        zoom = self.s.index('<div class="zoom">')
        self.assertLess(alle, knopf)
        self.assertLess(knopf, zoom)

    def test_gesperrt_oeffnet_das_blatt_statt_mittelpunkt(self):
        sperre = self.s.index("if(node && locked")
        mitte = self.s.index("if(node){ holdInPlace(")
        self.assertLess(sperre, mitte, "the lock has to answer before the centre moves")
        zeile = self.s[sperre:self.s.index("\n", sperre)]
        self.assertIn("openSheet(", zeile)
        self.assertNotIn("setCentre(", zeile)


class TestNurDerTitelKlebt(unittest.TestCase):

    def test_koepfe_tragen_nur_kicker_und_titel(self):
        s = vorlage()
        koepfe = []
        for stueck in s.split('<div class="sheet-head"')[1:]:
            body, foot = stueck.find('class="sheet-body'), stueck.find('class="sheet-foot')
            # the unsaved-work question has no body to scroll - it is all head
            if body < 0 or (0 <= foot < body):
                continue
            koepfe.append(stueck[:body])
        self.assertGreater(len(koepfe), 10)
        for kopf in koepfe:
            for fremd in ('class="legend"', 'class="node-meta"', "portrait", "<p"):
                self.assertNotIn(fremd, kopf, "only the title belongs in a sticky head")


if __name__ == "__main__":
    unittest.main(verbosity=2)
