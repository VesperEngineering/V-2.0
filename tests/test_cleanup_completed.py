from pathlib import Path

from scripts import cleanup_completed
from scripts.cleanup_completed import main


def test_cleanup_is_dry_run_by_default_and_removes_only_generated_dirs(tmp_path, capsys):
    repo = tmp_path / "repo"
    worktree = repo / ".worktrees" / "finished"
    target = worktree / "target"
    scratch = worktree / ".tmp"
    nested_tmp = scratch / "nested" / "tmp"
    source = worktree / "src" / "keep.py"
    target.mkdir(parents=True)
    nested_tmp.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    target.joinpath("artifact.bin").write_bytes(b"generated")
    nested_tmp.joinpath("scratch.txt").write_text("temporary", encoding="utf-8")
    source.write_text("keep", encoding="utf-8")

    assert main(["--repo-root", str(repo), "--path", str(worktree)]) == 0
    assert target.exists()
    assert scratch.exists()
    output = capsys.readouterr().out
    assert ".tmp" in output
    assert "nested\\tmp" not in output

    assert main(["--repo-root", str(repo), "--path", str(worktree), "--apply"]) == 0
    assert not target.exists()
    assert not scratch.exists()
    assert source.exists()


def test_cleanup_rejects_paths_outside_repo(tmp_path, capsys):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside" / "target"
    repo.mkdir()
    outside.mkdir(parents=True)

    assert main(["--repo-root", str(repo), "--path", str(outside), "--apply"]) == 2
    assert outside.exists()
    assert "outside repository" in capsys.readouterr().out


def test_cleanup_rejects_protected_data(tmp_path, capsys):
    repo = tmp_path / "repo"
    protected = repo / "vesper" / "data" / "massive" / "target"
    protected.mkdir(parents=True)

    assert main(["--repo-root", str(repo), "--path", str(protected), "--apply"]) == 2
    assert protected.exists()
    assert "protected" in capsys.readouterr().out


def test_cleanup_marks_unreadable_candidates(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    def deny_walk(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(cleanup_completed.os, "walk", deny_walk)

    assert cleanup_completed._directory_size(candidate) is None


def test_done_gate_rejects_dirty_worktree(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    worktree = repo / "finished"
    worktree.mkdir(parents=True)
    monkeypatch.setattr(cleanup_completed, "_git_status", lambda _: [" M source.py"])

    assert main(["--repo-root", str(repo), "--path", str(worktree), "--done"]) == 2
    assert "dirty" in capsys.readouterr().out


def test_done_gate_accepts_clean_worktree_without_generated_candidates(
    monkeypatch, tmp_path, capsys
):
    repo = tmp_path / "repo"
    worktree = repo / "finished"
    worktree.mkdir(parents=True)
    monkeypatch.setattr(cleanup_completed, "_git_status", lambda _: [])

    assert main(["--repo-root", str(repo), "--path", str(worktree), "--done"]) == 0
    assert "DONE OK" in capsys.readouterr().out


def test_done_gate_automatically_removes_generated_dirs(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    worktree = repo / "finished"
    target = worktree / "target"
    target.mkdir(parents=True)
    target.joinpath("artifact.bin").write_bytes(b"generated")
    monkeypatch.setattr(cleanup_completed, "_git_status", lambda _: [])

    assert main(["--repo-root", str(repo), "--path", str(worktree), "--done"]) == 0
    assert not target.exists()
    assert "DONE OK" in capsys.readouterr().out
