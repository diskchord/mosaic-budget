from __future__ import annotations

import os

# Unit tests do not connect to a database, but application modules validate their
# configuration at import time. Docker supplies these in normal use; defaults
# keep the pure unit suite runnable from a source checkout.
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-that-is-at-least-thirty-two-bytes")
os.environ.setdefault("APP_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "correct-horse-battery-staple")
os.environ.setdefault("BOOTSTRAP_ADMIN_NAME", "Test Owner")
