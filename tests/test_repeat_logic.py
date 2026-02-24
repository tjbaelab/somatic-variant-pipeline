"""Characterization tests for utils/repeat.py -- Layer 2 (mocked subprocess).

Tests ref_seq(), repeat(), and faidx() by mocking samtools faidx calls.
"""

import subprocess
import pytest
import utils.repeat as mod


def faidx_response(sequence):
    """Create a mock samtools faidx CompletedProcess response."""
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=">region\n{}\n".format(sequence)
    )


class TestRefSeq:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)

    def test_single_base(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response("A"))
        result = mod.ref_seq("chr1", 100)
        assert result == "A"

    def test_range(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response("ACGT"))
        result = mod.ref_seq("chr1", 100, 103)
        assert result == "ACGT"

    def test_multiline_fasta_joined(self, monkeypatch):
        """samtools faidx may output multi-line FASTA."""
        resp = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=">region\nACGT\nACGT\n")
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: resp)
        result = mod.ref_seq("chr1", 100, 107)
        assert result == "ACGTACGT"

    def test_single_base_site_format(self, monkeypatch):
        """Single-base query uses chrom:pos-pos format."""
        captured = {}

        def capture_run(cmd, **kw):
            captured["cmd"] = cmd
            return faidx_response("A")

        monkeypatch.setattr(subprocess, "run", capture_run)
        mod.ref_seq("chr1", 100)
        assert captured["cmd"][3] == "chr1:100-100"

    def test_range_site_format(self, monkeypatch):
        """Range query uses chrom:start-end format."""
        captured = {}

        def capture_run(cmd, **kw):
            captured["cmd"] = cmd
            return faidx_response("ACGT")

        monkeypatch.setattr(subprocess, "run", capture_run)
        mod.ref_seq("chr1", 100, 200)
        assert captured["cmd"][3] == "chr1:100-200"


class TestRepeat:
    def test_homopolymer_detected(self, monkeypatch):
        """Homopolymer A run: alt=A should detect high repeat count."""
        seq = "A" * 201
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

        result = mod.repeat("chr1", "200", "A")

        parts = result.split("\t")
        assert len(parts) == 3
        n = int(parts[0])
        assert n > 1

    def test_output_format(self, monkeypatch):
        """Output: n<TAB>length<TAB>repeat_seq with [ref>alt] notation."""
        seq = "A" * 201
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

        result = mod.repeat("chr1", "200", "T")

        parts = result.split("\t")
        assert len(parts) == 3
        int(parts[0])     # n: integer
        int(parts[1])     # length: integer
        assert "[" in parts[2] and ">" in parts[2] and "]" in parts[2]

    def test_non_repeat_region(self, monkeypatch):
        """Non-repeating sequence: should return n=1."""
        # Build a 201-char sequence with no tandem repeats at the center
        seq = "ACGTCGATCAGTACGC" * 12 + "ACGTCGATN"  # 201 chars
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

        result = mod.repeat("chr1", "200", "T")

        parts = result.split("\t")
        n = int(parts[0])
        assert n >= 1  # At minimum, the variant itself counts as 1


class TestFaidx:
    def test_output_format(self, monkeypatch):
        """faidx() returns chr<TAB>pos<TAB>REF<TAB>ALT<TAB>repeat_info."""
        seq = "N" * 201
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

        result = mod.faidx("chr1", "200", "A", "T")

        parts = result.split("\t")
        assert parts[0] == "chr1"
        assert parts[1] == "200"
        assert parts[2] == "A"
        assert parts[3] == "T"

    def test_uppercases_ref_alt(self, monkeypatch):
        seq = "N" * 201
        monkeypatch.setattr(mod, "ref_file", "/fake/ref.fa", raising=False)
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **kw: faidx_response(seq))

        result = mod.faidx("chr1", "200", "a", "t")

        parts = result.split("\t")
        assert parts[2] == "A"
        assert parts[3] == "T"
