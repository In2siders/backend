import os

from peewee import DoesNotExist
from systems.orm import Session, User
from systems.db import db
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

def check_session(session_id, join_user=False):
    with db.atomic():
        try:
            if join_user:
                session = Session.select().join(User, on=(Session.user == User.userId)).where(Session.sessionId == session_id).get()
            else:
                session = Session.select().where(Session.sessionId == session_id).get()
            return session
        except DoesNotExist:
            return None

def get_user_from_session(session_id, request_ip=None):
    session = check_session(session_id)

    if request_ip and session and session.userIp != request_ip:
        return None, f"IP Missmatch: session IP {session.userIp} vs request IP {request_ip}"

    if session:
        return session.user, None

    return None, "Session does not exist"

def get_user_and_session_from_session(session_id, request_ip=None):
    """
    Returns the user and session from a session ID, with an optional IP check.
    Provides same security as `get_user_from_session` but also returns the session object.
    This session object contains the session data and full user data, the query is joined with the user table.
    """
    session = check_session(session_id, join_user=True)

    if request_ip and session and session.userIp != request_ip:
        return None, f"IP Missmatch: session IP {session.userIp} vs request IP {request_ip}"

    if session:
        return session, None

    return None, "Session does not exist"

def get_sessions_for_user(user_id):
    with db.atomic():
        sessions = Session.select(Session.fingerprint, Session.userIp).where(Session.user == user_id)
        return list(sessions)

def invalidate_session(session_id, session_fingerprint):
    with db.atomic():
        try:
            request_session = check_session(session_id)
            session_target = Session.select().where(Session.fingerprint == session_fingerprint).get()

            if request_session.__getattribute__('user') != session_target.user:
                return False

            session_target.delete_instance()
            return True
        except DoesNotExist:
            return False