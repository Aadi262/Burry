#!/usr/bin/env python3
"""Tests for remaining AgentScope integration items."""
import json
import pathlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestSkillMdFiles(unittest.TestCase):

    def test_all_agent_skills_have_skill_md(self):
        skills_dir = pathlib.Path("agent_skills")
        if not skills_dir.exists():
            self.skipTest("agent_skills directory not found")
        for subdir in sorted(skills_dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("_"):
                skill_md = subdir / "SKILL.md"
                self.assertTrue(
                    skill_md.exists(),
                    f"Missing SKILL.md in agent_skills/{subdir.name}/",
                )

    def test_skill_md_has_required_fields(self):
        skills_dir = pathlib.Path("agent_skills")
        if not skills_dir.exists():
            self.skipTest("agent_skills directory not found")
        for skill_md in skills_dir.glob("*/SKILL.md"):
            content = skill_md.read_text()
            self.assertIn("name", content, f"{skill_md} missing name field")
            self.assertIn("description", content, f"{skill_md} missing description")
            self.assertIn("trigger_patterns", content, f"{skill_md} missing trigger_patterns")


class TestSessionPersistence(unittest.TestCase):

    def test_save_restore_functions_exist(self):
        from memory.long_term import save_session_state, restore_session_state
        self.assertTrue(callable(save_session_state))
        self.assertTrue(callable(restore_session_state))

    def test_session_file_path_defined(self):
        from memory.long_term import SESSION_FILE
        self.assertIsNotNone(SESSION_FILE)

    def test_shutdown_handler_in_butler(self):
        src = pathlib.Path("butler.py").read_text()
        self.assertIn("_shutdown_handler", src,
            "Shutdown handler not wired in butler.py")
        self.assertIn("signal.SIGTERM", src,
            "SIGTERM handler not registered")
        self.assertIn("atexit.register", src,
            "atexit handler not registered")

    def test_save_session_state_handles_async_memory_snapshot(self):
        from memory import long_term

        class FakeMessage:
            role = "assistant"

            def get_text_content(self):
                return "All good."

        class FakeMemory:
            def state_dict(self):
                return {"saved": True}

            async def get_memory(self):
                return [FakeMessage()]

        class FakeAgent:
            memory = FakeMemory()

        with tempfile.TemporaryDirectory() as tempdir:
            session_path = Path(tempdir) / "burry_session.json"
            with patch.object(long_term, "SESSION_FILE", session_path):
                long_term.save_session_state(FakeAgent())
                payload = json.loads(session_path.read_text())

        self.assertEqual(payload["memory"][0]["content"], "All good.")
        self.assertEqual(payload["memory_state"], {"saved": True})


class TestRLLoop(unittest.TestCase):

    def test_record_episode_with_agentscope_feedback_exists(self):
        from memory.rl_loop import record_episode_with_agentscope_feedback
        self.assertTrue(callable(record_episode_with_agentscope_feedback))

    def test_rl_feedback_does_not_crash_without_tuner(self):
        from memory.rl_loop import record_episode_with_agentscope_feedback
        try:
            record_episode_with_agentscope_feedback(
                text="test command",
                intent="question",
                model="gemma4:e4b",
                response="test response",
                outcome="success",
            )
        except Exception as exc:
            self.fail(f"record_episode_with_agentscope_feedback raised: {exc}")


class TestKnowledgeBase(unittest.TestCase):

    def test_search_knowledge_base_exists(self):
        from memory.knowledge_base import search_knowledge_base
        self.assertTrue(callable(search_knowledge_base))

    def test_custom_kb_fallback_exists(self):
        from memory.knowledge_base import _search_custom_kb
        self.assertTrue(callable(_search_custom_kb))

    def test_init_agentscope_rag_exists(self):
        from memory.knowledge_base import init_agentscope_rag
        self.assertTrue(callable(init_agentscope_rag))

    def test_search_does_not_crash_without_agentscope_rag(self):
        from memory.knowledge_base import search_knowledge_base
        try:
            results = search_knowledge_base("test query")
            self.assertIsInstance(results, list)
        except Exception as exc:
            self.fail(f"search_knowledge_base raised: {exc}")


class TestA2AServer(unittest.TestCase):

    def test_start_agentscope_a2a_exists(self):
        from channels.a2a_server import start_agentscope_a2a
        self.assertTrue(callable(start_agentscope_a2a))

    def test_a2a_does_not_crash_without_module(self):
        from channels.a2a_server import start_agentscope_a2a
        result = start_agentscope_a2a(agent=None)
        self.assertIsInstance(result, bool)


class TestFullPipeline(unittest.TestCase):

    def test_all_backbone_modules_import(self):
        modules = [
            "brain.agentscope_backbone",
            "brain.agentscope_ollama_model",
            "agents.planner_agent",
            "agents.research_agent",
            "agents.runner",
            "brain.toolkit",
            "brain.tools_registry",
            "memory.long_term",
            "memory.rl_loop",
            "memory.knowledge_base",
            "channels.a2a_server",
            "channels.imessage_channel",
            "runtime.tracing",
            "brain.rate_limiter",
            "brain.structured_output",
        ]
        for mod in modules:
            try:
                __import__(mod)
            except Exception as exc:
                self.fail(f"Failed to import {mod}: {exc}")

    def test_persistent_loop_running(self):
        from brain.agentscope_backbone import _get_persistent_loop
        loop = _get_persistent_loop()
        self.assertFalse(loop.is_closed(), "Persistent loop is closed")
        self.assertTrue(loop.is_running(), "Persistent loop not running")

    def test_intent_ctx_scaling(self):
        from brain.agentscope_backbone import _get_num_ctx
        self.assertLessEqual(_get_num_ctx("greeting"), 2048)
        self.assertGreaterEqual(_get_num_ctx("deep_research"), 4096)

    def test_toolkit_cache_is_dict(self):
        from brain.agentscope_backbone import _INTENT_TOOLKIT_CACHE
        self.assertIsInstance(_INTENT_TOOLKIT_CACHE, dict)

    def test_mcp_tools_cache_is_dict(self):
        from brain.agentscope_backbone import _MCP_TOOLS_CACHE
        self.assertIsInstance(_MCP_TOOLS_CACHE, dict)

    def test_parallel_tool_intents_defined(self):
        from brain.agentscope_backbone import PARALLEL_TOOL_INTENTS
        self.assertIn("question", PARALLEL_TOOL_INTENTS)
        self.assertIn("deep_research", PARALLEL_TOOL_INTENTS)

    def test_no_double_agentscope_init_in_runner(self):
        src = pathlib.Path("agents/runner.py").read_text()
        self.assertNotIn("agentscope.init(", src,
            "runner.py still calls agentscope.init() directly")

    def test_compression_config_not_none(self):
        from brain.agentscope_backbone import _compression_config
        cfg = _compression_config("gemma4:e4b")
        self.assertIsNotNone(cfg)

    def test_call_server_tool_args_fixed(self):
        src = pathlib.Path("brain/agentscope_backbone.py").read_text()
        self.assertNotIn(
            "call_server_tool(server_name, tool_name, kwargs)",
            src,
        )

    def test_planner_handles_running_loop(self):
        import inspect
        import agents.planner_agent as m
        src = inspect.getsource(m.plan_and_execute)
        self.assertIn("get_running_loop", src)

    def test_research_handles_running_loop(self):
        import inspect
        import agents.research_agent as m
        src = inspect.getsource(m.deep_research)
        self.assertIn("get_running_loop", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
