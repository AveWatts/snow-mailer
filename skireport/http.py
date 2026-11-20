import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import TIMEOUT, USER_AGENT

_session = None


def session():
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "POST"))
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        s.headers["User-Agent"] = USER_AGENT
        _session = s
    return _session


def get(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    r = session().get(url, **kw)
    r.raise_for_status()
    return r


def get_json(url, **kw):
    return get(url, **kw).json()
