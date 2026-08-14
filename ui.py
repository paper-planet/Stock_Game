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
        
        if getattr(self.app,'selected_chart',None)==self.index:
            self.app.selected_chart=None
            self.configure(highlightbackground='#263547')
        else:
            self.app.selected_chart=self.index
            for ch in self.app.charts:
                ch.configure(highlightbackground=BLUE if ch is self else '#263547')
            self.app.active_chart=self.index;self.app.sync_chart_controls()
        self.start=(e.x,e.y);self.cross=(e.x,e.y)
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
        p=self.y_to_price(e.y);m=tk.Menu(self,tearoff=0);m.add_command(label=f'BUY {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'BUY','LIMIT',p));m.add_command(label=f'SELL {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SELL','LIMIT',p));m.add_command(label=f'SHORT {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SHORT','LIMIT',p));m.add_command(label=f'COVER {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'COVER','LIMIT',p));m.add_separator();m.add_command(label='Buy at Market',command=lambda:self.app.order_window(a,'BUY','MARKET',None));m.add_command(label='Set Stop',command=lambda:self.app.order_window(a,'SELL','STOP',p));m.add_command(label='Open Options',command=lambda:self.app.options_for(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.app.depth_for(a));m.add_command(label='POP OUT ADVANCED CHART',command=lambda:self.app.advanced_chart(a));m.add_separator();m.add_command(label='ADD CHART',command=self.app.add_chart);m.add_command(label='REMOVE THIS CHART',command=lambda:self.app.remove_chart(self.index));m.tk_popup(e.x_root,e.y_root)
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
        super().__init__(parent);self.market=market;self.portfolio=portfolio;self.refresh_main=refresh;self.style_window('OPTIONS — PRO CHAIN','1320x820');self.rate_ms=350;self.selected_side='CALL';self.selected_strike=None;self.visible_cols={x:True for x in ['Bid','Ask','Last','Vol','OI','IV','Delta','Gamma','Theta','Vega']}
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=7)
        ttk.Label(top,text='Ticker').pack(side='left');self.entry=ttk.Entry(top,width=12);self.entry.insert(0,'SPX');self.entry.pack(side='left',padx=5);self.entry.bind('<Return>',lambda e:self.apply_symbol());ttk.Button(top,text='LOAD',command=self.apply_symbol).pack(side='left')
        for label,vals,var in [('Expiry',[x[0] for x in EXPIRATIONS],'0DTE'),('Range',['ATM ±5 Strikes','ATM ±10 Strikes','ATM ±20 Strikes','ATM ±50 Strikes','All'],'ATM ±20 Strikes'),('Sort',['Strike','Volume','Open Interest','IV','Delta','Gamma'],'Strike'),('Update',['150ms','250ms','350ms','500ms','1000ms'],'350ms')]:
            ttk.Label(top,text=label).pack(side='left',padx=(12,2));v=ttk.Combobox(top,values=vals,state='readonly',width=12);v.set(var);v.pack(side='left');setattr(self,label.lower().replace('update','rate'),v)
        self.span=self.range
        self.rate.bind('<<ComboboxSelected>>',lambda e:self.set_rate());ttk.Label(top,text='Sector').pack(side='left',padx=(10,2));self.sector_filter=tk.StringVar(value='ALL');self.sector_cb=ttk.Combobox(top,textvariable=self.sector_filter,values=['ALL']+market.sectors,state='readonly',width=14);self.sector_cb.pack(side='left');self.sector_cb.bind('<<ComboboxSelected>>',lambda e:self.apply_correlated_filter());ttk.Label(top,text='Correlated').pack(side='left',padx=(8,2));self.corr=tk.StringVar(value='Underlying');self.corr_cb=ttk.Combobox(top,textvariable=self.corr,values=['Underlying','Sector ETF','Index','Commodity','FX'],state='readonly',width=14);self.corr_cb.pack(side='left');ttk.Button(top,text='SPREAD BUILDER',command=self.spread_builder).pack(side='left',padx=7);ttk.Button(top,text='VARIABLES',command=self.variables).pack(side='left');self.live=ttk.Label(top,text='● LIVE');self.live.pack(side='right')
        head=tk.Frame(self,bg=BG);head.pack(fill='x',padx=8);tk.Label(head,text='CALLS',bg='#123326',fg=GREEN,font=('Arial',11,'bold')).pack(side='left',fill='x',expand=True);tk.Label(head,text='STRIKE / ATM',bg='#3c3320',fg=YELLOW,font=('Arial',11,'bold'),width=16).pack(side='left');tk.Label(head,text='PUTS',bg='#38202a',fg=RED,font=('Arial',11,'bold')).pack(side='left',fill='x',expand=True)
        cols=('cbid','cask','clast','cvol','coi','civ','cd','cg','ct','cv','strike','pd','pg','pt','pv','piv','poi','pvol','plast','pbid','pask');labels=['Bid','Ask','Last','Vol','OI','IV','Δ','Γ','Θ','V','Strike','Δ','Γ','Θ','V','IV','OI','Vol','Last','Bid','Ask'];self.chain_frame=ttk.Frame(self);self.chain_frame.pack(fill='both',expand=True,padx=8,pady=(5,0))
        self.call_cols=['Bid','Ask','Last','Vol','OI','IV','Delta','Gamma','Theta','Vega']; self.put_cols=list(self.call_cols)
        self.tv_calls=ttk.Treeview(self.chain_frame,show='headings',selectmode='browse'); self.tv_strike=ttk.Treeview(self.chain_frame,columns=('strike',),show='headings',selectmode='browse'); self.tv_puts=ttk.Treeview(self.chain_frame,show='headings',selectmode='browse')
        self.tv_strike.heading('strike',text='STRIKE / ATM'); self.tv_strike.column('strike',width=96,anchor='center',stretch=False)
        self.tv_calls.grid(row=0,column=0,sticky='nsew'); self.tv_strike.grid(row=0,column=1,sticky='nsew'); self.tv_puts.grid(row=0,column=2,sticky='nsew')
        self.chain_frame.columnconfigure(0,weight=1); self.chain_frame.columnconfigure(1,weight=0); self.chain_frame.columnconfigure(2,weight=1); self.chain_frame.rowconfigure(0,weight=1)
        self.tv_calls.tag_configure('itm',background='#173d2e',foreground='#bfffe7');self.tv_calls.tag_configure('otm',background='#5b1f2c',foreground='#ffdce2');self.tv_calls.tag_configure('atm',background='#403720',foreground='#fff2ae');self.tv_calls.tag_configure('owned',background='#1b4d77',foreground='#ffffff')
        self.tv_puts.tag_configure('itm',background='#173d2e',foreground='#bfffe7');self.tv_puts.tag_configure('otm',background='#5b1f2c',foreground='#ffdce2');self.tv_puts.tag_configure('atm',background='#403720',foreground='#fff2ae');self.tv_puts.tag_configure('owned',background='#1b4d77',foreground='#ffffff')
        for tv in (self.tv_calls,self.tv_strike,self.tv_puts):
            tv.bind('<Button-1>',lambda e,tv=tv:self.chain_select(e,tv)); tv.bind('<Button-3>',lambda e,tv=tv:self.context(e)); tv.bind('<Double-1>',lambda e:self.trade())
        self.tv=self.tv_calls
        self.info_lbl=ttk.Label(self,text='ITM = green/blue • OTM = red • ATM = gold • right-click any column to trade or configure variables.');self.info_lbl.pack(fill='x',padx=8,pady=5);self.after(100,self.update_chain)
    def set_rate(self):self.rate_ms=int(self.rate.get().replace('ms',''))
    def variables(self):
        if getattr(self,'var_window',None) is not None and self.var_window.winfo_exists(): self.var_window.lift(); return
        w=tk.Toplevel(self);self.var_window=w;w.title('OPTIONS VARIABLES');w.geometry('380x520');w.resizable(True,True);w.configure(bg=BG);ttk.Label(w,text='Visible option-chain variables',font=('Arial',12,'bold')).pack(anchor='w',padx=12,pady=10)
        for k in self.visible_cols:
            v=tk.BooleanVar(value=self.visible_cols[k]);ttk.Checkbutton(w,text=k,variable=v,command=lambda key=k,var=v:self.toggle_col(key,var)).pack(anchor='w',padx=20,pady=4)
        ttk.Button(w,text='RESET ALL COLUMNS',command=lambda:self.reset_columns()).pack(fill='x',padx=18,pady=12)
        w.protocol('WM_DELETE_WINDOW',lambda:(setattr(self,'var_window',None),w.destroy()))
    def reset_columns(self):
        for k in self.visible_cols:self.visible_cols[k]=True
        self.rebuild_chain_columns()
    def toggle_col(self,k,v):self.visible_cols[k]=bool(v.get());self.rebuild_chain_columns()
    def rebuild_chain_columns(self):
        cols=[k for k,v in self.visible_cols.items() if v]
        if not cols: cols=['Bid']
        for tv in (self.tv_calls,self.tv_puts):
            tv['columns']=tuple(cols)
            for c in cols: tv.heading(c,text=c if c not in ('Delta','Gamma','Theta','Vega') else {'Delta':'Δ','Gamma':'Γ','Theta':'Θ','Vega':'Vega'}[c]);tv.column(c,width=76,anchor='center',stretch=False)
        self.update_chain()
    def chain_select(self,e,tv):
        iid=tv.identify_row(e.y)
        if not iid:return
        for x in (self.tv_calls,self.tv_strike,self.tv_puts):
            x.selection_remove(x.selection())
        tv.selection_set(iid);tv.focus(iid);self.selected_strike=int(iid);self.selected_side='CALL' if tv is self.tv_calls else 'PUT';self.info()
    def apply_symbol(self):
        s=self.entry.get().strip().upper();a=self.market.get_asset(s)
        if not a:self.info_lbl.config(text=f'{s}: ticker not found');return
        if self.expiry.get()=='0DTE' and a.symbol not in {'SPX','NDX','RUT','DJI','ES=F','NQ=F'}: self.expiry.set('1D')
        self.info_lbl.config(text=f'Loaded {a.symbol} — {a.name}')
    def apply_correlated_filter(self):
        sec=self.sector_filter.get()
        if sec!='ALL':
            candidates=[a.symbol for a in self.market.stocks if a.category==sec][:40]
            if candidates:self.corr_cb['values']=['Underlying']+candidates
        else:self.corr_cb['values']=['Underlying','Sector ETF','Index','Commodity','FX']
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
            self.rebuild_chain_columns_no_refresh()
            a=self.asset();days=dict(EXPIRATIONS).get(self.expiry.get(),0);span={'ATM ±5 Strikes':5,'ATM ±10 Strikes':10,'ATM ±20 Strikes':20,'ATM ±50 Strikes':50}.get(self.span.get(),20);cs=option_chain(a,days,span);calls={int(c.strike):c for c in cs if c.option_type=='call'};puts={int(c.strike):c for c in cs if c.option_type=='put'};ks=sorted(calls);center=round(a.price);rng=self.span.get()
            if rng!='All':ks=[k for k in ks if abs(k-center)<=int(rng.split('±')[1].split()[0])]
            if self.sort.get()!='Strike':
                def m(k):
                    c=calls[k];return {'Volume':c.volume,'Open Interest':c.open_interest,'IV':c.volatility,'Delta':abs(c.stats['delta']),'Gamma':c.stats['gamma']}.get(self.sort.get(),k)
                ks=sorted(ks,key=m,reverse=True)
            for tv in (self.tv_calls,self.tv_strike,self.tv_puts):tv.delete(*tv.get_children())
            visible=[k for k,v in self.visible_cols.items() if v] or ['Bid']
            for k in ks:
                c,p=calls[k],puts[k];cs_,ps_=c.stats,p.stats
                ctag='atm' if k==center else 'itm' if c.itm() else 'otm'; ptag='atm' if k==center else 'itm' if p.itm() else 'otm'
                if self.owned_contract(a,k,'call',days):ctag='owned'
                if self.owned_contract(a,k,'put',days):ptag='owned'
                cv={'Bid':f'{c.bid:.2f}','Ask':f'{c.ask:.2f}','Last':f'{c.mid:.2f}','Vol':f'{c.volume:,}','OI':f'{c.open_interest:,}','IV':f'{c.volatility*100:.1f}%','Delta':f'{cs_["delta"]:+.2f}','Gamma':f'{cs_["gamma"]:.4f}','Theta':f'{cs_["theta"]:.3f}','Vega':f'{cs_["vega"]:.3f}'}
                pv={'Bid':f'{p.bid:.2f}','Ask':f'{p.ask:.2f}','Last':f'{p.mid:.2f}','Vol':f'{p.volume:,}','OI':f'{p.open_interest:,}','IV':f'{p.volatility*100:.1f}%','Delta':f'{ps_["delta"]:+.2f}','Gamma':f'{ps_["gamma"]:.4f}','Theta':f'{ps_["theta"]:.3f}','Vega':f'{ps_["vega"]:.3f}'}
                self.tv_calls.insert('','end',iid=str(k),values=tuple(cv[x] for x in visible),tags=(ctag,));self.tv_strike.insert('','end',iid=str(k),values=(f'${k:,.0f}',),tags=('atm' if k==center else '',));self.tv_puts.insert('','end',iid=str(k),values=tuple(pv[x] for x in visible),tags=(ptag,))
            self.live.config(text=f'● LIVE  {a.symbol} ${a.price:,.2f}  {self.market.clock.time}  ATM ${center:,.0f}  {days}D')
        except Exception as e:self.info_lbl.config(text=f'Chain recovered: {e}')
        if self.winfo_exists():self.after(self.rate_ms,self.update_chain)
    def rebuild_chain_columns_no_refresh(self):
        cols=[k for k,v in self.visible_cols.items() if v] or ['Bid']
        for tv in (self.tv_calls,self.tv_puts):
            if tuple(tv['columns'])!=tuple(cols):
                tv['columns']=tuple(cols)
                for c in cols:tv.heading(c,text=c if c not in ('Delta','Gamma','Theta','Vega') else {'Delta':'Δ','Gamma':'Γ','Theta':'Θ','Vega':'Vega'}[c]);tv.column(c,width=76,anchor='center',stretch=False)
    
    def info(self):
        it=self.tv.selection()
        if not it:return
        self.selected_strike=int(it[0]);a=self.asset();d=dict(EXPIRATIONS).get(self.expiry.get(),0);c=OptionContract(a,self.selected_strike,d,'call');p=OptionContract(a,self.selected_strike,d,'put');self.info_lbl.config(text=f'{a.symbol} {self.selected_strike:,.0f} | CALL Δ {c.stats["delta"]:+.3f} Γ {c.stats["gamma"]:.5f} Θ {c.stats["theta"]:.3f} | PUT Δ {p.stats["delta"]:+.3f} Γ {p.stats["gamma"]:.5f} Θ {p.stats["theta"]:.3f}')
    def selected_contract(self,side=None):
        it=self.tv.selection()
        if not it:return None
        k=int(it[0]);a=self.asset();days=dict(EXPIRATIONS).get(self.expiry.get(),0);typ=(side or self.selected_side).lower();return OptionContract(a,k,days,typ)
    def context(self,e):
        tv=e.widget;iid=tv.identify_row(e.y)
        if not iid:return
        self.selected_strike=int(iid);self.selected_side='CALL' if tv is self.tv_calls else 'PUT';tv.selection_set(iid);tv.focus(iid);m=tk.Menu(self,tearoff=0);c=self.selected_contract();m.add_command(label=f'BUY {c}',command=lambda:self.trade_action('BUY'));m.add_command(label=f'SELL/CLOSE {c}',command=lambda:self.trade_action('SELL'));m.add_command(label='Set LIMIT',command=lambda:self.option_order('LIMIT'));m.add_command(label='Set STOP',command=lambda:self.option_order('STOP'));m.add_separator();m.add_command(label='Add Leg to Spread',command=self.add_leg_to_spread);m.add_command(label='Open Spread Builder',command=self.spread_builder);m.add_command(label='Liquidate Matching Contract',command=self.liquidate_matching);m.tk_popup(e.x_root,e.y_root)
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
        top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8);ttk.Label(top,text='Ticker').pack(side='left');ttk.Entry(top,textvariable=self.ticker,width=10).pack(side='left',padx=4);ttk.Label(top,text='Expiry').pack(side='left',padx=(12,2));ttk.Combobox(top,textvariable=self.exp,values=[x[0] for x in EXPIRATIONS if x[0] != '0DTE'],state='readonly',width=8).pack(side='left');ttk.Label(top,text='Preset').pack(side='left',padx=(12,2));self.preset=tk.StringVar(value='Call Debit Spread');ttk.Combobox(top,textvariable=self.preset,values=['Call Debit Spread','Call Credit Spread','Put Debit Spread','Put Credit Spread','Bull Call Spread','Bear Put Spread','Long Straddle','Short Straddle','Iron Condor'],state='readonly',width=18).pack(side='left');ttk.Button(top,text='LOAD PRESET',command=self.template).pack(side='left',padx=6)
        self.tv=ttk.Treeview(self,columns=('action','type','strike','qty','mark'),show='headings',height=8);[self.tv.heading(c,text=c.upper()) for c in self.tv['columns']];self.tv.pack(fill='x',padx=10,pady=8);qbar=ttk.Frame(self);qbar.pack(fill='x',padx=10);ttk.Label(qbar,text='Selected leg quantity').pack(side='left');self.leg_qty=tk.IntVar(value=1);ttk.Spinbox(qbar,from_=1,to=100000, textvariable=self.leg_qty,width=10,command=self.set_selected_qty).pack(side='left',padx=6);ttk.Button(qbar,text='APPLY QTY',command=self.set_selected_qty).pack(side='left');self.preview=ttk.Label(self,text='No legs');self.preview.pack(fill='x',padx=10,pady=8);self.payoff=tk.Canvas(self,bg='#081018',height=240,highlightthickness=0);self.payoff.pack(fill='x',padx=10,pady=8);bar=ttk.Frame(self);bar.pack(fill='x',padx=10);ttk.Label(bar,text='Order').pack(side='left');ttk.Combobox(bar,textvariable=self.action,values=['BUY','SELL'],state='readonly',width=8).pack(side='left',padx=4);ttk.Combobox(bar,textvariable=self.order_type,values=['MARKET','LIMIT','STOP'],state='readonly',width=10).pack(side='left',padx=4);self.price=tk.DoubleVar(value=0);ttk.Entry(bar,textvariable=self.price,width=10).pack(side='left',padx=4);ttk.Button(bar,text='EXECUTE / WORK',command=self.execute).pack(side='left',padx=8);ttk.Button(bar,text='REMOVE SELECTED',command=self.remove).pack(side='left');self.template()
        if first:self.rows.append({'action':'BUY','type':first.option_type.upper(),'strike':first.strike,'qty':1,'contract':first});self.refresh_table()
    def template(self):
        a=self.market.get_asset(self.ticker.get().upper())
        if not a:return
        d=dict(EXPIRATIONS).get(self.exp.get(),30);center=round(a.price);w=5;name=self.preset.get()
        presets={
            'Call Debit Spread':[('BUY','CALL',center),('SELL','CALL',center+w)],
            'Call Credit Spread':[('SELL','CALL',center),('BUY','CALL',center+w)],
            'Put Debit Spread':[('BUY','PUT',center),('SELL','PUT',center-w)],
            'Put Credit Spread':[('SELL','PUT',center),('BUY','PUT',center-w)],
            'Bull Call Spread':[('BUY','CALL',center),('SELL','CALL',center+w)],
            'Bear Put Spread':[('BUY','PUT',center),('SELL','PUT',center-w)],
            'Long Straddle':[('BUY','CALL',center),('BUY','PUT',center)],
            'Short Straddle':[('SELL','CALL',center),('SELL','PUT',center)],
            'Iron Condor':[('BUY','PUT',center-2*w),('SELL','PUT',center-w),('SELL','CALL',center+w),('BUY','CALL',center+2*w)]}
        self.rows=[{'action':x,'type':t,'strike':k,'qty':1} for x,t,k in presets.get(name,presets['Call Debit Spread'])];self.refresh_table(d)
    def refresh_table(self,d=None):
        self.tv.delete(*self.tv.get_children());a=self.market.get_asset(self.ticker.get().upper());days=d if d is not None else dict(EXPIRATIONS).get(self.exp.get(),30);net=0;greeks={k:0 for k in ['delta','gamma','theta','vega']}
        for i,r in enumerate(self.rows):
            c=r.get('contract') or OptionContract(a,r['strike'],days,r['type'].lower());r['contract']=c;sign=1 if r['action']=='BUY' else -1;net+=sign*c.mid*r['qty']*100;s=c.stats
            for k in greeks:greeks[k]+=sign*s[k]*r['qty']*100
            self.tv.insert('','end',iid=str(i),values=(r['action'],r['type'],f'{c.strike:,.0f}',r['qty'],f'${c.mid:.2f}'))
        self.price.set(round(abs(net)/100,2));self.preview.config(text=f'Net debit/credit ${net:,.2f} • Δ {greeks["delta"]:+.2f} Γ {greeks["gamma"]:+.4f} Θ {greeks["theta"]:+.2f} Vega {greeks["vega"]:+.2f} • Contracts are multiplied by each leg quantity');self.draw_payoff(a)
    def set_selected_qty(self):
        it=self.tv.selection()
        if not it:return
        try:self.rows[int(it[0])]['qty']=max(1,int(self.leg_qty.get()))
        except:pass
        self.refresh_table()
    def draw_payoff(self,a):
        c=self.payoff;c.delete('all');w=max(600,c.winfo_width());h=max(180,c.winfo_height());center=a.price;span=max(center*.25,10);lo=max(.01,center-span);hi=center+span;pts=[]
        vals=[]
        for i in range(101):
            spot=lo+(hi-lo)*i/100;pnl=0
            for r in self.rows:
                oc=r.get('contract') or OptionContract(a,r['strike'],dict(EXPIRATIONS).get(self.exp.get(),30),r['type'].lower());pnl+=(1 if r['action']=='BUY' else -1)*r['qty']*oc.intrinsic(spot)*100
            vals.append(pnl)
        mn,mx=min(vals+[0]),max(vals+[0]);rng=max(1,mx-mn);base=h-30
        for i,pnl in enumerate(vals):
            x=20+(w-40)*i/100;y=base-(pnl-mn)/rng*(h-55);pts.extend([x,y])
        c.create_line(20,base-(0-mn)/rng*(h-55),w-20,base-(0-mn)/rng*(h-55),fill='#607080',dash=(4,3));
        if len(pts)>3:c.create_line(*pts,fill=GREEN,width=3)
        c.create_text(22,10,anchor='nw',text='PAYOFF PREVIEW',fill=TEXT,font=('Arial',10,'bold'));c.create_text(w-22,10,anchor='ne',text=f'Underlying ${a.price:,.2f}',fill=MUTED,font=('Arial',9))
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
        super().__init__(parent);self.market=market;self.style_window('MARKET MAP — SECTOR TREEMAP','1350x950');self.sec=tk.StringVar(value='ALL');self.mode=tk.StringVar(value='Market Cap');self.detail=tk.BooleanVar(value=True);self.min_tile=tk.IntVar(value=42);self.rects=[]
        bar=ttk.Frame(self);bar.pack(fill='x',padx=8,pady=5);ttk.Label(bar,text='Sector').pack(side='left');ttk.Combobox(bar,textvariable=self.sec,values=['ALL']+market.sectors,state='readonly',width=18).pack(side='left',padx=5);ttk.Label(bar,text='Sizing').pack(side='left');ttk.Combobox(bar,textvariable=self.mode,values=['Market Cap','Equal'],state='readonly',width=12).pack(side='left',padx=5);ttk.Checkbutton(bar,text='Ticker + %',variable=self.detail).pack(side='left',padx=10);ttk.Button(bar,text='VARIABLES',command=self.variables).pack(side='right')
        self.cv=tk.Canvas(self,bg='#05090e',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=8,pady=8);self.cv.bind('<Button-3>',self.context);self.cv.bind('<Button-1>',self.click);self.after(200,self.draw)
    def variables(self):
        w=tk.Toplevel(self);w.title('MARKET MAP VARIABLES');w.geometry('430x360');w.configure(bg=BG);ttk.Label(w,text='Map controls',font=('Arial',13,'bold')).pack(anchor='w',padx=15,pady=12);ttk.Checkbutton(w,text='Show ticker + percentage',variable=self.detail).pack(anchor='w',padx=20,pady=8);ttk.Label(w,text='Minimum readable tile size').pack(anchor='w',padx=20);tk.Scale(w,from_=22,to=90,variable=self.min_tile,orient='horizontal',bg=PANEL,fg=TEXT,highlightthickness=0).pack(fill='x',padx=20);ttk.Label(w,text='Tip: zoom the window larger to reveal more labels. Right-click a tile to trade or open its chart/options.',wraplength=380).pack(anchor='w',padx=20,pady=15)
    def _split(self,items,x,y,w,h,vertical=False):
        if not items:return []
        total=sum(max(1,a.market_cap) if self.mode.get()=='Market Cap' else 1 for a in items);out=[];cur=x
        for i,a in enumerate(items):
            weight=(max(1,a.market_cap) if self.mode.get()=='Market Cap' else 1)/total;ww=w*weight if not vertical else w;hh=h*weight if vertical else h
            if vertical: rect=(x,y,w,hh);y+=hh
            else: rect=(cur,y,ww,h);cur+=ww
            out.append((a,rect))
        return out
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');self.rects=[];w=max(900,c.winfo_width());h=max(650,c.winfo_height());pad=8;W=w-2*pad;H=h-2*pad
        assets=[a for a in self.market.stocks if self.sec.get()=='ALL' or a.category==self.sec.get()]
        groups={}
        for a in assets:groups.setdefault(a.category,[]).append(a)
        groups={k:sorted(v,key=lambda a:a.market_cap,reverse=True) for k,v in groups.items()}
        ordered=sorted(groups.items(),key=lambda kv:sum(max(1,a.market_cap) for a in kv[1]),reverse=True)
        total=sum(sum(max(1,a.market_cap) for a in v) for _,v in ordered) or 1
        # Give each sector area proportional to its total market cap, then pack sectors in rows.
        nsec=len(ordered);sector_cols=max(1,min(4,math.ceil(math.sqrt(nsec))))
        row_count=math.ceil(nsec/sector_cols);row_h=H/row_count
        for si,(sector,arr) in enumerate(ordered):
            col=si%sector_cols;row=si//sector_cols;cell_w=W/sector_cols;x0=pad+col*cell_w;y0=pad+row*row_h
            sector_total=sum(max(1,a.market_cap) for a in arr);sector_share=sector_total/total
            # Within the sector, use a recursive alternating split so tile AREA follows market cap.
            inner=(x0+3,y0+27,x0+cell_w-3,y0+row_h-3);ix,iy,ix2,iy2=inner;iw=max(1,ix2-ix);ih=max(1,iy2-iy)
            c.create_rectangle(x0,y0,x0+cell_w,y0+row_h,fill='#0b1420',outline='#31465b',width=2);c.create_text(x0+7,y0+6,anchor='nw',text=f'{sector} • {len(arr)}',fill=TEXT,font=('Arial',10,'bold'))
            items=sorted(arr,key=lambda a:max(1,a.market_cap),reverse=True)
            rects=[(items,ix,iy,iw,ih)];sector_rects=[]
            while rects:
                group,x,y,ww,hh=rects.pop()
                if not group:continue
                if len(group)==1:
                    a=group[0];sector_rects.append((x,y,x+ww,y+hh,a));continue
                vals=[max(1,a.market_cap) for a in group];cut=max(1,int(len(group)/2));a1=group[:cut];a2=group[cut:];s1=sum(max(1,a.market_cap) for a in a1);ratio=s1/(s1+sum(max(1,a.market_cap) for a in a2))
                if ww>=hh:
                    w1=ww*ratio;rects.append((a2,x+w1,y,ww-w1,hh));rects.append((a1,x,y,w1,hh))
                else:
                    h1=hh*ratio;rects.append((a2,x,y+h1,ww,hh-h1));rects.append((a1,x,y,ww,h1))
            for x,y,xx,yy,a in sector_rects:
                self.rects.append((x,y,xx,yy,a))
                chg=a.change_percent();fill='#0f8f65' if chg>=0 else '#b33b54';c.create_rectangle(x+1,y+1,xx-1,yy-1,fill=fill,outline='#071017');cw=xx-x;ch=yy-y
                if cw>=self.min_tile.get() and ch>=22:
                    fs=max(7,min(14,int(min(cw/8.5,ch/3.0))));txt=f'{a.symbol}\n{chg:+.2f}%' if self.detail.get() else a.symbol;c.create_text((x+xx)/2,(y+yy)/2,text=txt,fill='white',font=('Arial',fs,'bold'),justify='center')
        c.create_text(pad+8,pad+8,anchor='nw',text='MARKET MAP • TILE AREA = MARKET CAP • COLOR = DAILY CHANGE • RIGHT-CLICK = TRADE / CHART / OPTIONS',fill=TEXT,font=('Arial',10,'bold'))
        self.after(900,self.draw)
    def _asset_at(self,e):
        for x1,y1,x2,y2,a in reversed(self.rects):
            if x1<=e.x<=x2 and y1<=e.y<=y2:return a
    def click(self,e):
        a=self._asset_at(e)
        if a:self.market.ui_app.load_asset_auto(a);self.market.ui_app.status_flash(f'{a.symbol} selected from market map')
    def context(self,e):
        a=self._asset_at(e)
        if not a:return
        m=tk.Menu(self.cv,tearoff=0);m.add_command(label=f'BUY {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SELL','MARKET',None));m.add_command(label=f'SHORT {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SHORT','MARKET',None));m.add_command(label='OPEN OPTIONS',command=lambda:self.market.ui_app.options_for(a));m.add_command(label='ADVANCED CHART',command=lambda:self.market.ui_app.load_asset_auto(a));m.add_command(label='LEVEL 2 / 3',command=lambda:self.market.ui_app.depth_for(a));m.tk_popup(e.x_root,e.y_root)

class GlobeWindow(ToolWindow):
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('GLOBAL TRADER — LIVE EARTH & EXCHANGE NETWORK','1500x930');self.cv=tk.Canvas(self,bg='#02060b',highlightthickness=0);self.cv.pack(fill='both',expand=True);self.cv.bind('<Button-1>',self.click);self.after(100,self.draw)
    def project(self,lon,lat,cx,cy,r,rot):
        # simple orthographic globe projection; land polygons are approximate visual training geometry.
        lonr=math.radians(lon)+rot;latr=math.radians(lat);x=math.cos(latr)*math.sin(lonr);y=math.sin(latr);z=math.cos(latr)*math.cos(lonr);return (cx+r*x,cy-r*y,z)
    def draw_land(self,c,cx,cy,r,rot):
        land=[ [(-168,72),(-145,70),(-125,60),(-110,50),(-98,40),(-90,28),(-82,25),(-78,38),(-65,48),(-55,58),(-75,75),(-120,82)], [(-82,15),(-70,5),(-65,-8),(-60,-20),(-52,-35),(-58,-52),(-72,-55),(-78,-30)], [(-10,36),(5,43),(20,42),(35,35),(50,20),(42,8),(20,0),(5,8)], [(-18,35),(-5,32),(12,25),(28,10),(38,-5),(45,-20),(34,-35),(15,-30),(-2,-10)], [(30,70),(55,72),(80,70),(105,62),(135,58),(160,52),(175,42),(160,30),(140,22),(120,10),(95,15),(70,28),(45,42)], [(40,35),(65,25),(85,20),(105,8),(120,0),(135,5),(150,20),(170,25)], [(110,-10),(130,-12),(150,-18),(155,-35),(135,-40),(118,-32)] ]
        for poly in land:
            pts=[];visible=True
            for lon,lat in poly:
                x,y,z=self.project(lon,lat,cx,cy,r,rot)
                if z>-.05:pts.extend([x,y])
            if len(pts)>=6:c.create_polygon(*pts,fill='#2b7650',outline='#75b88c')
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(900,self.cv.winfo_width());h=max(650,self.cv.winfo_height());r=min(h*.39,w*.28);cx=w*.34;cy=h*.51;utc=self.market.clock.current;rot=2*math.pi*((utc.hour*60+utc.minute)/1440)-math.pi/2
        # day/night shading with layered globe rim
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#071827',outline='#2c8ac2',width=4);self.draw_land(c,cx,cy,r,rot);c.create_oval(cx-r,cy-r,cx+r,cy+r,outline='#6fd4ff',width=1)
        # Subtle geographic graticule, clipped visually by the globe circle.
        for lat in (-60,-30,0,30,60):
            pts=[]
            for lon in range(-180,181,10):
                x,y,z=self.project(lon,lat,cx,cy,r,rot)
                if z>0:pts.extend([x,y])
            if len(pts)>=4:c.create_line(*pts,fill='#173b4d',width=1)
        positions={'US':(-74,40),'LSE':(-0.1,51.5),'XETRA':(8.7,50.1),'TSE':(139.7,35.7),'HKEX':(114.2,22.3),'SSE':(121.5,31.2),'ASX':(151.2,-33.9),'CME':(-87.6,41.9),'FX':(0,0),'CRYPTO':(0,25)};self.blips=[]
        for code,(lon,lat) in positions.items():
            x,y,z=self.project(lon,lat,cx,cy,r,rot)
            if z<0:continue
            op=market_status(code,self.market.clock.current);col=GREEN if op else '#3c4b5c';c.create_oval(x-8,y-8,x+8,y+8,fill=col,outline=TEXT,width=1);c.create_text(x+12,y,text=SESSIONS[code].name,fill=TEXT,anchor='w',font=('Arial',9,'bold'));self.blips.append((x-12,y-12,x+12,y+12,code))
        # shipping routes / vessels are driven by commodity-market momentum, not decorative sine waves.
        ship_speed=sum(abs(a.change_percent()) for a in self.market.commodities)/max(1,len(self.market.commodities));phase=(self.market.clock.current.timestamp()/900)*(1+ship_speed/10)
        routes=[((-70,20),(10,30)),((10,30),(80,30)),((80,30),(145,10)),((-30,-20),(120,-30))]
        for rid,(a,b) in enumerate(routes):
            p1=self.project(*a,cx,cy,r,rot);p2=self.project(*b,cx,cy,r,rot)
            if p1[2]>.1 and p2[2]>.1:
                c.create_line(p1[0],p1[1],p2[0],p2[1],fill='#31586c',dash=(4,6),width=1)
                t=(phase*.02+rid*.23)%1; sx=p1[0]+(p2[0]-p1[0])*t;sy=p1[1]+(p2[1]-p1[1])*t;c.create_polygon(sx,sy,sx-10,sy+4,sx-6,sy-6,fill='#e6b65c',outline='')
        c.create_text(w*.62,35,text='GLOBAL TRADER NETWORK',fill=TEXT,font=('Arial',19,'bold'),anchor='w');c.create_text(w*.62,68,text=f'IN-GAME CLOCK  {self.market.clock.time} • UTC {self.market.clock.utc_time}',fill=CYAN,font=('Arial',12,'bold'),anchor='w');y=108
        for code,sess in SESSIONS.items():
            op=market_status(code,self.market.clock.current);c.create_text(w*.62,y,text=f'{sess.name:<22}  {"OPEN" if op else "CLOSED"}',fill=GREEN if op else MUTED,font=('Arial',10,'bold'),anchor='w');y+=22
        c.create_text(w*.62, y+10,text='Click a visible exchange node to trade its market. Ships visualize modeled commodity/logistics flow.',fill=MUTED,anchor='w',font=('Arial',10));self.after(250,self.draw)
    def click(self,e):
        for x1,y1,x2,y2,code in getattr(self,'blips',[]):
            if x1<=e.x<=x2 and y1<=e.y<=y2:GlobalMarketWindow(self,self.market,code);return

class GlobalMarketWindow(ToolWindow):
    def __init__(self,parent,market,code):
        super().__init__(parent);self.market=market;self.code=code;self.style_window(f'GLOBAL MARKET — {SESSIONS[code].name}','1100x720');ttk.Label(self,text=f'{SESSIONS[code].name} • {"OPEN" if market_status(code,market.clock.current) else "CLOSED"}',font=('Arial',15,'bold')).pack(anchor='w',padx=12,pady=10);self.tv=ttk.Treeview(self,columns=('symbol','name','price','chg','status'),show='headings');
        for c in self.tv['columns']:self.tv.heading(c,text=c.upper());self.tv.column(c,width=180 if c=='name' else 120)
        self.tv.pack(fill='both',expand=True,padx=10,pady=10);self.tv.bind('<Double-1>',self.trade);bar=ttk.Frame(self);bar.pack(fill='x',padx=10,pady=6);ttk.Button(bar,text='OPEN SELECTED IN MARKET FEED',command=self.open_feed).pack(side='left');ttk.Button(bar,text='OPTIONS',command=self.open_options).pack(side='left',padx=6);ttk.Button(bar,text='ADVANCED CHART',command=self.open_chart).pack(side='left');self.after(200,self.refresh)
    def refresh(self):
        if not self.winfo_exists():return
        self.tv.delete(*self.tv.get_children());assets=[a for a in self.market.all_assets() if getattr(a,'session','US')==self.code]
        if self.code=='US':assets=self.market.stocks
        if self.code=='CME':assets=self.market.futures
        if self.code=='FX':assets=self.market.forex
        if self.code=='CRYPTO':assets=self.market.crypto
        for a in assets:self.tv.insert('','end',iid=a.symbol,values=(a.symbol,a.name,f'${a.price:,.2f}',f'{a.change_percent():+.2f}%', 'OPEN' if market_status(self.code,self.market.clock.current) else 'CLOSED'))
        self.after(600,self.refresh)
    def open_feed(self):
        it=self.tv.selection()
        if it:
            a=self.market.get_asset(it[0]);self.market.ui_app.load_asset_auto(a);self.market.ui_app.refresh_watch();self.market.ui_app.status_flash(f'{a.symbol} loaded from {self.code} into market feed')
    def open_options(self):
        it=self.tv.selection()
        if it:self.market.ui_app.options_for(self.market.get_asset(it[0]))
    def open_chart(self):
        it=self.tv.selection()
        if it:self.market.ui_app.advanced_chart(self.market.get_asset(it[0]))
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
    """Multi-hand blackjack training table with persistent cards and count education."""
    DEALERS=[('Aiko','#ffd6e7'),('Mina','#ffe4c4'),('Yuna','#d7e8ff'),('Rei','#e7d7ff'),('Sora','#d7ffe8'),('Emi','#ffe7d0')]
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('BLACKJACK TRAINER — CARD COUNTING LAB','1280x820')
        self.deck_count=tk.IntVar(value=6);self.count_mode=tk.StringVar(value='Hi-Lo');self.bet=tk.IntVar(value=100);self.hand_count=tk.IntVar(value=1);self.running=0;self.shoe=[];self.hands=[];self.dealer=[];self.active=False;self.bet_amounts=[];self.dealer_name=random.choice(self.DEALERS)[0];self.history=[];self.active_hand=0;self.split_used=set()
        top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8)
        for label,var,vals in [('Decks',self.deck_count,[1,2,6]),('Count',self.count_mode,['None','Hi-Lo','KO']),('Hands',self.hand_count,[1,2,3,4,5])]:
            ttk.Label(top,text=label).pack(side='left',padx=(5,2));ttk.Combobox(top,textvariable=var,values=vals,state='readonly',width=8).pack(side='left',padx=3)
        ttk.Label(top,text='Bet / hand').pack(side='left',padx=(14,2));ttk.Entry(top,textvariable=self.bet,width=10).pack(side='left')
        for chips in (25,100,500,1000,5000,10000):ttk.Button(top,text=f'${chips:,}',command=lambda x=chips:self.bet.set(x),width=7).pack(side='left',padx=2)
        ttk.Button(top,text='NEW SHOE',command=self.new_shoe).pack(side='left',padx=8);ttk.Button(top,text='COUNTING HELP',command=self.help).pack(side='left')
        self.canvas=tk.Canvas(self,bg='#064b32',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=10,pady=8)
        bar=ttk.Frame(self);bar.pack(fill='x',padx=10,pady=5);ttk.Button(bar,text='DEAL',command=self.deal).pack(side='left');ttk.Button(bar,text='HIT',command=self.hit).pack(side='left',padx=5);ttk.Button(bar,text='DOUBLE',command=self.double).pack(side='left');ttk.Button(bar,text='SPLIT PAIR',command=self.split_pair).pack(side='left',padx=5);ttk.Button(bar,text='STAND',command=self.stand).pack(side='left',padx=5);self.info=ttk.Label(bar,text='');self.info.pack(side='right')
        self.new_shoe()
    def help(self):
        messagebox.showinfo('Card-counting trainer','Hi-Lo: 2–6 = +1, 7–9 = 0, 10/J/Q/K/A = -1.\nTrue count = running count / estimated decks remaining.\nKO removes the true-count conversion. Use this as a training aid, not a guarantee of advantage.')
    def new_shoe(self):
        import random as r
        suits=['♠','♥','♦','♣'];ranks=list(range(1,14));self.shoe=[(rank,s) for _ in range(self.deck_count.get()) for s in suits for rank in ranks];r.shuffle(self.shoe);self.running=0;self.active=False;self.hands=[];self.dealer=[];self.history=[];self.draw_table()
    def card(self):
        import random as r
        if len(self.shoe)<max(10,int(52*self.deck_count.get()*.18)):self.new_shoe()
        card=self.shoe.pop();rank,s=card;v=1 if rank==1 else min(10,rank)
        if self.count_mode.get()=='Hi-Lo':self.running += 1 if 2<=v<=6 else -1 if v==10 else 0
        elif self.count_mode.get()=='KO':self.running += 1 if 2<=v<=7 else -1 if v in (10,1) else 0
        return card
    def val(self,h):
        total=sum(1 if r==1 else min(10,r) for r,s in h);aces=sum(r==1 for r,s in h)
        while aces and total+10<=21:total+=10;aces-=1
        return total
    def deal(self):
        try:b=int(self.bet.get());n=int(self.hand_count.get())
        except:return
        if b<=0 or n<1 or b*n>self.portfolio.cash:return messagebox.showerror('Blackjack','Invalid bet or insufficient cash.')
        self.portfolio.cash-=b*n;self.bet_amounts=[b]*n;self.hands=[[self.card(),self.card()] for _ in range(n)];self.dealer=[self.card(),self.card()];self.active=True;self.active_hand=0;self.split_used=set();self.draw_table()
    def hit(self):
        if not self.active or self.active_hand>=len(self.hands):return
        h=self.hands[self.active_hand]
        if self.val(h)<21:h.append(self.card())
        if self.val(h)>=21 and self.active_hand<len(self.hands)-1:self.active_hand+=1
        self.draw_table()
    def split_pair(self):
        if not self.active or self.active_hand>=len(self.hands) or self.active_hand in self.split_used:return
        h=self.hands[self.active_hand]
        if len(h)!=2 or h[0][0]!=h[1][0]:return
        b=self.bet_amounts[self.active_hand]
        if self.portfolio.cash<b:return messagebox.showerror('Blackjack','Insufficient cash to split.')
        self.portfolio.cash-=b;card=h.pop();new=[card,self.card()];h.append(self.card());self.hands.insert(self.active_hand+1,new);self.bet_amounts.insert(self.active_hand+1,b);self.split_used.add(self.active_hand);self.draw_table()
    def double(self):
        if not self.active:return
        if self.active_hand>=len(self.hands):return
        i=self.active_hand;h=self.hands[i]
        if len(h)==2 and self.portfolio.cash>=self.bet_amounts[i]:self.portfolio.cash-=self.bet_amounts[i];self.bet_amounts[i]*=2;h.append(self.card());self.active_hand=min(self.active_hand+1,len(self.hands)-1)
        self.draw_table()
    def stand(self):
        if not self.active:return
        while self.val(self.dealer)<17:self.dealer.append(self.card())
        dv=self.val(self.dealer);payout=0
        for i,h in enumerate(self.hands):
            pv=self.val(h);b=self.bet_amounts[i]
            if pv>21:continue
            if dv>21 or pv>dv:payout+=b*2
            elif pv==dv:payout+=b
        self.portfolio.cash+=payout;self.history.append((self.dealer_name,self.running,len(self.shoe)));self.active=False;self.draw_table()
    def draw_card(self,c,x,y,hidden=False):
        r,s=c;w,h=78,108;self.canvas.create_rectangle(x,y,x+w,y+h,fill='#ffffff',outline='#d7e0ea',width=2)
        if hidden:self.canvas.create_text(x+w/2,y+h/2,text='?',fill='#23364a',font=('Arial',30,'bold'));return
        txt='A' if r==1 else 'J' if r==11 else 'Q' if r==12 else 'K' if r==13 else str(r);col='#d52e4d' if s in '♥♦' else '#111827';self.canvas.create_text(x+12,y+18,text=txt,fill=col,font=('Arial',15,'bold'));self.canvas.create_text(x+w/2,y+h/2+8,text=s,fill=col,font=('Arial',27,'bold'))
    def draw_table(self):
        c=self.canvas;c.delete('all');w=max(1000,c.winfo_width());h=max(550,c.winfo_height());c.create_text(w/2,25,text=f'BLACKJACK • {self.dealer_name} DEALER',fill='#f6e6b5',font=('Arial',20,'bold'))
        c.create_text(30,65,anchor='w',text='DEALER',fill='#cfe9dc',font=('Arial',11,'bold'));x=150
        for i,card in enumerate(self.dealer):self.draw_card(card,x+i*90,80,hidden=self.active and i==1)
        base=h/2+10
        cols=max(1,min(4,len(self.hands)));gap=w/(cols+1);base=h*.48
        for j,hnd in enumerate(self.hands):
            col=j%cols;row=j//cols;x0=gap*(col+1)-90;y=base+row*170;c.create_text(x0,y-18,anchor='w',text=f'HAND {j+1}  ${self.bet_amounts[j] if j<len(self.bet_amounts) else 0:,}',fill='#cfe9dc',font=('Arial',11,'bold'))
            for i,card in enumerate(hnd):self.draw_card(card,x0+i*82,y)
            c.create_text(x0+300,y+45,text=f'{self.val(hnd)}',fill='#f6e6b5',font=('Arial',22,'bold'))
        c.create_text(30,h-24,anchor='w',text=f'ACTIVE HAND {self.active_hand+1 if self.hands else 0} • SPLIT PAIRS ENABLED',fill='#b9d6c7',font=('Arial',10,'bold'))
        decks=max(.01,len(self.shoe)/52);true=self.running/decks if self.count_mode.get()=='Hi-Lo' else self.running;edge='—' if self.count_mode.get()=='None' else f'{true:+.2f}'
        self.info.config(text=f'Balance ${self.portfolio.cash:,.2f} • Running {self.running:+d} • True {edge} • Decks left {decks:.2f} • Cards in shoe {len(self.shoe)}')

class CasinoWindow(ToolWindow):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('ARCADE — 24/7 TRADING BREAK','1100x720');self.dealer=random.choice(BlackjackWindow.DEALERS);ttk.Label(self,text='24/7 VIRTUAL ARCADE • independent of market session',font=('Arial',15,'bold')).pack(pady=15);f=ttk.Frame(self);f.pack(fill='x',padx=20);ttk.Button(f,text='BLACKJACK TRAINER',command=lambda:BlackjackWindow(self,portfolio,market)).pack(side='left',padx=15,pady=15);ttk.Button(f,text='ROULETTE',command=lambda:RouletteWindow(self,portfolio,market)).pack(side='left',padx=15,pady=15);ttk.Label(self,text='Virtual simulator credits only.').pack(pady=10)

class RouletteWindow(ToolWindow):
    REDS={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('ROULETTE — FULL TABLE','1650x980');self.resizable(True,True);self.chips=[25,100,500,1000,5000,10000];self.chip=tk.IntVar(value=100);self.bets={};self.history=[];self.spinning=False;self.dealer=random.choice(BlackjackWindow.DEALERS)[0];self.target=0;self.anim=0
        top=ttk.Frame(self);top.pack(fill='x',padx=12,pady=7);ttk.Label(top,text=f'DEALER: {self.dealer}  •  Balance').pack(side='left');self.balance=ttk.Label(top,text='');self.balance.pack(side='left',padx=6)
        for v in self.chips:ttk.Button(top,text=f'${v:,}',command=lambda x=v:self.chip.set(x),width=7).pack(side='left',padx=2)
        ttk.Button(top,text='CLEAR BETS',command=self.clear_bets).pack(side='right');ttk.Button(top,text='SPIN',command=self.spin).pack(side='right',padx=6)
        self.cv=tk.Canvas(self,bg='#0a1118',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=10,pady=6);self.result=ttk.Label(self,text='Click a number, edge, corner, split, street, dozen, column, or outside bet.');self.result.pack(fill='x',padx=10,pady=5);self.cv.bind('<Button-1>',self.board_click);self.after(100,self.draw)
    def add_bet(self,key):self.bets[key]=self.bets.get(key,0)+self.chip.get();self.draw()
    def clear_bets(self):self.bets.clear();self.draw()
    def board_click(self,e):
        w=max(1100,self.cv.winfo_width());h=max(700,self.cv.winfo_height());bx=w*.42;by=h*.39;cw=min(82,(w*.48)/12);ch=max(48,min(64,h*.075));zero_w=cw*.72
        if bx-zero_w<=e.x<=bx and by<=e.y<=by+ch*3:self.add_bet(0);return
        # numbers: 12 columns, rows 1/2/3. Boundaries create split/corner bets.
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch
            if x<=e.x<=x+cw and y<=e.y<=y+ch:
                edge=7
                near_left=abs(e.x-x)<edge;near_right=abs(e.x-(x+cw))<edge;near_top=abs(e.y-y)<edge;near_bottom=abs(e.y-(y+ch))<edge
                if near_right and col<11:
                    other=n+3;self.add_bet(tuple(sorted((n,other))))
                elif near_left and col>0:
                    other=n-3;self.add_bet(tuple(sorted((n,other))))
                elif near_bottom and row<2:
                    other=n+1;self.add_bet(tuple(sorted((n,other))))
                elif near_top and row>0:
                    other=n-1;self.add_bet(tuple(sorted((n,other))))
                else:self.add_bet(n)
                return
        # column 2:1 squares at end
        for row,key in enumerate(('2:1_ROW1','2:1_ROW2','2:1_ROW3')):
            x=bx+12*cw;y=by+row*ch
            if x<=e.x<=x+cw*.85 and y<=e.y<=y+ch:self.add_bet(key);return
        # dozens below
        oy=by+3*ch+12;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw
            if x<=e.x<=x+rw and oy<=e.y<=oy+ch*.9:self.add_bet(key);return
        # outside bets
        oy2=oy+ch+10;labels=('1-18','EVEN','RED','BLACK','ODD','19-36');rw=(cw*12)/6
        for i,key in enumerate(labels):
            x=bx+i*rw
            if x<=e.x<=x+rw and oy2<=e.y<=oy2+ch*.9:self.add_bet(key);return
    def win_for(self,key,n):
        if isinstance(key,int):return n==key,35
        if isinstance(key,tuple):return n in key,17 if len(key)==2 else 8
        if key=='RED':return n in self.REDS,1
        if key=='BLACK':return n>0 and n not in self.REDS,1
        if key=='ODD':return n>0 and n%2==1,1
        if key=='EVEN':return n>0 and n%2==0,1
        if key=='1-18':return 1<=n<=18,1
        if key=='19-36':return 19<=n<=36,1
        if key=='1-12':return 1<=n<=12,2
        if key=='13-24':return 13<=n<=24,2
        if key=='25-36':return 25<=n<=36,2
        if key=='2:1_ROW1':return n>0 and (n-1)%3==0,2
        if key=='2:1_ROW2':return n>0 and (n-1)%3==1,2
        if key=='2:1_ROW3':return n>0 and (n-1)%3==2,2
        return False,0
    def spin(self):
        if self.spinning or not self.bets:return
        total=sum(self.bets.values())
        if total>self.portfolio.cash:return messagebox.showerror('Roulette','Insufficient balance for selected chips.')
        self.portfolio.cash-=total;self.spinning=True;self.target=random.randint(0,36);self.anim=0;self._spin_step()
    def _spin_step(self):
        steps=72
        if self.anim<steps:
            self.draw(wheel_number=random.randint(0,36),ball_phase=self.anim/steps,spinning=True);self.anim+=1;self.after(28+int(self.anim*.7),self._spin_step);return
        target=self.target;payout=0;wins=[]
        for key,amt in self.bets.items():
            win,m=self.win_for(key,target)
            if win:payout+=amt*(m+1);wins.append(key)
        self.portfolio.cash+=payout;self.history.append(target);self.history=self.history[-500:];self.bets.clear();self.spinning=False;self.result.config(text=f'BALL LANDED ON {target} • {"WIN" if wins else "LOSS"} • Payout ${payout:,.0f}');self.draw(target,0,False)
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        c=self.cv;c.delete('all');w=max(1100,c.winfo_width());h=max(700,c.winfo_height());cx=w*.18;cy=h*.44;r=min(h*.34,w*.18);c.create_text(cx,30,text=f'{self.dealer} • ROULETTE',fill='#f6e6b5',font=('Arial',21,'bold'))
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#0d2519',outline='#d8b96a',width=6);c.create_oval(cx-r*.82,cy-r*.82,cx+r*.82,cy+r*.82,fill='#161d23',outline='#8b6d35',width=3)
        for i,n in enumerate(range(37)):
            a=2*math.pi*i/37-math.pi/2;col='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#171b20';x=cx+math.cos(a)*r*.70;y=cy+math.sin(a)*r*.70;rr=15;c.create_oval(x-rr,y-rr,x+rr,y+rr,fill=col,outline='#d6c08a');c.create_text(x,y,text=str(n),fill='white',font=('Arial',9,'bold'))
        c.create_oval(cx-r*.16,cy-r*.16,cx+r*.16,cy+r*.16,fill='#0b1218',outline='#d8b96a',width=2);c.create_text(cx,cy,text=str(wheel_number) if wheel_number is not None else '0',fill='white',font=('Arial',25,'bold'))
        if wheel_number is not None:
            a=2*math.pi*(wheel_number%37)/37-math.pi/2 + ball_phase*math.pi*12;bx=cx+math.cos(a)*(r*.88);by=cy+math.sin(a)*(r*.88);c.create_oval(bx-8,by-8,bx+8,by+8,fill='white',outline='#cfd8df',width=2)
        # table
        bx=w*.40;by=h*.22;cw=min(88,(w*.50)/12);ch=max(52,min(70,h*.075));c.create_rectangle(bx-cw*.72,by,bx,by+ch*3,fill='#13865c',outline='#d8b96a',width=2);c.create_text(bx-cw*.36,by+ch*1.5,text='0',fill='white',font=('Arial',17,'bold'))
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch;fill='#b92f48' if n in self.REDS else '#151b23';c.create_rectangle(x,y,x+cw,y+ch,fill=fill,outline='#d8b96a');self._chip(c,x+cw/2,y+ch/2,self.bets.get(n,0),str(n))
        for row,key in enumerate(('2:1_ROW1','2:1_ROW2','2:1_ROW3')):
            x=bx+12*cw;y=by+row*ch;c.create_rectangle(x,y,x+cw*.85,y+ch,fill='#0e6950',outline='#d8b96a');self._chip(c,x+cw*.42,y+ch/2,self.bets.get(key,0),'2:1')
        oy=by+3*ch+14;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw;c.create_rectangle(x,oy,x+rw,oy+ch*.9,fill='#0e6950',outline='#d8b96a');self._chip(c,x+rw/2,oy+ch*.45,self.bets.get(key,0),key)
        oy2=oy+ch+10;rw=(cw*12)/6
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            x=bx+i*rw;fill='#b92f48' if key=='RED' else '#151b23' if key=='BLACK' else '#0e6950';c.create_rectangle(x,oy2,x+rw,oy2+ch*.9,fill=fill,outline='#d8b96a');self._chip(c,x+rw/2,oy2+ch*.45,self.bets.get(key,0),key)
        hx=w*.82;c.create_text(hx,by-18,text='LAST 500 SPINS',fill='#f6e6b5',font=('Arial',14,'bold'));hist=self.history[-500:];cols=5
        for i,n in enumerate(reversed(hist)):
            row=i//cols;col=i%cols;x=hx-2*70+col*70;y=by+row*26;fill='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#151b23';c.create_oval(x-13,y-13,x+13,y+13,fill=fill,outline='#d8b96a');c.create_text(x,y,text=str(n),fill='white',font=('Arial',8,'bold'))
        c.create_text(hx,by+min(500//5,18)*26+20,text='Bets use selected chip value. Click near an edge to place split bets.',fill=MUTED,font=('Arial',9),width=w*.28)
        self.balance.config(text=f'${self.portfolio.cash:,.2f}')
    def _chip(self,c,x,y,amt,label):
        if not amt:return
        c.create_oval(x-15,y-15,x+15,y+15,fill='#d8b96a',outline='#fff2c2',width=2);c.create_text(x,y,text=f'${amt:,}',fill='#111820',font=('Arial',7,'bold'))

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
        self.root=root;self.market=market;self.portfolio=portfolio;self.market.ui_app=self;self.active_chart=0;self.selected_chart=None;self.ind_vars={k:tk.BooleanVar(value=k in ('Volume',)) for k in ('SMA','EMA','BB','VWAP','RSI','Volume')};self.ind_vars_version=0;self.sort_key='Symbol';self.sort_reverse=False;self.build_style();self.make_menu();self.build();self.set_chart_count(initial=8);self.refresh()
    def build_style(self):
        s=ttk.Style();s.theme_use('clam');s.configure('.',background=PANEL,foreground=TEXT);s.configure('TFrame',background=PANEL);s.configure('TLabel',background=PANEL,foreground=TEXT);s.configure('TButton',background=PANEL2,foreground=TEXT,padding=6);s.map('TButton',background=[('active',BLUE)],foreground=[('active','white')]);s.configure('TEntry',fieldbackground='#f4f7fb',foreground='#111827',insertcolor='#111827');s.configure('TCombobox',fieldbackground='#f4f7fb',foreground='#111827',background='#f4f7fb',arrowcolor='#111827');s.map('TCombobox',fieldbackground=[('readonly','#f4f7fb')],foreground=[('readonly','#111827')]);s.configure('Treeview',background='#0c151f',fieldbackground='#0c151f',foreground=TEXT,rowheight=24);s.configure('Treeview.Heading',background='#1e3041',foreground=TEXT);s.map('Treeview',background=[('selected','#1c5f8f')],foreground=[('selected','#ffffff')])
    def make_menu(self):
        mb=tk.Menu(self.root,tearoff=0,bg='#172331',fg=TEXT,activebackground='#2c6da0',activeforeground='white');self.root.config(menu=mb)
        v=tk.Menu(mb,tearoff=0);v.add_command(label='Market Map',command=self.market_map);v.add_command(label='Global Trader Globe',command=self.globe);v.add_command(label='Options Chain',command=self.options);v.add_command(label='Level 2 / Level 3',command=self.depth);v.add_command(label='Market Screener',command=lambda:MarketListWindow(self.root,self.market));v.add_command(label='After-Hours Arcade',command=self.casino);mb.add_cascade(label='View',menu=v)
        tr=tk.Menu(mb,tearoff=0);tr.add_command(label='Order Entry',command=self.order_window);tr.add_command(label='Smart Large-Lot Order',command=self.smart_order);tr.add_command(label='Liquidate Selected',command=self.liquidate);tr.add_command(label='Load MAX / IPO History',command=self.load_max_selected);tr.add_command(label='Market Event Lab',command=self.market_event_lab);mb.add_cascade(label='Tools',menu=tr)
        ind=tk.Menu(mb,tearoff=0);[ind.add_checkbutton(label=k,variable=v,command=self.redraw) for k,v in self.ind_vars.items()];mb.add_cascade(label='Indicators',menu=ind)
        ws=tk.Menu(mb,tearoff=0);ws.add_command(label='Workspace Variables / Sliders',command=self.workspace_controls);ws.add_command(label='Add Chart',command=self.add_chart);ws.add_command(label='Remove Active Chart',command=lambda:self.remove_chart(self.active_chart));ws.add_command(label='4 Charts',command=lambda:self.set_chart_count(initial=4));ws.add_command(label='6 Charts',command=lambda:self.set_chart_count(initial=6));ws.add_command(label='8 Charts',command=lambda:self.set_chart_count(initial=8));mb.add_cascade(label='Workspace',menu=ws)
        ch=tk.Menu(mb,tearoff=0);ch.add_command(label='Crosshair',command=lambda:self.set_tool('Crosshair'));ch.add_command(label='Trendline',command=lambda:self.set_tool('Trendline'));ch.add_command(label='Horizontal Line',command=lambda:self.set_tool('Horizontal'));ch.add_command(label='Clear Drawings',command=self.clear_drawings);mb.add_cascade(label='Chart Tools',menu=ch)
        tm=tk.Menu(mb,tearoff=0);tm.add_command(label='Slow Down',command=lambda:self.change_speed(1.5));tm.add_command(label='Normal Speed',command=lambda:self.set_speed(.08));tm.add_command(label='Fast Forward',command=lambda:self.change_speed(.45));tm.add_command(label='Ultra Fast',command=lambda:self.change_speed(2.0));tm.add_command(label='Pause / Resume',command=self.toggle_pause);mb.add_cascade(label='Time',menu=tm)
        ac=tk.Menu(mb,tearoff=0);ac.add_command(label='Account / Difficulty',command=self.account_panel);ac.add_command(label='Session Statistics',command=self.session_stats);mb.add_cascade(label='Account',menu=ac)
    def build(self):
        self.starting_cash=self.portfolio.cash;self.root.title('STOCK_GAME PRO — GLOBAL TRADING SIMULATOR v1');self.root.geometry('1900x1100');outer=ttk.PanedWindow(self.root,orient='horizontal');outer.pack(fill='both',expand=True);left=ttk.Frame(outer,width=340);center=ttk.Frame(outer);right=ttk.Frame(outer,width=460);outer.add(left,weight=2);outer.add(center,weight=6);outer.add(right,weight=3)
        ttk.Label(left,text='MARKET / WATCHLIST',font=('Arial',12,'bold')).pack(anchor='w',padx=7,pady=5);sf=ttk.Frame(left);sf.pack(fill='x',padx=7);self.search=tk.StringVar();e=ttk.Entry(sf,textvariable=self.search);e.pack(fill='x');e.bind('<KeyRelease>',lambda x:self.refresh_watch());ff=ttk.Frame(left);ff.pack(fill='x',padx=7,pady=4);self.kind=tk.StringVar(value='STOCK');ttk.Combobox(ff,textvariable=self.kind,values=['STOCK','INDEX','COMMODITY','FUTURES','CRYPTO','INTERNATIONAL','FOREX','ALL'],state='readonly',width=12).pack(side='left');self.sector=tk.StringVar(value='ALL');ttk.Combobox(ff,textvariable=self.sector,values=['ALL']+self.market.sectors,state='readonly',width=14).pack(side='right');self.watch=ttk.Treeview(left,columns=('symbol','name','price','chg','sector'),show='headings',selectmode='browse');
        for c,l in zip(self.watch['columns'],['Symbol','Name','Price','Chg %','Sector']):self.watch.heading(c,text=l,command=lambda col=c:self.sort_watch(col));self.watch.column(c,width=78 if c!='name' else 130,anchor='center')
        self.watch.pack(fill='both',expand=True,padx=7,pady=5);self.watch.bind('<<TreeviewSelect>>',self.market_selected);self.watch.bind('<Double-1>',lambda e:self.load_active());self.watch.bind('<Button-3>',self.watch_context)
        ttk.Button(left,text='BUY / SELL / SHORT',command=self.order_window).pack(fill='x',padx=7,pady=3);ttk.Button(left,text='OPTIONS / SPREADS',command=self.options).pack(fill='x',padx=7,pady=3);ttk.Label(left,text='Click = chart • Right-click = trade/menu',foreground=MUTED).pack(fill='x',padx=7,pady=3);density=ttk.Frame(left);density.pack(fill='x',padx=7,pady=(0,4));ttk.Label(density,text='Watchlist density').pack(side='left');self.watch_density=tk.IntVar(value=24);tk.Scale(density,from_=18,to=34,variable=self.watch_density,orient='horizontal',showvalue=0,length=120,bg=PANEL,fg=TEXT,highlightthickness=0,command=lambda x:self.apply_watch_density()).pack(side='left',fill='x',expand=True);self.watch_density_label=ttk.Label(density,text='24px',width=5);self.watch_density_label.pack(side='right')
        top=ttk.Frame(center);top.pack(fill='x',padx=5,pady=4);self.active_label=ttk.Label(top,text='Chart 1');self.active_label.pack(side='left');self.tf=ttk.Combobox(top,values=['1D','1W','1M','3M','6M','1Y','5Y','MAX'],state='readonly',width=7);self.tf.set('1D');self.tf.pack(side='left',padx=5);self.tf.bind('<<ComboboxSelected>>',lambda e:self.charts[self.active_chart].set_tf(self.tf.get()));self.ctype=ttk.Combobox(top,values=['Candles','Line','Area'],state='readonly',width=9);self.ctype.set('Candles');self.ctype.pack(side='left');self.ctype.bind('<<ComboboxSelected>>',lambda e:self.set_type());ttk.Button(top,text='BUY',command=lambda:self.chart_trade('BUY')).pack(side='left',padx=3);ttk.Button(top,text='SELL',command=lambda:self.chart_trade('SELL')).pack(side='left',padx=3);ttk.Button(top,text='LIMIT',command=lambda:self.chart_trade('BUY','LIMIT')).pack(side='left',padx=3);ttk.Button(top,text='STOP',command=lambda:self.chart_trade('SELL','STOP')).pack(side='left',padx=3);ttk.Button(top,text='SLOW',command=lambda:self.change_speed(1.5)).pack(side='left',padx=10);ttk.Button(top,text='▶ FAST',command=lambda:self.change_speed(2)).pack(side='left',padx=3);self.clock_label=ttk.Label(top,text='',font=('Arial',10,'bold'));self.clock_label.pack(side='right')
        self.grid=ttk.PanedWindow(center,orient='horizontal');self.grid.pack(fill='both',expand=True,padx=5,pady=5);self.charts=[]
        ttk.Label(right,text='PORTFOLIO / ACCOUNT',font=('Arial',12,'bold')).pack(anchor='w',padx=7,pady=5);tabs=ttk.Notebook(right);tabs.pack(fill='both',expand=True,padx=5,pady=3)
        pos_tab=ttk.Frame(tabs);acct_tab=ttk.Frame(tabs);ord_tab=ttk.Frame(tabs);tabs.add(pos_tab,text='Positions');tabs.add(acct_tab,text='Account');tabs.add(ord_tab,text='Orders')
        pwrap=ttk.Frame(pos_tab);pwrap.pack(fill='both',expand=True);self.pos=ttk.Treeview(pwrap,columns=('symbol','qty','last','value','pnl','pct','type'),show='headings',height=16);px=ttk.Scrollbar(pwrap,orient='horizontal',command=self.pos.xview);py=ttk.Scrollbar(pwrap,orient='vertical',command=self.pos.yview);self.pos.configure(xscrollcommand=px.set,yscrollcommand=py.set);self.pos.grid(row=0,column=0,sticky='nsew');py.grid(row=0,column=1,sticky='ns');px.grid(row=1,column=0,sticky='ew');pwrap.rowconfigure(0,weight=1);pwrap.columnconfigure(0,weight=1)
        for c,l,w in [('symbol','Symbol',72),('qty','Qty',72),('last','Last',78),('value','Value',95),('pnl','P/L',90),('pct','P/L %',70),('type','Type',70)]:self.pos.heading(c,text=l);self.pos.column(c,width=w,anchor='e' if c not in ('symbol','type') else 'center',stretch=False)
        self.pos.bind('<<TreeviewSelect>>',lambda e:self.position_info());self.pos.bind('<Button-3>',self.position_context);ttk.Button(pos_tab,text='LIQUIDATE SELECTED / CASH',command=self.liquidate).pack(fill='x',padx=6,pady=5)
        self.pred=ttk.Label(acct_tab,text='MODEL',justify='left');self.pred.pack(fill='x',padx=8,pady=7);self.summary=tk.Text(acct_tab,height=18,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat',wrap='none');self.summary.pack(fill='both',expand=True,padx=6,pady=5)
        self.orders_view=ttk.Treeview(ord_tab,columns=('id','asset','side','type','qty','price','status'),show='headings');self.orders_view.pack(fill='both',expand=True,padx=6,pady=5);[self.orders_view.heading(c,text=c.upper()) for c in self.orders_view['columns']];[self.orders_view.column(c,width=80,stretch=False) for c in self.orders_view['columns']]
        action=ttk.Frame(right);action.pack(fill='x',pady=3);ttk.Button(action,text='ORDER ENTRY',command=self.order_window).pack(side='left',expand=True,fill='x',padx=2);ttk.Button(action,text='GLOBAL',command=self.globe).pack(side='left',expand=True,fill='x',padx=2);ttk.Button(action,text='MAP',command=self.market_map).pack(side='left',expand=True,fill='x',padx=2);ttk.Button(action,text='ARCADE',command=self.casino).pack(side='left',expand=True,fill='x',padx=2)
        newsf=ttk.Frame(self.root);newsf.pack(fill='x',padx=6,pady=4);nh=ttk.Frame(newsf);nh.pack(fill='x');ttk.Label(nh,text='NEWS / MARKET TAPE',font=('Arial',11,'bold')).pack(side='left');ttk.Button(nh,text='POP OUT / RESIZE',command=self.news_popup).pack(side='left',padx=8);self.news_filter=ttk.Combobox(nh,values=['ALL','STOCK','INDEX','COMMODITY','MACRO','GLOBAL'],state='readonly',width=12);self.news_filter.set('ALL');self.news_filter.pack(side='right');self.news_filter.bind('<<ComboboxSelected>>',lambda e:self.refresh_news());self.news=tk.Text(newsf,height=7,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat');self.news.pack(fill='both');self.status=ttk.Label(self.root,text='');self.status.pack(fill='x',padx=7)
    def add_chart(self):
        if len(self.charts)>=8:return self.status_flash('Maximum 8 charts in the main workspace.')
        self._workspace_count=len(self.charts)+1;self.set_chart_count(initial=self._workspace_count)
    def remove_chart(self,index):
        if len(self.charts)<=1:return self.status_flash('Keep at least one chart.')
        self._workspace_count=max(1,len(self.charts)-1);self.set_chart_count(initial=self._workspace_count);self.active_chart=min(index,len(self.charts)-1);self.sync_chart_controls()
    def market_event_lab(self):
        # Safe educational substitute for hacking/manipulation: fictional, abstract event-risk scenarios.
        w=tk.Toplevel(self.root);w.title('MARKET EVENT LAB — RISK TRAINING');w.geometry('620x520');w.configure(bg=BG)
        ttk.Label(w,text='Fictional Market Event Lab',font=('Arial',15,'bold')).pack(anchor='w',padx=18,pady=14)
        ttk.Label(w,text='This mode models legal event-risk decisions against fictional entities; it does not target real organizations or provide hacking instructions.',wraplength=560).pack(anchor='w',padx=18,pady=6)
        bal=ttk.Label(w,text='');bal.pack(anchor='w',padx=18,pady=6)
        risk=tk.IntVar(value=50);size=tk.IntVar(value=5000)
        ttk.Label(w,text='Event intensity').pack(anchor='w',padx=18);ttk.Scale(w,from_=1,to=100,variable=risk,orient='horizontal').pack(fill='x',padx=18)
        ttk.Label(w,text='Capital at risk').pack(anchor='w',padx=18);ttk.Scale(w,from_=100,to=max(1000,int(self.portfolio.cash*.25)),variable=size,orient='horizontal').pack(fill='x',padx=18)
        result=ttk.Label(w,text='Choose a fictional scenario.');result.pack(anchor='w',padx=18,pady=15)
        def run():
            amt=min(int(size.get()),self.portfolio.cash);p=max(.05,min(.95,.55-(risk.get()-50)*.004));success=random.random()<p;self.portfolio.cash-=amt
            if success:self.portfolio.cash+=amt*(1+0.45*risk.get()/100);result.config(text=f'Scenario succeeded. Educational payoff credited: ${amt*.45*risk.get()/100:,.0f}.',foreground=GREEN)
            else:self.portfolio.cash+=amt*.35;result.config(text=f'Scenario failed. Risk loss: ${amt*.65:,.0f}. No real organization was targeted.',foreground=RED)
            bal.config(text=f'Virtual cash: ${self.portfolio.cash:,.2f}')
        ttk.Button(w,text='RUN FICTIONAL EVENT',command=run).pack(fill='x',padx=18,pady=8);bal.config(text=f'Virtual cash: ${self.portfolio.cash:,.2f}')
    def account_mode(self):
        w=tk.Toplevel(self.root);w.title('ACCOUNT / DIFFICULTY');w.geometry('520x390');w.configure(bg=BG);w.transient(self.root)
        ttk.Label(w,text='Simulation difficulty',font=('Arial',14,'bold')).pack(anchor='w',padx=18,pady=16)
        mode=tk.StringVar(value=getattr(self.market,'difficulty','MEDIUM'));
        for name,cash,speed,desc in [('EASY',50000,.12,'Slower pace and smaller starting account'),('MEDIUM',250000,.08,'Balanced training mode'),('EXPERT',1000000,.045,'Faster market and larger account')]:
            ttk.Radiobutton(w,text=f'{name} — ${cash:,.0f}',variable=mode,value=name).pack(anchor='w',padx=24,pady=7)
        def apply():
            vals={'EASY':(50000,.12),'MEDIUM':(250000,.08),'EXPERT':(1000000,.045)}[mode.get()]
            self.market.difficulty=mode.get();self.market.speed=vals[1];self.status_flash(f'Difficulty set to {mode.get()} — existing cash retained')
            w.destroy()
        ttk.Button(w,text='APPLY',command=apply).pack(fill='x',padx=18,pady=20)

    def load_max_selected(self):
        a=self.selected() or self.charts[self.active_chart].asset
        if a:self.market.load_ipo_history(a);self.status_flash(f'Loading MAX / earliest available history for {a.symbol}')
    def set_chart_count(self,initial=None):
        count=initial or int(getattr(self,'_workspace_count',8) if hasattr(self,'_workspace_count') else 8);count=max(1,min(8,count));self._workspace_count=count
        if hasattr(self,'grid'):
            for child in list(self.grid.panes()):
                try:self.grid.forget(child)
                except Exception:pass
                try:self.root.nametowidget(child).destroy()
                except Exception:pass
            self.charts=[]
            cols=4 if count>=8 else 3 if count>=6 else 2 if count>=4 else 1
            rows=math.ceil(count/cols)
            for col in range(cols):
                vp=ttk.PanedWindow(self.grid,orient='vertical')
                self.grid.add(vp,weight=1)
                for row in range(rows):
                    i=col*rows+row
                    if i>=count:break
                    c=Chart(vp,self,i);vp.add(c,weight=1);self.charts.append(c)
            defaults=['SPY','VIX','NVDA','AAPL','CL=F','GC=F','GME',random.choice([a.symbol for a in self.market.stocks])]
            for i,c in enumerate(self.charts):
                a=self.market.get_asset(defaults[i]) or self.market.get_asset('SPY');c.set_asset(a)
            self.active_chart=0;self.sync_chart_controls();self.status_flash(f'{count} chart workspace — drag the dividers between charts to resize them')
    def apply_watch_density(self):
        px=int(self.watch_density.get());self.watch_density_label.config(text=f'{px}px');ttk.Style().configure('Treeview',rowheight=px)
    def toggle_pause(self):
        self.market.paused=not getattr(self.market,'paused',False);self.status_flash('Simulation PAUSED' if self.market.paused else 'Simulation RUNNING')
    def account_panel(self):
        w=ToolWindow(self.root);w.style_window('ACCOUNT / DIFFICULTY','520x430');ttk.Label(w,text='ACCOUNT / DIFFICULTY',font=('Arial',15,'bold')).pack(anchor='w',padx=16,pady=12);name=getattr(self,'account_username',None) or 'Guest / Training';ttk.Label(w,text=f'Account: {name}').pack(anchor='w',padx=16,pady=5);ttk.Label(w,text=f'Current mode: {self.market.difficulty}').pack(anchor='w',padx=16,pady=5);ttk.Label(w,text='Change difficulty for the next session from the main menu.').pack(anchor='w',padx=16,pady=5);ttk.Label(w,text=f'Cash: ${self.portfolio.cash:,.2f}').pack(anchor='w',padx=16,pady=5);ttk.Label(w,text=f'Net worth: ${self.portfolio.mark_value(self.market.all_assets()):,.2f}').pack(anchor='w',padx=16,pady=5);ttk.Label(w,text=f'Trades: {self.portfolio.trade_count}').pack(anchor='w',padx=16,pady=5)
    def session_stats(self):
        w=ToolWindow(self.root);w.style_window('SESSION STATISTICS','620x520');ttk.Label(w,text='SESSION PERFORMANCE',font=('Arial',15,'bold')).pack(anchor='w',padx=16,pady=12);rows=[('Starting cash',getattr(self,'starting_cash',self.portfolio.cash)),('Current cash',self.portfolio.cash),('Net worth',self.portfolio.mark_value(self.market.all_assets())),('Realized P/L',self.portfolio.realized),('Margin used',getattr(self.portfolio,'reserved_margin',0)),('Trades',self.portfolio.trade_count),('Working orders',len(self.market.pending_orders)+len(self.market.pending_option_orders)+len(self.market.pending_spread_orders))];
        for k,v in rows:ttk.Label(w,text=f'{k:<22} ${v:,.2f}' if isinstance(v,(int,float)) and k!='Trades' and k!='Working orders' else f'{k:<22} {v:,}').pack(anchor='w',padx=24,pady=6)
    def market_selected(self,e=None):
        a=self.selected();
        if a:self.load_asset_auto(a)
    def selected(self):
        it=self.watch.selection() or ((self.watch.focus(),) if self.watch.focus() else ());return self.market.get_asset(self.watch.item(it[0],'values')[0]) if it and self.watch.exists(it[0]) else None
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
        self.watch.selection_set(iid);self.watch.focus(iid);self.watch.see(iid);a=self.market.get_asset(iid);m=tk.Menu(self.watch,tearoff=0);m.add_command(label=f'BUY {a.symbol}',command=lambda:self.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL {a.symbol}',command=lambda:self.order_window(a,'SELL','MARKET',None));m.add_command(label=f'SHORT {a.symbol}',command=lambda:self.order_window(a,'SHORT','MARKET',None));m.add_command(label='COVER',command=lambda:self.order_window(a,'COVER','MARKET',None));m.add_separator();m.add_command(label='Open Options Chain',command=lambda:self.options_for(a));m.add_command(label='Advanced Chart',command=lambda:self.load_asset_auto(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.depth_for(a));m.add_command(label='WATCHLIST VARIABLES',command=self.watch_variables);m.tk_popup(event.x_root,event.y_root)
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
    def advanced_chart(self,a):
        w=ToolWindow(self.root);w.style_window(f'ADVANCED CHART — {a.symbol}','1200x760');w.resizable(True,True);c=Chart(w,self,self.active_chart);c.pack(fill='both',expand=True,padx=8,pady=8);c.set_asset(a);c.selected_popup=True
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
        for sym,name,q,p,v,pnl,typ in self.portfolio.position_rows(self.market.all_assets()):
            pct=(pnl/max(1e-9,abs(self.portfolio.cost_basis.get(sym,0))) if sym in self.portfolio.cost_basis else 0)
            self.pos.insert('','end',iid=sym,values=(sym,f'{q:,}',f'${p:,.2f}',f'${v:,.2f}',f'${pnl:,.2f}',f'{pct:+.2f}%',typ))
        if keep and keep in self.pos.get_children():self.pos.selection_set(keep);self.pos.focus(keep)
    def position_context(self,e):
        iid=self.pos.identify_row(e.y)
        if not iid:return
        self.pos.selection_set(iid);m=tk.Menu(self.pos,tearoff=0);m.add_command(label='Liquidate / Cash',command=self.liquidate);m.add_command(label='PORTFOLIO VARIABLES',command=self.position_variables);m.tk_popup(e.x_root,e.y_root)
    def position_variables(self):
        self.column_variables(self.pos, {'Symbol':'symbol','Qty':'qty','Last':'last','Value':'value','P/L':'pnl','P/L %':'pct','Type':'type'})
    def watch_variables(self):
        self.column_variables(self.watch, {'Symbol':'symbol','Name':'name','Price':'price','Chg %':'chg','Sector':'sector'})
    def column_variables(self,tv,names):
        w=tk.Toplevel(self.root);w.title('TABLE VARIABLES');w.geometry('360x420');w.resizable(True,True);ttk.Label(w,text='Visible columns',font=('Arial',12,'bold')).pack(anchor='w',padx=12,pady=10)
        for label,key in names.items():
            v=tk.BooleanVar(value=tv.column(key,'width')>0);ttk.Checkbutton(w,text=label,variable=v,command=lambda k=key,var=v:self.toggle_table_column(tv,k,var)).pack(anchor='w',padx=20,pady=4)
    def toggle_table_column(self,tv,key,var):tv.column(key,width=0 if not var.get() else (130 if key=='name' else 90),stretch=False)
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
    def refresh_orders(self):
        if not hasattr(self,'orders_view'): return
        self.orders_view.delete(*self.orders_view.get_children())
        for o in self.market.pending_orders:
            a=o.get('asset');self.orders_view.insert('','end',values=(o.get('id',''),getattr(a,'symbol',''),o.get('side',''),o.get('type',''),f"{o.get('qty',0):,}",f"${o.get('price',0):,.2f}",'WORKING'))
        for i,o in enumerate(self.market.pending_option_orders):
            c=o.get('contract');self.orders_view.insert('','end',values=(f'OPT{i}',c.underlying.symbol if c else '',o.get('side',''),o.get('type',''),o.get('qty',1),f"${o.get('price') or 0:,.2f}",'WORKING'))
        for i,o in enumerate(self.market.pending_spread_orders):
            self.orders_view.insert('','end',values=(f'SP{i}',getattr(o.get('strategy'),'name','SPREAD'),o.get('side',''),o.get('type',''),len(getattr(o.get('strategy'),'legs',[])),f"${o.get('price') or 0:,.2f}",'WORKING'))

    def news_popup(self):
        w=ToolWindow(self.root);w.style_window('NEWS — POP OUT','900x600');w.resizable(True,True);top=ttk.Frame(w);top.pack(fill='x',padx=8,pady=6);ttk.Label(top,text='NEWS / MARKET TAPE',font=('Arial',13,'bold')).pack(side='left');tv=tk.Text(w,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat',wrap='word');tv.pack(fill='both',expand=True,padx=8,pady=8)
        for n in self.market.news[-500:]:tv.insert('end',f'[{{getattr(n,"severity","NORMAL")}}] {{n}}\n')
        w.transient(self.root)
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
            self.portfolio.apply_corporate_actions(self.market.all_assets());self.portfolio.best_net_worth=max(getattr(self.portfolio,'best_net_worth',0),self.portfolio.mark_value(self.market.all_assets()));self.refresh_watch();self.refresh_positions();self.summary.delete('1.0','end');self.summary.insert('end',self.portfolio.summary(self.market.all_assets()));
            a=self.selected() or self.charts[self.active_chart].asset
            if a:
                p=self.market.predict(a);self.pred.config(text=f'MODEL {a.symbol}\n{p["label"]}  confidence {p["confidence"]*100:.0f}%\nMomentum {p["momentum"]*100:+.2f}%  vol {p["volatility"]*100:.2f}%')
            self.refresh_news();self.refresh_orders();self.clock_label.config(text=f'{self.market.clock.time}  •  {self.market.clock.utc_time}  •  {"US OPEN" if self.market.clock.open else "US CLOSED"}');self.status.config(text=f'Assets {len(self.market.all_assets())} • {self.market.data_status} • Working orders {len(self.market.pending_orders)+len(self.market.pending_option_orders)+len(self.market.pending_spread_orders)} • Engine errors {len(self.market.errors)}');self.redraw()
        except Exception as e:self.status.config(text=f'UI recovered: {e}')
        self.root.after(700,self.refresh)
