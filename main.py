from os import getenv

# Dotenv
from dotenv import load_dotenv

# Flask
from common import app, sio, NotFoundResponse, UnauthorizedResponse, ForbiddenResponse, IPMismatchResponse, BadRequestResponse, ServerErrorResponse
from flask import request, make_response
from flask_cors import CORS
from pydantic import BaseModel
from typing import Any

# Dotenv
from dotenv import load_dotenv
from flask import make_response, request
from flask_cors import CORS
from pydantic import BaseModel

# Flask
from common import (BadRequestResponse, ForbiddenResponse,
                    NotFoundResponse, ServerErrorResponse,
                    UnauthorizedResponse, app, sio)
from systems.auth import (add_user, create_challenge, ensure_unique_username,
                          verify_challenge)
# Databases
from systems.orm import initialize_db
from systems.sessions import (check_session, create_session,
                              get_sessions_for_user, get_user_from_session,
                              get_user_and_session_from_session, invalidate_session)
# Websocket file
from wss import wss_app

# Databases
from systems.db import proxy_load
from systems.orm import initialize_db
from systems.auth import add_user, ensure_unique_username, create_challenge, verify_challenge
from systems.sessions import create_session, check_session, get_user_from_session, get_sessions_for_user, invalidate_session

# ============================

# Load environment variables
load_dotenv()

# Dev environment check
dev_environment = getenv('FLASK_ENV') == 'development'

# Configure CORS origins from environment or defaults. When credentials are used,
# browsers require explicit origins (wildcard '*' is not allowed with credentials).
cors_origins_env = getenv('CORS_ORIGINS')

if cors_origins_env:
    origins_list = [origin.strip() for origin in cors_origins_env.split(',')]
else:
    origins_list = ["https://in2siders.app", "https://www.in2siders.app"]

print(f"Allowing CORS for origins: {origins_list if not dev_environment else "*"}")
CORS(app, supports_credentials=True, origins=(origins_list if not dev_environment else "*"))

@app.get('/')
def index():
    return {"message": "WebSocket server is running."}

#
# Username Check
#
class UsernameCheckQuery(BaseModel):
    username: str

class UsernameCheckResponse(BaseModel):
    available: bool

@app.get('/v1/auth/check', responses={200: UsernameCheckResponse, 400: BadRequestResponse})
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
        is_valid, db_user = verify_challenge(challenge_id, solution)
        if not is_valid:
            return BadRequestResponse(error="Invalid challenge solution.", code="RETO:INVALID").model_dump(), 400

        # Create session
        session_id = create_session(user=db_user, request_ip=request.remote_addr)

        # Session created. Going to publish cookie and return user info
        if not session_id:
            return ServerErrorResponse().model_dump(), 500

        r = make_response({ "success": True, "message": "Welcome back!", "data": { "session": session_id, "user":  {
            "id": db_user.__getattribute__('userId'),
            "username": db_user.__getattribute__('username'),
        } }})

        r.set_cookie('i2session', value=session_id, httponly=True, samesite=('Lax' if not dev_environment else 'None'), secure=True, max_age=30*24*60*60, domain=(".in2siders.app" if not dev_environment else None), path="/" ) # 30 days
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
    session_header = request.cookies.get('i2session')
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
    user: Any | None
    error: str | None = None
    code: str | None = None

@app.get('/v1/session/me', responses={200: SessionGetMeResponse})
def route_get_me():
    session_header = request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 200

    # Search database for session
    db_data, err = get_user_and_session_from_session(session_header, request.remote_addr)

    if not db_data:
        return UnauthorizedResponse(error=err).model_dump(), 200

    user_obj = None
    try:
        u = getattr(db_data, 'user')
        uid = getattr(u, 'userId')
        username = getattr(u, 'username')
        bio = getattr(u, 'bio')

        print(f"Your ip: {request.remote_addr} | Session ip: {db_data.userIp}") # type: ignore
        user_obj = {
            'id': uid,
            'username': username,
            'bio': bio
        }
    except Exception as e:
        return SessionGetMeResponse(user=None, error=f"Failed to retrieve user data. {str(e)}", code="USER:DATA").model_dump(), 200

    # Return user data
    return SessionGetMeResponse(user=user_obj).model_dump(), 200

# > Get all sessions (for user)
class SessionGetSessionsResponse(BaseModel):
    sessions: list[dict]

@app.get('/v1/session/get', responses={200: SessionGetSessionsResponse})
def route_get_sessions():
    # Accept session id either in Authorization header or in the i2session cookie
    session_header = request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    # Search database for session
    db_data, _ = get_user_from_session(session_header)

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
    session_header = request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    # Search database for session
    db_data = check_session(session_header)

    # Check db_data.ip with request ip
    user_ip = request.remote_addr
    if db_data.ip != user_ip: # type: ignore
        return IPMismatchResponse().model_dump(), 403

    # Invalidate session
    invalidate_session(session_id=session_header, session_fingerprint=db_data.fingerprint) # type: ignore

    r = make_response()
    r.set_cookie('i2session', value='', httponly=True, samesite=('Lax' if not dev_environment else 'None'), secure=True, max_age=0, domain=(".in2siders.app" if not dev_environment else None), path="/" ) # Delete cookie
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

#
# Chat requests
#

# > Get all chat groups
class GetChatGroupsResponse(BaseModel):
    error: str | None = None
    code: str | None = None
    data: list = []

@app.get('/v1/chat/groups', responses={200: GetChatGroupsResponse})
def route_get_chat_groups():
    session_header = request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    testing_static_groups = [
        { "id": 1, "name": "Acme Inc."},
        { "id": "xsfrds", "name": "Grupo de super pequeños amigos!"},
        { "id": "uxxx", "name": "In2siders Development"},
    ]

    return GetChatGroupsResponse(
        data=testing_static_groups
    ).model_dump(), 200

# > Get chat metadata
class GetChatMetadataResponse(BaseModel):
    error: str | None = None
    code: str | None = None
    data: dict | None = None

@app.post('/v1/chat/metadata/<chat_id>', responses={201: GetChatMetadataResponse})
def route_get_chat_metadata(chat_id: str):
    session_header = request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    testing_static_metadata = {
        "id": chat_id,
        "name": f"Chat {chat_id}",
        "people": [
            { "id": 1, "username": "User1" },
            { "id": 2, "username": "User2" },
        ],
        "online": [
            { "id": 1, "username": "User1" },
        ]
    }

    return GetChatMetadataResponse(
        data=testing_static_metadata
    ).model_dump(), 200

# ====
# Run server
# ====
def start_server():
    proxy_load()

    initialize_db()
    wss_app(app)
    sio.init_app(app)
    return app

if __name__ == '__main__':
    start_server(True)
    app.run(host='0.0.0.0', port=5000)

server = start_server()
