# -*- coding: utf-8 -*-
"""The name check as a test - run only when asked for.

The check itself is `tools/namenspruefung.py`; its docstring says how it finds
the names without ever holding a list of them, and why it never prints one.

It has to read the family's data folder to do its job, and that folder is off
limits to everything else that runs the test suite - an assistant working in a
worktree, a build server, a fresh clone.  So a plain `pytest` skips it, and it
runs only when the person who keeps the trees sets `AHNEN_NAMENSPRUEFUNG=1`,
or calls the checker directly.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import namenspruefung  # noqa: E402


@unittest.skipUnless(os.environ.get("AHNEN_NAMENSPRUEFUNG") == "1",
                     "Namenspruefung nur auf Wunsch: AHNEN_NAMENSPRUEFUNG=1 setzen "
                     "oder python tools/namenspruefung.py starten")
class TestKeineNamenImRepo(unittest.TestCase):

    def test_kein_name_aus_dem_stammbaum_steht_im_quelltext(self):
        muster = namenspruefung.muster_fuer(namenspruefung.namen_aus_dem_datenordner())
        if muster is None:
            self.skipTest("kein Datenordner auf diesem Rechner - "
                          "es gibt nichts, wogegen geprueft werden koennte")
        funde = namenspruefung.pruefen(namenspruefung.WURZEL, muster)
        self.assertEqual(
            funde, [],
            "In diesen Zeilen steht ein Name aus deinem Stammbaum. "
            "Der Name wird hier absichtlich nicht genannt - sieh an der Stelle nach:\n  "
            + "\n  ".join(funde))


class TestErsetzer(unittest.TestCase):
    """The replacing half, against invented names - no data folder involved."""

    def test_gleicher_name_gleiche_nummer(self):
        muster = namenspruefung.muster_fuer({"Quastmann", "Ottilie"})
        text, anzahl = namenspruefung.Ersetzer(muster).text(
            "Ottilie Quastmann und quastmann, nicht Quastmannshof")
        self.assertEqual(anzahl, 3)
        self.assertEqual(text, "Person 1 Person 2 und Person 2, nicht Quastmannshof")

    def test_harmlose_woerter_zaehlen_nicht(self):
        for wort in ("Stammbaum", "Familie", "Frau", "Herr", "Mark", "Post"):
            self.assertIn(wort.casefold(), namenspruefung.HARMLOS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
