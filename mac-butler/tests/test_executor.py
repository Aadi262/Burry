import json
import subprocess
import tempfile
import unittest
import urllib.parse
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from executor.engine import Executor

TEST_ROOT = Path(__file__).resolve().parents[1]


class ExecutorTests(unittest.TestCase):
    def test_requires_confirmation_for_git_push(self):
        executor = Executor()
        action = {"type": "run_command", "cmd": "git push", "cwd": "~/Burry/mac-butler"}
        self.assertTrue(executor._requires_confirmation(action))

    def test_requires_confirmation_for_git_commit(self):
        executor = Executor()
        action = {"type": "git_action", "cmd": "commit", "cwd": "~/Burry/mac-butler"}
        self.assertTrue(executor._requires_confirmation(action))

    @patch.object(Executor, "_ask_confirmation", return_value=False)
    def test_run_marks_cancelled_confirmation_as_skipped(self, _mock_confirm):
        executor = Executor()
        action = {"type": "run_command", "cmd": "git push", "cwd": "~/Burry/mac-butler"}
        result = executor.run([action])
        self.assertEqual(result[0]["status"], "ok")
        self.assertIn("cancelled", result[0]["result"])

    @patch("executor.engine.time.sleep", return_value=None)
    @patch("executor.engine.sys.stdin")
    @patch("runtime.clear_confirmation")
    @patch("runtime.resolve_confirmation")
    @patch("runtime.load_runtime_state", side_effect=[{"pending_confirmation": {"id": "abc", "status": "pending"}}, {"pending_confirmation": {"id": "abc", "status": "approved"}}])
    @patch("runtime.request_confirmation", return_value={"id": "abc"})
    @patch("voice.speak")
    @patch("executor.engine.subprocess.run", side_effect=RuntimeError("osascript unavailable"))
    def test_headless_confirmation_waits_for_runtime_flag(
        self,
        _mock_run,
        mock_speak,
        _mock_request,
        _mock_load_runtime,
        _mock_resolve,
        mock_clear,
        mock_stdin,
        _mock_sleep,
    ):
        mock_stdin.closed = True
        mock_stdin.isatty.return_value = False
        executor = Executor()

        approved = executor._ask_confirmation({"type": "run_command", "cmd": "git push"})

        self.assertTrue(approved)
        mock_speak.assert_called()
        mock_clear.assert_called_with("abc")

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

    @patch.object(Executor, "open_terminal", return_value="opened new Terminal window")
    def test_open_app_terminal_smart_opens_new_window_not_existing_focus(self, mock_open_terminal):
        result = Executor().open_app("Terminal")

        self.assertEqual(result, "opened new Terminal window")
        mock_open_terminal.assert_called_once_with("window")

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

    @patch.object(Executor, "_resolve_browser_app", return_value="Google Chrome")
    @patch("executor.engine.subprocess.run")
    def test_open_app_maps_google_sheet_to_browser_url(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().open_app("google sheet")
        self.assertIn("https://sheets.new", result)
        self.assertEqual(
            mock_run.call_args.args[0],
            ["open", "-a", "Google Chrome", "https://sheets.new"],
        )

    @patch.object(Executor, "_browser_window_for_app", return_value="opened browser window")
    @patch.object(Executor, "_browser_app_available", return_value=True)
    @patch.object(Executor, "_is_app_running", return_value=True)
    def test_open_app_chrome_smart_opens_new_browser_window_when_running(
        self,
        _mock_running,
        _mock_available,
        mock_browser_window,
    ):
        result = Executor().open_app("Google Chrome")

        self.assertEqual(result, "opened browser window")
        mock_browser_window.assert_called_once_with("Google Chrome")

    @patch.object(Executor, "_resolve_browser_app", return_value="Google Chrome")
    @patch("executor.engine.subprocess.run")
    def test_browser_new_tab_uses_applescript(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_new_tab("https://example.com")
        self.assertIn("opened new browser tab", result)
        script = mock_run.call_args.args[0][2]
        self.assertIn("Google Chrome", script)
        self.assertIn("https://example.com", script)

    @patch.object(Executor, "_resolve_browser_app", return_value="Safari")
    @patch("executor.engine.subprocess.run")
    def test_browser_window_uses_resolved_browser_family(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_window("https://example.com")
        self.assertIn("opened browser window", result)
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell application "Safari"', script)
        self.assertIn('make new document with properties {URL:"https://example.com"}', script)

    @patch.object(Executor, "_resolve_browser_app", return_value="Brave Browser")
    @patch("executor.engine.subprocess.run")
    def test_browser_go_back_uses_resolved_browser_app(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_go_back()
        self.assertEqual(result, "went back in browser")
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell application "Brave Browser"', script)
        self.assertIn("go back", script)

    @patch.object(Executor, "_resolve_browser_app", return_value="Safari")
    @patch("executor.engine.subprocess.run")
    def test_browser_refresh_uses_safari_reload_script(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_refresh()
        self.assertEqual(result, "reloaded browser tab")
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell application "Safari"', script)
        self.assertIn('window.location.reload();', script)

    @patch("executor.engine.subprocess.run")
    def test_focus_app_uses_applescript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().focus_app("Cursor")
        self.assertEqual(result, "Focused Cursor")
        self.assertIn('tell application "Cursor" to activate', mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_minimize_app_uses_system_events(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().minimize_app("Google Chrome")
        self.assertEqual(result, "Minimized Google Chrome")
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell process "Google Chrome"', script)
        self.assertIn("set miniaturized of window 1 to true", script)

    @patch("executor.engine.subprocess.run")
    def test_hide_app_uses_system_events(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().hide_app("Cursor")
        self.assertEqual(result, "Hidden Cursor")
        self.assertIn('set visible of process "Cursor" to false', mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_chrome_open_tab_uses_applescript(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().chrome_open_tab("https://github.com/Aadi262/Burry")
        self.assertIn("Opened tab", result)
        script = mock_run.call_args.args[0][2]
        self.assertIn('make new tab with properties {URL:"https://github.com/Aadi262/Burry"}', script)

    @patch("executor.engine.subprocess.run")
    def test_chrome_close_tab_uses_title_filter(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().chrome_close_tab("AI Trade Bot")
        self.assertEqual(result, "Closed tab containing AI Trade Bot")
        self.assertIn('if title of t contains "AI Trade Bot"', mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_chrome_focus_tab_uses_title_filter(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().chrome_focus_tab("AI SDR")
        self.assertEqual(result, "Focused tab containing AI SDR")
        self.assertIn('if title of t contains "AI SDR"', mock_run.call_args.args[0][2])
        self.assertIn("set active tab index of w to tab_index", mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_send_email_uses_mail_app(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().send_email("john@example.com", "Meeting", "See you at 3.")
        self.assertEqual(result, "Email sent to john@example.com")
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell application "Mail"', script)
        self.assertIn('subject:"Meeting"', script)
        self.assertIn('address:"john@example.com"', script)

    @patch("executor.engine.subprocess.run")
    def test_send_whatsapp_uses_keyboard_simulation(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().send_whatsapp("Rushil", "I'll be late")
        self.assertEqual(result, "WhatsApp message sent to Rushil")
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell application "WhatsApp"', script)
        self.assertIn('keystroke "Rushil"', script)
        self.assertIn('keystroke "I\'ll be late"', script)

    @patch("executor.engine.subprocess.run")
    def test_calendar_read_filters_events_in_applescript_loop(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Standup at Monday", stderr="")

        result = Executor().calendar_read("today")

        self.assertEqual(result, "Standup at Monday")
        args = mock_run.call_args.args[0]
        self.assertEqual(args[:3], ["osascript", "-l", "JavaScript"])
        script = args[4]
        self.assertIn('Application("/System/Applications/Calendar.app")', script)
        self.assertIn("var calendars = Calendar.calendars()", script)
        self.assertIn("var events = calendars[i].events()", script)
        self.assertIn("eventStart >= startDate && eventStart < endDate", script)

    @patch("executor.engine.subprocess.run")
    def test_calendar_read_formats_next_event_from_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "title": "Standup",
                        "start": "2026-04-13T04:30:00Z",
                        "end": "2026-04-13T05:00:00Z",
                        "calendar": "Work",
                    }
                ]
            ),
            stderr="",
        )

        result = Executor().calendar_read("next")

        self.assertIn("your next event is Standup at", result)
        self.assertIn("Mon", result)
        script = mock_run.call_args.args[0][4]
        self.assertIn('mode === "next"', script)
        self.assertIn("entries.sort", script)

    @patch("executor.engine.subprocess.run")
    def test_calendar_read_formats_this_week_summary_from_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "title": "Planning",
                        "start": "2026-04-13T04:30:00Z",
                        "end": "2026-04-13T05:00:00Z",
                        "calendar": "Work",
                    },
                    {
                        "title": "Demo",
                        "start": "2026-04-15T10:30:00Z",
                        "end": "2026-04-15T11:00:00Z",
                        "calendar": "Work",
                    },
                ]
            ),
            stderr="",
        )

        result = Executor().calendar_read("this_week")

        self.assertIn("you have 2 calendar events this week", result)
        self.assertIn("Planning at", result)
        self.assertIn("Demo at", result)
        script = mock_run.call_args.args[0][4]
        self.assertIn('mode === "this_week"', script)
        self.assertIn("nextWeekStart", script)

    @patch("executor.engine.subprocess.run")
    def test_calendar_read_returns_clear_message_when_calendar_automation_is_blocked(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Connection Invalid error for service com.apple.hiservices-xpcservice. Error: Parameter is missing. (-1701)",
        )

        result = Executor().calendar_read("today")

        self.assertEqual(
            result,
            "Calendar read is unavailable until Calendar automation access is granted on this host.",
        )

    @patch("executor.engine.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=8))
    def test_calendar_read_returns_clear_message_on_timeout(self, _mock_run):
        result = Executor().calendar_read("today")

        self.assertEqual(
            result,
            "Calendar read is unavailable until Calendar automation access is granted on this host.",
        )

    @patch.object(Executor, "browser_new_tab", return_value="opened new browser tab: https://www.google.com/search?q=gemma")
    def test_browser_search_uses_google_query(self, mock_new_tab):
        result = Executor().browser_search("gemma")
        self.assertIn("opened new browser tab", result)
        self.assertIn("google.com/search", mock_new_tab.call_args.args[0])

    @patch.object(Executor, "_resolve_browser_app", return_value="Google Chrome")
    @patch("executor.engine.subprocess.run")
    def test_browser_close_tab_uses_applescript(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_close_tab()
        self.assertEqual(result, "closed current browser tab")
        self.assertIn("close active tab", mock_run.call_args.args[0][2])

    @patch.object(Executor, "_resolve_browser_app", return_value="Google Chrome")
    @patch("executor.engine.subprocess.run")
    def test_browser_close_window_uses_applescript(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().browser_close_window()
        self.assertEqual(result, "closed current browser window")
        self.assertIn("close front window", mock_run.call_args.args[0][2])

    @patch.object(Executor, "_resolve_browser_app", return_value="Google Chrome")
    @patch("executor.engine.subprocess.run")
    def test_pause_video_executes_browser_javascript(self, mock_run, _mock_browser):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().pause_video()
        self.assertEqual(result, "paused media in browser")
        self.assertIn("execute javascript", mock_run.call_args.args[0][2])

    @patch.object(Executor, "_resolve_browser_app", return_value="Google Chrome")
    @patch("executor.engine.subprocess.run")
    def test_open_url_in_browser_falls_back_to_system_default_when_app_missing(self, mock_run, _mock_browser):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="Unable to find application named 'Google Chrome'"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        result = Executor().open_url_in_browser("youtube.com", "Google Chrome")

        self.assertEqual(result, "opened https://youtube.com")
        self.assertEqual(mock_run.call_args_list[0].args[0], ["open", "-a", "Google Chrome", "https://youtube.com"])
        self.assertEqual(mock_run.call_args_list[1].args[0], ["open", "https://youtube.com"])

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
    def test_brightness_set_uses_repeated_key_codes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().brightness_set(70)
        self.assertEqual(result, "set brightness to 70")
        script = mock_run.call_args.args[0][2]
        self.assertEqual(script.count("key code 145"), 16)
        self.assertEqual(script.count("key code 144"), 11)

    @patch("executor.engine.subprocess.run")
    def test_run_dispatches_brightness_level_action(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().run([{"type": "brightness", "level": 70}])
        self.assertEqual(result[0]["status"], "ok")
        self.assertEqual(result[0]["result"], "set brightness to 70")

    @patch("executor.engine.subprocess.run")
    def test_dark_mode_enable_uses_boolean_script(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().dark_mode(True)
        self.assertEqual(result, "toggled dark mode")
        self.assertIn("set dark mode to true", mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_do_not_disturb_disable_returns_directional_message(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().do_not_disturb(False)
        self.assertEqual(result, "toggled do not disturb off")
        self.assertIn('process "ControlCenter"', mock_run.call_args.args[0][2])

    @patch("executor.engine.subprocess.run")
    def test_take_screenshot_uses_screencapture(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = Executor().take_screenshot()
        self.assertEqual(result, "/tmp/burry_screen.png")
        self.assertEqual(mock_run.call_args.args[0][:2], ["screencapture", "-x"])

    @patch.object(Executor, "_summarize_text", return_value="page summary")
    @patch("memory.knowledge_base.get_indexed_document", return_value=None)
    @patch("requests.get")
    def test_summarize_page_falls_back_to_direct_html_fetch(self, mock_get, _mock_cached, _mock_summarize):
        mock_get.side_effect = [
            MagicMock(status_code=502, text="", headers={"content-type": "text/plain"}),
            MagicMock(
                status_code=200,
                text="<html><head><title>Gemma</title></head><body><article>Gemma release notes</article></body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            ),
        ]

        result = Executor().summarize_page("https://example.com/gemma")

        self.assertEqual(result, "page summary")
        self.assertEqual(mock_get.call_count, 2)
        self.assertIn("r.jina.ai/https://example.com/gemma", mock_get.call_args_list[0].args[0])
        self.assertEqual(mock_get.call_args_list[1].args[0], "https://example.com/gemma")

    @patch.object(Executor, "_summarize_text", return_value="cached summary")
    @patch("requests.get")
    @patch("memory.knowledge_base.get_indexed_document", return_value={"text": "Cached Gemma 4 page snapshot"})
    def test_summarize_page_uses_indexed_snapshot_before_live_fetch(self, _mock_cached, mock_get, _mock_summarize):
        result = Executor().summarize_page("https://example.com/gemma")

        self.assertEqual(result, "cached summary")
        mock_get.assert_not_called()

    @patch.object(Executor, "_summarize_text", return_value="page summary")
    @patch("memory.knowledge_base.get_indexed_document", return_value=None)
    @patch("memory.knowledge_base.index_web_page")
    @patch("requests.get")
    def test_summarize_page_indexes_fetched_snapshot_for_reuse(self, mock_get, mock_index, _mock_cached, _mock_summarize):
        mock_get.return_value = MagicMock(
            status_code=200,
            text="Gemma 4 launch notes with broader deployment details.",
            headers={"content-type": "text/plain"},
        )

        result = Executor().summarize_page("https://example.com/gemma")

        self.assertEqual(result, "page summary")
        mock_index.assert_called_once_with(
            "https://example.com/gemma",
            "Gemma 4 launch notes with broader deployment details.",
        )

    @patch("requests.get")
    def test_youtube_transcript_from_caption_tracks_uses_watch_page_metadata(self, mock_get):
        mock_get.side_effect = [
            MagicMock(
                status_code=200,
                text='{"captions":{"playerCaptionsTracklistRenderer":{"captionTracks":[{"baseUrl":"https://example.com/captions.xml","languageCode":"en"}]}}}',
                headers={"content-type": "text/html; charset=utf-8"},
            ),
            MagicMock(
                status_code=200,
                text="<transcript><text>Hello world</text><text>from captions</text></transcript>",
                headers={"content-type": "application/xml"},
            ),
        ]

        transcript = Executor()._youtube_transcript_from_caption_tracks("https://www.youtube.com/watch?v=abcdefghijk")

        self.assertEqual(transcript, "Hello world from captions")
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_get.call_args_list[1].args[0], "https://example.com/captions.xml")

    @patch.object(Executor, "obsidian_note", return_value="saved to Obsidian: 2026-04-12 Video Summary.md")
    @patch.object(Executor, "_summarize_text", return_value="video summary")
    @patch.object(Executor, "_video_transcript_text", return_value="full transcript")
    def test_summarize_video_save_to_obsidian_reports_saved_note(self, _mock_transcript, _mock_summarize, mock_obsidian):
        result = Executor().summarize_video("https://www.youtube.com/watch?v=abcdefghijk", save_to_obsidian=True)

        self.assertIn("video summary", result)
        self.assertIn("saved to Obsidian", result)

    @patch("executor.engine.subprocess.Popen")
    def test_obsidian_note_opens_vault_relative_url_instead_of_raw_icloud_path(self, mock_popen):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            with patch("executor.engine.OBSIDIAN_VAULT", tmpdir), patch("executor.engine.OBSIDIAN_VAULT_NAME", "Burry"):
                result = Executor().obsidian_note("Memory Test", "remember this", folder="Daily")

        url = mock_popen.call_args.args[0][1]
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        self.assertIn("saved to Obsidian", result)
        self.assertEqual(parsed.scheme, "obsidian")
        self.assertEqual(params["vault"], ["Burry"])
        self.assertTrue(params["file"][0].startswith("Daily/"))
        self.assertNotIn("path", params)
        self.assertNotIn("Mobile%20Documents", url)

    @patch("executor.engine.subprocess.Popen")
    def test_obsidian_daily_note_does_not_duplicate_date_title(self, mock_popen):
        today = datetime.now().strftime("%Y-%m-%d")

        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            with patch("executor.engine.OBSIDIAN_VAULT", tmpdir), patch("executor.engine.OBSIDIAN_VAULT_NAME", "Burry"):
                result = Executor().obsidian_note(today, "daily memory", folder="Daily")
                saved = Path(tmpdir) / "Daily" / f"{today}.md"
                saved_exists = saved.exists()

        self.assertEqual(result, f"saved to Obsidian: {today}.md")
        self.assertTrue(saved_exists)
        opened_url = mock_popen.call_args.args[0][1]
        self.assertIn(f"file=Daily/{today}.md", opened_url)
        self.assertNotIn(f"{today}%20{today}", opened_url)

    @patch.object(Executor, "_speak")
    @patch.object(Executor, "_listen_followup", return_value="yes")
    def test_delete_file_removes_target_after_confirmation(self, _mock_listen, _mock_speak):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            target = Path(tmpdir) / "resume.pdf"
            target.write_text("resume", encoding="utf-8")

            result = Executor().delete_file(str(target))
            exists_after = target.exists()

        self.assertIn("deleted", result)
        self.assertFalse(exists_after)

    def test_zip_folder_creates_archive(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            folder = Path(tmpdir) / "Documents"
            folder.mkdir()
            (folder / "notes.txt").write_text("phase3a", encoding="utf-8")

            result = Executor().zip_folder(str(folder))
            archive = folder.parent / "Documents.zip"
            archive_exists = archive.exists()

        self.assertIn(str(archive), result)
        self.assertTrue(archive_exists)

    @patch.object(Executor, "_run_osascript", side_effect=RuntimeError("Not authorized (-1743)"))
    def test_calendar_add_returns_clear_message_on_permission_error(self, _mock_run):
        result = Executor().calendar_add("Phase 3A smoke", "tomorrow 9am")

        self.assertEqual(
            result,
            "Calendar event creation is unavailable until Calendar automation access is granted on this host.",
        )

    @patch.object(Executor, "_run_osascript", side_effect=RuntimeError("Application isn’t running. (-600)"))
    def test_calendar_add_returns_clear_message_when_calendar_lookup_is_unavailable(self, _mock_run):
        result = Executor().calendar_add("Phase 3A smoke", "tomorrow 9am")

        self.assertEqual(
            result,
            "Calendar event creation is unavailable until Calendar automation access is granted on this host.",
        )

    @patch.object(Executor, "_applescript_date_expression", return_value='date "14 April 2026 09:00:00 AM"')
    @patch.object(Executor, "_run_osascript", return_value=MagicMock(returncode=0, stdout="", stderr=""))
    def test_calendar_add_uses_applescript_date_expression_for_natural_language(self, mock_run, mock_date_expr):
        result = Executor().calendar_add("Phase 3A smoke", "tomorrow 9am")

        self.assertEqual(result, "added calendar event Phase 3A smoke")
        mock_date_expr.assert_called_once_with("tomorrow 9am")
        script = mock_run.call_args.args[0]
        self.assertIn('tell application "Calendar"', script)
        self.assertIn("activate", script)
        self.assertIn('set startDate to date "14 April 2026 09:00:00 AM"', script)

    @patch("executor.engine.subprocess.run")
    def test_set_reminder_uses_reminders_app(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = Executor().set_reminder(minutes=30, message="check deployments")

        self.assertEqual(result, "reminder set for 30 min")
        script = mock_run.call_args.args[0][2]
        self.assertIn('tell application "Reminders"', script)
        self.assertIn("30 * minutes", script)

    @patch.object(Executor, "_applescript_date_expression", return_value='date "14 April 2026 05:00:00 PM"')
    @patch.object(Executor, "_run_osascript", return_value=MagicMock(returncode=0, stdout="", stderr=""))
    def test_set_reminder_uses_applescript_date_expression_for_absolute_time(self, mock_run, mock_date_expr):
        result = Executor().set_reminder(when="5pm", message="check deployments")

        self.assertEqual(result, "reminder set for 5pm")
        mock_date_expr.assert_called_once_with("5pm")
        script = mock_run.call_args.args[0]
        self.assertIn('set remindDate to date "14 April 2026 05:00:00 PM"', script)

    def test_normalize_browser_url_preserves_file_scheme(self):
        self.assertEqual(
            Executor._normalize_browser_url("file:///tmp/phase3a-browser-1.html"),
            "file:///tmp/phase3a-browser-1.html",
        )

    @patch.object(Executor, "_reminder_exists", return_value=True)
    @patch.object(Executor, "_dispatch", return_value="reminder set for 30 min")
    def test_run_attaches_reminder_verification_metadata(self, _mock_dispatch, _mock_exists):
        result = Executor().run([{"type": "set_reminder", "minutes": 30, "message": "check deployments"}])[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification_status"], "verified")
        self.assertIn("Confirmed the reminder exists", result["verification_detail"])

    @patch.object(Executor, "_browser_snapshot")
    @patch.object(Executor, "_dispatch", return_value="went back")
    def test_run_attaches_browser_back_verification_metadata(self, _mock_dispatch, mock_browser_snapshot):
        mock_browser_snapshot.side_effect = [
            {
                "app": "Google Chrome",
                "running": True,
                "window_count": 1,
                "tab_count": 1,
                "url": "https://example.org",
            },
            {
                "app": "Google Chrome",
                "running": True,
                "window_count": 1,
                "tab_count": 1,
                "url": "https://example.com",
            },
        ]

        result = Executor().run([{"type": "browser_go_back"}])[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification_status"], "verified")
        self.assertIn("navigated back", result["verification_detail"].lower())

    @patch.object(Executor, "_browser_snapshot")
    @patch.object(Executor, "_dispatch", return_value="refreshed")
    def test_run_attaches_browser_refresh_verification_metadata(self, _mock_dispatch, mock_browser_snapshot):
        mock_browser_snapshot.side_effect = [
            {
                "app": "Google Chrome",
                "running": True,
                "window_count": 1,
                "tab_count": 1,
                "url": "https://example.com",
            },
            {
                "app": "Google Chrome",
                "running": True,
                "window_count": 1,
                "tab_count": 1,
                "url": "https://example.com",
            },
        ]

        result = Executor().run([{"type": "browser_refresh"}])[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification_status"], "verified")
        self.assertIn("refreshed", result["verification_detail"].lower())

    @patch.object(Executor, "open_url", return_value="opened https://wa.me/919999999999?text=hello")
    def test_whatsapp_send_prefers_phone_url(self, mock_open_url):
        result = Executor().whatsapp_send("vedang", "hello", phone="+91 99999 99999")
        self.assertIn("opened WhatsApp message flow", result)
        self.assertEqual(mock_open_url.call_args.args[0], "https://wa.me/919999999999?text=hello")

    @patch.object(Executor, "open_url", return_value="opened https://wa.me/919999999999?text=ship+it")
    def test_whatsapp_send_accepts_legacy_phone_then_message_positional_order(self, mock_open_url):
        result = Executor().whatsapp_send("vedang", "+91 99999 99999", "ship it")

        self.assertIn("opened WhatsApp message flow", result)
        self.assertEqual(mock_open_url.call_args.args[0], "https://wa.me/919999999999?text=ship+it")

    @patch.object(Executor, "whatsapp_send", return_value="attachment flow opened")
    def test_compose_whatsapp_with_attachment_skips_pywhatkit_and_uses_attachment_flow(self, mock_send):
        result = Executor().compose_whatsapp("vedang", "+91 99999 99999", "review this", attachments=["resume.pdf"])

        self.assertEqual(result, "attachment flow opened")
        mock_send.assert_called_once_with("vedang", "review this", phone="+91 99999 99999", attachments=["resume.pdf"])

    @patch.object(Executor, "_run_osascript")
    @patch.object(Executor, "_resolve_attachment_paths", return_value=(["/tmp/resume.pdf"], []))
    def test_compose_email_with_attachment_uses_mail_draft(self, _mock_paths, mock_script):
        result = Executor().compose_email(
            "vedang2803@gmail.com",
            "project update",
            "shipping tonight",
            attachments=["resume.pdf"],
        )

        self.assertIn("opened Mail draft", result)
        self.assertIn("1 attachment", result)
        self.assertIn("/tmp/resume.pdf", mock_script.call_args.args[0])

    @patch.object(Executor, "open_url_in_browser")
    @patch.object(Executor, "_resolve_attachment_paths", return_value=([], ["resume.pdf"]))
    def test_compose_email_reports_missing_attachment_and_falls_back_to_gmail(self, _mock_paths, mock_open_url):
        result = Executor().compose_email(
            "vedang2803@gmail.com",
            "project update",
            "shipping tonight",
            attachments=["resume.pdf"],
        )

        self.assertIn("couldn't find resume.pdf", result)
        mock_open_url.assert_called_once()

    @patch.object(Executor, "open_url_in_browser")
    @patch.object(Executor, "_resolve_attachment_paths", return_value=(["/tmp/resume.pdf"], []))
    @patch.object(Executor, "_run_osascript", side_effect=RuntimeError("Not authorized (-1743)"))
    def test_compose_email_attachment_flow_falls_back_truthfully_when_mail_automation_is_blocked(
        self,
        _mock_script,
        _mock_paths,
        mock_open_url,
    ):
        result = Executor().compose_email(
            "vedang2803@gmail.com",
            "project update",
            "shipping tonight",
            attachments=["resume.pdf"],
        )

        self.assertIn("Mail attachment automation is unavailable", result)
        mock_open_url.assert_called_once()

    @patch.object(Executor, "run_agent_task", return_value="healthy")
    @patch.object(Executor, "_default_vps_host", return_value="root@194.163.146.149")
    @patch.object(Executor, "_vps_preflight_error", return_value="")
    def test_vps_check_uses_default_host_for_agent_status(self, _mock_preflight, _mock_host, mock_run_agent):
        result = Executor().vps_check("status")

        self.assertEqual(result, "healthy")
        mock_run_agent.assert_called_once_with("vps", {"action": "status", "host": "root@194.163.146.149"})

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

    @patch.object(Executor, "open_terminal", return_value="opened new Terminal window")
    @patch.object(Executor, "_terminal_editor_cli", return_value="/usr/local/bin/codex")
    def test_open_editor_opens_codex_in_terminal_window(self, _mock_cli, mock_open_terminal):
        result = Executor().open_editor(path="~/Burry/mac-butler", editor="codex", mode="new_window")

        self.assertEqual(result, "opened new Terminal window for Codex at /Users/adityatiwari/Burry/mac-butler")
        mock_open_terminal.assert_called_once_with(
            mode="window",
            cmd="/usr/local/bin/codex",
            cwd="/Users/adityatiwari/Burry/mac-butler",
        )

    @patch("runtime.note_project_context_hint")
    @patch("memory.layered.get_project_detail", return_value="live project detail")
    @patch("projects.get_project", return_value={"name": "mac-butler", "path": "~/Burry/mac-butler"})
    @patch.object(Executor, "_terminal_editor_cli", return_value="/usr/local/bin/claude")
    @patch.object(Executor, "open_terminal", return_value="opened new Terminal window")
    def test_open_project_prefers_claude_terminal_flow(
        self,
        mock_open_terminal,
        _mock_cli,
        _mock_get_project,
        _mock_detail,
        mock_note_hint,
    ):
        result = Executor().open_project("mac-butler", editor="claude")

        self.assertEqual(result, "opened new Terminal window for Claude Code at /Users/adityatiwari/Burry/mac-butler")
        mock_open_terminal.assert_called_once_with(
            mode="window",
            cmd="/usr/local/bin/claude",
            cwd="/Users/adityatiwari/Burry/mac-butler",
        )
        mock_note_hint.assert_called_once()

    @patch("executor.engine.subprocess.run")
    def test_open_terminal_quotes_cwd_with_spaces(self, mock_run):
        Executor().open_terminal(mode="window", cmd="pwd", cwd="/tmp/Burry Space")

        script = mock_run.call_args.args[0][2]
        self.assertIn("cd '/tmp/Burry Space'; pwd", script)

    @patch.object(Executor, "open_editor", return_value="Visual Studio Code is not installed")
    def test_create_file_in_editor_reports_created_path_even_if_editor_missing(self, _mock_open_editor):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            result = Executor().create_file_in_editor("demo.txt", editor="vscode", directory=tmpdir)
            self.assertIn(str(Path(tmpdir) / "demo.txt"), result)
        self.assertIn("Visual Studio Code is not installed", result)

    @patch.object(Executor, "_filesystem_search_roots")
    def test_read_file_resolves_fuzzy_name_from_search_roots(self, mock_roots):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            downloads = Path(tmpdir) / "Downloads"
            downloads.mkdir()
            target = downloads / "notes.txt"
            target.write_text("hello from downloads", encoding="utf-8")
            mock_roots.return_value = [downloads]

            result = Executor().read_file("notes file")

        self.assertEqual(result, "hello from downloads")

    @patch("executor.engine.subprocess.Popen")
    @patch.object(Executor, "_filesystem_search_roots")
    def test_open_file_resolves_fuzzy_name_from_search_roots(self, mock_roots, mock_popen):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            docs = Path(tmpdir) / "Documents"
            docs.mkdir()
            target = docs / "budget.xlsx"
            target.write_text("sheet", encoding="utf-8")
            mock_roots.return_value = [docs]

            result = Executor().open_file("budget.xlsx")

        self.assertIn(str(target), result)
        mock_popen.assert_called_once_with(["open", str(target)])

    @patch.object(Executor, "_filesystem_search_roots")
    def test_move_file_to_directory_preserves_filename(self, mock_roots):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            desktop = Path(tmpdir) / "Desktop"
            documents = Path(tmpdir) / "Documents"
            desktop.mkdir()
            documents.mkdir()
            source = desktop / "resume.pdf"
            source.write_text("resume", encoding="utf-8")
            mock_roots.return_value = [desktop, documents]

            result = Executor().move_file("resume", str(documents))

            moved = documents / "resume.pdf"
            moved_exists = moved.exists()
            source_exists = source.exists()

        self.assertIn(str(moved), result)
        self.assertTrue(moved_exists)
        self.assertFalse(source_exists)

    @patch.object(Executor, "_filesystem_search_roots")
    def test_copy_file_to_directory_preserves_filename(self, mock_roots):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            desktop = Path(tmpdir) / "Desktop"
            downloads = Path(tmpdir) / "Downloads"
            desktop.mkdir()
            downloads.mkdir()
            source = desktop / "resume.pdf"
            source.write_text("resume", encoding="utf-8")
            mock_roots.return_value = [desktop, downloads]

            result = Executor().copy_file("resume", str(downloads))
            copied = downloads / "resume.pdf"
            copied_exists = copied.exists()
            source_exists = source.exists()

        self.assertIn(str(copied), result)
        self.assertTrue(copied_exists)
        self.assertTrue(source_exists)

    @patch("runtime.notify.notify")
    def test_executor_notify_uses_runtime_notification_helper(self, mock_runtime_notify):
        result = Executor().notify("Burry", "Tests finished")

        self.assertEqual(result, "notified")
        mock_runtime_notify.assert_called_once_with("Burry", "Tests finished", subtitle="Executor")

    @patch("executor.engine.subprocess.run")
    def test_run_command_creates_missing_cwd_and_caps_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout="x" * 350, stderr="", returncode=0)
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

    def test_run_attaches_filesystem_verification_metadata(self):
        executor = Executor()
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmpdir:
            target = Path(tmpdir) / "verified.txt"

            result = executor.run([{"type": "create_file", "path": str(target), "content": "hello"}])[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification_status"], "verified")
        self.assertIn("Confirmed the file exists", result["verification_detail"])

    @patch.object(Executor, "_browser_snapshot")
    @patch.object(Executor, "_dispatch", return_value="opened https://youtube.com")
    def test_run_attaches_browser_verification_metadata(self, _mock_dispatch, mock_browser_snapshot):
        mock_browser_snapshot.side_effect = [
            {
                "app": "Google Chrome",
                "running": True,
                "window_count": 1,
                "tab_count": 1,
                "url": "https://www.google.com",
            },
            {
                "app": "Google Chrome",
                "running": True,
                "window_count": 1,
                "tab_count": 2,
                "url": "https://youtube.com",
            },
        ]

        result = Executor().run([{"type": "open_url_in_browser", "url": "https://youtube.com"}])[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification_status"], "verified")
        self.assertIn("browser is on https://youtube.com", result["verification_detail"].lower())

    @patch.object(Executor, "_app_snapshot", return_value={"app": "WhatsApp", "running": True, "window_count": 1, "focused": True})
    @patch.object(Executor, "_dispatch", return_value="WhatsApp message sent to Rushil")
    def test_run_marks_unverified_whatsapp_send_as_degraded(self, _mock_dispatch, _mock_app_snapshot):
        result = Executor().run([{"type": "send_whatsapp", "contact": "Rushil", "message": "hi"}])[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["verification_status"], "degraded")
        self.assertIn("couldn't confirm", result["verification_detail"].lower())

    @patch("executor.engine.subprocess.run")
    def test_run_command_raises_on_non_zero_exit(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="permission denied", returncode=1)

        with self.assertRaises(RuntimeError):
            Executor().run_command("git status", cwd=str(TEST_ROOT))

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
