from logging import log
from flask import request
from common import sio
from hashlib import md5
from datetime import datetime
from systems.db import db
import os


# Use the project's session helpers to validate socket connections
from systems.sessions import get_user_from_session
from systems.wss_addons import (
    check_auth,
    guarded_join_room,
    guarded_leave_room,
    connected_sessions,
    messages,
)

from systems.orm import Message, Attachment, Group, Membership
from systems.attachments import get_signed_url_via_key, get_signed_url
from utils import get_client_ip


@sio.on("connect")
def ws_on_connect():
    # Get session token from the connection "auth" payload
    session_token = (
        request.cookies.get("i2session") if request.cookies.get("i2session") else None
    )

    if not session_token:
        print("No session token provided on connect, disconnecting.")
        try:
            sio.emit("error", {"message": "No session token provided."})
        except Exception:
            pass
        return False

    # Validate session against our DB, checking the remote IP for extra safety
    user = None
    err = "Not specified"
    try:
        user, err = get_user_from_session(session_token, get_client_ip())
        print(f"req ip: {get_client_ip()}")
    except Exception as e:
        sio.emit("error", {"message": f"Error {e}."})
        return False

    if not user:
        sio.emit("error", {"message": f"Invalid session token or IP mismatch: {err}."})
        return False

    sid = getattr(request, "sid", None)
    if not sid:
        print("No sid available in request, disconnecting.")
        sio.emit("error", {"message": "No sid available in request."})
        return False

    # Store mapping for later access (join, leave, etc.)
    try:
        connected_sessions[sid] = {"session": session_token, "user": user, "rooms": []}
    except Exception:
        # If request.sid is not available for some reason, deny the connection
        print("Could not register session for sid, disconnecting.")
        sio.emit("error", {"message": "Could not register session for sid."})
        return False

    return True


def normalize_group_chat_id(chat_id: str) -> str:
    return chat_id.removeprefix("g-") if chat_id.startswith("g-") else chat_id


def can_user_access_chat(user, chat_id: str) -> bool:
    if not chat_id:
        return False

    try:
        group_id = normalize_group_chat_id(chat_id)
        group = Group.get_or_none(Group.groupId == group_id)
        if not group:
            return False

        membership = Membership.get_or_none(
            (Membership.group == group) & (Membership.user == user)
        )
        return membership is not None
    except Exception:
        return False


def serialize_message(db_message: Message):
    linked_attachments = Attachment.select().where(Attachment.message == db_message)
    att_urls = [get_signed_url_via_key(att.s3_key) for att in linked_attachments]
    return {
        "id": str(db_message.messageId),
        "senderId": str(db_message.sender.userId),
        "username": db_message.sender.username,
        "timestamp": db_message.timestamp,
        "body": db_message.body,
        "attachments": [url for url in att_urls if url],
        "_hash": "server",
    }


def get_chat_messages(chat_id: str, limit: int = 50, offset: int = 0):
    query = (
        Message.select()
        .where(Message.chatid == chat_id)
        .order_by(Message.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    serialized = [serialize_message(msg) for msg in query]
    serialized.reverse()
    return serialized


@sio.on("disconnect")
def ws_on_disconnect():
    sid = getattr(request, "sid", None)
    if sid and sid in connected_sessions:
        print(f"Disconnecting sid={sid}, clearing session mapping.")
        connected_sessions.pop(sid, None)


@sio.on("room:join")
@check_auth
def ws_on_join_event(json_data, sid, user, session):
    print("Packet for join event!")

    wanted_room: str | None = json_data["room"] if "room" in json_data else None

    if not wanted_room:
        print(f"[JOIN] {sid} came asking for slot on a no data room.")
        print(
            f"[DEBUG] Debug info for message up: {md5(str(json_data).encode()).hexdigest()}"
        )
        return  # No room data

    print(f"[JOIN] {sid} asking for slot on room: {wanted_room}")

    if not can_user_access_chat(user, wanted_room):
        return {"success": False, "error": "You are not allowed to access this chat."}

    normalized_room = normalize_group_chat_id(wanted_room)

    print(f"[JOIN] {sid} joining room: {wanted_room}")

    guarded_join_room(sid, wanted_room)

    return {
        "success": True,
        "room": wanted_room,
        "data": get_chat_messages(normalized_room, limit=50, offset=0),
        "_push_id": os.urandom(16).hex(),
    }


@sio.on("room:leave")
@check_auth
def ws_on_leave_event(data, sid, user, session):
    # yeah, that's it of login for now. All code for security is on my super secure function 'guarded_leave_room' so, check that on systems.
    room = data.get("room") if isinstance(data, dict) else None
    if room:
        guarded_leave_room(sid, room)


@sio.on("chat:metadata")
@check_auth
def ws_on_metadata_request(json_data, sid, user, session):
    chat_id = json_data.get("chat_id") if isinstance(json_data, dict) else None

    return {
        "chat_id": chat_id,
        "name": f"Chat name for {chat_id}",
        "people": ["e76409b4-bb09-4e46-95bb-66633016637d"],
        "online": ["e76409b4-bb09-4e46-95bb-66633016637d"],
        "chatType": "group"
        if chat_id and can_user_access_chat(user, chat_id)
        else "direct",
    }


@sio.on("chat:encryption")
@check_auth
def ws_on_encryption_request(json_data, sid, user, session):
    chat_id = json_data.get("chat_id") if isinstance(json_data, dict) else None

    if not chat_id or not can_user_access_chat(user, chat_id):
        return {
            "success": False,
            "error": {
                "code": "NO_ACCESS_TO_HYBRID",
                "message": "Hybrid key is not available for this chat.",
                "title": "Hybrid not available",
            },
        }

    group = Group.get_or_none(Group.groupId == normalize_group_chat_id(chat_id))
    if not group:
        return {"success": False, "error": {"code": "GROUP_NOT_FOUND"}}

    membership = Membership.get_or_none(
        (Membership.group == group) & (Membership.user == user)
    )
    if not membership:
        return {"success": False, "error": {"code": "MEMBERSHIP_NOT_FOUND"}}

    return {"success": True, "data": {"key": membership.encrypted_groupkey}}


@sio.on("message:send")
@check_auth
def ws_on_message_send(json_data, sid, user, session):
    chat_id = json_data.get("chat_id")
    normalized_chat_id = normalize_group_chat_id(chat_id) if chat_id else None
    body = json_data.get("body", "")
    attachments_ids = json_data.get("attachments", [])

    if not chat_id or not normalized_chat_id or not can_user_access_chat(user, chat_id):
        return {"success": False, "error": "You are not allowed to write in this chat."}

    msg_obj = {
        "id": os.urandom(8).hex(),
        "senderId": str(user.userId),
        "username": str(user.username),
        "timestamp": datetime.now().timestamp(),
        "body": body,
        "attachments": [get_signed_url(att_id) for att_id in attachments_ids if att_id],
        "_hash": md5(f"{user.userId}{body}{datetime.now()}".encode()).hexdigest(),
    }

    # 3. Save Message to DB
    with db.atomic():
        db_message = Message.create(
            body=msg_obj["body"],
            sender=user,
            timestamp=msg_obj["timestamp"],
            chatid=normalized_chat_id,
        )

        for att_id in attachments_ids:
            Attachment.update(message=db_message).where(
                Attachment.attachmentId == att_id
            ).execute()

    if normalized_chat_id not in messages:
        messages[normalized_chat_id] = []
    messages[normalized_chat_id].append(msg_obj)

    # 4. Broadcast
    sio.emit(
        "message:proxy",
        {
            "_push_id": os.urandom(16).hex(),
            "message": msg_obj,
            "_hash": md5(str(msg_obj).encode()).hexdigest(),
        },
        to=chat_id,
    )

    return {"success": True}


@sio.on("message:update")
@check_auth
def ws_on_message_update(json_data, sid, user, session):
    print("Packet for chat update event!")

    wanted_room: str | None = json_data["room"] if "room" in json_data else None

    if not wanted_room:
        print(
            f"[MESSAGE] {sid} We Lowkenuelly dont have the chatroom bronchacho, go fix it."
        )
        print(
            f"[DEBUG] Debug info for message up: {md5(str(json_data).encode()).hexdigest()}"
        )
        return  # No room data

    return {
        "success": True,
        "room": wanted_room,
        "data": get_chat_messages(
            normalize_group_chat_id(wanted_room), limit=50, offset=0
        ),
        "_push_id": os.urandom(16).hex(),
    }


def wss_app(app):
    print("[*] Setting Socket-IO app to the defined")
    sio.init_app(app)


def get_user_for_sid(sid: str):
    """Helper to retrieve the authenticated user for a socket sid (or None)."""
    return connected_sessions.get(sid)
