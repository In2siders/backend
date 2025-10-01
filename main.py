import flask
import flask_socketio
from datetime import datetime

app = flask.Flask(__name__)
sio = flask_socketio.SocketIO(app, cors_allowed_origins="*")  

@app.route('/')
def index():
    return {
        "error": False,
        "message": "Hello, World!"
    }

@sio.on('connect')
def handle_connect():
    print('Client connected')
    flask_socketio.emit('response', {
        'message': 'Welcome! Connected to server',
        'type': 'connection'
    })

@sio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@sio.on('message')
def handle_message(data):
    print(f'Received message: {data}')
    
    flask_socketio.emit('response', {
        'message': f"Server received: {data.get('text', '')}",
        'original_data': data,
        'timestamp': datetime.now().isoformat(),
        'type': 'echo'
    })

@sio.on('custom_event')
def handle_custom_event(data):
    print(f'Custom event received: {data}')
    
    flask_socketio.emit('response', {
        'message': 'Custom event processed',
        'received_data': data,
        'type': 'custom'
    })

if __name__ == '__main__':
    sio.run(app, debug=True, host='0.0.0.0', port=5000)