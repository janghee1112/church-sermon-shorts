import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.database.session import Base, get_db
from app.main import app


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    settings = get_settings()
    settings.upload_dir = tmp_path / "uploads"
    settings.processed_dir = tmp_path / "processed"
    settings.upload_dir.mkdir()
    settings.processed_dir.mkdir()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    yield session
    session.close()
    app.dependency_overrides.clear()


@pytest.fixture
def client(db_session):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    path = tmp_path / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=black:s=320x180:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path),
    ], check=True)
    return path


@pytest.fixture
def silent_video(tmp_path: Path) -> Path:
    path = tmp_path / "silent.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=black:s=320x180:d=2",
        "-c:v", "libx264", str(path),
    ], check=True)
    return path

