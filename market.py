import asyncio,random,threading,time,math,os
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from game_core import Stock,Commodity,Index,Future,Crypto,Forex,InternationalStock,Candle
from game_core import OrderBook
from game_core import STOCKS,COMMODITIES,INDEXES,GLOBAL_STOCKS,GLOBAL_INDEXES,INCEPTION_FALLBACK
from game_core import generate_news,major,NewsEvent
from game_core import market_status,SESSIONS

class GameClock:
    def __init__(self):
        now=datetime.now(ZoneInfo('America/New_York')).replace(tzinfo=None)
        self.current=now.replace(microsecond=0);self.running=True
    def advance(self,minutes):self.current+=timedelta(minutes=float(minutes))
    def advance_seconds(self,seconds):self.current+=timedelta(seconds=float(seconds))
    @property
    def time(self):return self.current.strftime('%Y-%m-%d %H:%M:%S')
    @property
    def utc_time(self):return self.current.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).strftime('%H:%M:%S UTC')
    @property
    def open(self):return market_status('US',self.current.replace(tzinfo=ZoneInfo('America/New_York')))
    def us_session_countdown(self):
        dt=self.current
        wd=dt.weekday();mins=dt.hour*60+dt.minute+dt.second/60
        open_m,close_m=9*60+30,16*60
        if wd<5 and open_m<=mins<close_m:
            sec=max(0,int((close_m-mins)*60));label='CLOSES IN'
        else:
            probe=dt
            while True:
                target=probe.replace(hour=9,minute=30,second=0,microsecond=0)
                if probe.weekday()<5 and probe<target:break
                probe=(probe+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
                if probe.weekday()<5:
                    target=probe.replace(hour=9,minute=30,second=0,microsecond=0);break
            sec=max(0,int((target-dt).total_seconds()));label='OPENS IN'
        d,sec=divmod(sec,86400);h,sec=divmod(sec,3600);m,sec=divmod(sec,60)
        text=(f'{d}d {h:02d}:{m:02d}:{sec:02d}' if d else f'{h:02d}:{m:02d}:{sec:02d}')
        return label,text

class Market:
    """Fast fictional market/economy simulator.

    Real-time pacing is decoupled from render speed: at 1x, one real second advances
    one in-game minute. Price dynamics are scaled by elapsed simulated time so higher
    time-warp changes the entire economy without spawning hundreds of UI callbacks.
    """
    def __init__(self):
        self.running=True;self.paused=False
        self.speed=.05                 # engine cadence (~20 Hz); real-time clock remains elapsed-time based
        self.time_warp=10.0            # 1x => 1 real second = 1 game minute
        self.step_minutes=1            # retained for compatibility with older controls
        self.difficulty='MEDIUM';self.clock=GameClock();self.visual_version=0;self.errors=[];self.news=[];self.expiration_events=[];self.data_status='SIMULATION READY';self.pending_orders=[];self.pending_option_orders=[];self.pending_spread_orders=[];self.order_id=1;self.books={};self.ui_app=None;self._loader_started=False;self._lock=threading.RLock();self._last_real_tick=time.monotonic();self._macro_accum_minutes=0.0;self._last_fed_day=self.clock.current.date();self.seed=int(os.environ.get('STOCK_GAME_SEED','0') or 0);random.seed(self.seed if self.seed else None)
        self.macro={'inflation':2.6,'policy_rate':4.25,'unemployment':4.1,'gdp_growth':2.0,'ten_year':4.35,'dollar':100.0,'sentiment':0.05,'liquidity':1.0,'fed_target':2.0}
        self._sector_factor={};self._book_cache_time={};self.freight_routes=[];self.shipments=[];self.freight_events=[];self._history_loading=set();self.research_mode=True;self.real_macro_source='SIMULATED'
        prices={'AAPL':210,'MSFT':520,'NVDA':180,'AMZN':225,'META':760,'GOOGL':190,'GOOG':192,'AVGO':300,'TSLA':340,'JPM':290,'V':350,'MA':580,'WMT':100,'COST':960,'NFLX':1150,'ORCL':240,'CRM':310,'AMD':165,'INTC':24,'QCOM':175,'CSCO':70,'IBM':250,'PLTR':160,'UBER':95,'DIS':120,'KO':70,'PEP':150,'MCD':300,'NKE':75,'XOM':110,'CVX':155,'GE':285,'CAT':400,'BA':180,'JNJ':175,'PFE':25,'LLY':800,'UNH':320,'BAC':50,'GS':720,'MS':150,'C':100,'WFC':85,'COIN':330,'HOOD':115,'SHOP':140,'MSTR':400,'ARM':150,'TSM':200,'ASML':700,'BABA':120,'NVO':55,'SAP':280,'SONY':30,'TM':250,'GME':25,'SPY':640,'VIX':18}
        self.stocks=[Stock(s,n,p if (p:=prices.get(s,100)) else 100,v,c) for s,n,c,v in STOCKS]
        self.commodities=[Commodity(s,n,{'CL=F':65,'BZ=F':68,'GC=F':3400,'SI=F':38,'HG=F':4.5,'NG=F':3.2,'ZC=F':450,'ZW=F':520,'ZS=F':1050}.get(s,100),v,c,data_symbol=s) for s,n,c,v in COMMODITIES]
        self.indexes=[Index(s,n,p,com,v) for s,n,p,com,v in INDEXES]
        for s,n,p,com,v,data_symbol,session in GLOBAL_INDEXES:
            idx=Index(s,n,p,com,v);idx.data_symbol=data_symbol;idx.session=session;idx.category='Global Index';self.indexes.append(idx)
        self.futures=[Future('ES=F','E-mini S&P 500',6400,.001,'Futures','ES=F',50,.08,'CME'),Future('NQ=F','E-mini Nasdaq 100',23500,.002,'Futures','NQ=F',20,.08,'CME'),Future('YM=F','E-mini Dow',42000,.0012,'Futures','YM=F',5,.08,'CME'),Future('RTY=F','E-mini Russell 2000',2250,.0015,'Futures','RTY=F',50,.08,'CME')]
        self.crypto=[Crypto('BTC-USD','Bitcoin',118000,.010),Crypto('ETH-USD','Ethereum',4200,.012),Crypto('SOL-USD','Solana',180,.016),Crypto('XRP-USD','XRP',2.8,.018),Crypto('DOGE-USD','Dogecoin',.22,.022),Crypto('ADA-USD','Cardano',.85,.019),Crypto('AVAX-USD','Avalanche',34,.021),Crypto('LINK-USD','Chainlink',24,.020),Crypto('DOT-USD','Polkadot',5.0,.020),Crypto('LTC-USD','Litecoin',125,.017),Crypto('BCH-USD','Bitcoin Cash',590,.018),Crypto('XLM-USD','Stellar',.42,.020),Crypto('SUI-USD','Sui',3.7,.024),Crypto('TRX-USD','TRON',.34,.016),Crypto('HBAR-USD','Hedera',.24,.021)]
        self.forex=[Forex('EURUSD=X','EUR/USD',1.17,.0015),Forex('USDJPY=X','USD/JPY',148,.0015),Forex('GBPUSD=X','GBP/USD',1.35,.0015),Forex('AUDUSD=X','AUD/USD',.66,.0015),Forex('USDCAD=X','USD/CAD',1.38,.0014),Forex('USDCHF=X','USD/CHF',.81,.0013)]
        existing={a.symbol:a for a in self.stocks};self.international=[]
        for s,n,p,v,c,ds,session,currency in GLOBAL_STOCKS:
            if s in existing:
                a=existing[s];a.session=session;a.currency=currency;a.data_symbol=ds
            else:self.international.append(InternationalStock(s,n,p,v,c,ds,session,currency))
        self._assets={a.symbol:a for a in self.all_assets()};self.sectors=sorted({a.category for a in self.stocks+self.international})
        for a in self.all_assets():
            if a.symbol in INCEPTION_FALLBACK:
                ds,px=INCEPTION_FALLBACK[a.symbol];a.inception_date=ds;a.inception_price=px
        self._init_history();self._init_freight()
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
        now=time.monotonic();last=self._book_cache_time.get(a.symbol,0)
        if now-last>.12:
            mom=max(-1.0,min(1.0,a.change_percent()/4.0));pressure=max(-.95,min(.95,mom*.7+self.macro.get('sentiment',0)*.35))
            self.books[a.symbol].update(a.price,pressure,max(.2,a.volatility/.001));self._book_cache_time[a.symbol]=now
        return self.books[a.symbol]
    def predict(self,a):
        h=list(a.history);mom=(h[-1]/h[-20]-1) if len(h)>=20 else 0;vol=a.volatility;label='BULLISH' if mom>.01 else 'BEARISH' if mom<-.01 else 'NEUTRAL';return {'label':label,'confidence':min(.99,.5+abs(mom)*4),'momentum':mom,'volatility':vol}
    def load_chart_data(self,a,interval='1d'):return a.chart_candles(interval)
    def load_ipo_history(self,a):
        if a is None or a.symbol in self._history_loading:return False
        self._history_loading.add(a.symbol);self.data_status=f'LOADING MAX HISTORY • {a.symbol}'
        def worker():
            try:
                from data import fetch_history_max
                candles=fetch_history_max(getattr(a,'data_symbol',a.symbol))
                if candles:
                    a.set_dataset('1d',candles);a.inception_date=candles[0].timestamp.date().isoformat();a.inception_price=float(candles[0].open);self.visual_version+=1;self.data_status=f'MAX HISTORY READY • {a.symbol} • {a.inception_date}'
                else:self.data_status=f'MAX HISTORY UNAVAILABLE • {a.symbol}'
            except Exception as e:self.errors.append(f'MAX history {a.symbol}: {e}')
            finally:self._history_loading.discard(a.symbol)
        threading.Thread(target=worker,daemon=True,name=f'History-{a.symbol}').start();return True
    def submit_pending(self,side,a,qty,otype,price):
        o={'id':self.order_id,'side':side,'asset':a,'qty':int(qty),'type':otype,'price':price};self.order_id+=1;self.pending_orders.append(o);return o
    def submit_option_pending(self,side,contract,qty,otype,price):
        o={'id':self.order_id,'side':side,'contract':contract,'qty':int(qty),'type':otype,'price':price};self.order_id+=1;self.pending_option_orders.append(o);return o
    def submit_spread_pending(self,side,strategy,otype,price):
        o={'id':self.order_id,'side':side,'strategy':strategy,'type':otype,'price':price};self.order_id+=1;self.pending_spread_orders.append(o);return o
    def update_pending_price(self,order_id,price):
        for o in self.pending_orders:
            if o.get('id')==order_id:
                o['price']=max(.0001,float(price));self.visual_version+=1;return True
        return False
    def update_pending_option_strike(self,order_id,strike):
        for o in self.pending_option_orders:
            if o.get('id')==order_id and o.get('contract') is not None:
                o['contract'].strike=max(.01,round(float(strike),2));self.visual_version+=1;return True
        return False
    def _init_freight(self):
        self.freight_routes=[
            {'name':'Shanghai → Los Angeles','points':[(31.2,121.5),(28,145),(30,170),(34,-150),(34,-118)],'days':14},
            {'name':'Singapore → Rotterdam','points':[(1.3,103.8),(6,80),(12,55),(30,32),(36,15),(52,4.5)],'days':22},
            {'name':'Rotterdam → New York','points':[(52,4.5),(52,-20),(48,-45),(42,-65),(40.7,-74)],'days':10},
            {'name':'Santos → Shanghai','points':[(-23.9,-46.3),(-35,-20),(-34,18),(-20,55),(1,100),(31.2,121.5)],'days':28},
        ]
        carriers=['ZIM','MATX','SBLK','DAC','FRO','STNG'];owners=['AAPL','AMZN','WMT','TSLA','NVDA','CAT','NKE','BABA','TM','SONY']
        for i in range(10):self.shipments.append(self._new_shipment(i,random.choice(carriers),random.choice(owners)))
    def _new_shipment(self,i,carrier=None,owner=None):
        route=random.choice(self.freight_routes);carrier=carrier or random.choice(['ZIM','MATX','SBLK','DAC','FRO','STNG']);owner=owner or random.choice(['AAPL','AMZN','WMT','TSLA','NVDA','CAT','NKE','BABA','TM','SONY'])
        hazard=random.choice(['STORM','PIRATES','NONE','NONE']);hpos=random.uniform(.35,.85)
        return {'id':i,'name':f'Vessel {i+1:02d}','carrier':carrier,'cargo_owner':owner,'route':route,'progress':random.random()*.25,'hazard':hazard,'hazard_progress':hpos,'hazard_resolved':False,'cargo_value':random.randint(40,900)*1_000_000,'status':'IN TRANSIT'}
    def shipment_position(self,sh):
        pts=sh['route']['points'];p=max(0,min(.999999,sh['progress']))*(len(pts)-1);i=int(p);f=p-i;(lat1,lon1),(lat2,lon2)=pts[i],pts[min(i+1,len(pts)-1)];return lat1+(lat2-lat1)*f,lon1+(lon2-lon1)*f
    def shipment_hazard_position(self,sh):
        temp=dict(sh);temp['progress']=sh['hazard_progress'];return self.shipment_position(temp)
    def _apply_shipment_shock(self,sh,kind):
        carrier=self.get_asset(sh['carrier']);owner=self.get_asset(sh['cargo_owner'])
        severity=random.uniform(.008,.035) if kind=='STORM' else random.uniform(.012,.050)
        if carrier:carrier.update_price(carrier.price*(1-severity*.7),random.randint(10000,80000),self.clock.current)
        if owner:owner.update_price(owner.price*(1-severity),random.randint(10000,80000),self.clock.current)
        sh['status']=f'{kind} IMPACT';self.freight_events.append((self.clock.current,kind,sh['carrier'],sh['cargo_owner'],severity))
        self.news.append(NewsEvent(f'{kind.title()} disrupts {sh["name"]}: {sh["cargo_owner"]} cargo carried by {sh["carrier"]}.',sh['cargo_owner'],-severity,0,'GLOBAL'))
    def _update_freight(self,game_minutes):
        for i,sh in enumerate(list(self.shipments)):
            sh['progress']+=game_minutes/max(1,sh['route']['days']*1440)
            if sh['hazard']!='NONE' and not sh['hazard_resolved'] and sh['progress']>=sh['hazard_progress']:
                sh['hazard_resolved']=True;self._apply_shipment_shock(sh,sh['hazard'])
            if sh['progress']>=1:
                owner=self.get_asset(sh['cargo_owner']);carrier=self.get_asset(sh['carrier'])
                if owner:owner.update_price(owner.price*(1+random.uniform(.001,.006)),random.randint(5000,30000),self.clock.current)
                if carrier:carrier.update_price(carrier.price*(1+random.uniform(.001,.004)),random.randint(5000,30000),self.clock.current)
                self.shipments[i]=self._new_shipment(sh['id'])

    def _process_orders(self):
        for o in list(self.pending_orders):
            a=o['asset'];p=a.ask if o['side'] in ('BUY','COVER') else a.bid;target=o['price'];typ=o.get('type','LIMIT')
            if typ=='STOP':hit=target is None or (o['side'] in ('BUY','COVER') and p>=target) or (o['side'] in ('SELL','SHORT') and p<=target)
            else:hit=typ=='MARKET' or target is None or (o['side'] in ('BUY','COVER') and p<=target) or (o['side'] in ('SELL','SHORT') and p>=target)
            if hit:
                try:
                    fn={'BUY':self.portfolio.buy_asset,'SELL':self.portfolio.sell_asset,'SHORT':self.portfolio.short_asset,'COVER':self.portfolio.cover_short}[o['side']];fn(a,o['qty']);self.pending_orders.remove(o)
                except Exception as e:self.errors.append(f'order {o["id"]}: {e}');self.pending_orders.remove(o)
        # Working option orders use the contract premium as their limit/stop axis.
        from game_core import OptionStrategy
        for o in list(self.pending_option_orders):
            c=o.get('contract');side=o.get('side','BUY');typ=o.get('type','LIMIT');target=o.get('price');
            if c is None:continue
            mark=c.ask if side=='BUY' else c.bid
            if typ=='STOP':hit=target is None or (side=='BUY' and mark>=target) or (side=='SELL' and mark<=target)
            else:hit=typ=='MARKET' or target is None or (side=='BUY' and mark<=target) or (side=='SELL' and mark>=target)
            if hit:
                try:
                    st=OptionStrategy(f'{side} {c}');st.add_leg(c,max(1,int(o.get('qty',1))),side);ok,_=self.portfolio.execute_strategy(st)
                    if ok:self.pending_option_orders.remove(o)
                except Exception as e:
                    self.errors.append(f'option order {o.get("id")}: {e}');self.pending_option_orders.remove(o)
        for o in list(self.pending_spread_orders):
            st=o.get('strategy');side=o.get('side','BUY');typ=o.get('type','LIMIT');target=o.get('price');
            if st is None:continue
            mark=abs(st.current_value())/max(1,len(getattr(st,'legs',[])))
            hit=typ=='MARKET' or target is None or (side=='BUY' and mark<=target) or (side=='SELL' and mark>=target)
            if hit:
                try:
                    ok,_=self.portfolio.execute_strategy(st)
                    if ok:self.pending_spread_orders.remove(o)
                except Exception as e:self.errors.append(f'spread order: {e}');self.pending_spread_orders.remove(o)
    def _process_expirations(self):
        if not hasattr(self,'portfolio'):return
        now=self.clock.current
        for i in range(len(self.portfolio.options)-1,-1,-1):
            st=self.portfolio.options[i];exp=getattr(st,'expiry_at',None)
            if exp is None:continue
            remain=max(0.0,(exp-now).total_seconds()/86400.0)
            for leg in st.legs:leg.contract.days=remain;leg.contract._stats_cache=None
            if now<exp:continue
            settlement=0.0;legs=[]
            for leg in st.legs:
                c=leg.contract;spot=float(c.underlying.price);intr=float(c.intrinsic(spot));leg_cash=leg.sign*intr*leg.quantity*100;settlement+=leg_cash
                legs.append(f'{leg.action} {leg.quantity} {c.option_type.upper()} {c.strike:g}: intrinsic ${intr:.2f} -> ${leg_cash:,.2f}')
            pnl=settlement-st.open_cost;self.portfolio.cash+=settlement;self.portfolio.realized+=pnl;self.portfolio.trade_count+=1;self.portfolio.reserved_margin=max(0.0,self.portfolio.reserved_margin-max(0.0,-st.open_cost*1.5))
            self.portfolio.options.pop(i)
            if hasattr(self.portfolio,'invalidate_option_cache'):self.portfolio.invalidate_option_cache()
            self.expiration_events.append({'name':st.name,'settlement':settlement,'pnl':pnl,'underlying':st.legs[0].contract.underlying.symbol if st.legs else '—','spot':st.legs[0].contract.underlying.price if st.legs else 0,'legs':legs,'expired_at':now})
            if len(self.expiration_events)>50:self.expiration_events=self.expiration_events[-50:]

    def _update_macro(self,game_minutes):
        self._macro_accum_minutes+=game_minutes
        if self._macro_accum_minutes<60:return
        hours=self._macro_accum_minutes/60;self._macro_accum_minutes%=60
        m=self.macro
        # Slow-moving macro economy: inflation/growth/unemployment respond to rates and shocks.
        gap=m['policy_rate']-(2.5+max(0,m['inflation']-2.0)*.35)
        m['gdp_growth']+=(-.0025*gap-.018*(m['gdp_growth']-2.0)+random.gauss(0,.015))*hours
        m['unemployment']+=(.0018*max(0,2.0-m['gdp_growth'])-.012*(m['unemployment']-4.1)+random.gauss(0,.006))*hours
        m['inflation']+=(-.0018*gap+.0015*(m['gdp_growth']-2.0)-.010*(m['inflation']-2.2)+random.gauss(0,.007))*hours
        m['sentiment']=max(-1,min(1,m['sentiment']+(.002*(m['gdp_growth']-2)-.002*max(0,m['policy_rate']-4)+random.gauss(0,.012))*hours))
        m['ten_year']+=.06*((m['policy_rate']*.55+m['inflation']*.45)-m['ten_year'])*min(1,hours)+random.gauss(0,.008)*math.sqrt(max(hours,.01))
        m['dollar']+=.035*(m['policy_rate']-m['inflation']-1.5)*hours+random.gauss(0,.06)*math.sqrt(max(hours,.01))
        m['liquidity']=max(.4,min(1.6,1.15-.06*m['policy_rate']+.05*m['sentiment']))
        # Monthly-ish Fed reaction function. It moves in 25bp steps toward a Taylor-style target.
        days=(self.clock.current.date()-self._last_fed_day).days
        if days>=30:
            target=max(.0,min(10.0,2.5+1.35*(m['inflation']-m['fed_target'])+.35*(m['gdp_growth']-2.0)-.20*(m['unemployment']-4.1)))
            old=m['policy_rate']
            if target>old+.125:m['policy_rate']=min(old+.25,target)
            elif target<old-.125:m['policy_rate']=max(old-.25,target)
            self._last_fed_day=self.clock.current.date()
            direction='raises' if m['policy_rate']>old else 'cuts' if m['policy_rate']<old else 'holds'
            self.news.append(NewsEvent(f'Federal Reserve {direction} policy rate at {m["policy_rate"]:.2f}% as inflation runs {m["inflation"]:.2f}%.',None,(-.006 if direction=='raises' else .006 if direction=='cuts' else 0),0,'MACRO'))
    def _asset_return(self,a,game_minutes,market_z,sector_z):
        m=self.macro;dt=max(game_minutes,1e-6)
        # Volatility inputs in this project are roughly short-horizon values; scale them by simulated time.
        sigma=a.volatility*math.sqrt(dt/5.0)
        cat=getattr(a,'category','')
        rate_drag=max(0,m['policy_rate']-3.0)*.000012
        growth_push=(m['gdp_growth']-2.0)*.000010
        inflation_drag=max(0,m['inflation']-2.5)*.000008
        drift=(growth_push-rate_drag-inflation_drag+m['sentiment']*.000012)*dt
        beta=1.0
        if cat in ('Tech','Consumer','Media'):beta=1.18
        elif cat in ('Health','Consumer Staples'):beta=.72
        elif cat=='Finance':beta=1.05;drift+=(m['policy_rate']-2.5)*.000004*dt
        elif cat=='Energy':beta=.85;drift+=(m['inflation']-2.0)*.000008*dt
        if isinstance(a,Crypto):beta=1.65;drift+=m['sentiment']*.000025*dt
        if isinstance(a,Forex):beta=.35
        if isinstance(a,Commodity):beta=.55
        z=.62*beta*market_z+.42*sector_z+.58*random.gauss(0,1)
        # Momentum/value-like investor behavior adds modest persistent flow rather than pure random walk.
        h=list(a.history);mom=(h[-1]/h[-10]-1) if len(h)>=10 and h[-10] else 0
        flow=max(-.00008,min(.00008,mom*.015))*dt
        return drift+flow+sigma*z
    def set_research_seed(self,seed):self.seed=int(seed);random.seed(self.seed);return self.seed
    def macro_snapshot(self):return dict(self.macro,time=self.clock.time,source=self.real_macro_source,seed=self.seed)
    def correlation(self,a,b):
        if a is None or b is None:return 0.0
        if a.symbol==b.symbol:return 1.0
        ca,cb=getattr(a,'category',''),getattr(b,'category','')
        corr=.28
        if ca and ca==cb:corr=.72
        if isinstance(a,Index) or isinstance(b,Index):corr=max(corr,.68)
        if isinstance(a,Crypto) and isinstance(b,Crypto):corr=.82
        if isinstance(a,Forex) and isinstance(b,Forex):corr=.48
        pairs={frozenset(('CL=F','BZ=F')):.90,frozenset(('GC=F','SI=F')):.72,frozenset(('SPY','ES=F')):.94,frozenset(('BTC-USD','MSTR')):.78,frozenset(('BTC-USD','COIN')):.72,frozenset(('NVDA','AMD')):.78,frozenset(('GOOG','GOOGL')):.99}
        return pairs.get(frozenset((a.symbol,b.symbol)),corr)
    def correlated_assets(self,a,limit=10):
        arr=[(self.correlation(a,b),b) for b in self.all_assets() if b is not a]
        arr.sort(key=lambda x:abs(x[0]),reverse=True);return arr[:max(1,int(limit))]
    async def tick(self):
        if not self.running:return
        if self.paused:
            self._last_real_tick=time.monotonic();await asyncio.sleep(.03);return
        now=time.monotonic();real_dt=max(.001,min(.20,now-self._last_real_tick));self._last_real_tick=now
        game_seconds=real_dt*60.0*max(.05,float(getattr(self,'time_warp',1.0)));game_minutes=game_seconds/60.0
        try:
            self.clock.advance_seconds(game_seconds);self._update_macro(game_minutes)
            with self._lock:
                market_z=random.gauss(0,1);sector_cache={}
                index_symbols={x.symbol for x in self.indexes}
                for a in self.all_assets():
                    if a.symbol in index_symbols:continue
                    cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1))
                    r=self._asset_return(a,game_minutes,market_z,sector_z);a.update_price(a.price*max(.75,1+r),random.randint(100,50000),self.clock.current)
                for idx in self.indexes:
                    comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
                    if comps:
                        weighted=sum((c.price/max(.0001,c.previous_price)-1) for c in comps)/len(comps)
                        idx.update_price(idx.price*max(.85,1+weighted+random.gauss(0,idx.volatility*.10*math.sqrt(max(game_minutes,.001)))),random.randint(1000,100000),self.clock.current)
                event_prob=min(.08,.00018*game_minutes)
                if random.random()<event_prob:self.news.append(generate_news(self.stocks,self.commodities))
                if random.random()<event_prob*.03:self.news.append(major())
                self._update_freight(game_minutes);self._update_geopolitics(game_minutes);self._process_orders();self._process_expirations()
                if hasattr(self,'portfolio') and time.monotonic()-getattr(self,'_last_networth_calc',0)>2.0:
                    self._last_networth_calc=time.monotonic();self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
            self.visual_version+=1;self.data_status=f'SIMULATION RUNNING • {self.time_warp:.2f}x • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
        except Exception as e:
            self.errors.append(f'tick: {type(e).__name__}: {e}')
            if len(self.errors)>100:self.errors=self.errors[-100:]
        await asyncio.sleep(max(.005,float(self.speed)))
    def start_background_loaders(self):
        if self._loader_started:return
        self._loader_started=True;threading.Thread(target=self._background_loader,daemon=True,name='MarketDataLoader').start()
    def _background_loader(self):
        self.data_status='SIMULATION + OPTIONAL LIVE DATA'
        try:
            from data import fetch_many_latest,fetch_fred_macro_snapshot
            assets=self.all_assets();latest=fetch_many_latest([a.data_symbol for a in assets],workers=8)
            for a in assets:
                c=latest.get(a.data_symbol)
                if c:a.last_real_close=float(c.close);a.last_real_timestamp=c.timestamp;a.update_price(float(c.close),int(c.volume),self.clock.current,record=True)
            snap=fetch_fred_macro_snapshot()
            if snap:
                self.macro.update({k:v for k,v in snap.items() if k in self.macro});self.real_macro_source='FRED';self.data_status='SIMULATION CALIBRATED TO FRED + MARKET QUOTES'
        except Exception as e:self.errors.append(f'background data: {e}')

# ===== Stock Game Pro 1.0 production geopolitical / event-radar patches =====
_Market_init_before_prod=Market.__init__
def _sgp_market_init(self):
    _Market_init_before_prod(self)
    self._last_networth_calc=0.0
    self.geopolitical_events=[]
    self._geo_seq=1
    self._geo_accum=0.0
    self._spawn_geopolitical_event(initial=True)
Market.__init__=_sgp_market_init

def _sgp_spawn_geo(self,initial=False):
    templates=[
        ('MARITIME TENSION',24.5,57.0,['Energy','Freight'],['XOM','CVX','SHEL','BP','ZIM','FRO','STNG']),
        ('REGIONAL CONFLICT RISK',34.5,36.0,['Industrial','Energy'],['BA','GE','PLTR','XOM','GC=F']),
        ('TRADE ROUTE DISRUPTION',12.0,45.0,['Freight','Consumer'],['ZIM','MATX','SBLK','AMZN','WMT']),
        ('PACIFIC SECURITY ALERT',22.0,121.0,['Tech','Industrial'],['TSM','NVDA','AAPL','SONY','TM']),
    ]
    name,lat,lon,sectors,symbols=random.choice(templates)
    lead=random.uniform(180,900) if not initial else random.uniform(90,360)
    ev={'id':self._geo_seq,'name':name,'lat':lat+random.uniform(-4,4),'lon':lon+random.uniform(-5,5),'sectors':sectors,'symbols':symbols,'minutes_to_event':lead,'initial_minutes':lead,'severity':random.uniform(.006,.028),'resolved':False,'status':'WATCH'}
    self._geo_seq+=1;self.geopolitical_events.append(ev);self.geopolitical_events=self.geopolitical_events[-8:]
    self.news.append(NewsEvent(f'GLOBAL RISK WATCH: {name} developing. Markets are monitoring possible disruption.',None,0,0,'GLOBAL'))
    return ev
Market._spawn_geopolitical_event=_sgp_spawn_geo

def _sgp_update_geo(self,game_minutes):
    self._geo_accum+=game_minutes
    for ev in list(self.geopolitical_events):
        if ev.get('resolved'):continue
        ev['minutes_to_event']-=game_minutes
        if ev['minutes_to_event']<=60 and ev.get('status')=='WATCH':
            ev['status']='ELEVATED';self.news.append(NewsEvent(f'RISK ELEVATED: {ev["name"]} may affect {", ".join(ev["sectors"])} markets.',None,0,0,'GLOBAL'))
        if ev['minutes_to_event']<=0:
            ev['resolved']=True;ev['status']='IMPACT'
            sev=ev['severity'];self.macro['sentiment']=max(-1,self.macro.get('sentiment',0)-sev*5)
            for sym in ev['symbols']:
                a=self.get_asset(sym)
                if not a:continue
                # Defense/industrial proxies can benefit from conflict spending while
                # exposed cargo/consumer/tech names generally take risk-off pressure.
                beneficial=a.category in ('Industrial',) and sym in ('BA','GE','PLTR')
                shock=sev*(.45 if beneficial else -1.0)
                a.update_price(a.price*(1+shock),random.randint(10000,120000),self.clock.current)
            oil=self.get_asset('CL=F');gold=self.get_asset('GC=F')
            if oil:oil.update_price(oil.price*(1+sev*.7),random.randint(10000,100000),self.clock.current)
            if gold:gold.update_price(gold.price*(1+sev*.45),random.randint(10000,100000),self.clock.current)
            self.news.append(NewsEvent(f'GLOBAL EVENT: {ev["name"]} materializes; cross-asset risk repricing underway.',None,-sev,sev*.08,'MAJOR'))
    if self._geo_accum>=720:
        self._geo_accum%=720
        if len([x for x in self.geopolitical_events if not x.get('resolved')])<3 and random.random()<.55:self._spawn_geopolitical_event()
Market._update_geopolitics=_sgp_update_geo

# ===== Stock Game Pro 1.1 market-session / logistics production patch =====
_Market_init_v11_base = Market.__init__
def _sgp_v11_market_init(self):
    _Market_init_v11_base(self)
    self._session_open_state = {}
    self._pending_gap_returns = {}
    # Futures-style commodities trade on the simulator's CME clock unless explicitly overridden.
    for a in self.commodities:
        a.session = getattr(a, 'session', 'CME') or 'CME'
    for a in self.stocks:
        if not hasattr(a, 'session'): a.session = 'US'
    for a in self.indexes:
        if not hasattr(a, 'session'): a.session = 'US'
    self.ports = [
        {'name':'Los Angeles / Long Beach','lat':33.74,'lon':-118.25,'operator':'MATX','region':'US West'},
        {'name':'New York / New Jersey','lat':40.67,'lon':-74.05,'operator':'AMKBY','region':'US East'},
        {'name':'Rotterdam','lat':51.95,'lon':4.14,'operator':'DPW.DU','region':'Europe'},
        {'name':'Jebel Ali / Dubai','lat':25.01,'lon':55.06,'operator':'DPW.DU','region':'Middle East'},
        {'name':'Shanghai Yangshan','lat':30.62,'lon':122.06,'operator':'1199.HK','region':'China'},
        {'name':'Hong Kong','lat':22.31,'lon':114.16,'operator':'0144.HK','region':'China'},
        {'name':'Singapore','lat':1.26,'lon':103.84,'operator':'AMKBY','region':'Asia'},
        {'name':'Tokyo / Yokohama','lat':35.45,'lon':139.66,'operator':'TM','region':'Japan'},
    ]
    # Attach port metadata to routes so the globe can expose investable transport chains.
    route_ports=[('Shanghai Yangshan','Los Angeles / Long Beach'),('Singapore','Rotterdam'),('Rotterdam','New York / New Jersey'),('Los Angeles / Long Beach','Tokyo / Yokohama')]
    for i,r in enumerate(self.freight_routes):
        op,dp=route_ports[i % len(route_ports)];r['origin_port']=op;r['destination_port']=dp
    self.air_routes=[
        {'name':'Los Angeles → Tokyo','points':[(34.05,-118.25),(38,-150),(40,170),(35.7,139.7)],'hours':11,'origin':'Los Angeles / Long Beach','destination':'Tokyo / Yokohama'},
        {'name':'New York → Rotterdam','points':[(40.7,-74),(48,-45),(52,4.5)],'hours':8,'origin':'New York / New Jersey','destination':'Rotterdam'},
        {'name':'Dubai → Singapore','points':[(25.2,55.3),(18,72),(8,90),(1.3,103.8)],'hours':7,'origin':'Jebel Ali / Dubai','destination':'Singapore'},
    ]
    self.air_shipments=[]
    carriers=['FDX','UPS','CPA'];owners=['AAPL','NVDA','AMZN','NKE','TSLA','BABA','SONY']
    for i in range(7):
        route=random.choice(self.air_routes)
        self.air_shipments.append({'id':i,'name':f'Cargo Flight {i+1:02d}','carrier':random.choice(carriers),'cargo_owner':random.choice(owners),'route':route,'progress':random.random(),'cargo_value':random.randint(15,240)*1_000_000,'status':'AIRBORNE'})
Market.__init__ = _sgp_v11_market_init

def _sgp_asset_session(self,a):
    if isinstance(a,Crypto): return 'CRYPTO'
    if isinstance(a,Forex): return 'FX'
    if isinstance(a,(Future,Commodity)): return getattr(a,'session','CME') or 'CME'
    return getattr(a,'session','US') or 'US'
Market.asset_session = _sgp_asset_session

def _sgp_asset_market_open(self,a):
    try:return bool(market_status(self.asset_session(a), self.clock.current))
    except Exception:return True
Market.asset_market_open = _sgp_asset_market_open

def _sgp_queue_or_apply_return(self,a,r,volume=None):
    if a is None:return
    if self.asset_market_open(a):
        a.update_price(a.price*max(.05,1+float(r)), volume or random.randint(5000,100000), self.clock.current)
    else:
        self._pending_gap_returns[a.symbol]=self._pending_gap_returns.get(a.symbol,0.0)+float(r)
Market.queue_or_apply_return = _sgp_queue_or_apply_return

def _sgp_apply_open_gap(self,a):
    r=self._pending_gap_returns.pop(a.symbol,0.0)
    if r:
        a.update_price(a.price*max(.05,1+r),random.randint(10000,120000),self.clock.current)
        self.news.append(NewsEvent(f'{a.symbol} opens with a {r*100:+.2f}% event gap after its local market reopened.',a.symbol,r,0,'MARKET'))
Market._apply_open_gap = _sgp_apply_open_gap

# Preserve the freight mechanics but make closed-market shocks queue for the next local open.
_old_ship_shock_v11 = Market._apply_shipment_shock
def _sgp_ship_shock_v11(self,sh,kind):
    carrier=self.get_asset(sh['carrier']);owner=self.get_asset(sh['cargo_owner'])
    severity=random.uniform(.008,.035) if kind=='STORM' else random.uniform(.012,.050)
    self.queue_or_apply_return(carrier,-severity*.7)
    self.queue_or_apply_return(owner,-severity)
    self.macro['sentiment']=max(-1,self.macro.get('sentiment',0)-severity*2)
    self.news.append(NewsEvent(f'{kind}: {sh["name"]} carrying {sh["cargo_owner"]} cargo is disrupted; {sh["carrier"]} logistics risk rises.',sh['cargo_owner'],-severity,0,'GLOBAL'))
Market._apply_shipment_shock = _sgp_ship_shock_v11

_old_update_freight_v11 = Market._update_freight
def _sgp_update_transport_v11(self,game_minutes):
    _old_update_freight_v11(self,game_minutes)
    # Air cargo moves materially faster than ships. It is visual/gameplay state and
    # intentionally cheap to update.
    for fl in self.air_shipments:
        hours=max(1,float(fl['route'].get('hours',8)));fl['progress'] += game_minutes/(hours*60.0)
        if fl['progress']>=1:
            carrier=self.get_asset(fl['carrier']);owner=self.get_asset(fl['cargo_owner'])
            self.queue_or_apply_return(carrier,random.uniform(.0002,.0012));self.queue_or_apply_return(owner,random.uniform(.0001,.0007))
            fl['route']=random.choice(self.air_routes);fl['progress']=0.0;fl['cargo_owner']=random.choice(['AAPL','NVDA','AMZN','NKE','TSLA','BABA','SONY']);fl['cargo_value']=random.randint(15,240)*1_000_000
Market._update_freight = _sgp_update_transport_v11

def _sgp_air_position(self,fl):
    pts=fl['route']['points'];p=max(0,min(.999999,fl['progress']))*(len(pts)-1);i=int(p);f=p-i;(lat1,lon1),(lat2,lon2)=pts[i],pts[min(i+1,len(pts)-1)];return lat1+(lat2-lat1)*f,lon1+(lon2-lon1)*f
Market.air_shipment_position = _sgp_air_position

# Session-aware order processing: working stock/options orders wait for the underlying's local market.
def _sgp_process_orders_v11(self):
    for o in list(self.pending_orders):
        a=o['asset']
        if not self.asset_market_open(a):continue
        p=a.ask if o['side'] in ('BUY','COVER') else a.bid;target=o['price'];typ=o.get('type','LIMIT')
        if typ=='STOP':hit=target is None or (o['side'] in ('BUY','COVER') and p>=target) or (o['side'] in ('SELL','SHORT') and p<=target)
        else:hit=typ=='MARKET' or target is None or (o['side'] in ('BUY','COVER') and p<=target) or (o['side'] in ('SELL','SHORT') and p>=target)
        if hit:
            try:
                fn={'BUY':self.portfolio.buy_asset,'SELL':self.portfolio.sell_asset,'SHORT':self.portfolio.short_asset,'COVER':self.portfolio.cover_short}[o['side']];fn(a,o['qty']);self.pending_orders.remove(o)
            except Exception as e:self.errors.append(f'order {o["id"]}: {e}');self.pending_orders.remove(o)
    from game_core import OptionStrategy
    for o in list(self.pending_option_orders):
        c=o.get('contract');side=o.get('side','BUY');typ=o.get('type','LIMIT');target=o.get('price')
        if c is None or not self.asset_market_open(c.underlying):continue
        mark=c.ask if side=='BUY' else c.bid
        if typ=='STOP':hit=target is None or (side=='BUY' and mark>=target) or (side=='SELL' and mark<=target)
        else:hit=typ=='MARKET' or target is None or (side=='BUY' and mark<=target) or (side=='SELL' and mark>=target)
        if hit:
            try:
                st=OptionStrategy(f'{side} {c}');st.add_leg(c,max(1,int(o.get('qty',1))),side);ok,_=self.portfolio.execute_strategy(st)
                if ok:self.pending_option_orders.remove(o)
            except Exception as e:self.errors.append(f'option order {o.get("id")}: {e}');self.pending_option_orders.remove(o)
    for o in list(self.pending_spread_orders):
        st=o.get('strategy');side=o.get('side','BUY');typ=o.get('type','LIMIT');target=o.get('price')
        if st is None:continue
        under=st.legs[0].contract.underlying if getattr(st,'legs',None) else None
        if under is not None and not self.asset_market_open(under):continue
        mark=abs(st.current_value())/max(1,len(getattr(st,'legs',[])));hit=typ=='MARKET' or target is None or (side=='BUY' and mark<=target) or (side=='SELL' and mark>=target)
        if hit:
            try:
                ok,_=self.portfolio.execute_strategy(st)
                if ok:self.pending_spread_orders.remove(o)
            except Exception as e:self.errors.append(f'spread order: {e}');self.pending_spread_orders.remove(o)
Market._process_orders = _sgp_process_orders_v11

# Session-aware engine. Prices freeze outside each instrument's correlated exchange,
# while macro/logistics/geopolitics continue to evolve and can queue an opening gap.
async def _sgp_tick_v11(self):
    if not self.running:return
    if self.paused:
        self._last_real_tick=time.monotonic();await asyncio.sleep(.03);return
    now=time.monotonic();real_dt=max(.001,min(.20,now-self._last_real_tick));self._last_real_tick=now
    game_seconds=real_dt*60.0*max(.05,float(getattr(self,'time_warp',1.0)));game_minutes=game_seconds/60.0
    try:
        self.clock.advance_seconds(game_seconds);self._update_macro(game_minutes)
        with self._lock:
            market_z=random.gauss(0,1);sector_cache={};index_symbols={x.symbol for x in self.indexes};opened_any=False
            for a in self.all_assets():
                session=self.asset_session(a);is_open=self.asset_market_open(a);prev=self._session_open_state.get(a.symbol,is_open);self._session_open_state[a.symbol]=is_open
                if is_open and not prev:
                    self._apply_open_gap(a);opened_any=True
                if a.symbol in index_symbols or not is_open:continue
                cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,game_minutes,market_z,sector_z);a.update_price(a.price*max(.75,1+r),random.randint(100,50000),self.clock.current)
            for idx in self.indexes:
                if not self.asset_market_open(idx):continue
                comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
                if comps:
                    weighted=sum((c.price/max(.0001,c.previous_price)-1) for c in comps)/len(comps);idx.update_price(idx.price*max(.85,1+weighted+random.gauss(0,idx.volatility*.10*math.sqrt(max(game_minutes,.001)))),random.randint(1000,100000),self.clock.current)
            event_prob=min(.08,.00018*game_minutes)
            if random.random()<event_prob:self.news.append(generate_news(self.stocks,self.commodities))
            if random.random()<event_prob*.03:self.news.append(major())
            self._update_freight(game_minutes);self._update_geopolitics(game_minutes);self._process_orders();self._process_expirations()
            if hasattr(self,'portfolio') and time.monotonic()-getattr(self,'_last_networth_calc',0)>2.0:
                self._last_networth_calc=time.monotonic();self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
        self.visual_version+=1
        if opened_any:self.visual_version+=1
        self.data_status=f'SESSION-AWARE SIM • {self.time_warp:.2f}x • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
    except Exception as e:
        self.errors.append(f'tick: {type(e).__name__}: {e}')
        if len(self.errors)>100:self.errors=self.errors[-100:]
    await asyncio.sleep(max(.005,float(self.speed)))
Market.tick = _sgp_tick_v11

# Session-aware geopolitical impacts: closed securities gap when their market reopens.
def _sgp_update_geo_v11(self,game_minutes):
    self._geo_accum+=game_minutes
    for ev in list(self.geopolitical_events):
        if ev.get('resolved'):continue
        ev['minutes_to_event']-=game_minutes
        if ev['minutes_to_event']<=60 and ev.get('status')=='WATCH':
            ev['status']='ELEVATED';self.news.append(NewsEvent(f'RISK ELEVATED: {ev["name"]} may affect {", ".join(ev["sectors"])} markets.',None,0,0,'GLOBAL'))
        if ev['minutes_to_event']<=0:
            ev['resolved']=True;ev['status']='IMPACT';sev=ev['severity'];self.macro['sentiment']=max(-1,self.macro.get('sentiment',0)-sev*5)
            for sym in ev['symbols']:
                a=self.get_asset(sym)
                if not a:continue
                beneficial=a.category in ('Industrial',) and sym in ('BA','GE','PLTR');shock=sev*(.45 if beneficial else -1.0);self.queue_or_apply_return(a,shock)
            self.queue_or_apply_return(self.get_asset('CL=F'),sev*.7);self.queue_or_apply_return(self.get_asset('GC=F'),sev*.45)
            self.news.append(NewsEvent(f'GLOBAL EVENT: {ev["name"]} materializes; cross-asset risk repricing underway.',None,-sev,sev*.08,'MAJOR'))
    if self._geo_accum>=720:
        self._geo_accum%=720
        if len([x for x in self.geopolitical_events if not x.get('resolved')])<3 and random.random()<.55:self._spawn_geopolitical_event()
Market._update_geopolitics=_sgp_update_geo_v11

# ===== Stock Game Pro 1.2 extended-hours / skip-to-open patch =====
# Regular exchange state remains authoritative for order execution.  US equities
# receive a lower-volatility extended-hours quote stream from 04:00-20:00 ET so
# the 1D chart can show pre/post-market activity into the following session.
def _sgp_v12_regular_open(self,a):
    try:return bool(market_status(self.asset_session(a), self.clock.current))
    except Exception:return True
Market.asset_regular_open = _sgp_v12_regular_open

def _sgp_v12_quote_open(self,a):
    code=self.asset_session(a)
    if code=='US' and isinstance(a,(Stock,InternationalStock)):
        try:return bool(market_status('EXT',self.clock.current))
        except Exception:return self.asset_regular_open(a)
    return self.asset_regular_open(a)
Market.asset_quote_open = _sgp_v12_quote_open

def _sgp_v12_next_open(self,a=None):
    """Return the next regular-session open in the game's New York-naive clock."""
    code=self.asset_session(a) if a is not None else 'US'
    if code in ('CRYPTO',):return self.clock.current
    from zoneinfo import ZoneInfo
    sess=SESSIONS.get(code,SESSIONS['US'])
    game=self.clock.current
    aware=game.replace(tzinfo=ZoneInfo('America/New_York')) if game.tzinfo is None else game
    local=aware.astimezone(ZoneInfo(sess.tz))
    # FX is effectively a weekday session; choose next minute if already open.
    if code=='FX' and market_status(code,game):return game
    probe=local
    for _ in range(10):
        target=probe.replace(hour=sess.open_time.hour,minute=sess.open_time.minute,second=sess.open_time.second,microsecond=0)
        if probe.weekday() in sess.weekdays and target>probe:break
        probe=(probe+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    # CME opens 17:00 CT Sunday-Thursday; Session helper already expresses 17:00.
    target=target.astimezone(ZoneInfo('America/New_York')).replace(tzinfo=None)
    return target
Market.next_regular_open = _sgp_v12_next_open

def _sgp_v12_skip_to_next_open(self,a=None):
    target=self.next_regular_open(a)
    now=self.clock.current
    if target<=now:return 0.0
    minutes=(target-now).total_seconds()/60.0
    # Advance slow world-state once, rather than iterating thousands of engine ticks.
    try:self._update_macro(minutes)
    except Exception:pass
    try:self._update_freight(minutes)
    except Exception:pass
    try:self._update_geopolitics(minutes)
    except Exception:pass
    self.clock.current=target
    self._last_real_tick=time.monotonic()
    try:self._process_expirations()
    except Exception:pass
    self.visual_version+=1
    self.data_status=f'SKIPPED TO {_sgp_asset_session(self,a) if False else self.asset_session(a) if a else "US"} OPEN • {self.clock.time}'
    return minutes
Market.skip_to_next_open = _sgp_v12_skip_to_next_open

async def _sgp_tick_v12(self):
    if not self.running:return
    if self.paused:
        self._last_real_tick=time.monotonic();await asyncio.sleep(.03);return
    now=time.monotonic();real_dt=max(.001,min(.20,now-self._last_real_tick));self._last_real_tick=now
    game_seconds=real_dt*60.0*max(.05,float(getattr(self,'time_warp',1.0)));game_minutes=game_seconds/60.0
    try:
        self.clock.advance_seconds(game_seconds);self._update_macro(game_minutes)
        with self._lock:
            market_z=random.gauss(0,1);sector_cache={};index_symbols={x.symbol for x in self.indexes};opened_any=False
            for a in self.all_assets():
                regular=self.asset_regular_open(a);prev=self._session_open_state.get(a.symbol,regular);self._session_open_state[a.symbol]=regular
                if regular and not prev:self._apply_open_gap(a);opened_any=True
                if a.symbol in index_symbols or not self.asset_quote_open(a):continue
                cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,game_minutes,market_z,sector_z)
                # US pre/post-market is intentionally thinner and less volatile than regular hours.
                if self.asset_session(a)=='US' and not regular:r*=.34
                a.update_price(a.price*max(.75,1+r),random.randint(30,15000) if not regular else random.randint(100,50000),self.clock.current)
            for idx in self.indexes:
                if not self.asset_regular_open(idx):continue
                comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
                if comps:
                    weighted=sum((c.price/max(.0001,c.previous_price)-1) for c in comps)/len(comps);idx.update_price(idx.price*max(.85,1+weighted+random.gauss(0,idx.volatility*.10*math.sqrt(max(game_minutes,.001)))),random.randint(1000,100000),self.clock.current)
            event_prob=min(.08,.00018*game_minutes)
            if random.random()<event_prob:self.news.append(generate_news(self.stocks,self.commodities))
            if random.random()<event_prob*.03:self.news.append(major())
            self._update_freight(game_minutes);self._update_geopolitics(game_minutes);self._process_orders();self._process_expirations()
            if hasattr(self,'portfolio') and time.monotonic()-getattr(self,'_last_networth_calc',0)>2.0:
                self._last_networth_calc=time.monotonic();self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
        self.visual_version+=1+(1 if opened_any else 0)
        self.data_status=f'EXTENDED-HOURS SIM • {self.time_warp:.2f}x • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
    except Exception as e:
        self.errors.append(f'tick: {type(e).__name__}: {e}')
        if len(self.errors)>100:self.errors=self.errors[-100:]
    await asyncio.sleep(max(.005,float(self.speed)))
Market.tick=_sgp_tick_v12

# ===== Stock Game Pro 1.3 global sessions / overnight ECN / history patch =====
def _sgp_v13_trade_state(self,a):
    """Human-readable execution state.

    Listed equities use their local exchange as the regular session and a simulated
    global ECN outside that session on weekdays. Listed options remain local-session only.
    Futures/FX/crypto keep their native session behavior.
    """
    code=self.asset_session(a)
    if code=='CRYPTO':return '24/7'
    if isinstance(a,Forex):
        return 'REGULAR' if self.asset_regular_open(a) else 'CLOSED'
    if isinstance(a,(Future,Commodity)):
        return 'REGULAR' if self.asset_regular_open(a) else 'CLOSED'
    if isinstance(a,(Stock,InternationalStock)):
        if self.asset_regular_open(a):return 'REGULAR'
        # Global stock ECN: 24x5 in the simulator, with a short 20:00 ET maintenance pause.
        dt=self.clock.current
        if dt.weekday()<5:
            minute=dt.hour*60+dt.minute
            if not (20*60 <= minute < 20*60+15):return 'OVERNIGHT ECN'
        return 'CLOSED'
    return 'REGULAR' if self.asset_regular_open(a) else 'CLOSED'
Market.asset_trade_state=_sgp_v13_trade_state

def _sgp_v13_stock_allowed(self,a):
    if isinstance(a,(Stock,InternationalStock)):return self.asset_trade_state(a) in ('REGULAR','OVERNIGHT ECN')
    return self.asset_regular_open(a)
Market.stock_trading_allowed=_sgp_v13_stock_allowed

def _sgp_v13_quote_open(self,a):
    if isinstance(a,(Stock,InternationalStock)):return self.stock_trading_allowed(a)
    return self.asset_regular_open(a)
Market.asset_quote_open=_sgp_v13_quote_open

# Stock working orders can execute on the global stock ECN; listed options wait for
# the underlying's regular local exchange session.
def _sgp_process_orders_v13(self):
    for o in list(self.pending_orders):
        a=o['asset']
        if not self.stock_trading_allowed(a):continue
        p=a.ask if o['side'] in ('BUY','COVER') else a.bid;target=o['price'];typ=o.get('type','LIMIT')
        if typ=='STOP':hit=target is None or (o['side'] in ('BUY','COVER') and p>=target) or (o['side'] in ('SELL','SHORT') and p<=target)
        else:hit=typ=='MARKET' or target is None or (o['side'] in ('BUY','COVER') and p<=target) or (o['side'] in ('SELL','SHORT') and p>=target)
        if hit:
            try:
                fn={'BUY':self.portfolio.buy_asset,'SELL':self.portfolio.sell_asset,'SHORT':self.portfolio.short_asset,'COVER':self.portfolio.cover_short}[o['side']]
                ok,_=fn(a,o['qty'])
                if ok:self.pending_orders.remove(o)
            except Exception as e:self.errors.append(f'order {o.get("id")}: {e}');self.pending_orders.remove(o)
    from game_core import OptionStrategy
    for o in list(self.pending_option_orders):
        c=o.get('contract');side=o.get('side','BUY');typ=o.get('type','LIMIT');target=o.get('price')
        if c is None or not self.asset_regular_open(c.underlying):continue
        mark=c.ask if side=='BUY' else c.bid
        if typ=='STOP':hit=target is None or (side=='BUY' and mark>=target) or (side=='SELL' and mark<=target)
        else:hit=typ=='MARKET' or target is None or (side=='BUY' and mark<=target) or (side=='SELL' and mark>=target)
        if hit:
            try:
                st=OptionStrategy(f'{side} {c}');st.add_leg(c,max(1,int(o.get('qty',1))),side);ok,_=self.portfolio.execute_strategy(st)
                if ok and o in self.pending_option_orders:self.pending_option_orders.remove(o)
            except Exception as e:self.errors.append(f'option order {o.get("id")}: {e}');self.pending_option_orders.remove(o)
    for o in list(self.pending_spread_orders):
        st=o.get('strategy');under=st.legs[0].contract.underlying if st is not None and getattr(st,'legs',None) else None
        if st is None or (under is not None and not self.asset_regular_open(under)):continue
        side=o.get('side','BUY');typ=o.get('type','LIMIT');target=o.get('price');mark=abs(st.current_value())/max(1,len(getattr(st,'legs',[])))
        hit=typ=='MARKET' or target is None or (side=='BUY' and mark<=target) or (side=='SELL' and mark>=target)
        if hit:
            try:
                ok,_=self.portfolio.execute_strategy(st)
                if ok and o in self.pending_spread_orders:self.pending_spread_orders.remove(o)
            except Exception as e:self.errors.append(f'spread order: {e}');self.pending_spread_orders.remove(o)
Market._process_orders=_sgp_process_orders_v13

# Price engine: regular local sessions get full liquidity; global-stock ECN gets a
# thinner overnight quote stream. International stocks therefore retain their local
# open/close semantics but are still tradable during US hours through the ECN layer.
_tick_v13_base=Market.tick
async def _sgp_tick_v13(self):
    if not self.running:return
    if self.paused:
        self._last_real_tick=time.monotonic();await asyncio.sleep(.03);return
    now=time.monotonic();real_dt=max(.001,min(.20,now-self._last_real_tick));self._last_real_tick=now
    game_seconds=real_dt*60.0*max(.05,float(getattr(self,'time_warp',1.0)));game_minutes=game_seconds/60.0
    try:
        self.clock.advance_seconds(game_seconds);self._update_macro(game_minutes)
        with self._lock:
            market_z=random.gauss(0,1);sector_cache={};index_symbols={x.symbol for x in self.indexes};opened_any=False
            for a in self.all_assets():
                regular=self.asset_regular_open(a);prev=self._session_open_state.get(a.symbol,regular);self._session_open_state[a.symbol]=regular
                if regular and not prev:self._apply_open_gap(a);opened_any=True
                if a.symbol in index_symbols or not self.asset_quote_open(a):continue
                cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,game_minutes,market_z,sector_z)
                state=self.asset_trade_state(a)
                if state=='OVERNIGHT ECN':r*=.28;vol=random.randint(10,7000)
                else:vol=random.randint(100,50000)
                a.update_price(a.price*max(.75,1+r),vol,self.clock.current)
            for idx in self.indexes:
                # Index cash levels only update during their own local cash session.
                if not self.asset_regular_open(idx):continue
                comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
                if comps:
                    weighted=sum((c.price/max(.0001,c.previous_price)-1) for c in comps)/len(comps);idx.update_price(idx.price*max(.85,1+weighted+random.gauss(0,idx.volatility*.10*math.sqrt(max(game_minutes,.001)))),random.randint(1000,100000),self.clock.current)
            event_prob=min(.08,.00018*game_minutes)
            if random.random()<event_prob:self.news.append(generate_news(self.stocks,self.commodities))
            if random.random()<event_prob*.03:self.news.append(major())
            self._update_freight(game_minutes);self._update_geopolitics(game_minutes);self._process_orders();self._process_expirations()
            if hasattr(self,'portfolio') and time.monotonic()-getattr(self,'_last_networth_calc',0)>2.0:
                self._last_networth_calc=time.monotonic();self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
        self.visual_version+=1+(1 if opened_any else 0)
        self.data_status=f'GLOBAL SESSION + ECN • {self.time_warp:.2f}x • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
    except Exception as e:
        self.errors.append(f'tick: {type(e).__name__}: {e}')
        if len(self.errors)>100:self.errors=self.errors[-100:]
    await asyncio.sleep(max(.008,float(self.speed)))
Market.tick=_sgp_tick_v13

# More realistic listed port operators for the logistics view.
_Market_init_v13_base=Market.__init__
def _sgp_market_init_v13(self):
    _Market_init_v13_base(self)
    by_name={p['name']:p for p in getattr(self,'ports',[])}
    upgrades={
      'Rotterdam':'HHFA.DE','Jebel Ali / Dubai':'DPW.DU','Shanghai Yangshan':'1199.HK','Hong Kong':'0144.HK',
      'Singapore':'5246.KL','Tokyo / Yokohama':'POT.NZ','Los Angeles / Long Beach':'MATX','New York / New Jersey':'AMKBY'
    }
    for name,sym in upgrades.items():
        if name in by_name:by_name[name]['operator']=sym
    # Extra investable ports.
    extras=[
      {'name':'Manila','lat':14.59,'lon':120.95,'operator':'ICT.PS','region':'Southeast Asia'},
      {'name':'Mundra','lat':22.74,'lon':69.70,'operator':'ADANIPORTS.NS','region':'India'},
      {'name':'Santos','lat':-23.96,'lon':-46.30,'operator':'STBP3.SA','region':'Brazil'},
      {'name':'Tauranga','lat':-37.67,'lon':176.17,'operator':'POT.NZ','region':'New Zealand'},
    ]
    existing={p['name'] for p in self.ports};self.ports.extend([p for p in extras if p['name'] not in existing])
Market.__init__=_sgp_market_init_v13

# Background full-history hydrator. It uses data.py's persistent cache, runs at low
# concurrency, and never resets the simulator's live price when a dataset arrives.
def _sgp_weekly_from_daily(candles):
    if not candles:return []
    out=[];bucket=[];key=None
    for c in candles:
        k=c.timestamp.isocalendar()[:2]
        if key is not None and k!=key and bucket:
            out.append(Candle(bucket[0].timestamp,bucket[0].open,max(x.high for x in bucket),min(x.low for x in bucket),bucket[-1].close,sum(x.volume for x in bucket)))
            bucket=[]
        key=k;bucket.append(c)
    if bucket:out.append(Candle(bucket[0].timestamp,bucket[0].open,max(x.high for x in bucket),min(x.low for x in bucket),bucket[-1].close,sum(x.volume for x in bucket)))
    return out

_start_loaders_v13_base=Market.start_background_loaders
def _sgp_start_loaders_v13(self):
    _start_loaders_v13_base(self)
    if getattr(self,'_full_history_loader_started',False):return
    self._full_history_loader_started=True
    def hydrate():
        try:
            from data import fetch_history_max
            from concurrent.futures import ThreadPoolExecutor,as_completed
            assets=list(self.all_assets())
            def one(a):return a,fetch_history_max(getattr(a,'data_symbol',a.symbol))
            done=0
            with ThreadPoolExecutor(max_workers=1) as ex:
                futs=[ex.submit(one,a) for a in assets]
                for fut in as_completed(futs):
                    try:a,candles=fut.result()
                    except Exception:continue
                    if candles:
                        with a.data_lock:
                            # Historical dataset only; preserve the live simulator mark.
                            a.datasets['1d']=candles
                            a.datasets['1wk']=_sgp_weekly_from_daily(candles)
                            a.inception_date=candles[0].timestamp.date().isoformat();a.inception_price=float(candles[0].open);a.data_loaded=True
                        done+=1
                    if done%10==0:self.data_status=f'HISTORY CACHE • {done}/{len(assets)} assets ready'
            self.data_status=f'REAL HISTORY READY • {done}/{len(assets)} assets • simulation overlay active'
            self.visual_version+=1
        except Exception as e:self.errors.append(f'history hydrator: {e}')
    threading.Thread(target=hydrate,daemon=True,name='FullHistoryHydrator').start()
Market.start_background_loaders=_sgp_start_loaders_v13


# ===== Stock Game Pro 1.4 production polish =====
# Make weekends immediately obvious everywhere the authoritative game clock is shown.
def _sgp_clock_time_v14(self):
    return self.current.strftime('%a %Y-%m-%d %H:%M:%S')
GameClock.time=property(_sgp_clock_time_v14)

def _sgp_clock_utc_v14(self):
    return self.current.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).strftime('%a %H:%M:%S UTC')
GameClock.utc_time=property(_sgp_clock_utc_v14)

# Corporate actions are deliberately infrequent and occur only on regular-session days.
# Splits preserve investor value mechanically, dilution/buybacks change shares outstanding,
# and dividends are paid to long shareholders. All actions are surfaced through the news tape.
_Market_init_v14_base=Market.__init__
def _sgp_market_init_v14(self):
    _Market_init_v14_base(self)
    self.corporate_events=[];self._corp_last_date=None
Market.__init__=_sgp_market_init_v14

def _sgp_corporate_action_cycle(self):
    d=self.clock.current.date()
    if self._corp_last_date==d:return
    self._corp_last_date=d
    if self.clock.current.weekday()>=5:return
    liquid=[a for a in self.stocks if getattr(a,'price',0)>2]
    if not liquid:return
    # About one event every ~18 simulated weekdays for the whole universe.
    if random.random()>.055:return
    a=random.choice(liquid);r=random.random();event=None
    if r<.28 and a.price>20:
        ratio=random.choice((2,3,4,5,10));a.split(ratio);event=f'{a.symbol} announces and executes a {ratio}-for-1 stock split.'
    elif r<.52:
        pct=random.uniform(.015,.08);a.shares_outstanding*=1+pct;a.market_cap=a.price*a.shares_outstanding
        # Dilution is a genuine per-share supply shock, not an accounting-only label.
        a.update_price(a.price/(1+pct*.80),random.randint(20000,150000),self.clock.current)
        event=f'{a.symbol} issues new equity equal to {pct*100:.1f}% of shares outstanding; dilution pressures the share price.'
    elif r<.76:
        pct=random.uniform(.01,.06);a.shares_outstanding=max(1,a.shares_outstanding*(1-pct));a.market_cap=a.price*a.shares_outstanding
        a.update_price(a.price*(1+pct*.45),random.randint(20000,150000),self.clock.current)
        event=f'{a.symbol} completes a {pct*100:.1f}% share-count buyback; remaining shares receive a modest repricing benefit.'
    else:
        y=random.uniform(.001,.012);div=a.price*y
        if hasattr(self,'portfolio'):
            q=max(0,self.portfolio.positions.get(a.symbol,0));self.portfolio.cash+=q*div
        event=f'{a.symbol} pays a ${div:.2f} simulated cash dividend per share.'
    if event:
        rec={'time':self.clock.current,'symbol':a.symbol,'text':event};self.corporate_events.append(rec);self.corporate_events=self.corporate_events[-200:]
        self.news.append(NewsEvent(event,a.symbol,0,0,'CORPORATE'))
Market._corporate_action_cycle=_sgp_corporate_action_cycle

_tick_v14_base=Market.tick
async def _sgp_tick_v14(self):
    await _tick_v14_base(self)
    # Base tick has already advanced the clock. Corporate action check is O(1) on most ticks.
    try:self._corporate_action_cycle()
    except Exception as e:
        self.errors.append(f'corporate action: {e}')
Market.tick=_sgp_tick_v14


# ===== Stock Game Pro 1.6 final polish: earnings + logistics fundamentals =====
from datetime import timedelta as _sgp_td_v16

_Market_init_v16_base = Market.__init__
def _sgp_market_init_v16(self):
    _Market_init_v16_base(self)
    self.company_fundamentals={}
    self.logistics_losses={}
    self.earnings_events=[]
    now=self.clock.current.date()
    for a in self.stocks:
        base_rev=max(50_000_000.0, float(getattr(a,'market_cap',1e9))*random.uniform(.08,.35))
        margin=random.uniform(.04,.28)
        self.company_fundamentals[a.symbol]={
            'quarter_revenue':base_rev,
            'quarter_eps':max(.01,base_rev*margin/max(1.0,getattr(a,'shares_outstanding',1e7))),
            'margin':margin,
            'growth':random.uniform(-.03,.12),
            'next_earnings':now+_sgp_td_v16(days=random.randint(12,85)),
            'last_report':None,
            'last_surprise':0.0,
            'logistics_drag':0.0,
        }
Market.__init__=_sgp_market_init_v16

_ship_shock_v16_base=Market._apply_shipment_shock
def _sgp_ship_shock_v16(self,sh,kind):
    _ship_shock_v16_base(self,sh,kind)
    sev=.0
    try:
        sev=float(self.freight_events[-1][-1]) if self.freight_events else random.uniform(.01,.04)
    except Exception:sev=.02
    value=float(sh.get('cargo_value',0.0));owner=sh.get('cargo_owner');carrier=sh.get('carrier')
    # Damaged/intercepted cargo reduces the next reported quarter's realized revenue.
    if owner:self.logistics_losses[owner]=self.logistics_losses.get(owner,0.0)+value*min(.65,.18+sev*6)
    if carrier:self.logistics_losses[carrier]=self.logistics_losses.get(carrier,0.0)+value*min(.20,.04+sev*2)
    sh['damage_value']=value*min(.65,.18+sev*6);sh['status']=f'{kind} • EST LOSS ${sh["damage_value"]/1e6:,.0f}M'
Market._apply_shipment_shock=_sgp_ship_shock_v16

_update_freight_v16_base=Market._update_freight
def _sgp_update_freight_v16(self,game_minutes):
    # Hazards move with world time. Pirates travel along the same route in the ship's
    # direction at ~55% vessel speed; storms drift more slowly. Camera FPS never changes this.
    for sh in getattr(self,'shipments',[]):
        if sh.get('hazard')=='PIRATES' and not sh.get('hazard_resolved'):
            sh['hazard_progress']=min(.995,float(sh.get('hazard_progress',.6))+game_minutes/max(1,sh['route']['days']*1440)*.55)
        elif sh.get('hazard')=='STORM' and not sh.get('hazard_resolved'):
            sh['hazard_progress']=min(.995,float(sh.get('hazard_progress',.6))+game_minutes/max(1,sh['route']['days']*1440)*.12)
    _update_freight_v16_base(self,game_minutes)
Market._update_freight=_sgp_update_freight_v16

def _sgp_process_earnings_v16(self):
    today=self.clock.current.date()
    if getattr(self,'_earnings_check_day_v16',None)==today:return
    self._earnings_check_day_v16=today
    for a in self.stocks:
        f=self.company_fundamentals.get(a.symbol)
        if not f or today < f['next_earnings']:continue
        macro=getattr(self,'macro',{})
        demand=(float(macro.get('gdp_growth',2.0))-2.0)*.012 - max(0,float(macro.get('policy_rate',4.0))-4.0)*.004
        sector_noise=random.gauss(0,.035)
        growth=max(-.35,min(.45,float(f.get('growth',0))+demand+sector_noise))
        expected=float(f['quarter_revenue'])*(1+float(f.get('growth',0)))
        logistics=float(self.logistics_losses.pop(a.symbol,0.0))
        realized=max(1e6,float(f['quarter_revenue'])*(1+growth)-logistics)
        surprise=(realized-expected)/max(1.0,expected)
        margin=max(.01,min(.45,float(f['margin'])+random.gauss(0,.012)-min(.08,logistics/max(realized,1)*.3)))
        eps=max(-20.0,min(100.0,realized*margin/max(1.0,getattr(a,'shares_outstanding',1e7))))
        guide=random.gauss(growth*.35,.025)
        impact=max(-.14,min(.14,surprise*.65+guide*.45-(logistics/max(expected,1))*1.2))
        self.queue_or_apply_return(a,impact,random.randint(30000,250000))
        f.update(quarter_revenue=realized,quarter_eps=eps,margin=margin,growth=max(-.15,min(.25,growth*.65+random.gauss(0,.025))),next_earnings=today+_sgp_td_v16(days=random.randint(82,98)),last_report=today,last_surprise=surprise,logistics_drag=logistics)
        miss='BEAT' if surprise>=0 else 'MISS';drag=f' • logistics loss ${logistics/1e6:,.0f}M' if logistics>0 else ''
        headline=f'{a.symbol} EARNINGS {miss}: revenue ${realized/1e9:,.2f}B ({surprise*100:+.1f}% vs estimate), EPS ${eps:.2f}, guidance {guide*100:+.1f}%{drag}.'
        ev=NewsEvent(headline,a.symbol,impact,0,'EARNINGS');self.news.append(ev);self.earnings_events.append({'time':self.clock.current,'symbol':a.symbol,'revenue':realized,'eps':eps,'surprise':surprise,'impact':impact,'logistics_loss':logistics})
        self.earnings_events=self.earnings_events[-500:]
Market._process_earnings_v16=_sgp_process_earnings_v16

_tick_v16_base=Market.tick
async def _sgp_tick_v16(self):
    await _tick_v16_base(self)
    if not self.paused:
        try:self._process_earnings_v16()
        except Exception as e:self.errors.append(f'earnings v1.6: {e}')
Market.tick=_sgp_tick_v16

def _sgp_asset_fundamentals_v16(self,a):
    f=self.company_fundamentals.get(getattr(a,'symbol',''),{})
    if not f:return {}
    return dict(f, logistics_pending=float(self.logistics_losses.get(a.symbol,0.0)))
Market.asset_fundamentals=_sgp_asset_fundamentals_v16

# ===== Stock Game Pro 1.9 smooth engine / order controls / experiment lab =====
# Final production patch: smoother engine cadence, per-session % baselines, cancellable
# working orders, scenario controls, and an explicit one-full-day simulation action.
_Market_init_v19_base=Market.__init__
def _sgp_market_init_v19(self):
    _Market_init_v19_base(self)
    self.speed=.025  # ~40 Hz engine cadence for smoother prints without tying UI FPS to market FPS.
    self.scenario_volatility=1.0
    self.scenario_liquidity=1.0
    self.scenario_whale_flow=0.0       # -1 .. +1
    self.scenario_whale_symbol=''
    self.scenario_event_intensity=1.0
    self._pct_open_state={a.symbol:self.asset_regular_open(a) for a in self.all_assets()}
    for a in self.all_assets():
        a.scenario_vol_mult=1.0;a.scenario_liquidity=1.0
Market.__init__=_sgp_market_init_v19

_asset_return_v19_base=Market._asset_return
def _sgp_asset_return_v19(self,a,game_minutes,market_z,sector_z):
    base=_asset_return_v19_base(self,a,game_minutes,market_z,sector_z)
    vol=max(.10,min(6.0,float(getattr(self,'scenario_volatility',1.0))))
    event=max(.10,min(4.0,float(getattr(self,'scenario_event_intensity',1.0))))
    vol*=math.sqrt(event)
    # Scale stochastic component approximately without multiplying the macro drift by the full factor.
    base*=math.sqrt(vol)
    whale=max(-1.0,min(1.0,float(getattr(self,'scenario_whale_flow',0.0))))
    target=str(getattr(self,'scenario_whale_symbol','') or '').upper().strip()
    if whale:
        strength=.000010*max(.001,float(game_minutes))*whale
        base+=strength*(4.0 if target and a.symbol.upper()==target else .35)
    return base
Market._asset_return=_sgp_asset_return_v19

_get_book_v19_base=Market.get_book
def _sgp_get_book_v19(self,a):
    a.scenario_liquidity=max(.10,min(5.0,float(getattr(self,'scenario_liquidity',1.0))))
    a.scenario_vol_mult=max(.10,min(6.0,float(getattr(self,'scenario_volatility',1.0))))
    book=_get_book_v19_base(self,a)
    # OrderBook.update rebuilds levels before this wrapper runs; scaling once per cache refresh is stable.
    stamp=getattr(self,'_book_cache_time',{}).get(a.symbol,0)
    if getattr(book,'_sgp_liq_stamp',None)!=stamp:
        liq=a.scenario_liquidity
        for lvl in list(getattr(book,'bids',[]))+list(getattr(book,'asks',[])):
            lvl.size=max(1,int(lvl.size*liq));lvl.hidden=max(0,int(lvl.hidden*liq))
        book._sgp_liq_stamp=stamp
    return book
Market.get_book=_sgp_get_book_v19

_tick_v19_base=Market.tick
async def _sgp_tick_v19(self):
    await _tick_v19_base(self)
    # Each security's percentage-change baseline rolls exactly when its own regular cash
    # session opens. Overnight ECN movement therefore carries into the opening gap and the
    # new day's % begins from the first regular-session print.
    try:
        opened=False
        for a in self.all_assets():
            regular=self.asset_regular_open(a);prev=self._pct_open_state.get(a.symbol,regular)
            if regular and not prev:
                a.reset_day();opened=True
            self._pct_open_state[a.symbol]=regular
        if opened:self.visual_version+=1
    except Exception as e:
        self.errors.append(f'open baseline: {type(e).__name__}: {e}')
Market.tick=_sgp_tick_v19

def _sgp_cancel_order(self,order_id,kind=None):
    sid=str(order_id)
    groups=[('STOCK',self.pending_orders),('OPTION',self.pending_option_orders),('SPREAD',self.pending_spread_orders)]
    for label,arr in groups:
        if kind and str(kind).upper()!=label:continue
        for o in list(arr):
            if str(o.get('id'))==sid:
                arr.remove(o);self.visual_version+=1;return True,f'Cancelled {label.lower()} order #{sid}'
    return False,f'Working order #{sid} was not found.'
Market.cancel_order=_sgp_cancel_order

def _sgp_advance_one_day(self):
    """Advance exactly 24 simulated hours in 30-minute market-aware substeps."""
    was_paused=bool(self.paused);self.paused=True
    step_minutes=30.0;steps=48
    try:
        with self._lock:
            for _ in range(steps):
                self.clock.advance_seconds(step_minutes*60);self._update_macro(step_minutes)
                market_z=random.gauss(0,1);sector_cache={};index_symbols={x.symbol for x in self.indexes}
                for a in self.all_assets():
                    regular=self.asset_regular_open(a);prev=self._pct_open_state.get(a.symbol,regular)
                    if regular and not prev:
                        try:self._apply_open_gap(a)
                        except Exception:pass
                        a.reset_day()
                    self._pct_open_state[a.symbol]=regular
                    if a.symbol in index_symbols or not self.asset_quote_open(a):continue
                    cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,step_minutes,market_z,sector_z)
                    state=self.asset_trade_state(a);vol=random.randint(10,7000) if state=='OVERNIGHT ECN' else random.randint(100,50000)
                    a.update_price(a.price*max(.65,1+r),vol,self.clock.current)
                for idx in self.indexes:
                    if not self.asset_regular_open(idx):continue
                    comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
                    if comps:
                        ret=sum((c.price/max(.0001,c.previous_price)-1) for c in comps)/len(comps)
                        idx.update_price(idx.price*max(.75,1+ret+random.gauss(0,idx.volatility*.10*math.sqrt(step_minutes))),random.randint(1000,100000),self.clock.current)
                try:self._update_freight(step_minutes);self._update_geopolitics(step_minutes)
                except Exception:pass
                self._process_orders();self._process_expirations()
            try:self._corporate_action_cycle()
            except Exception:pass
            self.visual_version+=1
            self.data_status=f'ADVANCED ONE FULL DAY • {self.clock.time}'
    finally:
        self._last_real_tick=time.monotonic();self.paused=was_paused
    return self.clock.current
Market.advance_one_day=_sgp_advance_one_day


# ===== Stock Game Pro 2.0 engine pacing / autosave overhaul =====
# The previous engine repriced every asset on every 25ms cycle. With ~200 instruments
# this produced thousands of Python object allocations per second and steadily increased
# GC/UI latency. The 2.0 engine keeps the clock at 40Hz but updates assets in rotating
# batches, so every symbol still receives a smooth ~8-12Hz quote stream.
_Market_init_v20_base=Market.__init__
def _sgp_market_init_v20(self):
    _Market_init_v20_base(self)
    self.speed=.025;self._v20_assets=[a for a in self.all_assets() if a not in self.indexes];self._v20_cursor=0;self._v20_batch=max(20,min(56,(len(self._v20_assets)+3)//4));self._v20_last_asset_time={a.symbol:time.monotonic() for a in self._v20_assets};self._v20_last_housekeeping=time.monotonic();self._v20_last_index=time.monotonic();self._v20_last_risk=time.monotonic();self._v20_us_open=market_status('US',self.clock.current);self._v20_last_autosave_day=None;self.autosave_callback=None
Market.__init__=_sgp_market_init_v20

async def _sgp_tick_v20(self):
    if not self.running:return
    if self.paused:
        self._last_real_tick=time.monotonic();await asyncio.sleep(.025);return
    now=time.monotonic();real_dt=max(.001,min(.12,now-self._last_real_tick));self._last_real_tick=now
    game_seconds=real_dt*60.0*max(.05,float(getattr(self,'time_warp',1.0)));game_minutes=game_seconds/60.0
    try:
        self.clock.advance_seconds(game_seconds);self._update_macro(game_minutes)
        with self._lock:
            assets=self._v20_assets;n=len(assets)
            if n:
                start=self._v20_cursor;count=min(self._v20_batch,n);market_z=random.gauss(0,1);sector_cache={}
                for j in range(count):
                    a=assets[(start+j)%n]
                    if not self.asset_quote_open(a):continue
                    last=self._v20_last_asset_time.get(a.symbol,now);elapsed=max(.005,min(.8,now-last));self._v20_last_asset_time[a.symbol]=now
                    # Convert this asset's actual elapsed wall time to its own simulated minutes.
                    amin=elapsed*max(.05,float(getattr(self,'time_warp',1.0)))
                    cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,amin,market_z,sector_z)
                    state=self.asset_trade_state(a)
                    if state=='OVERNIGHT ECN':r*=.28;vol=random.randint(10,7000)
                    else:vol=random.randint(100,50000)
                    a.update_price(a.price*max(.75,1+r),vol,self.clock.current)
                self._v20_cursor=(start+count)%n
            # Indexes do not need 40Hz recomputation; 8-10Hz is visually continuous.
            if now-self._v20_last_index>=.10:
                self._v20_last_index=now
                for idx in self.indexes:
                    if not self.asset_regular_open(idx):continue
                    comps=[self.get_asset(s) for s in idx.components if self.get_asset(s)]
                    if not comps:continue
                    # Use a gentle current-component move rather than requiring every component
                    # to have updated in exactly the same scheduler slice.
                    weighted=sum((c.price/max(.0001,c.open_price)-1) for c in comps)/len(comps)
                    target=idx.open_price*(1+weighted);blend=.16;new=idx.price+(target-idx.price)*blend+idx.price*random.gauss(0,idx.volatility*.018)
                    idx.update_price(max(.0001,new),random.randint(1000,100000),self.clock.current)
            if now-self._v20_last_risk>=.10:
                elapsed=now-self._v20_last_risk;self._v20_last_risk=now;gm=elapsed*max(.05,float(getattr(self,'time_warp',1.0)))
                self._update_freight(gm);self._update_geopolitics(gm);self._process_orders();self._process_expirations()
            # Session transitions, earnings, corporate actions and autosave are low-frequency.
            if now-self._v20_last_housekeeping>=.25:
                self._v20_last_housekeeping=now;opened=False
                for a in self.all_assets():
                    regular=self.asset_regular_open(a);prev=self._pct_open_state.get(a.symbol,regular)
                    if regular and not prev:
                        try:self._apply_open_gap(a)
                        except Exception:pass
                        a.reset_day();opened=True
                    self._pct_open_state[a.symbol]=regular
                us_open=market_status('US',self.clock.current)
                if self._v20_us_open and not us_open:
                    day=self.clock.current.date()
                    if self._v20_last_autosave_day!=day and callable(getattr(self,'autosave_callback',None)):
                        self._v20_last_autosave_day=day
                        try:self.autosave_callback('end of trading day')
                        except Exception as e:self.errors.append(f'autosave: {type(e).__name__}: {e}')
                self._v20_us_open=us_open
                try:self._corporate_action_cycle();self._process_earnings_v16()
                except Exception as e:self.errors.append(f'daily systems: {type(e).__name__}: {e}')
                if opened:self.visual_version+=1
                if hasattr(self,'portfolio') and now-getattr(self,'_last_networth_calc',0)>3.0:
                    self._last_networth_calc=now;self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
        self.visual_version+=1;self.data_status=f'SIMULATION RUNNING • {self.time_warp:.2f}x • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
    except Exception as e:
        self.errors.append(f'tick v2.0: {type(e).__name__}: {e}')
        if len(self.errors)>100:self.errors=self.errors[-100:]
    await asyncio.sleep(max(.005,float(self.speed)))
Market.tick=_sgp_tick_v20

# A +24H manual jump is also a save boundary.
_advance_day_v20_base=Market.advance_one_day
def _sgp_advance_day_v20(self):
    out=_advance_day_v20_base(self)
    if callable(getattr(self,'autosave_callback',None)):
        try:self.autosave_callback('manual next day')
        except Exception as e:self.errors.append(f'autosave next day: {e}')
    return out
Market.advance_one_day=_sgp_advance_day_v20

# ===== Stock Game Pro 2.1 liquidity / market-impact engine =====
# Market orders now consume displayed liquidity and create persistent price impact.
# Distressed equities also have a fundamental-value anchor so the simulator does not
# create an artificial absorbing state near zero.
_Market_init_v21_base=Market.__init__
def _sgp_market_init_v21(self):
    _Market_init_v21_base(self)
    self._liquidity_health={}
    self._impact_state={}
    self._impact_last=time.monotonic()
    for a in self.all_assets():
        ref=max(.0001,float(getattr(a,'last_real_close',0) or 0),float(getattr(a,'inception_price',0) or 0),float(a.price))
        a.fundamental_value=ref
        a.liquidity_health=1.0
        a.last_market_impact=0.0
        a.last_execution_vwap=float(a.price)
Market.__init__=_sgp_market_init_v21

def _sgp_adv_shares(self,a):
    """Estimate normal daily share capacity from real/simulated daily bars when available."""
    try:
        bars=list(a.chart_candles('1d'))[-30:]
        vols=sorted(float(c.volume) for c in bars if getattr(c,'volume',0)>0)
        if vols:
            med=vols[len(vols)//2]
            if med>0:return max(500.0,med)
    except Exception:pass
    shares=max(1.0,float(getattr(a,'shares_outstanding',1_000_000)))
    # Fallback turnover is deliberately conservative for names without history.
    return max(2_000.0,min(5_000_000.0,shares*.0035))
Market.adv_shares=_sgp_adv_shares

def _sgp_execution_quote(self,side,a,qty):
    q=max(1,int(qty));side=str(side).upper();buy=side in ('BUY','COVER')
    book=self.get_book(a)
    levels=list(book.asks if buy else book.bids)
    remain=q;notional=0.0;shown=0
    for lvl in levels:
        take=min(remain,max(0,int(lvl.size)))
        if take:
            notional+=take*float(lvl.price);shown+=take;remain-=take
        if remain<=0:break
    adv=max(1.0,self.adv_shares(a));participation=q/adv
    sigma=max(.004,min(.35,float(getattr(a,'volatility',.002))*math.sqrt(390.0)))
    health=max(.05,min(1.0,float(self._liquidity_health.get(a.symbol,1.0))))
    penny_mult=1.0 if a.price>=5 else min(7.0,max(1.0,(5.0/max(.01,a.price))**.22))
    liq_mult=(1.0/max(.10,health))**.45
    # Square-root market-impact law with a modest linear tail for truly huge orders.
    impact=sigma*(.42*math.sqrt(max(0.0,participation))+.055*participation)*penny_mult*liq_mult
    impact=max(0.0,min(.85,impact))
    spread=max(.000001,float(a.ask)-float(a.bid))
    base=float(a.ask if buy else a.bid)
    if remain>0:
        # Undisplayed/deeper liquidity fills progressively farther from the touch.
        deep_px=max(.000001,base*(1+(impact*.62 if buy else -impact*.62)))
        notional+=remain*deep_px
    vwap=notional/q if q else base
    # Ensure impact is reflected even if the generated visible book happens to be deep.
    impact_vwap=max(vwap,base*(1+impact*.32)) if buy else min(vwap,base*(1-impact*.32))
    permanent=min(.70,impact*.38)
    return {'qty':q,'vwap':max(.000001,impact_vwap),'impact':impact,'permanent':permanent,'shown':shown,
            'adv':adv,'participation':participation,'health':health,'spread':spread}
Market.preview_execution=_sgp_execution_quote

def _sgp_execute_liquidity_order(self,side,a,qty):
    side=str(side).upper();q=max(1,int(qty));quote=self.preview_execution(side,a,q);buy=side in ('BUY','COVER')
    book=self.get_book(a);remaining=q
    levels=book.asks if buy else book.bids
    # Consume displayed shares instead of regenerating them immediately.
    for lvl in levels:
        take=min(remaining,max(0,int(lvl.size)))
        lvl.size=max(0,int(lvl.size)-take);remaining-=take
        if remaining<=0:break
    adv=max(1.0,quote['adv']);depletion=min(.90,.55*math.sqrt(max(0.0,q/adv)))
    old_health=float(self._liquidity_health.get(a.symbol,1.0));health=max(.05,old_health*(1-depletion))
    self._liquidity_health[a.symbol]=health;a.liquidity_health=health
    signed=1.0 if buy else -1.0
    old=float(a.price)
    # The final print follows the post-trade mid, while VWAP remains the actual accounting price.
    new=max(.000001,old*(1+signed*quote['permanent']))
    # A large sweep can never be visually invisible. Respect at least a fraction of VWAP displacement.
    if buy:new=max(new,old+(quote['vwap']-old)*.45)
    else:new=min(new,old+(quote['vwap']-old)*.45)
    new=max(.000001,new)
    a.update_price(new,q,self.clock.current)
    a.last_market_impact=signed*quote['impact'];a.last_execution_vwap=quote['vwap']
    st=self._impact_state.setdefault(a.symbol,{'pressure':0.0,'last':time.monotonic()})
    st['pressure']=max(-1.5,min(1.5,float(st.get('pressure',0))+signed*quote['impact']));st['last']=time.monotonic()
    self._book_cache_time[a.symbol]=0;self.visual_version+=1
    return quote
Market.execute_liquidity_order=_sgp_execute_liquidity_order

_get_book_v21_base=Market.get_book
def _sgp_get_book_v21(self,a):
    book=_get_book_v21_base(self,a)
    health=max(.05,min(1.0,float(self._liquidity_health.get(a.symbol,1.0))))
    stamp=(getattr(self,'_book_cache_time',{}).get(a.symbol,0),round(health,3))
    if getattr(book,'_v21_health_stamp',None)!=stamp:
        # Existing scenario-liquidity scaling remains intact; this is additional depletion.
        for lvl in list(getattr(book,'bids',[]))+list(getattr(book,'asks',[])):
            lvl.size=max(1,int(lvl.size*health));lvl.hidden=max(0,int(lvl.hidden*health))
        book._v21_health_stamp=stamp
    return book
Market.get_book=_sgp_get_book_v21

_asset_return_v21_base=Market._asset_return
def _sgp_asset_return_v21(self,a,game_minutes,market_z,sector_z):
    r=float(_asset_return_v21_base(self,a,game_minutes,market_z,sector_z))
    # Slowly replenish liquidity and decay order-flow pressure in simulated time.
    h=float(self._liquidity_health.get(a.symbol,1.0));recovery=1-math.exp(-max(.0,float(game_minutes))/75.0)
    self._liquidity_health[a.symbol]=min(1.0,h+(1-h)*recovery)
    # Distressed securities are not mathematically trapped at the minimum price. Their
    # fundamental anchor can pull them back up, while still allowing bankrupt-like collapse.
    ref=max(.0001,float(getattr(a,'fundamental_value',0) or getattr(a,'last_real_close',0) or a.price))
    ratio=max(1e-9,float(a.price)/ref)
    if ratio<.20:
        distress=math.log(.20/max(1e-9,ratio))
        r+=min(.035,.0012*distress*max(.05,float(game_minutes)))
        if a.price<=.00012:
            r=max(r,random.uniform(.015,.09))
    # Persistent impact fades rather than vanishing on the very next random tick.
    st=self._impact_state.get(a.symbol)
    if st:
        pressure=float(st.get('pressure',0.0));r+=pressure*.0015*min(1.0,max(.01,float(game_minutes)))
        st['pressure']=pressure*math.exp(-max(.0,float(game_minutes))/35.0)
    return max(-.70,min(.70,r))
Market._asset_return=_sgp_asset_return_v21

# ===== Stock Game Pro 2.2 realism / correlation / research-model patch =====
# This patch intentionally keeps the simulation deterministic enough for strategy testing while
# giving the main US ETF/index complex tighter factor relationships and a richer predictive model.
_Market_init_v22_base=Market.__init__
def _sgp22_market_init(self):
    _Market_init_v22_base(self)
    self.time_warp=.25
    self.scenario_correlation=float(getattr(self,'scenario_correlation',.82))
    self.scenario_mean_reversion=float(getattr(self,'scenario_mean_reversion',1.0))
    self.scenario_trend=float(getattr(self,'scenario_trend',1.0))
    self.scenario_option_iv=float(getattr(self,'scenario_option_iv',1.0))
    self.scenario_rate_shock=float(getattr(self,'scenario_rate_shock',0.0))
    self.scenario_credit_stress=float(getattr(self,'scenario_credit_stress',0.0))
    self.scenario_oil_shock=float(getattr(self,'scenario_oil_shock',0.0))
    self.scenario_fx_shock=float(getattr(self,'scenario_fx_shock',0.0))
    # Broaden the index baskets so index/ETF behavior is driven by actual constituents rather
    # than only a handful of names.  SPY is treated as the investable tracker for SPX.
    spx=self.get_asset('SPX');ndx=self.get_asset('NDX');dji=self.get_asset('DJI')
    us=[a.symbol for a in self.stocks if getattr(a,'category','') not in ('ETF','Index')]
    if spx is not None:spx.components=us[:]
    if ndx is not None:ndx.components=[a.symbol for a in self.stocks if getattr(a,'category','') in ('Tech','Media','Consumer')][:80]
    if dji is not None:dji.components=[s for s in ('AAPL','MSFT','AMZN','JPM','V','WMT','MCD','CAT','HON','RTX','UNH','GS','HD','KO','DIS','IBM','AXP') if self.get_asset(s)]
Market.__init__=_sgp22_market_init

# Timestamp-aware regular-session helper used by chart overnight shading.
def _sgp22_regular_open_at(self,a,dt):
    try:return bool(market_status(self.asset_session(a),dt))
    except Exception:return True
Market.asset_regular_open_at=_sgp22_regular_open_at

_predict_v22_base=Market.predict
def _sgp22_predict(self,a):
    """Multi-factor educational forecast seeded from the newest available real quote/history.

    The score combines multi-horizon momentum, RSI mean reversion, market/index direction,
    macro regime and volatility.  It is a simulator signal, not a claim of future returns.
    """
    try:
        hist=[float(x) for x in list(a.history)]
        daily=list(a.chart_candles('1d'))
        if daily and len(daily)>=5: hist=[float(c.close) for c in daily[-260:]]
        if len(hist)<3:return _predict_v22_base(self,a)
        def ret(n):return hist[-1]/hist[-min(len(hist),n+1)]-1 if len(hist)>1 else 0.0
        r5,r20,r60=ret(5),ret(20),ret(60)
        # RSI without importing UI helpers.
        w=hist[-15:];g=[max(0,b-a0) for a0,b in zip(w,w[1:])];l=[max(0,a0-b) for a0,b in zip(w,w[1:])]
        ag=sum(g)/max(1,len(g));al=sum(l)/max(1,len(l));rsi_v=100. if al==0 else 100-100/(1+ag/al)
        trend=(.45*r5+.35*r20+.20*r60)*float(getattr(self,'scenario_trend',1.0))
        meanrev=((50-rsi_v)/50.0)*.006*float(getattr(self,'scenario_mean_reversion',1.0))
        macro=self.macro;sector=str(getattr(a,'category',''))
        macro_score=float(macro.get('sentiment',0))*.006
        rate=float(macro.get('policy_rate',4.0));infl=float(macro.get('inflation',2.5));growth=float(macro.get('gdp_growth',2.0))
        if sector in ('Tech','Consumer','Real Estate'):macro_score-=max(0,rate-3.0)*.0007
        if sector in ('Finance',):macro_score+=(rate-3.0)*.00035
        if sector in ('Energy',):macro_score+=float(getattr(self,'scenario_oil_shock',0))*0.004
        macro_score+=(growth-2.0)*.0006-(infl-2.0)*.00035-float(getattr(self,'scenario_credit_stress',0))*0.003
        spx=self.get_asset('SPX');market_mom=0.0
        if spx is not None and len(spx.history)>=20:
            hh=list(spx.history);market_mom=hh[-1]/hh[-20]-1
        corr=max(0,min(1.25,float(getattr(self,'scenario_correlation',.82))))
        expected=trend+meanrev+macro_score+market_mom*.20*corr
        vol=max(.0001,float(getattr(a,'volatility',.002))*float(getattr(self,'scenario_volatility',1.0)))
        z=expected/max(.002,vol*4);conf=max(.50,min(.96,.52+abs(z)*.18))
        label='BULLISH' if expected>.003 else 'BEARISH' if expected<-.003 else 'NEUTRAL'
        real_stamp=getattr(a,'last_real_timestamp',None)
        return {'label':label,'confidence':conf,'momentum':r20,'volatility':vol,'expected_return':expected,
                'rsi':rsi_v,'market_momentum':market_mom,'real_timestamp':real_stamp}
    except Exception:return _predict_v22_base(self,a)
Market.predict=_sgp22_predict

_asset_return_v22_base=Market._asset_return
def _sgp22_asset_return(self,a,game_minutes,market_z,sector_z):
    r=float(_asset_return_v22_base(self,a,game_minutes,market_z,sector_z))
    gm=max(.001,float(game_minutes));corr=max(0,min(1.25,float(getattr(self,'scenario_correlation',.82))))
    # Correlated broad-market impulse.  It is deliberately small per tick but persistent.
    r += float(market_z)*float(getattr(a,'volatility',.002))*0.16*corr*math.sqrt(gm)
    # Explicit scenario variables used by the experiment lab.
    cat=str(getattr(a,'category',''))
    r += float(getattr(self,'scenario_rate_shock',0.0)) * (-.00030 if cat in ('Tech','Consumer','Real Estate') else .00010 if cat=='Finance' else -.00005) * gm
    r += float(getattr(self,'scenario_credit_stress',0.0)) * (-.00032 if cat in ('Finance','Consumer','Real Estate') else -.00012) * gm
    r += float(getattr(self,'scenario_oil_shock',0.0)) * (.00038 if cat=='Energy' else -.00008 if cat in ('Industrial','Consumer') else 0) * gm
    # SPY closely tracks SPX but retains a little ETF microstructure noise.
    if getattr(a,'symbol','')=='SPY':
        spx=self.get_asset('SPX')
        if spx is not None and float(getattr(spx,'previous_price',0))>0:
            spx_r=float(spx.price)/float(spx.previous_price)-1
            r=.96*spx_r+.04*r
    return max(-.70,min(.70,r))
Market._asset_return=_sgp22_asset_return

# Quote/option volatility scenario multiplier.  Existing option contracts already use the
# underlying's volatility, so assigning this per-asset value keeps the strategy lab coherent.
_old_get_book_v22=Market.get_book
def _sgp22_get_book(self,a):
    try:a.scenario_option_iv=float(getattr(self,'scenario_option_iv',1.0))
    except Exception:pass
    return _old_get_book_v22(self,a)
Market.get_book=_sgp22_get_book

# ===== Stock Game Pro 2.2.1 large-position / execution safety overhaul =====
# Keep whale trading meaningful without allowing one request to create unbounded integer/float
# states.  Instant marketable liquidity is limited by displayed depth, ADV and estimated float;
# oversized requests are partially filled rather than forcing the whole quantity through one tick.

def _sgp221_estimated_float_shares(self,a):
    try:adv=max(1.0,float(self.adv_shares(a)))
    except Exception:adv=100_000.0
    try:reported=max(1.0,float(getattr(a,'shares_outstanding',0.0) or 0.0))
    except Exception:reported=1.0
    # The older simulator initialized unknown companies with a generic $1B market cap, which can
    # imply unrealistically tiny share counts for high-priced names.  ADV gives a better lower bound.
    floor=50_000_000.0 if getattr(a,'category','') in ('ETF','Index') else 10_000_000.0
    turnover_float=adv*(80.0 if getattr(a,'category','')=='ETF' else 45.0)
    return max(floor,reported,turnover_float)
Market.estimated_float_shares=_sgp221_estimated_float_shares

def _sgp221_position_capacity(self,a,side='BUY'):
    side=str(side).upper();f=self.estimated_float_shares(a)
    # ETFs can create/redeem shares; individual equities are constrained more tightly by float.
    if getattr(a,'category','')=='ETF':mult=2.5 if side in ('BUY','SELL') else 1.5
    else:mult=.95 if side in ('BUY','SELL') else 1.20
    return max(1,int(f*mult))
Market.position_capacity=_sgp221_position_capacity

def _sgp221_max_executable_qty(self,a,side,requested):
    req=max(1,int(requested));book=self.get_book(a);buy=str(side).upper() in ('BUY','COVER')
    levels=book.asks if buy else book.bids;visible=sum(max(0,int(x.size)) for x in levels)
    f=max(1.0,self.estimated_float_shares(a));adv=max(float(self.adv_shares(a)),f*.01)
    # One click may sweep several times normal daily volume, but not an effectively infinite book.
    # Penny names are intentionally tighter because float/liquidity dominates their execution.
    px=max(.0001,float(a.price));float_frac=.04 if px<5 else .10
    cap=max(float(visible)*12.0,adv*3.0,f*float_frac)
    return max(1,min(req,int(cap)))
Market.max_executable_qty=_sgp221_max_executable_qty

_sgp221_preview_base=Market.preview_execution
def _sgp221_preview_execution(self,side,a,qty):
    requested=max(1,int(qty));filled=self.max_executable_qty(a,side,requested)
    q=dict(_sgp221_preview_base(self,side,a,filled))
    # Guard the instantaneous permanent displacement.  The residual impact state still carries
    # pressure into subsequent ticks, giving large orders a persistent footprint without overflow.
    penny=max(.0001,float(a.price))<5
    q['permanent']=min(float(q.get('permanent',0.0)),.35 if penny else .18)
    q['requested_qty']=requested;q['filled_qty']=filled;q['remaining_qty']=max(0,requested-filled)
    return q
Market.preview_execution=_sgp221_preview_execution

def _sgp221_execute_liquidity_order(self,side,a,qty):
    side=str(side).upper();quote=self.preview_execution(side,a,qty);q=max(1,int(quote['filled_qty']));buy=side in ('BUY','COVER')
    book=self.get_book(a);remaining=q;levels=book.asks if buy else book.bids
    for lvl in levels:
        take=min(remaining,max(0,int(lvl.size)))
        if take:
            lvl.size=max(0,int(lvl.size)-take);remaining-=take
        if remaining<=0:break
    adv=max(1.0,float(quote['adv']));depletion=min(.85,.45*math.sqrt(max(0.0,q/adv)))
    old_health=float(self._liquidity_health.get(a.symbol,1.0));health=max(.05,old_health*(1-depletion))
    self._liquidity_health[a.symbol]=health;a.liquidity_health=health
    signed=1.0 if buy else -1.0;old=max(.000001,float(a.price));perm=float(quote.get('permanent',0.0))
    new=old*(1+signed*perm)
    vwap=float(quote.get('vwap',old))
    if buy:new=max(new,old+(vwap-old)*.35)
    else:new=min(new,old+(vwap-old)*.35)
    if not math.isfinite(new):new=old
    new=max(.000001,min(1.0e12,new))
    a.update_price(new,min(q,9_000_000_000_000_000_000),self.clock.current)
    a.last_market_impact=signed*float(quote.get('impact',0.0));a.last_execution_vwap=vwap
    st=self._impact_state.setdefault(a.symbol,{'pressure':0.0,'last':time.monotonic()})
    st['pressure']=max(-1.5,min(1.5,float(st.get('pressure',0.0))+signed*float(quote.get('impact',0.0))));st['last']=time.monotonic()
    self._book_cache_time[a.symbol]=0;self.visual_version+=1
    return quote
Market.execute_liquidity_order=_sgp221_execute_liquidity_order


# ===== Stock Game Pro 2.3 real-second time-warp convention =====
# Existing engine math advances 60 simulated seconds per real second at internal 1.0.
# Therefore UI/display 1x is represented internally as 1/60.
_Market_init_v23_base=Market.__init__
def _sgp23_market_init(self):
    _Market_init_v23_base(self);self.time_warp=1.0/60.0
Market.__init__=_sgp23_market_init

# ===== Stock Game Pro 2.4 real-time pacing / opening-bell baseline / S&P universe =====
try:
    from sp500_constituents import SP500_SYMBOLS as _SGP24_SP500_SYMBOLS
except Exception:
    _SGP24_SP500_SYMBOLS=[]

_Market_init_v24_base=Market.__init__
def _sgp24_market_init(self):
    _Market_init_v24_base(self)
    # Internal time_warp is simulated minutes per real second. 1/60 therefore means
    # exactly one simulated second per real-world second; 100x is 100/60.
    self.time_warp=1.0/60.0
    self._session_groups24={}
    for a in self.all_assets():
        code=str(getattr(a,'session','US') or 'US')
        if code not in SESSIONS:code='US'
        self._session_groups24.setdefault(code,[]).append(a)
        a.regular_close_price=float(getattr(a,'regular_close_price',0.0) or getattr(a,'last_real_close',0.0) or a.price)
        a.previous_close_price=float(getattr(a,'previous_close_price',a.regular_close_price))
    self._session_state24={code:bool(market_status(code,self.clock.current)) for code in self._session_groups24}
    self._v24_last_autosave_day=None
    # Keep SPX tied only to actual index constituents. Non-index research names remain tradable
    # without contaminating S&P 500 movement.
    spx=self.get_asset('SPX')
    if spx is not None and _SGP24_SP500_SYMBOLS:
        spx.components=[s for s in _SGP24_SP500_SYMBOLS if self.get_asset(s) is not None]
Market.__init__=_sgp24_market_init

def _sgp24_handle_session_transitions(self):
    """Reset each exchange's daily % baseline at its opening bell, before new prints occur."""
    opened_any=False
    for code,assets in self._session_groups24.items():
        try:regular=bool(market_status(code,self.clock.current))
        except Exception:regular=False
        prev=bool(self._session_state24.get(code,regular))
        if regular and not prev:
            for a in assets:
                try:
                    a.previous_close_price=float(getattr(a,'regular_close_price',a.price) or a.price)
                    self._apply_open_gap(a)
                    a.reset_day()  # change_percent() is now exactly 0 at the new opening baseline.
                    a.day_open_timestamp=self.clock.current
                except Exception as e:
                    self.errors.append(f'open baseline {a.symbol}: {e}')
            opened_any=True
        elif prev and not regular:
            for a in assets:
                try:
                    a.regular_close_price=float(a.price)
                    a.regular_close_timestamp=self.clock.current
                except Exception:pass
            if code=='US':
                day=self.clock.current.date()
                if self._v24_last_autosave_day!=day and callable(getattr(self,'autosave_callback',None)):
                    self._v24_last_autosave_day=day
                    try:self.autosave_callback('end of trading day')
                    except Exception as e:self.errors.append(f'autosave: {type(e).__name__}: {e}')
        self._session_state24[code]=regular
    if opened_any:
        self.visual_version+=1
        app=getattr(self,'ui_app',None)
        try:app.root.after(0,app.refresh_watch)
        except Exception:pass
Market._handle_session_transitions24=_sgp24_handle_session_transitions

async def _sgp24_tick(self):
    """Final engine loop: true real-second 1x pacing, up to 100x, with transition-safe baselines."""
    if not self.running:return
    if self.paused:
        self._last_real_tick=time.monotonic();await asyncio.sleep(.025);return
    now=time.monotonic();real_dt=max(.001,min(.12,now-self._last_real_tick));self._last_real_tick=now
    warp=max(1.0/60.0,min(100.0/60.0,float(getattr(self,'time_warp',1.0/60.0))))
    game_seconds=real_dt*60.0*warp
    game_minutes=game_seconds/60.0
    try:
        self.clock.advance_seconds(game_seconds)
        # Do this before the first tradable print of the new session so CHG% never carries
        # yesterday's baseline through the bell.
        self._handle_session_transitions24()
        self._update_macro(game_minutes)
        with self._lock:
            assets=self._v20_assets;n=len(assets)
            if n:
                start=self._v20_cursor;count=min(self._v20_batch,n);market_z=random.gauss(0,1);sector_cache={}
                for j in range(count):
                    a=assets[(start+j)%n]
                    if not self.asset_quote_open(a):continue
                    last=self._v20_last_asset_time.get(a.symbol,now);elapsed=max(.005,min(.8,now-last));self._v20_last_asset_time[a.symbol]=now
                    amin=elapsed*warp
                    cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,amin,market_z,sector_z)
                    state=self.asset_trade_state(a)
                    if state=='OVERNIGHT ECN':r*=.28;vol=random.randint(10,7000)
                    else:vol=random.randint(100,50000)
                    a.update_price(a.price*max(.75,1+r),vol,self.clock.current)
                self._v20_cursor=(start+count)%n
            # Index calculations are deliberately slower than quote prints. With 503 SPX
            # constituents this remains responsive while still keeping SPY/SPX tightly linked.
            if now-self._v20_last_index>=.12:
                self._v20_last_index=now
                for idx in self.indexes:
                    if not self.asset_regular_open(idx):continue
                    comps=[self.get_asset(s) for s in idx.components];comps=[c for c in comps if c is not None]
                    if not comps:continue
                    # Market-cap weighting when useful caps are available; equal weights are the
                    # fallback for synthetic/unseeded names.
                    caps=[max(1.0,float(getattr(c,'market_cap',1.0))) for c in comps];tot=sum(caps)
                    weighted=sum(w*(c.price/max(.0001,c.open_price)-1.0) for c,w in zip(comps,caps))/max(1.0,tot)
                    target=idx.open_price*(1+weighted);blend=.18;new=idx.price+(target-idx.price)*blend+idx.price*random.gauss(0,idx.volatility*.012)
                    idx.update_price(max(.0001,new),random.randint(1000,100000),self.clock.current)
            if now-self._v20_last_risk>=.10:
                elapsed=now-self._v20_last_risk;self._v20_last_risk=now;gm=elapsed*warp
                self._update_freight(gm);self._update_geopolitics(gm);self._process_orders();self._process_expirations()
            if now-self._v20_last_housekeeping>=.25:
                self._v20_last_housekeeping=now
                try:self._corporate_action_cycle();self._process_earnings_v16()
                except Exception as e:self.errors.append(f'daily systems: {type(e).__name__}: {e}')
                if hasattr(self,'portfolio') and now-getattr(self,'_last_networth_calc',0)>3.0:
                    self._last_networth_calc=now;self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
        self.visual_version+=1
        self.data_status=f'SIMULATION RUNNING • {warp*60.0:.2f}x REAL-SECOND • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
    except Exception as e:
        self.errors.append(f'tick v2.4: {type(e).__name__}: {e}')
        if len(self.errors)>100:self.errors=self.errors[-100:]
    await asyncio.sleep(max(.005,float(self.speed)))
Market.tick=_sgp24_tick

# ===== Stock Game Pro 2.5 performance / index engine overhaul =====
# Broad constituent coverage is intentionally decoupled from quote frequency. Thousands of
# tradable symbols can exist without forcing thousands of Candle allocations every second.
try:
    from index_constituents import INDEX_COMPONENTS as _SGP25_INDEX_COMPONENTS, INDEX_PRICE_HINTS as _SGP25_PRICE_HINTS, INDEX_WEIGHTS as _SGP25_INDEX_WEIGHTS
except Exception:
    _SGP25_INDEX_COMPONENTS={};_SGP25_PRICE_HINTS={};_SGP25_INDEX_WEIGHTS={}
try:
    from sp500_constituents import SP500_SYMBOLS as _SGP25_SP500
except Exception:
    _SGP25_SP500=[]

_Market_init_v25_base=Market.__init__
def _sgp25_market_init(self):
    _Market_init_v25_base(self)
    # 25 Hz engine cadence is more than enough for a desktop simulator. The 2.4 build used
    # a 40 Hz engine and up to 56 asset updates per pulse, which became costly after the
    # constituent universe grew into the thousands.
    self.speed=.04
    self._v20_batch=14
    self._v25_last_hot_refresh=0.0;self._v25_hot_cache=set()
    self._v25_last_visual=0.0;self._v25_last_index_rebuild=time.monotonic()
    # Restore authoritative component sets after legacy init wrappers that replaced NDX/DJI.
    for _idx in self.indexes:
        _comps=_SGP25_INDEX_COMPONENTS.get(getattr(_idx,'symbol',''))
        if _comps:
            _idx.components=[sym for sym in _comps if self.get_asset(sym) is not None]
    self._v25_index_cache={};self._v25_index_reverse={};self._v25_index_dirty=set()
    self._v25_quote_loading=set();self._v25_real_seeded=set()
    # Seed Russell/IWM proxy names at their bundled snapshot prices instead of a generic $100.
    for sym,px in _SGP25_PRICE_HINTS.items():
        a=self.get_asset(sym)
        if a is None or not math.isfinite(float(px)) or float(px)<=.001:continue
        if abs(float(a.price)-100.0)>.0001:continue
        factor=float(px)/max(.0001,float(a.price))
        try:
            a.price*=factor;a.open_price*=factor;a.previous_price*=factor;a.high*=factor;a.low*=factor;a.bid*=factor;a.ask*=factor;a.last_real_close*=factor
            for bars in list(getattr(a,'live_bars',{}).values()):
                for c in bars:
                    c.open*=factor;c.high*=factor;c.low*=factor;c.close*=factor
            for bars in list(getattr(a,'datasets',{}).values()):
                for c in bars:
                    c.open*=factor;c.high*=factor;c.low*=factor;c.close*=factor
            try:
                from collections import deque
                a.history=deque((float(x)*factor for x in a.history),maxlen=getattr(a.history,'maxlen',30000))
            except Exception:pass
            a.fundamental_value=float(px)
        except Exception:pass
    self._v25_rebuild_index_cache()
Market.__init__=_sgp25_market_init

def _sgp25_rebuild_index_cache(self):
    self._v25_index_cache={};self._v25_index_reverse={}
    # SPX remains the complete S&P basket from 2.4. NDX/DJI/RUT use their 2.5 component lists.
    for idx in self.indexes:
        syms=[s for s in getattr(idx,'components',[]) if self.get_asset(s) is not None]
        if not syms:continue
        mode='price' if idx.symbol=='DJI' else 'return'
        rec={'mode':mode,'num':0.0,'den':0.0,'members':len(syms)}
        explicit=_SGP25_INDEX_WEIGHTS.get(idx.symbol,{})
        for s in syms:
            a=self.get_asset(s)
            if a is None:continue
            if mode=='price':
                w=1.0;rec['num']+=float(a.price);rec['den']+=max(.0001,float(a.open_price))
            else:
                w=max(.000001,float(explicit.get(s,getattr(a,'market_cap',1.0) or 1.0)))
                rec['num']+=w*(float(a.price)/max(.0001,float(a.open_price))-1.0);rec['den']+=w
            self._v25_index_reverse.setdefault(s,[]).append((idx.symbol,w,mode))
        self._v25_index_cache[idx.symbol]=rec
    self._v25_last_index_rebuild=time.monotonic()
Market._v25_rebuild_index_cache=_sgp25_rebuild_index_cache

def _sgp25_note_asset_move(self,a,old_price):
    for idxsym,w,mode in self._v25_index_reverse.get(getattr(a,'symbol',''),()):
        rec=self._v25_index_cache.get(idxsym)
        if not rec:continue
        try:
            if mode=='price':rec['num']+=float(a.price)-float(old_price)
            else:
                op=max(.0001,float(a.open_price));rec['num']+=float(w)*((float(a.price)-float(old_price))/op)
        except Exception:self._v25_index_dirty.add(idxsym)
Market._v25_note_asset_move=_sgp25_note_asset_move

def _sgp25_hot_symbols(self,now):
    if now-self._v25_last_hot_refresh<.40:return self._v25_hot_cache
    self._v25_last_hot_refresh=now;hot={'SPY','SPX','NDX','DJI','RUT'}
    try:
        app=self.ui_app
        for c in list(getattr(app,'charts',()))+list(getattr(app,'extra_charts',())):
            a=getattr(c,'asset',None)
            if a:hot.add(a.symbol)
        sel=app.selected()
        if sel:hot.add(sel.symbol)
    except Exception:pass
    try:hot.update(str(s) for s,q in self.portfolio.positions.items() if q)
    except Exception:pass
    for o in self.pending_orders:
        a=o.get('asset')
        if a:hot.add(a.symbol)
    self._v25_hot_cache=hot;return hot
Market._v25_hot_symbols=_sgp25_hot_symbols

# Allocation-free return model. The old base model converted each asset's potentially
# 30,000-point history deque into a Python list on every quote update. With a broad index
# universe that single line dominated CPU time and garbage collection.
def _sgp25_asset_return(self,a,game_minutes,market_z,sector_z):
    m=self.macro;dt=max(float(game_minutes),1e-6);cat=str(getattr(a,'category',''))
    sigma=float(a.volatility)*math.sqrt(dt/5.0)
    rate_drag=max(0,float(m.get('policy_rate',4.0))-3.0)*.000012
    growth_push=(float(m.get('gdp_growth',2.0))-2.0)*.000010
    inflation_drag=max(0,float(m.get('inflation',2.5))-2.5)*.000008
    drift=(growth_push-rate_drag-inflation_drag+float(m.get('sentiment',0))*.000012)*dt
    beta=1.0
    if cat in ('Tech','Information Technology','Consumer','Consumer Discretionary','Media','Communication Services'):beta=1.18
    elif cat in ('Health','Health Care','Consumer Staples','Utilities'):beta=.72
    elif cat in ('Finance','Financials'):beta=1.05;drift+=(float(m.get('policy_rate',4.0))-2.5)*.000004*dt
    elif cat=='Energy':beta=.85;drift+=(float(m.get('inflation',2.5))-2.0)*.000008*dt
    if isinstance(a,Crypto):beta=1.65;drift+=float(m.get('sentiment',0))*.000025*dt
    if isinstance(a,Forex):beta=.35
    if isinstance(a,Commodity):beta=.55
    z=.62*beta*float(market_z)+.42*float(sector_z)+.58*random.gauss(0,1)
    h=getattr(a,'history',())
    try:mom=(float(h[-1])/float(h[-10])-1.0) if len(h)>=10 and float(h[-10]) else 0.0
    except Exception:mom=0.0
    r=drift+max(-.00008,min(.00008,mom*.015))*dt+sigma*z
    # Scenario multipliers from the research lab.
    vol=max(.10,min(6.0,float(getattr(self,'scenario_volatility',1.0))))*math.sqrt(max(.10,min(4.0,float(getattr(self,'scenario_event_intensity',1.0)))))
    r*=math.sqrt(vol)
    whale=max(-1.0,min(1.0,float(getattr(self,'scenario_whale_flow',0.0))));target=str(getattr(self,'scenario_whale_symbol','') or '').upper().strip()
    if whale:r+=.000010*dt*whale*(4.0 if target and a.symbol.upper()==target else .35)
    # Liquidity recovery / distressed-value anchor / persistent market impact from 2.1.
    lh=float(self._liquidity_health.get(a.symbol,1.0));recovery=1-math.exp(-max(0.0,dt)/75.0);self._liquidity_health[a.symbol]=min(1.0,lh+(1-lh)*recovery)
    ref=max(.0001,float(getattr(a,'fundamental_value',0) or getattr(a,'last_real_close',0) or a.price));ratio=max(1e-9,float(a.price)/ref)
    if ratio<.20:
        distress=math.log(.20/max(1e-9,ratio));r+=min(.035,.0012*distress*max(.05,dt))
        if a.price<=.00012:r=max(r,random.uniform(.015,.09))
    st=self._impact_state.get(a.symbol)
    if st:
        pressure=float(st.get('pressure',0.0));r+=pressure*.0015*min(1.0,max(.01,dt));st['pressure']=pressure*math.exp(-max(0.0,dt)/35.0)
    # 2.2 correlation / macro experiment factors.
    corr=max(0,min(1.25,float(getattr(self,'scenario_correlation',.82))))
    r+=float(market_z)*float(getattr(a,'volatility',.002))*0.16*corr*math.sqrt(max(.001,dt))
    r+=float(getattr(self,'scenario_rate_shock',0.0))*(-.00030 if cat in ('Tech','Information Technology','Consumer','Consumer Discretionary','Real Estate') else .00010 if cat in ('Finance','Financials') else -.00005)*dt
    r+=float(getattr(self,'scenario_credit_stress',0.0))*(-.00032 if cat in ('Finance','Financials','Consumer','Consumer Discretionary','Real Estate') else -.00012)*dt
    r+=float(getattr(self,'scenario_oil_shock',0.0))*(.00038 if cat=='Energy' else -.00008 if cat in ('Industrial','Industrials','Consumer','Consumer Discretionary') else 0)*dt
    if getattr(a,'symbol','')=='SPY':
        spx=self.get_asset('SPX')
        if spx is not None and float(getattr(spx,'previous_price',0))>0:
            spx_r=float(spx.price)/float(spx.previous_price)-1.0;r=.96*spx_r+.04*r
    return max(-.70,min(.70,r))
Market._asset_return=_sgp25_asset_return

# Opening-bell reset without rebuilding a multi-thousand-row Tk Treeview. The visible-row
# streamer updates CHG% immediately, while the index cache is rebuilt only on a session edge.
def _sgp25_handle_session_transitions(self):
    changed=False;opened_any=False
    for code,assets in self._session_groups24.items():
        try:regular=bool(market_status(code,self.clock.current))
        except Exception:regular=False
        prev=bool(self._session_state24.get(code,regular))
        if regular and not prev:
            for a in assets:
                try:
                    a.previous_close_price=float(getattr(a,'regular_close_price',a.price) or a.price);self._apply_open_gap(a);a.reset_day();a.day_open_timestamp=self.clock.current
                except Exception as e:self.errors.append(f'open baseline {a.symbol}: {e}')
            opened_any=True;changed=True
        elif prev and not regular:
            for a in assets:
                try:a.regular_close_price=float(a.price);a.regular_close_timestamp=self.clock.current
                except Exception:pass
            if code=='US':
                day=self.clock.current.date()
                if self._v24_last_autosave_day!=day and callable(getattr(self,'autosave_callback',None)):
                    self._v24_last_autosave_day=day
                    try:self.autosave_callback('end of trading day')
                    except Exception as e:self.errors.append(f'autosave: {type(e).__name__}: {e}')
            changed=True
        self._session_state24[code]=regular
    if changed:self._v25_rebuild_index_cache()
    if opened_any:self.visual_version+=1
Market._handle_session_transitions24=_sgp25_handle_session_transitions

async def _sgp25_tick(self):
    if not self.running:return
    if self.paused:
        self._last_real_tick=time.monotonic();await asyncio.sleep(.04);return
    now=time.monotonic();real_dt=max(.001,min(.18,now-self._last_real_tick));self._last_real_tick=now
    warp=max(1.0/60.0,min(100.0/60.0,float(getattr(self,'time_warp',1.0/60.0))))
    game_seconds=real_dt*60.0*warp;game_minutes=game_seconds/60.0;changed=False
    try:
        self.clock.advance_seconds(game_seconds);self._handle_session_transitions24();self._update_macro(game_minutes)
        with self._lock:
            assets=self._v20_assets;n=len(assets);updated=set();market_z=random.gauss(0,1);sector_cache={}
            # Small hot set gets smooth quotes regardless of how large the total universe becomes.
            for sym in tuple(self._v25_hot_symbols(now)):
                a=self.get_asset(sym)
                if a is None or a in self.indexes or not self.asset_quote_open(a):continue
                last=self._v20_last_asset_time.get(a.symbol,0.0)
                if now-last<.09:continue
                elapsed=max(.01,min(1.5,now-last));self._v20_last_asset_time[a.symbol]=now
                cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,elapsed*warp,market_z,sector_z)
                state=self.asset_trade_state(a);vol=random.randint(10,7000) if state=='OVERNIGHT ECN' else random.randint(100,50000);old=float(a.price);a.update_price(a.price*max(.75,1+r),vol,self.clock.current);self._v25_note_asset_move(a,old);updated.add(a.symbol);changed=True
            # Broad universe advances in a rotating low-allocation batch. Elapsed time is carried
            # per asset, so reducing quote frequency does not slow its simulated stochastic clock.
            if n:
                start=self._v20_cursor;count=min(int(self._v20_batch),n)
                for j in range(count):
                    a=assets[(start+j)%n]
                    if a.symbol in updated or not self.asset_quote_open(a):continue
                    last=self._v20_last_asset_time.get(a.symbol,now);elapsed=max(.01,min(8.0,now-last));self._v20_last_asset_time[a.symbol]=now
                    cat=getattr(a,'category','OTHER');sector_z=sector_cache.setdefault(cat,random.gauss(0,1));r=self._asset_return(a,elapsed*warp,market_z,sector_z)
                    state=self.asset_trade_state(a);vol=random.randint(10,7000) if state=='OVERNIGHT ECN' else random.randint(100,50000);old=float(a.price);a.update_price(a.price*max(.75,1+r),vol,self.clock.current);self._v25_note_asset_move(a,old);changed=True
                self._v20_cursor=(start+count)%n
            # O(number of indexes), not O(number of constituents), on every index refresh.
            if now-self._v20_last_index>=.22:
                self._v20_last_index=now
                for idx in self.indexes:
                    if not self.asset_regular_open(idx):continue
                    rec=self._v25_index_cache.get(idx.symbol)
                    if not rec or rec.get('den',0)<=0:continue
                    if rec['mode']=='price':ret=rec['num']/rec['den']-1.0
                    else:ret=rec['num']/rec['den']
                    target=max(.0001,float(idx.open_price)*(1+ret));old=float(idx.price);new=old+(target-old)*.28
                    idx.update_price(new,random.randint(1000,100000),self.clock.current);changed=True
            # Order handling remains responsive; freight/geopolitics can be lower cadence.
            if now-self._v20_last_risk>=.12:
                elapsed=now-self._v20_last_risk;self._v20_last_risk=now;gm=elapsed*warp;self._process_orders();self._process_expirations()
                if int(now*4)!=int((now-elapsed)*4):self._update_freight(gm);self._update_geopolitics(gm)
            if now-self._v20_last_housekeeping>=.50:
                self._v20_last_housekeeping=now
                try:self._corporate_action_cycle();self._process_earnings_v16()
                except Exception as e:self.errors.append(f'daily systems: {type(e).__name__}: {e}')
                if hasattr(self,'portfolio') and now-getattr(self,'_last_networth_calc',0)>4.0:
                    self._last_networth_calc=now;self.portfolio.best_net_worth=max(self.portfolio.best_net_worth,self.portfolio.mark_value(self.all_assets()))
            if now-self._v25_last_index_rebuild>30.0:self._v25_rebuild_index_cache()
        if changed and now-self._v25_last_visual>.09:self.visual_version+=1;self._v25_last_visual=now
        self.data_status=f'OPTIMIZED SIM • {warp*60.0:.2f}x • {len(self.stocks):,} stocks • CPI {self.macro["inflation"]:.2f}% • FED {self.macro["policy_rate"]:.2f}%'
    except Exception as e:
        self.errors.append(f'tick v2.5: {type(e).__name__}: {e}')
        if len(self.errors)>100:self.errors=self.errors[-100:]
    await asyncio.sleep(max(.02,float(self.speed)))
Market.tick=_sgp25_tick

# Keep index return caches in sync when a player moves a stock through the liquidity engine.
_exec_liq_v25_base=Market.execute_liquidity_order
def _sgp25_execute_liquidity_order(self,side,a,qty):
    old=float(a.price);out=_exec_liq_v25_base(self,side,a,qty)
    try:self._v25_note_asset_move(a,old)
    except Exception:pass
    return out
Market.execute_liquidity_order=_sgp25_execute_liquidity_order

# Lazy real-data hydration. Do not launch 2,000+ Yahoo/MAX-history requests at login.
def _sgp25_ensure_real_data(self,a,history=False):
    if a is None:return
    sym=getattr(a,'symbol','')
    if not sym or sym in self._v25_quote_loading:return
    self._v25_quote_loading.add(sym)
    def worker():
        try:
            from data import fetch_latest,fetch_history_max
            q=fetch_latest(getattr(a,'data_symbol',sym))
            if q:
                a.last_real_close=float(q.close);a.last_real_timestamp=q.timestamp;a.fundamental_value=max(.0001,float(q.close));self._v25_real_seeded.add(sym)
            if history and not getattr(a,'data_loaded',False):
                candles=fetch_history_max(getattr(a,'data_symbol',sym))
                if candles:
                    with a.data_lock:
                        a.datasets['1d']=candles;a.inception_date=candles[0].timestamp.date().isoformat();a.inception_price=float(candles[0].open);a.data_loaded=True
            self.visual_version+=1
        except Exception as e:
            self.errors.append(f'lazy data {sym}: {e}')
        finally:self._v25_quote_loading.discard(sym)
    threading.Thread(target=worker,daemon=True,name=f'Data-{sym}').start()
Market.ensure_real_data=_sgp25_ensure_real_data

def _sgp25_start_background_loaders(self):
    if getattr(self,'_loader_started',False):return
    self._loader_started=True
    # Prime only the symbols users see immediately; every other asset hydrates lazily when opened.
    priority=['SPY','SPX','NDX','DJI','RUT','VIX','QQQ']
    try:
        for c in getattr(self.ui_app,'charts',[]):
            if getattr(c,'asset',None):priority.append(c.asset.symbol)
        priority.extend(getattr(self.portfolio,'positions',{}).keys())
    except Exception:pass
    for sym in dict.fromkeys(priority):
        a=self.get_asset(sym)
        if a:self.ensure_real_data(a,history=(sym in ('SPY','SPX','NDX','DJI','RUT')))
Market.start_background_loaders=_sgp25_start_background_loaders

# ===== Stock Game Pro 2.5 offline gameplay / explicit snapshot policy =====
def _sgp251_rebase_asset(a,target):
    """Move bundled synthetic starting history onto an account's creation-time quote."""
    try:
        target=max(.000001,float(target));old=max(.000001,float(a.price));factor=target/old
        a.price*=factor;a.open_price*=factor;a.previous_price*=factor;a.high*=factor;a.low*=factor;a.bid*=factor;a.ask*=factor
        seen=set()
        for bars in list(getattr(a,'live_bars',{}).values())+list(getattr(a,'datasets',{}).values()):
            for c in bars:
                ident=id(c)
                if ident in seen:continue
                seen.add(ident);c.open*=factor;c.high*=factor;c.low*=factor;c.close*=factor
        try:
            from collections import deque
            a.history=deque((float(x)*factor for x in a.history),maxlen=getattr(a.history,'maxlen',30000))
        except Exception:pass
        a.last_real_close=target;a.fundamental_value=max(.000001,target)
        a.regular_close_price=target;a.previous_close_price=target
        try:a._reprice_book()
        except Exception:pass
        return True
    except Exception:return False


def _sgp251_load_account_market_seed(self,username=None):
    """Apply only local creation-time data. This method never performs network I/O."""
    try:
        from data import load_account_seed,fetch_macro_cached
        quotes=load_account_seed(username);applied=0
        for a in self.all_assets():
            rec=quotes.get(getattr(a,'data_symbol',a.symbol)) or quotes.get(a.symbol)
            if not isinstance(rec,dict) or rec.get('close') is None:continue
            if _sgp251_rebase_asset(a,rec['close']):
                applied+=1
                try:
                    ts=rec.get('timestamp')
                    if ts:
                        from datetime import datetime as _dt
                        a.last_real_timestamp=_dt.fromisoformat(ts).replace(tzinfo=None)
                except Exception:pass
        macro=fetch_macro_cached()
        if macro:
            self.macro.update({k:v for k,v in macro.items() if k in self.macro});self.real_macro_source='LOCAL CACHE'
        try:self._v25_rebuild_index_cache()
        except Exception:pass
        self.network_playback_enabled=False
        self.data_status=f'OFFLINE PLAY • {applied:,} CREATION-SNAPSHOT QUOTES • NO NETWORK DURING GAMEPLAY'
        return applied
    except Exception as e:
        self.errors.append(f'local market seed: {e}');self.network_playback_enabled=False;self.data_status='OFFLINE PLAY • BUNDLED/CACHED DATA • NO NETWORK DURING GAMEPLAY';return 0
Market.load_account_market_seed=_sgp251_load_account_market_seed


def _sgp251_ensure_real_data(self,a,history=False):
    """Cache-only replacement for the old lazy online hydrator."""
    if a is None:return False
    sym=getattr(a,'symbol','')
    try:
        from data import fetch_latest_cached,fetch_history_max_cached
        q=fetch_latest_cached(getattr(a,'data_symbol',sym))
        if q:
            a.last_real_close=float(q.close);a.last_real_timestamp=q.timestamp
            if not getattr(a,'fundamental_value',None):a.fundamental_value=max(.0001,float(q.close))
            self._v25_real_seeded.add(sym)
        if history and not getattr(a,'data_loaded',False):
            candles=fetch_history_max_cached(getattr(a,'data_symbol',sym))
            if candles:
                with a.data_lock:
                    a.datasets['1d']=list(candles);a.inception_date=candles[0].timestamp.date().isoformat();a.inception_price=float(candles[0].open);a.data_loaded=True
        return bool(q or (history and getattr(a,'data_loaded',False)))
    except Exception as e:
        self.errors.append(f'local data {sym}: {e}');return False
Market.ensure_real_data=_sgp251_ensure_real_data


def _sgp251_load_ipo_history(self,a):
    if a is None:return False
    sym=getattr(a,'symbol','')
    try:
        from data import fetch_history_max_cached
        candles=fetch_history_max_cached(getattr(a,'data_symbol',sym))
        if not candles:
            self.data_status=f'OFFLINE PLAY • NO LOCAL MAX HISTORY FOR {sym} • NO NETWORK REQUEST SENT';return False
        with a.data_lock:
            a.datasets['1d']=list(candles);a.inception_date=candles[0].timestamp.date().isoformat();a.inception_price=float(candles[0].open);a.data_loaded=True
        self.visual_version+=1;self.data_status=f'LOCAL MAX HISTORY • {sym} • {a.inception_date} • OFFLINE PLAY';return True
    except Exception as e:
        self.errors.append(f'local MAX history {sym}: {e}');return False
Market.load_ipo_history=_sgp251_load_ipo_history


def _sgp251_start_background_loaders(self):
    # Deliberately no thread and no downloader. Local data was loaded before the
    # simulation thread started; gameplay is network-silent by design.
    if getattr(self,'_loader_started',False):return
    self._loader_started=True;self.network_playback_enabled=False
    if 'OFFLINE PLAY' not in str(getattr(self,'data_status','')):
        self.data_status='OFFLINE PLAY • LOCAL ACCOUNT SNAPSHOT • NO NETWORK DURING GAMEPLAY'
Market.start_background_loaders=_sgp251_start_background_loaders
Market._background_loader=lambda self: None


# ===== Stock Game Pro 2.5 production manual snapshot application =====
def _sgp25_apply_refreshed_market_snapshot(self,username=None):
    """Apply a freshly downloaded (or cache-fallback) account snapshot in-place.

    Holdings, cost basis, realized P/L, working orders, and options are intentionally left
    untouched. Only market marks/baselines are replaced, which is why the UI requires an
    explicit warning before calling this method. The operation performs no network I/O; the
    download has already completed in data.refresh_account_market_snapshot().
    """
    try:
        from data import load_account_seed,fetch_macro_cached
        quotes=load_account_seed(username);applied=0;now=self.clock.current
        # Keep the simulation thread paused while thousands of symbols are repriced.
        lock=getattr(self,'_lock',None)
        if lock is None:
            class _Null:
                def __enter__(self):return self
                def __exit__(self,*a):return False
            lock=_Null()
        with lock:
            for a in self.all_assets():
                ds=getattr(a,'data_symbol',a.symbol)
                special={'SPX':'^GSPC','NDX':'^NDX','DJI':'^DJI','RUT':'^RUT','VIX':'^VIX'}.get(getattr(a,'symbol',''))
                rec=quotes.get(special) if special else None
                rec=rec or quotes.get(ds) or quotes.get(getattr(a,'symbol',''))
                if not isinstance(rec,dict) or rec.get('close') is None:continue
                try:
                    target=float(rec['close'])
                    if not math.isfinite(target) or target<=0:continue
                    target=max(.000001,min(1.0e12,target))
                    a.previous_price=target;a.price=target;a.open_price=target;a.high=target;a.low=target
                    a.last_real_close=target;a.fundamental_value=target
                    a.regular_close_price=target;a.previous_close_price=target
                    a.volume=max(0,int(rec.get('volume',0) or 0));a.last_market_impact=0.0
                    try:
                        ts=rec.get('timestamp')
                        if ts:
                            from datetime import datetime as _dt
                            dt=_dt.fromisoformat(str(ts).replace('Z','+00:00'))
                            if getattr(dt,'tzinfo',None):dt=dt.replace(tzinfo=None)
                            a.last_real_timestamp=dt
                    except Exception:pass
                    try:a._reprice_book()
                    except Exception:pass
                    self._book_cache_time[a.symbol]=0
                    applied+=1
                except Exception:continue
            # A refresh is a new simulation baseline: market change percentages start from
            # the refreshed marks rather than comparing real-world quotes with the old sim.
            try:self._pct_open_state={a.symbol:self.asset_regular_open(a) for a in self.all_assets()}
            except Exception:pass
            try:self._impact_state.clear();self._liquidity_health.clear()
            except Exception:pass
            try:self._v25_rebuild_index_cache()
            except Exception:pass
            macro=fetch_macro_cached()
            if macro:
                self.macro.update({k:v for k,v in macro.items() if k in self.macro});self.real_macro_source='REFRESHED LOCAL SNAPSHOT'
        self.visual_version+=1;self.network_playback_enabled=False
        self.data_status=f'OFFLINE PLAY • MANUAL SNAPSHOT APPLIED • {applied:,} QUOTES • NO BACKGROUND NETWORK'
        return applied
    except Exception as e:
        self.errors.append(f'manual snapshot apply: {type(e).__name__}: {e}')
        self.network_playback_enabled=False
        return 0
Market.apply_refreshed_market_snapshot=_sgp25_apply_refreshed_market_snapshot

# ===== Stock Game Pro 2.5 production polish: 24/7 daily-session rollover =====
# Exchange-open edge detection never fires for crypto because CRYPTO is open 24/7. Give the
# asset class a real UTC day boundary so CHG% / daily marks reset once per calendar day.
_Market_init_crypto_day25_base=Market.__init__
def _sgp25prod_market_init_crypto_day(self,*args,**kwargs):
    _Market_init_crypto_day25_base(self,*args,**kwargs)
    try:
        et=self.clock.current.replace(tzinfo=ZoneInfo('America/New_York'));self._crypto_utc_day=et.astimezone(timezone.utc).date()
    except Exception:self._crypto_utc_day=self.clock.current.date()
Market.__init__=_sgp25prod_market_init_crypto_day

def _sgp25prod_crypto_day_roll(self):
    try:
        et=self.clock.current.replace(tzinfo=ZoneInfo('America/New_York'));day=et.astimezone(timezone.utc).date()
    except Exception:day=self.clock.current.date()
    old=getattr(self,'_crypto_utc_day',day)
    if day==old:return False
    self._crypto_utc_day=day
    for a in self.crypto:
        try:
            # Preserve the just-finished UTC close, then establish exactly 0.00% at the new day.
            a.previous_close_price=float(a.price);a.regular_close_price=float(a.price);a.reset_day();a.day_open_timestamp=self.clock.current
        except Exception as e:self.errors.append(f'crypto daily reset {getattr(a,"symbol","?")}: {e}')
    self.visual_version+=1
    return True
Market._crypto_day_roll=_sgp25prod_crypto_day_roll

_tick_crypto_day25_base=Market.tick
async def _sgp25prod_tick_crypto_day(self):
    await _tick_crypto_day25_base(self)
    try:self._crypto_day_roll()
    except Exception as e:
        try:self.errors.append(f'crypto UTC day rollover: {e}')
        except Exception:pass
Market.tick=_sgp25prod_tick_crypto_day
