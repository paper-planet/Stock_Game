"""Small dependency-free market-data bridge."""
import json,time,urllib.parse,urllib.request
from datetime import datetime,timezone
import threading
from assets import Candle
USER_AGENT='Mozilla/5.0 STOCK_GAME/5.0'
def _url(symbol,p1=0,interval='1d'):
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='')}?period1={int(p1)}&period2={int(time.time())}&interval={interval}&events=history&includeAdjustedClose=true"
def fetch_history(symbol,period1=0,interval='1d',timeout=8):
    try:
        req=urllib.request.Request(_url(symbol,period1,interval),headers={'User-Agent':USER_AGENT})
        with urllib.request.urlopen(req,timeout=timeout) as r: payload=json.load(r)
        result=(payload.get('chart',{}).get('result') or [None])[0]
        if not result:return []
        ts=result.get('timestamp') or []; q=(result.get('indicators',{}).get('quote') or [{}])[0]
        fields=[q.get(k) or [] for k in ('open','high','low','close','volume')]; out=[]
        for i,t in enumerate(ts):
            if any(i>=len(x) or x[i] is None for x in fields[:4]):continue
            dt=datetime.fromtimestamp(t,tz=timezone.utc).replace(tzinfo=None)
            out.append(Candle(dt,float(fields[0][i]),float(fields[1][i]),float(fields[2][i]),float(fields[3][i]),int(fields[4][i] or 0) if i<len(fields[4]) else 0))
        return out
    except Exception:return []
def fetch_latest(symbol,timeout=6):
    c=fetch_history(symbol,max(0,int(time.time())-45*86400),'1d',timeout);return c[-1] if c else None
def fetch_many_latest(symbols,workers=10):
    # Use explicitly daemonized workers. ThreadPoolExecutor creates non-daemon
    # worker threads, which could keep a closed Tkinter game alive while a
    # network request was waiting for its timeout.
    out={}; lock=threading.Lock(); sem=threading.Semaphore(max(1,int(workers))); threads=[]
    def worker(symbol):
        try:
            c=fetch_latest(symbol)
            if c:
                with lock: out[symbol]=c
        finally:
            sem.release()
    for symbol in symbols:
        sem.acquire()
        t=threading.Thread(target=worker,args=(symbol,),daemon=True)
        threads.append(t);t.start()
    for t in threads:t.join(timeout=7)
    return out


def fetch_sp500_constituents(timeout=8):
    """Fetch the current S&P 500 symbol/security/sector table from Wikipedia.
    Returns a list of (symbol, name, sector) and gracefully falls back to [].
    """
    from html.parser import HTMLParser
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(); self.in_tr=False; self.in_td=False; self.buf=[]; self.row=[]; self.rows=[]; self.header=False
        def handle_starttag(self,tag,attrs):
            if tag=='tr': self.in_tr=True; self.row=[]
            elif tag in ('td','th') and self.in_tr: self.in_td=True; self.buf=[]
        def handle_endtag(self,tag):
            if tag in ('td','th') and self.in_td:
                txt=' '.join(''.join(self.buf).split()); self.row.append(txt); self.in_td=False
            elif tag=='tr' and self.in_tr:
                if len(self.row)>=3:
                    if self.row[0].lower()=='symbol': self.header=True
                    elif self.header and len(self.row[0])<=12: self.rows.append(tuple(self.row[:3]))
                self.in_tr=False
        def handle_data(self,data):
            if self.in_td:self.buf.append(data)
    try:
        req=urllib.request.Request('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',headers={'User-Agent':USER_AGENT})
        with urllib.request.urlopen(req,timeout=timeout) as r: html=r.read().decode('utf-8','ignore')
        parser=Parser(); parser.feed(html); out=[]
        for sym,name,sector in parser.rows:
            sym=sym.replace('\xa0','').strip(); name=' '.join(name.split()); sector=' '.join(sector.split())
            if sym and sym not in {x[0] for x in out}: out.append((sym,name,sector))
        return out[:600]
    except Exception:
        return []


def fetch_market_caps(symbols,timeout=8):
    """Best-effort Yahoo quote metadata lookup for market-cap sizing."""
    out={}
    try:
        chunks=[symbols[i:i+100] for i in range(0,len(symbols),100)]
        for chunk in chunks:
            url='https://query1.finance.yahoo.com/v7/finance/quote?symbols='+urllib.parse.quote(','.join(chunk),safe=',')
            req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
            with urllib.request.urlopen(req,timeout=timeout) as r: payload=json.load(r)
            for q in (payload.get('quoteResponse',{}).get('result') or []):
                sym=q.get('symbol'); cap=q.get('marketCap'); shares=q.get('sharesOutstanding')
                if sym and cap: out[sym]=(float(cap),float(shares or 0))
    except Exception: pass
    return out


def fetch_us_equities(timeout=8):
    """Best-effort broad US equity universe from Nasdaq screener; returns (symbol,name,sector)."""
    import json, urllib.request, urllib.parse
    try:
        url='https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&exchange=nasdaq,nyse,amex'
        req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json, text/plain, */*','Referer':'https://www.nasdaq.com/'})
        with urllib.request.urlopen(req,timeout=timeout) as r: payload=json.load(r)
        rows=((payload.get('data') or {}).get('rows') or [])
        out=[]
        for row in rows:
            sym=str(row.get('symbol') or '').strip().upper();name=str(row.get('name') or sym).strip()
            if not sym or len(sym)>10 or any(ch in sym for ch in '^/='): continue
            sector=str(row.get('sector') or 'US Equity').strip()
            out.append((sym,name,sector))
        return out
    except Exception:
        return []
