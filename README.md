---
title: WebTask Arena
emoji: 🕹️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Deterministic, server-graded web tasks for GUI agents
---

# WebTask Arena

A controlled environment for studying **where GUI agents fail**.

> **Live demo:** this repo also runs as a Hugging Face Space —
> [xiningli/webtask-arena](https://huggingface.co/spaces/xiningli/webtask-arena) —
> with a **replay player** (step through recorded UI-TARS episodes: every
> screenshot, action, and model thought next to the server's verdict) and a
> **"beat the agent" mode** (play the same seeded episode yourself and get
> graded by the same oracle, subgoal by subgoal).

WebTask Arena is a set of deterministic, resettable, self-contained web tasks
with server-side reward functions, built for evaluating computer-use agents
(UI-TARS, Qwen2.5-VL, Claude computer use, ...) under conditions you can
actually reproduce: fixed seeds, versioned task logic, and no external
network dependencies.

## Why another environment?

Agent evaluations are noisy. Public benchmarks like OSWorld and WebArena are
invaluable for coverage, but hard to use for *controlled* failure analysis:
tasks depend on real software versions, rewards are sometimes brittle, and
runs are expensive. WebTask Arena takes the opposite trade-off — a small
number of fully-owned tasks where:

- **Every episode is seed-deterministic.** `POST /api/email-triage/reset
  {"seed": 42}` produces byte-identical state, instruction, and page, every
  time, on every machine.
- **Reward is computed server-side from ground-truth state**, never scraped
  from the DOM. The agent can't fool the grader, and neither can a flaky
  selector.
- **Success is decomposed into named subgoals** (`archived_all_from_target`,
  `no_extra_archived`, ...), so a failed episode tells you *which* capability
  broke, not just that one did.
- **Adversarial rendering is a flag, not a fork.** Every task can be run with
  artificial load latency (`latency_ms`) and delayed layout shift
  (`layout_shift`) to measure how much of an agent's success rate is an
  artifact of stable, instant pages.
- **Hermetic by construction.** No CDNs, no fonts, no analytics, no external
  requests. The container is the whole world.

## Tasks (v0)

| Task | Skills probed | Traps |
|---|---|---|
| `email-triage` | list scanning, per-row actions, precision | extra archives fail; star exactly one |
| `settings-panel` | navigation across sections, toggles, selects | draft changes don't count until **Save**; unrelated changes fail |
| `checkout-form` | multi-step forms, validation-error recovery | submitting wrong data "succeeds" in the UI but fails verification |

## Quickstart

```bash
docker compose up --build
# open http://localhost:8000
```

Drive an episode:

```bash
# start a fresh, seeded episode (optionally with adversarial rendering)
curl -X POST localhost:8000/api/email-triage/reset \
  -H 'Content-Type: application/json' \
  -d '{"seed": 42, "latency_ms": 800, "layout_shift": true}'
# -> {"task_id": "email-triage", "seed": 42, "instruction": "In the inbox, archive every email from ..."}

# ...point your agent at http://localhost:8000/task/email-triage ...

# grade the episode
curl localhost:8000/api/email-triage/verify
# -> {"success": false, "subgoals": {"archived_all_from_target": false, ...}}
```

`/api/*/verify` and `/api/*/state` are **oracle endpoints for the harness** —
never expose them to the agent under evaluation.

One episode per task per container; parallelize batch evals by running
multiple containers.

## Harness

The harness drives real browser episodes with Playwright: screenshot in,
[computer-use-style action](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
out (`left_click` at pixel coordinates, `type`, `key`, `scroll`, ...), executed
against a fixed 1280×800 viewport. Every episode records `step_NNN.png`,
`actions.jsonl`, and `result.json` with per-subgoal outcomes.

```bash
pip install -r requirements-dev.txt && playwright install chromium
uvicorn server.app:app &

# self-test: the scripted oracle agent exercises the full pipeline
python -m harness.run --agent scripted --task all --seeds 0-4

# same tasks under adversarial rendering
python -m harness.run --agent scripted --task all --seeds 0-4 \
    --latency-ms 800 --layout-shift

# Claude computer-use adapter (needs ANTHROPIC_API_KEY + pip install anthropic)
python -m harness.run --agent claude --task all --seeds 0-4
```

The **scripted agent** is a DOM-oracle reference implementation: it parses the
natural-language instruction and emits ordinary click/type/key actions, but
locates targets via the DOM. It exists to validate the pipeline (env →
screenshots → executor → server state → verify), not as a baseline — model
adapters never get DOM access. It passes 3/3 tasks across seeds under both
clean and adversarial rendering.

## Development

```bash
pip install -r requirements-dev.txt
pytest            # determinism + reward contract tests
uvicorn server.app:app --reload
```

Adding a task: implement the `Task` protocol (`server/registry.py`) — a
seeded `generate`, an `instruction`, UI action handlers, and a `verify` that
returns named subgoals — then register it. The contract tests in
`tests/test_environment.py` are parametrized over the registry.

## Roadmap

- [x] Playwright harness: screenshot loop, agent adapter interface, trajectory recording
- [x] Claude computer-use adapter (`computer_20251124`)
- [x] UI-TARS-1.5-7B evaluated against the arena — see
      [uitars-webtask-eval](https://github.com/xiningli/uitars-webtask-eval)
      (1/3 pass at seed 0, with a diagnosed state-tracking failure and an
      environment finding about native `<select>` under headless rendering)
- [ ] Qwen2.5-VL adapter; port the UI-TARS adapter into `harness/agents/`
- [ ] pass@1 / pass^k reporting with per-subgoal breakdowns across repeated seeds
- [ ] Failure taxonomy: grounding misclicks vs. perception errors vs. planning loops vs. premature termination
- [ ] More tasks: drag-to-reorder, infinite-scroll search, modal interruptions

## Related work

- [UI-TARS / UI-TARS-2](https://github.com/bytedance/UI-TARS) — native GUI agent models (ByteDance)
- [OSWorld](https://os-world.github.io/) — real-OS benchmark for multimodal agents
- [WebArena](https://webarena.dev/) / VisualWebArena — realistic self-hosted web benchmarks
- [ScreenSpot](https://github.com/njucckevin/SeeClick) — GUI grounding evaluation
- [Anthropic computer use](https://docs.anthropic.com/en/docs/agents-and-tools/computer-use) — reference agent loop

## License

MIT
