# -*- coding: utf-8 -*-
"""Options that outlive a restart - kept with the program, not in the browser.

The editor's window gets a new port on every start, and the browser files what
it remembers under the port.  So Tageslicht/Abendlicht is written into
`einstellungen.json`, and the copy handed around keeps using the browser.

    python tools/test_optionen.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)


def lesen(name: str) -> str:
    with open(os.path.join(HIER, name), encoding="utf-8") as fh:
        return fh.read()


class TestLichtBleibt(unittest.TestCase):

    def setUp(self):
        # A throwaway data folder, so nothing here touches a real family.
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["AHNEN_DATEN"] = self.tmp.name
        self.store = self._neu_starten()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("AHNEN_DATEN", None)
        sys.modules.pop("store", None)

    def _neu_starten(self):
        """The module thrown away and loaded again, as a fresh start would."""
        sys.modules.pop("store", None)
        import store
        return store

    def test_nie_gewaehlt(self):
        self.assertIsNone(self.store.theme())

    def test_abendlicht_ueberlebt_den_neustart(self):
        self.store.remember(theme="abend")
        self.assertEqual(self._neu_starten().theme(), "abend")

    def test_zurueck_auf_tageslicht(self):
        self.store.remember(theme="abend")
        self.store.remember(theme="tag")
        self.assertEqual(self._neu_starten().theme(), "tag")

    def test_unsinn_zaehlt_nicht(self):
        self.store.remember(theme="lila")
        self.assertIsNone(self.store.theme())

    def test_andere_einstellungen_bleiben(self):
        self.store.remember(stationen_auto=False)
        self.store.remember(theme="abend")
        self.assertFalse(self.store.stationen_auto())


class TestServerUndSeite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = lesen("edit_server.py")
        cls.seite = lesen("template.html")

    def test_server_gibt_und_nimmt_das_licht(self):
        self.assertIn('"theme": store.theme()', self.server)
        self.assertIn('payload.get("theme") in store.THEMES', self.server)

    def test_licht_steht_im_kopf_vor_dem_zeichnen(self):
        kopf = self.seite.split("</head>", 1)[0]
        self.assertIn('localStorage.getItem("stammbaum-theme")', kopf)
        self.assertIn("setAttribute('data-theme',", self.server)

    def test_editor_speichert_beim_programm(self):
        self.assertIn('api("/api/einstellung?k=" + encodeURIComponent(EDIT.token), {theme})',
                      self.seite)

    def test_weitergegebene_datei_bleibt_beim_browser(self):
        self.assertIn('localStorage.setItem("stammbaum-theme", theme)', self.seite)

    def test_das_bin_ich_im_editor_im_baum(self):
        # Already tree-bound: meta.root, saved through /api/set-root.  Only the
        # copy without a program keeps it in the reader's browser.
        self.assertIn("if(IS_EDIT) return DATA.meta.root", self.seite)
        self.assertIn('route == "/api/set-root"', self.server)

    def test_druck_bleibt_hell(self):
        self.assertIn('root.setAttribute("data-theme", "tag");', self.seite)


if __name__ == "__main__":
    unittest.main(verbosity=2)
