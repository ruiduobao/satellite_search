"""test_compare.py — Tests for satellite-search compare + countries (batch3+)."""

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import satellite_search  # noqa: E402


class TestCountryNameZh(unittest.TestCase):
    def test_china(self):
        self.assertEqual(satellite_search._country_zh("PRC"), "中国")
        self.assertEqual(satellite_search._country_zh("CHINA"), "中国")

    def test_usa(self):
        self.assertEqual(satellite_search._country_zh("USA"), "美国")
        self.assertEqual(satellite_search._country_zh("US"), "美国")

    def test_unknown_passthrough(self):
        self.assertEqual(satellite_search._country_zh("ZZ"), "ZZ")

    def test_none(self):
        self.assertIsNone(satellite_search._country_zh(None))


class TestCmdCompare(unittest.TestCase):
    def test_compare_two_satellites(self):
        ns = satellite_search.build_parser().parse_args(["compare", "Sentinel-2A", "Landsat-8"])
        rc = satellite_search.cmd_compare(ns)
        self.assertEqual(rc, 0)

    def test_compare_one_missing(self):
        ns = satellite_search.build_parser().parse_args(
            ["compare", "不存在的卫星xyz", "Sentinel-2A"]
        )
        rc = satellite_search.cmd_compare(ns)
        self.assertEqual(rc, 1)

    def test_compare_wrong_argc(self):
        # argparse rejects too few positional args; we expect SystemExit
        with self.assertRaises(SystemExit):
            satellite_search.build_parser().parse_args(["compare", "Sentinel-2A"])


class TestCmdCountries(unittest.TestCase):
    def test_list_countries(self):
        ns = satellite_search.build_parser().parse_args(["countries"])
        rc = satellite_search.cmd_countries(ns)
        self.assertEqual(rc, 0)


class TestHelpHasNewCommands(unittest.TestCase):
    def test_help_includes_compare_and_countries(self):
        import argparse
        p = satellite_search.build_parser()
        # Check that the subparsers include compare / countries
        for action in p._actions:
            if isinstance(action, argparse._SubParsersAction):
                names = list(action.choices.keys())
                self.assertIn("compare", names)
                self.assertIn("countries", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
