"""Environment contract tests: determinism, reward correctness, and the
failure modes the tasks are designed to catch."""

import pytest
from fastapi.testclient import TestClient

from server.app import EPISODES, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_episodes():
    EPISODES.clear()
    yield


def reset(task_id, seed=0, **opts):
    r = client.post(f"/api/{task_id}/reset", json={"seed": seed, **opts})
    assert r.status_code == 200
    return r.json()


def oracle(task_id):
    return client.get(f"/api/{task_id}/state").json()["state"]


def verify(task_id):
    return client.get(f"/api/{task_id}/verify").json()


def act(task_id, payload):
    return client.post(f"/api/{task_id}/action", json=payload)


# Fully seed-deterministic tasks: identical (task, seed) -> identical state,
# and instructions vary across seeds. flash-offer is deliberately excluded —
# its grading is tied to real elapsed time, so it gets its own tests below.
ALL_TASKS = ["email-triage", "settings-panel", "checkout-form", "causal-gate"]
EVERY_TASK = ALL_TASKS + ["flash-offer"]


# ---------------------------------------------------------------- determinism

@pytest.mark.parametrize("task_id", ALL_TASKS)
@pytest.mark.parametrize("seed", [0, 7, 12345])
def test_same_seed_same_episode(task_id, seed):
    first = reset(task_id, seed)
    first_state = oracle(task_id)
    second = reset(task_id, seed)
    assert first["instruction"] == second["instruction"]
    assert first_state == oracle(task_id)


@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_different_seeds_differ(task_id):
    instructions = {reset(task_id, s)["instruction"] for s in range(20)}
    assert len(instructions) > 1


@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_fresh_episode_is_not_solved(task_id):
    reset(task_id, seed=3)
    assert verify(task_id)["success"] is False


def test_task_page_renders():
    for task_id in EVERY_TASK:
        reset(task_id, seed=1)
        r = client.get(f"/task/{task_id}")
        assert r.status_code == 200
        assert "app" in r.text


def test_sessions_are_isolated():
    # two visitors on the same task must not share episode state
    client.post("/api/email-triage/reset?sid=alice", json={"seed": 1})
    client.post("/api/email-triage/reset?sid=bob", json={"seed": 1})
    alice_state = client.get("/api/email-triage/state?sid=alice").json()["state"]
    target = next(e for e in alice_state["emails"]
                  if e["sender"] == alice_state["target_sender"])
    client.post("/api/email-triage/action?sid=alice",
                json={"op": "archive", "id": target["id"]})
    bob_state = client.get("/api/email-triage/state?sid=bob").json()["state"]
    assert not any(e["archived"] for e in bob_state["emails"])
    # and the default (harness) session is untouched by either
    reset("email-triage", seed=1)
    assert verify("email-triage")["success"] is False


def test_landing_and_demo_pages():
    assert "WebTask Arena" in client.get("/").text
    assert client.get("/play").status_code == 200
    # /replays is 200 when assets are bundled, 404 otherwise — both acceptable
    assert client.get("/replays").status_code in (200, 404)


# --------------------------------------------------------------- email triage

def solve_email(task_id="email-triage"):
    state = oracle(task_id)
    for e in state["emails"]:
        if e["sender"] == state["target_sender"]:
            assert act(task_id, {"op": "archive", "id": e["id"]}).status_code == 200
    assert act(task_id, {"op": "star", "id": state["star_target_id"]}).status_code == 200


def test_email_triage_success():
    reset("email-triage", seed=42)
    solve_email()
    result = verify("email-triage")
    assert result["success"] is True, result


def test_email_triage_extra_archive_fails():
    reset("email-triage", seed=42)
    solve_email()
    state = oracle("email-triage")
    extra = next(e for e in state["emails"]
                 if e["sender"] != state["target_sender"] and not e["archived"])
    act("email-triage", {"op": "archive", "id": extra["id"]})
    result = verify("email-triage")
    assert result["success"] is False
    assert result["subgoals"]["no_extra_archived"] is False


def test_email_triage_wrong_star_fails():
    reset("email-triage", seed=42)
    state = oracle("email-triage")
    wrong = next(e for e in state["emails"] if e["id"] != state["star_target_id"])
    act("email-triage", {"op": "star", "id": wrong["id"]})
    assert verify("email-triage")["subgoals"]["starred_target_only"] is False


# ------------------------------------------------------------- settings panel

def test_settings_success():
    reset("settings-panel", seed=9)
    tz = oracle("settings-panel")["target_timezone"]
    r = act("settings-panel", {"op": "save", "draft": {"dark_mode": True, "timezone": tz}})
    assert r.status_code == 200
    assert verify("settings-panel")["success"] is True


def test_settings_unsaved_draft_does_not_count():
    # The trap this task exists for: toggling the UI without saving is failure.
    reset("settings-panel", seed=9)
    assert verify("settings-panel")["subgoals"]["dark_mode_saved"] is False


def test_settings_unrelated_change_fails():
    reset("settings-panel", seed=9)
    tz = oracle("settings-panel")["target_timezone"]
    act("settings-panel", {"op": "save",
                           "draft": {"dark_mode": True, "timezone": tz, "beta_features": True}})
    result = verify("settings-panel")
    assert result["success"] is False
    assert result["subgoals"]["no_unrelated_changes"] is False


# -------------------------------------------------------------- checkout form

def test_checkout_success():
    reset("checkout-form", seed=5)
    exp = oracle("checkout-form")["expected"]
    assert act("checkout-form", {"op": "contact", "name": exp["name"], "email": exp["email"]}).status_code == 200
    assert act("checkout-form", {"op": "shipping", "street": exp["street"],
                                 "city": exp["city"], "zip": exp["zip"]}).status_code == 200
    assert act("checkout-form", {"op": "submit"}).status_code == 200
    assert verify("checkout-form")["success"] is True


def test_checkout_validation_rejects_bad_input():
    reset("checkout-form", seed=5)
    r = act("checkout-form", {"op": "contact", "name": "", "email": "not-an-email"})
    assert r.status_code == 400
    assert set(r.json()["errors"]) == {"name", "email"}

    exp = oracle("checkout-form")["expected"]
    act("checkout-form", {"op": "contact", "name": exp["name"], "email": exp["email"]})
    r = act("checkout-form", {"op": "shipping", "street": exp["street"],
                              "city": exp["city"], "zip": "abc"})
    assert r.status_code == 400
    assert "zip" in r.json()["errors"]


def test_checkout_cannot_skip_steps():
    reset("checkout-form", seed=5)
    assert act("checkout-form", {"op": "submit"}).status_code == 400


def test_checkout_wrong_data_submits_but_fails_verify():
    # Submitting *something* is not success — fields must match the instruction.
    reset("checkout-form", seed=5)
    act("checkout-form", {"op": "contact", "name": "Wrong Person", "email": "wrong@example.com"})
    act("checkout-form", {"op": "shipping", "street": "1 Nowhere St", "city": "Nil", "zip": "00000"})
    act("checkout-form", {"op": "submit"})
    result = verify("checkout-form")
    assert result["subgoals"]["submitted"] is True
    assert result["success"] is False


# --------------------------------------------------------------- causal gate

def test_causal_gate_success():
    reset("causal-gate", seed=3)
    code = oracle("causal-gate")["expected_code"]
    act("causal-gate", {"op": "set_source", "value": "Friend referral"})
    act("causal-gate", {"op": "save", "draft": {"referral_code": code}})
    assert verify("causal-gate")["success"] is True


def test_causal_gate_code_without_source_fails():
    # Typing the right code into the right-shaped field isn't enough — the
    # source selection is the causal precondition, checked independently.
    reset("causal-gate", seed=3)
    code = oracle("causal-gate")["expected_code"]
    act("causal-gate", {"op": "save", "draft": {"referral_code": code}})
    result = verify("causal-gate")
    assert result["success"] is False
    assert result["subgoals"]["referral_code_correct"] is False


def test_causal_gate_only_final_save_counts():
    # Like settings-panel: draft state doesn't matter, only what's true at
    # the moment of the final save (flipping source back and forth is fine).
    reset("causal-gate", seed=3)
    code = oracle("causal-gate")["expected_code"]
    act("causal-gate", {"op": "set_source", "value": "Friend referral"})
    act("causal-gate", {"op": "set_source", "value": "Search engine"})
    act("causal-gate", {"op": "set_source", "value": "Friend referral"})
    act("causal-gate", {"op": "save", "draft": {"referral_code": code}})
    assert verify("causal-gate")["success"] is True


def test_causal_gate_decoy_field_fails():
    # The failure mode this task exists to catch: pattern-matching "code-shaped
    # field near a discount theme" instead of the actual causal precondition.
    reset("causal-gate", seed=3)
    code = oracle("causal-gate")["expected_code"]
    act("causal-gate", {"op": "save", "draft": {"gift_card": code}})
    result = verify("causal-gate")
    assert result["success"] is False
    assert result["subgoals"]["referral_code_correct"] is False
    assert result["subgoals"]["gift_card_untouched"] is False


# -------------------------------------------------------------- flash offer

def test_flash_offer_fresh_not_solved():
    reset("flash-offer", seed=2)
    assert verify("flash-offer")["success"] is False


def test_flash_offer_success_immediately_after_reset():
    # Well under CYCLE_SECONDS after reset, slot 0 is still the current code.
    reset("flash-offer", seed=1)
    codes = oracle("flash-offer")["codes"]
    r = act("flash-offer", {"op": "redeem", "code": codes[0]})
    assert r.status_code == 200
    assert verify("flash-offer")["success"] is True


def test_flash_offer_stale_code_fails():
    reset("flash-offer", seed=1)
    codes = oracle("flash-offer")["codes"]
    act("flash-offer", {"op": "redeem", "code": codes[1]})  # a different slot's code
    result = verify("flash-offer")
    assert result["success"] is False
    assert result["subgoals"]["code_matched_live_value"] is False


def test_flash_offer_codes_deterministic_per_seed():
    # The code *set* is seed-pure even though which one is "current" is not.
    reset("flash-offer", seed=1)
    codes_a = oracle("flash-offer")["codes"]
    reset("flash-offer", seed=1)
    codes_b = oracle("flash-offer")["codes"]
    assert codes_a == codes_b


def test_flash_offer_seeds_pick_different_code_sets():
    sets = set()
    for s in range(20):
        reset("flash-offer", seed=s)
        sets.add(tuple(oracle("flash-offer")["codes"]))
    assert len(sets) > 1
