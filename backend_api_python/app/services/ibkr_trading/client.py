"""
Interactive Brokers Trading Client

Uses ib_insync library to connect to TWS or IB Gateway for trading.
All ib_insync operations run in a dedicated event-loop thread so that
Flask/WebAPI threads never interfere with IB callbacks.
"""

import threading
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from app.utils.logger import get_logger
from app.services.ibkr_trading.symbols import normalize_symbol, format_display_symbol

logger = get_logger(__name__)

# Lazy import – allows the rest of the app to work without ib_insync installed
ib_insync = None


def _ensure_ib_insync():
    """Ensure ib_insync is imported."""
    global ib_insync
    if ib_insync is None:
        try:
            import ib_insync as _ib
            ib_insync = _ib
        except ImportError:
            raise ImportError(
                "ib_insync is not installed. Run: pip install ib_insync"
            )
    return ib_insync


def _clean_price(value) -> Optional[float]:
    """Return None for unset IB price sentinels (0 or inf)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f in (0.0, float("inf"), float("-inf")) else f


# ---------------------------------------------------------------------------
# Config / Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class IBKRConfig:
    """IBKR connection configuration."""
    host: str = "127.0.0.1"
    port: int = 7497   # TWS Live:7497 | TWS Paper:7496 | GW Live:4001 | GW Paper:4002
    client_id: int = 1
    readonly: bool = False
    account: str = ""  # Leave empty to auto-select first account
    timeout: float = 20.0


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    order_id: int = 0
    perm_id: int = 0
    filled: float = 0.0
    avg_price: float = 0.0
    status: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class IBKRClient:
    """
    Interactive Brokers Trading Client.

    All ib_insync calls are dispatched to a private background thread that
    owns a persistent asyncio event loop.  Public methods are synchronous
    and safe to call from any thread (Flask routes, celery workers, etc.).

    Usage:
        config = IBKRConfig(port=7497)
        client = IBKRClient(config)

        if client.connect():
            result = client.place_market_order("AAPL", "buy", 10)
            positions = client.get_positions()
            client.disconnect()
    """

    def __init__(self, config: Optional[IBKRConfig] = None):
        self.config = config or IBKRConfig()
        self._ib = None
        self._connected = False
        self._lock = threading.Lock()
        self._account = ""

        # Dedicated event-loop thread – ib_insync lives here exclusively
        self._loop = asyncio.new_event_loop()
        self._ib_thread = threading.Thread(
            target=self._start_loop,
            name="ib-insync-loop",
            daemon=True,
        )
        self._ib_thread.start()

    # ------------------------------------------------------------------
    # Event-loop helpers
    # ------------------------------------------------------------------

    def _start_loop(self):
        """Bind the loop to this thread then run it forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_coro(self, coro, timeout: float = 15):
        """
        Submit *coro* to the ib_insync thread and block until done.
        Safe to call from any external thread.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        if self._ib is None:
            return False
        return self._ib.isConnected()

    def connect(self) -> bool:
        """Connect to TWS or IB Gateway. Idempotent."""
        with self._lock:
            if self.connected:
                return True

            async def _connect():
                _ensure_ib_insync()

                if self._ib is None:
                    self._ib = ib_insync.IB()

                logger.info(
                    f"Connecting to IBKR {self.config.host}:{self.config.port} "
                    f"clientId={self.config.client_id}"
                )

                await self._ib.connectAsync(
                    host=self.config.host,
                    port=self.config.port,
                    clientId=self.config.client_id,
                    readonly=self.config.readonly,
                    timeout=self.config.timeout,
                )

                self._ib.setTimeout(timeout=self.config.timeout)

                accounts = self._ib.managedAccounts()
                if accounts:
                    self._account = self.config.account or accounts[0]
                    logger.info(f"IBKR connected – account: {self._account}")
                else:
                    logger.warning("IBKR connected but no account retrieved")

                # Pre-warm caches so the first API call is not slow
                try:
                    self._ib.accountSummary(self._account)
                except Exception as exc:
                    logger.warning(f"Pre-fetch accountSummary failed: {exc}")

                # Subscribe to position updates (populates positions cache)
                try:
                    self._ib.reqPositions()
                    await asyncio.sleep(0.5)
                except Exception as exc:
                    logger.warning(f"reqPositions failed: {exc}")

            try:
                self._run_coro(_connect(), timeout=self.config.timeout + 5)
                self._connected = True
                return True
            except Exception as exc:
                logger.error(f"IBKR connection failed: {exc}")
                self._connected = False
                return False

    def disconnect(self):
        """Disconnect gracefully."""
        with self._lock:
            if self._ib is not None:
                try:
                    # IB.disconnect() is sync – run it inside the loop thread
                    # so pending callbacks can flush before the socket closes.
                    async def _disconnect():
                        self._ib.disconnect()

                    self._run_coro(_disconnect(), timeout=5)
                except Exception as exc:
                    logger.warning(f"Disconnect exception: {exc}")
                finally:
                    self._connected = False
                    logger.info("IBKR disconnected")

    def _ensure_connected(self):
        if not self.connected:
            if not self.connect():
                raise ConnectionError("Cannot connect to IBKR")

    # ------------------------------------------------------------------
    # Contract helpers
    # ------------------------------------------------------------------

    def _create_contract(self, symbol: str, market_type: str):
        _ensure_ib_insync()
        ib_symbol, exchange, currency = normalize_symbol(symbol, market_type)
        return ib_insync.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)

    def _qualify_contract(self, contract):
        """
        Qualify *contract* and return the qualified list (may be empty).
        Runs inside the ib_insync loop to avoid deadlock.
        """
        async def _qualify():
            return await self._ib.qualifyContractsAsync(contract)

        try:
            return self._run_coro(_qualify())
        except Exception as exc:
            logger.warning(f"Contract qualification failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        market_type: str = "USStock",
    ) -> OrderResult:
        """Place a market order."""

        async def _place():
            contract = self._create_contract(symbol, market_type)
            qualified = await self._ib.qualifyContractsAsync(contract)
            if not qualified:
                return None, f"Invalid contract: {symbol}"

            order = ib_insync.MarketOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=quantity,
                account=self._account,
            )
            trade = self._ib.placeOrder(qualified[0], order)
            await asyncio.sleep(2)   # wait for initial status callback
            return trade, None

        try:
            self._ensure_connected()
            _ensure_ib_insync()

            trade, err = self._run_coro(_place())
            if err:
                return OrderResult(success=False, message=err)

            status = trade.orderStatus.status
            rejected = status in ("Cancelled", "ApiCancelled", "Inactive")
            return OrderResult(
                success=not rejected,
                order_id=trade.order.orderId,
                perm_id=trade.order.permId,
                filled=float(trade.orderStatus.filled or 0),
                avg_price=float(trade.orderStatus.avgFillPrice or 0),
                status=status,
                message="Order submitted" if not rejected else f"Order {status}",
                raw={
                    "orderId": trade.order.orderId,
                    "permId": trade.order.permId,
                    "status": status,
                    "filled": float(trade.orderStatus.filled or 0),
                    "remaining": float(trade.orderStatus.remaining or 0),
                },
            )

        except Exception as exc:
            logger.error(f"Market order failed: {exc}")
            return OrderResult(success=False, message=str(exc))

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        market_type: str = "USStock",
    ) -> OrderResult:
        """Place a limit order."""

        async def _place():
            contract = self._create_contract(symbol, market_type)
            qualified = await self._ib.qualifyContractsAsync(contract)
            if not qualified:
                return None, f"Invalid contract: {symbol}"

            order = ib_insync.LimitOrder(
                action="BUY" if side.lower() == "buy" else "SELL",
                totalQuantity=quantity,
                lmtPrice=price,
                account=self._account,
            )
            trade = self._ib.placeOrder(qualified[0], order)
            await asyncio.sleep(2)
            return trade, None

        try:
            self._ensure_connected()
            _ensure_ib_insync()

            trade, err = self._run_coro(_place())
            if err:
                return OrderResult(success=False, message=err)

            status = trade.orderStatus.status
            rejected = status in ("Cancelled", "ApiCancelled", "Inactive")
            return OrderResult(
                success=not rejected,
                order_id=trade.order.orderId,
                perm_id=trade.order.permId,
                filled=float(trade.orderStatus.filled or 0),
                avg_price=float(trade.orderStatus.avgFillPrice or 0),
                status=status,
                message="Limit order submitted" if not rejected else f"Limit order {status}",
                raw={
                    "orderId": trade.order.orderId,
                    "permId": trade.order.permId,
                    "status": status,
                    "limitPrice": price,
                    "filled": float(trade.orderStatus.filled or 0),
                    "remaining": float(trade.orderStatus.remaining or 0),
                },
            )

        except Exception as exc:
            logger.error(f"Limit order failed: {exc}")
            return OrderResult(success=False, message=str(exc))

    def cancel_order(self, perm_id: int) -> bool:
        """
        Cancel an open order by its permId.

        Args:
            perm_id: The permanent order ID returned by place_* methods.
        """

        async def _cancel():
            # Refresh open orders from TWS first
            self._ib.reqAllOpenOrders()
            await asyncio.sleep(1)

            for trade in self._ib.openTrades():
                if trade.order.permId == perm_id:
                    self._ib.cancelOrder(trade.order)
                    await asyncio.sleep(0.5)   # allow cancellation callback
                    logger.info(f"Cancel sent for permId={perm_id}")
                    return True

            logger.warning(f"Open order not found for permId={perm_id}")
            return False

        try:
            self._ensure_connected()
            return self._run_coro(_cancel())
        except Exception as exc:
            logger.error(f"Cancel order failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Return all currently open orders."""

        async def _fetch():
            self._ib.reqAllOpenOrders()
            await asyncio.sleep(1)
            return self._ib.openTrades()

        try:
            self._ensure_connected()
            trades = self._run_coro(_fetch())
            result = []

            for trade in trades:
                order   = trade.order
                contract = trade.contract
                status  = trade.orderStatus

                result.append({
                    "orderId": order.permId,
                    "symbol": contract.symbol,
                    "action": order.action,
                    "quantity": float(order.totalQuantity),
                    "orderType": order.orderType,
                    "limitPrice": getattr(order, 'lmtPrice', None),
                    "status": status.status,
                    "filled": float(status.filled or 0),
                    "remaining": float(status.remaining or 0),
                    "avgFillPrice": float(status.avgFillPrice or 0),
                })

            result.sort(key=lambda x: x["orderId"], reverse=True)
            return result

        except Exception as exc:
            logger.error(f"Get open orders failed: {exc}")
            return []

    def get_account_summary(self) -> Dict[str, Any]:
        """Return account summary from cache (pre-fetched on connect)."""
        try:
            self._ensure_connected()
            summary = self._ib.accountSummary(self._account)
            result = {}
            for item in summary:
                result[item.tag] = {"value": item.value, "currency": item.currency}
            return {"account": self._account, "summary": result}
        except Exception as exc:
            logger.error(f"Get account summary failed: {exc}")
            raise

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return positions from cache (subscribed on connect)."""
        try:
            self._ensure_connected()
            positions = self._ib.positions(self._account)
            result = []
            for pos in positions:
                contract = pos.contract
                exchange = contract.exchange or contract.primaryExchange or "SMART"
                result.append({
                    "symbol":      format_display_symbol(contract.symbol, exchange),
                    "ib_symbol":   contract.symbol,
                    "secType":     contract.secType,
                    "exchange":    exchange,
                    "currency":    contract.currency,
                    "quantity":    float(pos.position),
                    "avgCost":     float(pos.avgCost),
                    "marketValue": float(pos.position) * float(pos.avgCost),
                })
            return result
        except Exception as exc:
            logger.error(f"Get positions failed: {exc}")
            return []

    def get_quote(self, symbol: str, market_type: str = "USStock") -> Dict[str, Any]:
        """Fetch a real-time snapshot quote."""

        async def _fetch():
            contract = self._create_contract(symbol, market_type)
            qualified = await self._ib.qualifyContractsAsync(contract)
            if not qualified:
                return {"success": False, "error": f"Invalid contract: {symbol}"}

            ticker = self._ib.reqMktData(qualified[0], "", False, False)
            await asyncio.sleep(2)

            result = {
                "success":  True,
                "symbol":   symbol,
                "bid":      _clean_price(ticker.bid),
                "ask":      _clean_price(ticker.ask),
                "last":     _clean_price(ticker.last),
                "high":     _clean_price(ticker.high),
                "low":      _clean_price(ticker.low),
                "close":    _clean_price(ticker.close),
                "volume":   ticker.volume if ticker.volume and ticker.volume > 0 else None,
            }

            self._ib.cancelMktData(qualified[0])
            return result

        try:
            self._ensure_connected()
            return self._run_coro(_fetch())
        except Exception as exc:
            logger.error(f"Get quote failed: {exc}")
            return {"success": False, "error": str(exc)}

    def get_connection_status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "host":      self.config.host,
            "port":      self.config.port,
            "clientId":  self.config.client_id,
            "account":   self._account,
            "readonly":  self.config.readonly,
        }


# ---------------------------------------------------------------------------
# Global singleton helpers
# ---------------------------------------------------------------------------

_global_client: Optional[IBKRClient] = None
_global_lock = threading.Lock()


def get_ibkr_client(config: Optional[IBKRConfig] = None) -> IBKRClient:
    """Return (and lazily create) the global IBKRClient singleton."""
    global _global_client
    with _global_lock:
        if _global_client is None:
            _global_client = IBKRClient(config)
        return _global_client


def reset_ibkr_client():
    """Disconnect and clear the global singleton."""
    global _global_client
    with _global_lock:
        if _global_client is not None:
            _global_client.disconnect()
            _global_client = None