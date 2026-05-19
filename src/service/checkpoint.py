from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from src.crud.source import SourceChunkChange, upsert_git_checkpoint_source
from src.db import SessionLocal
from src.service.graph import GraphService

CHECKPOINT_SUMMARY_ENV = "GUARDIAN_CHECKPOINT_SUMMARY"


@dataclass(frozen=True)
class GitCheckpoint:
    commit_sha: str
    commit_message: str
    branch: str | None
    changed_files: list[str]
    session_summary: str


def capture_git_checkpoint(
    session: Session,
    *,
    checkpoint: GitCheckpoint,
    graph_service: GraphService | None = None,
) -> SourceChunkChange:
    change = upsert_git_checkpoint_source(
        session,
        commit_sha=checkpoint.commit_sha,
        commit_message=checkpoint.commit_message,
        branch=checkpoint.branch,
        changed_files=checkpoint.changed_files,
        session_summary=checkpoint.session_summary,
    )
    try:
        if graph_service is not None and change.changed:
            session.flush()
            graph_service.connect_chunks(session, change.chunks)
        session.commit()
    except Exception:
        session.rollback()
        if graph_service is not None and change.changed:
            graph_service.delete_chunks([chunk.id for chunk in change.chunks])
            graph_service.reconstruct(session)
        raise
    return change


def checkpoint_from_git(repo_path: Path, commit_sha: str = "HEAD") -> GitCheckpoint:
    full_sha = _git(repo_path, "rev-parse", commit_sha)
    commit_message = _git(repo_path, "log", "-1", "--format=%B", full_sha)
    branch = _git(repo_path, "branch", "--show-current") or None
    changed_files = _git(
        repo_path,
        "diff-tree",
        "--root",
        "-m",
        "--no-commit-id",
        "--name-only",
        "-r",
        full_sha,
    )
    files = list(dict.fromkeys(line for line in changed_files.splitlines() if line.strip()))
    session_summary = os.getenv(CHECKPOINT_SUMMARY_ENV) or commit_message.strip()
    return GitCheckpoint(
        commit_sha=full_sha,
        commit_message=commit_message.strip(),
        branch=branch,
        changed_files=files,
        session_summary=session_summary.strip(),
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Capture a git commit as Guardian memory.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--session-summary")
    args = parser.parse_args(argv)

    checkpoint = checkpoint_from_git(args.repo, args.commit)
    if args.session_summary:
        checkpoint = GitCheckpoint(
            commit_sha=checkpoint.commit_sha,
            commit_message=checkpoint.commit_message,
            branch=checkpoint.branch,
            changed_files=checkpoint.changed_files,
            session_summary=args.session_summary,
        )

    graph_service = GraphService()
    with SessionLocal() as session:
        graph_service.reconstruct(session)
        capture_git_checkpoint(session, checkpoint=checkpoint, graph_service=graph_service)
    return 0


def _git(repo_path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_path), *args],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


if __name__ == "__main__":
    raise SystemExit(main())
