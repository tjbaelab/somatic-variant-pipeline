"""Characterization tests for jobs/run_variant_calling.py -- Layer 2.

Tests argument parsing, SLURM option formatting, sample iteration,
run_info contract generation, and error conditions.
"""

import os
import pytest
from pipeline import run_variant_calling as mod


class MockQueue:
    """Records submit() calls without invoking sbatch."""

    def __init__(self):
        self.calls = []
        self._jid = 0
        self.run_jid = None

    def submit(self, q_opt, cmd):
        self._jid += 1
        jid = str(self._jid)
        self.calls.append({"q_opt": q_opt, "cmd": cmd, "jid": jid})
        return jid

    def set_run_jid(self, fname, new=False):
        self.run_jid = fname

    def num_run_jid_in_queue(self, fname):
        return 0


class TestOpt:
    def test_basic_format(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mod.opt("SAMPLE1", "normal")
        assert "--partition=normal" in result
        assert "%x.%j.stdout" in result
        assert "%x.%j.stderr" in result
        assert "--parsable" in result

    def test_with_dependency(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mod.opt("SAMPLE1", "normal", jid="12345")
        assert "-d afterok:12345" in result
        assert "--partition=normal" in result

    def test_no_dependency_by_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mod.opt("SAMPLE1", "normal")
        assert "afterok" not in result


class TestParseArgs:
    def test_required_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
        ])
        args = mod.parse_args()
        assert args.queue == "normal"
        assert args.sample_list == "samples.txt"

    def test_defaults(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
        ])
        args = mod.parse_args()
        assert args.reference == "b37"
        assert args.conda_env == "bp"
        assert args.align_fmt == "cram"
        assert args.con_down_limit == 6
        assert args.run_gatk_hc is False
        assert args.max_gaussians == 4
        assert args.run_mutect_single is False
        assert args.skip_cnvnator is False
        assert args.run_filters is False

    def test_ploidy_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
            "-p", "2", "3",
        ])
        args = mod.parse_args()
        assert args.run_gatk_hc == [2, 3]


class TestMain:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch, mock_conda):
        self.mock_q = MockQueue()
        self.tmp = tmp_path
        monkeypatch.setattr(mod, "create_queue", lambda: self.mock_q)
        monkeypatch.chdir(tmp_path)

    def _sample_list(self, content):
        f = self.tmp / "samples.txt"
        f.write_text(content)
        return str(f)

    def test_single_bam_submits_one_job(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        assert len(self.mock_q.calls) == 1
        assert "pre_3.run_variant_calling.sh" in self.mock_q.calls[0]["cmd"]

    def test_writes_run_info(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        run_info_file = self.tmp / "SAMPLE1" / "run_info"
        assert run_info_file.exists()
        content = run_info_file.read_text()
        assert "Q=normal" in content
        assert "FILETYPE=bam" in content
        assert "REFVER=b37" in content

    def test_run_info_gatk_hc_ploidy(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
            "-p", "2", "3",
        ])

        mod.main()

        content = (self.tmp / "SAMPLE1" / "run_info").read_text()
        assert "RUN_GATK_HC=True" in content
        assert 'PLOIDY="2 3"' in content

    def test_fastq_raises(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.fastq.gz\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        with pytest.raises(Exception, match="should be bam or cram"):
            mod.main()

    def test_cram_bam_mismatch_raises(self, monkeypatch):
        """Default -f cram with bam input raises alignment format error."""
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl,
            # default -f cram
        ])

        with pytest.raises(Exception, match="alignment format"):
            mod.main()

    def test_skips_sample_with_existing_jobs(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])
        self.mock_q.num_run_jid_in_queue = lambda fname: 1

        mod.main()

        assert len(self.mock_q.calls) == 0

    def test_multiple_samples(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.bam\t/data\n"
            "SAMPLE2\tSAMPLE2.bam\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        assert len(self.mock_q.calls) == 2
