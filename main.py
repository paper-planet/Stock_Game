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
                'EURUSD=X','USDJPY=X','GBPUSD=X','AUDUSD=X','USDCAD=X','USDCHF=X']
        return list(dict.fromkeys(str(x) for x in out if x))
    except Exception:return ['SPY','^GSPC','^NDX','^DJI','^RUT','^VIX']

def main_menu(root,accounts):
    """Stock Game Pro 2.5 trader portal with fitted port-to-port commerce."""
    result={'action':'cancel','mode':'MEDIUM','cash':25000,'username':None,'profile':{}}
    w=tk.Toplevel(root);w.title('Stock Game Pro • Global Trader Portal');w.geometry('1360x820');w.minsize(1120,720);w.configure(bg='#02070c');w.protocol('WM_DELETE_WINDOW',w.destroy)
    style=ttk.Style(w);style.configure('Login.Treeview',rowheight=29,font=('Segoe UI',9),background='#071623',fieldbackground='#071623',foreground='#dceaf2');style.configure('Login.Treeview.Heading',font=('Segoe UI',9,'bold'),background='#102b3c',foreground='#b8dff1');style.map('Login.Treeview',background=[('selected','#174e6d')],foreground=[('selected','#ffffff')])
    canvas=tk.Canvas(w,bg='#02070c',highlightthickness=0);canvas.place(relx=0,rely=0,relwidth=1,relheight=1)
    anim={'phase':0.0,'job':None};preview={'AAPL':210.0,'NVDA':180.0,'MSFT':520.0,'SPY':640.0,'TSLA':340.0,'BTC':118000.0,'FTSE':9100.0,'NIKKEI':43000.0,'GOLD':3400.0,'OIL':65.0};preview_prev=dict(preview)
    # Production portal uses the same flat real-coastline geometry as the Global Map.
    # Keep the animation deliberately slow/lightweight: this screen is a launcher, not a second market engine.
    try:
        from world_land import LAND_POLYGONS as _PORTAL_LAND, COUNTRY_BORDERS as _PORTAL_BORDERS
    except Exception:
        _PORTAL_LAND=[];_PORTAL_BORDERS=[]
    portal_ex=[('NY',40.71,-74.01),('LDN',51.51,-.13),('FRA',50.11,8.68),('TYO',35.68,139.77),('HK',22.32,114.17),('SHA',31.23,121.47),('SYD',-33.87,151.21),('TOR',43.65,-79.38),('SP',-23.55,-46.63)]
    portal_ports=[('LA',33.74,-118.27),('NY',40.67,-74.04),('RTM',51.95,4.14),('SG',1.26,103.84),('SHA',31.35,121.50),('TYO',35.45,139.64),('SAN',-23.96,-46.30),('SYD',-33.96,151.21)]
    portal_routes=[(0,5),(5,4),(4,3),(3,2),(2,1),(1,0),(6,4),(7,3)]
    def draw_bg():
        if not w.winfo_exists():return
        c=canvas;c.delete('all');ww=max(1080,c.winfo_width());hh=max(700,c.winfo_height());phase=anim['phase'];anim['phase']=(phase+.004)%100000
        map_w=ww*.545;mx0,my0=18,55;mw=max(620,map_w-36);mh=max(470,hh-170)
        def xy(lat,lon):return mx0+(lon+180)/360*mw,my0+(90-lat)/180*mh
        c.create_rectangle(0,0,map_w,hh,fill='#02090f',outline='')
        c.create_rectangle(mx0,my0,mx0+mw,my0+mh,fill='#04131f',outline='#175069',width=2)
        # Geographic grid.
        for lon in range(-150,181,30):x,_=xy(0,lon);c.create_line(x,my0,x,my0+mh,fill='#0d2936')
        for lat in range(-60,61,30):_,y=xy(lat,0);c.create_line(mx0,y,mx0+mw,y,fill='#0d2936')
        # Authentic bundled coastline/country geometry, same data source used by the workstation map.
        for typ,poly in _PORTAL_LAND:
            if typ not in (1,5):continue
            pts=[]
            for lon,lat in poly:pts.extend(xy(lat,lon))
            if len(pts)>=6:c.create_polygon(*pts,fill='#113a2d',outline='#316d59',width=1)
        for typ,poly in _PORTAL_LAND:
            if typ!=2:continue
            pts=[]
            for lon,lat in poly:pts.extend(xy(lat,lon))
            if len(pts)>=6:c.create_polygon(*pts,fill='#04131f',outline='#143645')
        for seg in _PORTAL_BORDERS:
            pts=[];last=None
            for lon,lat in seg:
                x,y=xy(lat,lon)
                if last is not None and abs(x-last)>mw*.55:
                    if len(pts)>=4:c.create_line(*pts,fill='#1b4b40',width=1)
                    pts=[]
                pts.extend((x,y));last=x
            if len(pts)>=4:c.create_line(*pts,fill='#1b4b40',width=1)
        pxy=[]
        for name,lat,lon in portal_ports:
            x,y=xy(lat,lon);pxy.append((x,y));c.create_rectangle(x-4,y-4,x+4,y+4,fill='#d5b85d',outline='#fff0b0');c.create_text(x,y-9,text=name,fill='#8ddcf0',font=('Segoe UI',6,'bold'))
        for a,b in portal_routes:
            x1,y1=pxy[a];x2,y2=pxy[b];c.create_line(x1,y1,x2,y2,fill='#12657e',width=1,dash=(4,5))
        # Slow launcher-only freight motion.
        for j,(a,b) in enumerate(portal_routes[:6]):
            t=(phase*.012+j*.17)%1.0;x1,y1=pxy[a];x2,y2=pxy[b];x=x1+(x2-x1)*t;y=y1+(y2-y1)*t
            ang=math.atan2(y2-y1,x2-x1);cs,sn=math.cos(ang),math.sin(ang)
            shape=[(-9,0),(-4,-4),(7,-3),(11,0),(7,3),(-4,4)]
            pts=[]
            for px,py in shape:pts.extend((x+px*cs-py*sn,y+px*sn+py*cs))
            c.create_polygon(*pts,fill='#6fd8ef',outline='#dffaff')
        for j,(a,b) in enumerate(portal_routes[2:6]):
            t=(phase*.018+j*.23+.27)%1.0;x1,y1=pxy[a];x2,y2=pxy[b];x=x1+(x2-x1)*t;y=y1+(y2-y1)*t;ang=math.atan2(y2-y1,x2-x1);cs,sn=math.cos(ang),math.sin(ang)
            shape=[(11,0),(2,-2),(-2,-8),(-5,-8),(-3,-2),(-10,-1),(-10,1),(-3,2),(-5,8),(-2,8),(2,2)]
            pts=[]
            for px,py in shape:pts.extend((x+px*cs-py*sn,y+px*sn+py*cs))
            c.create_polygon(*pts,fill='#bdb3f5',outline='#eeeaff')
        for name,lat,lon in portal_ex:
            x,y=xy(lat,lon);c.create_oval(x-4,y-4,x+4,y+4,fill='#4bd5a1',outline='#dff7ee');c.create_text(x+6,y-6,text=name,anchor='w',fill='#96c7d7',font=('Consolas',6,'bold'))
        c.create_text(mx0+10,my0+10,anchor='nw',text='GLOBAL MARKET / FREIGHT NETWORK',fill='#dfeef4',font=('Segoe UI',10,'bold'))
        c.create_text(mx0+10,my0+29,anchor='nw',text='Real coastlines • exchange nodes • ocean + air logistics',fill='#6798aa',font=('Segoe UI',7))
        # Three launcher-preview tapes; they are local animation only and never touch account data/network.
        if int(phase*20)%5==0:
            preview_prev.update(preview)
            for k,v in list(preview.items()):preview[k]=max(.01,v*(1+random.gauss(0,.00045 if k!='BTC' else .0009)))
        def qt(k,dec=2):
            arrow='▲' if preview[k]>=preview_prev.get(k,preview[k]) else '▼';return f'{k} {arrow} {preview[k]:,.{dec}f}'
        us='NYSE/NASDAQ   '+ '   '.join(qt(k,2) for k in ('AAPL','NVDA','MSFT','SPY','TSLA'))
        glob='GLOBAL       '+ '   '.join((qt('FTSE',1),qt('NIKKEI',1),qt('GOLD',1),qt('OIL',2)))
        alt='24/7         '+qt('BTC',0)+'   •  local launcher preview'
        c.create_rectangle(0,hh-86,map_w,hh,fill='#020b12',outline='#0e3142');c.create_text(ww*.015,hh-70,text=us,anchor='w',fill='#65e5ff',font=('Consolas',8,'bold'));c.create_text(ww*.015,hh-46,text=glob,anchor='w',fill='#5fa9c1',font=('Consolas',8,'bold'));c.create_text(ww*.015,hh-23,text=alt,anchor='w',fill='#5d7180',font=('Consolas',7))
        anim['job']=w.after(250,draw_bg)
    draw_bg()

    panel=tk.Frame(w,bg='#07131e',highlightbackground='#1e617e',highlightthickness=1);panel.place(relx=.555,rely=.035,relwidth=.42,relheight=.93)
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
    ttk.Button(create_box,text='CREATE PROFILE',command=create).grid(row=1,column=2,padx=(5,10),pady=(2,10))
    buttons=tk.Frame(panel,bg='#07131e');buttons.pack(fill='x',padx=28,pady=(2,20));ttk.Button(buttons,text='ENTER WORKSTATION',command=login).pack(side='left',fill='x',expand=True,ipady=5);ttk.Button(buttons,text='DELETE',command=delete).pack(side='left',padx=6,ipady=5);ttk.Button(buttons,text='GUEST',command=guest).pack(side='left',ipady=5)
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
    def autosave(reason='autosave'):
        if not app.account_username:return
        try:
            accounts.save_session(app.account_username,portfolio.cash,market.difficulty,{'trades':portfolio.trade_count,'realized':portfolio.realized,'best_net_worth':portfolio.best_net_worth});accounts.save_profile_state(app.account_username,portfolio);accounts.save_game_state(app.account_username,portfolio,market,reason)
            try:app.status_flash(f'Saved progress • {reason}')
            except Exception:pass
        except Exception as e:
            try:market.errors.append(f'autosave: {e}')
            except Exception:pass
    market.autosave_callback=autosave
    # Crash-resilience checkpoint: end-of-day/exit saves remain authoritative, with a modest
    # real-time checkpoint so an unexpected GUI/driver crash loses at most about one minute.
    def periodic_autosave():
        try:
            if market.running and app.account_username:autosave('periodic safety checkpoint')
        finally:
            if market.running:root.after(60000,periodic_autosave)
    root.after(60000,periodic_autosave)
    sim=threading.Thread(target=simulation,args=(market,),daemon=True,name='MarketSimulation');sim.start();market.start_background_loaders()
    def stop():
        market.running=False
        if app.account_username:
            autosave('exit')
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',stop);root.mainloop();market.running=False

if __name__=='__main__':main()
