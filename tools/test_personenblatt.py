# -*- coding: utf-8 -*-
"""What the person sheet promises, held open against the next change.

Three of these were written after the thing had already gone wrong once, and
two of those went wrong at runtime rather than in the markup:

  * `editGuard` was given a continuation so the unsaved-work question could
    carry on where the caller left off.  It also ran that continuation in the
    case where nothing was in the way - and `openEditor` hands in *itself*, so
    opening any person recursed until the stack ran out.  Nothing in the markup
    looked wrong; the page simply died on the first click.

  * `lookup` asked the sidecar and the tree but not the draft.  The draft is a
    deep copy, so a role chosen in the form was written to the copy and read
    back off the original, and the dropdown snapped back to the old value the
    moment the form redrew.

  * `spouseKind` read a tie nobody had said anything about as a partnership
    while the drawing read the same tie as a marriage - so one couple was an
    Ehe in the diagram and a Partnerschaft in the form at the same time.

Like `test_verknuepfen_knopf.py` these read the template rather than drive a
browser.  What is being held open is a shape in the source, and a test that
needs a browser to say so is a test that stops being run.

    python tools/test_personenblatt.py
"""
from __future__ import annotations

import os
import re
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")


def vorlage() -> str:
    with open(VORLAGE, encoding="utf-8") as fh:
        return fh.read()


def rumpf(quelle: str, name: str) -> str:
    """The body of a top level function, by brace counting."""
    start = quelle.index("function %s(" % name)
    auf = quelle.index("{", start)
    tiefe = 0
    for i in range(auf, len(quelle)):
        if quelle[i] == "{":
            tiefe += 1
        elif quelle[i] == "}":
            tiefe -= 1
            if tiefe == 0:
                return quelle[auf + 1:i]
    raise AssertionError("Funktion %s hat keine schliessende Klammer" % name)


class TestDieVierKnoepfe(unittest.TestCase):
    """Up a parent, down a child, left a sibling, right a partner."""

    def setUp(self):
        self.adds = rumpf(vorlage(), "addsHTML")

    def test_rechts_legt_einen_partner_an(self):
        self.assertRegex(self.adds, r'b\("right",\s*"spouse"',
                         "der rechte Knopf legt keinen Partner an")

    def test_rechts_traegt_ein_gleichheitszeichen(self):
        stelle = re.search(r'b\("right".*?\)\}', self.adds, re.S)
        self.assertIsNotNone(stelle, "der rechte Knopf ist nicht mehr zu finden")
        self.assertIn('"="', stelle.group(0), "der rechte Knopf zeigt kein =")

    def test_links_bleibt_das_geschwister(self):
        """Asked for explicitly: the sibling button does not move."""
        self.assertRegex(self.adds, r'b\("left",\s*"sibling"',
                         "links steht kein Geschwister mehr")

    def test_es_bleiben_genau_vier(self):
        self.assertEqual(len(re.findall(r"\$\{b\(", self.adds)), 4)


class TestDieFrageNachUngespeichertem(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_drei_wege_statt_zwei(self):
        for knopf in ("askSave", "askDrop", "askBack"):
            self.assertIn(knopf, self.s, "in der Frage fehlt %s" % knopf)

    def test_die_frage_wird_nicht_mehr_per_confirm_gestellt(self):
        """`confirm` can only offer two answers, and the one that was missing -
        save it and carry on - is the one somebody actually wants."""
        self.assertNotIn("Trotzdem schliessen?", self.s)
        self.assertNotIn("Trotzdem schließen?", self.s)

    def test_der_waechter_ruft_die_fortsetzung_nicht_doppelt(self):
        """The stack overflow.  On the clear path the caller carries on by
        itself, so running the continuation here as well runs it twice - and
        for `openEditor`, whose continuation is itself, twice for ever."""
        koerper = rumpf(self.s, "editGuard")
        klar = koerper[:koerper.index("askUnsaved")]
        self.assertNotIn("weiter()", klar,
                         "editGuard ruft die Fortsetzung auch dann auf, wenn "
                         "der Aufrufer selbst weitermacht - das rekursiert")

    def test_jeder_ausgang_fragt(self):
        """The close button, Escape and the backdrop leave by the same door."""
        for stelle in ('if(e.key === "Escape") closeSheet();',
                       'if(e.target.id === "scrim") closeSheet();'):
            self.assertIn(stelle, self.s, "ein Ausgang fragt nicht nach: " + stelle)


class TestSpeichernSchliesstNicht(unittest.TestCase):

    def setUp(self):
        self.save = rumpf(vorlage(), "saveDraft")

    def test_der_erfolgsfall_laesst_das_blatt_offen(self):
        erfolg = self.save[:self.save.index("}catch")]
        self.assertNotIn("closeSheetHard()", erfolg,
                         "Speichern schliesst das Blatt immer noch")

    def test_es_wird_neu_gezeichnet_statt_geschlossen(self):
        self.assertIn("renderForm()", self.save)

    def test_eine_gespeicherte_person_ist_nicht_mehr_neu(self):
        """Otherwise the next save adds them again under a fresh number."""
        self.assertIn("editingNew = false", self.save)

    def test_der_aufrufer_erfaehrt_ob_es_geklappt_hat(self):
        """The unsaved-work dialog only carries on when the file really has it."""
        self.assertIn("return true", self.save)
        self.assertIn("return false", self.save)


class TestWerDieWahrheitHat(unittest.TestCase):

    def test_der_entwurf_wird_zuerst_gefragt(self):
        koerper = rumpf(vorlage(), "lookup")
        self.assertLess(koerper.index("draft"), koerper.index("BY_ID"),
                        "lookup fragt die Datei vor dem offenen Entwurf")
        self.assertLess(koerper.index("draft"), koerper.index("sidecar"),
                        "lookup fragt den Beiwagen vor dem offenen Entwurf")


class TestDieRollenNebenDenNamen(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_eltern_und_partner_haben_ein_dropdown(self):
        chips = rumpf(self.s, "chipsHTML")
        self.assertIn('role === "parents"', chips)
        self.assertIn('role === "spouses"', chips)

    def test_kinder_und_geschwister_haben_eines(self):
        """Sohn/Tochter and Bruder/Schwester - asked for, so that a wrong
        entry shows in the list itself. The word is the other person's sex."""
        chips = rumpf(self.s, "chipsHTML")
        self.assertIn('role === "children"', chips)
        self.assertIn('role === "siblings"', chips)
        for wort in ("Sohn", "Tochter", "Bruder", "Schwester"):
            self.assertIn('t: "%s"' % wort, self.s, "im Dropdown fehlt " + wort)

    def test_sohn_und_tochter_tragen_das_geschlecht_ein(self):
        koerper = rumpf(self.s, "setRole")
        self.assertIn('role === "children" || role === "siblings"', koerper)
        self.assertIn("other.sex = value", koerper)
        # "Kind" / "Geschwister" says nothing and must not clear a known sex.
        self.assertIn('value === "m" || value === "w"', koerper)

    def test_geschwister_stehen_neben_den_kindern(self):
        self.assertIn('linkSection("siblings", "Geschwister"', self.s)
        self.assertIn('class="secpair"', self.s)

    def test_geschwister_bekommen_dieselben_eltern(self):
        """Siblings are not stored - entering one hands over the parents."""
        koerper = rumpf(self.s, "linkPerson")
        self.assertIn('role === "siblings"', koerper)
        self.assertIn("sib.parents", koerper)

    def test_ein_fenster_bleibt_beim_neuzeichnen_wo_es_war(self):
        koerper = rumpf(self.s, "closeSheetHard")
        self.assertIn("lastSheet", koerper,
                      "ein neu gezeichnetes Fenster springt wieder nach oben")
        self.assertIn("new MutationObserver", self.s)

    def test_vater_und_mutter_tragen_das_geschlecht_ein(self):
        koerper = rumpf(self.s, "setRole")
        self.assertIn("parent.sex = chosen.sex", koerper,
                      "die Wahl Vater/Mutter traegt das Geschlecht nicht ein")

    def test_ein_geschlecht_wird_nie_wieder_geloescht(self):
        """Elternteil means nobody has said - not forget what you knew."""
        koerper = rumpf(self.s, "setRole")
        self.assertIn("if(chosen.sex){", koerper)

    def test_stiefeltern_stehen_zur_wahl(self):
        for wort in ("Stiefvater", "Stiefmutter", "Stiefelternteil"):
            self.assertIn(wort, self.s, "im Dropdown fehlt " + wort)

    def test_die_ehe_wird_auf_beiden_seiten_geschrieben(self):
        koerper = rumpf(self.s, "setRole")
        self.assertIn("other.spouse_kind[draft.id]", koerper,
                      "die andere Seite der Ehe wird nicht mitgeschrieben")

    def test_die_namen_sind_anklickbar(self):
        self.assertIn('data-goto="${id}"', rumpf(self.s, "chipsHTML"),
                      "die Namen im Formular fuehren nirgendwohin")


class TestUnbekanntesGeschlecht(unittest.TestCase):
    """It stays unknown.  It used to come out male."""

    def setUp(self):
        self.s = vorlage()

    def test_ohne_geschlecht_nicht_mehr_maennlich(self):
        zeile = re.search(r"const MF = .*", self.s).group(0)
        self.assertIn('p.sex === "m"', zeile,
                      "MF entscheidet nicht mehr ausdruecklich ueber m")
        self.assertIn("(u ||", zeile,
                      "MF hat kein drittes Wort fuer den unbekannten Fall")

    def test_es_gibt_neutrale_woerter_wo_deutsch_welche_hat(self):
        for wort in ("Elternteil", "Enkelkind", "geschwister", "Kind"):
            self.assertIn('"%s"' % wort, self.s,
                          "das neutrale Wort %s fehlt" % wort)


class TestEheUndPartnerschaft(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def test_ungesagt_heisst_ueberall_dasselbe(self):
        """A pair may not be an Ehe in the diagram and a Partnerschaft in the
        form.  Both ask the same question, so both must answer it the same."""
        # Only an explicit partnership or engagement is not a marriage - in both.
        self.assertIn('said === "partner" || said === "engaged" ? said : "marriage"',
                      rumpf(self.s, "spouseKind"))
        self.assertIn('const wed = said !== "partner" && said !== "engaged";', self.s,
                      "die Zeichnung liest ungesagte Verbindungen anders")

    def test_die_ehe_bleibt_die_doppellinie(self):
        stelle = self.s[self.s.index("const wed ="):]
        stelle = stelle[:stelle.index("/* The sibling bar")]
        self.assertEqual(stelle.count("wires.push"), 3,
                         "Ehe (zwei Linien) und Partnerschaft (eine) stimmen nicht")

    def test_die_partnerschaft_ist_gestrichelt(self):
        self.assertIn(".wires path.marriage.partnered{stroke-dasharray", self.s)


class TestDasBildWirdGross(unittest.TestCase):
    """A click on the portrait shows the picture itself, large, over the sheet."""

    def setUp(self):
        self.s = vorlage()

    def test_das_bild_auf_dem_blatt_ist_ein_knopf(self):
        self.assertIn('data-zoom="${p.id}"', rumpf(self.s, "sheetHTML"),
                      "das Portrait auf dem Personenblatt ist nicht anklickbar")

    def test_die_grossansicht_zeigt_dieselbe_quelle(self):
        self.assertIn("const src = PHOTOS[id];", rumpf(self.s, "openZoom"))

    def test_die_grossansicht_borgt_sich_keinen_namen(self):
        """`.zoom` is the diagram's zoom buttons.  Sharing the name once laid a
        dark full-screen layer with the buttons spread across it over the tree."""
        self.assertEqual(self.s.count(".zoom{"), 1,
                         "die Grossansicht benutzt wieder die Klasse der Zoomknoepfe")
        self.assertNotIn('getElementById("zoom")', self.s)

    def test_escape_schliesst_erst_das_bild(self):
        """Escape and the click put the picture away, not the sheet under it -
        so both answer in the capture phase, before the sheet's own handlers."""
        stelle = self.s[self.s.index("function closeZoom("):]
        stelle = stelle[:stelle.index('document.addEventListener("click", e => {\n  /* The unsaved')]
        self.assertEqual(stelle.count("}, true);"), 2)
        self.assertEqual(stelle.count("stopImmediatePropagation"), 3)


class TestGeburtZuerstTodDahinter(unittest.TestCase):
    """Birth is what is known of almost everyone, so it is always there; death
    and burial wait behind "Gestorben" unless something is already known."""

    def setUp(self):
        self.s = vorlage()
        self.form = rumpf(self.s, "formHTML")

    def test_konfession_steht_in_der_geburtszeile(self):
        zeile = self.form[self.form.index('class="birthrow"'):]
        zeile = zeile[:zeile.index("Geburtsort")]
        self.assertIn('"religion"', zeile, "die Konfession steht nicht neben der Geburt")
        self.assertEqual(self.form.count('"religion"'), 1,
                         "die Konfession steht zweimal im Formular")

    def test_beruf_bleibt_unter_leben(self):
        leben = self.form[self.form.index("<h3>Leben</h3>"):]
        leben = leben[:leben.index("<h3>Wohnorte</h3>")]
        self.assertIn('"occupation"', leben)

    def test_die_geburtszeile_bricht_um(self):
        self.assertIn(".birthrow{display:flex;flex-wrap:wrap", self.s)

    def test_der_knopf_kommt_vor_dem_todesblock(self):
        knopf = self.form.index("data-deathtoggle")
        self.assertLess(self.form.index("<h3>Geburt</h3>"), knopf)
        self.assertLess(knopf, self.form.index("<h3>Tod und Beerdigung</h3>"))
        self.assertIn("✝ Gestorben", self.form)

    def test_der_todesblock_ist_nur_offen_wenn_gewollt(self):
        self.assertIn('id="deathBox"${deathOpen ? "" : " hidden"}', self.form)

    def test_vorhandene_sterbedaten_oeffnen_ihn(self):
        self.assertIn("deathOpen = hasDeathData(draft);", rumpf(self.s, "openEditor"))
        pruefung = rumpf(self.s, "hasDeathData")
        for feld in ("death.year", "death.place", "death.cause",
                     "burial.year", "burial.place"):
            self.assertIn('"%s"' % feld, pruefung, "hasDeathData uebersieht " + feld)

    def test_zuklappen_loescht_nichts(self):
        stelle = self.s[self.s.index('closest("[data-deathtoggle]")'):]
        stelle = stelle[:stelle.index('closest("[data-add]")')]
        self.assertNotIn("draft.", stelle, "der Knopf fasst den Entwurf an")
        self.assertNotIn("markDirty", stelle)

    def test_der_hinweis_bleibt_im_todesblock(self):
        block = self.form[self.form.index('id="deathBox"'):]
        block = block[:block.index("<h3>Leben</h3>")]
        self.assertIn("Leer lassen, solange die Person lebt", block)


class TestDerAusgangLaeuftMit(unittest.TestCase):

    def test_der_kopf_klebt_wie_die_speicherleiste(self):
        """The close button used to scroll off the top of a long sheet."""
        s = vorlage()
        self.assertIn(".sheet-head{position:sticky;top:0", s)
        self.assertIn(".sheet-foot{\n  position:sticky;bottom:0", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
