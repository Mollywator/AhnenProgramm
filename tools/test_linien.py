# -*- coding: utf-8 -*-
"""Two families' vertical lines may never lie on top of each other.

The case that was reported: a couple on the left and a couple on the right, one
row down a child of the left couple standing exactly under the middle of the
right couple.  The child's line and the right couple's line ran down the same
x, the left bar ended right where the right couple's line came down, and the
picture said the child belonged to the right couple.  Only hovering told the
truth.

The layout itself is run in node here, with the geometry of that screenshot.
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


def teil(s: str, muster: str) -> str:
    treffer = re.search(muster, s, re.S)
    if treffer is None:
        raise AssertionError("nicht mehr in der Seite: " + muster)
    return treffer.group(0)


def bar(anchor, *kids, gen=0):
    return {"gen": gen, "anchor": anchor, "kids": [{"x": x} for x in kids]}


class TestLinienLiegenNichtAufeinander(unittest.TestCase):

    def setUp(self):
        with open(VORLAGE, encoding="utf-8") as fh:
            self.s = fh.read()
        self.node = shutil.which("node")
        if not self.node:
            self.skipTest("node nicht gefunden")

    def trennen(self, bars):
        code = "\n".join([
            teil(self.s, r"const POST_GAP = \d+;"),
            teil(self.s, r"function separatePosts\(bars\)\{.*?\n\}"),
            "const bars = " + json.dumps(bars) + ";",
            "separatePosts(bars);",
            "console.log(JSON.stringify(bars));",
        ])
        lauf = subprocess.run([self.node, "-e", code], capture_output=True, text=True)
        self.assertEqual(lauf.returncode, 0, lauf.stderr)
        gap = int(re.search(r"const POST_GAP = (\d+);", self.s).group(1))
        return json.loads(lauf.stdout), gap

    def pruefe_abstand(self, bars, gap):
        for a in bars:
            for b in bars:
                if a is b or a["gen"] != b["gen"]:
                    continue
                for kid in a["kids"]:
                    self.assertGreaterEqual(
                        abs(kid["x"] - b["anchor"]), gap,
                        "Kindlinie %s liegt auf der Elternlinie %s" % (kid["x"], b["anchor"]))

    def test_der_gemeldete_fall(self):
        # left couple drops at 387 to children at 178, 387 and 808;
        # right couple drops at 808 to a child at 598.
        bars, gap = self.trennen([bar(387, 178, 387, 808), bar(808, 598)])
        self.pruefe_abstand(bars, gap)
        links, rechts = bars
        # the moved line goes towards its own parents, so the left bar now ends
        # before the right couple's line instead of running into it
        self.assertLess(links["x1"], rechts["anchor"])
        self.assertEqual(links["x1"], 808 - gap)
        # and it still crosses the right bar in the open, where that one hops
        self.assertGreater(links["x1"], rechts["x0"])
        self.assertLess(links["x1"], rechts["x1"])

    def test_von_rechts_kommend(self):
        bars, gap = self.trennen([bar(1200, 800), bar(803, 600)])
        self.pruefe_abstand(bars, gap)
        self.assertEqual(bars[0]["kids"][0]["x"], 803 + gap)
        self.assertEqual(bars[0]["x0"], 803 + gap)

    def test_eigene_linie_bleibt(self):
        # a child right under its own parents is the cross that is meant
        bars, _ = self.trennen([bar(387, 387, 178)])
        self.assertEqual(bars[0]["kids"][0]["x"], 387)

    def test_andere_generation_stoert_nicht(self):
        bars, _ = self.trennen([bar(387, 808, gen=0), bar(808, 598, gen=1)])
        self.assertEqual(bars[0]["kids"][0]["x"], 808)

    def test_wird_vor_den_spuren_aufgerufen(self):
        aufruf = self.s.index("separatePosts(bars);")
        self.assertLess(aufruf, self.s.index("list.sort((a, b) => a.x0 - b.x0);"))


if __name__ == "__main__":
    unittest.main()
