#!/usr/bin/env python3

import argparse
import os
import sys

cmd_home = os.path.dirname(os.path.realpath(__file__))
pipe_home = os.path.normpath(cmd_home + "/..")
job_home = pipe_home + "/jobs/variant_filtering"
sys.path.append(pipe_home)

from library.config import run_info, write_run_options
from library.parser import sample_list
from library.job_queue import sbatch_opt as opt, create_queue

q = None

def main():
    global q
    args = parse_args()

    os.environ["PIPELINE_BACKEND"] = args.backend
    q = create_queue()

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
            "RUN_FILTERS": args.run_filters,
            "MULTI_ALIGNS": len(sdata) > 1,
        }
        if args.run_gatk_hc:
            ploidy = " ".join(str(i) for i in args.run_gatk_hc)
            options["RUN_GATK_HC"] = "True"
            options["PLOIDY"] = '"{}"'.format(ploidy)
        else:
            options["RUN_GATK_HC"] = args.run_gatk_hc
        write_run_options(f_run_info, options)

        #if filetype == "fastq":
        #    raise Exception("The input filetype should be bam or cram.")

        if args.vcf_directory is not None:
            q.submit(opt(sample, args.queue),
                "{job_home}/prep/start_variant_filtering.sh {sample} {vcf_dir}".format(
                    job_home=job_home, sample=sample, vcf_dir=args.vcf_directory))
        else:
            q.submit(opt(sample, args.queue),
                "{job_home}/prep/start_variant_filtering.sh {sample}".format(job_home=job_home, sample=sample))

        print()

def parse_args():
    parser = argparse.ArgumentParser(description='Variant Filtering Pipeline')
    parser.add_argument('-q', '--queue', metavar='queue', required=True,
        help='''Specify the queue name of Sun Grid Engine for jobs to be submitted''')
    parser.add_argument('-n', '--conda-env', metavar='env',
        help='''Specify the name of conda environment for pipeline [default is bp]''', default="bp")
    parser.add_argument('-p', '--run-gatk-hc', metavar='ploidy', type=int, nargs='+', default=False)
    parser.add_argument('--skip-cnvnator', action='store_true', default=False)
    parser.add_argument('--run-filters', action='store_true', default=True)
    parser.add_argument('-f', '--align-fmt', metavar='fmt',
        help='''Alignment format [cram (default) or bam]''', default="cram")
    parser.add_argument('-r', '--reference', metavar='ref',
        help='''Reference version [b37 (default) or hg19]''', default="b37")
    parser.add_argument('-v', '--vcf-directory', metavar='dir',
        help='''Specify a directory where existing VCF files are, if you have.
        VCF file for each ploidy will be linked into the sample directory before running the filtering.
        VCF and index file names must be formed as follows:
            <sample name>.ploidy_<ploidy>.vcf.gz
            <sample name>.ploidy_<ploidy>.vcf.gz.tbi
        [Default: None]''', default=None)
    parser.add_argument('--backend', choices=['auto', 'local', 'slurm'],
        default='auto', help='Execution backend [default: auto]')
    parser.add_argument('--sample-list', metavar='sample_list.txt', required=True,
        help='''Sample list file.
        Each line format is "sample_id\\tfile_name\\tlocation".
        Lines staring with "#" will omitted.
        Header line should also start with "#".
        Trailing columns will be ignored.''')
    return parser.parse_args()

if __name__ == "__main__":
    main()
