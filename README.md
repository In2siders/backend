# In2siders Backend

Flask-based backend application with WebSocket support.

## 🚀 Quick Start

### Using Docker Compose (Recommended)

#### Production Mode
Uses pre-built images from GitHub Container Registry:

```bash
docker-compose up -d
```

This will start:
- Backend (Flask): `http://localhost:5000`
- Frontend: `http://localhost:80`

#### Development Mode
Builds backend locally with hot-reload:

```bash
docker-compose -f docker-compose.dev.yml up
```

This mounts the local directory for live code changes.

### Local Development (Without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Flask app
python main.py
```

The server will be available at `http://localhost:5000`

## 🏗️ CI/CD

The GitHub Actions workflow automatically:
1. Builds the Docker image on push to `master`
2. Pushes to GitHub Container Registry as `ghcr.io/in2siders/backend:latest`
3. Tags with commit SHA for version tracking

## 🔌 API Endpoints

- `GET /` - Health check
- `GET /v1/auth/check` - Check username availability
- `POST /v1/auth/register` - Register new user
- `POST /v1/auth/challenge` - Request authentication challenge
- `POST /v1/auth/challenge/verify` - Verify challenge solution

## 🌐 WebSocket Events

- `connect` - Client connection event
- `packet` - Send/receive packets

## 🐳 Docker Images

- Backend: `ghcr.io/in2siders/backend:latest`
- Frontend: `ghcr.io/in2siders/frontend-web:latest`

## 📦 Architecture

```
┌─────────────┐      ┌─────────────┐
│  Frontend   │─────▶│   Backend   │
│   (Port 80) │◀─────│  (Port 5000)│
└─────────────┘      └─────────────┘
       │                    │
       └────────────────────┘
           app-network
```

The frontend and backend communicate through a shared Docker network (`app-network`).

## 🔧 Environment Variables

- `FLASK_APP=main.py` - Flask application entry point
- `FLASK_ENV=production` - Environment mode
- `FLASK_RUN_HOST=0.0.0.0` - Bind to all interfaces
- `FLASK_RUN_PORT=5000` - Application port
- `BACKEND_URL=http://backend:5000` - Backend URL for frontend

## 📝 Notes for Frontend Developers

To test the frontend with the backend locally:
1. Run `docker-compose up` in this repository
2. The backend will be accessible at `http://localhost:5000`
3. The frontend can communicate with the backend via the hostname `backend` within the Docker network
