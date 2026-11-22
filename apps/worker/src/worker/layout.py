"""The layout check: what a page looks like at the run's screen size, measured, not judged.

Three problems, each against a published threshold (none from any one site):
- the page is wider than the screen: it scrolls sideways (WCAG 2.1 SC 1.4.10 Reflow). The
  elements that stick out are named, outermost first, skipping ones inside their own scroll
  box or fixed to the screen (they don't widen the page);
- tap targets smaller than 44×44 CSS px on screens under 768 px wide (WCAG 2.2 SC 2.5.5 Target
  Size, and Apple's Human Interface Guidelines: 44×44 pt). WCAG's exceptions are kept: a link
  inside a sentence, a disabled control. A hidden checkbox counts as big as its label;
- visible text under 12 px, outside code blocks (Lighthouse's "legible font sizes" audit uses
  the same 12 px line).

Everything is measured in one page.evaluate, so the check costs one round trip per page.
"""

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from worker.agent.observe import CSS_PATH_JS
from worker.report import LayoutCheck

MIN_TARGET_PX = 44  # WCAG 2.5.5 (AAA) and Apple HIG
SMALL_SCREEN_MAX_PX = 768  # tap targets are checked below this width (phones, small tablets)
MIN_FONT_PX = 12  # Lighthouse's legible-font-size line
MAX_LISTED = 10  # examples kept per problem; the count says how many there are
MAX_STICKING_OUT = 5
MAX_ELEMENTS = 5000  # elements scanned per page, so a huge page can't stall the run
MAX_TEXT_NODES = 20000

LAYOUT_JS = """(opts) => {
  const cssPath = /*CSS_PATH*/;
  const root = document.scrollingElement || document.documentElement;
  const body = document.body;
  const vw = document.documentElement.clientWidth;
  const out = { viewport_width: window.innerWidth, overflow_px: 0, sticking_out: [],
                small_targets: [], small_target_count: 0, small_text: [], small_text_count: 0 };
  if (!body) return out;
  const visible = (el) => el.checkVisibility
    ? el.checkVisibility({ opacityProperty: true, visibilityProperty: true })
    : !!(el.offsetWidth || el.offsetHeight);
  const style = (el) => getComputedStyle(el);
  const elements = Array.from(body.querySelectorAll('*')).slice(0, opts.maxElements);

  // 1. Wider than the screen: content past the right edge that a user can scroll to. With
  //    overflow-x: hidden on the page (the html element's, or else the body's, applies to the
  //    viewport) the extra width is clipped and can't be scrolled to.
  const htmlStyle = style(document.documentElement);
  const viewportOverflow = htmlStyle.overflowX !== 'visible' ? htmlStyle.overflowX
    : style(body).overflowX;
  const scrollable = !['hidden', 'clip'].includes(viewportOverflow);
  if (scrollable && root.scrollWidth > vw) {
    out.overflow_px = Math.round(root.scrollWidth - vw);
    const contained = (el) => {
      for (let n = el; n && n !== body; n = n.parentElement) {
        const s = style(n);
        if (s.position === 'fixed') return true;
        if (n !== el && s.overflowX !== 'visible') return true;
      }
      return false;
    };
    const out_ = elements.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.right + window.scrollX > vw + 1 && !contained(el);
    });
    const set = new Set(out_);
    out.sticking_out = out_.filter((el) => !set.has(el.parentElement))
      .map((el) => ({ selector: cssPath(el), tag: el.tagName.toLowerCase(),
                      right: Math.round(el.getBoundingClientRect().right + window.scrollX),
                      width: Math.round(el.getBoundingClientRect().width) }))
      .sort((a, b) => b.right - a.right)
      .slice(0, opts.maxStickingOut);
  }

  // 2. Small tap targets, on small screens only.
  if (window.innerWidth < opts.smallScreen) {
    const selector = [
      'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea', 'summary',
      '[role=button]', '[role=link]', '[role=checkbox]', '[role=radio]', '[role=tab]',
      '[role=menuitem]', '[role=switch]',
    ].join(',');
    const blockOf = (el) => {
      let n = el.parentElement;
      while (n && n !== body && style(n).display.startsWith('inline')) n = n.parentElement;
      return n;
    };
    // WCAG's inline exception: a link in a line of text, sized by the text around it.
    const inSentence = (el) => {
      if (!style(el).display.startsWith('inline') || style(el).display === 'inline-block') {
        return false;
      }
      const block = blockOf(el);
      if (!block) return false;
      const own = (el.textContent || '').trim().length;
      return (block.textContent || '').trim().length > own + 20;
    };
    const union = (rects) => {
      const r = rects.filter((b) => b.width > 0 && b.height > 0);
      if (!r.length) return null;
      const left = Math.min(...r.map((b) => b.left)), right = Math.max(...r.map((b) => b.right));
      const top = Math.min(...r.map((b) => b.top)), bottom = Math.max(...r.map((b) => b.bottom));
      return { left, right, width: right - left, height: bottom - top };
    };
    for (const el of body.querySelectorAll(selector)) {
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
      if (el.closest('[aria-hidden="true"], [inert]')) continue;
      if (el.parentElement && el.parentElement.closest(selector)) continue;  // counted outside
      const labels = el.labels ? Array.from(el.labels).filter(visible) : [];
      const own = el.getBoundingClientRect();
      const ownShown = visible(el) && own.width > 1 && own.height > 1;
      const parts = [...(ownShown ? [own] : []), ...labels.map((l) => l.getBoundingClientRect())];
      const box = union(parts);
      if (!box) continue;  // not shown at all
      if (box.right <= 0 || box.left >= vw) continue;  // an off-screen menu, not reachable yet
      if (inSentence(el)) continue;
      if (Math.round(box.width) >= opts.minTarget && Math.round(box.height) >= opts.minTarget) {
        continue;
      }
      out.small_target_count++;
      if (out.small_targets.length < opts.maxListed) {
        const name = (el.getAttribute('aria-label') || (labels[0] && labels[0].innerText)
          || el.innerText || el.value || el.getAttribute('title') || '')
          .trim().replace(/\\s+/g, ' ').slice(0, 60);
        out.small_targets.push({ selector: cssPath(el), tag: el.tagName.toLowerCase(), name,
                                 width: Math.round(box.width), height: Math.round(box.height) });
      }
    }
  }

  // 3. Small text, outside code.
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const counted = new Set();
  let scanned = 0;
  for (let node = walker.nextNode(); node && scanned < opts.maxTextNodes;
       node = walker.nextNode()) {
    scanned++;
    const text = node.textContent.trim();
    const parent = node.parentElement;
    if (!text || !parent || counted.has(parent)) continue;
    if (parent.closest('code, pre, kbd, samp, script, style, noscript, template, svg')) continue;
    const size = parseFloat(style(parent).fontSize);
    if (!(size < opts.minFont) || !visible(parent)) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const r = range.getBoundingClientRect();
    const box = parent.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1 || box.width <= 1 || box.height <= 1) {
      continue;  // visually hidden (screen-reader only)
    }
    counted.add(parent);
    out.small_text_count++;
    if (out.small_text.length < opts.maxListed) {
      out.small_text.push({ selector: cssPath(parent), text: text.slice(0, 60),
                            font_size: Math.round(size * 10) / 10 });
    }
  }
  return out;
}""".replace("/*CSS_PATH*/", CSS_PATH_JS)


def check_layout(page: Page) -> LayoutCheck | None:
    """Measure the page at its current viewport. None if the page can't be measured."""
    options = {
        "minTarget": MIN_TARGET_PX,
        "smallScreen": SMALL_SCREEN_MAX_PX,
        "minFont": MIN_FONT_PX,
        "maxListed": MAX_LISTED,
        "maxStickingOut": MAX_STICKING_OUT,
        "maxElements": MAX_ELEMENTS,
        "maxTextNodes": MAX_TEXT_NODES,
    }
    try:
        return LayoutCheck(**page.evaluate(LAYOUT_JS, options))
    except PlaywrightError:
        return None
