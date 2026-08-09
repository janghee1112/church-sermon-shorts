from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import get_settings
from app.models import Project, RenderJob
from app.services.r2_storage_service import R2StorageService
from app.services.storage_service import CompletedPart, StorageObjectMetadata, validate_project_object_key
from app.services.video_service import VideoMetadata


class FakeStorage:
    backend_name = "r2"

    def __init__(self, size: int = 10):
        self.size = size
        self.completed = []
        self.aborted = []
        self.deleted_prefixes = []

    def create_multipart_upload(self, object_key, content_type):
        return "provider-upload-id"

    def generate_part_upload_url(self, object_key, upload_id, part_number, expires_in):
        return f"https://r2.example/{part_number}?expires={expires_in}"

    def complete_multipart_upload(self, object_key, upload_id, parts):
        self.completed.append((object_key, upload_id, list(parts)))

    def abort_multipart_upload(self, object_key, upload_id):
        self.aborted.append((object_key, upload_id))

    def get_object_metadata(self, object_key):
        return StorageObjectMetadata(self.size, "video/mp4", "etag")

    def generate_download_url(self, object_key, expires_in, download_name=None):
        return f"https://r2.example/{object_key}?signed=1"

    def upload_file(self, source, object_key, content_type):
        return StorageObjectMetadata(Path(source).stat().st_size, content_type, "etag")

    def delete_object(self, object_key):
        return None

    def delete_project_objects(self, project_id):
        self.deleted_prefixes.append(project_id)
        return 2


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def create_multipart_upload(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"UploadId": "upload-1"}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append((operation, Params, ExpiresIn))
        return f"https://signed.example/{operation}"

    def complete_multipart_upload(self, **kwargs):
        self.calls.append(("complete", kwargs))

    def head_object(self, **kwargs):
        return {"ContentLength": 123, "ContentType": "video/mp4", "ETag": '"abc"'}

    def list_objects_v2(self, **kwargs):
        return {"Contents": [{"Key": f"{kwargs['Prefix']}original/source.mp4"}], "IsTruncated": False}

    def delete_objects(self, **kwargs):
        self.calls.append(("delete_objects", kwargs))


def test_r2_client_uses_private_s3_operations_and_sorted_parts(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "r2")
    monkeypatch.setattr(settings, "r2_access_key_id", "key")
    monkeypatch.setattr(settings, "r2_secret_access_key", "secret")
    monkeypatch.setattr(settings, "r2_bucket_name", "sermon-shorts")
    monkeypatch.setattr(settings, "r2_endpoint_url", "https://account.r2.cloudflarestorage.com")
    client = FakeS3Client()
    service = R2StorageService(settings, client=client)
    assert service.create_multipart_upload("projects/p/original/source.mp4", "video/mp4") == "upload-1"
    assert service.generate_part_upload_url("projects/p/original/source.mp4", "upload-1", 2, 600).startswith("https://signed")
    service.complete_multipart_upload(
        "projects/p/original/source.mp4",
        "upload-1",
        [CompletedPart(2, "two"), CompletedPart(1, "one")],
    )
    complete = next(item for item in client.calls if item[0] == "complete")[1]
    assert complete["MultipartUpload"]["Parts"] == [
        {"PartNumber": 1, "ETag": "one"},
        {"PartNumber": 2, "ETag": "two"},
    ]
    assert service.get_object_metadata("projects/p/original/source.mp4").size == 123
    assert service.delete_project_objects("p") == 1


def test_project_object_key_validation_rejects_other_prefixes_and_traversal():
    assert validate_project_object_key("p1", "projects/p1/original/source.mp4")
    assert not validate_project_object_key("p1", "projects/p2/original/source.mp4")
    assert not validate_project_object_key("p1", "projects/p1/../p2/source.mp4")


def test_multipart_api_creates_project_verifies_head_and_stores_only_object_key(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "r2")
    monkeypatch.setattr(settings, "r2_multipart_part_size_mb", 5)
    fake = FakeStorage(size=10)
    monkeypatch.setattr("app.api.uploads.get_storage_service", lambda *_: fake)
    monkeypatch.setattr(
        "app.api.uploads.VideoService.probe",
        lambda self, source: VideoMetadata(120.0, 1920, 1080, True),
    )
    initiated = client.post("/api/uploads/multipart/init", json={
        "file_name": "sermon.mp4", "file_size": 10, "content_type": "video/mp4",
    })
    assert initiated.status_code == 201
    upload = initiated.json()
    assert upload["object_key"] == f"projects/{upload['project_id']}/original/source.mp4"
    assert upload["total_parts"] == 1
    completed = client.post("/api/uploads/multipart/complete", json={
        "session_id": upload["session_id"],
        "parts": [{"part_number": 1, "etag": '"etag-1"'}],
    })
    assert completed.status_code == 200
    assert completed.json()["status"] == "uploaded"
    project = db_session.get(Project, upload["project_id"])
    assert project is not None
    assert project.stored_file_path == ""
    assert project.original_object_key == upload["object_key"]
    assert project.duration_seconds == 120.0
    assert fake.completed[0][0] == upload["object_key"]


def test_multipart_completion_rejects_missing_parts(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "r2")
    monkeypatch.setattr(settings, "r2_multipart_part_size_mb", 5)
    fake = FakeStorage(size=6 * 1024 * 1024)
    monkeypatch.setattr("app.api.uploads.get_storage_service", lambda *_: fake)
    initiated = client.post("/api/uploads/multipart/init", json={
        "file_name": "sermon.mp4", "file_size": 6 * 1024 * 1024, "content_type": "video/mp4",
    }).json()
    response = client.post("/api/uploads/multipart/complete", json={
        "session_id": initiated["session_id"],
        "parts": [{"part_number": 1, "etag": "etag-1"}],
    })
    assert response.status_code == 422
    assert fake.completed == []


def test_r2_source_and_render_endpoints_redirect_without_proxying_files(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "r2")
    fake = FakeStorage()
    monkeypatch.setattr("app.api.projects.get_storage_service", lambda *_: fake)
    monkeypatch.setattr("app.api.renders.get_storage_service", lambda *_: fake)
    project_id = str(uuid4())
    project = Project(
        id=project_id, original_file_name="sermon.mp4", stored_file_path="",
        original_object_key=f"projects/{project_id}/original/source.mp4",
        duration_seconds=120, width=1920, height=1080, file_size=10,
        status="completed", progress=100, analysis_mode="real",
    )
    db_session.add(project)
    db_session.flush()
    job = RenderJob(
        project_id=project_id, draft_id=999, version=1, status="completed", progress=100,
        current_step="finalizing", output_object_key=f"projects/{project_id}/renders/v1/out.mp4",
        output_file_name="out.mp4", output_file_size=10, output_duration_sec=60,
        output_width=1080, output_height=1920, settings_snapshot="{}",
        completed_at=datetime.now(timezone.utc),
    )
    # The FK target is intentionally disabled only for this isolated redirect assertion.
    db_session.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")
    db_session.add(job)
    db_session.commit()
    source = client.get(f"/api/projects/{project_id}/video", follow_redirects=False)
    rendered = client.get(f"/api/renders/{job.id}/video", follow_redirects=False)
    download = client.get(f"/api/renders/{job.id}/download", follow_redirects=False)
    assert source.status_code == rendered.status_code == download.status_code == 307
    assert source.headers["location"].startswith("https://r2.example/projects/")
    assert rendered.headers["location"].startswith("https://r2.example/projects/")


def test_project_delete_removes_only_its_r2_prefix_before_database_row(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "r2")
    fake = FakeStorage()
    monkeypatch.setattr("app.services.project_cleanup_service.get_storage_service", lambda *_: fake)
    project_id = str(uuid4())
    project = Project(
        id=project_id, original_file_name="sermon.mp4", stored_file_path="",
        original_object_key=f"projects/{project_id}/original/source.mp4",
        duration_seconds=120, width=1920, height=1080, file_size=10,
        status="completed", progress=100, analysis_mode="real",
    )
    db_session.add(project)
    db_session.commit()
    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 204
    assert fake.deleted_prefixes == [project_id]
    assert db_session.get(Project, project_id) is None
