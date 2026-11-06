"""Read-only extension audit; no table reads or additional auditor privileges."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from dev_agent_execution_gate import service_identity
from dev_agent_rollout import OWNER, FUNCTIONS


def audit_exception(conn):
    service_identity(conn,'dev_agent_auditor_v27')
    with conn.transaction():
        conn.execute('SET TRANSACTION READ ONLY')
        schema=conn.execute("SELECT n.oid,r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='dev_agent_canary_exception'").fetchone()
        if schema is None or schema[1]!=OWNER:raise ValueError('exception schema owner')
        funcs=conn.execute("SELECT p.oid,p.proname,r.rolname,p.prosecdef,p.proconfig FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.pronamespace=%s",(schema[0],)).fetchall()
        if len(funcs)!=1 or funcs[0][1:]!=('consume',OWNER,True,['search_path=pg_catalog, pg_temp']):
            raise ValueError('exception function boundary')
        grants=conn.execute("SELECT a.grantee,a.is_grantable FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid=%s AND a.privilege_type='EXECUTE' AND a.grantee<>p.proowner",(funcs[0][0],)).fetchall()
        expected=conn.execute("SELECT oid,false FROM pg_roles WHERE rolname='dev_agent_verifier_v27'").fetchall()
        if grants!=expected:raise ValueError('exception function grantee')
        tables=conn.execute("SELECT c.oid,c.relname,r.rolname FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE c.relnamespace=%s AND c.relkind='r'",(schema[0],)).fetchall()
        if len(tables)!=2 or {r[1] for r in tables}!={'policy','claim'} or any(r[2]!=OWNER for r in tables):
            raise ValueError('exception tables')
        # Inspect actual ACLs for every grantee, including PUBLIC and unrelated
        # roles. Effective service-role checks alone miss dormant/delegable grants.
        unexpected=conn.execute("SELECT 1 FROM pg_namespace n,LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a WHERE n.oid=%s AND a.grantee<>n.nspowner AND (a.grantee<>%s OR a.privilege_type<>'USAGE' OR a.is_grantable)",(schema[0],expected[0][0])).fetchone()
        if unexpected:raise ValueError('exception schema ACL')
        for oid,_,_ in tables:
            unexpected=conn.execute("SELECT 1 FROM pg_class c,LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=%s AND a.grantee<>c.relowner UNION ALL SELECT 1 FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid,LATERAL aclexplode(t.attacl) a WHERE c.oid=%s AND a.grantee<>c.relowner",(oid,oid)).fetchone()
            if unexpected:raise ValueError('exception table or column ACL')
        for role in FUNCTIONS:
            if conn.execute("SELECT has_schema_privilege(%s,%s,'CREATE')",(role,schema[0])).fetchone()[0]:
                raise ValueError('exception schema write')
            for oid,_,_ in tables:
                if conn.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(%s,%s,'SELECT,INSERT,UPDATE,REFERENCES')",(role,oid,role,oid)).fetchone()[0]:
                    raise ValueError('exception direct table access')
    return True


if __name__=='__main__':
    import psycopg
    try:
        with psycopg.connect(os.environ['DEV_AGENT_AUDIT_DATABASE_URL'],autocommit=True,connect_timeout=8) as conn:
            audit_exception(conn)
    except Exception:
        print('Exception boundary audit denied',file=sys.stderr);sys.exit(2)
    print('Exception boundary audit passed; no prior-cost assumption')
