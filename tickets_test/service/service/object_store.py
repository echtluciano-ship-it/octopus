from __future__ import annotations

import boto3

from service.config import settings


def client():
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",
    )


def put_original(object_key: str, content: bytes, mime_type: str) -> None:
    client().put_object(
        Bucket=settings.minio_bucket,
        Key=object_key,
        Body=content,
        ContentType=mime_type,
        Metadata={"immutable": "true"},
    )


def get_original(object_key: str) -> bytes:
    response = client().get_object(Bucket=settings.minio_bucket, Key=object_key)
    return response["Body"].read()
