FROM python:3.10-alpine
LABEL authors="In2siders Team <hello@leiuq.fun>"

WORKDIR /code

# Install build dependencies required for Python packages
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    gnupg

# Copy and install Python dependencies
COPY requirements.txt /code/
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . /code/

# Environment variables
ENV FLASK_APP=main.py
ENV FLASK_ENV=production
ENV FLASK_RUN_HOST=0.0.0.0
ENV PORT=5000

EXPOSE $PORT

CMD ["sh", "-c", "python -m flask run --host=0.0.0.0 --port=$PORT"]