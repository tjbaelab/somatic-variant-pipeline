"""Characterization tests for library/pileup.py coroutine layer -- Layer 2.

Tests pileup() coroutine, load_config(), base_count(), base_qual_tuple()
by mocking subprocess.run (samtools mpileup).
"""

import subprocess
import pytest
import library.pileup as mod
from library.pileup import (
    pileup, base_n, base_qual, base_count, base_qual_tuple, load_config,
)


def mpileup_response(stdout, returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr="")


class TestLoadConfig:
    def test_sets_samtools_from_config(self, monkeypatch, tmp_path):
        fake_samtools = tmp_path / "samtools"
        fake_samtools.write_text("#!/bin/bash\n")
        fake_samtools.chmod(0o755)

        monkeypatch.setattr(mod, "read_config", lambda ref, env: {
            "TOOLS": {"SAMTOOLS": str(fake_samtools)},
        })
        load_config("b37", "bp")
        assert mod.SAMTOOLS == str(fake_samtools)

    def test_falls_back_to_which_when_not_found(self, monkeypatch):
        monkeypatch.setattr(mod, "read_config", lambda ref, env: {
            "TOOLS": {"SAMTOOLS": "/nonexistent/path/samtools"},
        })
        load_config("b37", "bp")
        assert mod.SAMTOOLS != "/nonexistent/path/samtools"

    def test_falls_back_when_not_executable(self, monkeypatch, tmp_path):
        fake_samtools = tmp_path / "samtools"
        fake_samtools.write_text("not executable")
        # Don't chmod +x

        monkeypatch.setattr(mod, "read_config", lambda ref, env: {
            "TOOLS": {"SAMTOOLS": str(fake_samtools)},
        })
        load_config("b37", "bp")
        assert mod.SAMTOOLS != str(fake_samtools)


class TestPileupCoroutine:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(mod, "SAMTOOLS", "/fake/samtools")

    def test_basic_with_base_n(self, monkeypatch):
        """pileup parses mpileup output and delegates to base_n target."""
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response("chr1\t100\tA\t5\tACGTa\tIIIII"))

        coro = pileup("test.bam", 20, 13, base_n())
        result = coro.send(("chr1", "100"))

        assert isinstance(result, dict)
        assert result["A"] == 1
        assert result["C"] == 1
        assert result["G"] == 1
        assert result["T"] == 1
        assert result["a"] == 1

    def test_basic_with_base_qual(self, monkeypatch):
        """pileup with base_qual target returns (base, quality) tuples."""
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response("chr1\t100\tA\t3\tACG\tIJK"))

        coro = pileup("test.bam", 20, 13, base_qual())
        result = coro.send(("chr1", "100"))

        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == ("A", ord("I") - 33)
        assert result[1] == ("C", ord("J") - 33)
        assert result[2] == ("G", ord("K") - 33)

    def test_empty_output(self, monkeypatch):
        """Empty mpileup output yields empty bases to target."""
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response(""))

        coro = pileup("test.bam", 20, 13, base_n())
        result = coro.send(("chr1", "100"))

        assert all(v == 0 for v in result.values())

    def test_truncated_output_value_error(self, monkeypatch):
        """Truncated output (missing quals) triggers ValueError → empty bases."""
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response("chr1\t100\tA\t5\tACGT"))

        coro = pileup("test.bam", 20, 13, base_n())
        result = coro.send(("chr1", "100"))

        assert all(v == 0 for v in result.values())

    def test_multi_bam_concatenation(self, monkeypatch):
        """Multiple BAMs: bases from each BAM are concatenated."""
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response(
                "chr1\t100\tA\t3\tACG\tIII\t2\tTT\tJJ"))

        coro = pileup("bam1.bam bam2.bam", 20, 13, base_n())
        result = coro.send(("chr1", "100"))

        assert result["A"] == 1
        assert result["C"] == 1
        assert result["G"] == 1
        assert result["T"] == 2

    def test_multiple_sends(self, monkeypatch):
        """Coroutine handles multiple send() calls."""
        call_count = [0]

        def mock_run(cmd, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return mpileup_response("chr1\t100\tA\t2\tAA\tII")
            return mpileup_response("chr1\t200\tA\t3\tTTT\tIII")

        monkeypatch.setattr(subprocess, "run", mock_run)

        coro = pileup("test.bam", 20, 13, base_n())
        r1 = coro.send(("chr1", "100"))
        r2 = coro.send(("chr1", "200"))

        assert r1["A"] == 2
        assert r2["T"] == 3

    def test_retry_on_failure(self, monkeypatch):
        """pileup retries on CalledProcessError."""
        call_count = [0]

        def mock_run(cmd, **kw):
            call_count[0] += 1
            if call_count[0] < 3:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=1, stdout="", stderr="err")
            return mpileup_response("chr1\t100\tA\t2\tAA\tII")

        monkeypatch.setattr(subprocess, "run", mock_run)

        coro = pileup("test.bam", 20, 13, base_n())
        result = coro.send(("chr1", "100"))

        assert call_count[0] == 3
        assert result["A"] == 2

    def test_max_retry_exits(self, monkeypatch):
        """pileup exits after exhausting retries."""
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="err"))

        coro = pileup("test.bam", 20, 13, base_n())
        with pytest.raises(SystemExit):
            coro.send(("chr1", "100"))

    def test_command_includes_bam_and_region(self, monkeypatch):
        """Verify the samtools command is built correctly."""
        captured = {}

        def capture_run(cmd, **kw):
            captured["cmd"] = cmd
            return mpileup_response("chr1\t100\tA\t1\tA\tI")

        monkeypatch.setattr(subprocess, "run", capture_run)

        coro = pileup("test.bam", 20, 13, base_n())
        coro.send(("chr1", "100"))

        cmd = captured["cmd"]
        assert cmd[0] == "/fake/samtools"
        assert "mpileup" in cmd
        assert "-q" in cmd
        assert "chr1:100-100" in cmd
        assert "test.bam" in cmd


class TestBaseCountWrapper:
    def test_returns_working_coroutine(self, monkeypatch):
        monkeypatch.setattr(mod, "SAMTOOLS", "/fake/samtools")
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response("chr1\t100\tA\t2\tAC\tII"))

        coro = base_count("test.bam", 20, 13)
        result = coro.send(("chr1", "100"))

        assert isinstance(result, dict)
        assert result["A"] == 1
        assert result["C"] == 1


class TestBaseQualTupleWrapper:
    def test_returns_working_coroutine(self, monkeypatch):
        monkeypatch.setattr(mod, "SAMTOOLS", "/fake/samtools")
        monkeypatch.setattr(subprocess, "run",
            lambda cmd, **kw: mpileup_response("chr1\t100\tA\t2\tAC\tIJ"))

        coro = base_qual_tuple("test.bam", 20, 13)
        result = coro.send(("chr1", "100"))

        assert isinstance(result, list)
        assert len(result) == 2
