# -*- coding: utf-8 -*-
"""Merging two records of one person, and taking it back.

Every name here is invented.
"""
from __future__ import annotations

import copy
import datetime
import os
import sys
import tempfile
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

import edits as person_lib  # noqa: E402
import papierkorb  # noqa: E402
import zusammenfuehren as z  # noqa: E402


def person(pid, name, **felder):
    p = person_lib.blank_person(pid)
    p["name"] = name
    p.update(felder)
    return p


def baum():
    people = [
        person(1, "Zorbas Quendel", sex="m", spouses=[2]),
        person(2, "Wemke Quendel", sex="w", spouses=[1]),
        person(3, "Ilvi Quendel", sex="w", parents=[1, 2], occupation="Bäuerin", bio="Text A",
               birth={"year": 1704}),
        person(6, "Ilvi Quendel", sex="w", parents=[1], spouses=[7], occupation="Magd",
               bio="Text B", birth={"year": 1704}, notes=["aus Kirchenbuch"],
               documents=[{"file": "brief.pdf", "title": "Brief"}]),
        person(7, "Xaver Grumbach", sex="m", spouses=[6],
               events=[{"kind": "Heirat", "year": 1725, "with": [6]}]),
        person(8, "Nepomuk Grumbach", sex="m", parents=[6, 7], parent_kind={"6": "blood"}),
    ]
    tree = {"meta": {"root": 6}, "people": people,
            "marriages": [{"people": [6, 7], "year": 1725}]}
    person_lib.normalise_links(tree["people"])
    return tree


def nach_id(tree):
    return {p["id"]: p for p in tree["people"]}


WAHL = {"occupation": "entfernt", "bio": "beide"}


class TestZusammenfuehren(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.docs = os.path.join(self.tmp.name, "dokumente")
        os.makedirs(os.path.join(self.docs, "6"))
        with open(os.path.join(self.docs, "6", "brief.pdf"), "w") as fh:
            fh.write("x")

    def test_ohne_entscheidung_passiert_nichts(self):
        tree = baum()
        vorher = copy.deepcopy(tree)
        with self.assertRaises(ValueError) as fehler:
            z.ausfuehren(tree, 3, 6, {"occupation": "entfernt"}, self.docs)
        self.assertIn("Originaltext", str(fehler.exception))
        self.assertEqual(tree, vorher)
        self.assertTrue(os.path.isfile(os.path.join(self.docs, "6", "brief.pdf")))

    def test_alles_landet_bei_der_bleibenden_nummer(self):
        tree = baum()
        e = z.ausfuehren(tree, 3, 6, WAHL, self.docs)
        person_lib.normalise_links(tree["people"])
        p = nach_id(tree)
        self.assertNotIn(6, p)
        self.assertEqual(p[3]["occupation"], "Magd")
        self.assertEqual(p[3]["bio"], "Text A\n\nText B")
        self.assertEqual(p[3]["parents"], [1, 2])
        self.assertEqual(p[3]["spouses"], [7])
        self.assertEqual(p[3]["notes"], ["aus Kirchenbuch"])
        self.assertEqual(p[7]["spouses"], [3])
        self.assertEqual(p[7]["events"][0]["with"], [3])
        self.assertEqual(p[8]["parents"], [3, 7])
        self.assertEqual(p[8]["parent_kind"], {"3": "blood"})
        self.assertEqual(tree["marriages"][0]["people"], [3, 7])
        self.assertEqual(tree["meta"]["root"], 3)
        self.assertTrue(os.path.isfile(os.path.join(self.docs, "3", "brief.pdf")))
        self.assertEqual(p[3]["documents"], [{"file": "brief.pdf", "title": "Brief"}])
        self.assertEqual(e["felder"]["occupation"], "entfernt")
        self.assertEqual(e["felder"]["birth"], "gleich")
        self.assertEqual(e["felder"]["notes"], "nur_entfernt")
        # Zorbas reaches #6 only through `children`, which is rebuilt on saving
        self.assertEqual(sorted(e["verwandte"]), ["7", "8"])

    def test_belegter_dateiname_wird_umbenannt(self):
        os.makedirs(os.path.join(self.docs, "3"))
        with open(os.path.join(self.docs, "3", "brief.pdf"), "w") as fh:
            fh.write("a")
        tree = baum()
        z.ausfuehren(tree, 3, 6, WAHL, self.docs)
        self.assertTrue(os.path.isfile(os.path.join(self.docs, "3", "brief (2).pdf")))
        self.assertEqual(nach_id(tree)[3]["documents"][0]["file"], "brief (2).pdf")

    def test_hindernisse(self):
        tree = baum()
        self.assertIn("Elternteil und Kind", z.hindernis(tree, 6, 8))
        nach_id(tree)[6]["link"] = {"slug": "anderer"}
        self.assertIn("muss deshalb", z.hindernis(tree, 3, 6))
        self.assertIsNone(z.hindernis(tree, 6, 3))
        nach_id(tree)[3]["link"] = {"slug": "dritter"}
        self.assertIn("Beide", z.hindernis(tree, 6, 3))
        self.assertIn("nicht", z.hindernis(tree, 3, 99))

    def zusammen_und_gespeichert(self, tree):
        e = z.ausfuehren(tree, 3, 6, WAHL, self.docs)
        person_lib.normalise_links(tree["people"])
        z.nachher_merken(e, tree)
        return e

    def test_rueckgaengig_stellt_alles_wieder_her(self):
        tree = baum()
        original = copy.deepcopy(tree)
        e = self.zusammen_und_gespeichert(tree)
        out = z.rueckgaengig(tree, e, self.docs)
        person_lib.normalise_links(tree["people"])
        self.assertEqual(out["nummer"], 6)
        self.assertEqual(out["hinweise"], [])
        gleich = lambda t: sorted(t["people"], key=lambda p: p["id"])  # noqa: E731
        self.assertEqual(gleich(tree), gleich(original))
        self.assertEqual(tree["marriages"], original["marriages"])
        self.assertEqual(tree["meta"]["root"], 6)
        self.assertTrue(os.path.isfile(os.path.join(self.docs, "6", "brief.pdf")))
        self.assertFalse(os.path.exists(os.path.join(self.docs, "3", "brief.pdf")))

    def test_spaetere_aenderung_an_einem_verwandten_bleibt(self):
        tree = baum()
        e = self.zusammen_und_gespeichert(tree)
        nach_id(tree)[8]["occupation"] = "Schmied"
        out = z.rueckgaengig(tree, e, self.docs)
        person_lib.normalise_links(tree["people"])
        p = nach_id(tree)
        self.assertEqual(p[8]["occupation"], "Schmied")
        self.assertEqual(p[8]["parents"], [6, 7], "an der alten Stelle, nicht hinten angehaengt")
        self.assertEqual(p[8]["parent_kind"], {"6": "blood"})
        self.assertEqual(p[3]["occupation"], "Bäuerin")
        self.assertEqual(out["hinweise"], [])

    def test_aenderung_an_der_bleibenden_person_wird_genannt(self):
        tree = baum()
        e = self.zusammen_und_gespeichert(tree)
        nach_id(tree)[3]["religion"] = "evangelisch"
        out = z.rueckgaengig(tree, e, self.docs)
        self.assertTrue(any("Konfession" in h for h in out["hinweise"]))

    def test_vergebene_nummer_bekommt_eine_neue(self):
        tree = baum()
        e = self.zusammen_und_gespeichert(tree)
        tree["people"].append(person(6, "Brumm Pimpernell"))
        out = z.rueckgaengig(tree, e, self.docs)
        person_lib.normalise_links(tree["people"])
        neu = out["nummer"]
        self.assertEqual(neu, person_lib.FIRST_NEW_ID)
        p = nach_id(tree)
        self.assertEqual(p[neu]["name"], "Ilvi Quendel")
        self.assertIn(neu, p[8]["parents"])
        self.assertEqual(p[7]["spouses"], [neu])
        self.assertTrue(os.path.isfile(os.path.join(self.docs, str(neu), "brief.pdf")))


class TestPapierkorb(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def eintrag(self, tage_alt):
        am = datetime.date(2026, 9, 14) - datetime.timedelta(days=tage_alt)
        return {"id": "z-%d" % tage_alt, "am": am.isoformat() + "T10:00:00",
                "behalten": 3, "entfernt": 6, "vorher": {}}

    def test_nach_60_tagen_weg(self):
        heute = datetime.date(2026, 9, 14)
        daten = papierkorb.bereinigen({"eintraege": [self.eintrag(59), self.eintrag(60),
                                                     self.eintrag(61)]}, heute)
        self.assertEqual([e["id"] for e in daten["eintraege"]], ["z-59", "z-60"])
        self.assertEqual(papierkorb.tage_uebrig(self.eintrag(59), heute), 1)

    def test_kaputte_datei_ist_leer(self):
        with open(os.path.join(self.tmp.name, papierkorb.NAME), "w", encoding="utf-8") as fh:
            fh.write("{ kaputt")
        self.assertEqual(papierkorb.laden(self.tmp.name), papierkorb.leer())

    def test_hinzufuegen_und_finden(self):
        e = self.eintrag(0)
        e["am"] = datetime.datetime.now().isoformat(timespec="seconds")
        papierkorb.hinzufuegen(self.tmp.name, e)
        self.assertEqual(papierkorb.finden(papierkorb.laden(self.tmp.name), e["id"])["behalten"], 3)


class TestServer(unittest.TestCase):

    def test_routen_und_zustand(self):
        with open(os.path.join(HIER, "edit_server.py"), encoding="utf-8") as fh:
            server = fh.read()
        self.assertIn('route == "/api/zusammenfuehren"', server)
        self.assertIn('route == "/api/zusammenfuehren-rueckgaengig"', server)
        self.assertIn('"papierkorb": papierkorb.laden(', server)
        self.assertIn('"zusammenfuehrenFelder"', server)


if __name__ == "__main__":
    unittest.main()
