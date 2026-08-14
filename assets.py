class Asset:
    def __init__(self, symbol, name, price, volatility=0.001):
        self.symbol = symbol
        self.name = name
        self.price = price
        self.open_price = price
        self.high = price
        self.low = price
        self.previous_price = price
        self.volatility = volatility

        # Intraday price history
        self.history = [price]

    def update_price(self, new_price):
        self.previous_price = self.price

        self.price = max(0.01, new_price)

        self.high = max(self.high, self.price)
        self.low = min(self.low, self.price)

        self.history.append(self.price)

    def change_percent(self):
        if self.open_price == 0:
            return 0

        return (
            (self.price - self.open_price)
            / self.open_price
        ) * 100

    def reset_day(self):
        self.open_price = self.price
        self.high = self.price
        self.low = self.price
        self.history = [self.price]

    def __str__(self):
        return (
            f"{self.symbol:<6} "
            f"${self.price:>10,.2f} "
            f"{self.change_percent():>7.2f}%"
        )


class Stock(Asset):
    pass


class Commodity(Asset):
    pass