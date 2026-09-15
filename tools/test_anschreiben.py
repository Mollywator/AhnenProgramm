# -*- coding: utf-8 -*-
"""Writing to the family: one address, or everybody at once as BCC.

The mail logic is plain functions in the template.  They are cut out of it and
run under Node, so what is tested is the code the page runs - not a copy.
Without Node those tests are skipped; the markup checks still run.

Only invented addresses, under `.invalid`.

    python tools/test_anschreiben.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "template.html")


def vorlage() -> str:
    with open(VORLAGE, encoding="utf-8") as fh:
        return fh.read()


def funktion(quelle: str, name: str) -> str:
    """A whole top level function, header included, by brace counting."""
    start = quelle.index("function %s(" % name)
    auf = quelle.index("{", start)
    tiefe = 0
    for i in range(auf, len(quelle)):
        if quelle[i] == "{":
            tiefe += 1
        elif quelle[i] == "}":
            tiefe -= 1
            if tiefe == 0:
                return quelle[start:i + 1]
    raise AssertionError("Funktion %s hat keine schliessende Klammer" % name)


def zeile(quelle: str, anfang: str) -> str:
    m = re.search(r"^%s.*$" % re.escape(anfang), quelle, re.M)
    if not m:
        raise AssertionError("%s fehlt in der Vorlage" % anfang)
    return m.group(0)


NODE = shutil.which("node")


def js(ausdruck: str):
    q = vorlage()
    code = "\n".join([
        zeile(q, "const linkOf ="), zeile(q, "const hiddenHere ="),
        funktion(q, "isGone"), funktion(q, "mailAddresses"), funktion(q, "mailtoHref"),
        funktion(q, "mailRecipients"), funktion(q, "mailToAll"),
        "process.stdout.write(JSON.stringify(%s));" % ausdruck,
    ])
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout)


def person(pid, name, email=None, **extra):
    p = {"id": pid, "name": name, "birth": {"year": 1970}}
    if email is not None:
        p["contact"] = {"email": email}
    p.update(extra)
    return p


LEUTE = [
    person(1, "Person Eins", "eins@beispiel.invalid"),
    person(2, "Person Zwei", "zwei@beispiel.invalid; geteilt@beispiel.invalid"),
    person(3, "Person Drei", "geteilt@beispiel.invalid"),           # shares one
    person(4, "Person Vier", "vier@beispiel.invalid", death={"year": 2001}),
    person(5, "Person Fuenf", "fuenf@beispiel.invalid", birth={"year": 1890}),
    person(6, "Person Sechs", "sechs@beispiel.invalid",
           link={"uid": "p-6", "trees": [], "via": None, "hidden": True}),
    person(7, "Person Sieben", "keine Adresse"),
    person(8, "Person Acht"),
]


@unittest.skipUnless(NODE, "Node fehlt - die Mail-Logik wird nicht ausgefuehrt")
class TestSammeln(unittest.TestCase):

    def test_nur_lebende_sichtbare_mit_adresse(self):
        leute = js("mailRecipients(%s).map(r => r.id)" % json.dumps(LEUTE))
        self.assertEqual(leute, [1, 2, 3])

    def test_doppelte_adresse_nur_einmal(self):
        out = js("mailToAll(mailRecipients(%s), '', '')" % json.dumps(LEUTE))
        self.assertEqual(out["bcc"], ["eins@beispiel.invalid", "zwei@beispiel.invalid",
                                      "geteilt@beispiel.invalid"])

    def test_gross_klein_ist_dieselbe_adresse(self):
        leute = [person(1, "A", "Eins@Beispiel.invalid"), person(2, "B", "eins@beispiel.invalid")]
        out = js("mailToAll(mailRecipients(%s), '', '')" % json.dumps(leute))
        self.assertEqual(len(out["bcc"]), 1)

    def test_unsinn_ist_keine_adresse(self):
        self.assertEqual(js("mailAddresses('keine Adresse @ oder so')"), [])
        self.assertEqual(js("mailAddresses('a@b')"), [])
        self.assertEqual(js("mailAddresses(null)"), [])


@unittest.skipUnless(NODE, "Node fehlt - die Mail-Logik wird nicht ausgefuehrt")
class TestLink(unittest.TestCase):

    def test_bcc_und_an_leer(self):
        href = js("mailtoHref(['eins@beispiel.invalid', 'zwei@beispiel.invalid'], '', '')")
        self.assertEqual(href, "mailto:?bcc=eins@beispiel.invalid,zwei@beispiel.invalid")

    def test_betreff_und_text_kodiert(self):
        href = js("mailtoHref(['a+b@beispiel.invalid'], 'Neuigkeiten & Grüße?', 'Hallo\\nihr')")
        self.assertEqual(href, "mailto:?bcc=a%2Bb@beispiel.invalid"
                               "&subject=Neuigkeiten%20%26%20Gr%C3%BC%C3%9Fe%3F"
                               "&body=Hallo%0D%0Aihr")

    def test_passt_in_einen_link(self):
        out = js("mailToAll(mailRecipients(%s), 'Neuigkeiten?', '')" % json.dumps(LEUTE))
        self.assertFalse(out["tooLong"])
        self.assertTrue(out["href"].startswith("mailto:?bcc="))

    def test_zu_viele_adressen(self):
        viele = [person(i, "P%d" % i, "verwandte.person.%03d@beispiel.invalid" % i)
                 for i in range(80)]
        out = js("mailToAll(mailRecipients(%s), 'Neuigkeiten?', 'Hallo')" % json.dumps(viele))
        self.assertTrue(out["tooLong"])
        self.assertEqual(len(out["bcc"]), 80)
        self.assertEqual(out["bare"], "mailto:?subject=Neuigkeiten%3F&body=Hallo")


class TestSeite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.q = vorlage()

    def test_personenblatt_macht_einen_link(self):
        blatt = funktion(self.q, "sheetHTML")
        self.assertIn('class="maillink" href="mailto:', blatt)
        self.assertIn('r[0] === "E-Mail" ? mailLinks(r[1]) : esc(r[1])', blatt)

    def test_knopf_unter_optionen(self):
        self.assertIn('id="mailAllBtn"', funktion(self.q, "optionsHTML"))

    def test_uebersicht_zum_abwaehlen(self):
        blatt = funktion(self.q, "mailAllHTML")
        self.assertIn("data-mail-person", blatt)
        self.assertIn('id="mailCopy"', blatt)
        self.assertIn('id="mailSend"', blatt)

    def test_hinweis_ohne_adressen(self):
        self.assertIn("keine einzige E-Mail-Adresse", funktion(self.q, "mailAllHTML"))

    def test_zu_lang_geht_in_die_zwischenablage(self):
        senden = funktion(self.q, "sendMailAll")
        self.assertIn("tooLong", senden)
        self.assertIn('join("; ")', senden)
        self.assertIn("BCC einfügen", senden)


if __name__ == "__main__":
    unittest.main(verbosity=2)
