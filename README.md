# 말씀컷 — 설교 쇼츠 구간 추천 MVP

MP4 설교 영상을 업로드하면 음성을 추출하고 한국어 대본과 타임스탬프를 만든 뒤, 서로 겹치지 않는 쇼츠 후보 4개를 추천하는 로컬 웹 애플리케이션입니다. 후보를 누르면 원본 영상이 정확한 시작 지점부터 재생되고 구간 끝에서 자동으로 멈춥니다.

## 현재 MVP 범위

- MP4 업로드, 크기/MIME/확장자/영상/오디오/길이 검증
- FFmpeg 기반 16kHz mono WAV 추출 및 긴 오디오 분할
- OpenAI 전사 또는 API 키가 필요 없는 Mock 전사
- 세그먼트·단어 타임스탬프와 검색 가능한 전체 대본
- 설교 요약, 주제, 후보 4개, 실제 대본, 제목 3개, 선정 이유와 점수
- 프로젝트별 `mock`/`real` 분석 모드 저장과 Mock 결과 경고
- 후보 범위를 AI의 자유 시간값이 아닌 실제 DB `segment_id`로 확정
- 실제 모드에서 오디오 길이·전사 내용·DB 재조회 검증 후에만 후보 분석
- 문장 경계 보정, 30~75초 제한, 영상 범위/후보 겹침 검사
- HTTP Range 원본 영상 스트리밍
- SQLite 상태 저장과 새로고침 복원
- 분석 진행률, 안전한 오류 메시지와 재시도
- 프로젝트 삭제 API와 관련 파일/DB 정리
- 후보별 편집 초안 생성·재조회와 문장 경계 기반 구간 조정
- 실제 전사 원문 기반 자막 자동 분할, 편집·분할·병합·원문 복원
- `sermon_letterbox_v1` 검은 9:16 캔버스와 분리된 제목·실제 대본·가로형 영상 영역
- 영상 영역 내부 100~140% 확대와 가로/세로 초점, 영상 영역 위아래 위치 조정
- 안전 영역·제목/자막 겹침 경고, 750ms 자동 저장과 새로고침 복구
- 저장 시점 스냅샷 기반 1080×1920 H.264/AAC 쇼츠 렌더링
- 실제 렌더링 진행률, 최근 버전 목록, 완성 MP4 Range 재생과 다운로드

인증, 결제, 클라우드 저장소와 분산 작업 큐는 포함하지 않습니다. 인물 분리, 사람 마스크와 segmentation 모델은 사용하지 않습니다.

## 기술 스택

- Frontend: Next.js 16.3, React 19, TypeScript, Tailwind CSS
- Backend: Python 3.9+, FastAPI, SQLAlchemy 2, SQLite, Pillow
- Media: FFmpeg / ffprobe
- AI: OpenAI 공식 Python SDK
- Test: pytest, Vitest, Testing Library

## 폴더 구조

```text
frontend/              Next.js 화면, 컴포넌트, API 클라이언트, 테스트
backend/app/api/       FastAPI 라우터
backend/app/models/    SQLAlchemy 모델
backend/app/schemas/   API 및 AI JSON Pydantic 스키마
backend/app/services/  영상, 전사, 분석, 프로젝트 오케스트레이션
backend/assets/fonts/  OFL 한글 제목·자막 렌더링 글꼴
backend/tests/         API/서비스 테스트
uploads/               원본 영상(버전 관리 제외)
processed/             추출 음성/조각/완성 렌더(버전 관리 제외)
```

## 사전 준비

- Python 3.9 이상
- Node.js 20.9 이상(권장 22 이상)
- FFmpeg와 ffprobe

macOS:

```bash
brew install ffmpeg
```

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

설치 확인:

```bash
ffmpeg -version
ffprobe -version
```

## 환경 변수 설정

프로젝트 루트에서 다음을 실행합니다.

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

주요 값:

| 변수 | 설명 | 기본 예시 |
|---|---|---|
| `USE_MOCK_AI` | `true`이면 OpenAI 호출 없이 동작 | `true` |
| `APP_ENV` | `development`에서 전사 검수용 디버그 정보 표시 | `development` |
| `OPENAI_API_KEY` | 실제 AI 모드의 서버 전용 키 | 빈 값 |
| `OPENAI_TRANSCRIBE_MODEL` | 전사 모델명 | `whisper-1` |
| `OPENAI_ANALYSIS_MODEL` | JSON 분석 모델명 | `gpt-4.1-mini` |
| `MAX_UPLOAD_SIZE_MB` | 업로드 최대 크기 | `2048` |
| `MAX_VIDEO_DURATION_MINUTES` | 최대 영상 길이 | `90` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite:///./sermon_shorts.db` |
| `CORS_ORIGINS` | 쉼표로 구분한 프론트 주소 | `http://localhost:3000` |
| `RENDER_WIDTH`, `RENDER_HEIGHT` | 출력 해상도 | `1080`, `1920` |
| `RENDER_FPS` | 출력 프레임레이트 | `30` |
| `RENDER_CRF`, `RENDER_PRESET` | H.264 품질과 속도 | `20`, `medium` |
| `TITLE_FONT_PATH` | 제목용 Pretendard Black 파일 | `./backend/assets/fonts/Pretendard-Black.otf` |
| `SUBTITLE_FONT_PATH` | 자막용 한글 명조 파일 | `./backend/assets/fonts/NanumMyeongjo-Regular.ttf` |

비밀 키는 프론트엔드 환경 변수에 넣지 마세요. `.env`는 Git에서 제외되어 있습니다.

## 로컬 실행

터미널 1 — 백엔드:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

터미널 2 — 프론트엔드:

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다. API 문서는 `http://localhost:8000/docs`, 상태 확인은 `http://localhost:8000/health`입니다. 서버는 시작할 때 렌더링 글꼴과 FFmpeg를 확인하며 실제 생성 시 누락을 사용자용 오류로 반환합니다.

분석 완료 후 후보 카드에서 추천 제목 3개 중 하나를 선택하고 **이 후보 편집하기**를 누르면, 선택한 제목이 입력된 `/editor/{draftId}`로 이동합니다. 시작·종료 문장을 고르고 **변경한 구간 적용**을 누른 뒤 자막과 큰 제목을 편집할 수 있습니다. 오른쪽 설정은 제목, 영상 위치, 자막의 세 섹션으로 구성됩니다. 제목은 어절 버튼으로 서로 떨어진 여러 구간을 강조할 수 있고, 선택한 어절을 다시 누르면 글자 단위 범위를 지정할 수 있습니다. 영상 영역 내부 확대·가로·세로 초점과 영상 영역의 위아래 위치 및 `0.9x`~`1.3x` 재생 속도를 조절할 수 있습니다. 입력은 750ms 후 자동 저장되며 상단 **저장** 버튼으로 즉시 저장할 수도 있습니다.

미리보기 내부 해상도는 360×640입니다. `calculateLetterboxVideoArea()`가 검은 캔버스 안의 영상 영역 좌표를 계산하고, `calculateVerticalCrop()`은 그 영역의 화면비에 대한 cover 배율에 `zoom_scale`을 곱해 원본 좌표계 `cropX`, `cropY`, `cropWidth`, `cropHeight`를 계산합니다. 서버의 `calculate_render_crop()`도 같은 수식을 1080×1920 좌표에 적용합니다. 새 Draft의 기본 위치는 제목 `0.08`, 대본 `0.21`, 영상 영역 `0.30`이며 영상 영역 높이 `0.48`과 기본 확대 `1.12`는 유지합니다. 하단 배너는 너비 비율 `0.46`, 상단 위치 `0.83`을 사용합니다. 기존 Draft의 저장된 위치값은 변경하지 않습니다.

편집을 마친 뒤 **쇼츠 생성**을 누르면 저장되지 않은 변경을 먼저 저장하고, 불변 `settings_snapshot`을 가진 새 렌더 버전을 만듭니다. 진행 중에는 1.5초마다 상태를 조회합니다. 완료되면 실제 생성된 MP4 플레이어, 파일 정보, 다운로드와 최근 5개 버전이 표시됩니다. 다시 편집한 뒤 생성하면 이전 파일을 덮어쓰지 않고 다음 버전이 만들어집니다.

제목과 위치 범위 기반의 다중 노란색 강조는 번들된 Pretendard Black으로 투명 PNG를 만들고, 자막은 번들된 Nanum Myeongjo로 cue별 투명 PNG를 만듭니다. 제목·현재 cue·교회 배너를 시간순 투명 이미지 타임라인 하나로 합친 뒤 FFmpeg에서 원본 영상 위에 overlay하므로 1GB 배포 환경에서도 여러 전체 화면 레이어를 동시에 열지 않습니다. 제목은 `900` 굵기와 `-0.03em` 자간을 사용합니다. 제목 범위는 프론트엔드와 백엔드 모두 Unicode code point 기준의 `[start, end)`로 처리합니다. 이 방식은 로컬 FFmpeg가 libass 필터 없이 설치된 경우에도 같은 한글 글꼴을 보장합니다. Pretendard 라이선스는 `licenses/Pretendard-LICENSE.txt`, Nanum 라이선스는 `backend/assets/fonts/OFL.txt`에 포함되어 있습니다.

제목은 서버의 `calculate_title_layout()`이 1080×1920 기준으로 줄바꿈, 글자 크기, 줄간격과 위치를 한 번만 계산합니다. 편집 미리보기는 `POST /api/title-layout/preview`가 같은 Pretendard Black 파일로 만든 투명 PNG를 축소 표시하고, 최종 렌더는 렌더 시작 시 `settings_snapshot.title_layout`에 저장된 동일 레이아웃을 사용합니다. 3줄 제목은 그대로 유지하며 제목 영역을 실제로 넘는 경우에만 자동 축소합니다.

`playback_rate`의 기본값은 `1.0`이며 기존 Draft도 마이그레이션 후 `1.0`으로 동작합니다. 브라우저 미리보기는 원본 media time을 유지한 채 `HTMLVideoElement.playbackRate`만 바꾸므로 원본 cue 비교를 그대로 사용합니다. 최종 MP4는 영상 `setpts`, 오디오 `atempo`, 자막 상대 시간을 같은 배속으로 변환하며 예상 및 검증 길이는 `(end_sec - start_sec) / playback_rate`로 계산합니다.

## Mock 모드 확인

1. 루트 `.env`에서 `USE_MOCK_AI=true`로 둡니다.
2. 음성 트랙이 있고 길이가 2분 이상인 MP4를 업로드합니다.
3. 업로드 → 음성 추출 → Mock 대본 → 후보 분석 단계가 진행됩니다.
4. 결과 카드 4개, 제목/점수/대본을 확인하고 각 미리보기 버튼과 대본 타임스탬프를 누릅니다.

결과 상단에는 Mock 데이터임을 알리는 경고가 항상 표시됩니다. Mock 대본은 실제 영상 발언이 아닙니다.

Mock 모드도 업로드 영상 자체는 FFmpeg로 검증하고 실제 음성을 추출합니다. 4개의 비중첩 30초 후보를 보장하려면 영상은 수학적으로 최소 2분이어야 하며, 그보다 짧으면 이해 가능한 오류를 표시합니다.

## 실제 OpenAI API 모드

루트 `.env`를 다음처럼 설정하고 백엔드를 다시 시작합니다.

```dotenv
USE_MOCK_AI=false
OPENAI_API_KEY=your_server_side_key
OPENAI_TRANSCRIBE_MODEL=whisper-1
OPENAI_ANALYSIS_MODEL=gpt-4.1-mini
```

`whisper-1`의 verbose JSON 타임스탬프를 기본으로 사용합니다. 긴 오디오는 기본 20분 조각과 2초 오버랩으로 나누고, 조각 기준 시간을 원본 영상 기준으로 환산한 뒤 시간/문자열 유사도로 중복을 제거합니다. 분석 응답은 Pydantic JSON 스키마로 검증하며 잘못된 응답은 한 번 재시도합니다.

실제 모드에서는 추출 오디오의 존재·크기·원본 대비 길이, 전사 텍스트와 세그먼트 경계, DB 저장 후 원문 재조회가 모두 검증되어야 후보 분석으로 넘어갑니다. 분석 AI는 `start_segment_id`와 `end_segment_id`만 선택하며 후보 카드의 대본은 해당 DB 세그먼트의 `text`를 수정 없이 연결한 값입니다.

교회명, 목사명, 성경 인명 등 추가 어휘는 `TranscriptionService.transcribe(..., extra_vocabulary=[...])` 입력으로 확장할 수 있습니다.

## 테스트와 빌드

백엔드:

```bash
cd backend
source .venv/bin/activate
pytest -q
```

프론트엔드:

```bash
cd frontend
npm test
npm run build
```

## Docker 실행

먼저 `.env`를 만든 뒤 다음을 실행합니다.

```bash
docker compose up --build
```

로컬 개발은 위의 개별 실행 방식을 권장합니다. Docker에서는 SQLite 데이터가 `app-data` 이름의 볼륨에 유지됩니다.

## Railway 단일 Web Service 배포

현재 운영 주소는 [https://church-sermon-shorts-production.up.railway.app](https://church-sermon-shorts-production.up.railway.app)입니다. 루트 `Dockerfile`로 Next.js와 FastAPI를 한 컨테이너에서 실행하며, Railway가 주입한 `PORT`를 FastAPI가 사용하고 Next.js는 내부 `127.0.0.1:3000`에서 동작합니다.

운영 설정:

- GitHub 비공개 저장소의 `main` 브랜치와 연결하고 push 시 자동 배포
- Health Check Path: `/health`
- 공개 도메인 target port: Railway가 주입한 `PORT`(현재 `8080`)
- Persistent Volume mount path: `/var/data`
- `DATA_DIR=/var/data`
- `DATABASE_URL=sqlite:////var/data/sermon_shorts.db`
- `UPLOAD_DIR=/var/data/uploads`
- `PROCESSED_DIR=/var/data/processed`
- 같은 origin을 사용하므로 `CORS_ORIGINS`는 빈 값
- 실제 분석은 `USE_MOCK_AI=false`; OpenAI 키와 모델명은 Railway Variables에만 저장

이후 수정 배포는 로컬 프로젝트에서 다음 순서로 진행합니다.

```bash
git add <수정한 파일>
git commit -m "변경 내용"
git push origin main
```

push가 끝나면 Railway가 자동으로 새 이미지를 빌드하고 `/health` 검증을 통과한 뒤 교체합니다. SQLite, 업로드 원본, 추출 파일과 완성 MP4는 `/var/data` Volume에 남으므로 정상 재배포에서는 유지됩니다.

## Render 단일 Web Service 배포

루트 [Dockerfile](./Dockerfile)은 기존 Next.js와 FastAPI 구조를 유지한 채 하나의 Render Docker Web Service에서 두 프로세스를 실행합니다. FastAPI가 Render의 외부 `PORT`를 받고 `/api`, `/health`, 영상 스트리밍을 직접 처리하며, 나머지 화면 요청은 컨테이너 내부 `127.0.0.1:3000`의 Next.js로 전달합니다. 프로덕션 프론트엔드는 같은 origin의 상대 `/api` 경로를 사용합니다.

Render 설정:

- Runtime: `Docker`
- Dockerfile: `./Dockerfile`
- Health Check Path: `/health`
- Persistent Disk mount path: `/var/data`
- `DATA_DIR=/var/data`
- SQLite: `/var/data/sermon_shorts.db`
- 업로드: `/var/data/uploads`
- 추출 오디오와 렌더 결과: `/var/data/processed`

필수 환경변수는 `OPENAI_API_KEY`, `OPENAI_TRANSCRIBE_MODEL`, `OPENAI_ANALYSIS_MODEL`, `USE_MOCK_AI`, `APP_ENV`, `DATA_DIR`, `CORS_ORIGINS`입니다. `DATABASE_URL`, `UPLOAD_DIR`, `PROCESSED_DIR`를 생략하면 모두 `DATA_DIR` 아래의 안전한 기본 경로를 사용합니다. 제목·자막 폰트와 교회 배너는 Docker 이미지에 포함되므로 시스템 폰트나 `/Users/...` 경로가 필요하지 않습니다.

Render Persistent Disk는 유료 Web Service에서만 연결할 수 있습니다. Disk 없이 무료 인스턴스로 실행하면 재배포나 재시작 때 SQLite, 업로드 영상과 완성 MP4가 사라지므로 이 프로젝트의 운영 조건을 만족하지 않습니다. 비용 승인을 받은 뒤 가장 작은 적정 인스턴스와 영상 보관량을 감당할 Disk 크기를 선택하세요.

## API

- `POST /api/projects` — 업로드, 검증, 메타데이터 저장
- `POST /api/projects/{id}/analyze` — 중복 방지 백그라운드 분석 시작
- `GET /api/projects/{id}` — 상태/진행률/오류 조회
- `GET /api/projects/{id}/transcript` — 전체 대본과 세그먼트/단어 시간
- `GET /api/projects/{id}/candidates` — 요약과 최종 후보 4개
- `GET /api/projects/{id}/video` — HTTP Range MP4 스트리밍
- `DELETE /api/projects/{id}` — DB/원본/처리 파일 삭제
- `POST /api/projects/{id}/drafts` — 후보와 선택한 추천 제목 순번을 기반으로 편집 초안 생성 또는 기존 초안 반환
- `GET /api/drafts/{id}` — 초안·후보·선택 범위·자막 조회
- `POST /api/title-layout/preview` — 최종 렌더와 동일한 제목 레이아웃 및 투명 미리보기 레이어 생성
- `PATCH /api/drafts/{id}` — 제목/강조, 영상 영역과 확대·가로·세로 구도, 재생 속도, 텍스트 크기와 편집 상태 저장
- `PATCH /api/drafts/{id}/range` — 실제 전사 문장 경계로 구간 변경 및 자막 재생성
- `PUT /api/drafts/{id}/subtitles` — 편집 자막 전체 저장과 시간·순서 검증
- `PATCH /api/drafts/{id}/subtitles/{subtitleId}` — 개별 자막 편집
- `POST /api/drafts/{id}/subtitles/{subtitleId}/split` — 자막 분할
- `POST /api/drafts/{id}/subtitles/merge` — 인접 자막 병합
- `POST /api/drafts/{id}/subtitles/reset` — 현재 구간의 전사 원문으로 자막 전체 복원
- `POST /api/drafts/{id}/renders` — 저장 설정 snapshot과 새 버전을 만들고 백그라운드 렌더 시작
- `GET /api/renders/{id}` — 렌더 상태·진행률·오류·출력 정보 조회
- `GET /api/drafts/{id}/renders` — 최신 순 렌더 버전 목록
- `GET /api/renders/{id}/video` — 완성 MP4 HTTP Range 스트리밍
- `GET /api/renders/{id}/download` — 안전한 한글 파일명으로 완성 MP4 다운로드

## 편집 데이터베이스 변경

서버 시작 시 SQLAlchemy `Base.metadata.create_all()`과 멱등 SQLite 마이그레이션이 기존 테이블과 데이터를 유지합니다. 신규 `render_jobs` 테이블은 초안별 버전, 상태, 진행률, 출력 메타데이터와 JSON `settings_snapshot`을 저장합니다. 기존 제목·자막·crop 값과 과거 DB 컬럼은 삭제하지 않습니다. 레거시 인물 분리 컬럼은 마이그레이션 호환 때문에 DB에만 남지만 API·미리보기·렌더링에서는 읽거나 사용하지 않습니다. 같은 후보에는 하나의 초안만 생성되고 편집 자막 시간은 원본 영상 기준 절대 시간으로 저장됩니다.

`template_type=sermon_letterbox_v1`은 `frontend/lib/sermonTemplate.ts`의 검은 캔버스 영역 규칙과 `pretendard_black_v1`, `korean_myeongjo_v1` 글꼴 키를 가리킵니다. 현재 단계에는 영상 영역 높이와 글꼴 종류를 직접 바꾸는 UI가 없습니다.

## 현재 제한 사항

- FastAPI 프로세스 내부 백그라운드 작업을 사용하므로 다중 서버/분산 처리를 지원하지 않습니다.
- 서버가 분석 또는 렌더링 도중 재시작되면 해당 작업을 `failed`로 복구하고 사용자가 재시도해야 합니다.
- OpenAI 계정/모델별 파일 크기와 출력 형식 지원 차이에 따라 전사 모델 설정을 조정해야 할 수 있습니다.
- SQLite와 로컬 디스크는 단일 서버 MVP 용도입니다.
- 아주 짧은 영상, 문장 경계가 드문 대본, 후보 소재가 부족한 설교에서는 엄격한 4개/30초 기준을 만족하지 못할 수 있습니다.
- OpenAI 모델의 응답 형식이나 사용 한도 변경 시 실제 모드 분석이 실패할 수 있으므로 Railway 로그와 사용자 오류 메시지를 함께 확인해야 합니다.
- 브라우저 성능에 따라 Canvas 미리보기 프레임률이 원본보다 낮을 수 있습니다.
- 브라우저 CSS와 Pillow의 글자 폭 계산 차이 때문에 아주 긴 제목의 자동 줄바꿈은 수 픽셀 정도 다를 수 있습니다.
- 렌더 취소는 이번 MVP에 포함하지 않았습니다. 진행 중 중복 생성은 차단됩니다.
- 서버 프로세스 내부 작업이므로 배포 중 재시작 시 자동 이어받기는 지원하지 않습니다.

## 다음 개발 단계

1. Redis/Celery 또는 관리형 작업 큐, 렌더 취소와 작업 재개
2. PostgreSQL 및 S3 호환 오브젝트 스토리지
3. 전사 청크 경계의 의미 기반 중복 제거 강화
4. 사용자 어휘/교회 설정
5. 렌더 품질 프리셋과 썸네일 선택
6. 렌더 결과 보존 기간·자동 정리 정책
7. 로그인과 프로젝트별 권한
