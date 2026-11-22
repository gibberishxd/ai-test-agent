"""The meta/SEO check: the tags that decide how a page looks when it is shared or bookmarked.

Checked once per page, against the Open Graph protocol (ogp.me: og:title, og:type, og:image and
og:url are its required properties; og:description is recommended), X/Twitter's card markup
(twitter:card), a canonical link, and the icons browsers and phones show (a favicon, and
apple-touch-icon for home screens).

The og:image must be a real image: not a placeholder service, and one that loads. It is loaded
through the run's own browser context, so the safety proxy vets it like any other request, and
once per scan (a site usually shares one image across pages).
"""

from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from worker.report import MetaCheck

IMAGE_TIMEOUT_MS = 5000

# Image placeholder services: an og:image there was never replaced with the real picture.
PLACEHOLDER_HOSTS = (
    "placehold.co",
    "placehold.it",
    "placeholder.com",  # via.placeholder.com
    "dummyimage.com",
    "fakeimg.pl",
    "placekitten.com",
    "placeimg.com",
    "lorempixel.com",
    "loremflickr.com",
    "picsum.photos",
)

META_JS = """() => {
  const content = (key) => {
    const el = document.querySelector(`meta[property="${key}"], meta[name="${key}"]`);
    const value = el && (el.getAttribute('content') || '').trim();
    return value || null;
  };
  const link = (rels) => {
    for (const el of document.querySelectorAll('link[rel][href]')) {
      const own = el.getAttribute('rel').toLowerCase().split(/\\s+/);
      if (rels.some((r) => own.includes(r))) return el.href;
    }
    return null;
  };
  return {
    'og:title': content('og:title'),
    'og:description': content('og:description'),
    'og:url': content('og:url'),
    'og:image': content('og:image') || content('og:image:url'),
    'twitter:card': content('twitter:card'),
    canonical: link(['canonical']),
    icon: link(['icon']),
    apple: link(['apple-touch-icon', 'apple-touch-icon-precomposed']),
  };
}"""


def placeholder_host(url: str) -> str | None:
    """The placeholder service `url` is on (the host itself or a subdomain of one), if any."""
    host = (urlsplit(url).hostname or "").lower()
    for known in PLACEHOLDER_HOSTS:
        if host == known or host.endswith("." + known):
            return host
    return None


def check_meta(page: Page, image_cache: dict[str, str | None]) -> MetaCheck | None:
    """The page's metadata problems. `image_cache` (url → problem or None) lives per scan."""
    try:
        tags = page.evaluate(META_JS)
    except PlaywrightError:
        return None
    problems = [
        f"{key} missing"
        for key in ("og:title", "og:description", "og:url", "og:image", "twitter:card")
        if not tags[key]
    ]
    image = urljoin(page.url, tags["og:image"]) if tags["og:image"] else None
    if image:
        host = placeholder_host(image)
        if host:
            problems.append(f"og:image is a placeholder ({host})")
        else:
            if image not in image_cache:
                image_cache[image] = _image_problem(page, image)
            if image_cache[image]:
                problems.append(f"og:image {image_cache[image]}")
    if not tags["canonical"]:
        problems.append("canonical link missing")
    if not tags["icon"] and not _default_favicon(page, image_cache):
        problems.append("favicon missing")
    if not tags["apple"]:
        problems.append("apple-touch-icon missing")
    return MetaCheck(og_image=image, problems=problems)


def _image_problem(page: Page, url: str, image_type: bool = True) -> str | None:
    """Why `url` isn't a loadable image, or None if it is. `image_type`: also require an image
    content type (servers often send /favicon.ico as application/octet-stream)."""
    if urlsplit(url).scheme not in ("http", "https"):
        return None  # data: URLs and the like: nothing to load
    try:
        response = page.context.request.get(url, timeout=IMAGE_TIMEOUT_MS)
    except PlaywrightError as error:
        return f"fails to load ({str(error).splitlines()[0][:120]})"
    if response.status >= 400:
        return f"fails to load (HTTP {response.status})"
    kind = response.headers.get("content-type", "")
    if image_type and kind and not kind.startswith("image/"):
        return f"is not an image ({kind.split(';')[0]})"
    return None


def _default_favicon(page: Page, cache: dict[str, str | None]) -> bool:
    """Without an icon link, browsers ask for /favicon.ico: is one there?"""
    url = urljoin(page.url, "/favicon.ico")
    if url not in cache:
        cache[url] = _image_problem(page, url, image_type=False)
    return cache[url] is None
