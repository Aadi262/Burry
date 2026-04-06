import unittest

from intents.router import route


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
        self.assertIn("view=cm", result.to_action()["url"])

    def test_new_mail_phrase_routes_to_gmail_compose(self):
        result = route("can you open a new mail")
        self.assertEqual(result.name, "compose_email")
        self.assertIn("view=cm", result.to_action()["url"])

    def test_compose_mail_to_name_sets_recipient(self):
        result = route("compose mail to vedang")
        self.assertEqual(result.name, "compose_email")
        self.assertIn("to=vedang", result.to_action()["url"])

    def test_compose_mail_accepts_male_homophone(self):
        result = route("compose a new male to vedang")
        self.assertEqual(result.name, "compose_email")
        self.assertIn("to=vedang", result.to_action()["url"])

    def test_compose_mail_parses_spoken_email_address(self):
        result = route("write a mail to vedang2803 at gmail dot com")
        self.assertEqual(result.name, "compose_email")
        self.assertIn("to=vedang2803%40gmail.com", result.to_action()["url"])

    def test_compose_mail_parses_subject_and_body(self):
        result = route("write a mail to vedang2803@gmail.com subject project update body shipping tonight")
        self.assertEqual(result.name, "compose_email")
        url = result.to_action()["url"]
        self.assertIn("to=vedang2803%40gmail.com", url)
        self.assertIn("su=project+update", url)
        self.assertIn("body=shipping+tonight", url)

    def test_open_google_sheet_routes_to_browser_url(self):
        result = route("open google sheet")
        self.assertEqual(result.name, "open_app")
        action = result.to_action()
        self.assertEqual(action["type"], "open_url_in_browser")
        self.assertIn("sheets.google.com", action["url"])

    def test_open_new_tab_routes_deterministically(self):
        result = route("can you open a new tab")
        self.assertEqual(result.name, "browser_new_tab")
        self.assertEqual(result.to_action()["type"], "browser_new_tab")

    def test_open_new_tab_to_search_routes_to_browser_search(self):
        result = route("open a new tab to search latest gemma news")
        self.assertEqual(result.name, "browser_search")
        self.assertEqual(result.params["query"], "latest gemma news")

    def test_close_tab_routes_deterministically(self):
        result = route("close the tabs")
        self.assertEqual(result.name, "browser_close_tab")

    def test_close_window_routes_deterministically(self):
        result = route("close the screen")
        self.assertEqual(result.name, "browser_close_window")

    def test_pause_video_routes_deterministically(self):
        result = route("pause video")
        self.assertEqual(result.name, "pause_video")

    def test_volume_up_routes_to_system_volume(self):
        result = route("turn up the volume")
        self.assertEqual(result.name, "system_volume")
        self.assertEqual(result.params["direction"], "up")

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

    def test_missing_file_name_requests_clarification(self):
        result = route("make a new file")
        self.assertEqual(result.name, "clarify_file")

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

    def test_work_question_routes_directly_to_what_next(self):
        result = route("what should i do")
        self.assertEqual(result.name, "what_next")

    def test_regular_question_routes_to_question_intent(self):
        result = route("why did spotify not understand me?")
        self.assertEqual(result.name, "question")
        self.assertTrue(result.needs_llm())


if __name__ == "__main__":
    unittest.main()
