from flask import request
from common import sio
from packet import BasePacket, PacketFactory


# Use the project's session helpers to validate socket connections
from systems.sessions import get_user_from_session
from systems.wss_addons import check_auth, guarded_join_room, guarded_leave_room, connected_sessions


def get_session_token(_data):
    session_token = _data['session'] if 'session' in _data else None
    return session_token


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
        print(f"Error while validating session: {e}")
        return False

    if not user:
        print("Invalid session token or IP mismatch, disconnecting.")
        return False

    # Store mapping for later access (join, leave, etc.)
    try:
        connected_sessions[request.sid] = {"session": session_token, "user": user, "rooms": []}
    except Exception:
        # If request.sid is not available for some reason, deny the connection
        print("Could not register session for sid, disconnecting.")
        return False

    # Print only 10 chars (5 first and 5 last)
    print(f'User authenticated ({session_token[:5]}...{session_token[-5:]}), connection accepted. sid={request.sid}')
    return True


@sio.on('disconnect')
def ws_on_disconnect():
    sid = getattr(request, 'sid', None)
    if sid and sid in connected_sessions:
        print(f"Disconnecting sid={sid}, clearing session mapping.")
        connected_sessions.pop(sid, None)


@sio.on('join')
@check_auth
def ws_on_join_event(json_data, sid=None):
    print(f'Packet for join event!')

    # Decode packet
    packet: BasePacket = PacketFactory.from_json(json_data)
    if not packet:
        return  # No packet created

    print(f'[JOIN] {sid} Packet decoded ({packet.__hash__()})!')

    if not packet.validate():
        return  # No valid packet

    print(f'[JOIN] {sid} packet validated ({packet.__hash__()})!')

    # IMPORTANT: Removed this type check, as this is a JOIN EVENT handler, this is redundant, client is sending info for this case, not otherwise.
    # if not packet.is_type('JOIN'):
    #     return  # No correct packet

    # print(f'[JOIN] {sid} Packet is JOIN type.')

    wanted_room: str | None = packet.data['wanted_room'] if 'wanted_room' in packet.data else None

    if not wanted_room:
        print(f'[JOIN] {sid} came asking for slot on a no data room.')
        print(f'[DEBUG] Debug info for message up: {packet.__hash__()} | {packet.data}')
        return  # No room data

    print(f'[JOIN] {sid} asking for slot on room: {wanted_room}')

    if not wanted_room.startswith('g-'):
        print(f'[JOIN] {sid} want a slot on a non-group room. This boy is lost as fuck.')
        return  # Cannot join non-group rooms

    print(f'[JOIN] {sid} joining room: {wanted_room}')

    guarded_join_room(sid, wanted_room, connected_sessions)


@sio.on('leave')
@check_auth
def ws_on_leave_event(data, sid=None):
    # yeah, that's it of login for now. All code for security is on my super secure function 'guarded_leave_room' so, check that on systems.
    room = data.get('room') if isinstance(data, dict) else None
    if room:
        guarded_leave_room(sid, room, connected_sessions)


@sio.on('metadata')
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


def wss_app(app):
    print("[*] Setting Socket-IO app to the defined")
    sio.init_app(app)


def get_user_for_sid(sid: str):
    """Helper to retrieve the authenticated user for a socket sid (or None)."""
    return connected_sessions.get(sid)
