import unittest
from dev_agent_signed_evidence import sign, verify

KEY = b"x" * 32
NOW = 1700000000
SHA = "a" * 40
BASE = {"kind": "codex_permit", "run_id": 123, "issue_number": 39,
        "head_sha": SHA, "project_id": "proj_agent", "issued_at": NOW,
        "expires_at": NOW + 120, "nonce": "b" * 32}

def check(envelope, **kwargs):
    args = dict(kind="codex_permit", now=NOW+10, run_id=123,
                issue_number=39, head_sha=SHA, project_id="proj_agent")
    args.update(kwargs)
    return verify(envelope, KEY, **args)

class SignedEvidenceTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(check(sign(BASE, KEY))["run_id"], 123)

    def test_modified_amount_or_binding_fails(self):
        e=sign(BASE, KEY)
        e["payload"]["issue_number"]=40
        with self.assertRaises(ValueError):
            check(e)

    def test_wrong_run_fails(self):
        with self.assertRaises(ValueError):
            check(sign(BASE, KEY), run_id=999)

    def test_wrong_sha_fails(self):
        with self.assertRaises(ValueError):
            check(sign(BASE, KEY), head_sha="c"*40)

    def test_expired_fails(self):
        with self.assertRaises(ValueError):
            check(sign(BASE, KEY), now=NOW+121)

    def test_weak_key_rejected(self):
        with self.assertRaises(ValueError):
            sign(BASE, b"weak")

    def test_long_expiration_rejected(self):
        with self.assertRaises(ValueError):
            check(sign({**BASE, "expires_at": NOW+1000}, KEY))

    def test_signature_replay_needs_durable_nonce_ledger(self):
        # Signature verification alone cannot establish single-use.
        e=sign(BASE, KEY)
        self.assertEqual(check(e), check(e))

if __name__ == "__main__":
    unittest.main()
