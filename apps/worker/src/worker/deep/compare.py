"""When two measurements count as the same: equal after rounding numbers to one decimal and
ignoring key order. Used by the harness (a report's claimed value against what it measures)
and by verification (a fresh browser's value against the report's)."""

import json


def same_result(a, b) -> bool:
    return canonical(a) == canonical(b)


def canonical(value) -> str:
    def round_all(v):
        if isinstance(v, bool) or v is None or isinstance(v, str):
            return v
        if isinstance(v, int | float):
            return round(float(v), 1)
        if isinstance(v, list):
            return [round_all(x) for x in v]
        if isinstance(v, dict):
            return {str(k): round_all(x) for k, x in v.items()}
        return str(v)

    return json.dumps(round_all(value), sort_keys=True)


def shown(value, limit: int = 200) -> str:
    return json.dumps(value)[:limit]
