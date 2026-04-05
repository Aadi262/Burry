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

    def test_compose_mail_routes_to_gmail_compose(self):
        result = route("can you compose a new mail")
        self.assertEqual(result.name, "open_app")
        self.assertIn("compose=new", result.to_action()["url"])

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

    def test_whats_reddit_saying_routes_to_agent(self):
        result = route("what's reddit saying")
        self.assertEqual(result.name, "reddit")
        self.assertEqual(result.to_action()["agent"], "reddit")

    def test_trending_repos_routes_to_agent(self):
        result = route("trending repos")
        self.assertEqual(result.name, "github_trending")
        self.assertEqual(result.to_action()["agent"], "github_trending")

    def test_work_question_falls_back_to_llm(self):
        result = route("what should i do next")
        self.assertTrue(result.needs_llm())

    def test_regular_question_routes_to_question_intent(self):
        result = route("why did spotify not understand me?")
        self.assertEqual(result.name, "question")
        self.assertTrue(result.needs_llm())


if __name__ == "__main__":
    unittest.main()
