"""Workspace provisioners — turn a resolved repo into a local working copy.

The worker agent "starts" by being handed a workspace path. Provisioning is a
write/side-effecting step, so the default is a no-op that only reports the
intended path (used in dry-run and tests); the git adapter performs the real
``git clone`` and is opt-in.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from ...domain import RepoRef
from ...ports import WorkspaceProvisioner

CommandRunner = Callable[[list[str]], None]


def _slug(ticket_key: str) -> str:
    return ticket_key.replace("/", "-")


class NoopWorkspaceProvisioner(WorkspaceProvisioner):
    """Reports the path a clone *would* land at without touching the disk."""

    def __init__(self, root: str = "/tmp/jiraya-workspaces") -> None:
        self._root = Path(root)
        self.provisioned: list[tuple[str, str]] = []  # (ticket_key, path)

    def provision(self, repo: RepoRef, ticket_key: str) -> str:
        dest = self._root / _slug(ticket_key)
        if repo.path:
            dest = dest / repo.path
        self.provisioned.append((ticket_key, str(dest)))
        return str(dest)


class GitWorkspaceProvisioner(WorkspaceProvisioner):
    """Clones the resolved repo so the worker agent can start on it."""

    def __init__(
        self,
        root: str = "/tmp/jiraya-workspaces",
        *,
        runner: CommandRunner | None = None,
        depth: int = 1,
    ) -> None:
        self._root = Path(root)
        self._depth = depth
        self._runner = runner or _default_runner

    def provision(self, repo: RepoRef, ticket_key: str) -> str:
        if not repo.clone_url:
            raise ValueError(f"Repo {repo.key} has no clone_url")
        checkout = self._root / _slug(ticket_key)
        if not checkout.exists():
            cmd = ["git", "clone", "--depth", str(self._depth)]
            if repo.default_branch:
                cmd += ["--branch", repo.default_branch]
            cmd += [repo.clone_url, str(checkout)]
            self._runner(cmd)
        return str(checkout / repo.path) if repo.path else str(checkout)


def _default_runner(cmd: list[str]) -> None:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"'{cmd[0]}' not found on PATH")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
