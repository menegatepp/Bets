import asyncio
import os
from bs4 import BeautifulSoup
from models import Outcome, OddsLine

HLTV_ODDS_URL = "https://www.hltv.org/betting/money"
DEBUG_HTML = os.path.join(os.path.dirname(__file__), "hltv_debug.html")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.201 Safari/537.36"
)


async def _fetch_page() -> str:
    from playwright.async_api import async_playwright
    try:
        from playwright_stealth import stealth_async
        use_stealth = True
    except ImportError:
        use_stealth = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        page = await context.new_page()

        if use_stealth:
            await stealth_async(page)

        # Simula comportamento humano
        await page.goto("https://www.hltv.org", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        await page.goto(HLTV_ODDS_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Move o mouse simulando leitura
        await page.mouse.move(400, 300)
        await asyncio.sleep(1)

        html = await page.content()

        # Salva HTML para debug
        try:
            with open(DEBUG_HTML, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass

        await browser.close()
        return html


def _parse_html(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    lines = []

    # Verifica se Cloudflare bloqueou
    title = soup.find("title")
    if title and ("just a moment" in title.text.lower() or "attention required" in title.text.lower()):
        return []  # Bloqueado por Cloudflare

    # Estratégia 1: seletores conhecidos do HLTV
    lines = _try_hltv_selectors(soup)
    if lines:
        return lines

    # Estratégia 2: extração heurística por proximidade de odds
    lines = _heuristic_extract(soup)
    return lines


def _try_hltv_selectors(soup) -> list:
    lines = []
    selectors = [
        "tr.bet-row",
        "[class*='betRow']",
        "[class*='matchOdds']",
        "[class*='bettingRow']",
        "[class*='oddsRow']",
        "tr[class*='match']",
    ]
    for sel in selectors:
        rows = soup.select(sel)
        if rows:
            for row in rows:
                parsed = _parse_row_generic(row)
                lines.extend(parsed)
            if lines:
                return lines

    # Tenta tabelas genéricas com odds
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            parsed = _parse_row_generic(row)
            lines.extend(parsed)
        if lines:
            return lines

    return lines


def _extract_decimal_odds(text: str) -> list:
    import re
    return [float(m) for m in re.findall(r'\b([1-9]\d?(?:\.\d{1,2})?)\b', text)
            if 1.05 <= float(m) <= 25.0]


def _parse_row_generic(row) -> list:
    text = row.get_text(separator=" ")
    odds_vals = _extract_decimal_odds(text)
    if len(odds_vals) < 2:
        return []

    # Tenta extrair nomes de times
    teams = []
    for tag in ["strong", "span", "a", "td"]:
        for el in row.find_all(tag):
            t = el.get_text(strip=True)
            if t and len(t) > 1 and len(t) < 40 and not any(c.isdigit() for c in t[:3]):
                teams.append(t)
            if len(teams) >= 2:
                break
        if len(teams) >= 2:
            break

    if len(teams) < 2:
        return []

    home, away = teams[0], teams[1]
    match_id = f"{home}_{away}".lower().replace(" ", "_")[:40]
    lines = []

    # Pares de odds → cada par é uma casa diferente
    for i in range(0, min(len(odds_vals) - 1, 10), 2):
        bookmaker = f"Casa {i//2 + 1}"
        # Tenta capturar nome da casa de atributos data-*
        outcomes = [
            Outcome(name=home, odds=odds_vals[i],   bookmaker=bookmaker),
            Outcome(name=away, odds=odds_vals[i+1], bookmaker=bookmaker),
        ]
        lines.append(OddsLine(
            match_id=match_id,
            team_home=home,
            team_away=away,
            market="h2h",
            outcomes=outcomes,
            source="hltv",
        ))
    return lines


def _heuristic_extract(soup) -> list:
    """Extração por blocos de conteúdo com padrão de odds."""
    import re
    lines = []
    # Encontra todos os blocos que contêm padrão de odds (dois números decimais próximos)
    for block in soup.find_all(["div", "article", "section"], recursive=True):
        text = block.get_text(separator="|")
        # Padrão: "Time A ... 2.10 ... 1.75 ... Time B"
        numbers = re.findall(r'(\d+\.\d{2})', text)
        odds = [float(n) for n in numbers if 1.05 <= float(n) <= 20.0]
        if len(odds) >= 2 and len(block.find_all()) < 30:  # Bloco folha
            words = [w for w in re.split(r'[\|\s]+', text) if len(w) > 2 and not re.match(r'^\d', w)]
            if len(words) >= 2:
                home, away = words[0][:20], words[1][:20]
                match_id = f"{home}_{away}".lower().replace(" ", "_")
                outcomes = [
                    Outcome(name=home, odds=odds[0], bookmaker="HLTV"),
                    Outcome(name=away, odds=odds[1], bookmaker="HLTV"),
                ]
                lines.append(OddsLine(
                    match_id=match_id,
                    team_home=home,
                    team_away=away,
                    market="h2h",
                    outcomes=outcomes,
                    source="hltv",
                ))
                if len(lines) >= 20:
                    break
    return lines


def scrape_hltv_odds() -> list:
    """Entry point síncrono."""
    html = asyncio.run(_fetch_page())
    return _parse_html(html)
