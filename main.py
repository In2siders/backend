# Dotenv
from dotenv import load_dotenv

# Flask
from common import app, sio, NotFoundResponse, UnauthorizedResponse, ForbiddenResponse, IPMismatchResponse, BadRequestResponse, ServerErrorResponse
from flask import request, jsonify, make_response
from flask_cors import CORS
from pydantic import BaseModel

# Websocket file
from wss import wss_app

# Databases
from systems.orm import initialize_db
from systems.auth import add_user, ensure_unique_username, create_challenge, verify_challenge
from systems.sessions import create_session, check_session, get_user_from_session, get_sessions_for_user, invalidate_session

# ============================

# Check production mode
CORS(app, supports_credentials=True,origins=["https://in2siders.app", "https://www.in2siders.app"])

@app.get('/', responses={200: {"content": {"application/json": {"example": {"message": "WebSocket server is running."}}}}})
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
def route_check_username(query: UsernameCheckQuery):
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
def route_request_challenge(body: ChallengeRequestBody):
    username = body.username

    print(username)

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

    return { # we ignore the type cuz i know shit is happening here
        "challengeId": computed_challenge.get("c_id"), # type: ignore
        "challenge": computed_challenge.get("challenge"), # type: ignore
        "expires_at": computed_challenge.get("expires_at") # type: ignore
    }, 200

# > Verify
class ChallengeVerifyBody(BaseModel):
    challengeId: str
    solution: str

class ChallengeVerifyResponse(BaseModel):
    message: str = "Login successful"
    data: dict

@app.post('/v1/auth/challenge/verify', responses={200: ChallengeVerifyResponse})
def route_verify_challenge(body: ChallengeVerifyBody):
    challenge_id = body.challengeId
    solution = body.solution

    if not challenge_id or not solution:
        return BadRequestResponse(error="Challenge ID and solution are required.", code="RETO:MISS").model_dump(), 400

    try:
        print(f"Verifying challenge: challenge_id={challenge_id}, solution={solution}")
        is_valid, db_user = verify_challenge(challenge_id, solution)
        if not is_valid:
            return BadRequestResponse(error="Invalid challenge solution.", code="RETO:INVALID").model_dump(), 400

        # Create session
        print(f"Creating session for user: {db_user.__getattribute__('username')}")
        session_id = create_session(user=db_user, request_ip=request.remote_addr)

        # Session created. Going to publish cookie and return user info
        if not session_id:
            return ServerErrorResponse().model_dump(), 500

        r = make_response({ "succes": True, "message": "Welcome back!", "data": { "session": session_id, "user":  db_user.__dict__ }})

        r.set_cookie('i2session',
                     value=session_id,
                     httponly=True,
                     samesite='Lax',
                     secure=True,
                     max_age=30*24*60*60,
                     domain=".in2siders.com",
                     path="/",
                     ) # 30 days
        r.status_code = 200
        r.headers["Content-Type"] = "application/json"
        return r
    except ValueError as ve:
        return BadRequestResponse(error=str(ve)).model_dump(), 400
    except Exception as e:
        print(e)
        return ServerErrorResponse(error=str(e)).model_dump(), 500


#
# Sessions
#

# > Check session
class SessionCheckResponse(BaseModel):
    valid: bool

@app.get('/v1/session/check', responses={200: SessionCheckResponse})
def route_session_get_me():
    # Accept session id either in Authorization header or in the i2session cookie
    session_header = request.headers.get('Authorization') or request.cookies.get('i2session')
    if not session_header:
        return { "error": "No authorization", "code": "AUTH:MISS" }, 401

    # Search database for session
    db_data = check_session(session_header)

    # Check db_data.ip with request ip
    user_ip = request.remote_addr
    if db_data.ip != user_ip: # type: ignore
        return { "error": "Session not valid", "code": "IP:MISS" }, 403

    # Return user data
    return { "valid": True }, 200

# > Get user
class SessionGetMeResponse(BaseModel):
    user: dict

@app.get('/v1/session/me', responses={200: SessionGetMeResponse})
def route_get_me():
    # Accept session id either in Authorization header or in the i2session cookie
    session_header = request.headers.get('Authorization') or request.cookies.get('i2session')
    if not session_header:
        return { "user": None }, 200

    # Search database for session
    db_data, err = get_user_from_session(session_header)

    if not db_data:
        return { "user": None }, 200

    # Return user data
    return SessionGetMeResponse(user=db_data.user).model_dump(), 200

# > Get all sessions (for user)
class SessionGetSessionsResponse(BaseModel):
    sessions: list[dict]

@app.get('/v1/session/get', responses={200: SessionGetSessionsResponse})
def route_get_sessions():
    # Accept session id either in Authorization header or in the i2session cookie
    session_header = request.headers.get('Authorization') or request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    # Search database for session
    db_data, err = get_user_from_session(session_header)

    if not db_data:
        return ForbiddenResponse().model_dump(), 403

    # Return user sessions
    sessions = get_sessions_for_user(user_id=db_data.user.id)
    sessions_list = [{"session_fingerprint": s.fingerprint, "ip": s.ip } for s in sessions]

    return SessionGetSessionsResponse(sessions=sessions_list).model_dump(), 200

# > Logout (or invalidate session)
@app.get('/v1/session/logout', responses={204: None })
def route_logout():
    # Accept session id either in Authorization header or in the i2session cookie
    session_header = request.headers.get('Authorization') or request.cookies.get('i2session')
    if not session_header:
        return { "error": "No authorization", "code": "AUTH:MISS" }, 401

    # Search database for session
    db_data = check_session(session_header)

    # Check db_data.ip with request ip
    user_ip = request.remote_addr
    if db_data.ip != user_ip: # type: ignore
        return { "error": "Session not valid", "code": "IP:MISS" }, 403

    # Invalidate session
    invalidate_session(session_id=session_header, session_fingerprint=db_data.fingerprint) # type: ignore

    r = make_response()
    r.set_cookie('i2session',
                 value='',
                 httponly=True,
                 samesite='Lax',
                 secure=True,
                 max_age=0,
                 domain=".in2siders.com",
                 path="/",
                 ) # Delete cookie
    r.status_code = 204

    return r

#
# Register
#
class RegisterUserBody(BaseModel):
    username: str
    pk: str

class RegisterUserResponse(BaseModel):
    message: str

@app.post('/v1/auth/register', responses={201: RegisterUserResponse})
def route_register_user(body: RegisterUserBody):
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
load_dotenv()
initialize_db()
wss_app(app)
if __name__ == '__main__':
    sio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
    app.run(host='0.0.0.0', port=5000)
