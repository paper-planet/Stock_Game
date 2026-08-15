"""StockGame Pro consolidated core modules. Generated for easier source distribution."""

# ===== markets.py =====
from dataclasses import dataclass
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
@dataclass(frozen=True)
class Session:
    code:str; name:str; tz:str; open_time:time; close_time:time; weekdays:tuple=(0,1,2,3,4)
    def is_open(self,dt=None):
        dt=dt or datetime.now(ZoneInfo(self.tz)); dt=dt.replace(tzinfo=ZoneInfo('America/New_York')) if dt.tzinfo is None else dt
        local=dt.astimezone(ZoneInfo(self.tz)); return local.weekday() in self.weekdays and self.open_time<=local.time().replace(tzinfo=None)<self.close_time
SESSIONS={'US':Session('US','United States','America/New_York',time(9,30),time(16,0)),'EXT':Session('EXT','US Extended','America/New_York',time(4),time(20)),'LSE':Session('LSE','London','Europe/London',time(8),time(16,30)),'XETRA':Session('XETRA','Frankfurt','Europe/Berlin',time(9),time(17,30)),'TSE':Session('TSE','Tokyo','Asia/Tokyo',time(9),time(15,30)),'HKEX':Session('HKEX','Hong Kong','Asia/Hong_Kong',time(9,30),time(16)),'SSE':Session('SSE','Shanghai','Asia/Shanghai',time(9,30),time(15)),'ASX':Session('ASX','Sydney','Australia/Sydney',time(10),time(16)),'FX':Session('FX','Global FX','UTC',time(0),time(23,59,59),(0,1,2,3,4)),'CRYPTO':Session('CRYPTO','Crypto 24/7','UTC',time(0),time(23,59,59),(0,1,2,3,4,5,6)),'CME':Session('CME','CME Futures','America/Chicago',time(17),time(16),(0,1,2,3,4,6))}
def market_status(code,dt=None):
    if code!='CME': return SESSIONS[code].is_open(dt)
    s=SESSIONS[code]; local=(dt or datetime.now(ZoneInfo(s.tz))); local=local.replace(tzinfo=ZoneInfo('America/New_York')) if local.tzinfo is None else local; local=local.astimezone(ZoneInfo(s.tz)); wd=local.weekday(); m=local.hour*60+local.minute
    if wd==5:return False
    if wd==6:return m>=1020
    if wd==4:return m<960
    return not 960<=m<1020


# ===== asset.py =====
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
        self.trade_count=0; self.dollar_volume=0.; self.inception_date=None; self.inception_price=None; self.history.append(self.price)
    def _bucket(self,ts,minutes): return ts.replace(minute=(ts.minute//minutes)*minutes,second=0,microsecond=0)
    def _bucket_seconds(self,ts,seconds):
        seconds=max(1,int(seconds));base=ts.replace(microsecond=0);day0=base.replace(hour=0,minute=0,second=0);elapsed=int((base-day0).total_seconds());return day0+timedelta(seconds=(elapsed//seconds)*seconds)
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
                # Preserve individual simulator prints plus a 30-second stream for professional intraday charting.
                ticks=self.live_bars.setdefault('tick',[]);ticks.append(Candle(ts,self.previous_price,self.price,self.price,self.price,int(max(0,volume))))
                if len(ticks)>30000:del ticks[:-30000]
                b30=self._bucket_seconds(ts,30);bars30=self.live_bars.setdefault('30s',[])
                if not bars30 or bars30[-1].timestamp!=b30:bars30.append(Candle(b30,self.previous_price,self.price,self.price,self.price,int(max(0,volume))))
                else:
                    c30=bars30[-1];c30.high=max(c30.high,self.price);c30.low=min(c30.low,self.price);c30.close=self.price;c30.volume+=int(max(0,volume))
                if len(bars30)>30000:del bars30[:-30000]
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


# ===== universe.py =====
STOCKS=[
('AAPL','Apple','Tech',.0015),('MSFT','Microsoft','Tech',.0015),('NVDA','NVIDIA','Tech',.003),('AMZN','Amazon','Consumer',.002),('META','Meta Platforms','Tech',.0025),('GOOGL','Alphabet A','Tech',.0018),('GOOG','Alphabet C','Tech',.0018),('AVGO','Broadcom','Tech',.0025),('TSLA','Tesla','Consumer',.004),('JPM','JPMorgan Chase','Finance',.0015),('V','Visa','Finance',.0015),('MA','Mastercard','Finance',.0016),('WMT','Walmart','Consumer',.0012),('COST','Costco','Consumer',.0015),('NFLX','Netflix','Media',.003),('ORCL','Oracle','Tech',.002),('CRM','Salesforce','Tech',.002),('AMD','AMD','Tech',.0035),('INTC','Intel','Tech',.0035),('QCOM','Qualcomm','Tech',.0025),('CSCO','Cisco','Tech',.0018),('IBM','IBM','Tech',.0017),('PLTR','Palantir','Tech',.0035),('UBER','Uber','Consumer',.003),('DIS','Disney','Media',.0025),('KO','Coca-Cola','Consumer',.0011),('PEP','PepsiCo','Consumer',.0012),('MCD','McDonald\'s','Consumer',.0014),('NKE','Nike','Consumer',.0022),('XOM','Exxon Mobil','Energy',.002),('CVX','Chevron','Energy',.0018),('GE','GE Aerospace','Industrial',.002),('CAT','Caterpillar','Industrial',.002),('BA','Boeing','Industrial',.003),('JNJ','Johnson & Johnson','Health',.0012),('PFE','Pfizer','Health',.002),('LLY','Eli Lilly','Health',.0022),('UNH','UnitedHealth','Health',.0017),('BAC','Bank of America','Finance',.002),('GS','Goldman Sachs','Finance',.002),('MS','Morgan Stanley','Finance',.0019),('C','Citigroup','Finance',.0021),('WFC','Wells Fargo','Finance',.0018),('COIN','Coinbase','Finance',.0045),('HOOD','Robinhood','Finance',.004),('SHOP','Shopify','Tech',.003),('MSTR','Strategy','Tech',.005),('ARM','Arm Holdings','Tech',.0035),('TSM','Taiwan Semiconductor','Tech',.002),('ASML','ASML','Tech',.0018),('BABA','Alibaba','Consumer',.0025),('NVO','Novo Nordisk','Health',.002),('SAP','SAP','Tech',.0017),('SONY','Sony','Consumer',.002),('TM','Toyota','Consumer',.0017),('GME','GameStop','Consumer',.006),('SPY','SPDR S&P 500 ETF','ETF',.001),('VIX','CBOE Volatility Index','Index',.004)]
COMMODITIES=[('CL=F','Crude Oil','Energy',.003),('BZ=F','Brent Crude','Energy',.003),('GC=F','Gold','Metals',.0015),('SI=F','Silver','Metals',.0025),('HG=F','Copper','Metals',.003),('NG=F','Natural Gas','Energy',.006),('ZC=F','Corn','Agriculture',.002),('ZW=F','Wheat','Agriculture',.0022),('ZS=F','Soybeans','Agriculture',.0022)]
INDEXES=[('SPX','S&P 500',5600,['AAPL','MSFT','NVDA','AMZN','META','JPM'],.0008),('NDX','Nasdaq 100',19500,['MSFT','NVDA','AAPL','AMZN','META'],.001),('DJI','Dow Jones',40500,['AAPL','JPM','WMT','JNJ','GS'],.0007),('RUT','Russell 2000',2200,['BAC','INTC','PFE','GE','WMT'],.0014)]

# International securities use Yahoo-compatible data symbols so MAX history can be
# loaded lazily from the real security history when network access is available.
GLOBAL_STOCKS=[
('SHEL','Shell plc',72,.0018,'Energy','SHEL','LSE','USD'),('BP','BP plc',34,.0020,'Energy','BP','LSE','USD'),
('AZN','AstraZeneca',78,.0017,'Health','AZN','LSE','USD'),('UL','Unilever',61,.0013,'Consumer Staples','UL','LSE','USD'),
('HSBC','HSBC Holdings',58,.0017,'Finance','HSBC','LSE','USD'),('RIO','Rio Tinto',67,.0021,'Materials','RIO','LSE','USD'),
('BHP','BHP Group',54,.0021,'Materials','BHP','ASX','USD'),('TTE','TotalEnergies',68,.0018,'Energy','TTE','XETRA','USD'),
('SNY','Sanofi',51,.0015,'Health','SNY','XETRA','USD'),('NVS','Novartis',118,.0014,'Health','NVS','XETRA','USD'),
('UBS','UBS Group',33,.0019,'Finance','UBS','XETRA','USD'),('DB','Deutsche Bank',19,.0025,'Finance','DB','XETRA','USD'),
('SONY','Sony Group',30,.0020,'Consumer','SONY','TSE','USD'),('TM','Toyota Motor',250,.0017,'Industrial','TM','TSE','USD'),
('HMC','Honda Motor',31,.0018,'Industrial','HMC','TSE','USD'),('MUFG','Mitsubishi UFJ',14,.0018,'Finance','MUFG','TSE','USD'),
('SMFG','Sumitomo Mitsui',16,.0018,'Finance','SMFG','TSE','USD'),('TSM','Taiwan Semiconductor',200,.0020,'Tech','TSM','TSE','USD'),
('ASX','ASE Technology',12,.0023,'Tech','ASX','TSE','USD'),('BABA','Alibaba',120,.0025,'Consumer','BABA','HKEX','USD'),
('JD','JD.com',34,.0027,'Consumer','JD','HKEX','USD'),('BIDU','Baidu',92,.0028,'Tech','BIDU','HKEX','USD'),
('PDD','PDD Holdings',120,.0030,'Consumer','PDD','HKEX','USD'),('NIO','NIO',5,.0048,'Consumer','NIO','HKEX','USD'),
('INFY','Infosys',19,.0018,'Tech','INFY','SSE','USD'),('WIT','Wipro',6,.0020,'Tech','WIT','SSE','USD'),
('IBN','ICICI Bank',30,.0018,'Finance','IBN','SSE','USD'),('HDB','HDFC Bank',66,.0017,'Finance','HDB','SSE','USD'),
('MELI','MercadoLibre',2100,.0027,'Consumer','MELI','US','USD'),('NU','Nu Holdings',14,.0030,'Finance','NU','US','USD'),
('VALE','Vale',11,.0027,'Materials','VALE','US','USD'),('PBR','Petrobras',14,.0028,'Energy','PBR','US','USD'),
('SE','Sea Limited',86,.0030,'Consumer','SE','US','USD'),('GRAB','Grab Holdings',5,.0033,'Consumer','GRAB','US','USD'),
('ZIM','ZIM Integrated Shipping',19,.0040,'Freight','ZIM','US','USD'),('MATX','Matson',133,.0024,'Freight','MATX','US','USD'),
('SBLK','Star Bulk Carriers',21,.0029,'Freight','SBLK','US','USD'),('DAC','Danaos',88,.0026,'Freight','DAC','US','USD'),
('FRO','Frontline',23,.0030,'Freight','FRO','US','USD'),('STNG','Scorpio Tankers',50,.0030,'Freight','STNG','US','USD'),
('UPS','United Parcel Service',125,.0018,'Freight','UPS','US','USD'),('FDX','FedEx',300,.0020,'Freight','FDX','US','USD'),
]

# Public transport / port-operator proxies used by the Global Trader logistics layer.
# Sessions are mapped to the closest supported exchange clock in the simulator.
GLOBAL_STOCKS += [
('AMKBY','A.P. Moller - Maersk ADR',13.5,.0025,'Freight','AMKBY','US','USD'),
('1199.HK','COSCO SHIPPING Ports',5.2,.0025,'Freight','1199.HK','HKEX','HKD'),
('0144.HK','China Merchants Port',13.8,.0022,'Freight','0144.HK','HKEX','HKD'),
('DPW.DU','DP World',16.5,.0022,'Freight','DPW.DU','XETRA','AED'),
('CPA','Copa Holdings',110,.0025,'Air Freight','CPA','US','USD'),
]

EXTRA_COMMODITIES=[
('RB=F','RBOB Gasoline','Energy',.0040),('HO=F','Heating Oil','Energy',.0038),('PA=F','Palladium','Metals',.0035),
('PL=F','Platinum','Metals',.0025),('ALI=F','Aluminum','Metals',.0028),('KC=F','Coffee','Agriculture',.0045),
('SB=F','Sugar','Agriculture',.0038),('CC=F','Cocoa','Agriculture',.0055),('CT=F','Cotton','Agriculture',.0035),
('LE=F','Live Cattle','Agriculture',.0025),('HE=F','Lean Hogs','Agriculture',.0033),('LBS=F','Lumber','Materials',.0045),
]
COMMODITIES += EXTRA_COMMODITIES

GLOBAL_INDEXES=[
('FTSE','FTSE 100',8400,['SHEL','BP','AZN','UL','HSBC','RIO'],.0008,'^FTSE','LSE'),
('DAX','DAX',23500,['SAP','DB','TTE'],.0010,'^GDAXI','XETRA'),('CAC','CAC 40',7800,['TTE','SNY'],.0010,'^FCHI','XETRA'),
('NIKKEI','Nikkei 225',41000,['TM','SONY','HMC','MUFG','SMFG'],.0011,'^N225','TSE'),
('HSI','Hang Seng',25000,['BABA','JD','BIDU'],.0014,'^HSI','HKEX'),('SSEC','Shanghai Composite',3600,['BABA','BIDU'],.0012,'000001.SS','SSE'),
('STOXX50','Euro Stoxx 50',5400,['SAP','DB','TTE','SNY'],.0010,'^STOXX50E','XETRA'),('ASX200','S&P/ASX 200',8600,['BHP'],.0009,'^AXJO','ASX'),
('TSX','S&P/TSX Composite',27500,['SHOP'],.0009,'^GSPTSE','US'),('BOVESPA','Bovespa',137000,['VALE','PBR','NU'],.0014,'^BVSP','US'),
]

# Approximate fallback inception metadata. When online, MAX history replaces this
# with actual daily history and therefore the actual first available trade date/price.
INCEPTION_FALLBACK={
'AAPL':('1980-12-12',0.10),'MSFT':('1986-03-13',0.10),'NVDA':('1999-01-22',0.44),'AMZN':('1997-05-15',1.50),
'META':('2012-05-18',38.0),'GOOGL':('2004-08-19',2.51),'GOOG':('2014-04-03',28.0),'TSLA':('2010-06-29',1.27),
'NFLX':('2002-05-23',1.16),'SPY':('1993-01-29',43.94),'COIN':('2021-04-14',328.28),'HOOD':('2021-07-29',38.0),
'ARM':('2023-09-14',51.0),'GME':('2002-02-13',2.51),'MSTR':('1998-06-11',120.0),'PLTR':('2020-09-30',10.0),
'BTC-USD':('2014-09-17',457.33),'ETH-USD':('2017-11-09',320.88),
}


# ===== news.py =====
import random
COMPANY=[('{s} beats earnings expectations.',.025),('{s} misses earnings expectations.',-.028),('{s} wins a major contract.',.020),('{s} loses a major contract.',-.021),('Analysts upgrade {s}.',.014),('Analysts downgrade {s}.',-.014),('{s} announces a buyback.',.018),('{s} raises guidance.',.023),('{s} warns of weaker demand.',-.024)]
MACRO=[('Inflation prints hotter than expected.',-.012,.025),('Inflation cools more than expected.',.014,-.028),('Economic growth beats expectations.',.010,.004),('Economic growth disappoints.',-.012,-.004),('Geopolitical tensions rise.',-.018,.018),('Global risk appetite improves.',.015,-.008)]
COMMS=[('Crude inventories fall sharply.','CL=F',.030,.014),('Crude inventories rise sharply.','CL=F',-.028,-.012),('Gold demand rises on safe-haven flows.','GC=F',.024,.006),('Copper demand jumps.','HG=F',.028,.010)]
class NewsEvent:
    def __init__(self,headline,symbol=None,impact=0,inflation=0,severity='NORMAL'): self.headline=headline;self.symbol=symbol;self.impact=impact;self.inflation=inflation;self.severity=severity
    def __str__(self): return self.headline
def generate_news(stocks,commodities):
    r=random.random()
    if r<.58:
        a=random.choice(stocks);t,i=random.choice(COMPANY);return NewsEvent(t.format(s=a.symbol),a.symbol,i,0)
    if r<.82:
        t,i,inf=random.choice(MACRO);return NewsEvent(t,None,i,inf,'MACRO')
    t,s,i,inf=random.choice(COMMS);return NewsEvent(t,s,i,inf,'COMMODITY')
def major():
    return NewsEvent(*random.choice([('🚨 Broad risk-off move.',None,-.035,.018),('🚨 Surprise fiscal stimulus boosts growth.',None,.028,-.008),('🚨 Major oil supply shock.','CL=F',-.018,.040),('🚨 Strong economic data sparks a rally.',None,.032,-.010)]),'MAJOR')


# ===== options.py =====
import math,random
from dataclasses import dataclass
CONTRACT_SIZE=100;RISK_FREE=.04
EXPIRATIONS=[('0DTE',0),('1D',1),('3D',3),('7D',7),('14D',14),('30D',30),('45D',45),('60D',60),('90D',180),('1Y',365)]
def norm_pdf(x):return math.exp(-.5*x*x)/math.sqrt(2*math.pi)
def norm_cdf(x):return .5*(1+math.erf(x/math.sqrt(2)))
def bs_all(spot,strike,days,vol,rate,typ):
    spot=max(float(spot),.0001);strike=max(float(strike),.0001);T=max(float(days),.01)/365;vol=max(.05,float(vol));s=math.sqrt(T);d1=(math.log(spot/strike)+(rate+.5*vol*vol)*T)/(vol*s);d2=d1-vol*s
    if typ=='call': price=spot*norm_cdf(d1)-strike*math.exp(-rate*T)*norm_cdf(d2);delta=norm_cdf(d1);theta=(-spot*norm_pdf(d1)*vol/(2*s)-rate*strike*math.exp(-rate*T)*norm_cdf(d2))/365;rho=strike*T*math.exp(-rate*T)*norm_cdf(d2)/100
    else: price=strike*math.exp(-rate*T)*norm_cdf(-d2)-spot*norm_cdf(-d1);delta=norm_cdf(d1)-1;theta=(-spot*norm_pdf(d1)*vol/(2*s)+rate*strike*math.exp(-rate*T)*norm_cdf(-d2))/365;rho=-strike*T*math.exp(-rate*T)*norm_cdf(-d2)/100
    return {'price':max(.005,price),'delta':delta,'gamma':norm_pdf(d1)/(spot*vol*s),'theta':theta,'vega':spot*norm_pdf(d1)*s/100,'rho':rho}
@dataclass
class OptionContract:
    underlying:object;strike:float;days:int;option_type:str;liquidity:float=1.;open_interest:int=0;volume:int=0;expiry_at:object=None
    _stats_cache:object=None
    @property
    def volatility(self):return max(.10,self.underlying.volatility*20+.12+abs(self.strike/self.underlying.price-1)*.30)
    @property
    def stats(self):
        key=(round(self.underlying.price,6),self.strike,self.days,round(self.volatility,6),self.option_type)
        if self._stats_cache and self._stats_cache[0]==key:return self._stats_cache[1]
        value=bs_all(self.underlying.price,self.strike,self.days,self.volatility,RISK_FREE,self.option_type);self._stats_cache=(key,value);return value
    @property
    def premium(self):return self.stats['price']
    @property
    def spread(self):return max(.005,self.premium*(.004+.020*(1-self.liquidity)))
    @property
    def bid(self):return max(.005,self.premium-self.spread/2)
    @property
    def ask(self):return self.premium+self.spread/2
    @property
    def mid(self):return (self.bid+self.ask)/2
    def intrinsic(self,spot):return max(spot-self.strike,0) if self.option_type=='call' else max(self.strike-spot,0)
    def itm(self):return self.intrinsic(self.underlying.price)>0
    def __str__(self):return f'{self.underlying.symbol} {self.option_type.upper()} {self.strike:.0f} {self.days}D'
@dataclass
class StrategyLeg:
    contract:OptionContract;quantity:int;action:str
    @property
    def sign(self):return 1 if self.action=='BUY' else -1
    @property
    def mark(self):return self.contract.ask if self.action=='BUY' else self.contract.bid
    @property
    def cash_flow(self):return -self.sign*self.mark*self.quantity*CONTRACT_SIZE
class OptionStrategy:
    _next_id=1
    def __init__(self,name='Custom'):
        self.name=name;self.legs=[];self.open_cost=0.;self.opened=False;self.strategy_id=None;self.opened_at=None;self.expiry_at=None
    def add_leg(self,c,q,a):
        q=int(q);a=a.upper()
        if q<=0 or q>1000000:raise ValueError('Invalid option quantity.')
        self.legs.append(StrategyLeg(c,q,a))
    def current_value(self):return sum((l.contract.bid if l.action=='BUY' else l.contract.ask)*l.quantity*CONTRACT_SIZE*l.sign for l in self.legs)
    def opening_debit(self):return sum(l.sign*l.mark*l.quantity*CONTRACT_SIZE for l in self.legs)
    def expiration_pnl(self,spot):return sum(l.sign*l.contract.intrinsic(spot)*l.quantity*CONTRACT_SIZE for l in self.legs)-self.open_cost
    def greeks(self):
        r={k:0. for k in ('delta','gamma','theta','vega','rho')}
        for l in self.legs:
            s=l.contract.stats
            for k in r:r[k]+=l.sign*l.quantity*CONTRACT_SIZE*s[k]
        return r
def option_chain(asset,days,span=25):
    p=max(asset.price,.01);center=round(p);out=[]
    for k in sorted(set(max(1,center+i) for i in range(-span,span+1))):
        liq=max(.15,1-abs(k/p-1)*1.8);base=int(1000*liq*random.uniform(.75,1.25));oi=int(5000*liq*random.uniform(.7,1.4));out.extend([OptionContract(asset,k,days,'call',liq,oi,base),OptionContract(asset,k,days,'put',liq,oi,base)])
    return out


# ===== orderbook.py =====
from dataclasses import dataclass
import random
from collections import deque
@dataclass
class BookLevel: price:float;size:int;orders:int;venue:str;market_maker:str;hidden:int=0
class OrderBook:
    def __init__(self,asset,seed=0,levels=12):
        self.asset=asset;self.rng=random.Random(seed+hash(asset.symbol)%100000);self.levels=levels;self.bids=[];self.asks=[];self.last_trade=asset.price;self.trade_size=100;self.imbalance=0.;self.trades=deque(maxlen=300);self.sequence=0;self.update()
    def update(self,mid=None,pressure=0.,vol_mult=1.):
        p=max(.0001,float(mid if mid is not None else self.asset.price));tick=max(.0001,p*.00003);base=max(50,int(1800*max(.15,min(4,vol_mult))*(1+abs(pressure))));self.imbalance=max(-1,min(1,pressure));self.bids=[];self.asks=[];makers=('VIRTEX','ALPHA_MM','NOVA_MM','FLOW_MM','CROSSING','CITADEL_SIM','JUMP_SIM')
        venues=('NYSE','NASDAQ','ARCA','BATS','IEX','EDGX')
        for i in range(1,self.levels+1):
            dist=tick*i*(1+self.rng.random()*.8);skew=pressure*p*.0007;bp=max(.0001,p-dist+skew);ap=max(.0001,p+dist+skew);bs=max(1,int(base/(i**.60)*self.rng.uniform(.55,1.55)*(1+max(0,pressure)*.5)));asz=max(1,int(base/(i**.60)*self.rng.uniform(.55,1.55)*(1+max(0,-pressure)*.5)));self.bids.append(BookLevel(bp,bs,self.rng.randint(1,max(2,min(99,bs//8))),self.rng.choice(venues),self.rng.choice(makers),int(bs*self.rng.uniform(.03,.22))));self.asks.append(BookLevel(ap,asz,self.rng.randint(1,max(2,min(99,asz//8))),self.rng.choice(venues),self.rng.choice(makers),int(asz*self.rng.uniform(.03,.22))))
        self.asset.bid=self.bids[0].price;self.asset.ask=self.asks[0].price
        # Simulated consolidated tape. Aggressor probability follows order-flow pressure.
        side='BUY' if self.rng.random()<.5+.35*self.imbalance else 'SELL';lvl=self.asks[0] if side=='BUY' else self.bids[0];size=max(1,int(self.rng.lognormvariate(4.2,1.0)));price=max(.0001,lvl.price+self.rng.gauss(0,tick*.20));self.last_trade=price;self.trade_size=size;self.sequence+=1
        self.trades.append({'seq':self.sequence,'side':side,'price':price,'size':size,'venue':lvl.venue,'maker':lvl.market_maker})
    def snapshot(self):
        bid_depth=sum(x.size for x in self.bids);ask_depth=sum(x.size for x in self.asks);depth_imb=(bid_depth-ask_depth)/max(1,bid_depth+ask_depth)
        return {'bids':self.bids[:],'asks':self.asks[:],'last':self.last_trade,'imbalance':depth_imb,'pressure':self.imbalance,'spread':self.asks[0].price-self.bids[0].price,'bid_depth':bid_depth,'ask_depth':ask_depth}
    def execute(self,side,qty,limit=None):
        remaining=int(max(0,qty));fills=[];levels=self.asks if side.upper() in ('BUY','COVER') else self.bids
        for lvl in levels:
            if limit is not None and ((side.upper() in ('BUY','COVER') and lvl.price>limit) or (side.upper() in ('SELL','SHORT') and lvl.price<limit)):break
            take=min(remaining,lvl.size)
            if take:fills.append((lvl.price,take,lvl.market_maker,lvl.venue));remaining-=take
            if remaining<=0:break
        if fills:self.last_trade=fills[-1][0]
        return fills,remaining
    def level3(self):
        rows=[]
        for side,levels in [('ASK',self.asks),('BID',self.bids)]:
            for lvl in levels:
                rem=lvl.size;count=max(1,min(lvl.orders,20))
                for n in range(count):
                    size=max(1,rem//max(1,count-n));rem=max(0,rem-size);rows.append((side,lvl.price,size,lvl.market_maker,f'{lvl.venue}-{n%4+1}',n+1,lvl.hidden if n==0 else 0));
                    if rem<=0:break
        return rows


# ===== portfolio.py =====
class Portfolio:
    def __init__(self,cash=100_000_000):
        self.cash=float(cash);self.positions={};self.cost_basis={};self.options=[];self.realized=0.;self.reserved_margin=0.;self.orders=[];self.trade_count=0;self.best_net_worth=float(cash);self.market=None;self._option_cache={};self._option_cache_version=0
    def _qty(self,sym):return int(self.positions.get(sym,0))
    def buy_asset(self,a,qty):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        if q<=0:return False,'Quantity must be positive.'
        cost=a.ask*q
        if cost>self.cash:return False,f'Insufficient cash. Need ${cost:,.2f}.'
        old=self._qty(a.symbol);self.cash-=cost;self.positions[a.symbol]=old+q;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+cost;self.trade_count+=1;return True,f'Bought {q:,} {a.symbol} @ ${a.ask:.2f}'
    def sell_asset(self,a,qty):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        owned=self._qty(a.symbol)
        if q<=0:return False,'Quantity must be positive.'
        if owned<=0:return False,f'No long {a.symbol} position.'
        if q>owned:return False,f'Only {owned:,} shares are held.'
        proceeds=a.bid*q;basis=self.cost_basis.get(a.symbol,0)*(q/owned);self.cash+=proceeds;self.realized+=proceeds-basis;remain=owned-q
        if remain:self.positions[a.symbol]=remain;self.cost_basis[a.symbol]=max(0,self.cost_basis.get(a.symbol,0)-basis)
        else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
        self.trade_count+=1;return True,f'Sold {q:,} {a.symbol} @ ${a.bid:.2f}'
    def short_asset(self,a,qty,margin_rate=.5):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        if q<=0:return False,'Quantity must be positive.'
        req=a.price*q*margin_rate
        if self.cash<req:return False,f'Margin required ${req:,.2f}; available ${self.cash:,.2f}.'
        old=self._qty(a.symbol);self.positions[a.symbol]=old-q;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+a.bid*q;self.cash+=a.bid*q;self.reserved_margin+=req;self.trade_count+=1;return True,f'Shorted {q:,} {a.symbol} @ ${a.bid:.2f} — margin ${req:,.2f}'
    def cover_short(self,a,qty):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        short=-self._qty(a.symbol)
        if short<=0:return False,'No short position.'
        if q<=0 or q>short:return False,f'Short position is {short:,} shares.'
        cost=a.ask*q;self.cash-=cost;entry=self.cost_basis.get(a.symbol,0)*(q/short);self.realized+=entry-cost;remain=short-q;self.reserved_margin=max(0,self.reserved_margin-a.price*q*.5)
        if remain:self.positions[a.symbol]=-remain;self.cost_basis[a.symbol]=max(0,self.cost_basis.get(a.symbol,0)-entry)
        else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
        self.trade_count+=1;return True,f'Covered {q:,} {a.symbol} @ ${a.ask:.2f}'
    def execute_strategy(self,s):
        debit=s.opening_debit();margin=max(0,-debit*1.5)
        if debit>self.cash:return False,f'Insufficient cash. Need ${debit:,.2f}.'
        if debit<0 and self.cash+(-debit)<margin:return False,f'Short option margin required ${margin:,.2f}.'
        now=getattr(getattr(self,'market',None),'clock',None)
        now=getattr(now,'current',None) or datetime.now()
        s.opened_at=now
        expiries=[]
        for leg in s.legs:
            c=leg.contract
            if getattr(c,'expiry_at',None) is None:
                if int(c.days)<=0:
                    close=now.replace(hour=16,minute=0,second=0,microsecond=0)
                    c.expiry_at=close if close>now else now+timedelta(minutes=1)
                else:c.expiry_at=now+timedelta(days=float(c.days))
            expiries.append(c.expiry_at)
        s.expiry_at=min(expiries) if expiries else None
        self.cash-=debit;self.reserved_margin+=margin;s.open_cost=debit;s.opened=True
        if getattr(s,'strategy_id',None) is None:s.strategy_id=OptionStrategy._next_id;OptionStrategy._next_id+=1
        self.options.append(s);self._option_cache_version+=1;self._option_cache.clear();self.trade_count+=1;return True,f'Opened {s.name}: ${debit:,.2f} net cash flow'
    def liquidate_strategy(self,ref):
        s=self.get_strategy(ref)
        if s is None:return False,'Invalid strategy.'
        try:self.options.remove(s)
        except ValueError:return False,'Strategy is no longer open.'
        self._option_cache_version+=1;self._option_cache.clear()
        proceeds=s.current_value();self.cash+=proceeds;self.realized+=proceeds-s.open_cost;self.reserved_margin=max(0,self.reserved_margin);self.trade_count+=1;return True,f'Liquidated {s.name}: ${proceeds-s.open_cost:,.2f} P/L'
    def liquidate_asset(self,a):q=self._qty(a.symbol);return self.sell_asset(a,q) if q>0 else self.cover_short(a,-q) if q<0 else (False,'No position.')
    def apply_corporate_actions(self,assets):
        for a in assets:
            ratio=getattr(a,'pending_split',None)
            if not ratio:continue
            if a.symbol in self.positions:self.positions[a.symbol]=int(round(self.positions[a.symbol]*ratio))
            for s in self.options:
                for leg in s.legs:
                    if leg.contract.underlying.symbol==a.symbol:leg.contract.strike/=ratio
            a.pending_split=None
    def _asset_map(self,assets=None):
        if getattr(self,'market',None) is not None and hasattr(self.market,'get_asset'):
            return None
        return {a.symbol:a for a in (assets or [])}
    def option_legs_for(self,symbol):
        key=str(symbol)
        cached=self._option_cache.get(key)
        if cached is not None:return cached
        out=[]
        for st in self.options:
            for leg in st.legs:
                if leg.contract.underlying.symbol==key:out.append((st,leg))
        self._option_cache[key]=out;return out
    def invalidate_option_cache(self):self._option_cache_version+=1;self._option_cache.clear()
    def get_strategy(self,ref):
        """Resolve an option strategy by stable id, tree iid (OPT:id), or legacy index."""
        if isinstance(ref,OptionStrategy):return ref
        token=str(ref)
        if token.startswith('OPT:'):token=token.split(':',1)[1]
        for st in self.options:
            if str(getattr(st,'strategy_id',''))==token:return st
        try:
            idx=int(token)
            if 0<=idx<len(self.options):return self.options[idx]
        except Exception:pass
        return None
    def strategy_ref(self,st):
        sid=getattr(st,'strategy_id',None)
        return f'OPT:{sid}' if sid is not None else f'OPT:{self.options.index(st)}'
    def mark_value(self,assets):
        total=self.cash; amap=self._asset_map(assets)
        for sym,q in self.positions.items():
            a=self.market.get_asset(sym) if getattr(self,'market',None) is not None else amap.get(sym)
            if a:total+=q*a.price
        for st in self.options:total+=st.current_value()
        return total
    def _strategy_display_symbol(self,st):
        if not st.legs:return 'OPTION'
        legs=st.legs;under=legs[0].contract.underlying.symbol
        if len(legs)==1:
            l=legs[0];c=l.contract;side='+' if l.action=='BUY' else '-';return f'{under} {side}{l.quantity} {c.option_type[0].upper()}{c.strike:g}'
        calls=sum(1 for l in legs if l.contract.option_type=='call');puts=len(legs)-calls
        return f'{under} {len(legs)}L {calls}C/{puts}P'
    def position_rows(self,assets):
        rows=[];amap=self._asset_map(assets)
        for sym,q in list(self.positions.items()):
            if not q:continue
            a=self.market.get_asset(sym) if getattr(self,'market',None) is not None else amap.get(sym)
            if not a:continue
            basis=self.cost_basis.get(sym,0);value=q*a.price;pnl=(value-basis) if q>0 else (basis+value);rows.append((sym,a.name,q,a.price,value,pnl,'LONG' if q>0 else 'SHORT','',0))
        for st in list(self.options):
            if not st.legs:continue
            first=st.legs[0].contract;under=first.underlying.symbol;label=self._strategy_display_symbol(st)
            total_qty=max(1,sum(abs(l.quantity) for l in st.legs));v=st.current_value();rows.append((self.strategy_ref(st),label,total_qty,v,v,v-st.open_cost,'OPTION',under,min((l.contract.days for l in st.legs),default=0)))
        return rows
    def option_time_remaining(self,ref,now=None):
        st=self.get_strategy(ref)
        if st is None:return '—',0.0
        now=now or (getattr(getattr(self,'market',None),'clock',None) and self.market.clock.current) or datetime.now()
        exp=getattr(st,'expiry_at',None)
        if exp is None:
            days=min((max(0,float(l.contract.days)) for l in st.legs),default=0);exp=now+timedelta(days=days);st.expiry_at=exp
        sec=max(0.0,(exp-now).total_seconds());days=sec/86400.0
        if sec<=0:return 'EXPIRED',0.0
        if sec<3600:return f'{int(sec//60)}m {int(sec%60):02d}s',days
        if sec<86400:return f'{int(sec//3600)}h {int((sec%3600)//60):02d}m',days
        return f'{int(sec//86400)}d {int((sec%86400)//3600):02d}h',days

    def summary(self,assets):
        lines=[f'CASH        ${self.cash:,.2f}',f'REALIZED    ${self.realized:,.2f}',f'MARGIN USED ${self.reserved_margin:,.2f}',f'NET WORTH   ${self.mark_value(assets):,.2f}','','POSITIONS'];rows=self.position_rows(assets)
        if not rows:lines.append('None')
        for sym,name,q,price,value,pnl,typ,under,days in rows:lines.append(f'{sym:<10} {q:>10,}  ${value:>15,.2f}  P/L ${pnl:>12,.2f}  {typ}'+(f'  {days}D' if typ=='OPTION' else ''))
        return '\n'.join(lines)


# ===== traders.py =====
import asyncio,random
class Trader:
    def __init__(self,name,kind,cash):self.name=name;self.kind=kind;self.cash=cash;self.positions={}
    async def think(self,market,news):
        await asyncio.sleep(random.uniform(.001,.012));asset=market.get_asset(news.symbol) if news and news.symbol else random.choice(market.stocks);bias={'Momentum':.02,'Value':-.02,'Prop':.01}.get(self.kind,0);signal=asset.change_percent()/100+bias+(news.impact*2 if news and news.symbol==asset.symbol else 0);return asset,('BUY' if random.random()<.5+max(-.3,min(.3,signal*4)) else 'SELL'),random.randint(10,600)
def create_traders():
    kinds=['Retail','Momentum','Value','Bank','Prop','Macro'];return [Trader(f'{k}-{i}',k,random.randint(100_000,10_000_000)) for i in range(120) for k in [random.choice(kinds)]]


# ===== account.py =====
import json,time
from pathlib import Path
APP_DIR=Path.home()/'.stock_game_pro';ACCOUNTS=APP_DIR/'accounts.json'
class AccountManager:
    def __init__(self,path=ACCOUNTS): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.accounts=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text())
        except Exception:return {}
    def _save(self):
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.accounts,indent=2));tmp.replace(self.path)
    def create(self,username,mode):
        username=username.strip().lower()
        if not username:return False,'Username is required.'
        if username in self.accounts:return False,'That account already exists.'
        cash={'EASY':50000,'MEDIUM':250000,'EXPERT':1000000}.get(mode,250000)
        self.accounts[username]={'mode':mode,'cash':cash,'created':time.time(),'stats':{'trades':0,'realized':0.0,'best_net_worth':cash}}
        self._save();return True,'Account created.'
    def login(self,username):
        username=username.strip().lower();rec=self.accounts.get(username)
        if not rec:return None
        return dict(rec,username=username)
    def delete(self,username):
        username=username.strip().lower()
        if username not in self.accounts:return False,'Account not found.'
        del self.accounts[username];self._save();return True,'Account deleted.'
    def save_session(self,username,cash,mode,stats):
        if username not in self.accounts:return
        rec=self.accounts[username];rec.update(cash=float(cash),mode=mode,stats=stats,last_login=time.time());self._save()


# ===== data.py =====
"""Small dependency-free market-data bridge. Network failures are non-fatal."""
import json,time,urllib.parse,urllib.request,threading
from datetime import datetime,timezone

USER_AGENT='Mozilla/5.0 STOCK_GAME/11.1'
def _url(symbol,p1=0,interval='1d'):return f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe="")}?period1={int(p1)}&period2={int(time.time())}&interval={interval}&events=history&includeAdjustedClose=true'
def fetch_history(symbol,period1=0,interval='1d',timeout=5):
    try:
        req=urllib.request.Request(_url(symbol,period1,interval),headers={'User-Agent':USER_AGENT})
        with urllib.request.urlopen(req,timeout=timeout) as r:payload=json.load(r)
        result=(payload.get('chart',{}).get('result') or [None])[0]
        if not result:return []
        ts=result.get('timestamp') or [];q=(result.get('indicators',{}).get('quote') or [{}])[0];fields=[q.get(k) or [] for k in ('open','high','low','close','volume')];out=[]
        for i,t in enumerate(ts):
            if any(i>=len(x) or x[i] is None for x in fields[:4]):continue
            dt=datetime.fromtimestamp(t,tz=timezone.utc).replace(tzinfo=None);out.append(Candle(dt,float(fields[0][i]),float(fields[1][i]),float(fields[2][i]),float(fields[3][i]),int(fields[4][i] or 0) if i<len(fields[4]) else 0))
        return out
    except Exception:return []
def fetch_latest(symbol,timeout=5):
    c=fetch_history(symbol,max(0,int(time.time())-45*86400),'1d',timeout);return c[-1] if c else None
def fetch_many_latest(symbols,workers=8):
    out={};lock=threading.Lock();threads=[]
    def worker(sym):
        c=fetch_latest(sym)
        if c:
            with lock:out[sym]=c
    for sym in symbols:
        t=threading.Thread(target=worker,args=(sym,),daemon=True);t.start();threads.append(t)
    for t in threads:t.join(timeout=6)
    return out


# ===== Stock Game Pro 1.0 production performance / portfolio patches =====
import time as _sgp_perf_time

def _sgp_strategy_mark(self):
    now=_sgp_perf_time.monotonic()
    key=tuple((round(l.contract.underlying.price,3),round(float(l.contract.days),4),round(float(l.contract.strike),4),l.contract.option_type,l.action,int(l.quantity)) for l in self.legs)
    cache=getattr(self,'_sgp_mark_cache',None)
    if cache and now-cache[0] < .12 and cache[1]==key:
        return cache[2]
    value=sum((l.contract.bid if l.action=='BUY' else l.contract.ask)*l.quantity*CONTRACT_SIZE*l.sign for l in self.legs)
    self._sgp_mark_cache=(now,key,value)
    return value
OptionStrategy.current_value=_sgp_strategy_mark

def _sgp_strategy_greeks(self):
    now=_sgp_perf_time.monotonic()
    key=tuple((round(l.contract.underlying.price,3),round(float(l.contract.days),4),round(float(l.contract.strike),4),l.contract.option_type,l.action,int(l.quantity)) for l in self.legs)
    cache=getattr(self,'_sgp_greek_cache',None)
    if cache and now-cache[0] < .18 and cache[1]==key:
        return dict(cache[2])
    r={k:0. for k in ('delta','gamma','theta','vega','rho')}
    for l in self.legs:
        s=l.contract.stats
        for k in r:r[k]+=l.sign*l.quantity*CONTRACT_SIZE*s[k]
    self._sgp_greek_cache=(now,key,dict(r))
    return r
OptionStrategy.greeks=_sgp_strategy_greeks

def _sgp_option_return_pct(self,st,current_value=None):
    if st is None:return 0.0
    value=st.current_value() if current_value is None else float(current_value)
    pnl=value-float(getattr(st,'open_cost',0.0))
    open_cost=float(getattr(st,'open_cost',0.0))
    # Long/debit strategies use premium paid as capital at risk. A fully worthless
    # long option therefore reports -100%, not -1%. Credit structures use a
    # conservative simulated margin denominator instead of dividing by a credit.
    capital=abs(open_cost) if open_cost>0 else max(abs(open_cost)*1.5,1.0)
    return pnl/max(capital,1e-9)
Portfolio.option_return_pct=_sgp_option_return_pct

# ===== Stock Game Pro 1.3 global universe / trading-session patch =====
# Additional liquid international listings / ADRs with Yahoo-compatible history symbols.
# These extend the existing universe without changing older saved-position symbols.
_SGP_V13_GLOBAL_STOCKS=[
('VOD.L','Vodafone Group',0.74,.0020,'Telecom','VOD.L','LSE','GBP'),('BARC.L','Barclays',3.20,.0022,'Finance','BARC.L','LSE','GBP'),
('LLOY.L','Lloyds Banking Group',0.82,.0020,'Finance','LLOY.L','LSE','GBP'),('RR.L','Rolls-Royce Holdings',10.5,.0025,'Industrial','RR.L','LSE','GBP'),
('GLEN.L','Glencore',3.20,.0028,'Materials','GLEN.L','LSE','GBP'),('DGE.L','Diageo',19.0,.0015,'Consumer Staples','DGE.L','LSE','GBP'),
('SIE.DE','Siemens',230,.0018,'Industrial','SIE.DE','XETRA','EUR'),('ALV.DE','Allianz',360,.0015,'Finance','ALV.DE','XETRA','EUR'),
('BMW.DE','BMW',88,.0020,'Auto','BMW.DE','XETRA','EUR'),('MBG.DE','Mercedes-Benz Group',56,.0020,'Auto','MBG.DE','XETRA','EUR'),
('BAS.DE','BASF',46,.0020,'Materials','BAS.DE','XETRA','EUR'),('ADS.DE','Adidas',170,.0023,'Consumer','ADS.DE','XETRA','EUR'),
('AIR.PA','Airbus',180,.0019,'Industrial','AIR.PA','XETRA','EUR'),('MC.PA','LVMH',500,.0019,'Consumer','MC.PA','XETRA','EUR'),
('OR.PA','LOréal',390,.0016,'Consumer','OR.PA','XETRA','EUR'),('SAN.PA','Sanofi',84,.0014,'Health','SAN.PA','XETRA','EUR'),
('7203.T','Toyota Motor Japan',2800,.0017,'Industrial','7203.T','TSE','JPY'),('6758.T','Sony Group Japan',3800,.0020,'Consumer','6758.T','TSE','JPY'),
('9984.T','SoftBank Group',16000,.0028,'Tech','9984.T','TSE','JPY'),('8306.T','Mitsubishi UFJ Financial',2200,.0018,'Finance','8306.T','TSE','JPY'),
('6861.T','Keyence',58000,.0018,'Tech','6861.T','TSE','JPY'),('8035.T','Tokyo Electron',26000,.0025,'Tech','8035.T','TSE','JPY'),
('0700.HK','Tencent Holdings',620,.0022,'Tech','0700.HK','HKEX','HKD'),('9988.HK','Alibaba HK',120,.0025,'Consumer','9988.HK','HKEX','HKD'),
('3690.HK','Meituan',125,.0030,'Consumer','3690.HK','HKEX','HKD'),('1810.HK','Xiaomi',55,.0030,'Tech','1810.HK','HKEX','HKD'),
('0005.HK','HSBC HK',98,.0017,'Finance','0005.HK','HKEX','HKD'),('1299.HK','AIA Group',75,.0018,'Finance','1299.HK','HKEX','HKD'),
('CBA.AX','Commonwealth Bank',180,.0015,'Finance','CBA.AX','ASX','AUD'),('BHP.AX','BHP Australia',41,.0021,'Materials','BHP.AX','ASX','AUD'),
('CSL.AX','CSL',190,.0018,'Health','CSL.AX','ASX','AUD'),('WES.AX','Wesfarmers',85,.0016,'Consumer','WES.AX','ASX','AUD'),
('RELIANCE.NS','Reliance Industries',1450,.0020,'Energy','RELIANCE.NS','NSE','INR'),('TCS.NS','Tata Consultancy Services',3100,.0018,'Tech','TCS.NS','NSE','INR'),
('INFY.NS','Infosys India',1450,.0019,'Tech','INFY.NS','NSE','INR'),('HDFCBANK.NS','HDFC Bank India',2000,.0017,'Finance','HDFCBANK.NS','NSE','INR'),
('VALE3.SA','Vale Brazil',56,.0026,'Materials','VALE3.SA','B3','BRL'),('PETR4.SA','Petrobras Brazil',32,.0028,'Energy','PETR4.SA','B3','BRL'),
('SHOP.TO','Shopify Canada',205,.0028,'Tech','SHOP.TO','TSX','CAD'),('RY.TO','Royal Bank of Canada',205,.0015,'Finance','RY.TO','TSX','CAD'),
# Listed port / terminal operators used by Global Trader.
('HHFA.DE','Hamburger Hafen und Logistik',22,.0021,'Port Operator','HHFA.DE','XETRA','EUR'),
('ICT.PS','International Container Terminal Services',500,.0023,'Port Operator','ICT.PS','PSE','PHP'),
('ADANIPORTS.NS','Adani Ports & SEZ',1350,.0025,'Port Operator','ADANIPORTS.NS','NSE','INR'),
('STBP3.SA','Santos Brasil',13,.0024,'Port Operator','STBP3.SA','B3','BRL'),
('5246.KL','Westports Holdings',5.2,.0020,'Port Operator','5246.KL','MYX','MYR'),
('POT.NZ','Port of Tauranga',7.2,.0019,'Port Operator','POT.NZ','NZX','NZD'),
]
# Additional local exchange clocks used by the expanded international universe.
SESSIONS.update({
    'NSE':Session('NSE','India NSE','Asia/Kolkata',__import__('datetime').time(9,15),__import__('datetime').time(15,30)),
    'B3':Session('B3','Brazil B3','America/Sao_Paulo',__import__('datetime').time(10),__import__('datetime').time(17)),
    'TSX':Session('TSX','Toronto','America/Toronto',__import__('datetime').time(9,30),__import__('datetime').time(16)),
    'PSE':Session('PSE','Philippines','Asia/Manila',__import__('datetime').time(9,30),__import__('datetime').time(15)),
    'MYX':Session('MYX','Malaysia','Asia/Kuala_Lumpur',__import__('datetime').time(9),__import__('datetime').time(17)),
    'NZX':Session('NZX','New Zealand','Pacific/Auckland',__import__('datetime').time(10),__import__('datetime').time(16,45)),
})

_seen={x[0] for x in GLOBAL_STOCKS}
GLOBAL_STOCKS += [x for x in _SGP_V13_GLOBAL_STOCKS if x[0] not in _seen]

# Market-aware enforcement for immediate stock and option actions.  Stock trading
# can use the simulator's global overnight ECN; listed options remain regular-session only.
_SGP_buy_asset_v13=Portfolio.buy_asset
_SGP_sell_asset_v13=Portfolio.sell_asset
_SGP_short_asset_v13=Portfolio.short_asset
_SGP_cover_short_v13=Portfolio.cover_short
_SGP_execute_strategy_v13=Portfolio.execute_strategy

def _sgp_stock_gate(self,a):
    market=getattr(self,'market',None)
    if market is not None and hasattr(market,'stock_trading_allowed') and not market.stock_trading_allowed(a):
        state=getattr(market,'asset_trade_state',lambda x:'CLOSED')(a)
        return False,f'{a.symbol} stock trading is {state}. Queue an order or wait for a tradable session.'
    return None

def _v13_buy(self,a,qty):
    gate=_sgp_stock_gate(self,a)
    return gate if gate else _SGP_buy_asset_v13(self,a,qty)
def _v13_sell(self,a,qty):
    gate=_sgp_stock_gate(self,a)
    return gate if gate else _SGP_sell_asset_v13(self,a,qty)
def _v13_short(self,a,qty,margin_rate=.5):
    gate=_sgp_stock_gate(self,a)
    return gate if gate else _SGP_short_asset_v13(self,a,qty,margin_rate)
def _v13_cover(self,a,qty):
    gate=_sgp_stock_gate(self,a)
    return gate if gate else _SGP_cover_short_v13(self,a,qty)

def _v13_execute_strategy(self,s):
    market=getattr(self,'market',None)
    under=s.legs[0].contract.underlying if getattr(s,'legs',None) else None
    if market is not None and under is not None and hasattr(market,'asset_regular_open') and not market.asset_regular_open(under):
        # Listed options never execute in the overnight ECN; queue the complete strategy
        # as a market-on-open working order instead.
        market.submit_spread_pending('BUY',s,'MARKET',None)
        return True,f'Options market closed for {under.symbol}; strategy queued for the next regular open.'
    return _SGP_execute_strategy_v13(self,s)

Portfolio.buy_asset=_v13_buy;Portfolio.sell_asset=_v13_sell;Portfolio.short_asset=_v13_short;Portfolio.cover_short=_v13_cover;Portfolio.execute_strategy=_v13_execute_strategy

# ===== Stock Game Pro 1.5 career / credit progression =====
# Difficulty now follows the expected game convention: easier modes provide more starting capital.
_SGP_STARTING_CASH={'EASY':1_000_000.0,'MEDIUM':250_000.0,'EXPERT':50_000.0}

_AccountManager_create_v15_base=AccountManager.create
_AccountManager_login_v15_base=AccountManager.login
_AccountManager_save_v15_base=AccountManager.save_session

def _sgp_account_defaults_v15(rec):
    rec.setdefault('xp',0)
    rec.setdefault('credit_score',700)
    rec.setdefault('loan_balance',0.0)
    rec.setdefault('loan_apr',0.0)
    rec.setdefault('loan_origin',None)
    rec.setdefault('last_loan_payment',None)
    rec.setdefault('tutorials',{})
    rec.setdefault('career',{'level':1,'boss_bonuses':0,'work_earnings':0.0,'loan_payments':0.0})
    return rec

def _sgp_create_v15(self,username,mode):
    username=username.strip().lower()
    if not username:return False,'Username is required.'
    if username in self.accounts:return False,'That account already exists.'
    cash=_SGP_STARTING_CASH.get(mode,250_000.0)
    self.accounts[username]=_sgp_account_defaults_v15({'mode':mode,'cash':cash,'created':time.time(),'stats':{'trades':0,'realized':0.0,'best_net_worth':cash}})
    self._save();return True,'Account created.'

def _sgp_login_v15(self,username):
    username=username.strip().lower();rec=self.accounts.get(username)
    if not rec:return None
    _sgp_account_defaults_v15(rec);self._save()
    return dict(rec,username=username)

def _sgp_save_v15(self,username,cash,mode,stats):
    if username not in self.accounts:return
    rec=_sgp_account_defaults_v15(self.accounts[username]);rec.update(cash=float(cash),mode=mode,stats=stats,last_login=time.time());self._save()

def _sgp_save_profile_state_v15(self,username,portfolio):
    if not username or username not in self.accounts:return
    rec=_sgp_account_defaults_v15(self.accounts[username])
    rec['cash']=float(portfolio.cash);rec['xp']=int(getattr(portfolio,'xp',0));rec['credit_score']=int(getattr(portfolio,'credit_score',700));rec['loan_balance']=float(getattr(portfolio,'loan_balance',0.0));rec['loan_apr']=float(getattr(portfolio,'loan_apr',0.0));rec['loan_origin']=getattr(portfolio,'loan_origin',None);rec['last_loan_payment']=getattr(portfolio,'last_loan_payment',None);rec['tutorials']=dict(getattr(portfolio,'tutorials',{}));rec['career']=dict(getattr(portfolio,'career',{}));self._save()

AccountManager.create=_sgp_create_v15
AccountManager.login=_sgp_login_v15
AccountManager.save_session=_sgp_save_v15
AccountManager.save_profile_state=_sgp_save_profile_state_v15

_Portfolio_init_v15_base=Portfolio.__init__
def _sgp_portfolio_init_v15(self,cash=100_000_000):
    _Portfolio_init_v15_base(self,cash)
    self.xp=0;self.credit_score=700;self.loan_balance=0.0;self.loan_apr=0.0;self.loan_origin=None;self.last_loan_payment=None;self.tutorials={};self.career={'level':1,'boss_bonuses':0,'work_earnings':0.0,'loan_payments':0.0};self._networth_cache=(0.0,float(cash))
Portfolio.__init__=_sgp_portfolio_init_v15

def _sgp_level_from_xp_v15(xp):
    # Negative XP is allowed. Levels do not fall below 1, but the raw XP is always shown.
    return max(1,1+max(0,int(xp))//250)
Portfolio.level=property(lambda self:_sgp_level_from_xp_v15(getattr(self,'xp',0)))

# Cheap mark cache for UI-only surfaces. Order execution / risk calculations still use live marks.
def _sgp_cached_networth_v15(self,assets,max_age=.35):
    import time as _time
    now=_time.monotonic();ts,val=getattr(self,'_networth_cache',(0.0,self.cash))
    if now-ts<=max_age:return val
    val=self.mark_value(assets);self._networth_cache=(now,val);return val
Portfolio.cached_net_worth=_sgp_cached_networth_v15

_Portfolio_mark_value_v15_base=Portfolio.mark_value
def _sgp_mark_value_v15(self,assets):
    return _Portfolio_mark_value_v15_base(self,assets)-float(getattr(self,'loan_balance',0.0))
Portfolio.mark_value=_sgp_mark_value_v15

# ===== Stock Game Pro 1.9 scenario-aware options / depth =====
# Market-condition experiments affect option IV/spreads and visible order-book depth too.
def _sgp_option_volatility_v19(self):
    mult=max(.10,min(6.0,float(getattr(self.underlying,'scenario_vol_mult',1.0))))
    return max(.05,(self.underlying.volatility*20+.12+abs(self.strike/self.underlying.price-1)*.30)*math.sqrt(mult))
OptionContract.volatility=property(_sgp_option_volatility_v19)

def _sgp_option_spread_v19(self):
    liq=max(.10,min(5.0,float(getattr(self.underlying,'scenario_liquidity',1.0))))
    return max(.005,self.premium*(.004+.020*(1-self.liquidity))/math.sqrt(liq))
OptionContract.spread=property(_sgp_option_spread_v19)
