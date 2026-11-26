"""One paced metadata connection shared by collection, imports and topic discovery."""
import datetime as dt
import email.utils
import threading
import time
import urllib.error
import urllib.request


class ArxivCooldown(ValueError):
    def __init__(self, seconds):
        self.retry_after = max(1, int(seconds + .999))
        super().__init__(f'arXiv 限流（HTTP 429），已暂停请求；约 {self.retry_after} 秒后可重试。上次成功采集进度已保留。')


def retry_after(headers, fallback):
    value = (headers or {}).get('Retry-After', '')
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            stamp = email.utils.parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            return max(0, stamp.timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return fallback


class ArxivTransport:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_request = 0
        self.cooldown_until = 0

    def read(self, request, limit):
        # Hold the lock through the response and retries: callers cannot compete.
        with self.lock:
            if self.cooldown_until > time.monotonic():
                raise ArxivCooldown(self.cooldown_until - time.monotonic())
            for attempt in range(3):
                time.sleep(max(0, self.next_request - time.monotonic()))
                try:
                    with urllib.request.urlopen(request, timeout=65) as response:
                        data = response.read(limit + 1)
                    if len(data) > limit:
                        raise ValueError('内容超过大小限制')
                    self.cooldown_until = 0
                    return data
                except urllib.error.HTTPError as exc:
                    code = exc.code
                    delay = retry_after(exc.headers, 30 * (2 ** attempt))
                    exc.close()
                    if code == 429:
                        # Long provider waits are surfaced, not shortened or bypassed.
                        if attempt == 2 or delay > 60:
                            self.cooldown_until = time.monotonic() + max(delay, 300)
                            raise ArxivCooldown(self.cooldown_until - time.monotonic()) from None
                        self.next_request = time.monotonic() + max(5, delay)
                    elif code in (502, 503, 504) and attempt < 2:
                        if delay > 60:
                            raise ValueError('arXiv 暂时不可用；请稍后重试。') from None
                        self.next_request = time.monotonic() + max(5, delay)
                    else:
                        raise ValueError('来源或 API 返回 HTTP %s；请稍后重试。' % code) from None
                except (urllib.error.URLError, TimeoutError) as exc:
                    if attempt == 2:
                        raise ValueError('arXiv 连接失败或超时，请检查网络或代理设置。') from exc
                    self.next_request = time.monotonic() + 10 * (attempt + 1)
                finally:
                    self.next_request = max(self.next_request, time.monotonic() + 5)


client = ArxivTransport()
