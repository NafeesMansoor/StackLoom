"""Process identity. A PID is ours only if its kernel start time still matches."""
from __future__ import annotations

import os
import subprocess


def start_time(pid: int) -> str | None:
    try:
        result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                                timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def alive(pid: int | None, recorded_start: str | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return recorded_start is not None and start_time(pid) == recorded_start
