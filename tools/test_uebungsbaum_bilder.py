# -*- coding: utf-8 -*-
"""The practice tree comes with portraits: four stick figures, two per sex."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import zweig  # noqa: E402


class TestUebungsbaumBilder(unittest.TestCase):

    def test_jede_person_hat_ein_bild_passend_zum_geschlecht(self):
        for p in zweig.uebungsbaum():
            self.assertIn(p["photo"], zweig.STRICHMAENNCHEN[p["sex"]])

    def test_beide_bilder_je_geschlecht_kommen_vor(self):
        benutzt = {p["photo"] for p in zweig.uebungsbaum()}
        self.assertEqual(benutzt, set(sum(zweig.STRICHMAENNCHEN.values(), [])))

    def test_die_vier_bilder_werden_gezeichnet(self):
        with tempfile.TemporaryDirectory() as ordner:
            zweig.strichmaennchen(ordner)
            self.assertEqual(sorted(os.listdir(ordner)),
                             sorted(sum(zweig.STRICHMAENNCHEN.values(), [])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
