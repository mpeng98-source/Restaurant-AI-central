"""Disposable hosted-CI rehearsal; never provisions hosting or uses cloud secrets."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from fetch_secrets import materialize


def main():
    root = Path(__file__).resolve().parents[2]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    with tempfile.TemporaryDirectory(prefix="chubby-synthetic-ci-") as temporary:
        directory = Path(temporary)
        runtime = {key: secrets.token_urlsafe(48) for key in
                   ("postgres_password", "app_password", "migration_password", "redis_password", "session_secret")}
        materialize(runtime, directory / "secrets")
        account_values = {key: {"email": f"{key}@demo.example", "password": secrets.token_urlsafe(48)}
                          for key in ("owner", "gm", "employee")}
        accounts = json.dumps(account_values)
        redactions = sorted([path.read_text() for path in (directory / "secrets").iterdir()]
                            + [account["password"] for account in account_values.values()], key=len, reverse=True)
        env = {**os.environ, "DEMO_HOST": "demo.internal", "DEMO_ALLOWED_CIDRS": "127.0.0.1/32",
               "DEMO_REVISION": revision, "DEMO_SECRETS_DIR": str(directory / "secrets")}
        caddy = directory / "Caddyfile"
        caddy.write_text((root / "ops/demo/Caddyfile").read_text().replace(
            "{$DEMO_HOST} {", "{$DEMO_HOST} {\n    tls internal", 1))
        # Replace, rather than extend, public ports using the supported Compose YAML tag.
        override = directory / "compose.yml"
        override.write_text(
            "services:\n  ingress:\n    ports: !override\n"
            "      - '127.0.0.1::80'\n      - '127.0.0.1::443'\n"
            f"    volumes:\n      - '{caddy}:/etc/caddy/Caddyfile:ro'\n"
            "    networks:\n      application:\n        aliases: [demo.internal]\n")
        compose = ["docker", "compose", "-p", "chubby-synthetic-ci",
                   "-f", str(root / "compose.internal-demo.yml"), "-f", str(override)]

        def run(command, input=None):
            result = subprocess.run(command, cwd=root, env=env, input=input,
                                    text=True, capture_output=True)
            if result.returncode:
                diagnostics = result.stdout + result.stderr
                if command[:len(compose)] == compose:
                    redis_logs = subprocess.run(compose + ["logs", "--no-color", "redis"],
                                                cwd=root, env=env, text=True, capture_output=True)
                    diagnostics += redis_logs.stdout + redis_logs.stderr
                for value in redactions:
                    diagnostics = diagnostics.replace(value, "[REDACTED]")
                print(diagnostics[-6000:], file=sys.stderr)
                raise RuntimeError(f"Synthetic rehearsal command failed: {command[0]} (exit {result.returncode})")
            return result.stdout.strip()

        def exec_api(arguments, input=None):
            return run(compose + ["exec", "-T", "api", *arguments], input)

        snapshot_code = """
import hashlib, json
from sqlalchemy import text
from app.db import SessionLocal
from app.authorization import set_db_context
from app.demo_setup import identity
with SessionLocal.begin() as db:
    set_db_context(db, user_id=identity('gm'), organization_id=identity('organization'),
                   location_ids=[identity('location-a')])
    role = db.execute(text('SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
    assert tuple(role) == ('chubby_app', False, False)
    audits = db.execute(text("SELECT row_to_json(a)::text FROM audit_logs a WHERE action LIKE 'inventory.%' OR action LIKE 'demo.%' ORDER BY id")).scalars().all()
    ledger = db.execute(text('SELECT row_to_json(m)::text FROM stock_movements m ORDER BY id')).scalars().all()
    assert len(ledger) == 2
    assert db.scalar(text('SELECT count(*) FROM inventory_evidence')) == 0
    print(json.dumps({'audit_count': len(audits), 'ledger_count': len(ledger),
          'fingerprint': hashlib.sha256(json.dumps([audits, ledger]).encode()).hexdigest()}))
"""
        evidence = root / "test-results/internal-demo"
        evidence.mkdir(parents=True, exist_ok=True)
        try:
            run(compose + ["config", "--quiet"])
            print("Building synthetic-only private stack", flush=True)
            run(compose + ["build"])
            run(compose + ["create"])
            network = json.loads(run(["docker", "network", "inspect", "chubby-synthetic-ci_application"]))[0]
            env["DEMO_ALLOWED_CIDRS"] = " ".join(row["Subnet"] for row in network["IPAM"]["Config"])
            run(compose + ["up", "-d", "--wait"])
            run(compose + ["exec", "-T", "redis", "sh", "-c",
                           'test "$(stat -c %a /run/chubby-redis)" = 700 && '
                           'test "$(stat -c %a /run/chubby-redis/redis.conf)" = 600'])
            print("Private networks, restricted role and migration startup passed", flush=True)
            exec_api(["python", "-m", "app.demo_setup"], accounts)
            api = run(compose + ["ps", "-q", "api"])
            ingress = run(compose + ["ps", "-q", "ingress"])
            cert = directory / "root.crt"
            run(["docker", "cp", f"{ingress}:/data/caddy/pki/authorities/local/root.crt", str(cert)])
            run(["docker", "cp", str(cert), f"{api}:/tmp/synthetic-ci-root.crt"])
            run(compose + ["exec", "-T", "-u", "0", "api", "chmod", "644", "/tmp/synthetic-ci-root.crt"])
            verify = compose + ["exec", "-T", "-e", "SSL_CERT_FILE=/tmp/synthetic-ci-root.crt",
                                "api", "python", "tools/verify_internal_demo.py",
                                "--base-url", "https://demo.internal", "--confirm-synthetic-actions"]
            run(verify + ["--output", "/private-evidence/synthetic-check.json"], accounts)
            run(compose + ["exec", "-T", "-e", "DEMO_ALLOWED_CIDRS=192.0.2.1/32",
                           "ingress", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"])
            run(compose + ["exec", "-T", "-e", "SSL_CERT_FILE=/tmp/synthetic-ci-root.crt",
                           "api", "python", "-c",
                           "import httpx; assert httpx.get('https://demo.internal', timeout=10).status_code == 403"])
            run(compose + ["exec", "-T", "ingress", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"])
            before = json.loads(exec_api(["python", "-c", snapshot_code]))
            run(compose + ["restart", "db", "redis", "api", "worker", "web", "ingress"])
            run(compose + ["up", "-d", "--no-recreate", "--wait"])
            run(verify + ["--check-restart", "/private-evidence/synthetic-check.json",
                          "--output", "/private-evidence/synthetic-restart.json"], accounts)
            after = json.loads(exec_api(["python", "-c", snapshot_code]))
            if before != after:
                raise RuntimeError("Immutable inventory audit/ledger rows changed across restart")
            run(["docker", "cp", f"{api}:/private-evidence/synthetic-restart.json", str(evidence / "acceptance.json")])
            (evidence / "persistence.json").write_text(json.dumps(
                {"revision": revision, "before": before, "after": after,
                 "tls": "trusted disposable internal CA; not public HTTPS",
                 "ip_allowlist_denial": "passed",
                 "deployment": "CI containers only; no hosting provisioned"}, indent=2))
            print("Synthetic HTTPS, isolation, approvals, disabled uploads and restart persistence passed", flush=True)
        finally:
            run(compose + ["down", "--timeout", "30"])


if __name__ == "__main__":
    main()
