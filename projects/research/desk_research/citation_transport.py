"""Bounded retries for the read-only Semantic Scholar batch lookup only."""
import datetime as dt
import email.utils
import json
import socket
import ssl
import time
import urllib.error
import urllib.request

URL = 'https://api.semanticscholar.org/graph/v1/paper/batch?fields=citationCount,externalIds'

class CitationLookupError(ValueError):
    def __init__(self, message, retry_after=0, status=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.status = status


def retry_seconds(value):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        try:
            date = email.utils.parsedate_to_datetime(value)
            return max(0, (date - dt.datetime.now(dt.timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def read_batch(ids, headers=None):
    request = urllib.request.Request(URL, data=json.dumps({'ids': ids}).encode(), headers={
        'User-Agent': 'LocalKnowledgeDesk/0.1 (personal research)',
        'Content-Type': 'application/json', **(headers or {})})
    for attempt in range(3):
        delay = (2, 5, 0)[attempt]
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise CitationLookupError('引用接口返回内容超过大小限制')
            result = json.loads(body)
            if not isinstance(result, list) or len(result) != len(ids):
                raise CitationLookupError('引用接口返回的数据数量不匹配')
            return result
        except urllib.error.HTTPError as exc:
            status = exc.code
            wait = retry_seconds(exc.headers.get('Retry-After'))
            # Only recognize this exact public API error; never expose raw bodies.
            not_found = False
            if status == 400:
                try:
                    body = exc.read(4096)
                    not_found = json.loads(body).get('error') == 'No valid paper ids given'
                except (ValueError, AttributeError, OSError):
                    pass
            exc.close()
            if not_found:
                return [None for _ in ids]
            # No upstream response bodies or headers are included in diagnostics.
            failure = CitationLookupError('引用接口返回 HTTP %s'%status, wait, status=status)
            if status not in (429, 500, 502, 503, 504) or wait > 30:
                raise failure from None
            delay = max(delay, wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, 'reason', exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise CitationLookupError('引用接口证书校验失败') from None
            category = ('域名解析失败' if isinstance(reason, socket.gaierror) else
                        '连接超时' if isinstance(reason, TimeoutError) else '网络连接失败')
            failure = CitationLookupError('引用接口%s（%s%s）'%(category, type(reason).__name__,
                ', errno='+str(reason.errno) if isinstance(getattr(reason,'errno',None),int) else ''))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CitationLookupError('引用接口未返回有效 JSON 数据') from None
        if attempt == 2:
            raise failure from None
        time.sleep(delay)
