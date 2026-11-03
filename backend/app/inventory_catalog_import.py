"""Bounded, create-only catalog import with preview digest and atomic audit."""
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.authorization import Principal, require_csrf
from app.db import get_db
from app.inventory_counts import DecimalBody, scope
from app.inventory_models import InventoryCategory, InventoryItem, InventoryItemUnitConversion, InventoryLocationItem, InventoryStorageZone, InventoryUnit, InventoryVendor, InventoryVendorItem
from app.inventory_pilot import digest, lock_location, operation
from app.inventory_approvals import database_conflict

router = APIRouter(prefix='/api/v1/inventory/locations/{location_id}/catalog-import', tags=['inventory operations'])


class CatalogRow(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    name: str = Field(min_length=1,max_length=180,pattern=r'\S')
    category: str = Field(min_length=1,max_length=120,pattern=r'\S')
    zone_code: str = Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    zone_name: str = Field(min_length=1,max_length=120,pattern=r'\S')
    base_unit_code: str = Field(min_length=1,max_length=24)
    purchase_unit_code: str = Field(min_length=1,max_length=24)
    pack_to_stock_factor: Decimal = Field(gt=0,max_digits=30,decimal_places=12,allow_inf_nan=False)
    vendor_code: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    vendor_name: str = Field(min_length=1,max_length=180,pattern=r'\S')
    vendor_sku: str = Field(min_length=1,max_length=80)
    unit_price: Decimal = Field(ge=0,max_digits=18,decimal_places=4,allow_inf_nan=False)
    currency_code: Literal['USD'] = 'USD'


class CatalogBatch(DecimalBody):
    model_config = ConfigDict(extra='forbid')
    rows: list[CatalogRow] = Field(min_length=1,max_length=200)

    @field_validator('rows')
    @classmethod
    def consistent(cls, rows):
        if len({r.sku for r in rows})!=len(rows):
            raise ValueError('Duplicate SKU in import')
        for key, name in [('zone_code','zone_name'),('vendor_code','vendor_name')]:
            known = {}
            for row in rows:
                code, value = getattr(row,key), getattr(row,name)
                if code in known and known[code]!=value:
                    raise ValueError('Conflicting zone or vendor names')
                known[code]=value
        return rows


class CatalogCommit(CatalogBatch):
    preview_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    idempotency_key: str = Field(min_length=1,max_length=128,pattern=r'\S')
    confirmed: Literal[True]
    approval_reference: str = Field(min_length=1,max_length=180,pattern=r'\S')


def validate(db, org, loc, rows):
    units = {u.code:u for u in db.scalars(select(InventoryUnit))}
    for row in rows:
        base, purchase = units.get(row.base_unit_code), units.get(row.purchase_unit_code)
        if not base or not purchase:
            raise HTTPException(422,'Unit must exist in the reviewed global unit catalog')
        if base.dimension == purchase.dimension and row.pack_to_stock_factor != purchase.factor_to_base/base.factor_to_base:
            raise HTTPException(422,'Physical conversion conflicts with the global unit definition')
        if db.scalar(select(InventoryItem.id).where(InventoryItem.organization_id==org,InventoryItem.sku==row.sku)):
            raise HTTPException(409,'SKU already exists; import is create-only and cannot change live conversions')
        for model, code_col, code, name in [(InventoryStorageZone,InventoryStorageZone.code,row.zone_code,row.zone_name), (InventoryVendor,InventoryVendor.vendor_code,row.vendor_code,row.vendor_name)]:
            query=select(model).where(model.organization_id==org,code_col==code)
            if model is InventoryStorageZone:
                query=query.where(model.location_id==loc)
            old=db.scalar(query)
            if old and (old.name!=name or not old.active):
                raise HTTPException(409,'Existing zone or vendor conflicts with import')
    return digest({'rows':[r.model_dump(mode='json') for r in rows]})


@router.post('/preview')
def preview(location_id: uuid.UUID, body: CatalogBatch, principal: Principal=Depends(require_csrf), db: Session=Depends(get_db)):
    grant,_=scope(db,principal,location_id,'inventory:catalog:manage')
    return {'preview_digest':validate(db,grant.organization_id,location_id,body.rows),'rows':len(body.rows),
            'mode':'create_only','requires_approved_catalog':True,'posts_stock':False}


@router.post('',status_code=201)
def commit(location_id: uuid.UUID, body: CatalogCommit, principal: Principal=Depends(require_csrf), db: Session=Depends(get_db)):
    grant,_=scope(db,principal,location_id,'inventory:catalog:manage')
    lock_location(db,grant.organization_id,location_id)
    # Org-wide catalog uniqueness and shared vendor/category names also serialize
    # imports from different restaurants in this organization.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:org,1))'),{'org':str(grant.organization_id)})
    fingerprint=digest(body.model_dump(mode='json'))
    old=operation(db,grant,location_id,principal,'catalog_import',body.idempotency_key,fingerprint)
    if old:
        return old
    if validate(db,grant.organization_id,location_id,body.rows)!=body.preview_digest:
        raise HTTPException(409,'Preview does not match the confirmed import')
    try:
        created=[]
        for row in body.rows:
            category=db.scalar(select(InventoryCategory).where(InventoryCategory.organization_id==grant.organization_id,InventoryCategory.name==row.category))
            if not category:
                category=InventoryCategory(organization_id=grant.organization_id,name=row.category);db.add(category);db.flush()
            if not category.active:
                raise HTTPException(409,'Catalog category is inactive')
            zone=db.scalar(select(InventoryStorageZone).where(InventoryStorageZone.organization_id==grant.organization_id,InventoryStorageZone.location_id==location_id,InventoryStorageZone.code==row.zone_code))
            if not zone:
                zone=InventoryStorageZone(organization_id=grant.organization_id,location_id=location_id,code=row.zone_code,name=row.zone_name);db.add(zone);db.flush()
            vendor=db.scalar(select(InventoryVendor).where(InventoryVendor.organization_id==grant.organization_id,InventoryVendor.vendor_code==row.vendor_code))
            if not vendor:
                vendor=InventoryVendor(organization_id=grant.organization_id,vendor_code=row.vendor_code,name=row.vendor_name);db.add(vendor);db.flush()
            item=InventoryItem(organization_id=grant.organization_id,category_id=category.id,sku=row.sku,name=row.name,item_type='ingredient',base_unit_code=row.base_unit_code,purchase_unit_code=row.purchase_unit_code)
            db.add(item);db.flush()
            db.add(InventoryLocationItem(organization_id=grant.organization_id,location_id=location_id,inventory_item_id=item.id,storage_zone_id=zone.id));db.flush()
            db.add(InventoryItemUnitConversion(organization_id=grant.organization_id,location_id=location_id,inventory_item_id=item.id,unit_code=row.purchase_unit_code,factor_to_stock_unit=row.pack_to_stock_factor))
            db.add(InventoryVendorItem(organization_id=grant.organization_id,location_id=location_id,vendor_id=vendor.id,inventory_item_id=item.id,vendor_sku=row.vendor_sku,purchase_unit_code=row.purchase_unit_code,pack_to_stock_factor=row.pack_to_stock_factor,unit_price=row.unit_price,currency_code=row.currency_code))
            created.append({'sku':row.sku,'inventory_item_id':str(item.id),'zone_id':str(zone.id)})
        db.flush()
        result={'created':created,'preview_digest':body.preview_digest,'approval_reference':body.approval_reference,'posted_movements':0}
        operation(db,grant,location_id,principal,'catalog_import',body.idempotency_key,fingerprint,result)
        db.commit()
        return result
    except DBAPIError as exc:
        database_conflict(db,exc)
