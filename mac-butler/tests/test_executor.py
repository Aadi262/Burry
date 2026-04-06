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

    @patch("executor.engine.subprocess.Popen")
    def test_open_app_maps_google_sheet_to_browser_url(self, mock_popen):
        result = Executor().open_app("google sheet")
        self.assertIn("sheets.google.com", result)
        mock_popen.assert_called_once_with(["open", "-a", "Google Chrome", "https://sheets.google.com"])

    @patch("executor.engine.subprocess.run")
    def test_browser_new_tab_uses_applescript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_new_tab("https://example.com")
        self.assertIn("opened new browser tab", result)
        script = mock_run.call_args.args[0][2]
        self.assertIn("Google Chrome", script)
        self.assertIn("https://example.com", script)

    @patch.object(Executor, "browser_new_tab", return_value="opened new browser tab: https://www.google.com/search?q=gemma")
    def test_browser_search_uses_google_query(self, mock_new_tab):
        result = Executor().browser_search("gemma")
        self.assertIn("opened new browser tab", result)
        self.assertIn("google.com/search", mock_new_tab.call_args.args[0])

    @patch("executor.engine.subprocess.run")
    def test_browser_close_tab_uses_applescript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_close_tab()
        self.assertEqual(result, "closed current browser tab")
        self.assertIn("close active tab", mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_browser_close_window_uses_applescript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_close_window()
        self.assertEqual(result, "closed current browser window")
        self.assertIn("close front window", mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_pause_video_executes_browser_javascript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().pause_video()
        self.assertEqual(result, "paused media in browser")
        self.assertIn("execute javascript", mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_volume_set_uses_osascript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().system_volume_set(42)
        self.assertEqual(result, "set system volume to 42")
        self.assertEqual(mock_run.call_args.args[0], ["osascript", "-e", "set volume output volume 42"])

    @patch("executor.engine.subprocess.run")
    def test_volume_adjust_uses_osascript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().system_volume_adjust("down")
        self.assertEqual(result, "adjusted system volume down")
        self.assertIn("targetVolume", mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_take_screenshot_uses_screencapture(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().take_screenshot()
        self.assertTrue(result.startswith("/tmp/butler_screenshot_"))
        self.assertEqual(mock_run.call_args.args[0][:2], ["screencapture", "-x"])

    @patch.object(Executor, "open_url", return_value="opened https://wa.me/919999999999?text=hello")
    def test_whatsapp_send_prefers_phone_url(self, mock_open_url):
        result = Executor().whatsapp_send("vedang", "+91 99999 99999", "hello")
        self.assertIn("opened WhatsApp message flow", result)
        self.assertEqual(mock_open_url.call_args.args[0], "https://wa.me/919999999999?text=hello")

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

    @patch.object(Executor, "open_editor", return_value="Visual Studio Code is not installed")
    def test_create_file_in_editor_reports_created_path_even_if_editor_missing(self, _mock_open_editor):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            result = Executor().create_file_in_editor("demo.txt", editor="vscode", directory=tmpdir)
            self.assertIn(str(Path(tmpdir) / "demo.txt"), result)
        self.assertIn("Visual Studio Code is not installed", result)

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
