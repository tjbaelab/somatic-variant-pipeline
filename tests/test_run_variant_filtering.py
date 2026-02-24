"""Characterization tests for jobs/run_variant_filtering.py -- Layer 2.

Tests argument parsing, SLURM option formatting, sample iteration,
run_info contract generation, and vcf_directory branching.
"""

import os
import pytest
from pipeline import run_variant_filtering as mod


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
        assert "--parsable" in result

    def test_with_dependency(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mod.opt("SAMPLE1", "normal", jid="12345")
        assert "-d afterok:12345" in result

    def test_no_dependency_by_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mod.opt("SAMPLE1", "normal")
        assert "afterok" not in result


class TestParseArgs:
    def test_required_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
        ])
        args = mod.parse_args()
        assert args.queue == "normal"
        assert args.sample_list == "samples.txt"

    def test_defaults(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
        ])
        args = mod.parse_args()
        assert args.reference == "b37"
        assert args.conda_env == "bp"
        assert args.align_fmt == "cram"
        assert args.run_gatk_hc is False
        assert args.skip_cnvnator is False
        assert args.run_filters is True  # default True for filtering
        assert args.vcf_directory is None

    def test_vcf_directory(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
            "-v", "/path/to/vcfs",
        ])
        args = mod.parse_args()
        assert args.vcf_directory == "/path/to/vcfs"


class TestMain:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch, mock_conda):
        self.mock_q = MockQueue()
        self.tmp = tmp_path
        monkeypatch.setattr(mod, "q", self.mock_q)
        monkeypatch.chdir(tmp_path)

    def _sample_list(self, content):
        f = self.tmp / "samples.txt"
        f.write_text(content)
        return str(f)

    def test_single_bam_submits_one_job(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        assert len(self.mock_q.calls) == 1
        assert "start_variant_filtering.sh" in self.mock_q.calls[0]["cmd"]

    def test_writes_run_info(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        run_info_file = self.tmp / "SAMPLE1" / "run_info"
        assert run_info_file.exists()
        content = run_info_file.read_text()
        assert "Q=normal" in content
        assert "FILETYPE=bam" in content
        assert "REFVER=b37" in content

    def test_vcf_directory_in_command(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
            "-v", "/vcfs",
        ])

        mod.main()

        cmd = self.mock_q.calls[0]["cmd"]
        assert "/vcfs" in cmd

    def test_no_vcf_directory_default(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        cmd = self.mock_q.calls[0]["cmd"]
        # Without -v, command has only sample arg (no vcf_dir)
        assert cmd.endswith("SAMPLE1")

    def test_skips_sample_with_existing_jobs(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_filtering.py", "-q", "normal",
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
            "run_variant_filtering.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        assert len(self.mock_q.calls) == 2
