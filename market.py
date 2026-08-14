import asyncio,random,threading
from datetime import datetime,timedelta,timezone
from assets import Stock,Commodity,Index,Future,Crypto,InternationalStock,Forex,Candle
from traders import create_traders
from news import generate_news,major,NewsEvent
from universe import STOCKS,COMMODITIES,INDEXES
from data import fetch_history,fetch_many_latest,fetch_sp500_constituents,fetch_market_caps,fetch_us_equities
from orderbook import OrderBook
from markets import market_status

class MarketClock:
    def __init__(self):
        self.current=datetime.now(timezone.utc).replace(second=0,microsecond=0)
        self.speed=.08; self.step_minutes=1
    @property
    def minutes(self):
        return self.current.hour*60+self.current.minute
    @property
    def open(self): return market_status('US',self.current)
    @property
    def time(self):
        et=self.current.astimezone(__import__('zoneinfo').ZoneInfo('America/New_York'))
        return et.strftime('%a %Y-%m-%d %I:%M:%S %p ET')
    @property
    def utc_time(self): return self.current.strftime('%H:%M:%S UTC')
    def advance(self,n=1): self.current += timedelta(minutes=n)

class Market:
    def __init__(self):
        self.lock=threading.RLock(); self.clock=MarketClock(); self.running=True; self.speed=.08; self.step_minutes=1
        self.stocks=self.make_stocks(); self.international=self.make_international(); self.forex=self.make_forex(); self.crypto=self.make_crypto(); self.commodities=self.make_commodities(); self.futures=self.make_futures(); self.indexes=[Index(*r) for r in INDEXES]; self._augment_sp500()
        self.traders=create_traders(); self.latest=None; self.news=[NewsEvent('STOCK_GAME PRO v8 terminal initialized — simulation online.')]; self.orders=0; self.ticks=0; self.errors=[]
        self.inflation=3.2; self.fed_rate=4.5; self.fed_action='Holding'; self.data_status='Loading real-market closes...'; self.loading=set(); self.orderbooks={}; self.data_cache={}; self.pending_orders=[]; self.pending_option_orders=[]; self.pending_spread_orders=[]; self.order_id=0; self.sectors=sorted(set(a.category for a in self.stocks)); self.ui_app=None
        for a in self.all_assets(): self.orderbooks[a.symbol]=OrderBook(a,self.ticks,levels=12)
        threading.Thread(target=self._load_latest_background,daemon=True).start()
    def make_stocks(self):
        rows=list(STOCKS)
        if not any(r[0]=='GME' for r in rows): rows.append(('GME','GameStop','Consumer',.0060))
        assets=[Stock(s,n,100.,v,c,data_symbol=s) for s,n,c,v in rows]
        # Core liquid instruments used by the default 8-chart workspace.
        assets += [Stock('SPY','SPDR S&P 500 ETF Trust',640.,.0016,'ETF',data_symbol='SPY'), Stock('VIX','CBOE Volatility Index',20.,.012,'Volatility',data_symbol='^VIX')]
        return assets
    def make_international(self):
        rows=[('7203.T','Toyota Motor',.0017,'TSE'),('6758.T','Sony Group',.002,'TSE'),('9984.T','SoftBank Group',.003,'TSE'),('0700.HK','Tencent',.0025,'HKEX'),('9988.HK','Alibaba HK',.0027,'HKEX'),('005930.KS','Samsung Electronics',.0022,'TSE'),('SAP.DE','SAP',.0017,'XETRA'),('SHEL.L','Shell',.002,'LSE'),('AZN.L','AstraZeneca',.0016,'LSE'),('HSBA.L','HSBC',.0018,'LSE'),('RIO.L','Rio Tinto',.0022,'LSE'),('BHP.AX','BHP',.0022,'ASX')]
        return [InternationalStock(s,n,100,v,'International',s,ses) for s,n,v,ses in rows]
    def make_forex(self):
        rows=[('EURUSD=X','EUR/USD',1.10,.0012,'FX'),('JPY=X','USD/JPY',150.0,.0015,'FX'),('GBPUSD=X','GBP/USD',1.28,.0013,'FX'),('AUDUSD=X','AUD/USD',.66,.0016,'FX'),('CADUSD=X','USD/CAD',1.36,.0012,'FX'),('CHFUSD=X','USD/CHF',.88,.0012,'FX'),('NZDUSD=X','NZD/USD',.60,.0017,'FX')]
        return [Forex(s,n,p,v,ses) for s,n,p,v,ses in rows]
    def make_crypto(self): return [Crypto('BTC-USD','Bitcoin',100000,.012,'BTC-USD'),Crypto('ETH-USD','Ethereum',3500,.015,'ETH-USD'),Crypto('SOL-USD','Solana',180,.022,'SOL-USD'),Crypto('XRP-USD','XRP',2.5,.025,'XRP-USD')]
    def make_futures(self):
        rows=[('ES=F','E-mini S&P 500',5600,.004,50,.08),('NQ=F','E-mini Nasdaq 100',20000,.005,20,.08),('YM=F','E-mini Dow',41000,.0035,5,.08),('RTY=F','E-mini Russell 2000',2200,.006,50,.10),('CL=F','Crude Oil',75,.006,1000,.10),('GC=F','Gold',2400,.003,100,.08),('SI=F','Silver',28,.006,5000,.12)]
        return [Future(s,n,p,v,'Futures',s,m,r) for s,n,p,v,m,r in rows]
    def _augment_sp500(self):
        rows=fetch_sp500_constituents(timeout=5)
        broad=fetch_us_equities(timeout=5)
        merged=[];seen=set()
        for row in rows+broad:
            if row[0] not in seen:merged.append(row);seen.add(row[0])
        rows=merged;existing={a.symbol for a in self.stocks}
        for sym,name,sector in rows:
            if sym in existing: continue
            clean=sector.replace('Information Technology','Tech').replace('Consumer Discretionary','Consumer').replace('Consumer Staples','Consumer').replace('Communication Services','Communication').replace('Health Care','Health').replace('Industrials','Industrial').replace('Financials','Finance')
            a=Stock(sym,name,100.,.0024 if clean in ('Tech','Consumer') else .0018,clean,data_symbol=sym);a.market_cap=5e9+(abs(hash(sym))%195)*1e9;a.shares_outstanding=a.market_cap/a.price;self.stocks.append(a)
        self.sectors=sorted(set(a.category for a in self.stocks))
    def make_commodities(self):
        out=[]
        for row in COMMODITIES:
            if len(row)==5:sym,name,cat,vol,data=row
            else:sym,name,cat,vol=row;data=sym
            out.append(Commodity(sym,name,100.,vol,cat,data_symbol=data))
        return out
    def all_assets(self): return self.stocks+self.international+self.forex+self.crypto+self.commodities+self.futures+self.indexes
    def tradable_assets(self): return self.stocks+self.international+self.forex+self.crypto+self.commodities+self.futures
    def get_asset(self,symbol):
        s=str(symbol).upper(); return next((a for a in self.all_assets() if a.symbol.upper()==s),None)
    def get_book(self,a): return self.orderbooks.get(a.symbol) if a else None
    def session_open(self,a):
        session=getattr(a,'session','US')
        return market_status(session,self.clock.current) if session in ('US','EXT','LSE','XETRA','TSE','HKEX','SSE','ASX','FX','CRYPTO','CME') else market_status('US',self.clock.current)
    def predict(self,a):
        """Small explainable momentum/mean-reversion score for gameplay, not financial advice."""
        hist=list(a.history)[-40:]
        if len(hist)<8:return {'score':0.,'label':'NEUTRAL','confidence':.5,'momentum':0.,'volatility':a.volatility}
        mom=hist[-1]/max(hist[-8],.0001)-1; fast=sum(hist[-5:])/5; slow=sum(hist[-20:])/max(1,min(20,len(hist))); z=(fast/slow-1) if slow else 0
        score=max(-1,min(1,0.65*mom/ max(a.volatility*8,.0001)+0.35*z/max(a.volatility*5,.0001)))
        return {'score':score,'label':'BULLISH' if score>.25 else 'BEARISH' if score<-.25 else 'NEUTRAL','confidence':min(.95,.5+abs(score)*.45),'momentum':mom,'volatility':a.volatility}
    def _load_latest_background(self):
        assets=self.tradable_assets(); live_assets=assets[:300]; symbols=[a.data_symbol for a in live_assets]
        try: latest=fetch_many_latest(symbols)
        except Exception: latest={}
        try: caps=fetch_market_caps([a.data_symbol for a in self.stocks[:300]])
        except Exception: caps={}
        with self.lock:
            for a in assets:
                c=latest.get(a.data_symbol)
                if c:
                    a.price=float(c.close);a.last_real_close=float(c.close);a.open_price=float(c.close);a.high=float(c.close);a.low=float(c.close);a.previous_price=float(c.close);a.data_loaded=True
                if a.symbol in caps:
                    cap,shares=caps[a.symbol];a.market_cap=cap;a.shares_outstanding=shares or max(1.,cap/max(a.price,.01))
            self.data_status=f'Real closes loaded: {len(latest)}/{len(symbols)} assets'
            for a in self.all_assets():
                b=self.get_book(a)
                if b:b.update(a.price)
    def _period_for(self,tf):
        now=int(datetime.now().timestamp());return {'1D':(now-7*86400,'5m'),'1W':(now-30*86400,'15m'),'1M':(now-90*86400,'1h'),'3M':(now-180*86400,'1h'),'6M':(now-370*86400,'1d'),'1Y':(now-400*86400,'1d'),'5Y':(now-6*365*86400,'1wk'),'MAX':(0,'1d')}.get(tf,(now-400*86400,'1d'))
    def load_chart_data(self,a,tf,force=False):
        if not a:return
        period,interval=self._period_for(tf);key=(a.symbol,tf)
        if not force and a.dataset(interval) and len(a.dataset(interval))>10:return
        if not a.dataset(interval):
            base=max(.01,a.price);mins={'5m':5,'15m':15,'1h':60,'1d':1440,'1wk':10080}.get(interval,1440);count={'5m':240,'15m':300,'1h':320,'1d':500,'1wk':500}.get(interval,500);now=datetime.now().replace(second=0,microsecond=0);tmp=[];px=base;rr=random.Random(hash(a.symbol)&0xffffffff)
            for i in range(count,0,-1):
                ts=now-timedelta(minutes=mins*i);o=px;px=max(.0001,px*(1+rr.gauss(0,a.volatility*.55)));hi=max(o,px)*(1+abs(rr.gauss(0,a.volatility*.25)));lo=min(o,px)*(1-abs(rr.gauss(0,a.volatility*.25)));tmp.append(Candle(ts,o,hi,lo,px,rr.randint(100,10000)))
            a.set_dataset(interval,tmp)
        with self.lock:
            if key in self.loading:return
            self.loading.add(key)
        def worker():
            try:
                c=fetch_history(a.data_symbol,period,interval)
                if c:a.set_dataset(interval,c[-50000:]);self.data_cache[key]=c;a.last_real_timestamp=c[-1].timestamp
            except Exception as e:self.errors.append(f'data {a.symbol}: {e}')
            finally:self.loading.discard(key)
        threading.Thread(target=worker,daemon=True).start()
    def load_ipo_history(self,a): self.load_chart_data(a,'MAX',True)
    def submit_pending(self,side,asset,qty,order_type='LIMIT',price=None):
        self.order_id+=1;o={'id':self.order_id,'side':side.upper(),'asset':asset,'qty':int(qty),'type':order_type.upper(),'price':float(price) if price not in (None,'') else None,'created':self.clock.current,'status':'OPEN'};self.pending_orders.append(o);return o
    def update_pending_price(self,order_id,price):
        for o in self.pending_orders:
            if o['id']==order_id:o['price']=max(.0001,float(price));return True
        return False
    def cancel_pending(self,order_id):
        self.pending_orders=[o for o in self.pending_orders if o['id']!=order_id]
    def submit_option_pending(self,side,contract,qty,order_type='LIMIT',price=None):
        self.order_id+=1;o={'id':self.order_id,'side':side.upper(),'contract':contract,'qty':int(qty),'type':order_type.upper(),'price':float(price) if price not in (None,'') else None,'created':self.clock.current,'status':'OPEN'};self.pending_option_orders.append(o);return o
    def process_pending(self,portfolio):
        if not portfolio:return
        keep=[]
        for o in self.pending_orders:
            a=o['asset'];p=a.price;trigger=False
            if o['type']=='LIMIT':trigger=(o['side'] in ('BUY','SHORT') and p<=o['price']) or (o['side'] in ('SELL','COVER') and p>=o['price'])
            elif o['type']=='STOP':trigger=(o['side'] in ('BUY','COVER') and p>=o['price']) or (o['side'] in ('SELL','SHORT') and p<=o['price'])
            if trigger:
                fn={'BUY':portfolio.buy_asset,'SELL':portfolio.sell_asset,'SHORT':portfolio.short_asset,'COVER':portfolio.cover_short}[o['side']];ok,msg=fn(a,o['qty']);o['status']='FILLED' if ok else 'REJECTED';o['message']=msg
            else:keep.append(o)
        self.pending_orders=keep
        okkeep=[]
        for o in self.pending_option_orders:
            c=o['contract'];p=c.mid;trigger=(o['side']=='BUY' and o['type']=='LIMIT' and p<=o['price']) or (o['side']=='SELL' and o['type']=='LIMIT' and p>=o['price']) or (o['side']=='BUY' and o['type']=='STOP' and p>=o['price']) or (o['side']=='SELL' and o['type']=='STOP' and p<=o['price'])
            if trigger:
                from options import OptionStrategy
                s=OptionStrategy(f'{o["side"]} {c}');s.add_leg(c,o['qty'],'BUY' if o['side']=='BUY' else 'SELL');ok,msg=portfolio.execute_strategy(s);o['status']='FILLED' if ok else 'REJECTED';o['message']=msg
            else:okkeep.append(o)
        self.pending_option_orders=okkeep
        spread_keep=[]
        for o in self.pending_spread_orders:
            strategy=o['strategy']; value=strategy.current_value(); trigger=(o['side']=='BUY' and o['type']=='LIMIT' and value<=o['price']) or (o['side']=='SELL' and o['type']=='LIMIT' and value>=o['price']) or (o['side']=='BUY' and o['type']=='STOP' and value>=o['price']) or (o['side']=='SELL' and o['type']=='STOP' and value<=o['price'])
            if trigger:
                ok,msg=portfolio.execute_strategy(strategy);o['status']='FILLED' if ok else 'REJECTED';o['message']=msg
            else:spread_keep.append(o)
        self.pending_spread_orders=spread_keep
    def submit_spread_pending(self,side,strategy,order_type='LIMIT',price=None):
        self.order_id+=1;o={'id':self.order_id,'side':side.upper(),'strategy':strategy,'type':order_type.upper(),'price':float(price) if price not in (None,'') else None,'created':self.clock.current,'status':'OPEN'};self.pending_spread_orders.append(o);return o
    def event(self):
        self.latest=major() if random.random()<.01 else generate_news(self.stocks,self.commodities);self.news.append(self.latest);self.news=self.news[-80:]
    def fed(self):
        gap=self.inflation-2
        if gap>1.2:self.fed_rate=min(8,self.fed_rate+.005);self.fed_action='Aggressive hike'
        elif gap>.4:self.fed_rate=min(8,self.fed_rate+.002);self.fed_action='Gradual hike'
        elif gap<-.5:self.fed_rate=max(.5,self.fed_rate-.003);self.fed_action='Cutting'
        else:self.fed_action='Holding'
    def prices(self):
        for a in self.tradable_assets():
            if not self.session_open(a):continue
            book=self.get_book(a);snap=book.snapshot() if book else None;flow=random.gauss(0,a.volatility*.45);impact=(self.latest.impact if self.latest and self.latest.symbol==a.symbol else 0);imb=snap['imbalance']*.0004 if snap else 0
            a.update_price(a.price*(1+flow+impact+imb),random.randint(100,12000),self.clock.current);book.update(a.price,flow/max(a.volatility,.0001),1+abs(flow)/max(a.volatility,.0001))
        for idx in self.indexes:
            members=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
            if idx.symbol=='SPX':members=self.stocks
            elif idx.symbol=='NDX':members=[a for a in self.stocks if a.category in ('Tech','Communication','Consumer')]
            elif idx.symbol=='DJI':members=[self.get_asset(s) for s in {'AAPL','AMGN','AMZN','AXP','BA','CAT','CRM','CSCO','CVX','DIS','GS','HD','HON','IBM','INTC','JNJ','JPM','KO','MCD','MMM','MRK','MSFT','NKE','PG','TRV','UNH','V','VZ','WMT'} if self.get_asset(s)]
            elif idx.symbol=='RUT':members=[a for a in self.stocks if a.market_cap<50e9]
            if members:
                total=sum(max(1,a.market_cap) for a in members);daily=sum((a.price/max(a.open_price,.01)-1)*(a.market_cap/total) for a in members);target=idx.open_price*(1+daily);idx.update_price(target,0,self.clock.current,record=False);self.get_book(idx).update(idx.price,daily*2)
        spx=self.get_asset('SPX'); spy=self.get_asset('SPY'); vix=self.get_asset('VIX')
        if spx and spy:
            spy.update_price(spy.open_price*(spx.price/max(spx.open_price,.01)),random.randint(5000,30000),self.clock.current)
        if vix:
            stress=sum(a.volatility for a in self.stocks)/max(1,len(self.stocks));vix_target=max(9.,min(80.,20*(1+stress*18)))
            vix.update_price(max(.1,vix.price*.97+vix_target*.03),random.randint(500,5000),self.clock.current)
        if random.random()<.00015 and self.stocks:
            candidates=[a for a in self.stocks if a.price>120]
            if candidates:random.choice(candidates).split(random.choice((2,3,4)))
    async def traders_step(self):
        try:
            results=await asyncio.gather(*[t.think(self,self.latest) for t in self.traders],return_exceptions=True);self.orders=sum(r[2] for r in results if isinstance(r,tuple))
        except Exception as e:self.errors.append(f'traders: {e}')
    async def tick(self):
        try:
            self.prices(); self.process_pending(getattr(self,'portfolio',None))
            if self.ticks%5==0:self.event();self.fed()
            if self.ticks%2==0:await self.traders_step()
            self.clock.advance(self.step_minutes);self.ticks+=1;await asyncio.sleep(self.speed)
        except Exception as e:self.errors.append(f'tick: {e}');await asyncio.sleep(self.speed)
