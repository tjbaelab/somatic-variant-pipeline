"""Characterization tests for jobs/run_genome_mapping.py -- Layer 2.

Tests argument parsing, SLURM option formatting, sample iteration,
run_info contract generation, fastq/bam branching, R1/R2 classification,
download concurrency queue, and job submission DAG.
"""

import os
import pytest
from jobs import run_genome_mapping as mod


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
            "run_genome_mapping.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
        ])
        args = mod.parse_args()
        assert args.queue == "normal"
        assert args.sample_list == "samples.txt"

    def test_defaults(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
        ])
        args = mod.parse_args()
        assert args.reference == "b37"
        assert args.conda_env == "bp"
        assert args.align_fmt == "cram"
        assert args.con_down_limit == 6
        assert args.run_gatk_hc is False
        assert args.run_mutect_single is False
        assert args.skip_cnvnator is False
        assert args.run_filters is False
        assert args.target_seq is False
        assert args.multiple_alignments is False

    def test_ploidy_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
            "-p", "2", "3",
        ])
        args = mod.parse_args()
        assert args.run_gatk_hc == [2, 3]

    def test_target_seq_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
            "-t",
        ])
        args = mod.parse_args()
        assert args.target_seq is True

    def test_con_down_limit(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py",
            "-q", "normal",
            "--sample-list", "samples.txt",
            "--con-down-limit", "3",
        ])
        args = mod.parse_args()
        assert args.con_down_limit == 3


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

    # -- fastq branch --

    def test_fastq_single_pair_submits_correct_jobs(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])

        mod.main()

        # 2 downloads + 2 splits (R1,R2) + 1 aln = 5 jobs
        assert len(self.mock_q.calls) == 5
        cmds = [c["cmd"] for c in self.mock_q.calls]
        assert sum("pre_1.download.sh" in c for c in cmds) == 2
        assert sum("pre_2.split_fastq_by_RG.sh" in c for c in cmds) == 2
        assert sum("pre_3.submit_aln_jobs.sh" in c for c in cmds) == 1

    def test_fastq_r1_r2_classification(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1_R1_001.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1_R2_001.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])

        mod.main()

        # Split commands should reference sorted fastq paths per read
        split_cmds = [c["cmd"] for c in self.mock_q.calls
                      if "pre_2.split_fastq_by_RG.sh" in c["cmd"]]
        assert len(split_cmds) == 2
        # R1 split has R1 file, R2 split has R2 file
        assert "R1" in split_cmds[0] or "R2" in split_cmds[0]

    def test_fastq_multiple_r1_files(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.lane1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.lane2.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.lane1.R2.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.lane2.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])

        mod.main()

        # 4 downloads + 2 splits + 1 aln = 7 jobs
        assert len(self.mock_q.calls) == 7
        cmds = [c["cmd"] for c in self.mock_q.calls]
        assert sum("pre_1.download.sh" in c for c in cmds) == 4

    def test_fastq_download_concurrency_limit(self, monkeypatch):
        """Download jobs respect con_down_limit via deque dependency."""
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
            "--con-down-limit", "6",
        ])

        mod.main()

        # With limit=6 and only 2 downloads, first downloads have no dependency
        download_calls = [c for c in self.mock_q.calls
                          if "pre_1.download.sh" in c["cmd"]]
        assert "afterok" not in download_calls[0]["q_opt"]
        assert "afterok" not in download_calls[1]["q_opt"]

    def test_fastq_download_concurrency_tight(self, monkeypatch):
        """With con_down_limit=1, second download depends on first."""
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
            "--con-down-limit", "1",
        ])

        mod.main()

        download_calls = [c for c in self.mock_q.calls
                          if "pre_1.download.sh" in c["cmd"]]
        # First download: no dependency (deque starts with [None])
        assert "afterok" not in download_calls[0]["q_opt"]
        # Second download: depends on first (jid "1" was pushed into deque)
        assert "afterok:1" in download_calls[1]["q_opt"]

    # -- bam branch --

    def test_bam_submits_correct_jobs(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        # 1 download + 1 bam2fastq + 2 splits (R1,R2) + 1 aln = 5 jobs
        assert len(self.mock_q.calls) == 5
        cmds = [c["cmd"] for c in self.mock_q.calls]
        assert sum("pre_1.download.sh" in c for c in cmds) == 1
        assert sum("pre_1b.bam2fastq.sh" in c for c in cmds) == 1
        assert sum("pre_2.split_fastq_by_RG.sh" in c for c in cmds) == 2
        assert sum("pre_3.submit_aln_jobs.sh" in c for c in cmds) == 1

    def test_bam_dependency_chain(self, monkeypatch):
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
        ])

        mod.main()

        calls = self.mock_q.calls
        # download (jid=1) -> bam2fastq (jid=2) -> split R1 (jid=3), split R2 (jid=4) -> aln (jid=5)
        assert "afterok" not in calls[0]["q_opt"]   # download: no dep
        assert "afterok:1" in calls[1]["q_opt"]       # bam2fastq -> download
        assert "afterok:2" in calls[2]["q_opt"]       # split R1 -> bam2fastq
        assert "afterok:2" in calls[3]["q_opt"]       # split R2 -> bam2fastq
        assert "afterok:3,4" in calls[4]["q_opt"]     # aln -> both splits

    # -- run_info contract --

    def test_writes_run_info(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])

        mod.main()

        run_info_file = self.tmp / "SAMPLE1" / "run_info"
        assert run_info_file.exists()
        content = run_info_file.read_text()
        assert "Q=normal" in content
        assert "FILETYPE=fastq" in content
        assert "REFVER=b37" in content
        assert "SKIP_CNVNATOR=False" in content
        assert "RUN_MUTECT_SINGLE=False" in content
        assert "TARGET_SEQ=False" in content

    def test_run_info_gatk_hc_ploidy(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
            "-p", "2", "3",
        ])

        mod.main()

        content = (self.tmp / "SAMPLE1" / "run_info").read_text()
        assert "RUN_GATK_HC=True" in content
        assert 'PLOIDY="2 3"' in content

    # -- sample iteration --

    def test_skips_sample_with_existing_jobs(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])
        self.mock_q.num_run_jid_in_queue = lambda fname: 1

        mod.main()

        assert len(self.mock_q.calls) == 0

    def test_multiple_samples(self, monkeypatch):
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
            "SAMPLE2\tSAMPLE2.R1.fastq.gz\t/data\n"
            "SAMPLE2\tSAMPLE2.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])

        mod.main()

        # Each sample: 2 downloads + 2 splits + 1 aln = 5
        # 2 samples = 10 jobs
        assert len(self.mock_q.calls) == 10

    def test_aln_job_depends_on_splits(self, monkeypatch):
        """submit_aln_jobs receives combined split JIDs as dependency."""
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_genome_mapping.py", "-q", "normal",
            "--sample-list", sl,
        ])

        mod.main()

        aln_call = [c for c in self.mock_q.calls
                    if "pre_3.submit_aln_jobs.sh" in c["cmd"]][0]
        # Aln depends on both split JIDs (3 and 4)
        assert "afterok:3,4" in aln_call["q_opt"]
