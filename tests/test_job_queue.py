"""Characterization tests for library/job_queue.py -- Layer 2 (mocked subprocess).

GridEngineQueue wraps SLURM sbatch/squeue commands.
We mock subprocess.run to test on macOS without SLURM.
"""

import os
import pytest
from unittest.mock import MagicMock
from library.job_queue import GridEngineQueue


class TestSubmit:
    def test_returns_jid(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = "12345"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        q = GridEngineQueue()
        jid = q.submit("--partition=normal --parsable", "test_script.sh sample1")
        assert jid == "12345"

    def test_sbatch_command_construction(self, monkeypatch):
        captured = {}

        def fake_run(cmd_list, **kwargs):
            captured["cmd"] = cmd_list
            result = MagicMock()
            result.stdout = "99999"
            return result

        monkeypatch.setattr("subprocess.run", fake_run)

        q = GridEngineQueue()
        q.submit("-d afterok:111 --partition=normal --parsable", "script.sh sample1")

        cmd = captured["cmd"]
        assert cmd[0] == "sbatch"
        assert "-d" in cmd
        assert "afterok:111" in cmd
        assert "--partition=normal" in cmd
        assert "--parsable" in cmd
        assert "script.sh" in cmd
        assert "sample1" in cmd

    def test_records_jid_to_file(self, tmp_path, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = "12345"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        jid_file = tmp_path / "run_jid"
        q = GridEngineQueue()
        q.set_run_jid(str(jid_file), new=True)
        q.submit("--partition=normal", "script.sh")

        assert "12345" in jid_file.read_text()

    def test_multiple_submits_append_jids(self, tmp_path, monkeypatch):
        call_count = [0]

        def fake_run(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            result.stdout = str(1000 + call_count[0])
            return result

        monkeypatch.setattr("subprocess.run", fake_run)

        jid_file = tmp_path / "run_jid"
        q = GridEngineQueue()
        q.set_run_jid(str(jid_file), new=True)
        q.submit("--partition=normal", "script1.sh")
        q.submit("--partition=normal", "script2.sh")

        content = jid_file.read_text()
        assert "1001" in content
        assert "1002" in content

    def test_no_jid_file_set(self, monkeypatch):
        """submit() works even without set_run_jid."""
        mock_result = MagicMock()
        mock_result.stdout = "12345"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        q = GridEngineQueue()
        jid = q.submit("--partition=normal", "script.sh")
        assert jid == "12345"


class TestNumRunJidInQueue:
    def test_no_file(self, tmp_path):
        q = GridEngineQueue()
        n = q.num_run_jid_in_queue(str(tmp_path / "nonexistent"))
        assert n == 0

    def test_empty_file(self, tmp_path):
        jid_file = tmp_path / "run_jid"
        jid_file.write_text("")
        q = GridEngineQueue()
        n = q.num_run_jid_in_queue(str(jid_file))
        assert n == 0

    def test_with_jids(self, tmp_path, monkeypatch):
        jid_file = tmp_path / "run_jid"
        jid_file.write_text("111\n222\n333\n")

        mock_result = MagicMock()
        mock_result.stdout = "2\n"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        q = GridEngineQueue()
        n = q.num_run_jid_in_queue(str(jid_file))
        assert n == 2

    def test_squeue_command(self, tmp_path, monkeypatch):
        jid_file = tmp_path / "run_jid"
        jid_file.write_text("111\n222\n")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            result = MagicMock()
            result.stdout = "0\n"
            return result

        monkeypatch.setattr("subprocess.run", fake_run)

        q = GridEngineQueue()
        q.num_run_jid_in_queue(str(jid_file))

        assert "squeue" in captured["cmd"]
        assert "111,222" in captured["cmd"]


class TestSetRunJid:
    def test_new_creates_empty_file(self, tmp_path):
        jid_file = tmp_path / "subdir" / "run_jid"
        q = GridEngineQueue()
        q.set_run_jid(str(jid_file), new=True)
        assert jid_file.exists()
        assert jid_file.read_text() == ""
        assert q.run_jid == str(jid_file)

    def test_existing_sets_path_only(self, tmp_path):
        jid_file = tmp_path / "run_jid"
        jid_file.write_text("old_jid\n")
        q = GridEngineQueue()
        q.set_run_jid(str(jid_file))
        assert q.run_jid == str(jid_file)
        assert jid_file.read_text() == "old_jid\n"

    def test_default_run_jid_is_none(self):
        q = GridEngineQueue()
        assert q.run_jid is None
