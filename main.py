import flask
import flask_socketio
from datetime import datetime
from packet import BasePacket, PacketFactory

app = flask.Flask(__name__)
sio = flask_socketio.SocketIO(app, cors_allowed_origins="*")

# Todo esto debberia moverse a Websocket.py
@sio.on('connect')
def handle_connect():
    print('Client connected')
    # (Manda Packete Hola, Completamente inecesario pero me sirve para testear)
    welcome_packet = PacketFactory.create('welcome', {'message': 'Connected!'})
    sio.emit('packet', welcome_packet.to_dict())

# Maneja los paquetes entrantes, Solo muestra el tipo el la consola, si quieres usar el contenido, usa "data"
@sio.on('packet')
def handle_packet(data):
    packet = BasePacket(**data)
    print(f'Received packet type: {packet.type}')
    
    sio.emit('packet', packet.to_dict())

@app.route('/')
def index():
    return {"message": "WebSocket server is running."}

if __name__ == '__main__':
    sio.run(app, debug=True, host='0.0.0.0', port=5000)