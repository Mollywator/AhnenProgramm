# -*- coding: utf-8 -*-
"""The button bar at the top stays on the right, however narrow the window.

The masthead wraps, and the spacer that pushes the bar right only works within
its own line - so after the break the bar started at the left, and in a small
window it was somewhere else than in a big one.

    python tools/test_leiste_rechts.py
"""
from __future__ import annotations

import os
import re
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))


def regel(css: str, selektor: str) -> str:
    treffer = re.search(r"(?m)^" + re.escape(selektor) + r"\{([^}]*)\}", css)
    return treffer.group(1) if treffer else ""


class TestLeisteRechts(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(HIER, "template.html"), encoding="utf-8") as fh:
            self.s = fh.read()
        self.tools = re.sub(r"\s+", "", regel(self.s, ".tools"))

    def test_leiste_schiebt_sich_selbst_nach_rechts(self):
        """Not reliant on the spacer, which does nothing after the break."""
        self.assertIn("margin-left:auto", self.tools)

    def test_umbrochene_leiste_bleibt_rechtsbuendig(self):
        self.assertIn("flex-wrap:wrap", self.tools)
        self.assertIn("justify-content:flex-end", self.tools)

    def test_erst_stapeln_dann_unter_den_titel(self):
        """Two lines beside the title before a line of its own under it."""
        self.assertIn("flex:110", self.tools)
        self.assertRegex(self.tools, r"min-width:min\(\d+px,100%\)")
        self.assertNotIn('class="spacer"', self.s,
                         "der Spacer nimmt der Leiste die Haelfte des Platzes weg")

    def test_kopf_bricht_weiter_um(self):
        """The title keeps its line; the bar goes under it rather than over it."""
        self.assertIn("flex-wrap:wrap", re.sub(r"\s+", "", regel(self.s, ".masthead")))


if __name__ == "__main__":
    unittest.main()
