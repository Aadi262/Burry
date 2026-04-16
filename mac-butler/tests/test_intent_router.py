import unittest
from unittest.mock import patch

from brain.session_context import ctx
from intents.router import _classifier_intent, route


class IntentRouterTests(unittest.TestCase):
    def test_play_song_routes_to_spotify_search(self):
        result = route("play mockingbird")
        self.assertEqual(result.name, "spotify_play")
        self.assertEqual(result.params["song"], "mockingbird")
        self.assertEqual(result.to_action()["type"], "search_and_play")

    def test_change_music_phrase_routes_to_spotify_search(self):
        result = route("can you change the music to shape of you")
        self.assertEqual(result.name, "spotify_play")
        self.assertEqual(result.params["song"], "shape of you")

    def test_play_song_strips_streaming_suffix(self):
        result = route("play mockingbird by eminem on spotify")
        self.assertEqual(result.name, "spotify_play")
        self.assertEqual(result.params["song"], "mockingbird by eminem")

    def test_play_that_song_asks_for_clarification(self):
        result = route("play that song")
        self.assertEqual(result.name, "clarify_song")

    def test_open_cursor_routes_to_open_app(self):
        result = route("open cursor")
        self.assertEqual(result.name, "open_app")
        self.assertEqual(result.params["app"], "Cursor")

    def test_open_visual_studio_code_routes_to_vscode(self):
        result = route("open visual studio code")
        self.assertEqual(result.name, "open_app")
        self.assertEqual(result.params["app"], "Visual Studio Code")

    def test_open_netflix_routes_to_browser(self):
        result = route("open netflix")
        self.assertEqual(result.name, "open_app")
        self.assertEqual(result.to_action()["type"], "open_url_in_browser")
        self.assertIn("netflix", result.to_action()["url"])

    def test_search_youtube_routes_to_results_page(self):
        result = route("search ranveer alahabadia on youtube")
        self.assertEqual(result.name, "open_app")
        self.assertIn("youtube.com/results", result.to_action()["url"])

    def test_search_for_youtube_strips_filler_word(self):
        result = route("search for ranveer alahabadia on youtube")
        self.assertEqual(result.name, "open_app")
        self.assertIn("ranveer+alahabadia", result.to_action()["url"])
        self.assertNotIn("for+ranveer", result.to_action()["url"])

    def test_search_youtube_accepts_voice_alias(self):
        result = route("search bhuvan bam you do")
        self.assertEqual(result.name, "open_app")
        self.assertIn("youtube.com/results", result.to_action()["url"])

    def test_compose_mail_routes_to_gmail_compose(self):
        result = route("can you compose a new mail")
        self.assertEqual(result.name, "compose_email")
        action = result.to_action()
        self.assertEqual(action["type"], "compose_email")
        self.assertEqual(action["recipient"], "")

    def test_new_mail_phrase_routes_to_gmail_compose(self):
        result = route("can you open a new mail")
        self.assertEqual(result.name, "compose_email")
        self.assertEqual(result.to_action()["type"], "compose_email")

    def test_compose_mail_to_name_sets_recipient(self):
        result = route("compose mail to vedang")
        self.assertEqual(result.name, "compose_email")
        self.assertEqual(result.to_action()["recipient"], "vedang")

    def test_compose_mail_accepts_male_homophone(self):
        result = route("compose a new male to vedang")
        self.assertEqual(result.name, "compose_email")
        self.assertEqual(result.to_action()["recipient"], "vedang")

    def test_compose_mail_parses_spoken_email_address(self):
        result = route("write a mail to vedang2803 at gmail dot com")
        self.assertEqual(result.name, "compose_email")
        self.assertEqual(result.to_action()["recipient"], "vedang2803@gmail.com")

    def test_compose_mail_parses_subject_and_body(self):
        result = route("write a mail to vedang2803@gmail.com subject project update body shipping tonight")
        self.assertEqual(result.name, "compose_email")
        action = result.to_action()
        self.assertEqual(action["recipient"], "vedang2803@gmail.com")
        self.assertEqual(action["subject"], "project update")
        self.assertEqual(action["body"], "shipping tonight")

    def test_compose_mail_drops_trailing_connector_before_body(self):
        result = route("open gmail and write a mail to vedang2803@gmail.com with subject test gmail and body how are u")
        self.assertEqual(result.name, "compose_email")
        action = result.to_action()
        self.assertEqual(action["recipient"], "vedang2803@gmail.com")
        self.assertEqual(action["subject"], "test gmail")
        self.assertEqual(action["body"], "how are u")

    def test_open_google_sheet_routes_to_browser_url(self):
        result = route("open google sheet")
        self.assertEqual(result.name, "open_app")
        action = result.to_action()
        self.assertEqual(action["type"], "open_url_in_browser")
        self.assertEqual(action["url"], "https://sheets.new")

    def test_create_folder_on_desktop_strips_location_from_name(self):
        result = route("create folder called client work on desktop")
        self.assertEqual(result.name, "create_folder")
        self.assertEqual(result.params["path"], "~/Desktop")
        self.assertEqual(result.params["name"], "client work")

    def test_open_finder_at_downloads_routes_to_open_folder(self):
        result = route("open finder at downloads")
        self.assertEqual(result.name, "open_folder")
        self.assertEqual(result.params["path"], "~/Downloads")

    def test_whats_on_my_desktop_routes_to_list_files(self):
        result = route("what's on my desktop")
        self.assertEqual(result.name, "list_files")
        self.assertEqual(result.params["path"], "~/Desktop")

    def test_find_resume_file_routes_to_find_file(self):
        result = route("find resume file")
        self.assertEqual(result.name, "find_file")
        self.assertEqual(result.params["query"], "resume")

    def test_read_file_phrase_routes_deterministically(self):
        result = route("read my notes file in downloads")
        self.assertEqual(result.name, "read_file")
        self.assertEqual(result.params["path"], "~/Downloads/notes")

    def test_write_file_phrase_routes_deterministically(self):
        result = route("write hello world to notes.txt on desktop")
        self.assertEqual(result.name, "write_file")
        self.assertEqual(result.params["path"], "~/Desktop/notes.txt")
        self.assertEqual(result.params["content"], "hello world")
        self.assertEqual(result.params["mode"], "overwrite")

    def test_move_file_phrase_routes_deterministically(self):
        result = route("move resume to documents")
        self.assertEqual(result.name, "move_file")
        self.assertEqual(result.params["from"], "resume")
        self.assertEqual(result.params["to"], "~/Documents")

    def test_copy_file_phrase_routes_deterministically(self):
        result = route("copy resume to downloads")
        self.assertEqual(result.name, "copy_file")
        self.assertEqual(result.params["from"], "resume")
        self.assertEqual(result.params["to"], "~/Downloads")

    def test_rename_file_phrase_routes_to_move_file(self):
        result = route("rename report.md to report-v2")
        self.assertEqual(result.name, "move_file")
        self.assertEqual(result.params["from"], "report.md")
        self.assertEqual(result.params["to"], "report-v2")

    def test_open_explicit_filename_routes_to_open_file(self):
        result = route("open budget.xlsx")
        self.assertEqual(result.name, "open_file")
        self.assertEqual(result.params["path"], "budget.xlsx")

    def test_task_query_routes_to_task_read(self):
        result = route("what are my tasks today")
        self.assertEqual(result.name, "task_read")
        self.assertEqual(result.params["filter"], "today")

    def test_calendar_query_routes_to_calendar_read(self):
        result = route("what's on my calendar today")
        self.assertEqual(result.name, "calendar_read")
        self.assertEqual(result.params["range"], "today")

    def test_schedule_query_for_tomorrow_routes_to_calendar_read(self):
        result = route("what's on my schedule tomorrow")
        self.assertEqual(result.name, "calendar_read")
        self.assertEqual(result.params["range"], "tomorrow")

    def test_next_meeting_routes_to_calendar_read(self):
        result = route("what's my next meeting")
        self.assertEqual(result.name, "calendar_read")
        self.assertEqual(result.params["range"], "next")

    def test_availability_phrase_routes_to_calendar_read(self):
        result = route("am i free tomorrow")
        self.assertEqual(result.name, "calendar_read")
        self.assertEqual(result.params["range"], "tomorrow")

    def test_agenda_this_week_routes_to_calendar_read(self):
        result = route("show my agenda this week")
        self.assertEqual(result.name, "calendar_read")
        self.assertEqual(result.params["range"], "this_week")

    def test_schedule_event_phrase_routes_to_calendar_add(self):
        result = route("schedule standup for tomorrow at 10am")
        self.assertEqual(result.name, "calendar_add")
        self.assertEqual(result.params["title"], "standup")
        self.assertEqual(result.params["time"], "tomorrow at 10am")

    def test_add_task_phrase_routes_to_task_add(self):
        result = route("add a task to fix login bug for adpilot")
        self.assertEqual(result.name, "task_add")
        self.assertEqual(result.params["title"], "fix login bug")
        self.assertEqual(result.params["project"], "adpilot")

    def test_open_new_tab_routes_deterministically(self):
        result = route("can you open a new tab")
        self.assertEqual(result.name, "browser_new_tab")
        self.assertEqual(result.to_action()["type"], "browser_new_tab")

    def test_open_new_tab_to_search_routes_to_browser_search(self):
        result = route("open a new tab to search latest gemma news")
        self.assertEqual(result.name, "browser_search")
        self.assertEqual(result.params["query"], "latest gemma news")

    def test_open_new_browser_window_routes_deterministically(self):
        result = route("open a new browser window")
        self.assertEqual(result.name, "browser_window")
        self.assertEqual(result.to_action()["type"], "browser_window")

    def test_open_site_in_new_browser_window_routes_with_target(self):
        result = route("open github.com in a new browser window")
        self.assertEqual(result.name, "browser_window")
        self.assertEqual(result.params["url"], "https://github.com")

    def test_close_tab_routes_deterministically(self):
        result = route("close the tabs")
        self.assertEqual(result.name, "browser_close_tab")

    def test_close_window_routes_deterministically(self):
        result = route("close the screen")
        self.assertEqual(result.name, "browser_close_window")

    def test_go_back_routes_to_browser_navigation(self):
        result = route("go back")
        self.assertEqual(result.name, "browser_go_back")
        self.assertEqual(result.to_action()["type"], "browser_go_back")

    def test_refresh_page_routes_to_browser_refresh(self):
        result = route("refresh this page")
        self.assertEqual(result.name, "browser_refresh")
        self.assertEqual(result.to_action()["type"], "browser_refresh")

    def test_pause_video_routes_deterministically(self):
        result = route("pause video")
        self.assertEqual(result.name, "pause_video")

    def test_summarize_article_routes_deterministically(self):
        result = route("summarize this article")
        self.assertEqual(result.name, "summarize_page")

    def test_save_notes_from_video_routes_to_obsidian_video_summary(self):
        result = route("save notes from this video")
        self.assertEqual(result.name, "summarize_video")
        self.assertTrue(result.params["save_to_obsidian"])

    def test_volume_up_routes_to_instant_volume_up(self):
        result = route("turn up the volume")
        self.assertEqual(result.name, "system_volume")
        self.assertEqual(result.params["direction"], "up")

    def test_exact_volume_up_routes_to_fast_pattern(self):
        result = route("volume up")
        self.assertEqual(result.name, "volume_up")
        self.assertEqual(result.to_action()["type"], "volume_up")

    def test_mute_the_system_routes_to_zero_volume(self):
        result = route("mute the system")
        self.assertEqual(result.name, "volume_set")
        self.assertEqual(result.params["level"], 0)

    def test_set_brightness_routes_with_level(self):
        result = route("set brightness to 70")
        self.assertEqual(result.name, "brightness")
        self.assertEqual(result.params["level"], 70)
        self.assertEqual(result.to_action()["level"], 70)

    def test_increase_brightness_routes_with_direction(self):
        result = route("increase brightness")
        self.assertEqual(result.name, "brightness")
        self.assertEqual(result.params["direction"], "up")
        self.assertEqual(result.to_action()["direction"], "up")

    def test_turn_on_dark_mode_routes_deterministically(self):
        result = route("turn on dark mode")
        self.assertEqual(result.name, "dark_mode")
        self.assertTrue(result.params["enable"])
        self.assertTrue(result.to_action()["enable"])

    def test_turn_off_dnd_routes_deterministically(self):
        result = route("turn off dnd")
        self.assertEqual(result.name, "do_not_disturb")
        self.assertFalse(result.params["enable"])
        self.assertFalse(result.to_action()["enable"])

    def test_lock_my_screen_routes_deterministically(self):
        result = route("lock my screen")
        self.assertEqual(result.name, "lock_screen")
        self.assertEqual(result.to_action()["type"], "lock_screen")

    def test_whatsapp_routes_deterministically(self):
        result = route("message vedang on whatsapp")
        self.assertEqual(result.name, "whatsapp_open")

    def test_whatsapp_send_with_message_routes_deterministically(self):
        result = route("send whatsapp to vedang message ship it tonight")
        self.assertEqual(result.name, "whatsapp_send")
        self.assertEqual(result.params["message"], "ship it tonight")

    def test_recap_routes_to_what_next(self):
        result = route("recap")
        self.assertEqual(result.name, "what_next")

    def test_news_shortcut_routes_to_news(self):
        result = route("news")
        self.assertEqual(result.name, "news")

    def test_bye_routes_to_sleep(self):
        result = route("bye")
        self.assertEqual(result.name, "butler_sleep")

    def test_stop_routes_to_pause(self):
        result = route("stop")
        self.assertEqual(result.name, "spotify_pause")

    def test_how_are_u_routes_to_greeting(self):
        result = route("how are u?")
        self.assertEqual(result.name, "greeting")

    def test_mcp_status_routes_deterministically(self):
        result = route("which mcp is failing")
        self.assertEqual(result.name, "mcp_status")

    def test_pause_music_routes_to_pause(self):
        result = route("pause music")
        self.assertEqual(result.name, "spotify_pause")
        self.assertEqual(result.to_action()["type"], "spotify_pause")

    def test_reminder_extracts_message(self):
        result = route("remind me in 30 minutes to check deployments")
        self.assertEqual(result.name, "set_reminder")
        self.assertEqual(result.params["minutes"], 30)
        self.assertEqual(result.params["message"], "check deployments")

    def test_natural_create_file_phrase_routes_deterministically(self):
        result = route("make a new file with the name Aditya")
        self.assertEqual(result.name, "create_file")
        self.assertEqual(result.params["filename"], "Aditya")

    def test_new_file_in_downloads_routes_with_location_path(self):
        result = route("new file in downloads")
        self.assertEqual(result.name, "create_file")
        self.assertEqual(result.params["path"], "~/Downloads/untitled.txt")

    def test_missing_file_name_requests_clarification(self):
        result = route("make a new file")
        self.assertEqual(result.name, "clarify_file")

    def test_delete_resume_file_routes_deterministically(self):
        result = route("delete resume file")
        self.assertEqual(result.name, "delete_file")
        self.assertEqual(result.params["path"], "resume")

    def test_zip_downloads_routes_deterministically(self):
        result = route("zip downloads")
        self.assertEqual(result.name, "zip_folder")
        self.assertEqual(result.params["path"], "~/Downloads")

    def test_absolute_reminder_phrase_routes_with_when(self):
        result = route("remind me at 5pm to check deployments")
        self.assertEqual(result.name, "set_reminder")
        self.assertEqual(result.params["when"], "5pm")
        self.assertEqual(result.params["message"], "check deployments")

    def test_new_project_in_vscode_opens_new_window(self):
        result = route("can you open a new project in visual studio code?")
        self.assertEqual(result.name, "open_editor_window")
        self.assertEqual(result.to_action()["type"], "open_editor")
        self.assertEqual(result.to_action()["editor"], "vscode")
        self.assertEqual(result.to_action()["mode"], "new_window")

    def test_last_workspace_is_deterministic(self):
        result = route("open last workspace")
        self.assertEqual(result.name, "open_last_workspace")
        self.assertFalse(result.needs_llm())

    def test_open_codex_in_terminal_is_deterministic(self):
        result = route("open codex in terminal")
        self.assertEqual(result.name, "open_codex")
        self.assertFalse(result.needs_llm())
        self.assertEqual(result.to_action()["type"], "open_terminal")

    def test_whats_on_hackernews_routes_to_agent(self):
        result = route("what's on hackernews")
        self.assertEqual(result.name, "hackernews")
        self.assertEqual(result.to_action()["agent"], "hackernews")

    def test_market_pulse_routes_to_agent(self):
        result = route("what's happening in AI today")
        self.assertEqual(result.name, "market")
        self.assertEqual(result.to_action()["agent"], "market")

    def test_air_news_routes_to_ai_news(self):
        result = route("tell me the latest air news")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "AI")

    def test_latest_news_on_topic_routes_directly(self):
        result = route("can you tell me latest news on iran and us")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "iran and us")

    def test_news_about_topic_routes_directly(self):
        result = route("news about google gemma")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "google gemma")

    def test_recent_news_on_topic_routes_directly(self):
        result = route("recent news on claude")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "claude")

    def test_whats_happening_in_country_routes_to_news(self):
        result = route("what's happening in india")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "india")

    def test_latest_news_in_topic_last_24_hours_routes_directly(self):
        result = route("latest news in india last 24 hours")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "india")
        self.assertEqual(result.params["hours"], 24)

    def test_latest_news_handles_glued_in_last_phrase_from_stt(self):
        result = route("tell me latest news in indiain last 24 hours")
        self.assertEqual(result.name, "news")
        self.assertEqual(result.params["topic"], "india")
        self.assertEqual(result.params["hours"], 24)

    def test_whats_reddit_saying_routes_to_agent(self):
        result = route("what's reddit saying")
        self.assertEqual(result.name, "reddit")
        self.assertEqual(result.to_action()["agent"], "reddit")

    def test_trending_repos_routes_to_agent(self):
        result = route("trending repos")
        self.assertEqual(result.name, "github_trending")
        self.assertEqual(result.to_action()["agent"], "github_trending")

    @patch("intents.router._call_classifier")
    def test_classifier_prompt_uses_recent_session_history(self, mock_call_classifier):
        ctx.reset()
        ctx.add_user("write mail to vedang")
        ctx.add_butler("What is the subject?")
        mock_call_classifier.return_value = '{"intent":"compose_email","params":{"to":"vedang","subject":"project update","body":""},"confidence":0.91,"platform":null,"needs_confirmation":false}'

        result = _classifier_intent("write mail to vedang about project update")

        self.assertEqual(result.name, "compose_email")
        self.assertEqual(result.params["recipient"], "vedang")
        prompt = mock_call_classifier.call_args.args[0]
        self.assertIn("User: write mail to vedang", prompt)
        self.assertIn("Burry: What is the subject?", prompt)

    @patch("intents.router._call_classifier")
    def test_classifier_low_confidence_drops_into_conversation(self, mock_call_classifier):
        mock_call_classifier.return_value = '{"intent":"open_app","params":{"app":"Terminal"},"confidence":0.2,"platform":null,"needs_confirmation":false}'

        result = _classifier_intent("open terminal maybe")

        self.assertEqual(result.name, "conversation")

    def test_work_question_routes_directly_to_what_next(self):
        result = route("what should i do")
        self.assertEqual(result.name, "what_next")

    def test_regular_question_routes_to_question_intent(self):
        result = route("why did spotify not understand me?")
        self.assertEqual(result.name, "question")
        self.assertTrue(result.needs_llm())


if __name__ == "__main__":
    unittest.main()
