import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from executor.engine import Executor

TEST_ROOT = Path(__file__).resolve().parents[1]


class ExecutorTests(unittest.TestCase):
    def test_requires_confirmation_for_git_push(self):
        executor = Executor()
        action = {"type": "run_command", "cmd": "git push", "cwd": "~/Burry/mac-butler"}
        self.assertTrue(executor._requires_confirmation(action))

    @patch.object(Executor, "_ask_confirmation", return_value=False)
    def test_run_marks_cancelled_confirmation_as_skipped(self, _mock_confirm):
        executor = Executor()
        action = {"type": "run_command", "cmd": "git push", "cwd": "~/Burry/mac-butler"}
        result = executor.run([action])
        self.assertEqual(result[0]["status"], "ok")
        self.assertIn("cancelled", result[0]["result"])

    @patch("executor.app_state.is_app_running", return_value=True)
    @patch("executor.engine.subprocess.run")
    def test_open_terminal_tab_uses_terminal(self, mock_run, _mock_running):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        executor = Executor()
        result = executor.open_terminal(mode="tab", cmd="echo hello", cwd="~/Burry/mac-butler")
        self.assertIn("new Terminal tab", result)
        args = mock_run.call_args.args[0]
        self.assertEqual(args[:2], ["osascript", "-e"])
        self.assertIn('keystroke "t" using command down', args[2])

    @patch("executor.engine.subprocess.run")
    def test_search_and_play_action_uses_applescript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        executor = Executor()
        result = executor.run([{"type": "search_and_play", "query": "chikni chameli"}])
        self.assertEqual(result[0]["status"], "ok")
        self.assertIn("searched and playing", result[0]["result"])
        args = mock_run.call_args.args[0]
        self.assertEqual(args[:2], ["osascript", "-e"])
        self.assertEqual(args[2], 'tell application "Spotify" to activate')
        self.assertIn('play track "spotify:search:chikni%20chameli"', args[4])

    @patch("executor.engine.subprocess.run")
    def test_search_and_play_reports_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)
        result = Executor().search_and_play_spotify("chikni chameli")
        self.assertIn("timed out", result)

    @patch.object(Executor, "_cursor_cli_path", return_value="/usr/local/bin/cursor")
    @patch("executor.engine.subprocess.Popen")
    def test_create_and_open_prefers_cursor_cli(self, mock_popen, _mock_cursor_cli):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            target = Path(tmpdir) / "butler-create-and-open"
            result = Executor().create_and_open(str(target), "cursor")

        self.assertIn("opened", result)
        mock_popen.assert_called_once_with(["/usr/local/bin/cursor", str(target.resolve(strict=False))])

    @patch.object(Executor, "_vscode_cli_path", return_value=None)
    @patch.object(Executor, "_editor_app_available", return_value=False)
    def test_open_editor_reports_missing_vscode_instead_of_cursor(self, _mock_available, _mock_vscode_cli):
        result = Executor().open_editor(editor="vscode", mode="smart")
        self.assertEqual(result, "Visual Studio Code is not installed")

    @patch("executor.engine.subprocess.run")
    def test_run_command_creates_missing_cwd_and_caps_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout="x" * 350, stderr="")
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            missing_cwd = Path(tmpdir) / "new-workspace"
            result = Executor().run_command("mkdir demo && code .", cwd=str(missing_cwd))

            self.assertTrue(missing_cwd.exists())

        self.assertEqual(len(result), 300)
        self.assertTrue(mock_run.call_args.kwargs["shell"])
        self.assertEqual(
            mock_run.call_args.kwargs["cwd"],
            str(missing_cwd.resolve(strict=False)),
        )

    @patch.object(Executor, "open_terminal", return_value="opened new Terminal tab")
    def test_ssh_open_uses_vps_helper_script(self, mock_open_terminal):
        result = Executor().ssh_open("root@194.163.146.149")

        self.assertIn("opened", result)
        command = mock_open_terminal.call_args.kwargs["cmd"]
        self.assertIn("scripts/vps.py", command)
        self.assertIn("shell", command)

    @patch("executor.engine.subprocess.run")
    def test_ssh_command_uses_vps_helper_script(self, mock_run):
        mock_run.return_value = MagicMock(stdout="docker ok", stderr="")

        result = Executor().ssh_command("root@194.163.146.149", "docker ps")

        self.assertEqual(result, "docker ok")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[0], "python3")
        self.assertTrue(args[1].endswith("scripts/vps.py"))
        self.assertEqual(args[2:5], ["exec", "--host", "root@194.163.146.149"])
        self.assertEqual(args[5], "docker ps")


if __name__ == "__main__":
    unittest.main()
