"""Unit tests for fs_tools (Part A)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import fs_tools
from fs_tools import FsToolError, list_files, read_file, search_in_file, write_file


def error_type(result: dict) -> str:
    assert result["success"] is False
    return result["error"]["type"]


# ----------------------------------------------------------------------------- read_file

class TestReadFile:
    def test_txt(self, sandbox):
        r = read_file("resumes/resume_alex_chen.txt")
        assert r["success"] and "React" in r["content"]
        meta = r["metadata"]
        assert meta["format"] == "txt" and meta["extension"] == ".txt"
        assert meta["word_count"] > 50 and meta["char_count"] == len(r["content"])
        assert meta["size_bytes"] > 0 and meta["modified"].endswith("+00:00")
        assert meta["truncated"] is False

    def test_pdf_has_page_count(self, sandbox):
        r = read_file("resumes/resume_john_doe.pdf")
        assert r["success"] and "FastAPI" in r["content"]
        assert r["metadata"]["format"] == "pdf" and r["metadata"]["page_count"] >= 1

    def test_docx_includes_table_cells(self, sandbox):
        r = read_file("resumes/resume_priya_sharma.docx")
        assert r["success"] and "Data Scientist" in r["content"]
        assert r["metadata"]["table_count"] == 1
        assert "Languages | Python, R, SQL" in r["content"]  # skills table rendered row by row

    def test_missing_file(self, sandbox):
        r = read_file("resumes/ghost.pdf")
        assert error_type(r) == "not_found" and "list_files" in r["error"]["message"]

    def test_directory(self, sandbox):
        assert error_type(read_file("resumes")) == "invalid_argument"

    def test_unsupported_extension(self, sandbox):
        (sandbox / "pic.png").write_bytes(b"\x89PNG")
        assert error_type(read_file("pic.png")) == "unsupported_format"

    def test_corrupt_pdf_and_docx(self, sandbox):
        (sandbox / "bad.pdf").write_bytes(b"this is not a pdf")
        (sandbox / "bad.docx").write_bytes(b"this is not a zip")
        assert error_type(read_file("bad.pdf")) == "extraction_failed"
        assert error_type(read_file("bad.docx")) == "extraction_failed"

    def test_blank_pdf_reports_no_text(self, sandbox):
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(sandbox / "blank.pdf"))
        c.showPage()
        c.save()
        r = read_file("blank.pdf")
        assert error_type(r) == "extraction_failed" and "scanned" in r["error"]["message"]

    def test_empty_txt(self, sandbox):
        (sandbox / "empty.txt").write_text("  \n\n ")
        assert error_type(read_file("empty.txt")) == "extraction_failed"

    def test_truncation_flag(self, sandbox):
        r = read_file("resumes/resume_alex_chen.txt", max_chars=100)
        assert r["success"] and len(r["content"]) == 100
        assert r["metadata"]["truncated"] is True and r["metadata"]["char_count"] > 100

    @pytest.mark.parametrize("bad", [0, -5, "10", True, None])
    def test_invalid_max_chars(self, sandbox, bad):
        assert error_type(read_file("resumes/resume_alex_chen.txt", max_chars=bad)) == "invalid_argument"

    def test_latin1_fallback(self, sandbox):
        (sandbox / "cafe.txt").write_bytes("Café résumé".encode("latin-1"))
        r = read_file("cafe.txt")
        assert r["success"] and r["content"] == "Café résumé" and r["metadata"]["encoding"] == "latin-1"

    def test_utf8_bom_stripped(self, sandbox):
        (sandbox / "bom.txt").write_bytes(b"\xef\xbb\xbfHello")
        assert read_file("bom.txt")["content"] == "Hello"

    def test_absolute_path_inside_root_is_allowed(self, sandbox):
        assert read_file(str(sandbox / "resumes" / "resume_alex_chen.txt"))["success"]

    @pytest.mark.parametrize("bad", ["", "   ", None, 123])
    def test_bad_path_argument(self, sandbox, bad):
        assert error_type(read_file(bad)) == "invalid_argument"


# ----------------------------------------------------------------------------- sandbox

class TestSandbox:
    def test_parent_traversal_blocked(self, sandbox):
        (sandbox.parent / "secret.txt").write_text("top secret")
        assert error_type(read_file("../secret.txt")) == "outside_sandbox"
        assert error_type(read_file("resumes/../../secret.txt")) == "outside_sandbox"

    def test_absolute_path_outside_blocked(self, sandbox, tmp_path_factory):
        other = tmp_path_factory.mktemp("elsewhere") / "x.txt"
        other.write_text("data")
        assert error_type(read_file(str(other))) == "outside_sandbox"

    def test_symlink_escape_blocked(self, sandbox, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside") / "leak.txt"
        outside.write_text("leaked")
        link = sandbox / "link.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not permitted on this platform/user")
        assert error_type(read_file("link.txt")) == "outside_sandbox"

    def test_write_outside_blocked(self, sandbox):
        assert error_type(write_file("../evil.txt", "x")) == "outside_sandbox"
        assert not (sandbox.parent / "evil.txt").exists()

    def test_list_outside_blocked(self, sandbox):
        with pytest.raises(FsToolError) as exc:
            list_files("..")
        assert exc.value.error_type == "outside_sandbox"


# ----------------------------------------------------------------------------- list_files

class TestListFiles:
    def test_lists_all_sorted_with_metadata(self, sandbox):
        files = list_files("resumes")
        assert [f["name"] for f in files] == [
            "resume_alex_chen.txt", "resume_john_doe.pdf", "resume_priya_sharma.docx",
        ]
        assert set(files[0]) == {"name", "path", "size_bytes", "modified", "extension"}
        assert files[1]["path"] == "resumes/resume_john_doe.pdf" and files[1]["size_bytes"] > 0

    @pytest.mark.parametrize("ext", ["pdf", ".pdf", ".PDF", " Pdf "])
    def test_extension_filter_variants(self, sandbox, ext):
        assert [f["name"] for f in list_files("resumes", ext)] == ["resume_john_doe.pdf"]

    def test_no_match_returns_empty_list(self, sandbox):
        assert list_files("resumes", ".md") == []

    def test_blank_extension_means_no_filter(self, sandbox):
        assert len(list_files("resumes", "")) == 3

    def test_skips_directories_and_hidden_files(self, sandbox):
        (sandbox / "resumes" / "sub").mkdir()
        (sandbox / "resumes" / ".hidden.txt").write_text("x")
        assert len(list_files("resumes")) == 3

    def test_missing_directory_raises_typed_error(self, sandbox):
        with pytest.raises(FsToolError) as exc:
            list_files("nope")
        assert exc.value.error_type == "not_found"

    def test_file_instead_of_directory(self, sandbox):
        with pytest.raises(FsToolError) as exc:
            list_files("resumes/resume_alex_chen.txt")
        assert exc.value.error_type == "invalid_argument"

    def test_root_listing(self, sandbox):
        assert list_files(".") == []  # only the 'resumes' directory exists at the root


# ----------------------------------------------------------------------------- write_file

class TestWriteFile:
    def test_creates_parent_directories(self, sandbox):
        r = write_file("output/deep/er/summary.md", "# Hello\n")
        assert r["success"] and r["bytes_written"] == 8 and r["overwritten"] is False
        assert r["created_directories"] == ["output", "output/deep", "output/deep/er"]
        assert (sandbox / "output/deep/er/summary.md").read_text() == "# Hello\n"

    def test_refuses_overwrite_by_default(self, sandbox):
        write_file("output/a.txt", "one")
        r = write_file("output/a.txt", "two")
        assert error_type(r) == "file_exists" and "overwrite" in r["error"]["message"]
        assert (sandbox / "output/a.txt").read_text() == "one"

    def test_overwrite_true_replaces(self, sandbox):
        write_file("output/a.txt", "one")
        r = write_file("output/a.txt", "two", overwrite=True)
        assert r["success"] and r["overwritten"] is True
        assert (sandbox / "output/a.txt").read_text() == "two"

    def test_unicode_roundtrip_and_byte_count(self, sandbox):
        r = write_file("output/u.txt", "naïve – 日本")
        assert r["bytes_written"] == len("naïve – 日本".encode())
        assert (sandbox / "output/u.txt").read_text(encoding="utf-8") == "naïve – 日本"

    @pytest.mark.parametrize("name", ["x.pdf", "x.docx", "x.exe", "noext"])
    def test_disallowed_extensions(self, sandbox, name):
        assert error_type(write_file(f"output/{name}", "data")) == "unsupported_format"

    def test_size_limit(self, sandbox):
        r = write_file("output/big.txt", "x" * (fs_tools.MAX_WRITE_BYTES + 1))
        assert error_type(r) == "invalid_argument"

    def test_directory_target(self, sandbox):
        (sandbox / "adir.txt").mkdir()
        assert error_type(write_file("adir.txt", "x")) == "invalid_argument"

    def test_non_string_content(self, sandbox):
        assert error_type(write_file("output/a.txt", 123)) == "invalid_argument"  # type: ignore[arg-type]

    def test_no_temp_files_left_behind(self, sandbox):
        write_file("output/a.txt", "x")
        write_file("output/a.txt", "y", overwrite=True)
        assert sorted(p.name for p in (sandbox / "output").iterdir()) == ["a.txt"]

    def test_written_file_is_readable_by_read_file(self, sandbox):
        write_file("output/note.txt", "hello world")
        assert read_file("output/note.txt")["content"] == "hello world"


# ----------------------------------------------------------------------------- search_in_file

class TestSearchInFile:
    def test_case_insensitive_preserves_original_case(self, sandbox):
        r = search_in_file("resumes/resume_alex_chen.txt", "PYTHON")
        assert r["success"] and r["total_matches"] == 2
        assert {m["match"] for m in r["matches"]} == {"Python"}

    def test_context_surrounds_match(self, sandbox):
        r = search_in_file("resumes/resume_alex_chen.txt", "Storybook", context_chars=20)
        ctx = r["matches"][0]["context"]
        assert "Storybook" in ctx and ctx.startswith("...") and len(ctx) < 80

    def test_context_zero(self, sandbox):
        r = search_in_file("resumes/resume_alex_chen.txt", "Storybook", context_chars=0)
        assert r["matches"][0]["context"].strip(".") == "Storybook"

    def test_no_match_is_success(self, sandbox):
        r = search_in_file("resumes/resume_alex_chen.txt", "COBOL")
        assert r["success"] and r["total_matches"] == 0 and r["matches"] == []

    def test_line_numbers_are_one_based(self, sandbox):
        r = search_in_file("resumes/resume_alex_chen.txt", "ALEX CHEN")
        assert r["matches"][0]["line"] == 1
        text = read_file("resumes/resume_alex_chen.txt")["content"]
        line = r["matches"][-1]["line"]
        assert "chen" in text.splitlines()[line - 1].lower()

    def test_whole_word(self, sandbox):
        (sandbox / "t.txt").write_text("JavaScript and Java and java.")
        loose = search_in_file("t.txt", "java")
        strict = search_in_file("t.txt", "java", whole_word=True)
        assert loose["total_matches"] == 3 and strict["total_matches"] == 2

    def test_keyword_is_literal_not_regex(self, sandbox):
        (sandbox / "t.txt").write_text("We use C++ and C#. Also a.b matches a.b only.")
        assert search_in_file("t.txt", "C++")["total_matches"] == 1
        assert search_in_file("t.txt", "a.b")["total_matches"] == 2
        assert search_in_file("t.txt", ".*")["total_matches"] == 0

    def test_max_matches_truncates_but_counts_all(self, sandbox):
        (sandbox / "t.txt").write_text("spam " * 50)
        r = search_in_file("t.txt", "spam", max_matches=5)
        assert r["total_matches"] == 50 and r["returned_matches"] == 5 and r["truncated"] is True

    def test_searches_pdf_and_docx(self, sandbox):
        assert search_in_file("resumes/resume_john_doe.pdf", "django")["total_matches"] >= 2
        assert search_in_file("resumes/resume_priya_sharma.docx", "pytorch")["total_matches"] >= 1

    def test_searches_full_text_not_truncated_view(self, sandbox):
        (sandbox / "long.txt").write_text("a " * 30_000 + "NEEDLE")
        assert search_in_file("long.txt", "needle")["total_matches"] == 1

    @pytest.mark.parametrize("kw", ["", "   ", None, 5])
    def test_invalid_keyword(self, sandbox, kw):
        assert error_type(search_in_file("resumes/resume_alex_chen.txt", kw)) == "invalid_argument"

    def test_invalid_numeric_options(self, sandbox):
        assert error_type(search_in_file("resumes/resume_alex_chen.txt", "x", max_matches=0)) == "invalid_argument"
        assert error_type(search_in_file("resumes/resume_alex_chen.txt", "x", context_chars=-1)) == "invalid_argument"

    def test_errors_propagate_from_loader(self, sandbox):
        assert error_type(search_in_file("resumes/ghost.pdf", "x")) == "not_found"
        assert error_type(search_in_file("../x.txt", "x")) == "outside_sandbox"


# ----------------------------------------------------------------------------- shipped sample data

class TestSampleData:
    def test_corpus_shape(self, real_project):
        files = list_files("resumes")
        assert len(files) == 8
        by_ext = {}
        for f in files:
            by_ext[f["extension"]] = by_ext.get(f["extension"], 0) + 1
        assert by_ext == {".pdf": 3, ".docx": 3, ".txt": 2}

    def test_every_resume_is_readable(self, real_project):
        for f in list_files("resumes"):
            r = read_file(f["path"])
            assert r["success"], (f["name"], r)
            assert r["metadata"]["word_count"] > 100

    def test_python_experience_spread(self, real_project):
        hits = {f["name"]: search_in_file(f["path"], "Python", whole_word=True)["total_matches"]
                for f in list_files("resumes")}
        assert hits["resume_david_okafor.docx"] == 0          # Java/Kotlin only
        assert hits["resume_john_doe.pdf"] >= 5                # core Python profile
        assert hits["resume_emily_watson.docx"] == 1           # intro course only
        assert sum(1 for v in hits.values() if v) == 7
