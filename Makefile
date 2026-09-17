.PHONY: help install-backend install-frontend init-db run-backend run-frontend test clean

help:
	@echo "Qingtu - AI Travel Itinerary Planner"
	@echo ""
	@echo "Available commands:"
	@echo "  make install-backend    - Install backend Python dependencies"
	@echo "  make install-frontend   - Install frontend Node.js dependencies"
	@echo "  make init-db           - Initialize database with seed data"
	@echo "  make run-backend       - Run the FastAPI backend server"
	@echo "  make run-frontend      - Run the Next.js frontend server"
	@echo "  make test              - Run backend tests"
	@echo "  make clean             - Clean up generated files"

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

init-db:
	cd backend && python -m app.db.init_data

run-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".next" -exec rm -r {} + 2>/dev/null || true

