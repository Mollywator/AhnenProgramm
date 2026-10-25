# -*- coding: utf-8 -*-
"""The search on the left finds an entry by its number.

"262" finds entry #262 and puts it first, next to whatever else has 262 in a
year or a place; "#262" asks for the number alone.  A number that was merged
away says which number it lives on as now - that is how a merge is checked.
`renderList` runs here in node against the page's own code, with invented
people only.

    python tools/test_suche_nummer.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
VORLAGE = os.path.join(HIER, "temp" + "late.html")


def vorlage() -> str:
    with open(VORLAGE, encoding="utf-8") as fh:
        return fh.read()


def teil(text: str, muster: str) -> str:
    treffer = re.search(muster, text, re.S)
    if not treffer:
        raise AssertionError("nicht gefunden: " + muster)
    return treffer.group(0)


LEUTE = [
    {"id": 7, "name": "Zorbas Quendel", "birth": {"year": 1262}, "events": []},
    {"id": 262, "name": "Ilvi Feldkamp", "birth": {"year": 1704}, "events": []},
    {"id": 31, "name": "Xaver Lindwurm", "birth": {"year": 1810}, "events": []},
]


class TestSucheNummer(unittest.TestCase):

    def setUp(self):
        self.s = vorlage()

    def suche(self, query: str, papierkorb=None):
        node = shutil.which("node")
        if not node:
            self.skipTest("node nicht gefunden")
        code = "\n".join([
            "const els = {list: {innerHTML: ''}, counter: {textContent: ''}};",
            "const document = {getElementById: id => els[id]};",
            "const DATA = {people: %s};" % json.dumps(LEUTE),
            "const BY_ID = new Map(DATA.people.map(p => [p.id, p]));",
            "const PHOTOS = {}; let filter = 'alle', centre = null;",
            "let query = %s;" % json.dumps(query),
            "var PAPIERKORB = %s;" % json.dumps(papierkorb or {"eintraege": []}),
            "const anyRelation = () => null, lifespan = () => '', avatarHTML = () => '';",
            "const esc = s => String(s);",
            teil(self.s, r"const fold = s => .*?\n\n"),
            teil(self.s, r"function renderList\(\)\{.*?\n\}"),
            "renderList();",
            "const ids = [...els.list.innerHTML.matchAll(/class=\"row[^\"]*\" data-open=\"(\\d+)\"/g)]"
            ".map(m => +m[1]);",
            "console.log(JSON.stringify({ids, html: els.list.innerHTML}));",
        ])
        out = subprocess.run([node, "-e", code], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_nummer_steht_zuerst(self):
        r = self.suche("262")
        self.assertEqual(r["ids"], [262, 7], "die Nummer zuerst, das Jahr 1262 dahinter")
        self.assertIn('class="row-num">#262<', r["html"])

    def test_raute_sucht_nur_die_nummer(self):
        self.assertEqual(self.suche("#262")["ids"], [262])
        self.assertEqual(self.suche("# 31")["ids"], [31])

    def test_text_sucht_wie_vorher(self):
        self.assertEqual(self.suche("feldkamp")["ids"], [262])
        self.assertEqual(self.suche("18")["ids"], [31])

    def test_zusammengefuehrte_nummer_sagt_wohin(self):
        korb = {"eintraege": [{"behalten": 31, "entfernt": 99,
                               "namen": ["Xaver Lindwurm", "Xaver Lindwurm"]}]}
        r = self.suche("#99", korb)
        self.assertEqual(r["ids"], [])
        self.assertIn("zusammengeführt", r["html"])
        self.assertIn('data-open="31"', r["html"])
        self.assertNotIn("Nichts gefunden", r["html"])

    def test_zurueckgenommen_ist_nicht_mehr_vereint(self):
        korb = {"eintraege": [{"behalten": 31, "entfernt": 99, "rueckgaengig": {"nummer": 99},
                               "namen": ["Xaver Lindwurm", "Xaver Lindwurm"]}]}
        self.assertIn("Nichts gefunden", self.suche("#99", korb)["html"])


if __name__ == "__main__":
    unittest.main()
