from worker.crawler import crawl
from worker.report import PageResult

BASE = "http://site.test"

# A fake site: page URL -> links on that page. No browser needed.
FAKE_SITE = {
    f"{BASE}/": [f"{BASE}/about", f"{BASE}/products", "https://other.example/", "mailto:a@b.c"],
    f"{BASE}/about": [f"{BASE}/", f"{BASE}/about#team"],  # loops back to home and to itself
    f"{BASE}/products": [f"{BASE}/products/1", f"{BASE}/"],
    f"{BASE}/products/1": [f"{BASE}/products"],
}


def fake_visit(url: str) -> tuple[PageResult, list[str]]:
    return PageResult(url=url, status=200), FAKE_SITE.get(url, [])


def visited_urls(pages: list[PageResult]) -> list[str]:
    return [p.url for p in pages]


def test_visits_every_same_origin_page_once_despite_loops():
    pages = crawl(f"{BASE}/", fake_visit)
    assert sorted(visited_urls(pages)) == sorted(FAKE_SITE)


def test_visits_breadth_first():
    pages = crawl(f"{BASE}/", fake_visit)
    # Home, then the pages it links to, then the next level down.
    assert visited_urls(pages) == [
        f"{BASE}/",
        f"{BASE}/about",
        f"{BASE}/products",
        f"{BASE}/products/1",
    ]


def test_records_which_page_linked_here():
    found_on = {p.url: p.found_on for p in crawl(f"{BASE}/", fake_visit)}
    assert found_on[f"{BASE}/"] is None
    assert found_on[f"{BASE}/products"] == f"{BASE}/"
    assert found_on[f"{BASE}/products/1"] == f"{BASE}/products"


def test_stops_at_max_pages():
    def endless_visit(url: str) -> tuple[PageResult, list[str]]:
        # Every page links to a new one: /p/1 -> /p/2 -> ... forever.
        n = int(url.rsplit("/", 1)[-1] or 0)
        return PageResult(url=url, status=200), [f"{BASE}/p/{n + 1}"]

    assert len(crawl(f"{BASE}/", endless_visit, max_pages=5)) == 5


def test_stops_at_max_depth():
    # Depth 0 is the start page; with max_depth=1 only its direct links are visited.
    pages = crawl(f"{BASE}/", fake_visit, max_depth=1)
    assert sorted(visited_urls(pages)) == sorted([f"{BASE}/", f"{BASE}/about", f"{BASE}/products"])


def test_calls_on_page_for_each_visit():
    seen = []
    crawl(f"{BASE}/", fake_visit, on_page=lambda page: seen.append(page.url))
    assert len(seen) == len(FAKE_SITE)


def test_should_stop_ends_the_crawl_early():
    pages = crawl(f"{BASE}/", fake_visit, should_stop=lambda: True)
    assert visited_urls(pages) == [f"{BASE}/"]  # the current page finishes, then it stops


def test_follows_links_after_the_site_upgrades_to_https():
    # The user typed http://, the site answers on https://: its links are still the same site.
    site = {
        "http://site.test/": ["https://site.test/about", "https://other.example/"],
        "https://site.test/about": ["https://site.test/contact"],
    }
    pages = crawl(
        "http://site.test/", lambda url: (PageResult(url=url, status=200), site.get(url, []))
    )
    assert visited_urls(pages) == [
        "http://site.test/",
        "https://site.test/about",
        "https://site.test/contact",
    ]


def test_links_the_skip_function_refuses_are_never_visited():
    # Run 4, J2: a signed-in crawl must not follow a "log out" link and end its own session.
    site = {f"{BASE}/": [f"{BASE}/account", f"{BASE}/logout"], f"{BASE}/account": []}
    pages = crawl(
        f"{BASE}/",
        lambda url: (PageResult(url=url, status=200), site.get(url, [])),
        skip_link=lambda url: url.endswith("/logout"),
    )
    assert visited_urls(pages) == [f"{BASE}/", f"{BASE}/account"]
