"""Single-active-run lock (production hardening, spec section 45).

Advisory lock file .forgex/run.lock {pid, host, created_at}. A live lock
(POSIX liveness check via os.kill(pid, 0)) refuses to start a second run.
Stale locks (dead pid, or older than STALE_AFTER_SECONDS where liveness
cannot be checked) are taken over.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from forgex.schemas.error import ProjectError

LOCK_NAME = "run.lock"
STALE_AFTER_SECONDS = 24 * 3600


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, owned by another user
    return False


class RunLock:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._acquired = False

    def acquire(self) -> None:
        if self._path.exists():
            data = None
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            if isinstance(data, dict) and "pid" in data:
                pid = int(data.get("pid", 0))
                age = time.time() - float(data.get("created_at", 0))
                if _pid_alive(pid):
                    raise ProjectError(
                        f"another FORGEX run appears active (pid {pid}, "
                        f"host {data.get('host', '?')}): {self._path}"
                    )
                if os.name != "posix" and age < STALE_AFTER_SECONDS:
                    raise ProjectError(
                        f"another FORGEX run may be active (pid {pid}) and liveness "
                        f"cannot be verified on this platform — remove {self._path} "
                        f"if you are sure it is stale"
                    )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "created_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
        self._acquired = True

    def release(self) -> None:
        if self._acquired:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass
            self._acquired = False
