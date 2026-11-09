import pytest

from worker.urls import is_same_origin, normalize

START = "http://localhost:5173/"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:5173/cart#top", "http://localhost:5173/cart"),  # fragment dropped
        ("HTTP://LocalHost:5173/Cart", "http://localhost:5173/Cart"),  # path case kept
        ("http://localhost:5173", "http://localhost:5173/"),  # empty path becomes "/"
        ("http://localhost:5173/a?b=1", "http://localhost:5173/a?b=1"),  # query kept
        ("http://localhost:5173/a?z=1&a=2", "http://localhost:5173/a?a=2&z=1"),  # params sorted
        ("http://example.com:80/x", "http://example.com/x"),  # default port dropped
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("url", "same"),
    [
        ("http://localhost:5173/products/1", True),
        ("http://LOCALHOST:5173/", True),
        ("http://localhost:3000/", False),  # different port
        ("https://localhost:5173/", False),  # different scheme
        ("http://example.com/", False),  # different host
        ("mailto:help@example.com", False),
        ("javascript:void(0)", False),
    ],
)
def test_is_same_origin(url, same):
    assert is_same_origin(url, START) is same
