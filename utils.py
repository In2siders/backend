from flask import request

def get_client_ip():
    return request.headers.get('CF-Connecting-IP') or \
           request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()