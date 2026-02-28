#!/usr/bin/env python3

import argparse
import os
import re
import sys
from collections import deque

cmd_home = os.path.dirname(os.path.realpath(__file__))
pipe_home = os.path.normpath(cmd_home + "/..")
job_home = pipe_home + "/jobs/genome_mapping"
sys.path.append(pipe_home)

from library.config import run_info, write_run_options
from library.job_queue import sbatch_opt as opt, create_queue
from library.parser import sample_list

q = None

def main():
    global q
    args = parse_args()

    os.environ["PIPELINE_BACKEND"] = args.backend
    q = create_queue()

    global down_jid_queue
    down_jid_queue = deque([None] * args.con_down_limit)

    samples = sample_list(args.sample_list)
    for (sample, filetype), sdata in samples.items():
        print("- Sample: " + sample)

        f_run_jid = sample + "/run_jid"
        if q.num_run_jid_in_queue(f_run_jid) > 0:
            print("There are submitted jobs for this sample.")
            print("Skip to submit jobs.\n")
            continue
        q.set_run_jid(f_run_jid, new=True)

        f_run_info = sample + "/run_info"
        run_info(f_run_info, args.reference, args.conda_env)
        options = {
            "Q": args.queue,
            "CONDA_ENV": args.conda_env,
            "SAMPLE_LIST": args.sample_list,
            "ALIGNFMT": args.align_fmt,
            "FILETYPE": filetype,
            "REFVER": args.reference,
            "SKIP_CNVNATOR": args.skip_cnvnator,
            "RUN_MUTECT_SINGLE": args.run_mutect_single,
            "RUN_FILTERS": args.run_filters,
            "MULTI_ALIGNS": args.multiple_alignments,
            "TARGET_SEQ": args.target_seq,
        }
        if args.run_gatk_hc:
            ploidy = " ".join(str(i) for i in args.run_gatk_hc)
            options["RUN_GATK_HC"] = "True"
            options["PLOIDY"] = '"{}"'.format(ploidy)
        else:
            options["RUN_GATK_HC"] = args.run_gatk_hc
        write_run_options(f_run_info, options)

        if filetype == "bam":
            jid = submit_pre_jobs_bam(sample, sdata, args.queue)
        else:
            jid = submit_pre_jobs_fastq(sample, sdata, args.queue)

        submit_aln_jobs(sample, args.queue, jid)
        print()

def submit_pre_jobs_fastq(sample, sdata, Q):
    global down_jid_queue

    jid_per_read = {"R1":[], "R2":[]}
    fq_per_read = {"R1":[], "R2":[]}
    for fname, loc in sdata:
        read = "R1" if re.search("(.R1|_R1|_r1|_1)(|_001).f(|ast)q(|.gz)", fname) else "R2"

        down_jid = down_jid_queue.popleft()
        jid = q.submit(opt(sample, Q, down_jid), 
            "{job_home}/pre_1.download.sh {sample} {fname} {loc}".format(
                job_home=job_home, sample=sample, fname=fname, loc=loc))
        down_jid_queue.append(jid)

        jid_per_read[read].append(jid)
        fq_per_read[read].append("{}/downloads/{}".format(sample, fname))

    jid_list = []
    for read in ["R1", "R2"]:
        fq_files = " ".join(sorted(fq_per_read[read]))
        jid = ",".join(jid_per_read[read])
        jid_list.append(q.submit(opt(sample, Q, jid),
            "{job_home}/pre_2.split_fastq_by_RG.sh {fq_files}".format(
                job_home=job_home, fq_files=fq_files)))
    jid = ",".join(jid_list)

    return jid

def submit_pre_jobs_bam(sample, sdata, Q):
    fname, loc = sdata[0]

    global down_jid_queue
    down_jid = down_jid_queue.popleft()

    jid = q.submit(opt(sample, Q, down_jid), 
        "{job_home}/pre_1.download.sh {sample} {fname} {loc}".format(
            job_home=job_home, sample=sample, fname=fname, loc=loc))

    down_jid_queue.append(jid)

    jid = q.submit(opt(sample, Q, jid), 
        "{job_home}/pre_1b.bam2fastq.sh {sample} {fname}".format(
            job_home=job_home, sample=sample, fname=fname))
        
    jid_list = []
    for read in ["R1", "R2"]:
        jid_list.append(q.submit(opt(sample, Q, jid),
            "{job_home}/pre_2.split_fastq_by_RG.sh {sample}/fastq/{fname}.{read}.fastq.gz".format(
                job_home=job_home, sample=sample, fname=fname, read=read)))
    jid = ",".join(jid_list)

    return jid

def submit_aln_jobs(sample, Q, jid):
    q.submit(opt(sample, Q, jid),
        "{job_home}/pre_3.submit_aln_jobs.sh {sample}".format(
            job_home=job_home, sample=sample))

def parse_args():
    parser = argparse.ArgumentParser(description='Genome Mapping Pipeline')
    parser.add_argument('--con-down-limit', metavar='int', type=int,
        help='''The maximum allowded number of concurrent downloads
        [ Default: 6 ]''', default=6)
    parser.add_argument('-q', '--queue', metavar='queue', required=True,
        help='''Specify the queue name of Sun Grid Engine for jobs to be submitted''')
    parser.add_argument('-n', '--conda-env', metavar='env',
        help='''Specify the name of conda environment for pipeline [default is bp]''', default="bp")
    parser.add_argument('-t', '--target-seq', action='store_true', default=False)
    parser.add_argument('-p', '--run-gatk-hc', metavar='ploidy', type=int, nargs='+', default=False)
    parser.add_argument('--run-mutect-single', action='store_true')
    parser.add_argument('--run-filters', action='store_true', default=False)
    parser.add_argument('-m', '--multiple-alignments', action='store_true', default=False)
    parser.add_argument('--skip-cnvnator', action='store_true', default=False)
    parser.add_argument('-f', '--align-fmt', metavar='fmt',
        help='''Alignment format [cram (default) or bam]''', default="cram")
    parser.add_argument('-r', '--reference', metavar='ref',
        help='''Reference version [b37 (default) or hg19 or hg38]''', default="b37")
    parser.add_argument('--backend', choices=['auto', 'local', 'slurm'],
        default='auto', help='Execution backend [default: auto]')
    parser.add_argument('--sample-list', metavar='sample_list.txt', required=True,
        help='''Sample list file.
        Each line format is "sample_id\\tfile_name\\tlocation".
        Lines staring with "#" will omitted.
        Header line should also start with "#".
        Trailing columns will be ignored.
        "location" is LocalPath.''')
    return parser.parse_args()

if __name__ == "__main__":
    main()
