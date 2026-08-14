from collections import deque
from dataclasses import dataclass
from datetime import datetime
import threading

@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

class Asset:
    def __init__(self,symbol,name,price,volatility=.002,category='',data_symbol=None,ipo_date=None):
        self.symbol=symbol; self.name=name; self.price=float(price); self.open_price=self.price
        self.high=self.price; self.low=self.price; self.previous_price=self.price
        self.volatility=float(volatility); self.category=category; self.data_symbol=data_symbol or symbol; self.ipo_date=ipo_date; self.ipo_price=None
        self.history=deque(maxlen=30000); self.candles=deque(maxlen=30000); self.datasets={}; self.volume=0
        self.bid=max(.0001,self.price*(1-self.volatility*.10)); self.ask=self.price*(1+self.volatility*.10)
        self.data_loaded=False; self.last_real_close=self.price; self.market_cap=1_000_000_000.; self.shares_outstanding=max(1.,self.market_cap/self.price)
        self.pending_split=None; self.last_real_timestamp=None; self.last_update=None; self.live_bars={}; self.data_lock=threading.RLock()
        self.trade_count=0; self.dollar_volume=0.; self.history.append(self.price)
    def _bucket(self,ts,minutes): return ts.replace(minute=(ts.minute//minutes)*minutes,second=0,microsecond=0)
    def _update_bar(self,interval,minutes,ts,price,volume):
        bucket=self._bucket(ts.replace(tzinfo=None) if getattr(ts,'tzinfo',None) else ts,minutes); bars=self.live_bars.setdefault(interval,[])
        if not bars or bars[-1].timestamp!=bucket: bars.append(Candle(bucket,self.previous_price,price,price,price,int(max(0,volume))))
        else:
            c=bars[-1]; c.high=max(c.high,price); c.low=min(c.low,price); c.close=price; c.volume+=int(max(0,volume))
        if len(bars)>30000: del bars[:-30000]
    def update_price(self,new_price,volume=0,timestamp=None,record=True):
        with self.data_lock:
            self.previous_price=self.price; self.price=max(.0001,float(new_price)); self.high=max(self.high,self.price); self.low=min(self.low,self.price)
            self.history.append(self.price); self.volume+=int(max(0,volume)); self.trade_count+=1; self.dollar_volume+=self.price*max(0,volume)
            spread=max(self.price*.00008,self.price*self.volatility*.025); self.bid=max(.0001,self.price-spread); self.ask=self.price+spread
            ts=timestamp or datetime.now(); ts=ts.replace(tzinfo=None) if getattr(ts,'tzinfo',None) else ts; self.last_update=ts
            if record:
                for interval,mins in [('1m',1),('5m',5),('15m',15),('1h',60),('1d',1440)]: self._update_bar(interval,mins,ts,self.price,volume)
                self.candles=deque(self.live_bars['1d'][-30000:],maxlen=30000)
    def set_dataset(self,interval,candles):
        if not candles:return
        candles=sorted(candles,key=lambda c:c.timestamp); self.datasets[interval]=candles
        if interval=='1d':
            self.candles=deque(candles[-30000:],maxlen=30000); self.history=deque([c.close for c in candles[-30000:]],maxlen=30000)
            first,last=candles[0],candles[-1]; self.ipo_date=first.timestamp.date(); self.ipo_price=float(first.open); self.price=float(last.close); self.last_real_close=self.price; self.last_real_timestamp=last.timestamp
            self.open_price=self.price; self.high=self.price; self.low=self.price; self.previous_price=self.price; self.volume=int(last.volume); self.data_loaded=True; self._reprice_book()
    def _reprice_book(self):
        spread=max(self.price*.00008,self.price*self.volatility*.025); self.bid=max(.0001,self.price-spread); self.ask=self.price+spread
    def dataset(self,interval): return self.datasets.get(interval,[])
    def chart_candles(self,interval=None):
        interval=interval or '1d'; hist=list(self.datasets.get(interval,[])); live=list(self.live_bars.get(interval,[]))
        if not hist:return live
        if not live:return hist
        if live[0].timestamp<=hist[-1].timestamp: live=[c for c in live if c.timestamp>hist[-1].timestamp]
        return hist+live
    def change_percent(self): return (self.price/self.open_price-1)*100 if self.open_price else 0
    def split(self,ratio):
        ratio=float(ratio)
        if ratio<=0:return
        self.price=max(.0001,self.price/ratio); self.open_price/=ratio; self.high/=ratio; self.low/=ratio; self.previous_price/=ratio; self.shares_outstanding*=ratio; self.pending_split=ratio; self._reprice_book()
    def reset_day(self): self.open_price=self.price; self.high=self.price; self.low=self.price; self.volume=0
class Stock(Asset): pass
class Commodity(Asset): pass
class Index(Asset):
    def __init__(self,symbol,name,price,components,volatility=.001): super().__init__(symbol,name,price,volatility,'Index'); self.components=components
class Future(Asset):
    def __init__(self,symbol,name,price,volatility=.003,category='Futures',data_symbol=None,multiplier=1.,margin_rate=.08,session='CME'):
        super().__init__(symbol,name,price,volatility,category,data_symbol=data_symbol or symbol); self.multiplier=float(multiplier); self.margin_rate=float(margin_rate); self.session=session
class Crypto(Asset):
    def __init__(self,symbol,name,price,volatility=.01,data_symbol=None): super().__init__(symbol,name,price,volatility,'Crypto',data_symbol=data_symbol or symbol); self.session='CRYPTO'
class Forex(Asset):
    def __init__(self,symbol,name,price,volatility=.0015,session='FX',currency='USD'): super().__init__(symbol,name,price,volatility,'Forex',data_symbol=symbol); self.session=session; self.currency=currency
class InternationalStock(Stock):
    def __init__(self,symbol,name,price,volatility,category,data_symbol,session,currency='USD'): super().__init__(symbol,name,price,volatility,category,data_symbol=data_symbol); self.session=session; self.currency=currency
