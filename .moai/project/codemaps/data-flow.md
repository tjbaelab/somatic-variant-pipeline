# Data Flow

## End-to-End Pipeline Data Flow

```mermaid
flowchart TD
    RAW(["Raw Input\nFASTQ / BAM / CRAM"])

    subgraph PHASE1["Phase 1 - Genome Mapping"]
        P1A["Stage Input\n(download or copy)"]
        P1B["Per-RG FASTQ\n(split by read group)"]
        P1C["Per-RG BAM (unsorted)\n(bwa mem)"]
        P1D["Per-RG BAM (sorted)\n(sambamba sort, 32 CPU)"]
        P1E["Merged BAM\n(samtools merge)"]
        P1F["Deduplicated BAM\n.dedup.bam\n(picard MarkDuplicates)"]
        P1G["Indel-Realigned BAM\n.realigned.bam\n(GATK3 IndelRealigner)"]
        P1H["BQSR BAM\n.bqsr.bam + .bai\n(GATK3 BaseRecalibrator + PrintReads)"]
        P1A --> P1B --> P1C --> P1D --> P1E --> P1F --> P1G --> P1H
    end

    subgraph PHASE2["Phase 2 - Variant Calling"]
        P2A["CRAM\n.cram + .crai\n(samtools view -C)"]
        P2B["Per-chromosome gVCF\n.g.vcf.gz\n(GATK4 HC array 1-24)"]
        P2C["Combined gVCF\n.combined.g.vcf.gz\n(bcftools concat)"]
        P2D["VQSR VCF\n.vqsr.vcf.gz\n(GATK4 VariantRecalibrator + ApplyVQSR)"]
        P2A --> P2B --> P2C --> P2D
    end

    subgraph PHASE3["Phase 3 - Variant Filtering"]
        P3A["gnomAD-filtered VCF\n.gnomad.vcf.gz\n(Stage A)"]
        P3B["PASS-only VCF\n.pass.vcf.gz\n(Stage B)"]
        P3C["VAF-filtered VCF\n.vaf.vcf.gz\n(Stage C)"]
        P3D["CNV-filtered VCF\n.cnv.vcf.gz\n(Stage D)"]
        P3E["Mayo-filtered VCF\n.mayo.vcf.gz\n(Stage E-branch1)"]
        P3F["Mosaic-classified VCF\n.mosaic.vcf.gz\n(Stage E-branch2)"]
        P3G["PON-masked VCF\n.pon.vcf.gz\n(Stage F)"]
        P3H["Final filtered VCF\n.final.vcf.gz + .tbi\n(Stage G)"]
        P3A --> P3B --> P3C --> P3D
        P3D --> P3E
        P3D --> P3F
        P3E --> P3G
        P3F --> P3G
        P3G --> P3H
    end

    FINAL(["Output\nFiltered Somatic Variants\n.final.vcf.gz + .tbi"])

    RAW --> P1A
    P1H -->|"hold_jid mechanism\nBAM also converted to CRAM"| P2A
    P2D -->|"hold_jid mechanism"| P3A
    P3H --> FINAL
```

---

## File Format Transformation Table

| Step | Input Format | Output Format | Tool | Intermediate Filename Pattern |
|---|---|---|---|---|
| Stage input | FASTQ / BAM | Staged FASTQ | cp / wget / samtools fastq | `<sample>.R1.fastq.gz` |
| Split by RG | Multi-RG FASTQ | Per-RG FASTQ | picard SplitSamByReadGroup | `<sample>.<rg>.R1.fastq.gz` |
| Alignment | FASTQ (paired) | Unsorted BAM | bwa mem | `<sample>.<rg>.bam` |
| Sort | Unsorted BAM | Sorted BAM | sambamba sort | `<sample>.<rg>.sorted.bam` |
| Merge | Multiple sorted BAMs | Merged BAM | samtools merge | `<sample>.merged.bam` |
| Mark duplicates | Merged BAM | Deduplicated BAM | picard MarkDuplicates | `<sample>.dedup.bam` |
| Indel realignment | Deduplicated BAM | Realigned BAM | GATK3 IndelRealigner | `<sample>.realigned.bam` |
| BQSR | Realigned BAM | Calibrated BAM | GATK3 BaseRecalibrator + PrintReads | `<sample>.bqsr.bam` |
| BAM to CRAM | BQSR BAM | CRAM | samtools view -C | `<sample>.cram` |
| Variant calling | CRAM | gVCF (per chr) | GATK4 HaplotypeCaller | `<sample>.chr<N>.g.vcf.gz` |
| gVCF concat | Per-chromosome gVCFs | Combined gVCF | bcftools concat | `<sample>.combined.g.vcf.gz` |
| VQSR | Combined gVCF | Recalibrated VCF | GATK4 VariantRecalibrator + ApplyVQSR | `<sample>.vqsr.vcf.gz` |
| gnomAD filter | VQSR VCF | Population-filtered VCF | bcftools + `germline_filter.py` | `<sample>.gnomad.vcf.gz` |
| PASS filter | gnomAD VCF | PASS-only VCF | bcftools view -f PASS | `<sample>.pass.vcf.gz` |
| VAF filters | PASS VCF | VAF-annotated VCF | `somatic_vaf.py`, `strand_bias.py`, `alt_bq_sum.py` | `<sample>.vaf.vcf.gz` |
| CNV filter | VAF VCF | CNV-excluded VCF | CNVnator + bedtools intersect | `<sample>.cnv.vcf.gz` |
| Mayo filters | CNV VCF | Expression-filtered VCF | bcftools filter (strand_bias, repeat, alt_bq) | `<sample>.mayo.vcf.gz` |
| MosaicForecast | CNV VCF | Mosaic-classified VCF | MosaicForecast ML pipeline | `<sample>.mosaic.vcf.gz` |
| PON mask | Mayo + Mosaic VCFs | PON-masked VCF | `PON_mask.2.py` + liftOver + bedtools | `<sample>.pon.vcf.gz` |
| Final output | PON VCF | Final filtered VCF | bcftools concat/merge | `<sample>.final.vcf.gz` |

---

## Phase 1 Detailed Data Flow: Genome Mapping

```mermaid
sequenceDiagram
    participant IN as Raw Input
    participant STAGE as Staged Files
    participant SPLIT as Per-RG FASTQs
    participant BWA as BWA mem (32 CPU)
    participant SORT as sambamba sort
    participant MERGE as samtools merge
    participant DEDUP as picard MarkDuplicates
    participant REALIGN as GATK3 IndelRealigner
    participant BQSR as GATK3 PrintReads

    IN->>STAGE: copy or download to work dir
    STAGE->>SPLIT: picard SplitSamByReadGroup or samtools
    Note over SPLIT: One FASTQ pair per read group
    SPLIT->>BWA: bwa mem -R @RG... reference R1.fastq R2.fastq
    BWA->>SORT: sambamba sort (in-stream, 32 CPU)
    Note over SORT: Parallel across read groups
    SORT->>MERGE: samtools merge (all per-RG BAMs)
    MERGE->>DEDUP: picard MarkDuplicates OPTICAL_DUPLICATE_PIXEL_DISTANCE=2500
    DEDUP->>REALIGN: GATK3 RealignerTargetCreator + IndelRealigner
    Note over REALIGN: Per-chromosome array job (1-24)
    REALIGN->>BQSR: GATK3 BaseRecalibrator (known sites) + PrintReads
    Note over BQSR: Per-chromosome array job, then gather
    Note over BQSR: Output: sample.bqsr.bam + sample.bqsr.bai
```

**Intermediate file location**: `<output-dir>/<sample_id>/mapping/`

**Key output**: `<output-dir>/<sample_id>/<sample_id>.bqsr.bam` + `.bai`

---

## Phase 2 Detailed Data Flow: Variant Calling

```mermaid
sequenceDiagram
    participant BQSR as BQSR BAM
    participant CRAM as CRAM Conversion
    participant HC as HaplotypeCaller\n(SLURM array 1-24)
    participant CHR as Per-chr gVCFs\n(chr1..chr24)
    participant CONCAT as bcftools concat
    participant VQSR_SNP as VQSR SNP tranches
    participant VQSR_IND as VQSR INDEL tranches
    participant FINAL as VQSR VCF

    BQSR->>CRAM: samtools view -C -T reference.fa
    Note over CRAM: Reduces storage 30-40%
    CRAM->>HC: GATK4 HaplotypeCaller -ERC GVCF\n-ploidy 2 (or 1 for sex chr)
    Note over HC: 24 parallel tasks, one per chromosome
    HC->>CHR: <sample>.chr<N>.g.vcf.gz
    CHR->>CONCAT: bcftools concat --naive-force
    CONCAT->>VQSR_SNP: GATK4 VariantRecalibrator (SNP mode)\nhapmap, omni, 1000G, dbSNP resources
    CONCAT->>VQSR_IND: GATK4 VariantRecalibrator (INDEL mode)\nMills, 1000G resources
    VQSR_SNP->>FINAL: GATK4 ApplyVQSR (SNPs)
    VQSR_IND->>FINAL: GATK4 ApplyVQSR (INDELs)
    Note over FINAL: <sample>.vqsr.vcf.gz + .tbi
```

**Intermediate file location**: `<output-dir>/<sample_id>/calling/`

**Key output**: `<output-dir>/<sample_id>/<sample_id>.vqsr.vcf.gz` + `.tbi`

---

## Phase 3 Detailed Data Flow: Variant Filtering (Stages A-G)

```mermaid
flowchart TD
    RAW_VCF["VQSR VCF\nraw somatic candidates"]

    subgraph A["Stage A - Two Parallel Tracks"]
        A_CNV["CNVnator mk_root\nBAM depth histogram\n(independent track)"]
        A_GNOMAD["gnomAD germline filter\nbcftools annotate\ngermline_filter.py\nAF threshold"]
    end

    subgraph B["Stage B - PASS Filter"]
        B1["bcftools view\n--apply-filters PASS\nRemoves VQSR-failing records"]
    end

    subgraph C["Stage C - VAF Filters"]
        C1["somatic_vaf.py\nbinomial test\npileup-based VAF"]
        C2["strand_bias.py\nFisher exact + Poisson\nstrand-aware pileup"]
        C3["alt_bq_sum.py\nalternate allele\nbase quality sum"]
    end

    subgraph D["Stage D - CNV Genotype Filter"]
        D1["CNVnator genotype\n(uses Stage A root files)"]
        D2["bedtools intersect\nexclude CNV regions"]
    end

    subgraph E["Stage E - Two Parallel Branches"]
        E1["mayo_filters*.sh\nbcftools filter expressions\nstrand_bias + repeat + alt_bq\nrepeat.py"]
        E2["MosaicForecast*.sh\nML-based mosaic classifier\nfeature extraction from BAM"]
    end

    subgraph F["Stage F - PON Mask"]
        F1["PON_mask.2.py\nmultiprocessing + pandas\nliftOver coordinate conversion"]
        F2["bedtools intersect\nexclude PON-recurrent sites"]
    end

    subgraph G["Stage G - Final VCF Assembly"]
        G1["bcftools concat/merge\nfinal output assembly\n.final.vcf.gz + .tbi"]
    end

    RAW_VCF --> A_GNOMAD
    RAW_VCF --> A_CNV
    A_GNOMAD --> B1 --> C1 --> C2 --> C3 --> D1
    A_CNV -->|"CNV root files"| D1
    D1 --> D2
    D2 --> E1
    D2 --> E2
    E1 --> F1
    E2 --> F1
    F1 --> F2 --> G1
```

### Filtering Stage Details

| Stage | Letter | Filter Logic | Python Utility | Data Sources |
|---|---|---|---|---|
| gnomAD germline | A | Remove variants with gnomAD AF above threshold (typically > 0.001) | `utils/germline_filter.py` | `downloads/gnomAD*.vcf.gz` |
| CNV root creation | A (parallel) | Create CNVnator BAM depth histogram root files | CNVnator (C++ binary) | Sample BAM/CRAM |
| PASS filter | B | Retain only GATK VQSR PASS-tagged records; remove FILTERED | bcftools only | VQSR FILTER field |
| VAF filters | C | Binomial test on VAF; Fisher exact on strand bias; alt BQ sum threshold | `utils/somatic_vaf.py`, `utils/strand_bias.py`, `utils/alt_bq_sum.py` | BAM pileup via samtools |
| CNV genotype | D | Exclude variants overlapping CNVnator-called CNV regions | CNVnator + bedtools | Stage A CNV root files |
| Mayo filters | E (branch 1) | Hard filters: strand bias ratio, tandem repeat region, alt BQ sum cutoffs | `utils/repeat.py` (via bcftools) | BAM + reference FASTA |
| MosaicForecast | E (branch 2) | ML-based somatic mosaic variant scoring and classification | MosaicForecast Python pipeline | BAM + VCF features |
| PON mask | F | Remove variants recurrently present in Panel of Normals cohort | `utils/PON_mask.2.py` | `downloads/PON*.bed` split files |
| Final assembly | G | Merge mayo and mosaic-filtered VCFs into single final output | bcftools | Stage E branch outputs |

---

## Sample Output Directory Structure

Each processed sample produces the following directory layout under the configured output root:

```
<output-dir>/
└── <sample_id>/
    ├── mapping/
    │   ├── <sample_id>.<rg>.sorted.bam           (per-RG intermediate)
    │   ├── <sample_id>.merged.bam                 (pre-dedup)
    │   ├── <sample_id>.dedup.bam                  (after MarkDuplicates)
    │   ├── <sample_id>.dedup.bam.metrics          (duplication metrics)
    │   ├── <sample_id>.realigned.bam              (after GATK3 IndelRealigner)
    │   └── <sample_id>.bqsr.bam + .bai            (final Phase 1 output)
    │
    ├── calling/
    │   ├── <sample_id>.cram + .crai               (CRAM from BQSR BAM)
    │   ├── <sample_id>.chr<N>.g.vcf.gz + .tbi    (per-chromosome gVCFs, 1-24)
    │   ├── <sample_id>.combined.g.vcf.gz + .tbi  (concatenated gVCF)
    │   └── <sample_id>.vqsr.vcf.gz + .tbi        (final Phase 2 output)
    │
    ├── filtering/
    │   ├── <sample_id>.gnomad.vcf.gz              (Stage A output)
    │   ├── <sample_id>.pass.vcf.gz                (Stage B output)
    │   ├── <sample_id>.vaf.vcf.gz                 (Stage C output)
    │   ├── <sample_id>.cnv.vcf.gz                 (Stage D output)
    │   ├── <sample_id>.mayo.vcf.gz                (Stage E branch 1)
    │   ├── <sample_id>.mosaic.vcf.gz              (Stage E branch 2)
    │   ├── <sample_id>.pon.vcf.gz                 (Stage F output)
    │   └── <sample_id>.final.vcf.gz + .tbi        (Stage G - final output)
    │
    └── logs/
        ├── mapping/
        │   ├── download.out / .err
        │   ├── align.out / .err
        │   └── bqsr.out / .err
        ├── calling/
        │   ├── haplotypecaller.chr<N>.out / .err
        │   └── vqsr.out / .err
        └── filtering/
            ├── stage_A.out / .err
            └── stage_G.out / .err
```

---

## Configuration Data Flow

```mermaid
flowchart LR
    INI["config.hg38_decoy.ini\n[TOOLS] tool binary paths\n[RESOURCES] reference data paths\n{ENVDIR} {PIPEHOME} substitution"]

    RC["library.config.read_config()\nreference='hg38_decoy'\nconda_env='somatic-pipeline'"]

    CP["ConfigParser object\nin-memory after template substitution"]

    RI["run_info file\n(shell-sourceable)\nkey=value pairs per sample\ne.g. REF=/path/ref.fa\nGATK4=/path/gatk"]

    HOLD["hold_jid storage\n(in config file)\nJID_BQSR=123456\nJID_VQSR=789012"]

    ENV["SLURM job environment\nsbatch --export=ALL\nor sbatch --export=VAR=val"]

    SH["Shell script\nsources run_info\nor uses $GATK4, $REF\nno hardcoded paths"]

    INI -->|"load and parse"| RC
    RC -->|"returns"| CP
    CP -->|"run_info_append()\nwrites key=value"| RI
    CP -->|"save_hold_jid()\npersists JID"| HOLD
    HOLD -->|"read by next phase\norchestrator"| RC
    RI -->|"sbatch --export"| ENV
    ENV -->|"available as $VAR"| SH
```

**Configuration flow summary**:
1. Researcher provides reference genome key (e.g., `hg38_decoy`) at CLI invocation.
2. `library.config.read_config()` loads `config.hg38_decoy.ini` and performs `{ENVDIR}` / `{PIPEHOME}` template substitution.
3. `run_info_append()` writes a shell-sourceable `run_info` file with all resolved paths.
4. SLURM shell scripts source or receive the `run_info` values as environment variables—zero hardcoded paths.
5. At phase completion, `save_hold_jid()` writes the final job ID back to the config file.
6. The next phase orchestrator reads the stored job ID to construct SLURM `afterok` dependency expressions.

---

## SLURM Job Dependency Chain Mechanism

The cross-phase execution ordering relies entirely on the `save_hold_jid` / `hold_jid` pattern in `library/config.py`. This allows all three orchestrator scripts to exit immediately after submission.

```
Phase 1 submission:
  run_genome_mapping.py runs on login node (seconds)
  → submits aln chain, saves JID_BQSR to config
  → exits immediately

SLURM scheduler runs Phase 1 jobs:
  download → split → align → merge → markdup → realign → bqsr
  (hours to days on compute nodes)

Phase 2 submission:
  run_variant_calling.py runs on login node (seconds)
  → reads JID_BQSR from config
  → submits: gatk-hc with -d afterok:JID_BQSR
  → saves JID_VQSR to config
  → exits immediately

SLURM waits for JID_BQSR to complete, then runs Phase 2 jobs:
  bam2cram → haplotypecaller (array 1-24) → concat → vqsr
  (hours to days)

Phase 3 submission:
  run_variant_filtering.py runs on login node (seconds)
  → reads JID_VQSR from config
  → submits: stage A with -d afterok:JID_VQSR
  → chains stages B through G
  → exits immediately

SLURM runs Phase 3 stages A → B → C → D → E(both) → F → G
```

The researcher can submit all three phases in sequence on the login node within minutes. The HPC scheduler guarantees correct execution ordering through the persisted job IDs.
