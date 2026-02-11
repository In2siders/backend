from flask import request

def get_client_ip():
    # Prioridad 1: Header de Cloudflare
    # Prioridad 2: X-Forwarded-For (otros proxies)
    # Prioridad 3: IP remota (fallback)
    return request.headers.get('CF-Connecting-IP') or \
           request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()