"""Small dependency-free market-data bridge. Network failures are non-fatal."""
import json,time,urllib.parse,urllib.request,threading
from datetime import datetime,timezone
from asset import Candle
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
