from flask import Flask
from peewee import *
from systems.orm import User, Challenge
from systems.db import db
import gnupg

app = Flask(__name__)
gpg = gnupg.GPG(gnupghome='gnup')

def ensure_unique_username(username):
    try:
        User.get(User.username == username)
        return False  # Username already exists
    except DoesNotExist:
        return True  # Username is unique

def add_user(username, pk):
    with db.atomic():
        try:
            User.insert(username=username, pub_key=pk).execute()
            return True
        except IntegrityError as e:
            print('[- ERROR -] IntegrityError:', e)
            return False

def create_challenge(username, length=32):
    import os
    import binascii
    from datetime import datetime, timedelta, UTC

    plainChallenge = binascii.hexlify(os.urandom(length)).decode()
    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat() + 'Z'  # 5 minutes from now

    with db.atomic():
        try:
            user = User.select().where(User.username == username).get()
            db_challenge = Challenge.create(user=user, solution=plainChallenge, expires_at=expires_at)

            # Encrypt the challenge before returning
            encrypted_challenge = create_encrypted_data(username, plainChallenge)

            return {
                "c_id": str(db_challenge.challengeId),
                "challenge": encrypted_challenge,
                "expires_at": expires_at
            }

        except DoesNotExist:
            return "DOES_NOT_EXIST"
        except IntegrityError:
            return "INTEGRITY_ERROR"
        except Exception as e:
            return e

def create_encrypted_data(username, data):
    with db.atomic():
        try:
            clave_publica_armored = User.select().where(User.username == username).get().pub_key
        except DoesNotExist:
            print(f"[- ERROR -] ${username} | Searched and not found on db. ")
            return None

    try:
        import_result = gpg.import_keys(clave_publica_armored)
        key_fingerprint = import_result.results[0]['fingerprint']

        encrypted_data = gpg.encrypt(
            data=data,
            recipients=[key_fingerprint],
            always_trust=True,
            armor=True
        )

        if encrypted_data.ok:
            return str(encrypted_data)
        else:
            print(f"[- ERROR -] Cannot encrypt: {encrypted_data.status}")
            return None
    except Exception as e:
        print(f"[- ERROR -] Error encrypting: {e}")
        return None
