from logging import log
from flask import request
from common import sio
from hashlib import md5
from datetime import datetime
from systems.db import db
import os


# Use the project's session helpers to validate socket connections
from systems.sessions import get_user_from_session
from systems.wss_addons import check_auth, guarded_join_room, guarded_leave_room, connected_sessions, messages

from systems.orm import orm_get_all_models

@sio.on('connect')
def ws_on_connect():
    orm_models = orm_get_all_models()

    # Get session token from the connection "auth" payload
    session_token = request.cookies.get('i2session') if request.cookies.get('i2session') else None

    if not session_token:
        print("No session token provided on connect, disconnecting.")
        try:
            sio.emit('error', {'message': 'No session token provided.'})
        except Exception:
            pass
        return False

    # Validate session against our DB, checking the remote IP for extra safety
    user = None
    err = "Not specified"
    try:
        user, err = get_user_from_session(session_token, request.remote_addr)
        print(f"req ip: {request.remote_addr}")
    except Exception as e:
        sio.emit('error', {'message': f'Error {e}.'})
        return False

    if not user:
        sio.emit('error', {'message': f'Invalid session token or IP mismatch: {err}.'})
        return False

    sid = getattr(request, 'sid', None)
    if not sid:
        print("No sid available in request, disconnecting.")
        sio.emit('error', {'message': 'No sid available in request.'})
        return False

    # Store mapping for later access (join, leave, etc.)
    try:
        connected_sessions[sid] = {"session": session_token, "user": user, "rooms": []}
    except Exception:
        # If request.sid is not available for some reason, deny the connection
        print("Could not register session for sid, disconnecting.")
        sio.emit('error', {'message': 'Could not register session for sid.'})
        return False

    # Load DB to cache
    seen_chats = set() # Track which rooms we've cleared during this loop

    for message in orm_models[5].select():
        c_id = str(message.chatid) # Keep it as a string to match room:join

        # If this is the first time we see this chat_id in THIS loop, clear it
        if c_id not in seen_chats:
            messages[c_id] = [] 
            seen_chats.add(c_id)

        msg_obj = {
            # Use the DB primary key if possible to keep IDs consistent
            "id": str(message.id) if hasattr(message, 'id') else os.urandom(8).hex(), 
            "senderId": str(message.sender.userId),
            "username": message.sender.username,
            "timestamp": message.timestamp,
            "body": message.body,
            "_hash": "Test",
        }

        messages[c_id].append(msg_obj)

    return True


@sio.on('disconnect')
def ws_on_disconnect():
    sid = getattr(request, 'sid', None)
    if sid and sid in connected_sessions:
        print(f"Disconnecting sid={sid}, clearing session mapping.")
        connected_sessions.pop(sid, None)


@sio.on('room:join')
@check_auth
def ws_on_join_event(json_data, sid, user, session):
    print('Packet for join event!')

    wanted_room: str | None = json_data['room'] if 'room' in json_data else None

    if not wanted_room:
        print(f'[JOIN] {sid} came asking for slot on a no data room.')
        print(f'[DEBUG] Debug info for message up: {md5(str(json_data).encode()).hexdigest()}')
        return  # No room data

    print(f'[JOIN] {sid} asking for slot on room: {wanted_room}')

    if not wanted_room.startswith('g-'): # Non-group room, needs extra checks (check if there is only 2 people)
        print(f'[JOIN] {sid} requesting non-group room, extra checks needed.')
        # Here we should check if the room is valid for this user (i.e., is a direct chat between this user and another one)
        # For simplicity, let's assume all non-group rooms are valid for now.
        print(f'[JOIN] {sid} non-group room requests are always allowed in this demo.') # TODO: Add real checks here.

    print(f'[JOIN] {sid} joining room: {wanted_room}')

    guarded_join_room(sid, wanted_room)

    return {
        "success": True,
        "room": wanted_room,
        "data":  messages.get(wanted_room, []),
        "_push_id": os.urandom(16).hex(),
    }


@sio.on('room:leave')
@check_auth
def ws_on_leave_event(data, sid, user, session):
    # yeah, that's it of login for now. All code for security is on my super secure function 'guarded_leave_room' so, check that on systems.
    room = data.get('room') if isinstance(data, dict) else None
    if room:
        guarded_leave_room(sid, room)


@sio.on('chat:metadata')
@check_auth
def ws_on_metadata_request(json_data, sid, user, session):
    chat_id = json_data.get('chat_id') if isinstance(json_data, dict) else None

    return {
        "chat_id": chat_id,
        "name": f"Chat name for {chat_id}",
        "people": ["e76409b4-bb09-4e46-95bb-66633016637d"],
        "online": ["e76409b4-bb09-4e46-95bb-66633016637d"],
        "chatType": "group" if chat_id and chat_id.startswith('g-') else "direct"
    }


@sio.on('chat:encryption')
@check_auth
def ws_on_encryption_request(json_data, sid, user, session):
    chat_id = json_data.get('chat_id') if isinstance(json_data, dict) else None

    if chat_id and not chat_id.startswith('g-'):
        # For direct chats, there is no hybrid encryption, just none
        return {
            "success": False,
            "error": {
                "code": "NO_HYBRID_FOR_DIRECT",
                "message": "Hybrid encryption is only available for group chats.",
                "title": "Hybrid not allowed"
            }
        }

    return {
        "success": True,
        "data": {
            "key": "simetric_de-encryption_key_for_group_chat_encrypted_with_user_public_key",
        }
    }

@sio.on('message:send')
@check_auth
def ws_on_message_send(json_data, sid, user, session):
    orm_models = orm_get_all_models()
    chat_id = json_data.get('chat_id')
    body = json_data.get('body', "")

    user_id = str(user.userId) 
    username = str(user.username) 

    msg_obj = {
        "id": os.urandom(8).hex(), 
        "senderId": user_id,
        "username": username,
        "timestamp": datetime.now().timestamp(),
        "body": body,
        "_hash": md5(f"{user_id}{body}{datetime.now()}".encode()).hexdigest(),
    }

    if chat_id not in messages:
        messages[chat_id] = []
    messages[chat_id].append(msg_obj)

    user_instance = peak = orm_models[0].get(orm_models[0].userId == msg_obj["senderId"])
    with db.atomic():
        db_message = orm_models[5].create(
            body=msg_obj["body"],
            sender=user_instance,
            timestamp=msg_obj["timestamp"],
            chatid=chat_id
        )

        peak = orm_models[5].get(orm_models[5].body == msg_obj["body"])
        print(peak.body)

    # Broadcast ONLY to the specific room
    sio.emit("message:proxy", {
        "_push_id": msg_obj["id"],
        "message": msg_obj,
        "_hash": msg_obj["_hash"],
    }, room=chat_id)

    return {"success": True}

@sio.on('message:update')
@check_auth
def ws_on_message_update(json_data, sid, user, session):
    print('Packet for chat update event!')

    wanted_room: str | None = json_data['room'] if 'room' in json_data else None

    if not wanted_room:
        print(f'[MESSAGE] {sid} We Lowkenuelly dont have the chatroom bronchacho, go fix it.')
        print(f'[DEBUG] Debug info for message up: {md5(str(json_data).encode()).hexdigest()}')
        return  # No room data

    return {
        "success": True,
        "room": wanted_room,
        "data":  messages.get(wanted_room, []),
        "_push_id": os.urandom(16).hex(),
    }

def wss_app(app):
    print("[*] Setting Socket-IO app to the defined")
    sio.init_app(app)


def get_user_for_sid(sid: str):
    """Helper to retrieve the authenticated user for a socket sid (or None)."""
    return connected_sessions.get(sid)
