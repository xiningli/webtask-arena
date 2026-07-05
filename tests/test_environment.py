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


ALL_TASKS = ["email-triage", "settings-panel", "checkout-form"]


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
    for task_id in ALL_TASKS:
        reset(task_id, seed=1)
        r = client.get(f"/task/{task_id}")
        assert r.status_code == 200
        assert "app" in r.text


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
