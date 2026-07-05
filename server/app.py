"""WebTask Arena — deterministic, resettable web environments for GUI agents.

Episode lifecycle (driven by the harness, out-of-band from the agent):

    POST /api/{task_id}/reset   {"seed": 42, "latency_ms": 0, "layout_shift": false}
        -> {"task_id", "seed", "instruction"}
    ...agent interacts with GET /task/{task_id} through the browser...
    GET  /api/{task_id}/verify
        -> {"success": bool, "subgoals": {name: bool}}

`/api/*/verify` and `/api/*/state` are oracle endpoints for the harness and
must never be exposed to the agent under evaluation.

Episodes are scoped by an optional `?sid=<session>` query parameter on every
task/API route. Without it everything lives in the `default` session — the
original single-episode-per-task behavior harnesses rely on. Interactive
pages (/play) mint a random sid per visitor so concurrent humans don't stomp
on each other's episodes. Sessions are LRU-capped for public deployments.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from .registry import TASKS

app = FastAPI(title="WebTask Arena")

_STATIC = Path(__file__).parent / "static"
_STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

# (sid, task_id) -> {"state": ..., "seed": ..., "opts": ..., "instruction": ...}
EPISODES: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
MAX_EPISODES = 512  # LRU cap for public deployments

DEFAULT_OPTS = {"latency_ms": 0, "layout_shift": False}


class ResetRequest(BaseModel):
    seed: int = 0
    latency_ms: int = 0
    layout_shift: bool = False


def _sid(request: Request) -> str:
    sid = request.query_params.get("sid", "default")
    return sid[:64] if sid else "default"


def _episode(sid: str, task_id: str) -> dict[str, Any]:
    if task_id not in TASKS:
        raise HTTPException(404, f"unknown task '{task_id}'")
    key = (sid, task_id)
    if key not in EPISODES:
        _do_reset(sid, task_id, ResetRequest())  # default: seed 0, no adversarial opts
    EPISODES.move_to_end(key)
    return EPISODES[key]


def _do_reset(sid: str, task_id: str, req: ResetRequest) -> dict[str, Any]:
    task = TASKS[task_id]
    state = task.generate(req.seed)
    EPISODES[(sid, task_id)] = {
        "state": state,
        "seed": req.seed,
        "opts": {"latency_ms": req.latency_ms, "layout_shift": req.layout_shift},
        "instruction": task.instruction(state),
    }
    EPISODES.move_to_end((sid, task_id))
    while len(EPISODES) > MAX_EPISODES:
        EPISODES.popitem(last=False)
    return EPISODES[(sid, task_id)]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    replays = []
    manifest = _STATIC / "replays" / "manifest.json"
    if manifest.is_file():
        replays = json.loads(manifest.read_text())
    tmpl = _templates.get_template("index.html")
    return tmpl.render(tasks=[(t.id, t.title) for t in TASKS.values()],
                       replays=replays)


@app.get("/replays", response_class=HTMLResponse)
def replays_page() -> str:
    manifest = _STATIC / "replays" / "manifest.json"
    if not manifest.is_file():
        raise HTTPException(404, "no replays bundled in this deployment")
    tmpl = _templates.get_template("replays.html")
    return tmpl.render(manifest_json=manifest.read_text())


@app.get("/play", response_class=HTMLResponse)
def play_page() -> str:
    manifest = _STATIC / "replays" / "manifest.json"
    replays = json.loads(manifest.read_text()) if manifest.is_file() else []
    tmpl = _templates.get_template("play.html")
    return tmpl.render(tasks=[(t.id, t.title) for t in TASKS.values()],
                       agent_results_json=json.dumps(replays))


@app.get("/task/{task_id}", response_class=HTMLResponse)
def task_page(task_id: str, request: Request) -> str:
    sid = _sid(request)
    ep = _episode(sid, task_id)
    task = TASKS[task_id]
    tmpl = _templates.get_template(task.template)
    opts = dict(ep["opts"], task_id=task_id)
    return tmpl.render(
        title=task.title,
        opts_json=json.dumps(opts),
        **task.view(ep["state"]),
    )


@app.post("/api/{task_id}/reset")
def reset(task_id: str, req: ResetRequest, request: Request) -> dict[str, Any]:
    if task_id not in TASKS:
        raise HTTPException(404, f"unknown task '{task_id}'")
    sid = _sid(request)
    ep = _do_reset(sid, task_id, req)
    return {"task_id": task_id, "seed": ep["seed"], "instruction": ep["instruction"]}


@app.get("/api/{task_id}/instruction")
def instruction(task_id: str, request: Request) -> dict[str, str]:
    return {"instruction": _episode(_sid(request), task_id)["instruction"]}


@app.post("/api/{task_id}/action")
async def action(task_id: str, request: Request) -> JSONResponse:
    ep = _episode(_sid(request), task_id)
    payload = await request.json()
    result = TASKS[task_id].handle_action(ep["state"], payload)
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


@app.get("/api/{task_id}/verify")
def verify(task_id: str, request: Request) -> dict[str, Any]:
    ep = _episode(_sid(request), task_id)
    subgoals = TASKS[task_id].verify(ep["state"])
    return {"success": all(subgoals.values()), "subgoals": subgoals}


@app.get("/api/{task_id}/state")
def state(task_id: str, request: Request) -> dict[str, Any]:
    """Oracle/debug view of raw episode state. Not for agent consumption."""
    ep = _episode(_sid(request), task_id)
    return {"seed": ep["seed"], "opts": ep["opts"], "state": ep["state"]}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
