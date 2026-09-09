# -*- coding: utf-8 -*-
"""Tests for what a format conversion may and may not leave behind.

A conversion is a thing that happens once, to a tree written by an older
program.  It is announced to the person who opened it, and then it is over.

It was not over.  The note saying "this was converted" is kept in `baum.json`,
which is right - the options page shows it, and it should still be there next
year.  What was wrong is that `load` decided whether to save by reading that
same note back.  So it saved.  Every time.  And because `save` writes the name
list, and the name list read the tree, `save` reached itself: about two hundred
rounds deep per open, ended only by Python running out of stack - which two
`except Exception` swallowed without a word.

What it cost: opening a tree of two people took four to seven seconds, one of
341 took twelve, a single save took six, and the twenty rolling backups were
overwritten with twenty copies of the same second, so the real history of a
family's edits was gone.  It arrived with format 2 (the linking release), which
is what first gave the machinery a conversion to perform.

These tests state the promises in the words they were made in:

  * a conversion happens once, however often the tree is opened afterwards
  * the note about it survives in the file, for the page to show
  * loading a tree does not write it
  * nothing in here may ever call itself

Run with the standard library alone, no test runner to install:

    python tools/test_umwandlung.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import format as schema             # noqa: E402


class UmwandlungTest(unittest.TestCase):
    """A throwaway data folder per test, so no real family is ever touched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["AHNEN_DATEN"] = self.tmp.name
        for name in ("store", "namensliste"):
            sys.modules.pop(name, None)
        import store
        self.store = store

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("AHNEN_DATEN", None)
        for name in ("store", "namensliste"):
            sys.modules.pop(name, None)

    # ---------------------------------------------------------------- helpers
    def alter_baum(self, leute: int = 3) -> str:
        """A tree on disk in the oldest shape the program still accepts."""
        slug = self.store.create("Alt", self.store.empty_tree("Alt"))
        pfad = self.store.tree_path(slug)
        with open(pfad, encoding="utf-8") as fh:
            tree = json.load(fh)
        tree["meta"]["format"] = schema.AELTESTE
        tree["people"] = [{"id": i, "name": "Person %d" % i}
                          for i in range(1, leute + 1)]
        with open(pfad, "w", encoding="utf-8") as fh:
            json.dump(tree, fh, ensure_ascii=False, indent=1)
        return slug

    def datei(self, slug: str) -> dict:
        with open(self.store.tree_path(slug), encoding="utf-8") as fh:
            return json.load(fh)

    def zaehle_saves(self):
        """Count calls to `save`, and hand back the counter."""
        n = [0]
        echt = self.store.save

        def gezaehlt(tree, slug=None):
            n[0] += 1
            return echt(tree, slug)

        self.store.save = gezaehlt
        self.addCleanup(setattr, self.store, "save", echt)
        return n

    # ------------------------------------------------------------- the promises
    def test_die_notiz_bleibt_in_der_datei(self):
        """The options page says "last converted" and means it.

        The note is what that section is built from, so it has to survive in
        `baum.json` and reach the page on every later open.  Keeping it was
        never the bug.
        """
        slug = self.alter_baum()
        tree = self.store.load(slug)
        self.assertTrue(tree["meta"]["umgewandelt"])
        self.assertIn("umgewandelt", self.datei(slug)["meta"])

        wieder = self.store.load(slug)
        self.assertEqual(1, wieder["meta"]["umgewandelt"]["von"])
        self.assertEqual(schema.FORMAT, wieder["meta"]["umgewandelt"]["auf"])

    def test_die_notiz_loest_kein_speichern_aus(self):
        """The whole fix, in one assertion.

        A tree that carries the note - every tree converted since format 2 does
        - must open without being written.  Reading the note as a thing to do
        is what made a two-person tree take seven seconds to open.
        """
        slug = self.alter_baum()
        self.store.load(slug)                       # converts once, writes once
        self.assertIn("umgewandelt", self.datei(slug)["meta"],
                      "precondition: the file carries the note")

        n = self.zaehle_saves()
        self.store.load(slug)
        self.assertEqual(0, n[0], "the note must not cause a save")

    def test_zweites_oeffnen_wandelt_nicht_erneut_um(self):
        """Converted once.  The steps do not run again on a tree that is current."""
        slug = self.alter_baum()
        erst = self.store.load(slug)["meta"]["umgewandelt"]["am"]
        wieder = self.store.load(slug)
        self.assertEqual(erst, wieder["meta"]["umgewandelt"]["am"],
                         "a fresh timestamp would mean it converted again")
        self.assertEqual(schema.FORMAT, schema.version(wieder))

    def test_laden_schreibt_nicht(self):
        """Opening a tree leaves the file, and the backups, alone."""
        slug = self.alter_baum()
        self.store.load(slug)                       # the one legitimate write
        pfad = self.store.tree_path(slug)
        sicherung = os.path.join(self.store.tree_dir(slug),
                                 self.store.BACKUP_DIRNAME)
        vorher_datei = os.path.getmtime(pfad)
        vorher_sicherungen = len(os.listdir(sicherung))

        time.sleep(0.01)
        for _ in range(5):
            self.store.load(slug)

        self.assertEqual(vorher_datei, os.path.getmtime(pfad),
                         "load must not rewrite baum.json")
        self.assertEqual(vorher_sicherungen, len(os.listdir(sicherung)),
                         "load must not consume the rolling backups")
        format_sicherung = os.path.join(self.store.tree_dir(slug),
                                        self.store.FORMAT_BACKUP_DIRNAME)
        self.assertEqual(1, len(os.listdir(format_sicherung)),
                         "one conversion is one pre-conversion copy")

    def test_umwandlung_speichert_genau_einmal(self):
        """One conversion, one save - not two hundred."""
        slug = self.alter_baum()
        n = self.zaehle_saves()
        self.store.load(slug)
        self.assertEqual(1, n[0])

    def test_ein_speichern_ist_ein_speichern(self):
        """One save is one save - not two hundred, and not a heap of backups.

        Counted as "at most one more" rather than "exactly one more": the
        backup file is stamped to the second, so two saves inside the same
        second land on the same name.  What this is about is the two hundred.
        """
        slug = self.alter_baum()
        tree = self.store.load(slug)
        sicherung = os.path.join(self.store.tree_dir(slug),
                                 self.store.BACKUP_DIRNAME)
        vorher = len(os.listdir(sicherung))
        n = self.zaehle_saves()

        self.store.save(tree, slug)

        self.assertEqual(1, n[0], "save must not reach itself")
        self.assertLessEqual(len(os.listdir(sicherung)), vorher + 1)

    def test_die_umwandlung_ist_wirklich_passiert(self):
        """None of the above may be bought by skipping the conversion."""
        slug = self.alter_baum()
        tree = self.store.load(slug)
        self.assertEqual(schema.FORMAT, schema.version(self.datei(slug)))
        for person in tree["people"]:
            self.assertIn("link", person)
        sicherung = os.path.join(self.store.tree_dir(slug),
                                 self.store.FORMAT_BACKUP_DIRNAME)
        self.assertTrue(os.listdir(sicherung),
                        "the file as it was has to be put aside first")

    def test_namensliste_wird_geschrieben(self):
        """The index still lands beside the tree, tree handed over or not."""
        import namensliste
        slug = self.alter_baum()
        tree = self.store.load(slug)
        pfad = os.path.join(self.store.tree_dir(slug), namensliste.LIST_FILE)
        self.assertTrue(os.path.isfile(pfad))
        with open(pfad, encoding="utf-8") as fh:
            self.assertIn("Person 1", fh.read())

        os.unlink(pfad)
        namensliste.write(self.store, slug)         # no tree in hand
        with open(pfad, encoding="utf-8") as fh:
            self.assertIn("Person 1", fh.read())

    def test_recursionerror_wird_nicht_verschluckt(self):
        """The tripwire.  A loop here must never be silent again.

        Two `except Exception` around the name list is what kept the old loop
        invisible: it ran two hundred deep, hit the recursion limit, and the
        error went into a `pass`.  `RecursionError` is now let through.
        """
        import namensliste
        echt = namensliste.write

        def kaputt(*args, **kwargs):
            raise RecursionError("maximum recursion depth exceeded")

        namensliste.write = kaputt
        self.addCleanup(setattr, namensliste, "write", echt)
        with self.assertRaises(RecursionError):
            self.store.save(self.store.empty_tree("Laut"), self.alter_baum())


if __name__ == "__main__":
    unittest.main(verbosity=2)
