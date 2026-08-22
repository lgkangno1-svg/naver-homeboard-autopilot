# 네이버 블로그 홈판 자동 발행 프로그램

네이버 홈피드(홈판) 노출을 목표로 한 블로그 글 **자동 생성 → 이미지 수집·워터마크 → 사람처럼 타이핑해서 발행** 파이프라인.

## 구성

| 파일 | 역할 |
|---|---|
| `config.json` | 주제/발행시간/포맷/워터마크/이미지소스 설정 (여기만 고치면 됨) |
| `.env` | 네이버 계정, API 키 |
| `analysis.json` | 홈판 샘플 77장 실측 기반 포맷 규칙 |
| `llm.py` | LLM 엔진 체인: stealth/ox-alpha(무료) → Ollama exaone3.5(로컬 폴백) |
| `writer.py` | 제목+본문 생성 (샘플 분석 규칙 적용) |
| `images.py` | 이미지 수집(toss상품/위키공용/Openverse/쇼핑썸네일) + 워터마크 |
| `naver.py` | 사람처럼 입력하는 브라우저 자동화 (로그인/임시저장/발행) |
| `run.py` | 실행 관리자 |
| `분석보고서.md` | 샘플 정량 분석 결과 |

## 사용법

```powershell
# 최초 1회: 로그인 (보이는 창에서 직접 진행, 캡차 시 손으로 해결)
.venv\Scripts\python.exe run.py login

# 글 1편 발행 (테스트는 --draft로 임시저장)
.venv\Scripts\python.exe run.py once
.venv\Scripts\python.exe run.py once --draft

# 매일 자동 운영 (설정된 시각에 3~5편)
.venv\Scripts\python.exe run.py daily
```

## 주제 바꾸기
`config.json` → `topic.name`, `keywords`, `image_style` 수정.

## 워터마크 바꾸기
`config.json` → `watermark`:
- `mode`: `text`(글자) / `image`(이미지 파일 watermark.png) / `both` / `none`
- `text`: 문구, `position`: 5곳 중 선택, `opacity`, `font_size_ratio`
- 이미지 모드는 반투명 PNG를 `watermark.png`로 저장

## 주의
- AI 대량생산 저품질 리스크: 하루 3~5편 상한 유지, 가끔 임시저장으로 검수 후 발행 권장
- 이미지는 저작권 안전 소스(자유 라이선스/상품 썸네일)만 사용. 타 블로그 스크래핑 없음
- 계정 비밀번호는 테스트 후 변경할 것
