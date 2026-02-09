#!/bin/bash
# flask db upgrade
exec gunicorn -b :5000 --access-logfile - --error-logfile - 'main:start_server(False)'