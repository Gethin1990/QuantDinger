"""Read-class market data endpoints."""
from __future__ import annotations

from app.data.market_symbols_seed import (
    get_hot_symbols as seed_get_hot_symbols,
    search_symbols as seed_search_symbols,
)
from app.services.kline import KlineService
from app.utils.agent_auth import (
    SCOPE_R, agent_required, instrument_allowed, market_allowed,
)
from app.utils.logger import get_logger
from app.utils.market_visibility import is_market_visible
from flask import request

from . import agent_v1_bp
from ._helpers import clip_int, envelope, error

logger = get_logger(__name__)
_kline_service = KlineService()


_MARKETS = [
    {"value": "USStock",  "label": "US Stocks"},
    {"value": "CNStock",  "label": "China A-shares"},
    {"value": "HKStock",  "label": "HK Stocks"},
    {"value": "Crypto",   "label": "Crypto"},
    {"value": "Forex",    "label": "Forex"},
    {"value": "Futures",  "label": "Futures"},
    {"value": "MOEX",     "label": "MOEX"},
]


@agent_v1_bp.route("/markets", methods=["GET"])
@agent_required(SCOPE_R)
def list_markets():
    """List markets the calling token is allowed to query.

    Filtering is the intersection of three rules:
      1. The token's ``markets`` allowlist (set per credential).
      2. Per-deployment visibility (``ENABLED_MARKETS`` / legacy ``SHOW_*``),
         resolved by :func:`app.utils.market_visibility.is_market_visible` so
         the Agent API stays in lock-step with the watchlist picker.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    responses:
      200:
        description: List of allowed markets
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      500:
        $ref: '#/components/responses/ServerError'
    """
    visible = [
        m for m in _MARKETS
        if market_allowed(m["value"]) and is_market_visible(m["value"])
    ]
    return envelope(visible)


@agent_v1_bp.route("/markets/<market>/symbols", methods=["GET"])
@agent_required(SCOPE_R)
def market_symbols(market: str):
    """Search symbols within a market.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: market
        in: path
        required: true
        schema:
          type: string
        description: Market identifier (e.g. USStock, Crypto, Forex)
      - name: keyword
        in: query
        required: false
        schema:
          type: string
        description: Substring or code to match (case-insensitive). If empty, returns hot symbols.
      - name: limit
        in: query
        required: false
        schema:
          type: integer
          minimum: 1
          maximum: 100
          default: 20
        description: Maximum number of symbols to return
    responses:
      200:
        description: List of matching symbols
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      401:
        description: Agent token required
      403:
        description: Market not allowed for this token
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      500:
        $ref: '#/components/responses/ServerError'
    """
    if not market_allowed(market):
        return error(403, f"Market not allowed for this token: {market}", http=403)

    keyword = (request.args.get("keyword") or "").strip().upper()
    limit = clip_int(request.args.get("limit"), default=20, lo=1, hi=100)

    if not keyword:
        out = seed_get_hot_symbols(market=market, limit=limit) or []
    else:
        out = seed_search_symbols(market=market, keyword=keyword, limit=limit) or []
    return envelope(out)


@agent_v1_bp.route("/klines", methods=["GET"])
@agent_required(SCOPE_R)
def klines():
    """OHLCV bars.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: market
        in: query
        required: true
        schema:
          type: string
        description: Market identifier (e.g. USStock, Crypto)
      - name: symbol
        in: query
        required: true
        schema:
          type: string
        description: Symbol to query (e.g. AAPL, BTC/USDT)
      - name: timeframe
        in: query
        required: false
        schema:
          type: string
          default: "1D"
        description: Bar timeframe (e.g. 1m, 5m, 1H, 1D)
      - name: limit
        in: query
        required: false
        schema:
          type: integer
          minimum: 1
          maximum: 2000
          default: 300
        description: Maximum number of bars to return
      - name: before_time
        in: query
        required: false
        schema:
          type: integer
        description: Unix timestamp in seconds for backwards pagination
    responses:
      200:
        description: OHLCV bar data
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      400:
        description: Missing required parameters or invalid before_time
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      401:
        description: Agent token required
      403:
        description: Market or instrument not allowed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      502:
        description: Kline fetch failed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
    """
    market = (request.args.get("market") or "").strip()
    symbol = (request.args.get("symbol") or "").strip()
    timeframe = (request.args.get("timeframe") or "1D").strip()
    limit = clip_int(request.args.get("limit"), default=300, lo=1, hi=2000)
    before_raw = request.args.get("before_time") or request.args.get("beforeTime")

    if not market or not symbol:
        return error(400, "market and symbol are required")
    if not market_allowed(market):
        return error(403, f"Market not allowed: {market}", http=403)
    if not instrument_allowed(symbol):
        return error(403, f"Instrument not allowed: {symbol}", http=403)

    before_time = None
    if before_raw:
        try:
            before_time = int(before_raw)
        except Exception:
            return error(400, "before_time must be unix seconds")

    try:
        rows = _kline_service.get_kline(
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            before_time=before_time,
        ) or []
    except Exception as exc:
        logger.error(f"agent_v1/klines failed: {exc}", exc_info=True)
        return error(500, "kline fetch failed", details=str(exc), retriable=True, http=502)

    return envelope({
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(rows),
        "klines": rows,
    })


@agent_v1_bp.route("/price", methods=["GET"])
@agent_required(SCOPE_R)
def price():
    """Latest price for a symbol.

    Requires agent token with R scope.

    ---
    tags:
      - Agent V1
    parameters:
      - name: market
        in: query
        required: true
        schema:
          type: string
        description: Market identifier (e.g. USStock, Crypto)
      - name: symbol
        in: query
        required: true
        schema:
          type: string
        description: Symbol to query (e.g. AAPL, BTC/USDT)
    responses:
      200:
        description: Latest price data
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentResponseEnvelope'
      400:
        description: Missing required parameters
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      401:
        description: Agent token required
      403:
        description: Market or instrument not allowed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
      502:
        description: Price fetch failed
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AgentErrorResponse'
    """
    market = (request.args.get("market") or "").strip()
    symbol = (request.args.get("symbol") or "").strip()
    if not market or not symbol:
        return error(400, "market and symbol are required")
    if not market_allowed(market):
        return error(403, f"Market not allowed: {market}", http=403)
    if not instrument_allowed(symbol):
        return error(403, f"Instrument not allowed: {symbol}", http=403)
    try:
        rows = _kline_service.get_kline(market=market, symbol=symbol, timeframe="1m", limit=1) or []
        if not rows:
            return envelope({"market": market, "symbol": symbol, "price": None})
        last = rows[-1]
        # KlineService rows are typically dicts with 'close'/'c' keys.
        close = (
            last.get("close") if isinstance(last, dict) else None
        ) or (last.get("c") if isinstance(last, dict) else None)
        return envelope({
            "market": market,
            "symbol": symbol,
            "price": close,
            "raw": last,
        })
    except Exception as exc:
        logger.error(f"agent_v1/price failed: {exc}", exc_info=True)
        return error(500, "price fetch failed", details=str(exc), retriable=True, http=502)
