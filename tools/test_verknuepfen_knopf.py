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


class TestAngeheirateteSeiteImDialog(unittest.TestCase):
    """The married-in groups are only useful if the dialog stays honest.

    Two things can go wrong and neither shows up in the Python tests: the page
    starts hard-coding the group list again, so a group added in
    `verknuepfung.GRUPPEN` never reaches a checkbox - and the in-law boxes get
    ticked without the partner they hang off, which drops people into the other
    tree with no line to anybody.
    """

    def setUp(self):
        self.s = vorlage()

    def test_die_gruppen_kommen_vom_programm_nicht_aus_der_seite(self):
        self.assertIn("EDIT.linkGruppen", self.s)
        for gruppe in ("spouse_parents", "spouse_siblings", "spouse_children"):
            self.assertNotIn('"%s"' % gruppe, self.s,
                             "die Seite kennt %s auswendig - dann driften "
                             "Seite und Programm auseinander" % gruppe)

    def test_die_angeheiratete_seite_ist_nicht_vorangehakt(self):
        f = re.search(r'function openLinkDialog\(id\)\{(.*?)\n\}', self.s, re.S)
        self.assertIsNotNone(f, "openLinkDialog gibt es nicht mehr")
        self.assertIn("g.vorgabe", f.group(1),
                      "der Dialog hakt wieder alle Gruppen an - damit reist "
                      "eine zweite Familie mit, ohne dass jemand hinsah")

    def test_wer_die_schwiegereltern_will_nimmt_die_ehepartner_mit(self):
        f = re.search(r'data-linkgruppe\]"\);(.*?)refreshLinkPreview\(\);', self.s, re.S)
        self.assertIsNotNone(f, "die Gruppen-Checkboxen haben keinen Handler mehr")
        koerper = f.group(1)
        self.assertIn('gewaehlt = ["spouses"].concat(gewaehlt)', koerper,
                      "die angeheiratete Seite reist ohne den Ehepartner, an "
                      "dem sie haengt")
        self.assertIn("angeheiratet.includes(g)", koerper,
                      "der Ehepartner laesst sich abwaehlen und seine Familie "
                      "bleibt angehakt")


class TestVorschauBleibtWahr(unittest.TestCase):
    """The preview is what somebody decides on, so it must not lag behind.

    Every ticked box asks the server again, and the replies do not have to
    arrive in the order they were asked.  Four quick clicks used to leave the
    answer to the FIRST one on screen - a list naming fewer people than would
    actually travel.
    """

    def test_nur_die_neueste_antwort_darf_schreiben(self):
        f = re.search(r'async function refreshLinkPreview\(\)\{(.*?)\n\}',
                      vorlage(), re.S)
        self.assertIsNotNone(f, "refreshLinkPreview gibt es nicht mehr")
        koerper = f.group(1)
        self.assertIn("linkVorschauLauf", koerper,
                      "die Vorschau zaehlt ihre Fragen nicht mehr durch - eine "
                      "alte Antwort kann die neue ueberschreiben")
        self.assertEqual(koerper.count("lauf !== linkVorschauLauf"), 2,
                         "eine veraltete Antwort wird nicht in beiden Faellen "
                         "verworfen")


if __name__ == "__main__":
    unittest.main(verbosity=2)
