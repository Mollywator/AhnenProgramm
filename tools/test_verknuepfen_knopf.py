# -*- coding: utf-8 -*-
"""The link button has to be FINDABLE - which is not the same as present.

It was built into the edit form, one level below the person sheet, and hidden
entirely while only one tree existed.  Both were wrong in the same way: the
person who has one tree and has never linked anything is exactly the person the
feature is for, and they will never go looking inside a form for it.

These tests read the template rather than a running browser, because what broke
was a condition in the markup, not behaviour at runtime.
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


class TestVerknuepfenKnopf(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_der_knopf_steht_im_personenblatt(self):
        """Where it was looked for: the sheet, next to Bearbeiten."""
        kopf = re.search(r'data-edit-person="\$\{p\.id\}">Bearbeiten</button>(.{0,400})',
                         self.s, re.S)
        self.assertIsNotNone(kopf, "der Bearbeiten-Knopf im Blatt ist weg")
        self.assertIn("linkButtonHTML(p)", kopf.group(1),
                      "im Personenblatt fehlt der Verknuepfen-Knopf")

    def test_der_knopf_steht_auch_im_formular(self):
        self.assertIn("linkButtonHTML(draft)", self.s,
                      "im Bearbeiten-Formular fehlt der Verknuepfen-Knopf")

    def test_ein_einziger_baum_versteckt_den_knopf_nicht(self):
        """The regression itself: `if(!others.length) return ""` made the whole
        feature undiscoverable until somebody already had two trees."""
        funktion = re.search(r'function linkButtonHTML\(p\)\{(.*?)\n\}', self.s, re.S)
        self.assertIsNotNone(funktion, "linkButtonHTML gibt es nicht mehr")
        koerper = funktion.group(1)
        self.assertNotIn("others", koerper,
                         "der Knopf haengt wieder davon ab, wie viele Baeume es gibt")
        self.assertIn("data-linkopen", koerper)

    def test_ohne_zweiten_baum_bietet_der_dialog_einen_an(self):
        self.assertIn("linkNeuerBaum", self.s,
                      "der Dialog bietet keinen zweiten Stammbaum an")
        self.assertIn("neuerBaumFuerLink", self.s,
                      "es gibt keine Funktion, die den zweiten Baum anlegt")

    def test_das_anlegen_wirft_die_offene_verknuepfung_nicht_weg(self):
        """`newTree()` reloads the page; doing that from inside the dialog
        would discard the half-filled link the user is standing in."""
        f = re.search(r'async function neuerBaumFuerLink\(\)\{(.*?)\n\}', self.s, re.S)
        self.assertIsNotNone(f)
        self.assertNotIn("location.reload", f.group(1),
                         "das Anlegen laedt die Seite neu und verliert den Dialog")
        self.assertIn("refreshLinkPreview", f.group(1),
                      "nach dem Anlegen wird die Vorschau nicht aktualisiert")

    def test_das_anlegen_bleibt_im_aktuellen_baum(self):
        """api_new switches the open tree to the new one - the dialog belongs
        to the tree it was opened from and has to switch back."""
        f = re.search(r'async function neuerBaumFuerLink\(\)\{(.*?)\n\}', self.s, re.S)
        self.assertIn("/api/open-tree", f.group(1),
                      "nach dem Anlegen wird nicht in den Ausgangsbaum zurueckgewechselt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
