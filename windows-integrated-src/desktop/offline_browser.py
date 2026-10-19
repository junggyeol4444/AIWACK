"""Stage55: explicitly owner-triggered, read-only Chromium tasks on local HTML.

The file's original markup is NEVER given to the browser. Only escaped plain
text extracted by Python is rendered. JavaScript and browser network are off.
This is NOT an OS-level guarantee against networking by the browser binary.
"""
from __future__ import annotations

import html
from html.parser import HTMLParser
import os
from pathlib import Path
import shutil
import stat

MAX_HTML_BYTES = 1_048_576
MAX_RENDERED_CHARS = 100_000
MAX_QUERY_CHARS = 120


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.title_mode = False
        self.title_parts: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in ('script', 'style', 'iframe', 'object', 'template', 'svg'):
            self.hidden += 1
        elif tag == 'title' and not self.hidden:
            self.title_mode = True
        elif tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag: str):
        if tag in ('script', 'style', 'iframe', 'object', 'template', 'svg'):
            self.hidden = max(0, self.hidden - 1)
        elif tag == 'title':
            self.title_mode = False

    def handle_data(self, data: str):
        if self.hidden:
            return
        if self.title_mode:
            self.title_parts.append(data)
        else:
            self.parts.append(data)


def read_local_html(path: Path) -> tuple[str, str]:
    if not isinstance(path, Path):
        raise ValueError('HTML 파일 경로가 필요합니다.')
    raw_path = str(path)
    if raw_path.startswith(('\\\\', '//')) or path.suffix.lower() not in ('.html', '.htm'):
        raise ValueError('로컬 HTML 파일만 선택할 수 있습니다.')
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_HTML_BYTES:
            raise ValueError('일반 HTML 파일(1MiB 이하)만 허용합니다.')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as handle:
            during = os.fstat(handle.fileno())
            if ((before.st_ino, before.st_dev) != (during.st_ino, during.st_dev)
                    or not stat.S_ISREG(during.st_mode) or during.st_size > MAX_HTML_BYTES):
                raise ValueError('검사 중 원본 파일이 변경되었습니다.')
            data = handle.read(MAX_HTML_BYTES + 1)
        after = path.lstat()
    except OSError as exc:
        raise ValueError('HTML 파일을 안전하게 읽을 수 없습니다.') from exc
    if len(data) > MAX_HTML_BYTES or (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns):
        raise ValueError('검사 중 원본 파일이 변경되었습니다.')
    # Never execute HTML; decoding errors are represented, not silently skipped.
    parser = _PlainHTML()
    parser.feed(data.decode('utf-8-sig', errors='replace'))
    title = ' '.join(''.join(parser.title_parts).split())[:200] or '(제목 없음)'
    content = ' '.join(''.join(parser.parts).split())[:MAX_RENDERED_CHARS]
    return title, content


def installed_chromium() -> str | None:
    """Only use already-installed browsers; never download/install a runtime."""
    for name in ('chromium', 'chromium-browser', 'google-chrome', 'msedge', 'chrome'):
        found = shutil.which(name)
        if found:
            return found
    if os.name == 'nt':
        for environment, relative in (
            ('PROGRAMFILES', 'Google/Chrome/Application/chrome.exe'),
            ('PROGRAMFILES(X86)', 'Microsoft/Edge/Application/msedge.exe'),
            ('LOCALAPPDATA', 'Microsoft/Edge/Application/msedge.exe'),
        ):
            base = os.getenv(environment)
            if base:
                candidate = Path(base) / relative
                if candidate.is_file():
                    return str(candidate)
    return None


def inspect_in_browser(path: Path, *, find_text: str = '', browser_path: str | None = None) -> dict:
    """Render ONLY escaped text in Chromium, then execute an allowlisted find task.

    Not a web crawler, full browser automation, trust verification, or OS sandbox.
    Request routing plus offline mode prohibit page network requests, while
    background traffic by the installed executable requires OS firewall control.
    """
    if not isinstance(find_text, str) or len(find_text) > MAX_QUERY_CHARS or '\x00' in find_text:
        raise ValueError('검색어는 120자 이하여야 합니다.')
    title, content = read_local_html(path)
    browser = browser_path if browser_path is not None else installed_chromium()
    if not browser or not Path(browser).is_file():
        raise RuntimeError('설치된 로컬 Chromium/Chrome/Edge가 없어 브라우저 작업을 실행할 수 없습니다.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError('로컬 Playwright가 없어 브라우저 작업을 실행할 수 없습니다. 자동 설치하지 않습니다.') from exc
    # No untrusted attributes, sources, stylesheet links, or scripts survive.
    safe_html = ('<!doctype html><html><head><meta charset="utf-8"><title>'
                 + html.escape(title, quote=True) + '</title></head><body><main><pre '
                 + 'style="white-space:pre-wrap">' + html.escape(content, quote=True)
                 + '</pre></main></body></html>')
    try:
        with sync_playwright() as playwright:
            engine = playwright.chromium.launch(
                executable_path=str(browser), headless=True, timeout=45000,
                args=['--disable-background-networking', '--disable-extensions',
                      '--no-first-run', '--no-default-browser-check',
                      '--disable-component-update', '--disable-sync',
                      '--host-resolver-rules=MAP * ~NOTFOUND'],
            )
            try:
                context = engine.new_context(java_script_enabled=False,
                                             service_workers='block', offline=True,
                                             accept_downloads=False)
                try:
                    context.route('**/*', lambda route: route.abort())
                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.set_content(safe_html, wait_until='domcontentloaded', timeout=5000)
                    rendered = page.locator('main pre').inner_text()
                    browser_title = page.title()
                    return {
                        'title': browser_title,
                        'characters': len(rendered),
                        'matches': rendered.casefold().count(find_text.casefold()) if find_text else 0,
                        'preview': rendered[:350],
                        'offline': True,
                        'browser_task': 'local_read_and_find',
                    }
                finally:
                    context.close()
            finally:
                engine.close()
    except Exception as exc:
        raise RuntimeError(f'로컬 브라우저 작업이 실패했습니다: {type(exc).__name__}') from exc
