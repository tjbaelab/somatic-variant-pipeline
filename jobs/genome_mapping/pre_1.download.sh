#!/bin/bash

#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mem=1G
#SBATCH --time=04:00:00
#SBATCH --signal=USR1@60

trap "exit 100" ERR

if [[ $# -lt 3 ]]; then
    echo "Usage: $(basename $0) <sample name> <file name> <location>"
    false
fi

SM=$1
FNAME=$2
LOC=$3

source $(pwd)/$SM/run_info

set -o nounset
set -o pipefail

mkdir -p $SM/run_status
DONE=$SM/run_status/pre_1.download.$FNAME.done

printf -- "---\n[$(date)] Start download: $FNAME\n"

if [[ -f $DONE ]]; then
    echo "Skip this step."
else
    mkdir -p $SM/downloads

    rc=0
    n=0
    until [[ $n -eq 5 ]]; do
        printf "[$(date)] Download try $n starts.\n\n"
        
        ls -lh $LOC && ln -sf $(readlink -f $LOC) $SM/downloads/$FNAME || rc=$?
        break

        n=$((n+1))
        printf "[$(date)] Download try $n failed.\n\n"
    done
    [[ $rc -eq 0 ]] || false
    rm -f $SM/downloads/$FNAME.*
    touch $DONE
fi

printf -- "[$(date)] Finish downlaod: $FNAME\n---\n"