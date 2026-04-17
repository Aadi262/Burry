import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "benchmark_models.py"
SPEC = importlib.util.spec_from_file_location("benchmark_models", MODULE_PATH)
benchmark_models = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark_models)


class ModelBenchmarkTests(unittest.TestCase):
    @patch.object(benchmark_models, "_provider_ready", return_value=True)
    @patch.object(benchmark_models, "pick_agent_model", return_value="nvidia::qwen/qwen2.5-coder-32b-instruct")
    @patch.object(benchmark_models, "pick_butler_model", return_value="nvidia::nvidia/nvidia-nemotron-nano-9b-v2")
    def test_run_benchmarks_dry_run_reports_selected_models(
        self,
        _mock_butler_model,
        _mock_agent_model,
        _mock_provider_ready,
    ):
        report = benchmark_models.run_benchmarks(
            case_names=["voice_brief", "github_status_agent"],
            execute=False,
        )

        self.assertTrue(report["nvidia_ready"])
        self.assertEqual(report["case_count"], 2)
        self.assertFalse(report["executed"])
        self.assertEqual(report["summary"]["error"], 0)
        self.assertEqual(report["results"][0]["status"], "planned")
        self.assertTrue(all(item["chain"] for item in report["results"]))

    @patch.object(benchmark_models, "_provider_ready", return_value=False)
    @patch.object(benchmark_models, "pick_butler_model", return_value="ollama_local::gemma4:e4b")
    @patch.object(benchmark_models, "_call", return_value="Latency looks reasonable and the routing stayed local.")
    @patch.object(benchmark_models.time, "perf_counter", side_effect=[1.0, 1.25, 2.0, 2.3])
    def test_run_benchmarks_executes_case_and_reports_latency(
        self,
        _mock_perf_counter,
        _mock_call,
        _mock_pick_model,
        _mock_provider_ready,
    ):
        report = benchmark_models.run_benchmarks(
            case_names=["voice_brief"],
            iterations=2,
            execute=True,
        )

        self.assertFalse(report["nvidia_ready"])
        self.assertEqual(report["summary"]["ok"], 1)
        self.assertEqual(report["summary"]["error"], 0)
        result = report["results"][0]
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["latencies_s"], [0.25, 0.3])
        self.assertEqual(result["avg_latency_s"], 0.275)
        self.assertIn("routing stayed local", result["response_excerpt"])


if __name__ == "__main__":
    unittest.main()
