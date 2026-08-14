class Portfolio:

    def __init__(self, cash=100_000_000):

        self.cash = cash

        self.positions = {}

        self.options = []

    def buy_asset(
        self,
        asset,
        quantity
    ):

        cost = asset.price * quantity

        if cost > self.cash:

            return False

        self.cash -= cost

        self.positions[
            asset.symbol
        ] = self.positions.get(
            asset.symbol,
            0
        ) + quantity

        return True

    def sell_asset(
        self,
        asset,
        quantity
    ):

        owned = self.positions.get(
            asset.symbol,
            0
        )

        if quantity > owned:

            return False

        self.cash += (
            asset.price * quantity
        )

        self.positions[
            asset.symbol
        ] -= quantity

        return True

    def buy_option(
        self,
        option,
        quantity
    ):

        cost = (
            option.premium
            *
            quantity
            *
            100
        )

        if cost > self.cash:

            return False

        self.cash -= cost

        self.options.append(
            {
                "option": option,
                "quantity": quantity
            }
        )

        return True

    def value(self, assets):

        total = self.cash

        for asset in assets:

            quantity = self.positions.get(
                asset.symbol,
                0
            )

            total += (
                asset.price
                *
                quantity
            )

        for position in self.options:

            option = position["option"]

            total += (
                option.premium
                *
                position["quantity"]
                *
                100
            )

        return total

    def summary(self, assets):

        lines = []

        lines.append(
            f"Cash: ${self.cash:,.2f}"
        )

        lines.append("")

        lines.append("POSITIONS")

        for asset in assets:

            quantity = self.positions.get(
                asset.symbol,
                0
            )

            if quantity:

                value = (
                    asset.price
                    *
                    quantity
                )

                lines.append(
                    f"{asset.symbol}: "
                    f"{quantity:,} "
                    f"(${value:,.2f})"
                )

        lines.append("")

        lines.append("OPTIONS")

        for position in self.options:

            option = position["option"]

            lines.append(
                f"{option} "
                f"x{position['quantity']}"
            )

        lines.append("")

        lines.append(
            f"NET WORTH: "
            f"${self.value(assets):,.2f}"
        )

        return "\n".join(lines)