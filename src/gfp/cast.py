def float_(value: str) -> float:
    return float(value)


def int_(value: str) -> int:
    return int(value)


def lstrip_(value: str) -> str:
    return value.lstrip()


def number_(value: str) -> int | float:
    try:
        return int(value)
    except ValueError:
        return float(value)


def rstrip_(value: str) -> str:
    return value.rstrip()


def strip_(value: str) -> str:
    return value.strip()


def uint_(value: str) -> int:
    converted = int(value)
    assert converted >= 0
    return converted
