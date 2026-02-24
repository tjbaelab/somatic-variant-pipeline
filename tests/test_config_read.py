"""Characterization tests for library/config.py:read_config -- Layer 2 (mocked conda).

read_config() calls subprocess.check_output for conda info.
We mock this to enable macOS testing without conda env.
"""

import os
import pytest
from library.config import read_config


class TestReadConfigB37:
    def test_returns_config_sections(self, mock_conda):
        config = read_config("b37", "bp")
        assert "PATH" in config
        assert "TOOLS" in config
        assert "RESOURCES" in config

    def test_path_section(self, mock_conda, fake_env_dir):
        config = read_config("b37", "bp")
        assert config["PATH"]["env_dir"] == fake_env_dir
        assert os.path.isdir(config["PATH"]["pipe_home"])

    def test_tools_substituted(self, mock_conda, fake_env_dir):
        config = read_config("b37", "bp")
        assert config["TOOLS"]["python3"] == fake_env_dir + "/bin/python3"
        assert config["TOOLS"]["bwa"] == fake_env_dir + "/bin/bwa"
        assert config["TOOLS"]["samtools"] == fake_env_dir + "/bin/samtools"

    def test_resources_substituted(self, mock_conda, pipe_home):
        config = read_config("b37", "bp")
        assert pipe_home in config["RESOURCES"]["ref"]
        assert "human_g1k_v37_decoy.fasta" in config["RESOURCES"]["ref"]

    def test_all_tools_present(self, mock_conda):
        config = read_config("b37", "bp")
        expected = [
            "python3", "java", "bwa", "samtools", "sambamba",
            "gatk", "gatk4", "picard", "bgzip", "tabix", "vt",
            "bcftools", "rootsys", "cnvnator", "liftover", "mfdir",
        ]
        for tool in expected:
            assert tool in config["TOOLS"], f"Missing tool: {tool}"

    def test_all_resources_present(self, mock_conda):
        config = read_config("b37", "bp")
        expected = [
            "refdir", "ref", "dbsnp", "mills", "indel1kg",
            "omni", "hapmap", "snp1kg", "mask1kg", "gnomad_snp",
            "ponfa", "hg19_to_hg38", "mfres",
        ]
        for res in expected:
            assert res in config["RESOURCES"], f"Missing resource: {res}"


class TestReadConfigHg19:
    def test_hg19_reference(self, mock_conda):
        config = read_config("hg19", "bp")
        assert "ucsc.hg19.fasta" in config["RESOURCES"]["ref"]

    def test_hg19_dbsnp(self, mock_conda):
        config = read_config("hg19", "bp")
        assert "dbsnp_138.hg19" in config["RESOURCES"]["dbsnp"]


class TestReadConfigHg38:
    def test_hg38_reference(self, mock_conda):
        config = read_config("hg38", "bp")
        assert "GRCh38" in config["RESOURCES"]["ref"]

    def test_hg38_dbsnp(self, mock_conda):
        config = read_config("hg38", "bp")
        assert "hg38" in config["RESOURCES"]["dbsnp"]


class TestReadConfigHg38Variants:
    def test_hg38_decoy_reference(self, mock_conda):
        config = read_config("hg38_decoy", "bp")
        assert "GRCh38_full_analysis_set_plus_decoy_hla" in config["RESOURCES"]["ref"]

    def test_hg38_v0_reference(self, mock_conda):
        config = read_config("hg38_v0", "bp")
        assert "Homo_sapiens_assembly38.fasta" in config["RESOURCES"]["ref"]

    def test_hg38_no_alt_gnomad_version(self, mock_conda):
        config = read_config("hg38_no_alt", "bp")
        assert "r3.1.2" in config["RESOURCES"]["gnomad_snp"]

    def test_hg38_decoy_gnomad_version(self, mock_conda):
        config = read_config("hg38_decoy", "bp")
        assert "r2.1.1" in config["RESOURCES"]["gnomad_snp"]

    def test_all_hg38_variants_have_tools(self, mock_conda):
        for ref in ["hg38_no_alt", "hg38_decoy", "hg38_v0"]:
            config = read_config(ref, "bp")
            assert "TOOLS" in config
            assert "samtools" in config["TOOLS"]


class TestReadConfigDefault:
    def test_default_is_b37(self, mock_conda):
        """read_config() with no reference arg defaults to b37."""
        config_default = read_config(conda_env="bp")
        config_b37 = read_config("b37", "bp")
        assert config_default["RESOURCES"]["ref"] == config_b37["RESOURCES"]["ref"]

    def test_unknown_reference_falls_back_to_default(self, mock_conda):
        """Unknown reference falls back to config.ini (symlink to b37)."""
        config = read_config("unknown_ref", "bp")
        assert "TOOLS" in config
        assert "RESOURCES" in config
