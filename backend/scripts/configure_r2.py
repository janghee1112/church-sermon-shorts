"""Apply the private R2 bucket CORS and incomplete multipart lifecycle safeguards."""

from __future__ import annotations

import os

import boto3
from botocore.config import Config


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} 환경변수가 필요합니다.")
    return value


def main() -> None:
    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    endpoint = os.environ.get("R2_ENDPOINT_URL", "").strip().rstrip("/")
    if not endpoint:
        endpoint = f"https://{required('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
    origins = [
        item.strip()
        for item in required("R2_CORS_ORIGINS").split(",")
        if item.strip()
    ]
    if not origins or "*" in origins:
        raise SystemExit("R2_CORS_ORIGINS에는 * 대신 허용할 사이트 주소를 정확히 입력하세요.")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("R2_REGION", "auto"),
        aws_access_key_id=required("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=required("R2_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
    )
    bucket = required("R2_BUCKET_NAME")
    client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={
            "CORSRules": [{
                "AllowedOrigins": origins,
                "AllowedMethods": ["GET", "HEAD", "PUT"],
                "AllowedHeaders": ["content-type"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }]
        },
    )
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [{
                "ID": "abort-incomplete-multipart-uploads",
                "Status": "Enabled",
                "Filter": {"Prefix": "projects/"},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
            }]
        },
    )
    print(f"Configured private R2 bucket: {bucket} ({len(origins)} allowed origins)")


if __name__ == "__main__":
    main()
