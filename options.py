#options
import math
import random


class Option:

    def __init__(
        self,
        underlying,
        strike,
        expiration,
        option_type,
        premium
    ):
        self.underlying = underlying
        self.strike = strike
        self.expiration = expiration
        self.option_type = option_type
        self.premium = premium

    def value(self):
        return self.premium

    def __str__(self):

        return (
            f"{self.underlying.symbol} "
            f"{self.option_type.upper()} "
            f"${self.strike:.2f} "
            f"Premium ${self.premium:.2f} "
            f"({self.expiration}d)"
        )


def normal_cdf(x):

    return (
        1 +
        math.erf(x / math.sqrt(2))
    ) / 2


def black_scholes(
    stock_price,
    strike,
    time,
    volatility,
    risk_free_rate,
    option_type
):

    if time <= 0:

        if option_type == "call":
            return max(
                stock_price - strike,
                0
            )

        return max(
            strike - stock_price,
            0
        )

    d1 = (
        math.log(stock_price / strike)
        +
        (
            risk_free_rate
            +
            volatility ** 2 / 2
        ) * time
    ) / (
        volatility * math.sqrt(time)
    )

    d2 = d1 - volatility * math.sqrt(time)

    if option_type == "call":

        value = (
            stock_price * normal_cdf(d1)
            -
            strike *
            math.exp(-risk_free_rate * time)
            *
            normal_cdf(d2)
        )

    else:

        value = (
            strike *
            math.exp(-risk_free_rate * time)
            *
            normal_cdf(-d2)
            -
            stock_price *
            normal_cdf(-d1)
        )

    return max(value, 0.01)


def create_option(
    stock,
    strike,
    days,
    option_type
):

    volatility = max(
        stock.volatility * 20,
        0.15
    )

    time = days / 365

    premium = black_scholes(
        stock.price,
        strike,
        time,
        volatility,
        0.04,
        option_type
    )

    # Add a little market noise
    premium *= random.uniform(
        0.97,
        1.03
    )

    return Option(
        stock,
        strike,
        days,
        option_type,
        premium
    )


def generate_option_chain(stock):

    strikes = []

    center = stock.price

    for multiplier in [
        0.90,
        0.95,
        1.00,
        1.05,
        1.10
    ]:

        strikes.append(
            round(
                center * multiplier,
                2
            )
        )

    options = []

    for strike in strikes:

        options.append(
            create_option(
                stock,
                strike,
                30,
                "call"
            )
        )

        options.append(
            create_option(
                stock,
                strike,
                30,
                "put"
            )
        )

    return options