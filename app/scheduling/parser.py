"""Intent detection is deliberately independent of execution and provider content."""
import re
from pydantic import ValidationError
from app.scheduling.models import Command, Intent


def detect(message: str) -> Command | None:
    try:
        return _detect(message)
    except ValidationError:
        return Command(intent=Intent.CREATE_REMINDER, target='clarify')


def _detect(message: str) -> Command | None:
    text = re.sub(r'^(?:jarvis[,:]?\s*)', '', message.strip(), flags=re.I)
    text = re.sub(r'\bplease\b', '', text, flags=re.I).strip().rstrip('.?!')
    lower = text.lower()
    if lower in {'confirm', 'confirm that', 'yes confirm', 'confirm my last change'}:
        return Command(intent=Intent.CONFIRM, confirmation_id='latest')
    if lower.startswith('confirm '):
        return Command(intent=Intent.CONFIRM, confirmation_id=text.split(maxsplit=1)[1])
    if 'bold' in lower:
        intent = Intent.BOLD_LIST_TASKS
        if 'note' in lower:
            intent = Intent.BOLD_CREATE_NOTE if re.search(r'\b(create|add)\b', lower) else Intent.BOLD_SEARCH_NOTES
            if intent == Intent.BOLD_CREATE_NOTE:
                content = re.split(r'\b(?:about|saying|that)\b', text, maxsplit=1, flags=re.I)
                return Command(intent=intent, title=content[1].strip() if len(content) == 2 else text)
            content = re.split(r'\b(?:about|for|with)\b', text, maxsplit=1, flags=re.I)
            return Command(intent=intent, target=content[1].strip() if len(content) == 2 else text)
        elif re.search(r'\b(create|add)\b', lower):
            intent = Intent.BOLD_CREATE_TASK
            content = re.split(r'\btask\s+in\s+bold\s+to\b|\btask\s+to\b|\bto\b', text, maxsplit=1, flags=re.I)
            title = content[1].strip() if len(content) == 2 else text
            due = ''
            due_match = re.search(r'\b(?:tomorrow|today|next\s+\w+|in\s+\d+\s+\w+|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm))\b.*$', title, re.I)
            if due_match:
                due = due_match.group(0).strip()
                title = title[:due_match.start()].strip()
            return Command(intent=intent, title=title or text, when=due)
        elif re.search(r'\b(complete|completed|done)\b', lower):
            intent = Intent.BOLD_COMPLETE_TASK
            content = re.split(r'\b(?:task|about)\b', text, maxsplit=1, flags=re.I)
            return Command(intent=intent, target=content[1].strip() if len(content) == 2 else text)
        elif 'sync' in lower:
            intent = Intent.BOLD_SYNC
        elif re.search(r'\b(move|reschedule|update)\b', lower):
            intent = Intent.BOLD_UPDATE_TASK
        return Command(intent=intent, title=text)
    if match := re.fullmatch(r'remind me (.+?) to (.+)', text, re.I):
        return Command(intent=Intent.CREATE_REMINDER, when=match[1], title=match[2])
    if re.search(r'\b(reminders?|automations?)\b', lower):
        kind = 'AUTOMATION' if 'automation' in lower else 'REMINDER'
        if re.match(r'(what|show|list)\b', lower):
            return Command(intent=Intent[f'LIST_{kind}S'], when='today' if 'today' in lower else '')
        if match := re.fullmatch(r'(cancel|delete|complete|finish|pause|resume|enable|disable|snooze|move|reschedule|update)\s+(?:my\s+)?(.+)', text, re.I):
            verb, target = match[1].lower(), match[2]
            when = ''
            if verb in ('move', 'reschedule', 'snooze', 'update'):
                split = re.split(r'\s+(?:to|for|until)\s+', target, maxsplit=1, flags=re.I)
                target, when = split[0], split[1] if len(split) > 1 else ''
                if verb == 'snooze' and re.fullmatch(r'\d+ (?:minute|hour)s?', when):
                    when = 'in ' + when
            target = re.sub(r'\b(?:my|reminder|automation|about|the)\b', '', target, flags=re.I).strip()
            operation = {'cancel': 'CANCEL', 'delete': 'CANCEL', 'complete': 'COMPLETE', 'finish': 'COMPLETE', 'pause': 'PAUSE', 'disable': 'PAUSE', 'resume': 'RESUME', 'enable': 'RESUME', 'snooze': 'SNOOZE', 'move': 'UPDATE', 'reschedule': 'UPDATE', 'update': 'UPDATE'}[verb]
            if kind == 'AUTOMATION' and operation == 'CANCEL':
                operation = 'DELETE'
            name = f'{operation}_{kind}'
            if name in Intent.__members__:
                return Command(intent=Intent[name], target=target, when=when)
        return Command(intent=Intent.LIST_AUTOMATIONS if kind == 'AUTOMATION' else Intent.LIST_REMINDERS, target='clarify')
    if match := re.fullmatch(r'(?:run|generate|check) (.+?) (every .+|in \d+ .+|tomorrow .+|at .+)', text, re.I):
        action_text = match[1].lower()
        action = 'daily_briefing' if 'brief' in action_text else 'reminder_summary' if 'reminder' in action_text else None
        if action:
            return Command(intent=Intent.CREATE_AUTOMATION, title=match[1], when=match[2], action=action)
        return Command(intent=Intent.CREATE_AUTOMATION, target='unsupported_action')
    if match := re.fullmatch(r'(?:schedule|book|block) (.+?) ((?:tomorrow|today|next |every |on |at |\d{4}-).+)', text, re.I):
        title = match[1]
        duration = 60
        if length := re.search(r'(\d+) (minutes?|hours?)', title, re.I):
            duration = int(length[1]) * (60 if length[2].lower().startswith('hour') else 1)
        if not 1 <= duration <= 1440:
            duration = 60
        return Command(intent=Intent.CREATE_CALENDAR_EVENT, title=title, when=match[2], duration_minutes=duration)
    if match := re.fullmatch(r'(move|reschedule|cancel|delete) (?:my )?(.*?(?:meeting|event).*)', text, re.I):
        target = match[2]
        when = ''
        if match[1].lower() in ('move', 'reschedule'):
            parts = re.split(r'\s+to\s+', target, maxsplit=1, flags=re.I)
            target, when = parts[0], parts[1] if len(parts) > 1 else ''
        return Command(intent=Intent.UPDATE_CALENDAR_EVENT if match[1].lower() in ('move', 'reschedule') else Intent.CANCEL_CALENDAR_EVENT, target=target, when=when)
    if lower.startswith('find a free'):
        duration = re.search(r'(\d+)[ -]minute', lower)
        return Command(intent=Intent.FIND_FREE_TIME, when='tomorrow' if 'tomorrow' in lower else 'today' if 'today' in lower else '', duration_minutes=int(duration[1]) if duration and 0 < int(duration[1]) <= 1440 else 30)
    if re.search(r'\b(schedule|calendar|meetings)\b', lower) and re.match(r'(what|show|list)\b', lower):
        return Command(intent=Intent.LIST_CALENDAR_EVENTS, when='next week' if 'next week' in lower else 'tomorrow' if 'tomorrow' in lower else 'today')
    if re.match(r'(remind me|schedule |book |block |run my |generate a weekly |check my )', lower):
        return Command(intent=Intent.CREATE_REMINDER, target='clarify')
    return None
