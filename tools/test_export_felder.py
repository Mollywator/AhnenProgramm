# -*- coding: utf-8 -*-
"""What the export lets out of the house before anybody ticks anything.

Two promises:

  * Only life dates, places and family are ticked in advance.  Everything else
    goes out because somebody ticked it, not because nobody looked.
  * Contact details go out line by line.  Ticking only the e-mail address means
    the telephone number, the mobile number and the address are cut out of the
    data - not merely left out of the printout.

The names are invented.

    python tools/test_export_felder.py
"""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edits as person_lib          # noqa: E402
import export                       # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")

KONTAKT = {"phone": "0000 111", "mobile": "0000 222",
           "email": "wiebke@beispiel.invalid", "address": "Am Deich 1"}


def daten():
    person = person_lib.fill_missing({"id": 1, "name": "Wiebke Tannhausen",
                                      "contact": dict(KONTAKT)})
    return {"meta": {}, "people": [person], "marriages": [], "checks": []}


def felder(**extra):
    return dict({"lebensdaten": True, "orte": True, "familie": True}, **extra)


class TestVorauswahl(unittest.TestCase):

    def test_nur_lebensdaten_orte_familie_sind_vorab_an(self):
        with open(VORLAGE, encoding="utf-8") as fh:
            s = fh.read()
        block = re.search(r"const EXPORT_FIELDS = \[(.*?)\];", s, re.S)
        self.assertIsNotNone(block, "EXPORT_FIELDS gibt es nicht mehr")
        an = re.findall(r'\["(\w+)",[^\]]*,\s*true\]', block.group(1))
        self.assertEqual(an, ["lebensdaten", "orte", "familie"])

    def test_kontaktteile_sind_vorab_aus(self):
        with open(VORLAGE, encoding="utf-8") as fh:
            s = fh.read()
        block = re.search(r"const EXPORT_CONTACT = \[(.*?)\];", s, re.S)
        self.assertIsNotNone(block, "die Kontakt-Unterauswahl fehlt")
        self.assertEqual(re.findall(r'\["(\w+)"', block.group(1)),
                         list(export.CONTACT_PARTS))
        self.assertIn('box("kontakt_" + key, label, false)', s)


class TestKontaktEinzeln(unittest.TestCase):

    def test_nur_email_gewaehlt(self):
        out = export.trim(daten(), felder(kontakt=True, kontakt_email=True))
        self.assertEqual(out["people"][0]["contact"], {"email": KONTAKT["email"]})

    def test_nur_email_auch_im_buch(self):
        out = export.trim(daten(), felder(kontakt=True, kontakt_email=True))
        eintrag = export.person_entry(out["people"][0], {}, {1: out["people"][0]},
                                      felder(kontakt=True, kontakt_email=True))
        self.assertIn(KONTAKT["email"], eintrag)
        for wert in ("phone", "mobile", "address"):
            self.assertNotIn(KONTAKT[wert], eintrag)

    def test_hauptschalter_aus_nimmt_alles(self):
        out = export.trim(daten(), felder(kontakt=False, kontakt_email=True,
                                          kontakt_telefon=True))
        self.assertIsNone(out["people"][0]["contact"])

    def test_hauptschalter_an_ohne_teile_nimmt_alles(self):
        out = export.trim(daten(), felder(kontakt=True))
        self.assertIsNone(out["people"][0]["contact"])

    def test_alle_teile_gewaehlt(self):
        out = export.trim(daten(), felder(kontakt=True, kontakt_telefon=True,
                                          kontakt_mobil=True, kontakt_email=True,
                                          kontakt_anschrift=True))
        self.assertEqual(out["people"][0]["contact"], KONTAKT)

    def test_das_original_bleibt_unberuehrt(self):
        d = daten()
        export.trim(d, felder(kontakt=True, kontakt_email=True))
        self.assertEqual(d["people"][0]["contact"], KONTAKT)


if __name__ == "__main__":
    unittest.main()
