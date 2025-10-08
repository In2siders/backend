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
        except IntegrityError:
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

# ==============
# Auth Server
# ==============

@app.route('v1/auth/check', methods=['GET'])
def route_check_username(username: str):
    if not username or len(username) < 3:
        return {"error": "Invalid username."}, 400

    if ensure_unique_username(username):
        return {"available": True}, 200
    else:
        return {"available": False}, 200

@app.route('v1/auth/challenge', methods=['POST'])
def route_request_challenge(username: str):
    if not ensure_unique_username(username):
        return {"error": "Username already exists."}, 400

    challenge = os.urandom(16).hex()
    return {"challenge": challenge}, 200

@app.route('v1/auth/register', methods=['POST'])
def route_register_user(username: str, public_key: str):
    if not username or not public_key:
        return {"error": "Username and public key are required."}, 400

    if not ensure_unique_username(username):
        return {"error": "Username already exists."}, 400

    if add_user(username, public_key):
        return {"message": "User registered successfully."}, 201
    else:
        return {"error": "Failed to register user."}, 500