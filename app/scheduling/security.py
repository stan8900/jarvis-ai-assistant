"""Dedicated scheduling credentials. Caller-provided user IDs never grant ownership."""
import hmac
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits = defaultdict(deque)


def require_owner(request: Request) -> str:
    token = os.getenv('JARVIS_SCHEDULER_TOKEN', '')
    if len(token) < 32:
        raise HTTPException(503, 'Set JARVIS_SCHEDULER_TOKEN to a random secret of at least 32 characters before using scheduling.')
    authorization = request.headers.get('authorization', '')
    scheme, _, candidate = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not hmac.compare_digest(candidate.encode(), token.encode()):
        raise HTTPException(401, 'Scheduling requires its configured Bearer token.', headers={'WWW-Authenticate': 'Bearer'})
    owner = os.getenv('JARVIS_SCHEDULER_OWNER', 'sultan')
    now = time.monotonic()
    with _lock:
        queue = _hits[owner]
        while queue and queue[0] <= now - 60:
            queue.popleft()
        if len(queue) >= 120:
            raise HTTPException(429, 'Scheduling rate limit reached; retry in one minute.', headers={'Retry-After': '60'})
        queue.append(now)
    return owner
