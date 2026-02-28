"""E2E smoke test: verify LocalQueue runs real shell scripts end-to-end.

Uses run_variant_calling.py (simplest pipeline: 1 submit) with --backend local
and a stub shell script to confirm commands actually execute.
"""

import os
import stat
import pytest
from pipeline import run_variant_calling as mod


class TestLocalE2E:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch, mock_conda):
        self.tmp = tmp_path
        monkeypatch.chdir(tmp_path)

        # Create stub job script that writes a marker file
        job_dir = tmp_path / "jobs" / "variant_calling"
        job_dir.mkdir(parents=True)
        stub = job_dir / "pre_3.run_variant_calling.sh"
        stub.write_text("#!/bin/bash\ntouch \"$1/e2e_marker\"\n")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

        # Point job_home to our stub directory
        monkeypatch.setattr(mod, "job_home", str(job_dir))

    def _sample_list(self, content):
        f = self.tmp / "samples.txt"
        f.write_text(content)
        return str(f)

    def test_local_backend_executes_script(self, monkeypatch):
        """LocalQueue actually runs the shell script and produces output."""
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
            "--backend", "local",
        ])

        mod.main()

        marker = self.tmp / "SAMPLE1" / "e2e_marker"
        assert marker.exists(), "Stub script did not execute"

    def test_local_backend_writes_run_info(self, monkeypatch):
        """run_info file is created before job execution."""
        sl = self._sample_list("SAMPLE1\tSAMPLE1.bam\t/data\n")
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
            "--backend", "local",
        ])

        mod.main()

        run_info = self.tmp / "SAMPLE1" / "run_info"
        assert run_info.exists()
        content = run_info.read_text()
        assert "Q=normal" in content
        assert "FILETYPE=bam" in content

    def test_local_backend_multiple_samples(self, monkeypatch):
        """Multiple samples each get their own script execution."""
        sl = self._sample_list(
            "SAMPLE1\tSAMPLE1.bam\t/data\n"
            "SAMPLE2\tSAMPLE2.bam\t/data\n"
        )
        monkeypatch.setattr("sys.argv", [
            "run_variant_calling.py", "-q", "normal",
            "--sample-list", sl, "-f", "bam",
            "--backend", "local",
        ])

        mod.main()

        assert (self.tmp / "SAMPLE1" / "e2e_marker").exists()
        assert (self.tmp / "SAMPLE2" / "e2e_marker").exists()
