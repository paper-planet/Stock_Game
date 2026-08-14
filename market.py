import asyncio
import random

from assets import Stock, Commodity
from market_clock import MarketClock
from news import (
    generate_news,
    generate_major_event
)
from traders import create_traders


class Market:

    def __init__(self):

        self.clock = MarketClock()

        self.day = 1

        self.stocks = self.create_stocks()

        self.commodities = (
            self.create_commodities()
        )

        self.traders = create_traders()

        self.latest_news = None

        self.news_history = []

        self.running = True

        self.last_trader_orders = 0

    def create_stocks(self):

        return [

            Stock(
                "AAPL",
                "Apple",
                180,
                0.0015
            ),

            Stock(
                "NVDA",
                "NVIDIA",
                175,
                0.003
            ),

            Stock(
                "TSLA",
                "Tesla",
                340,
                0.004
            ),

            Stock(
                "AMZN",
                "Amazon",
                230,
                0.002
            ),

            Stock(
                "MSFT",
                "Microsoft",
                520,
                0.0015
            ),

            Stock(
                "GOOG",
                "Alphabet",
                190,
                0.0018
            ),

            Stock(
                "META",
                "Meta",
                780,
                0.0025
            ),

            Stock(
                "JPM",
                "JPMorgan",
                300,
                0.0015
            ),

            Stock(
                "AMD",
                "AMD",
                160,
                0.0035
            ),

            Stock(
                "XOM",
                "Exxon Mobil",
                120,
                0.002
            )
        ]

    def create_commodities(self):

        return [

            Commodity(
                "OIL",
                "Crude Oil",
                78,
                0.003
            ),

            Commodity(
                "GOLD",
                "Gold",
                2350,
                0.0015
            ),

            Commodity(
                "SILVER",
                "Silver",
                28,
                0.0025
            ),

            Commodity(
                "GAS",
                "Natural Gas",
                3.2,
                0.006
            ),

            Commodity(
                "CORN",
                "Corn",
                450,
                0.002
            )
        ]

    def all_assets(self):

        return (
            self.stocks
            +
            self.commodities
        )

    def get_asset(self, symbol):

        symbol = symbol.upper()

        for asset in self.all_assets():

            if asset.symbol == symbol:

                return asset

        return None

    def generate_news_event(self):

        # Small chance of huge news

        if random.random() < 0.015:

            event = generate_major_event()

        else:

            event = generate_news(
                self.stocks,
                self.commodities
            )

        self.latest_news = event

        self.news_history.append(
            event
        )

        if len(self.news_history) > 20:

            self.news_history.pop(0)

        return event

    def update_prices(self, news):

        for asset in self.all_assets():

            random_move = random.gauss(
                0,
                asset.volatility
            )

            news_move = 0

            if news:

                if (
                    news.symbol
                    ==
                    asset.symbol
                ):

                    news_move = (
                        news.impact
                    )

                elif news.symbol is None:

                    news_move = (
                        news.impact
                        *
                        random.uniform(
                            0.5,
                            1.0
                        )
                    )

            total_move = (
                random_move
                +
                news_move
            )

            asset.update_price(
                asset.price
                *
                (
                    1
                    +
                    total_move
                )
            )

    async def run_traders(self):

        tasks = []

        for trader in self.traders:

            tasks.append(
                trader.think(
                    self,
                    self.latest_news
                )
            )

        results = await asyncio.gather(
            *tasks
        )

        buys = sum(
            result[0]
            for result in results
        )

        sells = sum(
            result[1]
            for result in results
        )

        self.last_trader_orders = (
            buys + sells
        )

        # Trader pressure

        pressure = (
            buys - sells
        )

        if pressure != 0:

            for asset in self.all_assets():

                impact = (
                    pressure
                    /
                    2_000_000
                )

                impact = max(
                    -0.002,
                    min(
                        0.002,
                        impact
                    )
                )

                asset.update_price(
                    asset.price
                    *
                    (1 + impact)
                )

    async def tick(self):

        if not self.clock.is_open:

            self.clock.next_day()

            self.day += 1

            for asset in self.all_assets():

                asset.reset_day()

            return

        # Occasionally generate news

        if (
            self.latest_news is None
            or
            random.random() < 0.025
        ):

            self.generate_news_event()

        self.update_prices(
            self.latest_news
        )

        await self.run_traders()

        await self.clock.tick()