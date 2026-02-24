#!/usr/bin/env python3

import argparse
import os
import sys
from collections import defaultdict, deque

cmd_home = os.path.dirname(os.path.realpath(__file__))
pipe_home = os.path.normpath(cmd_home + "/..")
job_home = pipe_home + "/jobs/variant_calling"
sys.path.append(pipe_home)

from library.config import run_info, write_run_options
from library.parser import sample_list
from library.job_queue import GridEngineQueue, sbatch_opt as opt
q = GridEngineQueue()

def main():
    args = parse_args()

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
            "RUN_FILTERS": args.run_filters,
            "MULTI_ALIGNS": len(sdata) > 1,
            "SKIP_CNVNATOR": args.skip_cnvnator,
            "RUN_MUTECT_SINGLE": args.run_mutect_single,
        }
        if args.run_gatk_hc:
            ploidy = " ".join(str(i) for i in args.run_gatk_hc)
            options["RUN_GATK_HC"] = "True"
            options["PLOIDY"] = '"{}"'.format(ploidy)
            options["MAX_GAUSSIANS"] = args.max_gaussians
        else:
            options["RUN_GATK_HC"] = args.run_gatk_hc
        write_run_options(f_run_info, options)

        if filetype == "fastq":
            raise Exception("The input filetype should be bam or cram.")

        #global down_jid
        #jid_list = []
        #for fname, loc in sdata:
        #    down_jid = down_jid_queue.popleft()
        #    jid = q.submit(opt(sample, args.queue, down_jid), 
        #            "{job_home}/pre_1.download.sh {sample} {fname} {loc}".format(
        #                job_home=job_home, sample=sample, fname=fname, loc=loc))
        #    jid_list.append(jid)
        #    down_jid_queue.append(jid)
        #jid = ",".join(jid_list)

        if args.align_fmt == "cram" and filetype == "bam":
            raise Exception("alignment format should be set to {}".format(filetype))
            #jid = q.submit(opt(sample, args.queue),
            #    "{job_home}/pre_2.bam2cram.sh {sample}".format(
            #        job_home=job_home, sample=sample))
            #jid = q.submit(opt(sample, args.queue, jid),
            #    "{job_home}/pre_2b.unmapped_reads.sh {sample}".format(
            #        job_home=job_home, sample=sample))

        #jid = q.submit(opt(sample, args.queue, jid),
        jid = q.submit(opt(sample, args.queue),
            "{job_home}/pre_3.run_variant_calling.sh {sample}".format(
                job_home=job_home, sample=sample))

        print()

def parse_args():
    parser = argparse.ArgumentParser(description='Variant Calling Pipeline')
    parser.add_argument('--con-down-limit', metavar='int', type=int,
        help='''The maximum allowded number of concurrent downloads
        [ Default: 6 ]''', default=6)
    parser.add_argument('-q', '--queue', metavar='queue', required=True,
        help='''Specify the queue name of Sun Grid Engine for jobs to be submitted''')
    parser.add_argument('-n', '--conda-env', metavar='env',
        help='''Specify the name of conda environment for pipeline [default is bp]''', default="bp")
    parser.add_argument('-p', '--run-gatk-hc', metavar='ploidy', type=int, nargs='+', default=False)
    parser.add_argument('--max-gaussians', metavar='int', type=int,
        help='''Set the maximum number of Gaussians for gatk VQSR step''', default=4)
    parser.add_argument('--run-mutect-single', action='store_true')
    parser.add_argument('--skip-cnvnator', action='store_true', default=False)
    parser.add_argument('--run-filters', action='store_true', default=False)
    parser.add_argument('-f', '--align-fmt', metavar='fmt',
        help='''Alignment format [cram (default) or bam]''', default="cram")
    parser.add_argument('-r', '--reference', metavar='ref',
        help='''Reference version [b37 (default) or hg19]''', default="b37")
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
