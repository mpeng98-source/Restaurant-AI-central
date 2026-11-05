"""CI-only recovery proof on synthetic data; not staging recovery certification."""
import os
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
assert os.environ.get('TEST_FIXTURE_DATABASE_URL') and os.environ.get('TEST_DATABASE_URL')
original=create_engine(os.environ['TEST_FIXTURE_DATABASE_URL'])
restored=create_engine(make_url(os.environ['TEST_FIXTURE_DATABASE_URL']).set(database='chubby_restore'))
for table in ['stock_movements','audit_logs','inventory_opening_requests','inventory_opening_decisions','inventory_evidence']:
    with original.connect() as a,restored.connect() as b:
        sql=text(f"SELECT count(*),md5(coalesce(string_agg(to_jsonb(t)::text,'|' ORDER BY id),'')) FROM {table} t")
        assert a.execute(sql).one()==b.execute(sql).one(),table
        assert b.execute(text('SELECT relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner) FROM pg_class WHERE relname=:table'),{'table':table}).one()==(True,True,'chubby_migrator')
app=create_engine(make_url(os.environ['TEST_DATABASE_URL']).set(database='chubby_restore'))
with app.begin() as c:
    assert c.execute(text('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()==('chubby_app',False,False)
    assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0005_inventory_pilot'
    assert c.execute(text('SELECT count(*) FROM stock_movements')).scalar_one()==0
    assert c.execute(text('SELECT count(*) FROM inventory_evidence')).scalar_one()==0
for engine in [original,restored,app]:engine.dispose()
print('Isolated CI PostgreSQL backup/restore verified: identical ledger/audit/evidence metadata, restricted ownership, forced RLS and fail-closed context. Private evidence-volume restore requires separate staging rehearsal.')
