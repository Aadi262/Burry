#!/usr/bin/env python3

import importlib
import os
import unittest
from unittest.mock import patch

import butler_config


class RuntimeConfigTests(unittest.TestCase):
    def test_searxng_url_defaults_to_unoccupied_local_port(self):
        with patch.dict(os.environ, {}, clear=True):
            reloaded = importlib.reload(butler_config)
            try:
                self.assertEqual(reloaded.SEARXNG_URL, "http://127.0.0.1:18080")
            finally:
                importlib.reload(butler_config)

    def test_searxng_url_can_be_overridden(self):
        with patch.dict(os.environ, {"SEARXNG_URL": "http://127.0.0.1:19090/"}, clear=False):
            reloaded = importlib.reload(butler_config)
            try:
                self.assertEqual(reloaded.SEARXNG_URL, "http://127.0.0.1:19090")
            finally:
                os.environ.pop("SEARXNG_URL", None)
                importlib.reload(butler_config)


if __name__ == "__main__":
    unittest.main()
