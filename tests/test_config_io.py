"""Characterization tests for library/config.py I/O functions -- Layer 1 (pure logic).

Tests run_info_append, log_dir, save_hold_jid -- the functions that
do NOT call subprocess.
"""

import os
import pytest
from library.config import run_info_append, log_dir, save_hold_jid


class TestRunInfoAppend:
    def test_appends_line(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("EXISTING=value\n")
        run_info_append(str(f), "NEW_KEY=new_value")
        content = f.read_text()
        assert "EXISTING=value\n" in content
        assert "NEW_KEY=new_value\n" in content

    def test_appends_multiple_lines(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("")
        run_info_append(str(f), "LINE1=a")
        run_info_append(str(f), "LINE2=b")
        lines = f.read_text().strip().split("\n")
        assert lines == ["LINE1=a", "LINE2=b"]

    def test_appends_with_newline(self, tmp_path):
        f = tmp_path / "run_info"
        f.write_text("")
        run_info_append(str(f), "KEY=val")
        assert f.read_text().endswith("\n")


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
