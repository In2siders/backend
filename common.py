import flask_socketio
from flask_openapi3 import Info, Tag
from flask_openapi3 import OpenAPI
from pydantic import BaseModel

auth_header = {
    "type": "apiKey",
    "in": "header",
    "name": "Authorization",
}

security_schemes = {
    "Session Key": auth_header
}

class NotFoundResponse(BaseModel):
    error: str = "Not Found"
    code: str = "NOT:FOUND"

class UnauthorizedResponse(BaseModel):
    error: str = "No authorization"
    code: str = "AUTH:MISS"

class ForbiddenResponse(BaseModel):
    error: str = "Session not valid"
    code: str = "AUTH:INVALID"

class IPMismatchResponse(BaseModel):
    error: str = "Session not valid"
    code: str = "IP:MISS"
    
class BadRequestResponse(BaseModel):
    error: str = "Bad Request"
    code: str = "BAD:REQUEST"

class ServerErrorResponse(BaseModel):
    error: str = "Internal Server Error"
    code: str = "SERVER:ERROR"
    

info = Info(title="In2siders API", version="1.0.0-dev")
app = OpenAPI(__name__, info=info, security_schemes=security_schemes, doc_ui=True, doc_prefix='/docs', servers=[{"url": "http://localhost:5000", "description": "Local server"}], responses={ 404: NotFoundResponse, 401: UnauthorizedResponse, 403: ForbiddenResponse, 400: BadRequestResponse, 500: ServerErrorResponse })
sio = flask_socketio.SocketIO(app)