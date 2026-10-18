"""Business logic. Services own all SQL; the UI only talks to services."""


class ValidationError(ValueError):
    """Input the user can fix; the message is shown to them as-is."""
