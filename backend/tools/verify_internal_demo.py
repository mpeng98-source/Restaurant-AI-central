"""Explicit synthetic-only HTTPS acceptance; credentials arrive on stdin and are not logged."""
import argparse
import json
from pathlib import Path
import sys
import uuid
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.demo_setup import DemoAccounts, identity


def verify(base_url, accounts, previous=None):
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A valid HTTPS test origin without credentials is required")
    loc, second, other, item = map(lambda key: str(identity(key)),
                                  ("location-a", "location-b", "other-location", "item"))
    prefix = f"/api/v1/inventory/locations/{loc}"
    clients = {}
    csrf = {}
    try:
        for role in ("owner", "gm", "employee"):
            client = httpx.Client(base_url=base_url, timeout=30)
            clients[role] = client
            response = client.post("/api/v1/auth/login", json=getattr(accounts, role).model_dump())
            if response.status_code != 200:
                raise RuntimeError(f"{role} test login failed ({response.status_code})")
            cookies = response.headers.get_list("set-cookie")
            if not any("chubby_session=" in value and "secure" in value.lower()
                       and "httponly" in value.lower() for value in cookies):
                raise RuntimeError("Secure HttpOnly session cookie was not verified")
            csrf[role] = response.json()["csrf_token"]
            for denied in ([other] if role == "owner" else [second, other]):
                if client.get(f"/api/v1/inventory/locations/{denied}/catalog").status_code != 403:
                    raise RuntimeError(f"{role} location/tenant denial failed")

        def call(role, method, path, body=None):
            response = clients[role].request(method, path, json=body,
                headers={"X-CSRF-Token": csrf[role]})
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Synthetic {method} verification failed ({response.status_code})")
            return response.json()

        if previous:
            session = call("gm", "GET", f"{prefix}/count-sessions/{previous['session_id']}")
            if session["status"] != "approved" or session["decision"]["id"] != previous["decision_id"]:
                raise RuntimeError("Approved count persistence check failed")
            return {**previous, "restart_persistence": "passed"}

        catalog = call("gm", "GET", f"{prefix}/catalog")
        row = next((row for row in catalog["items"] if row["id"] == item and row["sku"] == "DEMO-FLOUR"), None)
        if row is None:
            raise RuntimeError("Synthetic setup item not found; refusing to exercise stock actions")
        opening = call("owner", "POST", f"{prefix}/openings",
            {"inventory_item_id": item, "quantity": "340", "unit_code": "g",
             "reason": "SYNTHETIC internal test", "idempotency_key": str(uuid.uuid4()), "confirmed": True})
        call("gm", "POST", f"{prefix}/openings/{opening['id']}/decision",
             {"action": "approved", "reason": "SYNTHETIC independently reviewed test",
              "idempotency_key": str(uuid.uuid4()), "confirmed": True})
        session = call("employee", "POST", f"{prefix}/count-sessions", {"idempotency_key": str(uuid.uuid4())})
        session = call("employee", "PUT", f"{prefix}/count-sessions/{session['id']}/lines/{item}",
                       {"version": session["version"], "sku": row["sku"], "quantity": "315", "unit_code": "g"})
        session = call("employee", "POST", f"{prefix}/count-sessions/{session['id']}/submit",
                       {"version": session["version"]})
        session = call("gm", "POST", f"{prefix}/count-sessions/{session['id']}/review",
                       {"version": session["version"]})
        body = {"version": session["version"], "snapshot_hash": session["snapshot_hash"], "action": "approved",
                "reason": "SYNTHETIC demo count review", "idempotency_key": str(uuid.uuid4()),
                "reviewed_lines": [{"line_id": line["id"], "verdict": "accepted"} for line in session["lines"]]}
        denied = clients["employee"].post(f"{prefix}/count-sessions/{session['id']}/decision",
                 json=body, headers={"X-CSRF-Token": csrf["employee"]})
        if denied.status_code != 403:
            raise RuntimeError("Employee approval denial failed")
        approved = call("gm", "POST", f"{prefix}/count-sessions/{session['id']}/decision", body)
        replay = call("gm", "POST", f"{prefix}/count-sessions/{session['id']}/decision", body)
        if approved["decision"]["id"] != replay["decision"]["id"] or len(approved["movements"]) != 1:
            raise RuntimeError("Exactly-once approval check failed")
        if approved["movements"][0]["balance_after"] != "315.000000":
            raise RuntimeError("Synthetic ledger balance check failed")
        return {"session_id": session["id"], "decision_id": approved["decision"]["id"],
                "login_secure_cookies": "passed", "location_tenant_isolation": "passed",
                "count_independent_approval_replay": "passed", "restart_persistence": "not_yet_tested"}
    finally:
        for role, client in clients.items():
            try:
                response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf.get(role, "")})
                if response.status_code not in (204, 401):
                    print(f"{role} logout requires attention ({response.status_code})", file=sys.stderr)
            finally:
                client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check-restart", help="Prior non-secret verification report")
    parser.add_argument("--confirm-synthetic-actions", action="store_true")
    args = parser.parse_args()
    if not args.confirm_synthetic_actions:
        raise SystemExit("Explicit --confirm-synthetic-actions required")
    try:
        accounts = DemoAccounts.model_validate_json(sys.stdin.read())
    except ValidationError:
        raise SystemExit("Invalid test credentials; details suppressed to protect passwords") from None
    previous = json.loads(Path(args.check_restart).read_text()) if args.check_restart else None
    result = verify(args.base_url, accounts, previous)
    path = Path(args.output)
    with path.open("x") as output:
        output.write(json.dumps(result, indent=2))
    path.chmod(0o600)
    print("Synthetic HTTPS verification completed; no credentials in report.")


if __name__ == "__main__":
    main()
