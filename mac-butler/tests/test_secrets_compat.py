#!/usr/bin/env python3

import secrets
import unittest

from butler_secrets.loader import SECRETS_PATHS


class SecretsCompatTests(unittest.TestCase):
    def test_stdlib_secrets_token_hex_is_available(self):
        token = secrets.token_hex(8)
        self.assertEqual(len(token), 16)
        self.assertTrue(all(char in "0123456789abcdef" for char in token))

    def test_loader_prefers_vault_path(self):
        self.assertTrue(str(SECRETS_PATHS[0]).endswith("vault/local_secrets.json"))


if __name__ == "__main__":
    unittest.main()
