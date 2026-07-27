"""Safe subprocess adapter for the official Cedar policy CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class CedarCliError(RuntimeError):
    """Raised when the official Cedar CLI cannot be executed reliably."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CedarCliResult:
    """Result of one Cedar CLI subprocess invocation."""

    args: tuple[str, ...]
    returncode: int
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


class CedarCli:
    """Invoke the official ``cedar`` binary without using a shell.

    Resolution order is an explicit constructor argument, ``CEDAR_CLI``, then
    ``cedar`` on ``PATH``. A capability probe prevents the Python package's
    unrelated, same-named ``cedar`` entry point from being accepted.
    """

    def __init__(
        self,
        executable: str | Path | None = None,
        *,
        timeout_seconds: float = 15.0,
        max_output_chars: int = 12_000,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._configured_executable = str(
            executable or os.environ.get("CEDAR_CLI") or "cedar"
        )
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self._resolved_executable: str | None = None
        self._probed = False

    def _resolve(self) -> str:
        if self._resolved_executable is not None:
            return self._resolved_executable

        configured = self._configured_executable
        if os.sep in configured or (os.altsep and os.altsep in configured):
            path = Path(configured).expanduser().resolve()
            resolved = str(path) if path.is_file() else None
        else:
            resolved = shutil.which(configured)

        if resolved is None:
            raise CedarCliError(
                "CEDAR_CLI_NOT_FOUND",
                "official Cedar CLI was not found; install cedar-policy-cli and "
                "set CEDAR_CLI to the absolute path of its cedar binary",
            )
        self._resolved_executable = resolved
        return resolved

    @staticmethod
    def _combined_output(completed: subprocess.CompletedProcess[str]) -> str:
        parts = [part.strip() for part in (completed.stdout, completed.stderr) if part]
        return "\n".join(parts)

    def _run(self, args: Sequence[str]) -> CedarCliResult:
        executable = self._resolve()
        command = [executable, *args]
        try:
            completed = subprocaess.run(  # noqa: S603
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise CedarCliError(
                "CEDAR_CLI_TIMEOUT",
                f"Cedar CLI timed out after {self.timeout_seconds:g} seconds",
            ) from exc
        except OSError as exc:
            raise CedarCliError(
                "CEDAR_CLI_EXECUTION",
                f"failed to execute Cedar CLI: {exc}",
            ) from exc

        output = self._combined_output(completed)
        if len(output) > self.max_output_chars:
            output = f"{output[: self.max_output_chars]}\n... output truncated ..."
        return CedarCliResult(tuple(args), completed.returncode, output)

    def ensure_compatible(self) -> None: # 确认是官方cedar cli
        """Require a command unique to the official Cedar policy CLI."""
        if self._probed:
            return
        result = self._run(("language-version",))
        if not result.passed:
            detail = result.output or f"exit code {result.returncode}"
            raise CedarCliError(
                "CEDAR_CLI_INCOMPATIBLE",
                "configured executable is not the official Cedar policy CLI "
                f"(language-version failed: {detail})",
            )
        self._probed = True

    def check_policy(self, policy_path: Path) -> CedarCliResult:
        self.ensure_compatible()
        return self._run(
            (
                "--error-format",
                "plain",
                "check-parse",
                "--policies",
                str(policy_path),
                "--policy-format",
                "cedar",
            )
        )

    def check_schema(self, schema_path: Path) -> CedarCliResult:
        self.ensure_compatible()
        return self._run(
            (
                "--error-format",
                "plain",
                "check-parse",
                "--schema",
                str(schema_path),
                "--schema-format",
                "cedar",
            )
        )

    def validate(self, policy_path: Path, schema_path: Path) -> CedarCliResult:
        self.ensure_compatible()
        return self._run(
            (
                "--error-format",
                "plain",
                "validate",
                "--policies",
                str(policy_path),
                "--policy-format",
                "cedar",
                "--schema",
                str(schema_path),
                "--schema-format",
                "cedar",
                "--validation-mode",
                "strict",
            )
        )
