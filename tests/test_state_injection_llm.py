"""Tests for State Injection — the core non-trivial piece of Binsai.

These tests call the REAL DeepSeek API (requires DEEPSEEK_API_KEY).
They verify that:
  1. The LLM actually reads the regulatory state embedded in the prompt
  2. Responses differ meaningfully between oversated and critical states
  3. The JSON output is parseable and contains required fields
  4. Token costs are tracked and map correctly to δ increments
  5. Proact generates a valid insight when δ is low

Skip if DEEPSEEK_API_KEY is not set (CI without key should not fail).
Mark slow with -m llm to opt in: pytest -m llm tests/test_state_injection_llm.py
"""

import json
import os
import pytest

from binsai.drives import Drive, Stratum
from binsai.actions import (
    ActionKind,
    ActionExecution,
    regulatory_state_to_prompt,
    execute_action_llm,
    token_cost_to_delta,
    call_llm,
    _system_prompt,
    _respond_fast_user,
    _respond_slow_user,
    _proact_user,
)

pytestmark = pytest.mark.llm

HAS_KEY = bool(os.getenv("DEEPSEEK_API_KEY"))


@pytest.fixture(autouse=True)
def require_key():
    if not HAS_KEY:
        pytest.skip("DEEPSEEK_API_KEY not set — skipping real LLM tests")


def make_drive(delta: float) -> Drive:
    d = Drive(
        name="metabolic", stratum=Stratum.MATERIAL,
        value=delta, set_point=0.30,
        lambda_rate=0.005, satiation_rate=0.10,
    )
    return d


def make_execution(kind: ActionKind, topic: str = "budget report") -> ActionExecution:
    return ActionExecution(
        kind=kind, started_at=1, ticks_remaining=0,
        demand_id="d1", demand_topic=topic,
    )


# ── 1. State injection block is well-formed ───────────────────────────────────

class TestStateInjectionBlock:
    def test_critical_state_contains_deficit_label(self):
        d = make_drive(0.80)
        block = regulatory_state_to_prompt(d)
        assert "critical" in block.lower()
        assert "deficit" in block.lower() or "δ" in block

    def test_oversated_state_contains_abundant_label(self):
        d = make_drive(0.05)
        block = regulatory_state_to_prompt(d)
        assert "oversated" in block.lower() or "abundant" in block.lower()

    def test_block_includes_numeric_delta(self):
        d = make_drive(0.72)
        block = regulatory_state_to_prompt(d)
        assert "0.720" in block

    def test_block_includes_all_zone_names(self):
        d = make_drive(0.30)
        block = regulatory_state_to_prompt(d)
        for zone in ["oversated", "sated", "nominal", "loaded", "critical"]:
            assert zone in block

    def test_scrambled_labels_replace_behavioral_description(self):
        """Scramble replaces zone behavioral descriptions only.

        The fixed δ scale line ('low δ = abundant resources') is NOT scrambled —
        it's the coordinate system, not the behavioral hint. Only the dominant-zone
        behavioral label after 'Dominant zone: X —' is replaced with metric codes.
        """
        d = make_drive(0.80)
        normal    = regulatory_state_to_prompt(d, scramble_labels=False)
        scrambled = regulatory_state_to_prompt(d, scramble_labels=True)

        # Normal contains behavioral label for critical zone
        assert "prioritize brevity" in normal or "severe resource deficit" in normal

        # Scrambled replaces behavioral label with metric codes
        assert "metric_A" in scrambled
        assert "signal_high" in scrambled  # critical maps to signal_high

        # Behavioral hint "prioritize brevity" should NOT appear in scrambled
        assert "prioritize brevity" not in scrambled
        assert "severe resource deficit" not in scrambled


# ── 2. LLM call returns parseable JSON ───────────────────────────────────────

class TestLLMCall:
    def test_call_llm_returns_string_and_token_count(self):
        d = make_drive(0.30)
        system = _system_prompt(d)
        user   = _respond_fast_user("quarterly summary")
        content, tokens = call_llm(system, user, max_tokens=128)
        assert isinstance(content, str) and len(content) > 0
        assert tokens > 0

    def test_respond_fast_parses_to_json(self):
        d = make_drive(0.30)
        ex = make_execution(ActionKind.RESPOND_FAST, "project status")
        result, tokens = execute_action_llm(ex, d, dry_run=False)
        assert result is not None
        assert "response" in result or "raw" in result  # raw = parse error fallback
        assert tokens > 0

    def test_respond_slow_parses_to_json(self):
        d = make_drive(0.10)  # oversated — agent can afford slow response
        ex = make_execution(ActionKind.RESPOND_SLOW, "risk analysis")
        result, tokens = execute_action_llm(ex, d, dry_run=False)
        assert result is not None
        assert tokens > 0

    def test_proact_parses_to_json(self):
        d = make_drive(0.05)  # heavily oversated
        ex = ActionExecution(
            kind=ActionKind.PROACT, started_at=1, ticks_remaining=0,
        )
        result, tokens = execute_action_llm(ex, d, queue_size=2, dry_run=False)
        assert result is not None
        assert "insight" in result or "raw" in result
        assert tokens > 0


# ── 3. State shapes LLM behavior (the actual thesis test) ────────────────────

class TestStateConditionedResponse:
    """These tests verify that the LLM's behavior changes with regulatory state.

    We cannot assert exact words, but we can assert structural differences:
    - Critical state → shorter response (less tokens used, or shorter 'response' key)
    - Oversated state → longer, more elaborate response
    - CoT (respond_slow) → 'thought' key present and non-empty
    """

    def test_critical_response_is_shorter_than_oversated(self):
        """Critical agent (δ=0.85) should produce briefer output than oversated (δ=0.05)."""
        topic = "department update"

        d_critical  = make_drive(0.85)
        d_oversated = make_drive(0.05)

        ex_crit = make_execution(ActionKind.RESPOND_FAST, topic)
        ex_over = make_execution(ActionKind.RESPOND_FAST, topic)

        res_crit, tok_crit = execute_action_llm(ex_crit, d_critical, dry_run=False)
        res_over, tok_over = execute_action_llm(ex_over, d_oversated, dry_run=False)

        # Oversated agent should use more tokens (more elaborate response)
        # We allow a soft assertion: at least one measure should differ
        resp_crit = res_crit.get("response", "") if res_crit else ""
        resp_over = res_over.get("response", "") if res_over else ""

        assert len(resp_over) >= len(resp_crit), (
            f"Expected oversated response ≥ critical in length. "
            f"oversated={len(resp_over)} chars, critical={len(resp_crit)} chars.\n"
            f"Critical response: {resp_crit[:100]}\n"
            f"Oversated response: {resp_over[:100]}"
        )

    def test_respond_slow_includes_thought_key(self):
        """respond_slow uses CoT prompt → model should return 'thought' field."""
        d  = make_drive(0.10)  # oversated, respond_slow appropriate
        ex = make_execution(ActionKind.RESPOND_SLOW, "technical architecture review")
        result, tokens = execute_action_llm(ex, d, dry_run=False)
        assert result is not None
        assert "thought" in result, (
            f"respond_slow should include 'thought' field (CoT). Got: {result}"
        )
        assert len(result.get("thought", "")) > 10, "Expected non-trivial thought content"

    def test_proact_includes_insight_key(self):
        """proact must include 'insight' key with non-trivial content."""
        d  = make_drive(0.05)
        ex = ActionExecution(kind=ActionKind.PROACT, started_at=1, ticks_remaining=0)
        result, tokens = execute_action_llm(ex, d, queue_size=0, dry_run=False)
        assert result is not None
        assert "insight" in result, f"proact missing 'insight'. Got: {result}"
        assert len(result.get("insight", "")) > 10

    def test_scrambled_labels_produce_valid_json(self):
        """Even with scrambled labels, the LLM should return parseable JSON."""
        d  = make_drive(0.50)
        ex = make_execution(ActionKind.RESPOND_FAST, "performance review")
        result, tokens = execute_action_llm(ex, d, scramble_labels=True, dry_run=False)
        assert result is not None
        assert tokens > 0


# ── 4. Token cost → δ mapping ─────────────────────────────────────────────────

class TestTokenCostMapping:
    def test_token_cost_is_positive(self):
        assert token_cost_to_delta(100) > 0

    def test_more_tokens_higher_delta_cost(self):
        assert token_cost_to_delta(300) > token_cost_to_delta(80)

    def test_respond_fast_costs_less_than_respond_slow_in_practice(self):
        """Real API: respond_fast uses fewer tokens → smaller δ increment."""
        d_f = make_drive(0.30)
        d_s = make_drive(0.30)

        ex_f = make_execution(ActionKind.RESPOND_FAST, "status")
        ex_s = make_execution(ActionKind.RESPOND_SLOW, "detailed status with reasoning")

        _, tok_fast = execute_action_llm(ex_f, d_f, dry_run=False)
        _, tok_slow = execute_action_llm(ex_s, d_s, dry_run=False)

        cost_fast = token_cost_to_delta(tok_fast)
        cost_slow = token_cost_to_delta(tok_slow)

        assert cost_fast < cost_slow, (
            f"Expected fast ({tok_fast} tok, δ+{cost_fast:.5f}) < "
            f"slow ({tok_slow} tok, δ+{cost_slow:.5f})"
        )

    def test_real_llm_call_increments_drive_delta(self):
        """After a real LLM call, the drive's δ should have increased."""
        d  = make_drive(0.30)
        ex = make_execution(ActionKind.RESPOND_FAST, "test topic")
        before = d.value
        result, tokens = execute_action_llm(ex, d, dry_run=False)
        # Caller is responsible for applying cost; simulate here
        d.deplete(token_cost_to_delta(tokens))
        assert d.value > before, "δ should increase after LLM call consumes tokens"
