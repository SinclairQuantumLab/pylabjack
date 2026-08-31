"""Small, dependency-free runtime software-provenance resolver.

The module is deliberately independent of LabJack code so it can be copied or
extracted into a separate package later.  Repository inspection is read-only,
uses Git commands rather than parsing ``.git`` internals, and never makes a
hardware operation fail when Git or distribution metadata is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


_GIT_TIMEOUT_S = 2.0
_FULL_GIT_HASH = re.compile(r"[0-9a-fA-F]{40,64}\Z")
_SCP_REMOTE = re.compile(
    r"^(?:[^@/\\\s]+@)?(?P<host>[^:/\\\s]+):(?P<path>[^\\\s]+)$"
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[/\\]")
_INSTALLED_PACKAGE_DIRECTORIES = {"site-packages", "dist-packages"}


@dataclass(frozen=True, slots=True)
class SoftwareProvenance:
    """Immutable package and source-repository identity for one process.

    ``is_worktree_dirty`` is ``None`` when the worktree state could not be
    determined; absence must not be misreported as a clean checkout.  The
    remote field is a credential-free repository identifier such as
    ``github.com/owner/repository``, not the raw remote URL.
    """

    package_name: str
    package_version: str | None
    git_repository_name: str | None
    git_remote_repository: str | None
    git_commit_hash: str | None
    is_worktree_dirty: bool | None
    git_metadata_available: bool


def _resolve_package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except Exception:
        # Broken or absent distribution metadata must not block an operation.
        return None


def _source_directory(source_path: str | os.PathLike[str]) -> Path:
    path = Path(source_path).expanduser()
    try:
        path = path.resolve(strict=False)
    except OSError:
        path = path.absolute()

    if path.is_dir():
        return path
    return path.parent


def _is_installed_package_directory(source_directory: Path) -> bool:
    return any(
        part.lower() in _INSTALLED_PACKAGE_DIRECTORIES
        for part in source_directory.parts
    )


def _run_git(source_directory: Path, *arguments: str) -> str | None:
    """Return Git stdout, or ``None`` for any unavailable/error state."""
    environment = os.environ.copy()
    environment.update({
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    })

    try:
        completed = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(source_directory),
                *arguments,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_S,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout


def _normalize_remote_repository(remote_url: str | None) -> str | None:
    """Remove transport, credentials, query data, and the ``.git`` suffix."""
    if remote_url is None:
        return None

    value = remote_url.strip()
    if not value or any(ord(character) < 32 for character in value):
        return None
    if value.startswith(("/", "\\", ".")):
        return None
    if _WINDOWS_ABSOLUTE_PATH.match(value):
        return None

    scp_match = _SCP_REMOTE.match(value)
    if scp_match is not None and "://" not in value:
        host = scp_match.group("host").lower()
        path = scp_match.group("path").strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host}/{path}" if host and path else None

    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"git", "http", "https", "ssh"}:
        return None
    if parsed.hostname is None:
        return None

    host = parsed.hostname.lower()
    try:
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError:
        return None

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{host}/{path}" if path else None


def _normalized_commit_hash(raw_hash: str | None) -> str | None:
    if raw_hash is None:
        return None
    commit_hash = raw_hash.strip()
    if _FULL_GIT_HASH.fullmatch(commit_hash) is None:
        return None
    return commit_hash.lower()


def capture_software_provenance(
    *,
    package_name: str,
    source_path: str | os.PathLike[str],
) -> SoftwareProvenance:
    """Capture one package/repository snapshot without caching it.

    The nearest Git worktree containing ``source_path`` is used.  Dirty means
    staged, unstaged, deleted, or untracked content is present; Git-ignored
    content does not count.  The preferred remote is ``origin`` when it exists.
    """
    normalized_package_name = str(package_name).strip()
    if not normalized_package_name:
        raise ValueError("package_name must be a non-empty string.")

    package_version = _resolve_package_version(normalized_package_name)
    source_directory = _source_directory(source_path)
    if _is_installed_package_directory(source_directory):
        return SoftwareProvenance(
            package_name=normalized_package_name,
            package_version=package_version,
            git_repository_name=None,
            git_remote_repository=None,
            git_commit_hash=None,
            is_worktree_dirty=None,
            git_metadata_available=False,
        )

    raw_repository_root = _run_git(
        source_directory,
        "rev-parse",
        "--show-toplevel",
    )
    if raw_repository_root is None or not raw_repository_root.strip():
        return SoftwareProvenance(
            package_name=normalized_package_name,
            package_version=package_version,
            git_repository_name=None,
            git_remote_repository=None,
            git_commit_hash=None,
            is_worktree_dirty=None,
            git_metadata_available=False,
        )

    repository_root = Path(raw_repository_root.strip())
    raw_commit_hash = _run_git(repository_root, "rev-parse", "HEAD")
    raw_status = _run_git(
        repository_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=normal",
        "--ignore-submodules=none",
    )
    raw_remote = _run_git(
        repository_root,
        "remote",
        "get-url",
        "origin",
    )

    repository_name = repository_root.name or None
    return SoftwareProvenance(
        package_name=normalized_package_name,
        package_version=package_version,
        git_repository_name=repository_name,
        git_remote_repository=_normalize_remote_repository(raw_remote),
        git_commit_hash=_normalized_commit_hash(raw_commit_hash),
        is_worktree_dirty=None if raw_status is None else bool(raw_status),
        git_metadata_available=True,
    )


@lru_cache(maxsize=None)
def _cached_software_provenance(
    package_name: str,
    source_directory: str,
) -> SoftwareProvenance:
    return capture_software_provenance(
        package_name=package_name,
        source_path=source_directory,
    )


def get_software_provenance(
    *,
    package_name: str,
    source_path: str | os.PathLike[str],
) -> SoftwareProvenance:
    """Return the process-cached provenance snapshot for this source path."""
    normalized_package_name = str(package_name).strip()
    if not normalized_package_name:
        raise ValueError("package_name must be a non-empty string.")
    source_directory = str(_source_directory(source_path))
    return _cached_software_provenance(
        normalized_package_name,
        source_directory,
    )
