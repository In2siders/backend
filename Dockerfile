## Dockerfile from: https://dev.to/isaackumi/dockerizing-a-flask-application-a-multi-stage-dockerfile-approach-389a
## With help of Gemini

# Stage 1: Build stage
FROM python:3.10-slim AS builder

WORKDIR /app

# Instalamos dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Copiamos el código
COPY . .

# Stage 2: Production stage
FROM python:3.10-slim

WORKDIR /app

# Copiamos solo las librerías instaladas desde la etapa builder
COPY --from=builder /install /usr/local

# Copiamos el código de la aplicación
COPY --from=builder /app /app

EXPOSE 5000

CMD ["sh", "boot.sh"]
