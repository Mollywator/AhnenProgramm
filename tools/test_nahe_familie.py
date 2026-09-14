# -*- coding: utf-8 -*-
"""Who the near view reaches, and who "Alle" keeps.

Three things that went wrong together:

* The one nephew box was labelled "Angeheiratete Neffen und Nichten" but drew
  the children of the centre's OWN brothers and sisters - blood family - and
  was off by default.  Blood nephews are now on by default; the married-in ones
  (children of the partner's siblings) are a box of their own, off.
* The ▾ beside "Nahe Familie" sat flush against "Ahnentafel" and read as that
  button's menu.
* A person linked into a second tree takes her children along as her
  relatives.  "Alle" over there dropped them unless her partner came too -
  from the user's side: the children were not taken over.

Read from the template, like the other page tests: what broke were rules in
the page, not the data.

    python tools/test_nahe_familie.py
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


class TestNaheFamilie(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def _box(self, key):
        m = re.search(r'<input type="checkbox" data-near="%s"([^>]*)>' % key, self.s)
        self.assertIsNotNone(m, "im Menue fehlt der Haken %s" % key)
        return m.group(1)

    def test_blutsverwandte_neffen_sind_vorangehakt(self):
        self.assertIn("checked", self._box("neffen"))
        self.assertRegex(self.s, r"const nearExtra = \{[^}]*neffen: true")

    def test_angeheiratete_neffen_sind_nicht_vorangehakt(self):
        self.assertNotIn("checked", self._box("neffenAngeheiratet"))
        self.assertRegex(self.s, r"const nearExtra = \{[^}]*neffenAngeheiratet: false")

    def test_die_beiden_haken_sind_richtig_beschriftet(self):
        self.assertRegex(self.s, r'data-near="neffen" checked> Neffen und Nichten<')
        self.assertRegex(self.s, r'data-near="neffenAngeheiratet"> Angeheiratete Neffen und Nichten<')

    def test_angeheiratete_neffen_haengen_am_schwager(self):
        self.assertIn('neffenAngeheiratet: "schwager"', self.s)
        self.assertIn("nearExtra.schwager && nearExtra.neffenAngeheiratet", self.s)

    def test_das_dreieck_gehoert_zur_nahen_familie(self):
        wrap = re.search(r'<span class="modewrap split">\s*<button[^>]*data-mode="nah"', self.s)
        self.assertIsNotNone(wrap, "der Pfeil steckt nicht mehr mit Nahe Familie zusammen")
        self.assertIn(".modewrap.split{gap:0;margin-right:", self.s)


class TestAlleBehaeltDieKinder(unittest.TestCase):

    def test_kinder_eigener_personen_bleiben_in_alle(self):
        s = vorlage()
        funktion = re.search(r"function alleSet\(\)\{(.*?)\n\}", s, re.S)
        self.assertIsNotNone(funktion, "alleSet gibt es nicht mehr")
        koerper = funktion.group(1)
        self.assertIn(".children", koerper.split("const married")[0],
                      "Alle geht von den eigenen Personen nicht mehr zu ihren Kindern hinunter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
