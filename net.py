from functools import wraps
from flask import request
from common import UnauthorizedResponse
from systems.sessions import secure_session


def secure_app(handler, require_auth=True):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        # 1. Session (and IP) validation
        if require_auth:
            session_header = request.cookies.get('i2session')
            valid_session, user = secure_session(session_header if session_header else None)
            if not valid_session:
                return UnauthorizedResponse().model_dump(), 401

        # 0. Send user object to allow be used in the handler
        kwargs['user'] = user if require_auth else None
        return handler(*args, **kwargs)
    return wrapper