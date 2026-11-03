"""Private, re-encoded photo objects. Access grants are bound to a live session.

A local private object store supports a single API instance with a persistent
volume. No public/static mount or client-selected object path is accepted.
"""
import hashlib
import hmac
import io
import os
import re
import subprocess
import time
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.authorization import Principal, authenticated_principal, require_csrf
from app.config import settings
from app.db import get_db
from app.inventory_counts import load_session, scope
from app.inventory_approvals import database_conflict
from app.models import AuditLog

router = APIRouter(prefix='/api/v1/inventory/locations/{location_id}', tags=['protected inventory evidence'])
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
KEY = re.compile(r'^[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f-]{36}\.jpg$')
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def sanitize_photo(raw: bytes, mime: str) -> bytes:
    expected = {'image/jpeg':'JPEG','image/png':'PNG'}.get(mime)
    magic = raw.startswith(b'\xff\xd8\xff') if expected=='JPEG' else raw.startswith(b'\x89PNG\r\n\x1a\n') if expected=='PNG' else False
    if not expected or not magic:
        raise HTTPException(415,'Only matching JPEG or PNG photos are accepted')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=['JPEG','PNG']) as image:
                if image.format!=expected or image.width*image.height>MAX_PIXELS or getattr(image,'n_frames',1)!=1:
                    raise ValueError('Invalid image dimensions or animation')
                image.verify()
            with Image.open(io.BytesIO(raw), formats=['JPEG','PNG']) as image:
                image.load()
                # Recreate pixels, omitting EXIF/GPS, text chunks, ICC and any
                # appended payload. Preserve camera orientation in the pixels.
                pixels = ImageOps.exif_transpose(image).convert('RGB')
                clean = Image.new('RGB',pixels.size);clean.paste(pixels)
                output=io.BytesIO();clean.save(output,format='JPEG',quality=90)
        if output.tell()>MAX_BYTES:
            raise ValueError('Sanitized image too large')
        return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422,'Photo cannot be safely decoded; choose a smaller JPEG or PNG') from exc


class PrivatePhotoStore:
    def path(self, key):
        if not KEY.fullmatch(key):
            raise HTTPException(404,'Evidence object not found')
        root=Path(settings.evidence_storage_dir)
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if root.is_symlink():
            raise HTTPException(503,'Private evidence storage is unavailable')
        os.chmod(root,0o700)
        path=root/key
        for directory in (path.parent.parent,path.parent):
            if directory.is_symlink():
                raise HTTPException(503,'Private evidence storage is unavailable')
            directory.mkdir(mode=0o700,exist_ok=True)
            os.chmod(directory,0o700)
        return path

    def put(self,key,data):
        path=self.path(key)
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(descriptor,'wb') as output:
                output.write(data);output.flush();os.fsync(output.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def read(self,key):
        try:
            with os.fdopen(os.open(self.path(key),os.O_RDONLY|os.O_NOFOLLOW),'rb') as source:
                return source.read(MAX_BYTES+1)
        except OSError as exc:
            raise HTTPException(410,'Evidence bytes are unavailable; contact the pilot administrator') from exc

    def remove(self,key):
        self.path(key).unlink(missing_ok=True)


store=PrivatePhotoStore()


def scan_photo(path):
    if not settings.evidence_scanner_path:
        if settings.environment not in {'development','test'}:
            raise HTTPException(503,'Evidence uploads require a configured malware scanner')
        return 'sanitized_only'
    try:
        result=subprocess.run([settings.evidence_scanner_path,'--no-summary','--',str(path)],capture_output=True,timeout=30,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise HTTPException(503,'Evidence scanner unavailable; upload rejected') from exc
    if result.returncode!=0:
        raise HTTPException(422 if result.returncode==1 else 503,'Evidence scanner rejected the upload or could not complete')
    return 'scanned'


def load_evidence(db, location_id, evidence_id, lock=False):
    row=db.execute(text('SELECT * FROM inventory_evidence WHERE id=:id AND location_id=:loc'+(' FOR UPDATE' if lock else '')),
        {'id':evidence_id,'loc':location_id}).mappings().first()
    if not row:
        raise HTTPException(404,'Photo evidence not found')
    return row


def live(row):
    if row['deleted_at'] is not None or (not row['legal_hold'] and row['retain_until']<=datetime.now(timezone.utc)):
        raise HTTPException(410,'Photo retention expired or the object was deleted')


def log_access(db, row, principal, action):
    db.add(AuditLog(organization_id=row['organization_id'],location_id=row['location_id'],user_id=principal.user_id,
        action=action,entity_type='inventory_evidence',entity_id=str(row['id']),metadata_json={'session_id':str(row['session_id'])}))


def public(row):
    return {key:value for key,value in row.items() if key not in {'uploaded_by','control_reason'}}


@router.post('/count-sessions/{session_id}/evidence', status_code=201)
async def upload(location_id: uuid.UUID, session_id: uuid.UUID, evidence_id: uuid.UUID, request: Request,
                 principal: Principal=Depends(require_csrf), db: Session=Depends(get_db)):
    grant,_=scope(db,principal,location_id,'inventory:count')
    session=load_session(db,location_id,session_id,lock=True)
    if session.status!='draft' or session.assigned_to!=principal.user_id:
        raise HTTPException(403,'Only the assigned counter can upload to a draft')
    if settings.environment not in {'development','test'} and not settings.evidence_scanner_path:
        raise HTTPException(503,'Evidence uploads require a configured malware scanner')
    # Real Redis rate limit applies before decoding any untrusted image.
    counter = request.app.state.redis.pipeline()
    rate_key = f'evidence-upload:{principal.user_id}:{location_id}'
    counter.incr(rate_key);counter.expire(rate_key,60,nx=True)
    if counter.execute()[0]>20:
        raise HTTPException(429,'Photo upload rate limit reached; retry in one minute')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_BYTES:
            raise HTTPException(413,'Photo exceeds the 5 MiB upload limit')
    data=await run_in_threadpool(sanitize_photo,bytes(raw),request.headers.get('content-type','').split(';')[0].strip().lower())
    sha=hashlib.sha256(data).hexdigest()
    old=db.execute(text('SELECT * FROM inventory_evidence WHERE id=:id'),{'id':evidence_id}).mappings().first()
    if old:
        if old['session_id']!=session_id or old['uploaded_by']!=principal.user_id or old['sha256']!=sha:
            raise HTTPException(409,'Evidence upload identity was reused')
        live(old)
        return public(old)
    from app.inventory_pilot import lock_location
    lock_location(db,grant.organization_id,location_id)
    count=db.scalar(text("SELECT count(*) FROM inventory_evidence WHERE organization_id=:org AND location_id=:loc AND uploaded_at>clock_timestamp()-interval '1 day'"),{'org':grant.organization_id,'loc':location_id})
    if count>=200:
        raise HTTPException(429,'Daily location evidence quota reached; contact the manager')
    key=f'{grant.organization_id}/{location_id}/{evidence_id}.jpg'
    try:
        path=await run_in_threadpool(store.put,key,data)
    except FileExistsError as exc:
        raise HTTPException(409,'Unconfirmed evidence object exists; contact the administrator before retrying') from exc
    try:
        scanner_status=await run_in_threadpool(scan_photo,path)
        db.execute(text('''INSERT INTO inventory_evidence(id,organization_id,location_id,session_id,object_key,sha256,byte_size,mime_type,uploaded_by,retain_until,control_reason,scanner_status)
          VALUES(:id,:org,:loc,:session,:key,:sha,:size,'image/jpeg',:actor,:retain,'Counter uploaded confirmed identification evidence',:scanner)'''),
          {'id':evidence_id,'org':grant.organization_id,'loc':location_id,'session':session_id,'key':key,'sha':sha,'size':len(data),
           'actor':principal.user_id,'retain':datetime.now(timezone.utc)+timedelta(seconds=settings.evidence_retention_seconds),'scanner':scanner_status})
        result=public(load_evidence(db,location_id,evidence_id))
        db.commit()
        return result
    except BaseException:
        db.rollback()
        await run_in_threadpool(store.remove,key)
        raise


@router.get('/evidence/{evidence_id}')
def metadata(location_id: uuid.UUID,evidence_id: uuid.UUID,principal: Principal=Depends(authenticated_principal),db: Session=Depends(get_db)):
    scope(db,principal,location_id)
    row=load_evidence(db,location_id,evidence_id)
    return public(row)


def sign(evidence_id,principal,expires):
    payload=f'evidence-v1:{evidence_id}:{principal.user_id}:{principal.session_id}:{expires}'
    return hmac.new(settings.session_secret.encode(),payload.encode(),hashlib.sha256).hexdigest()


@router.post('/evidence/{evidence_id}/access')
def access(location_id: uuid.UUID,evidence_id: uuid.UUID,principal: Principal=Depends(require_csrf),db: Session=Depends(get_db)):
    scope(db,principal,location_id)
    row=load_evidence(db,location_id,evidence_id);live(row)
    expires=int(time.time())+60
    token=f'{expires}.{sign(evidence_id,principal,expires)}'
    log_access(db,row,principal,'inventory.evidence.access_granted');db.commit()
    return {'path':f'/api/v1/inventory/locations/{location_id}/evidence/{evidence_id}/content','token':token,'expires_in':60}


@router.get('/evidence/{evidence_id}/content')
def content(location_id: uuid.UUID,evidence_id: uuid.UUID,x_evidence_token: str=Header(default='',max_length=128),
            principal: Principal=Depends(authenticated_principal),db: Session=Depends(get_db)):
    scope(db,principal,location_id)
    row=load_evidence(db,location_id,evidence_id);live(row)
    try:
        expires,signature=x_evidence_token.split('.',1);expires=int(expires)
        if expires<int(time.time()) or expires>int(time.time())+60 or not hmac.compare_digest(signature,sign(evidence_id,principal,expires)):
            raise ValueError('Invalid grant')
    except (ValueError,TypeError):
        raise HTTPException(403,'Photo access grant expired or is invalid')
    data=store.read(row['object_key'])
    if len(data)!=row['byte_size'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
        raise HTTPException(503,'Photo integrity check failed')
    log_access(db,row,principal,'inventory.evidence.viewed');db.commit()
    return Response(data,media_type='image/jpeg',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"default-src 'none'; sandbox",'Content-Disposition':'inline; filename="inventory-evidence.jpg"'})


class RetentionBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    legal_hold: bool
    retain_until: datetime | None=None
    reason: str=Field(min_length=1,max_length=2000,pattern=r'\S')


class DeleteBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason: str=Field(min_length=1,max_length=2000,pattern=r'\S')


@router.patch('/evidence/{evidence_id}/retention')
def retention(location_id: uuid.UUID,evidence_id: uuid.UUID,body: RetentionBody,
              principal: Principal=Depends(require_csrf),db: Session=Depends(get_db)):
    scope(db,principal,location_id,'inventory:approve')
    row=load_evidence(db,location_id,evidence_id,lock=True)
    if body.retain_until and body.retain_until.tzinfo is None:
        raise HTTPException(422,'Retention deadline must include a timezone')
    try:
        db.execute(text('UPDATE inventory_evidence SET legal_hold=:hold,retain_until=:retain,control_reason=:reason WHERE id=:id'),
            {'id':evidence_id,'hold':body.legal_hold,'retain':body.retain_until or row['retain_until'],'reason':body.reason})
        result=public(load_evidence(db,location_id,evidence_id));db.commit();return result
    except DBAPIError as exc:
        database_conflict(db,exc)


@router.post('/evidence/{evidence_id}/delete')
def delete(location_id: uuid.UUID,evidence_id: uuid.UUID,body: DeleteBody,
           principal: Principal=Depends(require_csrf),db: Session=Depends(get_db)):
    scope(db,principal,location_id,'inventory:approve')
    row=load_evidence(db,location_id,evidence_id,lock=True)
    if not row['deleted_at']:
        try:
            db.execute(text('UPDATE inventory_evidence SET deleted_at=clock_timestamp(),control_reason=:reason WHERE id=:id'),{'id':evidence_id,'reason':body.reason})
            # Deny access durably before deleting bytes. A filesystem failure is
            # retryable; it must never resurrect a photo or roll back its tombstone.
            db.commit()
        except DBAPIError as exc:
            database_conflict(db,exc)
    try:
        store.remove(row['object_key'])
    except OSError as exc:
        raise HTTPException(503,'Access revoked; object erasure pending. Retry deletion and alert the administrator.') from exc
    log_access(db,row,principal,'inventory.evidence.bytes_erased');db.commit()
    return {'id':str(evidence_id),'deleted':True,'bytes_erased':True}
