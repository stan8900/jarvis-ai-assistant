"""Authenticated local client helpers shared with the voice loop."""
import os
from urllib.parse import urlsplit, urlunsplit
import httpx

from app.core.config import _load_local_env

_load_local_env()

def scheduling_headers(api_url: str) -> dict:
    token = os.getenv('JARVIS_SCHEDULER_TOKEN', '')
    if not token:
        return {}
    parsed = urlsplit(api_url)
    if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Scheduling credentials require HTTPS or a loopback API URL.')
    return {'Authorization': 'Bearer ' + token}


def poll_notifications(api_url: str) -> None:
    """The active CLI displays the inbox; it does not promise off-device delivery."""
    headers = scheduling_headers(api_url)
    if not headers:
        return
    parsed = urlsplit(api_url)
    base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rsplit('/chat/', 1)[0] + '/schedule', '', ''))
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(base + '/notifications', headers=headers)
            response.raise_for_status()
            for note in response.json()['items']:
                print('\nJARVIS notification: ' + note['content'])
                ack = client.post(base + '/notifications/' + note['id'] + '/ack', headers=headers)
                ack.raise_for_status()
    except httpx.HTTPError:
        # Leave the inbox unacknowledged so a later poll can recover it.
        print('Notification inbox unavailable; pending reminders remain stored.')

