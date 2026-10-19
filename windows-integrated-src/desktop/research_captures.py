"""Stage54 offline research evidence intake; never opens URLs or network sockets.

Records are administrator-entered, NOT authenticated source observations.
HTML is parsed as inert text only, not opened/rendered as active content.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import stat
from html.parser import HTMLParser
import sqlite3
from urllib.parse import urlsplit, urlunsplit, urljoin

MAX_RAW_BYTES = 256_000
MAX_CONTENT = 60_000


class _VisibleText(HTMLParser):
    BLOCKS = frozenset({'p','div','section','article','li','h1','h2','h3','h4','h5','h6',
                       'blockquote','tr','br','hr','header','footer'})
    HIDDEN = frozenset({'script','style','noscript','svg','template'})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        elif not self.hidden and tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in self.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
        elif tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)



class _OfflineLinks(HTMLParser):
    """Extract passive <a href> metadata; no URL is ever opened.

    Ignore document-supplied <base> tags: the human-entered claimed source URL
    is the only base allowed for resolving relative links. All results remain
    unverified, including apparently same-domain URLs.
    """
    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = claimed_source
        self.urls: list[str] = []
        self.seen: set[str] = set()
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if self.hidden or tag != 'a' or len(self.urls) >= 100:
            return
        href = next((value for name, value in attrs if name == 'href'), None)
        if not isinstance(href, str) or not href or len(href) > 2048:
            return
        try:
            # Discard javascript:, data:, file:, mailto:, and non-web schemes
            # even when Python urljoin might otherwise reinterpret them.
            parsed = urlsplit(href)
            if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                return
            normalized = validate_url(urljoin(self.claimed_source, href))
        except (ValueError, UnicodeError):
            return
        if normalized != self.claimed_source and normalized not in self.seen:
            self.seen.add(normalized)
            self.urls.append(normalized)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def extract_offline_links(html_text: str, claimed_source: str) -> list[str]:
    """Return up to 100 local HTML link strings for *manual* investigation."""
    claimed_source = validate_url(claimed_source)
    parser = _OfflineLinks(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.urls



class _InertSourceHints(HTMLParser):
    """Look at local HTML author-declared identity hints, never follow them.

    These *claims* are not independent proof of origin. Cap records and do not
    evaluate scripts, fetch links, or honor a document-supplied <base> tag.
    """
    MAX_HINTS = 8

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.hints: list[dict] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if self.hidden or len(self.hints) >= self.MAX_HINTS:
            return
        attributes = dict(attrs)
        marker = None
        candidate = None
        if tag == 'link' and 'canonical' in (attributes.get('rel') or '').lower().split():
            marker, candidate = 'canonical', attributes.get('href')
        elif tag == 'meta' and (attributes.get('property') or '').lower() == 'og:url':
            marker, candidate = 'og:url', attributes.get('content')
        if marker is None:
            return
        if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > 2048:
            normalized, status = None, 'invalid'
        else:
            try:
                # An explicit non-http scheme must never become a web URL.
                parsed = urlsplit(candidate.strip())
                if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                    raise ValueError('non-web scheme')
                normalized = validate_url(urljoin(self.claimed_source, candidate.strip()))
                status = 'match' if normalized == self.claimed_source else 'mismatch'
            except (ValueError, UnicodeError):
                normalized, status = None, 'invalid'
        self.hints.append({'kind': marker, 'status': status,
                           'claimed_url': normalized, 'raw_value': candidate[:160] if isinstance(candidate, str) else ''})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def inspect_offline_source_hints(html_text: str, claimed_source: str) -> list[dict]:
    """Inspect up to 8 inert canonical/og:url claims without resolving hosts."""
    parser = _InertSourceHints(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.hints

class _InertNavigationDirectives(HTMLParser):
    """Inspect at most eight inert HTML navigation directives, never act on them.

    A document-supplied base can alter relative link resolution in a browser,
    while a refresh can initiate navigation. Neither changes our offline link
    parser's explicitly owner-entered URL base.
    """
    MAX_DIRECTIVES = 8
    REFRESH_URL = re.compile(r'^\s*\d+(?:\.\d+)?\s*;\s*url\s*=\s*(.+?)\s*$', re.I | re.S)

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.directives: list[dict] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if self.hidden or len(self.directives) >= self.MAX_DIRECTIVES:
            return
        attributes = dict(attrs)
        kind, raw = None, None
        if tag == 'base' and 'href' in attributes:
            kind, raw = 'base', attributes['href']
        elif tag == 'meta' and (attributes.get('http-equiv') or '').strip().lower() == 'refresh':
            # Refresh without a URL is only a timed reload, not a target claim.
            content = attributes.get('content')
            if not isinstance(content, str):
                kind, raw = 'refresh', content
            else:
                match = self.REFRESH_URL.fullmatch(content)
                if match:
                    kind, raw = 'refresh', match.group(1).strip().strip('\"\'')
                elif 'url' in content.lower():
                    kind, raw = 'refresh', None  # malformed attempted navigation
        if kind is None:
            return
        normalized, status = None, 'invalid'
        if isinstance(raw, str) and raw.strip() and len(raw) <= 2048:
            try:
                candidate = raw.strip()
                parsed = urlsplit(candidate)
                if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                    raise ValueError('non-http navigation')
                normalized = validate_url(urljoin(self.claimed_source, candidate))
                original = urlsplit(self.claimed_source)
                target = urlsplit(normalized)
                status = ('same_origin' if (original.scheme.lower(), original.hostname, original.port)
                          == (target.scheme.lower(), target.hostname, target.port)
                          else 'other_origin')
            except (ValueError, UnicodeError):
                pass
        self.directives.append({'kind': kind, 'status': status,
                                'target_url': normalized,
                                'raw_value': raw[:160] if isinstance(raw, str) else ''})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def inspect_offline_navigation_directives(html_text: str, claimed_source: str) -> list[dict]:
    """Passive <base> and refresh inspection; no DNS, rendering, or requests."""
    parser = _InertNavigationDirectives(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.directives



class _InertActiveTargets(HTMLParser):
    """List bounded HTML form / iframe / external script targets as inert text.

    An archived HTML file can contain submission or embedded-resource endpoints.
    This parser NEVER makes a request, interprets scripts or submits a form.
    Relative URLs always resolve against the owner-entered source URL, never
    an untrusted <base> element. These are warnings, not proofs of danger.
    """
    MAX_TARGETS = 8

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.targets: list[dict] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        # A script itself may have a remote src; inspect *before* hiding its
        # contents. Ignore markup inside scripts/styles/noscript/templates.
        if not self.hidden and len(self.targets) < self.MAX_TARGETS:
            attributes = dict(attrs)
            kind, raw, method = None, None, None
            if tag == 'form':
                kind = 'form'
                method = (attributes.get('method') or 'GET')
                if not isinstance(method, str):
                    method = '?'
                method = method.strip().upper()[:16]
                raw = attributes.get('action')
                if raw is None or raw == '':  # browser default submission URL
                    raw = self.claimed_source
            elif tag == 'iframe' and 'src' in attributes:
                kind, raw = 'iframe', attributes['src']
            elif tag == 'script' and 'src' in attributes:
                kind, raw = 'script', attributes['src']
            if kind is not None:
                normalized, status = None, 'invalid'
                if isinstance(raw, str) and 0 < len(raw.strip()) <= 2048:
                    try:
                        candidate = raw.strip()
                        split = urlsplit(candidate)
                        if split.scheme and split.scheme.lower() not in ('http', 'https'):
                            raise ValueError('non-web endpoint')
                        normalized = validate_url(urljoin(self.claimed_source, candidate))
                        src, dest = urlsplit(self.claimed_source), urlsplit(normalized)
                        status = ('same_origin' if (src.scheme.lower(), src.hostname, src.port)
                                  == (dest.scheme.lower(), dest.hostname, dest.port)
                                  else 'other_origin')
                    except (ValueError, UnicodeError):
                        pass
                self.targets.append({'kind': kind, 'status': status,
                                     'target_url': normalized,
                                     'raw_value': raw[:160] if isinstance(raw, str) else '',
                                     'method': method})
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def inspect_offline_active_targets(html_text: str, claimed_source: str) -> list[dict]:
    """Inert, capped form-action / iframe-src / script-src warning candidates."""
    parser = _InertActiveTargets(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.targets


class _InertFormControls(HTMLParser):
    """Record bounded *types*, never values, of selected HTML form controls.

    Hidden/file/password fields are a review cue, not evidence of exfiltration.
    Only controls nested in explicit <form> elements are covered; scripts,
    templates and HTML form= ID associations are intentionally not evaluated.
    No inputs, values, field names, URLs or executable markup are retained.
    """
    MAX_CONTROLS = 8
    KINDS = frozenset({'password', 'file', 'hidden'})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.controls: list[dict] = []
        self.hidden: list[str] = []
        self.forms: list[tuple[int, str]] = []
        self.form_number = 0

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in _VisibleText.HIDDEN:
                self.hidden.append(tag)
            return
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if tag == 'form':
            attrs_map = dict(attrs)
            method = attrs_map.get('method') or 'GET'
            if not isinstance(method, str):
                method = 'OTHER'
            method = method.strip().upper()
            if method not in ('GET', 'POST'):
                method = 'OTHER'
            self.form_number += 1
            self.forms.append((self.form_number, method))
        elif tag == 'input' and self.forms and len(self.controls) < self.MAX_CONTROLS:
            raw = dict(attrs).get('type') or 'text'
            if isinstance(raw, str):
                kind = raw.strip().lower()
                if kind in self.KINDS:
                    ordinal, method = self.forms[-1]
                    self.controls.append({'kind': kind, 'form_ordinal': ordinal,
                                          'method': method,
                                          'password_in_get': kind == 'password' and method == 'GET'})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN or tag == 'form':
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
        elif tag == 'form' and self.forms:
            self.forms.pop()


def inspect_offline_form_controls(html_text: str) -> list[dict]:
    """Inert review of up to eight password/file/hidden input *types* in forms."""
    parser = _InertFormControls()
    parser.feed(html_text)
    parser.close()
    return parser.controls



class _InertPassiveResources(HTMLParser):
    """Bounded, non-executing HTML external resource inspection.

    Only static src/href/poster attributes are covered; CSS url(), srcset,
    JS-generated elements, redirects and browser network policy are NOT parsed.
    Store just target host, never URL paths, query strings, credentials or HTML.
    Document-supplied <base> intentionally cannot change URL resolution.
    """
    MAX_REFERENCES = 12

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.references: list[dict] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in _VisibleText.HIDDEN:
                self.hidden.append(tag)
            return
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if len(self.references) >= self.MAX_REFERENCES:
            return
        data = dict(attrs)
        kind, candidate = None, None
        if tag == 'img' and 'src' in data:
            kind, candidate = 'image', data['src']
        elif tag == 'link' and 'stylesheet' in (data.get('rel') or '').lower().split() and 'href' in data:
            kind, candidate = 'stylesheet', data['href']
        elif tag == 'video' and 'poster' in data:
            kind, candidate = 'media', data['poster']
        elif tag in ('audio', 'video', 'source', 'track') and 'src' in data:
            kind, candidate = 'media', data['src']
        if kind is None:
            return
        status, host = 'invalid', None
        if isinstance(candidate, str) and candidate.strip() and len(candidate) <= 2048:
            try:
                raw = candidate.strip()
                parsed = urlsplit(raw)
                if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                    raise ValueError('not a web URL')
                resolved = validate_url(urljoin(self.claimed_source, raw))
                origin, target = urlsplit(self.claimed_source), urlsplit(resolved)
                status = ('same_origin' if (origin.scheme.lower(), origin.hostname, origin.port)
                          == (target.scheme.lower(), target.hostname, target.port)
                          else 'other_origin')
                host = target.hostname
            except (ValueError, UnicodeError):
                pass
        self.references.append({'kind': kind, 'status': status, 'target_host': host})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def inspect_offline_passive_resources(html_text: str, claimed_source: str) -> list[dict]:
    """Only inspect up to 12 static HTML resource attributes; no requests."""
    parser = _InertPassiveResources(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.references

class _InertResponsiveImages(HTMLParser):
    """Inspect HTML img/source srcset candidates, without fetching or rendering.

    Counts at most 12 candidates per HTML file, even if the attribute is huge.
    Comma-containing URL tokens (e.g. data: URI) cannot be reliably parsed
    with this conservative scanner and are reported as invalid rather than
    claiming browser-equivalent interpretation. Never retain paths/queries.
    """
    MAX_CANDIDATES = 12
    MAX_ATTRIBUTE = 4096

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.candidates: list[dict] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in _VisibleText.HIDDEN:
                self.hidden.append(tag)
            return
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if tag not in ('img', 'source') or len(self.candidates) >= self.MAX_CANDIDATES:
            return
        data = dict(attrs)
        if 'srcset' not in data:
            return
        raw = data['srcset']
        if not isinstance(raw, str) or len(raw) > self.MAX_ATTRIBUTE or not raw.strip():
            parts = ['']
        elif 'data:' in raw.lower():
            # Data-URI commas are not srcset candidate separators. Conservative.
            parts = ['']
        else:
            parts = raw.split(',', self.MAX_CANDIDATES)
        for part in parts:
            if len(self.candidates) >= self.MAX_CANDIDATES:
                break
            tokens = part.strip().split()
            status, host, descriptor = 'invalid', None, None
            if len(tokens) in (1, 2):
                candidate = tokens[0]
                raw_descriptor = tokens[1] if len(tokens) == 2 else ''
                # Only accept simple positive width/density descriptors. Never
                # return untrusted text; only return the validated token.
                descriptor_ok = (not raw_descriptor or
                    re.fullmatch(r'(?:[1-9][0-9]*w|(?:[0-9]+(?:\.[0-9]+)?)x)', raw_descriptor))
                if descriptor_ok and (not raw_descriptor or not raw_descriptor.startswith(('0w','0x','0.'))):
                    if 0 < len(candidate) <= 2048:
                        try:
                            parsed = urlsplit(candidate)
                            if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                                raise ValueError('not http(s)')
                            resolved = validate_url(urljoin(self.claimed_source, candidate))
                            base, target = urlsplit(self.claimed_source), urlsplit(resolved)
                            status = ('same_origin' if
                                (base.scheme.lower(), base.hostname, base.port) ==
                                (target.scheme.lower(), target.hostname, target.port)
                                else 'other_origin')
                            host = target.hostname
                            descriptor = raw_descriptor or None
                        except (ValueError, UnicodeError):
                            pass
            self.candidates.append({'element': tag, 'status': status,
                                    'target_host': host, 'descriptor': descriptor})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def inspect_offline_responsive_images(html_text: str, claimed_source: str) -> list[dict]:
    """Host-only static srcset inspection; no images/URLs are ever opened."""
    parser = _InertResponsiveImages(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.candidates



class _InertUsageHints(HTMLParser):
    """Bounded HTML robots/license *claims*, not verified usage permissions.

    Never resolve hosts over DNS, follow licenses or expose arbitrary metadata
    values. An HTML robots meta tag is not the site's robots.txt policy.
    """
    MAX_HINTS = 12
    ROBOTS_FLAGS = frozenset({'noindex', 'nofollow', 'noarchive', 'nosnippet', 'none'})

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.hints: list[dict] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in _VisibleText.HIDDEN:
                self.hidden.append(tag)
            return
        if tag in _VisibleText.HIDDEN:
            self.hidden.append(tag)
            return
        if len(self.hints) >= self.MAX_HINTS:
            return
        data = dict(attrs)
        if tag == 'meta' and (data.get('name') or '').strip().lower() == 'robots':
            raw = data.get('content')
            # Keep only a fixed vocabulary: no free-form content is retained.
            tokens = ([token.strip().lower() for token in raw.split(',')]
                      if isinstance(raw, str) and len(raw) <= 2048 else [])
            flags = sorted({token for token in tokens if token in self.ROBOTS_FLAGS})
            self.hints.append({'kind': 'robots', 'status': 'restricted' if flags else 'other',
                               'flags': flags, 'target_host': None})
        elif tag == 'link' and 'license' in (data.get('rel') or '').lower().split():
            raw = data.get('href')
            status, host = 'invalid', None
            if isinstance(raw, str) and 0 < len(raw.strip()) <= 2048:
                try:
                    candidate = raw.strip()
                    parsed = urlsplit(candidate)
                    if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                        raise ValueError('non-web license URI')
                    resolved = validate_url(urljoin(self.claimed_source, candidate))
                    origin, target = urlsplit(self.claimed_source), urlsplit(resolved)
                    status = ('same_origin' if
                              (origin.scheme.lower(), origin.hostname, origin.port) ==
                              (target.scheme.lower(), target.hostname, target.port)
                              else 'other_origin')
                    host = target.hostname
                except (ValueError, UnicodeError):
                    pass
            self.hints.append({'kind': 'license', 'status': status,
                               'flags': [], 'target_host': host})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _VisibleText.HIDDEN:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()


def inspect_offline_usage_hints(html_text: str, claimed_source: str) -> list[dict]:
    """Inert robots/license hint labels only; never infer legal rights."""
    parser = _InertUsageHints(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.hints



class _InertInlineCssReferences(HTMLParser):
    """Bounded best-effort CSS URL cues from local HTML; never execute CSS.

    Reads <style> text and style= attributes only. Ignores script/template/
    noscript/svg, CSS comments, and never includes URL path or query in output.
    A subset of CSS syntax is recognized, not a browser/CSS security audit.
    """
    MAX_REFERENCES = 12
    MAX_CSS_CHARS = 32768
    _URL = re.compile(r"url\s*\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)]*))\s*\)", re.I)
    _IMPORT = re.compile(r"@import\s+(['\"])(.*?)\1", re.I | re.S)
    _COMMENTS = re.compile(r"/\*.*?\*/", re.S)

    def __init__(self, claimed_source: str):
        super().__init__(convert_charrefs=True)
        self.claimed_source = validate_url(claimed_source)
        self.references: list[dict] = []
        self.hidden: list[str] = []
        self.in_style = False

    def _record(self, kind, candidate):
        if len(self.references) >= self.MAX_REFERENCES:
            return
        status, host = 'invalid', None
        if isinstance(candidate, str) and 0 < len(candidate.strip()) <= 2048:
            try:
                raw = candidate.strip()
                parsed = urlsplit(raw)
                if parsed.scheme and parsed.scheme.lower() not in ('http', 'https'):
                    raise ValueError('non-web CSS URL')
                resolved = validate_url(urljoin(self.claimed_source, raw))
                origin, target = urlsplit(self.claimed_source), urlsplit(resolved)
                status = ('same_origin' if
                          (origin.scheme.lower(), origin.hostname, origin.port) ==
                          (target.scheme.lower(), target.hostname, target.port)
                          else 'other_origin')
                host = target.hostname
            except (ValueError, UnicodeError):
                pass
        self.references.append({'kind':kind, 'status':status, 'target_host':host})

    def _css(self, raw: str):
        if not raw or len(self.references) >= self.MAX_REFERENCES:
            return
        if len(raw) > self.MAX_CSS_CHARS:
            # Too large to parse reliably within the bounded inspection.
            self._record('oversized', None)
            return
        css = self._COMMENTS.sub('', raw)
        matches = []
        for found in self._URL.finditer(css):
            matches.append((found.start(), found.end(), 'url', next((x for x in found.groups() if x is not None), '')))
        for found in self._IMPORT.finditer(css):
            if not any(start <= found.start() < end for start, end, _, _ in matches):
                matches.append((found.start(), found.end(), 'import', found.group(2)))
        for _, _, kind, value in sorted(matches):
            self._record(kind, value)
            if len(self.references) >= self.MAX_REFERENCES:
                break

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag in ('script', 'template', 'noscript', 'svg'):
                self.hidden.append(tag)
            return
        if tag in ('script', 'template', 'noscript', 'svg'):
            self.hidden.append(tag)
            return
        if tag == 'style':
            self.in_style = True
            return
        if not self.in_style and len(self.references) < self.MAX_REFERENCES:
            value = dict(attrs).get('style')
            if isinstance(value, str):
                self._css(value)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden:
            if self.hidden[-1] == tag:
                self.hidden.pop()
        elif tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if self.in_style and not self.hidden:
            self._css(data)


def inspect_offline_inline_css_references(html_text: str, claimed_source: str) -> list[dict]:
    """Inspect bounded inline CSS reference hints from a saved HTML string."""
    parser = _InertInlineCssReferences(claimed_source)
    parser.feed(html_text)
    parser.close()
    return parser.references


def _text(value, label, maximum):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or '\x00' in value:
        raise ValueError(f'{label}: 1~{maximum}자 입력이 필요합니다.')
    return value.strip()


def _id(value):
    if type(value) is not int or value <= 0:
        raise ValueError('올바른 자료 ID가 필요합니다.')
    return value


def validate_url(value):
    value = _text(value, '출처 URL', 2048)
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('URL에 공백이나 제어문자를 넣을 수 없습니다.')
    try:
        p = urlsplit(value)
        if p.scheme.lower() not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None:
            raise ValueError('http(s) 출처 주소만 등록할 수 있습니다.')
        if p.port is not None and p.port not in (80, 443):
            raise ValueError('비표준 포트는 출처에 등록할 수 없습니다.')
        # URL is provenance *metadata*, not a fetch or a verified online claim.
        host = p.hostname
        if host == 'localhost' or host.endswith('.localhost'):
            raise ValueError('로컬 주소는 웹 출처로 등록할 수 없습니다.')
        if p.fragment:
            value = urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))
        return value
    except (ValueError, UnicodeError) as exc:
        raise ValueError('유효한 http(s) 출처 URL을 입력해 주세요.') from exc


def extract_html(raw_html):
    raw_html = _text(raw_html, 'HTML 사본', MAX_RAW_BYTES)
    parser = _VisibleText()
    parser.feed(raw_html)
    parser.close()
    # Normalize layout and eliminate invisible instructions/code from indexed text.
    cleaned = '\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines())
    cleaned = '\n'.join(line for line in cleaned.splitlines() if line)
    return _text(cleaned, '추출된 본문', MAX_CONTENT)


def initialize(con: sqlite3.Connection) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS offline_research_captures (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       source_url TEXT NOT NULL CHECK(length(source_url) BETWEEN 8 AND 2048),
       title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 200),
       body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 60000),
       capture_kind TEXT NOT NULL CHECK(capture_kind IN ('manual_text','html_snapshot')),
       content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
       source_verification TEXT NOT NULL DEFAULT 'unverified'
           CHECK(source_verification = 'unverified'),
       recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
       archived_at TEXT,
       UNIQUE(source_url,content_sha256)
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS offline_research_no_delete
       BEFORE DELETE ON offline_research_captures BEGIN
       SELECT RAISE(ABORT,'research evidence cannot be deleted'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS offline_research_immutable
       BEFORE UPDATE ON offline_research_captures BEGIN
       SELECT RAISE(ABORT,'research evidence is immutable except archive')
       WHERE OLD.source_url IS NOT NEW.source_url OR OLD.title IS NOT NEW.title
          OR OLD.body IS NOT NEW.body OR OLD.capture_kind IS NOT NEW.capture_kind
          OR OLD.content_sha256 IS NOT NEW.content_sha256
          OR OLD.source_verification IS NOT NEW.source_verification
          OR OLD.recorded_at IS NOT NEW.recorded_at
          OR OLD.archived_at IS NOT NULL OR NEW.archived_at IS NULL;
       END''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_offline_research_date ON offline_research_captures(id DESC)')
    # Passive outbound URL inventory for freshly registered HTML snapshots.
    # Historical HTML source bytes were not retained; do not fabricate backfills.
    con.execute('''CREATE TABLE IF NOT EXISTS offline_research_html_links (
       capture_id INTEGER NOT NULL REFERENCES offline_research_captures(id),
       position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 100),
       linked_url TEXT NOT NULL CHECK(length(linked_url) BETWEEN 8 AND 2048),
       source_verification TEXT NOT NULL DEFAULT 'unverified'
            CHECK(source_verification='unverified'),
       PRIMARY KEY(capture_id,position),
       UNIQUE(capture_id,linked_url)
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS offline_research_html_links_no_update
       BEFORE UPDATE ON offline_research_html_links BEGIN
       SELECT RAISE(ABORT,'offline link inventory is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS offline_research_html_links_no_delete
       BEFORE DELETE ON offline_research_html_links BEGIN
       SELECT RAISE(ABORT,'offline link inventory cannot be deleted'); END''')
    # Stage54 continuation: local source *file* custody, separate from text hash.
    # Do not change, republish or reinterpret older captures on migration.
    con.execute('''CREATE TABLE IF NOT EXISTS offline_research_local_imports (
       capture_id INTEGER PRIMARY KEY REFERENCES offline_research_captures(id),
       original_filename TEXT NOT NULL CHECK(length(original_filename) BETWEEN 1 AND 255),
       raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64),
       raw_size INTEGER NOT NULL CHECK(raw_size BETWEEN 1 AND 256000),
       imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS offline_research_import_no_update
       BEFORE UPDATE ON offline_research_local_imports BEGIN
       SELECT RAISE(ABORT,'import provenance is immutable'); END''')
    con.execute('''CREATE TRIGGER IF NOT EXISTS offline_research_import_no_delete
       BEFORE DELETE ON offline_research_local_imports BEGIN
       SELECT RAISE(ABORT,'import provenance cannot be deleted'); END''')
    # Each offline manifest binds a set of local artifacts to their claimed URLs.
    # Neither a URL nor a manifest is proof that an online source is authentic.
    con.execute('''CREATE TABLE IF NOT EXISTS offline_research_batches (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       manifest_filename TEXT NOT NULL,
       manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
       item_count INTEGER NOT NULL CHECK(item_count BETWEEN 1 AND 20),
       imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS offline_research_batch_items (
       batch_id INTEGER NOT NULL REFERENCES offline_research_batches(id),
       capture_id INTEGER NOT NULL UNIQUE REFERENCES offline_research_captures(id),
       ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 20),
       PRIMARY KEY(batch_id,ordinal)
    )''')
    for table in ('offline_research_batches', 'offline_research_batch_items'):
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_update
           BEFORE UPDATE ON {table} BEGIN
           SELECT RAISE(ABORT,'research bundle provenance is immutable'); END''')
        con.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_delete
           BEFORE DELETE ON {table} BEGIN
           SELECT RAISE(ABORT,'research bundle provenance is immutable'); END''')
    # Separate append-only owner review annotations; never alter old evidence.
    from desktop.research_followup_notes import initialize as initialize_followup_notes
    initialize_followup_notes(con)




def add(con, source_url, title, raw_content, capture_kind='manual_text'):
    source_url = validate_url(source_url)
    title = _text(title, '제목', 200)
    if capture_kind not in ('manual_text', 'html_snapshot'):
        raise ValueError('자료 등록 방식을 선택해 주세요.')
    if capture_kind == 'html_snapshot':
        body = extract_html(raw_content)
    else:
        body = _text(raw_content, '본문', MAX_CONTENT)
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
    try:
        capture_id = con.execute('''INSERT INTO offline_research_captures
             (source_url,title,body,capture_kind,content_sha256)
             VALUES(?,?,?,?,?)''', (source_url,title,body,capture_kind,digest)).lastrowid
        if capture_kind == 'html_snapshot':
            for position, linked_url in enumerate(extract_offline_links(raw_content, source_url), 1):
                con.execute('''INSERT INTO offline_research_html_links
                    (capture_id,position,linked_url) VALUES(?,?,?)''',
                    (capture_id,position,linked_url))
        return capture_id
    except sqlite3.IntegrityError as exc:
        raise ValueError('같은 출처 URL과 본문의 자료가 이미 등록되어 있습니다.') from exc


def read_local_snapshot(path):
    """Read an explicitly supplied local text/HTML file; never fetch a URL.

    Raw bytes are hashed before UTF-8 decoding and extraction. This records the
    *local file bytes*, not the authenticity of the claimed web source.
    """
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError('로컬 자료 파일 경로가 필요합니다.')
    path_text = os.fspath(path)
    if not path_text or '\x00' in path_text or path_text.startswith(('\\\\', '//')):
        raise ValueError('네트워크 공유 경로나 잘못된 경로는 허용하지 않습니다.')
    item = Path(path_text)
    if not item.is_absolute():
        raise ValueError('절대 경로의 로컬 자료 파일만 가져올 수 있습니다.')
    if os.name == 'nt':
        # A Windows drive letter can denote a mapped SMB share: reject it too.
        # DRIVE_REMOTE=4; do not resolve a remote path to check it.
        import ctypes
        from ctypes import wintypes
        root = item.anchor
        if not root:
            raise ValueError('로컬 드라이브 경로가 필요합니다.')
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(wintypes.LPCWSTR(root))
        if drive_type in (0, 1, 4):
            raise ValueError('확인되지 않은 드라이브 또는 네트워크 드라이브는 허용하지 않습니다.')
    if len(item.name) > 255:
        raise ValueError('파일 이름은 255자를 넘길 수 없습니다.')
    if item.suffix.lower() not in ('.txt', '.md', '.html', '.htm'):
        raise ValueError('txt, md, html, htm 파일만 가져올 수 있습니다.')
    if item.is_symlink():
        raise ValueError('심볼릭 링크 파일은 가져올 수 없습니다.')
    try:
        # O_NOFOLLOW protects the final file from replacement on POSIX.
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(item, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('일반 파일만 가져올 수 있습니다.')
            if before.st_size <= 0 or before.st_size > MAX_RAW_BYTES:
                raise ValueError('빈 파일 또는 256KB 초과 파일은 가져올 수 없습니다.')
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                raw = handle.read(MAX_RAW_BYTES + 1)
            after = os.fstat(fd)
            if (len(raw) != before.st_size or len(raw) > MAX_RAW_BYTES or
                    (before.st_size, before.st_mtime_ns, before.st_ino) !=
                    (after.st_size, after.st_mtime_ns, after.st_ino)):
                raise ValueError('읽는 동안 변경된 파일은 가져올 수 없습니다.')
        finally:
            os.close(fd)
    except OSError as exc:
        raise ValueError('로컬 자료 파일을 안전하게 읽을 수 없습니다.') from exc
    try:
        contents = raw.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc:
        raise ValueError('UTF-8 텍스트 파일만 지원합니다.') from exc
    if item.suffix.lower() in ('.html', '.htm'):
        kind = 'html_snapshot'
        # Validate content before inserting any evidence row.
        extract_html(contents)
    else:
        kind = 'manual_text'
        _text(contents, '본문', MAX_CONTENT)
    return contents, kind, item.name, hashlib.sha256(raw).hexdigest(), len(raw)


def add_local_file(con, source_url, title, path):
    contents, kind, filename, raw_hash, byte_length = read_local_snapshot(path)
    ident = add(con, source_url, title, contents, kind)
    con.execute('''INSERT INTO offline_research_local_imports
        (capture_id,original_filename,raw_sha256,raw_size)
        VALUES (?,?,?,?)''', (ident,filename,raw_hash,byte_length))
    return ident



def _portable_bundle_filename(filename: str) -> str:
    """Return a case-insensitive Windows collision key for an inert bundle name.

    Check on *all* development platforms: a bundle created on Linux must be
    usable on Windows without reserved DOS devices, alternate data streams,
    trailing-dot normalization or case-insensitive name collisions. This is a
    path-component check only; callers separately enforce local paths/ACLs.
    """
    if (not isinstance(filename, str) or not 1 <= len(filename) <= 255 or
            filename in ('.', '..') or filename[-1] in (' ', '.') or
            any(ord(char) < 32 or char in '<>:"/\\|?*' for char in filename)):
        raise ValueError('Windows에서 사용할 수 없는 자료 묶음 파일 이름입니다.')
    # Windows treats CON.txt, AUX.htm, COM1.json (etc.) as device names.
    # The superscript digit forms are also recognized as device aliases.
    stem = filename.split('.', 1)[0].upper()
    if stem in {'CON', 'PRN', 'AUX', 'NUL'} or (len(stem) == 4 and
            stem[:3] in {'COM', 'LPT'} and stem[3] in '123456789¹²³'):
        raise ValueError('Windows 예약 장치 이름은 자료 묶음에서 사용할 수 없습니다.')
    return filename.casefold()


class DuplicateJSONKeyError(ValueError):
    """A local custody JSON object repeats a member name."""


def _unique_json_members(pairs):
    """Reject ambiguous duplicate JSON object keys at *every* nesting level.

    The default JSON decoder silently keeps the last value. For manually
    supplied research manifests and local custody receipts this can make an
    owner approve one interpretation of an ambiguous artifact. This validates
    keys before any import, without changing the established v1 JSON schema.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError('JSON 객체에 중복된 키가 있습니다.')
        result[key] = value
    return result


def _read_local_manifest_entries(path):
    """Safely read local manifest *metadata* without requiring its source files.

    An imported bundle can be audited when original files were moved or lost;
    audit must report those cases rather than fail while parsing the manifest.
    """
    if not isinstance(path, (str, os.PathLike)):
        raise ValueError('로컬 JSON 목록 파일 경로를 지정해 주세요.')
    value = os.fspath(path)
    if not value or '\x00' in value or value.startswith(('\\\\', '//')):
        raise ValueError('네트워크 공유 경로는 사용할 수 없습니다.')
    item = Path(value)
    if not item.is_absolute() or item.suffix.lower() != '.json':
        raise ValueError('로컬 JSON 파일의 절대 경로가 필요합니다.')
    _portable_bundle_filename(item.name)
    if item.is_symlink():
        raise ValueError('심볼릭 링크 파일은 사용할 수 없습니다.')
    # No symlink parent may redirect the whole bundle outside the chosen directory.
    if any(parent.is_symlink() for parent in item.parents):
        raise ValueError('심볼릭 링크 폴더에서는 가져올 수 없습니다.')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        drive = ctypes.windll.kernel32.GetDriveTypeW(wintypes.LPCWSTR(item.anchor))
        if drive in (0, 1, 4):
            raise ValueError('네트워크 드라이브를 사용할 수 없습니다.')
    try:
        fd = os.open(item, os.O_RDONLY | getattr(os, 'O_BINARY', 0) |
                     getattr(os, 'O_NOFOLLOW', 0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= 32_768:
                raise ValueError('JSON 목록 파일은 1~32KB여야 합니다.')
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                data = handle.read(32_769)
            after = os.fstat(fd)
            if len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino) != (
                after.st_size, after.st_mtime_ns, after.st_ino):
                raise ValueError('읽는 중 변경된 목록 파일은 허용하지 않습니다.')
        finally:
            os.close(fd)
    except OSError as exc:
        raise ValueError('로컬 JSON 목록을 안전하게 읽을 수 없습니다.') from exc
    try:
        manifest = json.loads(data.decode('utf-8-sig', errors='strict'),
                              object_pairs_hook=_unique_json_members)
    except DuplicateJSONKeyError as exc:
        raise ValueError('JSON 목록에 중복된 키가 있습니다.') from exc
    except (UnicodeError, ValueError) as exc:
        raise ValueError('UTF-8 JSON 목록 파일이 올바르지 않습니다.') from exc
    if not isinstance(manifest, dict) or set(manifest) != {'format', 'items'} or (
        manifest.get('format') != 'aiwack-offline-research-bundle-v1'):
        raise ValueError('지원하지 않는 오프라인 묶음 목록 형식입니다.')
    entries = manifest.get('items')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
        raise ValueError('한 묶음은 1~20개 자료로 구성해야 합니다.')
    seen = set()
    validated = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'file', 'url', 'title'}:
            raise ValueError('각 목록 항목에는 file, url, title만 입력할 수 있습니다.')
        filename = entry['file']
        collision_key = _portable_bundle_filename(filename)
        if collision_key in seen or collision_key == item.name.casefold():
            raise ValueError('Windows에서 충돌하는 중복 파일 이름이나 목록 파일 자체는 등록할 수 없습니다.')
        seen.add(collision_key)
        url = validate_url(entry['url'])
        title = _text(entry['title'], '제목', 200)
        validated.append((filename, url, title))
    return item.name, hashlib.sha256(data).hexdigest(), item.parent, validated


def _read_local_manifest(path):
    filename, manifest_sha256, parent, entries = _read_local_manifest_entries(path)
    prepared = []
    for basename, url, title in entries:
        # read_local_snapshot validates size, symlinks, type, UTF-8, and hash.
        contents, kind, safe_name, digest, size = read_local_snapshot(parent / basename)
        prepared.append((url, title, contents, kind, safe_name, digest, size))
    return filename, manifest_sha256, prepared


def verify_imported_local_bundle(con: sqlite3.Connection, manifest_path) -> dict:
    """Read-only custody audit of up to 20 already-imported local bundle files.

    Looks up the exact JSON manifest bytes recorded in SQLite, then compares
    each *explicitly selected local* file against immutable recorded hashes.
    No URL is fetched. A matching hash cannot authenticate a web publisher or
    establish that the chosen directory is the original source directory.
    """
    filename, manifest_hash, parent, entries = _read_local_manifest_entries(manifest_path)
    batch = con.execute("""SELECT id, manifest_filename, item_count
        FROM offline_research_batches WHERE manifest_sha256=? ORDER BY id DESC LIMIT 1""",
        (manifest_hash,)).fetchone()
    if batch is None:
        raise ValueError('이 JSON 목록의 등록된 로컬 자료 묶음 이력이 없습니다.')
    batch_id, recorded_filename, item_count = batch
    rows = con.execute("""SELECT i.ordinal, c.id, c.source_url, c.title,
            l.original_filename, l.raw_sha256, l.raw_size, c.archived_at
        FROM offline_research_batch_items AS i
        LEFT JOIN offline_research_captures AS c ON c.id=i.capture_id
        LEFT JOIN offline_research_local_imports AS l ON l.capture_id=i.capture_id
        WHERE i.batch_id=? ORDER BY i.ordinal""", (batch_id,)).fetchall()
    by_ordinal = {row[0]: row for row in rows}
    results = []
    counts = {'match': 0, 'changed': 0, 'unavailable': 0, 'record_mismatch': 0}
    for ordinal, (basename, url, title) in enumerate(entries, 1):
        row = by_ordinal.get(ordinal)
        record_id = row[1] if row is not None else None
        if (row is None or row[2] != url or row[3] != title or row[4] != basename or
                not isinstance(row[5], str) or not isinstance(row[6], int)):
            status = 'record_mismatch'
            details = 'SQLite 등록 이력의 항목 정보가 목록과 일치하지 않습니다.'
        else:
            try:
                # File can be missing, changed, inaccessible, or symlinked.
                _, _, _, actual_hash, actual_size = read_local_snapshot(parent / basename)
            except (ValueError, OSError) as exc:
                status = 'unavailable'
                details = f'로컬 파일을 안전하게 읽거나 검증할 수 없습니다: {exc}'
            else:
                if actual_hash == row[5] and actual_size == row[6]:
                    status = 'match'
                    details = '등록 당시 기록된 원본 파일 바이트의 SHA-256과 크기가 일치합니다.'
                else:
                    status = 'changed'
                    details = '등록 당시 기록된 원본 파일 바이트와 내용 또는 크기가 다릅니다.'
        counts[status] += 1
        results.append({'ordinal': ordinal, 'capture_id': record_id,
                        'filename': basename, 'status': status, 'details': details,
                        'archived': bool(row[7]) if row else None})
    # Detect missing/extra batch relations too, not only per-file mismatches.
    structure_ok = (recorded_filename == filename and item_count == len(entries)
                    and len(rows) == len(entries)
                    and set(by_ordinal) == set(range(1, len(entries) + 1)))
    return {'batch_id': batch_id, 'manifest_filename': filename,
            'manifest_sha256': manifest_hash, 'item_count': len(entries),
            'records_consistent': structure_ok and counts['record_mismatch'] == 0,
            'passed': structure_ok and counts['match'] == len(entries),
            'counts': counts, 'items': results, 'network_accessed': False,
            'database_modified': False, 'web_source_verified': False,
            'original_folder_authenticated': False}




def _bundle_html_links(prepared):
    """Read inert HTML hyperlinks from owner-supplied local bytes, max 2,000.

    Claimed URLs are never fetched or DNS-resolved. Keep source order and
    duplicates across distinct HTML documents; one document caps at 100 URLs.
    """
    result = []
    for ordinal, (url, _, contents, kind, _, _, _) in enumerate(prepared, 1):
        if kind == 'html_snapshot':
            result.extend((ordinal, linked) for linked in extract_offline_links(contents, url))
    return result


def _bundle_link_preview(con: sqlite3.Connection, prepared) -> dict:
    """Read-only snapshot of a candidate bundle's passive outbound links."""
    links = _bundle_html_links(prepared)
    registered = {}
    unique = sorted({url for _, url in links})
    # Chunk to fit even older SQLite's 999-variable limit. No network calls.
    for start in range(0, len(unique), 300):
        chunk = unique[start:start + 300]
        sql = ('SELECT id, source_url, archived_at FROM offline_research_captures '
               'WHERE source_url IN (' + ','.join('?' for _ in chunk) + ') ORDER BY id')
        for ident, url, archived_at in con.execute(sql, chunk):
            bucket = registered.setdefault(url, {'active': [], 'archived': []})
            bucket['archived' if archived_at is not None else 'active'].append(ident)
    bundle_ordinal = {}
    for ordinal, (url, *_rest) in enumerate(prepared, 1):
        bundle_ordinal.setdefault(url, []).append(ordinal)
    totals = dict(in_bundle=0, registered_active=0, registered_archived=0, unregistered=0)
    examples = {}
    per_source = {}
    for source_ordinal, linked in links:
        bundle_matches = bundle_ordinal.get(linked, [])
        db_matches = registered.get(linked, {})
        if bundle_matches:
            status = 'in_bundle'
            witnesses = bundle_matches[:3]
        elif db_matches.get('active'):
            status = 'registered_active'
            witnesses = db_matches['active'][:3]
        elif db_matches.get('archived'):
            status = 'registered_archived'
            witnesses = db_matches['archived'][:3]
        else:
            status = 'unregistered'
            witnesses = []
        totals[status] += 1
        per_source.setdefault(source_ordinal, dict(in_bundle=0, registered_active=0,
                                                   registered_archived=0, unregistered=0))[status] += 1
        target = examples.setdefault(source_ordinal, [])
        if len(target) < 5:
            target.append({'linked_url': linked, 'status': status, 'candidate_ids_or_ordinals': witnesses})
    return {'link_count': len(links), 'status_counts': totals,
            'by_source': per_source, 'examples_by_source': examples,
            'max_links_per_html': 100, 'web_source_verified': False,
            'network_accessed': False}

def _bundle_database_fingerprint(con: sqlite3.Connection, prepared) -> str:
    """Stable read-only fingerprint of local records affecting bundle warnings.

    Captures are immutable apart from archiving, which does not affect our
    warning types.  Include both matching claimed URLs and body hashes so a
    newly inserted *different version* is detected before owner-approved
    import, not just a UNIQUE constraint conflict.  Stream query rows instead
    of materializing full bodies or visiting the network.
    """
    sources = set()
    bodies = set()
    for source, _, content, kind, _, _, _ in prepared:
        body = extract_html(content) if kind == 'html_snapshot' else _text(content, '본문', MAX_CONTENT)
        sources.add(source)
        bodies.add(hashlib.sha256(body.encode('utf-8')).hexdigest())
    # Also bind HTML link target registration to the owner's approval token.
    # A target added/archived while the approval dialog is open may change the
    # link classification and must be shown again before import.
    link_sources = {url for _, url in _bundle_html_links(prepared)}
    candidates = {}
    for column, values in (('source_url', sources | link_sources),
                           ('content_sha256', bodies)):
        ordered = sorted(values)
        for offset in range(0, len(ordered), 300):
            segment = ordered[offset:offset + 300]
            sql = ('SELECT id, source_url, content_sha256, archived_at FROM offline_research_captures '
                   'WHERE ' + column + ' IN (' + ','.join('?' for _ in segment) + ')')
            for ident, source, body_hash, archived in con.execute(sql, segment):
                candidates[ident] = (source, body_hash, archived)
    digest = hashlib.sha256(b'aiwack-bundle-local-context-v2\n')
    for ident, (source, body_hash, archived) in sorted(candidates.items()):
        # Preserve historical archive-insensitive approval behavior for
        # primary URL/body matches; bind archive changes for HTML link targets.
        link_archive = archived is not None if source in link_sources else None
        record = json.dumps([ident, source, body_hash, link_archive], ensure_ascii=False,
                            separators=(',', ':')).encode('utf-8')
        digest.update(len(record).to_bytes(4, 'big'))
        digest.update(record)
    return digest.hexdigest()


def _bundle_preview_token(manifest_sha256, prepared, database_fingerprint=None):
    """Local equality marker binding files and relevant SQLite evidence.

    Not a digital signature or a guarantee about the web. Only guarded
    imports with explicit owner confirmation use the DB-bound form.
    """
    entries = []
    for url, title, content, kind, name, raw_sha, size in prepared:
        body = extract_html(content) if kind == 'html_snapshot' else _text(content, '본문', MAX_CONTENT)
        entries.append([url, title, kind, name, raw_sha, size,
                        hashlib.sha256(body.encode('utf-8')).hexdigest()])
    payload = json.dumps([manifest_sha256, entries, database_fingerprint], ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def preview_local_bundle(con: sqlite3.Connection, manifest_path) -> dict:
    """Read-only dry run before a deliberate import. No DB or network writes.

    A preview is NOT a reservation. Guarded import re-reads and verifies all
    bytes and metadata; a concurrent DB insertion still fails atomically.
    """
    filename, manifest_hash, prepared = _read_local_manifest(manifest_path)
    context_hash = _bundle_database_fingerprint(con, prepared)
    token = _bundle_preview_token(manifest_hash, prepared, context_hash)
    items = []
    seen = {}
    duplicate_count = 0
    for index, (url, title, contents, kind, basename, rawhash, size) in enumerate(prepared, 1):
        body = extract_html(contents) if kind == 'html_snapshot' else _text(contents, '본문', MAX_CONTENT)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        key = (url, digest)
        conflict = con.execute('SELECT id FROM offline_research_captures '
                               'WHERE source_url=? AND content_sha256=?', key).fetchone()
        in_batch = seen.get(key)
        if conflict is not None:
            state = 'already_registered'
            existing_id = conflict[0]
        elif in_batch is not None:
            state = 'duplicate_in_bundle'
            existing_id = None
        else:
            state = 'new'
            existing_id = None
        if state != 'new':
            duplicate_count += 1
        seen.setdefault(key, index)
        # A claimed URL and body hash are only local metadata.  Never contact
        # the URL or assume independent origins when hashes match.
        items.append({'ordinal': index, 'filename': basename, 'title': title,
                      'claimed_source_url': url, 'kind': kind, 'raw_size': size,
                      'raw_sha256': rawhash, 'content_sha256': digest,
                      'status': state, 'existing_capture_id': existing_id,
                      'duplicate_of_ordinal': in_batch if state == 'duplicate_in_bundle' else None})

    # Separate warnings from exact duplicate blocking.  A version difference
    # may be legitimate, but must be visible before the owner's import approval.
    # Each per-item SQL query is bounded and supports archived rows as evidence.
    warning_items = 0
    warning_totals = {
        'existing_url_other_body': 0, 'existing_body_other_url': 0,
        'bundle_url_other_body': 0, 'bundle_body_other_url': 0,
    }
    for item in items:
        url, digest = item['claimed_source_url'], item['content_sha256']
        witnesses = {
            'existing_url_other_body': [row[0] for row in con.execute(
                'SELECT id FROM offline_research_captures '
                'WHERE source_url=? AND content_sha256<>? ORDER BY id DESC LIMIT 3',
                (url, digest)).fetchall()],
            'existing_body_other_url': [row[0] for row in con.execute(
                'SELECT id FROM offline_research_captures '
                'WHERE content_sha256=? AND source_url<>? ORDER BY id DESC LIMIT 3',
                (digest, url)).fetchall()],
            'bundle_url_other_body': [other['ordinal'] for other in items
                if other['ordinal'] != item['ordinal'] and
                other['claimed_source_url'] == url and other['content_sha256'] != digest][:3],
            'bundle_body_other_url': [other['ordinal'] for other in items
                if other['ordinal'] != item['ordinal'] and
                other['content_sha256'] == digest and other['claimed_source_url'] != url][:3],
        }
        item['warnings'] = [code for code, references in witnesses.items() if references]
        # IDs and manifest ordinals are bounded *examples*, not total counts.
        item['warning_examples'] = {code: references for code, references in witnesses.items()
                                    if references}
        if item['warnings']:
            warning_items += 1
            for code in item['warnings']:
                warning_totals[code] += 1
    # Reuse the passive URL-string classifier *before* owner approval, not
    # only after links are already stored. Do not resolve hosts or fetch URLs.
    # Keep provenance/content warnings separate from URL preflight warnings.
    from desktop.research_url_preflight import classify_stored_url
    url_warning_counts = {}
    url_warning_items = 0
    for item in items:
        codes = list(classify_stored_url(item['claimed_source_url']))
        item['url_warning_codes'] = codes
        if codes:
            url_warning_items += 1
        for code in codes:
            url_warning_counts[code] = url_warning_counts.get(code, 0) + 1
    # A saved HTML page can itself *claim* a different canonical identity.
    # Report the disagreement before import; never rewrite owner metadata.
    source_hint_totals = dict(match=0, mismatch=0, invalid=0)
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        hints = inspect_offline_source_hints(contents, url) if kind == 'html_snapshot' else []
        item['source_hint_count'] = len(hints)
        item['source_hint_examples'] = hints[:4]
        item['source_hint_status_counts'] = {code: sum(h['status'] == code for h in hints)
                                             for code in source_hint_totals}
        for code in source_hint_totals:
            source_hint_totals[code] += item['source_hint_status_counts'][code]
    # HTML <base> and meta refresh are inert here, but would affect navigation
    # if the saved file were opened in a real browser. Warn prior to approval.
    navigation_totals = dict(same_origin=0, other_origin=0, invalid=0)
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        directives = inspect_offline_navigation_directives(contents, url) if kind == 'html_snapshot' else []
        item['navigation_directive_count'] = len(directives)
        item['navigation_directive_examples'] = directives[:4]
        item['navigation_directive_status_counts'] = {
            code: sum(d['status'] == code for d in directives) for code in navigation_totals}
        for code in navigation_totals:
            navigation_totals[code] += item['navigation_directive_status_counts'][code]
    # Flag HTML elements which could POST or load external resources if a
    # person later opened this archive in a browser. Nothing is executed.
    active_target_totals = dict(same_origin=0, other_origin=0, invalid=0)
    active_target_kind_totals = dict(form=0, iframe=0, script=0)
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        targets = inspect_offline_active_targets(contents, url) if kind == 'html_snapshot' else []
        item['active_target_count'] = len(targets)
        item['active_target_examples'] = targets[:4]
        item['active_target_status_counts'] = {
            code: sum(t['status'] == code for t in targets) for code in active_target_totals}
        for code in active_target_totals:
            active_target_totals[code] += item['active_target_status_counts'][code]
        for code in active_target_kind_totals:
            active_target_kind_totals[code] += sum(t['kind'] == code for t in targets)
    # Sensitive-looking input *types* in an archived HTML form are useful
    # manual-review cues, especially password controls in a GET form.  This
    # scan never stores actual input values or attempts to submit the form.
    form_control_totals = dict(password=0, file=0, hidden=0)
    password_get_total = 0
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        controls = inspect_offline_form_controls(contents) if kind == 'html_snapshot' else []
        item['form_control_count'] = len(controls)
        item['form_control_examples'] = controls[:4]
        item['form_control_kind_counts'] = {
            code: sum(c['kind'] == code for c in controls) for code in form_control_totals}
        item['form_password_get_count'] = sum(c['password_in_get'] for c in controls)
        password_get_total += item['form_password_get_count']
        for code in form_control_totals:
            form_control_totals[code] += item['form_control_kind_counts'][code]
    # Passive image, stylesheet and media sources can cause unexpected requests
    # when a user opens an archived HTML page in a browser. Never open them here.
    passive_status_totals = dict(same_origin=0, other_origin=0, invalid=0)
    passive_kind_totals = dict(image=0, stylesheet=0, media=0)
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        resources = inspect_offline_passive_resources(contents, url) if kind == 'html_snapshot' else []
        item['passive_resource_count'] = len(resources)
        item['passive_resource_examples'] = resources[:4]
        item['passive_resource_status_counts'] = {
            code: sum(x['status'] == code for x in resources) for code in passive_status_totals}
        item['passive_resource_kind_counts'] = {
            code: sum(x['kind'] == code for x in resources) for code in passive_kind_totals}
        for code in passive_status_totals:
            passive_status_totals[code] += item['passive_resource_status_counts'][code]
        for code in passive_kind_totals:
            passive_kind_totals[code] += item['passive_resource_kind_counts'][code]
    # Responsive image candidates are separate from src/poster so existing
    # passive resource results do not change.  No media is fetched.
    responsive_totals = dict(same_origin=0, other_origin=0, invalid=0)
    responsive_element_totals = dict(img=0, source=0)
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        candidates = inspect_offline_responsive_images(contents, url) if kind == 'html_snapshot' else []
        item['responsive_image_count'] = len(candidates)
        item['responsive_image_examples'] = candidates[:4]
        item['responsive_image_status_counts'] = {
            code: sum(x['status'] == code for x in candidates) for code in responsive_totals}
        item['responsive_image_element_counts'] = {
            code: sum(x['element'] == code for x in candidates) for code in responsive_element_totals}
        for code in responsive_totals:
            responsive_totals[code] += item['responsive_image_status_counts'][code]
        for code in responsive_element_totals:
            responsive_element_totals[code] += item['responsive_image_element_counts'][code]
    # Robots meta and rel=license are author-controlled hints, not verified
    # license grants or crawler policy. Keep only allowlisted flags and hosts.
    usage_kind_totals = dict(robots=0, license=0)
    usage_status_totals = dict(restricted=0, other=0, same_origin=0,
                               other_origin=0, invalid=0)
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        hints = inspect_offline_usage_hints(contents, url) if kind == 'html_snapshot' else []
        item['usage_hint_count'] = len(hints)
        item['usage_hint_examples'] = hints[:4]
        item['usage_hint_kind_counts'] = {
            code: sum(h['kind'] == code for h in hints) for code in usage_kind_totals}
        item['usage_hint_status_counts'] = {
            code: sum(h['status'] == code for h in hints) for code in usage_status_totals}
        for code in usage_kind_totals:
            usage_kind_totals[code] += item['usage_hint_kind_counts'][code]
        for code in usage_status_totals:
            usage_status_totals[code] += item['usage_hint_status_counts'][code]
    # HTML inline CSS may reference external assets even when no <img>/<link>
    # attribute does. Only host/status labels; never fetch, parse imported CSS
    # files, or interpret CSS as a browser would.
    css_status_totals = dict(same_origin=0, other_origin=0, invalid=0)
    css_kind_totals = {'url': 0, 'import': 0, 'oversized': 0}
    for item, (url, _, contents, kind, _, _, _) in zip(items, prepared):
        cues = inspect_offline_inline_css_references(contents, url) if kind == 'html_snapshot' else []
        item['css_reference_count'] = len(cues)
        item['css_reference_examples'] = cues[:4]
        item['css_reference_status_counts'] = {
            code: sum(c['status'] == code for c in cues) for code in css_status_totals}
        item['css_reference_kind_counts'] = {
            code: sum(c['kind'] == code for c in cues) for code in css_kind_totals}
        for code in css_status_totals:
            css_status_totals[code] += item['css_reference_status_counts'][code]
        for code in css_kind_totals:
            css_kind_totals[code] += item['css_reference_kind_counts'][code]
    html_links = _bundle_link_preview(con, prepared)
    for item in items:
        item['html_link_count'] = sum(html_links['by_source'].get(item['ordinal'], {}).values())
        item['html_link_status_counts'] = html_links['by_source'].get(item['ordinal'], dict(
            in_bundle=0, registered_active=0, registered_archived=0, unregistered=0))
        item['html_link_examples'] = html_links['examples_by_source'].get(item['ordinal'], [])
    return {'manifest_filename': filename, 'manifest_sha256': manifest_hash,
            'preview_token': token, 'local_context_sha256': context_hash,
            'html_link_count': html_links['link_count'],
            'html_link_status_counts': html_links['status_counts'],
            'source_hint_count': sum(source_hint_totals.values()),
            'source_hint_status_counts': source_hint_totals,
            'source_hints_are_unverified': True,
            'navigation_directive_count': sum(navigation_totals.values()),
            'navigation_directive_status_counts': navigation_totals,
            'navigation_directives_inert': True,
            'active_target_count': sum(active_target_totals.values()),
            'active_target_status_counts': active_target_totals,
            'active_target_kind_counts': active_target_kind_totals,
            'active_targets_inert': True,
            'form_control_count': sum(form_control_totals.values()),
            'form_control_kind_counts': form_control_totals,
            'form_password_get_count': password_get_total,
            'form_controls_inert': True,
            'form_values_captured': False,
            'passive_resource_count': sum(passive_status_totals.values()),
            'passive_resource_status_counts': passive_status_totals,
            'passive_resource_kind_counts': passive_kind_totals,
            'passive_resources_inert': True,
            'passive_resource_full_urls_exposed': False,
            'responsive_image_count': sum(responsive_totals.values()),
            'responsive_image_status_counts': responsive_totals,
            'responsive_image_element_counts': responsive_element_totals,
            'responsive_images_inert': True,
            'responsive_image_full_urls_exposed': False,
            'css_reference_count': sum(css_status_totals.values()),
            'css_reference_status_counts': css_status_totals,
            'css_reference_kind_counts': css_kind_totals,
            'css_references_inert': True,
            'css_full_urls_exposed': False,
            'usage_hint_count': sum(usage_kind_totals.values()),
            'usage_hint_kind_counts': usage_kind_totals,
            'usage_hint_status_counts': usage_status_totals,
            'usage_hints_unverified': True,
            'usage_hint_full_urls_exposed': False,
            'html_links_are_unverified': True,
            'item_count': len(items), 'duplicate_count': duplicate_count,
            'importable': duplicate_count == 0, 'items': items,
            'warning_item_count': warning_items, 'warning_category_counts': warning_totals,
            'url_warning_item_count': url_warning_items,
            'url_warning_category_counts': dict(sorted(url_warning_counts.items())),
            'url_preflight_is_string_only': True, 'dns_checked': False,
            'safe_to_fetch_verified': False,
            'database_modified': False, 'network_accessed': False,
            'web_source_verified': False, 'approval_is_signature': False}


def add_local_bundle(con, manifest_path, *, expected_preview_token=None):
    """Atomically import; optional approval token binds manifest AND file bytes."""
    filename, manifest_sha256, prepared = _read_local_manifest(manifest_path)
    if expected_preview_token is not None:
        import hmac
        if (not isinstance(expected_preview_token, str) or
                len(expected_preview_token) != 64 or
                not expected_preview_token.isascii()):
            raise ValueError('사전 검토 정보가 유효하지 않습니다. 다시 검토해 주세요.')
        fingerprint = _bundle_database_fingerprint(con, prepared)
        current_token = _bundle_preview_token(manifest_sha256, prepared, fingerprint)
        if not hmac.compare_digest(current_token, expected_preview_token):
            # Keep the former exact-duplicate error intelligible to callers;
            # no inserts have occurred yet, and BEGIN IMMEDIATE prevents races.
            for url, _, content, kind, _, _, _ in prepared:
                body = extract_html(content) if kind == 'html_snapshot' else _text(content, '본문', MAX_CONTENT)
                digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
                if con.execute('SELECT 1 FROM offline_research_captures '
                               'WHERE source_url=? AND content_sha256=?',
                               (url, digest)).fetchone():
                    raise ValueError('이미 등록된 자료가 있습니다. 다시 검토해 주세요.')
            raise ValueError('사전 검토 뒤 파일 또는 관련 로컬 조사 자료가 변경되었습니다. 다시 검토해 주세요.')
    batch_id = con.execute('''INSERT INTO offline_research_batches
        (manifest_filename,manifest_sha256,item_count) VALUES(?,?,?)''',
        (filename, manifest_sha256, len(prepared))).lastrowid
    ids = []
    for ordinal, (url, title, content, kind, basename, rawhash, size) in enumerate(prepared, 1):
        ident = add(con, url, title, content, kind)
        con.execute('''INSERT INTO offline_research_local_imports
            (capture_id,original_filename,raw_sha256,raw_size) VALUES(?,?,?,?)''',
            (ident, basename, rawhash, size))
        con.execute('''INSERT INTO offline_research_batch_items
            (batch_id,capture_id,ordinal) VALUES(?,?,?)''',
            (batch_id, ident, ordinal))
        ids.append(ident)
    return {'batch_id': batch_id, 'capture_ids': ids, 'manifest_sha256': manifest_sha256}

def get(con, capture_id):
    _id(capture_id)
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT * FROM offline_research_captures WHERE id=?', (capture_id,)).fetchone()
    if row is None:
        raise ValueError('자료를 찾을 수 없습니다.')
    result = dict(row)
    provenance = con.execute('''SELECT original_filename,raw_sha256,raw_size,imported_at
        FROM offline_research_local_imports WHERE capture_id=?''', (capture_id,)).fetchone()
    result['local_import'] = dict(provenance) if provenance else None
    batch = con.execute('''SELECT b.id AS batch_id,b.manifest_filename,b.manifest_sha256,
        b.item_count,b.imported_at,i.ordinal
        FROM offline_research_batch_items AS i
        JOIN offline_research_batches AS b ON b.id=i.batch_id
        WHERE i.capture_id=?''', (capture_id,)).fetchone()
    result['bundle_import'] = dict(batch) if batch else None
    return result



def list_offline_links(con, capture_id):
    """Local URL inventory: has_local_copy is not a claim of online truth."""
    _id(capture_id)
    con.row_factory = sqlite3.Row
    if con.execute('SELECT 1 FROM offline_research_captures WHERE id=?',
                   (capture_id,)).fetchone() is None:
        raise ValueError('자료를 찾을 수 없습니다.')
    return [dict(row) for row in con.execute('''SELECT l.position,l.linked_url,
          EXISTS(SELECT 1 FROM offline_research_captures AS c
                 WHERE c.source_url=l.linked_url) AS has_local_copy,
          l.source_verification
          FROM offline_research_html_links AS l
          WHERE l.capture_id=? ORDER BY l.position''', (capture_id,))]



def trace_offline_references(con, capture_id, max_depth=2):
    '''Traverse *stored URL strings*, not the internet, with strict size limits.

    Every match is a candidate local capture, never authenticated proof of an
    actual hyperlink relationship. Historical captures lacking link inventory
    are not reconstructed; archived captures remain visible for evidence review.
    '''
    from collections import deque

    _id(capture_id)
    if type(max_depth) is not int or not 1 <= max_depth <= 3:
        raise ValueError('참조 연결 조회 깊이는 1~3이어야 합니다.')
    con.row_factory = sqlite3.Row
    start = con.execute('''SELECT id,title,source_url,archived_at
        FROM offline_research_captures WHERE id=?''', (capture_id,)).fetchone()
    if start is None:
        raise ValueError('자료를 찾을 수 없습니다.')

    def node_record(row, depth):
        return {'id': row['id'], 'title': row['title'],
                'source_url': row['source_url'], 'archived': row['archived_at'] is not None,
                'depth': depth}

    nodes = [node_record(start, 0)]
    edges = []
    visited = {capture_id}
    waiting = deque([(capture_id, 0)])
    truncated = False
    # Guard against malicious or enormous local inventories: at most 50 capture
    # nodes and 150 link records; never execute the URL or read a local file.
    while waiting:
        current, depth = waiting.popleft()
        if depth >= max_depth:
            continue
        rows = con.execute('''SELECT position,linked_url FROM offline_research_html_links
            WHERE capture_id=? ORDER BY position''', (current,)).fetchall()
        for row in rows:
            if len(edges) >= 150:
                truncated = True
                break
            matches = con.execute('''SELECT id,title,source_url,archived_at
                FROM offline_research_captures WHERE source_url=? ORDER BY id LIMIT 51''',
                (row['linked_url'],)).fetchall()
            candidate_ids = [item['id'] for item in matches]
            if len(matches) > 50:
                truncated = True
            edges.append({'from_id': current, 'position': row['position'],
                          'linked_url': row['linked_url'], 'candidate_ids': candidate_ids[:50],
                          'status': 'missing' if not candidate_ids else
                                    'one' if len(candidate_ids) == 1 else 'multiple'})
            for match in matches:
                if match['id'] in visited:
                    continue
                if len(nodes) >= 50:
                    truncated = True
                    continue
                visited.add(match['id'])
                nodes.append(node_record(match, depth + 1))
                waiting.append((match['id'], depth + 1))
        if len(edges) >= 150:
            if waiting or len(rows) > 0:
                truncated = True
            break
    return {'start_id': capture_id, 'max_depth': max_depth, 'nodes': nodes,
            'links': edges, 'truncated': truncated, 'source_authenticity_verified': False,
            'network_accessed': False}

def search(con, query='', *, include_archived=False, limit=200):
    if not isinstance(query,str) or len(query)>200 or '\x00' in query:
        raise ValueError('검색어는 200자 이하여야 합니다.')
    if type(include_archived) is not bool or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('조회 옵션이 유효하지 않습니다.')
    sql = 'SELECT id,source_url,title,capture_kind,content_sha256,source_verification,recorded_at,archived_at FROM offline_research_captures'
    conditions=[]
    args=[]
    if not include_archived:
        conditions.append('archived_at IS NULL')
    if query:
        # Treat %, _ and backslash as literals rather than SQL wildcards.
        pattern='%' + query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        conditions.append("(title LIKE ? ESCAPE '\\' OR source_url LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')")
        args.extend((pattern,)*3)
    if conditions:
        sql+=' WHERE '+' AND '.join(conditions)
    con.row_factory=sqlite3.Row
    return [dict(row) for row in con.execute(sql+' ORDER BY id DESC LIMIT ?', (*args,limit))]


def build_local_evidence_report(con, query: str, *, include_archived: bool = False,
                                limit: int = 20) -> dict:
    """Quote matching *stored* lines with capture IDs and provenance; never fetch URLs.

    This is deterministic text search, NOT AI synthesis, corroboration,
    online-source authentication, or a certificate of truth. Read-only and bounded.
    """
    if (not isinstance(query, str) or not 1 <= len(query.strip()) <= 80 or
            any(ord(char) < 32 or ord(char) == 127 for char in query)):
        raise ValueError('근거 검색어는 1~80자 단일 행 텍스트여야 합니다.')
    if type(include_archived) is not bool or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('근거 보고서 옵션이 올바르지 않습니다.')
    query = query.strip()
    folded = query.casefold()
    con.row_factory = sqlite3.Row
    rows = con.execute('''SELECT c.id,c.title,c.source_url,c.body,c.content_sha256,
           c.recorded_at,c.archived_at,c.source_verification,
           i.original_filename,i.raw_sha256
           FROM offline_research_captures c
           LEFT JOIN offline_research_local_imports i ON i.capture_id=c.id
           WHERE (? OR c.archived_at IS NULL)
           ORDER BY c.id DESC LIMIT 501''', (int(include_archived),)).fetchall()
    hits = []
    cut_off = len(rows) > 500
    for row in rows[:500]:
        excerpts = []
        for line_number, line in enumerate(row['body'].splitlines(), 1):
            location = line.casefold().find(folded)
            if location == -1:
                continue
            start = max(0, location - 55)
            end = min(len(line), location + len(query) + 95)
            snippet = (('…' if start else '') + line[start:end] +
                       ('…' if end < len(line) else ''))
            excerpts.append({'line': line_number, 'text': snippet})
            if len(excerpts) == 2:
                break
        if not excerpts:
            continue
        digest_matches = hashlib.sha256(row['body'].encode('utf-8')).hexdigest() == row['content_sha256']
        hits.append({'capture_id': row['id'], 'title': row['title'],
                     'source_url': row['source_url'], 'recorded_at': row['recorded_at'],
                     'archived': row['archived_at'] is not None,
                     'content_sha256': row['content_sha256'],
                     'local_content_hash_matches': digest_matches,
                     'original_filename': row['original_filename'],
                     'raw_sha256': row['raw_sha256'], 'excerpts': excerpts,
                     'source_verification': row['source_verification']})
        if len(hits) >= limit:
            break
    truncated = cut_off or (len(hits) >= limit and len(rows) > limit)
    lines = [f'AIWACK 오프라인 근거 발췌 | 검색어: {query}',
             '이 보고서는 저장된 로컬 사본의 문자 일치를 인용한 것입니다.',
             '웹 출처·내용 진위는 미검증, 인터넷 접속 없음, AI 해석/결론 없음.',
             f'최대 {min(len(rows),500)}건 스캔 / {len(hits)}건 표시' +
             (' / 일부 결과 생략 가능' if truncated else '')]
    if not hits:
        lines.append('일치하는 로컬 본문 없음 (온라인에 자료가 없음을 의미하지 않음).')
    for hit in hits:
        lines += ['', f'[로컬 자료 #{hit["capture_id"]}] {hit["title"]}',
                  f'등록 출처 URL(미검증): {hit["source_url"]}',
                  f'본문 SHA-256: {hit["content_sha256"]}',
                  '현재 SQLite 본문 해시 일치: ' + ('예' if hit['local_content_hash_matches'] else '아니오 — 주의'),
                  f'등록 시각: {hit["recorded_at"]} / 보관: {"예" if hit["archived"] else "아니오"}']
        if hit['raw_sha256']:
            lines.append(f'로컬 원본 파일: {hit["original_filename"]} / SHA-256: {hit["raw_sha256"]}')
        for excerpt in hit['excerpts']:
            lines.append(f'본문 {excerpt["line"]}행: {excerpt["text"]}')
    lines.append('주의: 동일 URL의 여러 등록본도 각각 미검증 로컬 증거입니다.')
    return {'query': query, 'hits': hits, 'scanned': min(len(rows),500),
            'truncated': truncated, 'source_authenticity_verified': False,
            'network_accessed': False, 'report_text': '\n'.join(lines)}

def archive(con, capture_id):
    _id(capture_id)
    result = con.execute('''UPDATE offline_research_captures SET archived_at=CURRENT_TIMESTAMP
          WHERE id=? AND archived_at IS NULL''', (capture_id,))
    if result.rowcount != 1:
        raise ValueError('자료가 없거나 이미 보관되었습니다.')
    return True


# Stage54 offline continuation: read-only consistency review of *locally stored*
# material. A successful audit DOES NOT authenticate the original website or
# prove that a malicious editor could not modify both the content and hash.
def audit_local_evidence(con):
    """Check recorded text digests and provenance relationships without writes."""
    con.row_factory = sqlite3.Row
    issues = []
    rows = con.execute("""SELECT id,body,content_sha256 FROM offline_research_captures
                          ORDER BY id""").fetchall()
    for row in rows:
        ident = row['id']
        expected = hashlib.sha256(row['body'].encode('utf-8')).hexdigest()
        if expected != row['content_sha256']:
            issues.append({'capture_id': ident, 'issue': '저장 본문 SHA-256 불일치'})
    # Additional relational checks guard against accidental DB corruption or
    # FOREIGN KEY enforcement being disabled in a third-party SQLite editor.
    for table, fk, parent in (
        ('offline_research_local_imports', 'capture_id', 'offline_research_captures'),
        ('offline_research_batch_items', 'capture_id', 'offline_research_captures'),
        ('offline_research_batch_items', 'batch_id', 'offline_research_batches'),
        ('offline_research_html_links', 'capture_id', 'offline_research_captures'),
    ):
        bad = con.execute(f"""SELECT t.{fk} AS missing_id FROM {table} AS t
            LEFT JOIN {parent} AS p ON p.id=t.{fk} WHERE p.id IS NULL ORDER BY t.{fk}""")
        for record in bad:
            issues.append({'capture_id': None, 'issue': f'{table}: 참조 ID {record["missing_id"]} 누락'})
    batches = con.execute("""SELECT b.id, b.item_count,
                COUNT(i.capture_id) AS stored_count,
                MIN(i.ordinal) AS first_position,
                MAX(i.ordinal) AS last_position
             FROM offline_research_batches AS b
             LEFT JOIN offline_research_batch_items AS i ON i.batch_id=b.id
             GROUP BY b.id ORDER BY b.id""").fetchall()
    for batch in batches:
        if (batch['item_count'] != batch['stored_count'] or
            batch['first_position'] != 1 or
            batch['last_position'] != batch['item_count']):
            issues.append({'capture_id': None, 'issue': f'묶음 #{batch["id"]}: 등록 수량 또는 순서 불일치'})
    linkgroups = con.execute('''SELECT capture_id, COUNT(*) AS n,
                    MIN(position) AS first_pos, MAX(position) AS last_pos
                  FROM offline_research_html_links GROUP BY capture_id''').fetchall()
    for group in linkgroups:
        if group['first_pos'] != 1 or group['last_pos'] != group['n']:
            issues.append({'capture_id':group['capture_id'],
                           'issue':'HTML 링크 목록의 순서가 연속되지 않습니다.'})
    return {
        'checked_captures': len(rows),
        'checked_batches': len(batches),
        'issues': issues,
        'passed': not issues,
        'source_authenticity_verified': False,
        'original_file_bytes_rechecked': False,
    }


def compare_local_evidence(con, first_id, second_id):
    """Compare exactly two local captures, never assert their claims are true."""
    _id(first_id)
    _id(second_id)
    if first_id == second_id:
        raise ValueError('서로 다른 두 자료의 ID를 선택해 주세요.')
    first = get(con, first_id)
    second = get(con, second_id)
    return {
        'first_id': first_id,
        'second_id': second_id,
        'same_body': first['body'] == second['body'],
        'same_claimed_source': first['source_url'] == second['source_url'],
        'same_local_raw_file': (first['local_import'] is not None and
            second['local_import'] is not None and
            first['local_import']['raw_sha256'] == second['local_import']['raw_sha256'] and
            first['local_import']['raw_size'] == second['local_import']['raw_size']),
        'first_title': first['title'],
        'second_title': second['title'],
        'first_sha256': first['content_sha256'],
        'second_sha256': second['content_sha256'],
        'source_authenticity_verified': False,
    }
