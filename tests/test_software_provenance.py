from dataclasses import FrozenInstanceError
from pathlib import Path
import shutil
import subprocess

import pytest

import pylabjack._software_provenance as provenance_module
from pylabjack._software_provenance import (
    SoftwareProvenance,
    capture_software_provenance,
    get_software_provenance,
)


_COMMIT_HASH = "0123456789abcdef0123456789abcdef01234567"


def _provenance(**overrides) -> SoftwareProvenance:
    values = {
        "package_name": "pylabjack",
        "package_version": "0.1.0",
        "git_repository_name": "pylabjack",
        "git_remote_repository": "github.com/example/pylabjack",
        "git_commit_hash": _COMMIT_HASH,
        "is_worktree_dirty": False,
        "git_metadata_available": True,
    }
    values.update(overrides)
    return SoftwareProvenance(**values)


def test_software_provenance_is_immutable():
    provenance = _provenance()

    with pytest.raises(FrozenInstanceError):
        provenance.is_worktree_dirty = True


@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        (
            "https://user:secret@GitHub.com/owner/repository.git?token=secret",
            "github.com/owner/repository",
        ),
        (
            "git@github.com:owner/repository.git",
            "github.com/owner/repository",
        ),
        (
            "ssh://git@example.com:2222/group/repository.git",
            "example.com:2222/group/repository",
        ),
        ("file:///private/repository.git", None),
        ("../private/repository.git", None),
        (r"C:\private\repository.git", None),
        ("https://[invalid/repository.git", None),
    ],
)
def test_remote_repository_normalization_omits_transport_and_credentials(
    remote_url,
    expected,
):
    normalized = provenance_module._normalize_remote_repository(remote_url)

    assert normalized == expected
    if normalized is not None:
        assert "secret" not in normalized
        assert "user" not in normalized


def test_capture_collects_self_contained_repository_identity(
    monkeypatch,
    tmp_path,
):
    repository_root = tmp_path / "repository"
    source_file = repository_root / "src" / "package.py"
    responses = {
        ("rev-parse", "--show-toplevel"): f"{repository_root}\n",
        ("rev-parse", "HEAD"): f"{_COMMIT_HASH.upper()}\n",
        (
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=none",
        ): "?? new-file.py\0",
        (
            "remote",
            "get-url",
            "origin",
        ): "https://user:secret@example.com/team/repository.git\n",
    }

    monkeypatch.setattr(
        provenance_module,
        "_resolve_package_version",
        lambda package_name: "1.2.3",
    )
    monkeypatch.setattr(
        provenance_module,
        "_run_git",
        lambda source_directory, *arguments: responses[arguments],
    )

    provenance = capture_software_provenance(
        package_name="example-package",
        source_path=source_file,
    )

    assert provenance == SoftwareProvenance(
        package_name="example-package",
        package_version="1.2.3",
        git_repository_name="repository",
        git_remote_repository="example.com/team/repository",
        git_commit_hash=_COMMIT_HASH,
        is_worktree_dirty=True,
        git_metadata_available=True,
    )


def test_capture_represents_missing_git_metadata_explicitly(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        provenance_module,
        "_resolve_package_version",
        lambda package_name: "1.2.3",
    )
    monkeypatch.setattr(
        provenance_module,
        "_run_git",
        lambda source_directory, *arguments: None,
    )

    provenance = capture_software_provenance(
        package_name="example-package",
        source_path=tmp_path,
    )

    assert provenance.package_version == "1.2.3"
    assert provenance.git_repository_name is None
    assert provenance.git_remote_repository is None
    assert provenance.git_commit_hash is None
    assert provenance.is_worktree_dirty is None
    assert provenance.git_metadata_available is False


def test_missing_origin_does_not_hide_other_git_metadata(
    monkeypatch,
    tmp_path,
):
    repository_root = tmp_path / "repository"

    def fake_git(source_directory, *arguments):
        if arguments == ("rev-parse", "--show-toplevel"):
            return f"{repository_root}\n"
        if arguments == ("rev-parse", "HEAD"):
            return f"{_COMMIT_HASH}\n"
        if arguments[0] == "status":
            return ""
        return None

    monkeypatch.setattr(provenance_module, "_run_git", fake_git)
    provenance = capture_software_provenance(
        package_name="package-that-is-not-installed",
        source_path=repository_root / "module.py",
    )

    assert provenance.git_repository_name == "repository"
    assert provenance.git_remote_repository is None
    assert provenance.git_commit_hash == _COMMIT_HASH
    assert provenance.is_worktree_dirty is False
    assert provenance.git_metadata_available is True


def test_installed_wheel_path_does_not_inherit_a_parent_worktree(
    monkeypatch,
    tmp_path,
):
    git_calls = []
    monkeypatch.setattr(
        provenance_module,
        "_resolve_package_version",
        lambda package_name: "1.2.3",
    )
    monkeypatch.setattr(
        provenance_module,
        "_run_git",
        lambda source_directory, *arguments: git_calls.append(arguments),
    )
    installed_module = (
        tmp_path
        / "worktree"
        / ".venv"
        / "Lib"
        / "site-packages"
        / "example_package"
        / "module.py"
    )

    provenance = capture_software_provenance(
        package_name="example-package",
        source_path=installed_module,
    )

    assert provenance.package_version == "1.2.3"
    assert provenance.git_metadata_available is False
    assert provenance.git_commit_hash is None
    assert provenance.is_worktree_dirty is None
    assert git_calls == []


def test_process_cache_reuses_one_immutable_snapshot(monkeypatch, tmp_path):
    expected = _provenance()
    capture_calls = []

    def fake_capture(*, package_name, source_path):
        capture_calls.append((package_name, source_path))
        return expected

    monkeypatch.setattr(
        provenance_module,
        "capture_software_provenance",
        fake_capture,
    )
    provenance_module._cached_software_provenance.cache_clear()
    try:
        first = get_software_provenance(
            package_name="pylabjack",
            source_path=tmp_path,
        )
        second = get_software_provenance(
            package_name="pylabjack",
            source_path=tmp_path,
        )
    finally:
        provenance_module._cached_software_provenance.cache_clear()

    assert first is expected
    assert second is expected
    assert len(capture_calls) == 1


def _run_test_git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def _initialize_test_repository(repository: Path) -> None:
    repository.mkdir()
    _run_test_git(repository, "init", "--quiet")
    _run_test_git(repository, "config", "user.name", "Provenance Test")
    _run_test_git(
        repository,
        "config",
        "user.email",
        "provenance@example.invalid",
    )
    (repository / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (repository / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _run_test_git(repository, "add", ".gitignore", "tracked.txt")
    _run_test_git(repository, "commit", "--quiet", "-m", "initial")
    _run_test_git(
        repository,
        "remote",
        "add",
        "origin",
        "git@example.com:group/repository.git",
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
@pytest.mark.parametrize(
    "worktree_change",
    ["staged", "unstaged", "deleted", "untracked"],
)
def test_real_git_dirty_contract_includes_every_nonignored_state(
    tmp_path,
    worktree_change,
):
    repository = tmp_path / "repository"
    _initialize_test_repository(repository)

    (repository / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    clean = capture_software_provenance(
        package_name="package-that-is-not-installed",
        source_path=repository / "tracked.txt",
    )
    assert clean.is_worktree_dirty is False

    if worktree_change == "staged":
        (repository / "tracked.txt").write_text("staged\n", encoding="utf-8")
        _run_test_git(repository, "add", "tracked.txt")
    elif worktree_change == "unstaged":
        (repository / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
    elif worktree_change == "deleted":
        (repository / "tracked.txt").unlink()
    else:
        (repository / "untracked.txt").write_text("new\n", encoding="utf-8")

    dirty = capture_software_provenance(
        package_name="package-that-is-not-installed",
        source_path=repository / "tracked.txt",
    )

    assert dirty.git_repository_name == "repository"
    assert dirty.git_remote_repository == "example.com/group/repository"
    assert dirty.git_commit_hash == _run_test_git(
        repository,
        "rev-parse",
        "HEAD",
    ).strip()
    assert dirty.is_worktree_dirty is True
    assert dirty.git_metadata_available is True
