# Somatic Variant Pipeline Refactoring Plan

## Overview

Incremental refactoring plan for restructuring the somatic variant pipeline codebase
from an organically evolved HPC-only layout to a responsibility-driven, locally testable structure.

### Goals

1. Establish test coverage before any structural change
2. Enable macOS local execution (not just HPC/SLURM)
3. Separate concerns: scheduling, orchestration, domain logic, configuration
4. Incremental migration -- each phase is independently deployable and verifiable

### Constraints

- No behavioral changes until characterization tests are in place
- macOS lacks SLURM (sbatch/squeue), pysam, rpy2, pyfaidx
- Mini test fixture creation requires one-time HPC access
- Pipeline must remain functional on HPC throughout all phases

---

## Testability Layers

| Layer | Scope | Isolation | Environment |
|-------|-------|-----------|-------------|
| 1 | Pure Python logic (parser, misc, config I/O) | tmp_path | macOS, CI |
| 2 | System boundary (conda, sbatch subprocess) | monkeypatch/mock | macOS, CI |
| 3 | Bioinformatics tool execution (samtools, bwa, gatk) | mini fixture + LocalQueue | macOS (conda) |
| E2E | Full pipeline with SLURM scheduling | mini fixture + SLURM | HPC only |

---

## Phase T: Characterization Tests (Layer 1, 2)

**Goal:** Capture current behavior of testable Python code before any changes.

**Prerequisites:** None (runs on macOS now).

### T-1. Test infrastructure

- Create `pyproject.toml` with pytest configuration
- Create `tests/conftest.py` with shared fixtures:
  - `fake_env_dir`: temporary directory mimicking conda env structure (`bin/` subdir)
  - `mock_conda`: monkeypatch `subprocess.check_output` for `conda info -e`
  - `pipe_home`: fixture pointing to the real repo root
  - `sample_list_file`: temporary sample list with test entries

### T-2. Layer 1 characterization tests (pure logic)

- `tests/test_parser.py`
  - `filetype()`: bam, cram, fastq, gz-wrapped, invalid extension
  - `sample_list()`: multi-sample parsing, comment skipping, file type grouping
- `tests/test_misc.py`
  - `coroutine()` decorator: generator priming, send/yield cycle
  - `printer()`: normal output, BrokenPipeError handling
- `tests/test_config_io.py`
  - `run_info()`: file creation, content format, TOOLS/RESOURCES sections
  - `run_info_append()`: append behavior
  - `log_dir()`: directory creation
  - `save_hold_jid()`: file write with parent dir creation
- `tests/test_germline_filter.py`
  - Known input VCF + gnomAD set -> expected output (stdin/stdout filter)

### T-3. Layer 2 characterization tests (mocked boundaries)

- `tests/test_config_read.py`
  - `read_config()` with mocked conda: verify config dict keys, placeholder substitution
  - All five reference configs (b37, hg19, hg38_no_alt, hg38_decoy, hg38_v0)
- `tests/test_job_queue.py`
  - `GridEngineQueue.submit()`: mock subprocess.run, verify sbatch args, JID file recording
  - `num_run_jid_in_queue()`: mock squeue, verify counting logic
  - `set_run_jid()`: file creation and tracking
- `tests/test_submitter_dag.py`
  - Mock `GridEngineQueue` entirely, run each submitter's `main()` with synthetic args
  - Capture the sequence of `submit()` calls (script path, arguments, dependencies)
  - Snapshot the resulting job DAG for each submitter:
    - `submit_aln_jobs.py`: align -> merge -> markdup -> indel_realign -> bqsr -> post
    - `submit_gatk-hc_jobs.py`: hc_call -> concat -> vqsr (per ploidy)
    - `submit_filtering_jobs.py`: gnomAD -> PASS -> VAF -> CNV -> mayo/mosaic -> PON -> filtered
  - These DAG snapshots become the safety net for Phase 0+

### Verification

```bash
pytest tests/ -v
# All tests pass, baseline established
```

---

## Phase S: SLURM Shim + Mini Fixture

**Goal:** Enable Layer 3 (actual bioinformatics tools) to run on macOS.

**Prerequisites:** Phase T complete. Mini fixture generation requires one-time HPC access.

### S-1. SLURM shim in shell scripts

Add fallback defaults for SLURM environment variables. Each shell script's SLURM-specific
variables get a portable fallback:

```bash
# Before (SLURM-only):
NSLOTS=$SLURM_CPUS_ON_NODE

# After (portable):
NSLOTS=${SLURM_CPUS_ON_NODE:-$(nproc 2>/dev/null || sysctl -n hw.ncpu)}
```

For array jobs (`aln_5.bqsr_array.sh`):

```bash
TASK_ID=${SLURM_ARRAY_TASK_ID:?'Set SLURM_ARRAY_TASK_ID or run via sbatch'}
```

### S-2. LocalQueue implementation

Add `LocalQueue` alongside `GridEngineQueue` in `library/job_queue.py`:

```python
class LocalQueue:
    """Run jobs directly via bash instead of sbatch."""
    def submit(self, q_opt_str, cmd_str):
        # Ignore SLURM options, execute directly
        result = subprocess.run(
            ["bash"] + cmd_str.split(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding='utf-8')
        pid = str(os.getpid())
        print("Local job {} completed (exit {})".format(pid, result.returncode))
        self._append_run_jid(pid)
        return pid
```

Selection via `--local` flag in `run_*.py` entry points.

### S-3. Mini test fixture (HPC generation)

Create `tests/fixtures/generate_fixture.sh` -- a script to run once on HPC:

```bash
# Extract 100kb region from chr22
samtools faidx human_g1k_v37_decoy.fasta 22:20000000-20100000 > mini.fa
samtools faidx mini.fa
bwa index mini.fa
samtools dict mini.fa > mini.dict

# Extract reads mapping to this region
samtools view -b full.bam 22:20000000-20100000 \
    | samtools fastq -1 test_R1.fastq.gz -2 test_R2.fastq.gz -

# Extract resource VCFs for this region
bcftools view -r 22:20000000-20100000 dbsnp_138.b37.vcf.gz | bgzip > dbsnp_mini.vcf.gz
tabix dbsnp_mini.vcf.gz
# ... repeat for mills, gnomad, etc.
```

Output committed to `tests/fixtures/` (a few MB total).

Accompanying files:
- `tests/fixtures/config.test.ini` -- points to mini reference/resources
- `tests/fixtures/sample_list.txt` -- test sample definition

### S-4. macOS conda environment

Create `environment_local.yml`:

```yaml
name: bp
channels:
  - bioconda
  - conda-forge
dependencies:
  - python=3
  - bwa
  - samtools>=1.10
  - bcftools
  - sambamba
  - gatk4
  - picard
  - bgzip  # via htslib
  - tabix   # via htslib
  - vt
  - scipy
  - numpy
  - pandas
  - statsmodels
  - pytest
  # Excluded: cnvnator (ROOT dependency), rpy2, pysam, pyfaidx
```

### S-5. Layer 3 integration tests

- `tests/test_integration_mapping.py`
  - Run alignment steps on mini fixture with LocalQueue
  - Verify BAM output exists and is valid
- `tests/test_integration_calling.py`
  - Run HaplotypeCaller on mini BAM
  - Verify VCF output
- `tests/test_integration_filtering.py`
  - Run filtering steps (with --skip-cnvnator)
  - Verify filtered output

### Verification

```bash
conda env create -f environment_local.yml
conda activate bp
pytest tests/ -v  # Layer 1, 2, 3 all pass on macOS
```

---

## Phase 0: Foundation (No Behavioral Change)

**Goal:** Structural cleanup without changing any logic.

**Prerequisites:** Phase T complete (Phase S recommended but not required).

### 0-1. Package scaffolding

- Create `pyproject.toml` with `[project]` metadata (extends Phase T's pytest-only version)
- Ensure `library/__init__.py` properly exports modules

### 0-2. Config consolidation

- Create `config/` directory
- Copy config files to `config/references/{b37,hg19,hg38_no_alt,hg38_decoy,hg38_v0}.ini`
- Update `library/config.py:read_config()` to check `config/references/` first, fall back to root
- Keep root config files as symlinks to `config/references/` (backward compatibility)

### 0-3. Cleanup dead code

- Remove `opt_old()` functions from `run_variant_filtering.py`, `submit_filtering_jobs.py`
- Remove SGE `#$` comment directives from shell scripts
- ~~Remove legacy `.1` utils: rename `somatic_vaf.2.py` -> `somatic_vaf.py` (etc.)~~ **DONE**
  - ~~Update all shell script references to drop `.2.` suffix~~ **DONE**

### Verification

```bash
pytest tests/ -v  # All characterization tests still pass
# On HPC: full pipeline run with real data (optional but recommended)
```

---

## Phase 1: Extract the `run_info` Schema

**Goal:** Make the implicit Python-to-shell contract explicit and validated.

**Prerequisites:** Phase 0 complete.

### 1-1. Define schema

- Create `RunInfoSchema` (dataclass or typed dict) declaring all known keys
- Centralize `run_info` generation: replace repeated `run_info_append()` chains
  with `RunInfoSchema.write(path)`
- Add validation: warn on missing keys, unknown keys

### 1-2. Shell-side validation (optional)

- Helper function sourced by shell scripts to verify expected variables are set

### Verification

- Characterization test: generated `run_info` byte-identical to prior output
- New unit tests for schema validation

---

## Phase 2: Consolidate Submitters

**Goal:** Eliminate duplicated code across Python submitters.

**Prerequisites:** Phase 1 complete.

### 2-1. Shared SLURM option builder

- Extract `opt()` / `opt_array()` into `library/slurm_opts.py`
- Single implementation used by all 6 submitter files

### 2-2. Shared sample preparation

- Extract "parse sample list, check running jobs, generate run_info" into shared function
- Reduce each `run_*.py` to: parse args -> prepare samples -> build DAG

### 2-3. Merge `submit_aln_jobs.just_mapping.py`

- Add `--just-mapping` flag to `submit_aln_jobs.py`
- Delete the `.just_mapping` variant

### Verification

- DAG snapshot tests: submit() call sequences unchanged
- Dry-run comparison on HPC

---

## Phase 3: Unify Config Files

**Goal:** Eliminate config duplication (TOOLS section identical across 5 files).

**Prerequisites:** Phase 0 complete (can run parallel with Phase 1-2).

### 3-1. Extract shared TOOLS section

- Create `config/tools.ini` with the common TOOLS section
- Reduce each reference config to RESOURCES section only

### 3-2. Compose config

- Update `read_config()` to load `tools.ini` + `references/{ref}.ini`
- Replace root symlinks with `config/defaults.ini` (default reference setting)

### Verification

- Config reading tests: identical output for all reference versions

---

## Phase 4: Directory Reorganization

**Goal:** Move files to target structure.

**Prerequisites:** Phase 0 complete. Recommended after Phase 1-3.

### Target structure

```
somatic-variant-pipeline/
├── config/
│   ├── references/         # b37.ini, hg19.ini, hg38_*.ini
│   ├── tools.ini           # shared tool paths
│   └── defaults.ini        # default reference, conda env
├── pipeline/               # Python package
│   ├── cli/                # run_mapping.py, run_calling.py, run_filtering.py
│   ├── submitters/          # alignment.py, haplotype_caller.py, filtering.py
│   ├── core/               # config.py, scheduler.py, sample_parser.py, slurm_opts.py
│   └── analysis/           # somatic_vaf.py, strand_bias.py, repeat.py, ...
├── jobs/                   # Shell scripts only
│   ├── mapping/
│   ├── calling/
│   └── filtering/
├── tests/
│   ├── fixtures/
│   ├── test_parser.py
│   ├── ...
│   └── test_integration_*.py
├── setup/
│   └── download_resources.sh
├── downloads/
├── etc/
├── environment.yml
├── environment_local.yml
├── pyproject.toml
└── README.md
```

### 4-1. Move Python code

- `library/` -> `pipeline/core/`
- `utils/` -> `pipeline/analysis/`
- `jobs/run_*.py` -> `pipeline/cli/`
- `jobs/submit_*.py` -> `pipeline/submitters/`

### 4-2. Update references

- All `sys.path.append` -> proper package imports
- All shell `$PIPE_HOME/utils/` -> `$PIPE_HOME/pipeline/analysis/`
- All shell `$PIPE_HOME/jobs/submit_*` -> `$PIPE_HOME/pipeline/submitters/`

### 4-3. Rename job directories

- `jobs/genome_mapping/` -> `jobs/mapping/`
- `jobs/variant_calling/` -> `jobs/calling/`
- `jobs/variant_filtering/` -> `jobs/filtering/`

### Verification

- All tests pass
- Full pipeline run on HPC with real data

---

## Phase 5: Eliminate Script Variants

**Goal:** Reduce shell script count by parameterizing conditional logic.

**Prerequisites:** Phase 4 complete.

### 5-1. Merge `.malign` variants

- `C.VAF_filters.malign.sh` -> conditional in `C.VAF_filters.sh` (using `$MULTI_ALIGNS`)
- `E.mayo_filters.malign.sh` -> conditional in `E.mayo_filters.sh`
- `E.MosaicForecast.malign.sh` -> conditional in `E.MosaicForecast.sh`
- `A.CNVnator_mk_root.malign.sh` -> conditional in `A.CNVnator_mk_root.sh`

### 5-2. Update submitters

- Remove `.malign` suffix logic from `submit_filtering_jobs.py`

### Verification

- Filtering output identical for single and multi-alignment cases
- Integration tests cover both paths

---

## Phase Dependency Graph

```
Phase T (Characterization Tests)
├── Phase S (SLURM Shim + Fixture)   ← HPC access needed for fixture
├── Phase 0 (Foundation)
│   ├── Phase 1 (run_info Schema)
│   │   └── Phase 2 (Consolidate Submitters)
│   ├── Phase 3 (Unify Configs)       ← parallel with Phase 1-2
│   └── Phase 4 (Directory Reorg)     ← after Phase 1-3 recommended
│       └── Phase 5 (Script Variants)
```

Phases 1, 3 can proceed in parallel after Phase 0.
Phase S can proceed in parallel with Phase 0 after Phase T.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Characterization test misses a behavior | DAG snapshot tests catch structural changes; HPC validation for E2E |
| mini fixture doesn't cover edge cases | Fixture covers happy path; edge cases tested via Layer 1-2 mocks |
| macOS conda env diverges from HPC | `environment_local.yml` is a strict subset of `environment.yml` |
| Phase 4 breaks shell $PIPE_HOME paths | grep-based verification script checks all `$PIPE_HOME` references |
| HPC users hit breakage mid-refactor | Each phase maintains backward compatibility via symlinks/fallbacks |
