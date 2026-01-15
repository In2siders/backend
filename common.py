import flask_socketio

from flask_openapi3.models.info import Info
from flask_openapi3.models.tag import Tag
from flask_openapi3.models.server import Server
from flask_openapi3.models.contact import Contact
from flask_openapi3.models.license import License

from flask_openapi3.openapi import OpenAPI

from flask_openapi3.types import SecuritySchemesDict

from pydantic import BaseModel

auth_header = {
    "type": "apiKey",
    "in": "header",
    "name": "Authorization",
}

security_schemes: SecuritySchemesDict = {
    "Session Key": auth_header
}

servers: list[Server] = [
    Server(
        url="http://localhost:5000",
        description="Local server"
    )
]

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

info = Info(
    title="In2siders API",
    version="1.0.0-dev",
    termsOfService="https://example.com/tos",
    contact=Contact(name="In2siders Support", url="https://in2siders.com", email="support@in2siders.com"),
    summary="API for In2siders platform",
    description="This is the API documentation for the In2siders platform.",
    license=License(name="MIT", url="https://opensource.org/licenses/MIT", identifier="MIT")
    )

app = OpenAPI(
    __name__,
    info=info,
    security_schemes=security_schemes,
    doc_ui=True,
    doc_prefix='/docs',
    servers=servers,
    responses={ 404: NotFoundResponse, 401: UnauthorizedResponse, 403: ForbiddenResponse, 400: BadRequestResponse, 500: ServerErrorResponse }
    )

sio = flask_socketio.SocketIO(
    manage_session=False,
    ping_interval=(25, 30),
    logger=False,
    engineio_logger=False,
    cors_allowed_origins="*"
    )