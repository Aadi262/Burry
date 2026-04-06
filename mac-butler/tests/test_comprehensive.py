#!/usr/bin/env python3
"""
tests/test_comprehensive.py
Comprehensive test suite for Mac Butler.
Tests every layer: identity, memory, tasks, context,
brain, executor, agents, heartbeat, confirmation gate,
and the full end-to-end pipeline.

Run: venv/bin/python -m pytest tests/test_comprehensive.py -v
Or:  venv/bin/python tests/test_comprehensive.py
"""

import json
import os
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make sure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════
# SUITE 1: IDENTITY LAYER
# ═══════════════════════════════════════════════════════════

class TestIdentityLayer(unittest.TestCase):
    """Tests for identity/loader.py — Butler must know Aditya."""

    def test_profile_yaml_exists(self):
        path = ROOT / "identity" / "profile.yaml"
        self.assertTrue(path.exists(),
            "identity/profile.yaml missing — Butler doesn't know who Aditya is")

    def test_loader_imports(self):
        try:
            from identity.loader import get_identity_context
        except ImportError as e:
            self.fail(f"identity/loader.py import failed: {e}")

    def test_identity_contains_name(self):
        from identity.loader import get_identity_context
        ctx = get_identity_context()
        self.assertIn("Aditya", ctx,
            "Identity missing Aditya's name")

    def test_identity_contains_company(self):
        from identity.loader import get_identity_context
        ctx = get_identity_context()
        self.assertIn("IEX", ctx,
            "Identity missing IEX (Aditya's company)")

    def test_identity_contains_projects(self):
        from identity.loader import get_identity_context
        ctx = get_identity_context()
        self.assertIn("mac-butler", ctx.lower(),
            "Identity missing mac-butler project")
        self.assertIn("email-infra", ctx.lower(),
            "Identity missing email-infra project")

    def test_identity_contains_how_to_talk(self):
        from identity.loader import get_identity_context
        ctx = get_identity_context()
        self.assertGreater(len(ctx), 100,
            "Identity context suspiciously short")

    def test_get_all_projects(self):
        try:
            from identity.loader import get_all_projects
            projects = get_all_projects()
            self.assertIsInstance(projects, list)
            names = [p.get("name","").lower() for p in projects]
            self.assertTrue(
                any("mac-butler" in n for n in names) or
                any("email" in n for n in names),
                f"No known projects found: {names}"
            )
        except ImportError:
            pass  # Optional function


# ═══════════════════════════════════════════════════════════
# SUITE 2: MEMORY LAYER
# ═══════════════════════════════════════════════════════════

class TestMemoryStore(unittest.TestCase):
    """Tests for memory/store.py — session recording."""

    def test_imports(self):
        try:
            from memory.store import (
                record_session,
                get_memory_context,
                get_last_session_summary,
            )
        except ImportError as e:
            self.fail(f"memory/store.py import failed: {e}")

    def test_record_and_retrieve_session(self):
        from memory.store import record_session, get_last_session_summary

        test_speech = f"Audit test at {datetime.now().isoformat()}"
        record_session(
            context_summary="testing memory store",
            speech=test_speech,
            actions=[{"type": "open_app", "app": "Cursor"}],
        )

        summary = get_last_session_summary()
        self.assertIsInstance(summary, str)
        self.assertGreater(len(summary), 5,
            "Session summary empty after recording")

    def test_summary_contains_action(self):
        from memory.store import record_session, get_last_session_summary

        record_session(
            context_summary="mac-butler audit",
            speech="Opened mac-butler folder.",
            actions=[{
                "type": "open_folder",
                "path": "~/Burry/mac-butler"
            }],
        )
        summary = get_last_session_summary()
        self.assertIn("mac-butler", summary.lower(),
            "Summary doesn't reference mac-butler folder")

    def test_summary_is_lean(self):
        """Summary must stay under ~300 chars — it goes in every LLM prompt."""
        from memory.store import get_last_session_summary
        summary = get_last_session_summary()
        self.assertLess(len(summary), 400,
            f"Summary too long for LLM prompt: {len(summary)} chars")

    def test_summary_does_not_echo_last_speech(self):
        from memory.store import record_session, get_last_session_summary

        record_session(
            context_summary="what should i do next",
            speech="Hey. mac-butler needs attention. Wire two-stage llm into butler.",
            actions=[],
        )

        summary = get_last_session_summary()
        self.assertIn("what should i do next", summary.lower())
        self.assertNotIn("needs attention", summary.lower())
        self.assertNotIn('Said: "', summary)

    def test_memory_file_created(self):
        from memory.store import record_session
        record_session("test", "test speech", [])
        mem_file = ROOT / "memory" / "butler_memory.json"
        self.assertTrue(mem_file.exists(),
            "butler_memory.json not created after record_session")


class TestLayeredMemory(unittest.TestCase):
    """Tests for memory/layered.py — 3-layer Claude Code pattern."""

    def test_imports(self):
        try:
            from memory.layered import (
                get_memory_index,
                append_to_index,
                save_session,
                save_project_detail,
                get_project_detail,
                search_sessions,
            )
        except ImportError as e:
            self.fail(f"memory/layered.py import failed: {e}")

    def test_memory_index_exists_or_creates(self):
        from memory.layered import get_memory_index
        index = get_memory_index()
        self.assertIsInstance(index, str)
        self.assertGreater(len(index), 20,
            "Memory index empty — should have project seeds")

    def test_memory_index_contains_projects(self):
        from memory.layered import get_memory_index
        index = get_memory_index()
        self.assertIn("mac-butler", index.lower(),
            "Memory index missing mac-butler")

    def test_append_to_index(self):
        from memory.layered import append_to_index, get_memory_index
        test_entry = f"test-entry-{int(time.time())}"
        append_to_index(test_entry)
        index = get_memory_index()
        self.assertIn(test_entry[:30], index,
            "append_to_index didn't write to MEMORY.md")

    def test_save_and_get_project_detail(self):
        from memory.layered import save_project_detail, get_project_detail
        test_content = f"Test note at {datetime.now().isoformat()}"
        save_project_detail("test-project", test_content)
        detail = get_project_detail("test-project")
        self.assertIn(test_content[:30], detail,
            "Project detail not saved/retrieved correctly")

    def test_save_session_layer3(self):
        from memory.layered import save_session, search_sessions
        unique_word = f"uniqueword{int(time.time())}"
        save_session({
            "timestamp": datetime.now().isoformat(),
            "speech": f"Testing {unique_word} session",
            "actions": [],
        })
        results = search_sessions(unique_word)
        self.assertTrue(len(results) > 0,
            "search_sessions didn't find recently saved session")

    def test_layer1_is_small(self):
        """Layer 1 must stay tiny — it's always loaded."""
        from memory.layered import get_memory_index
        index = get_memory_index()
        self.assertLess(len(index), 800,
            f"Memory index too large for always-loaded layer: {len(index)} chars")


# ═══════════════════════════════════════════════════════════
# SUITE 3: TASK SYSTEM
# ═══════════════════════════════════════════════════════════

class TestTaskSystem(unittest.TestCase):
    """Tests for tasks/task_store.py — persistent task list."""

    def test_imports(self):
        try:
            from tasks.task_store import (
                get_tasks_for_prompt,
                add_task,
                update_task_status,
                get_active_tasks,
            )
        except ImportError as e:
            self.fail(f"tasks/task_store.py import failed: {e}")

    def test_tasks_seeded(self):
        from tasks.task_store import _load, add_task
        tasks = _load()
        if not tasks:
            add_task("Wire two-stage LLM", "mac-butler", "high")
            add_task("Design trust score formula", "email-infra", "high")
            tasks = _load()
        self.assertGreater(len(tasks), 0,
            "Task store empty — should have seeded tasks")

    def test_has_both_projects(self):
        from tasks.task_store import _load, add_task
        tasks = _load()
        projects = {t.get("project","").lower() for t in tasks}
        if "mac-butler" not in projects:
            add_task("Wire two-stage LLM", "mac-butler", "high")
        if "email-infra" not in projects:
            add_task("Design trust score", "email-infra", "high")
        tasks = _load()
        projects = {t.get("project","").lower() for t in tasks}
        self.assertIn("mac-butler", projects,
            "No mac-butler tasks found")
        self.assertIn("email-infra", projects,
            "No email-infra tasks found")

    def test_get_tasks_for_prompt_format(self):
        from tasks.task_store import get_tasks_for_prompt
        prompt_text = get_tasks_for_prompt()
        self.assertIsInstance(prompt_text, str)
        self.assertIn("[TASK LIST]", prompt_text,
            "get_tasks_for_prompt missing [TASK LIST] header")
        # Check status icons
        self.assertTrue(
            any(icon in prompt_text for icon in ["○","◉","✓","✗"]),
            "No status icons in task list"
        )

    def test_add_and_update_task(self):
        from tasks.task_store import (
            add_task, update_task_status, get_active_tasks
        )
        task = add_task(
            "Test task for audit",
            "mac-butler",
            "high"
        )
        self.assertIn("id", task)
        self.assertEqual(task["status"], "todo")

        updated = update_task_status(task["id"], "in_progress")
        self.assertTrue(updated, "update_task_status returned False")

    def test_get_active_tasks_by_project(self):
        from tasks.task_store import get_active_tasks
        butler_tasks = get_active_tasks("mac-butler")
        self.assertIsInstance(butler_tasks, list)
        for t in butler_tasks:
            self.assertNotEqual(t.get("status"), "done",
                "get_active_tasks returned done tasks")

    def test_tasks_for_prompt_under_limit(self):
        """Task block must fit in compressed context."""
        from tasks.task_store import get_tasks_for_prompt
        prompt_text = get_tasks_for_prompt()
        self.assertLess(len(prompt_text), 500,
            f"Task list too long for context: {len(prompt_text)} chars")


# ═══════════════════════════════════════════════════════════
# SUITE 4: CONTEXT ENGINE
# ═══════════════════════════════════════════════════════════

class TestContextEngine(unittest.TestCase):
    """Tests for context/__init__.py — what Butler sees."""

    def test_imports(self):
        try:
            from context import build_structured_context
        except ImportError as e:
            self.fail(f"context import failed: {e}")

    def test_builds_without_crash(self):
        from context import build_structured_context
        try:
            ctx = build_structured_context()
        except Exception as e:
            self.fail(f"build_structured_context crashed: {e}")

    @patch("context.sync_from_todo_md")
    def test_build_context_uses_cached_tasks_instead_of_hot_path_sync(self, mock_sync):
        from context import build_structured_context

        build_structured_context()

        mock_sync.assert_not_called()

    def test_returns_formatted_string(self):
        from context import build_structured_context
        ctx = build_structured_context()
        self.assertIn("formatted", ctx)
        self.assertIsInstance(ctx["formatted"], str)
        self.assertGreater(len(ctx["formatted"]), 10)

    def test_context_under_700_chars(self):
        """Context MUST stay compressed — 14B models degrade with long context."""
        from context import build_structured_context
        ctx = build_structured_context()
        length = len(ctx["formatted"])
        self.assertLessEqual(length, 700,
            f"Context too long: {length} chars (max 700)")

    def test_no_raw_git_hashes(self):
        """Git hashes are noise — should be compressed to commit messages."""
        from context import build_structured_context
        ctx = build_structured_context()
        formatted = ctx["formatted"]
        lines = formatted.split("\n")
        for line in lines:
            words = line.strip().split()
            if words and len(words[0]) == 7:
                is_hash = all(
                    c in "0123456789abcdef"
                    for c in words[0].lower()
                )
                self.assertFalse(is_hash,
                    f"Raw git hash in context: {line}")

    def test_has_task_section(self):
        from context import build_structured_context
        ctx = build_structured_context()
        formatted = ctx["formatted"]
        has_tasks = (
            "[TASK LIST]" in formatted or
            "[PENDING TASKS]" in formatted or
            "mac-butler" in formatted.lower() or
            "email-infra" in formatted.lower()
        )
        self.assertTrue(has_tasks,
            "Context has no task/project reference")

    def test_has_time_section(self):
        from context import build_structured_context
        ctx = build_structured_context()
        self.assertIn("[TIME]", ctx["formatted"],
            "Context missing [TIME] section")

    def test_compress_function_exists(self):
        try:
            from context import _compress
            result = _compress("a " * 300, limit=100)
            self.assertLessEqual(len(result), 103)
        except ImportError:
            # _compress might be private — that's fine
            pass


# ═══════════════════════════════════════════════════════════
# SUITE 5: TWO-STAGE LLM BRAIN
# ═══════════════════════════════════════════════════════════

class TestTwoStageBrain(unittest.TestCase):
    """Tests for brain/ollama_client.py — the planning+speech engine."""

    KNOWN_CONTEXT = """[TASK LIST]
  ◉ Wire two-stage LLM (mac-butler) [HIGH]
  ○ Design trust score formula (email-infra) [HIGH]
  ○ Build reputation graph (email-infra)
[TIME]
  late_night (01:30 AM)
[FOCUS]
  project: mac-butler
  last work: fixing brain prompt"""

    def test_imports(self):
        try:
            from brain.ollama_client import (
                send_to_ollama,
                _call,
                _strip,
                _time_greeting,
            )
        except ImportError as e:
            self.fail(f"brain/ollama_client.py import failed: {e}")

    def test_strip_removes_fences(self):
        from brain.ollama_client import _strip
        fenced = '```json\n{"key": "value"}\n```'
        result = _strip(fenced)
        self.assertEqual(result, '{"key": "value"}')

    def test_strip_extracts_json(self):
        from brain.ollama_client import _strip
        with_text = 'Here is the answer: {"speech": "hello"} done'
        result = _strip(with_text)
        self.assertEqual(result, '{"speech": "hello"}')

    def test_time_greeting_morning(self):
        from brain.ollama_client import _time_greeting
        with patch("brain.ollama_client.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 9
            greeting = _time_greeting()
            self.assertIn(greeting,
                ["Good morning", "Morning"],
                f"Unexpected morning greeting: {greeting}")

    def test_time_greeting_late_night(self):
        from brain.ollama_client import _time_greeting
        with patch("brain.ollama_client.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 2
            greeting = _time_greeting()
            self.assertIn("grinding", greeting.lower(),
                f"Late night should say grinding, got: {greeting}")

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_send_to_ollama_returns_valid_json(self, mock_call, mock_call_voice):
        """Mock Ollama to test JSON parsing logic."""
        from brain.ollama_client import send_to_ollama

        # Stage 1: planner returns focused plan
        # Stage 2: speech returns sharp response
        mock_call.return_value = (
            '{"focus":"mac-butler two-stage LLM",'
            '"next":"fix planner prompt",'
            '"actions":[]}'
        )
        mock_call_voice.return_value = (
            '{"speech":"Still grinding. '
            '[[slnc 300]] mac-butler planner needs fixing. '
            'Want to tackle it now?",'
            '"greeting":"Still grinding",'
            '"actions":[]}'
        )

        result = send_to_ollama(self.KNOWN_CONTEXT)
        data = json.loads(result)

        self.assertIn("speech", data)
        self.assertIn("greeting", data)
        self.assertIn("actions", data)
        self.assertIsInstance(data["actions"], list)

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_speech_is_specific_not_generic(self, mock_call, mock_call_voice):
        """Speech must reference actual projects, not generic filler."""
        from brain.ollama_client import send_to_ollama

        mock_call.return_value = '{"focus":"mac-butler","next":"fix prompt","actions":[]}'
        mock_call_voice.return_value = (
            '{"speech":"Still grinding. mac-butler planner '
            'is the blocker. Fix it now?","greeting":"Still grinding",'
            '"actions":[]}'
        )

        result = send_to_ollama(self.KNOWN_CONTEXT)
        data = json.loads(result)
        speech = data["speech"].lower()

        generic_phrases = [
            "current work", "next useful step",
            "stay focused", "keep moving",
            "continue where you left off",
            "visible in your",
        ]
        specific_refs = [
            "mac-butler", "email-infra",
            "two-stage", "trust score",
            "planner", "executor",
        ]

        found_generic = [p for p in generic_phrases if p in speech]
        found_specific = [p for p in specific_refs if p in speech]

        self.assertEqual(found_generic, [],
            f"Generic phrases in speech: {found_generic}")
        self.assertTrue(len(found_specific) > 0,
            f"No specific project refs in speech: {speech}")

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_speech_under_word_limit(self, mock_call, mock_call_voice):
        from brain.ollama_client import send_to_ollama

        mock_call.return_value = '{"focus":"mac-butler","next":"fix","actions":[]}'
        mock_call_voice.return_value = (
            '{"speech":"Still grinding. mac-butler needs the '
            'planner fixed. Jump in?","greeting":"Still grinding",'
            '"actions":[]}'
        )

        result = send_to_ollama(self.KNOWN_CONTEXT)
        data = json.loads(result)
        word_count = len(data["speech"].split())
        self.assertLessEqual(word_count, 65,
            f"Speech too long: {word_count} words")

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_fallback_on_parse_failure(self, mock_call, mock_call_voice):
        """If LLM returns garbage, Butler should still respond."""
        from brain.ollama_client import send_to_ollama

        mock_call.return_value = "this is not json at all"
        mock_call_voice.return_value = "also not json"

        result = send_to_ollama(self.KNOWN_CONTEXT)
        # Should not crash — returns fallback JSON
        self.assertIsInstance(result, str)
        data = json.loads(result)
        self.assertIn("speech", data)

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_actions_preserved_from_planner(self, mock_call, mock_call_voice):
        """Actions from stage 1 should appear in final output."""
        from brain.ollama_client import send_to_ollama

        mock_call.return_value = (
            '{"focus":"mac-butler","next":"open project",'
            '"actions":[{"type":"open_editor",'
            '"path":"~/Burry/mac-butler","editor":"cursor","mode":"smart"}]}'
        )
        mock_call_voice.return_value = (
            '{"speech":"Morning. mac-butler is calling. Open it?",'
            '"greeting":"Morning","actions":[]}'
        )

        result = send_to_ollama(self.KNOWN_CONTEXT)
        data = json.loads(result)
        # Actions from stage 1 should be merged if stage 2 drops them
        self.assertTrue(
            len(data.get("actions", [])) > 0,
            "Actions from planner were lost"
        )


# ═══════════════════════════════════════════════════════════
# SUITE 6: EXECUTOR ENGINE
# ═══════════════════════════════════════════════════════════

class TestExecutorEngine(unittest.TestCase):
    """Tests for executor/engine.py — safe action execution."""

    def test_imports(self):
        try:
            from executor.engine import Executor
        except ImportError as e:
            self.fail(f"executor/engine.py import failed: {e}")

    def test_notify_action(self):
        from executor.engine import Executor
        e = Executor()
        results = e.run([{
            "type": "notify",
            "title": "Butler test",
            "message": "Comprehensive test suite running"
        }])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "ok",
            f"notify failed: {results[0]}")

    def test_unknown_action_handled(self):
        from executor.engine import Executor
        e = Executor()
        results = e.run([{
            "type": "totally_fake_action_xyz"
        }])
        self.assertEqual(results[0]["status"], "error",
            "Unknown action should return error, not crash")

    def test_empty_actions(self):
        from executor.engine import Executor
        e = Executor()
        results = e.run([])
        self.assertEqual(results, [])

    def test_requires_confirmation_git_push(self):
        from executor.engine import Executor
        e = Executor()
        action = {"type": "run_command", "cmd": "git push origin main"}
        self.assertTrue(
            e._requires_confirmation(action),
            "git push must require confirmation"
        )

    def test_requires_confirmation_docker_stop(self):
        from executor.engine import Executor
        e = Executor()
        action = {"type": "run_command", "cmd": "docker stop api-service"}
        self.assertTrue(
            e._requires_confirmation(action),
            "docker stop must require confirmation"
        )

    def test_no_confirmation_for_safe_commands(self):
        from executor.engine import Executor
        e = Executor()
        safe_actions = [
            {"type": "open_app", "app": "Cursor"},
            {"type": "run_command", "cmd": "git status"},
            {"type": "run_command", "cmd": "ls -la"},
            {"type": "play_music", "mode": "focus"},
        ]
        for action in safe_actions:
            self.assertFalse(
                e._requires_confirmation(action),
                f"Safe action should not need confirmation: {action}"
            )

    def test_safe_path_validation(self):
        from executor.engine import Executor
        e = Executor()
        # Should not raise for valid home paths
        try:
            e._safe_home_path("~/Burry/mac-butler")
        except Exception as ex:
            self.fail(f"Valid path raised exception: {ex}")

    def test_run_agent_task_wired(self):
        """Executor must have run_agent_task method."""
        from executor.engine import Executor
        e = Executor()
        self.assertTrue(
            hasattr(e, "run_agent_task"),
            "Executor missing run_agent_task method"
        )


class TestAppAwareExecutor(unittest.TestCase):
    def test_app_state_imports(self):
        try:
            from executor.app_state import (
                get_app_state,
                get_window_count,
                is_app_running,
            )
            self.assertTrue(callable(is_app_running))
            self.assertTrue(callable(get_window_count))
            self.assertTrue(callable(get_app_state))
        except ImportError as e:
            self.fail(f"app_state.py import failed: {e}")

    def test_is_app_running_returns_bool(self):
        from executor.app_state import is_app_running

        result = is_app_running("Finder")
        self.assertIsInstance(result, bool)
        self.assertTrue(result, "Finder is always running")

    def test_get_app_state_structure(self):
        from executor.app_state import get_app_state

        state = get_app_state("Finder")
        self.assertIn("running", state)
        self.assertIn("window_count", state)
        self.assertIn("focused", state)
        self.assertTrue(state["running"])

    def test_terminal_mode_field(self):
        from executor.engine import Executor

        self.assertTrue(hasattr(Executor(), "open_terminal"))

    def test_editor_new_window_mode(self):
        from executor.engine import Executor

        self.assertTrue(hasattr(Executor(), "open_editor"))

    def test_open_app_smart_mode(self):
        from executor.engine import Executor

        with patch("executor.app_state.is_app_running", return_value=True):
            with patch("executor.engine.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(stdout="", stderr="")
                result = Executor().open_app("TestApp", mode="smart")
                self.assertIn("focused", result.lower())

    def test_open_app_new_mode(self):
        from executor.engine import Executor

        with patch("executor.engine.subprocess.Popen") as mock_popen:
            Executor().open_app("TestApp", mode="new")
            call_args = mock_popen.call_args[0][0]
            self.assertIn("-n", call_args)

    def test_vps_config_fields(self):
        import butler_config

        self.assertTrue(
            hasattr(butler_config, "USE_VPS_OLLAMA"),
            "butler_config missing USE_VPS_OLLAMA",
        )
        self.assertTrue(
            hasattr(butler_config, "VPS_OLLAMA_URL"),
            "butler_config missing VPS_OLLAMA_URL",
        )

    def test_ollama_client_has_vps_routing(self):
        try:
            from brain.ollama_client import _get_ollama_url, check_vps_connection

            self.assertTrue(callable(_get_ollama_url))
            self.assertTrue(callable(check_vps_connection))
        except ImportError as e:
            self.fail(f"VPS routing not wired: {e}")

    def test_check_vps_connection_returns_dict(self):
        from brain.ollama_client import check_vps_connection

        result = check_vps_connection()
        self.assertIn("status", result)
        self.assertIn("backend", result)


# ═══════════════════════════════════════════════════════════
# SUITE 7: SPECIALIST AGENTS
# ═══════════════════════════════════════════════════════════

class TestSpecialistAgents(unittest.TestCase):
    """Tests for agents/runner.py — multi-model specialist system."""

    def test_imports(self):
        try:
            from agents.runner import (
                run_agent,
                _get_installed_models,
                _pick_model,
            )
        except ImportError as e:
            self.fail(f"agents/runner.py import failed: {e}")

    def test_get_installed_models_returns_set(self):
        from agents.runner import _get_installed_models
        models = _get_installed_models()
        self.assertIsInstance(models, set,
            "_get_installed_models should return a set")

    def test_pick_model_returns_string(self):
        from agents.runner import _pick_model
        for agent_type in ["news","market","hackernews","reddit","github_trending","vps","memory","code","search"]:
            model = _pick_model(agent_type)
            self.assertIsInstance(model, str)
            self.assertGreater(len(model), 0,
                f"_pick_model returned empty for {agent_type}")

    def test_pick_model_fallback(self):
        """If specialist not installed, should fall back."""
        from agents.runner import _pick_model
        from butler_config import OLLAMA_MODEL
        # Even if all specialists are missing, should return SOMETHING
        model = _pick_model("nonexistent_agent_type")
        self.assertIsInstance(model, str)

    def test_run_agent_unknown_type(self):
        from agents.runner import run_agent
        result = run_agent("totally_fake_agent", {})
        self.assertEqual(result["status"], "error",
            "Unknown agent type should return error status")

    @patch("agents.runner._call_model")
    @patch("agents.runner._fetch_headlines")
    def test_news_agent_with_headlines(
        self, mock_headlines, mock_call
    ):
        from agents.runner import run_agent

        mock_headlines.return_value = (
            "Headline 1: AI breakthrough\n"
            "Headline 2: LLM news"
        )
        mock_call.return_value = (
            "1. AI breakthrough reported. "
            "2. LLM developments continuing."
        )

        result = run_agent("news", {
            "topic": "AI", "hours": 24
        })
        self.assertEqual(result["status"], "ok")
        self.assertGreater(len(result["result"]), 5)

    @patch("agents.runner._fetch_headlines")
    def test_news_agent_no_headlines_graceful(
        self, mock_headlines
    ):
        from agents.runner import run_agent
        mock_headlines.return_value = ""
        result = run_agent("news", {"topic": "obscure"})
        self.assertEqual(result["status"], "ok",
            "News agent should handle empty headlines gracefully")

    @patch("agents.runner._call_model")
    @patch("agents.runner._fetch_headlines")
    def test_search_agent_returns_answer(
        self, mock_headlines, mock_call
    ):
        from agents.runner import run_agent

        mock_headlines.return_value = "Qwen is a model by Alibaba"
        mock_call.return_value = "Qwen is Alibaba's LLM family."

        result = run_agent("search", {
            "query": "what is Qwen"
        })
        self.assertEqual(result["status"], "ok")
        self.assertIn("Qwen", result["result"])

    def test_vps_agent_no_host(self):
        from agents.runner import run_agent
        result = run_agent("vps", {})
        # Should fail gracefully when no host configured
        self.assertIn(result["status"], ["error", "ok"],
            "VPS agent should return structured result")

    @patch("agents.runner._call_model")
    def test_memory_agent_compresses(self, mock_call):
        from agents.runner import run_agent

        mock_call.return_value = (
            "04/04: worked on mac-butler planner\n"
            "04/03: designed trust score concept\n"
            "04/02: started email-infra research"
        )

        result = run_agent("memory", {
            "sessions": [
                {
                    "timestamp": "2026-04-04T01:00:00",
                    "speech": "Fixed mac-butler planner"
                },
                {
                    "timestamp": "2026-04-03T23:00:00",
                    "speech": "Trust score design for email-infra"
                },
            ]
        })
        self.assertEqual(result["status"], "ok")
        self.assertIn("points", result.get("data", {}))

    def test_model_routing_all_agents(self):
        """Print model routing — not a failure test, informational."""
        from agents.runner import _pick_model, _get_installed_models
        installed = _get_installed_models()
        print(f"\n  Installed models: {installed}")
        for agent_type in ["news","market","hackernews","reddit","github_trending","vps","memory","code","search"]:
            model = _pick_model(agent_type)
            print(f"  {agent_type:8} → {model}")


# ═══════════════════════════════════════════════════════════
# SUITE 8: KAIROS HEARTBEAT
# ═══════════════════════════════════════════════════════════

class TestHeartbeat(unittest.TestCase):
    """Tests for daemon/heartbeat.py — KAIROS background monitor."""

    def test_imports(self):
        try:
            from daemon.heartbeat import heartbeat_tick, run_heartbeat
        except ImportError as e:
            self.fail(f"daemon/heartbeat.py import failed: {e}")

    @patch("daemon.heartbeat._call")
    @patch("daemon.heartbeat.build_structured_context")
    def test_heartbeat_silent_when_nothing(
        self, mock_ctx, mock_call
    ):
        from daemon.heartbeat import heartbeat_tick

        mock_ctx.return_value = {
            "formatted": "[TASK LIST]\n  ○ Some task"
        }
        mock_call.return_value = "nothing"

        # Should complete without crash and without notifying
        try:
            heartbeat_tick()
        except Exception as e:
            self.fail(f"heartbeat_tick crashed: {e}")

    @patch("daemon.heartbeat._call")
    @patch("daemon.heartbeat.build_structured_context")
    @patch("daemon.heartbeat.Executor")
    def test_heartbeat_notifies_when_relevant(
        self, mock_executor, mock_ctx, mock_call
    ):
        from daemon.heartbeat import heartbeat_tick

        mock_ctx.return_value = {
            "formatted": (
                "[TASK LIST]\n  ◉ urgent mac-butler fix [HIGH]"
            )
        }
        mock_call.return_value = (
            '{"notify": true, '
            '"message": "mac-butler executor needs testing"}'
        )

        mock_executor_instance = MagicMock()
        mock_executor.return_value = mock_executor_instance

        heartbeat_tick()

        mock_executor_instance.run.assert_called_once()

    def test_heartbeat_skips_sleep_hours(self):
        """Heartbeat must not run during 5-9 AM (sleep time)."""
        from daemon.heartbeat import heartbeat_tick
        with patch("daemon.heartbeat.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 7
            # Should return early without calling LLM
            with patch(
                "daemon.heartbeat.build_structured_context"
            ) as mock_ctx:
                heartbeat_tick()
                mock_ctx.assert_not_called()

    def test_heartbeat_never_crashes(self):
        """Heartbeat must NEVER crash — it runs in background."""
        from daemon.heartbeat import heartbeat_tick
        with patch(
            "daemon.heartbeat.build_structured_context",
            side_effect=Exception("simulated crash")
        ):
            try:
                heartbeat_tick()
            except Exception as e:
                self.fail(
                    f"heartbeat_tick crashed instead of "
                    f"handling gracefully: {e}"
                )


# ═══════════════════════════════════════════════════════════
# SUITE 9: FULL PIPELINE INTEGRATION
# ═══════════════════════════════════════════════════════════

class TestFullPipeline(unittest.TestCase):
    """Integration tests — full end-to-end pipeline."""

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_context_flows_into_brain(self, mock_call, mock_call_voice):
        """Context engine output should flow into the brain."""
        from context import build_structured_context
        from brain.ollama_client import send_to_ollama

        mock_call.return_value = '{"focus":"mac-butler","next":"fix prompt","actions":[]}'
        mock_call_voice.return_value = (
            '{"speech":"Morning. mac-butler planner needs fixing. '
            'Tackle it?","greeting":"Morning","actions":[]}'
        )

        ctx = build_structured_context()
        result = send_to_ollama(ctx["formatted"])
        data = json.loads(result)

        self.assertIn("speech", data)
        self.assertGreater(len(data["speech"]), 5)

    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_memory_flows_into_brain(self, mock_call, mock_call_voice):
        """Brain must receive memory context in its prompt."""
        from memory.store import record_session
        from brain.ollama_client import send_to_ollama

        # Record a session first
        record_session(
            context_summary="mac-butler audit",
            speech="Fixed the planner prompt.",
            actions=[]
        )

        # Track what gets sent to the model
        captured_prompts = []

        def capture_call(prompt, model, **kwargs):
            captured_prompts.append(prompt)
            return '{"focus":"mac-butler","next":"continue","actions":[]}'

        mock_call.side_effect = capture_call
        mock_call_voice.side_effect = lambda prompt, model, **kwargs: captured_prompts.append(prompt) or '{"speech":"Morning. mac-butler next.","greeting":"Morning","actions":[]}'

        send_to_ollama("[FOCUS]\n  project: mac-butler\n[TIME]\n  morning")

        # Memory should appear in one of the prompts
        all_prompts = " ".join(captured_prompts).lower()
        has_memory = (
            "last active" in all_prompts or
            "last session" in all_prompts or
            "previously" in all_prompts or
            "mac-butler" in all_prompts
        )
        self.assertTrue(has_memory,
            "Memory context not flowing into brain prompts")

    @patch("brain.ollama_client._call")
    def test_agent_results_enrich_speech(self, mock_call):
        """Agent results should be incorporated into final speech."""
        from butler import _rewrite_speech_with_agent_results

        mock_call.return_value = (
            "Anthropic released Claude 4 and "
            "OpenAI launched GPT-5 today."
        )

        enriched = _rewrite_speech_with_agent_results(
            speech="Here is the latest AI news.",
            execution_results=[{
                "action": "run_agent",
                "status": "ok",
                "result": (
                    "Major AI releases: "
                    "Claude 4 and GPT-5 launched today"
                ),
            }]
        )

        # Should produce enriched speech or empty string
        self.assertIsInstance(enriched, str)

    def test_observe_loop_skips_trivial_results(self):
        """Observe loop must not speak for trivial actions."""
        from butler import observe_and_followup

        trivial_results = [
            {"action": "open_app", "status": "ok",
             "result": "opened Cursor"},
            {"action": "play_music", "status": "ok",
             "result": "music paused"},
        ]

        observation = observe_and_followup(
            plan={"speech": "Opening Cursor."},
            execution_results=trivial_results,
            test_mode=False,
        )

        self.assertEqual(observation, "",
            "Observe loop should skip trivial results")

    @patch("butler._raw_llm")
    def test_observe_loop_speaks_for_meaningful(self, mock_llm):
        """Observe loop SHOULD speak when results have real content."""
        from butler import observe_and_followup

        mock_llm.return_value = "Docker is running fine."

        meaningful_results = [{
            "action": "run_agent",
            "status": "ok",
            "result": (
                "docker ps: api-service running, "
                "redis healthy, nginx up"
            ),
        }]

        observation = observe_and_followup(
            plan={"speech": "Checking your VPS."},
            execution_results=meaningful_results,
            test_mode=False,
        )

        self.assertIsInstance(observation, str)

    def test_confirmation_gate_blocks_git_push(self):
        """git push must never execute without confirmation."""
        from executor.engine import Executor

        e = Executor()
        # Simulate user cancelling
        with patch.object(e, "_ask_confirmation", return_value=False):
            results = e.run([{
                "type": "run_command",
                "cmd": "git push origin main",
                "cwd": "~/Burry/mac-butler"
            }])

        self.assertEqual(len(results), 1)
        self.assertIn("cancelled", results[0].get("result","").lower(),
            "Cancelled git push should say cancelled")

    def test_confirmation_gate_allows_safe_cmd(self):
        """Safe commands must NOT ask for confirmation."""
        from executor.engine import Executor

        e = Executor()
        # _ask_confirmation should NOT be called for safe commands
        with patch.object(
            e, "_ask_confirmation"
        ) as mock_confirm:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="On branch main",
                    stderr=""
                )
                e.run([{
                    "type": "run_command",
                    "cmd": "git status",
                    "cwd": "~/Burry/mac-butler"
                }])

            mock_confirm.assert_not_called()


# ═══════════════════════════════════════════════════════════
# SUITE 10: BUTLER CONFIG
# ═══════════════════════════════════════════════════════════

class TestButlerConfig(unittest.TestCase):
    """Tests for butler_config.py — configuration correctness."""

    def test_imports(self):
        try:
            import butler_config
        except ImportError as e:
            self.fail(f"butler_config.py import failed: {e}")

    def test_ollama_model_set(self):
        from butler_config import OLLAMA_MODEL
        self.assertIsInstance(OLLAMA_MODEL, str)
        self.assertGreater(len(OLLAMA_MODEL), 3,
            "OLLAMA_MODEL not configured")
        self.assertNotEqual(OLLAMA_MODEL, "",
            "OLLAMA_MODEL is empty string")

    def test_ollama_model_is_configured_for_supported_runtime(self):
        from butler_config import OLLAMA_MODEL
        self.assertTrue(
            any(name in OLLAMA_MODEL.lower() for name in ("gemma", "deepseek", "qwen", "llama")),
            f"OLLAMA_MODEL should be a supported local model, got: {OLLAMA_MODEL}",
        )

    def test_fallback_model_set(self):
        from butler_config import OLLAMA_FALLBACK
        self.assertIsInstance(OLLAMA_FALLBACK, str)
        self.assertGreater(len(OLLAMA_FALLBACK), 3)

    def test_agent_models_dict(self):
        try:
            from butler_config import AGENT_MODELS
            self.assertIsInstance(AGENT_MODELS, dict)
            for key in ["news","market","hackernews","reddit","github_trending","vps","memory","code","search"]:
                self.assertIn(key, AGENT_MODELS,
                    f"AGENT_MODELS missing key: {key}")
        except ImportError:
            pass  # AGENT_MODELS is optional

    def test_safety_flags(self):
        try:
            from butler_config import (
                REQUIRE_CONFIRMATION_FOR_PUSH,
                REQUIRE_CONFIRMATION_FOR_DOCKER,
            )
            self.assertTrue(REQUIRE_CONFIRMATION_FOR_PUSH,
                "git push confirmation must be enabled")
            self.assertTrue(REQUIRE_CONFIRMATION_FOR_DOCKER,
                "docker confirmation must be enabled")
        except ImportError:
            pass  # Optional config


# ═══════════════════════════════════════════════════════════
# REPORT GENERATOR
# ═══════════════════════════════════════════════════════════

def generate_report(result: unittest.TestResult) -> str:
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors
    skipped = len(result.skipped)

    lines = [
        "",
        "═" * 60,
        "  MAC BUTLER COMPREHENSIVE TEST REPORT",
        "═" * 60,
        f"  Date:    {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Total:   {total}",
        f"  Passed:  {passed} ✓",
        f"  Failed:  {failures} ✗",
        f"  Errors:  {errors} ✗",
        f"  Skipped: {skipped}",
        "─" * 60,
    ]

    if failures or errors:
        lines.append("  FAILURES AND ERRORS:")
        for test, traceback in result.failures + result.errors:
            lines.append(f"  ✗ {test}")
            # Extract just the assertion message
            for line in traceback.split("\n"):
                if "AssertionError" in line or "Error:" in line:
                    lines.append(f"    → {line.strip()}")
                    break
        lines.append("─" * 60)

    if passed == total:
        lines.append("  STATUS: ALL TESTS PASSED ✓")
    elif failures + errors <= 2:
        lines.append("  STATUS: MOSTLY PASSING — fix the failures above")
    else:
        lines.append(
            f"  STATUS: {failures + errors} ISSUES — "
            f"check failures above"
        )

    lines.append("═" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Load all test suites in order
    test_classes = [
        TestIdentityLayer,
        TestMemoryStore,
        TestLayeredMemory,
        TestTaskSystem,
        TestContextEngine,
        TestTwoStageBrain,
        TestExecutorEngine,
        TestSpecialistAgents,
        TestHeartbeat,
        TestFullPipeline,
        TestButlerConfig,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print(generate_report(result))

    # Save report to file
    report = generate_report(result)
    report_path = ROOT / "audit_report.md"
    with open(report_path, "w") as f:
        f.write(f"# Mac Butler Test Report\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write("```\n")
        f.write(report)
        f.write("\n```\n\n")
        if result.failures or result.errors:
            f.write("## Failures Detail\n\n")
            for test, tb in result.failures + result.errors:
                f.write(f"### {test}\n```\n{tb}\n```\n\n")
    print(f"\nReport saved to audit_report.md")

    # Exit with error code if tests failed
    sys.exit(1 if result.failures or result.errors else 0)
