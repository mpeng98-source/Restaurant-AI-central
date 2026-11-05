"""Synthetic pilot rehearsals. This is not the approved Burbank operational catalog."""
import base64
import io
import json
import os
from pathlib import Path
import sys
from PIL import Image
from sqlalchemy import create_engine, text
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from conftest import make_test_actors
from test_inventory_postgres import make_inventory_fixture
assert os.environ.get('TEST_DATABASE_URL') and os.environ.get('TEST_FIXTURE_DATABASE_URL')
cases=[]
image=Image.new('RGB',(48,64),(130,90,20));data=io.BytesIO();image.save(data,format='PNG')
for name,width,height in [('portrait opening and protected photo',768,1024),('landscape opening and protected photo',1024,768)]:
    actors=make_test_actors();inventory=make_inventory_fixture(actors)
    engine=create_engine(os.environ['TEST_FIXTURE_DATABASE_URL'])
    with engine.connect() as connection:
        record=connection.execute(text('SELECT sku,name FROM inventory_items WHERE id=:id'),{'id':inventory.item_a}).one()
    engine.dispose()
    cases.append({'name':name,'width':width,'height':height,'organization_id':str(actors.organization_id),'location_id':str(actors.location_a),
                  'item_id':str(inventory.item_a),'sku':record.sku,'item_name':record.name,'employee_email':actors.employee_email,
                  'gm_email':actors.gm_email,'owner_email':actors.owner_email,'gm_id':str(actors.gm_id),'password':actors.password,
                  'photo_base64':base64.b64encode(data.getvalue()).decode()})
path=Path(os.environ['BROWSER_PILOT_FIXTURES_FILE']);path.write_text(json.dumps(cases));path.chmod(0o600)
print('Seeded two synthetic opening/photo pilot scenarios. No approved operational catalog has been imported.')
