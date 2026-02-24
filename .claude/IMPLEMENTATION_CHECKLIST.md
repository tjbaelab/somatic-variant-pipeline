# Implementation Checklist

**프로젝트**: Somatic Variant Calling Pipeline
**팀**: TJBaeLab
**분석 날짜**: 2026-02-21
**목표**: 0% → 85% 테스트 커버리지 (DDD PRESERVE → IMPROVE)

---

## Phase 0: 긴급 버그 수정 (PAY NOW OR PAY LATER)

### Week 1: P0/P1 Critical Fixes

#### 2026-02-21 (Day 1)

- [ ] **P0-1 정보**: PON_mask.2.py line 56 논리 오류
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P0: Critical Bugs → Bug #1
  - [ ] 수정: `if base_string == ['']:` → `if not base_string or base_string == '':`
  - [ ] 검증: `python3 -c "print('' == [''])"  # False 확인`
  - [ ] 테스트: `python3 tests/test_pon_mask.py::test_count_site_empty_bases`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P1-1 정보**: job_queue.py line 40 Shell Injection
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P1: Security Issues → Issue #1
  - [ ] 수정:
    ```python
    import shlex
    qsub_cmd_list = ["sbatch"] + shlex.split(q_opt_str) + shlex.split(cmd_str)
    ```
  - [ ] 에러 처리 추가: returncode 확인, jid 검증
  - [ ] 테스트: `python3 tests/test_job_queue.py::test_submit_security`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P1-2 정보**: PON_mask.2.py line 46 os.popen()
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P1: Security Issues → Issue #2
  - [ ] 수정: `os.popen()` → `subprocess.run()`
  - [ ] 에러 처리 추가: timeout, return code 확인
  - [ ] 테스트: `python3 tests/test_pon_mask.py::test_count_site_subprocess`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-02-22 (Day 2)

- [ ] **P1-3 정보**: config.py line 9 Shell Execution
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P1: Security Issues → Issue #3
  - [ ] 입력 검증 추가: `ALLOWED_ENVS = ["bp", "bp_frozen"]`
  - [ ] shell=True 제거: Python으로 구현
  - [ ] 테스트: `python3 tests/test_config.py::test_invalid_env`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P1-4 정보**: repeat.py / repeat.2.py line 12 Shell Injection
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P1: Security Issues → Issue #4
  - [ ] 염색체 검증: `VALID_CHROMS = {f'chr{i}' for i in range(1, 23)}`
  - [ ] 위치 검증: `isinstance(pos, int) and pos >= 0`
  - [ ] subprocess.run() 사용
  - [ ] 테스트: `python3 tests/test_repeat.py::test_ref_seq_invalid_chrom`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-02-23 (Day 3)

- [ ] **검증 및 통합 테스트**
  - [ ] 문법 검사: `python3 -m py_compile library/*.py utils/*.py`
  - [ ] Import 테스트: `python3 -c "from library.pileup import bases_clean"`
  - [ ] 기본 함수 동작: `python3 -c "from library.parser import filetype; print(filetype('test.bam'))"`
  - [ ] 샘플 파이프라인 드라이 런:
    ```bash
    python3 jobs/submit_aln_jobs.py --queue test-queue --sample-name DRY_RUN
    ```
  - **Reviewed By**: ___________  **Passed By**: ___________  **Date**: ___________

- [ ] **코드 리뷰**
  - [ ] Reviewer 1: _____________  Date: __________
  - [ ] Reviewer 2: _____________  Date: __________
  - [ ] Approved: _____________  Date: __________

- [ ] **Git 커밋 (원자적 커밋)**
  ```bash
  git add library/job_queue.py
  git commit -m "fix(job_queue): add shlex.split() for shell injection protection"

  git add library/config.py
  git commit -m "fix(config): validate conda_env input and refactor to Python subprocess"

  git add utils/PON_mask.2.py
  git commit -m "fix(pon_mask): fix logic bug line 56 and replace os.popen()"

  git add utils/repeat.py utils/repeat.2.py
  git commit -m "fix(repeat): add input validation for chromosome and position"
  ```

---

## Phase 1: P2 코드 품질 (Quality Focus)

### Week 2: Code Quality Fixes

#### 2026-02-24 (Monday)

- [ ] **P2-1**: bases_clean() 중복 제거
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P2: Code Quality → Issue #5
  - [ ] library/pileup.py 확인: bases_clean() 함수 위치
  - [ ] 수정:
    - [ ] utils/PON_mask.2.py에서 `def bases_clean():` 제거
    - [ ] utils/PON_mask.2.py 상단에 추가: `from library.pileup import bases_clean`
  - [ ] 테스트: `python3 tests/test_pileup.py::TestBasesClean`
  - [ ] 동작 검증: PON_mask.2.py의 bases_clean() 호출이 정상 동작
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P2-8**: GridEngineQueue.submit() 에러 처리
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P2: Code Quality → Issue #8
  - [ ] 개선사항:
    - [ ] returncode 확인
    - [ ] jid 유효성 검증 (숫자인지 확인)
    - [ ] stderr 로깅
    - [ ] 타임아웃 처리
  - [ ] 테스트: `python3 tests/test_job_queue.py::TestGridEngineQueue`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-02-25 (Tuesday)

- [ ] **P2-7**: 주석 처리 코드 정리
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P2: Code Quality → Issue #7
  - [ ] 결정:
    - [ ] git 히스토리 확인: `git log -p -- jobs/submit_aln_jobs.just_mapping.py`
    - [ ] 불필요한 코드: 삭제
    - [ ] 향후 기능: 이슈로 등록하고 삭제
    - [ ] 임시 코드: 주석 추가하고 유지
  - [ ] 수정: 해당 항목 적용
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P2-9**: 미사용 매개변수 정리
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P2: Code Quality → Issue #9
  - [ ] utils/PON_mask.2.py calc_freq(): 매개변수 `i` 언팩 명시
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-02-26 (Wednesday)

- [ ] **P2-10**: 타입 힌트 추가 (선택사항)
  - [ ] library/parser.py: filetype(), sample_list() 타입 힌트
  - [ ] library/pileup.py: 주요 함수에 타입 힌트
  - [ ] 테스트: `mypy library/parser.py`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **검증 및 커밋**
  - [ ] 전체 문법 검사: `python3 -m py_compile library/*.py utils/*.py`
  - [ ] 테스트 통과: `pytest tests/ -v`
  - [ ] Git 커밋:
    ```bash
    git add utils/PON_mask.2.py
    git commit -m "refactor(pon_mask): remove duplicate bases_clean(), import from pileup"

    git add library/job_queue.py
    git commit -m "refactor(job_queue): improve error handling in submit()"

    git add jobs/submit_aln_jobs.*.py
    git commit -m "chore(submit_aln_jobs): clean up commented code"
    ```

---

## Phase 2: P4 Testing (DDD PRESERVE)

### Week 3-4: Characterization Tests (80% Coverage)

#### 2026-03-03 (Monday - Week 3 Start)

- [ ] **테스트 환경 설정**
  - [ ] pytest 설치: `pip install pytest pytest-cov`
  - [ ] 테스트 디렉토리 구성:
    ```
    mkdir -p tests/
    mkdir -p tests/fixtures/
    touch tests/__init__.py
    touch tests/conftest.py
    ```
  - [ ] conftest.py 작성: 공통 fixture 정의
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **library/parser.py 테스트** (2시간)
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P4: DDD Testing Strategy → library/parser.py
  - [ ] 파일 생성: tests/test_parser.py
  - [ ] 특성화 테스트 구현:
    - [ ] TestFiletype: 6개 테스트
    - [ ] TestSampleList: 5개 테스트
  - [ ] 커버리지 확인: `pytest tests/test_parser.py --cov=library.parser`
  - [ ] 목표: 80%+ (권장: 90%+)
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-03-04 (Tuesday)

- [ ] **library/pileup.py 테스트** (3시간)
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P4 → library/pileup.py
  - [ ] 파일 생성: tests/test_pileup.py
  - [ ] 특성화 테스트 구현:
    - [ ] TestBasesClean: 5개 테스트
    - [ ] TestBaseN: 3개 테스트
  - [ ] 생성자 테스트: @coroutine 함수들
  - [ ] 커버리지: 80%+
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-03-05 (Wednesday)

- [ ] **library/config.py 테스트** (2시간)
  - [ ] 파일 생성: tests/test_config.py
  - [ ] 특성화 테스트:
    - [ ] TestReadConfig: 5개 테스트
    - [ ] 다양한 reference (b37, hg38) 테스트
    - [ ] conda 환경 경로 검증
  - [ ] Mock 사용: conda 명령 mock
  - [ ] 커버리지: 75%+
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-03-06 (Thursday)

- [ ] **library/job_queue.py 테스트** (2시간)
  - [ ] 파일 생성: tests/test_job_queue.py
  - [ ] 특성화 테스트:
    - [ ] TestGridEngineQueue: 8개 테스트
    - [ ] sbatch mock 사용
    - [ ] 에러 시나리오
  - [ ] Mock sbatch 구현
  - [ ] 커버리지: 80%+
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-03-07 (Friday)

- [ ] **utils/PON_mask.2.py 테스트** (3시간)
  - [ ] 파일 생성: tests/test_pon_mask.py
  - [ ] 특성화 테스트:
    - [ ] TestBasesClean (pileup 테스트와 동기화)
    - [ ] TestCountSite: samtools mock 사용
    - [ ] TestCalcCAF: 5개 테스트
  - [ ] samtools mock: 다양한 pileup 출력
  - [ ] 커버리지: 75%+
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-03-10 (Monday - Week 4)

- [ ] **통합 테스트**
  - [ ] 전체 테스트 실행: `pytest tests/ -v`
  - [ ] 커버리지 리포트: `pytest tests/ --cov=library --cov=utils --cov-report=html`
  - [ ] 목표 확인: 80% 달성 여부
  - [ ] 누락 영역 식별:
    ```bash
    pytest tests/ --cov=library --cov=utils --cov-report=term-missing
    ```
  - **Reviewed By**: ___________  **Passed By**: ___________  **Date**: ___________

- [ ] **테스트 코드 리뷰**
  - [ ] Reviewer 1: ______________  Date: __________
  - [ ] Reviewer 2: ______________  Date: __________
  - [ ] 의견 반영 및 수정
  - **Approved By**: ______________  Date: __________

- [ ] **Git 커밋**
  ```bash
  git add tests/
  git commit -m "test(all): add characterization tests for DDD PRESERVE phase (80% coverage)"
  ```

---

## Phase 3: P3 Performance + P2 Refactoring

### Week 5: Optimization & Architecture

#### 2026-03-12 (Wednesday - P3 Performance)

- [ ] **P3-1**: samtools faidx 캐싱
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P3: Performance Issues → Issue #11
  - [ ] 구현:
    - [ ] lru_cache 또는 ReferenceCache 클래스
    - [ ] repeat.py, repeat.2.py 수정
  - [ ] 성능 테스트:
    ```bash
    # 1000개 변이로 성능 측정
    time python3 utils/repeat.2.py -r ref.fa < variants.txt
    ```
  - [ ] 목표: 90% 시간 단축
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P3-2**: DataFrame 메모리 최적화
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P3: Performance Issues → Issue #12
  - [ ] PON_mask.2.py 수정: Series 기반으로 변경
  - [ ] 메모리 프로파일링:
    ```bash
    pip install memory-profiler
    python3 -m memory_profiler utils/PON_mask.2.py input.txt output.txt cram_dir 4
    ```
  - [ ] 목표: 메모리 80% 감소
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

#### 2026-03-13 (Thursday - P2 Refactoring)

- [ ] **P2-6**: 전역 변수 제거
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P2: Code Quality → Issue #6
  - [ ] library/pileup.py: PileupProcessor 클래스로 리팩토링
  - [ ] utils/repeat.py: ref_file 제거, 매개변수화
  - [ ] 테스트 업데이트: 새 클래스 구조 적응
  - [ ] 테스트 통과 확인: `pytest tests/test_pileup.py -v`
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

- [ ] **P5-1**: ConfigManager 싱글톤 구현
  - [ ] 코드 리뷰: IMPROVEMENT_REPORT.md → P5: Architecture Improvements → Issue #13
  - [ ] 구현: ConfigManager 클래스
  - [ ] 테스트: `pytest tests/test_config.py -v`
  - [ ] 기존 코드 마이그레이션
  - **Reviewed By**: ___________  **Completed By**: ___________  **Date**: ___________

---

## Phase 4: Final Validation

### Week 6: Integration & Deployment Prep

#### 2026-03-17 (Monday)

- [ ] **통합 테스트**
  - [ ] 전체 파이프라인 테스트: 샘플 데이터로 end-to-end
  - [ ] 회귀 테스트: 이전 단계 모두 통과 확인
  - [ ] 성능 벤치마크:
    - [ ] 처리 속도
    - [ ] 메모리 사용량
    - [ ] 에러율
  - **Verified By**: ______________  **Date**: __________

#### 2026-03-18 (Tuesday)

- [ ] **보안 감시**
  - [ ] grep -r "shell=True" library/ utils/ (0개여야 함)
  - [ ] grep -r "os.popen" library/ utils/ (0개여야 함)
  - [ ] grep -r ".split()" | grep subprocess (shlex 사용 확인)
  - [ ] grep -r "subprocess.run" | 타임아웃 확인
  - **Verified By**: ______________  **Date**: __________

#### 2026-03-19 (Wednesday)

- [ ] **최종 커버리지 검증**
  - [ ] 커버리지 리포트: `pytest --cov=library --cov=utils --cov-report=html`
  - [ ] 목표: 85%+ 달성
  - [ ] 누락 영역: 정당성 확인 및 문서화
  - **Verified By**: ______________  **Date**: __________

- [ ] **코드 리뷰 (최종)**
  - [ ] 아키텍트 리뷰: P5 구조 검증
  - [ ] 보안 리뷰: P1 완화 확인
  - [ ] 성능 리뷰: P3 개선 확인
  - **Approved By**: ______________  **Date**: __________

#### 2026-03-20 (Thursday)

- [ ] **문서화**
  - [ ] API 문서: docstring 모두 작성
  - [ ] README: 설치 및 사용법 업데이트
  - [ ] CHANGELOG: 변경사항 기록
  - [ ] 개발자 가이드: 권장 패턴 문서화
  - **Written By**: ______________  **Date**: __________

#### 2026-03-21 (Friday)

- [ ] **배포 준비**
  - [ ] 최종 테스트: 모든 테스트 통과
  - [ ] 배포 체크리스트:
    - [ ] 보안: P1 이슈 모두 해결
    - [ ] 품질: P2 이슈 모두 해결
    - [ ] 성능: P3 이슈 모두 해결
    - [ ] 테스트: 85%+ 커버리지
    - [ ] 아키텍처: P5 개선 적용
  - [ ] 배포 승인
  - **Approved By**: ______________  **Date**: __________

---

## Risk Management

### Critical Blockers

```
[ ] P0-1 미해결 → MUST FIX FIRST
    상태: _____________  %완료
    예상 완료일: _____________

[ ] P1-1,2,3,4 미해결 → 프로덕션 불가
    상태: _____________  %완료
    예상 완료일: _____________

[ ] 커버리지 < 80% → IMPROVE 단계 불가
    현재: _____________%
    예상 완료일: _____________
```

### Timeline Risk

```
Week 1 지연:
  [ ] 원인: _________________________________
  [ ] 영향: Phase 2 일정 연기 (Days)
  [ ] 완화: ________________________________

Week 3-4 지연:
  [ ] 테스트 구현 어려움
  [ ] Mock 작성 시간 부족
  [ ] 원인 분석 및 계획 수립
```

---

## Sign-Off

### 각 페이즈별 승인

**Phase 0 (P0/P1):**
- [ ] 기술 리더: _______________  Date: __________
- [ ] QA: _______________  Date: __________
- [ ] 팀 리더: _______________  Date: __________

**Phase 1 (P2):**
- [ ] 코드 리뷰어 1: _______________  Date: __________
- [ ] 코드 리뷰어 2: _______________  Date: __________

**Phase 2 (P4):**
- [ ] QA 엔지니어: _______________  Date: __________
- [ ] 커버리지 검증: _______________  Date: __________

**Phase 3 (P3/P5):**
- [ ] 성능 검증: _______________  Date: __________
- [ ] 아키텍트: _______________  Date: __________

**Phase 4 (최종):**
- [ ] 프로젝트 매니저: _______________  Date: __________
- [ ] 기술 이사: _______________  Date: __________

---

## Metrics Dashboard

### 진행상황 추적

| 주차 | 완료 | 총 | % | 예정 |
|-----|------|-----|-------|------|
| Week 1 | ___ | 5 | ___% | P0/P1 100% |
| Week 2 | ___ | 4 | ___% | P2 100% |
| Week 3 | ___ | 5 | ___% | 특성화 테스트 50% |
| Week 4 | ___ | 5 | ___% | 특성화 테스트 100% |
| Week 5 | ___ | 3 | ___% | P3 + P5 |
| Week 6 | ___ | 5 | ___% | 최종 검증 + 배포 |

### 품질 지표

| 지표 | 현재 | 목표 | Week 6 |
|-----|------|------|---------|
| 테스트 커버리지 | 0% | 85% | ____% |
| 보안 이슈 | 4 | 0 | ____ |
| 코드 품질 점수 | 3.2/10 | 8.0/10 | ____/10 |
| 성능 개선 | 1x | 50x | ____x |

---

**최초 작성**: 2026-02-21
**최종 업데이트**: 2026-02-21
**담당자**: _________________
**검토자**: _________________
