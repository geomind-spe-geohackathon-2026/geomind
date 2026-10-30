"""Remove known secret values from what is stored or streamed."""

from swarmax.types.events import event_from_dict

REDACTED = "[redacted]"


def redact(value, secrets):
    """Return JSON-like ``value`` or bytes with every secret replaced in its text."""
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, bytes):
        return redact(value.decode("latin-1"), secrets).encode("latin-1")
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    return value


def redact_event(event, secrets):
    """Return ``event`` without the secrets; without secrets it is the same object."""
    if not secrets:
        return event
    return event_from_dict(redact(event.to_dict(), secrets))
