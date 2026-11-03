"""Human-confirmed opening balances and read-only reconciliation; no AI posting."""
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.authorization import Principal, authenticated_principal, require_csrf
from app.db import get_db
from app.inventory_approvals import database_conflict
from app.inventory_units import normalize_stock_quantity
from app.inventory_counts import DecimalBody, scope

router = APIRouter(prefix='/api/v1/inventory/locations/{location_id}', tags=['inventory pilot'])


class OpeningBody(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    inventory_item_id: uuid.UUID
    quantity: Decimal = Field(ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)
    unit_code: str = Field(min_length=1, max_length=24)
    reason: str = Field(min_length=1, max_length=2000, pattern=r'\S')
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r'\S')
    confirmed: Literal[True]


class OpeningDecision(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    action: Literal['approved', 'rejected']
    reason: str = Field(min_length=1, max_length=2000, pattern=r'\S')
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r'\S')
    confirmed: Literal[True]


def opening_rows(db, location_id, request_id=None):
    rows = list(db.execute(text('''SELECT r.*,d.id AS decision_id,d.action,d.reason AS decision_reason,d.decided_by,d.audit_log_id
        FROM inventory_opening_requests r LEFT JOIN inventory_opening_decisions d ON d.request_id=r.id
        WHERE r.location_id=:loc AND (CAST(:id AS uuid) IS NULL OR r.id=CAST(:id AS uuid)) ORDER BY r.created_at DESC LIMIT 200'''),
        {'loc': location_id, 'id': request_id}).mappings())
    return [{key:str(value) if isinstance(value,Decimal) else value for key,value in row.items()} for row in rows]


@router.get('/openings')
def openings(location_id: uuid.UUID, principal: Principal = Depends(authenticated_principal), db: Session = Depends(get_db)):
    scope(db, principal, location_id, 'inventory:catalog:manage')
    return opening_rows(db, location_id)


@router.post('/openings', status_code=201)
def request_opening(location_id: uuid.UUID, body: OpeningBody, principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, _ = scope(db, principal, location_id, 'inventory:catalog:manage')
    try:
        request_id = db.scalar(text('SELECT inventory_request_opening(:org,:loc,:item,:qty,:unit,:reason,:key)'),
            {'org':grant.organization_id, 'loc':location_id, 'item':body.inventory_item_id, 'qty':body.quantity,
             'unit':body.unit_code, 'reason':body.reason, 'key':body.idempotency_key})
        result = opening_rows(db, location_id, request_id)[0]
        db.commit()
        return result
    except DBAPIError as exc:
        database_conflict(db, exc)


@router.post('/openings/{request_id}/decision')
def decide_opening(location_id: uuid.UUID, request_id: uuid.UUID, body: OpeningDecision,
                   principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, _ = scope(db, principal, location_id, 'inventory:approve')
    try:
        db.execute(text('SELECT inventory_decide_opening(:org,:loc,:id,:action,:reason,:key)'),
            {'org':grant.organization_id,'loc':location_id,'id':request_id,'action':body.action,'reason':body.reason,'key':body.idempotency_key})
        result = opening_rows(db, location_id, request_id)[0]
        db.commit()
        return result
    except DBAPIError as exc:
        database_conflict(db, exc)


class ManualLine(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    quantity: Decimal = Field(ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)
    unit_code: str = Field(min_length=1, max_length=24)


class ReconciliationBody(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    manual_sheet_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    signed_by: str = Field(min_length=1, max_length=180, pattern=r'\S')
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r'\S')
    lines: list[ManualLine] = Field(min_length=1, max_length=200)

    @field_validator('lines')
    @classmethod
    def unique_skus(cls, lines):
        if len({line.sku for line in lines}) != len(lines):
            raise ValueError('Each manual SKU must appear once')
        return lines


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def operation(db, grant, location_id, principal, kind, key, request_hash, payload=None):
    previous = db.execute(text('SELECT * FROM inventory_operations WHERE organization_id=:org AND location_id=:loc AND kind=:kind AND idempotency_key=:key'),
        {'org':grant.organization_id,'loc':location_id,'kind':kind,'key':key}).mappings().first()
    if previous:
        if previous['request_hash'] != request_hash or previous['actor_id'] != principal.user_id:
            raise HTTPException(409, 'Operational idempotency key reused')
        return previous['payload']
    if payload is not None:
        db.execute(text('INSERT INTO inventory_operations(id,organization_id,location_id,kind,idempotency_key,request_hash,payload,actor_id) VALUES(:id,:org,:loc,:kind,:key,:hash,CAST(:payload AS jsonb),:actor)'),
            {'id':uuid.uuid4(),'org':grant.organization_id,'loc':location_id,'kind':kind,'key':key,'hash':request_hash,'payload':json.dumps(payload),'actor':principal.user_id})
    return payload


def lock_location(db, org, loc):
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:org AS text)||':'||CAST(:loc AS text),0))"), {'org':str(org),'loc':str(loc)})


@router.post('/reconciliation')
def reconcile(location_id: uuid.UUID, body: ReconciliationBody, principal: Principal = Depends(require_csrf), db: Session = Depends(get_db)):
    grant, _ = scope(db, principal, location_id, 'inventory:catalog:manage')
    lock_location(db, grant.organization_id, location_id)
    fingerprint = digest(body.model_dump(mode='json'))
    old = operation(db, grant, location_id, principal, 'reconciliation', body.idempotency_key, fingerprint)
    if old:
        return old
    rows = []
    for line in body.lines:
        row = db.execute(text('''SELECT i.id,i.base_unit_code,inventory_opening_factor(i.organization_id,:loc,i.id,:unit) AS factor,
          EXISTS(SELECT 1 FROM stock_movements m WHERE m.organization_id=i.organization_id AND m.location_id=:loc AND m.inventory_item_id=i.id AND m.movement_type IN ('opening','count_adjustment'))
          OR EXISTS(SELECT 1 FROM inventory_opening_requests r JOIN inventory_opening_decisions d ON d.request_id=r.id WHERE r.organization_id=i.organization_id AND r.location_id=:loc AND r.inventory_item_id=i.id AND d.action='approved') AS baseline,
          (SELECT coalesce(sum(m.quantity_delta),0) FROM stock_movements m WHERE m.organization_id=i.organization_id AND m.location_id=:loc AND m.inventory_item_id=i.id) AS balance
          FROM inventory_items i JOIN inventory_location_items li ON li.organization_id=i.organization_id AND li.inventory_item_id=i.id
          WHERE i.organization_id=:org AND li.location_id=:loc AND li.active AND i.active AND i.sku=:sku'''),
            {'org':grant.organization_id,'loc':location_id,'sku':line.sku,'unit':line.unit_code}).mappings().first()
        if not row or row['factor'] is None:
            raise HTTPException(422, 'Manual sheet contains an unavailable SKU or incompatible unit')
        physical = normalized(line.quantity,row['factor'])
        rows.append({'sku':line.sku,'unit_code':row['base_unit_code'],'manual_quantity':str(physical),'input_quantity':str(line.quantity),'input_unit':line.unit_code,'factor':str(row['factor']),
                     'ledger_quantity':str(row['balance']) if row['baseline'] else None,
                     'difference':str(physical-row['balance']) if row['baseline'] else None,
                     'status':'baseline_required' if not row['baseline'] else ('matched' if physical==row['balance'] else 'discrepancy')})
    result = {'manual_sheet_sha256':body.manual_sheet_sha256,'signed_by':body.signed_by,'lines':rows,
              'reconciled_at':str(db.scalar(text('SELECT clock_timestamp()'))), 'posted_movements':0,
              'scope':'Provided manual sheet lines only; compare catalog coverage before pilot sign-off'}
    operation(db, grant, location_id, principal, 'reconciliation', body.idempotency_key, fingerprint, result)
    db.commit()
    return result


class OpeningImportLine(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    inventory_item_id: uuid.UUID
    quantity: Decimal = Field(ge=0,max_digits=24,decimal_places=6,allow_inf_nan=False)
    unit_code: str = Field(min_length=1,max_length=24)


class OpeningImport(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    lines: list[OpeningImportLine] = Field(min_length=1,max_length=200)
    reason: str = Field(min_length=1,max_length=2000,pattern=r'\S')

    @field_validator('lines')
    @classmethod
    def unique_items(cls, lines):
        if len({row.inventory_item_id for row in lines})!=len(lines):
            raise ValueError('Each opening item must appear once')
        return lines


class OpeningImportCommit(OpeningImport):
    preview_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    idempotency_key: uuid.UUID
    confirmed: Literal[True]


def normalized(quantity,factor):
    try:
        return normalize_stock_quantity(quantity,factor)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


def opening_import_preview(db, grant, loc, body):
    rows=[]
    for line in body.lines:
        row=db.execute(text('''SELECT i.id,i.sku,i.name,i.base_unit_code,inventory_opening_factor(i.organization_id,:loc,i.id,:unit) AS factor,
          EXISTS(SELECT 1 FROM stock_movements m WHERE m.organization_id=i.organization_id AND m.location_id=:loc AND m.inventory_item_id=i.id)
          OR EXISTS(SELECT 1 FROM inventory_opening_requests r JOIN inventory_opening_decisions d ON d.request_id=r.id WHERE r.organization_id=i.organization_id AND r.location_id=:loc AND r.inventory_item_id=i.id AND d.action='approved') AS initialized
          FROM inventory_items i WHERE i.organization_id=:org AND i.id=:item'''),
          {'org':grant.organization_id,'loc':loc,'item':line.inventory_item_id,'unit':line.unit_code}).mappings().first()
        if not row or row['factor'] is None or row['initialized']:
            raise HTTPException(409,'Opening import contains an unavailable, initialized or incompatible item')
        rows.append({'inventory_item_id':str(row['id']),'sku':row['sku'],'name':row['name'],'unit_code':line.unit_code,'quantity':str(line.quantity),
                     'base_unit_code':row['base_unit_code'],'factor':str(row['factor']), 'base_quantity':str(normalized(line.quantity,row['factor']))})
    return {'preview_digest':digest({'reason':body.reason,'lines':rows}),'lines':rows,'posts_stock':False,'requires_independent_approval':True}


@router.post('/opening-import/preview')
def opening_preview(location_id: uuid.UUID,body: OpeningImport,principal: Principal=Depends(require_csrf),db: Session=Depends(get_db)):
    grant,_=scope(db,principal,location_id,'inventory:catalog:manage')
    return opening_import_preview(db,grant,location_id,body)


@router.post('/opening-import',status_code=201)
def opening_import(location_id: uuid.UUID,body: OpeningImportCommit,principal: Principal=Depends(require_csrf),db: Session=Depends(get_db)):
    grant,_=scope(db,principal,location_id,'inventory:catalog:manage')
    lock_location(db,grant.organization_id,location_id)
    fingerprint=digest(body.model_dump(mode='json'))
    key=str(body.idempotency_key)
    old=operation(db,grant,location_id,principal,'opening_import',key,fingerprint)
    if old:
        return old
    if opening_import_preview(db,grant,location_id,body)['preview_digest']!=body.preview_digest:
        raise HTTPException(409,'Opening preview is stale or changed')
    try:
        ids=[]
        for line in body.lines:
            request_id=db.scalar(text('SELECT inventory_request_opening(:org,:loc,:item,:qty,:unit,:reason,:key)'),
                {'org':grant.organization_id,'loc':location_id,'item':line.inventory_item_id,'qty':line.quantity,'unit':line.unit_code,'reason':body.reason,'key':key+':'+str(line.inventory_item_id)})
            ids.append(str(request_id))
        result={'request_ids':ids,'posted_movements':0,'requires_independent_approval':True}
        operation(db,grant,location_id,principal,'opening_import',key,fingerprint,result)
        db.commit();return result
    except DBAPIError as exc:
        database_conflict(db,exc)
