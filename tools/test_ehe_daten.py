# -*- coding: utf-8 -*-
"""When a couple began, where, and how it ended - held open against the next change.

Two promises matter more than the rest, and both are about not losing what a
family already wrote down:

  * A "Heirat" or "Scheidung" that is already in a life story is tied to the
    couple it describes and lends it its date - and the station itself stays
    word for word.
  * A station somebody entered is never rewritten by the program, not on load,
    not on conversion, not on export.

The names are invented.

    python tools/test_ehe_daten.py
"""
from __future__ import annotations

import copy
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edits as person_lib          # noqa: E402
import format as schema             # noqa: E402
import gedcom                       # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))


def person(pid, name, **extra):
    return person_lib.fill_missing(dict({"id": pid, "name": name}, **extra))


def paar(**a_extra):
    """Two invented people who belong together."""
    a = person(1, "Tamo Wiebking", sex="m", spouses=[2], **a_extra)
    b = person(2, "Ilka Dornbusch", sex="w", spouses=[1])
    return [a, b]


class TestVorhandeneStationen(unittest.TestCase):

    def test_heirat_mit_partner_wird_zugeordnet(self):
        leute = paar(events=[{"kind": "Heirat", "with": [2], "year": 2015,
                              "month": 5, "day": 12, "place": "Aurich"}])
        person_lib.normalise_links(leute)
        a, b = leute
        self.assertEqual(a["spouse_info"]["2"]["since"],
                         {"year": 2015, "month": 5, "day": 12, "approx": False})
        self.assertEqual(a["spouse_info"]["2"]["place"], "Aurich")
        self.assertEqual(b["spouse_info"]["1"], a["spouse_info"]["2"],
                         "beide Seiten muessen dasselbe sagen")
        self.assertEqual(a["events"][0]["tie"], {"with": 2, "part": "start", "auto": None})

    def test_station_bleibt_wortgleich(self):
        station = {"kind": "Heirat", "with": [2], "year": 2015, "approx": True,
                   "place": "Leer", "text": "standesamtlich"}
        leute = paar(events=[copy.deepcopy(station)])
        person_lib.normalise_links(leute)
        ev = dict(leute[0]["events"][0])
        ev.pop("tie")
        self.assertEqual(ev, station)

    def test_ohne_partnername_nur_bei_einem_partner(self):
        leute = paar(events=[{"kind": "Scheidung", "with": [], "year": 2020}])
        person_lib.normalise_links(leute)
        a = leute[0]
        self.assertEqual(a["spouse_info"]["2"]["end"], "divorced")
        self.assertEqual(a["spouse_info"]["2"]["until"]["year"], 2020)
        self.assertEqual(a["events"][0]["with"], [2])

    def test_zwei_partner_ohne_namen_bleibt_offen(self):
        a = person(1, "Tamo Wiebking", spouses=[2, 3],
                   events=[{"kind": "Heirat", "with": [], "year": 1990}])
        leute = [a, person(2, "Ilka Dornbusch", spouses=[1]),
                 person(3, "Xandra Quellbrink", spouses=[1])]
        person_lib.normalise_links(leute)
        self.assertNotIn("tie", a["events"][0], "geraten wird nicht")
        self.assertEqual(a["spouse_info"], {})

    def test_vorhandenes_datum_wird_nicht_ueberschrieben(self):
        leute = paar(events=[{"kind": "Heirat", "with": [2], "year": 2015}])
        leute[0]["spouse_info"] = {"2": {"since": {"year": 2014}}}
        leute[1]["spouse_info"] = {"1": {"since": {"year": 2014}}}
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_info"]["2"]["since"]["year"], 2014)

    def test_heirat_macht_aus_partnerschaft_eine_ehe(self):
        leute = paar(events=[{"kind": "Hochzeit", "with": [2], "year": 2001}],
                     spouse_kind={"2": "partner"})
        leute[1]["spouse_kind"] = {"1": "partner"}
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_kind"]["2"], "marriage")
        self.assertEqual(leute[1]["spouse_kind"]["1"], "marriage")

    def test_verlobung_neben_heirat_nimmt_nicht_den_beginn(self):
        leute = paar(events=[{"kind": "Verlobung", "with": [2], "year": 2013},
                             {"kind": "Heirat", "with": [2], "year": 2015}])
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_info"]["2"]["since"]["year"], 2015)
        self.assertTrue(all("tie" in e for e in leute[0]["events"]))

    def test_zuordnung_zu_niemandem_mehr_faellt_weg(self):
        leute = paar(events=[{"kind": "Heirat", "with": [2], "year": 2015,
                              "tie": {"with": 9, "part": "start", "auto": None}}])
        person_lib.normalise_links(leute)
        # the stale tie goes, and the station is joined to the real partner again
        self.assertEqual(leute[0]["events"][0]["tie"]["with"], 2)


class TestAufraeumen(unittest.TestCase):

    def test_leerer_eintrag_verschwindet(self):
        leute = paar(spouse_info={"2": {"since": {"year": None}, "place": " ", "end": None}})
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_info"], {})

    def test_unbekanntes_ende_gilt_als_nichts(self):
        leute = paar(spouse_info={"2": {"end": "verwitwet", "until": {"year": 1990}, "note": "x"}})
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_info"]["2"],
                         {"since": None, "place": None, "end": None, "until": None, "note": "x"})

    def test_der_vollere_eintrag_gewinnt(self):
        leute = paar(spouse_info={"2": {"since": {"year": 2015}}})
        leute[1]["spouse_info"] = {"1": {"since": {"year": 2015}, "place": "Emden", "end": "divorced"}}
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_info"]["2"]["place"], "Emden")
        self.assertEqual(leute[0]["spouse_info"], {"2": leute[1]["spouse_info"]["1"]})

    def test_verlobt_ist_eine_art(self):
        leute = paar(spouse_kind={"2": "engaged"})
        person_lib.normalise_links(leute)
        self.assertEqual(leute[1]["spouse_kind"]["1"], "engaged")

    def test_ehe_schlaegt_verlobung(self):
        leute = paar(spouse_kind={"2": "engaged"})
        leute[1]["spouse_kind"] = {"1": "marriage"}
        person_lib.normalise_links(leute)
        self.assertEqual(leute[0]["spouse_kind"]["2"], "marriage")


class TestUmwandlung(unittest.TestCase):

    def test_format_3_bekommt_das_feld_und_die_zuordnung(self):
        tree = {"meta": {"format": 3}, "people": [
            {"id": 1, "name": "Tamo Wiebking", "spouses": [2], "spouse_kind": {"2": "marriage"},
             "parent_kind": {}, "events": [{"kind": "Heirat", "with": [2], "year": 1999}]},
            {"id": 2, "name": "Ilka Dornbusch", "spouses": [1], "spouse_kind": {"1": "marriage"},
             "parent_kind": {}, "events": []}]}
        getan = schema.umwandeln(tree)
        self.assertEqual(schema.version(tree), 4)
        self.assertEqual(len(getan), 1)
        self.assertEqual(tree["people"][0]["spouse_info"]["2"]["since"]["year"], 1999)
        self.assertEqual(tree["people"][1]["spouse_info"]["1"]["since"]["year"], 1999)


class TestGedcom(unittest.TestCase):

    def baum(self):
        leute = paar(spouse_kind={"2": "marriage"},
                     spouse_info={"2": {"since": {"year": 2015, "month": 5, "day": 12, "approx": False},
                                        "place": "Aurich", "end": "divorced",
                                        "until": {"year": 2020, "approx": True},
                                        "note": "erste Zeile\nzweite Zeile"}})
        person_lib.normalise_links(leute)
        return {"meta": {"title": "Test"}, "people": leute, "marriages": []}

    def test_export_traegt_datum_ort_scheidung_und_notiz(self):
        text = gedcom.write(self.baum())
        fam = text[text.index("0 @F1@ FAM"):]
        self.assertIn("1 MARR\r\n2 DATE 12 MAY 2015\r\n2 PLAC Aurich", fam)
        self.assertIn("1 DIV\r\n2 DATE ABT 2020", fam)
        self.assertIn("1 NOTE erste Zeile\r\n2 CONT zweite Zeile", fam)

    def test_zurueck_eingelesen_ist_es_wieder_dasselbe_paar(self):
        wieder = gedcom.read(gedcom.write(self.baum()))
        a = wieder["people"][0]
        tie = a["spouse_info"][str(a["spouses"][0])]
        self.assertEqual(tie["since"]["year"], 2015)
        self.assertEqual(tie["place"], "Aurich")
        self.assertEqual(tie["end"], "divorced")
        self.assertEqual(tie["until"]["year"], 2020)

    def test_verlobung_geht_als_enga_raus(self):
        tree = self.baum()
        for p in tree["people"]:
            for k in p["spouse_kind"]:
                p["spouse_kind"][k] = "engaged"
        self.assertIn("1 ENGA", gedcom.write(tree))

    def test_zugeordnete_station_steht_nicht_doppelt_drin(self):
        tree = self.baum()
        tree["people"][0]["events"].append(
            {"kind": "Trennung", "with": [2], "year": 2019,
             "tie": {"with": 2, "part": "end", "auto": None}})
        indi = gedcom.write(tree).split("0 @F1@ FAM")[0]
        self.assertNotIn("TYPE Trennung", indi)


class TestSeite(unittest.TestCase):
    """Shapes in the page the promises above depend on."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HIER, "temp" + "late.html"), encoding="utf-8") as fh:
            cls.s = fh.read()

    def test_verlobt_steht_im_auswahlfeld(self):
        rollen = re.search(r"const SPOUSE_ROLES = \[(.*?)\];", self.s, re.S).group(1)
        self.assertIn('"engaged"', rollen)
        self.assertIn("Verlobt", rollen)

    def test_unter_jedem_partner_beginn_und_ende(self):
        self.assertIn('role === "spouses" ? tieHTML(id)', self.s)
        koerper = self.s[self.s.index("function tieHTML("):self.s.index("function chipsHTML(")]
        for teil in (".since", ".until", ".place", ".end", "geschieden", "getrennt", "ungefähr",
                     "data-tienote"):
            self.assertIn(teil, koerper)

    def test_eine_notiz_mit_text_ist_zu_sehen(self):
        koerper = self.s[self.s.index("function tieHTML("):self.s.index("function chipsHTML(")]
        self.assertIn("hasNote", koerper)
        self.assertIn("notebtn.has", self.s)

    def test_was_ist_passiert_erst_auf_knopfdruck(self):
        koerper = self.s[self.s.index("function eventCards("):self.s.index("const DOC_ICON")]
        self.assertIn("data-eventnote", koerper)
        self.assertIn("Notiz hinzufügen", koerper)

    def test_eigene_stationen_werden_nie_angefasst(self):
        koerper = self.s[self.s.index("function syncStations("):self.s.index("function syncTies(")]
        self.assertIn("linked.some(e => !e.tie.auto)", koerper)

    def test_speichern_gleicht_ab_und_die_option_schaltet_es_ab(self):
        self.assertIn("syncTies();", self.s[self.s.index("async function saveDraft("):])
        self.assertIn("EDIT.stationenAuto === false", self.s)
        self.assertIn('id="optStationen"', self.s)
        self.assertIn("/api/einstellung", self.s)


if __name__ == "__main__":
    unittest.main()
