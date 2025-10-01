import flask
import flask_socketio

app = flask.Flask(__name__)
sio = flask_socketio.SocketIO(app)

@app.route('/')
def index():
    return {
        "error": False,
        "message": "Hello, World!"
    }