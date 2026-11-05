"""Image and private-filesystem boundary tests; these do not substitute for RLS."""
import io
import os
import struct
import uuid
import zlib

import pytest
from fastapi import HTTPException
from PIL import Image

from app.config import settings
from app.inventory_evidence import PrivatePhotoStore, sanitize_photo, scan_photo


def test_reencoding_strips_exif_gps_and_appended_payload():
    photo=Image.new('RGB',(8,12),'brown');exif=Image.Exif();exif[0x010E]='Private metadata must be stripped'
    out=io.BytesIO();photo.save(out,format='JPEG',exif=exif)
    clean=sanitize_photo(out.getvalue()+b'<script>discard me</script>','image/jpeg')
    decoded=Image.open(io.BytesIO(clean));assert decoded.size==(8,12) and not decoded.getexif()
    assert b'Private metadata' not in clean and b'<script>' not in clean


def test_mime_mismatch_and_decompression_bomb_headers_fail_closed():
    out=io.BytesIO();Image.new('RGB',(1,1)).save(out,format='PNG');raw=out.getvalue()
    with pytest.raises(HTTPException) as mismatch:sanitize_photo(raw,'image/jpeg')
    assert mismatch.value.status_code==415
    header=struct.pack('>IIBBBBB',4096,4096,8,2,0,0,0)
    chunk=b'IHDR'+header
    bomb=raw[:8]+struct.pack('>I',len(header))+chunk+struct.pack('>I',zlib.crc32(chunk)&0xffffffff)+raw[33:]
    with pytest.raises(HTTPException) as rejected:sanitize_photo(bomb,'image/png')
    assert rejected.value.status_code==422


def test_private_objects_reject_traversal_symlinks_and_overwrites(tmp_path,monkeypatch):
    root=tmp_path/'private';monkeypatch.setattr(settings,'evidence_storage_dir',str(root));store=PrivatePhotoStore()
    org,loc,item=(str(uuid.uuid4()) for _ in range(3));key=f'{org}/{loc}/{item}.jpg'
    path=store.put(key,b'private object');assert store.read(key)==b'private object'
    assert os.stat(path).st_mode & 0o777==0o600 and os.stat(root).st_mode & 0o777==0o700
    with pytest.raises(FileExistsError):store.put(key,b'overwrite')
    with pytest.raises(HTTPException):store.read('../../secret.jpg')
    second=str(uuid.uuid4());(root/org/second).symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(HTTPException):store.put(f'{org}/{second}/{item}.jpg',b'escape')
    assert store.read(key)==b'private object'


def test_staging_requires_scanner_and_scanner_errors_are_not_success(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'environment','staging');monkeypatch.setattr(settings,'evidence_scanner_path',None)
    path=tmp_path/'photo.jpg';path.write_bytes(b'irrelevant')
    with pytest.raises(HTTPException) as missing:scan_photo(path)
    assert missing.value.status_code==503
    monkeypatch.setattr(settings,'evidence_scanner_path','/missing/scanner')
    with pytest.raises(HTTPException) as unavailable:scan_photo(path)
    assert unavailable.value.status_code==503
