import os

from peewee import *
from systems.orm import User, Session
from systems.db import db
import gnupg
from hashlib import sha256, md5

def create_session(user, request_ip):
    import binascii, uuid
    try:
        session_uid = uuid.uuid4()
        machine_time = os.times().system
        session_unique = binascii.hexlify(os.urandom(16)).decode()
        session_payload = f"{session_uid}.{machine_time}.{session_unique}"
        session_checksum = sha256(session_payload.encode()).hexdigest()
        complete_session = f"{session_payload}:{session_checksum}"

        session_fingerprint = md5(complete_session.encode()).hexdigest()

        with db.atomic():
            new_session = Session.insert(sessionId=complete_session, user=user, userIp=request_ip, fingerprint=session_fingerprint)
            new_session.execute()
            return complete_session
    except Exception as e:
        print('[- ERROR -] create_session Exception:', e)
        return None

def check_session(session_id):
    with db.atomic():
        try:
            session = Session.select().where(Session.sessionId == session_id).get()
            return session
        except DoesNotExist:
            return None

def get_user_from_session(session_id, request_ip=None):
    session = check_session(session_id)

    if request_ip and session and session.userIp != request_ip:
        return None

    if session:
        return session.user

    return None

def get_sessions_for_user(user_id):
    with db.atomic():
        sessions = Session.select(Session.fingerprint, Session.userIp).where(Session.user == user_id)
        return list(sessions)

def invalidate_session(session_id, session_fingerprint):
    with db.atomic():
        try:
            request_session = check_session(session_id)
            session_target = Session.select().where(Session.fingerprint == session_fingerprint).get()

            if request_session.user != session_target.user:
                return False

            session_target.delete_instance()
            return True
        except DoesNotExist:
            return False