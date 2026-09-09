# -*- coding: utf-8 -*-
"""Tests for how a portrait reaches the screen, and what that costs.

Two ways, and the difference between them is the whole file:

  * The copy handed to the family carries every picture inside it.  It runs
    from `file://` with no program behind it, so a picture that is not in the
    file is a picture that does not exist.

  * The editor has a server behind it and is told where the pictures are.
    Nothing is decoded, nothing is scaled, nothing is base64.  The page arrives
    without them and the browser fetches each one as it comes into view.

That second way is what made a tree of 341 people open in a fraction of the
time: building its page went from half a second to fourteen milliseconds, and
the page from 2,6 MB to 0,74 MB.  It also shows the picture at the size it was
stored in rather than a second, smaller copy - the pictures used to be scaled
down twice, once in the browser on the way in and once again on the way out.

The promises stated here:

  * the family's copy carries its pictures, always
  * the editor's copy carries addresses, and no picture bytes at all
  * a record naming a file that is gone gets no entry either way
  * both ways answer with the same people, so `Mit Foto` and the portrait
    count cannot disagree with each other

Run with the standard library alone, no test runner to install:

    python tools/test_fotos.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_site                     # noqa: E402


def bild(pfad: str, farbe: tuple[int, int, int] = (120, 90, 60)) -> None:
    """A real JPEG on disk, so nothing here passes by accident."""
    try:
        from PIL import Image
    except ImportError:                                     # pragma: no cover
        with open(pfad, "wb") as fh:                        # a byte string is
            fh.write(b"\xff\xd8\xff\xe0not-a-real-jpeg")    # enough for the URL
        return                                              # side of the tests
    Image.new("RGB", (900, 1200), farbe).save(pfad, "JPEG")


class FotoTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fotos = os.path.join(self.tmp.name, "fotos")
        os.makedirs(self.fotos)
        bild(os.path.join(self.fotos, "oma.jpg"))
        bild(os.path.join(self.fotos, "opa mit leerzeichen.jpg"))
        self.people = [
            {"id": 1, "name": "Oma", "photo": "oma.jpg"},
            {"id": 2, "name": "Opa", "photo": "opa mit leerzeichen.jpg"},
            {"id": 3, "name": "Ohne Bild", "photo": None},
            {"id": 4, "name": "Bild ist weg", "photo": "gibtsnicht.jpg"},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------- the two ways
    def test_familie_bekommt_die_bilder_mit(self):
        """The copy handed on has no program behind it, so it carries everything."""
        out = build_site.encode_photos(self.people, self.fotos)
        self.assertEqual({"1", "2"}, set(out))
        for wert in out.values():
            self.assertTrue(wert.startswith("data:image/"),
                            "the family's copy has to carry the bytes")

    def test_editor_bekommt_adressen(self):
        """The editor is told where the picture is, and fetches it itself."""
        out = build_site.photo_urls(self.people, self.fotos)
        self.assertEqual({"1", "2"}, set(out))
        self.assertEqual("/foto/oma.jpg", out["1"])
        for wert in out.values():
            self.assertFalse(wert.startswith("data:"),
                             "no picture bytes may travel in the editor's page")

    def test_leerzeichen_im_namen_wird_verpackt(self):
        """A file name is not a URL until it has been made into one."""
        out = build_site.photo_urls(self.people, self.fotos)
        self.assertEqual("/foto/opa%20mit%20leerzeichen.jpg", out["2"])
        self.assertNotIn(" ", out["2"])

    def test_beide_wege_meinen_dieselben_leute(self):
        """`Mit Foto` and the portrait count are read off this - they must agree."""
        self.assertEqual(set(build_site.encode_photos(self.people, self.fotos)),
                         set(build_site.photo_urls(self.people, self.fotos)))

    def test_fehlende_datei_gibt_keinen_eintrag(self):
        """A name in the record whose file is gone must not become a broken image."""
        for out in (build_site.encode_photos(self.people, self.fotos),
                    build_site.photo_urls(self.people, self.fotos)):
            self.assertNotIn("4", out)
            self.assertNotIn("3", out)

    # ------------------------------------------------------------- the page
    def _seite(self, **kw) -> str:
        tree = {"meta": {"title": "Prüfbaum"}, "people": self.people,
                "marriages": [], "source_titles": {}, "checks": []}
        return build_site.page_html(tree, self.fotos, **kw)

    def test_editor_seite_traegt_keine_bilddaten(self):
        """The point of the whole change, stated as a size.

        Asked about the portrait payload by name rather than about `data:` in
        general: the template legitimately builds a `data:image/svg+xml` of its
        own when it turns the diagram into a PNG, and that has nothing to do
        with whether the portraits travelled inside the page.
        """
        nutzlast = "data:image/jpeg;base64,"
        familie = self._seite()
        editor = self._seite(als_adressen=True)
        self.assertIn(nutzlast, familie,
                      "the family's copy has to carry the portraits")
        self.assertNotIn(nutzlast, editor,
                         "no portrait bytes may travel in the editor's page")
        self.assertIn("/foto/oma.jpg", editor)
        self.assertLess(len(editor), len(familie),
                        "the editor's page has to be the smaller one")

    def test_das_seitenskript_bleibt_gueltig(self):
        """Whatever was changed in the template, the page must still parse."""
        build_site.check_script(self._seite(als_adressen=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
