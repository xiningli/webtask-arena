"""WebTask Arena — deterministic, resettable web environments for GUI agents.

Episode lifecycle (driven by the harness, out-of-band from the agent):

    POST /api/{task_id}/reset   {"seed": 42, "latency_ms": 0, "layout_shift": false}
        -> {"task_id", "seed", "instruction"}
    ...agent interacts with GET /task/{task_id} through the browser...
    GET  /api/{task_id}/verify
        -> {"success": bool, "subgoals": {name: bool}}

`/api/*/verify` and `/api/*/state` are oracle endpoints for the harness and
must never be exposed to the agent under evaluation.

One episode per task per container; run containers in parallel for batch evals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from .registry import TASKS

app = FastAPI(title="WebTask Arena")

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

# task_id -> {"state": ..., "seed": ..., "opts": ..., "instruction": ...}
EPISODES: dict[str, dict[str, Any]] = {}

DEFAULT_OPTS = {"latency_ms": 0, "layout_shift": False}


class ResetRequest(BaseModel):
    seed: int = 0
    latency_ms: int = 0
    layout_shift: bool = False


def _episode(task_id: str) -> dict[str, Any]:
    if task_id not in TASKS:
        raise HTTPException(404, f"unknown task '{task_id}'")
    if task_id not in EPISODES:
        _do_reset(task_id, ResetRequest())  # default episode: seed 0, no adversarial opts
    return EPISODES[task_id]


def _do_reset(task_id: str, req: ResetRequest) -> dict[str, Any]:
    task = TASKS[task_id]
    state = task.generate(req.seed)
    EPISODES[task_id] = {
        "state": state,
        "seed": req.seed,
        "opts": {"latency_ms": req.latency_ms, "layout_shift": req.layout_shift},
        "instruction": task.instruction(state),
    }
    return EPISODES[task_id]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    tmpl = _templates.get_template("index.html")
    return tmpl.render(tasks=[(t.id, t.title) for t in TASKS.values()])


@app.get("/task/{task_id}", response_class=HTMLResponse)
def task_page(task_id: str) -> str:
    ep = _episode(task_id)
    task = TASKS[task_id]
    tmpl = _templates.get_template(task.template)
    opts = dict(ep["opts"], task_id=task_id)
    return tmpl.render(
        title=task.title,
        opts_json=json.dumps(opts),
        **task.view(ep["state"]),
    )


@app.post("/api/{task_id}/reset")
def reset(task_id: str, req: ResetRequest) -> dict[str, Any]:
    if task_id not in TASKS:
        raise HTTPException(404, f"unknown task '{task_id}'")
    ep = _do_reset(task_id, req)
    return {"task_id": task_id, "seed": ep["seed"], "instruction": ep["instruction"]}


@app.get("/api/{task_id}/instruction")
def instruction(task_id: str) -> dict[str, str]:
    return {"instruction": _episode(task_id)["instruction"]}


@app.post("/api/{task_id}/action")
async def action(task_id: str, request: Request) -> JSONResponse:
    ep = _episode(task_id)
    payload = await request.json()
    result = TASKS[task_id].handle_action(ep["state"], payload)
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


@app.get("/api/{task_id}/verify")
def verify(task_id: str) -> dict[str, Any]:
    ep = _episode(task_id)
    subgoals = TASKS[task_id].verify(ep["state"])
    return {"success": all(subgoals.values()), "subgoals": subgoals}


@app.get("/api/{task_id}/state")
def state(task_id: str) -> dict[str, Any]:
    """Oracle/debug view of raw episode state. Not for agent consumption."""
    ep = _episode(task_id)
    return {"seed": ep["seed"], "opts": ep["opts"], "state": ep["state"]}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
