"""The meta/SEO check, on synthetic pages (tests/fixtures/site/meta/)."""

from worker.browser import VisitOptions, visit_page
from worker.findings import findings_from_pages
from worker.meta import check_meta, placeholder_host
from worker.report import MetaCheck, PageResult


def meta_of(context, url: str, cache: dict | None = None) -> MetaCheck:
    page = context.new_page()
    try:
        page.goto(url)
        return check_meta(page, cache if cache is not None else {})
    finally:
        page.close()


def test_complete_metadata_has_no_problems(context, site_url):
    assert meta_of(context, f"{site_url}/meta/complete.html").problems == []


def test_missing_tags_are_listed(context, site_url):
    meta = meta_of(context, f"{site_url}/clean.html")
    assert meta.problems == [
        "og:title missing",
        "og:description missing",
        "og:url missing",
        "og:image missing",
        "twitter:card missing",
        "canonical link missing",
        "apple-touch-icon missing",
    ]  # clean.html has an icon link, so no favicon problem


def test_placeholder_og_image_is_named_without_loading_it(context, site_url):
    meta = meta_of(context, f"{site_url}/meta/placeholder.html")
    assert "og:image is a placeholder (via.placeholder.com)" in meta.problems


def test_og_image_that_fails_to_load(context, site_url):
    meta = meta_of(context, f"{site_url}/meta/broken.html")
    assert meta.problems == ["og:image fails to load (HTTP 404)"]


def test_the_og_image_is_loaded_once_per_scan(context, site_url):
    cache: dict = {}
    meta_of(context, f"{site_url}/meta/broken.html", cache)
    cache[f"{site_url}/meta/gone.png"] = None  # pretend it loaded: the cache is what's used
    assert meta_of(context, f"{site_url}/meta/broken.html", cache).problems == []


def test_without_an_icon_link_the_browsers_default_favicon_is_checked(context, site_url):
    meta = meta_of(context, f"{site_url}/meta/no-icon.html")
    assert "favicon missing" in meta.problems  # the test site has no /favicon.ico


def test_placeholder_hosts():
    assert placeholder_host("https://placehold.co/600x400") == "placehold.co"
    assert placeholder_host("https://via.placeholder.com/1200") == "via.placeholder.com"
    assert placeholder_host("https://cdn.example.com/share.png") is None
    assert placeholder_host("https://notplacehold.co/x.png") is None


def test_visit_page_runs_the_meta_check(context, site_url):
    page, _ = visit_page(context, f"{site_url}/meta/broken.html", VisitOptions(image_cache={}))
    assert page.meta is not None
    assert page.meta.problems == ["og:image fails to load (HTTP 404)"]


def _page(url: str, problems: list[str]) -> PageResult:
    return PageResult(url=url, status=200, meta=MetaCheck(problems=problems))


def test_identical_problems_on_several_pages_are_one_finding():
    same = ["og:image missing", "canonical link missing"]
    bugs = findings_from_pages(
        [_page("http://shop.test/", same), _page("http://shop.test/cart", same)]
    )
    assert len(bugs) == 1
    bug = bugs[0]
    assert bug.category == "seo"
    assert bug.severity == "low"
    assert bug.evidence["pages"] == ["http://shop.test/", "http://shop.test/cart"]
    assert bug.evidence["problems"] == same
    assert bug.status == "confirmed"


def test_different_problems_are_one_finding_per_page():
    bugs = findings_from_pages(
        [
            _page("http://shop.test/", ["og:image missing"]),
            _page("http://shop.test/cart", ["canonical link missing"]),
            _page("http://shop.test/ok", []),
        ]
    )
    assert sorted(b.page_url for b in bugs) == ["http://shop.test/", "http://shop.test/cart"]
