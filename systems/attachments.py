from os import getenv, urandom
import base64
import uuid
import boto3
from io import BytesIO
from botocore.config import Config

# DB
from systems.db import db
from systems.orm import Attachment


# Pon las keys para que funcione
s3 = boto3.client(
    "s3",
    endpoint_url=getenv("S3_ENDPOINT_URL", ""),
    aws_access_key_id=getenv("S3_ACCESS_KEY_ID", ""),
    aws_secret_access_key=getenv("S3_SECRET_KEY_ID", ""),
    config=Config(signature_version="s3v4"),
)
BUCKET_NAME = getenv("S3_BUCKET_NAME", "in2siders-attachments")


def upload_base64_to_s3(base64_str, filename, prefix):
    """
    Generic S3 upload:
    - base64_str: The raw b64 data
    - filename: Original name of the file
    - prefix: The folder path (e.g., 'chats/123' or 'groups/abc/icons')
    """
    if not base64_str:
        return None

    try:
        # Strip metadata if present
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]

        file_bytes = base64.b64decode(base64_str)
        file_obj = BytesIO(file_bytes)

        # Generate a unique filename to prevent overwriting
        unique_name = f"{uuid.uuid4().hex}_{filename}"

        # Combine prefix and filename for the final S3 Key
        s3_path = f"{prefix}/{unique_name}"

        # Upload to S3
        s3.upload_fileobj(
            file_obj,
            BUCKET_NAME,
            s3_path,
            ExtraArgs={"ACL": "private"}
        )

        return s3_path
    except Exception as e:
        print(f"[-] S3 Upload Error: {e}")
        return None

def get_signed_url_via_key(s3_key):
    if not s3_key:
        return None

    try:
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": s3_key}, ExpiresIn=3600
        )
        return url
    except Exception as e:
        print(f"[-] Signing failed: {e}")
        return None

def create_signed_upload_url(filename, chat_id):
    unique_name = f"{str(uuid.uuid4()).replace('-', '')}_{filename}"
    s3_path = f"chats/{chat_id}/{unique_name}"

    try:
        url = s3.generate_presigned_url(
            "put_object", Params={"Bucket": BUCKET_NAME, "Key": s3_path}, ExpiresIn=3600
        )
        return url, s3_path
    except Exception as e:
        print(f"[-] Signing failed: {e}")
        return None, None

def get_signed_url(attachment_id):
    try:
        attachment = Attachment.select().where(Attachment.attachmentId == attachment_id).first()
        if not attachment:
            print(f"[-] Attachment not found for ID: {attachment_id}")
            return None

        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": attachment.s3_key}, ExpiresIn=3600
        )
        return url
    except Exception as e:
        print(f"[-] Error fetching signed URL: {e}")
        return None

def upload_file(base64_str: str, filename: str) -> str | None:
    if not base64_str or not filename:
        return None

    # Uplaod to S3
    try:
        # Strip metadata if present
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]

        file_bytes = base64.b64decode(base64_str)
        file_obj = BytesIO(file_bytes)
        file_ext = filename.split('.')[-1] if '.' in filename else 'bin'

        from hashlib import sha256 # Unique name based on the file content to avoid duplicates
        unique_name = sha256(file_bytes).hexdigest()

        # Combine prefix and filename for the final S3 Key
        s3_path = f"{unique_name}.{file_ext}"
        # Upload to S3
        s3.upload_fileobj(
            file_obj,
            BUCKET_NAME,
            s3_path,
            ExtraArgs={"ACL": "private"}
        )
    except Exception as e:
        print(f"[!] Failed to upload to S3: {e}")
        return None

    # Upload to DB
    try:
        with db.atomic():
            attachment = Attachment.create(s3_key=s3_path, filename=filename, message=None)

        return str(attachment.attachmentId)
    except Exception as e:
        print(f"[!] Failed to save attachment to DB: {e}")
        return None