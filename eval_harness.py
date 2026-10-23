"""
Evaluation Benchmark Harness for TracePilot.
Executes quantitative diagnostic evaluations across seeded distributed incident scenarios,
measuring root-cause localization accuracy (Precision/Recall/F1), MTTD reduction,
token consumption, and end-to-end latency.
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.workflow.engine import InvestigationEngine
from app.schemas.incidents import IncidentCreate, Severity


class BenchmarkScenario(BaseModel):
    """Definition of a ground-truth incident evaluation scenario."""
    scenario_id: str
    name: str
    category: str
    incident: IncidentCreate
    ground_truth_root_cause: str
    expected_correlation_chain: List[str]
    human_baseline_mttd_minutes: float


class ScenarioEvaluationResult(BaseModel):
    """Quantitative results from executing a benchmark scenario."""
    scenario_id: str
    name: str
    category: str
    ground_truth_root_cause: str
    predicted_root_cause: str
    is_correct: bool
    confidence_score: float
    tracepilot_mttd_seconds: float
    human_baseline_mttd_minutes: float
    mttd_reduction_pct: float
    estimated_tokens_used: int
    tool_calls_count: int
    execution_trace_steps: int


class BenchmarkSuiteResult(BaseModel):
    """Aggregate benchmark metrics across all test scenarios."""
    total_scenarios: int
    correct_localizations: int
    precision: float
    recall: float
    f1_score: float
    average_tracepilot_mttd_seconds: float
    average_human_baseline_mttd_minutes: float
    average_mttd_reduction_pct: float
    average_confidence_score: float
    total_tokens_consumed: int
    scenario_results: List[ScenarioEvaluationResult] = Field(default_factory=list)


# Pre-seeded Ground Truth Incident Scenarios
BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    BenchmarkScenario(
        scenario_id="SCENARIO-01-BANK-504",
        name="External Payment Gateway 504 Gateway Timeout Cascade",
        category="Third-Party Latency Cascade",
        incident=IncidentCreate(
            title="High Latency & 504 Gateway Timeouts in European Checkout",
            description="Checkout requests timing out when calling downstream payment processing. Cascading 504 errors.",
            severity=Severity.P0,
            affected_service="checkout-service",
            environment="production",
        ),
        ground_truth_root_cause="bank-gateway",
        expected_correlation_chain=["checkout-service", "payment-service", "bank-gateway"],
        human_baseline_mttd_minutes=38.5,
    ),
    BenchmarkScenario(
        scenario_id="SCENARIO-02-REDIS-LEAK",
        name="Inventory Service Redis Connection Pool Starvation",
        category="State Store Resource Exhaustion",
        incident=IncidentCreate(
            title="Redis Connection Exhaustion & Stock Check Failures",
            description="Inventory service failing to acquire Redis connections during flash-sale catalog lookup.",
            severity=Severity.P1,
            affected_service="inventory-service",
            environment="production",
        ),
        ground_truth_root_cause="inventory-service",
        expected_correlation_chain=["inventory-service"],
        human_baseline_mttd_minutes=45.0,
    ),
    BenchmarkScenario(
        scenario_id="SCENARIO-03-DB-DEADLOCK",
        name="Pricing Service Postgres Lock Inversion Deadlock",
        category="Database Concurrency Lock Contention",
        incident=IncidentCreate(
            title="Postgres Transaction Deadlock on Concurrent Bulk Promotions",
            description="Pricing updates locking catalog rows in conflicting orders, throwing transaction rollback errors.",
            severity=Severity.P1,
            affected_service="pricing-service",
            environment="production",
        ),
        ground_truth_root_cause="pricing-service",
        expected_correlation_chain=["pricing-service"],
        human_baseline_mttd_minutes=42.0,
    ),
]


class EvaluationHarness:
    """Automated benchmark harness for AI incident diagnosis."""

    def __init__(self, scenarios: Optional[List[BenchmarkScenario]] = None):
        self.scenarios = scenarios or BENCHMARK_SCENARIOS
        self.engine = InvestigationEngine()

    def run_scenario(self, scenario: BenchmarkScenario) -> ScenarioEvaluationResult:
        """Executes diagnostic agent on a single scenario and scores its output."""
        start_time = time.time()

        state = self.engine.run_investigation(
            incident_id=f"EVAL-{scenario.scenario_id}",
            title=scenario.incident.title,
            description=scenario.incident.description,
            affected_service=scenario.incident.affected_service,
            severity=scenario.incident.severity.value if hasattr(scenario.incident.severity, "value") else str(scenario.incident.severity),
            environment=scenario.incident.environment,
        )

        elapsed_seconds = round(time.time() - start_time, 2)
        report = state.get("final_report")

        predicted_culprit = report.root_cause_service if report else "UNKNOWN"
        is_correct = predicted_culprit.lower() == scenario.ground_truth_root_cause.lower()
        confidence = report.confidence_score if report else 0.0

        # Calculate MTTD Reduction percentage against human baseline
        baseline_seconds = scenario.human_baseline_mttd_minutes * 60.0
        mttd_reduction = round(((baseline_seconds - elapsed_seconds) / baseline_seconds) * 100.0, 2)

        # Estimate tokens and tool calls
        trace_steps = len(state.get("execution_trace", []))
        tool_calls = len(state.get("evidence_cards", []))
        est_tokens = 850 + (tool_calls * 320) + (trace_steps * 110)

        return ScenarioEvaluationResult(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            category=scenario.category,
            ground_truth_root_cause=scenario.ground_truth_root_cause,
            predicted_root_cause=predicted_culprit,
            is_correct=is_correct,
            confidence_score=confidence,
            tracepilot_mttd_seconds=elapsed_seconds,
            human_baseline_mttd_minutes=scenario.human_baseline_mttd_minutes,
            mttd_reduction_pct=mttd_reduction,
            estimated_tokens_used=est_tokens,
            tool_calls_count=tool_calls,
            execution_trace_steps=trace_steps,
        )

    def run_suite(self) -> BenchmarkSuiteResult:
        """Executes the full evaluation benchmark suite and aggregates metrics."""
        results: List[ScenarioEvaluationResult] = []

        for scenario in self.scenarios:
            res = self.run_scenario(scenario)
            results.append(res)

        total = len(results)
        correct = sum(1 for r in results if r.is_correct)

        # Accuracy & Precision/Recall
        precision = round(correct / total, 3) if total > 0 else 0.0
        recall = precision  # Closed ground-truth multi-class evaluation
        f1 = precision

        avg_mttd_sec = round(sum(r.tracepilot_mttd_seconds for r in results) / total, 2)
        avg_base_min = round(sum(r.human_baseline_mttd_minutes for r in results) / total, 2)
        avg_reduct = round(sum(r.mttd_reduction_pct for r in results) / total, 2)
        avg_conf = round(sum(r.confidence_score for r in results) / total, 3)
        total_toks = sum(r.estimated_tokens_used for r in results)

        suite_res = BenchmarkSuiteResult(
            total_scenarios=total,
            correct_localizations=correct,
            precision=precision,
            recall=recall,
            f1_score=f1,
            average_tracepilot_mttd_seconds=avg_mttd_sec,
            average_human_baseline_mttd_minutes=avg_base_min,
            average_mttd_reduction_pct=avg_reduct,
            average_confidence_score=avg_conf,
            total_tokens_consumed=total_toks,
            scenario_results=results,
        )

        # Save to disk
        out_file = ROOT_DIR / "data" / "eval_benchmark_results.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(suite_res.model_dump(), f, indent=2)

        return suite_res


def print_benchmark_report(suite: BenchmarkSuiteResult):
    """Prints a formatted evaluation report in the console."""
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    print(f"\n{CYAN}{BOLD}=============================================================================={RESET}")
    print(f"{CYAN}{BOLD}               TRACEPILOT QUANTITATIVE AI EVALUATION BENCHMARK{RESET}")
    print(f"{CYAN}{BOLD}=============================================================================={RESET}\n")

    print(f"  {BOLD}Benchmark Summary:{RESET}")
    print(f"    • Scenarios Evaluated:         {BOLD}{suite.total_scenarios}{RESET}")
    print(f"    • Root-Cause Accuracy:         {GREEN}{BOLD}{suite.precision * 100:.1f}% ({suite.correct_localizations}/{suite.total_scenarios} Correct){RESET}")
    print(f"    • Precision / Recall / F1:     {GREEN}{BOLD}{suite.f1_score:.3f}{RESET}")
    print(f"    • Mean TracePilot MTTD:        {CYAN}{BOLD}{suite.average_tracepilot_mttd_seconds:.2f}s{RESET}")
    print(f"    • Mean Human SRE Baseline:     {YELLOW}{suite.average_human_baseline_mttd_minutes:.1f} minutes{RESET}")
    print(f"    • Simulated MTTD Reduction:    {GREEN}{BOLD}{suite.average_mttd_reduction_pct:.1f}% Reduction{RESET}")
    print(f"    • Mean Diagnostic Confidence:  {BOLD}{suite.average_confidence_score * 100:.1f}%{RESET}")
    print(f"    • Total Token Consumption:     {suite.total_tokens_consumed} tokens")

    print(f"\n  {BOLD}Scenario Breakdown:{RESET}")
    for r in suite.scenario_results:
        status_icon = f"{GREEN}[PASS]{RESET}" if r.is_correct else f"{RED}[FAIL]{RESET}"
        print(f"    {status_icon} {BOLD}{r.scenario_id}{RESET}: {r.name}")
        print(f"         Expected: {CYAN}{r.ground_truth_root_cause}{RESET} | Predicted: {GREEN if r.is_correct else RED}{r.predicted_root_cause}{RESET} (Conf: {r.confidence_score*100:.0f}%)")
        print(f"         MTTD: {r.tracepilot_mttd_seconds}s vs Baseline {r.human_baseline_mttd_minutes}m ({GREEN}{r.mttd_reduction_pct}% faster{RESET}) | Tokens: {r.estimated_tokens_used}")

    print(f"\n{CYAN}{BOLD}=============================================================================={RESET}\n")


if __name__ == "__main__":
    harness = EvaluationHarness()
    results = harness.run_suite()
    print_benchmark_report(results)
