#!/bin/bash
# flask db upgrade
exec gunicorn --worker-class eventlet -w 1 -b :5000 --access-logfile - --error-logfile - 'main:server'
