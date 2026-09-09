# -*- coding: utf-8 -*-
"""Tests for the one part of the program that writes into somebody else's file.

Everything else here edits the tree in front of the user.  Linking does not: it
copies a person into a second family's file and, from then on, every save
writes into both.  A mistake there is not a wrong pixel - it is a wrong or a
missing person in a file nobody was looking at, found weeks later.

So these tests state the promises that were made when it was built, in the
words they were made in:

  * change her once, she is changed everywhere
  * remove a tree and she is still whole in the other one
  * her number, her marriage and her parents stay where they are
  * nothing is ever merged by name
  * a life is added up, not chosen between

Run with the standard library alone, no test runner to install:

    python tools/test_verknuepfung.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edits as person_lib          # noqa: E402
import format as schema             # noqa: E402
import verknuepfung as v            # noqa: E402


def person(pid: int, name: str, **fields) -> dict:
    p = person_lib.blank_person(pid)
    p["name"] = name
    p.update(fields)
    return p


def naechste_id(tree: dict) -> int:
    used = [int(p["id"]) for p in tree.get("people") or []]
    return max([person_lib.FIRST_NEW_ID - 1] + used) + 1


def kleine_familie() -> dict:
    """Two people married, they have a child, and one of them has a parent."""
    return {"meta": {}, "people": [
        person(1, "Person 1",        spouses=[2], children=[3]),
        person(2, "Person 2",      spouses=[1], children=[3], parents=[4]),
        person(3, "Person 3",       parents=[1, 2]),
        person(4, "Person 4", children=[2]),
    ], "marriages": []}


class TestKnuepfen(unittest.TestCase):
    """Carrying a person, and a chosen group, into a second tree."""

    def setUp(self):
        self.quelle = kleine_familie()
        self.ziel = {"meta": {}, "people": [], "marriages": []}
        self.ergebnis = v.knuepfen(
            self.quelle, "baum-a", 1, self.ziel, "baum-b",
            ["spouses", "children"], person_lib.blank_person, naechste_id)
        self.dort = {p["name"]: p for p in self.ziel["people"]}

    def test_die_verknuepfte_person_kommt_an(self):
        self.assertIn("Person 1", self.dort)

    def test_die_angehakten_gruppen_kommen_mit(self):
        self.assertIn("Person 2", self.dort)      # Ehepartner
        self.assertIn("Person 3", self.dort)       # Kinder

    def test_was_nicht_angehakt_war_bleibt_zurueck(self):
        # "Eltern" was not ticked, so the parent stays in his own tree.
        self.assertNotIn("Person 4", self.dort)

    def test_sie_selbst_ist_nicht_geliehen(self):
        # She is in the second tree in her own right - which is what puts her
        # into its "Alle" view.
        self.assertFalse(v.geliehen(self.dort["Person 1"]))

    def test_die_mitgereisten_sind_geliehen(self):
        # They arrived as HER family. This is what keeps a married-in family
        # out of the big views on the far side.
        self.assertTrue(v.geliehen(self.dort["Person 2"]))
        self.assertTrue(v.geliehen(self.dort["Person 3"]))
        self.assertEqual(v.link_von(self.dort["Person 2"])["via"],
                         self.ergebnis["uid"])

    def test_beide_seiten_kennen_einander(self):
        hier = self.quelle["people"][0]
        self.assertEqual(v.uid_von(hier), v.uid_von(self.dort["Person 1"]))
        self.assertEqual(v.andere_baeume(hier, "baum-a"),
                         [{"slug": "baum-b", "id": int(self.dort["Person 1"]["id"])}])

    def test_nummern_sind_ortsgebunden(self):
        # Her number in the first tree is 1; in the second she gets a fresh one.
        self.assertEqual(int(self.quelle["people"][0]["id"]), 1)
        self.assertGreaterEqual(int(self.dort["Person 1"]["id"]),
                                person_lib.FIRST_NEW_ID)

    def test_verbindungen_werden_auf_die_neuen_nummern_umgeschrieben(self):
        p1, p2, p3 = self.dort["Person 1"], self.dort["Person 2"], self.dort["Person 3"]
        self.assertEqual(p1["spouses"], [int(p2["id"])])
        self.assertEqual(sorted(p3["parents"]),
                         sorted([int(p1["id"]), int(p2["id"])]))

    def test_kein_draht_ins_nichts(self):
        # the parent did not travel, so the child must not point at them over
        # there - his number means somebody else in that file.
        self.assertEqual(self.dort["Person 2"]["parents"], [])

    def test_zweimal_verknuepfen_verdoppelt_niemanden(self):
        v.knuepfen(self.quelle, "baum-a", 1, self.ziel, "baum-b",
                   ["spouses", "children"], person_lib.blank_person, naechste_id)
        namen = [p["name"] for p in self.ziel["people"]]
        self.assertEqual(sorted(namen), ["Person 1", "Person 2", "Person 3"])


def angeheiratete_familie() -> dict:
    """Her, him, their child - and his whole family behind him.

    Numbered from her point of view, because that is the direction the dialog
    is used in: she is the one being carried into a second tree, and everything
    below 10 is the family she marries into.
    """
    return {"meta": {}, "people": [
        person(1, "Sie",              spouses=[2], children=[3]),
        person(2, "Er",               spouses=[1], children=[3, 4], parents=[5, 6]),
        person(3, "Gemeinsames Kind", parents=[1, 2]),
        person(4, "Sein Kind",        parents=[2]),
        person(5, "Schwiegervater",   spouses=[6], children=[2, 7]),
        person(6, "Schwiegermutter",  spouses=[5], children=[2, 7]),
        person(7, "Schwager",         parents=[5, 6]),
    ], "marriages": []}


class TestAngeheirateteSeite(unittest.TestCase):
    """The family somebody marries into can come along too.

    Without this, linking a wife into her own tree left her there with her
    husband and nobody of his - and every parent-in-law had to be typed a
    second time, by hand, into a file where nothing then kept the two copies
    in step.
    """

    def setUp(self):
        self.quelle = angeheiratete_familie()

    def _wer(self, gruppe):
        namen = {int(p["id"]): p["name"] for p in self.quelle["people"]}
        return sorted(namen[i] for i in v.gruppe_ids(self.quelle, 1, gruppe))

    def test_schwiegereltern_sind_die_eltern_der_ehepartner(self):
        self.assertEqual(self._wer("spouse_parents"),
                         ["Schwiegermutter", "Schwiegervater"])

    def test_geschwister_der_ehepartner(self):
        # His siblings - and he himself is not one of them.
        self.assertEqual(self._wer("spouse_siblings"), ["Schwager"])

    def test_kinder_der_ehepartner_schliesst_die_gemeinsamen_ein(self):
        # They are his children; the group says so and does not pretend that
        # a shared child belongs to only one of them.
        self.assertEqual(self._wer("spouse_children"),
                         ["Gemeinsames Kind", "Sein Kind"])

    def test_sie_selbst_ist_in_keiner_dieser_gruppen(self):
        for gruppe in v.UEBER_EHEPARTNER:
            self.assertNotIn("Sie", self._wer(gruppe))

    def test_ohne_ehepartner_gibt_es_keine_angeheiratete_seite(self):
        allein = {"meta": {}, "people": [person(1, "Sie")], "marriages": []}
        for gruppe in v.UEBER_EHEPARTNER:
            self.assertEqual(v.gruppe_ids(allein, 1, gruppe), [])

    def test_die_ehepartner_kommen_zwangslaeufig_mit(self):
        # Ticked without them, the parents-in-law would arrive over there with
        # no line to anybody, because their child stayed behind.
        self.assertEqual(v.mit_ehepartner(["spouse_parents"]),
                         ["spouses", "spouse_parents"])
        self.assertEqual(v.mit_ehepartner(["parents"]), ["parents"])

    def test_die_vorschau_nennt_sie_beim_namen(self):
        namen = [r["name"] for r in v.vorschau(self.quelle, 1, ["spouse_parents"])]
        self.assertEqual(sorted(namen), ["Er", "Schwiegermutter", "Schwiegervater"])

    def test_sie_wandern_wirklich_hinueber_und_haengen_zusammen(self):
        ziel = {"meta": {}, "people": [], "marriages": []}
        v.knuepfen(self.quelle, "baum-a", 1, ziel, "baum-b",
                   ["spouse_parents", "spouse_children"],
                   person_lib.blank_person, naechste_id)
        dort = {p["name"]: p for p in ziel["people"]}
        self.assertEqual(sorted(dort), ["Er", "Gemeinsames Kind", "Schwiegermutter",
                                        "Schwiegervater", "Sein Kind", "Sie"])
        # He hangs off his parents, and his children off him - the numbers are
        # the second tree's own.
        self.assertEqual(sorted(dort["Er"]["parents"]),
                         sorted([int(dort["Schwiegervater"]["id"]),
                                 int(dort["Schwiegermutter"]["id"])]))
        self.assertIn(int(dort["Er"]["id"]), dort["Sein Kind"]["parents"])
        # The married-in side arrived as HER family, so the big views over
        # there leave them out.
        self.assertTrue(v.geliehen(dort["Schwiegervater"]))
        self.assertFalse(v.geliehen(dort["Sie"]))

    def test_niemand_reist_zweimal(self):
        # The shared child is in two of the ticked groups and is one person.
        ziel = {"meta": {}, "people": [], "marriages": []}
        v.knuepfen(self.quelle, "baum-a", 1, ziel, "baum-b",
                   ["children", "spouse_children"],
                   person_lib.blank_person, naechste_id)
        namen = [p["name"] for p in ziel["people"]]
        self.assertEqual(len(namen), len(set(namen)))


class TestNameIstKeinBeweis(unittest.TestCase):
    """Two people are never joined because they are called the same."""

    def test_gleiche_namen_werden_gemeldet_nicht_verschmolzen(self):
        ziel = {"meta": {}, "people": [
            person(1001, "Person 1", birth={"year": 1990, "month": None, "day": None,
                                       "place": None, "approx": False}),
        ], "marriages": []}
        gefunden = v.schon_drueben(ziel, ["Person 1"])
        self.assertEqual(len(gefunden), 1)
        self.assertEqual(gefunden[0]["jahr"], 1990)

        # Reporting must not link anything: after asking, the record is untouched.
        self.assertIsNone(ziel["people"][0]["link"])

    def test_ein_namensgleicher_wird_nicht_wiederverwendet(self):
        quelle = kleine_familie()
        ziel = {"meta": {}, "people": [person(1001, "Person 1")], "marriages": []}
        v.knuepfen(quelle, "baum-a", 1, ziel, "baum-b", [],
                   person_lib.blank_person, naechste_id)
        # The namesake who was already there keeps to herself; the linked one is new.
        self.assertEqual(len(ziel["people"]), 2)
        self.assertIsNone(ziel["people"][0]["link"])
        self.assertIsNotNone(ziel["people"][1]["link"])


class TestGeteiltUndOertlich(unittest.TestCase):
    """What belongs to the person travels; what belongs to the tree stays."""

    def test_person_reist_baum_bleibt(self):
        geteilt = v.einsammeln(person(1, "Person 1", occupation="Hebamme",
                                      spouses=[2], photo="bild.jpg"))
        self.assertEqual(geteilt["occupation"], "Hebamme")
        self.assertNotIn("spouses", geteilt)   # a number, local to one tree
        self.assertNotIn("photo", geteilt)     # a file in one tree's folder
        self.assertNotIn("id", geteilt)

    def test_verteilen_meldet_ob_sich_etwas_geaendert_hat(self):
        ziel = person(1001, "Person 1")
        self.assertTrue(v.verteilen(ziel, {"occupation": "Hebamme"}))
        self.assertFalse(v.verteilen(ziel, {"occupation": "Hebamme"}))


class TestZusammenfuehren(unittest.TestCase):
    """A life is added up, not chosen between."""

    def test_listen_werden_vereinigt_ohne_rueckfrage(self):
        hier = person(1, "Person 1", events=[{"kind": "Heirat", "year": 2015}])
        dort = person(9, "Person 1", events=[{"kind": "Beruf", "year": 2012}])
        vereint, streit = v.zusammenfuehren(hier, dort)
        self.assertEqual(len(vereint["events"]), 2)
        self.assertEqual(streit, [])

    def test_eine_zweite_heirat_ist_kein_widerspruch(self):
        hier = person(1, "Person 1", events=[{"kind": "Heirat", "year": 2015}])
        dort = person(9, "Person 1", events=[{"kind": "Heirat", "year": 2021}])
        vereint, streit = v.zusammenfuehren(hier, dort)
        self.assertEqual(len(vereint["events"]), 2)
        self.assertEqual(streit, [])

    def test_doppelte_eintraege_werden_nicht_verdoppelt(self):
        eintrag = {"kind": "Heirat", "year": 2015}
        vereint, _ = v.zusammenfuehren(person(1, "Person 1", events=[eintrag]),
                                       person(9, "Person 1", events=[eintrag]))
        self.assertEqual(len(vereint["events"]), 1)

    def test_zwei_geburtsdaten_koennen_nicht_beide_gelten(self):
        a = {"year": 1990, "month": None, "day": None, "place": None, "approx": False}
        b = {"year": 1991, "month": None, "day": None, "place": None, "approx": False}
        _, streit = v.zusammenfuehren(person(1, "Person 1", birth=a),
                                      person(9, "Person 1", birth=b))
        self.assertIn("birth", streit)

    def test_gleiche_werte_sind_kein_streit(self):
        _, streit = v.zusammenfuehren(person(1, "Person 1", occupation="Hebamme"),
                                      person(9, "Person 1", occupation="Hebamme"))
        self.assertEqual(streit, [])

    def test_ein_leeres_feld_nimmt_was_die_andere_seite_weiss(self):
        vereint, streit = v.zusammenfuehren(person(1, "Person 1"),
                                            person(9, "Person 1", occupation="Hebamme"))
        self.assertEqual(vereint["occupation"], "Hebamme")
        self.assertEqual(streit, [])


class TestFormat(unittest.TestCase):
    """A tree older than the link field is brought forward, once."""

    def test_ein_baum_von_vorher_bekommt_das_feld(self):
        tree = {"meta": {}, "people": [{"id": 1, "name": "A"}]}
        getan = schema.umwandeln(tree)
        self.assertEqual(len(getan), 1)
        self.assertIn("link", tree["people"][0])
        self.assertEqual(schema.version(tree), schema.FORMAT)

    def test_ein_baum_aus_der_zukunft_wird_nicht_geoeffnet(self):
        self.assertTrue(schema.zu_neu({"meta": {"format": schema.FORMAT + 1}}))


class TestSpiegeln(unittest.TestCase):
    """Change her once - she is changed in every tree that carries her."""

    def setUp(self):
        # A throwaway data folder per test, handed over through the same
        # environment variable a second machine would use - so these tests can
        # never touch a real family.
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["AHNEN_DATEN"] = self.tmp.name
        for name in ("store", "namensliste"):
            sys.modules.pop(name, None)
        import store
        self.store = store

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("AHNEN_DATEN", None)
        sys.modules.pop("store", None)

    def _zwei_baeume(self):
        a = self.store.empty_tree("Baum A")
        a["people"] = kleine_familie()["people"]
        a_slug = self.store.create("Baum A", a, open_it=True)
        b_slug = self.store.create("Baum B", self.store.empty_tree("Baum B"),
                                      open_it=False)
        quelle = self.store.load(a_slug)
        ziel = self.store.load(b_slug)
        v.knuepfen(quelle, a_slug, 1, ziel, b_slug, ["spouses"],
                   person_lib.blank_person, self.store.next_id)
        self.store.save(ziel, b_slug)
        self.store.save(quelle, a_slug)
        return a_slug, b_slug

    def test_eine_aenderung_drueben_steht_auch_hier(self):
        a_slug, b_slug = self._zwei_baeume()
        b = self.store.load(b_slug)
        eine = next(p for p in b["people"] if p["name"] == "Person 1")
        eine["occupation"] = "Hebamme"
        self.store.save(b, b_slug)

        a = self.store.load(a_slug)
        hier = next(p for p in a["people"] if int(p["id"]) == 1)
        self.assertEqual(hier["occupation"], "Hebamme")

    def test_die_oertlichen_felder_bleiben_unberuehrt(self):
        a_slug, b_slug = self._zwei_baeume()
        b = self.store.load(b_slug)
        eine_dort = next(p for p in b["people"] if p["name"] == "Person 1")
        eine_dort["occupation"] = "Hebamme"
        self.store.save(b, b_slug)

        a = self.store.load(a_slug)
        hier = next(p for p in a["people"] if int(p["id"]) == 1)
        self.assertEqual(int(hier["id"]), 1)
        self.assertEqual(hier["spouses"], [2])       # her marriage here
        self.assertEqual(hier["children"], [3])

    def test_ein_baum_weniger_nimmt_die_person_nicht_mit(self):
        a_slug, b_slug = self._zwei_baeume()
        self.store.discard(b_slug)

        a = self.store.load(a_slug)
        eine = next((p for p in a["people"] if int(p["id"]) == 1), None)
        self.assertIsNotNone(eine, "die Person darf mit dem Baum nicht verschwinden")
        self.assertEqual(eine["name"], "Person 1")

    def test_ein_fehlender_baum_wird_gemeldet_und_kostet_nicht_das_speichern(self):
        a_slug, b_slug = self._zwei_baeume()
        self.store.discard(b_slug)

        a = self.store.load(a_slug)
        eine = next(p for p in a["people"] if int(p["id"]) == 1)
        eine["occupation"] = "Hebamme"
        self.store.save(a, a_slug)

        self.assertTrue(self.store.LETZTE_SPIEGEL_BERICHTE,
                        "der fehlende Baum muss gemeldet werden")
        wieder = self.store.load(a_slug)
        hier = next(p for p in wieder["people"] if int(p["id"]) == 1)
        self.assertEqual(hier["occupation"], "Hebamme",
                         "die Aenderung muss trotzdem gespeichert sein")

    def test_jeder_baum_bleibt_fuer_sich_lesbar(self):
        _, b_slug = self._zwei_baeume()
        with open(self.store.tree_path(b_slug), encoding="utf-8") as fh:
            allein = json.load(fh)
        eine = next(p for p in allein["people"] if p["name"] == "Person 1")
        # No lookup into the other file needed to know who she is.
        self.assertEqual(eine["name"], "Person 1")
        self.assertEqual(allein["meta"]["format"], schema.FORMAT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
