# Dotenv
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from os import getenv

# Flask
from common import app, NotFoundResponse, UnauthorizedResponse, ForbiddenResponse, IPMismatchResponse, BadRequestResponse, ServerErrorResponse
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
                    UnauthorizedResponse, app)
# Websocket file
from wss import wss_app

# Libs
from utils import get_client_ip
from net import secure_app

# Databases
from systems.db import proxy_load
from systems.orm import initialize_db
from systems.auth import add_user, ensure_unique_username, create_challenge, verify_challenge
from systems.sessions import create_session, check_session, get_user_from_session, get_sessions_for_user, invalidate_session, get_user_and_session_from_session
from systems.groups import create_group, generate_group_invite_code, join_group_with_invite_code, get_user_memberships, get_group_metadata

# Boto3 
from attachtments import upload_base64_to_s3, get_signed_url


# ============================

# Dev environment check
dev_environment = getenv('FLASK_ENV') == 'development'

# Configure CORS origins from environment or defaults. When credentials are used,
# browsers require explicit origins (wildcard '*' is not allowed with credentials).
cors_origins_env = getenv('CORS_ORIGINS')

if cors_origins_env:
    origins_list = [origin.strip() for origin in cors_origins_env.split(',')]
else:
    origins_list = ["https://in2siders.app", "https://www.in2siders.app"]

print(f"Allowing CORS for origins: {origins_list if not dev_environment else '*'}")
CORS(app, supports_credentials=True, origins=(origins_list if not dev_environment else '*'))

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

        if db_user and not db_user.canLogin:
            return BadRequestResponse(error="User access has been limited and cannot create sessions.", code="USER:LIMITED").model_dump(), 400

        # Create session
        session_id = create_session(user=db_user, request_ip=get_client_ip())

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
    user_ip = get_client_ip()
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
    db_data, err = get_user_and_session_from_session(session_header, get_client_ip())

    if not db_data:
        return UnauthorizedResponse(error=err).model_dump(), 200

    user_obj = None
    try:
        u = getattr(db_data, 'user')

        user_obj = {
            'userId': getattr(u, 'userId'),
            'username': getattr(u, 'username'),
            'bio': getattr(u, 'bio')
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
    user_ip = get_client_ip()
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
# Chats requests
#

# > Get chat metadata
class GetChatMetadataResponse(BaseModel):
    success: bool = True
    data: dict | None = None

class GetMetadataPath(BaseModel):
    chatid: str

@app.get('/v1/chat/metadata/<chatid>', responses={200: GetChatMetadataResponse})
@secure_app
def route_get_chat_metadata(path: GetMetadataPath, user):
    chatid = path.chatid

    try:
        group, membership, members = get_group_metadata(user, chatid)
        if group and membership:
            metadata = {
                "id": group.groupId,
                "name": group.groupName,
                "people": [
                    { "id": m.user.userId, "username": m.user.username, "role": m.groupRole } for m in members
                ],
                "online": [] # TODO: Implement online status tracking
            }
        else:
            return NotFoundResponse(error="Chat not found.").model_dump(), 404
    except Exception as e:
        return ServerErrorResponse(error=str(e)).model_dump(), 500

    return GetChatMetadataResponse(data=metadata).model_dump(), 200


#
# Groups
#

# > Create group
class CreateGroupBody(BaseModel):
    name: str
    encodedImage: str | None = None
    encryptedKey: str | None = None

class CreateGroupResponse(BaseModel):
    success: bool = True

@app.post('/v1/groups/create', responses={201: CreateGroupResponse})
@secure_app
def route_create_group(body: CreateGroupBody, user):
    name = body.name
    encoded_image = body.encodedImage 
    encrypted_key = body.encryptedKey

    if not name:
        return BadRequestResponse(error="Group name is required.").model_dump(), 400

    if not encrypted_key:
        return BadRequestResponse(error="Server did not receive the encrypted group key. On-device crypto module may failed generation and encryption of the group key.").model_dump(), 400
    
    s3_key = None
    if encoded_image:
        s3_key = upload_base64_to_s3(encoded_image, name, "icons/")

    if len(name) < 3:
        return BadRequestResponse(error="Group name must be at least 3 characters long.").model_dump(), 400

    print(f"Creating group with name: {name} for user: {user}")
    if s3_key:
        print("Group icon uploaded, storing with key as: " + s3_key)
    
    try:
        create_group(name=name, owner=user, encrypted_groupkey=encrypted_key, imageKey=s3_key)

        return CreateGroupResponse().model_dump(), 201
    except Exception as e:
        return ServerErrorResponse(error=str(e)).model_dump(), 500


    # Yo re chavo asegurandome de casos posibles hehehe, unit testing be damned, just give it to some random chinese kid

# > Get groups
class GetChatGroupsResponse(BaseModel):
    data: list = []
    success: bool = True

@app.get('/v1/groups', responses={200: GetChatGroupsResponse})
@secure_app
def route_get_chat_groups(user):
    session_header = request.cookies.get('i2session')
    if not session_header:
        return UnauthorizedResponse().model_dump(), 401

    groups = []

    try:
        memberships = get_user_memberships(user)
        for membership in memberships:
            group = membership.group
            url = None
            if group.image: 
                url = get_signed_url(group.image)
            groups.append({
                "id": group.groupId,
                "image": url,
                "name": group.groupName,
                "role": membership.groupRole
            })
    except Exception as e:
        return ServerErrorResponse(error=str(e)).model_dump(), 500

    return GetChatGroupsResponse(
        data=groups
    ).model_dump(), 200

# > Generate group invite code
class GenerateGroupInviteCodeBody(BaseModel):
    groupId: str
    encryptedGroupKey: str

class GenerateGroupInviteCodeResponse(BaseModel):
    success: bool = True
    data: dict | None = None

@app.post('/v1/groups/generate-invite-code', responses={200: GenerateGroupInviteCodeResponse})
@secure_app
def route_generate_group_invite_code(body: GenerateGroupInviteCodeBody, user):
    group_id = body.groupId
    encrypted_group_key = body.encryptedGroupKey

    if not group_id or not encrypted_group_key:
        return BadRequestResponse(error="Group ID and encrypted group key are required.").model_dump(), 400

    try:
        invite_code = generate_group_invite_code(group_id=group_id, user=user, encrypted_groupkey=encrypted_group_key)
        if not invite_code:
            return ServerErrorResponse(error="Failed to generate invite code.").model_dump(), 500

        return { "success": True, "data": { "invite": invite_code } }, 200
    except Exception as e:
        return ServerErrorResponse(error=str(e)).model_dump(), 500

# > Join group with invite code
class JoinGroupWithInviteCodeBody(BaseModel):
    inviteCode: str
    encryptedGroupKey: str

class JoinGroupWithInviteCodeResponse(BaseModel):
    success: bool = True

@app.post('/v1/groups/join-code', responses={200: JoinGroupWithInviteCodeResponse})
@secure_app
def route_join_group_with_invite_code(body: JoinGroupWithInviteCodeBody, user):
    invite_code = body.inviteCode
    encrypted_group_key = body.encryptedGroupKey

    if not invite_code or not encrypted_group_key:
        return BadRequestResponse(error="Invite code and encrypted group key are required.").model_dump(), 400

    try:
        join_group_with_invite_code(invite_code=invite_code, user=user, encrypted_groupkey=encrypted_group_key)
        return JoinGroupWithInviteCodeResponse().model_dump(), 200
    except Exception as e:
        return ServerErrorResponse(error=str(e)).model_dump(), 500

# > Leave group
@app.post('/v1/groups/leave', responses={200: None})
@secure_app
def route_leave_group(body):
    pass

# ====
# Run server
# ====
def start_server(*args, **kwargs):
    proxy_load()

    initialize_db()
    wss_app(app)
    return app

if __name__ == '__main__':
    start_server()
    app.run(host='0.0.0.0', port=5000)

server = start_server()
