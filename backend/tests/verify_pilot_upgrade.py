"""Prove 0004 records survive 0005 and prior financial contracts still execute."""
import json
import os
from decimal import Decimal
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,text
from test_inventory_postgres import set_scope
case=json.loads(Path('../test-results/pilot-upgrade-fixture.json').read_text());r=case['report']
engine=create_engine(os.environ['TEST_DATABASE_URL'])
with engine.begin() as c:
    assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0005_inventory_pilot'
    assert c.execute(text('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()==('chubby_app',False,False)
    set_scope(c,case['org'],[case['loc']],case['gm'])
    assert c.execute(text("SELECT md5(string_agg(to_jsonb(m)::text,'|' ORDER BY id)) FROM stock_movements m")).scalar_one()==case['ledger_hash']
    assert c.execute(text('SELECT inventory_report_digest(:id)'),{'id':r['id']}).scalar_one()==r['snapshot_hash']
    params={'org':case['org'],'loc':case['loc'],'report':r['id'],'v':r['version'],'hash':r['snapshot_hash'],'key':str(uuid.uuid4()),'lines':json.dumps([{'line_id':line['id'],'verdict':'accepted'} for line in r['lines']])}
    statement=text("SELECT inventory_decide_count(:org,:loc,:report,:v,:hash,'approved','Upgrade rehearsal independent review',:key,CAST(:lines AS jsonb))")
    decision=c.execute(statement,params).scalar_one();assert c.execute(statement,params).scalar_one()==decision
    assert c.execute(text('SELECT sum(quantity_delta) FROM stock_movements')).scalar_one()==Decimal('315')
    assert c.execute(text("SELECT count(*) FROM stock_movements WHERE movement_type='count_adjustment'")).scalar_one()==1
    assert c.execute(text("SELECT quantity_delta FROM stock_movements WHERE movement_type='count_adjustment'")).scalar_one()==Decimal('-25')
engine.dispose()
print('0004 -> 0005 upgrade verified: historical ledger and frozen digest unchanged; independent approval -25 exactly once; final balance 315')
