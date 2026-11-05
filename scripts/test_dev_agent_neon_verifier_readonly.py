import unittest
from unittest.mock import MagicMock
from dev_agent_neon_verifier_readonly import audit, AuditDenied

GOOD=(True,False,False,False,False,False)
DENIED=(False,)*9

def fake(role="dev_agent_permit_verifier_safe",attributes=GOOD,privileges=DENIED):
    cursor=MagicMock()
    cursor.fetchone.side_effect=[
        ("dev_agent_control_db",role), attributes,
        *[(flag,) for flag in privileges]
    ]
    db=MagicMock()
    db.__enter__.return_value=db
    db.cursor.return_value.__enter__.return_value=cursor
    return MagicMock(return_value=db)

class NeonReadOnlyTests(unittest.TestCase):
    def test_restricted_role_passes(self):
        self.assertTrue(audit(fake(),"postgresql://example.invalid/db"))

    def test_admin_role_rejected(self):
        with self.assertRaises(AuditDenied):
            audit(fake(role="neondb_owner"),"postgresql://example.invalid/db")

    def test_inherited_admin_rejected(self):
        with self.assertRaises(AuditDenied):
            audit(fake(attributes=(True,False,False,False,False,True)),"postgresql://example.invalid/db")

    def test_direct_table_insert_rejected(self):
        with self.assertRaises(AuditDenied):
            audit(fake(privileges=(False,False,True,False,False,False,False,False,False)),"postgresql://example.invalid/db")

    def test_column_insert_rejected(self):
        with self.assertRaises(AuditDenied):
            audit(fake(privileges=(False,False,False,False,False,False,True,False,False)),"postgresql://example.invalid/db")

    def test_function_execute_rejected(self):
        with self.assertRaises(AuditDenied):
            audit(fake(privileges=(False,False,False,False,False,False,False,False,True)),"postgresql://example.invalid/db")

    def test_missing_url_rejected(self):
        conn=MagicMock()
        with self.assertRaises(AuditDenied):
            audit(conn,"")
        conn.assert_not_called()

    def test_connection_failure_is_sanitized(self):
        conn=MagicMock(side_effect=RuntimeError("password=TOP_SECRET"))
        with self.assertRaises(AuditDenied) as cm:
            audit(conn,"postgresql://example.invalid/db")
        self.assertEqual(cm.exception.stage,"connection")
        self.assertNotIn("TOP_SECRET",str(cm.exception))

    def test_identity_query_failure_sanitized(self):
        conn=fake()
        db=conn.return_value
        cursor=db.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect=RuntimeError("postgresql://secret")
        with self.assertRaises(AuditDenied) as cm:
            audit(conn,"postgresql://example.invalid/db")
        self.assertEqual(cm.exception.stage,"identity-query")
        self.assertNotIn("secret",str(cm.exception))

    def test_privilege_query_failure_sanitized(self):
        conn=fake()
        cursor=conn.return_value.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect=[None,None,RuntimeError("password=SECRET")]
        with self.assertRaises(AuditDenied) as cm:
            audit(conn,"postgresql://example.invalid/db")
        self.assertEqual(cm.exception.stage,"privilege-query-database-create")


    def test_privilege_checks_use_catalog_oid_without_schema_usage(self):
        conn=fake()
        self.assertTrue(audit(conn,"postgresql://example.invalid/db"))
        cursor=conn.return_value.cursor.return_value.__enter__.return_value
        queries=[call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(len(queries),11)
        for query in queries[4:]:
            self.assertIn("pg_catalog.pg_class", query) if (
                "table" in query or "column" in query
            ) else None
        self.assertIn("pg_catalog.pg_proc", queries[-1])
        self.assertTrue(all("'dev_agent_control.consumed_permit'" not in q for q in queries))
        self.assertTrue(all("::regprocedure" not in q for q in queries))

    def test_missing_catalog_object_denied_closed(self):
        conn=fake()
        cursor=conn.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[
            ("dev_agent_control_db","dev_agent_permit_verifier_safe"),GOOD,
            (False,),(False,),(None,)
        ]
        with self.assertRaises(AuditDenied) as cm:
            audit(conn,"postgresql://example.invalid/db")
        self.assertEqual(cm.exception.stage,"privilege-policy-table-insert")

if __name__=="__main__":
    unittest.main()

