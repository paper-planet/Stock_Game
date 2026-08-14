import asyncio,threading,tkinter as tk
from market import Market
from portfolio import Portfolio
from ui import App

def simulation(market):
    async def run():
        while market.running: await market.tick()
    try:asyncio.run(run())
    except Exception as e:market.errors.append(f'simulation thread: {e}')

def main():
    market=Market();portfolio=Portfolio(100_000_000);market.portfolio=portfolio
    threading.Thread(target=simulation,args=(market,),daemon=True,name='MarketSimulation').start();root=tk.Tk()
    def stop():market.running=False;root.destroy()
    root.protocol('WM_DELETE_WINDOW',stop);App(root,market,portfolio);root.mainloop();market.running=False
if __name__=='__main__':main()
