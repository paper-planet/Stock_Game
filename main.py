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

def main_menu(root,accounts):
    """Stock Game Pro 1.7 trader portal with fitted port-to-port commerce."""
    result={'action':'cancel','mode':'MEDIUM','cash':250000,'username':None,'profile':{}}
    w=tk.Toplevel(root);w.title('Stock Game Pro • Global Trader Portal');w.geometry('1360x820');w.minsize(1120,720);w.configure(bg='#02070c');w.protocol('WM_DELETE_WINDOW',w.destroy)
    style=ttk.Style(w);style.configure('Login.Treeview',rowheight=29,font=('Segoe UI',9),background='#071623',fieldbackground='#071623',foreground='#dceaf2');style.configure('Login.Treeview.Heading',font=('Segoe UI',9,'bold'),background='#102b3c',foreground='#b8dff1');style.map('Login.Treeview',background=[('selected','#174e6d')],foreground=[('selected','#ffffff')])
    canvas=tk.Canvas(w,bg='#02070c',highlightthickness=0);canvas.place(relx=0,rely=0,relwidth=1,relheight=1)
    anim={'phase':0.0,'job':None};preview={'AAPL':210.0,'NVDA':180.0,'MSFT':520.0,'SPY':640.0,'TSLA':340.0,'BTC':118000.0,'FTSE':9100.0,'NIKKEI':43000.0,'GOLD':3400.0,'OIL':65.0};preview_prev=dict(preview)
    # Stylized continents and real-ish port anchor positions. This is intentionally a
    # lightweight hologram so the login screen remains responsive.
    land=[ [(-.88,-.30),(-.72,-.46),(-.50,-.37),(-.43,-.12),(-.55,.02),(-.68,.02),(-.82,-.10)],
           [(-.58,.10),(-.48,.18),(-.43,.40),(-.50,.62),(-.62,.45),(-.66,.22)],
           [(-.14,-.36),(.05,-.42),(.22,-.28),(.18,-.02),(.02,.05),(-.10,-.04)],
           [(.02,.08),(.22,.05),(.32,.22),(.26,.55),(.08,.62),(-.02,.38)],
           [(.18,-.34),(.48,-.43),(.78,-.28),(.90,-.05),(.71,.12),(.46,.07),(.27,-.06)],
           [(.62,.28),(.84,.24),(.90,.48),(.70,.58),(.55,.45)] ]
    ports=[('LA',-.82,-.10),('NY',-.43,-.12),('RTM',-.14,-.36),('DXB',.27,-.06),('SG',.46,.07),('SHA',.78,-.28),('TYO',.90,-.05),('SYD',.84,.24)]
    lanes=[(0,6),(6,5),(5,4),(4,2),(2,1),(1,0),(3,4),(7,4)]
    def draw_bg():
        if not w.winfo_exists():return
        c=canvas;c.delete('all');ww=max(1080,c.winfo_width());hh=max(700,c.winfo_height());phase=anim['phase'];anim['phase']+=.016;cx,cy=ww*.255,hh*.45;rx=min(285,ww*.205);ry=min(220,hh*.29)
        rng=random.Random(91313)
        for _ in range(95):
            x=rng.randrange(0,ww);y=rng.randrange(0,hh);c.create_oval(x,y,x+1,y+1,fill='#0a2a3c',outline='')
        # Holographic world grid.
        c.create_oval(cx-rx-8,cy-ry-8,cx+rx+8,cy+ry+8,outline='#0c5f7c',width=2)
        c.create_oval(cx-rx,cy-ry,cx+rx,cy+ry,fill='#031824',outline='#59d8f4',width=2)
        for lat in (-.66,-.33,0,.33,.66):
            y=cy+lat*ry;c.create_oval(cx-rx*(1-abs(lat)*.25),y-10,cx+rx*(1-abs(lat)*.25),y+10,outline='#0b4359')
        for frac in (-.66,-.33,0,.33,.66):c.create_arc(cx-rx,cy-ry,cx+rx,cy+ry,start=90+frac*50,extent=180,style='arc',outline='#0b4359')
        # Land masses.
        for poly in land:
            pts=[]
            for x,y in poly:pts.extend([cx+x*rx,cy+y*ry])
            c.create_polygon(*pts,fill='#174f38',outline='#63b887',width=1)
        # Sea routes.
        pxy=[]
        for name,x,y in ports:
            px,py=cx+x*rx,cy+y*ry;pxy.append((px,py));c.create_oval(px-5,py-5,px+5,py+5,fill='#f3c85f',outline='#fff0ae');c.create_text(px,py-13,text=name,fill='#8ddcf0',font=('Segoe UI',7,'bold'))
        for a,b in lanes:
            x1,y1=pxy[a];x2,y2=pxy[b];c.create_line(x1,y1,x2,y2,fill='#0d7795',width=2,dash=(5,5),arrow='last',arrowshape=(7,8,3))
        # Boats travel strictly port-to-port. A $ pulse appears only when a boat lands.
        for j,(a,b) in enumerate(lanes[:6]):
            t=(phase*.095+j*.19)%1.0;x1,y1=pxy[a];x2,y2=pxy[b];ease=t*t*(3-2*t);x=x1+(x2-x1)*ease;y=y1+(y2-y1)*ease
            c.create_polygon(x-9,y+4,x+9,y+4,x+5,y-4,x-5,y-4,fill='#7de7ff',outline='#e4fbff');c.create_line(x-2,y-5,x-2,y-12,fill='#dffaff',width=2);c.create_polygon(x-1,y-12,x+8,y-8,x-1,y-5,fill='#66cce7',outline='')
            if t>.92:
                pulse=(t-.92)/.08;c.create_text(x2,y2-18-16*pulse,text='$',fill='#f6d66e',font=('Georgia',14+int(8*pulse),'bold'))
        # Cargo aircraft connect the same real port nodes, visually distinct from vessels.
        for j,(a,b) in enumerate(lanes[2:6]):
            t=(phase*.135+j*.23+.35)%1.0;x1,y1=pxy[a];x2,y2=pxy[b];x=x1+(x2-x1)*t;y=y1+(y2-y1)*t
            c.create_polygon(x,y-8,x+3,y-2,x+10,y+2,x+3,y+3,x+1,y+8,x-2,y+8,x-3,y+3,x-10,y+2,x-3,y-2,fill='#bdadff',outline='#e9e5ff')
        c.create_text(cx,cy+ry+38,text='GLOBAL COMMERCE NETWORK',fill='#5dcde8',font=('Segoe UI',11,'bold'));c.create_text(cx,cy+ry+60,text='Ports • Freight • Markets • Risk',fill='#2e738a',font=('Segoe UI',9))
        # Three live preview tapes. USA receives the strongest visual emphasis.
        if int(phase*10)%3==0:
            preview_prev.update(preview)
            for k,v in list(preview.items()):preview[k]=max(.01,v*(1+random.gauss(0,.0007 if k not in ('BTC',) else .0015)))
        def qt(k,dec=2):
            arrow='▲' if preview[k]>=preview_prev.get(k,preview[k]) else '▼'
            return f'{k} {arrow} {preview[k]:,.{dec}f}'
        us='NYSE/NASDAQ   '+ '   '.join(qt(k,2) for k in ('AAPL','NVDA','MSFT','SPY','TSLA'))
        glob='GLOBAL       '+ '   '.join((qt('FTSE',1),qt('NIKKEI',1),qt('GOLD',1),qt('OIL',2)))
        alt='24/7         '+qt('BTC',0)+'   •  animated portal preview — simulator starts after login'
        tape_w=ww*.54;c.create_rectangle(0,hh-86,tape_w,hh,fill='#020b12',outline='#0e3142');c.create_text(ww*.015,hh-70,text=us,anchor='w',fill='#65e5ff',font=('Consolas',8,'bold'));c.create_text(ww*.015,hh-46,text=glob,anchor='w',fill='#5fa9c1',font=('Consolas',8,'bold'));c.create_text(ww*.015,hh-23,text=alt,anchor='w',fill='#5d7180',font=('Consolas',7))
        anim['job']=w.after(50,draw_bg)
    draw_bg()

    panel=tk.Frame(w,bg='#07131e',highlightbackground='#1e617e',highlightthickness=1);panel.place(relx=.555,rely=.035,relwidth=.42,relheight=.93)
    header=tk.Frame(panel,bg='#07131e');header.pack(fill='x',padx=22,pady=(18,8))
    tk.Label(header,text='STOCK GAME PRO',bg='#07131e',fg='#f3f8fb',font=('Segoe UI',24,'bold')).pack(anchor='w')
    tk.Label(header,text='1.7  •  GLOBAL TRADER PORTAL',bg='#07131e',fg='#57cce9',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(2,0))
    tk.Label(header,text='Select a saved account, review the profile, then enter the workstation.',bg='#07131e',fg='#8fa9b8',font=('Segoe UI',10),wraplength=440,justify='left').pack(anchor='w',pady=(8,0))
    table_wrap=tk.Frame(panel,bg='#07131e');table_wrap.pack(fill='both',expand=True,padx=20,pady=(4,6))
    tv=ttk.Treeview(table_wrap,style='Login.Treeview',columns=('account','mode','cash','credit','xp','last'),show='headings',selectmode='browse',height=10)
    specs=[('account','TRADER',105),('mode','MODE',58),('cash','CASH',82),('credit','CREDIT',58),('xp','XP',52),('last','LAST SESSION',102)]
    for col,title,width in specs:tv.heading(col,text=title);tv.column(col,width=width,minwidth=48,anchor='w' if col in ('account','last') else 'center',stretch=(col in ('account','last')))
    sb=ttk.Scrollbar(table_wrap,orient='vertical',command=tv.yview);tv.configure(yscrollcommand=sb.set);tv.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y')
    status=tk.Label(panel,text='Ready.',bg='#07131e',fg='#8fa9b8',font=('Segoe UI',9));status.pack(fill='x',padx=28,pady=(0,7))
    create_box=tk.Frame(panel,bg='#0a1d2b',highlightbackground='#143b50',highlightthickness=1);create_box.pack(fill='x',padx=28,pady=(0,10))
    tk.Label(create_box,text='NEW TRADER PROFILE',bg='#0a1d2b',fg='#6bcfe8',font=('Segoe UI',9,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',padx=10,pady=(8,3))
    tk.Label(create_box,text='EASY $1,000,000  •  MEDIUM $250,000  •  EXPERT $50,000',bg='#0a1d2b',fg='#6f8e9f',font=('Segoe UI',8)).grid(row=2,column=0,columnspan=3,sticky='w',padx=10,pady=(0,8))
    user=tk.Entry(create_box,bg='#eef5f8',fg='#10202a',relief='flat',font=('Segoe UI',10));user.grid(row=1,column=0,sticky='ew',padx=(10,5),pady=(2,10),ipady=6);user.insert(0,'account name')
    mode=tk.StringVar(value='MEDIUM');ttk.Combobox(create_box,textvariable=mode,values=['EASY','MEDIUM','EXPERT'],state='readonly',width=10).grid(row=1,column=1,padx=5,pady=(2,10));create_box.columnconfigure(0,weight=1)
    def selected_name():
        it=tv.selection();return tv.item(it[0],'values')[0] if it else ''
    def refresh_accounts(select=None):
        tv.delete(*tv.get_children());import datetime
        for name,rec in sorted(accounts.accounts.items()):
            stats=rec.get('stats',{});last=rec.get('last_login') or rec.get('created');lasttxt=datetime.datetime.fromtimestamp(last).strftime('%b %d  %H:%M') if last else '—';tv.insert('','end',iid=name,values=(name,rec.get('mode','MEDIUM'),f"${float(rec.get('cash',0)):,.0f}",int(rec.get('credit_score',700)),int(rec.get('xp',0)),lasttxt))
        if select and select in tv.get_children():tv.selection_set(select);tv.focus(select);tv.see(select)
    def login():
        name=selected_name()
        if not name:return status.config(text='Select a saved trader profile first.',fg='#ff6b7d')
        rec=accounts.login(name)
        if not rec:return status.config(text='Account no longer exists.',fg='#ff6b7d')
        result.update(action='start',username=rec['username'],mode=rec.get('mode','MEDIUM'),cash=float(rec.get('cash',250000)),profile=rec);w.destroy()
    def delete():
        name=selected_name()
        if not name:return status.config(text='Select an account to delete.',fg='#ff6b7d')
        if messagebox.askyesno('Delete trader profile',f'Delete “{name}” and its saved progress? This cannot be undone.'):
            ok,msg=accounts.delete(name);status.config(text=msg,fg='#31d6a0' if ok else '#ff6b7d');refresh_accounts()
    def create():
        name=user.get().strip().lower();name='' if name=='account name' else name;ok,msg=accounts.create(name,mode.get());status.config(text=msg,fg='#31d6a0' if ok else '#ff6b7d')
        if ok:user.delete(0,'end');refresh_accounts(name)
    def guest():result.update(action='start',username=None,mode=mode.get(),cash={'EASY':1000000,'MEDIUM':250000,'EXPERT':50000}[mode.get()],profile={});w.destroy()
    ttk.Button(create_box,text='CREATE PROFILE',command=create).grid(row=1,column=2,padx=(5,10),pady=(2,10))
    buttons=tk.Frame(panel,bg='#07131e');buttons.pack(fill='x',padx=28,pady=(2,20));ttk.Button(buttons,text='ENTER WORKSTATION',command=login).pack(side='left',fill='x',expand=True,ipady=5);ttk.Button(buttons,text='DELETE',command=delete).pack(side='left',padx=6,ipady=5);ttk.Button(buttons,text='GUEST',command=guest).pack(side='left',ipady=5)
    tv.bind('<Double-1>',lambda e:login());refresh_accounts();root.wait_window(w);return result

def main():
    root=tk.Tk();root.withdraw();accounts=AccountManager();choice={'action':'start','username':None,'mode':'MEDIUM','cash':250000} if '--guest' in sys.argv else main_menu(root,accounts)
    if choice['action']!='start':root.destroy();return
    root.deiconify();market=Market();market.difficulty=choice['mode'];market.speed=.05;market.time_warp=10.0;portfolio=Portfolio(choice['cash']);profile=choice.get('profile') or {};portfolio.xp=int(profile.get('xp',0));portfolio.credit_score=int(profile.get('credit_score',700));portfolio.loan_balance=float(profile.get('loan_balance',0.0));portfolio.loan_apr=float(profile.get('loan_apr',0.0));portfolio.loan_origin=profile.get('loan_origin');portfolio.last_loan_payment=profile.get('last_loan_payment');portfolio.tutorials=dict(profile.get('tutorials',{}));portfolio.career=dict(profile.get('career',portfolio.career));portfolio.market=market;market.portfolio=portfolio;app=App(root,market,portfolio);app.account_username=choice.get('username');app.account_manager=accounts
    sim=threading.Thread(target=simulation,args=(market,),daemon=True,name='MarketSimulation');sim.start();root.after(800,market.start_background_loaders)
    def stop():
        market.running=False
        if app.account_username:
            accounts.save_session(app.account_username,portfolio.cash,market.difficulty,{'trades':portfolio.trade_count,'realized':portfolio.realized,'best_net_worth':portfolio.best_net_worth});accounts.save_profile_state(app.account_username,portfolio)
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',stop);root.mainloop();market.running=False

if __name__=='__main__':main()
