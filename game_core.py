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
        cash={'EASY':50000,'MEDIUM':25000,'EXPERT':1000}.get(mode,25000)
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
_SGP_STARTING_CASH={'EASY':50_000.0,'MEDIUM':25_000.0,'EXPERT':1_000.0}

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


# ===== Stock Game Pro 2.0 performance + persistent-session overhaul =====
# High-frequency price storage is bounded aggressively so long play sessions do not
# accumulate millions of Candle objects. The live chart still receives every useful
# market print, while long-range bars are updated in place.
from collections import deque as _sgp_deque_v20
import threading as _sgp_threading_v20

_SGP_BAR_LIMITS_V20={'tick':2500,'30s':3000,'1m':5000,'5m':5000,'15m':5000,'1h':7000,'1d':30000}

def _sgp_trim_bar_list_v20(asset,interval):
    bars=asset.live_bars.get(interval)
    if bars is None:return
    lim=_SGP_BAR_LIMITS_V20.get(interval,5000)
    if len(bars)>lim:
        del bars[:-lim]

def _sgp_update_bar_v20(self,interval,minutes,ts,price,volume):
    ts=ts.replace(tzinfo=None) if getattr(ts,'tzinfo',None) else ts
    bucket=self._bucket(ts,minutes)
    bars=self.live_bars.setdefault(interval,[])
    if not bars or bars[-1].timestamp!=bucket:
        bars.append(Candle(bucket,float(self.previous_price),float(price),float(price),float(price),int(max(0,volume))))
    else:
        c=bars[-1];c.high=max(float(c.high),float(price));c.low=min(float(c.low),float(price));c.close=float(price);c.volume+=int(max(0,volume))
    _sgp_trim_bar_list_v20(self,interval)
Asset._update_bar=_sgp_update_bar_v20

def _sgp_update_price_v20(self,new_price,volume=0,timestamp=None,record=True):
    with self.data_lock:
        self.previous_price=float(self.price);self.price=max(.0001,float(new_price));self.high=max(float(self.high),self.price);self.low=min(float(self.low),self.price)
        self.volume+=int(max(0,volume));self.trade_count+=1;self.dollar_volume+=self.price*max(0,int(volume))
        spread=max(self.price*.00008,self.price*self.volatility*.025);self.bid=max(.0001,self.price-spread);self.ask=self.price+spread
        ts=timestamp or datetime.now();ts=ts.replace(tzinfo=None) if getattr(ts,'tzinfo',None) else ts;self.last_update=ts
        # Momentum history does not need one sample for every 25ms engine pass.
        self._history_sample_counter=getattr(self,'_history_sample_counter',0)+1
        if self._history_sample_counter>=4 or not self.history:
            self._history_sample_counter=0;self.history.append(self.price)
        if not record:return
        # One tick Candle per actual asset update, but keep only a bounded recent window.
        ticks=self.live_bars.setdefault('tick',[])
        ticks.append(Candle(ts,self.previous_price,max(self.previous_price,self.price),min(self.previous_price,self.price),self.price,int(max(0,volume))))
        _sgp_trim_bar_list_v20(self,'tick')
        b30=self._bucket_seconds(ts,30);bars30=self.live_bars.setdefault('30s',[])
        if not bars30 or bars30[-1].timestamp!=b30:
            bars30.append(Candle(b30,self.previous_price,max(self.previous_price,self.price),min(self.previous_price,self.price),self.price,int(max(0,volume))))
        else:
            c30=bars30[-1];c30.high=max(c30.high,self.price);c30.low=min(c30.low,self.price);c30.close=self.price;c30.volume+=int(max(0,volume))
        _sgp_trim_bar_list_v20(self,'30s')
        for interval,mins in [('1m',1),('5m',5),('15m',15),('1h',60),('1d',1440)]:self._update_bar(interval,mins,ts,self.price,volume)
        self.candles=deque(self.live_bars.get('1d',[])[-30000:],maxlen=30000)
Asset.update_price=_sgp_update_price_v20

# Full account-state persistence. This supplements the existing lightweight career
# profile save and preserves positions, option strategies and working orders.
def _sgp_dt_iso_v20(v):
    try:return v.isoformat() if v is not None else None
    except Exception:return None

def _sgp_dt_parse_v20(v):
    if not v:return None
    try:return datetime.fromisoformat(v)
    except Exception:return None

def _sgp_strategy_to_state_v20(st):
    return {
        'name':str(getattr(st,'name','Custom')),'strategy_id':getattr(st,'strategy_id',None),
        'open_cost':float(getattr(st,'open_cost',0.0)),'opened':bool(getattr(st,'opened',True)),
        'opened_at':_sgp_dt_iso_v20(getattr(st,'opened_at',None)),'expiry_at':_sgp_dt_iso_v20(getattr(st,'expiry_at',None)),
        'legs':[{'underlying':l.contract.underlying.symbol,'strike':float(l.contract.strike),'days':float(l.contract.days),
                 'option_type':str(l.contract.option_type),'quantity':int(l.quantity),'action':str(l.action),
                 'liquidity':float(getattr(l.contract,'liquidity',1.0)),'open_interest':int(getattr(l.contract,'open_interest',0)),
                 'volume':int(getattr(l.contract,'volume',0)),'expiry_at':_sgp_dt_iso_v20(getattr(l.contract,'expiry_at',None))}
                for l in getattr(st,'legs',[])]}

def _sgp_strategy_from_state_v20(state,market):
    st=OptionStrategy(state.get('name','Custom'));st.strategy_id=state.get('strategy_id');st.open_cost=float(state.get('open_cost',0.0));st.opened=bool(state.get('opened',True));st.opened_at=_sgp_dt_parse_v20(state.get('opened_at'));st.expiry_at=_sgp_dt_parse_v20(state.get('expiry_at'))
    for x in state.get('legs',[]):
        a=market.get_asset(x.get('underlying'))
        if a is None:continue
        c=OptionContract(a,float(x.get('strike',a.price)),int(max(0,float(x.get('days',0)))),str(x.get('option_type','call')),float(x.get('liquidity',1.0)),int(x.get('open_interest',0)),int(x.get('volume',0)),_sgp_dt_parse_v20(x.get('expiry_at')))
        st.add_leg(c,int(x.get('quantity',1)),str(x.get('action','BUY')))
    return st if st.legs else None

def _sgp_account_save_game_state_v20(self,username,portfolio,market,reason='autosave'):
    if not username or username not in self.accounts:return False
    lock=getattr(self,'_sgp_io_lock_v20',None)
    if lock is None:self._sgp_io_lock_v20=_sgp_threading_v20.RLock();lock=self._sgp_io_lock_v20
    with lock:
        rec=_sgp_account_defaults_v15(self.accounts[username]) if '_sgp_account_defaults_v15' in globals() else self.accounts[username]
        state={
            'saved_at':time.time(),'reason':reason,'clock':_sgp_dt_iso_v20(getattr(getattr(market,'clock',None),'current',None)),
            'cash':float(portfolio.cash),'positions':{str(k):int(v) for k,v in portfolio.positions.items()},'cost_basis':{str(k):float(v) for k,v in portfolio.cost_basis.items()},
            'realized':float(portfolio.realized),'reserved_margin':float(portfolio.reserved_margin),'trade_count':int(portfolio.trade_count),'best_net_worth':float(portfolio.best_net_worth),
            'options':[_sgp_strategy_to_state_v20(st) for st in portfolio.options],
            'pending_orders':[{'id':o.get('id'),'side':o.get('side'),'asset':getattr(o.get('asset'),'symbol',None),'qty':int(o.get('qty',0)),'type':o.get('type'),'price':o.get('price'),'position_exit':bool(o.get('position_exit',False))} for o in getattr(market,'pending_orders',[])],
            'pending_option_orders':[{'id':o.get('id'),'side':o.get('side'),'qty':int(o.get('qty',1)),'type':o.get('type'),'price':o.get('price'),'contract':_sgp_strategy_to_state_v20(OptionStrategy('tmp')) if False else {
                'underlying':getattr(getattr(o.get('contract'), 'underlying', None),'symbol',None),'strike':float(getattr(o.get('contract'),'strike',0)),'days':float(getattr(o.get('contract'),'days',0)),'option_type':getattr(o.get('contract'),'option_type','call')
            }} for o in getattr(market,'pending_option_orders',[]) if o.get('contract') is not None],
            'pending_spread_orders':[{'id':o.get('id'),'side':o.get('side'),'type':o.get('type'),'price':o.get('price'),'strategy':_sgp_strategy_to_state_v20(o.get('strategy'))} for o in getattr(market,'pending_spread_orders',[]) if o.get('strategy') is not None],
            'macro':dict(getattr(market,'macro',{}))
        }
        rec['game_state']=state;rec['cash']=float(portfolio.cash);self._save();return True
AccountManager.save_game_state=_sgp_account_save_game_state_v20

def _sgp_account_restore_game_state_v20(self,username,portfolio,market):
    if not username:return False
    rec=self.accounts.get(str(username).lower()) or self.accounts.get(username)
    state=(rec or {}).get('game_state') or {}
    if not state:return False
    portfolio.cash=float(state.get('cash',portfolio.cash));portfolio.positions={str(k):int(v) for k,v in state.get('positions',{}).items()};portfolio.cost_basis={str(k):float(v) for k,v in state.get('cost_basis',{}).items()};portfolio.realized=float(state.get('realized',0.0));portfolio.reserved_margin=float(state.get('reserved_margin',0.0));portfolio.trade_count=int(state.get('trade_count',0));portfolio.best_net_worth=float(state.get('best_net_worth',portfolio.cash))
    portfolio.options=[]
    max_sid=0
    for x in state.get('options',[]):
        st=_sgp_strategy_from_state_v20(x,market)
        if st is not None:portfolio.options.append(st);max_sid=max(max_sid,int(getattr(st,'strategy_id',0) or 0))
    OptionStrategy._next_id=max(OptionStrategy._next_id,max_sid+1);portfolio.invalidate_option_cache()
    market.pending_orders=[];market.pending_option_orders=[];market.pending_spread_orders=[];max_oid=0
    for o in state.get('pending_orders',[]):
        a=market.get_asset(o.get('asset'))
        if a is None:continue
        oid=int(o.get('id') or 0);max_oid=max(max_oid,oid);market.pending_orders.append({'id':oid,'side':o.get('side','BUY'),'asset':a,'qty':int(o.get('qty',0)),'type':o.get('type','LIMIT'),'price':o.get('price'),'position_exit':bool(o.get('position_exit',False))})
    for o in state.get('pending_option_orders',[]):
        cst=o.get('contract',{});a=market.get_asset(cst.get('underlying'))
        if a is None:continue
        c=OptionContract(a,float(cst.get('strike',a.price)),int(max(0,float(cst.get('days',0)))),str(cst.get('option_type','call')));oid=int(o.get('id') or 0);max_oid=max(max_oid,oid);market.pending_option_orders.append({'id':oid,'side':o.get('side','BUY'),'contract':c,'qty':int(o.get('qty',1)),'type':o.get('type','LIMIT'),'price':o.get('price')})
    for o in state.get('pending_spread_orders',[]):
        st=_sgp_strategy_from_state_v20(o.get('strategy',{}),market)
        if st is None:continue
        oid=int(o.get('id') or 0);max_oid=max(max_oid,oid);market.pending_spread_orders.append({'id':oid,'side':o.get('side','BUY'),'strategy':st,'type':o.get('type','LIMIT'),'price':o.get('price')})
    market.order_id=max(int(getattr(market,'order_id',1)),max_oid+1)
    dt=_sgp_dt_parse_v20(state.get('clock'))
    if dt is not None:market.clock.current=dt
    if isinstance(state.get('macro'),dict):market.macro.update(state['macro'])
    return True
AccountManager.restore_game_state=_sgp_account_restore_game_state_v20

# ===== Stock Game Pro 2.1 execution accounting =====
# Portfolio market orders route through Market.execute_liquidity_order so player flow
# consumes depth and changes the simulated quote instead of transacting at a static bid/ask.
def _sgp_market_fill_v21(self,a,side,qty):
    m=getattr(self,'market',None)
    if m is not None and hasattr(m,'execute_liquidity_order'):
        q=m.execute_liquidity_order(side,a,qty);return float(q['vwap']),q
    px=float(a.ask if side in ('BUY','COVER') else a.bid);return px,{'vwap':px,'impact':0.0,'participation':0.0,'shown':qty,'adv':qty}
Portfolio._market_fill_v21=_sgp_market_fill_v21

def _sgp_buy_asset_v21(self,a,qty):
    try:q=int(qty)
    except:return False,'Invalid quantity.'
    if q<=0:return False,'Quantity must be positive.'
    m=getattr(self,'market',None);preview=m.preview_execution('BUY',a,q) if m is not None and hasattr(m,'preview_execution') else {'vwap':a.ask,'impact':0,'participation':0}
    est=float(preview['vwap'])*q
    if est>self.cash:return False,f'Insufficient cash. Estimated sweep cost ${est:,.2f}.'
    px,fill=self._market_fill_v21(a,'BUY',q);cost=px*q;old=self._qty(a.symbol);self.cash-=cost;self.positions[a.symbol]=old+q;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+cost;self.trade_count+=1
    return True,f'Bought {q:,} {a.symbol} • VWAP ${px:,.4f} • impact {fill.get("impact",0)*100:.2f}% • {fill.get("participation",0)*100:.2f}% ADV'
Portfolio.buy_asset=_sgp_buy_asset_v21

def _sgp_sell_asset_v21(self,a,qty):
    try:q=int(qty)
    except:return False,'Invalid quantity.'
    owned=self._qty(a.symbol)
    if q<=0:return False,'Quantity must be positive.'
    if owned<=0:return False,f'No long {a.symbol} position.'
    if q>owned:return False,f'Only {owned:,} shares are held.'
    px,fill=self._market_fill_v21(a,'SELL',q);proceeds=px*q;basis=self.cost_basis.get(a.symbol,0)*(q/owned);self.cash+=proceeds;self.realized+=proceeds-basis;remain=owned-q
    if remain:self.positions[a.symbol]=remain;self.cost_basis[a.symbol]=max(0,self.cost_basis.get(a.symbol,0)-basis)
    else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
    self.trade_count+=1;return True,f'Sold {q:,} {a.symbol} • VWAP ${px:,.4f} • impact {fill.get("impact",0)*100:.2f}% • {fill.get("participation",0)*100:.2f}% ADV'
Portfolio.sell_asset=_sgp_sell_asset_v21

def _sgp_short_asset_v21(self,a,qty,margin_rate=.5):
    try:q=int(qty)
    except:return False,'Invalid quantity.'
    if q<=0:return False,'Quantity must be positive.'
    m=getattr(self,'market',None);preview=m.preview_execution('SHORT',a,q) if m is not None and hasattr(m,'preview_execution') else {'vwap':a.bid,'impact':0,'participation':0}
    req=float(preview['vwap'])*q*margin_rate
    if self.cash<req:return False,f'Margin required about ${req:,.2f}; available ${self.cash:,.2f}.'
    px,fill=self._market_fill_v21(a,'SHORT',q);old=self._qty(a.symbol);self.positions[a.symbol]=old-q;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+px*q;self.cash+=px*q;self.reserved_margin+=req;self.trade_count+=1
    return True,f'Shorted {q:,} {a.symbol} • VWAP ${px:,.4f} • impact {fill.get("impact",0)*100:.2f}% • margin ${req:,.2f}'
Portfolio.short_asset=_sgp_short_asset_v21

def _sgp_cover_short_v21(self,a,qty):
    try:q=int(qty)
    except:return False,'Invalid quantity.'
    short=-self._qty(a.symbol)
    if short<=0:return False,'No short position.'
    if q<=0 or q>short:return False,f'Short position is {short:,} shares.'
    m=getattr(self,'market',None);preview=m.preview_execution('COVER',a,q) if m is not None and hasattr(m,'preview_execution') else {'vwap':a.ask}
    if float(preview['vwap'])*q>self.cash:return False,'Insufficient cash to cover at estimated market-impact price.'
    px,fill=self._market_fill_v21(a,'COVER',q);cost=px*q;self.cash-=cost;entry=self.cost_basis.get(a.symbol,0)*(q/short);self.realized+=entry-cost;remain=short-q;self.reserved_margin=max(0,self.reserved_margin-px*q*.5)
    if remain:self.positions[a.symbol]=-remain;self.cost_basis[a.symbol]=max(0,self.cost_basis.get(a.symbol,0)-entry)
    else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
    self.trade_count+=1;return True,f'Covered {q:,} {a.symbol} • VWAP ${px:,.4f} • impact {fill.get("impact",0)*100:.2f}%'
Portfolio.cover_short=_sgp_cover_short_v21

_set_dataset_v21_base=Asset.set_dataset
def _sgp_set_dataset_v21(self,interval,candles):
    before=float(getattr(self,'price',0.0))
    _set_dataset_v21_base(self,interval,candles)
    if interval=='1d' and candles:
        try:self.fundamental_value=max(.0001,float(candles[-1].close))
        except Exception:pass
Asset.set_dataset=_sgp_set_dataset_v21


# ===== Stock Game Pro 2.2 expanded professional universe =====
# Keep the core list compact enough to render quickly while broadening every major sector.
def _sgp22_extend_unique(seq, rows):
    have={r[0] for r in seq}
    for row in rows:
        if row[0] not in have:
            seq.append(row);have.add(row[0])

_sgp22_extend_unique(STOCKS,[
 ('ADBE','Adobe','Tech',.0022),('NOW','ServiceNow','Tech',.0024),('PANW','Palo Alto Networks','Tech',.0027),('CRWD','CrowdStrike','Tech',.0030),('MU','Micron','Tech',.0030),('TXN','Texas Instruments','Tech',.0018),
 ('HD','Home Depot','Consumer',.0015),('LOW','Lowe\'s','Consumer',.0016),('TGT','Target','Consumer',.0022),('SBUX','Starbucks','Consumer',.0020),('BKNG','Booking Holdings','Consumer',.0019),('ABNB','Airbnb','Consumer',.0028),
 ('ABBV','AbbVie','Health',.0013),('MRK','Merck','Health',.0014),('TMO','Thermo Fisher','Health',.0017),('AMGN','Amgen','Health',.0016),('ISRG','Intuitive Surgical','Health',.0020),
 ('BRK-B','Berkshire Hathaway B','Finance',.0011),('AXP','American Express','Finance',.0016),('BLK','BlackRock','Finance',.0016),('SCHW','Charles Schwab','Finance',.0019),('SPGI','S&P Global','Finance',.0016),
 ('COP','ConocoPhillips','Energy',.0021),('SLB','SLB','Energy',.0022),('EOG','EOG Resources','Energy',.0020),('OXY','Occidental Petroleum','Energy',.0026),
 ('DE','Deere','Industrial',.0018),('HON','Honeywell','Industrial',.0015),('RTX','RTX','Industrial',.0016),('LMT','Lockheed Martin','Industrial',.0015),('UPS','UPS','Industrial',.0017),('FDX','FedEx','Industrial',.0020),
 ('NEE','NextEra Energy','Utilities',.0014),('DUK','Duke Energy','Utilities',.0011),('SO','Southern Company','Utilities',.0011),
 ('LIN','Linde','Materials',.0014),('FCX','Freeport-McMoRan','Materials',.0028),('NEM','Newmont','Materials',.0025),
 ('AMT','American Tower','Real Estate',.0017),('PLD','Prologis','Real Estate',.0016),('EQIX','Equinix','Real Estate',.0016),
 ('T','AT&T','Telecom',.0013),('VZ','Verizon','Telecom',.0012),('TMUS','T-Mobile US','Telecom',.0016),
 ('QQQ','Invesco QQQ','ETF',.0012),('IWM','iShares Russell 2000','ETF',.0015),('DIA','SPDR Dow Jones','ETF',.0010),('TLT','iShares 20+ Year Treasury','ETF',.0010),('HYG','iShares High Yield Bond','ETF',.0008)
])

_sgp22_extend_unique(GLOBAL_STOCKS,[
 ('SHEL','Shell',70,.0018,'Energy','SHEL','LSE','USD'),('BP','BP',34,.0020,'Energy','BP','LSE','USD'),('AZN','AstraZeneca',78,.0015,'Health','AZN','LSE','USD'),('UL','Unilever',63,.0013,'Consumer','UL','LSE','USD'),
 ('SIEGY','Siemens ADR',105,.0017,'Industrial','SIEGY','XETRA','USD'),('BASFY','BASF ADR',12,.0020,'Materials','BASFY','XETRA','USD'),('DTEGY','Deutsche Telekom ADR',38,.0013,'Telecom','DTEGY','XETRA','USD'),
 ('HMC','Honda',31,.0017,'Consumer','HMC','TSE','USD'),('MUFG','Mitsubishi UFJ',15,.0017,'Finance','MUFG','TSE','USD'),('SMFG','Sumitomo Mitsui',16,.0017,'Finance','SMFG','TSE','USD'),('NTDOY','Nintendo ADR',22,.0020,'Consumer','NTDOY','TSE','USD'),
 ('JD','JD.com ADR',35,.0028,'Consumer','JD','HKEX','USD'),('BIDU','Baidu ADR',96,.0027,'Tech','BIDU','HKEX','USD'),('PDD','PDD Holdings',120,.0030,'Consumer','PDD','HKEX','USD'),
 ('BHP','BHP Group',55,.0018,'Materials','BHP','ASX','USD'),('RIO','Rio Tinto',62,.0019,'Materials','RIO','ASX','USD'),('CSL.AX','CSL Limited',290,.0018,'Health','CSL.AX','ASX','AUD'),('CBA.AX','Commonwealth Bank',165,.0015,'Finance','CBA.AX','ASX','AUD'),
 ('RY','Royal Bank of Canada',145,.0014,'Finance','RY','US','USD'),('TD','Toronto-Dominion Bank',72,.0015,'Finance','TD','US','USD'),('CNQ','Canadian Natural Resources',36,.0019,'Energy','CNQ','US','USD'),
 ('VALE','Vale ADR',11,.0025,'Materials','VALE','US','USD'),('PBR','Petrobras ADR',14,.0027,'Energy','PBR','US','USD')
])

# Stock Game Pro 2.2 option-IV scenario integration.
def _sgp22_option_volatility(self):
    regime=max(.10,min(8.0,float(getattr(self.underlying,'scenario_vol_mult',1.0))))
    iv=max(.20,min(5.0,float(getattr(self.underlying,'scenario_option_iv',1.0))))
    return max(.04,(self.underlying.volatility*20+.12+abs(self.strike/max(.0001,self.underlying.price)-1)*.30)*math.sqrt(regime)*iv)
OptionContract.volatility=property(_sgp22_option_volatility)

# ===== Stock Game Pro 2.2.1 scalable portfolio / margin accounting =====
# Stock positions stay O(1) regardless of share quantity.  Identical option fills are compacted
# into one aggregate strategy, and short-sale proceeds are treated as restricted collateral so
# they cannot be recursively re-used to pyramid into astronomical positions.
import math as _sgp_math221

def _sgp221_available_funds(self):
    locked=0.0
    for sym,q in self.positions.items():
        if int(q)<0:locked+=max(0.0,float(self.cost_basis.get(sym,0.0)))
    return max(0.0,float(self.cash)-locked-max(0.0,float(getattr(self,'reserved_margin',0.0))))
Portfolio.available_funds=_sgp221_available_funds
Portfolio.buying_power=property(lambda self:self.available_funds())

def _sgp221_room(self,a,side,requested):
    q=max(1,int(requested));m=getattr(self,'market',None);current=int(self.positions.get(a.symbol,0))
    if m is None or not hasattr(m,'position_capacity'):return q
    if side=='BUY':room=max(0,int(m.position_capacity(a,'BUY'))-max(0,current))
    elif side=='SHORT':room=max(0,int(m.position_capacity(a,'SHORT'))-max(0,-current))
    else:room=q
    if room<=0:return 0
    try:q=min(q,int(m.max_executable_qty(a,side,q)))
    except Exception:pass
    return min(q,room)
Portfolio._execution_room_v221=_sgp221_room

def _sgp221_fill_suffix(fill,requested,filled):
    rem=max(0,int(requested)-int(filled));base=f'VWAP ${float(fill.get("vwap",0)):,.4f} • impact {float(fill.get("impact",0))*100:.2f}%'
    return base+(f' • PARTIAL {filled:,}/{requested:,} filled; {rem:,} not filled' if rem else '')

def _sgp221_buy(self,a,qty):
    try:requested=int(qty)
    except Exception:return False,'Invalid quantity.'
    if requested<=0:return False,'Quantity must be positive.'
    q=self._execution_room_v221(a,'BUY',requested)
    if q<=0:return False,f'{a.symbol} position is at the simulator float/capacity limit.'
    m=getattr(self,'market',None);preview=m.preview_execution('BUY',a,q) if m and hasattr(m,'preview_execution') else {'vwap':a.ask,'filled_qty':q}
    q=int(preview.get('filled_qty',q));est=float(preview['vwap'])*q
    if est>self.available_funds():return False,f'Insufficient buying power. Need about ${est:,.2f}; available ${self.available_funds():,.2f}.'
    px,fill=self._market_fill_v21(a,'BUY',q);filled=int(fill.get('filled_qty',q));cost=px*filled;old=self._qty(a.symbol)
    self.cash-=cost;self.positions[a.symbol]=old+filled;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+cost;self.trade_count+=1
    return True,f'Bought {filled:,} {a.symbol} • {_sgp221_fill_suffix(fill,requested,filled)}'
Portfolio.buy_asset=_sgp221_buy

def _sgp221_sell(self,a,qty):
    try:requested=int(qty)
    except Exception:return False,'Invalid quantity.'
    owned=self._qty(a.symbol)
    if requested<=0:return False,'Quantity must be positive.'
    if owned<=0:return False,f'No long {a.symbol} position.'
    requested=min(requested,owned);m=getattr(self,'market',None);q=min(requested,int(m.max_executable_qty(a,'SELL',requested))) if m and hasattr(m,'max_executable_qty') else requested
    px,fill=self._market_fill_v21(a,'SELL',q);filled=int(fill.get('filled_qty',q));proceeds=px*filled;basis_total=self.cost_basis.get(a.symbol,0);basis=basis_total*(filled/owned)
    self.cash+=proceeds;self.realized+=proceeds-basis;remain=owned-filled
    if remain:self.positions[a.symbol]=remain;self.cost_basis[a.symbol]=max(0,basis_total-basis)
    else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
    self.trade_count+=1;return True,f'Sold {filled:,} {a.symbol} • {_sgp221_fill_suffix(fill,requested,filled)}'
Portfolio.sell_asset=_sgp221_sell

def _sgp221_short(self,a,qty,margin_rate=.5):
    try:requested=int(qty)
    except Exception:return False,'Invalid quantity.'
    if requested<=0:return False,'Quantity must be positive.'
    q=self._execution_room_v221(a,'SHORT',requested)
    if q<=0:return False,f'{a.symbol} short is at the estimated borrow/float capacity limit.'
    m=getattr(self,'market',None);preview=m.preview_execution('SHORT',a,q) if m and hasattr(m,'preview_execution') else {'vwap':a.bid,'filled_qty':q}
    q=int(preview.get('filled_qty',q));req=float(preview['vwap'])*q*float(margin_rate)
    avail=self.available_funds()
    if avail<req:return False,f'Initial margin requires about ${req:,.2f}; buying power ${avail:,.2f}. Short-sale proceeds are restricted collateral.'
    px,fill=self._market_fill_v21(a,'SHORT',q);filled=int(fill.get('filled_qty',q));proceeds=px*filled;req=px*filled*float(margin_rate);old=self._qty(a.symbol)
    self.positions[a.symbol]=old-filled;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+proceeds;self.cash+=proceeds;self.reserved_margin+=req;self.trade_count+=1
    return True,f'Shorted {filled:,} {a.symbol} • {_sgp221_fill_suffix(fill,requested,filled)} • margin ${req:,.2f}'
Portfolio.short_asset=_sgp221_short

def _sgp221_cover(self,a,qty):
    try:requested=int(qty)
    except Exception:return False,'Invalid quantity.'
    short=-self._qty(a.symbol)
    if short<=0:return False,'No short position.'
    if requested<=0:return False,'Quantity must be positive.'
    requested=min(requested,short);m=getattr(self,'market',None);q=min(requested,int(m.max_executable_qty(a,'COVER',requested))) if m and hasattr(m,'max_executable_qty') else requested
    preview=m.preview_execution('COVER',a,q) if m and hasattr(m,'preview_execution') else {'vwap':a.ask,'filled_qty':q}
    q=int(preview.get('filled_qty',q));est=float(preview['vwap'])*q
    if est>self.cash:return False,f'Cover requires about ${est:,.2f}; account cash ${self.cash:,.2f}. Reduce quantity or liquidate other assets.'
    px,fill=self._market_fill_v21(a,'COVER',q);filled=int(fill.get('filled_qty',q));cost=px*filled;basis_total=self.cost_basis.get(a.symbol,0);entry=basis_total*(filled/short)
    self.cash-=cost;self.realized+=entry-cost;remain=short-filled;release_ratio=filled/max(1,short);self.reserved_margin=max(0.0,self.reserved_margin*(1-release_ratio))
    if remain:self.positions[a.symbol]=-remain;self.cost_basis[a.symbol]=max(0,basis_total-entry)
    else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
    self.trade_count+=1;return True,f'Covered {filled:,} {a.symbol} • {_sgp221_fill_suffix(fill,requested,filled)}'
Portfolio.cover_short=_sgp221_cover

# Prevent duplicate option fills from growing self.options without bound.
def _sgp221_leg_key(leg):
    c=leg.contract;exp=getattr(c,'expiry_at',None)
    expkey=exp.isoformat() if hasattr(exp,'isoformat') else str(getattr(c,'days',0))
    return (getattr(c.underlying,'symbol',''),round(float(c.strike),6),str(c.option_type),str(leg.action),expkey)

def _sgp221_strategy_map(st):
    return {_sgp221_leg_key(l):l for l in st.legs}

def _sgp221_compact_options(self):
    merged=[];by_sig={}
    for st in list(self.options):
        if not getattr(st,'legs',None):continue
        keys=tuple(sorted(_sgp221_leg_key(l) for l in st.legs))
        target=by_sig.get(keys)
        if target is None:
            by_sig[keys]=st;merged.append(st);continue
        tm=_sgp221_strategy_map(target)
        for leg in st.legs:
            k=_sgp221_leg_key(leg)
            if k in tm:tm[k].quantity+=int(leg.quantity)
            else:target.legs.append(leg)
        target.open_cost=float(getattr(target,'open_cost',0.0))+float(getattr(st,'open_cost',0.0))
        if getattr(target,'expiry_at',None) is None:target.expiry_at=getattr(st,'expiry_at',None)
    if len(merged)!=len(self.options):
        self.options=merged;self.invalidate_option_cache()
    return len(merged)
Portfolio.compact_option_positions=_sgp221_compact_options

_sgp221_exec_strategy_base=Portfolio.execute_strategy
def _sgp221_execute_strategy(self,s):
    # Risk checks use free buying power, not gross cash that may contain restricted short proceeds.
    debit=s.opening_debit();margin=max(0.0,-debit*1.5);avail=self.available_funds()
    if debit>0 and debit>avail:return False,f'Insufficient buying power. Need ${debit:,.2f}; available ${avail:,.2f}.'
    if debit<0 and margin>avail:return False,f'Short-option margin required ${margin:,.2f}; buying power ${avail:,.2f}.'
    before=list(self.options);ok,msg=_sgp221_exec_strategy_base(self,s)
    if ok:
        self.compact_option_positions()
        if len(self.options)<len(before)+1:msg+=f' • aggregated into existing position ({len(self.options)} option position groups)'
    return ok,msg
Portfolio.execute_strategy=_sgp221_execute_strategy

# Sanitize pathological values from older saves before they reach chart/Black-Scholes math.
_Asset_update_v221_base=Asset.update_price
def _sgp221_safe_update_price(self,new_price,volume=0,timestamp=None,record=True):
    try:p=float(new_price)
    except Exception:p=float(getattr(self,'price',1.0))
    if not _sgp_math221.isfinite(p):p=float(getattr(self,'price',1.0))
    p=max(.000001,min(1.0e12,p))
    try:v=max(0,min(int(volume),9_000_000_000_000_000_000))
    except Exception:v=0
    return _Asset_update_v221_base(self,p,v,timestamp,record)
Asset.update_price=_sgp221_safe_update_price

# Compact duplicate option positions immediately after restoring an older account.
_sgp221_restore_base=AccountManager.restore_game_state
def _sgp221_restore(self,portfolio,market,state):
    ok=_sgp221_restore_base(self,portfolio,market,state)
    try:portfolio.compact_option_positions()
    except Exception:pass
    return ok
AccountManager.restore_game_state=_sgp221_restore

# 2.2.1.1: preserve session gates around the final scalable execution methods.
def _sgp221_stock_session_gate(portfolio,a):
    m=getattr(portfolio,'market',None)
    if m is not None and hasattr(m,'stock_trading_allowed') and not m.stock_trading_allowed(a):
        state=getattr(m,'asset_trade_state',lambda x:'CLOSED')(a)
        return False,f'{a.symbol} stock trading is {state}. Queue an order or wait for a tradable session.'
    return None

_sgp221_buy_nogate=Portfolio.buy_asset;_sgp221_sell_nogate=Portfolio.sell_asset;_sgp221_short_nogate=Portfolio.short_asset;_sgp221_cover_nogate=Portfolio.cover_short
def _sgp221_buy_gate(self,a,qty):
    gate=_sgp221_stock_session_gate(self,a);return gate if gate else _sgp221_buy_nogate(self,a,qty)
def _sgp221_sell_gate(self,a,qty):
    gate=_sgp221_stock_session_gate(self,a);return gate if gate else _sgp221_sell_nogate(self,a,qty)
def _sgp221_short_gate(self,a,qty,margin_rate=.5):
    gate=_sgp221_stock_session_gate(self,a);return gate if gate else _sgp221_short_nogate(self,a,qty,margin_rate)
def _sgp221_cover_gate(self,a,qty):
    gate=_sgp221_stock_session_gate(self,a);return gate if gate else _sgp221_cover_nogate(self,a,qty)
Portfolio.buy_asset=_sgp221_buy_gate;Portfolio.sell_asset=_sgp221_sell_gate;Portfolio.short_asset=_sgp221_short_gate;Portfolio.cover_short=_sgp221_cover_gate

_sgp221_strategy_risk_base=Portfolio.execute_strategy
def _sgp221_execute_strategy_session_safe(self,s):
    m=getattr(self,'market',None);under=s.legs[0].contract.underlying if getattr(s,'legs',None) else None
    before_count=len(self.options)
    ok,msg=_sgp221_strategy_risk_base(self,s)
    # A closed-session market-on-open queue is not an owned position yet.
    if ok and len(self.options)==before_count and 'queued' in str(msg).lower():return ok,msg
    return ok,msg
Portfolio.execute_strategy=_sgp221_execute_strategy_session_safe

def _sgp221_execute_strategy_final(self,s):
    m=getattr(self,'market',None);under=s.legs[0].contract.underlying if getattr(s,'legs',None) else None
    # Let the existing v1.3 session gate queue listed options without charging margin/cash.
    if m is not None and under is not None and hasattr(m,'asset_regular_open') and not m.asset_regular_open(under):
        return _sgp221_exec_strategy_base(self,s)
    debit=s.opening_debit();margin=max(0.0,-debit*1.5);avail=self.available_funds()
    if debit>0 and debit>avail:return False,f'Insufficient buying power. Need ${debit:,.2f}; available ${avail:,.2f}.'
    if debit<0 and margin>avail:return False,f'Short-option margin required ${margin:,.2f}; buying power ${avail:,.2f}.'
    before_count=len(self.options);ok,msg=_sgp221_exec_strategy_base(self,s)
    if ok and len(self.options)>before_count:
        precompact=len(self.options);self.compact_option_positions()
        if len(self.options)<precompact:msg+=f' • aggregated into existing position ({len(self.options)} option position groups)'
    return ok,msg
Portfolio.execute_strategy=_sgp221_execute_strategy_final

# 2.2.1.2: legacy-save numeric safety.  Do not throw away an old whale position; clamp only the
# floating-point valuation used by the UI so an oversized historical integer cannot overflow Tk/Python.
def _sgp221_money(x,limit=1.0e300):
    try:v=float(x)
    except Exception:return 0.0
    if not _sgp_math221.isfinite(v):return limit if v>0 else -limit if v<0 else 0.0
    return max(-limit,min(limit,v))

def _sgp221_notional(q,price):
    try:
        qf=float(q);pf=float(price);v=qf*pf
    except Exception:return 1.0e300 if int(q)>=0 else -1.0e300
    return _sgp221_money(v)

def _sgp221_available_funds_safe(self):
    cash=_sgp221_money(self.cash);locked=0.0
    for sym,q in self.positions.items():
        if int(q)<0:locked=min(1.0e300,locked+max(0.0,_sgp221_money(self.cost_basis.get(sym,0.0))))
    margin=max(0.0,_sgp221_money(getattr(self,'reserved_margin',0.0)))
    v=cash-locked-margin
    return max(0.0,_sgp221_money(v))
Portfolio.available_funds=_sgp221_available_funds_safe
Portfolio.buying_power=property(lambda self:self.available_funds())

def _sgp221_mark_value_safe(self,assets):
    total=_sgp221_money(self.cash);amap=self._asset_map(assets)
    for sym,q in self.positions.items():
        a=self.market.get_asset(sym) if getattr(self,'market',None) is not None else amap.get(sym)
        if a:total=_sgp221_money(total+_sgp221_notional(q,a.price))
    for st in self.options:
        try:total=_sgp221_money(total+_sgp221_money(st.current_value()))
        except Exception:pass
    total=_sgp221_money(total-float(getattr(self,'loan_balance',0.0)))
    return total
Portfolio.mark_value=_sgp221_mark_value_safe

def _sgp221_position_rows_safe(self,assets):
    rows=[];amap=self._asset_map(assets)
    for sym,q in list(self.positions.items()):
        if not q:continue
        a=self.market.get_asset(sym) if getattr(self,'market',None) is not None else amap.get(sym)
        if not a:continue
        basis=_sgp221_money(self.cost_basis.get(sym,0.0));value=_sgp221_notional(q,a.price);pnl=_sgp221_money(value-basis if q>0 else basis+value)
        rows.append((sym,a.name,q,float(a.price),value,pnl,'LONG' if q>0 else 'SHORT','',0))
    for st in list(self.options):
        if not st.legs:continue
        first=st.legs[0].contract;under=first.underlying.symbol;label=self._strategy_display_symbol(st);total_qty=max(1,sum(abs(int(l.quantity)) for l in st.legs))
        try:v=_sgp221_money(st.current_value())
        except Exception:v=0.0
        rows.append((self.strategy_ref(st),label,total_qty,v,v,_sgp221_money(v-st.open_cost),'OPTION',under,min((l.contract.days for l in st.legs),default=0)))
    return rows
Portfolio.position_rows=_sgp221_position_rows_safe


# ===== Stock Game Pro 2.3 account analytics + simplified PDT training rule =====
# Simulator rule requested by the player: accounts below $25k may complete up to three
# same-day round trips in a rolling 5-business-day window. A fourth attempted day trade
# flags the account until equity is back at/above $25k.
from datetime import timedelta as _sgp23_td

_Portfolio_init_v23_base=Portfolio.__init__
def _sgp23_portfolio_init(self,cash=25_000):
    _Portfolio_init_v23_base(self,cash)
    self.day_trade_log=[]
    self.pdt_flagged=False
    self._intraday_open={}
    self.equity_history=[]
    self._equity_last_stamp=None
    self._daily_equity_open={}
Portfolio.__init__=_sgp23_portfolio_init

def _sgp23_now(self):
    m=getattr(self,'market',None);return getattr(getattr(m,'clock',None),'current',None) or datetime.now()

def _sgp23_equity(self):
    m=getattr(self,'market',None)
    try:return float(self.mark_value(m.all_assets())) if m else float(self.cash)
    except Exception:return float(self.cash)
Portfolio.regulatory_equity=_sgp23_equity

def _sgp23_prune(self):
    now=_sgp23_now(self).date();cut=now-_sgp23_td(days=7)
    self.day_trade_log=[x for x in getattr(self,'day_trade_log',[]) if _sgp_dt_parse_v20(x.get('time')).date()>=cut if _sgp_dt_parse_v20(x.get('time'))]
    # Count only the newest rolling five business dates represented in the simulator.
    dates=[];d=now
    while len(dates)<5:
        if d.weekday()<5:dates.append(d)
        d-=_sgp23_td(days=1)
    allowed=set(dates);self.day_trade_log=[x for x in self.day_trade_log if _sgp_dt_parse_v20(x.get('time')).date() in allowed]
    if self.regulatory_equity()>=25_000:self.pdt_flagged=False
Portfolio._pdt_prune=_sgp23_prune

def _sgp23_day_trades(self):
    self._pdt_prune();return len(self.day_trade_log)
Portfolio.day_trades_rolling=property(_sgp23_day_trades)

def _sgp23_would_daytrade(self,a,closing_side):
    today=_sgp23_now(self).date().isoformat();entry=getattr(self,'_intraday_open',{}).get(a.symbol)
    if not entry or entry.get('date')!=today:return False
    return (closing_side=='SELL' and entry.get('long',0)>0) or (closing_side=='COVER' and entry.get('short',0)>0)

def _sgp23_pdt_check(self,a,side):
    if side not in ('SELL','COVER') or not _sgp23_would_daytrade(self,a,side):return None
    self._pdt_prune();eq=self.regulatory_equity()
    if eq>=25_000:return None
    if self.pdt_flagged:return f'PDT FLAGGED — day trading locked while account equity is below $25,000. Current equity ${eq:,.2f}.'
    if self.day_trades_rolling>=3:
        self.pdt_flagged=True
        return f'PDT FLAGGED — this would exceed 3 day trades in the rolling week while equity is below $25,000. Day trading is locked until equity reaches $25,000.'
    return None

def _sgp23_note_open(self,a,side,qty):
    today=_sgp23_now(self).date().isoformat();d=self._intraday_open.setdefault(a.symbol,{'date':today,'long':0,'short':0})
    if d.get('date')!=today:d.clear();d.update(date=today,long=0,short=0)
    if side=='BUY':d['long']=int(d.get('long',0))+int(qty)
    elif side=='SHORT':d['short']=int(d.get('short',0))+int(qty)

def _sgp23_note_close(self,a,side,qty):
    if not _sgp23_would_daytrade(self,a,side):return
    d=self._intraday_open.get(a.symbol,{});key='long' if side=='SELL' else 'short';closed=min(int(qty),int(d.get(key,0)))
    if closed<=0:return
    d[key]=max(0,int(d.get(key,0))-closed)
    self.day_trade_log.append({'time':_sgp_dt_iso_v20(_sgp23_now(self)),'symbol':a.symbol,'side':side,'qty':closed})
    self._pdt_prune()

_buy_v23_base=Portfolio.buy_asset
_sell_v23_base=Portfolio.sell_asset
_short_v23_base=Portfolio.short_asset
_cover_v23_base=Portfolio.cover_short

def _sgp23_buy(self,a,qty):
    ok,msg=_buy_v23_base(self,a,qty)
    if ok:_sgp23_note_open(self,a,'BUY',qty)
    return ok,msg

def _sgp23_sell(self,a,qty):
    block=_sgp23_pdt_check(self,a,'SELL')
    if block:return False,block
    ok,msg=_sell_v23_base(self,a,qty)
    if ok:_sgp23_note_close(self,a,'SELL',qty)
    return ok,msg

def _sgp23_short(self,a,qty,margin_rate=.5):
    ok,msg=_short_v23_base(self,a,qty,margin_rate)
    if ok:_sgp23_note_open(self,a,'SHORT',qty)
    return ok,msg

def _sgp23_cover(self,a,qty):
    block=_sgp23_pdt_check(self,a,'COVER')
    if block:return False,block
    ok,msg=_cover_v23_base(self,a,qty)
    if ok:_sgp23_note_close(self,a,'COVER',qty)
    return ok,msg
Portfolio.buy_asset=_sgp23_buy;Portfolio.sell_asset=_sgp23_sell;Portfolio.short_asset=_sgp23_short;Portfolio.cover_short=_sgp23_cover

def _sgp23_record_equity(self,force=False):
    now=_sgp23_now(self);stamp=now.replace(second=0,microsecond=0)
    if not force and getattr(self,'_equity_last_stamp',None)==stamp:return
    eq=self.regulatory_equity();hold=[]
    m=getattr(self,'market',None)
    if m:
        for sym,q in self.positions.items():
            a=m.get_asset(sym)
            if a and q:hold.append((sym,int(q),float(a.price),float(q)*float(a.price)))
        hold=sorted(hold,key=lambda x:abs(x[3]),reverse=True)[:12]
    rec={'time':_sgp_dt_iso_v20(now),'equity':eq,'cash':float(self.cash),'realized':float(self.realized),'holdings':hold}
    self.equity_history.append(rec);self.equity_history=self.equity_history[-20000:];self._equity_last_stamp=stamp
    day=now.date().isoformat();self._daily_equity_open.setdefault(day,eq)
Portfolio.record_equity_snapshot=_sgp23_record_equity

def _sgp23_daily_pl(self):
    day=_sgp23_now(self).date().isoformat();eq=self.regulatory_equity();base=float(getattr(self,'_daily_equity_open',{}).get(day,eq));return eq-base
Portfolio.daily_pl=property(_sgp23_daily_pl)

_save_v23_base=AccountManager.save_game_state
def _sgp23_save_game(self,username,portfolio,market,reason='autosave'):
    portfolio.record_equity_snapshot(force=True)
    ok=_save_v23_base(self,username,portfolio,market,reason)
    if ok and username in self.accounts:
        st=self.accounts[username].setdefault('game_state',{})
        st['day_trade_log']=list(getattr(portfolio,'day_trade_log',[]))[-100:]
        st['pdt_flagged']=bool(getattr(portfolio,'pdt_flagged',False))
        st['intraday_open']=dict(getattr(portfolio,'_intraday_open',{}))
        st['equity_history']=list(getattr(portfolio,'equity_history',[]))[-20000:]
        st['daily_equity_open']=dict(getattr(portfolio,'_daily_equity_open',{}))
        self._save()
    return ok
AccountManager.save_game_state=_sgp23_save_game

_restore_v23_base=AccountManager.restore_game_state
def _sgp23_restore_game(self,username,portfolio,market):
    ok=_restore_v23_base(self,username,portfolio,market)
    if ok:
        rec=self.accounts.get(str(username).lower(),{});st=rec.get('game_state',{})
        portfolio.day_trade_log=list(st.get('day_trade_log',[]));portfolio.pdt_flagged=bool(st.get('pdt_flagged',False));portfolio._intraday_open=dict(st.get('intraday_open',{}));portfolio.equity_history=list(st.get('equity_history',[]));portfolio._daily_equity_open=dict(st.get('daily_equity_open',{}));portfolio._pdt_prune()
    return ok
AccountManager.restore_game_state=_sgp23_restore_game

# ===== Stock Game Pro 2.4 S&P 500 universe + session metrics =====
# The S&P 500 contains 503 listed securities representing 500 companies because a few
# constituents have multiple public share classes.  Keep the simulator's extra research
# symbols, but guarantee every current S&P constituent is available in the STOCK watchlist.
try:
    from sp500_constituents import SP500_CONSTITUENTS, SP500_SYMBOLS
except Exception:
    SP500_CONSTITUENTS=[];SP500_SYMBOLS=[]

if SP500_CONSTITUENTS:
    _sgp24_have={r[0] for r in STOCKS}
    for _sym,_name,_sector,_vol,_official,_subindustry in SP500_CONSTITUENTS:
        if _sym not in _sgp24_have:
            STOCKS.append((_sym,_name,_sector,float(_vol)));_sgp24_have.add(_sym)
    # The index definition itself is updated too, so SPX uses the actual constituent set
    # instead of every US research symbol in the game.
    _sgp24_indexes=[]
    for _row in INDEXES:
        if _row[0]=='SPX':
            _sgp24_indexes.append((_row[0],_row[1],_row[2],list(SP500_SYMBOLS),_row[4]))
        else:_sgp24_indexes.append(_row)
    INDEXES[:]=_sgp24_indexes

def _sgp24_after_hours_percent(self):
    base=float(getattr(self,'regular_close_price',0.0) or getattr(self,'last_real_close',0.0) or getattr(self,'open_price',0.0) or self.price)
    return (float(self.price)/base-1.0)*100.0 if base else 0.0
Asset.after_hours_percent=_sgp24_after_hours_percent

# ===== Stock Game Pro 2.5 full index-universe patch =====
# Keep the core S&P 500 universe from 2.4 and add complete/publicly available
# constituent snapshots for the other US indexes represented by the simulator.
try:
    from index_constituents import INDEX_STOCK_ROWS as _SGP25_INDEX_STOCK_ROWS, INDEX_COMPONENTS as _SGP25_INDEX_COMPONENTS
except Exception:
    _SGP25_INDEX_STOCK_ROWS=[];_SGP25_INDEX_COMPONENTS={}

if _SGP25_INDEX_STOCK_ROWS:
    _sgp25_have={r[0] for r in STOCKS}
    for _sym,_name,_sector,_vol in _SGP25_INDEX_STOCK_ROWS:
        if _sym and _sym not in _sgp25_have:
            STOCKS.append((_sym,_name,_sector,float(_vol)));_sgp25_have.add(_sym)
    _sgp25_indexes=[]
    for _row in INDEXES:
        _sym,_name,_price,_components,_vol=_row
        comps=_SGP25_INDEX_COMPONENTS.get(_sym)
        _sgp25_indexes.append((_sym,_name,_price,list(comps) if comps else _components,_vol))
    INDEXES[:]=_sgp25_indexes


# ===== Stock Game Pro 2.5 major global-index constituent coverage =====
# Add bundled FTSE 100, DAX 40 and Hang Seng members as true international assets with
# their home sessions. Other global indexes keep their existing representative baskets.
try:
    from global_index_constituents import GLOBAL_INDEX_COMPONENTS as _SGP25_GLOBAL_COMPONENTS, GLOBAL_INDEX_ROWS as _SGP25_GLOBAL_ROWS
except Exception:
    _SGP25_GLOBAL_COMPONENTS={};_SGP25_GLOBAL_ROWS={}

if _SGP25_GLOBAL_ROWS:
    _existing_global={r[0] for r in GLOBAL_STOCKS}
    _cfg={
        'FTSE':('LSE','GBP','UK Equity',.0018),
        'DAX':('XETRA','EUR','Germany Equity',.0019),
        'HSI':('HKEX','HKD','Hong Kong Equity',.0024),
    }
    for _idx,_rows in _SGP25_GLOBAL_ROWS.items():
        _session,_currency,_cat,_vol=_cfg[_idx]
        for _sym,_name in _rows:
            if _sym and _sym not in _existing_global:
                GLOBAL_STOCKS.append((_sym,_name,100.0,_vol,_cat,_sym,_session,_currency));_existing_global.add(_sym)
    _new_global=[]
    for _row in GLOBAL_INDEXES:
        _sym,_name,_price,_components,_vol,_ds,_session=_row
        _comps=_SGP25_GLOBAL_COMPONENTS.get(_sym)
        _new_global.append((_sym,_name,_price,list(_comps) if _comps else _components,_vol,_ds,_session))
    GLOBAL_INDEXES[:]=_new_global

# ===== Stock Game Pro 2.5 production offline-play account seed / persistent market state =====
# Prevent legacy helpers in this consolidated module from ever creating network traffic
# during gameplay. The data module exposes cache-only public reads in production 2.5.
def fetch_latest(symbol,timeout=5):
    try:
        from data import fetch_latest_cached
        q=fetch_latest_cached(symbol)
        if q is None:return None
        return Candle(q.timestamp,float(q.close),float(q.close),float(q.close),float(q.close),int(q.volume))
    except Exception:return None

def fetch_many_latest(symbols,workers=8):
    out={}
    for sym in symbols:
        c=fetch_latest(sym)
        if c is not None:out[sym]=c
    return out

def fetch_history(symbol,period1=0,interval='1d',timeout=5):
    if interval!='1d':return []
    try:
        from data import fetch_history_max_cached
        return list(fetch_history_max_cached(symbol))
    except Exception:return []

_AccountManager_create_v251_base=AccountManager.create
def _sgp251_account_create(self,username,mode):
    ok,msg=_AccountManager_create_v251_base(self,username,mode)
    if ok:
        key=str(username).strip().lower();rec=self.accounts.get(key)
        if rec is not None:
            rec['market_seed_complete']=False;rec['market_seed_info']={'source':'PENDING','saved_at':None,'fresh_quotes':0,'cached_quotes':0}
            self._save()
    return ok,msg
AccountManager.create=_sgp251_account_create

def _sgp251_set_market_seed_info(self,username,info):
    key=str(username or '').strip().lower();rec=self.accounts.get(key)
    if rec is None:return False
    rec['market_seed_complete']=True;rec['market_seed_info']=dict(info or {});self._save();return True
AccountManager.set_market_seed_info=_sgp251_set_market_seed_info

# Persist simulator prices so reopening an established account continues its simulated
# market rather than re-seeding from the creation-time snapshot.
_AccountManager_save_game_v251_base=AccountManager.save_game_state
def _sgp251_save_game_state(self,username,portfolio,market,reason='autosave'):
    ok=_AccountManager_save_game_v251_base(self,username,portfolio,market,reason)
    if ok and username:
        try:
            rec=self.accounts.get(str(username).lower()) or self.accounts.get(username);st=rec.get('game_state',{})
            prices={}
            for a in market.all_assets():
                prices[a.symbol]=[
                    float(a.price),float(a.open_price),float(a.previous_price),float(a.high),float(a.low),
                    float(getattr(a,'regular_close_price',a.price)),float(getattr(a,'previous_close_price',getattr(a,'regular_close_price',a.price)))
                ]
            st['market_prices']=prices;rec['game_state']=st;self._save()
        except Exception:pass
    return ok
AccountManager.save_game_state=_sgp251_save_game_state

_AccountManager_restore_game_v251_base=AccountManager.restore_game_state
def _sgp251_restore_game_state(self,username,portfolio,market):
    ok=_AccountManager_restore_game_v251_base(self,username,portfolio,market)
    try:
        rec=self.accounts.get(str(username).lower()) or self.accounts.get(username) or {};prices=(rec.get('game_state') or {}).get('market_prices') or {}
        if prices:
            for sym,v in prices.items():
                a=market.get_asset(sym)
                if a is None or not isinstance(v,(list,tuple)) or not v:continue
                try:
                    a.price=max(.000001,float(v[0]));a.open_price=max(.000001,float(v[1] if len(v)>1 else a.price));a.previous_price=max(.000001,float(v[2] if len(v)>2 else a.price));a.high=max(a.price,float(v[3] if len(v)>3 else a.price));a.low=max(.000001,min(a.price,float(v[4] if len(v)>4 else a.price)))
                    a.regular_close_price=max(.000001,float(v[5] if len(v)>5 else a.price));a.previous_close_price=max(.000001,float(v[6] if len(v)>6 else a.regular_close_price));a._reprice_book()
                except Exception:pass
            try:market._v25_rebuild_index_cache()
            except Exception:pass
    except Exception:pass
    return ok
AccountManager.restore_game_state=_sgp251_restore_game_state

# ===== Stock Game Pro 2.5 production polish: durable trade ledger + correct daily buckets =====
# The consolidated core historically used the generic minute bucketer for 1-day candles.
# A 1,440-minute bucket must start at midnight; leaving the hour intact created pseudo-daily
# bars that rolled every hour and made completed candles appear to reset on some views.
_Asset_bucket_prod25_base=Asset._bucket
def _sgp25prod_bucket(self,ts,minutes):
    minutes=max(1,int(minutes))
    ts=ts.replace(tzinfo=None) if getattr(ts,'tzinfo',None) else ts
    if minutes>=1440:
        # All current daily bars use 1,440 minutes. Keep this explicit and stable.
        return ts.replace(hour=0,minute=0,second=0,microsecond=0)
    if minutes>=60:
        total=ts.hour*60+ts.minute;slot=(total//minutes)*minutes
        return ts.replace(hour=(slot//60)%24,minute=slot%60,second=0,microsecond=0)
    return ts.replace(minute=(ts.minute//minutes)*minutes,second=0,microsecond=0)
Asset._bucket=_sgp25prod_bucket

# A compact, persistent trade ledger backs the new Trade History panel.  It records actual
# filled quantities by comparing positions before/after the final execution functions, so
# partial whale fills are represented correctly instead of logging the requested quantity.
_Portfolio_init_trade25_base=Portfolio.__init__
def _sgp25prod_portfolio_init(self,*args,**kwargs):
    _Portfolio_init_trade25_base(self,*args,**kwargs)
    if not hasattr(self,'trade_history'):self.trade_history=[]
Portfolio.__init__=_sgp25prod_portfolio_init

def _sgp25prod_trade_time(portfolio):
    m=getattr(portfolio,'market',None);now=getattr(getattr(m,'clock',None),'current',None) or datetime.now()
    try:return now.isoformat(timespec='seconds')
    except Exception:return str(now)

def _sgp25prod_append_trade(portfolio,side,symbol,qty,price,kind='STOCK',details='',realized=None):
    try:qty=int(abs(qty))
    except Exception:qty=0
    if qty<=0:return
    try:px=float(price)
    except Exception:px=0.0
    if not math.isfinite(px):px=0.0
    try:notional=min(1.0e300,abs(float(qty)*px))
    except Exception:notional=1.0e300
    rec={'time':_sgp25prod_trade_time(portfolio),'side':str(side).upper(),'symbol':str(symbol),'qty':qty,
         'price':px,'notional':notional,'kind':str(kind),'details':str(details)[:500],
         'realized':float(portfolio.realized if realized is None else realized)}
    hist=getattr(portfolio,'trade_history',None)
    if hist is None:portfolio.trade_history=[];hist=portfolio.trade_history
    hist.append(rec)
    if len(hist)>5000:del hist[:-5000]
Portfolio._append_trade_history=_sgp25prod_append_trade

_buy_trade25_base=Portfolio.buy_asset
_sell_trade25_base=Portfolio.sell_asset
_short_trade25_base=Portfolio.short_asset
_cover_trade25_base=Portfolio.cover_short

def _sgp25prod_buy_trade(self,a,qty):
    before=int(self.positions.get(a.symbol,0));ok,msg=_buy_trade25_base(self,a,qty);after=int(self.positions.get(a.symbol,0))
    if ok:
        filled=max(0,after-before);px=float(getattr(a,'last_execution_vwap',0) or getattr(a,'ask',a.price) or a.price)
        self._append_trade_history('BUY',a.symbol,filled,px,'STOCK',msg)
    return ok,msg

def _sgp25prod_sell_trade(self,a,qty):
    before=int(self.positions.get(a.symbol,0));ok,msg=_sell_trade25_base(self,a,qty);after=int(self.positions.get(a.symbol,0))
    if ok:
        filled=max(0,before-after);px=float(getattr(a,'last_execution_vwap',0) or getattr(a,'bid',a.price) or a.price)
        self._append_trade_history('SELL',a.symbol,filled,px,'STOCK',msg)
    return ok,msg

def _sgp25prod_short_trade(self,a,qty,margin_rate=.5):
    before=int(self.positions.get(a.symbol,0));ok,msg=_short_trade25_base(self,a,qty,margin_rate);after=int(self.positions.get(a.symbol,0))
    if ok:
        filled=max(0,before-after);px=float(getattr(a,'last_execution_vwap',0) or getattr(a,'bid',a.price) or a.price)
        self._append_trade_history('SHORT',a.symbol,filled,px,'STOCK',msg)
    return ok,msg

def _sgp25prod_cover_trade(self,a,qty):
    before=int(self.positions.get(a.symbol,0));ok,msg=_cover_trade25_base(self,a,qty);after=int(self.positions.get(a.symbol,0))
    if ok:
        filled=max(0,after-before);px=float(getattr(a,'last_execution_vwap',0) or getattr(a,'ask',a.price) or a.price)
        self._append_trade_history('COVER',a.symbol,filled,px,'STOCK',msg)
    return ok,msg
Portfolio.buy_asset=_sgp25prod_buy_trade;Portfolio.sell_asset=_sgp25prod_sell_trade
Portfolio.short_asset=_sgp25prod_short_trade;Portfolio.cover_short=_sgp25prod_cover_trade

_exec_strategy_trade25_base=Portfolio.execute_strategy
_liq_strategy_trade25_base=Portfolio.liquidate_strategy
def _sgp25prod_exec_strategy_trade(self,s):
    before=int(getattr(self,'trade_count',0));ok,msg=_exec_strategy_trade25_base(self,s)
    if ok and int(getattr(self,'trade_count',0))>before and 'queued' not in str(msg).lower():
        try:
            under=s.legs[0].contract.underlying.symbol if s.legs else 'OPTION';contracts=max(1,sum(abs(int(l.quantity)) for l in s.legs));debit=float(getattr(s,'open_cost',s.opening_debit()))
            px=abs(debit)/max(1,contracts*100);self._append_trade_history('OPEN',under,contracts,px,'OPTION',f'{getattr(s,"name","Strategy")} • {msg}')
        except Exception:pass
    return ok,msg

def _sgp25prod_liq_strategy_trade(self,s):
    before=int(getattr(self,'trade_count',0));under=s.legs[0].contract.underlying.symbol if getattr(s,'legs',None) else 'OPTION'
    try:contracts=max(1,sum(abs(int(l.quantity)) for l in s.legs));pre=float(s.current_value())
    except Exception:contracts=1;pre=0.0
    ok,msg=_liq_strategy_trade25_base(self,s)
    if ok and int(getattr(self,'trade_count',0))>before:
        self._append_trade_history('CLOSE',under,contracts,abs(pre)/max(1,contracts*100),'OPTION',f'{getattr(s,"name","Strategy")} • {msg}')
    return ok,msg
Portfolio.execute_strategy=_sgp25prod_exec_strategy_trade;Portfolio.liquidate_strategy=_sgp25prod_liq_strategy_trade

# Persist the ledger with the account. This wraps the final production save/restore chain.
_save_trade25_base=AccountManager.save_game_state
def _sgp25prod_save_trade_history(self,username,portfolio,market,reason='autosave'):
    ok=_save_trade25_base(self,username,portfolio,market,reason)
    if ok and username:
        try:
            rec=self.accounts.get(str(username).lower()) or self.accounts.get(username)
            if rec is not None:
                st=rec.setdefault('game_state',{});st['trade_history']=list(getattr(portfolio,'trade_history',[]))[-5000:];self._save()
        except Exception:pass
    return ok
AccountManager.save_game_state=_sgp25prod_save_trade_history

_restore_trade25_base=AccountManager.restore_game_state
def _sgp25prod_restore_trade_history(self,username,portfolio,market):
    ok=_restore_trade25_base(self,username,portfolio,market)
    try:
        rec=self.accounts.get(str(username).lower()) or self.accounts.get(username) or {};hist=(rec.get('game_state') or {}).get('trade_history') or []
        portfolio.trade_history=list(hist)[-5000:]
    except Exception:portfolio.trade_history=[]
    return ok
AccountManager.restore_game_state=_sgp25prod_restore_trade_history

# ===== Stock Game Pro 2.5 production system-polish universe + portfolio attribution =====
# Add home-market sessions used by the expanded global research universe. These remain fully
# simulated/offline during gameplay; the account-creation snapshot is the only automatic online seed.
from datetime import time as _sgp25_clock_time
try:
    _extra_sessions={
        'EURONEXT':Session('EURONEXT','Euronext Paris','Europe/Paris',_sgp25_clock_time(9,0),_sgp25_clock_time(17,30)),
        'SIX':Session('SIX','SIX Swiss Exchange','Europe/Zurich',_sgp25_clock_time(9,0),_sgp25_clock_time(17,30)),
        'KRX':Session('KRX','Korea Exchange','Asia/Seoul',_sgp25_clock_time(9,0),_sgp25_clock_time(15,30)),
        'NSE':Session('NSE','National Stock Exchange India','Asia/Kolkata',_sgp25_clock_time(9,15),_sgp25_clock_time(15,30)),
        'SGX':Session('SGX','Singapore Exchange','Asia/Singapore',_sgp25_clock_time(9,0),_sgp25_clock_time(17,0)),
        'B3':Session('B3','B3 Brasil','America/Sao_Paulo',_sgp25_clock_time(10,0),_sgp25_clock_time(17,0)),
        'TSX':Session('TSX','Toronto Stock Exchange','America/Toronto',_sgp25_clock_time(9,30),_sgp25_clock_time(16,0)),
        'JSE':Session('JSE','Johannesburg Stock Exchange','Africa/Johannesburg',_sgp25_clock_time(9,0),_sgp25_clock_time(17,0)),
    }
    SESSIONS.update({k:v for k,v in _extra_sessions.items() if k not in SESSIONS})
except Exception:pass

# Broader physical futures/commodity research set.
_SGP25_MORE_COMMODITIES=[
    ('OJ=F','Orange Juice','Agriculture',.0048),('GF=F','Feeder Cattle','Agriculture',.0027),
    ('ZO=F','Oats','Agriculture',.0032),('ZR=F','Rough Rice','Agriculture',.0030),
    ('KE=F','KC HRW Wheat','Agriculture',.0028),('MGC=F','Micro Gold','Metals',.0017),
    ('MCL=F','Micro WTI Crude','Energy',.0034),('SIL=F','Micro Silver','Metals',.0028),
]
_have_com={r[0] for r in COMMODITIES}
for _row in _SGP25_MORE_COMMODITIES:
    if _row[0] not in _have_com:COMMODITIES.append(_row);_have_com.add(_row[0])

# Expanded worldwide single-stock universe. Exact/full bundled constituent sets continue to be used
# for SPX, NDX, DJI, RUT/IWM proxy, FTSE, DAX and HSI; these rows deepen the remaining world indexes.
_SGP25_WORLD_ROWS=[
    # France / Euronext
    ('MC.PA','LVMH',650,.0019,'France Equity','MC.PA','EURONEXT','EUR'),('OR.PA',"L'Oreal",390,.0016,'France Equity','OR.PA','EURONEXT','EUR'),
    ('SAN.PA','Sanofi',93,.0015,'France Equity','SAN.PA','EURONEXT','EUR'),('AIR.PA','Airbus',185,.0019,'France Equity','AIR.PA','EURONEXT','EUR'),
    ('BNP.PA','BNP Paribas',78,.0018,'France Equity','BNP.PA','EURONEXT','EUR'),('SU.PA','Schneider Electric',235,.0018,'France Equity','SU.PA','EURONEXT','EUR'),
    ('AI.PA','Air Liquide',180,.0014,'France Equity','AI.PA','EURONEXT','EUR'),('DG.PA','Vinci',130,.0015,'France Equity','DG.PA','EURONEXT','EUR'),
    ('CS.PA','AXA',40,.0016,'France Equity','CS.PA','EURONEXT','EUR'),('ENGI.PA','Engie',19,.0016,'France Equity','ENGI.PA','EURONEXT','EUR'),
    ('CAP.PA','Capgemini',150,.0020,'France Equity','CAP.PA','EURONEXT','EUR'),('KER.PA','Kering',235,.0023,'France Equity','KER.PA','EURONEXT','EUR'),
    ('RMS.PA','Hermes International',2200,.0018,'France Equity','RMS.PA','EURONEXT','EUR'),('RI.PA','Pernod Ricard',105,.0017,'France Equity','RI.PA','EURONEXT','EUR'),
    # Switzerland
    ('NESN.SW','Nestle',75,.0012,'Swiss Equity','NESN.SW','SIX','CHF'),('NOVN.SW','Novartis',102,.0013,'Swiss Equity','NOVN.SW','SIX','CHF'),
    ('ROG.SW','Roche Holding',285,.0014,'Swiss Equity','ROG.SW','SIX','CHF'),('UBSG.SW','UBS Group',31,.0018,'Swiss Equity','UBSG.SW','SIX','CHF'),
    ('ZURN.SW','Zurich Insurance',550,.0014,'Swiss Equity','ZURN.SW','SIX','CHF'),('ABBN.SW','ABB',58,.0016,'Swiss Equity','ABBN.SW','SIX','CHF'),
    # Japan / Nikkei expansion (official TSE listings; broader than the original ADR-only basket)
    ('4151.T','Kyowa Kirin',2550,.0019,'Japan Equity','4151.T','TSE','JPY'),('4502.T','Takeda Pharmaceutical',4450,.0015,'Japan Equity','4502.T','TSE','JPY'),
    ('4503.T','Astellas Pharma',1500,.0017,'Japan Equity','4503.T','TSE','JPY'),('4507.T','Shionogi',2700,.0018,'Japan Equity','4507.T','TSE','JPY'),
    ('4519.T','Chugai Pharmaceutical',7300,.0018,'Japan Equity','4519.T','TSE','JPY'),('4523.T','Eisai',4700,.0020,'Japan Equity','4523.T','TSE','JPY'),
    ('4568.T','Daiichi Sankyo',3500,.0020,'Japan Equity','4568.T','TSE','JPY'),('4578.T','Otsuka Holdings',7800,.0017,'Japan Equity','4578.T','TSE','JPY'),
    ('6501.T','Hitachi',4200,.0019,'Japan Equity','6501.T','TSE','JPY'),('6503.T','Mitsubishi Electric',3100,.0018,'Japan Equity','6503.T','TSE','JPY'),
    ('6504.T','Fuji Electric',8500,.0021,'Japan Equity','6504.T','TSE','JPY'),('6506.T','Yaskawa Electric',3700,.0022,'Japan Equity','6506.T','TSE','JPY'),
    ('6701.T','NEC',3800,.0020,'Japan Equity','6701.T','TSE','JPY'),('6702.T','Fujitsu',3300,.0019,'Japan Equity','6702.T','TSE','JPY'),
    ('6723.T','Renesas Electronics',1900,.0024,'Japan Equity','6723.T','TSE','JPY'),('6752.T','Panasonic Holdings',1550,.0019,'Japan Equity','6752.T','TSE','JPY'),
    ('6758.T','Sony Group TSE',3900,.0020,'Japan Equity','6758.T','TSE','JPY'),('6762.T','TDK',1900,.0022,'Japan Equity','6762.T','TSE','JPY'),
    ('6857.T','Advantest',11500,.0030,'Japan Equity','6857.T','TSE','JPY'),('6861.T','Keyence',58000,.0021,'Japan Equity','6861.T','TSE','JPY'),
    ('6902.T','Denso',2050,.0019,'Japan Equity','6902.T','TSE','JPY'),('6920.T','Lasertec',15800,.0035,'Japan Equity','6920.T','TSE','JPY'),
    ('6954.T','Fanuc',4100,.0019,'Japan Equity','6954.T','TSE','JPY'),('6971.T','Kyocera',1750,.0018,'Japan Equity','6971.T','TSE','JPY'),
    ('6981.T','Murata Manufacturing',2250,.0020,'Japan Equity','6981.T','TSE','JPY'),('7201.T','Nissan Motor',355,.0025,'Japan Equity','7201.T','TSE','JPY'),
    ('7203.T','Toyota Motor TSE',2900,.0017,'Japan Equity','7203.T','TSE','JPY'),('7267.T','Honda Motor TSE',1550,.0018,'Japan Equity','7267.T','TSE','JPY'),
    ('7269.T','Suzuki Motor',1850,.0020,'Japan Equity','7269.T','TSE','JPY'),('7270.T','Subaru',2900,.0021,'Japan Equity','7270.T','TSE','JPY'),
    ('7735.T','SCREEN Holdings',11500,.0027,'Japan Equity','7735.T','TSE','JPY'),('7751.T','Canon',4300,.0016,'Japan Equity','7751.T','TSE','JPY'),
    ('8035.T','Tokyo Electron',26000,.0028,'Japan Equity','8035.T','TSE','JPY'),('9984.T','SoftBank Group',14500,.0030,'Japan Equity','9984.T','TSE','JPY'),
    ('9432.T','NTT',155,.0012,'Japan Equity','9432.T','TSE','JPY'),('9433.T','KDDI',2450,.0014,'Japan Equity','9433.T','TSE','JPY'),
    ('8306.T','Mitsubishi UFJ Financial',2050,.0019,'Japan Equity','8306.T','TSE','JPY'),('8316.T','Sumitomo Mitsui Financial',3900,.0019,'Japan Equity','8316.T','TSE','JPY'),
    # Korea
    ('005930.KS','Samsung Electronics',79000,.0021,'Korea Equity','005930.KS','KRX','KRW'),('000660.KS','SK Hynix',270000,.0030,'Korea Equity','000660.KS','KRX','KRW'),
    ('005380.KS','Hyundai Motor',220000,.0022,'Korea Equity','005380.KS','KRX','KRW'),('000270.KS','Kia',105000,.0022,'Korea Equity','000270.KS','KRX','KRW'),
    ('035420.KS','NAVER',225000,.0025,'Korea Equity','035420.KS','KRX','KRW'),('035720.KS','Kakao',55000,.0027,'Korea Equity','035720.KS','KRX','KRW'),
    ('051910.KS','LG Chem',310000,.0025,'Korea Equity','051910.KS','KRX','KRW'),('006400.KS','Samsung SDI',230000,.0028,'Korea Equity','006400.KS','KRX','KRW'),
    ('105560.KS','KB Financial',105000,.0020,'Korea Equity','105560.KS','KRX','KRW'),('055550.KS','Shinhan Financial',62000,.0020,'Korea Equity','055550.KS','KRX','KRW'),
    # India
    ('RELIANCE.NS','Reliance Industries',1450,.0020,'India Equity','RELIANCE.NS','NSE','INR'),('TCS.NS','Tata Consultancy Services',3200,.0018,'India Equity','TCS.NS','NSE','INR'),
    ('HDFCBANK.NS','HDFC Bank India',2000,.0018,'India Equity','HDFCBANK.NS','NSE','INR'),('ICICIBANK.NS','ICICI Bank India',1420,.0019,'India Equity','ICICIBANK.NS','NSE','INR'),
    ('INFY.NS','Infosys India',1520,.0020,'India Equity','INFY.NS','NSE','INR'),('BHARTIARTL.NS','Bharti Airtel',1900,.0018,'India Equity','BHARTIARTL.NS','NSE','INR'),
    ('SBIN.NS','State Bank of India',820,.0021,'India Equity','SBIN.NS','NSE','INR'),('LT.NS','Larsen & Toubro',3600,.0019,'India Equity','LT.NS','NSE','INR'),
    ('ITC.NS','ITC',410,.0015,'India Equity','ITC.NS','NSE','INR'),('HINDUNILVR.NS','Hindustan Unilever',2500,.0015,'India Equity','HINDUNILVR.NS','NSE','INR'),
    # Australia
    ('CBA.AX','Commonwealth Bank',175,.0017,'Australia Equity','CBA.AX','ASX','AUD'),('BHP.AX','BHP Group ASX',43,.0020,'Australia Equity','BHP.AX','ASX','AUD'),
    ('CSL.AX','CSL',205,.0018,'Australia Equity','CSL.AX','ASX','AUD'),('NAB.AX','National Australia Bank',42,.0017,'Australia Equity','NAB.AX','ASX','AUD'),
    ('WBC.AX','Westpac',36,.0018,'Australia Equity','WBC.AX','ASX','AUD'),('ANZ.AX','ANZ Group',34,.0018,'Australia Equity','ANZ.AX','ASX','AUD'),
    ('WES.AX','Wesfarmers',88,.0017,'Australia Equity','WES.AX','ASX','AUD'),('MQG.AX','Macquarie Group',205,.0020,'Australia Equity','MQG.AX','ASX','AUD'),
    ('WOW.AX','Woolworths Group',29,.0015,'Australia Equity','WOW.AX','ASX','AUD'),('RIO.AX','Rio Tinto ASX',118,.0020,'Australia Equity','RIO.AX','ASX','AUD'),
    # Canada
    ('RY.TO','Royal Bank of Canada',210,.0016,'Canada Equity','RY.TO','TSX','CAD'),('TD.TO','Toronto-Dominion Bank',112,.0017,'Canada Equity','TD.TO','TSX','CAD'),
    ('ENB.TO','Enbridge',64,.0014,'Canada Equity','ENB.TO','TSX','CAD'),('CNR.TO','Canadian National Railway',145,.0015,'Canada Equity','CNR.TO','TSX','CAD'),
    ('CNQ.TO','Canadian Natural Resources',50,.0019,'Canada Equity','CNQ.TO','TSX','CAD'),('BNS.TO','Bank of Nova Scotia',88,.0017,'Canada Equity','BNS.TO','TSX','CAD'),
    ('BMO.TO','Bank of Montreal',165,.0017,'Canada Equity','BMO.TO','TSX','CAD'),('CP.TO','Canadian Pacific Kansas City',110,.0016,'Canada Equity','CP.TO','TSX','CAD'),
    ('CSU.TO','Constellation Software',5200,.0019,'Canada Equity','CSU.TO','TSX','CAD'),('SHOP.TO','Shopify Canada',195,.0028,'Canada Equity','SHOP.TO','TSX','CAD'),
    # Brazil
    ('PETR4.SA','Petrobras PN',31,.0025,'Brazil Equity','PETR4.SA','B3','BRL'),('VALE3.SA','Vale ON',55,.0024,'Brazil Equity','VALE3.SA','B3','BRL'),
    ('ITUB4.SA','Itau Unibanco PN',38,.0020,'Brazil Equity','ITUB4.SA','B3','BRL'),('BBDC4.SA','Banco Bradesco PN',16,.0022,'Brazil Equity','BBDC4.SA','B3','BRL'),
    ('ABEV3.SA','Ambev',14,.0018,'Brazil Equity','ABEV3.SA','B3','BRL'),('WEGE3.SA','WEG',45,.0021,'Brazil Equity','WEGE3.SA','B3','BRL'),
    ('B3SA3.SA','B3 SA',15,.0021,'Brazil Equity','B3SA3.SA','B3','BRL'),('SUZB3.SA','Suzano',53,.0022,'Brazil Equity','SUZB3.SA','B3','BRL'),
    ('PRIO3.SA','PRIO',46,.0028,'Brazil Equity','PRIO3.SA','B3','BRL'),('RENT3.SA','Localiza',48,.0025,'Brazil Equity','RENT3.SA','B3','BRL'),
    # Singapore / South Africa
    ('D05.SI','DBS Group',52,.0016,'Singapore Equity','D05.SI','SGX','SGD'),('O39.SI','OCBC Bank',17,.0016,'Singapore Equity','O39.SI','SGX','SGD'),
    ('U11.SI','United Overseas Bank',36,.0016,'Singapore Equity','U11.SI','SGX','SGD'),('C6L.SI','Singapore Airlines',7,.0020,'Singapore Equity','C6L.SI','SGX','SGD'),
    ('NPN.JO','Naspers',5200,.0024,'South Africa Equity','NPN.JO','JSE','ZAR'),('FSR.JO','FirstRand',8500,.0020,'South Africa Equity','FSR.JO','JSE','ZAR'),
]
_have_global={r[0] for r in GLOBAL_STOCKS}
for _row in _SGP25_WORLD_ROWS:
    if _row[0] not in _have_global:GLOBAL_STOCKS.append(_row);_have_global.add(_row[0])

# Expand the still-representative world-index baskets without pretending an incomplete public list is exact.
_SGP25_DEEP_COMPONENTS={
 'CAC':['MC.PA','OR.PA','SAN.PA','AIR.PA','BNP.PA','SU.PA','AI.PA','DG.PA','CS.PA','ENGI.PA','CAP.PA','KER.PA','RMS.PA','RI.PA','TTE','SNY'],
 'NIKKEI':['4151.T','4502.T','4503.T','4507.T','4519.T','4523.T','4568.T','4578.T','6501.T','6503.T','6504.T','6506.T','6701.T','6702.T','6723.T','6752.T','6758.T','6762.T','6857.T','6861.T','6902.T','6920.T','6954.T','6971.T','6981.T','7201.T','7203.T','7267.T','7269.T','7270.T','7735.T','7751.T','8035.T','9984.T','9432.T','9433.T','8306.T','8316.T','TM','SONY','HMC','MUFG','SMFG'],
 'STOXX50':['SAP.DE','SIE.DE','AIR.DE','ALV.DE','BAS.DE','BAYN.DE','DTE.DE','IFX.DE','MBG.DE','MUV2.DE','RWE.DE','VOW3.DE','MC.PA','OR.PA','SAN.PA','AIR.PA','BNP.PA','SU.PA','AI.PA','DG.PA','CS.PA','RMS.PA','NESN.SW','NOVN.SW','ROG.SW','UBSG.SW','ZURN.SW','ABBN.SW'],
 'ASX200':['CBA.AX','BHP.AX','CSL.AX','NAB.AX','WBC.AX','ANZ.AX','WES.AX','MQG.AX','WOW.AX','RIO.AX','BHP'],
 'TSX':['RY.TO','TD.TO','ENB.TO','CNR.TO','CNQ.TO','BNS.TO','BMO.TO','CP.TO','CSU.TO','SHOP.TO','SHOP'],
 'BOVESPA':['PETR4.SA','VALE3.SA','ITUB4.SA','BBDC4.SA','ABEV3.SA','WEGE3.SA','B3SA3.SA','SUZB3.SA','PRIO3.SA','RENT3.SA','VALE','PBR','NU'],
}
_ng=[]
for _row in GLOBAL_INDEXES:
    _sym,_name,_price,_components,_vol,_ds,_session=_row
    _session={'CAC':'EURONEXT','TSX':'TSX','BOVESPA':'B3'}.get(_sym,_session)
    _ng.append((_sym,_name,_price,list(_SGP25_DEEP_COMPONENTS.get(_sym,_components)),_vol,_ds,_session))
GLOBAL_INDEXES[:]=_ng

# Portfolio chart attribution now snapshots every security class, not just the equity dictionary.
def _sgp25_system_record_equity(self,force=False):
    now=_sgp23_now(self);stamp=now.replace(second=0,microsecond=0)
    if not force and getattr(self,'_equity_last_stamp',None)==stamp:return
    eq=self.regulatory_equity();hold=[];m=getattr(self,'market',None)
    if m:
        for sym,q in self.positions.items():
            a=m.get_asset(sym)
            if a is not None and q:
                value=float(q)*float(a.price);hold.append((sym,int(q),float(a.price),value,str(getattr(a,'category','Security'))))
        for st in list(getattr(self,'options',[])):
            try:
                if not st.legs:continue
                under=st.legs[0].contract.underlying.symbol;qty=max(1,sum(abs(int(l.quantity)) for l in st.legs));value=float(st.current_value());hold.append((self.strategy_ref(st),qty,value/max(1,qty),value,f'Option • {under}'))
            except Exception:pass
        hold=sorted(hold,key=lambda x:abs(float(x[3])),reverse=True)[:40]
    rec={'time':_sgp_dt_iso_v20(now),'equity':eq,'cash':float(self.cash),'realized':float(self.realized),'holdings':hold}
    self.equity_history.append(rec);self.equity_history=self.equity_history[-20000:];self._equity_last_stamp=stamp
    day=now.date().isoformat();self._daily_equity_open.setdefault(day,eq)
Portfolio.record_equity_snapshot=_sgp25_system_record_equity

# ===== Stock Game Pro 2.5 final production polish: stable microstructure wicks =====
# Quote-to-quote simulation can otherwise produce candles whose high/low are identical to the
# body for long stretches. Expand each live aggregate bar by a small deterministic microstructure
# wick. The seed is tied to symbol + bar timestamp, so a completed wick NEVER changes on redraw.
_Asset_update_bar_sgp25fp_base=Asset._update_bar
def _sgp25fp_update_bar(self,interval,minutes,ts,price,volume):
    _Asset_update_bar_sgp25fp_base(self,interval,minutes,ts,price,volume)
    try:
        bars=self.live_bars.get(interval)
        if not bars:return
        c=bars[-1];ref=max(.000001,float(c.close));spread=max(.000001,float(getattr(self,'ask',ref)-getattr(self,'bid',ref)))
        # Keep ordinary wicks subtle: roughly 1-8 bps on liquid securities, somewhat larger on
        # high-volatility names. This is display/aggregation microstructure, not an extra price shock.
        cap=min(.0016,max(.00008,float(getattr(self,'volatility',.002))*.22))
        seed=sum((i+1)*ord(ch) for i,ch in enumerate(str(getattr(self,'symbol',''))))+int(c.timestamp.timestamp()//max(1,int(minutes)*60))*131
        frac=((seed%997)/996.0);frac2=(((seed//17)%991)/990.0)
        up=max(spread*.42,ref*cap*(.28+.72*frac));dn=max(spread*.42,ref*cap*(.28+.72*frac2))
        c.high=max(float(c.high),float(c.open),float(c.close),max(float(c.open),float(c.close))+up)
        c.low=max(.000001,min(float(c.low),float(c.open),float(c.close),min(float(c.open),float(c.close))-dn))
    except Exception:pass
Asset._update_bar=_sgp25fp_update_bar
