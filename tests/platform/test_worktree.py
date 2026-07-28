from __future__ import annotations

import subprocess

import pytest

from vesper.platform.worktree import WorktreeBoundaryError, inspect_worktree


def git(*arguments, cwd=None):
    subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_clean_standalone_clone_is_recorded_and_linked_worktree_is_rejected(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    git("init", "-q", cwd=primary)
    (primary / "README.md").write_text("baseline\n", encoding="utf-8")
    git("add", "README.md", cwd=primary)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "baseline",
        cwd=primary,
    )
    clone = tmp_path / "clone"
    git("clone", "-q", str(primary), str(clone), cwd=tmp_path)
    git("switch", "-q", "-c", "m2/test-clone", cwd=clone)

    context = inspect_worktree(clone)

    assert context.branch == "m2/test-clone"
    assert context.standalone_clone is True
    assert context.starting_status == ()
    assert len(context.commit) == 40
    linked = tmp_path / "linked"
    git("worktree", "add", "-q", "-b", "m2/linked", str(linked), cwd=primary)
    with pytest.raises(WorktreeBoundaryError, match="standalone disposable"):
        inspect_worktree(linked)


def test_dirty_standalone_clone_is_rejected(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    git("init", "-q", cwd=primary)
    (primary / "README.md").write_text("baseline\n", encoding="utf-8")
    git("add", "README.md", cwd=primary)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "baseline",
        cwd=primary,
    )
    clone = tmp_path / "clone"
    git("clone", "-q", str(primary), str(clone), cwd=tmp_path)
    (clone / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(WorktreeBoundaryError, match="clean"):
        inspect_worktree(clone)


def test_ignored_content_in_standalone_clone_is_rejected(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    git("init", "-q", cwd=primary)
    (primary / ".gitignore").write_text("*.secret\n", encoding="utf-8")
    git("add", ".gitignore", cwd=primary)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "baseline",
        cwd=primary,
    )
    clone = tmp_path / "clone"
    git("clone", "-q", str(primary), str(clone), cwd=tmp_path)
    (clone / "credential.secret").write_text("must not be mounted\n", encoding="utf-8")

    with pytest.raises(WorktreeBoundaryError, match="clean"):
        inspect_worktree(clone)


def test_git_init_checkout_is_not_treated_as_a_disposable_clone(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    git("init", "-q", cwd=repository)
    (repository / "README.md").write_text("baseline\n", encoding="utf-8")
    git("add", "README.md", cwd=repository)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "baseline",
        cwd=repository,
    )

    with pytest.raises(WorktreeBoundaryError, match="origin provenance"):
        inspect_worktree(repository)


def test_standalone_clone_requires_the_controller_approved_temporary_branch_prefix(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    git("init", "-q", cwd=primary)
    (primary / "README.md").write_text("baseline\n", encoding="utf-8")
    git("add", "README.md", cwd=primary)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "baseline",
        cwd=primary,
    )
    clone = tmp_path / "clone"
    git("clone", "-q", str(primary), str(clone), cwd=tmp_path)
    git("switch", "-q", "-c", "feature/not-m2", cwd=clone)

    with pytest.raises(WorktreeBoundaryError, match="branch"):
        inspect_worktree(clone, required_branch_prefix="m2/")


def test_standalone_clone_with_gitlink_is_rejected(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    git("init", "-q", cwd=primary)
    (primary / "README.md").write_text("baseline\n", encoding="utf-8")
    git("add", "README.md", cwd=primary)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "baseline",
        cwd=primary,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=primary,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{revision},vendor/library", cwd=primary)
    git(
        "-c",
        "user.name=V20 Test",
        "-c",
        "user.email=v20-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "gitlink",
        cwd=primary,
    )
    clone = tmp_path / "clone"
    git("clone", "-q", str(primary), str(clone), cwd=tmp_path)

    with pytest.raises(WorktreeBoundaryError, match="submodules"):
        inspect_worktree(clone)
