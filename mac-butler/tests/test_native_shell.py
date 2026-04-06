#!/usr/bin/env python3

import unittest

from projects.native_shell import BurryWindowApi


class _FakeWindow:
    def __init__(self):
        self.on_top = True
        self.minimized = False
        self.closed = False

    def minimize(self):
        self.minimized = True

    def destroy(self):
        self.closed = True


class NativeShellTests(unittest.TestCase):
    def test_window_api_toggles_pin(self):
        api = BurryWindowApi()
        window = _FakeWindow()
        api.attach(window)

        result = api.toggle_pin()

        self.assertTrue(result["ok"])
        self.assertFalse(result["pinned"])
        self.assertFalse(window.on_top)

    def test_window_api_minimizes_and_closes(self):
        api = BurryWindowApi()
        window = _FakeWindow()
        api.attach(window)

        self.assertTrue(api.minimize()["ok"])
        self.assertTrue(api.close()["ok"])
        self.assertTrue(window.minimized)
        self.assertTrue(window.closed)


if __name__ == "__main__":
    unittest.main()
