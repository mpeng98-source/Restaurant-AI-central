"""Execute the real authenticated CLI against CI's actual API and PostgreSQL.

Passwords travel only through a subprocess stdin pipe, never arguments or logs.
All input/output reports remain ignored and outside the artifact whitelist.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import uuid
from decimal import Decimal
from sqlalchemy import create_engine,text

fixture=json.loads(Path(os.environ['BROWSER_PILOT_FIXTURES_FILE']).read_text())[0]
root=Path('../test-results/cli-private');root.mkdir(mode=0o700,exist_ok=True)
script=Path('tools/inventory_pilot.py').resolve()


def execute(name,action,body=None):
    output=root/(name+'-result.json')
    command=[sys.executable,str(script),'--base-url','http://localhost:8000','--allow-loopback-http',
             '--email',fixture['gm_email'],'--location',fixture['location_id'],'--action',action,'--output',str(output)]
    if body is not None:
        source=root/(name+'-input.json');source.write_text(json.dumps(body));source.chmod(0o600)
        command+=['--input',str(source)]
    result=subprocess.run(command,input=fixture['password']+'\n',capture_output=True,text=True,timeout=45)
    if result.returncode:
        # Never dump the completed process/input or unsanitized captured output.
        raise AssertionError('CLI command failed: '+name+'; '+result.stderr.replace(fixture['password'],'[redacted]')[-1000:])
    assert stat.S_IMODE(output.stat().st_mode)==0o600
    return json.loads(output.read_text())


row={'sku':'SAMPLE-CLI-EXTRA','name':'CI CLI sample item, not operational data','category':'CLI sample dry goods',
     'zone_code':'CLI-DRY','zone_name':'CLI sample dry store','base_unit_code':'g','purchase_unit_code':'kg',
     'pack_to_stock_factor':'1000','vendor_code':'CLI-VENDOR','vendor_name':'CLI sample vendor','vendor_sku':'CLI-1KG','unit_price':'4.2500','currency_code':'USD'}
preview=execute('catalog-preview','catalog-preview',{'rows':[row]})
body={'rows':[row],'preview_digest':preview['preview_digest'],'idempotency_key':str(uuid.uuid4()),'confirmed':True,'approval_reference':'CI SYNTHETIC CLI source review'}
imported=execute('catalog-import','catalog-import',body)
assert execute('catalog-replay','catalog-import',body)==imported
assert imported['posted_movements']==0 and len(imported['created'])==1
item=imported['created'][0]['inventory_item_id']
opening={'reason':'CI SYNTHETIC explicit zero baseline proposal','lines':[{'inventory_item_id':item,'quantity':'0','unit_code':'g'}]}
p=execute('opening-preview','opening-preview',opening)
submitted=execute('opening-import','opening-import',{**opening,'preview_digest':p['preview_digest'],'idempotency_key':str(uuid.uuid4()),'confirmed':True})
assert submitted['posted_movements']==0 and len(submitted['request_ids'])==1
requests=execute('opening-list','openings')
assert any(r['inventory_item_id']==item and r['action'] is None for r in requests)
manual={'manual_sheet_sha256':hashlib.sha256(b'CI SYNTHETIC manual sheet 315g').hexdigest(),'signed_by':'CI synthetic CLI reviewer',
        'idempotency_key':str(uuid.uuid4()),'lines':[{'sku':fixture['sku'],'quantity':'315','unit_code':'g'}]}
reconciled=execute('manual-reconciliation','reconciliation',manual)
assert reconciled['posted_movements']==0 and reconciled['lines'][0]['status']=='matched'
engine=create_engine(os.environ['TEST_DATABASE_URL'])
with engine.begin() as c:
    for key,value in {'app.organization_id':fixture['organization_id'],'app.location_ids':fixture['location_id'],'app.user_id':fixture['gm_id']}.items():
        c.execute(text('SELECT set_config(:key,:value,true)'),{'key':key,'value':value})
    assert c.execute(text('SELECT current_user')).scalar_one()=='chubby_app'
    assert c.execute(text('SELECT count(*) FROM stock_movements WHERE inventory_item_id=:id'),{'id':item}).scalar_one()==0
    assert c.execute(text('SELECT sum(quantity_delta) FROM stock_movements WHERE inventory_item_id=:id'),{'id':fixture['item_id']}).scalar_one()==Decimal('315')
engine.dispose()
print('CLI acceptance passed: 7 authenticated API commands, create-only catalog replay, bulk zero proposal without posting, scoped manual reconciliation, mode-0600 reports and logout; original ledger remains 315')
