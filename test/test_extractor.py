#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2018-2020 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import sys
import time
import string
from datetime import datetime, timedelta

import unittest
from unittest.mock import patch

from gallery_dl import extractor
from gallery_dl.extractor.common import Extractor, Message
from gallery_dl.extractor.directlink import DirectlinkExtractor as DLExtractor


class FakeExtractor(Extractor):
    category = "fake"
    subcategory = "test"
    pattern = "fake:"

    def items(self):
        yield Message.Version, 1
        yield Message.Url, "text:foobar", {}


class TestExtractorModule(unittest.TestCase):
    VALID_URIS = (
        "https://example.org/file.jpg",
        "tumblr:foobar",
        "oauth:flickr",
        "test:pixiv:",
        "recursive:https://example.org/document.html",
    )

    def setUp(self):
        extractor._cache.clear()
        extractor._module_iter = iter(extractor.modules)

    def test_find(self):
        for uri in self.VALID_URIS:
            result = extractor.find(uri)
            self.assertIsInstance(result, Extractor, uri)

        for not_found in ("", "/tmp/file.ext"):
            self.assertIsNone(extractor.find(not_found))

        for invalid in (None, [], {}, 123, b"test:"):
            with self.assertRaises(TypeError):
                extractor.find(invalid)

    def test_add(self):
        uri = "fake:foobar"
        self.assertIsNone(extractor.find(uri))

        extractor.add(FakeExtractor)
        self.assertIsInstance(extractor.find(uri), FakeExtractor)

    def test_add_module(self):
        uri = "fake:foobar"
        self.assertIsNone(extractor.find(uri))

        classes = extractor.add_module(sys.modules[__name__])
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0].pattern, FakeExtractor.pattern)
        self.assertEqual(classes[0], FakeExtractor)
        self.assertIsInstance(extractor.find(uri), FakeExtractor)

    def test_blacklist(self):
        link_uri = "https://example.org/file.jpg"
        test_uri = "test:"
        fake_uri = "fake:"

        self.assertIsInstance(extractor.find(link_uri), DLExtractor)
        self.assertIsInstance(extractor.find(test_uri), Extractor)
        self.assertIsNone(extractor.find(fake_uri))

        with extractor.blacklist(["directlink"]):
            self.assertIsNone(extractor.find(link_uri))
            self.assertIsInstance(extractor.find(test_uri), Extractor)
            self.assertIsNone(extractor.find(fake_uri))

        with extractor.blacklist([], [DLExtractor, FakeExtractor]):
            self.assertIsNone(extractor.find(link_uri))
            self.assertIsInstance(extractor.find(test_uri), Extractor)
            self.assertIsNone(extractor.find(fake_uri))

        with extractor.blacklist(["test"], [DLExtractor]):
            self.assertIsNone(extractor.find(link_uri))
            self.assertIsNone(extractor.find(test_uri))
            self.assertIsNone(extractor.find(fake_uri))

    def test_from_url(self):
        for uri in self.VALID_URIS:
            cls = extractor.find(uri).__class__
            extr = cls.from_url(uri)
            self.assertIs(type(extr), cls)
            self.assertIsInstance(extr, Extractor)

        for not_found in ("", "/tmp/file.ext"):
            self.assertIsNone(FakeExtractor.from_url(not_found))

        for invalid in (None, [], {}, 123, b"test:"):
            with self.assertRaises(TypeError):
                FakeExtractor.from_url(invalid)

    def test_unique_pattern_matches(self):
        test_urls = []

        # collect testcase URLs
        for extr in extractor.extractors():
            for testcase in extr._get_tests():
                test_urls.append((testcase[0], extr))

        # iterate over all testcase URLs
        for url, extr1 in test_urls:
            matches = []

            # ... and apply all regex patterns to each one
            for extr2 in extractor._cache:

                # skip DirectlinkExtractor pattern if it isn't tested
                if extr1 != DLExtractor and extr2 == DLExtractor:
                    continue

                match = extr2.pattern.match(url)
                if match:
                    matches.append(match)

            # fail if more or less than 1 match happened
            if len(matches) > 1:
                msg = "'{}' gets matched by more than one pattern:".format(url)
                for match in matches:
                    msg += "\n- "
                    msg += match.re.pattern
                self.fail(msg)

            if len(matches) < 1:
                msg = "'{}' isn't matched by any pattern".format(url)
                self.fail(msg)

    def test_docstrings(self):
        """ensure docstring uniqueness"""
        for extr1 in extractor.extractors():
            for extr2 in extractor.extractors():
                if extr1 != extr2 and extr1.__doc__ and extr2.__doc__:
                    self.assertNotEqual(
                        extr1.__doc__,
                        extr2.__doc__,
                        "{} <-> {}".format(extr1, extr2),
                    )

    def test_names(self):
        """Ensure extractor classes are named CategorySubcategoryExtractor"""
        def capitalize(c):
            if "-" in c:
                return string.capwords(c.replace("-", " ")).replace(" ", "")
            return c.capitalize()

        for extr in extractor.extractors():
            if extr.category not in ("", "oauth"):
                expected = "{}{}Extractor".format(
                    capitalize(extr.category),
                    capitalize(extr.subcategory),
                )
                if expected[0].isdigit():
                    expected = "_" + expected
                self.assertEqual(expected, extr.__name__)


class TestExtractorWait(unittest.TestCase):

    def test_wait_seconds(self):
        extr = extractor.find("test:")
        seconds = 5
        until = time.time() + seconds

        with patch("time.sleep") as sleep, patch.object(extr, "log") as log:
            extr.wait(seconds=seconds)

            sleep.assert_called_once_with(6.0)

            calls = log.info.mock_calls
            self.assertEqual(len(calls), 1)
            self._assert_isotime(calls[0][1][1], until)

    def test_wait_until(self):
        extr = extractor.find("test:")
        until = time.time() + 5

        with patch("time.sleep") as sleep, patch.object(extr, "log") as log:
            extr.wait(until=until)

            calls = sleep.mock_calls
            self.assertEqual(len(calls), 1)
            self.assertAlmostEqual(calls[0][1][0], 6.0, places=1)

            calls = log.info.mock_calls
            self.assertEqual(len(calls), 1)
            self._assert_isotime(calls[0][1][1], until)

    def test_wait_until_datetime(self):
        extr = extractor.find("test:")
        until = datetime.utcnow() + timedelta(seconds=5)
        until_local = datetime.now() + timedelta(seconds=5)

        with patch("time.sleep") as sleep, patch.object(extr, "log") as log:
            extr.wait(until=until)

            calls = sleep.mock_calls
            self.assertEqual(len(calls), 1)
            self.assertAlmostEqual(calls[0][1][0], 6.0, places=1)

            calls = log.info.mock_calls
            self.assertEqual(len(calls), 1)
            self._assert_isotime(calls[0][1][1], until_local)

    def _assert_isotime(self, output, until):
        if not isinstance(until, datetime):
            until = datetime.fromtimestamp(until)
        o = self._isotime_to_seconds(output)
        u = self._isotime_to_seconds(until.time().isoformat()[:8])
        self.assertLess(o-u, 1.0)

    @staticmethod
    def _isotime_to_seconds(isotime):
        parts = isotime.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


if __name__ == "__main__":
    unittest.main()
