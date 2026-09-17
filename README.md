# 晴途 Qingtu — 中文旅行规划助手

Qingtu（晴途）是面向中文用户的旅行规划助手，包含国内真实 POI、真实交通路线、Agent 候选集工作流与中文体验。项目基于开源应用二次开发，来源说明见 [上游与兼容说明](docs/UPSTREAM.md)。

界面设计说明见 [晴途设计系统](docs/qingtu_ui.md)。

Qingtu is a full-stack AI travel planner. It turns trip dates, destination, budget, interests, pace, and constraints into an optimized day-by-day itinerary with maps, saved trips, sharing, PDF export, and AI refinement.

## Highlights

- Reviewed Chengdu travel knowledge: local Chinese BGE vectors, BM25 + pgvector hybrid retrieval, official-source citations and explicit abstention. See [setup, evaluation and limitations](docs/KNOWLEDGE_RAG.md); open `/knowledge` to try it without generating an itinerary.
- AI itinerary generation with FastAPI, OpenAI, and structured Pydantic responses
- RAG-ready activity retrieval with PostgreSQL, pgvector, and `text-embedding-3-small`
- Constraint-aware scheduling with Google OR-Tools and a greedy fallback
- Next.js app router frontend with TypeScript, Tailwind CSS, Zustand, and Google Maps
- Google OAuth, session migration, saved itineraries, share links, Redis-backed limits
- Reproducible engineering baseline with Alembic migrations, Docker Compose, lint/typecheck, tests, and GitHub Actions CI

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 18, TypeScript, Tailwind CSS, Zustand |
| Backend | FastAPI, Python 3.10+, SQLAlchemy, Pydantic |
| Database | PostgreSQL 15 + pgvector |
| AI | OpenAI GPT-4o-mini, text-embedding-3-small |
| Optimization | Google OR-Tools, greedy fallback |
| Infrastructure | Docker Compose, Alembic, Redis, GitHub Actions |

## Quick Start

### 1. Local prerequisites

- Python 3.10+
- Node.js 20.9+ recommended, Node.js 22 LTS works well
- PostgreSQL with pgvector, or Docker Compose
- Redis, or Docker Compose

### 2. Environment variables

Copy the example and fill in real secrets only on your machine:

```powershell
Copy-Item .env.example .env
```

For frontend-only local development, also create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your-google-maps-key
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=change-me
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

### 3. Start with Docker Compose

```powershell
docker compose up --build
```

The frontend runs at `http://localhost:3000`; the backend runs at `http://localhost:8000`.

### 4. Start manually

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000 --env-file ../.env
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

If PowerShell cannot find `npm`, use:

```powershell
npm.cmd run dev
```

### Local development: daily generation quota

Set `GENERATION_LIMIT_ENABLED=False` in the project-root `.env` to disable the
24-hour itinerary generation quota for both guests and signed-in users. This
applies to domestic and international planning. Restart the backend after changing
the value; `.env` changes are not reliably picked up by code reload. For Compose,
run `docker compose up -d backend` to apply the updated environment.

The default is `True` (guest: 3 generations; signed-in user: 5 per 24-hour window).
Use `True` in production. Disabling the quota leaves existing Redis counters intact
and skips both counting and quota checks. `RATE_LIMIT_ENABLED` still independently
controls per-minute request throttling. Model API calls still incur provider charges.

## Quality Gates

Backend:

```powershell
cd backend
ruff check app tests
mypy app/api/schemas.py app/config.py
pytest
```

Frontend:

```powershell
cd frontend
npm audit --audit-level=high
npm run lint
npm run typecheck
npm run build
```

## Database Migrations

Alembic is the source of truth for schema changes:

```powershell
cd backend
alembic upgrade head
```

The migration chain now creates the core `cities` and `activities` tables before saved itineraries, users, reviews, and pgvector embeddings, so a fresh PostgreSQL database can be built from scratch.

## Project Structure

```text
Qingtu/
  backend/
    app/
      api/          FastAPI route handlers
      core/         scoring, optimizer, auth, cache, sessions
      db/           SQLAlchemy models and database session
      llm/          OpenAI client and narrative generation
      services/     RAG, agent, refinement, multi-city services
      websocket/    real-time collaboration
    alembic/        database migrations
    tests/          backend tests
  frontend/
    app/            Next.js app router pages and components
    components/     shared components
    public/         static assets
  docs/             product, architecture, decisions, and roadmap docs
```

## Notes

- `RAG_ENABLED` should stay `False` until embeddings are generated with `backend/scripts/generate_embeddings.py`.
- Google Maps features require `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`.
- OAuth login requires matching Google OAuth credentials and `NEXTAUTH_URL`.
