from __future__ import annotations

import json
from pathlib import Path

from jarvis.core.contracts import PolicyDenied


DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "config" / "permissions.json"


class PermissionPolicy:
    def __init__(self, path: Path = DEFAULT_POLICY) -> None:
        self._config = json.loads(path.read_text(encoding="utf-8"))

    def require_tool(self, agent: str, tool: str) -> None:
        allowed = set(self._config.get("agents", {}).get(agent, {}).get("allow_tools", []))
        if tool not in allowed:
            raise PolicyDenied(f"Agent {agent!r} cannot call tool {tool!r}")

    def require_agent(self, coordinator: str, target: str) -> None:
        allowed = set(self._config.get("agents", {}).get(coordinator, {}).get("allow_agents", []))
        if target not in allowed:
            raise PolicyDenied(f"Agent {coordinator!r} cannot delegate to {target!r}")

    @property
    def environment(self) -> str:
        return str(self._config.get("environment", "unknown"))
