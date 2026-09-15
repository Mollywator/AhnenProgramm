# -*- coding: utf-8 -*-
"""Typing a date as on paper: 13.08.1921 without the mouse (issue #27).

Like `test_personenblatt.py` these read the template rather than drive a
browser.  What they hold open is where the behaviour is easy to lose again:

  * the separators - `-` was asked for after the first draft, next to `.` and
    `/`, because plenty of people write 13-08-1921;
  * the page-wide "/" shortcut opens the search, so the date handler has to
    answer in the capture phase or a slash typed into a day box moves the caret
    into the search field;
  * padding "8" to "08" on leaving must not turn an untouched form unsaved.

    python tools/test_datumseingabe.py
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


def abschnitt() -> str:
    s = vorlage()
    start = s.index("/* ---- typing a date as on paper")
    ende = s.index("dateSet(el, datePad(el.value.trim()));", start)
    return s[start:ende]


class TestTrennzeichen(unittest.TestCase):

    def setUp(self):
        self.a = abschnitt()

    def test_die_ueblichen_trennzeichen_springen(self):
        muster = re.search(r"const DATE_SEP = /\[(.*?)\]/;", self.a)
        self.assertIsNotNone(muster, "DATE_SEP fehlt")
        for zeichen in (".", "/", "-", ",", " "):
            self.assertIn(zeichen, muster.group(1).replace("\\", ""),
                          "das Trennzeichen %r springt nicht weiter" % zeichen)

    def test_das_trennzeichen_landet_nicht_im_feld(self):
        self.assertIn("e.preventDefault(); e.stopImmediatePropagation();", self.a)

    def test_der_schraegstrich_oeffnet_nicht_die_suche(self):
        """The date keydown runs in the capture phase, ahead of the "/" shortcut."""
        s = vorlage()
        self.assertIn('if(e.key === "/" && document.activeElement.id !== "q")', s)
        stelle = self.a[self.a.index('document.addEventListener("keydown"'):]
        stelle = stelle[:stelle.index('document.addEventListener("input"')]
        self.assertTrue(stelle.rstrip().endswith("}, true);"),
                        "der Datums-Handler laeuft nicht mehr in der Capture-Phase")

    def test_ein_springen_schluckt_den_folgenden_punkt(self):
        self.assertIn("if(dateLanded === el){ dateLanded = null; return; }", self.a)

    def test_ein_springen_schluckt_auch_den_tab(self):
        """A day of 7 jumps by itself; the Tab typed after it must not skip the month."""
        self.assertIn('e.key === "Tab" && !e.shiftKey && dateLanded === el', self.a)

    def test_das_handy_wird_ueber_input_bedient(self):
        self.assertIn("el.value.split(DATE_SEP)", self.a)


class TestVollesFeld(unittest.TestCase):

    def setUp(self):
        self.a = abschnitt()

    def test_zwei_ziffern_oder_eine_unmoegliche_springen(self):
        """Day 4-9 and month 2-9 fill their box alone - typed or pasted."""
        self.assertIn('v !== "" && +v[0] > (i === 0 ? 3 : 1) ? 1 : 2', self.a)
        self.assertIn("const full = !last && v.length === cap;", self.a)

    def test_fuehrende_null(self):
        self.assertIn('/^[1-9]$/.test(v) ? "0" + v : v', self.a)

    def test_auffuellen_macht_das_formular_nicht_geaendert(self):
        self.assertIn("if(dateNum(before) !== dateNum(v))", self.a)

    def test_das_jahr_bleibt_vierstellig(self):
        self.assertIn("const cap = last ? 4 :", self.a)


class TestZurueck(unittest.TestCase):

    def test_ruecktaste_im_leeren_feld(self):
        self.assertIn('e.key === "Backspace" && i > 0 && el.value === ""', abschnitt())


class TestTeildaten(unittest.TestCase):

    def test_die_drei_kaestchen_bleiben(self):
        """Year alone and month plus year stay possible: three boxes, no picker."""
        s = vorlage()
        koerper = s[s.index("function dateField("):s.index("function sexField(")]
        for teil in (".day", ".month", ".year"):
            self.assertIn('data-k="${prefix}%s"' % teil, koerper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
