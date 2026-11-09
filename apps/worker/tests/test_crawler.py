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
