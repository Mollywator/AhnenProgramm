# -*- coding: utf-8 -*-
"""The "Reihe" switch in the near view's menu: side lines by generation.

Asked for: show an aunt, and her children, without switching to "Ganze Linie"
and getting the whole family at once.  Reihe 1 is the brothers and sisters of
the parents with their children, Reihe 2 adds those of the grandparents with
children and grandchildren, Reihe 3 those of the great-grandparents.  Each line
stops at the centre's own generation.

nearSet is run in node on a made-up family, numbers only:

    1+2                                   (Reihe 3 needs them on the stage)
     |-- 3+5 ............ 4 - 40 - 41 - 42 - 43
     |    |-- 6 ......... 7 - 70 - 71 - 72
     |    |   |-- 8+80 .. 9+90 - 91 - 92
     |    |   |    |-- 100   (the centre)

    python tools/test_reihe.py
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

# id -> (parents, spouses)
FAMILIE = {
    1: ([], [2]), 2: ([], [1]),
    3: ([1, 2], [5]), 5: ([], [3]), 4: ([1, 2], []),
    40: ([4], []), 41: ([40], []), 42: ([41], []), 43: ([42], []),
    6: ([3, 5], []), 7: ([3, 5], []),
    70: ([7], []), 71: ([70], []), 72: ([71], []),
    8: ([6], [80]), 80: ([], [8]), 9: ([6], [90]), 90: ([], [9]),
    91: ([9, 90], []), 92: ([91], []),
    100: ([8, 80], []),
}


def teil(s: str, muster: str) -> str:
    treffer = re.search(muster, s, re.S)
    if treffer is None:
        raise AssertionError("nicht mehr in der Seite: " + muster)
    return treffer.group(0)


class TestReihe(unittest.TestCase):

    def setUp(self):
        with open(VORLAGE, encoding="utf-8") as fh:
            self.s = fh.read()
        self.node = shutil.which("node")
        if not self.node:
            self.skipTest("node nicht gefunden")

    def buehne(self, reihe):
        leute = [{"id": i, "parents": e, "spouses": sp,
                  "children": [k for k, (ke, _) in FAMILIE.items() if i in ke]}
                 for i, (e, sp) in FAMILIE.items()]
        code = "\n".join([
            "const BY_ID = new Map(%s.map(p => [p.id, p]));" % json.dumps(leute),
            teil(self.s, r"const nearExtra = \{.*?\};"),
            "nearExtra.reihe = %d;" % reihe,
            teil(self.s, r"function nearSet\(id\)\{.*?\n\}"),
            "console.log(JSON.stringify(Array.from(nearSet(100))));",
        ])
        lauf = subprocess.run([self.node, "-e", code], capture_output=True, text=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        return set(json.loads(lauf.stdout))

    def test_ohne_reihe_keine_tante(self):
        self.assertTrue({9, 90, 91, 7, 4}.isdisjoint(self.buehne(0)))

    def test_erste_reihe_tante_mit_kindern(self):
        b = self.buehne(1)
        self.assertTrue({9, 90, 91} <= b)
        self.assertNotIn(92, b, "die Linie geht unter die Generation des Mittelpunkts")
        self.assertTrue({7, 70, 4}.isdisjoint(b))

    def test_zweite_reihe_grosstante_bis_zur_eigenen_generation(self):
        b = self.buehne(2)
        self.assertTrue({9, 91, 7, 70, 71} <= b)
        self.assertNotIn(72, b)
        self.assertTrue({4, 40}.isdisjoint(b))

    def test_dritte_reihe_bringt_die_gemeinsamen_eltern_mit(self):
        b = self.buehne(3)
        self.assertTrue({1, 2, 4, 40, 41, 42, 7, 71, 91} <= b)
        self.assertNotIn(43, b)

    def test_knopf_steht_im_menue_der_nahen_familie(self):
        menue = teil(self.s, r'<span class="popover" id="nearMenu" hidden>.*?\n          </span>')
        for n in "0123":
            self.assertIn('data-reihe="%s"' % n, menue)
        self.assertIn(">Reihe<", menue)


if __name__ == "__main__":
    unittest.main(verbosity=2)
