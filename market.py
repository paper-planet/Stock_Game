import asyncio,random,threading,time
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from asset import Stock,Commodity,Index,Future,Crypto,Forex,InternationalStock,Candle
from orderbook import OrderBook
from universe import STOCKS,COMMODITIES,INDEXES
from news import generate_news,major
from markets import market_status

class GameClock:
    def __init__(self):
        now=datetime.now(ZoneInfo('America/New_York')).replace(tzinfo=None)
        self.current=now.replace(second=0,microsecond=0);self.running=True
    def advance(self,minutes):self.current+=timedelta(minutes=minutes)
    @property
    def time(self):return self.current.strftime('%Y-%m-%d %H:%M')
    @property
    def utc_time(self):return self.current.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).strftime('%H:%M UTC')
    @property
    def open(self):return market_status('US',self.current.replace(tzinfo=ZoneInfo('America/New_York')))

class Market:
    def __init__(self):
        self.running=True;self.paused=False;self.speed=.08;self.step_minutes=1;self.difficulty='MEDIUM';self.clock=GameClock();self.errors=[];self.news=[];self.data_status='SIMULATION READY';self.pending_orders=[];self.pending_option_orders=[];self.pending_spread_orders=[];self.order_id=1;self.books={};self.ui_app=None;self._loader_started=False;self._lock=threading.RLock()
        prices={'AAPL':210,'MSFT':520,'NVDA':180,'AMZN':225,'META':760,'GOOGL':190,'GOOG':192,'AVGO':300,'TSLA':340,'JPM':290,'V':350,'MA':580,'WMT':100,'COST':960,'NFLX':1150,'ORCL':240,'CRM':310,'AMD':165,'INTC':24,'QCOM':175,'CSCO':70,'IBM':250,'PLTR':160,'UBER':95,'DIS':120,'KO':70,'PEP':150,'MCD':300,'NKE':75,'XOM':110,'CVX':155,'GE':285,'CAT':400,'BA':180,'JNJ':175,'PFE':25,'LLY':800,'UNH':320,'BAC':50,'GS':720,'MS':150,'C':100,'WFC':85,'COIN':330,'HOOD':115,'SHOP':140,'MSTR':400,'ARM':150,'TSM':200,'ASML':700,'BABA':120,'NVO':55,'SAP':280,'SONY':30,'TM':250,'GME':25,'SPY':640,'VIX':18}
        self.stocks=[Stock(s,n,p if (p:=prices.get(s,100)) else 100,v,c) for s,n,c,v in STOCKS]
        self.commodities=[Commodity(s,n,{'CL=F':65,'BZ=F':68,'GC=F':3400,'SI=F':38,'HG=F':4.5,'NG=F':3.2,'ZC=F':450,'ZW=F':520,'ZS=F':1050}.get(s,100),v,c,data_symbol=s) for s,n,c,v in COMMODITIES]
        self.indexes=[Index(s,n,p,com,v) for s,n,p,com,v in INDEXES]
        self.futures=[Future('ES=F','E-mini S&P 500',6400,.001,'Futures','ES=F',50,.08,'CME'),Future('NQ=F','E-mini Nasdaq 100',23500,.002,'Futures','NQ=F',20,.08,'CME')]
        self.crypto=[Crypto('BTC-USD','Bitcoin',118000,.01),Crypto('ETH-USD','Ethereum',4200,.012)]
        self.forex=[Forex('EURUSD=X','EUR/USD',1.17,.0015),Forex('USDJPY=X','USD/JPY',148,.0015),Forex('GBPUSD=X','GBP/USD',1.35,.0015)]
        self.international=[InternationalStock('LSEG','London Stock Exchange',11500,.0018,'International','LSEG.L','LSE','GBP'),InternationalStock('7203.T','Toyota',2600,.0017,'International','7203.T','TSE','JPY'),InternationalStock('9984.T','SoftBank',12000,.0025,'International','9984.T','TSE','JPY')]
        self._assets={a.symbol:a for a in self.all_assets()};self.sectors=sorted({a.category for a in self.stocks});self._init_history()
    def _init_history(self):
        base=self.clock.current-timedelta(days=60)
        for a in self.all_assets():
            p=a.price
            for i in range(60):
                ts=base+timedelta(days=i);o=p;p=max(.0001,p*(1+random.gauss(0,a.volatility*2)));a.live_bars.setdefault('1d',[]).append(Candle(ts,o,max(o,p),min(o,p),p,random.randint(1000,1000000)))
            a.datasets['1d']=list(a.live_bars['1d']);a.candles.clear();a.candles.extend(a.datasets['1d']);a.history.clear();a.history.extend(c.close for c in a.candles)
    def all_assets(self):return self.stocks+self.indexes+self.commodities+self.futures+self.crypto+self.forex+self.international
    def get_asset(self,symbol):return self._assets.get(symbol)
    def get_book(self,a):
        if a.symbol not in self.books:self.books[a.symbol]=OrderBook(a)
        self.books[a.symbol].update(a.price,0,a.volatility/.001)
        return self.books[a.symbol]
    def predict(self,a):
        h=list(a.history);mom=(h[-1]/h[-20]-1) if len(h)>=20 else 0;vol=a.volatility;label='BULLISH' if mom>.01 else 'BEARISH' if mom<-.01 else 'NEUTRAL';return {'label':label,'confidence':min(.99,.5+abs(mom)*4),'momentum':mom,'volatility':vol}
    def load_chart_data(self,a,interval='1d'):return a.chart_candles(interval)
    def load_ipo_history(self,a):return None
    def submit_pending(self,side,a,qty,otype,price):
        o={'id':self.order_id,'side':side,'asset':a,'qty':int(qty),'type':otype,'price':price};self.order_id+=1;self.pending_orders.append(o);return o
    def submit_option_pending(self,side,contract,qty,otype,price):
        o={'id':self.order_id,'side':side,'contract':contract,'qty':int(qty),'type':otype,'price':price};self.order_id+=1;self.pending_option_orders.append(o);return o
    def submit_spread_pending(self,side,strategy,otype,price):
        o={'id':self.order_id,'side':side,'strategy':strategy,'type':otype,'price':price};self.order_id+=1;self.pending_spread_orders.append(o);return o
    def update_pending_price(self,*args,**kwargs):return None
    def _process_orders(self):
        for o in list(self.pending_orders):
            a=o['asset'];p=a.ask if o['side'] in ('BUY','COVER') else a.bid;target=o['price'];hit=o['type']=='MARKET' or target is None or (o['side'] in ('BUY','COVER') and p<=target) or (o['side'] in ('SELL','SHORT') and p>=target)
            if hit:
                try:
                    fn={'BUY':self.portfolio.buy_asset,'SELL':self.portfolio.sell_asset,'SHORT':self.portfolio.short_asset,'COVER':self.portfolio.cover_short}[o['side']];fn(a,o['qty']);self.pending_orders.remove(o)
                except Exception as e:self.errors.append(f'order {o["id"]}: {e}');self.pending_orders.remove(o)
    async def tick(self):
        if not self.running:return
        if self.paused:await asyncio.sleep(.05);return
        try:
            self.clock.advance(self.step_minutes)
            with self._lock:
                for a in self.all_assets():
                    if a.symbol in ('SPX','NDX','DJI','RUT'): continue
                    shock=random.gauss(0,a.volatility);a.update_price(a.price*(1+shock),random.randint(100,50000),self.clock.current)
                for idx in self.indexes:
                    comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)];r=sum(c.change_percent()/100 for c in comps)/max(1,len(comps));idx.update_price(idx.price*(1+r*.08+random.gauss(0,idx.volatility)),random.randint(1000,100000),self.clock.current)
                if random.random()<.012:self.news.append(generate_news(self.stocks,self.commodities))
                if random.random()<.001:self.news.append(major())
                self._process_orders()
                if hasattr(self,'portfolio'):
                    self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
            self.data_status='SIMULATION RUNNING'
        except Exception as e:
            self.errors.append(f'tick: {type(e).__name__}: {e}')
            if len(self.errors)>100:self.errors=self.errors[-100:]
        await asyncio.sleep(max(.001,float(self.speed)))
    def start_background_loaders(self):
        if self._loader_started:return
        self._loader_started=True;threading.Thread(target=self._background_loader,daemon=True,name='MarketDataLoader').start()
    def _background_loader(self):
        self.data_status='SIMULATION + OPTIONAL LIVE DATA'
        try:
            from data import fetch_many_latest
            latest=fetch_many_latest([a.data_symbol for a in self.stocks[:20]],workers=6)
            for a in self.stocks:
                c=latest.get(a.data_symbol)
                if c:a.set_dataset('1d',[c])
        except Exception as e:self.errors.append(f'background data: {e}')
