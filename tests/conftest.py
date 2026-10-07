"""Shared fixtures: an isolated sandbox root populated with one resume per format."""

from __future__ import annotations

from pathlib import Path

import pytest

import generate_resumes as gen

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _by_slug(slug: str) -> dict:
    return next(r for r in gen.RESUMES if r["slug"] == slug)


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """tmp sandbox root with resumes/{john_doe.pdf, priya_sharma.docx, alex_chen.txt}."""
    monkeypatch.setenv("FS_ROOT", str(tmp_path))
    resumes = tmp_path / "resumes"
    resumes.mkdir()
    gen.render_pdf(_by_slug("john_doe"), resumes / "resume_john_doe.pdf")
    gen.render_docx(_by_slug("priya_sharma"), resumes / "resume_priya_sharma.docx")
    gen.render_txt(_by_slug("alex_chen"), resumes / "resume_alex_chen.txt")
    return tmp_path


@pytest.fixture()
def real_project(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the sandbox at the real project folder (shipped sample resumes)."""
    monkeypatch.setenv("FS_ROOT", str(PROJECT_ROOT))
    return PROJECT_ROOT
