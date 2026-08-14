import tkinter as tk
from tkinter import ttk,messagebox
import math,random
from options import option_chain,OptionContract,OptionStrategy,EXPIRATIONS
from markets import SESSIONS,market_status

BG='#071019'; PANEL='#101a25'; PANEL2='#142231'; GRID='#223242'; TEXT='#f2f6fb'; MUTED='#91a3b6'; GREEN='#26d69a'; RED='#ff5d73'; BLUE='#52a8ff'; YELLOW='#f5d06f'; PURPLE='#b991ff'; CYAN='#55d6e6'; ORANGE='#ffad5c'

def sma(v,n):
    out=[];q=[];s=0
    for x in v:q.append(x);s+=x;out.append(s/len(q) if len(q)<n else s/n);s-=q.pop(0) if len(q)>n else 0
    return out

def ema(v,n):
    out=[];p=None;k=2/(n+1)
    for x in v:p=x if p is None else p+k*(x-p);out.append(p)
    return out

def rsi(v,n=14):
    if len(v)<2:return [50]*len(v)
    gains=[max(0,b-a) for a,b in zip(v,v[1:])];loss=[max(0,a-b) for a,b in zip(v,v[1:])];out=[50]
    for i in range(len(gains)):
        if i<n-1:out.append(50);continue
        ag=sum(gains[i-n+1:i+1])/n;al=sum(loss[i-n+1:i+1])/n;out.append(100 if al==0 else 100-100/(1+ag/al))
    return out

def boll(v,n=20,m=2):
    mid=sma(v,n);up=[];lo=[]
    for i in range(len(v)):
        w=v[max(0,i-n+1):i+1];sd=(sum((z-mid[i])**2 for z in w)/len(w))**.5;up.append(mid[i]+m*sd);lo.append(mid[i]-m*sd)
    return mid,up,lo

def vwap(c):
    out=[];pv=vv=0.;day=None
    for x in c:
        if day!=x.timestamp.date():pv=vv=0.;day=x.timestamp.date()
        pv+=((x.high+x.low+x.close)/3)*x.volume;vv+=x.volume;out.append(pv/vv if vv else x.close)
    return out

class ToolWindow(tk.Toplevel):
    def style_window(self,title,size='900x650'):
        self.title(title);self.geometry(size);self.configure(bg=BG)
    def vars_button(self,callback): ttk.Button(self,text='VARIABLES',command=callback).pack(side='right',padx=5)

class Chart(tk.Canvas):
    def __init__(self,parent,app,index):
        super().__init__(parent,bg=BG,highlightthickness=2,highlightbackground='#263547');self.app=app;self.index=index;self.asset=None;self.timeframe='1D';self.kind='Candles';self.zoom=1.;self.cross=None;self.tool='Crosshair';self.drawings=[];self.drag_order=None;self.drag_start=None;self.bind('<Button-1>',self.click);self.bind('<Button-3>',self.context);self.bind('<B1-Motion>',self.drag);self.bind('<ButtonRelease-1>',self.release);self.bind('<Motion>',self.motion);self.bind('<MouseWheel>',self.wheel);self.bind('<Button-4>',lambda e:self._zoom(True));self.bind('<Button-5>',lambda e:self._zoom(False));self.bind('<Configure>',lambda e:self.draw());self._key=None
    def click(self,e):
        self.app.active_chart=self.index;self.app.sync_chart_controls();self.start=(e.x,e.y);self.cross=(e.x,e.y);self.configure(highlightbackground=BLUE)
        self.drag_order=self.nearest_order(e.y)
    def drag(self,e):
        self.cross=(e.x,e.y)
        if self.drag_order:
            p=self.y_to_price(e.y);self.app.market.update_pending_price(self.drag_order['id'],p);self.draw();return
        if self.tool=='Trendline' and self.start:self.draw()
    def release(self,e):
        if self.drag_order:self.app.status_flash(f"Order #{self.drag_order['id']} moved to ${self.y_to_price(e.y):,.2f}");self.drag_order=None
        elif self.tool in ('Trendline','Horizontal') and self.start:
            if self.tool=='Trendline':self.drawings.append(('line',self.start,(e.x,e.y)))
            else:self.drawings.append(('h',e.y))
        self.start=None;self.draw()
    def motion(self,e):self.cross=(e.x,e.y);self.draw()
    def wheel(self,e):self._zoom(e.delta>0)
    def _zoom(self,up):self.zoom=max(.25,min(20,self.zoom*(1.12 if up else .89)));self.draw()
    def set_asset(self,a):
        self.asset=a;self.zoom=1.;self.app.market.load_chart_data(a,self.timeframe);self.draw()
    def set_tf(self,tf):
        self.timeframe=tf;self.zoom=1.;self.app.market.load_chart_data(self.asset,tf);self.draw()
    def data(self):
        if not self.asset:return []
        interval={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe];d=self.asset.chart_candles(interval);maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':500,'MAX':900}[self.timeframe];return d[-max(30,int(maxbars/self.zoom)):]
    def price_bounds(self):
        d=self.data()
        if not d:return (0,1)
        lo=min(x.low for x in d);hi=max(x.high for x in d);return lo,hi
    def y_to_price(self,y):
        w=max(280,self.winfo_width());h=max(170,self.winfo_height());top,bottom=24,h-34;lo,hi=self.price_bounds();span=max(.00001,hi-lo);return hi-(y-top)/(bottom-top)*span
    def price_to_y(self,p):
        h=max(170,self.winfo_height());top,bottom=24,h-34;lo,hi=self.price_bounds();span=max(.00001,hi-lo);return bottom-(p-lo)/span*(bottom-top)
    def nearest_order(self,y):
        if not self.asset:return None
        orders=[o for o in self.app.market.pending_orders if o['asset'].symbol==self.asset.symbol and o.get('price') is not None]
        if not orders:return None
        best=min(orders,key=lambda o:abs(self.price_to_y(o['price'])-y));return best if abs(self.price_to_y(best['price'])-y)<12 else None
    def context(self,e):
        self.app.active_chart=self.index;self.app.sync_chart_controls();a=self.asset
        if not a:return
        p=self.y_to_price(e.y);m=tk.Menu(self,tearoff=0);m.add_command(label=f'BUY {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'BUY','LIMIT',p));m.add_command(label=f'SELL {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SELL','LIMIT',p));m.add_command(label=f'SHORT {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SHORT','LIMIT',p));m.add_command(label=f'COVER {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'COVER','LIMIT',p));m.add_separator();m.add_command(label='Buy at Market',command=lambda:self.app.order_window(a,'BUY','MARKET',None));m.add_command(label='Set Stop',command=lambda:self.app.order_window(a,'SELL','STOP',p));m.add_command(label='Open Options',command=lambda:self.app.options_for(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.app.depth_for(a));m.tk_popup(e.x_root,e.y_root)
    def draw(self):
        a=self.asset;d=self.data();w=max(280,self.winfo_width());h=max(170,self.winfo_height());key=(a.symbol if a else None,self.timeframe,self.kind,round(self.zoom,2),len(d),round(a.price,3) if a else 0,w,h,len(self.drawings),len(self.app.market.pending_orders),self.app.ind_vars_version)
        if key==self._key:return
        self._key=key;self.delete('all')
        if not a:self.create_text(w/2,h/2,text=f'CHART {self.index+1}\nClick a market ticker',fill=MUTED,font=('Arial',12,'bold'));return
        if len(d)<2:self.create_text(10,10,anchor='nw',text=f'{a.symbol} — loading {self.timeframe}...',fill=TEXT,font=('Arial',11));return
        left,right,top,bottom=62,w-12,26,h-40;lo,hi=min(x.low for x in d),max(x.high for x in d);span=max(.00001,hi-lo);n=len(d);step=(right-left)/max(1,n)
        def py(p):return bottom-(p-lo)/span*(bottom-top)
        for j in range(6):
            y=top+j*(bottom-top)/5;v=hi-j*span/5;self.create_line(left,y,right,y,fill=GRID);self.create_text(left-5,y,text=f'{v:,.2f}',anchor='e',fill=MUTED,font=('Arial',8))
        if self.kind=='Candles':
            for i,c in enumerate(d):
                x=left+(i+.5)*step;col=GREEN if c.close>=c.open else RED;self.create_line(x,py(c.high),x,py(c.low),fill=col);self.create_rectangle(x-step*.35,py(c.open),x+step*.35,py(c.close),fill=col,outline=col)
        else:
            pts=[]
            for i,c in enumerate(d):pts += [left+(i+.5)*step,py(c.close)]
            if self.kind=='Area':self.create_polygon(*(pts+[right,bottom,left,bottom]),fill='#12314a',outline='');self.create_line(*pts,fill=BLUE,width=2)
            else:self.create_line(*pts,fill=BLUE,width=2)
        close=[x.close for x in d]
        if self.app.ind_vars['SMA'].get():self._line(sma(close,20),left,step,py,YELLOW)
        if self.app.ind_vars['EMA'].get():self._line(ema(close,20),left,step,py,PURPLE)
        if self.app.ind_vars['BB'].get():
            _,u,l=boll(close);self._line(u,left,step,py,CYAN);self._line(l,left,step,py,CYAN)
        if self.app.ind_vars['VWAP'].get():self._line(vwap(d),left,step,py,ORANGE)
        if self.app.ind_vars['RSI'].get():
            vals=rsi(close);self._line(vals,left,step,lambda v:bottom-(v/100)*(bottom-top)*.22-bottom*.0,BLUE)
        if self.app.ind_vars['Volume'].get():
            vmax=max(x.volume for x in d) or 1;vh=(bottom-top)*.14
            for i,c in enumerate(d):x=left+(i+.5)*step;y=bottom-c.volume/vmax*vh;self.create_rectangle(x-step*.3,bottom,x+step*.3,y,fill='#33485b',outline='')
        for o in self.app.market.pending_orders:
            if o['asset'].symbol==a.symbol and o.get('price') is not None:
                y=py(o['price']);col=GREEN if o['side'] in ('BUY','COVER') else RED;dash=(7,4) if o['type']=='LIMIT' else (2,3);self.create_line(left,y,right,y,fill=col,dash=dash,width=2);self.create_text(right-3,y-8,anchor='e',text=f"#{o['id']} {o['type']} {o['side']} ${o['price']:,.2f}",fill=col,font=('Arial',8,'bold'))
        for dr in self.drawings:
            if dr[0]=='line':self.create_line(*dr[1],*dr[2],fill=YELLOW,width=2)
            else:self.create_line(left,dr[1],right,dr[1],fill=YELLOW,dash=(5,3))
        pred=self.app.market.predict(a);pcol=GREEN if pred['score']>0 else RED if pred['score']<0 else MUTED
        self.create_text(8,5,anchor='nw',text=f'{a.symbol}  ${a.price:,.2f}  {a.change_percent():+.2f}%  {self.timeframe} • {self.kind}',fill=TEXT,font=('Arial',10,'bold'))
        self.create_text(w-8,5,anchor='ne',text=f"MODEL {pred['label']} {pred['confidence']*100:.0f}%",fill=pcol,font=('Arial',9,'bold'))
        self.create_text(8,h-8,anchor='sw',text=f'O {d[-1].open:.2f}  H {d[-1].high:.2f}  L {d[-1].low:.2f}  C {d[-1].close:.2f}  V {d[-1].volume:,}',fill=MUTED,font=('Arial',8))
        if self.cross:
            x,y=self.cross;self.create_line(x,top,x,bottom,fill='#5c7085');self.create_line(left,y,right,y,fill='#5c7085');self.create_text(x+6,y-5,text=f'${self.y_to_price(y):,.2f}',fill=TEXT,anchor='w',font=('Arial',8,'bold'))
    def _line(self,vals,left,step,py,col):
        pts=[]
        for i,v in enumerate(vals):
            if v is not None:pts += [left+(i+.5)*step,py(v)]
        if len(pts)>3:self.create_line(*pts,fill=col,width=1)

class OptionsWindow(ToolWindow):
    def __init__(self,parent,market,portfolio,refresh):
        super().__init__(parent);self.market=market;self.portfolio=portfolio;self.refresh_main=refresh;self.style_window('OPTIONS — PRO CHAIN','1820x940');self.rate_ms=350;self.selected_side='CALL';self.selected_strike=None;self.visible_cols={x:True for x in ['Bid','Ask','Last','Vol','OI','IV','Delta','Gamma','Theta','Vega']}
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=7)
        ttk.Label(top,text='Ticker').pack(side='left');self.entry=ttk.Entry(top,width=12);self.entry.insert(0,'SPX');self.entry.pack(side='left',padx=5);self.entry.bind('<Return>',lambda e:self.apply_symbol());ttk.Button(top,text='LOAD',command=self.apply_symbol).pack(side='left')
        for label,vals,var in [('Expiry',[x[0] for x in EXPIRATIONS],'0DTE'),('Range',['ATM ±5','ATM ±10','ATM ±20','ATM ±50','All'],'ATM ±20'),('Sort',['Strike','Volume','Open Interest','IV','Delta','Gamma'],'Strike'),('Update',['150ms','250ms','350ms','500ms','1000ms'],'350ms')]:
            ttk.Label(top,text=label).pack(side='left',padx=(12,2));v=ttk.Combobox(top,values=vals,state='readonly',width=12);v.set(var);v.pack(side='left');setattr(self,label.lower().replace('update','rate'),v)
        self.rate.bind('<<ComboboxSelected>>',lambda e:self.set_rate());ttk.Button(top,text='SPREAD BUILDER',command=self.spread_builder).pack(side='left',padx=7);ttk.Button(top,text='VARIABLES',command=self.variables).pack(side='left');self.live=ttk.Label(top,text='● LIVE');self.live.pack(side='right')
        head=tk.Frame(self,bg=BG);head.pack(fill='x',padx=8);tk.Label(head,text='CALLS',bg='#123326',fg=GREEN,font=('Arial',11,'bold')).pack(side='left',fill='x',expand=True);tk.Label(head,text='STRIKE / ATM',bg='#3c3320',fg=YELLOW,font=('Arial',11,'bold'),width=16).pack(side='left');tk.Label(head,text='PUTS',bg='#38202a',fg=RED,font=('Arial',11,'bold')).pack(side='left',fill='x',expand=True)
        cols=('cbid','cask','clast','cvol','coi','civ','cd','cg','ct','cv','strike','pd','pg','pt','pv','piv','poi','pvol','plast','pbid','pask');labels=['Bid','Ask','Last','Vol','OI','IV','Δ','Γ','Θ','V','Strike','Δ','Γ','Θ','V','IV','OI','Vol','Last','Bid','Ask'];self.tv=ttk.Treeview(self,columns=cols,show='headings',selectmode='browse')
        for c,l in zip(cols,labels):self.tv.heading(c,text=l);self.tv.column(c,width=72,anchor='center');
        self.tv.column('strike',width=100);self.tv.tag_configure('call_itm',background='#123a2a',foreground='#d5ffef');self.tv.tag_configure('put_itm',background='#40222c',foreground='#ffe0e5');self.tv.tag_configure('atm',background='#403720',foreground='#fff2ae');self.tv.tag_configure('owned',background='#1b4d77',foreground='#ffffff');self.tv.pack(fill='both',expand=True,padx=8,pady=5);self.tv.bind('<<TreeviewSelect>>',lambda e:self.info());self.tv.bind('<Button-3>',self.context);self.tv.bind('<Double-1>',lambda e:self.trade())
        self.info_lbl=ttk.Label(self,text='Green = ITM calls • red = ITM puts • gold = ATM • blue overlay = owned/short contracts.');self.info_lbl.pack(fill='x',padx=8,pady=5);self.after(100,self.update_chain)
    def set_rate(self):self.rate_ms=int(self.rate.get().replace('ms',''))
    def variables(self):
        w=tk.Toplevel(self);w.title('OPTIONS VARIABLES');w.geometry('360x430');w.configure(bg=BG);ttk.Label(w,text='Visible option-chain variables',font=('Arial',12,'bold')).pack(anchor='w',padx=12,pady=10)
        for k in self.visible_cols:
            v=tk.BooleanVar(value=self.visible_cols[k]);ttk.Checkbutton(w,text=k,variable=v,command=lambda key=k,var=v:self.toggle_col(key,var)).pack(anchor='w',padx=20,pady=4)
    def toggle_col(self,k,v):self.visible_cols[k]=v;self.update_chain()
    def apply_symbol(self):
        s=self.entry.get().strip().upper();a=self.market.get_asset(s)
        if not a:self.info_lbl.config(text=f'{s}: ticker not found');return
        if self.expiry.get()=='0DTE' and a.symbol not in {'SPX','NDX','RUT','DJI','ES=F','NQ=F'}: self.expiry.set('1D')
        self.info_lbl.config(text=f'Loaded {a.symbol} — {a.name}')
    def asset(self):return self.market.get_asset(self.entry.get().strip().upper()) or self.market.get_asset('SPX')
    def owned_contract(self,a,k,typ,days):
        needle=(a.symbol,int(k),typ.lower(),int(days));
        for s in self.portfolio.options:
            for l in s.legs:
                c=l.contract
                if (c.underlying.symbol,int(c.strike),c.option_type.lower(),int(c.days))==needle:return True
        return False
    def update_chain(self):
        try:
            a=self.asset();days=dict(EXPIRATIONS).get(self.expiry.get(),0);span={'ATM ±5':5,'ATM ±10':10,'ATM ±20':20,'ATM ±50':50}.get(self.span.get(),25);cs=option_chain(a,days,span);calls={int(c.strike):c for c in cs if c.option_type=='call'};puts={int(c.strike):c for c in cs if c.option_type=='put'};ks=sorted(calls);center=round(a.price);rng=self.span.get()
            if rng!='All':ks=[k for k in ks if abs(k-center)<=int(rng.split('±')[1])]
            if self.sort.get()!='Strike':
                def m(k):
                    c=calls[k];return {'Volume':c.volume,'Open Interest':c.open_interest,'IV':c.volatility,'Delta':abs(c.stats['delta']),'Gamma':c.stats['gamma']}.get(self.sort.get(),k)
                ks=sorted(ks,key=m,reverse=True)
            prior=self.tv.selection();prior_iid=prior[0] if prior else None;self.tv.delete(*self.tv.get_children())
            for k in ks:
                c,p=calls[k],puts[k];cs,ps=c.stats,p.stats;tag='atm' if k==center else 'call_itm' if c.itm() else 'put_itm' if p.itm() else ''
                if self.owned_contract(a,k,'call',days) or self.owned_contract(a,k,'put',days):tag='owned'
                vals=(f'{c.bid:.2f}',f'{c.ask:.2f}',f'{c.mid:.2f}',f'{c.volume:,}',f'{c.open_interest:,}',f'{c.volatility*100:.1f}%',f'{cs["delta"]:+.2f}',f'{cs["gamma"]:.4f}',f'{cs["theta"]:.3f}',f'{cs["vega"]:.3f}',f'${k:,.0f}',f'{ps["delta"]:+.2f}',f'{ps["gamma"]:.4f}',f'{ps["theta"]:.3f}',f'{ps["vega"]:.3f}',f'{p.volatility*100:.1f}%',f'{p.open_interest:,}',f'{p.volume:,}',f'{p.mid:.2f}',f'{p.bid:.2f}',f'{p.ask:.2f}')
                self.tv.insert('','end',iid=str(k),values=vals,tags=(tag,))
            if prior_iid and prior_iid in self.tv.get_children():self.tv.selection_set(prior_iid);self.tv.focus(prior_iid)
            self.live.config(text=f'● LIVE  {a.symbol} ${a.price:,.2f}  {self.market.clock.time}  ATM ${center:,.0f}  {days}D')
        except Exception as e:self.info_lbl.config(text=f'Chain recovered: {e}')
        if self.winfo_exists():self.after(self.rate_ms,self.update_chain)
    def info(self):
        it=self.tv.selection()
        if not it:return
        self.selected_strike=int(it[0]);a=self.asset();d=dict(EXPIRATIONS).get(self.expiry.get(),0);c=OptionContract(a,self.selected_strike,d,'call');p=OptionContract(a,self.selected_strike,d,'put');self.info_lbl.config(text=f'{a.symbol} {self.selected_strike:,.0f} | CALL Δ {c.stats["delta"]:+.3f} Γ {c.stats["gamma"]:.5f} Θ {c.stats["theta"]:.3f} | PUT Δ {p.stats["delta"]:+.3f} Γ {p.stats["gamma"]:.5f} Θ {p.stats["theta"]:.3f}')
    def selected_contract(self,side=None):
        it=self.tv.selection()
        if not it:return None
        k=int(it[0]);a=self.asset();days=dict(EXPIRATIONS).get(self.expiry.get(),0);typ=(side or self.selected_side).lower();return OptionContract(a,k,days,typ)
    def context(self,e):
        iid=self.tv.identify_row(e.y)
        if not iid:return
        self.tv.selection_set(iid);self.tv.focus(iid);col=self.tv.identify_column(e.x);self.selected_side='CALL' if col in {'#1','#2','#3','#4','#5','#6','#7','#8','#9','#10'} else 'PUT';m=tk.Menu(self,tearoff=0);c=self.selected_contract();m.add_command(label=f'BUY {c}',command=lambda:self.trade_action('BUY'));m.add_command(label=f'SELL/CLOSE {c}',command=lambda:self.trade_action('SELL'));m.add_command(label='Set LIMIT',command=lambda:self.option_order('LIMIT'));m.add_command(label='Set STOP',command=lambda:self.option_order('STOP'));m.add_separator();m.add_command(label='Add Leg to Spread',command=self.add_leg_to_spread);m.add_command(label='Open Spread Builder',command=self.spread_builder);m.add_command(label='Liquidate Matching Contract',command=self.liquidate_matching);m.tk_popup(e.x_root,e.y_root)
    def trade_action(self,action):
        c=self.selected_contract();q=1
        if not c:return
        s=OptionStrategy(f'{action} {c}');s.add_leg(c,q,'BUY' if action=='BUY' else 'SELL');ok,msg=self.portfolio.execute_strategy(s)
        if ok:self.info_lbl.config(text=msg);self.refresh_main()
        else:messagebox.showerror('Option order',msg)
    def option_order(self,typ):
        c=self.selected_contract();w=OptionOrderWindow(self,c,self.portfolio,self.refresh_main,typ);w.grab_set()
    def add_leg_to_spread(self):self.spread_builder(self.selected_contract())
    def spread_builder(self,first=None):SpreadBuilder(self,self.market,self.portfolio,self.refresh_main,first)
    def liquidate_matching(self):
        c=self.selected_contract();
        if not c:return
        for i,s in enumerate(list(self.portfolio.options)):
            if any(l.contract.underlying.symbol==c.underlying.symbol and int(l.contract.strike)==int(c.strike) and l.contract.option_type==c.option_type for l in s.legs):
                ok,msg=self.portfolio.liquidate_strategy(i);messagebox.showinfo('Liquidation',msg) if ok else messagebox.showerror('Liquidation',msg);self.refresh_main();return
        messagebox.showwarning('Contract','No matching owned contract found.')
    def trade(self):self.trade_action('BUY')

class OptionOrderWindow(ToolWindow):
    def __init__(self,parent,contract,portfolio,refresh,order_type):
        super().__init__(parent);self.contract=contract;self.portfolio=portfolio;self.refresh=refresh;self.style_window('OPTION ORDER','480x430');f=ttk.Frame(self);f.pack(fill='both',expand=True,padx=16,pady=16);self.action=tk.StringVar(value='BUY');self.qty=tk.IntVar(value=1);self.typ=tk.StringVar(value=order_type);self.price=tk.DoubleVar(value=round(contract.mid,2));
        ttk.Label(f,text=str(contract),font=('Arial',12,'bold')).pack(anchor='w',pady=5);ttk.Label(f,text='Action').pack(anchor='w');ttk.Combobox(f,textvariable=self.action,values=['BUY','SELL'],state='readonly').pack(fill='x',pady=4);ttk.Label(f,text='Order type').pack(anchor='w');ttk.Combobox(f,textvariable=self.typ,values=['LIMIT','STOP'],state='readonly').pack(fill='x',pady=4);ttk.Label(f,text='Quantity').pack(anchor='w');ttk.Entry(f,textvariable=self.qty).pack(fill='x',pady=4);ttk.Label(f,text='Trigger / limit price').pack(anchor='w');ttk.Entry(f,textvariable=self.price).pack(fill='x',pady=4);self.margin=ttk.Label(f,text='');self.margin.pack(fill='x',pady=8);ttk.Button(f,text='PLACE WORKING OPTION ORDER',command=self.submit).pack(fill='x');self.update_margin()
    def update_margin(self):
        q=max(1,self.qty.get());self.margin.config(text=f'Estimated mark ${self.contract.mid:,.2f} • notional ${self.contract.mid*q*100:,.2f} • short margin estimate ${max(0,self.contract.ask*q*100*1.5):,.2f}')
    def submit(self):
        try:q=int(self.qty.get());p=float(self.price.get())
        except:return messagebox.showerror('Option order','Invalid quantity/price.')
        o=self.portfolio # market retrieved through parent
        market=getattr(self.master,'market',None) or getattr(self.master,'app',None) and self.master.app.market
        if market is None:return messagebox.showerror('Option order','Market engine unavailable.')
        side=self.action.get();market.submit_option_pending(side,self.contract,q,self.typ.get(),p);self.refresh();self.destroy()

class SpreadBuilder(ToolWindow):
    def __init__(self,parent,market,portfolio,refresh,first=None):
        super().__init__(parent);self.market=market;self.portfolio=portfolio;self.refresh=refresh;self.style_window('ADVANCED SPREAD BUILDER','900x720');self.rows=[];self.exp=tk.StringVar(value='30D');self.ticker=tk.StringVar(value=first.underlying.symbol if first else 'SPY');self.net=tk.DoubleVar(value=0);self.order_type=tk.StringVar(value='MARKET');self.action=tk.StringVar(value='BUY')
        top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8);ttk.Label(top,text='Ticker').pack(side='left');ttk.Entry(top,textvariable=self.ticker,width=10).pack(side='left',padx=4);ttk.Label(top,text='Expiry').pack(side='left',padx=(12,2));ttk.Combobox(top,textvariable=self.exp,values=[x[0] for x in EXPIRATIONS if x[0] != '0DTE'],state='readonly',width=8).pack(side='left');ttk.Button(top,text='Add 4-leg template',command=self.template).pack(side='left',padx=10)
        self.tv=ttk.Treeview(self,columns=('action','type','strike','qty','mark'),show='headings',height=8);[self.tv.heading(c,text=c.upper()) for c in self.tv['columns']];self.tv.pack(fill='x',padx=10,pady=8);self.preview=ttk.Label(self,text='No legs');self.preview.pack(fill='x',padx=10,pady=8);bar=ttk.Frame(self);bar.pack(fill='x',padx=10);ttk.Label(bar,text='Order').pack(side='left');ttk.Combobox(bar,textvariable=self.action,values=['BUY','SELL'],state='readonly',width=8).pack(side='left',padx=4);ttk.Combobox(bar,textvariable=self.order_type,values=['MARKET','LIMIT','STOP'],state='readonly',width=10).pack(side='left',padx=4);self.price=tk.DoubleVar(value=0);ttk.Entry(bar,textvariable=self.price,width=10).pack(side='left',padx=4);ttk.Button(bar,text='EXECUTE / WORK',command=self.execute).pack(side='left',padx=8);ttk.Button(bar,text='REMOVE SELECTED',command=self.remove).pack(side='left');self.template()
        if first:self.rows.append({'action':'BUY','type':first.option_type.upper(),'strike':first.strike,'qty':1,'contract':first});self.refresh_table()
    def template(self):
        a=self.market.get_asset(self.ticker.get().upper())
        if not a:return
        d=dict(EXPIRATIONS).get(self.exp.get(),30);center=round(a.price);self.rows=[{'action':'BUY','type':'CALL','strike':center,'qty':1},{'action':'SELL','type':'CALL','strike':center+5,'qty':1},{'action':'SELL','type':'PUT','strike':center-5,'qty':1},{'action':'BUY','type':'PUT','strike':center-10,'qty':1}];self.refresh_table(d)
    def refresh_table(self,d=None):
        self.tv.delete(*self.tv.get_children());a=self.market.get_asset(self.ticker.get().upper());days=d if d is not None else dict(EXPIRATIONS).get(self.exp.get(),30);net=0;greeks={k:0 for k in ['delta','gamma','theta','vega']}
        for i,r in enumerate(self.rows):
            c=r.get('contract') or OptionContract(a,r['strike'],days,r['type'].lower());r['contract']=c;sign=1 if r['action']=='BUY' else -1;net+=sign*c.mid*r['qty']*100;s=c.stats
            for k in greeks:greeks[k]+=sign*s[k]*r['qty']*100
            self.tv.insert('','end',iid=str(i),values=(r['action'],r['type'],f'{c.strike:,.0f}',r['qty'],f'${c.mid:.2f}'))
        self.price.set(round(abs(net)/100,2));self.preview.config(text=f'Net debit/credit ${net:,.2f} • Δ {greeks["delta"]:+.2f} Γ {greeks["gamma"]:+.4f} Θ {greeks["theta"]:+.2f} Vega {greeks["vega"]:+.2f}')
    def remove(self):
        it=self.tv.selection();
        if it:self.rows.pop(int(it[0]));self.refresh_table()
    def execute(self):
        a=self.market.get_asset(self.ticker.get().upper());d=dict(EXPIRATIONS).get(self.exp.get(),30);s=OptionStrategy('CUSTOM SPREAD')
        for r in self.rows:
            c=OptionContract(a,r['strike'],d,r['type'].lower());s.add_leg(c,r['qty'],r['action'])
        if self.order_type.get()=='MARKET':ok,msg=self.portfolio.execute_strategy(s)
        else:self.market.submit_spread_pending(self.action.get(),s,self.order_type.get(),self.price.get());ok=True;msg=f'Working {self.order_type.get()} spread at ${self.price.get():,.2f}'
        if ok:self.refresh();messagebox.showinfo('Spread',msg);self.destroy()
        else:messagebox.showerror('Spread rejected',msg)

class DepthWindow(ToolWindow):
    def __init__(self,parent,market,asset):
        super().__init__(parent);self.market=market;self.asset=asset;self.style_window(f'ORDER BOOK — {asset.symbol}','1350x780');top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=6);self.mode=ttk.Combobox(top,values=['LEVEL 2','LEVEL 3','MICROSTRUCTURE','IMBALANCE','TRADE TAPE'],state='readonly',width=18);self.mode.set('LEVEL 2');self.mode.pack(side='left');self.rate=ttk.Combobox(top,values=['100ms','250ms','500ms','1s'],state='readonly',width=8);self.rate.set('250ms');self.rate.pack(side='left',padx=8);self.summary=ttk.Label(top,text='');self.summary.pack(side='left',padx=20);ttk.Button(top,text='VARIABLES',command=self.variables).pack(side='right');self.tv=ttk.Treeview(self,columns=('side','price','size','orders','maker','venue','queue','hidden','cum'),show='headings');
        for c,t in zip(self.tv['columns'],['Side','Price','Size','Orders','Maker','Venue','Queue','Hidden','Cum Size']):self.tv.heading(c,text=t);self.tv.column(c,width=135,anchor='center')
        self.tv.tag_configure('bid',foreground=GREEN);self.tv.tag_configure('ask',foreground=RED);self.tv.pack(fill='both',expand=True,padx=8,pady=5);self.after(100,self.refresh)
    def variables(self):messagebox.showinfo('Depth variables','LEVEL 2 = aggregated depth\nLEVEL 3 = simulated individual orders\nMicrostructure = spread, imbalance and microprice\nUpdate rate is adjustable from 100ms to 1s.')
    def refresh(self):
        if not self.winfo_exists():return
        b=self.market.get_book(self.asset);self.tv.delete(*self.tv.get_children());cum=0
        if b:
            rows=b.level3() if self.mode.get()!='LEVEL 2' else [(s,x.price,x.size,x.orders,x.market_maker,x.venue,x.orders,x.hidden,0) for s,lvls in [('ASK',list(reversed(b.asks))),('BID',b.bids)] for x in lvls]
            for r in rows:
                side,price,size,orders,maker,venue,queue,hidden,_=r;cum+=size;self.tv.insert('','end',values=(side,f'{price:.4f}',f'{size:,}',orders,maker,venue,queue,hidden,f'{cum:,}'),tags=('bid' if side=='BID' else 'ask',))
            snap=b.snapshot();micro=(b.bids[0].price*b.asks[0].size+b.asks[0].price*b.bids[0].size)/(b.bids[0].size+b.asks[0].size);self.summary.config(text=f'Last ${snap["last"]:,.2f} • Spread ${snap["spread"]:.4f} • Imbalance {snap["imbalance"]:+.2f} • Micro ${micro:,.4f}')
        self.after(int(self.rate.get().replace('ms','').replace('s','000')),self.refresh)

class MarketMapWindow(ToolWindow):
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('MARKET MAP — SECTOR TREEMAP','1250x950');self.sec=tk.StringVar(value='ALL');self.mode=tk.StringVar(value='Market Cap');self.cv=tk.Canvas(self,bg='#05090e',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=8,pady=8);bar=ttk.Frame(self);bar.pack(fill='x',padx=8,pady=5);ttk.Label(bar,text='Sector').pack(side='left');ttk.Combobox(bar,textvariable=self.sec,values=['ALL']+market.sectors,state='readonly',width=18).pack(side='left',padx=5);ttk.Label(bar,text='Sizing').pack(side='left');ttk.Combobox(bar,textvariable=self.mode,values=['Market Cap','Equal'],state='readonly',width=12).pack(side='left',padx=5);ttk.Button(bar,text='VARIABLES',command=self.variables).pack(side='right');self.after(200,self.draw)
    def variables(self):messagebox.showinfo('Market map variables','Tile area = market capitalization.\nColor = daily percentage change.\nSector selector isolates sectors.\nThe layout automatically rescales to the square viewport.')
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(600,c.winfo_width());h=max(600,c.winfo_height());side=min(w-20,h-20);ox=(w-side)/2;oy=(h-side)/2;assets=[a for a in self.market.stocks if self.sec.get()=='ALL' or a.category==self.sec.get()];sectors={}
        for a in assets:sectors.setdefault(a.category,[]).append(a)
        cols=max(1,math.ceil(math.sqrt(len(sectors))));rows=math.ceil(len(sectors)/cols);sw=side/cols;sh=side/rows
        for si,(sector,arr) in enumerate(sorted(sectors.items())):
            sx=ox+(si%cols)*sw;sy=oy+(si//cols)*sh;c.create_rectangle(sx,sy,sx+sw,sy+sh,fill='#0c1621',outline='#2d4053',width=2);c.create_text(sx+6,sy+5,anchor='nw',text=sector,fill=TEXT,font=('Arial',10,'bold'));arr=sorted(arr,key=lambda x:x.market_cap,reverse=True);n=max(1,math.ceil(math.sqrt(len(arr))));groups=[arr[i:i+n] for i in range(0,len(arr),n)];rh=(sh-22)/max(1,len(groups));yy=sy+22
            for g in groups:
                x=sx;tot=sum(max(1,a.market_cap) for a in g)
                for a in g:
                    ww=(sw*max(1,a.market_cap)/tot if self.mode.get()=='Market Cap' else sw/len(g));ww=max(28,ww);x2=min(sx+sw,x+ww);ch=a.change_percent();strength=min(1,abs(ch)/4);col=('#0d4d39' if ch>=0 else '#54232f') if abs(ch)<1 else ('#18a66f' if ch>0 else '#bd3b55');c.create_rectangle(x,yy,x2,yy+rh,fill=col,outline='#071017');fs=max(7,min(13,int(min((x2-x)/6,max(9,rh/2.6)))));c.create_text((x+x2)/2,yy+rh/2,text=f'{a.symbol}\n{ch:+.2f}%',fill='white',font=('Arial',fs,'bold'));x=x2
                yy+=rh
        c.create_text(ox+8,oy+8,anchor='nw',text='MARKET MAP • AREA = MARKET CAP • COLOR = DAILY CHANGE • SECTORS',fill=TEXT,font=('Arial',10,'bold'));self.after(900,self.draw)

class GlobeWindow(ToolWindow):
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('GLOBAL TRADER — WORLD SESSION CONTROL','1450x900');self.cv=tk.Canvas(self,bg='#03070c',highlightthickness=0);self.cv.pack(fill='both',expand=True);self.cv.bind('<Button-1>',self.click);self.after(100,self.draw)
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(900,self.winfo_width());h=max(650,self.winfo_height());r=min(h*.38,w*.27);cx=w*.34;cy=h*.5;utc=self.market.clock.current;mins=utc.hour*60+utc.minute;rot=2*math.pi*mins/1440
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#0b2942',outline='#4ea9ff',width=3)
        # stylized latitude/longitude + day/night terminator; no sine-wave artifacts.
        for frac in (-.7,-.35,0,.35,.7):
            yy=cy+frac*r;c.create_oval(cx-r*.94,yy-r*.14,cx+r*.94,yy+r*.14,outline='#21445e')
        for deg in range(0,360,30):
            a=math.radians(deg)+rot;x1=cx+math.cos(a)*r*.94;y1=cy+math.sin(a)*r*.94;c.create_line(cx,cy,x1,y1,fill='#193d58')
        sx=cx+r*1.55*math.cos(rot-math.pi/2);sy=cy+r*1.55*math.sin(rot-math.pi/2);c.create_oval(sx-16,sy-16,sx+16,sy+16,fill='#fff1a2',outline='');c.create_line(sx,sy,cx,cy,fill='#9fb8cf',dash=(4,5))
        positions={'US':(-.52,.02),'LSE':(-.08,-.20),'XETRA':(.02,-.22),'TSE':(.50,-.02),'HKEX':(.46,.16),'SSE':(.42,.23),'ASX':(.58,.48),'FX':(.0,.46),'CME':(-.42,.15),'CRYPTO':(.0,0)};self.blips=[]
        for code,(bx,by) in positions.items():
            x=cx+bx*r*1.55;y=cy+by*r*1.55;op=market_status(code,self.market.clock.current);col=GREEN if op else '#405365';c.create_oval(x-9,y-9,x+9,y+9,fill=col,outline=TEXT,width=1);c.create_text(x+14,y,text=SESSIONS[code].name,fill=TEXT,anchor='w',font=('Arial',9,'bold'));self.blips.append((x-12,y-12,x+12,y+12,code))
        c.create_text(w*.62,34,text=f'GLOBAL CLOCK  {self.market.clock.time}',fill=TEXT,font=('Arial',18,'bold'),anchor='w');c.create_text(w*.62,64,text=self.market.clock.utc_time,fill=MUTED,font=('Arial',11),anchor='w');y=100
        for code,sess in SESSIONS.items():
            op=market_status(code,self.market.clock.current);col=GREEN if op else MUTED;c.create_text(w*.62,y,text=f'{sess.name:<22}  {"OPEN" if op else "CLOSED"}',fill=col,font=('Arial',10,'bold'),anchor='w');y+=23
        # freight lanes are tied to open/closed commodity-related venues; moving ships represent modeled logistics flow.
        for i in range(7):
            x1=cx-r*.8+i*r*.22+((mins*0.01+i*15)%r);y1=cy+r*.6-i*r*.09;x2=x1+35;y2=y1-8;c.create_line(x1,y1,x2,y2,fill='#5c9fba',width=2);c.create_polygon(x2,y2,x2-8,y2+3,x2-5,y2-7,fill='#5c9fba',outline='')
        c.create_text(w*.62,y+15,text='Select an exchange blip to open its market dashboard and trade while its session is open.',fill=TEXT,anchor='w',font=('Arial',10))
        self.after(250,self.draw)
    def click(self,e):
        for x1,y1,x2,y2,code in getattr(self,'blips',[]):
            if x1<=e.x<=x2 and y1<=e.y<=y2:GlobalMarketWindow(self,self.market,code);return

class GlobalMarketWindow(ToolWindow):
    def __init__(self,parent,market,code):
        super().__init__(parent);self.market=market;self.code=code;self.style_window(f'GLOBAL MARKET — {SESSIONS[code].name}','1100x720');ttk.Label(self,text=f'{SESSIONS[code].name} • {"OPEN" if market_status(code,market.clock.current) else "CLOSED"}',font=('Arial',15,'bold')).pack(anchor='w',padx=12,pady=10);self.tv=ttk.Treeview(self,columns=('symbol','name','price','chg','status'),show='headings');
        for c in self.tv['columns']:self.tv.heading(c,text=c.upper());self.tv.column(c,width=180 if c=='name' else 120)
        self.tv.pack(fill='both',expand=True,padx=10,pady=10);self.tv.bind('<Double-1>',self.trade);self.after(200,self.refresh)
    def refresh(self):
        if not self.winfo_exists():return
        self.tv.delete(*self.tv.get_children());assets=[a for a in self.market.all_assets() if getattr(a,'session','US')==self.code]
        if self.code=='US':assets=self.market.stocks
        if self.code=='CME':assets=self.market.futures
        if self.code=='FX':assets=self.market.forex
        if self.code=='CRYPTO':assets=self.market.crypto
        for a in assets:self.tv.insert('','end',iid=a.symbol,values=(a.symbol,a.name,f'${a.price:,.2f}',f'{a.change_percent():+.2f}%', 'OPEN' if market_status(self.code,self.market.clock.current) else 'CLOSED'))
        self.after(600,self.refresh)
    def trade(self,e):
        it=self.tv.selection();
        if it:
            a=self.market.get_asset(it[0]);self.market.ui_app.order_window(a,'BUY','MARKET',None)

class MarketListWindow(ToolWindow):
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('MARKET SCREENER','1000x700');ttk.Label(self,text='Global Market Screener',font=('Arial',15,'bold')).pack(anchor='w',padx=12,pady=10);self.tv=ttk.Treeview(self,columns=('symbol','name','price','chg','sector'),show='headings');
        for c in self.tv['columns']:self.tv.heading(c,text=c.upper(),command=lambda col=c:self.sort(col));self.tv.column(c,width=180 if c=='name' else 120)
        self.tv.pack(fill='both',expand=True,padx=10,pady=10);self.tv.bind('<Button-3>',self.context);self.sort_key='symbol';self.reverse=False;self.after(200,self.refresh)
    def sort(self,c):self.reverse=not self.reverse if self.sort_key==c else False;self.sort_key=c
    def refresh(self):
        if not self.winfo_exists():return
        assets=self.market.all_assets();k=self.sort_key;fn={'symbol':lambda a:a.symbol.lower(),'name':lambda a:a.name.lower(),'price':lambda a:a.price,'chg':lambda a:a.change_percent(),'sector':lambda a:a.category.lower()}[k];assets=sorted(assets,key=fn,reverse=self.reverse);sel=self.tv.selection();sid=sel[0] if sel else None;self.tv.delete(*self.tv.get_children())
        for a in assets:self.tv.insert('','end',iid=a.symbol,values=(a.symbol,a.name,f'${a.price:,.2f}',f'{a.change_percent():+.2f}%',a.category))
        if sid and sid in self.tv.get_children():self.tv.selection_set(sid)
        self.after(700,self.refresh)
    def context(self,e):
        iid=self.tv.identify_row(e.y)
        if not iid:return
        self.tv.selection_set(iid);a=self.market.get_asset(iid);m=tk.Menu(self,tearoff=0);m.add_command(label=f'Buy {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'Sell {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SELL','MARKET',None));m.add_command(label='Open Options',command=lambda:self.market.ui_app.options_for(a));m.add_command(label='Advanced Chart',command=lambda:self.market.ui_app.load_asset_auto(a));m.tk_popup(e.x_root,e.y_root)

class BlackjackWindow(ToolWindow):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('BLACKJACK TRAINER','900x650');self.deck_count=tk.IntVar(value=6);self.count_mode=tk.StringVar(value='Hi-Lo');self.running=0;self.shoe=[];self.hand=[];self.dealer=[];self.bet=tk.IntVar(value=100);self.active=False;top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8);ttk.Label(top,text='Decks').pack(side='left');ttk.Combobox(top,textvariable=self.deck_count,values=[1,2,6],state='readonly',width=6).pack(side='left',padx=5);ttk.Label(top,text='Count').pack(side='left');ttk.Combobox(top,textvariable=self.count_mode,values=['None','Hi-Lo','KO'],state='readonly',width=10).pack(side='left');ttk.Label(top,text='Bet').pack(side='left',padx=(15,2));ttk.Entry(top,textvariable=self.bet,width=10).pack(side='left');ttk.Button(top,text='NEW SHOE',command=self.new_shoe).pack(side='left',padx=5);self.canvas=tk.Canvas(self,bg='#063d2a',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=10,pady=10);bar=ttk.Frame(self);bar.pack(fill='x',padx=10);ttk.Button(bar,text='DEAL',command=self.deal).pack(side='left');ttk.Button(bar,text='HIT',command=self.hit).pack(side='left',padx=5);ttk.Button(bar,text='STAND',command=self.stand).pack(side='left');self.info=ttk.Label(bar,text='');self.info.pack(side='right');self.new_shoe()
    def new_shoe(self):
        import random as r
        suits=['♠','♥','♦','♣'];ranks=list(range(1,14));self.shoe=[(rank,s) for _ in range(self.deck_count.get()) for s in suits for rank in ranks];r.shuffle(self.shoe);self.running=0;self.active=False;self.draw_table()
    def card(self):
        if len(self.shoe)<max(10,52*self.deck_count.get()*.2):self.new_shoe()
        card=self.shoe.pop();rank,s=card;v=1 if rank==1 else min(10,rank);self.running += (1 if self.count_mode.get() in ('Hi-Lo','KO') and v<=6 else -1 if self.count_mode.get()=='Hi-Lo' and v>=10 else 0);return card
    def val(self,h):
        total=sum(1 if r==1 else min(10,r) for r,s in h);aces=sum(r==1 for r,s in h)
        while aces and total+10<=21:total+=10;aces-=1
        return total
    def deal(self):
        try:b=int(self.bet.get())
        except:return
        if b<=0 or b>self.portfolio.cash:return messagebox.showerror('Blackjack','Invalid bet.')
        self.portfolio.cash-=b;self.bet_amount=b;self.hand=[self.card(),self.card()];self.dealer=[self.card(),self.card()];self.active=True;self.draw_table()
    def hit(self):
        if self.active:self.hand.append(self.card());self.draw_table();self.stand() if self.val(self.hand)>21 else None
    def stand(self):
        if not self.active:return
        while self.val(self.dealer)<17:self.dealer.append(self.card())
        p,d=self.val(self.hand),self.val(self.dealer);win=d>21 or p>d;push=p==d
        self.portfolio.cash += self.bet_amount*(2 if win else 1 if push else 0);self.active=False;self.draw_table()
    def draw_table(self):
        c=self.canvas;c.delete('all');w=max(700,c.winfo_width());h=max(450,c.winfo_height());c.create_text(w/2,35,text='BLACKJACK TRAINING TABLE',fill='white',font=('Arial',20,'bold'));c.create_text(25,80,anchor='w',text='DEALER',fill='#b8d9c9',font=('Arial',11,'bold'));c.create_text(25,h/2+10,anchor='w',text='PLAYER',fill='#b8d9c9',font=('Arial',11,'bold'))
        def draw_hand(hand,y,hide=False):
            for i,(r,s) in enumerate(hand):
                x=170+i*105;c.create_rectangle(x,y,x+82,y+112,fill='white',outline='#c8d0d8',width=2);txt='?' if hide and i==1 else ('A' if r==1 else 'J' if r==11 else 'Q' if r==12 else 'K' if r==13 else str(r));col='#c52843' if s in '♥♦' else '#111';c.create_text(x+41,y+42,text=txt,fill=col,font=('Arial',24,'bold'));c.create_text(x+41,y+78,text=s,fill=col,font=('Arial',20,'bold'))
        draw_hand(self.dealer,90, self.active);draw_hand(self.hand,h/2+30);count=self.running;decks=max(.1,len(self.shoe)/52);true=count/decks if self.count_mode.get()=='Hi-Lo' else count;self.info.config(text=f'Balance ${self.portfolio.cash:,.2f} • Running {count:+d} • True {true:+.2f} • Decks left {decks:.2f}')

class CasinoWindow(ToolWindow):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('AFTER-HOURS ARCADE','1050x700');ttk.Button(self,text='BLACKJACK TRAINER',command=lambda:BlackjackWindow(self,portfolio,market)).pack(side='left',padx=15,pady=15);ttk.Button(self,text='ROULETTE',command=lambda:RouletteWindow(self,portfolio,market)).pack(side='left',padx=15,pady=15);ttk.Label(self,text='Virtual simulator credits only.').pack(side='left',padx=15)

class RouletteWindow(ToolWindow):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('ROULETTE','1000x760');self.bet=tk.IntVar(value=100);self.choice=tk.StringVar(value='RED');f=ttk.Frame(self);f.pack(fill='x',padx=10,pady=8);ttk.Label(f,text='Bet').pack(side='left');ttk.Entry(f,textvariable=self.bet,width=10).pack(side='left',padx=5);ttk.Combobox(f,textvariable=self.choice,values=['RED','BLACK','ODD','EVEN','1-18','19-36','0'],state='readonly',width=10).pack(side='left');ttk.Button(f,text='SPIN',command=self.spin).pack(side='left',padx=8);self.cv=tk.Canvas(self,bg='#10151d',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=10,pady=10);self.result=ttk.Label(self,text='');self.result.pack(fill='x',padx=10,pady=5);self.draw(0)
    def draw(self,n):
        c=self.cv;c.delete('all');w=max(700,c.winfo_width());h=max(500,c.winfo_height());cx=w/2;cy=h/2;r=min(w,h)*.34;c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#121b25',outline='#d8b96a',width=5)
        colors=['#2b2b2b','#b6283e'];nums=[0]+list(range(1,37))
        for i,num in enumerate(nums):
            a=2*math.pi*i/37-math.pi/2;col='#0d8c68' if num==0 else colors[i%2];x1=cx+math.cos(a)*r*.84;y1=cy+math.sin(a)*r*.84;x2=cx+math.cos(a+2*math.pi/37)*r*.84;y2=cy+math.sin(a+2*math.pi/37)*r*.84;c.create_polygon(cx,cy,x1,y1,x2,y2,fill=col,outline='#394653');tx=cx+math.cos(a+math.pi/37)*r*.66;ty=cy+math.sin(a+math.pi/37)*r*.66;c.create_text(tx,ty,text=str(num),fill='white',font=('Arial',8,'bold'))
        c.create_oval(cx-r*.18,cy-r*.18,cx+r*.18,cy+r*.18,fill='#1a2733',outline='#d8b96a',width=3);c.create_text(cx,cy,text=str(n),fill='white',font=('Arial',30,'bold'));c.create_oval(cx-7,cy-r-18,cx+7,cy-r-4,fill='#f3f3f3',outline='')
    def spin(self):
        try:b=int(self.bet.get())
        except:return
        if b<=0 or b>self.portfolio.cash:return messagebox.showerror('Roulette','Invalid bet.')
        self.portfolio.cash-=b;n=random.randint(0,36);choice=self.choice.get();win=(choice=='0' and n==0) or (choice=='RED' and n>0 and n%2==1) or (choice=='BLACK' and n>0 and n%2==0) or (choice=='ODD' and n%2==1) or (choice=='EVEN' and n>0 and n%2==0) or (choice=='1-18' and 1<=n<=18) or (choice=='19-36' and 19<=n<=36);payout=36 if choice=='0' else 2;self.portfolio.cash += b*payout if win else 0;self.result.config(text=f'Ball landed on {n}. '+('WIN' if win else 'LOSS')+f' • Balance ${self.portfolio.cash:,.2f}');self.draw(n)

class OrderWindow(ToolWindow):
    def __init__(self,parent,app,defaults=None):
        super().__init__(parent);self.app=app;self.style_window('ORDER ENTRY — SMART ROUTER','600x560');f=ttk.Frame(self);f.pack(fill='both',expand=True,padx=16,pady=16);self.vars={'ticker':tk.StringVar(value=defaults[0].symbol if defaults else 'SPY'),'qty':tk.StringVar(value='100'),'otype':tk.StringVar(value=defaults[2] if defaults else 'MARKET'),'price':tk.StringVar(value='' if not defaults or defaults[3] is None else str(round(defaults[3],2)))}
        for label,key in [('Ticker','ticker'),('Quantity','qty'),('Order Type','otype'),('Price / Stop','price')]:
            ttk.Label(f,text=label).pack(anchor='w',pady=(5,1));w=ttk.Combobox(f,textvariable=self.vars[key],values=['MARKET','LIMIT','STOP'],state='readonly') if key=='otype' else ttk.Entry(f,textvariable=self.vars[key]);w.pack(fill='x',pady=3)
        ttk.Label(f,text='Action').pack(anchor='w',pady=(5,1));self.action=ttk.Combobox(f,values=['BUY','SELL','SHORT','COVER'],state='readonly');self.action.set(defaults[1] if defaults else 'BUY');self.action.pack(fill='x',pady=3);self.margin=ttk.Label(f,text='');self.margin.pack(fill='x',pady=8);ttk.Button(f,text='SUBMIT ORDER',command=self.submit).pack(fill='x');ttk.Button(f,text='SMART LARGE LOT',command=lambda:self.app.smart_order()).pack(fill='x',pady=5);self.vars['ticker'].trace_add('write',lambda *x:self.update_margin());self.vars['qty'].trace_add('write',lambda *x:self.update_margin());self.action.bind('<<ComboboxSelected>>',lambda e:self.update_margin());self.update_margin()
    def update_margin(self):
        a=self.app.market.get_asset(self.vars['ticker'].get().upper());
        try:q=int(self.vars['qty'].get())
        except:q=0
        self.margin.config(text=f'Estimated short margin: ${a.price*q*.5:,.2f}' if a and self.action.get()=='SHORT' else 'Enter market, limit, or stop orders. Drag working lines directly on charts.')
    def submit(self):
        a=self.app.market.get_asset(self.vars['ticker'].get().upper());
        if not a:return messagebox.showerror('Order','Unknown ticker.')
        try:q=int(self.vars['qty'].get());price=float(self.vars['price'].get()) if self.vars['price'].get().strip() else None
        except:return messagebox.showerror('Order','Invalid quantity or price.')
        side=self.action.get();typ=self.vars['otype'].get()
        if typ=='MARKET':fn={'BUY':self.app.portfolio.buy_asset,'SELL':self.app.portfolio.sell_asset,'SHORT':self.app.portfolio.short_asset,'COVER':self.app.portfolio.cover_short}[side];ok,msg=fn(a,q)
        else:o=self.app.market.submit_pending(side,a,q,typ,price);ok=True;msg=f'Working order #{o["id"]}: {side} {q} {a.symbol} {typ} {price}'
        if ok:self.app.refresh();messagebox.showinfo('Order',msg);self.destroy()
        else:messagebox.showerror('Order rejected',msg)

class WorkspaceControls(ToolWindow):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.style_window('WORKSPACE — VARIABLES / LAYOUT','700x760');ttk.Label(self,text='Customize the terminal',font=('Arial',15,'bold')).pack(anchor='w',padx=12,pady=10);self.vars={}
        for name,val,lo,hi in [('Market speed',app.market.speed,.01,.5),('Step minutes',app.market.step_minutes,1,60),('UI refresh',.5,.1,2.0),('Chart zoom',1,.5,3)]:
            row=ttk.Frame(self);row.pack(fill='x',padx=12,pady=7);ttk.Label(row,text=name,width=18).pack(side='left');v=tk.DoubleVar(value=val);self.vars[name]=v;tk.Scale(row,from_=lo,to=hi,resolution=.01 if hi<5 else 1,orient='horizontal',variable=v,length=350,bg=PANEL,fg=TEXT,highlightthickness=0,command=lambda x:self.apply()).pack(side='left',fill='x',expand=True);ttk.Label(row,textvariable=v,width=8).pack(side='right')
        ttk.Label(self,text='Main workspace charts',font=('Arial',11,'bold')).pack(anchor='w',padx=12,pady=(15,5));self.count=tk.IntVar(value=len(app.charts));ttk.Combobox(self,textvariable=self.count,values=[4,6,8],state='readonly',width=8).pack(anchor='w',padx=20);ttk.Button(self,text='APPLY CHART COUNT',command=app.set_chart_count).pack(anchor='w',padx=20,pady=5);ttk.Label(self,text='Indicators are removable/addable from the Chart Tools menu and chart variables panel.',wraplength=640).pack(anchor='w',padx=12,pady=15)
    def apply(self):self.app.market.speed=float(self.vars['Market speed'].get());self.app.market.step_minutes=int(self.vars['Step minutes'].get());self.app.root.after(50,self.app.redraw)

class SmartOrderWindow(ToolWindow):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.style_window('SMART LARGE-LOT ORDER','650x560');f=ttk.Frame(self);f.pack(fill='both',expand=True,padx=14,pady=14);self.ticker=tk.StringVar(value='AAPL');self.qty=tk.IntVar(value=10000);self.side=tk.StringVar(value='BUY');self.style=tk.StringVar(value='VWAP');self.part=tk.DoubleVar(value=10);self.lbl=ttk.Label(f,text='');
        for label,var in [('Ticker',self.ticker),('Quantity',self.qty)]:ttk.Label(f,text=label).pack(anchor='w');ttk.Entry(f,textvariable=var).pack(fill='x',pady=4)
        ttk.Label(f,text='Action').pack(anchor='w');ttk.Combobox(f,textvariable=self.side,values=['BUY','SELL','SHORT','COVER'],state='readonly').pack(fill='x',pady=4);ttk.Label(f,text='Execution style').pack(anchor='w');ttk.Combobox(f,textvariable=self.style,values=['VWAP','TWAP','POV','ICEBERG'],state='readonly').pack(fill='x',pady=4);ttk.Label(f,text='Participation / slice %').pack(anchor='w');tk.Scale(f,from_=1,to=50,resolution=1,orient='horizontal',variable=self.part,bg=PANEL,fg=TEXT,highlightthickness=0).pack(fill='x');self.lbl.pack(fill='x',pady=8);ttk.Button(f,text='CALCULATE SMART PLAN',command=self.calc).pack(fill='x');ttk.Button(f,text='SUBMIT SIMULATED PLAN',command=self.submit).pack(fill='x',pady=5);self.calc()
    def calc(self):
        a=self.app.market.get_asset(self.ticker.get().upper());q=max(0,self.qty.get())
        if not a:self.lbl.config(text='Unknown ticker');return
        levels=self.app.market.get_book(a).asks if self.side.get() in ('BUY','COVER') else self.app.market.get_book(a).bids;need=q;notional=0;shown=0
        for l in levels:take=min(need,l.size);notional+=take*l.price;need-=take;shown+=take;\
            None
        avg=notional/max(1,shown);self.lbl.config(text=f'{a.symbol}: visible depth {shown:,}/{q:,} • est avg ${avg:,.4f} • residual {need:,} • model slippage ${(max(0,need)*a.price*.0005):,.2f}')
    def submit(self):
        a=self.app.market.get_asset(self.ticker.get().upper());q=max(0,self.qty.get());
        if not a or q<=0:return messagebox.showerror('Smart Order','Invalid ticker or quantity.')
        sliceq=max(1,int(q*self.part.get()/100));left=q;created=[];side=self.side.get()
        while left>0:n=min(sliceq,left);created.append(self.app.market.submit_pending(side,a,n,'LIMIT',a.ask if side in ('BUY','COVER') else a.bid));left-=n
        self.app.refresh();messagebox.showinfo('Smart Order',f'Created {len(created)} working slices using {self.style.get()} logic.');self.destroy()

class App:
    def __init__(self,root,market,portfolio):
        self.root=root;self.market=market;self.portfolio=portfolio;self.market.ui_app=self;self.active_chart=0;self.ind_vars={k:tk.BooleanVar(value=k in ('Volume',)) for k in ('SMA','EMA','BB','VWAP','RSI','Volume')};self.ind_vars_version=0;self.sort_key='Symbol';self.sort_reverse=False;self.build_style();self.make_menu();self.build();self.set_chart_count(initial=8);self.refresh()
    def build_style(self):
        s=ttk.Style();s.theme_use('clam');s.configure('.',background=PANEL,foreground=TEXT);s.configure('TFrame',background=PANEL);s.configure('TLabel',background=PANEL,foreground=TEXT);s.configure('TButton',background=PANEL2,foreground=TEXT,padding=6);s.map('TButton',background=[('active',BLUE)],foreground=[('active','white')]);s.configure('TEntry',fieldbackground='#f4f7fb',foreground='#111827',insertcolor='#111827');s.configure('TCombobox',fieldbackground='#f4f7fb',foreground='#111827',background='#f4f7fb',arrowcolor='#111827');s.map('TCombobox',fieldbackground=[('readonly','#f4f7fb')],foreground=[('readonly','#111827')]);s.configure('Treeview',background='#0c151f',fieldbackground='#0c151f',foreground=TEXT,rowheight=24);s.configure('Treeview.Heading',background='#1e3041',foreground=TEXT);s.map('Treeview',background=[('selected','#1c5f8f')],foreground=[('selected','#ffffff')])
    def make_menu(self):
        mb=tk.Menu(self.root,tearoff=0,bg='#172331',fg=TEXT,activebackground='#2c6da0',activeforeground='white');self.root.config(menu=mb);v=tk.Menu(mb,tearoff=0);v.add_command(label='Market Map',command=self.market_map);v.add_command(label='Global Trader Globe',command=self.globe);v.add_command(label='Options Chain',command=self.options);v.add_command(label='Level 2 / Level 3',command=self.depth);v.add_command(label='Market Screener',command=lambda:MarketListWindow(self.root,self.market));v.add_command(label='After-Hours Arcade',command=self.casino);mb.add_cascade(label='View',menu=v)
        ind=tk.Menu(mb,tearoff=0);[ind.add_checkbutton(label=k,variable=v,command=self.redraw) for k,v in self.ind_vars.items()];mb.add_cascade(label='Indicators',menu=ind)
        tr=tk.Menu(mb,tearoff=0);tr.add_command(label='Order Entry',command=self.order_window);tr.add_command(label='Smart Large-Lot Order',command=self.smart_order);tr.add_command(label='Liquidate Selected',command=self.liquidate);mb.add_cascade(label='Trading',menu=tr)
        ws=tk.Menu(mb,tearoff=0);ws.add_command(label='Workspace Variables / Sliders',command=self.workspace_controls);ws.add_command(label='8-Chart Default Workspace',command=lambda:self.set_chart_count(initial=8));mb.add_cascade(label='Workspace',menu=ws)
        ch=tk.Menu(mb,tearoff=0);ch.add_command(label='Crosshair',command=lambda:self.set_tool('Crosshair'));ch.add_command(label='Trendline',command=lambda:self.set_tool('Trendline'));ch.add_command(label='Horizontal Line',command=lambda:self.set_tool('Horizontal'));ch.add_command(label='Clear Drawings',command=self.clear_drawings);mb.add_cascade(label='Chart Tools',menu=ch)
        tm=tk.Menu(mb,tearoff=0);tm.add_command(label='Slow Down',command=lambda:self.change_speed(1.5));tm.add_command(label='Normal Speed',command=lambda:self.set_speed(.08));tm.add_command(label='Fast Forward',command=lambda:self.change_speed(.45));tm.add_command(label='Ultra Fast',command=lambda:self.change_speed(2.0));mb.add_cascade(label='Time',menu=tm)
    def build(self):
        self.root.title('STOCK_GAME PRO — GLOBAL TRADING SIMULATOR v1');self.root.geometry('1900x1100');outer=ttk.PanedWindow(self.root,orient='horizontal');outer.pack(fill='both',expand=True);left=ttk.Frame(outer,width=330);center=ttk.Frame(outer);right=ttk.Frame(outer,width=330);outer.add(left,weight=1);outer.add(center,weight=5);outer.add(right,weight=1)
        ttk.Label(left,text='MARKET / WATCHLIST',font=('Arial',12,'bold')).pack(anchor='w',padx=7,pady=5);sf=ttk.Frame(left);sf.pack(fill='x',padx=7);self.search=tk.StringVar();e=ttk.Entry(sf,textvariable=self.search);e.pack(fill='x');e.bind('<KeyRelease>',lambda x:self.refresh_watch());ff=ttk.Frame(left);ff.pack(fill='x',padx=7,pady=4);self.kind=tk.StringVar(value='STOCK');ttk.Combobox(ff,textvariable=self.kind,values=['STOCK','INDEX','COMMODITY','FUTURES','CRYPTO','INTERNATIONAL','FOREX','ALL'],state='readonly',width=12).pack(side='left');self.sector=tk.StringVar(value='ALL');ttk.Combobox(ff,textvariable=self.sector,values=['ALL']+self.market.sectors,state='readonly',width=14).pack(side='right');self.watch=ttk.Treeview(left,columns=('symbol','name','price','chg','sector'),show='headings',selectmode='browse');
        for c,l in zip(self.watch['columns'],['Symbol','Name','Price','Chg %','Sector']):self.watch.heading(c,text=l,command=lambda col=c:self.sort_watch(col));self.watch.column(c,width=78 if c!='name' else 130,anchor='center')
        self.watch.pack(fill='both',expand=True,padx=7,pady=5);self.watch.bind('<<TreeviewSelect>>',self.market_selected);self.watch.bind('<Double-1>',lambda e:self.load_active());self.watch.bind('<Button-3>',self.watch_context)
        ttk.Button(left,text='BUY / SELL / SHORT',command=self.order_window).pack(fill='x',padx=7,pady=3);ttk.Button(left,text='OPTIONS / SPREADS',command=self.options).pack(fill='x',padx=7,pady=3);ttk.Button(left,text='ADVANCED CHART',command=self.load_active).pack(fill='x',padx=7,pady=3)
        top=ttk.Frame(center);top.pack(fill='x',padx=5,pady=4);self.active_label=ttk.Label(top,text='Chart 1');self.active_label.pack(side='left');self.tf=ttk.Combobox(top,values=['1D','1W','1M','3M','6M','1Y','5Y','MAX'],state='readonly',width=7);self.tf.set('1D');self.tf.pack(side='left',padx=5);self.tf.bind('<<ComboboxSelected>>',lambda e:self.charts[self.active_chart].set_tf(self.tf.get()));self.ctype=ttk.Combobox(top,values=['Candles','Line','Area'],state='readonly',width=9);self.ctype.set('Candles');self.ctype.pack(side='left');self.ctype.bind('<<ComboboxSelected>>',lambda e:self.set_type());ttk.Button(top,text='BUY',command=lambda:self.chart_trade('BUY')).pack(side='left',padx=3);ttk.Button(top,text='SELL',command=lambda:self.chart_trade('SELL')).pack(side='left',padx=3);ttk.Button(top,text='LIMIT',command=lambda:self.chart_trade('BUY','LIMIT')).pack(side='left',padx=3);ttk.Button(top,text='STOP',command=lambda:self.chart_trade('SELL','STOP')).pack(side='left',padx=3);ttk.Button(top,text='SLOW',command=lambda:self.change_speed(1.5)).pack(side='left',padx=10);ttk.Button(top,text='▶ FAST',command=lambda:self.change_speed(2)).pack(side='left',padx=3);self.clock_label=ttk.Label(top,text='',font=('Arial',10,'bold'));self.clock_label.pack(side='right')
        self.grid=ttk.Frame(center);self.grid.pack(fill='both',expand=True,padx=5,pady=5);self.charts=[]
        ttk.Label(right,text='PORTFOLIO / POSITIONS',font=('Arial',12,'bold')).pack(anchor='w',padx=7,pady=5);self.pos=ttk.Treeview(right,columns=('qty','price','value','pnl','type'),show='headings',height=12);self.pos.pack(fill='x',padx=7);[self.pos.heading(c,text=c.upper()) for c in self.pos['columns']];self.pos.bind('<<TreeviewSelect>>',lambda e:self.position_info());self.pos.bind('<Button-3>',self.position_context);ttk.Button(right,text='LIQUIDATE / CASH',command=self.liquidate).pack(fill='x',padx=7,pady=4);self.pred=ttk.Label(right,text='MODEL',justify='left');self.pred.pack(fill='x',padx=7,pady=5);self.summary=tk.Text(right,height=10,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat');self.summary.pack(fill='both',expand=True,padx=7,pady=5);ttk.Button(right,text='ORDER ENTRY',command=self.order_window).pack(fill='x',padx=7,pady=3);ttk.Button(right,text='GLOBAL TRADER',command=self.globe).pack(fill='x',padx=7,pady=3);ttk.Button(right,text='MARKET MAP',command=self.market_map).pack(fill='x',padx=7,pady=3);ttk.Button(right,text='ARCADE',command=self.casino).pack(fill='x',padx=7,pady=3)
        newsf=ttk.Frame(self.root);newsf.pack(fill='x',padx=6,pady=4);nh=ttk.Frame(newsf);nh.pack(fill='x');ttk.Label(nh,text='NEWS / MARKET TAPE',font=('Arial',11,'bold')).pack(side='left');self.news_filter=ttk.Combobox(nh,values=['ALL','STOCK','INDEX','COMMODITY','MACRO','GLOBAL'],state='readonly',width=12);self.news_filter.set('ALL');self.news_filter.pack(side='right');self.news_filter.bind('<<ComboboxSelected>>',lambda e:self.refresh_news());self.news=tk.Text(newsf,height=7,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat');self.news.pack(fill='both');self.status=ttk.Label(self.root,text='');self.status.pack(fill='x',padx=7)
    def set_chart_count(self,initial=None):
        count=initial or int(getattr(self,'_workspace_count',8) if hasattr(self,'_workspace_count') else 8);self._workspace_count=count
        if hasattr(self,'grid'):
            for c in self.charts:c.destroy()
            self.charts=[Chart(self.grid,self,i) for i in range(count)]
            for i,c in enumerate(self.charts):c.grid(row=i//4,column=i%4,sticky='nsew',padx=2,pady=2);self.grid.rowconfigure(i//4,weight=1);self.grid.columnconfigure(i%4,weight=1)
            defaults=['SPY','VIX','NVDA','AAPL','CL=F','GC=F','GME',random.choice([a.symbol for a in self.market.stocks])]
            for i,c in enumerate(self.charts):
                if i<len(defaults):a=self.market.get_asset(defaults[i]) or self.market.get_asset('SPY');c.set_asset(a)
            self.active_chart=0;self.sync_chart_controls()
    def market_selected(self,e=None):
        a=self.selected();
        if a:self.load_asset_auto(a)
    def selected(self):
        it=self.watch.selection();return self.market.get_asset(self.watch.item(it[0],'values')[0]) if it else None
    def sort_watch(self,c):
        key={'symbol':'Symbol','name':'Name','price':'Price','chg':'Change %','sector':'Sector'}[c];self.sort_reverse=not self.sort_reverse if self.sort_key==key else False;self.sort_key=key;self.refresh_watch()
    def refresh_watch(self):
        q=self.search.get().upper();kind=self.kind.get();sec=self.sector.get();mapping={'STOCK':self.market.stocks,'INDEX':self.market.indexes,'COMMODITY':self.market.commodities,'FUTURES':self.market.futures,'CRYPTO':self.market.crypto,'INTERNATIONAL':self.market.international,'FOREX':self.market.forex};assets=list(mapping.get(kind,self.market.all_assets()));
        if sec!='ALL':assets=[a for a in assets if a.category==sec]
        if q:assets=[a for a in assets if q in a.symbol.upper() or q in a.name.upper()]
        k=self.sort_key;fn=(lambda a:a.symbol.upper()) if k=='Symbol' else (lambda a:a.name.upper()) if k=='Name' else (lambda a:a.price) if k=='Price' else (lambda a:a.change_percent()) if k=='Change %' else (lambda a:a.category.upper());assets=sorted(assets,key=fn,reverse=self.sort_reverse);sel=self.watch.selection();sid=self.watch.item(sel[0],'values')[0] if sel else None;self.watch.delete(*self.watch.get_children())
        for a in assets:self.watch.insert('','end',iid=a.symbol,values=(a.symbol,a.name,f'${a.price:,.2f}',f'{a.change_percent():+.2f}%',a.category))
        if sid and sid in self.watch.get_children():self.watch.selection_set(sid);self.watch.focus(sid)
    def watch_context(self,event):
        iid=self.watch.identify_row(event.y)
        if not iid:return
        self.watch.selection_set(iid);self.watch.focus(iid);self.watch.see(iid);a=self.market.get_asset(iid);m=tk.Menu(self.watch,tearoff=0);m.add_command(label=f'BUY {a.symbol}',command=lambda:self.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL {a.symbol}',command=lambda:self.order_window(a,'SELL','MARKET',None));m.add_command(label=f'SHORT {a.symbol}',command=lambda:self.order_window(a,'SHORT','MARKET',None));m.add_command(label='COVER',command=lambda:self.order_window(a,'COVER','MARKET',None));m.add_separator();m.add_command(label='Open Options Chain',command=lambda:self.options_for(a));m.add_command(label='Advanced Chart',command=lambda:self.load_asset_auto(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.depth_for(a));m.tk_popup(event.x_root,event.y_root)
    def load_asset_auto(self,a):self.charts[self.active_chart].set_asset(a);self.sync_chart_controls();self.status_flash(f'{a.symbol} loaded into Chart {self.active_chart+1}')
    def load_active(self):
        a=self.selected();
        if a:self.load_asset_auto(a)
    def options_for(self,a):w=OptionsWindow(self.root,self.market,self.portfolio,self.refresh);w.entry.delete(0,'end');w.entry.insert(0,a.symbol);w.apply_symbol()
    def depth_for(self,a):DepthWindow(self.root,self.market,a)
    def order_window(self,a=None,side=None,otype=None,price=None):OrderWindow(self.root,self,defaults=(a,side or 'BUY',otype or 'MARKET',price) if a else None)
    def chart_trade(self,side,otype='MARKET'):
        a=self.charts[self.active_chart].asset
        if a:self.order_window(a,side,otype,None if otype=='MARKET' else self.charts[self.active_chart].y_to_price(self.charts[self.active_chart].winfo_height()/2))
    def options(self):OptionsWindow(self.root,self.market,self.portfolio,self.refresh)
    def market_map(self):MarketMapWindow(self.root,self.market)
    def globe(self):GlobeWindow(self.root,self.market)
    def depth(self):
        a=self.selected() or self.charts[self.active_chart].asset
        if a:self.depth_for(a)
    def casino(self):CasinoWindow(self.root,self.portfolio,self.market)
    def workspace_controls(self):WorkspaceControls(self.root,self)
    def smart_order(self):SmartOrderWindow(self.root,self)
    def set_tool(self,t):
        for c in self.charts:c.tool=t
    def clear_drawings(self):
        for c in self.charts:c.drawings=[];c.draw()
    def sync_chart_controls(self):
        c=self.charts[self.active_chart];self.active_label.config(text=f'Chart {self.active_chart+1}: {c.asset.symbol if c.asset else "—"}');self.tf.set(c.timeframe);self.ctype.set(c.kind)
    def set_type(self):self.charts[self.active_chart].kind=self.ctype.get();self.charts[self.active_chart].draw()
    def redraw(self):self.ind_vars_version+=1;[c.draw() for c in self.charts]
    def refresh_positions(self):
        old=self.pos.selection();keep=old[0] if old else None;self.pos.delete(*self.pos.get_children())
        for sym,name,q,p,v,pnl,typ in self.portfolio.position_rows(self.market.all_assets()):self.pos.insert('','end',iid=sym,values=(f'{q:,}',f'${p:,.2f}',f'${v:,.2f}',f'${pnl:,.2f}',typ))
        if keep and keep in self.pos.get_children():self.pos.selection_set(keep);self.pos.focus(keep)
    def position_context(self,e):
        iid=self.pos.identify_row(e.y)
        if not iid:return
        self.pos.selection_set(iid);m=tk.Menu(self.pos,tearoff=0);m.add_command(label='Liquidate / Cash',command=self.liquidate);m.tk_popup(e.x_root,e.y_root)
    def position_info(self):
        it=self.pos.selection();
        if it:self.status_flash(f'{it[0]} selected — selection preserved during refresh')
    def liquidate(self):
        it=self.pos.selection();
        if not it:return messagebox.showwarning('Position','Select a position row first.')
        k=it[0];
        if k.startswith('OPT:'):ok,msg=self.portfolio.liquidate_strategy(int(k.split(':')[1]))
        else:ok,msg=self.portfolio.liquidate_asset(self.market.get_asset(k))
        if ok:self.refresh();messagebox.showinfo('Liquidated',msg)
        else:messagebox.showerror('Liquidation',msg)
    def refresh_news(self):
        filt=self.news_filter.get();self.news.delete('1.0','end');idx={x.symbol for x in self.market.indexes};com={x.symbol for x in self.market.commodities};stocks={x.symbol for x in self.market.stocks}
        for n in self.market.news[-35:]:
            sym=getattr(n,'symbol',None);sev=getattr(n,'severity','NORMAL')
            if filt=='STOCK' and sym not in stocks:continue
            if filt=='INDEX' and sym not in idx:continue
            if filt=='COMMODITY' and sym not in com:continue
            if filt=='MACRO' and sev not in ('MACRO','MAJOR'):continue
            if filt=='GLOBAL' and sym in stocks|idx|com:continue
            self.news.insert('end',f'[{sev}] {n}\n')
    def change_speed(self,factor):self.market.speed=max(.005,min(2,self.market.speed/factor));self.status_flash(f'Time speed {1/self.market.speed:.1f}x base')
    def set_speed(self,s):self.market.speed=s;self.status_flash('Normal simulation speed')
    def status_flash(self,msg):self.status.config(text=msg)
    def refresh(self):
        try:
            self.portfolio.apply_corporate_actions(self.market.all_assets());self.refresh_watch();self.refresh_positions();self.summary.delete('1.0','end');self.summary.insert('end',self.portfolio.summary(self.market.all_assets()));
            a=self.selected() or self.charts[self.active_chart].asset
            if a:
                p=self.market.predict(a);self.pred.config(text=f'MODEL {a.symbol}\n{p["label"]}  confidence {p["confidence"]*100:.0f}%\nMomentum {p["momentum"]*100:+.2f}%  vol {p["volatility"]*100:.2f}%')
            self.refresh_news();self.clock_label.config(text=f'{self.market.clock.time}  •  {self.market.clock.utc_time}  •  {"US OPEN" if self.market.clock.open else "US CLOSED"}');self.status.config(text=f'Assets {len(self.market.all_assets())} • {self.market.data_status} • Working orders {len(self.market.pending_orders)+len(self.market.pending_option_orders)+len(self.market.pending_spread_orders)} • Engine errors {len(self.market.errors)}');self.redraw()
        except Exception as e:self.status.config(text=f'UI recovered: {e}')
        self.root.after(700,self.refresh)
