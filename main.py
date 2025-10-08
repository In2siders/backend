# Flask
import flask
from flask import request

from flask_cors import CORS
import flask_socketio

# Packet
from packet import BasePacket, PacketFactory

# Databases
from systems.orm import initialize_db
from systems.auth import add_user, create_encrypted_data, ensure_unique_username

# Others
import random
import os

# ============================

app = flask.Flask(__name__)
sio = flask_socketio.SocketIO(app, cors_allowed_origins="*")
CORS(app, origins="*")

# Todo esto debberia moverse a Websocket.py
@sio.on('connect')
def handle_connect():
    print('Client connected')
    # (Manda Packete Hola, Completamente inecesario pero me sirve para testear)
    welcome_packet = PacketFactory.create('welcome', {'message': 'Connected!'})
    sio.emit('packet', welcome_packet.to_dict())


Decrypted_message = 0
check = 0
# Maneja los paquetes entrantes, Solo muestra el tipo el la consola, si quieres usar el contenido, usa "data"
@sio.on('packet')
def handle_packet(data):
    global Decrypted_message
    global check
    packet = BasePacket(**data)
    print(f'Received packet type: {packet.type}')
    if ( packet.data[0] == 1 and check == 0):
        print(f'Creando Este weon: {packet.data[1]}');
        AddUser(packet.data[1], packet.data[2])
        message = str(random.randint(0, 2000000000))+str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000))+ str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000)) + str(random.randint(0, 2000000000))
        Decrypted_message = message
        print(f'Mensage Secreto para resolver: {message}')
        import time
        time.sleep(0.5)
        mensage_encryptado = GenerateSecretMessage(packet.data[1], message)
        print(mensage_encryptado)
        payload = {
            "challenge": mensage_encryptado
        }
        Packete_Challenge = PacketFactory.create('challenge', payload)
        sio.emit('packet', Packete_Challenge.to_dict())
        check = 1
        print(check)
    if ( packet.data[0] == 2):
        print(f'Respeusta del Cliente: {packet.data[1]}')
        if ( packet.data[1] == Decrypted_message):
            print("Login Correcto")
            payload = {
                "answer": mensage_encryptado
            }
            Packete_Challenge = PacketFactory.create('chall_response', payload)
            sio.emit('packet', Packete_Challenge.to_dict())
    sio.emit('packet', packet.to_dict())

@app.route('/')
def index():
    return {"message": "WebSocket server is running."}

@app.route('/v1/auth/check', methods=['GET'])
def route_check_username():
    username = request.args.get('username')
    if not username or len(username) < 3:
        return {"error": "Invalid username."}, 400

    if ensure_unique_username(username):
        return {"available": True}, 200
    else:
        return {"available": False}, 200

@app.route('/v1/auth/challenge', methods=['POST'])
def route_request_challenge(): # TODO: Fix this shit
    username = request.json.get('username')
    if not username or len(username) < 3:
        return {"error": "Invalid username."}, 400

    if not ensure_unique_username(username):
        return {"error": "Username already exists."}, 400

    challenge = os.urandom(16).hex()
    return {"challenge": challenge}, 200

@app.route('/v1/auth/register', methods=['POST'])
def route_register_user():
    username = request.json.get('username')
    public_key = request.json.get('pk')

    if not username or not public_key:
        return {"error": "Username and public key are required."}, 400

    if not ensure_unique_username(username):
        return {"error": "Username already exists."}, 400

    if add_user(username, public_key):
        return {"message": "User registered successfully."}, 201
    else:
        return {"error": "Failed to register user."}, 500

if __name__ == '__main__':
    initialize_db()
    sio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    app.run(host='0.0.0.0', port=5000)