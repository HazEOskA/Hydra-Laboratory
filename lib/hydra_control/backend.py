"""Execution backend protocol and safe deterministic local implementation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from hermes.redact import redact

from .models import (
    BackendError,
    CommandResult,
    CreateSessionInput,
    ExecuteTaskInput,
    ExecutionArtifact,
    ExecutionEvent,
    ExecutionResult,
    ExecutionSession,
    ExecutionStatus,
)
from .store import utc_now


MAX_OUTPUT_BYTES = 128 * 1024
COMMAND_TIMEOUT_SECONDS = 20
SAFE_REPOSITORY = "fixture://hydra-safe-demo"
BACKEND_ID = "deterministic-local"
SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
SAFE_BRANCH = re.compile(r"^hydra/mission-[0-9a-f]{8}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@runtime_checkable
class ExecutionBackend(Protocol):
    """Production-shaped adapter boundary required by the mission contract."""

    backend_id: str

    def create_session(self, input: CreateSessionInput) -> ExecutionSession: ...

    def execute_task(self, input: ExecuteTaskInput) -> ExecutionResult: ...

    def get_status(self, session_id: str) -> ExecutionStatus: ...

    def stream_events(self, session_id: str) -> AsyncIterable[ExecutionEvent]: ...

    def cancel(self, session_id: str) -> None: ...

    def collect_artifacts(self, session_id: str) -> list[ExecutionArtifact]: ...


class DeterministicLocalBackend:
    """Fixture-only backend that performs real, bounded local work.

    API values never become commands or filesystem targets. Node IDs select fixed
    internal handlers, and every subprocess is an argv array run without a shell.
    """

    backend_id = BACKEND_ID

    def __init__(
        self,
        workspace_root: str | Path,
        artifact_root: str | Path,
        fixture_root: str | Path,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.artifact_root = Path(artifact_root).resolve()
        self.fixture_root = Path(fixture_root).resolve(strict=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ExecutionSession] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._events: dict[str, list[ExecutionEvent]] = {}
        self._artifacts: dict[str, list[ExecutionArtifact]] = {}
        self._lock = threading.RLock()
        self._validate_fixture()

    def _validate_fixture(self) -> None:
        if not self.fixture_root.is_dir():
            raise BackendError(f"fixture directory missing: {self.fixture_root}")
        for path in self.fixture_root.rglob("*"):
            if path.is_symlink():
                raise BackendError(f"fixture symlinks are forbidden: {path.name}")

    def create_session(self, input: CreateSessionInput) -> ExecutionSession:
        if input.repository != SAFE_REPOSITORY:
            raise BackendError("deterministic backend accepts only the built-in fixture")
        if not SAFE_SEGMENT.fullmatch(input.mission_id):
            raise BackendError("invalid internally generated mission id")
        if not SAFE_BRANCH.fullmatch(input.branch):
            raise BackendError("invalid internally generated mission branch")
        workspace = self._contained(
            self.workspace_root, self.workspace_root / input.mission_id, must_exist=False
        )
        with self._lock:
            session = self._sessions.get(input.mission_id)
            if session is None:
                session = ExecutionSession(
                    session_id=input.mission_id,
                    mission_id=input.mission_id,
                    backend=self.backend_id,
                    workspace=workspace,
                )
                self._sessions[input.mission_id] = session
                self._cancel[input.mission_id] = threading.Event()
                self._events[input.mission_id] = []
                self._artifacts[input.mission_id] = []
            if (workspace / ".git").is_dir():
                session.base_commit = self._git_sha(workspace, "main")
                session.result_commit = self._git_sha(workspace, "HEAD")
            self._emit(session, "SESSION_READY", "", "session is ready")
            return session

    def execute_task(self, input: ExecuteTaskInput) -> ExecutionResult:
        session = self._session(input.session_id)
        if self._cancel[input.session_id].is_set():
            return ExecutionResult(
                success=False,
                summary="session cancelled",
                error_code="CANCELLED",
            )
        handlers = {
            "mission-intake": self._mission_intake,
            "repository-fact-load": self._repository_fact_load,
            "feasibility-analysis": self._feasibility_analysis,
            "implementation-plan": self._implementation_plan,
            "sandbox-provisioning": self._sandbox_provisioning,
            "agent-execution": self._agent_execution,
            "quality-checks": self._quality_checks,
            "targeted-tests": self._targeted_tests,
            "runtime-verification": self._runtime_verification,
            "independent-review": self._independent_review,
            "apr-evidence": self._apr_evidence,
            "draft-pull-request": self._draft_pull_request,
        }
        handler = handlers.get(input.node_id)
        if handler is None:
            return ExecutionResult(
                success=False,
                summary=f"backend has no executable handler for {input.node_id}",
                error_code="UNSUPPORTED_NODE",
            )
        session.status = "RUNNING"
        self._emit(session, "TASK_STARTED", input.node_id, "task execution started")
        try:
            result = handler(session, input)
        except Exception as error:
            session.status = "FAILED"
            self._emit(session, "TASK_FAILED", input.node_id, str(error))
            return ExecutionResult(
                success=False,
                summary="deterministic backend failed safely",
                error_code=type(error).__name__.upper(),
                metadata={"detail": redact(str(error))[:500]},
            )
        session.status = "READY" if result.success else "FAILED"
        self._emit(
            session,
            "TASK_PASSED" if result.success else "TASK_FAILED",
            input.node_id,
            result.summary,
        )
        return result

    def get_status(self, session_id: str) -> ExecutionStatus:
        session = self._session(session_id)
        current = ""
        if session.workspace.is_dir() and (session.workspace / ".git").is_dir():
            current = self._git_sha(session.workspace, "HEAD")
        return ExecutionStatus(
            session_id=session_id,
            status="CANCELLED" if self._cancel[session_id].is_set() else session.status,
            commit_sha=current,
            detail="fixture-only workspace",
        )

    async def stream_events(self, session_id: str) -> AsyncIterable[ExecutionEvent]:
        index = 0
        while True:
            events = list(self._events.get(session_id, []))
            while index < len(events):
                yield events[index]
                index += 1
            status = self.get_status(session_id).status
            if status in {"FAILED", "CANCELLED"} or (
                status == "READY" and index >= len(events)
            ):
                return
            await asyncio.sleep(0.1)

    def cancel(self, session_id: str) -> None:
        session = self._session(session_id)
        self._cancel[session_id].set()
        session.status = "CANCELLED"
        self._emit(session, "SESSION_CANCELLED", "", "cancellation requested")

    def collect_artifacts(self, session_id: str) -> list[ExecutionArtifact]:
        self._session(session_id)
        return list(self._artifacts.get(session_id, []))

    def _mission_intake(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        artifact = self._artifact(
            session,
            input.node_id,
            "mission-manifest",
            "mission-manifest.json",
            json.dumps(input.manifest, indent=2, sort_keys=True) + "\n",
        )
        return ExecutionResult(
            True,
            "validated mission manifest stored",
            artifacts=[artifact],
            metadata={"validation": "PASS"},
        )

    def _repository_fact_load(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        facts: list[dict[str, Any]] = []
        for path in sorted(self.fixture_root.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                facts.append(
                    {
                        "path": path.relative_to(self.fixture_root).as_posix(),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        artifact = self._artifact(
            session,
            input.node_id,
            "repository-facts",
            "repository-facts.json",
            json.dumps(
                {
                    "repository": SAFE_REPOSITORY,
                    "files": facts,
                    "networkUsed": False,
                    "source": "built-in immutable fixture",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExecutionResult(
            True,
            f"loaded {len(facts)} fixture repository facts",
            artifacts=[artifact],
            metadata={"fileCount": len(facts)},
        )

    def _feasibility_analysis(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        analysis = {
            "feasible": True,
            "riskLevel": input.manifest["risk_level"],
            "backend": self.backend_id,
            "constraints": [
                "built-in fixture only",
                "no production credentials",
                "no network access",
                "no push or deployment",
            ],
            "unknowns": ["real Michael Angelo service contract", "remote agent sandbox"],
        }
        artifact = self._artifact(
            session,
            input.node_id,
            "analysis",
            "feasibility.json",
            json.dumps(analysis, indent=2, sort_keys=True) + "\n",
        )
        return ExecutionResult(True, "safe fixture execution is feasible", artifacts=[artifact])

    def _implementation_plan(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        artifact = self._artifact(
            session,
            input.node_id,
            "plan",
            "implementation-plan.json",
            json.dumps(
                {
                    "steps": [
                        "provision dedicated Git fixture workspace",
                        "create controlled typed function",
                        "run fixed quality and test commands",
                        "verify runtime output and independent Git diff",
                        "bind APR evidence to result commit",
                    ],
                    "rollback": "discard only the dedicated mission workspace",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExecutionResult(True, "deterministic implementation plan generated", artifacts=[artifact])

    def _sandbox_provisioning(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        workspace = session.workspace
        if workspace.exists():
            if not (workspace / ".git").is_dir():
                raise BackendError("existing mission workspace is not a Git worktree")
            session.base_commit = self._git_sha(workspace, "main")
            session.result_commit = self._git_sha(workspace, "HEAD")
            return ExecutionResult(
                True,
                "existing dedicated workspace recovered",
                metadata={
                    "workspace": str(workspace),
                    "baseCommit": session.base_commit,
                    "resultCommit": session.result_commit,
                },
            )
        shutil.copytree(self.fixture_root, workspace)
        self._assert_tree_safe(workspace)
        for text_path in workspace.rglob("*"):
            if text_path.is_file():
                text = text_path.read_text(encoding="utf-8")
                with text_path.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
        (workspace / ".home").mkdir()
        commands = [
            self._run(
                session,
                input.node_id,
                ("git", "init", "-b", "main"),
                require_git=False,
            ),
            self._run(
                session,
                input.node_id,
                ("git", "config", "core.autocrlf", "false"),
                require_git=False,
            ),
            self._run(
                session,
                input.node_id,
                ("git", "config", "user.name", "Hydra Deterministic Worker"),
                require_git=False,
            ),
            self._run(
                session,
                input.node_id,
                ("git", "config", "user.email", "hydra-worker@localhost"),
                require_git=False,
            ),
            self._run(
                session, input.node_id, ("git", "add", "."), require_git=False
            ),
            self._run(
                session,
                input.node_id,
                ("git", "commit", "-m", "fixture: create deterministic baseline"),
                require_git=False,
            ),
            self._run(
                session,
                input.node_id,
                ("git", "rev-parse", "HEAD"),
                require_git=False,
            ),
        ]
        failed = next((command for command in commands if command.exit_code != 0), None)
        if failed:
            return ExecutionResult(
                False,
                "sandbox provisioning command failed",
                commands=commands,
                error_code="COMMAND_FAILED",
            )
        session.base_commit = commands[-1].stdout.strip()
        session.result_commit = session.base_commit
        return ExecutionResult(
            True,
            "dedicated fixture Git workspace provisioned",
            commands=commands,
            metadata={
                "workspace": str(workspace),
                "baseCommit": session.base_commit,
                "resultCommit": session.result_commit,
            },
        )

    def _agent_execution(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._require_workspace(session)
        app = session.workspace / "app.py"
        text = app.read_text(encoding="utf-8")
        commands: list[CommandResult] = []
        if "def mission_summary(" not in text:
            marker = "# HYDRA_AGENT_INSERTION_POINT"
            if marker not in text:
                raise BackendError("controlled insertion point is missing")
            replacement = (
                "def mission_summary() -> str:\n"
                "    \"\"\"Return a deterministic worker result.\"\"\"\n"
                "    return \"Hydra mission executed with commit-bound evidence.\"\n\n\n"
                + marker
            )
            with app.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text.replace(marker, replacement))
            commands.extend(
                [
                    self._run(
                        session,
                        input.node_id,
                        ("git", "checkout", "-b", input.manifest["branch"]),
                    ),
                    self._run(session, input.node_id, ("git", "add", "app.py")),
                    self._run(
                        session,
                        input.node_id,
                        ("git", "commit", "-m", "feat: add deterministic mission result"),
                    ),
                ]
            )
        commands.append(self._run(session, input.node_id, ("git", "rev-parse", "HEAD")))
        failed = next((command for command in commands if command.exit_code != 0), None)
        if failed:
            return ExecutionResult(
                False,
                "controlled agent Git operation failed",
                commands=commands,
                error_code="COMMAND_FAILED",
            )
        session.result_commit = commands[-1].stdout.strip()
        if input.manifest.get("failure_mode") == "tests_once":
            marker = session.workspace / ".hydra-fail-once"
            if input.attempt == 1 and not marker.exists():
                marker.write_text("fail the next targeted test once\n", encoding="utf-8")
        artifact = self._artifact(
            session,
            input.node_id,
            "change-summary",
            "controlled-change.json",
            json.dumps(
                {
                    "file": "app.py",
                    "baseCommit": session.base_commit,
                    "resultCommit": session.result_commit,
                    "branch": input.manifest["branch"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExecutionResult(
            True,
            "controlled file change committed in dedicated workspace",
            commands=commands,
            artifacts=[artifact],
            metadata={"resultCommit": session.result_commit},
        )

    def _quality_checks(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._require_workspace(session)
        commands = [
            self._run(session, input.node_id, (sys.executable, "quality_check.py")),
            self._run(
                session,
                input.node_id,
                (sys.executable, "-m", "compileall", "-q", "app.py", "test_app.py"),
            ),
        ]
        success = all(command.exit_code == 0 for command in commands)
        return ExecutionResult(
            success,
            "format and lint checks passed" if success else "quality checks failed",
            commands=commands,
            metadata={
                "checks": {
                    "format": "PASS" if commands[0].exit_code == 0 else "FAIL",
                    "lint": "PASS" if commands[1].exit_code == 0 else "FAIL",
                    "typecheck": "NOT_REQUIRED",
                }
            },
            error_code="" if success else "QUALITY_CHECK_FAILED",
        )

    def _targeted_tests(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._require_workspace(session)
        command = self._run(
            session,
            input.node_id,
            (sys.executable, "-m", "unittest", "-v", "test_app.py"),
        )
        success = command.exit_code == 0
        return ExecutionResult(
            success,
            "targeted tests passed" if success else "targeted tests failed",
            commands=[command],
            metadata={"checks": {"tests": "PASS" if success else "FAIL"}},
            error_code="" if success else "TARGETED_TESTS_FAILED",
        )

    def _runtime_verification(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._require_workspace(session)
        command = self._run(session, input.node_id, (sys.executable, "app.py"))
        success = command.exit_code == 0 and "Hydra mission executed" in command.stdout
        return ExecutionResult(
            success,
            "runtime output verified" if success else "runtime verification failed",
            commands=[command],
            metadata={
                "checks": {"runtimeVerification": "PASS" if success else "FAIL"}
            },
            error_code="" if success else "RUNTIME_VERIFICATION_FAILED",
        )

    def _independent_review(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._require_workspace(session)
        base = input.base_commit or session.base_commit
        result = input.result_commit or session.result_commit
        self._validate_commits(base, result)
        commands = [
            self._run(session, input.node_id, ("git", "diff", "--check", base, result)),
            self._run(session, input.node_id, ("git", "status", "--porcelain")),
        ]
        success = commands[0].exit_code == 0 and commands[1].exit_code == 0
        artifact = self._artifact(
            session,
            input.node_id,
            "review",
            "independent-review.json",
            json.dumps(
                {
                    "reviewer": "deterministic-independent-review-v1",
                    "baseCommit": base,
                    "resultCommit": result,
                    "diffCheckExitCode": commands[0].exit_code,
                    "worktreeClean": commands[1].stdout.strip() == "",
                    "result": "PASS" if success else "FAIL",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExecutionResult(
            success,
            "independent Git review passed" if success else "independent review failed",
            commands=commands,
            artifacts=[artifact],
            metadata={"checks": {"review": "PASS" if success else "FAIL"}},
            error_code="" if success else "REVIEW_FAILED",
        )

    def _apr_evidence(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._require_workspace(session)
        base = input.base_commit or session.base_commit
        result = input.result_commit or session.result_commit
        self._validate_commits(base, result)
        commands = [
            self._run(
                session,
                input.node_id,
                ("git", "diff", "--name-only", base, result),
            ),
            self._run(session, input.node_id, ("git", "diff", "--stat", base, result)),
            self._run(session, input.node_id, ("git", "rev-parse", "HEAD")),
        ]
        success = all(command.exit_code == 0 for command in commands)
        current = commands[-1].stdout.strip()
        if current != result:
            success = False
        return ExecutionResult(
            success,
            "APR evidence inputs collected" if success else "APR commit binding failed",
            commands=commands,
            metadata={
                "changedFiles": [
                    value for value in commands[0].stdout.splitlines() if value.strip()
                ],
                "diffSummary": commands[1].stdout.strip(),
                "currentCommit": current,
                "checks": {"build": "NOT_REQUIRED"},
            },
            error_code="" if success else "APR_COMMIT_MISMATCH",
        )

    def _draft_pull_request(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        artifact = self._artifact(
            session,
            input.node_id,
            "draft-pull-request",
            "draft-pull-request.json",
            json.dumps(
                {
                    "title": input.manifest["title"],
                    "branch": input.manifest["branch"],
                    "base": "main",
                    "headCommit": input.result_commit or session.result_commit,
                    "status": "DRAFT_READY_LOCAL",
                    "remoteMutation": False,
                    "note": "No branch was pushed and no GitHub PR was created.",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExecutionResult(
            True,
            "local draft pull-request descriptor generated",
            artifacts=[artifact],
            metadata={"prStatus": "DRAFT_READY_LOCAL"},
        )

    def _run(
        self,
        session: ExecutionSession,
        node_id: str,
        argv: tuple[str, ...],
        *,
        require_git: bool = True,
    ) -> CommandResult:
        if require_git:
            self._require_workspace(session)
        else:
            self._contained(self.workspace_root, session.workspace, must_exist=True)
        if self._cancel[session.session_id].is_set():
            return CommandResult(
                command=argv,
                display=self._display(argv),
                started_at=utc_now(),
                finished_at=utc_now(),
                exit_code=130,
                stdout="",
                stderr="cancelled before command start",
                cancelled=True,
            )
        allowed_executables = {"git", sys.executable}
        if argv[0] not in allowed_executables:
            raise BackendError(f"executable is not allowlisted: {argv[0]}")
        started = utc_now()
        environment = self._minimal_environment(session.workspace)
        process = subprocess.Popen(
            list(argv),
            cwd=session.workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
        timed_out = False
        cancelled = False
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if self._cancel[session.session_id].is_set():
                    process.terminate()
                    cancelled = True
                    stdout, stderr = process.communicate(timeout=2)
                    break
                if time.monotonic() >= deadline:
                    process.kill()
                    timed_out = True
                    stdout, stderr = process.communicate(timeout=2)
                    break
        stdout = self._bounded(redact(stdout))
        stderr = self._bounded(redact(stderr))
        return CommandResult(
            command=argv,
            display=self._display(argv),
            started_at=started,
            finished_at=utc_now(),
            exit_code=124 if timed_out else (130 if cancelled else int(process.returncode or 0)),
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
        )

    @staticmethod
    def _minimal_environment(workspace: Path) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(workspace / ".home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
        if os.name == "nt":
            for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
                if os.environ.get(key):
                    env[key] = os.environ[key]
        return env

    def _artifact(
        self,
        session: ExecutionSession,
        node_id: str,
        kind: str,
        name: str,
        content: str,
    ) -> ExecutionArtifact:
        for value in (session.mission_id, node_id):
            if not SAFE_SEGMENT.fullmatch(value):
                raise BackendError("unsafe artifact path segment")
        directory = self.artifact_root / session.mission_id / node_id
        directory.mkdir(parents=True, exist_ok=True)
        directory = self._contained(self.artifact_root, directory, must_exist=True)
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", name)[:100]
        suffix = uuid.uuid4().hex[:8]
        path = directory / f"{suffix}-{safe_name}"
        data = redact(content).encode("utf-8")
        path.write_bytes(data)
        artifact = ExecutionArtifact(
            artifact_id=str(uuid.uuid4()),
            mission_id=session.mission_id,
            node_id=node_id,
            kind=kind,
            name=name,
            path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
        self._artifacts[session.session_id].append(artifact)
        return artifact

    def command_artifacts(
        self,
        session_id: str,
        node_id: str,
        command: CommandResult,
        index: int,
    ) -> tuple[ExecutionArtifact, ExecutionArtifact]:
        session = self._session(session_id)
        stdout = self._artifact(
            session,
            node_id,
            "command-stdout",
            f"command-{index:02d}-stdout.txt",
            command.stdout,
        )
        stderr = self._artifact(
            session,
            node_id,
            "command-stderr",
            f"command-{index:02d}-stderr.txt",
            command.stderr,
        )
        return stdout, stderr

    def evidence_artifact(
        self, session_id: str, node_id: str, bundle: dict[str, Any]
    ) -> ExecutionArtifact:
        return self._artifact(
            self._session(session_id),
            node_id,
            "apr-evidence",
            "apr-evidence.json",
            json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        )

    def _session(self, session_id: str) -> ExecutionSession:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise BackendError(f"unknown execution session: {session_id}") from error

    @staticmethod
    def _display(argv: tuple[str, ...]) -> str:
        return " ".join(json.dumps(value) if re.search(r"\s", value) else value for value in argv)

    @staticmethod
    def _bounded(text: str) -> str:
        data = text.encode("utf-8", errors="replace")
        if len(data) <= MAX_OUTPUT_BYTES:
            return text
        return data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore") + "\n[OUTPUT TRUNCATED]\n"

    def _emit(
        self, session: ExecutionSession, event_type: str, node_id: str, message: str
    ) -> None:
        self._events[session.session_id].append(
            ExecutionEvent(
                event_id=str(uuid.uuid4()),
                session_id=session.session_id,
                node_id=node_id,
                event_type=event_type,
                timestamp=utc_now(),
                message=redact(message)[:500],
            )
        )

    @staticmethod
    def _contained(root: Path, path: Path, *, must_exist: bool) -> Path:
        candidate = path.resolve(strict=must_exist)
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise BackendError(f"workspace path escapes dedicated root: {path}") from error
        return candidate

    @staticmethod
    def _assert_tree_safe(root: Path) -> None:
        for path in root.rglob("*"):
            if path.is_symlink():
                raise BackendError(f"workspace contains forbidden symlink: {path.name}")

    @staticmethod
    def _git_sha(workspace: Path, revision: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", revision],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            shell=False,
        )
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and COMMIT_SHA.fullmatch(value) else ""

    @staticmethod
    def _validate_commits(base: str, result: str) -> None:
        if not COMMIT_SHA.fullmatch(base) or not COMMIT_SHA.fullmatch(result):
            raise BackendError("commit binding requires full lowercase Git SHAs")

    @staticmethod
    def _require_workspace(session: ExecutionSession) -> None:
        if not session.workspace.is_dir() or not (session.workspace / ".git").is_dir():
            raise BackendError("execution workspace has not been provisioned")
