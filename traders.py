import asyncio
import random


class Trader:

    def __init__(
        self,
        name,
        trader_type,
        cash
    ):

        self.name = name
        self.trader_type = trader_type
        self.cash = cash

        self.positions = {}

    def buy(
        self,
        asset,
        quantity
    ):

        cost = (
            asset.price
            *
            quantity
        )

        if cost > self.cash:

            return 0

        self.cash -= cost

        self.positions[
            asset.symbol
        ] = self.positions.get(
            asset.symbol,
            0
        ) + quantity

        return quantity

    def sell(
        self,
        asset,
        quantity
    ):

        owned = self.positions.get(
            asset.symbol,
            0
        )

        quantity = min(
            quantity,
            owned
        )

        if quantity <= 0:

            return 0

        self.positions[
            asset.symbol
        ] -= quantity

        self.cash += (
            asset.price
            *
            quantity
        )

        return quantity

    async def think(
        self,
        market,
        news
    ):

        await asyncio.sleep(
            random.uniform(
                0.01,
                0.15
            )
        )

        asset = None

        if news and news.symbol:

            asset = market.get_asset(
                news.symbol
            )

        if asset is None:

            asset = random.choice(
                market.all_assets()
            )

        buy_probability = 0.5

        # Different trader personalities

        if self.trader_type == "Retail":

            buy_probability = 0.52

        elif self.trader_type == "Momentum":

            buy_probability = 0.55

        elif self.trader_type == "Value":

            buy_probability = 0.48

        elif self.trader_type == "Bank":

            buy_probability = 0.50

        elif self.trader_type == "Prop Firm":

            buy_probability = 0.51

        # News reaction

        if news:

            if news.symbol == asset.symbol:

                buy_probability += (
                    news.impact * 3
                )

        if random.random() < buy_probability:

            quantity = random.randint(
                10,
                300
            )

            return (
                self.buy(
                    asset,
                    quantity
                ),
                0
            )

        else:

            quantity = random.randint(
                10,
                300
            )

            return (
                0,
                self.sell(
                    asset,
                    quantity
                )
            )


def create_traders():

    traders = []

    types = [
        "Retail",
        "Retail",
        "Momentum",
        "Value",
        "Bank",
        "Prop Firm"
    ]

    for i in range(75):

        trader_type = random.choice(
            types
        )

        traders.append(
            Trader(
                f"{trader_type}_{i + 1}",
                trader_type,
                random.randint(
                    250_000,
                    10_000_000
                )
            )
        )

    return traders