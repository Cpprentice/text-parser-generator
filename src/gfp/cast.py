def float_(value: str) -> float:
    return float(value)


def int_(value: str) -> int:
    return int(value)


def lstrip_(value: str) -> str:
    return value.lstrip()


def bool_(value: str) -> bool:
    true_values = {'true', 'yes', '1'}
    false_values = {'false', 'no', '0'}
    value = value.strip().lower()
    if value in true_values:
        return True
    elif value in false_values:
        return False
    raise ValueError(f'Cannot cast value "{value}" to bool')


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


def quoted_(value: str) -> str:
    return value.strip()[1:-1]
