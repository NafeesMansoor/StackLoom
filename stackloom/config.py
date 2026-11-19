"""config.toml: the few settings a person may want to edit by hand."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from stackloom import paths


@dataclass
class Config:
    workspaces: list[str] = field(default_factory=list)
    port_pool: tuple[int, int] = (4100, 4999)
    dashboard_port: int | None = None
    auto_refresh_maps: bool = True
    recent_window_hours: int = 72
    discovery_depth: int = 5

    @classmethod
    def load(cls, base: Path | None = None) -> "Config":
        path = paths.config_path(base)
        if not path.exists():
            return cls()
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        pool = data.get("port_pool", {})
        cc = data.get("codecortex", {})
        return cls(
            workspaces=[str(Path(w).expanduser()) for w in data.get("workspaces", [])],
            port_pool=(int(pool.get("start", 4100)), int(pool.get("end", 4999))),
            dashboard_port=data.get("dashboard", {}).get("port"),
            auto_refresh_maps=bool(cc.get("auto_refresh", True)),
            recent_window_hours=int(cc.get("recent_window_hours", 72)),
            discovery_depth=int(data.get("discovery", {}).get("depth", 5)),
        )

    def save(self, base: Path | None = None) -> None:
        def q(s: str) -> str:
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

        lines = [
            "# STACKLOOM settings. Edit while STACKLOOM is stopped, or use the Settings page.",
            "workspaces = [" + ", ".join(q(w) for w in self.workspaces) + "]",
            "",
            "[port_pool]",
            f"start = {self.port_pool[0]}",
            f"end = {self.port_pool[1]}",
            "",
            "[dashboard]",
        ]
        if self.dashboard_port:
            lines.append(f"port = {int(self.dashboard_port)}")
        lines += [
            "",
            "[discovery]",
            f"depth = {int(self.discovery_depth)}",
            "",
            "[codecortex]",
            f"auto_refresh = {'true' if self.auto_refresh_maps else 'false'}",
            f"recent_window_hours = {int(self.recent_window_hours)}",
            "",
        ]
        path = paths.config_path(base)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(path)
