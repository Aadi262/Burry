import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "system_check.py"
SPEC = importlib.util.spec_from_file_location("system_check", MODULE_PATH)
system_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(system_check)


class SystemCheckTests(unittest.TestCase):
    @patch.object(system_check, "_phase1_calendar_read_check", return_value={"name": "phase1_calendar_read", "ok": True})
    @patch.object(system_check, "_phase1_filesystem_check", return_value={"name": "phase1_filesystem", "ok": True})
    @patch.object(system_check, "_run_python_check")
    def test_phase1_host_steps_include_safe_checks_and_skip_real_sends_by_default(
        self,
        mock_python,
        _mock_filesystem,
        _mock_calendar,
    ):
        mock_python.side_effect = lambda name, source, timeout=120: {
            "name": name,
            "ok": True,
            "output": "",
            "timeout": timeout,
        }

        steps = system_check._phase1_host_steps()

        self.assertEqual(
            [step["name"] for step in steps],
            [
                "phase1_filesystem",
                "phase1_browser",
                "phase1_terminal",
                "phase1_calendar_read",
                "phase1_gmail_compose",
                "phase1_whatsapp_open",
                "phase1_reminder",
                "phase1_mail_send",
                "phase1_whatsapp_send",
            ],
        )
        self.assertTrue(steps[-2]["skipped"])
        self.assertTrue(steps[-1]["skipped"])

    @patch.object(system_check, "_phase1_calendar_read_check", return_value={"name": "phase1_calendar_read", "ok": True})
    @patch.object(system_check, "_phase1_filesystem_check", return_value={"name": "phase1_filesystem", "ok": True})
    @patch.object(system_check, "_run_python_check")
    def test_phase1_host_steps_run_real_send_smokes_when_targets_are_provided(
        self,
        mock_python,
        _mock_filesystem,
        _mock_calendar,
    ):
        mock_python.side_effect = lambda name, source, timeout=120: {
            "name": name,
            "ok": True,
            "output": source,
            "timeout": timeout,
        }

        steps = system_check._phase1_host_steps(
            mail_to="phase1@example.com",
            whatsapp_contact="Rushil",
            whatsapp_message="ship it",
        )

        self.assertFalse(steps[-2].get("skipped", False))
        self.assertFalse(steps[-1].get("skipped", False))
        self.assertIn("phase1@example.com", steps[-2]["output"])
        self.assertIn("Rushil", steps[-1]["output"])

    @patch.object(system_check, "_phase1_host_steps", return_value=[{"name": "phase1_browser", "ok": True}])
    @patch.object(system_check, "_default_steps", return_value=[{"name": "unit_tests", "ok": True}])
    def test_run_checks_appends_phase1_host_steps_when_requested(self, mock_default, mock_phase1):
        summary = system_check.run_checks(include_phase1_host=True, mail_to="phase1@example.com")

        self.assertTrue(summary["ok"])
        self.assertEqual([step["name"] for step in summary["steps"]], ["unit_tests", "phase1_browser"])
        mock_default.assert_called_once()
        mock_phase1.assert_called_once_with(
            mail_to="phase1@example.com",
            whatsapp_contact="",
            whatsapp_message="",
        )

    @patch.object(system_check, "_phase1_host_steps", return_value=[{"name": "phase1_browser", "ok": True}])
    @patch.object(system_check, "_default_steps", return_value=[{"name": "unit_tests", "ok": True}])
    def test_run_checks_can_skip_default_sequence_for_host_only_mode(self, mock_default, mock_phase1):
        summary = system_check.run_checks(include_phase1_host=True, phase1_host_only=True)

        self.assertTrue(summary["ok"])
        self.assertEqual([step["name"] for step in summary["steps"]], ["phase1_browser"])
        mock_default.assert_not_called()
        mock_phase1.assert_called_once_with(
            mail_to="",
            whatsapp_contact="",
            whatsapp_message="",
        )

    def test_skipped_steps_do_not_fail_overall_status(self):
        with patch.object(system_check, "_default_steps", return_value=[{"name": "unit_tests", "ok": True}]), patch.object(
            system_check,
            "_phase1_host_steps",
            return_value=[{"name": "phase1_mail_send", "ok": True, "skipped": True}],
        ):
            summary = system_check.run_checks(include_phase1_host=True)

        self.assertTrue(summary["ok"])

    def test_stringify_output_decodes_timeout_bytes(self):
        self.assertEqual(system_check._stringify_output(b"hello"), "hello")
        self.assertEqual(system_check._stringify_output("world"), "world")

    @patch("executor.engine.Executor.run", return_value=[{"status": "ok", "result": "Calendar read is unavailable until Calendar automation access is granted on this host."}])
    def test_phase1_calendar_read_check_marks_permission_block_as_skipped(self, _mock_run):
        step = system_check._phase1_calendar_read_check()

        self.assertTrue(step["ok"])
        self.assertTrue(step["skipped"])
        self.assertEqual(step["name"], "phase1_calendar_read")

    @patch.object(system_check, "_phase3a_reminder_check", return_value={"name": "phase3a_reminder", "ok": True})
    @patch.object(system_check, "_phase3a_calendar_write_check", return_value={"name": "phase3a_calendar_add", "ok": True})
    @patch.object(system_check, "_phase3a_browser_check", return_value={"name": "phase3a_browser", "ok": True})
    @patch.object(system_check, "_phase3a_filesystem_check", return_value={"name": "phase3a_filesystem", "ok": True})
    @patch.object(system_check, "_run_python_check")
    def test_phase3a_host_steps_include_safe_checks_and_skip_disruptive_system_by_default(
        self,
        mock_python,
        _mock_filesystem,
        _mock_browser,
        _mock_calendar,
        _mock_reminder,
    ):
        mock_python.side_effect = lambda name, source, timeout=120: {
            "name": name,
            "ok": True,
            "output": "",
            "timeout": timeout,
        }

        steps = system_check._phase3a_host_steps()

        self.assertEqual(
            [step["name"] for step in steps],
            [
                "phase3a_filesystem",
                "phase3a_browser",
                "phase3a_calendar_add",
                "phase3a_reminder",
                "phase3a_system_safe",
                "phase3a_system_disruptive",
            ],
        )
        self.assertTrue(steps[-1]["skipped"])

    @patch.object(system_check, "_phase3a_reminder_check", return_value={"name": "phase3a_reminder", "ok": True})
    @patch.object(system_check, "_phase3a_calendar_write_check", return_value={"name": "phase3a_calendar_add", "ok": True})
    @patch.object(system_check, "_phase3a_browser_check", return_value={"name": "phase3a_browser", "ok": True})
    @patch.object(system_check, "_phase3a_filesystem_check", return_value={"name": "phase3a_filesystem", "ok": True})
    @patch.object(system_check, "_run_python_check")
    def test_phase3a_host_steps_can_run_disruptive_system_checks(
        self,
        mock_python,
        _mock_filesystem,
        _mock_browser,
        _mock_calendar,
        _mock_reminder,
    ):
        mock_python.side_effect = lambda name, source, timeout=120: {
            "name": name,
            "ok": True,
            "output": source,
            "timeout": timeout,
        }

        steps = system_check._phase3a_host_steps(allow_disruptive_system=True)

        self.assertFalse(steps[-1].get("skipped", False))
        self.assertEqual(steps[-1]["name"], "phase3a_system_disruptive")

    @patch("executor.engine.Executor.run")
    def test_phase3a_browser_check_uses_local_file_targets(self, mock_run):
        mock_run.return_value = [
            {"status": "ok", "verification_status": "verified"},
            {"status": "ok", "verification_status": "verified"},
            {"status": "ok", "verification_status": "verified"},
            {"status": "ok", "verification_status": "verified"},
            {"status": "ok", "verification_status": "verified"},
        ]

        step = system_check._phase3a_browser_check()

        self.assertTrue(step["ok"])
        actions = mock_run.call_args.args[0]
        urls = [action["url"] for action in actions if "url" in action]
        self.assertTrue(urls)
        self.assertTrue(all(url.startswith("file://") for url in urls))
        self.assertTrue(all("example." not in url for url in urls))

    @patch.object(system_check, "_phase3a_host_steps", return_value=[{"name": "phase3a_browser", "ok": True}])
    @patch.object(system_check, "_default_steps", return_value=[{"name": "unit_tests", "ok": True}])
    def test_run_checks_appends_phase3a_host_steps_when_requested(self, mock_default, mock_phase3a):
        summary = system_check.run_checks(include_phase3a_host=True, allow_disruptive_system=True)

        self.assertTrue(summary["ok"])
        self.assertEqual([step["name"] for step in summary["steps"]], ["unit_tests", "phase3a_browser"])
        mock_default.assert_called_once()
        mock_phase3a.assert_called_once_with(allow_disruptive_system=True)

    @patch.object(system_check, "_phase3a_host_steps", return_value=[{"name": "phase3a_browser", "ok": True}])
    @patch.object(system_check, "_default_steps", return_value=[{"name": "unit_tests", "ok": True}])
    def test_run_checks_can_skip_default_sequence_for_phase3a_host_only_mode(self, mock_default, mock_phase3a):
        summary = system_check.run_checks(include_phase3a_host=True, phase3a_host_only=True)

        self.assertTrue(summary["ok"])
        self.assertEqual([step["name"] for step in summary["steps"]], ["phase3a_browser"])
        mock_default.assert_not_called()
        mock_phase3a.assert_called_once_with(allow_disruptive_system=False)


if __name__ == "__main__":
    unittest.main()
