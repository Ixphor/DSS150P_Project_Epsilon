"""HTTP session with automatic retries and backoff for flaky public APIs."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from curl_cffi import requests as curl_requests

def build_session(retries: int = 5, backoff: float = 1.0) -> requests.Session:
    """Session that retries 429/5xx responses and connection errors with exponential backoff."""
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "dss150p-epsilon-pipeline/1.0"})
    return session

def build_browser_session():
    """
    Session that impersonates a real Chrome browser's TLS fingerprint.
    Needed for CFPB's API, which blocks standard requests/urllib3 clients
    (403 Forbidden) even with correct headers -- the block operates at the
    TLS handshake level, not the HTTP header level. Requires: pip install curl_cffi
    """
    from curl_cffi import requests as curl_requests
    return curl_requests.Session(impersonate="chrome")