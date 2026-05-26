"""
Unit tests for IBKRClient.

All ib_insync calls are mocked so no TWS/Gateway is required.
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.ibkr_trading.client import (
    IBKRClient,
    IBKRConfig,
    OrderResult,
    get_ibkr_client,
    reset_ibkr_client,
    _ensure_event_loop,
    _ensure_ib_insync,
)


# ---------------------------------------------------------------------------
# Helpers: build mock ib_insync objects
# ---------------------------------------------------------------------------

def _make_mock_trade(order_id=1, status="Submitted", filled=0.0,
                     remaining=100.0, avg_fill_price=0.0):
    trade = MagicMock()
    trade.order.orderId = order_id
    trade.orderStatus.status = status
    trade.orderStatus.filled = filled
    trade.orderStatus.remaining = remaining
    trade.orderStatus.avgFillPrice = avg_fill_price
    return trade


def _make_mock_position(symbol="AAPL", exchange="SMART", currency="USD",
                        secType="STK", position=10.0, avg_cost=150.0):
    pos = MagicMock()
    pos.contract.symbol = symbol
    pos.contract.exchange = exchange
    pos.contract.primaryExchange = "NASDAQ"
    pos.contract.currency = currency
    pos.contract.secType = secType
    pos.position = position
    pos.avgCost = avg_cost
    return pos


def _make_mock_account_value(tag="NetLiquidation", value="100000",
                             currency="USD"):
    av = MagicMock()
    av.tag = tag
    av.value = value
    av.currency = currency
    return av


def _make_mock_ticker(bid=149.5, ask=150.5, last=150.0, high=151.0,
                      low=148.0, volume=1000000, close=149.0):
    ticker = MagicMock()
    ticker.bid = bid
    ticker.ask = ask
    ticker.last = last
    ticker.high = high
    ticker.low = low
    ticker.volume = volume
    ticker.close = close
    return ticker


def _make_mock_order(order_id=1, action="BUY", total_quantity=10.0,
                     order_type="MKT", lmt_price=0.0):
    order = MagicMock()
    order.orderId = order_id
    order.action = action
    order.totalQuantity = total_quantity
    order.orderType = order_type
    order.lmtPrice = lmt_price
    return order


def _make_mock_open_trade(order_id=1, symbol="AAPL", action="BUY",
                          quantity=10.0, order_type="MKT", lmt_price=0.0,
                          status="Submitted", filled=0.0, remaining=10.0,
                          avg_fill_price=0.0):
    trade = MagicMock()
    trade.order = _make_mock_order(order_id, action, quantity, order_type,
                                   lmt_price)
    trade.contract.symbol = symbol
    trade.orderStatus.status = status
    trade.orderStatus.filled = filled
    trade.orderStatus.remaining = remaining
    trade.orderStatus.avgFillPrice = avg_fill_price
    return trade


def _connected_client(config=None):
    """Return an IBKRClient with a mocked connected IB instance."""
    client = IBKRClient(config or IBKRConfig())
    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.managedAccounts.return_value = ["DU123456"]
    ib.sleep.return_value = True
    client._ib = ib
    client._connected = True
    client._account = "DU123456"
    return client


# ---------------------------------------------------------------------------
# IBKRConfig
# ---------------------------------------------------------------------------

class TestIBKRConfig:
    def test_defaults(self):
        cfg = IBKRConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 7497
        assert cfg.client_id == 1
        assert cfg.readonly is False
        assert cfg.account == ""
        assert cfg.timeout == 20.0

    def test_custom_values(self):
        cfg = IBKRConfig(host="10.0.0.1", port=4001, client_id=7,
                         readonly=True, account="U999", timeout=30)
        assert cfg.host == "10.0.0.1"
        assert cfg.port == 4001
        assert cfg.client_id == 7
        assert cfg.readonly is True
        assert cfg.account == "U999"
        assert cfg.timeout == 30


# ---------------------------------------------------------------------------
# OrderResult
# ---------------------------------------------------------------------------

class TestOrderResult:
    def test_defaults(self):
        r = OrderResult(success=True)
        assert r.success is True
        assert r.order_id == 0
        assert r.filled == 0.0
        assert r.avg_price == 0.0
        assert r.status == ""
        assert r.message == ""
        assert r.raw == {}

    def test_custom_values(self):
        r = OrderResult(success=False, order_id=42, filled=5.0,
                        avg_price=150.0, status="Filled", message="done",
                        raw={"key": "val"})
        assert r.order_id == 42
        assert r.raw == {"key": "val"}


# ---------------------------------------------------------------------------
# _ensure_event_loop
# ---------------------------------------------------------------------------

class TestEnsureEventLoop:
    def test_creates_loop_when_none_exists(self):
        """Should create a new event loop without raising."""
        loop = _ensure_event_loop()
        assert loop is not None
        assert isinstance(loop, asyncio.AbstractEventLoop)


# ---------------------------------------------------------------------------
# IBKRClient – connection
# ---------------------------------------------------------------------------

class TestIBKRClientConnection:
    def test_connected_property_returns_false_when_no_ib(self):
        client = IBKRClient()
        assert client.connected is False

    def test_connected_property_delegates_to_ib(self):
        client = IBKRClient()
        ib = MagicMock()
        ib.isConnected.return_value = True
        client._ib = ib
        assert client.connected is True

    @patch("app.services.ibkr_trading.client._ensure_event_loop")
    @patch("app.services.ibkr_trading.client._ensure_ib_insync")
    def test_connect_success(self, mock_ensure_ib, mock_loop):
        import app.services.ibkr_trading.client as mod
        mock_ib = MagicMock()
        ib_instance = MagicMock()
        ib_instance.isConnected.return_value = True
        ib_instance.managedAccounts.return_value = ["DU111111"]
        mock_ib.IB.return_value = ib_instance
        old = mod.ib_insync
        mod.ib_insync = mock_ib
        try:
            client = IBKRClient(IBKRConfig(port=7496))
            result = client.connect()

            assert result is True
            assert client._account == "DU111111"
            ib_instance.connect.assert_called_once_with(
                host="127.0.0.1", port=7496, clientId=1,
                readonly=False, timeout=20.0,
            )
        finally:
            mod.ib_insync = old

    @patch("app.services.ibkr_trading.client._ensure_event_loop")
    @patch("app.services.ibkr_trading.client._ensure_ib_insync")
    def test_connect_uses_configured_account(self, mock_ensure_ib, mock_loop):
        import app.services.ibkr_trading.client as mod
        mock_ib = MagicMock()
        ib_instance = MagicMock()
        ib_instance.isConnected.return_value = True
        ib_instance.managedAccounts.return_value = ["DU111111", "DU222222"]
        mock_ib.IB.return_value = ib_instance
        old = mod.ib_insync
        mod.ib_insync = mock_ib
        try:
            client = IBKRClient(IBKRConfig(account="DU222222"))
            client.connect()

            assert client._account == "DU222222"
        finally:
            mod.ib_insync = old

    @patch("app.services.ibkr_trading.client._ensure_event_loop")
    @patch("app.services.ibkr_trading.client._ensure_ib_insync")
    def test_connect_no_accounts(self, mock_ensure_ib, mock_loop):
        import app.services.ibkr_trading.client as mod
        mock_ib = MagicMock()
        ib_instance = MagicMock()
        ib_instance.isConnected.return_value = True
        ib_instance.managedAccounts.return_value = []
        mock_ib.IB.return_value = ib_instance
        old = mod.ib_insync
        mod.ib_insync = mock_ib
        try:
            client = IBKRClient()
            result = client.connect()

            assert result is True
            assert client._account == ""
        finally:
            mod.ib_insync = old

    @patch("app.services.ibkr_trading.client._ensure_event_loop")
    @patch("app.services.ibkr_trading.client._ensure_ib_insync")
    def test_connect_failure_returns_false(self, mock_ensure_ib, mock_loop):
        import app.services.ibkr_trading.client as mod
        mock_ib = MagicMock()
        ib_instance = MagicMock()
        ib_instance.isConnected.return_value = False
        ib_instance.connect.side_effect = ConnectionError("refused")
        mock_ib.IB.return_value = ib_instance
        old = mod.ib_insync
        mod.ib_insync = mock_ib
        try:
            client = IBKRClient()
            result = client.connect()

            assert result is False
            assert client._connected is False
        finally:
            mod.ib_insync = old

    @patch("app.services.ibkr_trading.client._ensure_event_loop")
    @patch("app.services.ibkr_trading.client._ensure_ib_insync")
    def test_connect_already_connected(self, mock_ensure_ib, mock_loop):
        import app.services.ibkr_trading.client as mod
        mock_ib = MagicMock()
        ib_instance = MagicMock()
        ib_instance.isConnected.return_value = True
        mock_ib.IB.return_value = ib_instance
        old = mod.ib_insync
        mod.ib_insync = mock_ib
        try:
            client = IBKRClient()
            client._ib = ib_instance
            result = client.connect()

            assert result is True
            ib_instance.connect.assert_not_called()
        finally:
            mod.ib_insync = old

    def test_disconnect(self):
        client = _connected_client()
        client.disconnect()
        client._ib.disconnect.assert_called_once()
        assert client._connected is False

    def test_disconnect_when_no_ib(self):
        client = IBKRClient()
        # should not raise
        client.disconnect()

    def test_disconnect_exception_is_swallowed(self):
        client = _connected_client()
        client._ib.disconnect.side_effect = RuntimeError("boom")
        client.disconnect()  # should not raise
        assert client._connected is False


# ---------------------------------------------------------------------------
# IBKRClient – place_market_order
# ---------------------------------------------------------------------------

class TestPlaceMarketOrder:
    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_buy_market_order_success(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.MarketOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=10, status="Submitted")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("AAPL", "buy", 10)

        assert result.success is True
        assert result.order_id == 10
        assert result.status == "Submitted"
        mock_ib.MarketOrder.assert_called_once_with(
            action="BUY", totalQuantity=10, account="DU123456"
        )

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_sell_market_order(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.MarketOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=11, status="Submitted")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("TSLA", "sell", 5)

        assert result.success is True
        mock_ib.MarketOrder.assert_called_once_with(
            action="SELL", totalQuantity=5, account="DU123456"
        )

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_market_order_invalid_contract(self, mock_ib):
        client = _connected_client()
        mock_ib.Stock.return_value = MagicMock()
        client._ib.qualifyContracts.return_value = []

        result = client.place_market_order("INVALID", "buy", 10)

        assert result.success is False
        assert "Invalid contract" in result.message

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_market_order_cancelled(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.MarketOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=20, status="Cancelled")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("AAPL", "buy", 10)

        assert result.success is False
        assert "Cancelled" in result.status

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_market_order_api_cancelled(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.MarketOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=21, status="ApiCancelled")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("AAPL", "buy", 10)
        assert result.success is False

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_market_order_inactive(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.MarketOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=22, status="Inactive")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("AAPL", "buy", 10)
        assert result.success is False

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_market_order_partial_fill(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.MarketOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=30, status="Submitted",
                                 filled=5.0, remaining=5.0)
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_market_order("AAPL", "buy", 10)

        assert result.success is True
        assert result.filled == 5.0

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_market_order_place_exception(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.side_effect = RuntimeError("network error")

        result = client.place_market_order("AAPL", "buy", 10)

        assert result.success is False
        assert "network error" in result.message


# ---------------------------------------------------------------------------
# IBKRClient – place_limit_order
# ---------------------------------------------------------------------------

class TestPlaceLimitOrder:
    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_buy_limit_order_success(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.LimitOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=40, status="Submitted")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_limit_order("AAPL", "buy", 10, 150.0)

        assert result.success is True
        assert result.order_id == 40
        mock_ib.LimitOrder.assert_called_once_with(
            action="BUY", totalQuantity=10, lmtPrice=150.0,
            account="DU123456"
        )

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_sell_limit_order(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.LimitOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=41, status="Submitted")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_limit_order("TSLA", "sell", 5, 200.0)

        assert result.success is True
        mock_ib.LimitOrder.assert_called_once_with(
            action="SELL", totalQuantity=5, lmtPrice=200.0,
            account="DU123456"
        )

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_limit_order_invalid_contract(self, mock_ib):
        client = _connected_client()
        mock_ib.Stock.return_value = MagicMock()
        client._ib.qualifyContracts.return_value = []

        result = client.place_limit_order("INVALID", "buy", 10, 150.0)

        assert result.success is False
        assert "Invalid contract" in result.message

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_limit_order_cancelled(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.LimitOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=42, status="Cancelled")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_limit_order("AAPL", "buy", 10, 150.0)

        assert result.success is False
        assert "Cancelled" in result.status

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_limit_order_raw_contains_price(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        mock_ib.LimitOrder.return_value = MagicMock()

        trade = _make_mock_trade(order_id=43, status="Submitted")
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.return_value = trade

        result = client.place_limit_order("AAPL", "buy", 10, 155.5)

        assert result.raw["limitPrice"] == 155.5

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_limit_order_place_exception(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.placeOrder.side_effect = RuntimeError("timeout")

        result = client.place_limit_order("AAPL", "buy", 10, 150.0)

        assert result.success is False
        assert "timeout" in result.message


# ---------------------------------------------------------------------------
# IBKRClient – cancel_order
# ---------------------------------------------------------------------------

class TestCancelOrder:
    def test_cancel_existing_order(self):
        client = _connected_client()
        trade = MagicMock()
        trade.order.orderId = 10
        client._ib.openTrades.return_value = [trade]

        result = client.cancel_order(10)

        assert result is True
        client._ib.cancelOrder.assert_called_once_with(trade.order)

    def test_cancel_nonexistent_order(self):
        client = _connected_client()
        trade = MagicMock()
        trade.order.orderId = 10
        client._ib.openTrades.return_value = [trade]

        result = client.cancel_order(999)

        assert result is False
        client._ib.cancelOrder.assert_not_called()

    def test_cancel_order_no_open_trades(self):
        client = _connected_client()
        client._ib.openTrades.return_value = []

        result = client.cancel_order(1)

        assert result is False

    def test_cancel_order_exception(self):
        client = _connected_client()
        client._ib.openTrades.side_effect = RuntimeError("disconnected")

        result = client.cancel_order(1)

        assert result is False


# ---------------------------------------------------------------------------
# IBKRClient – get_account_summary
# ---------------------------------------------------------------------------

class TestGetAccountSummary:
    def test_success(self):
        client = _connected_client()
        client._ib.accountSummary.return_value = [
            _make_mock_account_value("NetLiquidation", "100000", "USD"),
            _make_mock_account_value("TotalCashValue", "50000", "USD"),
        ]

        result = client.get_account_summary()

        assert result["account"] == "DU123456"
        assert "NetLiquidation" in result["summary"]
        assert result["summary"]["NetLiquidation"]["value"] == "100000"
        assert result["summary"]["TotalCashValue"]["currency"] == "USD"

    def test_empty_summary(self):
        client = _connected_client()
        client._ib.accountSummary.return_value = []

        result = client.get_account_summary()

        assert result["account"] == "DU123456"
        assert result["summary"] == {}

    def test_error_raises(self):
        client = _connected_client()
        client._ib.accountSummary.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            client.get_account_summary()


# ---------------------------------------------------------------------------
# IBKRClient – get_positions
# ---------------------------------------------------------------------------

class TestGetPositions:
    def test_with_positions(self):
        client = _connected_client()
        client._ib.positions.return_value = [
            _make_mock_position("AAPL", "SMART", "USD", "STK", 10, 150.0),
            _make_mock_position("TSLA", "SMART", "USD", "STK", 5, 200.0),
        ]

        result = client.get_positions()

        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["quantity"] == 10.0
        assert result[0]["avgCost"] == 150.0
        assert result[0]["marketValue"] == 1500.0
        assert result[1]["symbol"] == "TSLA"
        assert result[1]["quantity"] == 5.0

    def test_empty_positions(self):
        client = _connected_client()
        client._ib.positions.return_value = []

        result = client.get_positions()

        assert result == []

    def test_position_uses_primary_exchange_fallback(self):
        client = _connected_client()
        pos = _make_mock_position("AAPL", "", "USD")
        pos.contract.exchange = ""
        client._ib.positions.return_value = [pos]

        result = client.get_positions()

        assert result[0]["exchange"] == "NASDAQ"

    def test_position_uses_smart_fallback(self):
        client = _connected_client()
        pos = _make_mock_position("AAPL", "", "USD")
        pos.contract.exchange = ""
        pos.contract.primaryExchange = ""
        client._ib.positions.return_value = [pos]

        result = client.get_positions()

        assert result[0]["exchange"] == "SMART"

    def test_error_returns_empty_list(self):
        client = _connected_client()
        client._ib.positions.side_effect = RuntimeError("timeout")

        result = client.get_positions()

        assert result == []


# ---------------------------------------------------------------------------
# IBKRClient – get_open_orders
# ---------------------------------------------------------------------------

class TestGetOpenOrders:
    def test_with_orders(self):
        client = _connected_client()
        client._ib.openTrades.return_value = [
            _make_mock_open_trade(order_id=1, symbol="AAPL", action="BUY",
                                  quantity=10, order_type="MKT", status="Submitted"),
            _make_mock_open_trade(order_id=2, symbol="TSLA", action="SELL",
                                  quantity=5, order_type="LMT", lmt_price=200.0,
                                  status="Submitted", filled=2.0, remaining=3.0),
        ]

        result = client.get_open_orders()

        assert len(result) == 2
        assert result[0]["orderId"] == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["action"] == "BUY"
        assert result[0]["quantity"] == 10.0
        assert result[0]["orderType"] == "MKT"
        assert result[1]["orderId"] == 2
        assert result[1]["limitPrice"] == 200.0
        assert result[1]["filled"] == 2.0
        assert result[1]["remaining"] == 3.0

    def test_empty_orders(self):
        client = _connected_client()
        client._ib.openTrades.return_value = []

        result = client.get_open_orders()

        assert result == []

    def test_error_returns_empty_list(self):
        client = _connected_client()
        client._ib.openTrades.side_effect = RuntimeError("disconnected")

        result = client.get_open_orders()

        assert result == []


# ---------------------------------------------------------------------------
# IBKRClient – get_quote
# ---------------------------------------------------------------------------

class TestGetQuote:
    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_success(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.reqMktData.return_value = _make_mock_ticker()

        result = client.get_quote("AAPL")

        assert result["success"] is True
        assert result["symbol"] == "AAPL"
        assert result["bid"] == 149.5
        assert result["ask"] == 150.5
        assert result["last"] == 150.0
        assert result["high"] == 151.0
        assert result["low"] == 148.0
        assert result["volume"] == 1000000
        assert result["close"] == 149.0
        client._ib.cancelMktData.assert_called_once_with(contract)

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_invalid_contract(self, mock_ib):
        client = _connected_client()
        mock_ib.Stock.return_value = MagicMock()
        client._ib.qualifyContracts.return_value = []

        result = client.get_quote("INVALID")

        assert result["success"] is False
        assert "Invalid contract" in result["error"]

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_empty_ticker_fields_return_none(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        client._ib.qualifyContracts.return_value = [contract]

        empty_ticker = MagicMock()
        empty_ticker.bid = 0
        empty_ticker.ask = 0
        empty_ticker.last = 0
        empty_ticker.high = 0
        empty_ticker.low = 0
        empty_ticker.volume = 0
        empty_ticker.close = 0
        client._ib.reqMktData.return_value = empty_ticker

        result = client.get_quote("AAPL")

        assert result["success"] is True
        assert result["bid"] is None
        assert result["ask"] is None
        assert result["last"] is None

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_none_ticker_fields_return_none(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        client._ib.qualifyContracts.return_value = [contract]

        none_ticker = MagicMock()
        none_ticker.bid = None
        none_ticker.ask = None
        none_ticker.last = None
        none_ticker.high = None
        none_ticker.low = None
        none_ticker.volume = None
        none_ticker.close = None
        client._ib.reqMktData.return_value = none_ticker

        result = client.get_quote("AAPL")

        assert result["success"] is True
        assert result["bid"] is None

    @patch("app.services.ibkr_trading.client.ib_insync")
    def test_exception_returns_error(self, mock_ib):
        client = _connected_client()
        contract = MagicMock()
        mock_ib.Stock.return_value = contract
        client._ib.qualifyContracts.return_value = [contract]
        client._ib.reqMktData.side_effect = RuntimeError("network")

        result = client.get_quote("AAPL")

        assert result["success"] is False
        assert "network" in result["error"]


# ---------------------------------------------------------------------------
# IBKRClient – get_connection_status
# ---------------------------------------------------------------------------

class TestGetConnectionStatus:
    def test_disconnected_client(self):
        client = IBKRClient(IBKRConfig(port=4001, client_id=7))
        status = client.get_connection_status()

        assert status["connected"] is False
        assert status["host"] == "127.0.0.1"
        assert status["port"] == 4001
        assert status["clientId"] == 7
        assert status["account"] == ""
        assert status["readonly"] is False

    def test_connected_client(self):
        client = _connected_client(IBKRConfig(port=7497, readonly=True))
        status = client.get_connection_status()

        assert status["connected"] is True
        assert status["account"] == "DU123456"
        assert status["readonly"] is True


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

class TestSingleton:
    def setup_method(self):
        reset_ibkr_client()

    def teardown_method(self):
        reset_ibkr_client()

    def test_get_creates_instance(self):
        client = get_ibkr_client()
        assert isinstance(client, IBKRClient)

    def test_get_returns_same_instance(self):
        c1 = get_ibkr_client()
        c2 = get_ibkr_client()
        assert c1 is c2

    def test_reset_clears_instance(self):
        c1 = get_ibkr_client()
        reset_ibkr_client()
        c2 = get_ibkr_client()
        assert c1 is not c2

    def test_reset_disconnects(self):
        client = get_ibkr_client()
        client._ib = MagicMock()
        client._ib.isConnected.return_value = True
        client._connected = True
        reset_ibkr_client()
        client._ib.disconnect.assert_called_once()

    def test_config_only_effective_on_first_call(self):
        c1 = get_ibkr_client(IBKRConfig(port=7496))
        c2 = get_ibkr_client(IBKRConfig(port=4001))
        assert c1 is c2
        assert c1.config.port == 7496


# ---------------------------------------------------------------------------
# _ensure_connected
# ---------------------------------------------------------------------------

class TestEnsureConnected:
    @patch("app.services.ibkr_trading.client._ensure_event_loop")
    @patch("app.services.ibkr_trading.client._ensure_ib_insync")
    def test_raises_when_not_connected(self, mock_ensure_ib, mock_loop):
        import app.services.ibkr_trading.client as mod
        mock_ib = MagicMock()
        ib_instance = MagicMock()
        ib_instance.isConnected.return_value = False
        ib_instance.connect.side_effect = ConnectionError("refused")
        mock_ib.IB.return_value = ib_instance
        old = mod.ib_insync
        mod.ib_insync = mock_ib
        try:
            client = IBKRClient()
            with pytest.raises(ConnectionError, match="Cannot connect to IBKR"):
                client._ensure_connected()
        finally:
            mod.ib_insync = old

    def test_passes_when_connected(self):
        client = _connected_client()
        # should not raise
        client._ensure_connected()
