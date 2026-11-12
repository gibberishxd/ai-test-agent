import pytest

from worker.urls import is_same_origin, is_same_site, normalize

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


@pytest.mark.parametrize(
    ("url", "target", "same"),
    [
        ("http://shop.test/cart", "http://shop.test/", True),  # same origin
        ("https://shop.test/cart", "http://shop.test/", True),  # the site upgraded to https
        ("https://SHOP.test:443/", "http://shop.test:80/", True),  # default ports written out
        ("http://shop.test/", "https://shop.test/", False),  # a downgrade is not an upgrade
        ("https://blog.shop.test/", "http://shop.test/", False),  # a subdomain is another host
        ("https://other.test/", "http://shop.test/", False),
        ("https://localhost:5173/", "http://localhost:5173/", False),  # not the default ports
        ("https://shop.test:8443/", "http://shop.test/", False),
        ("mailto:help@shop.test", "http://shop.test/", False),
    ],
)
def test_is_same_site_allows_only_the_https_upgrade(url, target, same):
    assert is_same_site(url, target) is same
