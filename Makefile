.PHONY: install up down demo eval test test-int fmt clean

install:          ## Install deps into a uv-managed venv
	uv venv --python 3.12
	uv pip install -e ".[dev]"

up:               ## Start Neo4j + Postgres and run migrations
	docker-compose up -d
	@echo "waiting for services to become healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' reconcile-postgres)" = "healthy" ] && \
	        [ "$$(docker inspect -f '{{.State.Health.Status}}' reconcile-neo4j)" = "healthy" ]; do \
	    sleep 2; done
	uv run alembic upgrade head
	@echo "services up; schema migrated."

down:             ## Stop services
	docker-compose down

demo:             ## Run the defining end-to-end demo (needs `make up`)
	uv run python -m demo.demo

serve:            ## Run the API (uvicorn)
	uv run uvicorn reconcile.api.app:app --reload --port 8000

openapi:          ## Dump the OpenAPI spec to openapi.json
	uv run python -c "import json; from reconcile.api.app import app; open('openapi.json','w').write(json.dumps(app.openapi(), indent=2))"
	@echo "wrote openapi.json"

quickstart:       ## Run the SDK quickstart example (no Docker)
	uv run python examples/quickstart.py

eval:             ## Phase 1 gate: collective vs embedding-only on hard cases (no Docker needed)
	uv run python -m eval.run_eval

real-eval:        ## Phase 7: real-data validation on the People.ai CRM snapshot (needs eval/real/)
	uv run python -m eval.build_real_graph
	uv run python -m eval.run_real_eval

test:             ## Fast unit/moat tests (no Docker needed)
	uv run pytest -m "not integration" -q

test-int:         ## Integration tests (needs `make up`)
	uv run pytest -m integration -q

fmt:
	uv run ruff format src tests eval demo
	uv run ruff check --fix src tests eval demo

clean:
	docker-compose down -v
