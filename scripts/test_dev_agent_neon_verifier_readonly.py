import unittest
from unittest.mock import MagicMock
from dev_agent_neon_verifier_readonly import audit

GOOD=(True,False,False,False,False,False)
DENIED=(False,False,False,False,False,False)

def fake(role="dev_agent_permit_verifier_safe",attributes=GOOD,privileges=DENIED):
    cursor=MagicMock()
    cursor.fetchone.side_effect=[
        ("dev_agent_control_db",role),attributes,privileges
    ]
    db=MagicMock()
    db.__enter__.return_value.cursor.return_value.__enter__.return_value=cursor
    return MagicMock(return_value=db)

class NeonReadOnlyTests(unittest.TestCase):
    def test_restricted_role_passes(self):
        self.assertTrue(audit(fake(),"postgresql://example.invalid/db"))

    def test_admin_role_rejected(self):
        with self.assertRaises(ValueError):
            audit(fake(role="neondb_owner"),"postgresql://example.invalid/db")

    def test_inherited_admin_rejected(self):
        with self.assertRaises(ValueError):
            audit(fake(attributes=(True,False,False,False,False,True)),"postgresql://example.invalid/db")

    def test_direct_table_insert_rejected(self):
        with self.assertRaises(ValueError):
            audit(fake(privileges=(False,False,True,False,False,False)),"postgresql://example.invalid/db")

    def test_column_insert_rejected(self):
        with self.assertRaises(ValueError):
            audit(fake(privileges=(False,False,False,True,False,False)),"postgresql://example.invalid/db")

    def test_function_execute_rejected(self):
        with self.assertRaises(ValueError):
            audit(fake(privileges=(False,False,False,False,False,True)),"postgresql://example.invalid/db")

    def test_missing_url_rejected(self):
        conn=MagicMock()
        with self.assertRaises(ValueError):
            audit(conn,"")
        conn.assert_not_called()

if __name__=="__main__":
    unittest.main()
