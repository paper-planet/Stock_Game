#ui
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from options import generate_option_chain


class StockGameUI:

    def __init__(
        self,
        root,
        market,
        portfolio
    ):

        self.root = root
        self.market = market
        self.portfolio = portfolio

        self.root.title(
            "Stock_Game 🐋"
        )

        self.root.geometry(
            "1250x800"
        )

        self.selected_asset = (
            market.stocks[0]
        )

        self.build_ui()

        self.root.after(
            100,
            self.refresh
        )

    def build_ui(self):

        # Header

        header = tk.Frame(
            self.root
        )

        header.pack(
            fill="x"
        )

        self.title = tk.Label(
            header,
            text="🐋 STOCK_GAME",
            font=("Arial", 22, "bold")
        )

        self.title.pack(
            side="left",
            padx=15,
            pady=10
        )

        self.clock_label = tk.Label(
            header,
            font=("Arial", 16)
        )

        self.clock_label.pack(
            side="right",
            padx=15
        )

        # Main area

        main = tk.Frame(
            self.root
        )

        main.pack(
            fill="both",
            expand=True
        )

        # Left ticker

        left = tk.Frame(
            main,
            width=250
        )

        left.pack(
            side="left",
            fill="y"
        )

        tk.Label(
            left,
            text="MARKET",
            font=("Arial", 15, "bold")
        ).pack(
            pady=5
        )

        self.asset_list = tk.Listbox(
            left,
            width=30,
            height=25,
            font=("Courier", 10)
        )

        self.asset_list.pack(
            padx=10
        )

        self.asset_list.bind(
            "<<ListboxSelect>>",
            self.select_asset
        )

        # Center chart

        center = tk.Frame(
            main
        )

        center.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.chart = tk.Canvas(
            center,
            bg="#111111",
            height=400
        )

        self.chart.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )

        self.chart_title = tk.Label(
            center,
            font=("Arial", 16, "bold")
        )

        self.chart_title.pack()

        # Right panel

        right = tk.Frame(
            main,
            width=300
        )

        right.pack(
            side="right",
            fill="y"
        )

        self.info = tk.Text(
            right,
            width=38,
            height=20
        )

        self.info.pack(
            padx=10,
            pady=10
        )

        # Trading controls

        tk.Label(
            right,
            text="TRADE",
            font=("Arial", 14, "bold")
        ).pack()

        self.quantity = tk.Entry(
            right
        )

        self.quantity.insert(
            0,
            "100"
        )

        self.quantity.pack(
            pady=5
        )

        tk.Button(
            right,
            text="BUY",
            command=self.buy
        ).pack(
            fill="x",
            padx=10
        )

        tk.Button(
            right,
            text="SELL",
            command=self.sell
        ).pack(
            fill="x",
            padx=10,
            pady=5
        )

        tk.Button(
            right,
            text="OPTION CHAIN",
            command=self.show_options
        ).pack(
            fill="x",
            padx=10
        )

        # News

        tk.Label(
            self.root,
            text="NEWS",
            font=("Arial", 14, "bold")
        ).pack()

        self.news = tk.Text(
            self.root,
            height=6
        )

        self.news.pack(
            fill="x",
            padx=10
        )

    def select_asset(self, event):

        selection = (
            self.asset_list.curselection()
        )

        if not selection:
            return

        index = selection[0]

        assets = (
            self.market.stocks
            +
            self.market.commodities
        )

        self.selected_asset = (
            assets[index]
        )

    def buy(self):

        try:

            quantity = int(
                self.quantity.get()
            )

        except ValueError:

            messagebox.showerror(
                "Error",
                "Invalid quantity."
            )

            return

        if quantity <= 0:
            return

        success = (
            self.portfolio.buy_asset(
                self.selected_asset,
                quantity
            )
        )

        if success:

            # Whale market impact

            impact = min(
                quantity / 1_000_000,
                0.03
            )

            self.selected_asset.update_price(
                self.selected_asset.price
                *
                (1 + impact)
            )

        else:

            messagebox.showerror(
                "Trade rejected",
                "Insufficient cash."
            )

    def sell(self):

        try:

            quantity = int(
                self.quantity.get()
            )

        except ValueError:

            return

        if quantity <= 0:
            return

        success = (
            self.portfolio.sell_asset(
                self.selected_asset,
                quantity
            )
        )

        if success:

            impact = min(
                quantity / 1_000_000,
                0.03
            )

            self.selected_asset.update_price(
                self.selected_asset.price
                *
                (1 - impact)
            )

        else:

            messagebox.showerror(
                "Trade rejected",
                "You don't own enough."
            )

    def show_options(self):

        options = generate_option_chain(
            self.selected_asset
        )

        window = tk.Toplevel(
            self.root
        )

        window.title(
            f"{self.selected_asset.symbol} Options"
        )

        text = tk.Text(
            window,
            width=70,
            height=20,
            font=("Courier", 11)
        )

        text.pack(
            padx=10,
            pady=10
        )

        for option in options:

            text.insert(
                "end",
                str(option)
                +
                "\n"
            )

    def draw_chart(self):

        self.chart.delete(
            "all"
        )

        history = (
            self.selected_asset.history
        )

        if len(history) < 2:
            return

        width = (
            self.chart.winfo_width()
        )

        height = (
            self.chart.winfo_height()
        )

        if width <= 1:
            return

        minimum = min(history)
        maximum = max(history)

        difference = (
            maximum - minimum
        )

        if difference == 0:
            difference = 1

        points = []

        for i, price in enumerate(
            history
        ):

            x = (
                i
                /
                (len(history) - 1)
                *
                (width - 20)
            ) + 10

            y = (
                height
                -
                (
                    (price - minimum)
                    /
                    difference
                    *
                    (height - 20)
                )
                -
                10
            )

            points.append(
                (x, y)
            )

        for i in range(
            len(points) - 1
        ):

            self.chart.create_line(
                points[i][0],
                points[i][1],
                points[i + 1][0],
                points[i + 1][1],
                fill="white",
                width=2
            )

        self.chart.create_text(
            10,
            10,
            anchor="nw",
            fill="white",
            text=(
                f"Open ${self.selected_asset.open_price:,.2f}   "
                f"High ${self.selected_asset.high:,.2f}   "
                f"Low ${self.selected_asset.low:,.2f}   "
                f"Last ${self.selected_asset.price:,.2f}"
            )
        )

    def refresh(self):

        assets = (
            self.market.stocks
            +
            self.market.commodities
        )

        self.asset_list.delete(
            0,
            "end"
        )

        for asset in assets:

            self.asset_list.insert(
                "end",
                (
                    f"{asset.symbol:<6} "
                    f"${asset.price:>9,.2f} "
                    f"{asset.change_percent():>6.2f}%"
                )
            )

        self.clock_label.config(
            text=(
                f"DAY {self.market.day}   "
                f"{self.market.clock.time_string}"
            )
        )

        self.chart_title.config(
            text=(
                f"{self.selected_asset.symbol} — "
                f"{self.selected_asset.name}"
            )
        )

        self.draw_chart()

        self.info.delete(
            "1.0",
            "end"
        )

        self.info.insert(
            "end",
            self.portfolio.summary(
                assets
            )
        )

        self.news.delete(
            "1.0",
            "end"
        )

        for event in (
            self.market.news_history[-6:]
        ):

            self.news.insert(
                "end",
                str(event)
                +
                "\n"
            )

        self.root.after(
            100,
            self.refresh
        )