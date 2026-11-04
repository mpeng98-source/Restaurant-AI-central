"""Ephemeral PostgreSQL acceptance for catalog-OID checks with no schema USAGE.

Never connects to Neon. The environment URL is a disposable CI database.
"""
import os
from pathlib import Path
import unittest

import psycopg
from dev_agent_neon_verifier_readonly import audit

URL = os.environ.get("DEV_AGENT_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(URL, "disposable PostgreSQL is required")
class RestrictedCatalogPrivilegeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS dev_agent_control")
            conn.execute((ROOT / "ops/dev-agent-control-schema.sql").read_text())
            conn.execute((ROOT / "ops/dev-agent-permit-ledger-draft.sql").read_text())
            conn.execute((ROOT / "ops/dev-agent-consume-permit-function-review.sql").read_text())
            conn.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='neon_superuser') THEN
                    CREATE ROLE neon_superuser NOLOGIN;
                  END IF;
                END $$
            """)
            conn.execute("""
                CREATE ROLE dev_agent_permit_verifier_safe LOGIN
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
            """)

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL, autocommit=True) as conn:
            conn.execute("DROP ROLE IF EXISTS dev_agent_permit_verifier_safe")
            conn.execute("DROP FUNCTION IF EXISTS dev_agent_control.consume_verified_permit(text,bigint,bigint,text,text)")
            conn.execute("DROP TABLE IF EXISTS dev_agent_control.consumed_permit")
            conn.execute("DROP ROLE IF EXISTS neon_superuser")

    def test_no_schema_usage_still_checks_catalog_privileges(self):
        def connect_as_restricted(url, connect_timeout=8):
            conn=psycopg.connect(url,connect_timeout=connect_timeout)
            conn.execute("SET ROLE dev_agent_permit_verifier_safe")
            return conn

        with psycopg.connect(URL) as conn:
            self.assertFalse(conn.execute(
                "SELECT has_schema_privilege('dev_agent_permit_verifier_safe','dev_agent_control','USAGE')"
            ).fetchone()[0])
        self.assertTrue(audit(connect_as_restricted,URL))


if __name__ == "__main__":
    unittest.main()
