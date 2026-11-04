"""Read-only control-plane readiness audit. No credentials or raw rows logged."""
import argparse
import os
import sys

from dev_agent_cost_evidence import project, require_idle

OWNER="dev_agent_accounting_owner_v27"
FUNCTIONS={"dev_agent_cost_writer_v27":"ingest_cost","dev_agent_reserver_v27":"reserve_task",
           "dev_agent_verifier_v27":"authorize_task","dev_agent_settler_v27":"finalize_run",
           "dev_agent_failure_v27":"mark_failed","dev_agent_auditor_v27":"rollout_status"}


def audit(conn,project_id,*,expected_database="dev_agent_control_db",allow_disabled=False):
    project(project_id);require_idle(conn)
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        if conn.execute("SELECT current_database(),current_user").fetchone()!=(expected_database,"dev_agent_auditor_v27"):
            raise ValueError("audit identity")
        roles=conn.execute("""SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls
             FROM pg_catalog.pg_roles WHERE rolname=ANY(%s)""",([OWNER,*FUNCTIONS],)).fetchall()
        if len(roles)!=7:raise ValueError("missing roles")
        for name,login,superuser,createdb,createrole,inherit,bypass in roles:
            if (login,superuser,createdb,createrole,inherit,bypass)!=(name!=OWNER,False,False,False,False,False):
                raise ValueError("unsafe role attributes")
            if conn.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='neon_superuser')").fetchone()[0]:
                if conn.execute("SELECT pg_has_role(%s,'neon_superuser','MEMBER')",(name,)).fetchone()[0]:
                    raise ValueError("inherited admin")
        funcs=conn.execute("""SELECT p.oid,p.proname,r.rolname,p.prosecdef,p.proconfig,
               EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                        WHERE a.grantee=0 AND a.privilege_type='EXECUTE')
              FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
             WHERE n.nspname='dev_agent_accounting'""").fetchall()
        expected_names=set(FUNCTIONS.values())|{"reserve_run","consume_permit"}
        if len(funcs)!=8 or {x[1] for x in funcs}!=expected_names:raise ValueError("unexpected functions")
        for oid,name,owner,definer,config,public in funcs:
            if owner!=OWNER or not definer or config!=['search_path=pg_catalog, pg_temp'] or public:
                raise ValueError("unsafe function boundary")
            for role,allowed in FUNCTIONS.items():
                if conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')",(role,oid)).fetchone()[0]!=(name==allowed):
                    raise ValueError("unexpected function privilege")
            grantees=conn.execute("""SELECT a.grantee FROM pg_proc p,
               LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
               WHERE p.oid=%s AND a.privilege_type='EXECUTE'
                 AND a.grantee<>p.proowner""",(oid,)).fetchall()
            expected=[role for role,allowed in FUNCTIONS.items() if allowed==name]
            expected_oids=conn.execute("SELECT oid FROM pg_roles WHERE rolname=ANY(%s)",(expected,)).fetchall()
            if set(grantees)!=set(expected_oids):raise ValueError("unreviewed function grantee")
        tables=conn.execute("""SELECT c.oid,r.rolname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                  JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='dev_agent_accounting' AND c.relkind='r'""").fetchall()
        if len(tables)!=5 or any(owner!=OWNER for _,owner in tables):raise ValueError("unexpected table owners")
        for role in FUNCTIONS:
            if conn.execute("SELECT has_database_privilege(%s,current_database(),'CREATE') OR has_schema_privilege(%s,'dev_agent_accounting','CREATE')",(role,role)).fetchone()[0]:
                raise ValueError("unexpected create privilege")
            if conn.execute("SELECT pg_has_role(%s,%s,'MEMBER')",(role,OWNER)).fetchone()[0]:raise ValueError("owner membership")
            for oid,_ in tables:
                if conn.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(%s,%s,'SELECT,INSERT,UPDATE,REFERENCES')",(role,oid,role,oid)).fetchone()[0]:
                    raise ValueError("direct table access")
        status=conn.execute("SELECT * FROM dev_agent_accounting.rollout_status(%s)",(project_id,)).fetchone()
        if status is None or status[1:]!=(0,0,0) or not (status[0] is True or allow_disabled):
            raise ValueError("unreconciled legacy or disabled project")
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--project-id",required=True);args=parser.parse_args()
    try:
        import psycopg
        with psycopg.connect(os.environ['DEV_AGENT_AUDIT_DATABASE_URL'],autocommit=True,connect_timeout=8) as conn:
            audit(conn,args.project_id)
    except Exception:
        print("Control-plane readiness denied",file=sys.stderr);return 2
    print("Control-plane read-only readiness passed");return 0


if __name__=="__main__":raise SystemExit(main())
