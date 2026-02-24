"""Characterization tests for library/config.py:run_info() -- Layer 2 (mocked conda).

Tests the run_info() function that creates the shell-sourceable
config file -- the contract between Python orchestration and
shell execution scripts.
"""

import pytest
from library.config import run_info


class TestRunInfo:
    def test_creates_file(self, tmp_path, mock_conda):
        f = tmp_path / "sample" / "run_info"
        run_info(str(f), "b37", "bp")
        assert f.exists()

    def test_creates_parent_dirs(self, tmp_path, mock_conda):
        f = tmp_path / "deep" / "nested" / "run_info"
        run_info(str(f), "b37", "bp")
        assert f.exists()

    def test_has_path_section(self, tmp_path, mock_conda, pipe_home):
        f = tmp_path / "run_info"
        run_info(str(f), "b37", "bp")
        content = f.read_text()
        assert "#PATH" in content
        assert "PIPE_HOME={}".format(pipe_home) in content

    def test_has_env_dir(self, tmp_path, mock_conda, fake_env_dir):
        f = tmp_path / "run_info"
        run_info(str(f), "b37", "bp")
        content = f.read_text()
        assert "ENV_DIR={}".format(fake_env_dir) in content

    def test_has_tools_section(self, tmp_path, mock_conda):
        f = tmp_path / "run_info"
        run_info(str(f), "b37", "bp")
        content = f.read_text()
        assert "\n#TOOLS\n" in content

    def test_has_resources_section(self, tmp_path, mock_conda):
        f = tmp_path / "run_info"
        run_info(str(f), "b37", "bp")
        content = f.read_text()
        assert "\n#RESOURCES\n" in content

    def test_tools_keys_uppercased(self, tmp_path, mock_conda):
        f = tmp_path / "run_info"
        run_info(str(f), "b37", "bp")
        content = f.read_text()
        assert "SAMTOOLS=" in content
        assert "BWA=" in content
        assert "GATK4=" in content

    def test_shell_sourceable_format(self, tmp_path, mock_conda):
        """Every non-empty, non-comment line must be KEY=VALUE."""
        f = tmp_path / "run_info"
        run_info(str(f), "b37", "bp")
        for line in f.read_text().splitlines():
            if line.strip() == "" or line.startswith("#"):
                continue
            assert "=" in line, "Line not KEY=VALUE format: {}".format(line)

    def test_hg19_uses_hg19_config(self, tmp_path, mock_conda):
        f = tmp_path / "run_info"
        run_info(str(f), "hg19", "bp")
        content = f.read_text()
        # hg19 config references ucsc.hg19 or hg19 resources
        assert "hg19" in content.lower() or "ucsc" in content.lower()

    def test_hg38_uses_hg38_config(self, tmp_path, mock_conda):
        f = tmp_path / "run_info"
        run_info(str(f), "hg38", "bp")
        content = f.read_text()
        assert "hg38" in content.lower() or "grch38" in content.lower()
