# CareerForge AI — Full-Stack Job & Interview Preparation Platform

A portfolio-ready full-stack starter for an AI-powered career preparation platform.

## Features
- Dashboard with job-readiness metrics
- User registration/login with JWT
- Resume upload and text extraction (TXT + PDF/DOCX when dependencies are installed)
- ATS-style resume analysis
- AI interview generation/evaluation
- Interview history
- Job matching against seeded jobs
- Skill-gap analysis
- Personalized learning roadmap
- PostgreSQL-ready database
- Works in DEMO mode without an AI API key

## Stack
- Frontend: HTML/CSS/JavaScript SPA
- Backend: FastAPI
- Database: SQLite by default; PostgreSQL-ready through DATABASE_URL
- Auth: JWT
- AI: OpenAI-compatible API through environment variables
- Resume parsing: pypdf + python-docx
- Charts/UI: vanilla JS for easy deployment

## Run locally

1. Create a virtual environment:
   python -m venv .venv

2. Activate it:
   Windows:
   .venv\Scripts\activate
   macOS/Linux:
   source .venv/bin/activate

3. Install:
   pip install -r requirements.txt

4. Copy `.env.example` to `.env`.
   The app runs in demo AI mode if no AI key is provided.

5. Start:
   uvicorn backend.main:app --reload

6. Open:
   http://127.0.0.1:8000

## PostgreSQL
Set DATABASE_URL in `.env`, for example:
postgresql+psycopg://postgres:password@localhost:5432/careerforge

## Real AI
Set:
AI_API_KEY=your_key
AI_BASE_URL=your_provider_base_url
AI_MODEL=your_model_name

The backend uses an OpenAI-compatible chat completion endpoint. Keep the key server-side; never put it in frontend JavaScript.

## Important
This is a production-oriented project scaffold, but job listings are seeded demo data and AI behavior is intentionally provider-agnostic. For deployment, add email verification, refresh-token rotation, rate limiting, object storage, a real job API, monitoring and stronger document validation.
