"""Stage58: read-only media adapter contract and owner audit."""
import hashlib
import io
import sqlite3
import struct
import zipfile

import pytest

from desktop.media_tool_adapters import available_adapters, inspect_local, MAX_BYTES
from desktop.storage import LocalStore, AuthenticationError


def _owner(tmp_path):
    store = LocalStore(tmp_path / 'owner.sqlite3')
    store.setup_owner('owner58', 'stage58-owner-long-password')
    return store


def _png():
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I',13) + b'IHDR' + struct.pack('>IIBBBBB', 20,30,8,2,0,0,0) + b'\0'*4


def _docx():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('word/document.xml','<document/>')
    return out.getvalue()


@pytest.mark.parametrize('adapter,extension,data,expected', [
    ('image_png','.png',_png(),'20x30'),
    ('image_jpeg','.jpeg',b'\xff\xd8\xff\xe0stuff\xff\xd9','JPEG'),
    ('video_mp4','.mp4',struct.pack('>I',20)+b'ftypisom'+b'\0'*8,'isom'),
    ('video_webm','.webm',b'\x1a\x45\xdf\xa3'+b'\x82\x84webm','EBML'),
    ('document_text','.md','안녕하세요\nhello'.encode(),'2줄'),
    ('document_pdf','.pdf',b'%PDF-1.4\n%%EOF','PDF'),
    ('document_docx','.docx',_docx(),'DOCX'),
])
def test_real_local_readonly_adapters(tmp_path,adapter,extension,data,expected):
    p=tmp_path/('source'+extension);p.write_bytes(data)
    result=inspect_local(p,adapter)
    assert result['category'] in ('image','video','document')
    assert result['sha256']==hashlib.sha256(data).hexdigest()
    assert result['byte_size']==len(data)
    assert expected in result['details']
    assert not result['external_execution']
    assert p.read_bytes()==data


def test_contract_is_fixed_and_not_executor():
    specs=available_adapters()
    assert len(specs)==7
    assert {a['category'] for a in specs}=={'image','video','document'}
    assert all(a['needs_owner_confirmation'] and not a['executes_external_program'] for a in specs)
    assert all(a['operation']=='inspect_local_file' for a in specs)


@pytest.mark.parametrize('extension,content,adapter', [
    ('.png',b'not png','image_png'),
    ('.jpg',b'\xff\xd8','image_jpeg'),
    ('.mp4',b'nope','video_mp4'),
    ('.webm',b'wrong','video_webm'),
    ('.txt',b'\xff\xff','document_text'),
    ('.pdf',b'%PDF-1.4','document_pdf'),
    ('.docx',b'PKnotzip','document_docx'),
    ('.docx',b'PK\x03\x04','document_docx'),
])
def test_reject_invalid_content(tmp_path,extension,content,adapter):
    p=tmp_path/('bad'+extension);p.write_bytes(content)
    with pytest.raises(ValueError):inspect_local(p,adapter)


def test_reject_wrong_type_unknown_empty_large_symlink(tmp_path):
    p=tmp_path/'a.png';p.write_bytes(_png())
    with pytest.raises(ValueError):inspect_local(p,'document_pdf')
    with pytest.raises(ValueError):inspect_local(p,'unknown')
    p.write_bytes(b'')
    with pytest.raises(ValueError):inspect_local(p,'image_png')
    with p.open('wb') as f:f.truncate(MAX_BYTES+1)
    with pytest.raises(ValueError):inspect_local(p,'image_png')
    link=tmp_path/'link.png';link.symlink_to(p)
    with pytest.raises(ValueError):inspect_local(link,'image_png')
    with pytest.raises(ValueError):inspect_local(tmp_path,'image_png')


def test_owner_audit_persists_and_denies_logged_out(tmp_path):
    store=_owner(tmp_path)
    p=tmp_path/'x.png';p.write_bytes(_png())
    assert len(store.list_media_adapters())==7
    result=store.inspect_media_file(str(p),'image_png')
    assert result['id']==1
    assert store.media_inspection_history()[0]['sha256']==result['sha256']
    with store._connect() as con:
        with pytest.raises(sqlite3.DatabaseError):con.execute('DELETE FROM media_adapter_inspections')
        with pytest.raises(sqlite3.DatabaseError):con.execute('UPDATE media_adapter_inspections SET filename="fake"')
    store.logout()
    for action in (lambda:store.inspect_media_file(str(p),'image_png'),
                   store.media_inspection_history,store.list_media_adapters):
        with pytest.raises(AuthenticationError):action()
    restored=LocalStore(tmp_path/'owner.sqlite3')
    restored.login('owner58','stage58-owner-long-password')
    assert restored.media_inspection_history()[0]['filename']=='x.png'


def test_rejected_content_is_not_logged(tmp_path):
    store=_owner(tmp_path)
    p=tmp_path/'bad.png';p.write_bytes(b'bad')
    with pytest.raises(ValueError):store.inspect_media_file(str(p),'image_png')
    assert store.media_inspection_history()==[]
