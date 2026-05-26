import asyncio
import json
import re
import sys
import threading
import traceback
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
    from bs4 import BeautifulSoup
    _REQUESTS = True
except ImportError:
    _REQUESTS = False

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    _PLAYWRIGHT = True
except ImportError:
    _PLAYWRIGHT = False

try:
    import google.generativeai as genai
    _GENAI = True
except ImportError:
    _GENAI = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_api_key() -> str:
    return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))["gemini_api_key"]


STORES = {
    "amazon": {"name": "Amazon", "url": "https://www.amazon.com/s?k={q}", "container": '[data-component-type="s-search-result"]', "name_sel": 'h2 a span', "price_sel": '.a-price-whole', "rating_sel": 'i.a-icon-star span.a-icon-alt', "link_sel": 'h2 a.a-link-normal'},
    "mercadolibre": {"name": "MercadoLibre", "url": "https://listado.mercadolibre.com/{q}#D[A:{q}]", "container": '.ui-search-layout__item', "name_sel": '.ui-search-item__title', "price_sel": '.andes-money-amount__fraction', "rating_sel": '.ui-search-reviews__rating', "link_sel": 'a.ui-search-link'},
    "walmart": {"name": "Walmart", "url": "https://www.walmart.com/search?q={q}", "container": '[data-item-id]', "name_sel": 'span[data-automation-id="product-title"]', "price_sel": '.f2', "rating_sel": '.stars-container', "link_sel": 'a[link-identifier="item title"]'},
    "bestbuy": {"name": "Best Buy", "url": "https://www.bestbuy.com/site/searchpage.jsp?st={q}", "container": '.shop-sku-list-item', "name_sel": '.sku-header a', "price_sel": '.priceView-customer-price span', "rating_sel": '.ratings-reviews div', "link_sel": '.sku-header a'},
    "ebay": {"name": "eBay", "url": "https://www.ebay.com/sch/i.html?_nkw={q}", "container": '.s-item', "name_sel": '.s-item__title span', "price_sel": '.s-item__price', "rating_sel": '.x-star-rating span', "link_sel": '.s-item__link'},
}


def _normalize_store(s: str) -> str:
    m = {"amazon":"amazon","amz":"amazon","mercadolibre":"mercadolibre","ml":"mercadolibre","walmart":"walmart","bestbuy":"bestbuy","best buy":"bestbuy","ebay":"ebay"}
    return m.get(s.lower().strip(), s.lower().strip())


class _Browser:
    def __init__(self):
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._pw = self._browser = self._context = self._page = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=30)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init())
        self._ready.set()
        self._loop.run_forever()

    async def _init(self):
        if not _PLAYWRIGHT:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=False, args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
        self._context = await self._browser.new_context(viewport={"width": 1280, "height": 800})
        self._page = await self._context.new_page()

    def run(self, coro, timeout=120):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    async def goto(self, url):
        p = self._page or await self._context.new_page()
        try:
            await p.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)
            return await p.title()
        except Exception as e:
            return str(e)

    async def get_text(self):
        try:
            return await (self._page or await self._context.new_page()).inner_text("body")
        except Exception:
            return ""

    async def search_store(self, store_key: str, query: str):
        cfg = STORES.get(store_key)
        if not cfg:
            return []
        url = cfg["url"].format(q=quote_plus(query))
        p = self._page or await self._context.new_page()
        await p.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        try:
            await p.wait_for_selector(cfg["container"], timeout=8000)
        except Exception:
            pass
        html = await p.content()
        return self._parse(store_key, html)

    def _parse(self, store_key: str, html: str):
        cfg = STORES.get(store_key)
        if not cfg:
            return []
        products = []
        soup = BeautifulSoup(html, "html.parser")
        for c in soup.select(cfg["container"])[:15]:
            try:
                name_el = c.select_one(cfg["name_sel"])
                name = name_el.get_text(strip=True) if name_el else ""
                price_el = c.select_one(cfg["price_sel"])
                price = price_el.get_text(strip=True)[:20] if price_el else ""
                rating_el = c.select_one(cfg["rating_sel"])
                rating = re.search(r'[\d.]+', rating_el.get_text(strip=True)).group() if rating_el else ""
                link_el = c.select_one(cfg["link_sel"])
                link = ""
                if link_el:
                    href = link_el.get("href", "")
                    if href and not href.startswith("http"):
                        domain = cfg["url"].split("/")[2]
                        href = f"https://{domain}{href}" if href.startswith("/") else f"https://{domain}/{href}"
                    link = href
                if name:
                    products.append({"name": name, "price": price, "rating": rating, "link": link, "store": cfg["name"]})
            except Exception:
                continue
        return products

    async def add_to_cart(self, url: str):
        p = self._page or await self._context.new_page()
        try:
            await p.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            for sel in ['#add-to-cart-button', '[value="Add to Cart"]', 'button:has-text("Cart")', 'button:has-text("cart")']:
                try:
                    btn = p.locator(sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=5000)
                        await asyncio.sleep(1.5)
                        return "Added to cart."
                except Exception:
                    continue
            return "Could not find add-to-cart button."
        except Exception as e:
            return f"Error: {e}"

    async def buy(self, url: str):
        p = self._page or await self._context.new_page()
        try:
            await p.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            for sel in ['#buy-now-button', '[value="Buy Now"]', 'button:has-text("Buy")']:
                try:
                    btn = p.locator(sel)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=5000)
                        await asyncio.sleep(2)
                        return "Proceeding to checkout."
                except Exception:
                    continue
            return "Could not find buy button."
        except Exception as e:
            return f"Error: {e}"


_browser = None
_browser_lock = threading.Lock()


def _get_browser():
    global _browser
    with _browser_lock:
        if _browser is None and _PLAYWRIGHT:
            _browser = _Browser()
            _browser.start()
        return _browser


def _ai_analyze(products, query: str):
    if not _GENAI:
        return _fallback(products, query)
    try:
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = f"""You are a shopping advisor. For the query "{query}", analyze these products:

{json.dumps(products, indent=2, ensure_ascii=False)}

Return JSON with: {{"best_pick":"product name","reasoning":"why (2 sentences)","comparison":"table of top 3 with prices/ratings","savings_tip":"money saving tip"}}
Only JSON, no markdown."""
        resp = model.generate_content(prompt)
        text = re.sub(r"```(?:json)?", "", resp.text).strip().rstrip("`").strip()
        try:
            d = json.loads(text)
            return f"Best: {d.get('best_pick','?')}\nWhy: {d.get('reasoning','')}\n\n{d.get('comparison','')}\n\nTip: {d.get('savings_tip','')}"
        except Exception:
            return text
    except Exception:
        return _fallback(products, query)


def _fallback(products, query):
    if not products:
        return "No products found."
    lines = [f"Results for: {query}", ""]
    for p in products[:5]:
        lines.append(f"{p.get('name','')[:40]:<42} {p.get('price',''):<16} {p.get('rating','N/A'):<8} {p.get('store','')}")
    return "\n".join(lines)


def _search_requests(query: str, store_key: str) -> list:
    cfg = STORES.get(store_key)
    if not cfg or not _REQUESTS:
        return []
    try:
        url = cfg["url"].format(q=quote_plus(query))
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"}, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        products = []
        for c in soup.select(cfg["container"])[:15]:
            try:
                name_el = c.select_one(cfg["name_sel"])
                name = name_el.get_text(strip=True) if name_el else ""
                price_el = c.select_one(cfg["price_sel"])
                price = price_el.get_text(strip=True)[:20] if price_el else ""
                if name:
                    products.append({"name": name, "price": price, "store": cfg["name"]})
            except Exception:
                continue
        return products
    except Exception:
        return []


def shopping_assistant(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").strip().lower()
    query = params.get("query", "").strip()
    store = params.get("store", "").strip()
    stores_raw = params.get("stores", "")
    url = params.get("url", "").strip()
    mode = params.get("mode", "best_value").strip().lower()

    if isinstance(stores_raw, str):
        store_list = [s.strip() for s in stores_raw.split(",") if s.strip()]
    else:
        store_list = list(stores_raw) if stores_raw else []
    if store and store not in store_list:
        store_list.insert(0, _normalize_store(store))

    if player:
        player.write_log(f"[Shopping] {action}: {query or url}")

    try:
        if action in ("navigate", "visit", "analyze_page"):
            if not url:
                return "Provide a URL."
            b = _get_browser()
            if not b:
                return "Playwright required."
            title = b.run(b.goto(url))
            text = b.run(b.get_text())
            if _GENAI:
                genai.configure(api_key=_get_api_key())
                model = genai.GenerativeModel("gemini-2.5-flash-lite")
                r = model.generate_content(f"You visited {url}\nTitle: {title}\nContent:\n{text[:4000]}\n\nAnalyze this page. What is it? Is it a good deal/option for the user? Give your honest opinion. Be concise.")
                return r.text[:2000]
            return f"Visited: {title}"

        elif action in ("search", "find", "compare", "shop"):
            if not query:
                return "Specify a product."
            if not store_list:
                store_list = list(STORES.keys())
            all_prods = []
            b = _get_browser()
            if b:
                for s in store_list:
                    n = _normalize_store(s)
                    if n in STORES:
                        try:
                            all_prods.extend(b.run(b.search_store(n, query)))
                        except Exception:
                            pass
            if not all_prods:
                for s in store_list:
                    n = _normalize_store(s)
                    if n in STORES:
                        all_prods.extend(_search_requests(query, n))
            if all_prods:
                return _ai_analyze(all_prods, query)
            return "No products found."

        elif action in ("reviews", "details", "product_info"):
            if not url:
                return "Provide a product URL."
            b = _get_browser()
            if not b:
                return "Playwright required."
            b.run(b.goto(url))
            text = b.run(b.get_text())
            if _GENAI:
                genai.configure(api_key=_get_api_key())
                model = genai.GenerativeModel("gemini-2.5-flash-lite")
                r = model.generate_content(f"Product URL: {url}\nPage content:\n{text[:5000]}\n\nAnalyze: key features, price, reviews, quality rating. Would you recommend? Honest opinion.")
                return r.text[:2000]
            return "Product page loaded."

        elif action in ("add_to_cart", "cart"):
            if not url:
                return "Provide product URL."
            b = _get_browser()
            if not b:
                return "Playwright required."
            return b.run(b.add_to_cart(url))

        elif action in ("buy", "purchase", "checkout"):
            if not url:
                return "Provide product URL."
            b = _get_browser()
            if not b:
                return "Playwright required."
            return b.run(b.buy(url))

        elif action == "compare_urls":
            urls = [u.strip() for u in (params.get("urls", "") or "").split(",") if u.strip()]
            if len(urls) < 2:
                return "Need at least 2 URLs."
            b = _get_browser()
            if not b:
                return "Playwright required."
            texts = []
            for u in urls[:4]:
                b.run(b.goto(u))
                texts.append({"url": u, "text": b.run(b.get_text())[:3000]})
            if _GENAI:
                genai.configure(api_key=_get_api_key())
                model = genai.GenerativeModel("gemini-2.5-flash-lite")
                r = model.generate_content(f"Compare these products:\n{json.dumps(texts, indent=2)}\nCompare prices, quality, value. Which is best? Honest opinion.")
                return r.text[:2000]
            return "Comparison done."

        return "Actions: search, navigate, reviews, add_to_cart, buy, compare_urls"

    except Exception as e:
        traceback.print_exc()
        return f"Shopping error: {e}"
