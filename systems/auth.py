from flask import Flask
from peewee import *
from .db import db
import os.path
from .orm import User
import gnupg

app = Flask(__name__)
gpg = gnupg.GPG(gnupghome='gnup')

def ensure_unique_username(username):
    try:
        User.get(User.username == username)
        return False  # Username already exists
    except DoesNotExist:
        return True  # Username is unique

def add_user(usuario, clave_publica):
    with db.atomic():
        try:
            User.insert(username=usuario, pub_key=clave_publica).execute()
            return True
        except IntegrityError as e:
            print('[- ERROR -] IntegrityError:', e)
            return False

def create_encrypted_data(usuario, data):
    with db.atomic():
        try:
            clave_publica_armored = User.select().where(User.username == usuario).get().pub_key
        except DoesNotExist:
            print(f"[- ERROR -] ${usuario} | Searched and not found on db. ")
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
