"""Tests for LocalQueue and create_queue factory -- Phase S."""

import os
import pytest
from unittest.mock import MagicMock
from library.job_queue import LocalQueue, create_queue, GridEngineQueue


class TestLocalQueueSubmit:
    def test_returns_sequential_jids(self, monkeypatch):
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: MagicMock(returncode=0))
        q = LocalQueue()
        j1 = q.submit("--partition=normal", "echo hello")
        j2 = q.submit("--partition=normal", "echo world")
        assert j1 == "1"
        assert j2 == "2"

    def test_runs_command(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            captured["env"] = kw.get("env", {})
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", fake_run)
        q = LocalQueue()
        q.submit("--partition=normal", "script.sh sample1")

        assert captured["cmd"] == ["script.sh", "sample1"]

    def test_sets_slurm_cpus_env(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kw):
            captured["env"] = kw.get("env", {})
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", fake_run)
        q = LocalQueue(max_cpus=8)
        q.submit("--partition=normal", "script.sh")

        assert captured["env"]["SLURM_CPUS_ON_NODE"] == "8"

    def test_default_max_cpus(self):
        q = LocalQueue()
        assert q.max_cpus == os.cpu_count() or q.max_cpus == 1

    def test_records_jid_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: MagicMock(returncode=0))
        jid_file = tmp_path / "run_jid"
        q = LocalQueue()
        q.set_run_jid(str(jid_file), new=True)
        q.submit("--partition=normal", "script.sh")

        assert "1" in jid_file.read_text()


class TestLocalQueueDependencies:
    def test_skips_on_failed_dep(self, monkeypatch, capsys):
        call_count = [0]

        def fake_run(cmd, **kw):
            call_count[0] += 1
            return MagicMock(returncode=1)

        monkeypatch.setattr("subprocess.run", fake_run)
        q = LocalQueue()

        j1 = q.submit("--partition=normal", "failing_script.sh")
        j2 = q.submit("-d afterok:1 --partition=normal", "dependent.sh")

        assert call_count[0] == 1  # second job was skipped
        assert q._completed["2"] == 1
        output = capsys.readouterr().out
        assert "skipped" in output

    def test_runs_when_dep_succeeded(self, monkeypatch):
        call_count = [0]

        def fake_run(cmd, **kw):
            call_count[0] += 1
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", fake_run)
        q = LocalQueue()

        q.submit("--partition=normal", "first.sh")
        q.submit("-d afterok:1 --partition=normal", "second.sh")

        assert call_count[0] == 2

    def test_parses_multiple_deps(self, monkeypatch):
        monkeypatch.setattr("subprocess.run",
                            lambda *a, **kw: MagicMock(returncode=0))
        q = LocalQueue()
        q.submit("--partition=normal", "a.sh")
        q.submit("--partition=normal", "b.sh")
        q.submit("-d afterok:1,2 --partition=normal", "c.sh")

        assert q._completed["3"] == 0


class TestLocalQueueArray:
    def test_array_sets_task_id(self, monkeypatch):
        task_ids = []

        def fake_run(cmd, **kw):
            task_ids.append(kw.get("env", {}).get("SLURM_ARRAY_TASK_ID"))
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", fake_run)
        q = LocalQueue()
        q.submit("--array=1-3 --partition=normal", "array_script.sh")

        assert task_ids == ["1", "2", "3"]

    def test_non_array_no_task_id(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kw):
            captured["env"] = kw.get("env", {})
            return MagicMock(returncode=0)

        monkeypatch.setattr("subprocess.run", fake_run)
        q = LocalQueue()
        q.submit("--partition=normal", "script.sh")

        assert "SLURM_ARRAY_TASK_ID" not in captured["env"]


class TestLocalQueueSetRunJid:
    def test_creates_file(self, tmp_path):
        jid_file = tmp_path / "subdir" / "run_jid"
        q = LocalQueue()
        q.set_run_jid(str(jid_file), new=True)
        assert jid_file.exists()
        assert jid_file.read_text() == ""

    def test_num_run_jid_always_zero(self, tmp_path):
        q = LocalQueue()
        assert q.num_run_jid_in_queue(str(tmp_path / "anything")) == 0


class TestCreateQueue:
    def test_local_backend(self):
        q = create_queue(backend="local")
        assert isinstance(q, LocalQueue)

    def test_slurm_backend(self):
        q = create_queue(backend="slurm")
        assert isinstance(q, GridEngineQueue)

    def test_auto_without_sbatch(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        q = create_queue(backend="auto")
        assert isinstance(q, LocalQueue)

    def test_auto_with_sbatch(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/sbatch")
        q = create_queue(backend="auto")
        assert isinstance(q, GridEngineQueue)

    def test_local_with_max_cpus(self):
        q = create_queue(backend="local", max_cpus=4)
        assert q.max_cpus == 4
