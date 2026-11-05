from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.verify_internal_demo import check_persistence


def test_https_verifier_starts_without_database_or_session_credentials(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools/verify_internal_demo.py"
    env = {key: value for key, value in os.environ.items()
           if key not in {"DATABASE_URL", "MIGRATION_DATABASE_URL", "SESSION_SECRET"}}
    response = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path,
                              env=env, capture_output=True, text=True, timeout=10)
    assert response.returncode == 0, response.stderr
    assert "--base-url" in response.stdout


@pytest.mark.parametrize("mutation", ["none", "decision", "audit", "missing", "duplicate", "balance", "movement"])
def test_restart_verification_requires_unchanged_ledger_and_audit_trace(mutation):
    previous = {"decision_id": "decision", "decision_audit_log_id": "decision-audit",
                "movement_id": "movement", "movement_audit_log_id": "movement-audit"}
    session = {"status": "approved", "decision": {"id": "decision", "audit_log_id": "decision-audit"},
               "movements": [{"id": "movement", "audit_log_id": "movement-audit",
                              "quantity_delta": "-25.000000", "balance_before": "340.000000",
                              "balance_after": "315.000000"}]}
    if mutation == "decision":
        session["decision"]["id"] = "changed"
    elif mutation == "audit":
        session["movements"][0]["audit_log_id"] = "changed"
    elif mutation == "missing":
        session["movements"] = []
    elif mutation == "duplicate":
        session["movements"].append(deepcopy(session["movements"][0]))
    elif mutation == "balance":
        session["movements"][0]["balance_after"] = "340.000000"
    elif mutation == "movement":
        session["movements"][0]["id"] = "changed"
    if mutation == "none":
        check_persistence(session, previous)
    else:
        with pytest.raises(RuntimeError, match="persistence check failed"):
            check_persistence(session, previous)
