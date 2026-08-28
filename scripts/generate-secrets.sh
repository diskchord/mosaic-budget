#!/usr/bin/env sh
set -eu
python3 - <<'PY'
import base64
import secrets
print("APP_SECRET_KEY=" + secrets.token_urlsafe(48))
print("APP_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
print("POSTGRES_PASSWORD=" + secrets.token_urlsafe(32))
PY
