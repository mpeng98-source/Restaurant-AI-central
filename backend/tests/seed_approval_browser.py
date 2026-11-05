"""Ephemeral browser fixtures only. Never upload this script's credential output file."""
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import make_test_actors
from test_inventory_postgres import make_inventory_fixture
from test_inventory_counting import ledger

assert os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is required for browser acceptance'
assert os.environ.get('TEST_FIXTURE_DATABASE_URL'), 'TEST_FIXTURE_DATABASE_URL is required for browser fixtures'
cases = []
for name, width, height, action, counter, expected in (
    ('portrait approval', 768, 1024, 'approved', 'employee', '315'),
    ('landscape approval and reversal', 1024, 768, 'reversed', 'employee', '340'),
    ('landscape rejection', 1024, 768, 'rejected', 'employee', '340'),
    ('portrait four-eyes owner approval', 768, 1024, 'approved', 'gm', '315'),
):
    actors = make_test_actors()
    inventory = make_inventory_fixture(actors)
    ledger(actors, inventory, [('opening','500'), ('receiving','200'), ('production_out','-350'), ('waste','-10')])
    engine = create_engine(os.environ['TEST_FIXTURE_DATABASE_URL'])
    with engine.connect() as connection:
        record = connection.execute(text('SELECT sku,name FROM inventory_items WHERE id=:id'), {'id': inventory.item_a}).one()
    engine.dispose()
    cases.append({'name': name, 'width': width, 'height': height, 'action': action, 'counter': counter, 'expected_balance': expected,
                  'organization_id': str(actors.organization_id), 'location_id': str(actors.location_a), 'item_id': str(inventory.item_a),
                  'sku': record.sku, 'item_name': record.name, 'employee_email': actors.employee_email, 'gm_email': actors.gm_email,
                  'owner_email': actors.owner_email, 'gm_id': str(actors.gm_id), 'password': actors.password})
path = Path(os.environ.get('BROWSER_FIXTURES_FILE', '../test-results/browser-fixtures.json'))
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(cases))
path.chmod(0o600)
print(f'Seeded {len(cases)} isolated real-PostgreSQL browser scenarios; credentials are in an ignored ephemeral file')
