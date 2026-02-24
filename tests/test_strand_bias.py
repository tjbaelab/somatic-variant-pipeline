"""Characterization tests for utils/strand_bias.py -- Layer 2 (mocked imports).

Tests strand_info() coroutine, p_fisher(), mpileup() formatter.
rpy2 and scipy are mocked if not installed.
"""

import sys
import types

# Mock rpy2 if not installed
try:
    from rpy2.robjects import r as _real_r
except ImportError:
    _rpy2 = types.ModuleType("rpy2")
    _rpy2_rob = types.ModuleType("rpy2.robjects")
    _rpy2_rob.r = lambda expr: [1.0]
    _rpy2.robjects = _rpy2_rob
    sys.modules["rpy2"] = _rpy2
    sys.modules["rpy2.robjects"] = _rpy2_rob

# Mock scipy if not installed
try:
    from scipy.stats import fisher_exact as _real_fisher
except ImportError:
    _scipy = types.ModuleType("scipy")
    _scipy_stats = types.ModuleType("scipy.stats")
    _scipy_stats.fisher_exact = lambda table: (1.0, 0.5)
    _scipy.stats = _scipy_stats
    sys.modules["scipy"] = _scipy
    sys.modules["scipy.stats"] = _scipy_stats

import io
import math
import pytest
from library.misc import coroutine
import utils.strand_bias as mod


@coroutine
def mock_base_count():
    """Mock coroutine returning fixed base counts.

    Forward: A=20, C=5, G=3, T=2  (total_fwd=30)
    Reverse: a=15, c=3, g=2, t=0  (total_rev=20)
    Dels: 1
    """
    result = None
    while True:
        chrom, pos = (yield result)
        result = {
            'A': 20, 'C': 5, 'G': 3, 'T': 2,
            'a': 15, 'c': 3, 'g': 2, 't': 0,
            'dels': 1,
        }


@coroutine
def mock_base_count_zero_rev():
    """Mock with zero reverse strand counts."""
    result = None
    while True:
        chrom, pos = (yield result)
        result = {
            'A': 10, 'C': 5, 'G': 3, 'T': 2,
            'a': 0, 'c': 0, 'g': 0, 't': 0,
            'dels': 0,
        }


class TestStrandInfo:
    def test_basic_counts(self):
        """strand_info computes forward/reverse strand metrics."""
        coro = mod.strand_info(mock_base_count())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        total = int(parts[0])
        total_fwd = int(parts[1])
        total_rev = int(parts[2])

        # Forward: 20+5+3+2=30, Reverse: 15+3+2+0=20, Total: 50+1(dels)=51
        assert total == 51
        assert total_fwd == 30
        assert total_rev == 20

    def test_ref_alt_counts(self):
        """Ref and alt allele counts combine forward + reverse."""
        coro = mod.strand_info(mock_base_count())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        ref_n = int(parts[5])
        ref_fwd = int(parts[6])
        ref_rev = int(parts[7])
        alt_n = int(parts[9])
        alt_fwd = int(parts[10])
        alt_rev = int(parts[11])

        # ref=A: fwd=20, rev=15, total=35
        assert ref_n == 35
        assert ref_fwd == 20
        assert ref_rev == 15
        # alt=G: fwd=3, rev=2, total=5
        assert alt_n == 5
        assert alt_fwd == 3
        assert alt_rev == 2

    def test_ratio_calculation(self):
        """Forward/reverse ratio computed correctly."""
        coro = mod.strand_info(mock_base_count())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        total_ratio = float(parts[3])
        ref_ratio = float(parts[8])
        alt_ratio = float(parts[12])

        assert abs(total_ratio - 30 / 20) < 1e-6
        assert abs(ref_ratio - 20 / 15) < 1e-6
        assert abs(alt_ratio - 3 / 2) < 1e-6

    def test_zero_reverse_inf_ratio(self):
        """Zero reverse count → ratio is inf."""
        coro = mod.strand_info(mock_base_count_zero_rev())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        total_ratio = float(parts[3])
        assert math.isinf(total_ratio)

    def test_output_field_count(self):
        """Output has 14 fields: total metrics(4) + p_poisson(1) + ref(4) + alt(4) + p_fisher(1)."""
        coro = mod.strand_info(mock_base_count())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        assert len(parts) == 14

    def test_multiple_sends(self):
        """Coroutine handles sequential queries."""
        coro = mod.strand_info(mock_base_count())
        r1 = coro.send(("chr1", "100", "A", "G"))
        r2 = coro.send(("chr1", "200", "A", "T"))

        # Same base_count mock but different ref/alt → different ref/alt metrics
        p1 = r1.split("\t")
        p2 = r2.split("\t")
        # Total is the same
        assert p1[0] == p2[0]
        # Alt counts differ (G vs T)
        assert p1[9] != p2[9]


class TestPFisher:
    def test_returns_float(self):
        """p_fisher returns a p-value float."""
        result = mod.p_fisher(10, 5, 8, 3)
        assert isinstance(result, float)

    def test_symmetric_input(self):
        """Equal counts in all cells → p-value = 1.0."""
        result = mod.p_fisher(10, 10, 10, 10)
        assert abs(result - 1.0) < 1e-6

    def test_zero_cells(self):
        """Zero counts don't cause errors."""
        result = mod.p_fisher(0, 0, 0, 0)
        assert isinstance(result, float)


class TestPPoisson:
    def test_returns_float(self):
        """p_poisson returns a p-value float."""
        result = mod.p_poisson(10, 10)
        assert isinstance(result, float)

    def test_equal_counts(self):
        """Equal forward/reverse → high p-value (no bias)."""
        result = mod.p_poisson(50, 50)
        assert isinstance(result, float)


class TestMpileupFormatter:
    def test_format(self):
        """mpileup() prepends chrom/pos/ref/alt to strand_info result."""
        coro = mod.strand_info(mock_base_count())
        result = mod.mpileup(coro, "chr1", "100", "a", "g")

        parts = result.split("\t")
        assert parts[0] == "chr1"
        assert parts[1] == "100"
        assert parts[2] == "A"  # uppercased
        assert parts[3] == "G"  # uppercased

    def test_total_fields(self):
        """Full output: 4 (position) + 14 (strand_info) = 18 fields."""
        coro = mod.strand_info(mock_base_count())
        result = mod.mpileup(coro, "chr1", "100", "A", "G")

        parts = result.split("\t")
        assert len(parts) == 18


class TestRun:
    def test_single_proc(self, monkeypatch, capsys):
        """run() processes SNVs in single-proc mode."""
        monkeypatch.setattr(mod, "base_count",
                            lambda bam, mq, bq: mock_base_count())

        infile = io.StringIO("chr1\t100\tA\tG\n")
        args = type("Args", (), {
            "bam": "test.bam",
            "min_MQ": 20,
            "min_BQ": 13,
            "nproc": 1,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        assert lines[0].startswith("#chr")
        assert len(lines) == 2

    def test_skips_comments(self, monkeypatch, capsys):
        """run() skips comment lines."""
        monkeypatch.setattr(mod, "base_count",
                            lambda bam, mq, bq: mock_base_count())

        infile = io.StringIO("#header\nchr1\t100\tA\tG\n")
        args = type("Args", (), {
            "bam": "test.bam",
            "min_MQ": 20,
            "min_BQ": 13,
            "nproc": 1,
            "infile": infile,
        })()

        mod.run(args)

        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        assert len(lines) == 2
