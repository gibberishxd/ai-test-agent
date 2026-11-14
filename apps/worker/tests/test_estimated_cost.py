"""Run 6, L1: the API-equivalent cost is stored per step and run and is what budgets use."""

from worker.config import Settings
from worker.db.models import Run
from worker.execute import add_usage, over_budget, remaining_budget, usage_fields
from worker.llm import Usage

CLI_CALL = Usage(
    model="claude-sonnet-5-5",
    input_tokens=10,
    output_tokens=200,
    cache_read_tokens=12_000,
    cache_write_tokens=3_000,
    cache_write_1h_tokens=3_000,
    cost_usd=0.0,
    estimated_cost_usd=0.0165,
)


def fresh_run() -> Run:
    return Run(
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        estimated_cost_usd=0.0,
    )


def test_a_step_stores_the_reported_model_every_token_type_and_both_costs():
    fields = usage_fields(CLI_CALL)
    assert fields["model"] == "claude-sonnet-5-5"
    assert fields["input_tokens"] == 10 + 12_000 + 3_000  # every input token, as before
    assert (fields["cache_read_tokens"], fields["cache_write_tokens"]) == (12_000, 3_000)
    assert fields["output_tokens"] == 200
    assert fields["cost_usd"] == 0.0
    assert fields["estimated_cost_usd"] == 0.0165


def test_a_charged_call_is_its_own_estimate():
    paid = Usage(model="claude-sonnet-5-5", input_tokens=1000, cost_usd=0.002)
    assert usage_fields(paid)["estimated_cost_usd"] == 0.002


def test_the_run_sums_the_cache_tokens_and_the_estimate():
    run = fresh_run()
    add_usage(run, CLI_CALL)
    add_usage(run, CLI_CALL)
    assert run.cache_read_tokens == 24_000 and run.cache_write_tokens == 6_000
    assert run.estimated_cost_usd == 0.033 and run.cost_usd == 0.0


def test_the_run_budget_is_spent_by_the_estimate_not_only_the_charge():
    settings = Settings(_env_file=None, max_run_cost_usd=0.03)
    run = fresh_run()
    add_usage(run, CLI_CALL)
    assert not over_budget(settings, run)
    assert remaining_budget(settings, run) == 0.03 - 0.0165
    add_usage(run, CLI_CALL)
    assert over_budget(settings, run)
    assert remaining_budget(settings, run) == 0


def test_pending_usage_counts_before_it_is_stored():
    settings = Settings(_env_file=None, max_run_cost_usd=0.02)
    assert over_budget(settings, fresh_run(), pending=[CLI_CALL, CLI_CALL])
