import asyncio,threading,tkinter as tk,sys,math,random
from tkinter import messagebox,ttk
from market import Market
from game_core import Portfolio,AccountManager
from ui import App

async def _simulation(market):
    while market.running: await market.tick()

def simulation(market):
    try:asyncio.run(_simulation(market))
    except Exception as e:market.errors.append(f'simulation thread: {type(e).__name__}: {e}')

def _account_creation_seed_symbols():
    """Yahoo/data symbols to snapshot once when a new account is created."""
    try:
        from game_core import STOCKS,COMMODITIES,INDEXES,GLOBAL_STOCKS,GLOBAL_INDEXES
        out=[r[0] for r in STOCKS]+[r[0] for r in COMMODITIES]
        out += [r[5] for r in GLOBAL_STOCKS if len(r)>5]
        out += [r[5] for r in GLOBAL_INDEXES if len(r)>5]
        idx_map={'SPX':'^GSPC','NDX':'^NDX','DJI':'^DJI','RUT':'^RUT'}
        out += [idx_map.get(r[0],r[0]) for r in INDEXES]
        out += ['^VIX','ES=F','NQ=F','YM=F','RTY=F','BTC-USD','ETH-USD','SOL-USD','XRP-USD','DOGE-USD','ADA-USD','AVAX-USD','LINK-USD','DOT-USD','LTC-USD','BCH-USD','XLM-USD','SUI-USD','TRX-USD','HBAR-USD',
                'BNB-USD','TON-USD','SHIB-USD','XMR-USD','UNI-USD','AAVE-USD','NEAR-USD','ICP-USD','ETC-USD','FIL-USD','ATOM-USD','ALGO-USD','VET-USD','APT-USD','ARB-USD','OP-USD',
                'EURUSD=X','USDJPY=X','GBPUSD=X','AUDUSD=X','USDCAD=X','USDCHF=X']
        return list(dict.fromkeys(str(x) for x in out if x))
    except Exception:return ['SPY','^GSPC','^NDX','^DJI','^RUT','^VIX']

def main_menu(root,accounts):
    """Stock Game Pro 2.5 trader portal with fitted port-to-port commerce."""
    result={'action':'cancel','mode':'MEDIUM','cash':25000,'username':None,'profile':{}}
    w=tk.Toplevel(root);w.title('Stock Game Pro • Global Trader Portal');w.geometry('1360x820');w.minsize(1120,720);w.configure(bg='#02070c');w.protocol('WM_DELETE_WINDOW',w.destroy)
    style=ttk.Style(w);style.configure('Login.Treeview',rowheight=29,font=('Segoe UI',9),background='#071623',fieldbackground='#071623',foreground='#dceaf2');style.configure('Login.Treeview.Heading',font=('Segoe UI',9,'bold'),background='#102b3c',foreground='#b8dff1');style.map('Login.Treeview',background=[('selected','#174e6d')],foreground=[('selected','#ffffff')])
    canvas=tk.Canvas(w,bg='#02070c',highlightthickness=0);canvas.place(relx=0,rely=0,relwidth=1,relheight=1)
    # Size the account/login column around the widest actual row instead of reserving a fixed
    # percentage of the screen. This leaves as much room as possible for the world-market map.
    try:
        import tkinter.font as _tkfont, datetime as _dt
        _rf=_tkfont.Font(family='Segoe UI',size=9)
        _rows=[]
        for _name,_rec in accounts.accounts.items():
            _last=_rec.get('last_login') or _rec.get('created');_lt=_dt.datetime.fromtimestamp(_last).strftime('%b %d  %H:%M') if _last else '—'
            _rows.append(f'{_name}   {_rec.get("mode","MEDIUM")}   ${float(_rec.get("cash",0)):,.0f}   {int(_rec.get("credit_score",700))}   {int(_rec.get("xp",0))}   {_lt}')
        panel_px=max(470,min(760,max([_rf.measure(x)+84 for x in _rows] or [470])))
    except Exception:panel_px=500

    # The launcher ticker is a read-only view of the newest local market snapshot. No quote
    # mutation and no HTTP request is allowed from the login screen.
    try:
        from data import load_local_quote_snapshot
        _portal_snapshot=load_local_quote_snapshot() or {}
    except Exception:_portal_snapshot={}
    _preferred=[('SPY','SPY'),('SPX','^GSPC'),('NDX','^NDX'),('DJI','^DJI'),('VIX','^VIX'),('AAPL','AAPL'),('MSFT','MSFT'),('NVDA','NVDA'),('AMZN','AMZN'),('META','META'),('TSLA','TSLA'),('JPM','JPM'),('BTC','BTC-USD'),('ETH','ETH-USD'),('GOLD','GC=F'),('OIL','CL=F'),('FTSE','^FTSE'),('DAX','^GDAXI'),('NIKKEI','^N225'),('HSI','^HSI'),('EURUSD','EURUSD=X'),('USDJPY','USDJPY=X')]
    _ticker_entries=[];_used=set()
    for _label,_sym in _preferred:
        _rec=_portal_snapshot.get(_sym)
        if isinstance(_rec,dict) and _rec.get('close') is not None:
            _ticker_entries.append((_label,float(_rec['close']),_rec.get('timestamp') or _rec.get('saved_at')));_used.add(_sym)
    # Fill the tape with additional cached instruments so it behaves like a dense exchange wall.
    for _sym,_rec in list(_portal_snapshot.items()):
        if len(_ticker_entries)>=72:break
        if _sym in _used or not isinstance(_rec,dict) or _rec.get('close') is None:continue
        try:_ticker_entries.append((str(_sym).replace('=F',''),float(_rec['close']),_rec.get('timestamp') or _rec.get('saved_at')));_used.add(_sym)
        except Exception:pass

    anim={'t0':__import__('time').monotonic(),'job':None,'static_key':None}
    try:
        from world_land import LAND_POLYGONS as _PORTAL_LAND, COUNTRY_BORDERS as _PORTAL_BORDERS
    except Exception:_PORTAL_LAND=[];_PORTAL_BORDERS=[]
    try:
        from game_core import market_status as _portal_market_status, SESSIONS as _PORTAL_SESSIONS
    except Exception:_portal_market_status=None;_PORTAL_SESSIONS={}
    portal_ex=[('NYSE','US',40.71,-74.01),('CME','CME',41.88,-87.63),('LSE','LSE',51.51,-.13),('XETRA','XETRA',50.11,8.68),('TSE','TSE',35.68,139.77),('HKEX','HKEX',22.32,114.17),('SSE','SSE',31.23,121.47),('SGX','SGX',1.35,103.82),('ASX','ASX',-33.87,151.21),('B3','B3',-23.55,-46.63)]
    portal_routes=[
      {'name':'Shanghai → Los Angeles','days':14,'points':[(31.35,121.5),(29,124),(24,138),(25,155),(30,175),(34,-165),(35,-145),(34,-125),(33.74,-118.27)]},
      {'name':'Singapore → Rotterdam','days':22,'points':[(1.26,103.84),(4,95),(7,82),(11,70),(13,58),(13,48),(18,41),(26,35),(30.2,32.6),(31.4,32.3),(34,27),(36,18),(36,8),(38,-1),(43,-9),(49,-6),(51,1),(51.95,4.14)]},
      {'name':'Rotterdam → New York','days':10,'points':[(51.95,4.14),(51,1),(49,-7),(50,-20),(47,-38),(44,-52),(41,-66),(40.67,-74.04)]},
      {'name':'Santos → Shanghai','days':28,'points':[(-23.96,-46.30),(-30,-35),(-35,-20),(-36,0),(-36,18),(-31,38),(-22,58),(-10,78),(0,97),(1,104),(8,110),(20,118),(31.35,121.5)]},
      {'name':'Sydney → Singapore','days':13,'points':[(-33.96,151.21),(-30,155),(-20,150),(-12,140),(-10,125),(-8,112),(-3,106),(1.26,103.84)]},
      {'name':'Yokohama → Los Angeles','days':12,'points':[(35.45,139.64),(32,145),(30,160),(34,178),(36,-160),(35,-140),(33.74,-118.27)]},
      {'name':'Dubai → Rotterdam','days':16,'points':[(25.27,55.30),(18,48),(13,43),(20,39),(29,33),(31.4,32.3),(35,25),(37,12),(38,0),(44,-8),(50,-4),(51.95,4.14)]},
    ]
    # Low-frequency risk monitor preview. It is visibly labeled as simulated launcher context;
    # live in-game risks come from the market/news engine after login.
    portal_risks=[('WX',30,155,0),('PIR',12,48,9),('POL',49,18,17),('LOG',1,103,25),('WX',-31,150,31)]
    def draw_bg():
        if not w.winfo_exists():return
        import time as _time
        c=canvas;ww=max(1080,c.winfo_width());hh=max(700,c.winfo_height());elapsed=_time.monotonic()-anim['t0'];map_w=max(610,ww-panel_px-38);mx0,my0=18,50;mw=max(560,map_w-36);mh=max(455,hh-145)
        def xy(lat,lon):return mx0+(lon+180)/360*mw,my0+(90-lat)/180*mh
        skey=(int(ww),int(hh),int(map_w))
        if skey!=anim.get('static_key'):
            anim['static_key']=skey;c.delete('portal_static')
            c.create_rectangle(0,0,map_w,hh,fill='#02090f',outline='',tags='portal_static');c.create_rectangle(mx0,my0,mx0+mw,my0+mh,fill='#04131f',outline='#175069',width=2,tags='portal_static')
            for lon in range(-150,181,30):x,_=xy(0,lon);c.create_line(x,my0,x,my0+mh,fill='#0d2936',tags='portal_static')
            for lat in range(-60,61,30):_,y=xy(lat,0);c.create_line(mx0,y,mx0+mw,y,fill='#0d2936',tags='portal_static')
            for typ,poly in _PORTAL_LAND:
                if typ not in (1,5):continue
                pts=[]
                for lon,lat in poly:pts.extend(xy(lat,lon))
                if len(pts)>=6:c.create_polygon(*pts,fill='#113a2d',outline='#316d59',width=1,tags='portal_static')
            for typ,poly in _PORTAL_LAND:
                if typ!=2:continue
                pts=[]
                for lon,lat in poly:pts.extend(xy(lat,lon))
                if len(pts)>=6:c.create_polygon(*pts,fill='#04131f',outline='#143645',tags='portal_static')
            for seg in _PORTAL_BORDERS:
                pts=[];last=None
                for lon,lat in seg:
                    x,y=xy(lat,lon)
                    if last is not None and abs(x-last)>mw*.55:
                        if len(pts)>=4:c.create_line(*pts,fill='#1b4b40',width=1,tags='portal_static')
                        pts=[]
                    pts.extend((x,y));last=x
                if len(pts)>=4:c.create_line(*pts,fill='#1b4b40',width=1,tags='portal_static')
            # Ocean-safe waypoints are drawn as segmented trade lanes instead of port-to-port chords.
            for route in portal_routes:
                seg=[];lastx=None
                for lat,lon in route['points']:
                    x,y=xy(lat,lon)
                    if lastx is not None and abs(x-lastx)>mw*.55:
                        if len(seg)>=4:c.create_line(*seg,fill='#12657e',width=1,dash=(4,5),tags='portal_static')
                        seg=[]
                    seg.extend((x,y));lastx=x
                if len(seg)>=4:c.create_line(*seg,fill='#12657e',width=1,dash=(4,5),tags='portal_static')
            c.create_text(mx0+10,my0+8,anchor='nw',text='GLOBAL MARKET / TRADE NETWORK',fill='#dfeef4',font=('Segoe UI',10,'bold'),tags='portal_static')
            c.create_text(mx0+10,my0+27,anchor='nw',text='Real coastlines • exchange sessions • ocean + air logistics',fill='#6798aa',font=('Segoe UI',7),tags='portal_static')
        c.delete('portal_dynamic')
        # Exchange state uses the real wall clock while the player is at the login portal.
        try:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo as _ZI
            now_et=_dt.now(_ZI('America/New_York')).replace(tzinfo=None)
        except Exception:now_et=None
        for name,code,lat,lon in portal_ex:
            x,y=xy(lat,lon)
            try:op=bool(_portal_market_status(code,now_et)) if _portal_market_status else False
            except Exception:op=False
            c.create_oval(x-5,y-5,x+5,y+5,fill='#28c996' if op else '#596875',outline='#e1edf2',tags='portal_dynamic');c.create_text(x+7,y-7,text=f'{name} {"OPEN" if op else "CLOSED"}',anchor='w',fill='#8fd9c2' if op else '#82929c',font=('Consolas',6,'bold'),tags='portal_dynamic')
        def route_pos(points,t):
            if len(points)<2:return points[0][0],points[0][1],0
            segs=[];total=0.0
            for a,b in zip(points,points[1:]):
                la1,lo1=a;la2,lo2=b;dl=lo2-lo1
                if dl>180:dl-=360
                elif dl<-180:dl+=360
                dist=max(.001,((la2-la1)**2+(dl*max(.25,math.cos(math.radians((la1+la2)/2))))**2)**.5);segs.append((dist,a,b,dl));total+=dist
            target=(t%1.0)*total;acc=0.0
            for dist,a,b,dl in segs:
                if acc+dist>=target:
                    f=(target-acc)/dist;la=a[0]+(b[0]-a[0])*f;lo=a[1]+dl*f
                    while lo>180:lo-=360
                    while lo<-180:lo+=360
                    la2,lo2=b;x,y=xy(la,lo);xn,yn=xy(la2,lo2);return x,y,math.atan2(yn-y,xn-x)
                acc+=dist
            x,y=xy(*points[-1]);return x,y,0
        # Faster launcher animation is purely visual and does not alter the simulator clock.
        for j,route in enumerate(portal_routes):
            t=(elapsed/(20.0+j*2.3)+j*.137)%1.0;x,y,ang=route_pos(route['points'],t);cs,sn=math.cos(ang),math.sin(ang);shape=[(-10,2),(-8,-2),(-3,-4),(8,-3),(12,0),(8,3),(-3,4)] ;pts=[]
            for px,py in shape:pts.extend((x+px*cs-py*sn,y+px*sn+py*cs))
            c.create_polygon(*pts,fill='#6fd8ef',outline='#dffaff',tags='portal_dynamic')
        # Air corridors are approximate great-circle-like arcs between logistics hubs.
        airs=[((40.64,-73.78),(51.47,-.45),9.0),((33.94,-118.40),(35.77,140.39),14.0),((50.04,8.56),(1.36,103.99),16.0),((25.25,55.36),(22.31,113.91),11.0)]
        for j,(a,b,dur) in enumerate(airs):
            t=(elapsed/dur+j*.23)%1.0;la=a[0]+(b[0]-a[0])*t;dl=b[1]-a[1]
            if dl>180:dl-=360
            elif dl<-180:dl+=360
            lo=a[1]+dl*t
            while lo>180:lo-=360
            while lo<-180:lo+=360
            la+=math.sin(math.pi*t)*5.0;x,y=xy(la,lo);t2=min(.999,t+.008);la2=a[0]+(b[0]-a[0])*t2+math.sin(math.pi*t2)*5.0;lo2=a[1]+dl*t2
            while lo2>180:lo2-=360
            while lo2<-180:lo2+=360
            xn,yn=xy(la2,lo2);ang=math.atan2(yn-y,xn-x);cs,sn=math.cos(ang),math.sin(ang);shape=[(10,0),(2,-2),(-1,-7),(-4,-7),(-3,-2),(-9,-1),(-9,1),(-3,2),(-4,7),(-1,7),(2,2)];pts=[]
            for px,py in shape:pts.extend((x+px*cs-py*sn,y+px*sn+py*cs))
            c.create_polygon(*pts,fill='#bdb3f5',outline='#eeeaff',tags='portal_dynamic')
        # Slow natural risk breathing, never rapid strobing.
        for label,lat,lon,offset in portal_risks:
            life=(elapsed+offset)%44.0
            if life>31:continue
            strength=max(0.0,min(1.0,life/5.0,(31-life)/7.0));pulse=.5+.5*math.sin((elapsed+offset)*1.15);r=5+5*strength+2*pulse;x,y=xy(lat,lon)
            c.create_oval(x-r,y-r,x+r,y+r,outline='#e89355',width=1 if strength<.55 else 2,stipple='gray50',tags='portal_dynamic');c.create_text(x+r+3,y,text=label,anchor='w',fill='#b57e58',font=('Consolas',6,'bold'),tags='portal_dynamic')
        # Multiple market clocks make it obvious which regions are currently active.
        try:
            aware=__import__('datetime').datetime.now(__import__('zoneinfo').ZoneInfo('UTC'))
        except Exception:aware=None
        try:
            import datetime as _datetime
            from zoneinfo import ZoneInfo as _ZoneInfo
            utc=_datetime.datetime.now(_datetime.timezone.utc);zones=[('NY','America/New_York'),('LDN','Europe/London'),('FRA','Europe/Berlin'),('TYO','Asia/Tokyo'),('HK','Asia/Hong_Kong'),('SYD','Australia/Sydney')];zt='   '.join(f'{n} {utc.astimezone(_ZoneInfo(z)):%H:%M}' for n,z in zones)
            c.create_rectangle(mx0+7,my0+mh-27,mx0+mw-7,my0+mh-5,fill='#06131d',outline='#173848',tags='portal_dynamic');c.create_text(mx0+14,my0+mh-16,anchor='w',text=zt,fill='#86aebe',font=('Consolas',7,'bold'),tags='portal_dynamic')
        except Exception:pass
        # NYSE-style single-row tape sourced from the local creation/refresh snapshot.
        tape_y=hh-42;c.create_rectangle(0,tape_y,map_w,hh,fill='#000000',outline='#1d2830',tags='portal_dynamic')
        if _ticker_entries:
            tape='    '.join(f'{sym}  {px:,.2f}' for sym,px,_ in _ticker_entries)+'     '
            est=max(1000,len(tape)*7);offset=(elapsed*74)%est;c.create_text(map_w-offset,tape_y+21,anchor='w',text=tape+tape,fill='#e8edf0',font=('Consolas',9,'bold'),tags='portal_dynamic')
            c.create_text(7,tape_y+5,anchor='nw',text='LOCAL MARKET SNAPSHOT',fill='#6f8c99',font=('Segoe UI',6,'bold'),tags='portal_dynamic')
        else:c.create_text(12,tape_y+21,anchor='w',text='LOCAL MARKET SNAPSHOT UNAVAILABLE • CREATE OR REFRESH AN ACCOUNT TO CACHE CURRENT QUOTES',fill='#8ea0a9',font=('Consolas',8,'bold'),tags='portal_dynamic')
        anim['job']=w.after(80,draw_bg)
    canvas.bind('<Configure>',lambda e:anim.__setitem__('static_key',None))
    draw_bg()

    panel=tk.Frame(w,bg='#07131e',highlightbackground='#1e617e',highlightthickness=1);panel.place(relx=1.0,x=-18,y=28,width=panel_px,relheight=.93,anchor='ne')
    header=tk.Frame(panel,bg='#07131e');header.pack(fill='x',padx=22,pady=(18,8))
    tk.Label(header,text='STOCK GAME PRO',bg='#07131e',fg='#f3f8fb',font=('Segoe UI',24,'bold')).pack(anchor='w')
    tk.Label(header,text='2.5  •  GLOBAL TRADER PORTAL',bg='#07131e',fg='#57cce9',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(2,0))
    tk.Label(header,text='Select a saved account, review the profile, then enter the workstation.',bg='#07131e',fg='#8fa9b8',font=('Segoe UI',10),wraplength=440,justify='left').pack(anchor='w',pady=(8,0))
    table_wrap=tk.Frame(panel,bg='#07131e');table_wrap.pack(fill='both',expand=True,padx=20,pady=(4,6))
    tv=ttk.Treeview(table_wrap,style='Login.Treeview',columns=('account','mode','cash','credit','xp','last'),show='headings',selectmode='browse',height=10)
    specs=[('account','TRADER',118),('mode','MODE',62),('cash','CASH',132),('credit','CREDIT',62),('xp','XP',62),('last','LAST SESSION',116)]
    for col,title,width in specs:tv.heading(col,text=title);tv.column(col,width=width,minwidth=52,anchor='w' if col in ('account','cash','last') else 'center',stretch=True)
    def resize_account_columns(event=None):
        try:
            width=max(520,table_wrap.winfo_width()-22);cash_chars=max([len(f"${float(r.get('cash',0)):,.0f}") for r in accounts.accounts.values()] or [10]);cash_w=min(int(width*.34),max(112,cash_chars*9+24))
            fixed={'mode':max(60,int(width*.10)),'credit':max(62,int(width*.10)),'xp':max(60,int(width*.09))};remaining=max(220,width-cash_w-sum(fixed.values()));account_w=max(105,int(remaining*.47));last_w=max(115,remaining-account_w)
            for c,wid in [('account',account_w),('mode',fixed['mode']),('cash',cash_w),('credit',fixed['credit']),('xp',fixed['xp']),('last',last_w)]:tv.column(c,width=wid,minwidth=52,stretch=True)
        except Exception:pass
    table_wrap.bind('<Configure>',resize_account_columns)
    sb=ttk.Scrollbar(table_wrap,orient='vertical',command=tv.yview);tv.configure(yscrollcommand=sb.set);tv.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y')
    status=tk.Label(panel,text='Ready.',bg='#07131e',fg='#8fa9b8',font=('Segoe UI',9));status.pack(fill='x',padx=28,pady=(0,7))
    create_box=tk.Frame(panel,bg='#0a1d2b',highlightbackground='#143b50',highlightthickness=1);create_box.pack(fill='x',padx=28,pady=(0,10))
    tk.Label(create_box,text='NEW TRADER PROFILE',bg='#0a1d2b',fg='#6bcfe8',font=('Segoe UI',9,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',padx=10,pady=(8,3))
    tk.Label(create_box,text='EASY $50,000  •  MEDIUM $25,000  •  EXPERT $1,000',bg='#0a1d2b',fg='#6f8e9f',font=('Segoe UI',8)).grid(row=2,column=0,columnspan=3,sticky='w',padx=10,pady=(0,8))
    user=tk.Entry(create_box,bg='#eef5f8',fg='#10202a',relief='flat',font=('Segoe UI',10));user.grid(row=1,column=0,sticky='ew',padx=(10,5),pady=(2,10),ipady=6);user.insert(0,'account name')
    mode=tk.StringVar(value='MEDIUM');ttk.Combobox(create_box,textvariable=mode,values=['EASY','MEDIUM','EXPERT'],state='readonly',width=10).grid(row=1,column=1,padx=5,pady=(2,10));create_box.columnconfigure(0,weight=1)
    def selected_name():
        it=tv.selection();return tv.item(it[0],'values')[0] if it else ''
    def refresh_accounts(select=None):
        tv.delete(*tv.get_children());import datetime
        for name,rec in sorted(accounts.accounts.items()):
            stats=rec.get('stats',{});last=rec.get('last_login') or rec.get('created');lasttxt=datetime.datetime.fromtimestamp(last).strftime('%b %d  %H:%M') if last else '—';tv.insert('','end',iid=name,values=(name,rec.get('mode','MEDIUM'),f"${float(rec.get('cash',0)):,.0f}",int(rec.get('credit_score',700)),int(rec.get('xp',0)),lasttxt))
        resize_account_columns()
        if select and select in tv.get_children():tv.selection_set(select);tv.focus(select);tv.see(select)
    def login():
        name=selected_name()
        if not name:return status.config(text='Select a saved trader profile first.',fg='#ff6b7d')
        rec=accounts.login(name)
        if not rec:return status.config(text='Account no longer exists.',fg='#ff6b7d')
        result.update(action='start',username=rec['username'],mode=rec.get('mode','MEDIUM'),cash=float(rec.get('cash',25000)),profile=rec);w.destroy()
    def delete():
        name=selected_name()
        if not name:return status.config(text='Select an account to delete.',fg='#ff6b7d')
        if messagebox.askyesno('Delete trader profile',f'Delete “{name}” and its saved progress? This cannot be undone.'):
            ok,msg=accounts.delete(name);status.config(text=msg,fg='#31d6a0' if ok else '#ff6b7d');refresh_accounts()
    def create():
        name=user.get().strip().lower();name='' if name=='account name' else name;ok,msg=accounts.create(name,mode.get());status.config(text=msg,fg='#31d6a0' if ok else '#ff6b7d')
        if not ok:return
        user.delete(0,'end');refresh_accounts(name)
        # The ONLY intentional network window in Stock Game Pro is this creation-time
        # snapshot. A modal keeps the player out of the workstation until every request
        # has completed, ensuring no downloader can remain alive during gameplay.
        sync=tk.Toplevel(w);sync.title('Create Market Snapshot');sync.geometry('520x180');sync.resizable(False,False);sync.transient(w);sync.grab_set();sync.configure(bg='#07131e');sync.protocol('WM_DELETE_WINDOW',lambda:None)
        tk.Label(sync,text='SETTING ACCOUNT MARKET BASELINE',bg='#07131e',fg='#f3f8fb',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=20,pady=(20,6))
        tk.Label(sync,text='Checking for the newest market quotes now. This is the only time the game uses the internet. If unavailable, the newest local cache is used instead.',bg='#07131e',fg='#8fa9b8',font=('Segoe UI',9),wraplength=475,justify='left').pack(anchor='w',padx=20,pady=(0,12))
        bar=ttk.Progressbar(sync,mode='indeterminate');bar.pack(fill='x',padx=20,pady=4);bar.start(12)
        sync_msg=tk.Label(sync,text='Creation-time data sync…',bg='#07131e',fg='#57cce9',font=('Segoe UI',9,'bold'));sync_msg.pack(anchor='w',padx=20,pady=6)
        state={}
        def worker():
            try:
                from data import refresh_account_creation_snapshot
                state['result']=refresh_account_creation_snapshot(_account_creation_seed_symbols(),name)
            except Exception as e:state['error']=str(e)
        threading.Thread(target=worker,daemon=True,name='AccountCreationMarketSeed').start()
        def poll():
            if 'result' not in state and 'error' not in state:
                if sync.winfo_exists():w.after(120,poll)
                return
            try:bar.stop();sync.grab_release();sync.destroy()
            except Exception:pass
            info=state.get('result') or {'source':'BUNDLED SIMULATION DEFAULTS','fresh_quotes':0,'cached_quotes':0,'network_used':False,'error':state.get('error')}
            try:accounts.set_market_seed_info(name,info)
            except Exception:pass
            status.config(text=f"Account created • market baseline: {info.get('source','LOCAL')} • {int(info.get('cached_quotes',0)):,} cached / {int(info.get('fresh_quotes',0)):,} freshly updated • gameplay will be offline",fg='#31d6a0')
            refresh_accounts(name)
        w.after(120,poll)
    def guest():result.update(action='start',username=None,mode=mode.get(),cash={'EASY':50000,'MEDIUM':25000,'EXPERT':1000}[mode.get()],profile={});w.destroy()
    def graphics():
        gw=tk.Toplevel(w);gw.title('Graphics / Performance');gw.geometry('520x330');gw.transient(w);gw.configure(bg='#07131e');profiles={'Efficiency':'Lowest CPU/RAM pressure; reduced animation density.','Balanced':'Recommended for the full global universe.','Smooth':'More CPU/RAM for smoother charts and map motion.','Maximum':'Highest CPU/RAM budget. Tkinter Canvas remains CPU-rendered; GPU allocation is OS-managed.'}
        try:
            import json as _j;from pathlib import Path as _P;pp=_P.home()/'.stock_game_pro_cache'/'performance_profile.json';cur=_j.loads(pp.read_text()).get('profile','Balanced') if pp.exists() else 'Balanced'
        except Exception:cur='Balanced'
        v=tk.StringVar(value=cur if cur in profiles else 'Balanced');tk.Label(gw,text='GRAPHICS / PERFORMANCE',bg='#07131e',fg='#f3f8fb',font=('Segoe UI',14,'bold')).pack(anchor='w',padx=18,pady=(18,6));tk.Label(gw,text='Choose how much CPU/RAM work the simulator may spend on visible animation, chart cadence and broad-market batches.',bg='#07131e',fg='#8fa9b8',wraplength=480,justify='left').pack(anchor='w',padx=18,pady=(0,10));cb=ttk.Combobox(gw,textvariable=v,values=list(profiles),state='readonly',width=18);cb.pack(anchor='w',padx=18);lab=tk.Label(gw,bg='#07131e',fg='#8fa9b8',wraplength=470,justify='left');lab.pack(anchor='w',padx=18,pady=12)
        def upd(*_):lab.config(text=profiles[v.get()])
        def save():
            try:pp.parent.mkdir(parents=True,exist_ok=True);pp.write_text(_j.dumps({'profile':v.get()}))
            except Exception:pass
            gw.destroy()
        cb.bind('<<ComboboxSelected>>',upd);upd();ttk.Button(gw,text='SAVE PROFILE',command=save).pack(anchor='w',padx=18,pady=8)
    ttk.Button(create_box,text='CREATE PROFILE',command=create).grid(row=1,column=2,padx=(5,10),pady=(2,10))
    buttons=tk.Frame(panel,bg='#07131e');buttons.pack(fill='x',padx=28,pady=(2,20));ttk.Button(buttons,text='ENTER WORKSTATION',command=login).pack(side='left',fill='x',expand=True,ipady=5);ttk.Button(buttons,text='DELETE',command=delete).pack(side='left',padx=4,ipady=5);ttk.Button(buttons,text='GUEST',command=guest).pack(side='left',padx=4,ipady=5);ttk.Button(buttons,text='GRAPHICS',command=graphics).pack(side='left',ipady=5)
    tv.bind('<Double-1>',lambda e:login());refresh_accounts();root.wait_window(w);return result

def main():
    root=tk.Tk();root.withdraw();accounts=AccountManager();choice={'action':'start','username':None,'mode':'MEDIUM','cash':25000} if '--guest' in sys.argv else main_menu(root,accounts)
    if choice['action']!='start':root.destroy();return
    root.deiconify();market=Market();market.difficulty=choice['mode'];market.speed=.025;market.time_warp=1/60;market.account_username=choice.get('username')
    # Apply the account's frozen creation-time quote snapshot from disk before the simulation
    # starts. Existing saved game-state prices are restored immediately afterward.
    try:market.load_account_market_seed(choice.get('username'))
    except Exception as e:market.errors.append(f'local account seed: {e}')
    portfolio=Portfolio(choice['cash']);profile=choice.get('profile') or {};portfolio.xp=int(profile.get('xp',0));portfolio.credit_score=int(profile.get('credit_score',700));portfolio.loan_balance=float(profile.get('loan_balance',0.0));portfolio.loan_apr=float(profile.get('loan_apr',0.0));portfolio.loan_origin=profile.get('loan_origin');portfolio.last_loan_payment=profile.get('last_loan_payment');portfolio.tutorials=dict(profile.get('tutorials',{}));portfolio.career=dict(profile.get('career',portfolio.career));portfolio.market=market;market.portfolio=portfolio;
    if choice.get('username'):
        try:accounts.restore_game_state(choice.get('username'),portfolio,market)
        except Exception as e:print(f'Unable to restore saved trading state: {e}')
    app=App(root,market,portfolio);app.account_username=choice.get('username');app.account_manager=accounts
    try:app.update_experiment_account_menu()
    except Exception:pass
    _autosave_lock=threading.Lock()
    def autosave(reason='autosave'):
        if not app.account_username:return
        try:
            # End-of-day can originate on the simulation thread while the 30-second checkpoint
            # runs on Tk's thread. Serialize file writes so the save JSON cannot be interleaved.
            with _autosave_lock:
                accounts.save_session(app.account_username,portfolio.cash,market.difficulty,{'trades':portfolio.trade_count,'realized':portfolio.realized,'best_net_worth':portfolio.best_net_worth});accounts.save_profile_state(app.account_username,portfolio);accounts.save_game_state(app.account_username,portfolio,market,reason)
            if threading.current_thread() is threading.main_thread():
                try:app.status_flash(f'Saved progress • {reason}')
                except Exception:pass
            else:
                market._ui_status_message25=f'Saved progress • {reason}'
        except Exception as e:
            try:market.errors.append(f'autosave: {e}')
            except Exception:pass
    market.autosave_callback=autosave
    # Crash-resilience checkpoint: end-of-day/exit saves remain authoritative, with a modest
    # real-time checkpoint so an unexpected GUI/driver crash loses at most about thirty seconds.
    def periodic_autosave():
        try:
            if market.running and app.account_username:autosave('periodic safety checkpoint')
        finally:
            if market.running:root.after(30000,periodic_autosave)
    root.after(30000,periodic_autosave)
    sim=threading.Thread(target=simulation,args=(market,),daemon=True,name='MarketSimulation');sim.start();market.start_background_loaders()
    def stop():
        market.running=False
        if app.account_username:
            autosave('exit')
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',stop);root.mainloop();market.running=False

if __name__=='__main__':main()
