"""Characterization tests for submitter DAG structure -- Layer 2 (mocked queue).

Captures the sequence of submit() calls for each submitter,
forming a safety net against unintended DAG changes during refactoring.

Each submitter is tested by:
  1. Replacing GridEngineQueue with a recording mock
  2. Mocking filesystem operations (log_dir, save_hold_jid, glob)
  3. Running main() with synthetic args
  4. Verifying the submit call sequence and dependency chain
"""

import importlib
import os
import sys
import pytest
import library.job_queue as jq_mod


class MockQueue:
    """Records all submit() calls for DAG verification."""

    def __init__(self):
        self.calls = []
        self._jid_counter = 0
        self.run_jid = None

    def submit(self, q_opt_str, cmd_str):
        self._jid_counter += 1
        jid = str(self._jid_counter)
        self.calls.append({"q_opt": q_opt_str, "cmd": cmd_str, "jid": jid})
        return jid

    def set_run_jid(self, fname, new=False):
        self.run_jid = fname

    def num_run_jid_in_queue(self, fname):
        return 0


def script_names(calls):
    """Extract script filename from each submit call's cmd string."""
    return [os.path.basename(c["cmd"].split()[0]) for c in calls]


def dependencies(calls):
    """Extract dependency JIDs from q_opt strings."""
    deps = []
    for c in calls:
        opt = c["q_opt"]
        if "afterok:" in opt:
            dep_str = opt.split("afterok:")[1].split()[0]
            deps.append(dep_str)
        else:
            deps.append(None)
    return deps


# ---------------------------------------------------------------------------
# submit_aln_jobs
# ---------------------------------------------------------------------------

class TestAlignmentDAG:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.mock_q = MockQueue()
        self.tmp_path = tmp_path

        from pipeline import submit_aln_jobs
        self.mod = submit_aln_jobs

        monkeypatch.setattr(jq_mod, "log_dir",
                            lambda sample: str(tmp_path / sample / "logs"))
        monkeypatch.setattr(self.mod, "save_hold_jid",
                            lambda fname, jid: None)
        monkeypatch.setattr(self.mod, "create_queue",
                            lambda: self.mock_q)
        monkeypatch.chdir(tmp_path)

    def test_non_target_seq_dag(self, monkeypatch):
        """Full alignment DAG: aln_1 x2 -> merge -> markdup -> indel -> bqsr_array -> bqsr_gather -> post_1, post_2."""
        monkeypatch.setattr("glob.glob", lambda pattern: [
            "SAMPLE1/fastq/SAMPLE1.PU1.R1.fastq.gz",
            "SAMPLE1/fastq/SAMPLE1.PU2.R1.fastq.gz",
        ])
        monkeypatch.setattr("sys.argv", [
            "submit_aln_jobs.py", "--queue", "normal", "--sample-name", "SAMPLE1",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert len(scripts) == 9

        # First 2: aln_1 per platform unit
        assert sorted(scripts[:2]) == ["aln_1.align_sort.sh", "aln_1.align_sort.sh"]
        # Sequential chain
        assert scripts[2] == "aln_2.merge_bam.sh"
        assert scripts[3] == "aln_3.markdup.sh"
        assert scripts[4] == "aln_4.indel_realign.sh"
        assert scripts[5] == "aln_5.bqsr_array.sh"
        assert scripts[6] == "aln_5.bqsr_gather.sh"
        # Fork: both post steps
        assert scripts[7] == "post_1.unmapped_reads.sh"
        assert scripts[8] == "post_2.run_variant_calling.sh"

    def test_target_seq_dag(self, monkeypatch):
        """Target-seq skips markdup, indel_realign, bqsr steps."""
        monkeypatch.setattr("glob.glob", lambda pattern: [
            "SAMPLE1/fastq/SAMPLE1.PU1.R1.fastq.gz",
        ])
        monkeypatch.setattr("sys.argv", [
            "submit_aln_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--target-seq",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert len(scripts) == 4
        assert scripts[0] == "aln_1.align_sort.sh"
        assert scripts[1] == "aln_2.merge_bam.sh"
        assert scripts[2] == "post_1.unmapped_reads.sh"
        assert scripts[3] == "post_2.run_variant_calling.sh"

    def test_dependency_chain(self, monkeypatch):
        """Verify correct JID dependency threading."""
        monkeypatch.setattr("glob.glob", lambda pattern: [
            "SAMPLE1/fastq/SAMPLE1.PU1.R1.fastq.gz",
            "SAMPLE1/fastq/SAMPLE1.PU2.R1.fastq.gz",
        ])
        monkeypatch.setattr("sys.argv", [
            "submit_aln_jobs.py", "--queue", "normal", "--sample-name", "SAMPLE1",
        ])

        self.mod.main()

        deps = dependencies(self.mock_q.calls)
        # aln_1 calls: no dependencies
        assert deps[0] is None
        assert deps[1] is None
        # merge depends on all aln_1 JIDs
        assert set(deps[2].split(",")) == {"1", "2"}
        # Sequential chain: each depends on previous
        assert deps[3] == "3"   # markdup -> merge
        assert deps[4] == "4"   # indel -> markdup
        assert deps[5] == "5"   # bqsr_array -> indel
        assert deps[6] == "6"   # bqsr_gather -> bqsr_array
        # Both post steps depend on bqsr_gather (aln_jid)
        assert deps[7] == "7"   # post_1 -> bqsr_gather
        assert deps[8] == "7"   # post_2 -> bqsr_gather

    def test_single_pu(self, monkeypatch):
        """Single platform unit: only one aln_1 call."""
        monkeypatch.setattr("glob.glob", lambda pattern: [
            "SAMPLE1/fastq/SAMPLE1.PU1.R1.fastq.gz",
        ])
        monkeypatch.setattr("sys.argv", [
            "submit_aln_jobs.py", "--queue", "normal", "--sample-name", "SAMPLE1",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert scripts[0] == "aln_1.align_sort.sh"
        assert scripts[1] == "aln_2.merge_bam.sh"
        assert len(scripts) == 8  # 1 less aln_1 than 2-PU case

    def test_mapping_only_dag(self, monkeypatch):
        """--mapping-only stops after merge_bam, skipping all post-alignment steps."""
        monkeypatch.setattr("glob.glob", lambda pattern: [
            "SAMPLE1/fastq/SAMPLE1.PU1.R1.fastq.gz",
            "SAMPLE1/fastq/SAMPLE1.PU2.R1.fastq.gz",
        ])
        monkeypatch.setattr("sys.argv", [
            "submit_aln_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--mapping-only",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert len(scripts) == 3  # 2 aln_1 + 1 merge
        assert sorted(scripts[:2]) == ["aln_1.align_sort.sh", "aln_1.align_sort.sh"]
        assert scripts[2] == "aln_2.merge_bam.sh"


# ---------------------------------------------------------------------------
# submit_gatk-hc_jobs
# ---------------------------------------------------------------------------

class TestHaplotypeCallerDAG:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.mock_q = MockQueue()
        self.mod = importlib.import_module("pipeline.submit_gatk-hc_jobs")

        monkeypatch.setattr(self.mod, "q", self.mock_q)
        monkeypatch.setattr(jq_mod, "log_dir",
                            lambda sample: str(tmp_path / sample / "logs"))
        monkeypatch.setattr(self.mod, "save_hold_jid",
                            lambda fname, jid: None)
        monkeypatch.chdir(tmp_path)

    def test_single_ploidy_dag(self, monkeypatch):
        """Ploidy=2: hc_1 -> hc_2 -> hc_3 -> start_filtering."""
        monkeypatch.setattr("sys.argv", [
            "submit_gatk-hc_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert len(scripts) == 4
        assert scripts[0] == "gatk-hc_1.call.sh"
        assert scripts[1] == "gatk-hc_2.concat_vcf.sh"
        assert scripts[2] == "gatk-hc_3.vqsr.sh"
        assert scripts[3] == "start_variant_filtering.sh"

    def test_single_ploidy_dependencies(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "submit_gatk-hc_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
        ])

        self.mod.main()

        deps = dependencies(self.mock_q.calls)
        assert deps[0] is None     # hc_1: no dep
        assert deps[1] == "1"      # hc_2 -> hc_1
        assert deps[2] == "2"      # hc_3 -> hc_2
        assert deps[3] == "3"      # start_filtering -> hc_3

    def test_dual_ploidy_dag(self, monkeypatch):
        """Ploidy=[2,3]: two parallel hc chains -> start_filtering."""
        monkeypatch.setattr("sys.argv", [
            "submit_gatk-hc_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2", "3",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert len(scripts) == 7  # 3 per ploidy + 1 start_filtering
        # Ploidy 2 chain
        assert scripts[0] == "gatk-hc_1.call.sh"
        assert scripts[1] == "gatk-hc_2.concat_vcf.sh"
        assert scripts[2] == "gatk-hc_3.vqsr.sh"
        # Ploidy 3 chain
        assert scripts[3] == "gatk-hc_1.call.sh"
        assert scripts[4] == "gatk-hc_2.concat_vcf.sh"
        assert scripts[5] == "gatk-hc_3.vqsr.sh"
        # Merge
        assert scripts[6] == "start_variant_filtering.sh"

    def test_dual_ploidy_dependencies(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "submit_gatk-hc_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2", "3",
        ])

        self.mod.main()

        deps = dependencies(self.mock_q.calls)
        # Ploidy 2 chain
        assert deps[0] is None     # hc_1 p2
        assert deps[1] == "1"      # hc_2 p2
        assert deps[2] == "2"      # hc_3 p2
        # Ploidy 3 chain
        assert deps[3] is None     # hc_1 p3
        assert deps[4] == "4"      # hc_2 p3
        assert deps[5] == "5"      # hc_3 p3
        # start_filtering depends on both vqsr completions
        assert set(deps[6].split(",")) == {"3", "6"}

    def test_malign_flag_adds_resources(self, monkeypatch):
        """--multiple-alignments adds extra sbatch resource args."""
        monkeypatch.setattr("sys.argv", [
            "submit_gatk-hc_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
            "--multiple-alignments",
        ])

        self.mod.main()

        # hc_1 call should have extra resource flags
        hc1_opts = self.mock_q.calls[0]["q_opt"]
        assert "--cpus-per-task=8" in hc1_opts
        assert "--mem=16G" in hc1_opts


# ---------------------------------------------------------------------------
# submit_filtering_jobs
# ---------------------------------------------------------------------------

class TestFilteringDAG:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.mock_q = MockQueue()

        from pipeline import submit_filtering_jobs
        self.mod = submit_filtering_jobs

        monkeypatch.setattr(self.mod, "q", self.mock_q)
        monkeypatch.setattr(jq_mod, "log_dir",
                            lambda sample: str(tmp_path / sample / "logs"))
        monkeypatch.setattr(self.mod, "save_hold_jid",
                            lambda fname, jid: None)
        monkeypatch.chdir(tmp_path)

    def test_single_ploidy_dag(self, monkeypatch):
        """Non-malign, ploidy=2: CNVnator + gnomAD -> PASS -> VAF -> CNV -> mayo/mosaic -> PON -> filtered."""
        monkeypatch.setattr("sys.argv", [
            "submit_filtering_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert len(scripts) == 10
        assert scripts[0] == "A.CNVnator_mk_root.sh"
        assert scripts[1] == "A.gnomAD_germline_filter.sh"
        assert scripts[2] == "B.PASS_P.sh"
        assert scripts[3] == "C.VAF_filters.sh"
        assert scripts[4] == "D.CNVnator_genotype_filter.sh"
        assert scripts[5] == "E.mayo_filters.sh"
        assert scripts[6] == "F.PON_mask.sh"
        assert scripts[7] == "E.MosaicForecast.sh"
        assert scripts[8] == "F.PON_mask.sh"
        assert scripts[9] == "G.filtered_VCF.sh"

    def test_single_ploidy_dependencies(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "submit_filtering_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
        ])

        self.mod.main()

        deps = dependencies(self.mock_q.calls)
        assert deps[0] is None           # CNVnator: no dep
        assert deps[1] is None           # gnomAD: no dep
        assert deps[2] == "2"            # PASS -> gnomAD
        assert deps[3] == "3"            # VAF -> PASS
        assert set(deps[4].split(",")) == {"1", "4"}   # CNV -> CNVnator + VAF
        assert deps[5] == "5"            # mayo -> CNV
        assert deps[6] == "6"            # PON_mayo -> mayo
        assert deps[7] == "5"            # mosaic -> CNV
        assert deps[8] == "8"            # PON_mosaic -> mosaic
        assert set(deps[9].split(",")) == {"7", "9"}   # filtered -> both PONs

    def test_malign_flag_uses_malign_scripts(self, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "submit_filtering_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
            "--multiple-alignments",
        ])

        self.mod.main()

        scripts = script_names(self.mock_q.calls)
        assert scripts[0] == "A.CNVnator_mk_root.malign.sh"
        assert scripts[3] == "C.VAF_filters.malign.sh"
        assert scripts[5] == "E.mayo_filters.malign.sh"
        assert scripts[7] == "E.MosaicForecast.malign.sh"

    def test_dag_structure_preserved_with_malign(self, monkeypatch):
        """malign flag changes script names but not DAG structure."""
        monkeypatch.setattr("sys.argv", [
            "submit_filtering_jobs.py", "--queue", "normal",
            "--sample-name", "SAMPLE1", "--ploidy", "2",
            "--multiple-alignments",
        ])

        self.mod.main()

        deps = dependencies(self.mock_q.calls)
        # Same dependency structure as non-malign
        assert deps[0] is None
        assert deps[1] is None
        assert deps[2] == "2"
        assert deps[3] == "3"
        assert set(deps[4].split(",")) == {"1", "4"}
        assert deps[5] == "5"
        assert deps[6] == "6"
        assert deps[7] == "5"
        assert deps[8] == "8"
        assert set(deps[9].split(",")) == {"7", "9"}
