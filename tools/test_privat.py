# -*- coding: utf-8 -*-
"""What somebody asked to keep to themselves stays out of every export.

A section of the edit form - the life story, the scans, the contact details -
can be locked, and so can a single station, a single scan, a single address or
a single line of the contact details.  Three promises:

  * a lock is not overruled by the export dialog.  Everything ticked, and the
    locked part is still cut out of the data - not hidden by the page.
  * name, birth, death and the family always go.  They are what makes somebody
    a place in the tree, and they have no lock.
  * a lock survives: a tree converted from an older shape, two records merged,
    and the same person kept in step with another tree all keep it.

The names are invented.

    python tools/test_privat.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edits as person_lib          # noqa: E402
import export                       # noqa: E402
import format as schema             # noqa: E402
import verknuepfung                 # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")

KRANKHEIT = "Tuberkulose-Kur in Sankt Blasien"
URLAUB = "Sommer an der Schlei"


def person(**extra):
    base = {
        "id": 1, "name": "Wiebke Tannhausen", "given": "Wiebke", "surname": "Tannhausen",
        "sex": "w", "spouses": [2], "spouse_kind": {"2": "marriage"},
        "birth": {"year": 1931, "month": 4, "day": 2, "place": "Kappeln", "approx": False},
        "death": {"year": 1999, "place": "Husum", "approx": False},
        "occupation": "Lehrerin", "religion": "evangelisch",
        "events": [{"kind": "Krankheit", "year": 1952, "text": KRANKHEIT},
                   {"kind": "Urlaub", "year": 1960, "text": URLAUB}],
        "residences": [{"place": "Kappeln", "address": "Am Hafen 3"}],
        "documents": [{"file": "arztbrief.pdf", "title": "Arztbrief"},
                      {"file": "taufschein.pdf", "title": "Taufschein"}],
        "contact": {"email": "wiebke@beispiel.invalid", "phone": "0000 111"},
        "freetext": "Wollte nie, dass das jemand liest.",
        "photo": "wiebke.jpg",
    }
    base.update(extra)
    return person_lib.fill_missing(base)


def baum(*people):
    partner = person_lib.fill_missing({"id": 2, "name": "Tamo Wiebking", "sex": "m",
                                       "spouses": [1], "spouse_kind": {"1": "marriage"}})
    return {"meta": {"title": "Probe"}, "people": [*people, partner],
            "marriages": [], "checks": []}


ALLES = {k: True for k in export.FIELD_GROUPS}
ALLES.update({"kontakt_" + k: True for k in export.CONTACT_PARTS})


class TestAbschnitte(unittest.TestCase):

    def test_ohne_sperre_bleibt_alles(self):
        d = baum(person())
        self.assertEqual(person_lib.lock_private(d), d)

    def test_lebenslauf_gesperrt(self):
        out = person_lib.lock_private(baum(person(private=["lebenslauf"])))["people"][0]
        self.assertEqual(out["events"], [])
        self.assertEqual(out["occupation"], "Lehrerin", "nur der Lebenslauf war gesperrt")
        self.assertEqual(len(out["documents"]), 2)

    def test_jeder_abschnitt_leert_seine_felder(self):
        alle = list(person_lib.PRIVATE_SECTIONS)
        out = person_lib.lock_private(baum(person(private=alle)))["people"][0]
        for key in ("occupation", "religion", "contact", "freetext", "photo"):
            self.assertIn(out[key], (None, ""), key)
        for key in ("events", "residences", "documents", "notes"):
            self.assertEqual(out[key], [], key)

    def test_tod_hat_keine_sperre(self):
        self.assertNotIn("tod", person_lib.PRIVATE_SECTIONS)
        out = person_lib.lock_private(baum(person(private=["tod"])))["people"][0]
        self.assertEqual(out["death"]["place"], "Husum")

    def test_name_geburt_tod_familie_bleiben_immer(self):
        alle = list(person_lib.PRIVATE_SECTIONS)
        out = person_lib.lock_private(baum(person(private=alle)))["people"][0]
        self.assertEqual(out["name"], "Wiebke Tannhausen")
        self.assertEqual(out["birth"]["place"], "Kappeln")
        self.assertEqual(out["death"]["year"], 1999)
        self.assertEqual(out["death"]["place"], "Husum")
        self.assertEqual(out["spouses"], [2])
        self.assertEqual(out["spouse_kind"], {"2": "marriage"})

    def test_die_sperre_selbst_reist_mit(self):
        out = person_lib.lock_private(baum(person(private=["kontakt"])))["people"][0]
        self.assertEqual(out["private"], ["kontakt"])

    def test_unbekannte_abschnitte_zaehlen_nicht(self):
        self.assertEqual(person_lib.private_sections({"private": ["name", "kontakt"]}), ["kontakt"])
        self.assertEqual(person_lib.private_sections({"private": True}), [])

    def test_das_original_bleibt_unberuehrt(self):
        d = baum(person(private=["lebenslauf"]))
        person_lib.lock_private(d)
        self.assertEqual(len(d["people"][0]["events"]), 2)


class TestEinzelneEintraege(unittest.TestCase):

    def test_eine_station(self):
        p = person()
        p["events"][0]["private"] = True
        out = person_lib.lock_private(baum(p))["people"][0]
        self.assertEqual([e["text"] for e in out["events"]], [URLAUB])

    def test_eine_datei(self):
        p = person()
        p["documents"][0]["private"] = True
        out = person_lib.lock_private(baum(p))["people"][0]
        self.assertEqual([d["file"] for d in out["documents"]], ["taufschein.pdf"])

    def test_ein_wohnort(self):
        p = person()
        p["residences"][0]["private"] = True
        self.assertEqual(person_lib.lock_private(baum(p))["people"][0]["residences"], [])


class TestKontaktzeilen(unittest.TestCase):

    def test_nur_telefon_gesperrt(self):
        out = person_lib.lock_private(baum(person(private=["kontakt_telefon"])))["people"][0]
        self.assertEqual(out["contact"], {"email": "wiebke@beispiel.invalid"})

    def test_alle_zeilen_gesperrt_ist_kein_kontakt(self):
        alle = list(person_lib.PRIVATE_CONTACT)
        self.assertIsNone(person_lib.lock_private(baum(person(private=alle)))["people"][0]["contact"])

    def test_zeilen_heissen_wie_im_exportdialog(self):
        self.assertEqual(sorted(person_lib.PRIVATE_CONTACT),
                         sorted("kontakt_" + k for k in export.CONTACT_PARTS))
        self.assertEqual(sorted(person_lib.PRIVATE_CONTACT.values()),
                         sorted(export.CONTACT_PARTS.values()))


class TestExportUeberstimmtNicht(unittest.TestCase):
    """Everything ticked, and the locked parts are still not in the files."""

    def schreiben(self, formate):
        p = person(private=["notizen", "kontakt_email"])
        p["events"][0]["private"] = True
        p["documents"][0]["private"] = True
        with tempfile.TemporaryDirectory() as ordner:
            geschrieben = export.run(baum(p), {"felder": ALLES, "formate": formate,
                                               "buch": False, "diagramm": False},
                                     ordner, "")
            texte = []
            for name in geschrieben:
                with open(os.path.join(ordner, name), encoding="utf-8") as fh:
                    texte.append(fh.read())
        return "\n".join(texte)

    def pruefen(self, text):
        for geheim in (KRANKHEIT, "arztbrief.pdf", "wiebke@beispiel.invalid", "Wollte nie"):
            self.assertNotIn(geheim, text)
        for bleibt in ("Tannhausen", "Kappeln", URLAUB, "taufschein.pdf", "0000 111"):
            self.assertIn(bleibt, text)

    def test_html_seite(self):
        self.pruefen(self.schreiben(["html"]))

    def test_gedcom(self):
        text = self.schreiben(["gedcom"])
        for geheim in (KRANKHEIT, "wiebke@beispiel.invalid", "Wollte nie"):
            self.assertNotIn(geheim, text)
        self.assertIn("Tannhausen", text)

    def test_buch(self):
        p = person(private=["lebenslauf"])
        out = person_lib.lock_private(baum(p))
        eintrag = export.person_entry(out["people"][0], {}, {1: out["people"][0]}, ALLES)
        self.assertNotIn(KRANKHEIT, eintrag)
        self.assertIn("Lehrerin", eintrag)


class TestSperreBleibt(unittest.TestCase):

    def test_umwandlung_von_format_4(self):
        tree = {"meta": {"format": 4}, "people": [{"id": 1, "name": "A"}]}
        getan = schema.umwandeln(tree)
        self.assertEqual(schema.version(tree), 5)
        self.assertEqual(len(getan), 1)
        self.assertEqual(tree["people"][0]["private"], [])

    def test_neue_person_hat_das_feld(self):
        self.assertEqual(person_lib.blank_person(7)["private"], [])

    def test_verknuepfte_person_vereint_die_sperren(self):
        hier = person(private=["kontakt"])
        dort = person(private=["lebenslauf"])
        out, streit = verknuepfung.zusammenfuehren(hier, dort)
        self.assertEqual(out["private"], ["kontakt", "lebenslauf"])
        self.assertNotIn("private", streit)
        self.assertIn("private", verknuepfung.GETEILT)

    def test_zusammenfuehren_behaelt_beide(self):
        import zusammenfuehren
        with open(zusammenfuehren.__file__, encoding="utf-8") as fh:
            s = fh.read()
        self.assertIn('neu["private"]', s)


class TestOberflaeche(unittest.TestCase):

    def setUp(self):
        with open(VORLAGE, encoding="utf-8") as fh:
            self.s = fh.read()

    def test_jeder_abschnitt_hat_seinen_knopf(self):
        form = self.s[self.s.index("function formHTML(){"):self.s.index("function refreshAutoName(")]
        knoepfe = re.findall(r'privateButtonHTML\("(\w+)"\)', form)
        self.assertEqual(sorted(knoepfe),
                         sorted(k for k in person_lib.PRIVATE_SECTIONS if k != "portrait"))
        self.assertIn('data-private="portrait"', self.s)

    def test_kein_knopf_bei_tod_und_beerdigung(self):
        self.assertIn('<h3>Tod und Beerdigung</h3>', self.s)

    def test_jede_kontaktzeile_hat_ein_schloss(self):
        form = self.s[self.s.index("function formHTML(){"):self.s.index("function refreshAutoName(")]
        teile = re.findall(r'contactFieldHTML\("[^"]+", "\w+", "(\w+)"', form)
        self.assertEqual(sorted("kontakt_" + t for t in teile), sorted(person_lib.PRIVATE_CONTACT))

    def test_der_knopf_steht_neben_lebenslauf(self):
        self.assertIn('<h3 class="withctl"><span>Lebenslauf</span>${privateButtonHTML("lebenslauf")}</h3>',
                      self.s)

    def test_texte_fuer_jeden_abschnitt(self):
        block = re.search(r"const PRIVATE_TEXT = \{(.*?)\};", self.s, re.S).group(1)
        self.assertEqual(sorted(re.findall(r"(\w+):", block)),
                         sorted([*person_lib.PRIVATE_SECTIONS, *person_lib.PRIVATE_CONTACT]))

    def test_einzelne_eintraege_haben_ein_schloss(self):
        for liste in person_lib.PRIVATE_ITEMS:
            self.assertIn('itemLockHTML("%s", i, ' % liste, self.s)

    def test_diagramm_laesst_gesperrte_portraits_weg(self):
        self.assertIn('photosAsData([...stageSet()].filter(id => !isPrivate(BY_ID.get(id), "portrait")))',
                      self.s)


if __name__ == "__main__":
    unittest.main()
