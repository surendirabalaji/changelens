def describe(error: BaseException) -> str:
    """Flatten exception groups into one short line per error."""
    if isinstance(error, BaseExceptionGroup):
        return " | ".join(describe(sub) for sub in error.exceptions)
    message = str(error)[:200]
    return f"{type(error).__name__}: {message}" if message else type(error).__name__