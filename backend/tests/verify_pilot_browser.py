"""Assert browser pilot outcomes using chubby_app and real PostgreSQL, not mocks."""
import json
import os
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine,text
fixtures=json.loads(Path(os.environ['BROWSER_PILOT_FIXTURES_FILE']).read_text())
report=json.loads(Path(os.environ['BROWSER_PILOT_REPORT_FILE']).read_text())
assert report['failed']==report['skipped']==0 and report['passed']==len(fixtures)
engine=create_engine(os.environ['TEST_DATABASE_URL'])
for case in fixtures:
    with engine.begin() as c:
        assert c.execute(text('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()==('chubby_app',False,False)
        for k,v in {'app.organization_id':case['organization_id'],'app.location_ids':case['location_id'],'app.user_id':case['gm_id']}.items():
            c.execute(text('SELECT set_config(:k,:v,true)'),{'k':k,'v':v})
        rows=c.execute(text('SELECT movement_type,quantity_delta FROM stock_movements WHERE inventory_item_id=:id ORDER BY created_at'),{'id':case['item_id']}).all()
        assert rows==[('opening',Decimal('340')),('count_adjustment',Decimal('-25'))],rows
        assert sum(row[1] for row in rows)==Decimal('315')
        assert c.execute(text('SELECT count(*) FROM inventory_opening_requests')).scalar_one()==1
        assert c.execute(text("SELECT count(*) FROM inventory_evidence WHERE legal_hold AND scanner_status='sanitized_only'")).scalar_one()==1
        assert c.execute(text('SELECT count(*) FROM inventory_count_lines WHERE photo_object_key IS NOT NULL')).scalar_one()==1
        print(f"Pilot SQL verification passed: {case['name']}; independently approved 340 opening -> 315 count -> -25 adjustment -> 315 ledger; protected evidence linked")
engine.dispose()
