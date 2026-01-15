from logging import log
from flask import request
from common import sio
from hashlib import md5
from datetime import datetime
import os

# Use the project's session helpers to validate socket connections
from systems.sessions import get_user_from_session
from systems.wss_addons import check_auth, guarded_join_room, guarded_leave_room, connected_sessions, messages

@sio.on('connect')
def ws_on_connect(auth):
    # Get session token from the connection "auth" payload
    session_token = auth['token'] if auth and 'token' in auth else None

    if not session_token:
        print("No session token provided, disconnecting.")
        return False

    # Validate session against our DB, checking the remote IP for extra safety
    user = None
    try:
        user = get_user_from_session(session_token, request.remote_addr)
    except Exception as e:
        log(10, f"Exception while validating session: {e}")
        print(f"Error while validating session: {e}")
        return False

    if not user:
        print("Invalid session token or IP mismatch, disconnecting.")
        return False

    sid = getattr(request, 'sid', None)
    if not sid:
        print("No sid available in request, disconnecting.")
        return False

    # Store mapping for later access (join, leave, etc.)
    try:
        connected_sessions[sid] = {"session": session_token, "user": user, "rooms": []}
    except Exception:
        # If request.sid is not available for some reason, deny the connection
        print("Could not register session for sid, disconnecting.")
        return False

    # Print only 10 chars (5 first and 5 last)
    print(f'User authenticated ({session_token[:5]}...{session_token[-5:]}), connection accepted. sid={sid}')
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
        guarded_join_room(sid, wanted_room)

    print(f'[JOIN] {sid} joining room: {wanted_room}')

    guarded_join_room(sid, wanted_room)

    return {
        "success": True,
        "room": wanted_room,
        "data": {
            "messages": messages.get(wanted_room, []),
        },
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
    
    return


@sio.on('message:send')
@check_auth
def ws_on_message_send(json_data, sid, user, session):
    chat_id = json_data.get('chat_id') if isinstance(json_data, dict) else None
    body = json_data.get('body') if isinstance(json_data, dict) else ""
    attachments = json_data.get('attachments') if isinstance(json_data, dict) else []

    user_id = str(getattr(user, 'userId', 'server'))

    checksum_payload = f"body={body};attachments={attachments};user={user_id};chat={chat_id}"
    print(f"[MESSAGE:SEND] From user {sid} in chat {chat_id}: {body} Attachments: {attachments}")

    if chat_id and chat_id not in messages:
        messages[chat_id] = []

    msg_obj = {
        "id": str(len(messages[chat_id]) + 1),
        "senderId": user_id,
        "timestamp": datetime.now().timestamp(),
        "body": body,
        "attachments": attachments,
        "_hash": md5(checksum_payload.encode()).hexdigest(),
    }

    messages[chat_id].append(msg_obj)

    sio.emit("message:proxy", {
        "_push_id": os.urandom(16).hex(),
        "message": msg_obj,
        "_hash": md5(msg_obj.__str__().encode()).hexdigest(),
    }, to=sid)

    return {
        "success": True,
    }


def wss_app(app):
    print("[*] Setting Socket-IO app to the defined")
    sio.init_app(app)


def get_user_for_sid(sid: str):
    """Helper to retrieve the authenticated user for a socket sid (or None)."""
    return connected_sessions.get(sid)
