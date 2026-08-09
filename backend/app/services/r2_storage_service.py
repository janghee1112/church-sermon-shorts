from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

from app.core.config import Settings
from app.services.storage_service import CompletedPart, StorageError, StorageObjectMetadata


class R2StorageService:
    backend_name = "r2"

    def __init__(self, settings: Settings, client: Any | None = None):
        self.settings = settings
        self.bucket = settings.r2_bucket_name.strip()
        missing = [
            name
            for name, value in (
                ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
                ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
                ("R2_BUCKET_NAME", self.bucket),
                ("R2_ENDPOINT_URL 또는 R2_ACCOUNT_ID", settings.resolved_r2_endpoint_url),
            )
            if not str(value).strip()
        ]
        if missing:
            raise StorageError("R2 환경변수가 설정되지 않았습니다: " + ", ".join(missing))
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:
                raise StorageError("R2 연결 라이브러리를 찾을 수 없습니다.") from exc
            client = boto3.client(
                "s3",
                endpoint_url=settings.resolved_r2_endpoint_url,
                region_name=settings.r2_region,
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
            )
        self.client = client

    @staticmethod
    def _wrap(message: str, exc: Exception) -> StorageError:
        return StorageError(message)

    def create_multipart_upload(self, object_key: str, content_type: str) -> str:
        try:
            result = self.client.create_multipart_upload(
                Bucket=self.bucket,
                Key=object_key,
                ContentType=content_type,
            )
            return str(result["UploadId"])
        except Exception as exc:
            raise self._wrap("R2 업로드를 시작하지 못했습니다.", exc) from exc

    def generate_part_upload_url(
        self, object_key: str, upload_id: str, part_number: int, expires_in: int
    ) -> str:
        try:
            return str(self.client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": object_key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_in,
            ))
        except Exception as exc:
            raise self._wrap("R2 업로드 권한을 만들지 못했습니다.", exc) from exc

    def complete_multipart_upload(
        self, object_key: str, upload_id: str, parts: Sequence[CompletedPart]
    ) -> None:
        payload = [
            {"PartNumber": item.part_number, "ETag": item.etag}
            for item in sorted(parts, key=lambda item: item.part_number)
        ]
        try:
            self.client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": payload},
            )
        except Exception as exc:
            raise self._wrap("R2 업로드를 완료하지 못했습니다.", exc) from exc

    def abort_multipart_upload(self, object_key: str, upload_id: str) -> None:
        try:
            self.client.abort_multipart_upload(
                Bucket=self.bucket, Key=object_key, UploadId=upload_id
            )
        except Exception as exc:
            raise self._wrap("R2 업로드를 취소하지 못했습니다.", exc) from exc

    def get_object_metadata(self, object_key: str) -> StorageObjectMetadata:
        try:
            result = self.client.head_object(Bucket=self.bucket, Key=object_key)
            return StorageObjectMetadata(
                size=int(result.get("ContentLength", 0)),
                content_type=str(result.get("ContentType") or "application/octet-stream"),
                etag=str(result.get("ETag") or "").strip('"') or None,
            )
        except Exception as exc:
            raise self._wrap("R2에서 영상 파일을 확인하지 못했습니다.", exc) from exc

    def generate_download_url(
        self, object_key: str, expires_in: int, download_name: str | None = None
    ) -> str:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": object_key}
        if download_name:
            encoded = quote(Path(download_name).name, safe="")
            params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{encoded}"
        try:
            return str(self.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_in
            ))
        except Exception as exc:
            raise self._wrap("R2 영상 접근 주소를 만들지 못했습니다.", exc) from exc

    def upload_file(self, source: Path, object_key: str, content_type: str) -> StorageObjectMetadata:
        if not source.is_file() or source.stat().st_size <= 0:
            raise StorageError("업로드할 완성 영상 파일을 찾을 수 없습니다.")
        try:
            self.client.upload_file(
                str(source), self.bucket, object_key, ExtraArgs={"ContentType": content_type}
            )
        except Exception as exc:
            raise self._wrap("완성 영상을 R2에 저장하지 못했습니다.", exc) from exc
        return self.get_object_metadata(object_key)

    def delete_object(self, object_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise self._wrap("R2 영상 파일을 삭제하지 못했습니다.", exc) from exc

    def delete_project_objects(self, project_id: str) -> int:
        prefix = f"projects/{project_id}/"
        deleted = 0
        continuation: str | None = None
        try:
            while True:
                request: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
                if continuation:
                    request["ContinuationToken"] = continuation
                response = self.client.list_objects_v2(**request)
                objects = [
                    {"Key": item["Key"]}
                    for item in response.get("Contents", [])
                    if str(item.get("Key", "")).startswith(prefix)
                ]
                if objects:
                    self.client.delete_objects(
                        Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True}
                    )
                    deleted += len(objects)
                if not response.get("IsTruncated"):
                    break
                continuation = str(response.get("NextContinuationToken") or "")
                if not continuation:
                    break
        except Exception as exc:
            raise self._wrap("R2 프로젝트 파일을 정리하지 못했습니다.", exc) from exc
        return deleted
