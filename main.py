import asyncio
import threading
import tkinter as tk

from market import Market
from portfolio import Portfolio
from ui import StockGameUI


def run_market(market):

    async def simulation():

        while market.running:

            await market.tick()

    asyncio.run(
        simulation()
    )


def main():

    market = Market()

    portfolio = Portfolio(
        100_000_000
    )

    # Run the simulation in its
    # own thread so Tkinter remains responsive.

    market_thread = threading.Thread(
        target=run_market,
        args=(market,),
        daemon=True
    )

    market_thread.start()

    root = tk.Tk()

    StockGameUI(
        root,
        market,
        portfolio
    )

    root.mainloop()

    market.running = False


if __name__ == "__main__":
    main()