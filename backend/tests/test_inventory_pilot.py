"""Actual restricted-role PostgreSQL acceptance for pilot operations and photos."""
import hashlib
import asyncio

import httpx
import io
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.main import app
from app.config import settings
from conftest import make_test_actors
from test_inventory_postgres import inventory_fixture, app_connection, set_scope
from test_inventory_counting import login, create, item, save, path, ledger, snapshot

APP_URL=os.getenv('TEST_DATABASE_URL')
ADMIN_URL=os.getenv('TEST_FIXTURE_DATABASE_URL')
pytestmark=[pytest.mark.postgres,pytest.mark.skipif(not APP_URL or not ADMIN_URL,reason='Real PostgreSQL is required for pilot security tests')]


@pytest.fixture
def test_actors():
    return make_test_actors()


def base(a):
    return f'/api/v1/inventory/locations/{a.location_a}'


def proposal(client,a,f,h,**extra):
    body={'inventory_item_id':str(f.item_a),'quantity':'0.5','unit_code':'kg','reason':'Signed opening sheet verified by GM',
          'idempotency_key':str(uuid.uuid4()),'confirmed':True,**extra}
    response=client.post(base(a)+'/openings',headers=h,json=body)
    return response,body


def opening_decide(client,a,r,h,**extra):
    body={'action':'approved','reason':'Independent item, units and physical sheet review','idempotency_key':str(uuid.uuid4()),'confirmed':True,**extra}
    return client.post(base(a)+f"/openings/{r['id']}/decision",headers=h,json=body),body


def scalar(a,sql,**values):
    engine=create_engine(APP_URL)
    with engine.begin() as c:
        set_scope(c,a.organization_id,[a.location_a],a.owner_id)
        result=c.execute(text(sql),values).scalar_one()
    engine.dispose();return result


def test_opening_requires_independent_confirmation_posts_once_and_audits(api_client,test_actors,inventory_fixture):
    a=test_actors;gm=login(api_client,a,'gm')
    response,body=proposal(api_client,a,inventory_fixture,gm)
    assert response.status_code==201,response.text
    r=response.json();assert Decimal(r['base_quantity'])==Decimal('500')
    assert scalar(a,'SELECT count(*) FROM stock_movements')==0
    assert api_client.post(base(a)+'/openings',headers=gm,json=body).json()['id']==r['id']
    own,_=opening_decide(api_client,a,r,gm);assert own.status_code==403
    owner=login(api_client,a,'owner');decision,payload=opening_decide(api_client,a,r,owner)
    assert decision.status_code==200,decision.text
    assert decision.json()['action']=='approved'
    assert scalar(a,'SELECT sum(quantity_delta) FROM stock_movements')==Decimal('500')
    assert scalar(a,"SELECT count(*) FROM audit_logs WHERE action IN ('inventory.opening.requested','inventory.opening.approved')")==2
    assert api_client.post(base(a)+f"/openings/{r['id']}/decision",headers=owner,json=payload).status_code==200
    assert scalar(a,'SELECT count(*) FROM stock_movements')==1
    changed={**payload,'reason':'Changed reason'}
    assert api_client.post(base(a)+f"/openings/{r['id']}/decision",headers=owner,json=changed).status_code==409
    assert proposal(api_client,a,inventory_fixture,owner)[0].status_code==409


@pytest.mark.parametrize('quantity',['0','0.000000'])
def test_explicit_zero_baseline_is_approved_without_zero_ledger_entry(api_client,test_actors,inventory_fixture,quantity):
    a=test_actors;gm=login(api_client,a,'gm')
    r,_=proposal(api_client,a,inventory_fixture,gm,quantity=quantity,unit_code='g');assert r.status_code==201
    owner=login(api_client,a,'owner');d,_=opening_decide(api_client,a,r.json(),owner);assert d.status_code==200,d.text
    assert scalar(a,'SELECT count(*) FROM stock_movements')==0
    employee=login(api_client,a,'employee');session,_=create(api_client,a,employee)
    saved=save(api_client,a,session,inventory_fixture,item(api_client,a,inventory_fixture)['sku'],employee,quantity='0');assert saved.status_code==200
    submitted=api_client.post(path(a,session['id'])+'/submit',headers=employee,json={'version':saved.json()['version']});assert submitted.status_code==200,submitted.text
    login(api_client,a,'gm');frozen=snapshot(api_client,a,session['id'])
    assert Decimal(frozen['expected_quantity'])==Decimal('0') and frozen['status']=='within_threshold'
    assert proposal(api_client,a,inventory_fixture,login(api_client,a,'gm'))[0].status_code==409


@pytest.mark.parametrize('field,value',[('quantity',0.5),('quantity','-1'),('quantity','0.0000001'),('unit_code','ml'),('confirmed',False),('reason',' ')])
def test_invalid_opening_never_posts(api_client,test_actors,inventory_fixture,field,value):
    a=test_actors;h=login(api_client,a,'gm')
    response,_=proposal(api_client,a,inventory_fixture,h,**{field:value})
    assert response.status_code in (409,422),response.text
    assert scalar(a,'SELECT count(*) FROM stock_movements')==0


def test_opening_rejection_and_ledger_conflict(api_client,test_actors,inventory_fixture):
    a=test_actors;gm=login(api_client,a,'gm');r,_=proposal(api_client,a,inventory_fixture,gm)
    owner=login(api_client,a,'owner');d,_=opening_decide(api_client,a,r.json(),owner,action='rejected');assert d.status_code==200,d.text
    assert scalar(a,'SELECT count(*) FROM stock_movements')==0
    fresh,_=proposal(api_client,a,inventory_fixture,owner);assert fresh.status_code==201
    ledger(a,inventory_fixture,[('receiving','25')])
    gm=login(api_client,a,'gm');conflict,_=opening_decide(api_client,a,fresh.json(),gm);assert conflict.status_code==409
    assert scalar(a,'SELECT sum(quantity_delta) FROM stock_movements')==Decimal('25')


def test_opening_stale_conversion_and_revoked_proposer_cannot_create_new_requests(api_client,test_actors,inventory_fixture):
    a=test_actors;gm=login(api_client,a,'gm');r,_=proposal(api_client,a,inventory_fixture,gm);cookies=dict(api_client.cookies)
    engine=create_engine(ADMIN_URL)
    with engine.begin() as c:
        c.execute(text("UPDATE inventory_items SET base_unit_code='kg' WHERE id=:id"),{'id':inventory_fixture.item_a})
    owner=login(api_client,a,'owner');response,_=opening_decide(api_client,a,r.json(),owner);assert response.status_code==409
    with engine.begin() as c:
        c.execute(text("UPDATE inventory_items SET base_unit_code='g' WHERE id=:id"),{'id':inventory_fixture.item_a})
        c.execute(text('UPDATE user_location_assignments SET active=false WHERE user_id=:id'),{'id':a.gm_id})
    response,_=opening_decide(api_client,a,r.json(),owner);assert response.status_code==200,response.text
    # An independently reviewed historical proposal survives creator revocation.
    # Revoked creator cannot create another proposal using their old session.
    assert api_client.post('/api/v1/auth/login',json={'email':a.gm_email,'password':a.password}).status_code==401
    with TestClient(app,base_url='https://testserver',cookies=cookies) as old_session:
        assert proposal(old_session,a,inventory_fixture,gm)[0].status_code==403
    engine.dispose()


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_opening_decisions_are_exactly_once(api_client,test_actors,inventory_fixture,same_key):
    a=test_actors;gm=login(api_client,a,'gm');r,_=proposal(api_client,a,inventory_fixture,gm)
    owner=login(api_client,a,'owner');cookie=dict(api_client.cookies);barrier=Barrier(2);key=str(uuid.uuid4())
    def post(index):
        with TestClient(app,base_url='https://testserver',cookies=cookie) as c:
            barrier.wait(timeout=10)
            return opening_decide(c,a,r.json(),owner,idempotency_key=key if same_key else f'{key}-{index}')[0].status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(post,[0,1]))==([200,200] if same_key else [200,409])
    assert scalar(a,'SELECT count(*) FROM stock_movements')==1


def test_opening_rls_permissions_and_immutable_history(api_client,test_actors,inventory_fixture,app_connection):
    a=test_actors;employee=login(api_client,a,'employee');assert proposal(api_client,a,inventory_fixture,employee)[0].status_code==403
    gm=login(api_client,a,'gm');r,_=proposal(api_client,a,inventory_fixture,gm);assert r.status_code==201
    assert proposal(api_client,a,inventory_fixture,gm,inventory_item_id=str(inventory_fixture.item_b))[0].status_code==409
    assert api_client.get(base(a).replace(str(a.location_a),str(a.location_b))+'/openings').status_code==403
    assert api_client.get(base(a).replace(str(a.location_a),str(a.other_location))+'/openings').status_code==403
    owner=login(api_client,a,'owner');d,_=opening_decide(api_client,a,r.json(),owner);assert d.status_code==200
    for org,locs in [(None,[]),(a.organization_id,[]),(a.other_organization,[a.other_location]),(a.organization_id,[a.location_b])]:
        set_scope(app_connection,org,locs,a.owner_id)
        assert app_connection.execute(text('SELECT count(*) FROM inventory_opening_requests')).scalar_one()==0
    set_scope(app_connection,a.organization_id,[a.location_a],a.employee_id)
    for statement in ["UPDATE inventory_items SET name='forged'", "UPDATE inventory_location_items SET active=false"]:
        # Restrictive policies filter unauthorized UPDATE rows rather than raise.
        assert app_connection.execute(text(statement)).rowcount==0
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            app_connection.execute(text("INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,actor_id) VALUES(:id,:org,:loc,:item,'opening',1,'g',:key,:actor)"),{'id':uuid.uuid4(),'org':a.organization_id,'loc':a.location_a,'item':inventory_fixture.item_a,'key':str(uuid.uuid4()),'actor':a.employee_id})


def catalog_row(sku='PILOT-FLOUR'):
    return {'sku':sku,'name':'Pilot sample flour — NOT approved operational data','category':'Dry goods','zone_code':'DRY','zone_name':'Dry store',
            'base_unit_code':'g','purchase_unit_code':'kg','pack_to_stock_factor':'1000','vendor_code':'SAMPLE','vendor_name':'Sample vendor',
            'vendor_sku':'FLOUR-1KG','unit_price':'4.2500','currency_code':'USD'}


def test_catalog_import_preview_atomicity_idempotency_and_manual_reconciliation(api_client,test_actors):
    a=test_actors;h=login(api_client,a,'gm');rows=[catalog_row()]
    preview=api_client.post(base(a)+'/catalog-import/preview',headers=h,json={'rows':rows});assert preview.status_code==200,preview.text
    payload={'rows':rows,'preview_digest':preview.json()['preview_digest'],'confirmed':True,'approval_reference':'TEST sample only','idempotency_key':str(uuid.uuid4())}
    posted=api_client.post(base(a)+'/catalog-import',headers=h,json=payload);assert posted.status_code==201,posted.text
    assert api_client.post(base(a)+'/catalog-import',headers=h,json=payload).json()==posted.json()
    assert scalar(a,'SELECT count(*) FROM stock_movements')==0
    assert scalar(a,'SELECT count(*) FROM inventory_vendor_items')==1
    item_id=posted.json()['created'][0]['inventory_item_id']
    opening=api_client.post(base(a)+'/openings',headers=h,json={'inventory_item_id':item_id,'quantity':'0.340','unit_code':'kg','reason':'Sample manual sheet','confirmed':True,'idempotency_key':str(uuid.uuid4())})
    assert opening.status_code==201,opening.text
    owner=login(api_client,a,'owner');d,_=opening_decide(api_client,a,opening.json(),owner);assert d.status_code==200,d.text
    manual={'manual_sheet_sha256':hashlib.sha256(b'SAMPLE signed sheet 340g').hexdigest(),'signed_by':'CI sample signer','idempotency_key':str(uuid.uuid4()),'lines':[{'sku':'PILOT-FLOUR','quantity':'0.340','unit_code':'kg'}]}
    result=api_client.post(base(a)+'/reconciliation',headers=owner,json=manual);assert result.status_code==200,result.text
    assert result.json()['lines'][0]['status']=='matched' and result.json()['posted_movements']==0
    assert api_client.post(base(a)+'/reconciliation',headers=owner,json=manual).json()==result.json()
    assert scalar(a,'SELECT count(*) FROM inventory_operations')==2
    assert scalar(a,'SELECT count(*) FROM stock_movements')==1


@pytest.mark.parametrize('alteration',['duplicate','physical_factor','unknown_unit','float','formula_sku','bad_digest'])
def test_catalog_bad_batches_never_partially_import(api_client,test_actors,alteration):
    a=test_actors;h=login(api_client,a,'gm');row=catalog_row();rows=[row]
    if alteration=='duplicate':rows.append(dict(row))
    if alteration=='physical_factor':row['pack_to_stock_factor']='999'
    if alteration=='unknown_unit':row['purchase_unit_code']='case'
    if alteration=='float':row['unit_price']=4.25
    if alteration=='formula_sku':row['sku']='=IMPORTDATA()'
    payload={'rows':rows}
    if alteration=='bad_digest':
        payload.update({'preview_digest':'0'*64,'confirmed':True,'approval_reference':'test','idempotency_key':str(uuid.uuid4())})
    response=api_client.post(base(a)+'/catalog-import'+('' if alteration=='bad_digest' else '/preview'),headers=h,json=payload)
    assert response.status_code in (409,422),response.text
    assert scalar(a,'SELECT count(*) FROM inventory_items')==0


def test_bulk_opening_validation_and_replay(api_client,test_actors,inventory_fixture):
    a=test_actors;h=login(api_client,a,'gm');body={'reason':'Approved sample opening sheet','lines':[{'inventory_item_id':str(inventory_fixture.item_a),'quantity':'340','unit_code':'g'}]}
    p=api_client.post(base(a)+'/opening-import/preview',headers=h,json=body);assert p.status_code==200,p.text
    payload={**body,'preview_digest':p.json()['preview_digest'],'idempotency_key':str(uuid.uuid4()),'confirmed':True}
    response=api_client.post(base(a)+'/opening-import',headers=h,json=payload);assert response.status_code==201,response.text
    assert api_client.post(base(a)+'/opening-import',headers=h,json=payload).json()==response.json()
    duplicate={**body,'lines':body['lines']*2}
    assert api_client.post(base(a)+'/opening-import/preview',headers=h,json=duplicate).status_code==422
    assert scalar(a,'SELECT count(*) FROM inventory_opening_requests')==1 and scalar(a,'SELECT count(*) FROM stock_movements')==0


@pytest.fixture
def photo_context(api_client,test_actors,inventory_fixture,tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'evidence_storage_dir',str(tmp_path/'objects'))
    monkeypatch.setattr(settings,'evidence_scanner_path',None)
    a=test_actors;h=login(api_client,a,'employee');session,_=create(api_client,a,h)
    return a,h,session,inventory_fixture


def image_bytes(fmt='PNG'):
    image=Image.new('RGB',(24,32),(130,90,20));out=io.BytesIO();image.save(out,format=fmt);return out.getvalue()


def upload(client,context,raw=None,mime='image/png',evidence_id=None):
    a,h,s,f=context
    return client.post(base(a)+f"/count-sessions/{s['id']}/evidence?evidence_id={evidence_id or uuid.uuid4()}",headers={**h,'Content-Type':mime},content=raw if raw is not None else image_bytes())


def test_private_photo_upload_signed_access_reference_and_audit(api_client,photo_context):
    a,h,s,f=photo_context;assert a.password not in repr(a)
    identifier=uuid.uuid4();raw=image_bytes()+b'<script>not preserved</script>'
    response=upload(api_client,photo_context,raw=raw,evidence_id=identifier);assert response.status_code==201,response.text
    row=response.json();assert row['scanner_status']=='sanitized_only'
    assert upload(api_client,photo_context,raw=raw,evidence_id=identifier).json()==row
    saved=save(api_client,a,s,f,item(api_client,a,f)['sku'],h,photo_object_key=row['object_key']);assert saved.status_code==200,saved.text
    grant=api_client.post(base(a)+f'/evidence/{identifier}/access',headers=h);assert grant.status_code==200,grant.text
    photo=api_client.get(grant.json()['path'],headers={'X-Evidence-Token':grant.json()['token']})
    assert photo.status_code==200 and photo.headers['cache-control']=='private, no-store'
    assert b'<script>' not in photo.content and photo.content.startswith(b'\xff\xd8\xff')
    assert not Image.open(io.BytesIO(photo.content)).getexif()
    object_path=os.path.join(settings.evidence_storage_dir,row['object_key'])
    assert os.stat(object_path).st_mode & 0o777==0o600
    assert hashlib.sha256(photo.content).hexdigest()==row['sha256']
    assert api_client.get(grant.json()['path']).status_code==403
    assert scalar(a,"SELECT count(*) FROM audit_logs WHERE action='inventory.evidence.viewed'")==1
    assert api_client.get(base(a)+'/evidence?state=active').status_code==403
    manager=login(api_client,a,'gm')
    assert api_client.get(grant.json()['path'],headers={'X-Evidence-Token':grant.json()['token']}).status_code==403
    new_grant=api_client.post(base(a)+f'/evidence/{identifier}/access',headers=manager);assert new_grant.status_code==200
    assert api_client.get(new_grant.json()['path'],headers={'X-Evidence-Token':new_grant.json()['token']}).status_code==200


@pytest.mark.parametrize('raw,mime,status',[(b'<svg onload="evil"/>','image/svg+xml',415),(b'<html/>','image/jpeg',415),(b'\x89PNG\r\n\x1a\nbroken','image/png',422),(b'x'*(5*1024*1024+1),'image/png',413)],ids=['svg','mime-mismatch','corrupt-png','oversize'])
def test_photo_rejects_unsafe_type_magic_corruption_and_size(api_client,photo_context,raw,mime,status):
    assert upload(api_client,photo_context,raw=raw,mime=mime).status_code==status
    assert scalar(photo_context[0],'SELECT count(*) FROM inventory_evidence')==0


def test_photo_csrf_cross_scope_forgery_and_retention_authority(api_client,photo_context):
    a,h,s,f=photo_context;identifier=uuid.uuid4();response=upload(api_client,photo_context,evidence_id=identifier);assert response.status_code==201
    endpoint=base(a)+f'/evidence/{identifier}'
    assert api_client.post(endpoint+'/access').status_code==403
    assert api_client.patch(endpoint+'/retention',headers=h,json={'legal_hold':True,'reason':'Employee forbidden'}).status_code==403
    assert api_client.get(endpoint.replace(str(a.location_a),str(a.location_b))).status_code==403
    assert api_client.get(endpoint.replace(str(a.location_a),str(a.other_location))).status_code==403
    forged=f'{a.organization_id}/{a.location_a}/{uuid.uuid4()}.jpg'
    assert save(api_client,a,s,f,item(api_client,a,f)['sku'],h,photo_object_key=forged).status_code==409
    manager=login(api_client,a,'gm')
    control=api_client.patch(endpoint+'/retention',headers=manager,json={'legal_hold':True,'reason':'Preserve disputed count'});assert control.status_code==200,control.text
    assert api_client.post(endpoint+'/delete',headers=manager,json={'reason':'premature delete'}).status_code==409
    earlier=datetime.now(timezone.utc)+timedelta(seconds=1)
    assert api_client.patch(endpoint+'/retention',headers=manager,json={'legal_hold':False,'retain_until':earlier.isoformat(),'reason':'Shorten forbidden'}).status_code==409


def test_expired_photo_tombstone_erasure_and_hold_are_enforced_in_postgres(api_client,photo_context,monkeypatch):
    a,h,s,f=photo_context;monkeypatch.setattr(settings,'evidence_retention_seconds',1)
    identifier=uuid.uuid4();response=upload(api_client,photo_context,evidence_id=identifier);assert response.status_code==201,response.text
    endpoint=base(a)+f'/evidence/{identifier}';object_path=os.path.join(settings.evidence_storage_dir,response.json()['object_key'])
    manager=login(api_client,a,'gm')
    assert api_client.patch(endpoint+'/retention',headers=manager,json={'legal_hold':True,'reason':'Hold during review'}).status_code==200
    time.sleep(1.1) # Actual PostgreSQL wall-clock expiration; no mocked database clock.
    assert api_client.post(endpoint+'/access',headers=manager).status_code==200
    assert api_client.post(endpoint+'/delete',headers=manager,json={'reason':'Held object'}).status_code==409
    assert api_client.patch(endpoint+'/retention',headers=manager,json={'legal_hold':False,'reason':'Review complete'}).status_code==200
    assert api_client.post(endpoint+'/access',headers=manager).status_code==410
    expired=api_client.get(base(a)+'/evidence?state=expired').json()
    assert [row['id'] for row in expired]==[str(identifier)]
    assert api_client.post(endpoint+'/delete',headers=manager,json={'reason':'Expired retention policy'}).status_code==200
    assert not os.path.exists(object_path)
    assert api_client.get(base(a)+'/evidence?state=deleted').json()[0]['id']==str(identifier)
    assert api_client.post(endpoint+'/delete',headers=manager,json={'reason':'Retry erasure'}).status_code==200
    assert api_client.patch(endpoint+'/retention',headers=manager,json={'legal_hold':True,'reason':'Cannot resurrect'}).status_code==403
    assert scalar(a,'SELECT count(*) FROM inventory_evidence WHERE deleted_at IS NOT NULL')==1


def test_photo_scanner_failure_is_closed_and_leaves_no_object(api_client,photo_context,monkeypatch):
    monkeypatch.setattr(settings,'evidence_scanner_path','/does/not/exist/clamscan')
    assert upload(api_client,photo_context).status_code==503
    assert scalar(photo_context[0],'SELECT count(*) FROM inventory_evidence')==0
    assert not list(__import__('pathlib').Path(settings.evidence_storage_dir).rglob('*.jpg'))


def test_internal_demo_without_scanner_rejects_photo_without_object(api_client,photo_context,monkeypatch):
    monkeypatch.setattr(settings,'environment','internal-demo')
    assert upload(api_client,photo_context).status_code==503
    assert scalar(photo_context[0],'SELECT count(*) FROM inventory_evidence')==0
    assert not list(__import__('pathlib').Path(settings.evidence_storage_dir).rglob('*.jpg'))


def test_photo_missing_tenant_location_and_other_employee_fail_closed(api_client,photo_context,app_connection):
    a,h,s,f=photo_context;assert upload(api_client,photo_context).status_code==201
    for org,locs,user in [(None,[],a.employee_id),(a.organization_id,[],a.employee_id),(a.organization_id,[a.location_b],a.employee_id),(a.other_organization,[a.other_location],a.employee_id)]:
        set_scope(app_connection,org,locs,user)
        assert app_connection.execute(text('SELECT count(*) FROM inventory_evidence')).scalar_one()==0
    other=make_test_actors()
    engine=create_engine(ADMIN_URL)
    with engine.begin() as c:
        c.execute(text('INSERT INTO user_location_assignments(id,user_id,organization_id,location_id,role_id,active) SELECT :id,:other,organization_id,location_id,role_id,true FROM user_location_assignments WHERE user_id=:employee AND location_id=:loc'),
                  {'id':uuid.uuid4(),'other':other.employee_id,'employee':a.employee_id,'loc':a.location_a})
    engine.dispose()
    set_scope(app_connection,a.organization_id,[a.location_a],other.employee_id)
    assert app_connection.execute(text('SELECT count(*) FROM inventory_evidence')).scalar_one()==0


def test_protected_photo_session_expiration_logout_and_modified_bytes(api_client,photo_context):
    a,h,s,f=photo_context;response=upload(api_client,photo_context);assert response.status_code==201
    row=response.json();endpoint=base(a)+f"/evidence/{row['id']}";grant=api_client.post(endpoint+'/access',headers=h).json()
    assert api_client.get(grant['path'],headers={'X-Evidence-Token':'1.'+grant['token'].split('.')[1]}).status_code==403
    object_path=os.path.join(settings.evidence_storage_dir,row['object_key'])
    with open(object_path,'wb') as dest:dest.write(b'tampered')
    assert api_client.get(grant['path'],headers={'X-Evidence-Token':grant['token']}).status_code==503
    logout=api_client.post('/api/v1/auth/logout',headers=h);assert logout.status_code in (200,204)
    assert api_client.get(grant['path'],headers={'X-Evidence-Token':grant['token']}).status_code==401


def test_photo_rate_limit_uses_real_redis(api_client,photo_context):
    a,h,s,f=photo_context
    rate_key=f'evidence-upload:{a.employee_id}:{a.location_a}'
    app.state.redis.set(rate_key,20,ex=60)
    try:
        assert upload(api_client,photo_context).status_code==429
        assert scalar(a,'SELECT count(*) FROM inventory_evidence')==0
    finally:
        app.state.redis.delete(rate_key)


def test_pilot_migration_installed_forced_rls_and_no_elevated_functions(app_connection):
    assert app_connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0005_inventory_pilot'
    tables=['inventory_opening_requests','inventory_opening_decisions','inventory_operations','inventory_evidence']
    for table in tables:
        row=app_connection.execute(text('SELECT relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner) FROM pg_class WHERE relname=:name'),{'name':table}).one()
        assert row==(True,True,'chubby_migrator')
    assert app_connection.execute(text("SELECT count(*) FROM pg_proc WHERE proname LIKE 'inventory_%' AND prosecdef")).scalar_one()==0


def test_oversized_json_is_rejected_before_catalog_parsing(api_client,test_actors):
    a=test_actors;h=login(api_client,a,'gm')
    response=api_client.post(base(a)+'/catalog-import/preview',headers={**h,'Content-Type':'application/json'},content=b' '*(256001))
    assert response.status_code==413


def test_employee_cannot_import_or_reconcile_and_reviewer_csrf_is_required(api_client,test_actors):
    a=test_actors;h=login(api_client,a,'employee')
    assert api_client.post(base(a)+'/catalog-import/preview',headers=h,json={'rows':[catalog_row()]}).status_code==403
    gm=login(api_client,a,'gm')
    assert api_client.post(base(a)+'/catalog-import/preview',json={'rows':[catalog_row()]}).status_code==403
    # Real manual mismatches remain proposals, never mutate stock.
    assert api_client.post(base(a)+'/catalog-import/preview',headers=gm,json={'rows':[catalog_row()]}).status_code==200


def test_concurrent_matching_photo_uploads_do_not_overwrite_or_block_event_loop(api_client,photo_context):
    a,h,s,f=photo_context;cookies=dict(api_client.cookies);identifier=uuid.uuid4();raw=image_bytes()
    async def requests_on_one_loop():
        # One fixture-owned lifespan and one ASGI event loop model the real
        # service. ASGITransport executes the actual app, PostgreSQL and Redis;
        # it does not mock requests or start/stop application lifespans.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://testserver',cookies=cookies) as client:
            endpoint=base(a)+f"/count-sessions/{s['id']}/evidence?evidence_id={identifier}"
            responses=await asyncio.gather(*(client.post(endpoint,headers={**h,'Content-Type':'image/png'},content=raw) for _ in range(2)))
            for response in responses:
                assert response.status_code==201,response.text
            return [response.json()['sha256'] for response in responses]
    hashes=asyncio.run(requests_on_one_loop())
    assert hashes[0]==hashes[1] and scalar(a,'SELECT count(*) FROM inventory_evidence')==1


def test_owner_opening_at_another_organization_location_can_be_reviewed_by_assigned_gm(api_client,test_actors,inventory_fixture):
    a=test_actors;engine=create_engine(ADMIN_URL)
    with engine.begin() as c:
        c.execute(text('INSERT INTO user_location_assignments(id,user_id,organization_id,location_id,role_id,active) SELECT :id,user_id,organization_id,:loc,role_id,true FROM user_location_assignments WHERE user_id=:gm AND location_id=:original'),{'id':uuid.uuid4(),'loc':a.location_b,'gm':a.gm_id,'original':a.location_a})
    engine.dispose()
    owner=login(api_client,a,'owner')
    target=base(a).replace(str(a.location_a),str(a.location_b))
    payload={'inventory_item_id':str(inventory_fixture.item_a),'quantity':'340','unit_code':'g','reason':'Owner confirmed second-location sample opening','idempotency_key':str(uuid.uuid4()),'confirmed':True}
    response=api_client.post(target+'/openings',headers=owner,json=payload);assert response.status_code==201,response.text
    gm=login(api_client,a,'gm');decision=api_client.post(target+f"/openings/{response.json()['id']}/decision",headers=gm,json={'action':'approved','reason':'Authorized second-location independent review','idempotency_key':str(uuid.uuid4()),'confirmed':True})
    assert decision.status_code==200,decision.text


@pytest.mark.parametrize('target',['opening','ledger','conversion'])
def test_database_rejects_nonfinite_inventory_numbers(app_connection,test_actors,inventory_fixture,target):
    a=test_actors;set_scope(app_connection,a.organization_id,[a.location_a],a.owner_id)
    with pytest.raises(DBAPIError):
        with app_connection.begin_nested():
            if target=='opening':
                app_connection.execute(text("SELECT inventory_request_opening(:org,:loc,:item,'NaN'::numeric,'g','Nonfinite forbidden',:key)"),{'org':a.organization_id,'loc':a.location_a,'item':inventory_fixture.item_a,'key':str(uuid.uuid4())})
            elif target=='ledger':
                app_connection.execute(text("INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,actor_id) VALUES(:id,:org,:loc,:item,'receiving','NaN'::numeric,'g',:key,:actor)"),{'id':uuid.uuid4(),'org':a.organization_id,'loc':a.location_a,'item':inventory_fixture.item_a,'key':str(uuid.uuid4()),'actor':a.owner_id})
            else:
                app_connection.execute(text("INSERT INTO inventory_item_unit_conversions(id,organization_id,location_id,inventory_item_id,unit_code,factor_to_stock_unit) VALUES(:id,:org,:loc,:item,'ea','NaN'::numeric)"),{'id':uuid.uuid4(),'org':a.organization_id,'loc':a.location_a,'item':inventory_fixture.item_a})


def test_opening_history_mutation_guards_without_another_open_reader(api_client,test_actors,inventory_fixture):
    a=test_actors;gm=login(api_client,a,'gm');r,_=proposal(api_client,a,inventory_fixture,gm)
    owner=login(api_client,a,'owner');d,_=opening_decide(api_client,a,r.json(),owner);assert d.status_code==200
    engine=create_engine(ADMIN_URL)
    with engine.begin() as c:
        for table in ['inventory_opening_requests','inventory_opening_decisions','stock_movements','audit_logs']:
            for command in [f'DELETE FROM {table}',f'TRUNCATE {table} CASCADE']:
                with pytest.raises(DBAPIError) as denied:
                    with c.begin_nested():c.execute(text(command))
                assert denied.value.orig.sqlstate=='P0001', 'Mutation must be denied by the guard, not a lock timeout'
    engine.dispose()



def test_opening_nonterminating_physical_factor_stays_frozen_and_approvable(api_client,test_actors,inventory_fixture):
    a=test_actors;engine=create_engine(ADMIN_URL)
    with engine.begin() as c:c.execute(text("UPDATE inventory_items SET base_unit_code='oz' WHERE id=:id"),{'id':inventory_fixture.item_a})
    engine.dispose();gm=login(api_client,a,'gm')
    proposed,_=proposal(api_client,a,inventory_fixture,gm,quantity='0.5',unit_code='g');assert proposed.status_code==201,proposed.text
    assert Decimal(proposed.json()['base_quantity'])==Decimal('0.017637')
    owner=login(api_client,a,'owner');decision,_=opening_decide(api_client,a,proposed.json(),owner);assert decision.status_code==200,decision.text
    assert scalar(a,'SELECT sum(quantity_delta) FROM stock_movements')==Decimal('0.017637')


def test_opening_conversion_overflow_returns_validation_error(api_client,test_actors,inventory_fixture):
    a=test_actors;gm=login(api_client,a,'gm')
    response,_=proposal(api_client,a,inventory_fixture,gm,quantity='999999999999999999.999999',unit_code='kg')
    assert response.status_code==422,response.text
    assert scalar(a,'SELECT count(*) FROM stock_movements')==0


def test_inventory_guard_functions_ignore_spoofed_temporary_unit_tables(app_connection,test_actors,inventory_fixture):
    a=test_actors;set_scope(app_connection,a.organization_id,[a.location_a],a.owner_id)
    app_connection.execute(text('CREATE TEMP TABLE inventory_units(code text,dimension text,factor_to_base numeric) ON COMMIT DROP'))
    app_connection.execute(text("INSERT INTO pg_temp.inventory_units VALUES('g','mass',1),('kg','mass',123)"))
    assert app_connection.execute(text("SELECT factor_to_base FROM pg_temp.inventory_units WHERE code='kg'")).scalar_one()==123
    factor=app_connection.execute(text("SELECT public.inventory_opening_factor(:org,:loc,:item,'kg')"),{'org':a.organization_id,'loc':a.location_a,'item':inventory_fixture.item_a}).scalar_one()
    assert factor==Decimal('1000')
    config=app_connection.execute(text("SELECT proconfig FROM pg_proc WHERE oid='public.inventory_opening_factor(uuid,uuid,uuid,text)'::regprocedure")).scalar_one()
    assert 'search_path=pg_catalog, public, pg_temp' in config
