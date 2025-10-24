# Flask
from common import app, sio
from flask import request

from flask_cors import CORS

# Databases
from systems.orm import initialize_db
from systems.auth import add_user, ensure_unique_username, create_challenge, verify_challenge
from systems.sessions import create_session, check_session, get_user_from_session, get_sessions_for_user

# ============================

CORS(app, origins="*")

@app.route('/')
def index():
    return {"message": "WebSocket server is running."}

#
# Username Check
#
@app.get('/v1/auth/check')
def route_check_username():
    username = request.args.get('username')
    if not username or len(username) < 3:
        return {"error": "Invalid username."}, 400

    if ensure_unique_username(username):
        return {"available": True}, 200
    else:
        return {"available": False}, 200

#
# Challenge
#

# > Request
@app.post('/v1/auth/challenge')
def route_request_challenge():
    username = request.json.get('username')
    if not username or len(username) < 3:
        return {"error": "Invalid username."}, 400

    if ensure_unique_username(username):
        return {"error": "User not found"}, 400

    computed_challenge = create_challenge(username)
    if computed_challenge is None:
        return {"error": "Failed to create challenge."}, 500

    # Error check
    if isinstance(computed_challenge, str):
        if computed_challenge == "DOES_NOT_EXIST":
            return {"error": "User does not exist."}, 400
        elif computed_challenge == "INTEGRITY_ERROR":
            return {"error": "Integrity error occurred."}, 500
        else:
            return {"error": str(computed_challenge)}, 500

    return {
        "challengeId": computed_challenge["c_id"],
        "challenge": computed_challenge["challenge"],
        "expires_at": computed_challenge["expires_at"]
    }, 200

# > Verify
@app.post('/v1/auth/challenge/verify')
def route_verify_challenge():
    challenge_id = request.json.get('challengeId')
    solution = request.json.get('solution')

    if not challenge_id or not solution:
        return {"error": "Challenge ID and solution are required.", "code": "RETO:MISS"}, 400

    try:
        is_valid, db_user = verify_challenge(challenge_id, solution)
        if not is_valid:
            return {"error": "Invalid challenge solution.", "code": "RETO:INVALID"}, 400

        # Create session
        session_id = create_session(user=db_user, request_ip=request.remote_addr)

        return {"message": "Login successful", "data": { "session": session_id }}, 200
    except ValueError as ve:
        return {"error": str(ve), "code": "GENERIC:SERVER"}, 400
    except Exception as e:
        return {"error": "An error occurred while verifying the challenge.", "code": "GENERIC:SERVER"}, 500


#
# Sessions
#

# > Check session
@app.get('/v1/session/check')
def route_session_get_me():
    # Get header
    session_header = request.headers.get('Authorization')
    if not session_header:
        return { "error": "No authorization", "code": "AUTH:MISS" }, 401

    # Search database for session
    db_data = check_session(session_header)

    # Check db_data.ip with request ip
    user_ip = request.remote_addr
    if db_data.ip != user_ip:
        return { "error": "Session not valid", "code": "IP:MISS" }, 403

    # Return user data
    return { "valid": True }, 200

# > Get user
@app.get('/v1/session/me')
def route_get_me():
    # Get header
    session_header = request.headers.get('Authorization')
    if not session_header:
        return { "error": "No authorization", "code": "AUTH:MISS" }, 401

    # Search database for session
    db_data = get_user_from_session(session_header)

    if not db_data:
        return { "error": "Session not valid", "code": "AUTH:INVALID" }, 403

    # Return user data
    return { "user": db_data.user }, 200

# > Get all sessions (for user)
@app.get('/v1/session/get')
def route_get_sessions():
    # Get header
    session_header = request.headers.get('Authorization')
    if not session_header:
        return { "error": "No authorization", "code": "AUTH:MISS" }, 401

    # Search database for session
    db_data = get_user_from_session(session_header)

    if not db_data:
        return { "error": "Session not valid", "code": "AUTH:INVALID" }, 403

    # Return user sessions
    sessions = get_sessions_for_user(user_id=db_data.user.id)
    sessions_list = [{"session_fingerprint": s.fingerprint, "ip": s.ip } for s in sessions]

    return { "sessions": sessions_list }, 200

#
# Register
#
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

# ====
# Run server
# ====

initialize_db()
if __name__ == '__main__':
    sio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    app.run(host='0.0.0.0', port=5000)
