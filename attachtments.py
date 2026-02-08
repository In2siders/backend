from os import getenv
import base64
import uuid
import boto3
from io import BytesIO
import os
from botocore.config import Config


# Pon las keys para que funcione
s3 = boto3.client(
    "s3",
    endpoint_url=getenv("S3_ENDPOINT_URL", ""),
    aws_access_key_id=getenv("S3_ACCESS_KEY_ID", ""),
    aws_secret_access_key=getenv("S3_SECRET_KEY_ID", ""),
    config=Config(signature_version="s3v4"),
)
BUCKET_NAME = getenv("S3_BUCKET_NAME", "in2siders-attachments")


def upload_base64_to_s3(base64_str, filename, chat_id):
    if not base64_str:
        return None

    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]

        file_bytes = base64.b64decode(base64_str)
        file_obj = BytesIO(file_bytes)

        # Generate the unique KEY (Path)
        unique_name = f"{uuid.uuid4()}_{filename}"
        s3_path = f"chats/{chat_id}/{unique_name}"

        # Upload to S3
        s3.upload_fileobj(file_obj, BUCKET_NAME, s3_path, ExtraArgs={"ACL": "private"})

        return s3_path

    except Exception as e:
        print(f"[-] S3 Upload Error: {e}")
        return None


def get_signed_url(s3_key):
    if not s3_key:
        return None

    if "amazonaws.com/" in s3_key:
        s3_key = s3_key.split("amazonaws.com/")[-1].split("?")[0]

    try:
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": s3_key}, ExpiresIn=3600
        )
        return url
    except Exception as e:
        print(f"[-] Signing failed: {e}")
        return None

