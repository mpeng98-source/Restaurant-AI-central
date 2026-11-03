"""Create an actual 0004 ledger and frozen count before applying 0005."""
import json
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from app.main import app
from conftest import make_test_actors
from test_inventory_postgres import make_inventory_fixture,set_scope
from test_inventory_counting import login,create,item,save,path
assert os.environ.get('TEST_DATABASE_URL') and os.environ.get('TEST_FIXTURE_DATABASE_URL')
a=make_test_actors();f=make_inventory_fixture(a)
engine=create_engine(os.environ['TEST_DATABASE_URL'])
with engine.begin() as c:
    assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0004_inventory_approvals'
    set_scope(c,a.organization_id,[a.location_a],a.owner_id)
    for kind,qty in [('opening','500'),('receiving','200'),('production_out','-350'),('waste','-10')]:
        c.execute(text("INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,actor_id) VALUES(:id,:org,:loc,:item,:kind,CAST(:qty AS numeric),'g',:key,:actor)"),{'id':uuid.uuid4(),'org':a.organization_id,'loc':a.location_a,'item':f.item_a,'kind':kind,'qty':qty,'key':str(uuid.uuid4()),'actor':a.owner_id})
with TestClient(app,base_url='https://testserver') as client:
    employee=login(client,a,'employee');session,_=create(client,a,employee)
    saved=save(client,a,session,f,item(client,a,f)['sku'],employee,quantity='315');assert saved.status_code==200,saved.text
    submitted=client.post(path(a,session['id'])+'/submit',headers=employee,json={'version':saved.json()['version']});assert submitted.status_code==200,submitted.text
    gm=login(client,a,'gm');reviewed=client.post(path(a,session['id'])+'/review',headers=gm,json={'version':submitted.json()['version']});assert reviewed.status_code==200,reviewed.text
    report=reviewed.json()
with engine.begin() as c:
    set_scope(c,a.organization_id,[a.location_a],a.gm_id)
    ledger_hash=c.execute(text("SELECT md5(string_agg(to_jsonb(m)::text,'|' ORDER BY id)) FROM stock_movements m")).scalar_one()
engine.dispose()
result={'org':str(a.organization_id),'loc':str(a.location_a),'gm':str(a.gm_id),'item':str(f.item_a),'report':report,'ledger_hash':ledger_hash}
p=Path('../test-results/pilot-upgrade-fixture.json');p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(result,default=str));p.chmod(0o600)
print('Prepared 0004 legacy opening ledger at 340 and frozen 315 count; no 0005 tables or functions used')
