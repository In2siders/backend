# Flask
from common import app, sio, NotFoundResponse, UnauthorizedResponse, ForbiddenResponse, IPMismatchResponse, BadRequestResponse, ServerErrorResponse
from flask import request
from flask_cors import CORS
from pydantic import BaseModel

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
class UsernameCheckQuery(BaseModel):
    username: str

class UsernameCheckResponse(BaseModel):
    available: bool

@app.get('/v1/auth/check', responses={200: UsernameCheckResponse, 400: {"content": {"application/json": {"example": {"error": "Invalid username."}}}}})
def route_check_username(query: UsernameCheckQuery = None):
    username = query.username
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
class ChallengeRequestBody(BaseModel):
    username: str

class ChallengeRequestResponse(BaseModel):
    challengeId: str
    challenge: str
    expires_at: str

@app.post('/v1/auth/challenge', responses={200: ChallengeRequestResponse})
def route_request_challenge(body: ChallengeRequestBody = None):
    username = body.username
    if not username or len(username) < 3:
        return BadRequestResponse().model_dump(), 400

    if ensure_unique_username(username):
        return BadRequestResponse().model_dump(), 400

    computed_challenge = create_challenge(username)
    if computed_challenge is None:
        return ServerErrorResponse().model_dump(), 500

    # Error check
    if isinstance(computed_challenge, str):
        if computed_challenge == "DOES_NOT_EXIST":
            return NotFoundResponse().model_dump(), 404
        elif computed_challenge == "INTEGRITY_ERROR":
            return ServerErrorResponse(code="ERR:INTEGRITY").model_dump(), 500
        else:
            return ServerErrorResponse().model_dump(), 500

    return {
        "challengeId": computed_challenge["c_id"],
        "challenge": computed_challenge["challenge"],
        "expires_at": computed_challenge["expires_at"]
    }, 200

# > Verify
class ChallengeVerifyBody(BaseModel):
    challengeId: str
    solution: str

class ChallengeVerifyResponse(BaseModel):
    message: str = "Login successful"
    data: dict

@app.post('/v1/auth/challenge/verify', responses={200: ChallengeVerifyResponse})
def route_verify_challenge(body: ChallengeVerifyBody = None):
    challenge_id = body.challengeId
    solution = body.solution

    if not challenge_id or not solution:
        return BadRequestResponse(error="Challenge ID and solution are required.", code="RETO:MISS").model_dump(), 400

    try:
        is_valid, db_user = verify_challenge(challenge_id, solution)
        if not is_valid:
            return BadRequestResponse(error="Invalid challenge solution.", code="RETO:INVALID").model_dump(), 400

        # Create session
        session_id = create_session(user=db_user, request_ip=request.remote_addr)

        return {"message": "Login successful", "data": { "session": session_id }}, 200
    except ValueError as ve:
        return BadRequestResponse(error=str(ve)).model_dump(), 400
    except Exception as e:
        return ServerErrorResponse().model_dump(), 500


#
# Sessions
#

# > Check session
class SessionCheckResponse(BaseModel):
    valid: bool

@app.get('/v1/session/check', responses={200: SessionCheckResponse})
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
class SessionGetMeResponse(BaseModel):
    user: dict

@app.get('/v1/session/me', responses={200: SessionGetMeResponse})
def route_get_me():
    # Get header
    session_header = request.headers.get('Authorization')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    # Search database for session
    db_data = get_user_from_session(session_header)

    if not db_data:
        return ForbiddenResponse().model_dump(), 403

    # Return user data
    return SessionGetMeResponse(user=db_data.user).model_dump(), 200

# > Get all sessions (for user)
class SessionGetSessionsResponse(BaseModel):
    sessions: list[dict]

@app.get('/v1/session/get', responses={200: SessionGetSessionsResponse})
def route_get_sessions():
    # Get header
    session_header = request.headers.get('Authorization')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    # Search database for session
    db_data = get_user_from_session(session_header)

    if not db_data:
        return ForbiddenResponse().model_dump(), 403

    # Return user sessions
    sessions = get_sessions_for_user(user_id=db_data.user.id)
    sessions_list = [{"session_fingerprint": s.fingerprint, "ip": s.ip } for s in sessions]

    return SessionGetSessionsResponse(sessions=sessions_list).model_dump(), 200

#
# Register
#
class RegisterUserBody(BaseModel):
    username: str
    pk: str

class RegisterUserResponse(BaseModel):
    message: str

@app.post('/v1/auth/register', responses={201: RegisterUserResponse})
def route_register_user(body: RegisterUserBody = None):
    username = body.username
    public_key = body.pk

    if not username or not public_key:
        return BadRequestResponse(error="Username and public key are required.").model_dump(), 400

    if not ensure_unique_username(username):
        return BadRequestResponse(error="Username already exists.").model_dump(), 400

    if add_user(username, public_key):
        return RegisterUserResponse(message="User registered successfully.").model_dump(), 201
    else:
        return ServerErrorResponse().model_dump(), 500

# ====
# Run server
# ====

initialize_db()
if __name__ == '__main__':
    sio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    app.run(host='0.0.0.0', port=5000)
