import asyncio,random
class Trader:
    def __init__(self,name,kind,cash):self.name=name;self.kind=kind;self.cash=cash;self.positions={}
    async def think(self,market,news):
        await asyncio.sleep(random.uniform(.001,.012));asset=market.get_asset(news.symbol) if news and news.symbol else None
        if asset is None:asset=random.choice(market.stocks)
        bias={'Retail':0,'Momentum':.02,'Value':-.02,'Bank':0,'Prop':.01,'Macro':0}.get(self.kind,0)
        signal=asset.change_percent()/100+bias
        if news and news.symbol==asset.symbol:signal+=news.impact*2
        p=.5+max(-.3,min(.3,signal*4));qty=random.randint(10,600)
        return asset,('BUY' if random.random()<p else 'SELL'),qty
def create_traders():
    kinds=['Retail','Momentum','Value','Bank','Prop','Macro'];return [Trader(f'{k}-{i}',k,random.randint(100_000,10_000_000)) for i in range(120) for k in [random.choice(kinds)]]
