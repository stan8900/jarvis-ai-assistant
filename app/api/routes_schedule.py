from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.scheduling.models import Command
from app.scheduling.parser import detect
from app.scheduling.security import require_owner
from app.scheduling.service import SchedulingService, get_service

router = APIRouter(prefix='/schedule', tags=['scheduling'])


class NaturalCommand(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default='default', min_length=1, max_length=128)


def execute(command, owner, session, request, service):
    header_key = request.headers.get('idempotency-key')
    if header_key:
        if len(header_key) > 128:
            raise HTTPException(422, 'Idempotency-Key must be at most 128 characters.')
        command = command.model_copy(update={'idempotency_key': header_key})
    # Explicit keys keep relative-date retries stable across multiple HTTP requests.
    if command.intent.value.startswith('CREATE_') and not command.idempotency_key:
        raise HTTPException(428, 'Supply an Idempotency-Key header for a new scheduled item. Reuse it only when retrying the same request.')
    return service.execute(command, owner, session)


@router.post('/commands')
def command(body: Command, request: Request, owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    return execute(body, owner, 'api', request, service)


@router.post('/text')
def natural_command(body: NaturalCommand, request: Request, owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    parsed = detect(body.message)
    if parsed is None:
        raise HTTPException(422, 'No supported scheduling command detected.')
    return execute(parsed, owner, body.session_id, request, service)


@router.get('/reminders')
def reminders(owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    return service.store.list(owner, 'reminder')


@router.get('/automations')
def automations(owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    return service.store.list(owner, 'automation')


@router.get('/notifications')
def notifications(owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    return {'channel': 'in_app', 'items': service.store.notifications(owner), 'device_delivery': 'not_configured'}


@router.post('/notifications/{notification_id}/ack')
def acknowledge(notification_id: str, owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    if not service.store.acknowledge(owner, notification_id):
        raise HTTPException(404, 'Pending notification not found.')
    return {'status': 'acknowledged'}


@router.get('/history')
def history(owner: str = Depends(require_owner), service: SchedulingService = Depends(get_service)):
    return service.store.history(owner)


@router.get('/bold/overview')
def bold_overview(request: Request, service: SchedulingService = Depends(get_service)):
    """Loopback-only planner feed for the native island; Bold is the sole source."""
    if request.client is None or request.client.host not in {'127.0.0.1', '::1', 'localhost'}:
        raise HTTPException(403, 'The native planner feed is local-only.')
    try:
        tasks = service.bold.list_records('task', limit=100)
        events = service.bold.list_records('calendar_event', limit=100)
    except Exception as exc:
        raise HTTPException(503, 'Bold planner data is temporarily unavailable.') from exc
    return {
        'source': 'bold',
        'tasks': tasks.get('records', []),
        'events': events.get('records', []),
        'fetched_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    }
