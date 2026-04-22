import sys
import os
import asyncio
import json
import concurrent.futures
from datetime import datetime
from typing import List

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
from models import Outcome, OddsLine
from arb_engine import scan_for_arbs

app = FastAPI(title="CS2 Arb Scanner")

# ── Estado da sessão ──────────────────────────────────────────────
state = {
    "bankroll": 100.0,
    "odds_lines": [],
    "arbs": [],
    "bets_history": [],
}

subscribers: list = []


# ── Broadcast SSE ─────────────────────────────────────────────────
async def broadcast(event_type: str, message: str, data=None):
    payload = {
        "type": event_type,
        "message": message,
        "time": datetime.now().strftime("%H:%M:%S"),
        "data": data or {},
    }
    for q in subscribers[:]:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def serialize_arbs(opps):
    result = []
    for arb in opps:
        line = arb.odds_line
        result.append({
            "match": f"{line.team_home} vs {line.team_away}",
            "market": line.market,
            "game_datetime": line.game_datetime,
            "arb_percent": arb.arb_percent,
            "implied_sum": arb.implied_sum,
            "bankroll": arb.bankroll,
            "target_payout": arb.target_payout,
            "guaranteed_profit": arb.guaranteed_profit,
            "stakes": [
                {
                    "outcome": o.name,
                    "bookmaker": o.bookmaker,
                    "odds": o.odds,
                    "stake": s,
                    "return_val": round(s * o.odds, 2),
                }
                for o, s in arb.stakes
            ],
        })
    return result


# ── SSE endpoint ──────────────────────────────────────────────────
@app.get("/events")
async def sse(request: Request):
    queue = asyncio.Queue(maxsize=50)
    subscribers.append(queue)

    async def generate():
        try:
            await queue.put({
                "type": "connected",
                "message": "Conectado ao scanner",
                "time": datetime.now().strftime("%H:%M:%S"),
                "data": {},
            })
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            if queue in subscribers:
                subscribers.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── API endpoints ─────────────────────────────────────────────────
@app.post("/api/fetch-hltv")
async def fetch_hltv():
    await broadcast("info", "🔍 Abrindo HLTV... aguarde (15-30s)")
    try:
        from hltv_scraper import scrape_hltv_odds
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            lines = await loop.run_in_executor(pool, scrape_hltv_odds)
        if lines:
            state["odds_lines"].extend(lines)
            await broadcast("success", f"✓ {len(lines)} linha(s) carregadas do HLTV")
            return {"ok": True, "count": len(lines)}
        else:
            await broadcast("warning", "⚠ Nenhuma odd encontrada — HLTV pode ter mudado o layout")
            return {"ok": False, "message": "Sem odds"}
    except Exception as e:
        await broadcast("error", f"✗ Erro HLTV: {str(e)}")
        return {"ok": False, "message": str(e)}


@app.post("/api/scan")
async def scan():
    if not state["odds_lines"]:
        await broadcast("warning", "⚠ Sem odds carregadas. Use Buscar HLTV ou Adicionar Manual.")
        return {"ok": False, "arbs": []}
    await broadcast("info", f"🔎 Escaneando {len(state['odds_lines'])} linha(s) com bankroll R${state['bankroll']:.2f}...")
    opps = scan_for_arbs(state["odds_lines"], state["bankroll"])
    arbs = serialize_arbs(opps)
    state["arbs"] = arbs
    if arbs:
        await broadcast("success", f"✓ {len(arbs)} arbitragem(ns) encontrada(s)!", {"arbs": arbs})
    else:
        await broadcast("info", "ℹ Nenhuma arbitragem encontrada nas odds atuais.")
    return {"ok": True, "arbs": arbs}


@app.get("/api/state")
async def get_state():
    odds_data = [
        {
            "match": f"{line.team_home} vs {line.team_away}",
            "market": line.market,
            "bookmaker": outcome.bookmaker,
            "outcome": outcome.name,
            "odds": outcome.odds,
            "source": line.source,
        }
        for line in state["odds_lines"]
        for outcome in line.outcomes
    ]
    return {
        "bankroll": state["bankroll"],
        "odds": odds_data,
        "arbs": state["arbs"],
        "odds_count": len(state["odds_lines"]),
        "bets_history": state["bets_history"],
    }


class BankrollPayload(BaseModel):
    bankroll: float


@app.put("/api/bankroll")
async def update_bankroll(data: BankrollPayload):
    if data.bankroll <= 0:
        return {"ok": False}
    state["bankroll"] = data.bankroll
    await broadcast("info", f"💰 Bankroll atualizado: R${data.bankroll:.2f}")
    return {"ok": True, "bankroll": state["bankroll"]}


class OutcomeInput(BaseModel):
    name: str
    odds: float


class BookmakerInput(BaseModel):
    name: str
    outcomes: List[OutcomeInput]


class ManualOddsPayload(BaseModel):
    match_name: str
    market: str
    bookmakers: List[BookmakerInput]
    game_datetime: str = ""


@app.post("/api/manual-odds")
async def add_manual(data: ManualOddsPayload):
    parts = [p.strip() for p in data.match_name.split("vs")]
    home = parts[0] if parts else "Time 1"
    away = parts[1] if len(parts) > 1 else "Time 2"
    match_id = data.match_name.lower().replace(" ", "_").replace("vs", "v")
    added = 0
    for bm in data.bookmakers:
        outcomes = [Outcome(name=o.name, odds=o.odds, bookmaker=bm.name) for o in bm.outcomes]
        if outcomes:
            state["odds_lines"].append(OddsLine(
                match_id=match_id,
                team_home=home,
                team_away=away,
                market=data.market,
                outcomes=outcomes,
                source="manual",
                game_datetime=data.game_datetime,
            ))
            added += 1
    await broadcast("success", f"✓ {added} casa(s) adicionada(s) para '{data.match_name}'")
    return {"ok": True, "added": added}


class BetFeitaPayload(BaseModel):
    arb: dict


@app.post("/api/bet-feita")
async def bet_feita(data: BetFeitaPayload):
    entry = {
        **data.arb,
        "registered_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    state["bets_history"].append(entry)
    await broadcast("success", f"✅ Bet registrada: {data.arb.get('match', '?')}")
    return {"ok": True, "total": len(state["bets_history"])}


@app.delete("/api/bets")
async def clear_bets():
    state["bets_history"] = []
    await broadcast("info", "🗑 Histórico de bets limpo.")
    return {"ok": True}


@app.delete("/api/odds")
async def clear_odds():
    state["odds_lines"] = []
    state["arbs"] = []
    await broadcast("info", "🗑 Odds limpas.")
    return {"ok": True}


@app.post("/api/demo")
async def load_demo():
    """Carrega odds de demonstração com arbitragem garantida para teste."""
    state["odds_lines"] = []
    state["arbs"] = []

    demo_matches = [
        {
            "home": "9z", "away": "alka",
            "market": "h2h",
            "books": [
                ("Stake",   [2.20, 1.70]),
                ("1xBet",   [2.05, 1.85]),
                ("Betsson", [1.95, 1.95]),
                ("Vbet",    [2.10, 1.80]),
                ("Betboom", [1.88, 2.05]),
            ],
        },
        {
            "home": "NAVI", "away": "Vitality",
            "market": "h2h",
            "books": [
                ("Stake",   [1.65, 2.30]),
                ("1xBet",   [1.70, 2.20]),
                ("Betsson", [1.60, 2.40]),
                ("Vbet",    [1.75, 2.10]),
            ],
        },
        {
            "home": "9z", "away": "alka",
            "market": "maps_total",
            "books": [
                ("Stake",   [1.90, 1.90]),
                ("Betboom", [1.95, 1.85]),
                ("1xBet",   [2.00, 1.80]),
            ],
        },
    ]

    for m in demo_matches:
        match_id = f"{m['home']}_{m['away']}_{m['market']}".lower()
        for book_name, odds in m["books"]:
            if m["market"] == "maps_total":
                names = ["Over", "Under"]
            else:
                names = [m["home"], m["away"]]
            outcomes = [
                Outcome(name=names[0], odds=odds[0], bookmaker=book_name),
                Outcome(name=names[1], odds=odds[1], bookmaker=book_name),
            ]
            state["odds_lines"].append(OddsLine(
                match_id=match_id,
                team_home=m["home"],
                team_away=m["away"],
                market=m["market"],
                outcomes=outcomes,
                source="manual",
            ))

    total = len(state["odds_lines"])
    await broadcast("success", f"✓ Demo carregado: {total} entradas de odds em 3 partidas")
    return {"ok": True, "count": total}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
