"""Stage55 allowed local Chromium tasks; zero remote browser actions."""
from pathlib import Path
import os
import pytest

from desktop.offline_browser import inspect_in_browser, read_local_html, installed_chromium, MAX_HTML_BYTES


def test_safe_plain_text_does_not_expose_script_css_or_raw_html(tmp_path):
    p=tmp_path/'a.html'
    p.write_text('''<title>Safe &amp; sound</title><h1>Visible alpha</h1>
    <script>SECRET_JS_DO_NOT_RUN</script><style>SECRET_CSS</style>
    <iframe src="https://example.invalid/secret">SECRET_FRAME</iframe>
    <img src="https://example.invalid/exfil?key=x"><p>Beta</p>''',encoding='utf-8')
    title,content=read_local_html(p)
    assert title=='Safe & sound'
    assert 'Visible alpha' in content and 'Beta' in content
    assert all(s not in content for s in ('SECRET_JS','SECRET_CSS','SECRET_FRAME','exfil'))


def test_refuse_symlink(tmp_path):
    real=tmp_path/'real.html'; real.write_text('<p>safe</p>')
    link=tmp_path/'link.html'; link.symlink_to(real)
    with pytest.raises(ValueError):read_local_html(link)


@pytest.mark.parametrize('file_name', ['unsafe.txt','CON.html.txt','bad.json'])
def test_non_html_rejected(tmp_path,file_name):
    p=tmp_path/file_name; p.write_text('bad')
    with pytest.raises(ValueError):read_local_html(p)


def test_oversized_file_rejected(tmp_path):
    p=tmp_path/'huge.html';p.write_bytes(b'x'*(MAX_HTML_BYTES+1))
    with pytest.raises(ValueError):read_local_html(p)


def test_unc_path_rejected():
    with pytest.raises(ValueError):read_local_html(Path('//remote/share/test.html'))


@pytest.mark.parametrize('query', ['x'*121,'\x00'])
def test_invalid_query_rejected_before_browser_launch(tmp_path,query):
    p=tmp_path/'ok.html';p.write_text('hello')
    with pytest.raises(ValueError):inspect_in_browser(p,find_text=query)


def test_browser_unavailable_fails_closed(tmp_path):
    p=tmp_path/'ok.html';p.write_text('hello')
    with pytest.raises(RuntimeError,match='브라우저'):
        inspect_in_browser(p,browser_path=str(tmp_path/'no-chromium'))


def test_real_browser_reads_only_sanitized_local_text(tmp_path):
    browser = installed_chromium()
    if not browser:
        pytest.skip('Chromium not preinstalled; never download')
    p=tmp_path/'local.html'
    p.write_text('<title>동작 확인</title><h1>Alpha</h1><p>ALPHA &amp; beta</p>'
                 '<script>document.title="STOLEN"</script>'
                 '<img src="https://example.invalid/remote.png">',encoding='utf-8')
    info = inspect_in_browser(p,find_text='alpha')
    assert info['title']=='동작 확인'
    assert info['matches']==2
    assert 'Alpha' in info['preview'] and 'STOLEN' not in info['preview']
    assert info['offline'] is True
