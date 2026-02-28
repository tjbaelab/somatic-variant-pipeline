import shutil
import subprocess
import re
import os


from library.config import log_dir


def sbatch_opt(sample, Q, jid=None):
    """Build sbatch options for a single job."""
    opt = "--partition={q} --output {log_dir}/%x.%j.stdout --error {log_dir}/%x.%j.stderr --parsable".format(q=Q, log_dir=log_dir(sample))
    if jid is not None:
        opt = "-d afterok:{jid} {opt}".format(jid=jid, opt=opt)
    return opt


def sbatch_opt_array(sample, Q, jid=None):
    """Build sbatch options for an array job."""
    opt = "--partition={q} --output {log_dir}/%x.%A.%a.stdout --error {log_dir}/%x.%A.%a.stderr --parsable".format(q=Q, log_dir=log_dir(sample))
    if jid is not None:
        opt = "-d afterok:{jid} {opt}".format(jid=jid, opt=opt)
    return opt


class SlurmQueue:

    def __init__(self):
        self.run_jid = None

    def num_run_jid_in_queue(self, fname):
        if os.path.exists(fname):
            jid = ",".join([line.strip() for line in open(fname)])
            if jid == "":
                n = 0
            else:
                n = int(subprocess.run("squeue -h --jobs {jid} |wc -l".format(jid=jid), 
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       shell=True, encoding='utf-8').stdout)
        else:
            n = 0
        return n

    def set_run_jid(self, fname, new=False):
        if new:
            os.makedirs(os.path.dirname(fname), exist_ok=True)
            open(fname, 'w').close()
        self.run_jid = fname

    def _append_run_jid(self, jid):
        if self.run_jid is not None:
            with open(self.run_jid, "a") as f:
                print(jid, file=f)

    def submit(self, q_opt_str, cmd_str):
        qsub_cmd_list = ["sbatch"] + q_opt_str.split() + cmd_str.split()
        jid = subprocess.run(qsub_cmd_list,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding='utf-8').stdout.rstrip()

        print("Your job {jid} has been submitted".format(jid=jid))

        self._append_run_jid(jid)
        return jid


GridEngineQueue = SlurmQueue


class LocalQueue:
    """Executes jobs locally via subprocess. No SLURM required."""

    def __init__(self, max_cpus=None):
        self._next_jid = 1
        self._completed = {}
        self.run_jid = None
        self.max_cpus = max_cpus or os.cpu_count() or 1

    def submit(self, q_opt_str, cmd_str):
        jid = str(self._next_jid)
        self._next_jid += 1

        deps = self._parse_deps(q_opt_str)
        array_spec = self._parse_array(q_opt_str)

        for dep in deps:
            if self._completed.get(dep, 0) != 0:
                print("Job {jid} skipped: dependency {dep} failed".format(
                    jid=jid, dep=dep))
                self._completed[jid] = 1
                self._append_run_jid(jid)
                return jid

        env = self._build_env()
        cmd_parts = cmd_str.split()

        if array_spec:
            rc = 0
            for task_id in array_spec:
                env['SLURM_ARRAY_TASK_ID'] = str(task_id)
                result = subprocess.run(cmd_parts, env=env)
                if result.returncode != 0:
                    rc = result.returncode
            self._completed[jid] = rc
        else:
            result = subprocess.run(cmd_parts, env=env)
            self._completed[jid] = result.returncode

        print("Your job {jid} has been submitted".format(jid=jid))
        self._append_run_jid(jid)
        return jid

    def set_run_jid(self, fname, new=False):
        if new:
            os.makedirs(os.path.dirname(fname), exist_ok=True)
            open(fname, 'w').close()
        self.run_jid = fname

    def num_run_jid_in_queue(self, fname):
        return 0

    def _append_run_jid(self, jid):
        if self.run_jid is not None:
            with open(self.run_jid, "a") as f:
                print(jid, file=f)

    def _build_env(self):
        env = os.environ.copy()
        env['SLURM_CPUS_ON_NODE'] = str(self.max_cpus)
        return env

    def _parse_deps(self, q_opt_str):
        m = re.search(r'afterok:(\S+)', q_opt_str)
        return m.group(1).split(',') if m else []

    def _parse_array(self, q_opt_str):
        m = re.search(r'--array=(\d+)-(\d+)', q_opt_str)
        return list(range(int(m.group(1)), int(m.group(2)) + 1)) if m else []


def create_queue(backend=None, max_cpus=None):
    """Factory: select execution backend.

    backend: "local", "slurm", "auto", or None (reads PIPELINE_BACKEND env var).
    """
    if backend is None:
        backend = os.environ.get("PIPELINE_BACKEND", "auto")
    if backend == "local":
        return LocalQueue(max_cpus=max_cpus)
    if backend == "slurm":
        return SlurmQueue()
    if shutil.which("sbatch"):
        return SlurmQueue()
    return LocalQueue(max_cpus=max_cpus)
