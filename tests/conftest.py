import os
import pytest


@pytest.fixture
def pipe_home():
    """Path to the repository root."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def fake_env_dir(tmp_path):
    """Temporary directory mimicking a conda environment with bin/ subdir."""
    env_dir = tmp_path / "envs" / "bp"
    (env_dir / "bin").mkdir(parents=True)
    return str(env_dir)


@pytest.fixture
def mock_conda(monkeypatch, fake_env_dir):
    """Mock conda subprocess to return fake_env_dir."""
    def fake_check_output(*args, **kwargs):
        return fake_env_dir + "\n"
    monkeypatch.setattr("subprocess.check_output", fake_check_output)
    return fake_env_dir


@pytest.fixture
def sample_list_file(tmp_path):
    """Temporary sample list with test entries."""
    content = (
        "# Comment line\n"
        "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data/SAMPLE1\n"
        "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data/SAMPLE1\n"
        "SAMPLE2\tSAMPLE2.bam\t/data/SAMPLE2\n"
    )
    f = tmp_path / "sample_list.txt"
    f.write_text(content)
    return str(f)
