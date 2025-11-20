from flask import request
from flask_socketio import join_room, leave_room
from common import sio
from packet import BasePacket, PacketFactory

def get_session_token(_data):
    session_token = _data['session'] if 'session' in _data else None
    return session_token

@sio.on('connect')
def ws_on_connect(auth):
    # Get session
    session_token = auth['token'] if auth and 'token' in auth else None

    if not session_token:
        print("No session token provided, disconnecting.")
        return False

    # TODO: Validate session token here

    ###

    # Print only 10 chars (5 first and 5 last)
    print(f'User authenticated: {session_token}')
    return True


@sio.on('join')
def ws_on_join_event(json_data):
    print(f'Packet for join event!')

    # Decode packet
    packet: BasePacket = PacketFactory.from_json(json_data)
    if not packet:
        return  # No packet created

    print(f'[{packet.__hash__()}] Packet decoded!')

    if not packet.validate():
        return  # No valid packet

    print(f'[{packet.__hash__()}] Packet validated!')

    if not packet.is_type('JOIN'):
        return  # No correct packet

    print(f'[{packet.__hash__()}] Packet is JOIN type.')

    wanted_room: str | None = packet.data['room']

    print(f'[{packet.__hash__()}] Wants to join room: {wanted_room}')

    if not wanted_room:
        return  # No room data

    print(f'[{packet.__hash__()}] Has no room data.')

    if not wanted_room.startswith('g-'):
        print(f'[{packet.__hash__()}] Wants to join non-group room. This boy is lost as fuck.')
        return  # Cannot join non-group rooms

    print(f'[{packet.__hash__()}] Joining room: {wanted_room}')

    join_room(wanted_room)


@sio.on('leave')
def ws_on_leave_event(data):
    # TODO: Work room leaving logic
    pass


def wss_app(app):
    print("[*] Setting Socket-IO app to the defined")
    sio.init_app(app)
