# Quick Fix Priority Guide

프로덕션 실행 전 **반드시** 해결해야 할 P0-P1 항목들입니다.

---

## ⚠️ CRITICAL - 지금 당장 해결

### 1. PON_mask.2.py Line 56: Logic Bug

**현재**:
```python
if base_string == ['']:  # String can NEVER equal list!
    return count_dict
```

**수정** (1분):
```python
if not base_string or base_string == '':
    return count_dict
```

**테스트**:
```bash
# 빠른 검증
python3 -c "
base_string = ''
print('Test 1:', not base_string or base_string == '')  # True
print('Test 2:', base_string == [''])  # False (버그)
"
```

---

### 2. job_queue.py Line 40: Shell Injection

**현재**:
```python
qsub_cmd_list = ["sbatch"] + q_opt_str.split() + cmd_str.split()
```

**수정** (2분):
```python
import shlex

try:
    qsub_cmd_list = ["sbatch"] + shlex.split(q_opt_str) + shlex.split(cmd_str)
except ValueError as e:
    raise ValueError(f"Invalid command syntax: {e}")

result = subprocess.run(
    qsub_cmd_list,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    encoding='utf-8',
    timeout=30,
    check=False
)

if result.returncode != 0:
    raise RuntimeError(f"sbatch failed: {result.stderr}")

jid = result.stdout.rstrip()
if not jid or not jid.isdigit():
    raise RuntimeError(f"Invalid job ID: {jid}")
```

---

### 3. PON_mask.2.py Line 46: os.popen() → subprocess

**현재**:
```python
a = os.popen(f'samtools mpileup {bam} -r {chrm}:{pos}-{pos} -Q 20 -q 20')
a = a.read().rstrip().split('\t')
```

**수정** (3분):
```python
result = subprocess.run(
    ['samtools', 'mpileup', bam,
     '-r', f'{chrm}:{pos}-{pos}',
     '-Q', '20', '-q', '20'],
    capture_output=True,
    text=True,
    timeout=30,
    check=False
)

if result.returncode != 0:
    return {ref: 0, alt: 0}

a = result.stdout.rstrip().split('\t')
```

---

## 🔒 HIGH PRIORITY - 이번 주

### 4. config.py Line 9: Validate Conda Input

**현재**:
```python
env_dir = subprocess.check_output(
    "conda info -e | grep -w ^{} | awk '{{print $NF}}'".format(conda_env),
    shell=True
)
```

**수정** (2분):
```python
# 입력 검증
ALLOWED_ENVS = ["bp", "bp_frozen"]
if conda_env not in ALLOWED_ENVS:
    raise ValueError(f"Invalid conda environment: {conda_env}")

# Python으로 구현
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
```

---

### 5. Remove Duplicate bases_clean()

**파일**: `/utils/PON_mask.2.py` 에서 import 추가

**변경사항** (1분):
```python
# 추가
from library.pileup import bases_clean

# 제거
# def bases_clean(bases):
#     ... 모두 삭제
```

---

## 📊 Implementation Checklist

```bash
# 날짜: ____________________
# 담당자: ____________________

[ ] 1. PON_mask.2.py line 56 논리 버그 수정
    테스트: python3 tests/test_pon_mask.py::test_empty_bases

[ ] 2. job_queue.py line 40 Shell injection 수정
    테스트: python3 tests/test_job_queue.py::test_submit_security

[ ] 3. PON_mask.2.py line 46 subprocess 교체
    테스트: python3 tests/test_pon_mask.py::test_count_site

[ ] 4. config.py line 9 입력 검증 추가
    테스트: python3 tests/test_config.py::test_invalid_env

[ ] 5. bases_clean() 중복 제거
    테스트: python3 tests/test_pileup.py::test_bases_clean

[ ] 6. repeat.py line 12 입력 검증 추가
    테스트: 수동 검사

# 최종 검증
[ ] 전체 모듈 import 확인
[ ] pytest 전체 통과
[ ] 샘플 파이프라인 실행 테스트
```

---

## Testing Commands

```bash
# 설정
python3 -m pytest tests/ -v

# P0-P1 항목만 테스트
python3 -m pytest tests/test_pon_mask.py::test_empty_bases -v
python3 -m pytest tests/test_job_queue.py::test_submit_security -v
python3 -m pytest tests/test_config.py::test_invalid_env -v

# 전체 보안 테스트
python3 -m pytest tests/ -k "security or injection" -v

# 커버리지 확인
python3 -m pytest tests/ --cov=library --cov=utils --cov-report=term-missing
```

---

## Before Production

```bash
# 1. 모든 P0-P1 해결됨
grep -r "TODO\|FIXME\|BUG" library/ utils/

# 2. No shell=True 사용
grep -r "shell=True" library/ utils/

# 3. No os.popen() 사용
grep -r "os\.popen" library/ utils/

# 4. 테스트 커버리지 80%+
python3 -m pytest --cov=library --cov=utils --cov-fail-under=80

# 5. 샘플 실행 (드라이 런)
python3 jobs/submit_aln_jobs.py --queue test-queue --sample-name TEST_SAMPLE_DRY_RUN
```

---

## Questions?

각 수정 항목 앞에 상세 설명이 있는 전체 보고서를 참조하세요:
**`/Users/taejeong/code/somatic-variant-pipeline/.claude/IMPROVEMENT_REPORT.md`**
