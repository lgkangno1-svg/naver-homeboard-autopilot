# 네이버 블로그 홈판 자동 발행 프로그램

네이버 홈피드 노출을 목표로 한 **출처 조사 → 소재 선정 → 글 생성 → 교차 품질검수 → 이미지 수집 → 임시저장/발행 → 결과 검증 → 최근 발행 글 재평가** 파이프라인입니다.

> 기본값은 `publish: false`입니다. 임시저장 품질과 네이버 에디터 동작을 먼저 확인한 뒤 실제 발행으로 전환하세요.

## 핵심 구조

| 파일 | 역할 |
|---|---|
| `config.json` | 주제/발행시간/콘텐츠 모드/품질 기준/이미지 설정 |
| `.env` | 네이버 계정과 API 키. **커밋 금지** |
| `.env.example` | 안전한 환경변수 예시 |
| `llm.py` | OpenCode Go writer/reviewer 분리 + fallback 체인 |
| `research.py` | 네이버 검색 결과 수집 + 출처 등급화 + 공식출처 보강 |
| `quality_feedback.py` | 최근 생성/실제 발행 글의 약점을 다음 원고에 반영 |
| `writer_v2.py` | 근거 기반 소재선정 + 품질게이트 + 교차검토 + 재작성 |
| `images.py` | Pixabay/Wikimedia/Openverse/local 이미지 + 워터마크 |
| `naver.py` | 네이버 에디터 입력/임시저장/발행 |
| `publish_guard.py` | 중복 방지, 슬롯 집계, 발행 후 독립 검증 |
| `run.py` | once/daily/cron/audit 실행 관리자 |
| `install_minipc.sh` | Linux 미니PC 설치 + 발행 cron + 야간 품질 audit 등록 |
| `final_check.sh` | 프로세스/cron/config/피드백/문법/자원 최종 점검 |

## 글 품질 파이프라인

`writer_v2.py`는 한 번에 글을 생성하지 않습니다.

1. 최근 제목/소재/품질 로그를 읽어 반복 패턴을 확인
2. 이번 글의 콘텐츠 모드를 랜덤 선택
   - 비교·선택 기준
   - 실수 방지
   - 구매 전 체크
   - 변경사항 해설
   - 절약 체크리스트
   - 조건 확인 가이드
   - 가격 판단 기준
3. 네이버 검색 결과를 URL/도메인과 함께 수집
4. 출처를 등급화
   - T1: 정부/공공 공식출처
   - T2: 기관/일반 웹 원문
   - T3: 뉴스
   - T4: 커머스
   - T5: 블로그/카페 등 UGC
5. 정책·지원금·세금·자격 같은 고위험 주제는 `site:go.kr` 검색을 추가 수행
6. 소재 후보 5개 생성 후 새로움/독자 효용/근거 강도로 1개 선택
7. Kimi K3 계열 writer가 초안 작성
8. deterministic 품질검사
9. DeepSeek 계열 reviewer가 별도로 점수/근거 부족 주장 검토
10. 기준 미달이면 최대 설정 횟수만큼 전체 재작성

## deterministic 품질 게이트

LLM의 자기판단만 믿지 않고 코드에서 별도로 막습니다.

- 근거 없는 `3개월 써봤다`, `직접 신청했다`, `내돈내산` 등 허위 체험 차단
- AI 상투어 차단
- 본문 길이/섹션/소제목 검증
- 종결어미 반복 감지
- 최근 제목과의 토큰 유사도 검사
- 검색 근거에 없는 금액/%/연도/기간 등 숫자 주장 차단
- 정책·금전성 주제에서 공식출처 없이 구체 숫자 단정 차단
- 제목의 숫자 자체에는 가점을 주지 않음
- 제목 숫자는 검색 근거에 같은 수치가 있을 때만 허용/가점

## 쓸수록 개선되는 피드백 루프

매일 02:35 KST에 `run.py audit`가 최근 실제 발행 글을 다시 읽습니다.

최근 글을 아래 항목으로 평가합니다.

- hook
- usefulness
- specificity
- naturalness
- factual_discipline
- mobile_readability

결과는 `logs/live_feedback.json`에 저장되며 Git에는 커밋되지 않습니다. 다음 글을 만들 때 최근 약점과 반복 소재가 자동으로 생성 프롬프트에 들어갑니다.

예를 들어 최근 글의 `specificity`가 낮으면 다음 글에는 추상적인 조언을 줄이고 근거 안에서 조건/상황을 더 구체화하라는 지시가 자동 적용됩니다.

이 피드백은 조회수 조작용이 아니라 **글 자체의 신뢰성·가독성·재방문 품질** 개선에만 사용합니다.

## OpenCode Go 연결

OpenCode Go API 키는 코드나 `config.json`에 넣지 않습니다.

```bash
cp .env.example .env
```

`.env`:

```env
OPENCODE_GO_API_KEY=여기에_키
OPENCODE_GO_MODEL=deepseek-v4-flash
OPENCODE_GO_REVIEW_MODEL=deepseek-v4-flash
OPENCODE_GO_VISION_MODEL=deepseek-v4-flash
PIXABAY_KEY=여기에_키
NAVER_ID=...
NAVER_PW=...
```

- `OPENCODE_GO_MODEL`: 소재 선정/초안/재작성
- `OPENCODE_GO_REVIEW_MODEL`: 독립 편집 평가와 근거 부족 주장 탐지
- `OPENCODE_GO_VISION_MODEL`: 이미지 관련성 검증

writer와 reviewer를 다른 모델로 분리해 같은 모델이 자기 글을 자기 채점하는 편향을 줄입니다.

## 최초 설치

### Windows

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
copy .env.example .env
```

OCR/샘플 분석 도구까지 필요한 경우에만:

```powershell
.venv\Scripts\pip install -r requirements-analysis-windows.txt
```

### Linux 미니PC

저장소를 `~/blogbot`에 둔 뒤:

```bash
chmod +x install_minipc.sh final_check.sh
./install_minipc.sh
```

설치 스크립트는 KST 기준 다음 작업을 등록합니다.

- 5분마다 `run.py cron`
- 매일 02:35 `run.py audit`

## 실행

```powershell
# 최초 로그인 / 세션 저장
.venv\Scripts\python.exe run.py login

# 로그인 확인
.venv\Scripts\python.exe run.py check

# 1편 생성 + 임시저장
.venv\Scripts\python.exe run.py once --draft

# config.publish 값에 따라 1편 처리
.venv\Scripts\python.exe run.py once

# 오늘 남은 시간표대로 실행
.venv\Scripts\python.exe run.py daily

# cron용: 현재까지 마감된 슬롯 중 최대 1개 처리
.venv\Scripts\python.exe run.py cron

# 최근 실제 발행 글 재평가 + 다음 원고용 품질 피드백 생성
.venv\Scripts\python.exe run.py audit
```

## 발행 안전장치

- `posts_per_day`만큼만 `publish_times`를 사용합니다.
- draft와 publish 슬롯을 따로 셉니다.
- 원고 `content_id`를 기록해 이미 성공 발행한 동일 원고를 다시 올리지 않습니다.
- 최종 발행 후 URL 확인이 실패하면 블로그 목록에서 제목을 한 번 더 독립 검증합니다.
- 그래도 결과가 불확실하면 `uncertain`으로 기록하고 **자동 재발행하지 않습니다.**
- 품질 로그에는 출처 수/공식출처 수/콘텐츠 모드/편집 점수/제목 유사도를 남깁니다.

## 운영 전 권장 검증

1. `config.json`의 `publish`가 `false`인지 확인
2. OpenCode Go 키를 `.env`에 입력
3. `run.py once --draft`를 최소 3~5회 실행
4. 제목/본문/이미지/줄바꿈/소제목을 실제 네이버 임시저장에서 확인
5. `logs/published.jsonl`의 품질 점수와 출처 정보를 확인
6. 실제 발행 글이 이미 있다면 `run.py audit` 실행
7. `final_check.sh`로 cron/피드백/문법 확인
8. 1편만 수동으로 `publish: true` 테스트
9. 실제 블로그에서 제목이 확인되는지 점검
10. 문제 없을 때 자동발행 활성화

## 보안 및 이미지 정책

- `.env`, `storage_state.json`, 런타임 로그/피드백은 Git에 커밋하지 않습니다.
- Pixabay 키도 반드시 `.env`의 `PIXABAY_KEY`로 관리합니다.
- 기본 이미지 소스는 Pixabay/Wikimedia Commons/Openverse/local pool입니다.
- 네이버 쇼핑/타 블로그 이미지 무단 수집은 기본 설정에서 사용하지 않습니다.
