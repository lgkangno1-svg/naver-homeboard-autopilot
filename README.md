# 네이버 블로그 홈판 자동 발행 프로그램

네이버 홈피드 노출을 목표로 한 **소재 조사 → 글 생성 → 품질검수 → 이미지 수집/워터마크 → 임시저장/발행 → 결과 검증** 파이프라인입니다.

> 업그레이드 버전은 기본값이 `publish: false`입니다. 먼저 임시저장으로 품질과 에디터 동작을 확인한 뒤 `true`로 전환하세요.

## 핵심 구조

| 파일 | 역할 |
|---|---|
| `config.json` | 주제/발행시간/품질 기준/이미지 설정 |
| `.env` | 네이버 계정과 API 키. **커밋 금지** |
| `.env.example` | 안전한 환경변수 예시 |
| `llm.py` | OpenCode Go → custom endpoint → OpenRouter → Ollama 폴백 |
| `research.py` | 네이버 검색 화면에서 참고 스니펫 수집 |
| `writer_v2.py` | 근거 기반 소재선정 + 작성 + 품질게이트 + 재작성 |
| `images.py` | Pixabay/Wikimedia/Openverse/local 이미지 + 워터마크 |
| `naver.py` | 네이버 에디터 입력/임시저장/발행 |
| `publish_guard.py` | 중복 방지, 슬롯 집계, 발행 후 독립 검증 |
| `run.py` | once/daily/cron 실행 관리자 |
| `install_minipc.sh` | Linux 미니PC 설치 + cron 등록 |
| `final_check.sh` | 프로세스/cron/config/문법/자원 최종 점검 |

## 글 품질 업그레이드

`writer_v2.py`는 한 번에 글을 생성하지 않습니다.

1. 최근 발행 제목을 읽어 중복 소재를 피함
2. 시드 키워드의 네이버 검색 스니펫 수집
3. 소재 후보 5개 생성 후 독자 효용/새로움 기준으로 1개 선택
4. 초안 생성
5. 규칙 기반 검사
   - 근거 없는 `3개월 써봤다`, `직접 신청했다`, `내돈내산` 등 금지
   - AI 상투어 감지
   - 문장 종결 반복 감지
   - 최소 본문 길이/섹션 수 검사
6. 별도 편집자 평가
   - hook
   - usefulness
   - specificity
   - naturalness
   - factual_discipline
   - mobile_readability
7. 평균 점수가 `quality.min_editor_score` 미만이면 최대 `quality.max_rewrites`회 재작성

가격·정책·지원금·할인율·날짜처럼 검증이 필요한 숫자는 검색 스니펫에 근거가 없으면 새로 만들지 않도록 지시합니다.

## OpenCode Go 연결

OpenCode Go API 키는 코드나 `config.json`에 넣지 않습니다.

```bash
cp .env.example .env
```

`.env`:

```env
OPENCODE_GO_API_KEY=여기에_키
OPENCODE_GO_MODEL=kimi-k3
OPENCODE_GO_VISION_MODEL=deepseek-v4-flash-vision-exp
PIXABAY_KEY=여기에_키
NAVER_ID=...
NAVER_PW=...
```

텍스트 생성은 `OPENCODE_GO_MODEL`, 이미지 관련성 검사는 `OPENCODE_GO_VISION_MODEL`을 사용합니다.

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
```

## 발행 안전장치

- `posts_per_day`만큼만 `publish_times`를 사용합니다.
- draft와 publish 슬롯을 따로 셉니다.
- 원고 `content_id`를 기록해 이미 성공 발행한 동일 원고를 다시 올리지 않습니다.
- 최종 발행 후 URL 확인이 실패하면 블로그 목록에서 제목을 한 번 더 독립 검증합니다.
- 그래도 결과가 불확실하면 `uncertain`으로 기록하고 **자동 재발행하지 않습니다.** 중복 게시보다 누락 1건이 안전하다는 정책입니다.

## 운영 전 권장 검증

1. `config.json`의 `publish`가 `false`인지 확인
2. `run.py once --draft`를 최소 3~5회 실행
3. 제목/본문/이미지/줄바꿈/굵게/정렬을 실제 네이버 임시저장에서 확인
4. `logs/published.jsonl`의 품질 점수와 상태 확인
5. 1편만 수동으로 `publish: true` 테스트
6. 실제 블로그에서 제목이 확인되는지 점검
7. 문제 없을 때 cron 자동발행 활성화

## 보안 및 이미지 정책

- `.env`, `storage_state.json`, 런타임 로그는 Git에 커밋하지 않습니다.
- Pixabay 키도 반드시 `.env`의 `PIXABAY_KEY`로 관리합니다.
- 기본 이미지 소스는 Pixabay/Wikimedia Commons/Openverse/local pool입니다.
- 네이버 쇼핑/타 블로그 이미지 무단 수집은 기본 설정에서 사용하지 않습니다.
