import logging

import pytest

from worker.safety.actions import ElementInfo, check_mode
from worker.safety.network import NetworkGuard, dev_allowed_local, is_public_ip
from worker.safety.secrets import MASK, RedactingFilter, redact

# --- 6.1 SSRF guard ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.1.2.3",  # 10/8
        "172.16.5.4",  # 172.16/12
        "192.168.1.1",  # 192.168/16
        "169.254.169.254",  # link-local / cloud metadata
        "::1",  # IPv6 loopback
        "fd12:3456::1",  # fc00::/7 unique local
        "::ffff:10.0.0.1",  # IPv4-mapped private address
        "100.100.100.200",  # Alibaba metadata
        "0.0.0.0",
    ],
)
def test_private_and_internal_ips_are_not_public(ip):
    assert not is_public_ip(ip)


def test_public_ip_is_public():
    assert is_public_ip("93.184.215.14")


def guard(**fake_dns) -> NetworkGuard:
    """A guard with fake DNS: host name → list of IPs."""
    dns = {host.replace("_", "."): ips for host, ips in fake_dns.items()}
    return NetworkGuard(resolver=lambda host: dns.get(host, []))


def test_public_host_is_allowed():
    assert guard(example_com=["93.184.215.14"]).check("https://example.com/") is None


def test_host_resolving_to_private_ip_is_blocked():
    reason = guard(evil_test=["10.0.0.5"]).check("http://evil.test/")
    assert "private" in reason


def test_host_with_any_private_ip_is_blocked():
    # DNS can return several addresses; one internal one is enough to refuse.
    assert guard(mixed_test=["93.184.215.14", "127.0.0.1"]).check("http://mixed.test/")


def test_ip_literal_metadata_endpoint_is_blocked():
    g = NetworkGuard()  # real resolver: an IP literal resolves to itself
    assert g.check("http://169.254.169.254/latest/meta-data/")


def test_metadata_hostname_is_blocked():
    assert guard().check("http://metadata.google.internal/computeMetadata/v1/")


def test_unresolvable_host_is_blocked():
    assert "resolve" in guard().check("http://does-not-exist.test/")


def test_non_http_schemes_are_blocked_but_data_urls_are_fine():
    g = guard()
    assert g.check("file:///etc/passwd")
    assert g.check("data:image/png;base64,AAAA") is None


def test_dev_mode_allows_only_our_own_localhost_ports():
    g = NetworkGuard(allowed_local=dev_allowed_local(["http://localhost:5173"]))
    assert g.check("http://localhost:5173/cart") is None
    assert g.check("http://127.0.0.1:5173/") is None
    assert g.check("http://localhost:5432/")  # Postgres: still blocked
    assert g.check("http://localhost:3000/")  # our own web app: not a test target


def test_navigation_must_stay_on_the_target_origin():
    g = NetworkGuard(
        allowed_local=dev_allowed_local(["http://localhost:5173"]),
        target_url="http://localhost:5173/",
        resolver=lambda host: ["93.184.215.14"],
    )
    assert g.check_navigation("http://localhost:5173/products/1") is None
    assert "origin" in g.check_navigation("https://example.com/")
    assert g.check("https://example.com/font.woff2") is None  # subresources may be elsewhere


def test_navigation_may_follow_the_target_to_https():
    g = NetworkGuard(target_url="http://shop.test/", resolver=lambda host: ["93.184.215.14"])
    assert g.check_navigation("https://shop.test/cart") is None
    assert "origin" in g.check_navigation("https://other.test/")


# --- 6.2 passive mode --------------------------------------------------------------------------

LINK = ElementInfo(role="link", name="About", tag="a", href="/about")
BUTTON = ElementInfo(role="button", name="Place order", tag="button", input_type="submit")


@pytest.mark.parametrize("action", ["type", "select", "submit"])
def test_passive_mode_blocks_input_actions(action):
    assert check_mode("passive", action, LINK)


def test_passive_mode_allows_clicking_links():
    assert check_mode("passive", "click", LINK) is None


def test_passive_mode_blocks_clicking_buttons():
    assert "passive" in check_mode("passive", "click", BUTTON)


def test_passive_mode_allows_read_only_actions():
    for action in ("navigate", "go_back", "scroll", "take_screenshot", "report_bug", "finish"):
        assert check_mode("passive", action) is None


def test_interactive_mode_allows_input():
    assert check_mode("interactive", "type", BUTTON) is None


# --- 6.6 secrets -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "key=sk-ant-api03-abcdefghijklmnop",
        "Authorization: Bearer abc.def.ghi-jkl",
        "fetch failed: token=supersecretvalue123",
        "password: hunter2hunter2",
    ],
)
def test_redact_masks_secrets(text):
    redacted = redact(text)
    assert MASK in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "supersecretvalue123" not in redacted
    assert "hunter2hunter2" not in redacted


def test_redact_masks_known_exact_secret():
    assert redact("my key is xyz-123-custom", known_secrets=("xyz-123-custom",)) == (
        f"my key is {MASK}"
    )


def test_redact_leaves_normal_text_alone():
    text = "TypeError: Cannot read properties of undefined (reading 'category')"
    assert redact(text) == text


def test_log_filter_redacts(caplog):
    logger = logging.getLogger("test-redact")
    logger.addFilter(RedactingFilter(known_secrets=("sk-live-123456",)))
    with caplog.at_level(logging.INFO, logger="test-redact"):
        logger.info("calling API with %s", "sk-live-123456")
    assert "sk-live-123456" not in caplog.text
    assert MASK in caplog.text


# --- dev mode is off unless switched on ---------------------------------------------------------


def test_without_dev_mode_the_local_demo_shops_are_refused():
    from worker.config import Settings
    from worker.scan import make_guard

    settings = Settings(_env_file=None)  # nothing set: must be the safe choice
    assert settings.dev_mode is False
    guard = make_guard(settings, settings.demo_url)
    assert "private or internal" in guard.check("http://localhost:5173/")
    assert "private or internal" in guard.check("http://localhost:5174/")


def test_dev_mode_has_to_be_switched_on_explicitly():
    from worker.config import Settings
    from worker.scan import make_guard

    settings = Settings(_env_file=None, dev_mode=True)
    guard = make_guard(settings, settings.demo_url)
    assert guard.check("http://localhost:5173/") is None
    assert guard.check("http://localhost:3000/") is not None  # only the demo shops' ports


def test_dev_mode_allows_the_demo_shops_own_host_name_too():
    # Run 4, J6: in the local production stack the worker runs in a container and reaches the
    # demo shop on the host as host.docker.internal; still only that port, still only in dev mode.
    from worker.safety.network import dev_allowed_local

    allowed = dev_allowed_local(["http://host.docker.internal:5173/"])
    assert ("host.docker.internal", 5173) in allowed
    assert ("localhost", 5173) in allowed
    assert ("host.docker.internal", 5432) not in allowed
