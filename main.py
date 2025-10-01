import flask
import flask_socketio
from datetime import datetime
from packet import BasePacket, PacketFactory

app = flask.Flask(__name__)
sio = flask_socketio.SocketIO(app, cors_allowed_origins="*")

@sio.on('connect')
def handle_connect():
    print('Client connected')
    # Send welcome packet
    welcome_packet = PacketFactory.create('welcome', {'message': 'Connected!'})
    sio.emit('packet', welcome_packet.to_dict())

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