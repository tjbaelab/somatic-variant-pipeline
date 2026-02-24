"""Characterization tests for utils/alt_bq_sum.py -- Layer 2 (mocked imports).

Tests alt_BQ_sum() coroutine.
statsmodels is mocked if not installed (dead import in alt_bq_sum.py).
"""

import sys
import types

# Mock statsmodels if not installed (alt_bq_sum imports it but doesn't use it)
try:
    import statsmodels.stats.proportion
except ImportError:
    _sm = types.ModuleType("statsmodels")
    _sm_stats = types.ModuleType("statsmodels.stats")
    _sm_prop = types.ModuleType("statsmodels.stats.proportion")
    _sm_prop.binom_test = lambda *a, **kw: 0.5
    _sm.stats = _sm_stats
    _sm_stats.proportion = _sm_prop
    sys.modules["statsmodels"] = _sm
    sys.modules["statsmodels.stats"] = _sm_stats
    sys.modules["statsmodels.stats.proportion"] = _sm_prop

import io
import pytest
from library.misc import coroutine
import utils.alt_bq_sum as mod


@coroutine
def mock_base_qual():
    """Mock coroutine returning (base, quality) tuples."""
    result = None
    while True:
        chrom, pos = (yield result)
        result = [
            ("A", 30), ("A", 25), ("G", 20),
            ("T", 15), ("C", 10), ("A", 35),
        ]


@coroutine
def mock_base_qual_empty():
    """Mock coroutine returning empty list."""
    result = None
    while True:
        chrom, pos = (yield result)
        result = []


class TestAltBQSum:
    def test_counts_alt_bases(self):
        """alt_BQ_sum counts only bases matching the alt allele."""
        coro = mod.alt_BQ_sum(mock_base_qual())
        result = coro.send(("chr1", "100", "A"))

        parts = result.split("\t")
        alt_n = int(parts[0])
        alt_bq = int(parts[1])

        # A appears at qualities 30, 25, 35 → n=3, sum=90
        assert alt_n == 3
        assert alt_bq == 90

    def test_different_alt_allele(self):
        """Changing alt allele filters different bases."""
        coro = mod.alt_BQ_sum(mock_base_qual())
        result = coro.send(("chr1", "100", "G"))

        parts = result.split("\t")
        alt_n = int(parts[0])
        alt_bq = int(parts[1])

        # G appears at quality 20 → n=1, sum=20
        assert alt_n == 1
        assert alt_bq == 20

    def test_no_matching_alt(self):
        """No bases match the alt allele → n=0, sum=0."""
        coro = mod.alt_BQ_sum(mock_base_qual())
        result = coro.send(("chr1", "100", "N"))

        parts = result.split("\t")
        assert parts[0] == "0"
        assert parts[1] == "0"

    def test_empty_pileup(self):
        """Empty pileup → n=0, sum=0."""
        coro = mod.alt_BQ_sum(mock_base_qual_empty())
        result = coro.send(("chr1", "100", "A"))

        parts = result.split("\t")
        assert parts[0] == "0"
        assert parts[1] == "0"

    def test_output_format(self):
        """Output is 'alt_n<TAB>alt_BQ_sum'."""
        coro = mod.alt_BQ_sum(mock_base_qual())
        result = coro.send(("chr1", "100", "T"))

        parts = result.split("\t")
        assert len(parts) == 2
        int(parts[0])  # Must be int
        int(parts[1])  # Must be int

    def test_case_insensitive_alt(self):
        """alt is uppercased for comparison."""
        coro = mod.alt_BQ_sum(mock_base_qual())
        result = coro.send(("chr1", "100", "a"))

        parts = result.split("\t")
        # 'a'.upper() = 'A', matches (A,30), (A,25), (A,35)
        assert int(parts[0]) == 3

    def test_multiple_sends(self):
        """Coroutine handles sequential queries."""
        coro = mod.alt_BQ_sum(mock_base_qual())
        r1 = coro.send(("chr1", "100", "A"))
        r2 = coro.send(("chr1", "200", "G"))

        assert r1 != r2
        assert "3" in r1.split("\t")[0]  # A count
        assert "1" in r2.split("\t")[0]  # G count


class TestRun:
    def test_single_proc(self, monkeypatch, capsys):
        """run() prints header + results."""
        monkeypatch.setattr(mod, "base_qual_tuple",
                            lambda bam, mq, bq: mock_base_qual())

        infile = io.StringIO("chr1\t100\tA\tG\n")
        args = type("Args", (), {
            "bam": "test.bam",
            "min_MQ": 20,
            "min_BQ": 13,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        assert lines[0].startswith("#chr")
        assert len(lines) == 2
        assert "chr1" in lines[1]

    def test_skips_comments(self, monkeypatch, capsys):
        """run() skips comment lines."""
        monkeypatch.setattr(mod, "base_qual_tuple",
                            lambda bam, mq, bq: mock_base_qual())

        infile = io.StringIO("#header\nchr1\t100\tA\tG\n")
        args = type("Args", (), {
            "bam": "test.bam",
            "min_MQ": 20,
            "min_BQ": 13,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        assert len(lines) == 2
