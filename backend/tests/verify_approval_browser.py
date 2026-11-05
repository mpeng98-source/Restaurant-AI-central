"""Verify browser decisions against the actual restricted-role ledger."""
import json
import os
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine, text

assert os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is mandatory'
fixtures = json.loads(Path(os.environ.get('BROWSER_FIXTURES_FILE', '../test-results/browser-fixtures.json')).read_text())
report = json.loads(Path(os.environ.get('BROWSER_REPORT_FILE', '../test-results/browser-report.json')).read_text())
assert report['failed'] == 0 and report['passed'] == len(fixtures) and report['skipped'] == 0
engine = create_engine(os.environ['TEST_DATABASE_URL'])
for case in fixtures:
    with engine.begin() as connection:
        assert connection.execute(text("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one() == ('chubby_app',False,False)
        for key, value in {'app.organization_id':case['organization_id'], 'app.location_ids':case['location_id'],
                           'app.user_id':case['gm_id']}.items():
            connection.execute(text('SELECT set_config(:key,:value,true)'), {'key':key,'value':value})
        balance = connection.execute(text('SELECT sum(quantity_delta) FROM stock_movements WHERE inventory_item_id=:id'), {'id':case['item_id']}).scalar_one()
        assert balance == Decimal(case['expected_balance']), (case['name'], str(balance))
        counts = dict(connection.execute(text("SELECT movement_type,count(*) FROM stock_movements WHERE inventory_item_id=:id AND movement_type IN ('count_adjustment','reversal') GROUP BY movement_type"), {'id':case['item_id']}).all())
        assert counts.get('count_adjustment',0) == (0 if case['action']=='rejected' else 1)
        assert counts.get('reversal',0) == (1 if case['action']=='reversed' else 0)
        decision = connection.execute(text('SELECT action FROM inventory_count_decisions WHERE organization_id=:org'), {'org':case['organization_id']}).scalar_one()
        assert decision == ('rejected' if case['action']=='rejected' else 'approved')
        if case['action'] != 'rejected':
            delta = connection.execute(text("SELECT quantity_delta FROM stock_movements WHERE inventory_item_id=:id AND movement_type='count_adjustment'"), {'id':case['item_id']}).scalar_one()
            assert delta == Decimal('-25'), 'original -25 adjustment must remain immutable after any reversal'
        print(f"Browser SQL verification passed: {case['name']}, ledger balance={balance}")
engine.dispose()
