from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Intent(str, Enum):
    CREATE_REMINDER = 'CREATE_REMINDER'
    LIST_REMINDERS = 'LIST_REMINDERS'
    UPDATE_REMINDER = 'UPDATE_REMINDER'
    CANCEL_REMINDER = 'CANCEL_REMINDER'
    SNOOZE_REMINDER = 'SNOOZE_REMINDER'
    COMPLETE_REMINDER = 'COMPLETE_REMINDER'
    CREATE_CALENDAR_EVENT = 'CREATE_CALENDAR_EVENT'
    LIST_CALENDAR_EVENTS = 'LIST_CALENDAR_EVENTS'
    UPDATE_CALENDAR_EVENT = 'UPDATE_CALENDAR_EVENT'
    CANCEL_CALENDAR_EVENT = 'CANCEL_CALENDAR_EVENT'
    FIND_FREE_TIME = 'FIND_FREE_TIME'
    CREATE_AUTOMATION = 'CREATE_AUTOMATION'
    LIST_AUTOMATIONS = 'LIST_AUTOMATIONS'
    UPDATE_AUTOMATION = 'UPDATE_AUTOMATION'
    PAUSE_AUTOMATION = 'PAUSE_AUTOMATION'
    RESUME_AUTOMATION = 'RESUME_AUTOMATION'
    DELETE_AUTOMATION = 'DELETE_AUTOMATION'
    BOLD_CREATE_NOTE = 'BOLD_CREATE_NOTE'
    BOLD_SEARCH_NOTES = 'BOLD_SEARCH_NOTES'
    BOLD_CREATE_TASK = 'BOLD_CREATE_TASK'
    BOLD_LIST_TASKS = 'BOLD_LIST_TASKS'
    BOLD_UPDATE_TASK = 'BOLD_UPDATE_TASK'
    BOLD_COMPLETE_TASK = 'BOLD_COMPLETE_TASK'
    BOLD_SYNC = 'BOLD_SYNC'
    CONFIRM = 'CONFIRM'


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: Intent
    title: str = Field(default='', max_length=500)
    when: str = Field(default='', max_length=200)
    timezone: str | None = Field(default=None, max_length=80)
    target: str = Field(default='', max_length=500)
    duration_minutes: int = Field(default=60, ge=1, le=1440)
    action: Literal['daily_briefing', 'reminder_summary'] = 'daily_briefing'
    confirmed: bool = False
    confirmation_id: str = Field(default='', max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)
