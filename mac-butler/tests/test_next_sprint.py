#!/usr/bin/env python3
"""Tests for the next AgentScope integration sprint."""
import pathlib
import unittest


class TestLifecycleHooks(unittest.TestCase):

    def test_register_burry_hooks_exists(self):
        from brain.agentscope_backbone import _register_burry_hooks
        self.assertTrue(callable(_register_burry_hooks))

    def test_ws_broadcast_exists(self):
        from brain.agentscope_backbone import _ws_broadcast
        self.assertTrue(callable(_ws_broadcast))

    def test_ws_broadcast_does_not_crash_without_dashboard(self):
        from brain.agentscope_backbone import _ws_broadcast
        try:
            _ws_broadcast({"type": "test", "payload": {}})
        except Exception as exc:
            self.fail(f"_ws_broadcast crashed: {exc}")

    def test_hooks_registered_on_agent_build(self):
        src = pathlib.Path("brain/agentscope_backbone.py").read_text()
        self.assertIn("_register_burry_hooks", src)
        self.assertIn("pre_reply", src)
        self.assertIn("post_reply", src)
        self.assertIn("pre_acting", src)
        self.assertIn("post_acting", src)
        self.assertIn("pre_reasoning", src)

    def test_broadcast_plan_update_exists(self):
        from brain.agentscope_backbone import _broadcast_plan_update
        self.assertTrue(callable(_broadcast_plan_update))


class TestFrontendEventHandlers(unittest.TestCase):

    def test_stream_js_handles_tool_start(self):
        src = pathlib.Path("projects/frontend/modules/stream.js").read_text()
        self.assertIn("tool_start", src)
        self.assertIn("tool_end", src)
        self.assertIn("agent_thinking", src)
        self.assertIn("agent_reply", src)
        self.assertIn("plan_update", src)

    def test_tool_map_has_all_tools(self):
        src = pathlib.Path("projects/frontend/modules/panels.js").read_text()
        required_tools = [
            "browse_web", "deep_research", "plan_and_execute",
            "open_project", "run_shell", "git_commit",
            "send_email", "send_imessage", "spotify_control",
            "ssh_vps", "search_knowledge_base",
        ]
        for tool in required_tools:
            self.assertIn(tool, src, f"Tool '{tool}' missing from TOOL_MAP")

    def test_events_js_has_truncation_indicator(self):
        src = pathlib.Path("projects/frontend/modules/events.js").read_text()
        self.assertIn("truncated", src.lower(), "No truncation indicator in events.js")

    def test_events_js_has_tool_call_kind(self):
        src = pathlib.Path("projects/frontend/modules/events.js").read_text()
        self.assertIn("tool_start", src)
        self.assertIn("tool_end", src)

    def test_index_html_has_new_panels(self):
        src = pathlib.Path("projects/frontend/index.html").read_text()
        self.assertIn("agent-trace-feed", src, "Agent trace panel missing")
        self.assertIn("tool-exec-row", src, "Live execution panel missing")
        self.assertIn("plan-steps-feed", src, "Plan steps panel missing")

    def test_style_css_has_new_panel_styles(self):
        src = pathlib.Path("projects/frontend/style.css").read_text()
        self.assertIn("agent-trace-panel", src)
        self.assertIn("tool-exec-panel", src)
        self.assertIn("plan-steps-panel", src)

    def test_js_files_pass_node_check(self):
        import subprocess
        result = subprocess.run(
            ["node", "--check",
             "projects/frontend/modules/stream.js",
             "projects/frontend/modules/panels.js",
             "projects/frontend/modules/events.js"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"JS syntax error: {result.stderr}")


class TestObservability(unittest.TestCase):

    def test_tracing_url_auto_detect_in_backbone(self):
        src = pathlib.Path("brain/agentscope_backbone.py").read_text()
        self.assertIn("localhost:4318", src, "No local OTel backend auto-detect")

    def test_agentscope_init_has_tracing_url(self):
        src = pathlib.Path("brain/agentscope_backbone.py").read_text()
        self.assertIn("tracing_url", src)


class TestRAG(unittest.TestCase):

    def test_init_agentscope_rag_exists(self):
        from memory.knowledge_base import init_agentscope_rag
        self.assertTrue(callable(init_agentscope_rag))

    def test_search_custom_kb_fallback_exists(self):
        from memory.knowledge_base import _search_custom_kb
        self.assertTrue(callable(_search_custom_kb))

    def test_search_does_not_crash(self):
        from memory.knowledge_base import search_knowledge_base
        result = search_knowledge_base("test query")
        self.assertIsInstance(result, list)


class TestOutOfBoxAgents(unittest.TestCase):

    def test_browser_agent_has_agentscope_path(self):
        src = pathlib.Path("agents/browser_agent.py").read_text()
        self.assertIn("BrowserAgent", src)
        self.assertIn("_sync_browse_custom", src, "No custom fallback in browser agent")

    def test_research_agent_has_agentscope_path(self):
        src = pathlib.Path("agents/research_agent.py").read_text()
        self.assertIn("DeepResearchAgent", src)
        self.assertIn("_deep_research_custom", src, "No custom fallback in research agent")

    def test_browser_agent_does_not_crash_on_import(self):
        import agents.browser_agent
        self.assertTrue(hasattr(agents.browser_agent, "sync_browse"))

    def test_research_agent_does_not_crash_on_import(self):
        import agents.research_agent
        self.assertTrue(hasattr(agents.research_agent, "deep_research"))


class TestFullIntegration(unittest.TestCase):

    def test_all_modules_import_clean(self):
        modules = [
            "brain.agentscope_backbone",
            "agents.browser_agent",
            "agents.research_agent",
            "agents.runner",
            "memory.knowledge_base",
        ]
        for mod in modules:
            try:
                __import__(mod)
            except Exception as exc:
                self.fail(f"Import failed {mod}: {exc}")

    def test_persistent_loop_still_running(self):
        from brain.agentscope_backbone import _get_persistent_loop
        loop = _get_persistent_loop()
        self.assertFalse(loop.is_closed())

    def test_timing_imports_fast(self):
        import time
        start = time.monotonic()
        import brain.agentscope_backbone
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 5.0, f"backbone import took {elapsed:.1f}s - too slow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
