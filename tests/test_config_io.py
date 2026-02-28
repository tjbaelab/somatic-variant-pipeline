"""Characterization tests for library/config.py I/O functions -- Layer 1 (pure logic).

Tests write_run_options, log_dir, save_hold_jid -- the functions
that do NOT call subprocess.
"""

import os
import pytest
from library.config import write_run_options, log_dir, save_hold_jid


class TestWriteRunOptions:
    def test_writes_header_and_options(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("#PATH\nPIPE_HOME=/foo\n")
        write_run_options(str(f), {"Q": "normal", "REFVER": "b37"})
        content = f.read_text()
        assert "#RUN_OPTIONS" in content
        assert "Q=normal\n" in content
        assert "REFVER=b37\n" in content

    def test_preserves_existing_content(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("#PATH\nPIPE_HOME=/foo\n")
        write_run_options(str(f), {"Q": "normal"})
        content = f.read_text()
        assert content.startswith("#PATH\nPIPE_HOME=/foo\n")

    def test_preserves_key_order(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("")
        write_run_options(str(f), {"A": "1", "B": "2", "C": "3"})
        lines = [l for l in f.read_text().strip().split("\n") if "=" in l]
        assert lines == ["A=1", "B=2", "C=3"]

    def test_ploidy_quoting(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("")
        write_run_options(str(f), {"RUN_GATK_HC": "True", "PLOIDY": '"2 3"'})
        content = f.read_text()
        assert "RUN_GATK_HC=True\n" in content
        assert 'PLOIDY="2 3"\n' in content


class TestLogDir:
    def test_creates_log_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = log_dir("SAMPLE1")
        assert os.path.isdir(tmp_path / "SAMPLE1" / "logs")

    def test_returns_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = log_dir("SAMPLE1")
        assert result == "SAMPLE1/logs"

    def test_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_dir("SAMPLE1")
        log_dir("SAMPLE1")  # Should not raise
        assert os.path.isdir(tmp_path / "SAMPLE1" / "logs")


class TestSaveHoldJid:
    def test_writes_jid(self, tmp_path):
        f = tmp_path / "hold_jid"
        save_hold_jid(str(f), "12345")
        assert f.read_text().strip() == "12345"

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "subdir" / "nested" / "hold_jid"
        save_hold_jid(str(f), "12345")
        assert f.exists()
        assert f.read_text().strip() == "12345"

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "hold_jid"
        save_hold_jid(str(f), "11111")
        save_hold_jid(str(f), "22222")
        assert f.read_text().strip() == "22222"
