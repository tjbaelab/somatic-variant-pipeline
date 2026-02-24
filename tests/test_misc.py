"""Characterization tests for library/misc.py -- Layer 1 (pure logic)."""

import sys
import pytest
from library.misc import coroutine, printer


class TestCoroutine:
    def test_primes_generator(self):
        @coroutine
        def accumulator():
            total = 0
            while True:
                value = yield total
                total += value

        acc = accumulator()
        assert acc.send(10) == 10
        assert acc.send(20) == 30
        assert acc.send(5) == 35

    def test_first_next_is_called(self):
        """Verify the decorator calls __next__() to prime the generator."""
        called = []

        @coroutine
        def tracker():
            called.append("primed")
            while True:
                yield

        tracker()
        assert called == ["primed"]

    def test_passes_args(self):
        @coroutine
        def adder(base):
            total = base
            while True:
                value = yield total
                total += value

        acc = adder(100)
        assert acc.send(1) == 101
        assert acc.send(2) == 103

    def test_passes_kwargs(self):
        @coroutine
        def adder(base=0):
            total = base
            while True:
                value = yield total
                total += value

        acc = adder(base=50)
        assert acc.send(10) == 60


class TestPrinter:
    def test_normal_output(self, capsys):
        printer("hello world")
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"

    def test_numeric_output(self, capsys):
        printer(42)
        captured = capsys.readouterr()
        assert captured.out == "42\n"

    def test_broken_pipe_handling(self, monkeypatch):
        """printer should handle BrokenPipeError gracefully."""
        import io

        def raise_broken_pipe(*args, **kwargs):
            raise BrokenPipeError()

        monkeypatch.setattr("builtins.print", raise_broken_pipe)
        # Provide fake stdout/stderr so closing them doesn't affect real streams
        monkeypatch.setattr("sys.stdout", io.StringIO())
        monkeypatch.setattr("sys.stderr", io.StringIO())
        # Should not raise
        printer("test")
