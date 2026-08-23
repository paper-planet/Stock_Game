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

# ===== Stock Game Pro 2.5 explicit-snapshot network policy =====
# Gameplay is deliberately offline. Internet access is allowed only in two explicit,
# user-visible workflows: (1) creating a new account and (2) pressing the manual
# Experimental -> Refresh Market Snapshot command and confirming its warning. All ordinary
# fetch_* entry points below remain cache-only, so charts, FIT MAX, options, global views,
# watchlists, and the simulation engine cannot silently create network traffic.
import json as _sgp26_json, pathlib as _sgp26_pathlib, threading as _sgp26_threading
from concurrent.futures import ThreadPoolExecutor as _sgp26_TPE, as_completed as _sgp26_as_completed
from datetime import datetime as _sgp26_datetime, timezone as _sgp26_timezone

_SGP26_CACHE_ROOT=_sgp26_pathlib.Path.home()/'.stock_game_pro_cache'
_SGP26_QUOTE_CACHE=_SGP26_CACHE_ROOT/'latest_quotes.json'
_SGP26_MACRO_CACHE=_SGP26_CACHE_ROOT/'macro_snapshot.json'
_SGP26_ACCOUNT_SEEDS=_SGP26_CACHE_ROOT/'account_seeds'
for _p in (_SGP26_CACHE_ROOT,_SGP26_ACCOUNT_SEEDS):
    try:_p.mkdir(parents=True,exist_ok=True)
    except Exception:pass
_SGP26_CACHE_LOCK=_sgp26_threading.RLock()

# Preserve the original network-capable functions privately. They are never called by
# normal gameplay after this patch.
_sgp26_fetch_latest_online=fetch_latest
_sgp26_fetch_many_latest_online=fetch_many_latest
_sgp26_fetch_history_online=_fetch_history_max_network
_sgp26_fetch_fred_online=fetch_fred_macro_snapshot


def _sgp26_atomic_json(path,obj):
    try:
        path=_sgp26_pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(_sgp26_json.dumps(obj,separators=(',',':')));tmp.replace(path);return True
    except Exception:return False


def load_local_quote_snapshot():
    """Return the newest locally stored quote snapshot without touching the network."""
    try:
        obj=_sgp26_json.loads(_SGP26_QUOTE_CACHE.read_text())
        return obj.get('quotes',obj) if isinstance(obj,dict) else {}
    except Exception:return {}


def _sgp26_quote_dict_from_history(symbol):
    """Recover a quote from the existing MAX-history disk cache when possible."""
    try:
        p=_hist_cache_path(symbol)
        if not p.exists():return None
        with p.open('rb') as f:bars=pickle.load(f)
        if not bars:return None
        c=bars[-1]
        ts=getattr(c,'timestamp',None)
        return {'close':float(c.close),'volume':int(getattr(c,'volume',0) or 0),
                'timestamp':ts.isoformat() if hasattr(ts,'isoformat') else None,
                'saved_at':float(p.stat().st_mtime),'source':'history-cache'}
    except Exception:return None


def cached_quote_record(symbol):
    symbol=str(symbol or '').strip()
    if not symbol:return None
    rec=load_local_quote_snapshot().get(symbol)
    if isinstance(rec,dict) and rec.get('close') is not None:return rec
    return _sgp26_quote_dict_from_history(symbol)


def fetch_latest_cached(symbol):
    rec=cached_quote_record(symbol)
    if not rec:return None
    try:
        ts=rec.get('timestamp');dt=_sgp26_datetime.fromisoformat(ts) if ts else _sgp26_datetime.fromtimestamp(float(rec.get('saved_at',0) or 0),_sgp26_timezone.utc).replace(tzinfo=None)
        if getattr(dt,'tzinfo',None):dt=dt.astimezone(_sgp26_timezone.utc).replace(tzinfo=None)
        return Quote(dt,float(rec['close']),int(rec.get('volume',0) or 0))
    except Exception:return None


def fetch_history_max_cached(symbol):
    """Read MAX daily history only from disk. Never performs an HTTP request."""
    try:
        p=_hist_cache_path(symbol)
        if p.exists():
            with p.open('rb') as f:return pickle.load(f)
    except Exception:pass
    return []


def load_account_seed(username):
    """Per-account creation-time quote snapshot. Falls back to the global local cache."""
    name=''.join(ch for ch in str(username or '').lower() if ch.isalnum() or ch in ('-','_','.'))
    if name:
        p=_SGP26_ACCOUNT_SEEDS/f'{name}.json'
        try:
            obj=_sgp26_json.loads(p.read_text());q=obj.get('quotes',{})
            if isinstance(q,dict) and q:return q
        except Exception:pass
    return load_local_quote_snapshot()


def _sgp26_parse_spark(obj):
    out={}
    try:rows=((obj or {}).get('spark') or {}).get('result') or []
    except Exception:rows=[]
    for row in rows:
        try:
            sym=str(row.get('symbol') or '').strip();resp=(row.get('response') or [{}])[0];meta=resp.get('meta') or {}
            price=meta.get('regularMarketPrice');ts=meta.get('regularMarketTime');vol=meta.get('regularMarketVolume',0)
            if price is None:
                stamps=resp.get('timestamp') or [];quote=((resp.get('indicators') or {}).get('quote') or [{}])[0]
                closes=quote.get('close') or [];vols=quote.get('volume') or []
                for i in range(len(closes)-1,-1,-1):
                    if closes[i] is not None:
                        price=closes[i];ts=stamps[i] if i<len(stamps) else ts;vol=vols[i] if i<len(vols) and vols[i] is not None else vol;break
            if not sym or price is None:continue
            dt=_sgp26_datetime.fromtimestamp(float(ts),_sgp26_timezone.utc).isoformat() if ts else _sgp26_datetime.now(_sgp26_timezone.utc).isoformat()
            out[sym]={'close':float(price),'volume':int(vol or 0),'timestamp':dt,'saved_at':_time.time(),'source':'snapshot-network'}
        except Exception:continue
    return out


def _sgp26_spark_batch(symbols,timeout=4):
    syms=[str(s).strip() for s in symbols if str(s).strip()]
    if not syms:return {}
    qs=urllib.parse.urlencode({'symbols':','.join(syms),'range':'5d','interval':'1d'})
    # Yahoo's spark endpoint is used only here because one request can seed dozens of
    # securities, avoiding thousands of individual requests during account creation.
    obj=_json('https://query1.finance.yahoo.com/v7/finance/spark?'+qs,timeout=timeout)
    return _sgp26_parse_spark(obj)


def refresh_history_cache_online(symbol):
    """Explicit account-creation-only MAX history refresh."""
    try:candles=_sgp26_fetch_history_online(symbol)
    except Exception:candles=[]
    if candles:
        try:
            with _hist_cache_path(symbol).open('wb') as f:pickle.dump(candles,f,pickle.HIGHEST_PROTOCOL)
        except Exception:pass
    return candles or fetch_history_max_cached(symbol)


def refresh_account_creation_snapshot(symbols,username=None,progress=None):
    """One-time online seed performed only while creating a brand-new account.

    If the network is unavailable, this returns the newest local quote/history cache.
    Once this call returns, the simulator's public fetch APIs are cache-only.
    """
    syms=list(dict.fromkeys(str(s).strip() for s in symbols if str(s).strip()))
    local=load_local_quote_snapshot();fresh={};network_ok=False
    # Fast probe. If this fails we immediately stay offline instead of allowing hundreds
    # of timeouts to continue after the player enters the workstation.
    probe=syms[:min(8,len(syms))]
    if progress:
        try:progress('Checking market-data connection…',0,len(syms))
        except Exception:pass
    try:
        got=_sgp26_spark_batch(probe,timeout=3)
        if got:fresh.update(got);network_ok=True
    except Exception:network_ok=False
    if network_ok:
        remaining=[s for s in syms if s not in fresh];batches=[remaining[i:i+60] for i in range(0,len(remaining),60)]
        done=len(fresh)
        with _sgp26_TPE(max_workers=6) as ex:
            futs={ex.submit(_sgp26_spark_batch,b,4):b for b in batches}
            for f in _sgp26_as_completed(futs):
                try:fresh.update(f.result() or {})
                except Exception:pass
                done+=len(futs[f])
                if progress:
                    try:progress(f'Updating creation-time market snapshot… {min(done,len(syms)):,}/{len(syms):,}',min(done,len(syms)),len(syms))
                    except Exception:pass
        if fresh:
            with _SGP26_CACHE_LOCK:
                merged=dict(local);merged.update(fresh);local=merged
                _sgp26_atomic_json(_SGP26_QUOTE_CACHE,{'saved_at':_time.time(),'quotes':local})
        # Prime only high-value broad-market history at account creation. Ordinary chart
        # use later is cache-only and can never start another download.
        for hs in ('SPY','^GSPC','^NDX','^DJI','^RUT','^VIX','QQQ'):
            try:refresh_history_cache_online(hs)
            except Exception:pass
        try:
            macro=_sgp26_fetch_fred_online()
            if macro:_sgp26_atomic_json(_SGP26_MACRO_CACHE,{'saved_at':_time.time(),'macro':macro})
        except Exception:pass
    # Fill holes from any historical files already saved locally.
    account_quotes={}
    for s in syms:
        rec=local.get(s)
        if not rec:rec=_sgp26_quote_dict_from_history(s)
        if rec:account_quotes[s]=rec
    if username:
        name=''.join(ch for ch in str(username).lower() if ch.isalnum() or ch in ('-','_','.'))
        if name:_sgp26_atomic_json(_SGP26_ACCOUNT_SEEDS/f'{name}.json',{'created_at':_time.time(),'network_refresh':bool(network_ok),'quotes':account_quotes})
    source='NETWORK + LOCAL CACHE' if network_ok and fresh else ('LOCAL CACHE' if account_quotes else 'BUNDLED SIMULATION DEFAULTS')
    return {'network_used':bool(network_ok),'fresh_quotes':len(fresh),'cached_quotes':len(account_quotes),'requested':len(syms),'source':source,'saved_at':_time.time()}



def refresh_account_market_snapshot(symbols,username=None,progress=None):
    """Explicit user-requested refresh for an existing account.

    This is intentionally the *only* gameplay-time function allowed to access the network.
    It reuses the same bounded/batched snapshot fetch used during account creation, writes
    the common local cache and the named account seed atomically, and then returns. Nothing
    keeps polling after this function exits. If internet access is unavailable it falls back
    to the newest locally cached quote/history snapshot.
    """
    info=refresh_account_creation_snapshot(symbols,username,progress)
    try:
        info=dict(info or {});info['manual_refresh']=True;info['reason']='explicit-user-refresh'
        name=''.join(ch for ch in str(username or '').lower() if ch.isalnum() or ch in ('-','_','.'))
        if name:
            p=_SGP26_ACCOUNT_SEEDS/f'{name}.json'
            try:obj=_sgp26_json.loads(p.read_text())
            except Exception:obj={'quotes':load_local_quote_snapshot()}
            obj['refreshed_at']=_time.time();obj['network_refresh']=bool(info.get('network_used'));obj['refresh_reason']='explicit-user-refresh'
            _sgp26_atomic_json(p,obj)
        return info
    except Exception:
        return info if isinstance(info,dict) else {'network_used':False,'fresh_quotes':0,'cached_quotes':0,'source':'LOCAL CACHE','manual_refresh':True}

def fetch_macro_cached():
    try:
        obj=_sgp26_json.loads(_SGP26_MACRO_CACHE.read_text());return dict(obj.get('macro',{}))
    except Exception:return {}

# Public gameplay API is OFFLINE-ONLY from this point onward.
def fetch_latest(symbol):return fetch_latest_cached(symbol)
def fetch_many_latest(symbols,workers=6):return {s:q for s in symbols if (q:=fetch_latest_cached(s)) is not None}
def fetch_history_max(symbol,cache_days=7):return fetch_history_max_cached(symbol)
def fetch_fred_macro_snapshot():return fetch_macro_cached()
