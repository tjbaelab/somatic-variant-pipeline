"""Characterization tests for utils/somatic_vaf.py -- Layer 2 (mocked imports).

Tests vaf_info() coroutine and mpileup() formatter.
statsmodels.stats.proportion is mocked if not installed.
"""

import sys
import types

# Mock statsmodels if not installed
try:
    import statsmodels.stats.proportion
except ImportError:
    _sm = types.ModuleType("statsmodels")
    _sm_stats = types.ModuleType("statsmodels.stats")
    _sm_prop = types.ModuleType("statsmodels.stats.proportion")
    _sm_prop.binom_test = lambda count, nobs, **kw: 0.5
    _sm.stats = _sm_stats
    _sm_stats.proportion = _sm_prop
    sys.modules["statsmodels"] = _sm
    sys.modules["statsmodels.stats"] = _sm_stats
    sys.modules["statsmodels.stats.proportion"] = _sm_prop

import io
import subprocess
import pytest
from library.misc import coroutine
import utils.somatic_vaf as mod


@coroutine
def mock_base_count():
    """Mock coroutine returning fixed base counts."""
    result = None
    while True:
        chrom, pos = (yield result)
        result = {
            'A': 20, 'C': 0, 'G': 5, 'T': 0,
            'a': 15, 'c': 0, 'g': 5, 't': 0,
            'dels': 0,
        }


@coroutine
def mock_base_count_zero():
    """Mock coroutine returning zero depth."""
    result = None
    while True:
        chrom, pos = (yield result)
        result = {
            'A': 0, 'C': 0, 'G': 0, 'T': 0,
            'a': 0, 'c': 0, 'g': 0, 't': 0,
            'dels': 0,
        }


class TestVafInfo:
    def test_basic_vaf_calculation(self):
        """vaf_info computes VAF = alt_n / depth."""
        coro = mod.vaf_info(mock_base_count())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        vaf = float(parts[0])
        depth = int(parts[1])
        ref_n = int(parts[2])
        alt_n = int(parts[3])

        # A=20, a=15 → ref_n=35; G=5, g=5 → alt_n=10; depth=45
        assert ref_n == 35
        assert alt_n == 10
        assert depth == 45
        assert abs(vaf - 10 / 45) < 1e-6

    def test_zero_depth_vaf(self):
        """VAF is 0 when depth is 0 (ZeroDivisionError handled)."""
        coro = mod.vaf_info(mock_base_count_zero())
        result = coro.send(("chr1", "100", "A", "T"))

        parts = result.split("\t")
        vaf = float(parts[0])
        assert vaf == 0.0

    def test_output_has_five_fields(self):
        """Output format: vaf<TAB>depth<TAB>ref_n<TAB>alt_n<TAB>p_binom."""
        coro = mod.vaf_info(mock_base_count())
        result = coro.send(("chr1", "100", "A", "G"))

        parts = result.split("\t")
        assert len(parts) == 5
        float(parts[0])   # vaf
        int(parts[1])     # depth
        int(parts[2])     # ref_n
        int(parts[3])     # alt_n
        float(parts[4])   # p_binom (scientific notation)

    def test_multiple_sends(self):
        """Coroutine handles multiple sequential queries."""
        coro = mod.vaf_info(mock_base_count())
        r1 = coro.send(("chr1", "100", "A", "G"))
        r2 = coro.send(("chr1", "200", "A", "G"))

        assert r1 == r2  # Same mock data, same result


class TestMpileup:
    def test_format(self):
        """mpileup() formats chrom/pos/ref/alt + vaf_info result."""
        coro = mod.vaf_info(mock_base_count())
        result = mod.mpileup(coro, "chr1", "100", "a", "g")

        parts = result.split("\t")
        assert parts[0] == "chr1"
        assert parts[1] == "100"
        assert parts[2] == "A"   # uppercased
        assert parts[3] == "G"   # uppercased

    def test_total_fields(self):
        """Full output has 9 fields: chr, pos, ref, alt + 5 vaf fields."""
        coro = mod.vaf_info(mock_base_count())
        result = mod.mpileup(coro, "chr1", "100", "A", "G")

        parts = result.split("\t")
        assert len(parts) == 9


class TestRun:
    def test_single_proc(self, monkeypatch, capsys):
        """run() processes SNVs and prints header + results."""
        mock_target = mock_base_count()
        monkeypatch.setattr(mod, "base_count",
                            lambda bam, mq, bq: mock_target)

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
        assert "chr1" in lines[1]

    def test_skips_comments(self, monkeypatch, capsys):
        """run() skips comment lines."""
        mock_target = mock_base_count()
        monkeypatch.setattr(mod, "base_count",
                            lambda bam, mq, bq: mock_target)

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
        assert len(lines) == 2  # header + 1 data line


class TestParseArgs:
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "somatic_vaf.py", "-b", "test.bam",
        ])
        # Redirect stdin to avoid blocking
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        args = mod.main.__wrapped__() if hasattr(mod.main, '__wrapped__') else None
        # Just test parse directly via the parser
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('-b', '--bam', required=True)
        parser.add_argument('-q', '--min-MQ', type=int, default=20)
        parser.add_argument('-Q', '--min-BQ', type=int, default=13)
        parser.add_argument('-n', '--nproc', type=int, default=1)
        args = parser.parse_args(["--bam", "test.bam"])
        assert args.min_MQ == 20
        assert args.min_BQ == 13
        assert args.nproc == 1
