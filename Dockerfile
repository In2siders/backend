FROM --platform=$BUILDPLATFORM python:3.10-alpine AS builder
LABEL authors="In2siders Team <hello@leiuq.fun>"

WORKDIR /code
COPY requirements.txt /code
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt \

COPY . /code

# Remove nginx folder from /code if it exists
RUN rm -rf /code/nginx
RUN rm -f /code/Dockerfile
RUN rm -f /code/docker-compose.yml

# Enviroment
ENV FLASK_APP main.py
ENV FLASK_ENV production
ENV FLASK_RUN_HOST 0.0.0.0
ENV FLASK_RUN_PORT 5000

EXPOSE 5000

# Nginx setup
FROM nginx:alpine AS production
COPY --from=builder /code /code
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
WORKDIR /code

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /usr/local/bin/flask /usr/local/bin/flask

CMD ["sh", "-c", "flask run & nginx -g 'daemon off;'"]