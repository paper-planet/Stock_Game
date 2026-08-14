"""Optional real-world data adapters for Stock Game Pro.

The simulator runs without network access.  When internet access is available this
module can seed live quotes / MAX history from Yahoo's public chart endpoint and can
calibrate selected US macro variables from FRED when FRED_API_KEY is set.
"""
from __future__ import annotations
import json, os, math, urllib.parse, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

@dataclass
class Quote:
    timestamp: datetime
    close: float
    volume: int = 0

UA={'User-Agent':'Mozilla/5.0 StockGamePro/1.0'}

def _json(url,timeout=8):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))

def _yahoo(symbol,interval='1d',period1=-2208988800,period2=None):
    period2=period2 or int(datetime.now(timezone.utc).timestamp())
    sym=urllib.parse.quote(symbol,safe='=^.-')
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(period1)}&period2={int(period2)}&interval={interval}&events=history&includeAdjustedClose=true'
    obj=_json(url);res=(obj.get('chart') or {}).get('result') or []
    if not res:return None
    return res[0]

def fetch_latest(symbol):
    try:
        res=_yahoo(symbol,interval='1d',period1=max(0,int(datetime.now(timezone.utc).timestamp())-10*86400))
        if not res:return None
        ts=res.get('timestamp') or [];q=((res.get('indicators') or {}).get('quote') or [{}])[0];cl=q.get('close') or [];vol=q.get('volume') or []
        for i in range(len(ts)-1,-1,-1):
            if i<len(cl) and cl[i] is not None:return Quote(datetime.fromtimestamp(ts[i],timezone.utc).replace(tzinfo=None),float(cl[i]),int((vol[i] if i<len(vol) else 0) or 0))
    except Exception:return None

def fetch_many_latest(symbols,workers=6):
    syms=list(dict.fromkeys(s for s in symbols if s));out={}
    with ThreadPoolExecutor(max_workers=max(1,min(int(workers),12))) as ex:
        fut={ex.submit(fetch_latest,s):s for s in syms}
        for f in as_completed(fut):
            try:q=f.result()
            except Exception:q=None
            if q:out[fut[f]]=q
    return out

def fetch_history_max(symbol):
    """Return all available daily candles, oldest first."""
    try:
        from game_core import Candle
        res=_yahoo(symbol,interval='1d',period1=-2208988800)
        if not res:return []
        ts=res.get('timestamp') or [];q=((res.get('indicators') or {}).get('quote') or [{}])[0]
        op=q.get('open') or [];hi=q.get('high') or [];lo=q.get('low') or [];cl=q.get('close') or [];vo=q.get('volume') or []
        out=[]
        for i,t in enumerate(ts):
            vals=[arr[i] if i<len(arr) else None for arr in (op,hi,lo,cl)]
            if any(v is None for v in vals):continue
            o,h,l,c=map(float,vals);v=int((vo[i] if i<len(vo) else 0) or 0)
            out.append(Candle(datetime.fromtimestamp(t,timezone.utc).replace(tzinfo=None),o,h,l,c,v))
        return out
    except Exception:return []

def _fred_observations(series_id,api_key,limit=60):
    qs=urllib.parse.urlencode({'series_id':series_id,'api_key':api_key,'file_type':'json','sort_order':'desc','limit':limit})
    obj=_json('https://api.stlouisfed.org/fred/series/observations?'+qs)
    vals=[]
    for row in obj.get('observations',[]):
        try:vals.append((row['date'],float(row['value'])))
        except Exception:pass
    return vals

def fetch_fred_macro_snapshot():
    """Calibrate simulator macro state from FRED if FRED_API_KEY is configured."""
    key=os.environ.get('FRED_API_KEY','').strip()
    if not key:return {}
    try:
        fed=_fred_observations('FEDFUNDS',key,4);un=_fred_observations('UNRATE',key,4);ten=_fred_observations('DGS10',key,15);cpi=_fred_observations('CPIAUCSL',key,20);gdp=_fred_observations('GDPC1',key,8)
        out={}
        if fed:out['policy_rate']=fed[0][1]
        if un:out['unemployment']=un[0][1]
        if ten:out['ten_year']=ten[0][1]
        if len(cpi)>=13 and cpi[12][1]:out['inflation']=(cpi[0][1]/cpi[12][1]-1)*100
        if len(gdp)>=5 and gdp[4][1]:out['gdp_growth']=(gdp[0][1]/gdp[4][1]-1)*100
        return {k:v for k,v in out.items() if math.isfinite(v)}
    except Exception:return {}

# ===== Stock Game Pro 1.3 persistent historical-data cache =====
import pathlib, pickle, hashlib, time as _time
_CACHE_DIR=pathlib.Path.home()/'.stock_game_pro_cache'/'history'
try:_CACHE_DIR.mkdir(parents=True,exist_ok=True)
except Exception:pass

def _hist_cache_path(symbol):
    key=hashlib.sha1(str(symbol).encode('utf-8')).hexdigest()[:18]
    return _CACHE_DIR/f'{key}.pkl'

_fetch_history_max_network=fetch_history_max
def fetch_history_max(symbol,cache_days=7):
    """All available Yahoo daily history with a local disk cache.

    This keeps subsequent launches fast and avoids repeatedly downloading decades of
    history for a large global universe. Network failure falls back to the cached copy.
    """
    path=_hist_cache_path(symbol)
    try:
        if path.exists() and (_time.time()-path.stat().st_mtime)<cache_days*86400:
            with path.open('rb') as f:return pickle.load(f)
    except Exception:pass
    candles=_fetch_history_max_network(symbol)
    if candles:
        try:
            with path.open('wb') as f:pickle.dump(candles,f,pickle.HIGHEST_PROTOCOL)
        except Exception:pass
        return candles
    try:
        if path.exists():
            with path.open('rb') as f:return pickle.load(f)
    except Exception:pass
    return []
