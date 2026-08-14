from dataclasses import dataclass
import random

@dataclass
class BookLevel:
    price: float; size: int; orders: int; venue: str; market_maker: str; hidden: int=0

class OrderBook:
    def __init__(self,asset,seed=0,levels=10):
        self.asset=asset; self.rng=random.Random(seed+hash(asset.symbol)%100000); self.levels=levels; self.bids=[]; self.asks=[]; self.last_trade=asset.price; self.trade_size=100; self.imbalance=0.; self.update()
    def update(self,mid=None,pressure=0.,vol_mult=1.):
        p=max(.0001,float(mid if mid is not None else self.asset.price)); tick=max(.0001,p*.00003); base=max(50,int(1800*max(.15,min(4,vol_mult))*(1+abs(pressure))))
        self.imbalance=max(-1,min(1,pressure)); self.bids=[];self.asks=[]
        makers=('VIRTEX','ALPHA_MM','NOVA_MM','FLOW_MM','CROSSING')
        for i in range(1,self.levels+1):
            dist=tick*i*(1+self.rng.random()*0.8); skew=pressure*p*.0007
            bp=max(.0001,p-dist+skew); ap=max(.0001,p+dist+skew)
            bs=max(1,int(base/(i**.60)*self.rng.uniform(.55,1.55))); asz=max(1,int(base/(i**.60)*self.rng.uniform(.55,1.55)))
            self.bids.append(BookLevel(bp,bs,self.rng.randint(1,max(2,min(99,bs//8))),self.rng.choice(makers),self.rng.choice(makers),int(bs*.1)))
            self.asks.append(BookLevel(ap,asz,self.rng.randint(1,max(2,min(99,asz//8))),self.rng.choice(makers),self.rng.choice(makers),int(asz*.1)))
        self.asset.bid=self.bids[0].price; self.asset.ask=self.asks[0].price
    def snapshot(self):return {'bids':self.bids[:],'asks':self.asks[:],'last':self.last_trade,'imbalance':self.imbalance,'spread':self.asks[0].price-self.bids[0].price}
    def execute(self,side,qty,limit=None):
        remaining=int(max(0,qty));fills=[];levels=self.asks if side.upper()=='BUY' else self.bids
        for lvl in levels:
            if limit is not None and ((side.upper()=='BUY' and lvl.price>limit) or (side.upper()=='SELL' and lvl.price<limit)):break
            take=min(remaining,lvl.size)
            if take:fills.append((lvl.price,take,lvl.market_maker,lvl.venue));remaining-=take
            if remaining<=0:break
        if fills:self.last_trade=fills[-1][0]
        return fills,remaining
    def level3(self):
        rows=[]
        for side,levels in [('ASK',self.asks),('BID',self.bids)]:
            for lvl in levels:
                rem=lvl.size; count=max(1,min(lvl.orders,20))
                for n in range(count):
                    size=max(1,rem//max(1,count-n)); rem=max(0,rem-size)
                    rows.append((side,lvl.price,size,lvl.market_maker,f'{lvl.venue}-{n%4+1}',n+1,lvl.hidden if n==0 else 0))
                    if rem<=0:break
        return rows
