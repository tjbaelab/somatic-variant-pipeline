# Module Catalog

## library/ - Shared Python Library

The `library/` package is the core shared infrastructure consumed by all orchestration scripts and utility modules. It has no imports from `jobs/` or `utils/`—it is a pure dependency sink with no upward coupling.

High fan-in modules: `config.py` (fan-in=6), `job_queue.py` (fan-in=6), `misc.py` (fan-in=4), `pileup.py` (fan-in=3), `parser.py` (fan-in=3).

---

### library/config.py

**Purpose**: Configuration management. Reads INI-format genome config files, resolves run-specific directories, and persists SLURM job IDs between phases.

**Fan-in**: 6 — consumed by `run_genome_mapping.py`, `run_variant_calling.py`, `run_variant_filtering.py`, `submit_aln_jobs.py`, `submit_gatk-hc_jobs.py`, `submit_filtering_jobs.py`, and internally by `library/pileup.py`.

**Key functions**:

| Function | Signature | Description |
|---|---|---|
| `read_config` | `(reference: str, conda_env: str) -> ConfigParser` | Reads and returns the parsed INI config object. Config files are named `config.<genome>.ini`. |
| `run_info` | `(fname: str, reference: str, conda_env: str) -> dict` | Extracts per-sample run metadata: output directories, tool paths, resource file paths (gnomAD VCF, PON BED, etc.). |
| `run_info_append` | `(fname: str, line: str) -> None` | Appends a line to the run_info shell-sourceable file produced for each sample. |
| `log_dir` | `(sample: str) -> str` | Returns the log directory path for a given sample run. |
| `save_hold_jid` | `(fname: str, jid: str) -> None` | Persists a SLURM job ID to the config file so downstream phases can express job dependencies. |

**Dependencies**: Python standard library only (`configparser`, `os`).

**Note**: This module is the backbone of cross-phase SLURM dependency management. The `save_hold_jid` / `hold_jid` mechanism allows orchestrator scripts to run independently (minutes or days apart) while the scheduler enforces execution order.

---

### library/job_queue.py

**Purpose**: SLURM/GridEngine queue interface. Submits shell scripts as SLURM batch jobs and monitors queue depth.

**Fan-in**: 6 — consumed by all six orchestration scripts (`run_*.py` and `submit_*.py`).

**Key class and methods**:

| Method | Signature | Description |
|---|---|---|
| `GridEngineQueue.__init__` | `(self)` | Initializes the queue interface. Despite the class name, this wraps `sbatch` (SLURM), not GridEngine. |
| `submit` | `(self, q_opt_str: str, cmd_str: str) -> str` | Submits a shell script to SLURM. `q_opt_str` contains SBATCH options (resources, dependencies). Returns the assigned job ID string. |
| `num_run_jid_in_queue` | `(self, fname: str) -> int` | Returns the count of running or pending jobs matching the job IDs stored in `fname`. Used by orchestrators to poll for phase completion. |
| `set_run_jid` | `(self, fname: str, new: str) -> None` | Writes a new job ID into the tracking file, replacing the old value. |

**Dependencies**: `subprocess` (wraps `sbatch` and `squeue` CLI calls).

**Note**: The class is named `GridEngineQueue` for historical reasons but exclusively uses SLURM (`sbatch`/`squeue`). This is the primary coupling point to the SLURM scheduler.

---

### library/parser.py

**Purpose**: Sample list parsing. Reads the input sample manifest (TSV) and determines input file types.

**Fan-in**: 3 — consumed by `run_genome_mapping.py`, `run_variant_calling.py`, `run_variant_filtering.py`.

**Key functions**:

| Function | Signature | Description |
|---|---|---|
| `filetype` | `(fname: str) -> str` | Detects whether the sample list references FASTQ, BAM, or CRAM inputs. Returns `"fastq"`, `"bam"`, or `"cram"`. |
| `sample_list` | `(fname: str) -> defaultdict` | Parses the tab-delimited sample manifest. Returns a `defaultdict` keyed by sample ID with file path values. |

**Sample list TSV format** (inferred from pipeline design):

```
sample_id    file_path                          pair_path (optional for paired FASTQ)
SAMPLE_001   /data/reads/sample001_R1.fastq.gz  /data/reads/sample001_R2.fastq.gz
SAMPLE_002   /data/bams/sample002.bam
```

**Dependencies**: Python standard library only (`collections.defaultdict`, `os`).

---

### library/pileup.py

**Purpose**: Samtools mpileup wrapper with coroutine-based streaming. Enables memory-efficient per-position base counting and quality filtering for VAF and strand bias calculations.

**Fan-in**: 3 — consumed by `utils/somatic_vaf.py`, `utils/strand_bias.py`, `utils/alt_bq_sum.py`.

**Key functions**:

| Function | Signature | Description |
|---|---|---|
| `load_config` | `(reference: str, conda_env: str) -> ConfigParser` | Loads the genome config to resolve samtools binary path and reference FASTA. |
| `base_count` | `(bam: str, min_MQ: int, min_BQ: int) -> coroutine` | Coroutine that yields per-position base count dicts `{'A': int, 'T': int, 'G': int, 'C': int, 'ref': int, 'del': int, 'ins': int}`. |
| `base_qual_tuple` | `(bam: str, min_MQ: int, min_BQ: int) -> coroutine` | Coroutine that yields lists of `(base, quality_score)` tuples. Used for quality-filtered and strand-aware allele counting. |
| `pileup` | `(bam: str, min_MQ: int, min_BQ: int, target: str) -> coroutine` | Main entry coroutine. Launches `samtools mpileup` as a subprocess and streams parsed pileup lines to downstream coroutines. |
| `bases_clean` | `(bases: str) -> str` | Cleans the raw mpileup bases string by removing reference indicators (`^`, `$`) and indel notation. |

**Dependencies**: `library.config` (for samtools path resolution), `library.misc` (for `@coroutine` decorator), `subprocess`.

**Note**: All functions are coroutines that must be primed before use. The `@coroutine` decorator from `library/misc.py` handles the initial `next()` call automatically.

---

### library/misc.py

**Purpose**: General-purpose utilities used across the library. Contains the foundational coroutine infrastructure that powers the streaming pileup pipeline.

**Fan-in**: 4 — consumed by `library/pileup.py`, `utils/somatic_vaf.py`, `utils/strand_bias.py`, `utils/alt_bq_sum.py`.

**Key items**:

| Item | Type | Description |
|---|---|---|
| `@coroutine` | Decorator | Advances a generator to its first `yield` point, enabling coroutine-style `send()` pipelines. All pileup streaming functions depend on this. |
| `printer` | Function `(out: str) -> None` | Prints a timestamped message to stdout. Used for pipeline progress logging across multiple modules. |

**Dependencies**: Python standard library only.

**Note**: This is the leaf node in the dependency graph—it imports nothing from the project. It is the most fundamental building block in the shared library.

---

## jobs/ - Pipeline Orchestrators and Shell Scripts

### Python Orchestrators

#### jobs/run_genome_mapping.py

**Purpose**: Phase 1 primary entry point. Reads sample list and config, then submits SLURM jobs for each genome mapping step in dependency order.

**CLI arguments**:

| Argument | Short | Required | Description |
|---|---|---|---|
| `--queue` | `-q` | Yes | SLURM queue/partition name |
| `--conda-env` | `-n` | Yes | Conda environment name for tool activation |
| `--align-fmt` | `-f` | Yes | Alignment input format: `fastq`, `bam`, or `cram` |
| `--reference` | `-r` | Yes | Reference genome identifier (e.g., `hg38_decoy`) |
| `--ploidy` | `-p` | Yes | Sample ploidy for sex chromosome handling |
| `--sample-list` | (positional) | Yes | Path to TSV sample manifest |

**Imports**: `library.config`, `library.parser`, `library.job_queue`

**Shell scripts delegated to**: `jobs/genome_mapping/*.sh`

---

#### jobs/run_variant_calling.py

**Purpose**: Phase 2 primary entry point. Submits GATK4 HaplotypeCaller jobs per chromosome, then concatenates gVCFs and applies VQSR.

**CLI arguments**: Same structure as `run_genome_mapping.py` (`-q`, `-n`, `-f`, `-r`, `-p`, `--sample-list`)

**Imports**: `library.config`, `library.parser`, `library.job_queue`

**Shell scripts delegated to**: `jobs/variant_calling/*.sh`

---

#### jobs/run_variant_filtering.py

**Purpose**: Phase 3 primary entry point. Submits the multi-stage filtering job chain (stages A-G).

**CLI arguments**: Same structure as `run_genome_mapping.py` (`-q`, `-n`, `-f`, `-r`, `-p`, `--sample-list`)

**Imports**: `library.config`, `library.parser`, `library.job_queue`

**Shell scripts delegated to**: `jobs/variant_filtering/*.sh`

---

#### jobs/submit_aln_jobs.py and jobs/submit_aln_jobs.just_mapping.py

**Purpose**: Helper scripts to re-submit alignment jobs for specific samples or steps without running the full Phase 1 orchestrator. The `just_mapping` variant skips the pre-processing steps and runs alignment only.

**Imports**: `library.config`, `library.job_queue`

---

#### jobs/submit_gatk-hc_jobs.py

**Purpose**: Helper script to re-submit GATK HaplotypeCaller jobs for specific samples or chromosomes independently.

**Imports**: `library.config`, `library.job_queue`

---

#### jobs/submit_filtering_jobs.py

**Purpose**: Helper script to re-submit filtering jobs starting from a specific stage. Used for partial pipeline recovery.

**Imports**: `library.config`, `library.job_queue`

---

### Shell Scripts: jobs/genome_mapping/

15+ shell scripts organized by stage with `pre_`, `aln_`, and `post_` naming conventions.

| Script | Stage Prefix | Tools Used | SLURM Resources |
|---|---|---|---|
| `pre_1.download.sh` | pre_1 | wget, cp | Low CPU, low mem |
| `pre_1b.bam2fastq.sh` | pre_1b | samtools fastq, picard SamToFastq | 4-8 CPU |
| `pre_2.split_fastq_by_RG.sh` | pre_2 | samtools, picard SplitSamByReadGroup | 4-8 CPU |
| `aln_1.align_sort.sh` | aln_1 | bwa mem, sambamba sort | 32 CPU, 64GB RAM |
| `aln_2.merge_bam.sh` | aln_2 | samtools merge | 4 CPU, 16GB RAM |
| `aln_3.markdup.sh` | aln_3 | picard MarkDuplicates | 8 CPU, 32GB RAM |
| `aln_3.markdup_spark.sh` | aln_3 (alt) | GATK4 MarkDuplicatesSpark | 16 CPU, 64GB RAM |
| `aln_4.indel_realign*.sh` | aln_4 | GATK3 RealignerTargetCreator + IndelRealigner | 4 CPU, 16GB RAM |
| `aln_5.bqsr*.sh` | aln_5 | GATK3 BaseRecalibrator + PrintReads | 8 CPU, 32GB RAM |
| `aln_5.bqsr*.gather.sh` | aln_5 gather | GATK3 GatherBqsrReports | 4 CPU |
| `post_1.unmapped_reads.sh` | post_1 | samtools view -f 4 | 4 CPU |
| `post_2.run_variant_calling.sh` | post_2 | Python (triggers Phase 2) | Minimal |
| `prep/` | pre-processing | Repair/preprocessing helpers | Variable |

Array job variants: `aln_4` and `aln_5` have array variants for per-chromosome parallel processing.

---

### Shell Scripts: jobs/variant_calling/

7 shell scripts with `pre_` and `gatk-hc_` naming conventions.

| Script | Stage | Tools Used | SLURM Resources |
|---|---|---|---|
| `pre_1.download.sh` | pre_1 | wget, cp | Low CPU |
| `pre_2.bam2cram.sh` | pre_2 | samtools view -C | 4 CPU, 16GB RAM |
| `pre_2b.unmapped_reads.sh` | pre_2b | samtools view -f 4 | 4 CPU |
| `pre_3.run_variant_calling.sh` | pre_3 | Python (phase trigger) | Minimal |
| `gatk-hc_1.call.sh` | gatk-hc_1 | GATK4 HaplotypeCaller | 4 CPU, 16GB RAM, array 1-24 |
| `gatk-hc_2.concat_vcf.sh` | gatk-hc_2 | bcftools concat | 4 CPU, 8GB RAM |
| `gatk-hc_3.vqsr.sh` | gatk-hc_3 | GATK4 VariantRecalibrator + ApplyVQSR | 8 CPU, 32GB RAM |

---

### Shell Scripts: jobs/variant_filtering/

14+ shell scripts with stage letter (A-G) naming conventions plus `prep/`.

| Script | Stage | Tools / Python Utilities Used |
|---|---|---|
| `prep/start_variant_filtering.sh` | Setup | Environment initialization |
| `A.CNVnator_mk_root*.sh` | A (parallel) | CNVnator root file creation |
| `A.gnomAD_germline_filter.sh` | A (main) | bcftools annotate, `utils/germline_filter.py` |
| `B.PASS_P.sh` | B | bcftools view --apply-filters PASS |
| `C.VAF_filters*.sh` | C | `utils/somatic_vaf.2.py`, strand bias, alt BQ filters |
| `D.CNVnator_genotype_filter.sh` | D | CNVnator, bedtools intersect |
| `E.mayo_filters*.sh` | E (branch 1) | bcftools filter (strand_bias, repeat, alt_bq expressions) |
| `E.MosaicForecast*.sh` | E (branch 2) | MosaicForecast ML classifier |
| `F.PON_mask.sh` | F | `utils/PON_mask.2.py`, liftOver, bedtools intersect |
| `G.filtered_VCF.sh` | G | bcftools concat/merge (final output assembly) |

---

## utils/ - Standalone Analysis Utilities

All utility scripts are invoked directly from filtering shell scripts as command-line tools. They produce per-variant annotations or filtered VCF records.

### .py vs .2.py Version Strategy

The `.2.py` suffix indicates a performance-optimized version using Python `multiprocessing`. The original `.py` file is the reference implementation. Both versions remain in the repository with no formal deprecation policy. Shell scripts in `variant_filtering/` reference `.2.py` versions for production use.

---

### utils/somatic_vaf.py and utils/somatic_vaf.2.py

**Purpose**: Compute per-variant Variant Allele Frequency (VAF) from BAM pileup data. Apply a binomial statistical test to distinguish true somatic variants from sequencing noise.

**Key logic**:
- Streams per-position base counts via `library.pileup.base_count()` coroutine
- Applies binomial test (`scipy.stats.binom_test`) to assess VAF significance
- Outputs VAF-annotated VCF records; flags variants below threshold

**Dependencies**: `library.misc`, `library.pileup`, `scipy.stats`

**v2 enhancement**: Parallelized across variant positions using `multiprocessing.Pool`.

---

### utils/strand_bias.py and utils/strand_bias.2.py

**Purpose**: Detect strand bias in variant-supporting reads using Fisher's exact test and Poisson-based tests. Strand bias is a common sequencing artefact that generates false positive somatic calls.

**Key logic**:
- Streams strand-aware base counts via `library.pileup.base_qual_tuple()` coroutine
- Applies Fisher's exact test (`scipy.stats.fisher_exact`) and Poisson tests via `rpy2`
- Flags variants with statistically significant strand bias

**Dependencies**: `library.misc`, `library.pileup`, `scipy.stats`, `rpy2` (R integration), `statsmodels`

**v2 enhancement**: Parallelized using `multiprocessing.Pool`.

---

### utils/alt_bq_sum.py

**Purpose**: Compute the sum of base qualities for alternate allele-supporting reads. Low base quality sums indicate low-confidence variant calls that should be filtered.

**Key logic**:
- Streams `(base, quality_score)` tuples via `library.pileup.base_qual_tuple()` coroutine
- Sums base qualities for reads supporting the alternate allele
- Outputs per-variant base quality sum for threshold filtering

**Dependencies**: `library.misc`, `library.pileup`

---

### utils/repeat.py and utils/repeat.2.py

**Purpose**: Detect tandem repeat regions overlapping variant positions. Variants in repeat regions are flagged as potentially artefactual due to alignment ambiguity.

**Key logic**:
- Reads reference FASTA sequence for the variant region via `pyfaidx`
- Implements a sliding-window tandem repeat detection algorithm
- Returns repeat unit and copy number for annotation

**Dependencies**: `pyfaidx` (FASTA indexing). No `library/` imports.

**v2 enhancement**: Parallelized repeat detection across variant positions.

---

### utils/germline_filter.py

**Purpose**: Remove variants present in gnomAD (Genome Aggregation Database) as known germline polymorphisms. Reduces false positive somatic calls from variants present at population allele frequencies above a threshold.

**Key logic**:
- Reads gnomAD VCF from path configured in INI `[RESOURCES]` section
- Compares variant positions and alleles against gnomAD records
- Removes variants above configured allele frequency threshold

**Dependencies**: `pysam` (VCF access). No `library/` imports directly (path from config passed as CLI argument).

---

### utils/PON_mask.2.py

**Purpose**: Panel of Normals (PON) masking. Removes variants that appear recurrently in a cohort of normal (non-tumor) samples, filtering out sequencing artefacts and common germline variants not captured by gnomAD.

**Key logic**:
- Reads PON BED/VCF split files from `downloads/`
- Uses `multiprocessing` for parallel intersection across PON entries
- Uses `pandas` DataFrames for position lookup
- Calls `liftOver` for coordinate system conversion between genome builds

**Dependencies**: `multiprocessing`, `pandas`, `pysam`. No `library/` imports directly.

---

### utils/resubmit_hanging_jobs.sh

**Purpose**: SLURM job recovery utility. Identifies and resubmits SLURM jobs that have exceeded expected wall time or are in an error state. Not part of the main pipeline flow.

**Dependencies**: SLURM CLI (`squeue`, `sacct`, `sbatch`).

---

## Configuration Files - config.*.ini

**Purpose**: INI-format configuration providing genome-specific tool binary paths and resource file paths. One file per supported reference genome. Loaded by `library/config.py`.

**Sections**:

| Section | Contents |
|---|---|
| `[TOOLS]` | Absolute paths to all bioinformatics binaries (BWA, GATK3, GATK4, samtools, sambamba, picard, bcftools, CNVnator, MosaicForecast) |
| `[RESOURCES]` | Absolute paths to reference FASTA, known variant VCFs (dbSNP, Mills, 1000G), gnomAD VCF, PON files, interval lists |

**Template substitution variables**:

| Variable | Expansion |
|---|---|
| `{ENVDIR}` | Conda environment directory path (resolved at runtime) |
| `{PIPEHOME}` | Pipeline root directory path (resolved at runtime) |

**Supported reference genomes**:

| Config File | Reference Genome | Description |
|---|---|---|
| `config.b37.ini` | GRCh37 / b37 | Broad Institute b37 build |
| `config.hg19.ini` | UCSC hg19 | UCSC hg19 build |
| `config.hg38_v0.ini` | GRCh38 base | GATK resource bundle v0 |
| `config.hg38_decoy.ini` | GRCh38 + decoy + HLA | Full reference with decoy sequences and HLA region |
| `config.hg38_no_alt.ini` | GRCh38 no alt contigs | GRCh38 without alternate contigs for simpler alignment |

**Known limitation**: 5 near-identical files with no shared base template. Adding a new tool path requires updating all 5 files independently.

---

## Supporting Directories

### etc/

**Purpose**: Shell scripts for activating the Conda environment required by the pipeline. Used by SLURM job scripts to set up the execution environment before running bioinformatics tools.

### downloads/

**Purpose**: Static reference data files used by filtering stages.

| File Type | Contents | Used By |
|---|---|---|
| gnomAD VCF | Population allele frequency database for germline filtering | Stage A: `A.gnomAD_germline_filter.sh` |
| PON split files | Panel of Normals data split by chromosome for parallel masking | Stage F: `F.PON_mask.sh` |

### environment.yml and environment_frozen.yml

| File | Purpose |
|---|---|
| `environment.yml` | Conda environment definition with flexible version ranges for development |
| `environment_frozen.yml` | Conda environment definition with pinned exact versions for reproducibility |

### tests/ (EMPTY)

**Current state**: The `tests/` directory exists but contains no test files. Zero test coverage across all library modules and utility scripts. The quality configuration targets 85% coverage with DDD methodology (characterization tests), but this is not yet implemented.

### pipeline/ (DOES NOT EXIST)

**Status**: This directory was planned for future modularization to extract reusable infrastructure from `jobs/` into proper Python packages (`config/`, `io/`, `scheduler/`). It does not exist in the current codebase and should not be referenced as an existing component.
