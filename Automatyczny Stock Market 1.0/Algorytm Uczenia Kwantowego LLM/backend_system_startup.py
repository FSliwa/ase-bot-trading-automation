#!/usr/bin/env python3
"""Utility launcher that starts the backend-only stack for the ASE bot.

This script replaces the previous full-system starters that also booted
web dashboards. It now focuses exclusively on the API services that power
trading automation and programmatic integrations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("backend_startup")


@dataclass
class ManagedProcess:
    """Track a subprocess together with human readable metadata."""

    name: str
    command: Sequence[str]
    process: subprocess.Popen

    def terminate(self, timeout: float = 10.0) -> None:
        """Attempt to stop the process gracefully."""
        if self.process.poll() is not None:
            return

        logger.info("Stopping %s", self.name)
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("%s did not exit in %.1fs – killing", self.name, timeout)
            self.process.kill()
            self.process.wait(timeout=timeout)


class BackendStartup:
    """Boot the backend API and optional background workers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.managed: List[ManagedProcess] = []
        self._shutdown = False

    # ------------------------------------------------------------------
    # Launch helpers
    # ------------------------------------------------------------------
    def _spawn(self, name: str, command: Sequence[str], cwd: Optional[Path] = None) -> None:
        cwd = cwd or self.project_root
        logger.info("Starting %s", name)
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.managed.append(ManagedProcess(name=name, command=command, process=proc))

    def start_fastapi(self, reload: bool = False, port: int = 8008) -> None:
        """Start the FastAPI backend via uvicorn."""
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]
        if reload:
            cmd.append("--reload")
        self._spawn("FastAPI backend", cmd)

    def start_worker(self) -> None:
        """Start the optional analytics worker if available."""
        worker_script = self.project_root / "advanced_analytics_engine.py"
        if not worker_script.exists():
            logger.info("Skipping analytics worker – script not found")
            return
        self._spawn("Analytics engine", [sys.executable, str(worker_script)])

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def stream_logs(self) -> None:
        """Continuously stream stdout of child processes."""
        async def _drain(proc: ManagedProcess) -> None:
            assert proc.process.stdout is not None
            loop = asyncio.get_event_loop()
            while not self._shutdown and proc.process.poll() is None:
                line = await loop.run_in_executor(None, proc.process.stdout.readline)
                if not line:
                    break
                logger.info("[%s] %s", proc.name, line.rstrip())

        await asyncio.gather(*[_drain(p) for p in self.managed])

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        logger.info("Shutting down backend processes")
        for proc in reversed(self.managed):
            proc.terminate()

    def install_signal_handlers(self) -> None:
        def _handler(signum, _frame):
            logger.info("Received signal %s – shutting down", signum)
            self.shutdown()

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    async def run(self, reload: bool = False) -> None:
        self.install_signal_handlers()
        self.start_fastapi(reload=reload)
        self.start_worker()
        try:
            await self.stream_logs()
        finally:
            self.shutdown()


def main() -> None:
    project_root = Path(__file__).resolve().parent
    startup = BackendStartup(project_root=project_root)
    reload = os.getenv("ASE_BACKEND_RELOAD", "false").lower() in {"1", "true", "yes"}

    asyncio.run(startup.run(reload=reload))


if __name__ == "__main__":
    main()
