"""Characterization tests for utils/germline_filter.py -- Layer 1 (subprocess).

germline_filter.py has no if __name__ guard; argparse runs on import.
Testing via subprocess is the only safe approach without modifying source.
"""

import gzip
import os
import subprocess
import sys
import pytest


@pytest.fixture
def pipe_home():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def germline_fixture(tmp_path, pipe_home):
    """Create test VCF input and known germline variant file."""
    # Known germline variants (tab-separated).
    # germline_filter.py reads lines, splits on whitespace, joins with ":".
    # "1\t100\tA\tG" -> split -> ["1","100","A","G"] -> "1:100:A:G"
    variant_file = tmp_path / "known_germline.txt.gz"
    with gzip.open(str(variant_file), "wt") as f:
        f.write("1\t100\tA\tG\n")
        f.write("1\t200\tC\tT\n")

    # VCF input (stdin).
    # VCF format: CHROM POS ID REF ALT QUAL FILTER INFO
    # germline_filter constructs var = "{chrom}:{pos}:{ref}:{alt}"
    # with chr prefix stripped from chrom.
    vcf_input = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "1\t100\t.\tA\tG\t30\tPASS\t.\n"       # known germline -> filtered
        "1\t150\t.\tT\tC\t30\tPASS\t.\n"       # not germline -> pass
        "1\t200\t.\tC\tT\t30\tPASS\t.\n"       # known germline -> filtered
        "chr1\t300\t.\tG\tA\t30\tPASS\t.\n"    # chr prefix stripped -> "1:300:G:A" -> pass
    )

    return {
        "variant_file": str(variant_file),
        "vcf_input": vcf_input,
        "script": os.path.join(pipe_home, "utils", "germline_filter.py"),
    }


class TestGermlineFilter:
    def test_filters_known_germline(self, germline_fixture):
        result = subprocess.run(
            [sys.executable, germline_fixture["script"],
             "--variant", germline_fixture["variant_file"]],
            input=germline_fixture["vcf_input"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output_lines = [
            line for line in result.stdout.strip().split("\n")
            if not line.startswith("#")
        ]
        # 1:100:A:G and 1:200:C:T are known germline -> filtered out
        # 1:150:T:C and chr1:300:G:A remain
        assert len(output_lines) == 2
        assert "150" in output_lines[0]
        assert "300" in output_lines[1]

    def test_preserves_header(self, germline_fixture):
        result = subprocess.run(
            [sys.executable, germline_fixture["script"],
             "--variant", germline_fixture["variant_file"]],
            input=germline_fixture["vcf_input"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        header_lines = [
            line for line in result.stdout.strip().split("\n")
            if line.startswith("#")
        ]
        assert len(header_lines) == 2
        assert header_lines[0].startswith("##fileformat")
        assert header_lines[1].startswith("#CHROM")

    def test_chr_prefix_stripped(self, germline_fixture, tmp_path):
        """Verify chr prefix is stripped when matching against known germline."""
        # Add chr1:300:G:A to known germline
        variant_file = tmp_path / "known_with_chr.txt.gz"
        with gzip.open(str(variant_file), "wt") as f:
            f.write("1\t300\tG\tA\n")

        vcf_input = (
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            "chr1\t300\t.\tG\tA\t30\tPASS\t.\n"
        )

        result = subprocess.run(
            [sys.executable, germline_fixture["script"],
             "--variant", str(variant_file)],
            input=vcf_input,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output_lines = [
            line for line in result.stdout.strip().split("\n")
            if not line.startswith("#")
        ]
        # chr1:300:G:A -> strip chr -> "1:300:G:A" matches known -> filtered
        assert len(output_lines) == 0

    def test_multi_allelic(self, germline_fixture, tmp_path):
        """Multi-allelic ALT: each alt checked independently."""
        variant_file = tmp_path / "known_multi.txt.gz"
        with gzip.open(str(variant_file), "wt") as f:
            f.write("1\t500\tA\tG\n")

        vcf_input = (
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
            "1\t500\t.\tA\tG,T\t30\tPASS\t.\n"
        )

        result = subprocess.run(
            [sys.executable, germline_fixture["script"],
             "--variant", str(variant_file)],
            input=vcf_input,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output_lines = [
            line for line in result.stdout.strip().split("\n")
            if not line.startswith("#")
        ]
        # G is known germline, T is not.
        # Current behavior: line is printed once for the unknown alt (T).
        assert len(output_lines) == 1
        assert "500" in output_lines[0]
