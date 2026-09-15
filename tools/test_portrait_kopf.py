# -*- coding: utf-8 -*-
"""The portrait belongs in the head of the edit form, not at its end.

Giving somebody a picture used to mean scrolling past names, dates, places,
family and the whole life story to a section called "Foto" near the bottom.
Now the picture sits left of the name, with a button to pick one and a button
to take it away.

These tests read the template, because what they guard is where things are in
the markup - the behaviour behind the buttons is the same as before.

    python tools/test_portrait_kopf.py
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


class TestPortraitImKopf(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()
        f = re.search(r'function formHTML\(\)\{(.*?)\n\}', self.s, re.S)
        self.assertIsNotNone(f, "formHTML gibt es nicht mehr")
        self.form = f.group(1)
        k = re.search(r'function portraitHeadHTML\(p\)\{(.*?)\n\}', self.s, re.S)
        self.assertIsNotNone(k, "portraitHeadHTML gibt es nicht mehr")
        self.kopf = k.group(1)

    def test_das_portrait_steht_vor_dem_namen(self):
        head = re.search(r'<div class="sheet-head">(.*?)id="editTitle"', self.form, re.S)
        self.assertIsNotNone(head, "der Kopf des Formulars hat kein Portrait vor dem Namen")
        self.assertIn("portraitHeadHTML(draft)", head.group(1))

    def test_der_abschnitt_foto_ist_weg(self):
        self.assertNotIn("<h3>Foto</h3>", self.form,
                         "der alte Abschnitt Foto steht noch unten im Formular")
        self.assertNotIn('data-upload="foto"', self.form.replace("portraitHeadHTML", ""),
                         "Bild waehlen steht noch ausserhalb des Kopfes")

    def test_beide_knoepfe_mit_namen_fuer_die_tastatur(self):
        self.assertRegex(self.kopf, r'class="shotbtn" data-upload="foto"[^>]*aria-label="Bild wählen"')
        self.assertRegex(self.kopf, r'class="shotbtn" data-clearphoto="1"[^>]*aria-label="Bild entfernen"',)
        self.assertNotRegex(self.kopf, r'class="shotbtn"[^>]*tabindex="-1"',
                            "ein Knopf im Kopf ist per Tastatur nicht erreichbar")

    def test_entfernen_nur_wenn_ein_bild_da_ist(self):
        self.assertIn('has ? "" : " disabled"', self.kopf)

    def test_der_hinweis_wandert_in_den_tooltip(self):
        self.assertIn("data/photos/", self.kopf)

    def test_die_initialen_bleiben_ohne_bild(self):
        self.assertIn('avatarHTML(p, "portrait")', self.kopf)

    def test_das_portrait_ist_klein(self):
        self.assertIn(".headshot .portrait{width:64px;height:82px", self.s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
