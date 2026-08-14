import random


class NewsEvent:

    def __init__(
        self,
        headline,
        symbol=None,
        impact=0,
        severity="normal"
    ):
        self.headline = headline
        self.symbol = symbol
        self.impact = impact
        self.severity = severity

    def __str__(self):
        return self.headline


COMPANY_NEWS = [
    (
        "{symbol} beats earnings expectations.",
        0.035
    ),
    (
        "{symbol} misses earnings expectations.",
        -0.035
    ),
    (
        "{symbol} announces a major new contract.",
        0.025
    ),
    (
        "{symbol} loses an important contract.",
        -0.025
    ),
    (
        "Analysts upgrade {symbol}.",
        0.018
    ),
    (
        "Analysts downgrade {symbol}.",
        -0.018
    ),
    (
        "{symbol} announces a major technological breakthrough.",
        0.04
    ),
    (
        "{symbol} faces regulatory concerns.",
        -0.03
    ),
    (
        "{symbol} announces unexpected layoffs.",
        -0.02
    ),
    (
        "Large institutional investors accumulate {symbol}.",
        0.022
    ),
    (
        "Large institutional investors reduce exposure to {symbol}.",
        -0.022
    ),
    (
        "{symbol} announces a large stock buyback.",
        0.025
    ),
    (
        "{symbol} announces plans for a major expansion.",
        0.02
    ),
]


MACRO_NEWS = [
    (
        "Federal Reserve signals that interest rates may remain high.",
        -0.012
    ),
    (
        "Federal Reserve signals potential interest-rate cuts.",
        0.015
    ),
    (
        "US economic growth comes in stronger than expected.",
        0.008
    ),
    (
        "US economic growth disappoints expectations.",
        -0.009
    ),
    (
        "Inflation data comes in hotter than expected.",
        -0.012
    ),
    (
        "Inflation data shows signs of cooling.",
        0.012
    ),
    (
        "Major geopolitical tensions increase.",
        -0.018
    ),
    (
        "Global markets rally on improving economic conditions.",
        0.015
    ),
    (
        "Global markets experience a broad selloff.",
        -0.02
    ),
]


COMMODITY_NEWS = [
    (
        "Oil inventories unexpectedly decline.",
        0.025
    ),
    (
        "Oil inventories unexpectedly increase.",
        -0.025
    ),
    (
        "Major disruption threatens global oil supply.",
        0.045
    ),
    (
        "Global oil production increases.",
        -0.03
    ),
    (
        "Gold demand increases as investors seek safety.",
        0.025
    ),
    (
        "Gold demand weakens as investors move into risk assets.",
        -0.02
    ),
    (
        "Major agricultural supply disruption reported.",
        0.035
    ),
]


def generate_news(stocks, commodities):

    roll = random.random()

    # 65% company news
    if roll < 0.65:

        asset = random.choice(stocks)

        template, impact = random.choice(
            COMPANY_NEWS
        )

        return NewsEvent(
            template.format(
                symbol=asset.symbol
            ),
            asset.symbol,
            impact
        )

    # 20% macro news
    elif roll < 0.85:

        headline, impact = random.choice(
            MACRO_NEWS
        )

        return NewsEvent(
            headline,
            None,
            impact,
            "major"
        )

    # 15% commodity news
    else:

        commodity = random.choice(
            commodities
        )

        headline, impact = random.choice(
            COMMODITY_NEWS
        )

        return NewsEvent(
            headline,
            commodity.symbol,
            impact
        )


def generate_major_event():

    events = [
        (
            "🚨 BREAKING: Major bank reports unexpected losses!",
            -0.035
        ),
        (
            "🚨 BREAKING: Emergency economic stimulus announced!",
            0.03
        ),
        (
            "🚨 BREAKING: Major geopolitical crisis escalates!",
            -0.045
        ),
        (
            "🚨 BREAKING: Surprise economic boom!",
            0.04
        ),
        (
            "🚨 BREAKING: Major financial institution collapses!",
            -0.06
        ),
    ]

    headline, impact = random.choice(events)

    return NewsEvent(
        headline,
        None,
        impact,
        "major"
    )