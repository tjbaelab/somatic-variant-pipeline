"""Characterization tests for library/pileup.py pure functions -- Layer 1.

Tests bases_clean(), base_n(), base_qual() -- functions that
do NOT call subprocess or access the filesystem.
"""

import pytest
from library.pileup import bases_clean, base_n, base_qual


class TestBasesClean:
    def test_simple_bases(self):
        assert bases_clean("ACGTacgt") == "ACGTacgt"

    def test_removes_caret_mapping_quality(self):
        """^X marks read start + mapping quality char."""
        assert bases_clean("^FA") == "A"
        assert bases_clean("^~ACG") == "ACG"

    def test_removes_dollar_read_end(self):
        assert bases_clean("ACG$") == "ACG"
        assert bases_clean("A$C$G$") == "ACG"

    def test_removes_insertions(self):
        """Format: +Nbases where N is length."""
        assert bases_clean("A+3CCCG") == "AG"
        assert bases_clean("A+1CT") == "AT"

    def test_removes_deletions(self):
        """Format: -Nbases where N is length."""
        assert bases_clean("A-3CCCG") == "AG"
        assert bases_clean("A-1CT") == "AT"

    def test_mixed_indels(self):
        assert bases_clean("A+2CC-1TG") == "AG"

    def test_empty_string(self):
        assert bases_clean("") == ""

    def test_reference_and_complement(self):
        """.,  represent forward/reverse reference matches."""
        assert bases_clean(".,.,") == ".,.,"

    def test_complex_pileup(self):
        """Real-world-like pileup string."""
        assert bases_clean("^FA.+2AA,$T") == "A.,T"

    def test_deletion_marker_preserved(self):
        """* represents a deletion at the current position."""
        assert bases_clean("A*G") == "A*G"

    def test_multi_digit_indel(self):
        """Indel length >= 10."""
        seq = "A+10ACGTACGTACG"
        assert bases_clean(seq) == "AG"


class TestBaseN:
    def _send(self, coro, bases, quals=""):
        return coro.send((bases, quals))

    def test_simple_counts(self):
        coro = base_n()
        result = self._send(coro, "AACCGGTTaaccggtt")
        assert result["A"] == 2
        assert result["C"] == 2
        assert result["G"] == 2
        assert result["T"] == 2
        assert result["a"] == 2
        assert result["c"] == 2
        assert result["g"] == 2
        assert result["t"] == 2
        assert result["dels"] == 0

    def test_empty_bases(self):
        coro = base_n()
        result = self._send(coro, "")
        for key in "ACGTacgt":
            assert result[key] == 0
        assert result["dels"] == 0

    def test_deletions(self):
        coro = base_n()
        result = self._send(coro, "AA**GG")
        assert result["A"] == 2
        assert result["G"] == 2
        assert result["dels"] == 2

    def test_multiple_sends(self):
        """Coroutine can be reused across multiple positions."""
        coro = base_n()
        r1 = self._send(coro, "AAAA")
        assert r1["A"] == 4
        r2 = self._send(coro, "GGGG")
        assert r2["A"] == 0
        assert r2["G"] == 4


class TestBaseQual:
    def _send(self, coro, bases, quals):
        return coro.send((bases, quals))

    def test_simple_mapping(self):
        """Quality char ord - 33 = Phred score."""
        coro = base_qual()
        result = self._send(coro, "AG", "II")  # ord('I')=73, 73-33=40
        assert result == [("A", 40), ("G", 40)]

    def test_mixed_case_uppercased(self):
        coro = base_qual()
        result = self._send(coro, "aG", "II")
        assert result == [("A", 40), ("G", 40)]

    def test_empty(self):
        coro = base_qual()
        result = self._send(coro, "", "")
        assert result == []

    def test_deletion_stars_removed(self):
        """Stars (*) are stripped before base-quality pairing."""
        coro = base_qual()
        result = self._send(coro, "A*G", "IJ")  # 2 quals for 2 non-star bases
        assert len(result) == 2
        assert result[0] == ("A", 40)
        assert result[1] == ("G", 41)  # ord('J')=74, 74-33=41

    def test_multiple_sends(self):
        coro = base_qual()
        r1 = self._send(coro, "A", "!")  # ord('!')=33, 33-33=0
        assert r1 == [("A", 0)]
        r2 = self._send(coro, "T", "~")  # ord('~')=126, 126-33=93
        assert r2 == [("T", 93)]
