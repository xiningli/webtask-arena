from .base import Agent, Observation
from .scripted import ScriptedAgent

__all__ = ["Agent", "Observation", "ScriptedAgent", "make_agent"]


def make_agent(name: str, **kwargs):
    if name == "scripted":
        return ScriptedAgent(**kwargs)
    if name == "claude":
        from .claude import ClaudeComputerUseAgent

        return ClaudeComputerUseAgent(**{k: v for k, v in kwargs.items() if k != "browser"})
    raise ValueError(f"unknown agent '{name}' (available: scripted, claude)")
