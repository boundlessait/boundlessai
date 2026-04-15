"""Tests for MarketOracle analytics functions."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
from skills.genesis.scripts.market_oracle import MarketOracle


class TestMarketOracle:
    def setup_method(self):
        self.oracle = MarketOracle()

    def test_calculate_log_returns(self):
        prices = [100, 105, 103, 108]
        returns = self.oracle._calculate_log_returns(prices)
        assert len(returns) == 3
        assert returns[0] > 0  # 100 -> 105 is positive

    def test_calculate_log_returns_empty(self):
        returns = self.oracle._calculate_log_returns([])
        assert len(returns) == 0

    def test_calculate_log_returns_single(self):
        returns = self.oracle._calculate_log_returns([100])
        assert len(returns) == 0

    def test_update_and_windowed_prices(self):
        self.oracle.update_price_history("ETH", "USDC", 2500.0)
        self.oracle.update_price_history("ETH", "USDC", 2510.0)
        self.oracle.update_price_history("ETH", "USDC", 2505.0)
        prices = self.oracle._windowed_prices("ETH", "USDC", 1.0)
        assert len(prices) == 3

    def test_windowed_prices_empty(self):
        prices = self.oracle._windowed_prices("BTC", "USDT", 1.0)
        assert len(prices) == 0

    def test_calculate_volatility_insufficient_data(self):
        vol = self.oracle.calculate_volatility("ETH", "USDC")
        assert vol is None

    def test_calculate_volatility_with_data(self):
        for i in range(20):
            self.oracle.update_price_history("ETH", "USDC", 2500 + i * 10)
        vol = self.oracle.calculate_volatility("ETH", "USDC", window_hours=1)
        assert vol is not None
        assert vol > 0

    def test_detect_trend_insufficient_data(self):
        trend = self.oracle.detect_trend("ETH", "USDC")
        assert trend == "sideways"

    def test_detect_trend_with_uptrend(self):
        for i in range(20):
            self.oracle.update_price_history("ETH", "USDC", 2000 + i * 50)
        trend = self.oracle.detect_trend("ETH", "USDC", window_hours=1)
        assert trend in ("trending_up", "sideways")

    def test_get_market_regime(self):
        for i in range(20):
            self.oracle.update_price_history("ETH", "USDC", 2500 + i * 5)
        regime = self.oracle.get_market_regime("ETH", "USDC")
        assert "regime_name" in regime
        assert "preset_name" in regime
        assert "confidence" in regime
        assert "volatility" in regime
        assert "trend" in regime

    def test_price_cache(self):
        self.oracle._price_cache[("TEST", "USD")] = (time.time(), 42.0)
        price = self.oracle.fetch_price("TEST", "USD")
        assert price == 42.0
