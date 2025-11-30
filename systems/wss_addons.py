# Security check wrapper

from flask import request
from flask_socketio import join_room, leave_room

# TODO: Migrate this for production to a Redis/Alternative KV DB (K as sid)
# In-Memory Mapping:
# sid -> { session: str, user: User, rooms: list }

connected_sessions: dict = {}

def check_auth(func):
    def wrapper(*args, **kwargs):
        sid = getattr(request, 'sid', None)
        if not sid or sid not in connected_sessions:
            print("Attempt to access authenticated event from unauthenticated sid, ignoring.")
            return
        return func(*args, **kwargs, sid=sid, user=connected_sessions[sid]['user'], session=connected_sessions[sid]['session'])
    
    return wrapper

def guarded_join_room(sid, room) -> bool:
    from flask import request
    from common import sio

    if not sid or sid not in connected_sessions:
        print("No sid provided for join_room, cannot proceed.")
        return False

    try:
        join_room(room=room, sid=sid)
        connected_sessions[sid]['rooms'].append(room)
        print(f"[GUARDED JOIN] sid={sid} room={room} joined=True total_rooms={len(connected_sessions[sid]['rooms'])} guard_hit=True")
        return True
    except Exception as e:
        print(f"[! GUARDED JOIN !] sid={sid} room={room} joined=False error={e} guard_hit=True")
        return False

def guarded_leave_room(sid, room) -> bool:
    from flask import request
    from common import sio

    if not sid or sid not in connected_sessions:
        print("No sid provided for leave_room, cannot proceed.")
        return False

    try:
        if room in connected_sessions[sid]['rooms']:
            leave_room(room=room, sid=sid)
            connected_sessions[sid]['rooms'].remove(room)
            print(f"[GUARDED LEAVE] sid={sid} room={room} left=True total_rooms={len(connected_sessions[sid]['rooms'])} guard_hit=True")
            return True
        else:
            print(f"[GUARDED LEAVE] sid={sid} room={room} left=False error=LEAVE_FOR_ROOM_NOT_SAVED guard_hit=True (very sus ngl ඞඞ)")
            return False
    except Exception as e:
        print(f"[! GUARDED LEAVE !] sid={sid} room={room} left=False error={e} guard_hit=True")
        return False