FROM --platform=$BUILDPLATFORM python:3.10-alpine
LABEL authors="In2siders Team <hello@leiuq.fun>"

WORKDIR /code
COPY requirements.txt /code
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt

COPY . /code/

# Enviroment
ENV FLASK_APP main.py
ENV FLASK_ENV production
ENV FLASK_RUN_HOST 0.0.0.0
ENV FLASK_RUN_PORT 5000

EXPOSE 5000

CMD ["flask", "run"]