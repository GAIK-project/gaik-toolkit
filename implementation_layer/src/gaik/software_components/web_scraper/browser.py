"""Render pages in headless Chromium, for sites that build their content with JavaScript.

Needs the ``web-scraper-browser`` extra and a browser download::

    pip install "gaik[web-scraper-browser]"
    playwright install chromium

Playwright's sync API is bound to the thread that started it, and it refuses to run
in a thread with a running asyncio event loop: call the scraper from a worker thread
in an async server.
"""

from __future__ import annotations

from .policy import ScrapeError, UrlPolicy

_SKIPPED_RESOURCES = frozenset({"image", "media", "font"})
_SETTLE_MS = 5000


def browser_available() -> bool:
    """Whether Playwright is installed (the browser itself may still be missing)."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


class BrowserRenderer:
    """One headless Chromium, reused for every page a scraper renders."""

    def __init__(self, user_agent: str, timeout_seconds: float):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ImportError(
                "render_js needs Playwright: pip install 'gaik[web-scraper-browser]' "
                "and run `playwright install chromium`"
            ) from exc
        self._timeout_ms = timeout_seconds * 1000
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context(user_agent=user_agent)
        except Exception:
            self._playwright.stop()
            raise

    def render(self, url: str, policy: UrlPolicy) -> tuple[str, int, str]:
        """Load the page, wait for the network to settle; return final URL, status, HTML.

        The policy guards every request the page makes: page navigations must stay in
        the allowed domains, and no request (scripts, images, XHR) may reach a private
        address.
        """
        page = self._context.new_page()
        refused: list[str] = []

        def guard(route) -> None:
            request = route.request
            if request.resource_type in _SKIPPED_RESOURCES:
                route.abort()  # not needed for the text, and the slowest to load
                return
            is_page = request.is_navigation_request() and request.frame == page.main_frame
            reason = policy.refusal(request.url, check_domains=is_page)
            if reason is None:
                route.continue_()
                return
            if is_page:
                refused.append(reason)
            route.abort()

        try:
            page.route("**/*", guard)
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            except Exception as exc:  # Playwright raises its own Error/TimeoutError
                if refused:
                    raise ScrapeError(url, refused[0]) from exc
                raise ScrapeError(url, f"the browser could not load the page: {exc}") from exc
            if refused:
                raise ScrapeError(url, refused[0])
            try:
                # Give scripts a moment to fetch and render the content. Analytics and
                # chat widgets often keep the network busy for good, so do not wait
                # for full idleness.
                page.wait_for_load_state("networkidle", timeout=_SETTLE_MS)
            except Exception:  # noqa: BLE001 - a busy network is not an error
                pass
            status = response.status if response is not None else 200
            return page.url, status, page.content()
        finally:
            page.close()

    def close(self) -> None:
        try:
            self._context.close()
            self._browser.close()
        finally:
            self._playwright.stop()
