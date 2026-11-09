from worker.findings import SLOW_PAGE_MS, findings_from_pages
from worker.report import A11yViolation, ConsoleError, FailedRequest, PageResult

HOME = "http://shop.test/"
CART = "http://shop.test/cart"


def page(url=HOME, **fields) -> PageResult:
    return PageResult(url=url, status=200, **fields)


def by_category(bugs):
    return {b.category: b for b in bugs}


def test_clean_pages_give_no_bugs():
    assert findings_from_pages([page(), page(CART, found_on=HOME)]) == []


def test_uncaught_exception_is_a_high_bug_with_evidence():
    error = ConsoleError(kind="pageerror", text="TypeError: x is undefined")
    [bug] = findings_from_pages([page(console_errors=[error])])
    assert bug.category == "console-error"
    assert bug.severity == "high"
    assert bug.source == "deterministic" and bug.status == "confirmed"
    assert bug.evidence["console_errors"][0]["text"] == "TypeError: x is undefined"
    assert bug.page_url == HOME


def test_same_console_error_on_many_pages_is_one_bug():
    error = ConsoleError(kind="console", text="boom")
    bugs = findings_from_pages([page(console_errors=[error]), page(CART, console_errors=[error])])
    assert len(bugs) == 1
    assert bugs[0].evidence["pages"] == [HOME, CART]


def test_server_error_on_fetch_is_a_network_bug():
    failed = FailedRequest(
        url="http://shop.test/api/profile", method="GET", resource_type="fetch", status=500
    )
    [bug] = findings_from_pages([page(failed_requests=[failed])])
    assert bug.category == "network"
    assert bug.severity == "high"
    assert "500" in bug.actual


def test_missing_image_is_a_medium_network_bug():
    failed = FailedRequest(
        url="http://shop.test/logo.png", method="GET", resource_type="image", status=404
    )
    [bug] = findings_from_pages([page(failed_requests=[failed])])
    assert bug.severity == "medium"


def test_linked_page_returning_404_is_one_broken_link_bug():
    pages = [
        page(),
        PageResult(url="http://shop.test/old", status=404, found_on=HOME),
    ]
    [bug] = findings_from_pages(pages)
    assert bug.category == "broken-link"
    assert bug.page_url == HOME  # where the user meets the broken link
    assert bug.evidence["link"] == "http://shop.test/old"


def test_soft_404_page_counts_as_a_broken_link():
    pages = [
        page(),
        PageResult(url="http://shop.test/nope", status=200, soft_404=True, found_on=HOME),
    ]
    assert by_category(findings_from_pages(pages))["broken-link"]


def test_unreachable_linked_page_is_a_broken_link():
    pages = [
        page(),
        PageResult(url="http://shop.test/x", status=None, error="net::ERR_FAILED", found_on=HOME),
    ]
    assert by_category(findings_from_pages(pages))["broken-link"]


def test_axe_rule_on_many_pages_is_one_bug():
    violation = A11yViolation(
        rule_id="button-name",
        impact="critical",
        help="Buttons must have discernible text",
        help_url="https://dequeuniversity.com/rules/axe/button-name",
        targets=["header button"],
    )
    bugs = findings_from_pages(
        [page(a11y_violations=[violation]), page(CART, a11y_violations=[violation])]
    )
    assert len(bugs) == 1
    assert bugs[0].category == "accessibility"
    assert bugs[0].severity == "medium"
    assert bugs[0].evidence["pages"] == [HOME, CART]


def test_slow_page_is_a_low_performance_bug():
    [bug] = findings_from_pages([page(load_ms=SLOW_PAGE_MS + 1)])
    assert bug.category == "performance"
    assert bug.severity == "low"


def test_document_404_of_a_broken_link_isnt_also_a_failed_request():
    # The 404 page's own response would otherwise appear twice: as a broken link and as a
    # failed "document" request.
    doc = FailedRequest(
        url="http://shop.test/old", method="GET", resource_type="document", status=404
    )
    pages = [
        page(),
        PageResult(url="http://shop.test/old", status=404, found_on=HOME, failed_requests=[doc]),
    ]
    assert [b.category for b in findings_from_pages(pages)] == ["broken-link"]
