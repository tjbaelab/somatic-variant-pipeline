"""Characterization tests for library/parser.py -- Layer 1 (pure logic)."""

import pytest
from library.parser import filetype, sample_list


class TestFiletype:
    def test_bam(self):
        assert filetype("sample.bam") == "bam"

    def test_bai(self):
        assert filetype("sample.bai") == "bam"

    def test_cram(self):
        assert filetype("sample.cram") == "cram"

    def test_crai(self):
        assert filetype("sample.crai") == "cram"

    def test_fastq(self):
        assert filetype("sample.fastq") == "fastq"

    def test_fq(self):
        assert filetype("sample.fq") == "fastq"

    def test_fastq_gz(self):
        assert filetype("sample.fastq.gz") == "fastq"

    def test_fq_gz(self):
        assert filetype("sample.fq.gz") == "fastq"

    def test_bam_gz(self):
        assert filetype("sample.bam.gz") == "bam"

    def test_with_path(self):
        assert filetype("/data/samples/sample.bam") == "bam"

    def test_dotted_name(self):
        assert filetype("sample.name.with.dots.fastq.gz") == "fastq"

    def test_invalid_extension(self):
        with pytest.raises(Exception, match="is not allowed filetype"):
            filetype("sample.txt")

    def test_invalid_gz_extension(self):
        with pytest.raises(Exception, match="is not allowed filetype"):
            filetype("sample.txt.gz")

    def test_no_extension(self):
        with pytest.raises(Exception, match="is not allowed filetype"):
            filetype("sample")


class TestSampleList:
    def test_basic_parsing(self, tmp_path):
        content = "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data/s1\n"
        f = tmp_path / "samples.txt"
        f.write_text(content)
        result = sample_list(str(f))
        assert ("SAMPLE1", "fastq") in result
        assert len(result[("SAMPLE1", "fastq")]) == 1
        assert result[("SAMPLE1", "fastq")][0] == ("SAMPLE1.R1.fastq.gz", "/data/s1")

    def test_comment_skipping(self, tmp_path):
        content = "# This is a comment\nSAMPLE1\tSAMPLE1.bam\t/data/s1\n"
        f = tmp_path / "samples.txt"
        f.write_text(content)
        result = sample_list(str(f))
        assert len(result) == 1
        assert ("SAMPLE1", "bam") in result

    def test_multi_sample(self, tmp_path):
        content = (
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data/s1\n"
            "SAMPLE1\tSAMPLE1.R2.fastq.gz\t/data/s1\n"
            "SAMPLE2\tSAMPLE2.bam\t/data/s2\n"
        )
        f = tmp_path / "samples.txt"
        f.write_text(content)
        result = sample_list(str(f))
        assert len(result[("SAMPLE1", "fastq")]) == 2
        assert len(result[("SAMPLE2", "bam")]) == 1

    def test_file_type_grouping(self, tmp_path):
        content = (
            "SAMPLE1\tSAMPLE1.bam\t/data/s1\n"
            "SAMPLE1\tSAMPLE1.R1.fastq.gz\t/data/s1\n"
        )
        f = tmp_path / "samples.txt"
        f.write_text(content)
        result = sample_list(str(f))
        assert ("SAMPLE1", "bam") in result
        assert ("SAMPLE1", "fastq") in result

    def test_returns_defaultdict(self, tmp_path):
        content = "SAMPLE1\tSAMPLE1.bam\t/data/s1\n"
        f = tmp_path / "samples.txt"
        f.write_text(content)
        result = sample_list(str(f))
        assert result[("NONEXISTENT", "bam")] == []

    def test_extra_columns_ignored(self, tmp_path):
        content = "SAMPLE1\tSAMPLE1.bam\t/data/s1\textra_col\n"
        f = tmp_path / "samples.txt"
        f.write_text(content)
        result = sample_list(str(f))
        assert ("SAMPLE1", "bam") in result
        assert result[("SAMPLE1", "bam")][0] == ("SAMPLE1.bam", "/data/s1")
