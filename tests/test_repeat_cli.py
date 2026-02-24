"""Characterization tests for utils/repeat.py CLI layer -- Layer 2.

Tests run() and main() by mocking subprocess (samtools faidx).
"""

import io
import subprocess
import sys
import pytest
import utils.repeat as mod


def faidx_response(sequence):
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=">{}\n{}\n".format("region", sequence))


class TestRun:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        seq = "A" * 201
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

    def test_single_proc_output(self, monkeypatch, capsys):
        """run() in single-proc mode prints header + one result per SNV."""
        infile = io.StringIO("chr1\t100\tA\tT\n")
        args = type("Args", (), {
            "ref": "/fake/ref.fa",
            "nproc": 1,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        assert lines[0].startswith("#chr")
        assert len(lines) == 2
        parts = lines[1].split("\t")
        assert parts[0] == "chr1"
        assert parts[1] == "100"

    def test_skips_comment_lines(self, monkeypatch, capsys):
        """run() skips lines starting with '#'."""
        infile = io.StringIO("#header\nchr1\t100\tA\tT\n")
        args = type("Args", (), {
            "ref": "/fake/ref.fa",
            "nproc": 1,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        # header + 1 data line (comment skipped)
        assert len(lines) == 2

    def test_multiple_snvs(self, monkeypatch, capsys):
        """run() processes all non-comment SNVs."""
        infile = io.StringIO(
            "chr1\t100\tA\tT\n"
            "chr1\t200\tG\tC\n"
            "chr2\t300\tA\tG\n"
        )
        args = type("Args", (), {
            "ref": "/fake/ref.fa",
            "nproc": 1,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        assert len(lines) == 4  # header + 3 data lines

    def test_sets_global_ref_file(self, monkeypatch):
        """run() sets the global ref_file from args."""
        infile = io.StringIO("")
        args = type("Args", (), {
            "ref": "/custom/ref.fa",
            "nproc": 1,
            "infile": infile,
        })()

        mod.run(args)

        assert mod.ref_file == "/custom/ref.fa"

class TestMain:
    def test_dispatches_to_run(self, monkeypatch, capsys, tmp_path):
        """main() parses args and dispatches to run()."""
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        seq = "A" * 201
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

        snv_file = tmp_path / "snvs.txt"
        snv_file.write_text("chr1\t100\tA\tT\n")

        monkeypatch.setattr("sys.argv", [
            "repeat.py", "-r", "/fake/ref.fa", str(snv_file),
        ])

        mod.main()

        output = capsys.readouterr().out
        assert "chr1" in output

    def test_nproc_arg(self, monkeypatch):
        """main() accepts -n for nproc."""
        monkeypatch.setattr("sys.argv", [
            "repeat.py", "-r", "/fake/ref.fa", "-n", "4",
        ])
        # Don't actually run, just verify parse succeeds
        # Redirect to avoid stdin read
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        # Parse args without running (to avoid stdin blocking)
        import argparse
        captured = {}
        orig_set_defaults = argparse.ArgumentParser.set_defaults

        def capture_defaults(self, **kw):
            captured["func"] = kw.get("func")
            orig_set_defaults(self, **kw)

        monkeypatch.setattr(argparse.ArgumentParser, "set_defaults", capture_defaults)
        mod.main()
        # If we got here without error, parsing succeeded
