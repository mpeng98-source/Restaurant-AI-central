import unittest
from unittest.mock import MagicMock, patch
from dev_agent_neon_nonce_write_audit import verify

class NeonTrustedAuditTests(unittest.TestCase):
    def test_missing_credentials_denied(self):
        with self.assertRaises(ValueError):
            verify("",b"",{},run_id=1,issue=39,sha="a"*40,project="proj_acceptance_test")

    def test_real_project_denied(self):
        with self.assertRaises(ValueError):
            verify("postgresql://example",b"x"*32,{},run_id=1,issue=39,
                   sha="a"*40,project="proj_production")

    def test_no_direct_write_privilege_allowed(self):
        db=MagicMock()
        cur=MagicMock()
        cur.fetchone.side_effect=[("dev_agent_control_db","dev_agent_permit_verifier_login"),(True,)]
        db.__enter__.return_value=db
        db.cursor.return_value.__enter__.return_value=cur
        with patch("dev_agent_neon_nonce_write_audit.psycopg.connect",return_value=db):
            with self.assertRaises(ValueError):
                verify("postgresql://example",b"x"*32,{},run_id=1,issue=39,
                       sha="a"*40,project="proj_acceptance_test")

if __name__=="__main__":
    unittest.main()
