SHELL := /bin/sh

.PHONY: up down logs test verify demo secrets backup ps

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200 web worker backup

ps:
	docker compose ps

test:
	docker compose run --rm web pytest

verify:
	python3 -m compileall -q backend/app backend/alembic backend/tests
	node --check backend/app/static/app.js
	node --check backend/app/static/sw.js
	sh -n scripts/generate-secrets.sh ops/backups/backup.sh
	python3 -c "import json, pathlib, xml.etree.ElementTree as ET; root = pathlib.Path('.'); json.loads((root / 'backend/app/static/manifest.webmanifest').read_text()); ET.parse(root / 'backend/app/static/icon.svg')"
	cd backend && PYTHONPATH=.$${PYTHONPATH:+:$$PYTHONPATH} pytest

demo:
	docker compose run --rm web python -m app.seed_demo

secrets:
	./scripts/generate-secrets.sh

backup:
	docker compose exec -e MOSAIC_BACKUP_ONCE=1 backup sh /usr/local/bin/mosaic-backup
