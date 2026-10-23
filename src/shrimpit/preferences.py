"""Read stored preferences with safe defaults."""


def integer_setting(settings, key, default, minimum, maximum):
    try:
        value = int(settings.value(key, default)) if settings is not None else default
    except (ValueError, TypeError, OverflowError):
        return default
    return value if minimum <= value <= maximum else default


def boolean_setting(settings, key, default=True):
    value = settings.value(key, default) if settings is not None else default
    if isinstance(value, bool):
        return value
    if str(value).lower() in {"true", "1"}:
        return True
    if str(value).lower() in {"false", "0"}:
        return False
    return default
