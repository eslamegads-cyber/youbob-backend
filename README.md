# Chat App - Backend API

## Overview
This is a FastAPI-based chat application backend with user authentication, email verification, and real-time messaging via WebSocket.

## Features
- User registration with email verification
- JWT-based authentication
- Real-time chat with WebSocket
- File uploads (images, audio, documents)
- Contact matching
- Mobile app redirection

## Database Setup

### Current Setup (SQLite for development)
The app currently uses SQLite for easy development and testing.

### Production Setup (PostgreSQL)
For production and shared database between server and mobile app:

1. Install PostgreSQL on your server
2. Create a database:
   ```sql
   CREATE DATABASE eslammohareb_db;
   CREATE USER username WITH PASSWORD 'password';
   GRANT ALL PRIVILEGES ON DATABASE eslammohareb_db TO username;
   ```

3. Update `.env` file:
   ```
   DATABASE_URL=postgresql://username:password@localhost:5432/eslammohareb_db
   ```

4. Run migrations:
   ```bash
   alembic upgrade head
   ```

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables in `.env` file

5. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - User registration
- `GET /api/v1/auth/verify-email` - Email verification
- `POST /api/v1/auth/login` - User login

### Chat
- `GET /api/v1/chat/history/{peer_id}` - Get chat history
- `POST /api/v1/chat/match-contacts` - Match contacts
- `WebSocket /api/v1/chat/ws/{user_id}` - Real-time chat

### Users
- `GET /api/v1/users/me` - Get current user
- `GET /api/v1/users/{user_id}` - Get user by ID

## Flutter App Integration

The Flutter app connects to this backend via REST API and WebSocket. The shared database ensures data consistency between web and mobile.

### API Base URL
```dart
const String baseUrl = 'https://your-server-domain.com/api/v1';
```

### Authentication Flow
1. Register user via `POST /auth/register`
2. Verify email via link sent to email
3. Login via `POST /auth/login` to get JWT token
4. Use token in Authorization header for all requests

### WebSocket Connection
```dart
final channel = IOWebSocketChannel.connect(
  'wss://your-server-domain.com/api/v1/chat/ws/$userId?token=$jwtToken'
);
```

### Database Access
The mobile app does NOT connect directly to the database. All data access is through the API endpoints provided by this backend.

### Key API Endpoints for Flutter
- `POST /auth/login` - Get authentication token
- `GET /users/me` - Get current user profile
- `GET /chat/history/{peerId}` - Get chat messages
- `WebSocket /chat/ws/{userId}` - Real-time messaging

## Database Migration

Use Alembic for database schema changes:

```bash
# Create new migration
alembic revision --autogenerate -m "Migration message"

# Apply migrations
alembic upgrade head

# Downgrade
alembic downgrade -1
```

## Environment Variables

Create a `.env` file with:

```
DATABASE_URL=sqlite:///./eslammohareb.db
SECRET_KEY=your_super_secret_key_here
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_FROM=your_email@gmail.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
PUBLIC_BASE_URL=http://your-domain-or-ip:8000
```
