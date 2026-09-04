"""Regression tests for the no-login SYSTEM_WORKS operator entry point."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "system_works_e2e", REPO_ROOT / "scripts" / "system_works_e2e.py"
)
assert SPEC and SPEC.loader
ENTRYPOINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRYPOINT)


MISSION_ID = "0a3d298b-3b4a-4d89-b43c-ab4823568974"
PACKET_SHA = "a" * 64


class SystemWorksEntryPointCase(unittest.TestCase):
    @mock.patch.object(ENTRYPOINT.shutil, "which", return_value="/usr/bin/gcloud")
    @mock.patch.object(ENTRYPOINT.subprocess, "run")
    def test_secret_uses_cached_account_without_login(self, run, _which) -> None:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "first@example.com\nsecond@example.com\n", ""),
            subprocess.CompletedProcess([], 1, "", "denied"),
            subprocess.CompletedProcess([], 0, "secret-value\n", ""),
        ]

        value, account = ENTRYPOINT.secret_from_cached_account(
            project="project", secret="secret"
        )

        self.assertEqual(value, "secret-value")
        self.assertEqual(account, "second@example.com")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(any(command[1:3] == ["auth", "login"] for command in commands))
        self.assertIn("--account=first@example.com", commands[1])
        self.assertIn("--account=second@example.com", commands[2])

    def test_approval_is_persisted_before_cached_auth_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = io.StringIO()
            with (
                mock.patch.object(
                    ENTRYPOINT,
                    "approve_exact_context",
                    return_value={"approved": True},
                ) as approve,
                mock.patch.object(
                    ENTRYPOINT,
                    "secret_from_ambient_credentials",
                    side_effect=ENTRYPOINT.EntryPointBlocked("no ambient credential"),
                ),
                contextlib.redirect_stdout(output),
            ):
                status = ENTRYPOINT.main(
                    [
                        "--mission-id",
                        MISSION_ID,
                        "--packet-sha256",
                        PACKET_SHA,
                        "--state-root",
                        root,
                    ]
                )

        self.assertEqual(status, 20)
        approve.assert_called_once()
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["systemWorks"], "BLOCKED")
        self.assertTrue(payload["contextApprovalPersisted"])
        self.assertFalse(payload["workerDispatched"])
        self.assertIn("no ambient credential", payload["reason"])

    def test_ambient_credentials_fall_back_to_application_default(self) -> None:
        with (
            mock.patch.object(
                ENTRYPOINT,
                "secret_from_cached_account",
                side_effect=ENTRYPOINT.EntryPointBlocked("no cached account"),
            ),
            mock.patch.object(
                ENTRYPOINT, "application_default_token", return_value="adc-token"
            ),
            mock.patch.object(
                ENTRYPOINT, "metadata_access_token", return_value="metadata-token"
            ) as metadata,
            mock.patch.object(
                ENTRYPOINT, "secret_from_access_token", return_value="secret-value"
            ) as access,
        ):
            value, identity = ENTRYPOINT.secret_from_ambient_credentials(
                project="valid-project", secret="valid-secret"
            )

        self.assertEqual((value, identity), ("secret-value", "application-default"))
        access.assert_called_once_with(
            token="adc-token", project="valid-project", secret="valid-secret"
        )
        metadata.assert_not_called()

    def test_ambient_credentials_fall_back_to_metadata_service_account(self) -> None:
        with (
            mock.patch.object(
                ENTRYPOINT,
                "secret_from_cached_account",
                side_effect=ENTRYPOINT.EntryPointBlocked("no cached account"),
            ),
            mock.patch.object(ENTRYPOINT, "application_default_token", return_value=""),
            mock.patch.object(
                ENTRYPOINT, "metadata_access_token", return_value="metadata-token"
            ),
            mock.patch.object(
                ENTRYPOINT, "secret_from_access_token", return_value="secret-value"
            ) as access,
        ):
            value, identity = ENTRYPOINT.secret_from_ambient_credentials(
                project="valid-project", secret="valid-secret"
            )

        self.assertEqual(
            (value, identity),
            ("secret-value", "metadata-default-service-account"),
        )
        access.assert_called_once_with(
            token="metadata-token", project="valid-project", secret="valid-secret"
        )


if __name__ == "__main__":
    unittest.main()
