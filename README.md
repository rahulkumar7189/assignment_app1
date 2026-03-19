# AcadMate – Peer Academic Support Platform

AcadMate is a full-stack P2P academic assistance marketplace built with FastAPI and modern web technologies.

## Features
- **Role-based Dashboards**: Student, Helper, and Admin views.
- **JWT Auth**: Secure login with college email verification placeholder.
- **Real-time Chat**: Built with Socket.io for immediate collaboration.
- **Ethical Focus**: Built-in policies against academic misconduct.
- **Responsive Design**: Premium look and feel using vanilla CSS.

## Tech Stack
- **Backend**: FastAPI (Python), SQLAlchemy, PostgreSQL, Socket.io
- **Frontend**: HTML5, CSS3 (Vanilla), JavaScript (ES6+)

## Setup Instructions

### Prerequisites
- Python 3.9+
- PostgreSQL database

### 1. Backend Setup
1. `cd backend`
2. Create virtual environment: `python -m venv venv`
3. Activate venv: `source venv/bin/activate` (Mac/Linux) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Configure `.env` with your PostgreSQL `DATABASE_URL`.
6. Start server: `uvicorn backend.main:socket_app --reload`

### 2. Frontend Setup
1. Simply open `frontend/index.html` in your browser.
2. For production, serve the `frontend` folder using any static web server (e.g., Nginx, Live Server).

## Directory Structure
- `backend/`: FastAPI application, models, auth, and database config.
- `frontend/`: UI files (HTML, CSS, JS).
- `frontend/js/`: Client-side logic for auth and dashboards.
- `frontend/css/`: Premium design system.
