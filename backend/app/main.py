from contextlib import asynccontextmanager
import shutil
import tempfile

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select, text

from app.api.projects import router as projects_router
from app.api.drafts import router as drafts_router
from app.api.renders import router as renders_router
from app.api.title_layout import router as title_layout_router
from app.api.subtitle_layout import router as subtitle_layout_router
from app.api.uploads import router as uploads_router
from app.core.config import get_settings
from app.database.session import SessionLocal, init_db
from app.models import Project
from app.services.render_service import recover_stalled_render_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        stalled = db.scalars(select(Project).where(Project.status.in_(["extracting_audio", "transcribing", "analyzing"]))).all()
        for project in stalled:
            project.status = "failed"
            project.error_stage = "server_restart"
            project.error_message = "서버가 재시작되어 분석이 중단되었습니다. 다시 시도해 주세요."
        recover_stalled_render_jobs(db)
        db.commit()
    finally:
        db.close()
    yield


settings = get_settings()
app = FastAPI(title="설교 쇼츠 스튜디오 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects_router)
app.include_router(drafts_router)
app.include_router(renders_router)
app.include_router(title_layout_router)
app.include_router(subtitle_layout_router)
app.include_router(uploads_router)


@app.get("/live", include_in_schema=False)
def live() -> dict[str, str]:
    """Lightweight process liveness check for the hosting platform.

    Dependency checks belong to /health. The platform must not restart an
    otherwise healthy render worker just because FFmpeg temporarily delays the
    internal frontend or a disk probe on a small instance.
    """
    return {"status": "ok"}


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    database_ok = storage_ok = tools_ok = frontend_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=settings.data_dir):
            pass
        storage_ok = True
    except OSError:
        storage_ok = False
    tools_ok = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
    if not settings.frontend_proxy_url:
        frontend_ok = True
    else:
        try:
            frontend_ok = httpx.get(settings.frontend_proxy_url, timeout=2.0).status_code < 500
        except httpx.HTTPError:
            frontend_ok = False
    healthy = database_ok and storage_ok and tools_ok and frontend_ok
    if not healthy:
        response.status_code = 503
    return {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if database_ok else "error",
        "storage": "ok" if storage_ok else "error",
        "ffmpeg": "ok" if tools_ok else "error",
        "frontend": "ok" if frontend_ok else "error",
    }


async def _close_proxy(upstream: httpx.Response, client: httpx.AsyncClient) -> None:
    await upstream.aclose()
    await client.aclose()


if settings.frontend_proxy_url:
    @app.api_route("/{frontend_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def proxy_frontend(frontend_path: str, request: Request) -> StreamingResponse:
        target = f"{settings.frontend_proxy_url.rstrip('/')}/{frontend_path}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        headers = {
            key: value for key, value in request.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }
        client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=False)
        try:
            upstream = await client.send(client.build_request(request.method, target, headers=headers), stream=True)
        except httpx.HTTPError:
            await client.aclose()
            return StreamingResponse(iter([b"Frontend service unavailable"]), status_code=503, media_type="text/plain")
        response_headers = {
            key: value for key, value in upstream.headers.items()
            if key.lower() not in {"connection", "transfer-encoding", "content-length"}
        }
        return StreamingResponse(
            upstream.aiter_raw(), status_code=upstream.status_code,
            headers=response_headers, background=BackgroundTask(_close_proxy, upstream, client),
        )
