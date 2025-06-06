# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

The pipeline uses conda environments for dependency management:
- Default environment: `bp` (created from `environment.yml`)
- Frozen version environment: `bp_frozen` (created from `environment_frozen.yml`)

Set up the environment with:
```bash
conda env create -f environment.yml
conda activate bp
```

Download required resources:
```bash
./download_resources.sh
```

## Architecture Overview

This is a somatic variant calling pipeline derived from the BSMN pipeline, customized for TJBaeLab. The pipeline follows a three-stage workflow:

### Core Components

1. **Configuration System** (`library/config.py`):
   - Reads configuration from `config.{b37,hg19,hg38}.ini` files based on reference genome
   - Dynamically resolves tool paths using conda environment directory
   - Supports multiple reference genomes (b37/GRCh37, hg19, hg38)

2. **Job Management** (`library/job_queue.py`):
   - SLURM-based job submission using `GridEngineQueue` class
   - Tracks job IDs in `run_jid` files to prevent duplicate submissions
   - Uses `sbatch` for job submission

3. **Sample Processing** (`library/parser.py`):
   - Parses `sample_list.txt` files with format: `sample_id file_name location`
   - Supports fastq, bam, and cram file types
   - Groups files by sample ID and file type

### Pipeline Stages

The pipeline consists of three main stages executed via Python scripts in the `jobs/` directory:

1. **Genome Mapping** (`jobs/run_genome_mapping.py`):
   - Aligns fastq files to reference genome using BWA
   - Performs quality control, duplicate marking, indel realignment, BQSR
   - Produces aligned CRAM/BAM files and unmapped reads
   - Job scripts in `jobs/genome_mapping/`

2. **Variant Calling** (`jobs/run_variant_calling.py`):
   - Runs GATK4 HaplotypeCaller with configurable ploidy options
   - Concatenates and filters VCF files
   - Job scripts in `jobs/variant_calling/`

3. **Variant Filtering** (`jobs/run_variant_filtering.py`):
   - Multi-step filtering including CNVnator, MosaicForecast, PON masking
   - Applies germline filters using gnomAD database
   - Job scripts in `jobs/variant_filtering/`

## Common Commands

Run the complete pipeline:
```bash
# Genome mapping only
python3 jobs/run_genome_mapping.py -q queue_name --sample-list sample_list.txt

# With variant calling (ploidy 2, 12, 50)
python3 jobs/run_genome_mapping.py -q queue_name -p 2 12 50 --sample-list sample_list.txt

# Variant calling only (if alignment already done)
python3 jobs/run_variant_calling.py -q queue_name -p 2 12 50 --sample-list sample_list.txt

# Variant filtering only
python3 jobs/run_variant_filtering.py -q queue_name -p 50 --sample-list sample_list.txt
```

Key command-line options:
- `-q/--queue`: SLURM queue name (required)
- `-n/--conda-env`: Conda environment name (default: `bp`)
- `-r/--reference`: Reference genome (b37|hg19|hg38, default: b37)
- `-f/--align-fmt`: Alignment format (cram|bam, default: cram)
- `-p/--run-gatk-hc`: Ploidy options for GATK HaplotypeCaller
- `--sample-list`: Path to sample list file (required)

## File Organization

- `config.*.ini`: Reference-specific configuration files
- `jobs/`: Pipeline execution scripts and SLURM job templates
- `library/`: Core Python modules for configuration, job management, parsing
- `utils/`: Utility scripts for filtering and analysis
- `resources/`: Downloaded reference genomes and databases (created by `download_resources.sh`)

## Sample List Format

Create a `sample_list.txt` file with one of these formats:

For fastq files:
```
sample_id    file_name                      location
SAMPLE1      SAMPLE1_R1_001.fastq.gz       /path/to/SAMPLE1_R1_001.fastq.gz
SAMPLE1      SAMPLE1_R2_001.fastq.gz       /path/to/SAMPLE1_R2_001.fastq.gz
```

For CRAM/BAM files:
```
sample_id    file_name        location
SAMPLE1      SAMPLE1.cram     /path/to/SAMPLE1.cram
```

## Development Notes

- The pipeline automatically activates the specified conda environment in job scripts
- Job dependencies are managed through SLURM job IDs stored in `run_jid` files
- Each sample gets its own directory with logs and intermediate files
- Configuration paths are dynamically resolved using the conda environment directory
- All Python scripts should be run from the desired output directory, not from the pipeline directory