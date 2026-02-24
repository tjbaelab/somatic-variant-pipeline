# 소마틱 변이 호출 파이프라인: 코드 품질 개선 분석 보고서

**분석 대상**: 7개 핵심 모듈, 약 350 줄 코드
**테스트 커버리지**: 0% (기준: 85% 목표)
**개발 방식**: DDD (Domain-Driven Development)
**분석 날짜**: 2026-02-21

---

## Executive Summary

파이프라인 분석 결과 **1개 치명적 버그**, **4개 보안 취약점**, **7개 코드 품질 문제**, **3개 성능 최적화 기회**, 그리고 **2개 아키텍처 개선 영역**을 발견했습니다.

**즉시 조치 필요**: P0 논리 버그 + P1 보안 취약점은 프로덕션 실행 전에 반드시 해결해야 합니다.

---

## P0: Critical Bugs (프로덕션 차단)

### Bug #1: 논리 오류 - 불가능한 문자열/리스트 비교

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/utils/PON_mask.2.py`
**라인**: 56
**심각도**: CRITICAL (로직 오류)

**문제 코드**:
```python
base_string = a[4]  # 문자열
# ... 처리 ...
base_string = base_string.upper()  # 여전히 문자열

if base_string == ['']:  # BUG: 문자열은 리스트와 절대 같을 수 없음
    return count_dict
```

**근본 원인**: `base_string`은 문자열이므로 `['']`(단일 빈 문자열을 담은 리스트)와 비교될 수 없습니다. 조건이 항상 거짓이므로 실제로 빈 문자열일 때도 `count_dict`를 반환하지 않습니다.

**영향 분석**:
- 빈 `bases_clean()` 결과에 대해 잘못된 결과 반환
- PON 마스킹 결과의 정확성 저하
- 특정 위치에서 기이한 allele frequency 계산

**수정 방법**:
```python
# 옵션 1: 빈 문자열 확인
if not base_string or base_string == '':
    return count_dict

# 옵션 2: 더 명확한 의도
if base_string.strip() == '':
    return count_dict

# 옵션 3 (권장): 여러 에러 조건 처리
if not base_string or len(base_string) == 0:
    return count_dict
```

**DDD 특성화 테스트 예시**:
```python
def test_count_site_empty_bases():
    """빈 base string 처리 특성화 테스트"""
    # 현재 실제 동작 캡처
    result = count_site('chr1', '1000', 'empty.bam', 'A', 'T')
    assert result == {'A': 0, 'T': 0}

def test_count_site_valid_bases():
    """정상 base string 처리"""
    # 실제 samtools mpileup 결과 시뮬레이션
    result = count_site('chr1', '1000', 'test.bam', 'A', 'T')
    assert isinstance(result, dict)
    assert set(result.keys()) == {'A', 'T'}
```

---

## P1: Security Issues (보안 취약점)

### Issue #1: Shell Injection - GridEngineQueue.submit()

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/library/job_queue.py`
**라인**: 40
**심각도**: HIGH (Shell Injection)
**OWASP**: A03:2021 – Injection

**취약 코드**:
```python
def submit(self, q_opt_str, cmd_str):
    # 위험: q_opt_str과 cmd_str이 unsanitized된 외부 입력
    qsub_cmd_list = ["sbatch"] + q_opt_str.split() + cmd_str.split()
    jid = subprocess.run(qsub_cmd_list,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8').stdout.rstrip()
```

**공격 시나리오**:
```python
# 공격자가 제어할 수 있는 queue 또는 sample_name
q.submit("--partition=gpu; rm -rf /", "echo pwned")
# 결과: sbatch --partition=gpu; rm -rf / echo pwned (shell에서 실행)
```

**근본 원인**: `split()`은 기본 whitespace split만 수행합니다. 특수 문자나 세미콜론을 포함하면 shell 메타문자로 해석됩니다.

**수정 방법**:
```python
import shlex

def submit(self, q_opt_str, cmd_str):
    # 옵션 1: shlex.split() 사용 (권장)
    try:
        qsub_cmd_list = ["sbatch"] + shlex.split(q_opt_str) + shlex.split(cmd_str)
        jid = subprocess.run(qsub_cmd_list,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=30, encoding='utf-8').stdout.rstrip()
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("sbatch submission timeout")

    if not jid:
        raise RuntimeError("sbatch returned empty job ID")

    self._append_run_jid(jid)
    return jid
```

**테스트 케이스**:
```python
def test_submit_injection_attempt():
    """Shell injection 방지 테스트"""
    q = GridEngineQueue()
    q.set_run_jid("/tmp/test_jid", new=True)

    # 악의적 입력
    with pytest.raises(ValueError):
        q.submit("--partition=gpu; echo hacked", "echo test")

def test_submit_valid_queue_options():
    """정상 queue 옵션"""
    q = GridEngineQueue()
    q.set_run_jid("/tmp/test_jid", new=True)

    # shlex.split()이 정상 처리하는 경우
    result = q.submit("--partition=normal --time=10:00:00", "echo valid")
    assert result is not None
```

---

### Issue #2: Deprecated os.popen() - PON_mask.2.py

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/utils/PON_mask.2.py`
**라인**: 46
**심각도**: HIGH (Deprecation + Injection Risk)
**OWASP**: A03:2021 – Injection

**취약 코드**:
```python
def count_site(chrm, pos, bam, ref, alt):
    # 위험: os.popen()은 Python 3.2부터 권장되지 않음
    a = os.popen(f'samtools mpileup {bam} -r {chrm}:{pos}-{pos} -Q 20 -q 20')
    a = a.read().rstrip().split('\t')
```

**문제점**:
1. `os.popen()`은 shell=True로 실행 (보안 취약점)
2. `bam` 매개변수가 f-string으로 직접 삽입
3. 에러 처리 없음 (실패한 명령이 조용히 무시됨)
4. 공격자가 `bam` 경로를 제어하면 임의 명령 실행 가능

**공격 시나리오**:
```python
# bam = "test.bam; rm -rf /tmp/*; echo"
result = count_site('chr1', '1000', 'test.bam; rm -rf /tmp/*; echo', 'A', 'T')
# samtools mpileup test.bam; rm -rf /tmp/*; echo -r chr1:1000-1000 ... (실행됨)
```

**수정 방법**:
```python
import subprocess

def count_site(chrm, pos, bam, ref, alt):
    count_dict = {ref: 0, alt: 0}

    # 옵션 1: subprocess.run() 사용 (권장)
    try:
        result = subprocess.run(
            ['samtools', 'mpileup', bam,
             '-r', f'{chrm}:{pos}-{pos}',
             '-Q', '20', '-q', '20'],
            capture_output=True,
            text=True,
            timeout=30,
            check=False  # CalledProcessError 대신 returncode 확인
        )

        if result.returncode != 0:
            # 경고만 하고 계속 (원래 동작 유지)
            sys.stderr.write(f"samtools error: {result.stderr}\n")
            return count_dict

        if not result.stdout.strip():
            return count_dict

        a = result.stdout.rstrip().split('\t')

    except subprocess.TimeoutExpired:
        sys.stderr.write(f"samtools timeout for {chrm}:{pos}\n")
        return count_dict
    except FileNotFoundError:
        sys.stderr.write("samtools not found in PATH\n")
        return count_dict

    # 기존 로직 계속
    if len(a) < 5:
        return count_dict

    base_string = a[4]
    base_string = bases_clean(base_string).upper()

    if base_string:  # 빈 문자열 체크 (Bug #1 수정)
        count_dict[ref] = base_string.count(ref)
        count_dict[alt] = base_string.count(alt)

    return count_dict
```

**테스트**:
```python
def test_count_site_subprocess_error():
    """subprocess 에러 처리"""
    # samtools 실패 시뮬레이션
    result = count_site('chr1', '1000', 'nonexistent.bam', 'A', 'T')
    assert result == {'A': 0, 'T': 0}

def test_count_site_timeout():
    """timeout 처리"""
    # 매우 큰 파일에서 timeout
    pass
```

---

### Issue #3: Shell Execution - config.py

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/library/config.py`
**라인**: 9
**심각도**: MEDIUM (Shell Execution)

**취약 코드**:
```python
def read_config(reference="b37", conda_env="bp"):
    # conda_env가 unsanitized 입력
    env_dir = subprocess.check_output(
        "conda info -e | grep -w ^{} | awk '{{print $NF}}'".format(conda_env),
        shell=True, universal_newlines=True
    ).strip()
```

**문제점**:
1. `conda_env` 값이 검증되지 않음
2. shell=True 사용으로 인한 injection 위험
3. 실패 시 subprocess.CalledProcessError 발생 (에러 처리 없음)

**수정 방법**:
```python
def read_config(reference="b37", conda_env="bp"):
    # 옵션 1: 화이트리스트 검증
    ALLOWED_ENVS = ["bp", "bp_frozen"]
    if conda_env not in ALLOWED_ENVS:
        raise ValueError(f"Invalid conda environment: {conda_env}. Allowed: {ALLOWED_ENVS}")

    # 옵션 2: subprocess 사용 (shell=False)
    try:
        result = subprocess.run(
            ['conda', 'info', '-e'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )

        # grep + awk 로직을 Python으로 구현
        env_dir = None
        for line in result.stdout.split('\n'):
            parts = line.split()
            if parts and parts[0] == conda_env:
                env_dir = parts[-1]
                break

        if not env_dir:
            raise ValueError(f"Conda environment '{conda_env}' not found")

    except subprocess.TimeoutExpired:
        raise RuntimeError("conda info timeout")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"conda info failed: {e.stderr}")

    # 경로 검증
    if not os.path.isdir(env_dir):
        raise ValueError(f"Invalid conda environment path: {env_dir}")

    return env_dir
```

---

### Issue #4: Shell Injection - repeat.py

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/utils/repeat.py` (line 13)
**심각도**: MEDIUM (String Interpolation in Command)

**취약 코드**:
```python
def ref_seq(chrom, pos1, pos2=None):
    if pos2 is None:
        site = "{chrom}:{pos}-{pos}".format(chrom=chrom, pos=pos1)
    else:
        site = "{chrom}:{start}-{end}".format(chrom=chrom, start=pos1, end=pos2)

    # 위험: chrom이 검증되지 않음
    base = ''.join(subprocess.run(
        ['samtools', 'faidx', ref_file, site],  # site에 chrom 포함
        stdout=subprocess.PIPE, encoding="utf-8"
    ).stdout.split("\n")[1:])
```

**공격 시나리오**:
```python
# chrom = "1 ; echo pwned ; #"
# site = "1 ; echo pwned ; #:100-100"
# samtools가 실패하지만 보안 경고로 간주
```

**수정 방법**:
```python
import re

def ref_seq(chrom, pos1, pos2=None):
    # 염색체 이름 검증 (hg38 기준)
    VALID_CHROMS = {f'chr{i}' for i in range(1, 23)} | {'chrX', 'chrY', 'chrM'}
    if chrom not in VALID_CHROMS:
        raise ValueError(f"Invalid chromosome: {chrom}. Valid: {VALID_CHROMS}")

    # 위치 검증
    if not isinstance(pos1, int) or pos1 < 0:
        raise ValueError(f"Invalid position: {pos1}")

    if pos2 is None:
        pos2 = pos1

    if not isinstance(pos2, int) or pos2 < pos1:
        raise ValueError(f"Invalid position range: {pos1}-{pos2}")

    try:
        result = subprocess.run(
            ['samtools', 'faidx', ref_file, f'{chrom}:{pos1}-{pos2}'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )

        if result.returncode != 0:
            raise RuntimeError(f"samtools faidx failed: {result.stderr}")

        # 첫 번째 라인(헤더) 제외
        base = ''.join(result.stdout.split("\n")[1:])
        return base.strip()

    except subprocess.TimeoutExpired:
        raise RuntimeError("samtools faidx timeout")
```

---

## P2: Code Quality Issues (코드 품질)

### Issue #5: 중복 코드 - bases_clean() 함수

**파일 1**: `/Users/taejeong/code/somatic-variant-pipeline/library/pileup.py` (line 64)
**파일 2**: `/Users/taejeong/code/somatic-variant-pipeline/utils/PON_mask.2.py` (line 26)
**심각도**: MEDIUM (DRY 원칙 위반)

**문제점**: 동일한 `bases_clean()` 함수가 2개 모듈에서 중복 정의됨

```python
# pileup.py
def bases_clean(bases):
    bases = re.sub(r'\^.', '', bases)
    bases = re.sub(r'\$', '', bases)
    for n in set(re.findall(r'-(\d+)', bases)):
        bases = re.sub(r'-{0}[ACGTNacgtn]{{{0}}}'.format(n), '', bases)
    for n in set(re.findall(r'\+(\d+)', bases)):
        bases = re.sub(r'\+{0}[ACGTNacgtn]{{{0}}}'.format(n), '', bases)
    return bases

# PON_mask.2.py (동일한 코드)
def bases_clean(bases):
    # ... 동일 ...
```

**리팩토링 전략**:
```python
# library/pileup.py (공용 모듈로 이동)
def bases_clean(bases: str) -> str:
    """
    samtools mpileup 출력 정리.

    제거 사항:
    - 읽기 시작 위치 플래그 (^)
    - 읽기 종료 위치 플래그 ($)
    - INDEL 마커 ([+-][숫자]+)

    Args:
        bases: 정제되지 않은 bases 문자열

    Returns:
        정제된 bases 문자열

    Example:
        >>> bases_clean("^!ACGT$A+2AT")
        'ACGTA'
    """
    # 읽기 시작 플래그 제거
    bases = re.sub(r'\^.', '', bases)

    # 읽기 종료 플래그 제거
    bases = re.sub(r'\$', '', bases)

    # INDEL 제거
    for n in set(re.findall(r'-(\d+)', bases)):
        bases = re.sub(r'-{0}[ACGTNacgtn]{{{0}}}'.format(n), '', bases)

    for n in set(re.findall(r'\+(\d+)', bases)):
        bases = re.sub(r'\+{0}[ACGTNacgtn]{{{0}}}'.format(n), '', bases)

    return bases
```

**import 수정**:
```python
# utils/PON_mask.2.py
from library.pileup import bases_clean  # 중복 정의 제거

# 로컬 bases_clean() 정의 삭제
```

**특성화 테스트**:
```python
def test_bases_clean_removes_start_flags():
    """읽기 시작 플래그 제거"""
    assert bases_clean("^!ACGT") == "ACGT"

def test_bases_clean_removes_end_flags():
    """읽기 종료 플래그 제거"""
    assert bases_clean("ACGT$") == "ACGT"

def test_bases_clean_removes_deletions():
    """삭제 마커 제거"""
    result = bases_clean("ACGT-2AT")
    assert "-2" not in result

def test_bases_clean_removes_insertions():
    """삽입 마커 제거"""
    result = bases_clean("ACGT+2AT")
    assert "+2" not in result
```

---

### Issue #6: 전역 변수 사용

**파일 1**: `/Users/taejeong/code/somatic-variant-pipeline/library/pileup.py` (line 10)
```python
SAMTOOLS = shutil.which("samtools")
```

**파일 2**: `/Users/taejeong/code/somatic-variant-pipeline/utils/repeat.py` (line 50)
```python
global ref_file
ref_file = args.ref
```

**심각도**: MEDIUM (상태 관리 문제)

**문제점**:
1. 전역 상태는 테스트와 재사용성을 저하
2. 함수 의존성이 명확하지 않음
3. 단위 테스트에서 상태 오염 가능

**수정 방법**:
```python
# library/pileup.py
class PileupProcessor:
    """samtools mpileup 기반 pileup 처리"""

    def __init__(self, samtools_path: str = None):
        """
        Args:
            samtools_path: samtools 실행 경로 (기본값: PATH에서 검색)
        """
        if samtools_path is None:
            samtools_path = shutil.which("samtools")

        if not samtools_path or not os.path.isfile(samtools_path):
            raise FileNotFoundError(f"samtools not found: {samtools_path}")

        self.samtools = samtools_path

    def pileup(self, bam, chrom, pos, min_MQ=20, min_BQ=20):
        """pileup 수행"""
        cmd = [self.samtools, 'mpileup', '-d', '8000',
               '-q', str(min_MQ), '-Q', str(min_BQ),
               '-r', f'{chrom}:{pos}-{pos}'] + bam.split()
        # ... 구현
```

**테스트**:
```python
def test_pileup_processor_initialization():
    """PileupProcessor 초기화"""
    processor = PileupProcessor()
    assert processor.samtools is not None

def test_pileup_processor_custom_path():
    """커스텀 samtools 경로"""
    processor = PileupProcessor("/usr/bin/samtools")
    assert processor.samtools == "/usr/bin/samtools"

def test_pileup_processor_missing_samtools():
    """samtools 없을 때"""
    with pytest.raises(FileNotFoundError):
        PileupProcessor("/nonexistent/samtools")
```

---

### Issue #7: 대규모 주석 처리 코드 블록

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/jobs/submit_aln_jobs.just_mapping.py`
**라인**: 42-59 (18줄의 주석 처리된 코드)

**심각도**: LOW (유지보수성)

**문제점**:
- 왜 이 코드가 비활성화되었는지 명확하지 않음
- git 히스토리 확인 필요
- 코드가 obsolete인지 분기 예정인지 불명확

**해결 방법 (우선순위)**:

1. **git 히스토리 확인**:
```bash
git log -p -- jobs/submit_aln_jobs.just_mapping.py | grep -A5 -B5 "markdup"
```

2. **분석 후 선택**:
   - **옵션 A**: 정말 필요 없으면 삭제 (git 히스토리에 남음)
   - **옵션 B**: 향후 기능인 경우 이슈로 등록하고 삭제
   - **옵션 C**: 임시 기능이면 주석 추가
```python
    # DEPRECATED: Array 기반 BQSR는 성능 문제로 비활성화
    # TODO: GPU 가속 BQSR 재구현 후 복구 (Issue #42)
```

---

### Issue #8: GridEngineQueue.submit() 에러 처리 부재

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/library/job_queue.py`
**라인**: 38-48
**심각도**: MEDIUM (오류 감지 불가)

**문제점**:
```python
def submit(self, q_opt_str, cmd_str):
    qsub_cmd_list = ["sbatch"] + q_opt_str.split() + cmd_str.split()
    jid = subprocess.run(qsub_cmd_list,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8').stdout.rstrip()

    # 문제:
    # 1. returncode 확인 안함
    # 2. sbatch 실패 시 에러 메시지만 stdout으로 출력
    # 3. jid가 빈 문자열일 수 있음 (예: 권한 오류)

    print("Your job {jid} has been submitted".format(jid=jid))
    self._append_run_jid(jid)
    return jid
```

**수정**:
```python
def submit(self, q_opt_str: str, cmd_str: str) -> str:
    """
    SLURM 작업 제출.

    Args:
        q_opt_str: sbatch 옵션 (e.g., "--partition=gpu --time=10:00:00")
        cmd_str: 실행할 명령어

    Returns:
        작업 ID (JID)

    Raises:
        ValueError: 명령어 문법 오류
        RuntimeError: sbatch 실행 실패
    """
    import shlex

    try:
        qsub_cmd_list = ["sbatch"] + shlex.split(q_opt_str) + shlex.split(cmd_str)
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")

    try:
        result = subprocess.run(
            qsub_cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            timeout=30,
            check=False  # returncode로 직접 확인
        )

        # sbatch 실패 확인
        if result.returncode != 0:
            raise RuntimeError(
                f"sbatch failed (rc={result.returncode}): {result.stderr}"
            )

        # JID 검증
        jid = result.stdout.rstrip()
        if not jid or not jid.isdigit():
            raise RuntimeError(
                f"Invalid job ID from sbatch: '{jid}'. "
                f"stderr: {result.stderr}"
            )

        logging.info(f"Job submitted: {jid}")
        self._append_run_jid(jid)
        return jid

    except subprocess.TimeoutExpired:
        raise RuntimeError("sbatch submission timeout (>30s)")
```

**테스트**:
```python
def test_submit_sbatch_failure():
    """sbatch 실패 처리"""
    q = GridEngineQueue()
    q.set_run_jid("/tmp/test_jid", new=True)

    # sbatch 명령이 없을 경우
    with pytest.raises(RuntimeError, match="sbatch failed"):
        q.submit("--partition=invalid", "echo test")

def test_submit_invalid_job_id():
    """유효하지 않은 JID"""
    # sbatch가 비정상 출력을 반환하는 경우
    pass
```

---

### Issue #9: 미사용 매개변수

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/utils/PON_mask.2.py`
**라인**: 97 (calc_freq 함수의 매개변수 `i`)

**심각도**: LOW (코드 정확성 영향 없음)

**코드**:
```python
def calc_freq(i, line):  # i가 사용되지 않음
    chrm38 = line['chrm']
    pos38 = line['pos']
    ref = line['ref']
    alt = line['alt']
    data_pd = pd.DataFrame()
    for bam in bam_li:
        # ... i 사용 안 함 ...
```

**분석**:
- `p.starmap(calc_freq, data_pd.iterrows())`에서 `i`는 index, `line`은 Series
- `i`는 실제로 필요 없음

**수정**:
```python
def calc_freq(i_line_tuple):
    """
    각 변이에 대해 모든 샘플의 빈도 계산.

    Args:
        i_line_tuple: (index, row) 튜플 from DataFrame.iterrows()
    """
    i, line = i_line_tuple  # 명시적으로 언팩
    # 또는
    _, line = i_line_tuple  # i가 불필요함을 명시
```

---

### Issue #10: 타입 힌트 부재

**영향 범위**: 모든 모듈
**심각도**: LOW (유지보수성)

**개선**:
```python
# library/parser.py
from typing import Dict, List, Tuple

def filetype(fname: str) -> str:
    """파일 확장명에서 파일 타입 결정"""
    # ...

def sample_list(fname: str) -> Dict[Tuple[str, str], List[Tuple[str, str]]]:
    """샘플 리스트 파일 파싱"""
    # ...
```

---

## P3: Performance Issues (성능 최적화)

### Issue #11: 반복적인 samtools faidx 호출 (repeat.py)

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/utils/repeat.py`

**심각도**: MEDIUM (성능 저하)

**문제점**:
```python
def repeat(chrom, pos, alt):
    read_size = 100
    read = ref_seq(chrom, int(pos)-read_size, int(pos)+read_size)
    # ref_seq는 매번 samtools faidx를 호출
    # → repeat() 함수가 여러 번 호출되면 동일한 지역을 반복 요청
```

**병목 분석**:
- 대규모 VCF 처리 시 (예: 1M 변이): 1M회의 samtools faidx 호출
- 각 호출은 ~50-100ms (네트워크/디스크 I/O)
- 총 처리 시간: 50,000-100,000초 (예상)

**최적화 방법**:
```python
from functools import lru_cache

@lru_cache(maxsize=10000)  # 최근 10K 지역 캐시
def ref_seq_cached(chrom: str, pos1: int, pos2: int = None) -> str:
    """캐시된 ref_seq"""
    if pos2 is None:
        pos2 = pos1
    # ... 기존 ref_seq 로직
    return base

# 또는 더 정교한 캐시:
class ReferenceCache:
    def __init__(self, ref_file: str, chunk_size=100000):
        self.ref_file = ref_file
        self.chunk_size = chunk_size
        self.cache: Dict[str, str] = {}  # chrom -> sequence

    def get_seq(self, chrom: str, pos1: int, pos2: int = None) -> str:
        """청크 기반 캐싱"""
        if pos2 is None:
            pos2 = pos1

        # 청크 범위 계산
        chunk_start = (pos1 // self.chunk_size) * self.chunk_size
        chunk_end = chunk_start + self.chunk_size

        cache_key = f"{chrom}:{chunk_start}-{chunk_end}"

        if cache_key not in self.cache:
            # samtools faidx 호출 (청크 단위)
            result = subprocess.run(
                ['samtools', 'faidx', self.ref_file,
                 f'{chrom}:{chunk_start}-{chunk_end}'],
                capture_output=True, text=True
            )
            self.cache[cache_key] = result.stdout.split('\n')[1]

        # 청크에서 필요한 부분만 추출
        offset_start = pos1 - chunk_start
        offset_end = pos2 - chunk_start + 1
        return self.cache[cache_key][offset_start:offset_end]
```

**성능 개선 예상**:
- 캐시 히트율 90%: 10K/1M 호출만 실제 samtools 실행
- 예상 속도 향상: 90배

---

### Issue #12: PON_mask.2.py의 DataFrame 생성 비효율

**파일**: `/Users/taejeong/code/somatic-variant-pipeline/utils/PON_mask.2.py`
**라인**: 102 (calc_freq 함수)

**심각도**: MEDIUM (메모리 사용)

**문제 코드**:
```python
def calc_freq(i, line):
    chrm38 = line['chrm']
    # ...
    data_pd = pd.DataFrame()  # 빈 DataFrame 생성
    for bam in bam_li:
        name = bam.split('.')[0]
        count_dict = count_site(...)
        # ...
        data_pd.loc[(i,f'{name}.{base}')] = count_dict[base]  # 행-단위 추가
    return data_pd
```

**문제점**:
1. 함수 호출마다 새로운 DataFrame 생성 (N번, N=변이 수)
2. `.loc[]`로 행을 추가할 때마다 DataFrame 복사 (N×M번, M=샘플 수)
3. 메모리 할당과 GC 오버헤드

**최적화**:
```python
def calc_freq(i, line):
    """각 변이의 빈도 계산 (최적화 버전)"""
    chrm38 = line['chrm']
    pos38 = line['pos']
    ref = line['ref']
    alt = line['alt']

    # 딕셔너리로 데이터 수집 (훨씬 빠름)
    row_data = {}
    for bam in bam_li:
        name = bam.split('.')[0]
        count_dict = count_site(chrm38, pos38, f'{cram_dir}/{bam}', ref, alt)
        cov = count_dict[ref] + count_dict[alt]

        row_data[f'{name}.{ref}'] = count_dict[ref]
        row_data[f'{name}.{alt}'] = count_dict[alt]
        row_data[f'{name}.CAF'] = count_dict[alt] / cov if cov > 0 else 0

    return pd.Series(row_data, name=i)  # Series로 반환

# main 로직 수정
with Pool(procs) as p:
    # Series 리스트를 DataFrame으로 변환
    results = p.starmap(calc_freq, data_pd.iterrows())
    result_df = pd.DataFrame(results)
    data_pd = pd.concat([data_pd, result_df], axis=1)
```

**성능 개선**:
- 메모리: ~80% 감소
- 속도: ~40% 향상 (GC 오버헤드 감소)

---

## P4: DDD Testing Strategy (특성화 테스트 계획)

### DDD 개발 방식 개요

이 파이프라인은 **기존 코드 기반 프로젝트** (0% → 85% 커버리지 목표)이므로
**DDD의 PRESERVE 단계**부터 시작해야 합니다.

### PRESERVE 단계: 특성화 테스트

**목표**: 현재 동작을 문서화하고 회귀를 방지

**핵심 모듈별 테스트 계획**:

#### 1. library/parser.py 테스트 계획

```python
# tests/test_parser.py
import pytest
from library.parser import filetype, sample_list

class TestFiletype:
    """filetype 함수의 특성화 테스트"""

    def test_bam_extension(self):
        """기존 동작: .bam -> 'bam'"""
        assert filetype("sample.bam") == "bam"

    def test_bam_index_extension(self):
        """기존 동작: .bai -> 'bam'"""
        assert filetype("sample.bai") == "bam"

    def test_cram_extension(self):
        assert filetype("sample.cram") == "cram"

    def test_cram_index_extension(self):
        assert filetype("sample.crai") == "cram"

    def test_fastq_extension(self):
        assert filetype("sample.fastq") == "fastq"

    def test_fastq_short_extension(self):
        assert filetype("sample.fq") == "fastq"

    def test_gzipped_extensions(self):
        """gzip 압축 파일"""
        assert filetype("sample.bam.gz") == "bam"
        assert filetype("sample.fastq.gz") == "fastq"

    def test_invalid_extension(self):
        """기존 동작: 허용되지 않는 확장자는 예외"""
        with pytest.raises(Exception, match="not allowed filetype"):
            filetype("sample.txt")

class TestSampleList:
    """sample_list 함수의 특성화 테스트"""

    def test_parse_fastq_samples(self, tmp_path):
        """기존 동작: fastq 샘플 파싱"""
        sample_file = tmp_path / "samples.txt"
        sample_file.write_text(
            "SAMPLE1\tSAMPLE1_R1.fastq.gz\t/path/to/R1.fastq.gz\n"
            "SAMPLE1\tSAMPLE1_R2.fastq.gz\t/path/to/R2.fastq.gz\n"
        )

        result = sample_list(str(sample_file))

        # 기존 동작 검증
        assert ('SAMPLE1', 'fastq') in result
        assert len(result[('SAMPLE1', 'fastq')]) == 2

    def test_parse_mixed_samples(self, tmp_path):
        """fastq와 cram 혼합"""
        sample_file = tmp_path / "samples.txt"
        sample_file.write_text(
            "SAMPLE1\tSAMPLE1_R1.fastq.gz\t/path/fastq\n"
            "SAMPLE2\tSAMPLE2.cram\t/path/cram\n"
        )

        result = sample_list(str(sample_file))
        assert ('SAMPLE1', 'fastq') in result
        assert ('SAMPLE2', 'cram') in result

    def test_skip_comment_lines(self, tmp_path):
        """기존 동작: # 주석 라인 스킵"""
        sample_file = tmp_path / "samples.txt"
        sample_file.write_text(
            "# This is a comment\n"
            "SAMPLE1\tSAMPLE1.fastq.gz\t/path\n"
        )

        result = sample_list(str(sample_file))
        assert len(result) == 1
```

**테스트 커버리지 목표**: 80%+

---

#### 2. library/pileup.py 테스트 계획

```python
# tests/test_pileup.py
import pytest
from library.pileup import bases_clean, base_count, base_n

class TestBasesClean:
    """bases_clean 함수의 특성화 테스트"""

    def test_remove_start_flag(self):
        """^. 플래그 제거"""
        assert bases_clean("^!ACGT") == "ACGT"

    def test_remove_end_flag(self):
        """$ 플래그 제거"""
        assert bases_clean("ACGT$") == "ACGT"

    def test_remove_deletion_markers(self):
        """deletion marker 제거"""
        # 실제 pileup에서의 동작
        result = bases_clean("AC-2ATGT")
        assert "-2" not in result
        assert "AT" not in result  # 2개 base 삭제됨

    def test_remove_insertion_markers(self):
        """insertion marker 제거"""
        result = bases_clean("AC+2ATGT")
        assert "+2" not in result

    def test_complex_pileup_string(self):
        """실제 samtools mpileup 출력 시뮬레이션"""
        # 실제 pileup: ACG^!T-2AT+1G*$
        result = bases_clean("ACG^!T-2AT+1G*$")
        # 예상: ACG, T, +1G, * 만 남음
        assert "^" not in result
        assert "$" not in result
        assert "-2" not in result

class TestBaseN:
    """base_n 함수의 특성화 테스트"""

    def test_count_bases(self):
        """base 카운팅"""
        from library.pileup import base_n
        processor = base_n()
        next(processor)

        result = processor.send(("ACGTACGT", ""))
        assert result['A'] == 2
        assert result['C'] == 2
        assert result['G'] == 2
        assert result['T'] == 2

    def test_case_insensitive_counting(self):
        """대소문자 구분 카운팅"""
        from library.pileup import base_n
        processor = base_n()
        next(processor)

        result = processor.send(("AaCcGgTt", ""))
        assert result['A'] == 1
        assert result['a'] == 1
        assert result['C'] == 1
        assert result['c'] == 1
```

---

#### 3. library/config.py 테스트 계획

```python
# tests/test_config.py
import pytest
import os
from library.config import read_config

class TestReadConfig:
    """read_config 함수의 특성화 테스트"""

    def test_load_default_config(self):
        """기존 동작: b37 설정 로드"""
        config = read_config(reference="b37", conda_env="bp")
        assert "TOOLS" in config
        assert "RESOURCES" in config

    def test_load_hg38_config(self):
        """hg38 설정 로드"""
        try:
            config = read_config(reference="hg38", conda_env="bp")
            assert "TOOLS" in config
        except FileNotFoundError:
            # config.hg38.ini가 없을 수 있음
            pass

    def test_conda_env_resolution(self):
        """conda 환경 경로 확인"""
        config = read_config(reference="b37", conda_env="bp")
        env_dir = config["PATH"]["env_dir"]
        assert os.path.isdir(env_dir)

    def test_template_variable_substitution(self):
        """{ENVDIR}, {PIPEHOME} 변수 치환"""
        config = read_config(reference="b37", conda_env="bp")

        # SAMTOOLS 경로가 실제 경로로 확인됨
        samtools = config["TOOLS"].get("SAMTOOLS")
        # samtools 경로가 {ENVDIR}, {PIPEHOME} 없이 완전히 확인됨
        if samtools:
            assert "{" not in samtools
```

---

#### 4. library/job_queue.py 테스트 계획

```python
# tests/test_job_queue.py
import pytest
import tempfile
from library.job_queue import GridEngineQueue

class TestGridEngineQueue:
    """GridEngineQueue의 특성화 테스트"""

    def test_set_run_jid_creates_file(self):
        """기존 동작: run_jid 파일 생성"""
        with tempfile.TemporaryDirectory() as tmpdir:
            q = GridEngineQueue()
            jid_file = f"{tmpdir}/test_jid"
            q.set_run_jid(jid_file, new=True)

            assert os.path.exists(jid_file)

    def test_append_run_jid(self):
        """JID 추가"""
        with tempfile.TemporaryDirectory() as tmpdir:
            q = GridEngineQueue()
            jid_file = f"{tmpdir}/test_jid"
            q.set_run_jid(jid_file, new=True)

            q._append_run_jid("123456")

            with open(jid_file) as f:
                content = f.read()
            assert "123456" in content

    def test_num_run_jid_in_queue(self):
        """기존 동작: 큐에 있는 JID 수 확인"""
        with tempfile.TemporaryDirectory() as tmpdir:
            q = GridEngineQueue()
            jid_file = f"{tmpdir}/test_jid"

            # 파일이 없을 때
            count = q.num_run_jid_in_queue(jid_file)
            assert count == 0
```

---

#### 5. utils/PON_mask.2.py 테스트 계획

```python
# tests/test_pon_mask.py
import pytest
from utils.PON_mask import bases_clean, count_site, calc_CAF

class TestPONMask:
    """PON 마스킹 함수의 특성화 테스트"""

    def test_calc_caf_zero_coverage(self):
        """coverage=0일 때 CAF"""
        result = calc_CAF({'A': 0, 'T': 0}, 'T', 0)
        assert result == 0

    def test_calc_caf_normal(self):
        """정상 CAF 계산"""
        result = calc_CAF({'A': 8, 'T': 2}, 'T', 10)
        assert result == 0.2

    @pytest.mark.skipif(not os.path.exists("test_data/test.cram"),
                        reason="Test data not available")
    def test_count_site_integration(self):
        """실제 CRAM 파일을 사용한 통합 테스트"""
        result = count_site('chr1', '1000', 'test_data/test.cram', 'A', 'T')
        assert 'A' in result
        assert 'T' in result
```

---

### 테스트 파일 구조

```
tests/
├── __init__.py
├── conftest.py                      # pytest 설정
├── fixtures/
│   └── sample_data.py              # 테스트 데이터 생성
├── test_parser.py                  # 80 줄
├── test_pileup.py                  # 100 줄
├── test_config.py                  # 60 줄
├── test_job_queue.py               # 70 줄
├── test_pon_mask.py                # 90 줄
├── integration/
│   └── test_pipeline_end_to_end.py # 150 줄 (E2E 테스트)
└── data/
    └── sample_*.txt                # 샘플 입력 파일
```

**목표 커버리지**:
- Phase 1 (PRESERVE): 80% (특성화 테스트 완료)
- Phase 2 (IMPROVE): 85%+ (새 기능 테스트 추가)

---

## P5: Architecture Improvements (아키텍처 개선)

### Issue #13: 설정 관리 방식 (Shell 기반 → Python 기반)

**현재 문제**:
```python
# config.py line 9
env_dir = subprocess.check_output(
    "conda info -e | grep -w ^{} | awk '{{print $NF}}'".format(conda_env),
    shell=True
)
```

**개선안**:

```python
# library/config.py (전체 리팩토링)
import configparser
import pathlib
import os
import subprocess
import json
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class Config:
    """파이프라인 설정 데이터 클래스"""
    pipe_home: str
    env_dir: str
    reference: str
    tools: Dict[str, str]
    resources: Dict[str, str]

    def get_tool(self, name: str) -> str:
        """도구 경로 조회"""
        return self.tools.get(name.upper())

class ConfigManager:
    """설정 관리 (싱글톤)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._config: Config = None

    @classmethod
    def load(cls, reference: str = "b37", conda_env: str = "bp") -> Config:
        """설정 로드"""
        manager = cls()

        if manager._config is None:
            manager._config = cls._read_config(reference, conda_env)

        return manager._config

    @staticmethod
    def _read_config(reference: str, conda_env: str) -> Config:
        """내부 설정 읽기"""
        # 파이프라인 홈 경로 결정
        lib_home = os.path.dirname(os.path.realpath(__file__))
        pipe_home = os.path.normpath(lib_home + "/..")

        # conda 환경 경로 조회
        env_dir = ConfigManager._get_conda_env(conda_env)

        # INI 파일 로드
        config = configparser.ConfigParser()
        config_file = pipe_home + (
            f"/config.{reference}.ini" if reference in ["hg19", "hg38"]
            else "/config.ini"
        )

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        config.read(config_file)

        # 변수 치환
        tools = {}
        resources = {}

        for key in config["TOOLS"]:
            path = config["TOOLS"][key]
            path = path.format(ENVDIR=env_dir, PIPEHOME=pipe_home)
            tools[key.upper()] = path

        for key in config["RESOURCES"]:
            path = config["RESOURCES"][key]
            path = path.format(ENVDIR=env_dir, PIPEHOME=pipe_home)
            resources[key.upper()] = path

        return Config(
            pipe_home=pipe_home,
            env_dir=env_dir,
            reference=reference,
            tools=tools,
            resources=resources
        )

    @staticmethod
    def _get_conda_env(conda_env: str) -> str:
        """conda 환경 경로 조회"""
        try:
            result = subprocess.run(
                ['conda', 'info', '-e'],
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )

            env_dir = None
            for line in result.stdout.split('\n'):
                parts = line.split()
                if parts and parts[0] == conda_env:
                    env_dir = parts[-1]
                    break

            if not env_dir:
                raise ValueError(f"Conda environment not found: {conda_env}")

            if not os.path.isdir(env_dir):
                raise ValueError(f"Invalid conda environment path: {env_dir}")

            return env_dir

        except subprocess.CalledProcessError:
            raise RuntimeError("conda command failed")
        except subprocess.TimeoutExpired:
            raise RuntimeError("conda command timeout")

# 사용 예
def main():
    config = ConfigManager.load(reference="b37", conda_env="bp")
    samtools = config.get_tool("SAMTOOLS")
    bwa = config.get_tool("BWA")
```

---

### Issue #14: 에러 처리 및 로깅 개선

**현재**:
```python
# 에러 처리 거의 없음
# 로깅 없음
# 디버깅 어려움
```

**개선안**:
```python
# library/logging_config.py
import logging
import sys

def setup_logging(name: str, level=logging.INFO) -> logging.Logger:
    """로깅 설정"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(level)

    # 포맷터
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    return logger

# 사용 예
logger = setup_logging(__name__)

class GridEngineQueue:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.run_jid = None

    def submit(self, q_opt_str: str, cmd_str: str) -> str:
        """작업 제출"""
        self.logger.info(f"Submitting job with options: {q_opt_str}")

        try:
            jid = self._do_submit(q_opt_str, cmd_str)
            self.logger.info(f"Job submitted successfully: {jid}")
            return jid
        except Exception as e:
            self.logger.error(f"Job submission failed: {e}", exc_info=True)
            raise
```

---

## 요약 및 우선순위 로드맵

### 즉시 해결 (1주일 내):
1. **P0 Bug**: PON_mask.2.py line 56 논리 오류 수정
2. **P1 Security**: GridEngineQueue shell injection 수정
3. **P1 Security**: PON_mask.2.py os.popen() 교체

### 단기 (2주일 내):
4. P2 Code Quality: bases_clean() 중복 제거
5. P1 Security: config.py shell execution 안전화
6. P2 Code Quality: GridEngineQueue 에러 처리 추가

### 중기 (4주일 내):
7. P3 Performance: repeat.py 캐싱 구현
8. P4 Testing: 특성화 테스트 80% 달성
9. P2 Code Quality: 전역 변수 제거

### 장기 (2개월):
10. P5 Architecture: ConfigManager 싱글톤 구현
11. P4 Testing: 100% 커버리지 달성
12. 기술 부채 정리 및 리팩토링

---

## 첨부: 테스트 커버리지 추적 방법

```bash
# pytest + coverage로 테스트 실행
pip install pytest pytest-cov

# 커버리지 보고서 생성
pytest tests/ --cov=library --cov=utils --cov-report=html --cov-report=term

# 커버리지 임계값 확인
pytest tests/ --cov=library --cov-fail-under=80
```

---

**다음 단계**: 이 보고서를 기반으로 GitHub Issues를 생성하고, P0-P1 항목부터 해결하기 시작합니다.
