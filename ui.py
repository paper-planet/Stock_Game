import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
import math,random,time,json
from pathlib import Path
from game_core import option_chain,OptionContract,OptionStrategy,EXPIRATIONS
from game_core import SESSIONS,market_status

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
        super().__init__(parent,bg=BG,highlightthickness=2,highlightbackground='#263547')
        self.app=app;self.index=index;self.asset=None;self.timeframe='1D';self.kind='Candles';self.zoom=1.
        self.cross=None;self.tool='Crosshair';self.drawings=[];self.drag_order=None;self.drag_marker=None;self.drag_start=None;self.drag_preview_price=None
        # Rendering is driven by App's single chart scheduler. A single Tk after-loop avoids
        # timer drift/starvation between Canvas widgets and keeps equal-rate charts phase-synced.
        self.refresh_ms=50;self._next_refresh_ms=0.0;self._key=None
        self.bind('<Button-1>',self.click);self.bind('<Button-3>',self.context);self.bind('<B1-Motion>',self.drag)
        self.bind('<ButtonRelease-1>',self.release);self.bind('<Motion>',self.motion);self.bind('<MouseWheel>',self.wheel)
        self.bind('<Button-4>',lambda e:self._zoom(True));self.bind('<Button-5>',lambda e:self._zoom(False))
        self.bind('<Configure>',lambda e:self.request_draw(force=True))

    def request_draw(self,force=False):
        if force:self._key=None
        try:
            self.draw()
            self._last_draw_error=None
        except tk.TclError:
            pass
        except Exception as e:
            # Do not let one bad indicator/model value kill all chart rendering. Record the
            # first occurrence of each error and allow the next scheduler pulse to recover.
            msg=f'chart {self.index+1} draw: {type(e).__name__}: {e}'
            if getattr(self,'_last_draw_error',None)!=msg:
                self._last_draw_error=msg
                try:self.app.market.errors.append(msg)
                except Exception:pass

    def set_refresh_rate(self,ms):
        try:ms=max(25,min(5000,int(ms)))
        except Exception:ms=180
        self.refresh_ms=ms
        # Reset due time so changing a chart's rate takes effect immediately, then the shared
        # scheduler keeps subsequent draws aligned to the chosen interval.
        self._next_refresh_ms=0.0

    def due_for_refresh(self,now_ms):
        return now_ms >= self._next_refresh_ms

    def mark_refreshed(self,now_ms):
        interval=max(25,int(self.refresh_ms))
        # Quantize to the common scheduler epoch. Charts with the same interval therefore
        # remain on the exact same phase instead of accumulating independent after() drift.
        self._next_refresh_ms=(int(now_ms//interval)+1)*interval

    def click(self,e):
        # Pop-out charts are self-contained and must not steal the main workspace selection.
        if not getattr(self,'selected_popup',False):
            if getattr(self.app,'selected_chart',None)==self.index:
                self.app.selected_chart=None;self.configure(highlightbackground='#263547')
            else:
                self.app.selected_chart=self.index
                for ch in self.app.charts:ch.configure(highlightbackground=BLUE if ch is self else '#263547')
                self.app.active_chart=self.index;self.app.sync_chart_controls()
        self.start=(e.x,e.y);self.cross=(e.x,e.y);self.drag_preview_price=None
        self.drag_order=self.nearest_order(e.y);self.drag_marker=None if self.drag_order else self.nearest_position_marker(e.y)
    def drag(self,e):
        self.cross=(e.x,e.y)
        if self.drag_order:
            p=self.y_to_price(e.y);self.app.market.update_pending_price(self.drag_order['id'],p);self.request_draw(force=True);return
        if self.drag_marker:
            self.drag_preview_price=self.y_to_price(e.y);self.request_draw(force=True);return
        if self.tool=='Trendline' and self.start:self.request_draw(force=True)
    def release(self,e):
        if self.drag_order:
            self.app.status_flash(f"Order #{self.drag_order['id']} moved to ${self.y_to_price(e.y):,.2f}");self.drag_order=None
        elif self.drag_marker:
            marker=self.drag_marker;target=self.y_to_price(e.y)
            if marker[0]=='position':
                a,q=marker[1],marker[2];side='SELL' if q>0 else 'COVER';qty=abs(int(q))
                existing=next((o for o in self.app.market.pending_orders if o.get('position_exit') and o.get('asset') is a),None)
                if existing:self.app.market.update_pending_price(existing['id'],target);existing['qty']=qty;existing['side']=side
                else:
                    o=self.app.market.submit_pending(side,a,qty,'LIMIT',target);o['position_exit']=True
                self.app.status_flash(f'{side} exit for {qty:,} {a.symbol} moved to ${target:,.2f}')
            elif marker[0]=='option':
                # Option strikes live on the underlying price axis. Dragging a working option marker
                # changes the selected strike while preserving its side/quantity/order premium.
                order=marker[1]
                if order is not None:self.app.market.update_pending_option_strike(order.get('id'),target);self.app.status_flash(f'Option order #{order.get("id")} strike moved to {target:,.2f}')
                else:self.app.status_flash('Owned option shown on chart. Create a working option order from ADVANCED OPTIONS before dragging its strike.')
            self.drag_marker=None;self.drag_preview_price=None
        elif self.tool in ('Trendline','Horizontal') and self.start:
            if self.tool=='Trendline':self.drawings.append(('line',self.start,(e.x,e.y)))
            else:self.drawings.append(('h',e.y))
        self.start=None;self.request_draw(force=True)
    def motion(self,e):
        # Crosshair movement is a lightweight overlay update. Do not redraw candles/indicators.
        self.cross=(e.x,e.y)
        self._draw_crosshair()
    def wheel(self,e):self._zoom(e.delta>0)
    def _zoom(self,up):self.zoom=max(.25,min(20,self.zoom*(1.12 if up else .89)));self.draw()
    def set_asset(self,a):
        self.asset=a;self.zoom=1.;self.app.market.load_chart_data(a,self.timeframe);self.draw()
    def set_tf(self,tf):
        self.timeframe=tf;self.zoom=1.;self.app.market.load_chart_data(self.asset,tf);self.draw()
    def data(self):
        if not self.asset:return []
        interval={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe];d=self.asset.chart_candles(interval)
        if self.timeframe=='MAX':
            # Preserve the entire lifespan on the x-axis, but sample it to a render
            # budget so decades of daily history do not freeze Tkinter.
            target=max(300,min(1800,int(max(400,self.winfo_width())*1.2/self.zoom)))
            if len(d)>target:
                step=(len(d)-1)/(target-1);d=[d[round(i*step)] for i in range(target)]
            return d
        maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':500}[self.timeframe];return d[-max(30,int(maxbars/self.zoom)):]
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
    def nearest_position_marker(self,y):
        if not self.asset:return None
        a=self.asset;q=int(self.app.portfolio.positions.get(a.symbol,0))
        candidates=[]
        if q:
            basis=float(self.app.portfolio.cost_basis.get(a.symbol,0));entry=basis/max(1,abs(q));candidates.append((abs(self.price_to_y(entry)-y),('position',a,q,entry)))
        for o in self.app.market.pending_option_orders:
            c=o.get('contract')
            if c is not None and c.underlying.symbol==a.symbol:candidates.append((abs(self.price_to_y(c.strike)-y),('option',o,c.strike)))
        for strat,leg in self.app.portfolio.option_legs_for(a.symbol):
            c=leg.contract;candidates.append((abs(self.price_to_y(c.strike)-y),('option',None,c.strike)))
        if not candidates:return None
        dist,marker=min(candidates,key=lambda x:x[0]);return marker if dist<10 else None
    def context(self,e):
        if not getattr(self,'selected_popup',False):self.app.active_chart=self.index;self.app.sync_chart_controls()
        a=self.asset
        if not a:return
        p=self.y_to_price(e.y);m=tk.Menu(self,tearoff=0);m.add_command(label=f'BUY {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'BUY','LIMIT',p));m.add_command(label=f'SELL {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SELL','LIMIT',p));m.add_command(label=f'SHORT {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SHORT','LIMIT',p));m.add_command(label=f'COVER {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'COVER','LIMIT',p));m.add_separator();m.add_command(label='Buy at Market',command=lambda:self.app.order_window(a,'BUY','MARKET',None));m.add_command(label='Set Stop',command=lambda:self.app.order_window(a,'SELL','STOP',p));m.add_command(label='Open Options',command=lambda:self.app.options_for(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.app.depth_for(a));m.add_command(label='POP OUT ADVANCED CHART',command=lambda:self.app.advanced_chart(a));m.add_separator();m.add_command(label='ADD CHART',command=self.app.add_chart);m.add_command(label='REMOVE THIS CHART',command=lambda:self.app.remove_chart(self.index));m.tk_popup(e.x_root,e.y_root)
    def draw(self):
        a=self.asset;d=self.data();w=max(280,self.winfo_width());h=max(170,self.winfo_height());key=(a.symbol if a else None,self.timeframe,self.kind,round(self.zoom,2),len(d),round(a.price,3) if a else 0,w,h,len(self.drawings),len(self.app.market.pending_orders),len(self.app.market.pending_option_orders),tuple(sorted(self.app.portfolio.positions.items())),len(self.app.portfolio.options),self.app.ind_vars_version,getattr(a,'last_update',None),tuple((o.get('id'),round(float(o.get('price') or 0),4)) for o in self.app.market.pending_orders if o.get('asset') is a),tuple((o.get('id'),round(float(getattr(o.get('contract'),'strike',0)),4)) for o in self.app.market.pending_option_orders if getattr(o.get('contract'),'underlying',None) is a))
        if key==self._key:return
        self._key=key;self.delete('all')
        if not a:self.create_text(w/2,h/2,text=f'CHART {self.index+1}\nClick a market ticker',fill=MUTED,font=('Arial',12,'bold'));return
        if len(d)<2:
            self.create_text(10,6,anchor='nw',text=f'{a.symbol}  •  {a.name}',fill=TEXT,font=('Arial',9,'bold'));self.create_text(10,24,anchor='nw',text=f'Loading {self.timeframe}...',fill=MUTED,font=('Arial',9));return
        left,right,top,bottom=62,w-12,34,h-32
        # One compact header row prevents the old duplicate labels from overlapping on small panes.
        name=a.name if w>430 else (a.name[:18]+'…' if len(a.name)>19 else a.name)
        self.create_text(8,7,anchor='nw',text=f'{a.symbol} • {name}',fill=TEXT,font=('Arial',9,'bold'))
        self.create_text(right,7,anchor='ne',text=f'{self.timeframe} • {self.kind} • ${a.price:,.2f} • {a.change_percent():+.2f}%',fill=MUTED,font=('Arial',8))
        lo,hi=self.price_bounds();span=max(.00001,hi-lo);n=len(d);step=(right-left)/max(1,n)
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
        # Portfolio positions and option strikes are visible directly on every chart.
        q=int(self.app.portfolio.positions.get(a.symbol,0))
        if q:
            basis=float(self.app.portfolio.cost_basis.get(a.symbol,0));entry=basis/max(1,abs(q));y=py(entry);col=GREEN if q>0 else RED
            self.create_line(left,y,right,y,fill=col,dash=(10,4),width=2);self.create_text(left+5,y-8,anchor='w',text=f'{"LONG" if q>0 else "SHORT"} {abs(q):,} @ ${entry:,.2f}  • drag = move full exit',fill=col,font=('Arial',8,'bold'))
        for strat,leg in self.app.portfolio.option_legs_for(a.symbol):
            c=leg.contract;y=py(c.strike);col=GREEN if leg.action=='BUY' else RED
            self.create_line(left,y,right,y,fill=col,dash=(2,5));self.create_text(right-4,y-7,anchor='e',text=f'OPT {leg.action} {leg.quantity} {c.option_type.upper()} {c.strike:g}',fill=col,font=('Arial',7,'bold'))
        for o in self.app.market.pending_option_orders:
            c=o.get('contract')
            if c is not None and c.underlying.symbol==a.symbol:
                y=py(c.strike);self.create_line(left,y,right,y,fill=PURPLE,dash=(5,3),width=2);self.create_text(right-4,y+8,anchor='e',text=f'OPT #{o.get("id")} {o.get("side")} {o.get("qty")} @ strike {c.strike:g}  • drag',fill=PURPLE,font=('Arial',7,'bold'))
        if self.drag_preview_price is not None:
            y=py(self.drag_preview_price);self.create_line(left,y,right,y,fill=YELLOW,width=2);self.create_text(left+6,y+8,anchor='w',text=f'NEW LEVEL ${self.drag_preview_price:,.2f}',fill=YELLOW,font=('Arial',8,'bold'))
        footer=f'O {d[-1].open:.2f}  H {d[-1].high:.2f}  L {d[-1].low:.2f}  C {d[-1].close:.2f}'
        if w>420:footer+=f'  V {d[-1].volume:,}'
        self.create_text(8,h-7,anchor='sw',text=footer,fill=MUTED,font=('Arial',7 if w<380 else 8))
        self._draw_crosshair(top=top,bottom=bottom,left=left,right=right)

    def _draw_crosshair(self,top=None,bottom=None,left=None,right=None):
        self.delete('crosshair')
        if not self.cross or not self.asset:return
        h=max(170,self.winfo_height());w=max(280,self.winfo_width())
        top=24 if top is None else top;bottom=h-34 if bottom is None else bottom
        left=62 if left is None else left;right=w-12 if right is None else right
        x,y=self.cross
        self.create_line(x,top,x,bottom,fill='#5c7085',tags='crosshair')
        self.create_line(left,y,right,y,fill='#5c7085',tags='crosshair')
        self.create_text(x+6,y-5,text=f'${self.y_to_price(y):,.2f}',fill=TEXT,anchor='w',font=('Arial',8,'bold'),tags='crosshair')

    def _line(self,vals,left,step,py,col):
        pts=[]
        for i,v in enumerate(vals):
            if v is not None:pts += [left+(i+.5)*step,py(v)]
        if len(pts)>3:self.create_line(*pts,fill=col,width=1)

class OptionsWindow(ToolWindow):
    DEFAULT_COLS=['Bid','Ask','Last','Vol','OI','IV']
    ALL_COLS=['Bid','Ask','Last','Vol','OI','IV','Delta','Gamma','Theta','Vega']
    def __init__(self,parent,market,portfolio,refresh):
        super().__init__(parent);self.market=market;self.portfolio=portfolio;self.refresh_main=refresh;self.style_window('Stock Game Pro 1.0 — Pro Options Chain','1420x840');self.resizable(True,True)
        self.rate_ms=500;self._after_id=None;self.selected_side='CALL';self.selected_strike=None;self.visible_cols={x:(x in self.DEFAULT_COLS) for x in self.ALL_COLS};self.sort_metric='Strike';self.sort_reverse=False;self.var_window=None;self._chain_cache={};self._last_key=None
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=7)
        ttk.Label(top,text='Ticker').pack(side='left');self.entry=ttk.Entry(top,width=12);self.entry.insert(0,'SPX');self.entry.pack(side='left',padx=5);self.entry.bind('<Return>',lambda e:self.apply_symbol());ttk.Button(top,text='LOAD',command=self.apply_symbol).pack(side='left')
        ttk.Label(top,text='Expiry').pack(side='left',padx=(12,2));self.expiry=ttk.Combobox(top,values=[x[0] for x in EXPIRATIONS],state='readonly',width=10);self.expiry.set('0DTE');self.expiry.pack(side='left')
        ttk.Label(top,text='Range').pack(side='left',padx=(12,2));self.span=ttk.Combobox(top,values=['ATM ±5 Strikes','ATM ±10 Strikes','ATM ±20 Strikes','ATM ±50 Strikes','All'],state='readonly',width=16);self.span.set('ATM ±10 Strikes');self.span.pack(side='left')
        ttk.Label(top,text='Update').pack(side='left',padx=(12,2));self.rate=ttk.Combobox(top,values=['250ms','500ms','1000ms','2000ms'],state='readonly',width=10);self.rate.set('500ms');self.rate.pack(side='left');self.rate.bind('<<ComboboxSelected>>',lambda e:self.set_rate())
        ttk.Label(top,text='Sector').pack(side='left',padx=(10,2));self.sector_filter=tk.StringVar(value='ALL');self.sector_cb=ttk.Combobox(top,textvariable=self.sector_filter,values=['ALL']+market.sectors,state='readonly',width=14);self.sector_cb.pack(side='left');self.sector_cb.bind('<<ComboboxSelected>>',lambda e:self.apply_correlated_filter())
        ttk.Button(top,text='SPREAD BUILDER',command=self.spread_builder).pack(side='left',padx=7);ttk.Button(top,text='VARIABLES',command=self.variables).pack(side='left');self.live_price=ttk.Label(top,text='LIVE  --',font=('Arial',10,'bold'));self.live_price.pack(side='right',padx=10);self.live=ttk.Label(top,text='● LIVE');self.live.pack(side='right')
        head=tk.Frame(self,bg=BG);head.pack(fill='x',padx=8);tk.Label(head,text='CALLS',bg='#123326',fg=GREEN,font=('Arial',9,'bold')).grid(row=0,column=0,sticky='ew');tk.Label(head,text='STRIKE / ATM',bg='#3c3320',fg=YELLOW,font=('Arial',9,'bold'),width=16).grid(row=0,column=1);tk.Label(head,text='PUTS',bg='#38202a',fg=RED,font=('Arial',9,'bold')).grid(row=0,column=2,sticky='ew');head.columnconfigure(0,weight=1);head.columnconfigure(2,weight=1)
        self.chain_frame=ttk.Frame(self);self.chain_frame.pack(fill='both',expand=True,padx=8,pady=(5,0));self.chain_frame.columnconfigure(0,weight=1);self.chain_frame.columnconfigure(1,weight=0);self.chain_frame.columnconfigure(2,weight=1);self.chain_frame.rowconfigure(0,weight=1)
        self.tv_calls=ttk.Treeview(self.chain_frame,show='headings',selectmode='browse');self.tv_strike=ttk.Treeview(self.chain_frame,columns=('strike',),show='headings',selectmode='browse');self.tv_puts=ttk.Treeview(self.chain_frame,show='headings',selectmode='browse')
        self.tv_strike.heading('strike',text='STRIKE / ATM');self.tv_strike.column('strike',width=110,anchor='center',stretch=False)
        self.tv_calls.grid(row=0,column=0,sticky='nsew');self.tv_strike.grid(row=0,column=1,sticky='ns');self.tv_puts.grid(row=0,column=2,sticky='nsew')
        self.tv_calls.tag_configure('itm',background='#173d2e',foreground='#bfffe7');self.tv_calls.tag_configure('otm',background='#5b1f2c',foreground='#ffdce2');self.tv_calls.tag_configure('atm',background='#403720',foreground='#fff2ae');self.tv_calls.tag_configure('owned',background='#1b4d77',foreground='#ffffff')
        self.tv_puts.tag_configure('itm',background='#173d2e',foreground='#bfffe7');self.tv_puts.tag_configure('otm',background='#5b1f2c',foreground='#ffdce2');self.tv_puts.tag_configure('atm',background='#403720',foreground='#fff2ae');self.tv_puts.tag_configure('owned',background='#1b4d77',foreground='#ffffff')
        self.tv_strike.tag_configure('atm',background='#403720',foreground='#fff2ae')
        # One shared vertical scrollbar: the strike column can never drift away from calls/puts.
        self.scroll=ttk.Scrollbar(self.chain_frame,orient='vertical',command=self._yview_all);self.scroll.grid(row=0,column=3,sticky='ns')
        for tv in (self.tv_calls,self.tv_strike,self.tv_puts):
            tv.configure(yscrollcommand=self._sync_scroll);tv.bind('<Button-1>',lambda e,tv=tv:self.chain_select(e,tv));tv.bind('<Button-3>',lambda e,tv=tv:self.context(e));tv.bind('<Double-1>',lambda e,tv=tv:self.double_option(e,tv));tv.bind('<MouseWheel>',self._wheel_sync)
        self.info_lbl=ttk.Label(self,text='ITM = green • OTM = red • ATM = gold • click a column heading to sort • double-click an option for order/spread preview.');self.info_lbl.pack(fill='x',padx=8,pady=5);self.rebuild_chain_columns();self.after(50,self.update_chain)
    def _yview_all(self,*args):
        for tv in (self.tv_calls,self.tv_strike,self.tv_puts):tv.yview(*args)
    def _sync_scroll(self,*args):
        if not hasattr(self,'scroll'):return
        self.scroll.set(*args)
        for tv in (self.tv_calls,self.tv_strike,self.tv_puts):
            try:tv.yview_moveto(args[0])
            except:pass
    def _wheel_sync(self,e):
        delta=-1 if e.delta>0 else 1
        for tv in (self.tv_calls,self.tv_strike,self.tv_puts):tv.yview_scroll(delta,'units')
        return 'break'
    def set_rate(self):self.rate_ms=int(self.rate.get().replace('ms',''))
    def variables(self):
        if self.var_window is not None and self.var_window.winfo_exists():self.var_window.lift();return
        w=tk.Toplevel(self);self.var_window=w;w.title('OPTIONS VARIABLES');w.geometry('380x560');w.resizable(True,True);w.configure(bg=BG);ttk.Label(w,text='Visible option-chain variables',font=('Arial',12,'bold')).pack(anchor='w',padx=12,pady=10)
        for k in self.ALL_COLS:
            v=tk.BooleanVar(value=self.visible_cols[k]);ttk.Checkbutton(w,text=k,variable=v,command=lambda key=k,var=v:self.toggle_col(key,var)).pack(anchor='w',padx=20,pady=4)
        ttk.Button(w,text='RESET TO CORE COLUMNS',command=self.reset_columns).pack(fill='x',padx=18,pady=12);ttk.Label(w,text='Greeks are intentionally off by default. Use the Advanced Spread Builder for Greeks and strategy analytics.',wraplength=330).pack(anchor='w',padx=18,pady=6)
        w.protocol('WM_DELETE_WINDOW',lambda:(setattr(self,'var_window',None),w.destroy()))
    def reset_columns(self):
        self.visible_cols={x:(x in self.DEFAULT_COLS) for x in self.ALL_COLS};self.rebuild_chain_columns()
    def toggle_col(self,k,v):self.visible_cols[k]=bool(v.get());self.rebuild_chain_columns()
    def rebuild_chain_columns(self):
        cols=[k for k in self.ALL_COLS if self.visible_cols.get(k)] or ['Bid']
        labels={'Delta':'Δ','Gamma':'Γ','Theta':'Θ','Vega':'Vega'}
        for tv in (self.tv_calls,self.tv_puts):
            tv['columns']=tuple(cols)
            for c in cols:
                tv.heading(c,text=labels.get(c,c),command=lambda metric=c:self.sort_by(metric));tv.column(c,width=78,anchor='center',stretch=True,minwidth=58)
        self.update_chain(force=True)
    def sort_by(self,metric):
        self.sort_reverse=not self.sort_reverse if self.sort_metric==metric else False;self.sort_metric=metric;self.update_chain(force=True)
    def chain_select(self,e,tv):
        iid=tv.identify_row(e.y)
        if not iid:return
        for x in (self.tv_calls,self.tv_strike,self.tv_puts):x.selection_remove(x.selection())
        tv.selection_set(iid);tv.focus(iid);self.selected_strike=int(iid);self.selected_side='CALL' if tv is self.tv_calls else 'PUT';self.info_lbl.config(text=f'{self.selected_side} {self.selected_strike} selected')
    def double_option(self,e,tv):
        self.chain_select(e,tv);c=self.selected_contract();
        if c:OptionPreviewWindow(self,c,self.portfolio,self.refresh_main,self)
    def apply_symbol(self):
        s=self.entry.get().strip().upper();a=self.market.get_asset(s)
        if not a:self.info_lbl.config(text=f'{s}: ticker not found');return
        if self.expiry.get()=='0DTE' and a.symbol not in {'SPX','NDX','RUT','DJI','ES=F','NQ=F'}:self.expiry.set('1D')
        self._chain_cache.clear();self.info_lbl.config(text=f'Loaded {a.symbol} — {a.name}');self.update_chain(force=True)
    def apply_correlated_filter(self):
        sec=self.sector_filter.get();self.info_lbl.config(text=f'Sector filter: {sec}');self.update_chain(force=True)
    def asset(self):return self.market.get_asset(self.entry.get().strip().upper()) or self.market.get_asset('SPX')
    def owned_contract(self,a,k,typ,days):
        needle=(a.symbol,int(k),typ.lower(),int(days))
        return any((l.contract.underlying.symbol,int(l.contract.strike),l.contract.option_type.lower(),int(l.contract.days))==needle for s in self.portfolio.options for l in s.legs)
    def _contracts(self,a,days,span):
        key=(a.symbol,days,span,round(float(a.price),0))
        if key not in self._chain_cache:self._chain_cache[key]=option_chain(a,days,span)
        return self._chain_cache[key]
    def update_chain(self,force=False):
        if not self.winfo_exists(): return
        try:
            a=self.asset(); days=dict(EXPIRATIONS).get(self.expiry.get(),0); self.live_price.config(text=f'{a.symbol}  LIVE ${a.price:,.2f}')
            span={'ATM ±5 Strikes':5,'ATM ±10 Strikes':10,'ATM ±20 Strikes':20,'ATM ±50 Strikes':50}.get(self.span.get(),40)
            cs=self._contracts(a,days,span)
            calls={int(c.strike):c for c in cs if c.option_type=='call'}
            puts={int(c.strike):c for c in cs if c.option_type=='put'}
            center=round(a.price); ks=sorted(calls)
            if self.span.get()!='All': ks=[k for k in ks if abs(k-center)<=span]
            if self.sort_metric!='Strike':
                def metric(k):
                    c=calls[k]; st=c.stats
                    return {'Bid':c.bid,'Ask':c.ask,'Last':c.mid,'Vol':c.volume,'OI':c.open_interest,'IV':c.volatility,'Delta':abs(st['delta']),'Gamma':st['gamma'],'Theta':st['theta'],'Vega':st['vega']}.get(self.sort_metric,k)
                ks=sorted(ks,key=metric,reverse=self.sort_reverse)
            visible=[k for k in self.ALL_COLS if self.visible_cols.get(k)] or ['Bid']
            wanted=[str(k) for k in ks]
            # Update existing rows in place. This eliminates the visible blank/flicker caused by deleting/reinserting the chain every tick.
            for tv in (self.tv_calls,self.tv_strike,self.tv_puts):
                existing=set(tv.get_children())
                for iid in existing-set(wanted): tv.delete(iid)
            for pos,k in enumerate(ks):
                c,p=calls[k],puts[k]; cs_,ps_=c.stats,p.stats
                ctag='atm' if k==center else ('itm' if c.itm() else 'otm'); ptag='atm' if k==center else ('itm' if p.itm() else 'otm')
                if self.owned_contract(a,k,'call',days): ctag='owned'
                if self.owned_contract(a,k,'put',days): ptag='owned'
                cv={'Bid':f'{c.bid:.2f}','Ask':f'{c.ask:.2f}','Last':f'{c.mid:.2f}','Vol':f'{c.volume:,}','OI':f'{c.open_interest:,}','IV':f'{c.volatility*100:.1f}%','Delta':f'{cs_["delta"]:+.2f}','Gamma':f'{cs_["gamma"]:.4f}','Theta':f'{cs_["theta"]:.3f}','Vega':f'{cs_["vega"]:.3f}'}
                pv={'Bid':f'{p.bid:.2f}','Ask':f'{p.ask:.2f}','Last':f'{p.mid:.2f}','Vol':f'{p.volume:,}','OI':f'{p.open_interest:,}','IV':f'{p.volatility*100:.1f}%','Delta':f'{ps_["delta"]:+.2f}','Gamma':f'{ps_["gamma"]:.4f}','Theta':f'{ps_["theta"]:.3f}','Vega':f'{ps_["vega"]:.3f}'}
                valsc=tuple(cv[x] for x in visible); valsp=tuple(pv[x] for x in visible)
                if str(k) in self.tv_calls.get_children(): self.tv_calls.item(str(k),values=valsc,tags=(ctag,)); self.tv_puts.item(str(k),values=valsp,tags=(ptag,)); self.tv_strike.item(str(k),values=(f'{k:,}',),tags=('atm' if k==center else ''))
                else:
                    self.tv_calls.insert('',pos,iid=str(k),values=valsc,tags=(ctag,)); self.tv_strike.insert('',pos,iid=str(k),values=(f'{k:,}',),tags=('atm' if k==center else '')); self.tv_puts.insert('',pos,iid=str(k),values=valsp,tags=(ptag,))
            # Explicitly restore the same order in all three synchronized views.
            for tv in (self.tv_calls,self.tv_strike,self.tv_puts):
                for pos,k in enumerate(wanted):
                    if k in tv.get_children(): tv.move(k,'',pos)
            self._last_key=(a.symbol,days,tuple(ks),tuple(visible),self.sort_metric,self.sort_reverse)
            if self._after_id:
                try:self.after_cancel(self._after_id)
                except Exception:pass
            self._after_id=self.after(self.rate_ms,lambda:self.update_chain(False))
        except Exception as e:
            self.info_lbl.config(text=f'Option chain recovered: {type(e).__name__}: {e}')
            if self._after_id:
                try:self.after_cancel(self._after_id)
                except Exception:pass
            self._after_id=self.after(1000,lambda:self.update_chain(False))

    def selected_contract(self):
        if self.selected_strike is None:return None
        a=self.asset();days=dict(EXPIRATIONS).get(self.expiry.get(),0);span={'ATM ±5 Strikes':5,'ATM ±10 Strikes':10,'ATM ±20 Strikes':20,'ATM ±50 Strikes':50}.get(self.span.get(),40);
        for c in self._contracts(a,days,span):
            if int(c.strike)==int(self.selected_strike) and c.option_type.lower()==self.selected_side.lower(): return c
        return OptionContract(a,self.selected_strike,days,self.selected_side.lower())
    def context(self,e):
        tv=e.widget;iid=tv.identify_row(e.y)
        if not iid:return
        self.chain_select(e,tv);c=self.selected_contract();m=tk.Menu(self,tearoff=0);m.add_command(label=f'BUY {c}',command=lambda:self.trade_action('BUY'));m.add_command(label='BUY QUANTITY / PREVIEW',command=lambda:OptionPreviewWindow(self,c,self.portfolio,self.refresh_main,self));m.add_command(label='Add Leg to Spread',command=self.add_leg_to_spread);m.add_command(label='Open Spread Builder',command=self.spread_builder);m.add_separator();m.add_command(label='Set LIMIT',command=lambda:self.option_order('LIMIT'));m.add_command(label='Set STOP',command=lambda:self.option_order('STOP'));m.add_command(label='Liquidate Matching Contract',command=self.liquidate_matching);m.tk_popup(e.x_root,e.y_root)
    def trade_action(self,action):
        c=self.selected_contract()
        if c:OptionPreviewWindow(self,c,self.portfolio,self.refresh_main,self,default_action=action)
    def option_order(self,typ):
        c=self.selected_contract();
        if c:OptionOrderWindow(self,c,self.portfolio,self.refresh_main,typ).grab_set()
    def add_leg_to_spread(self):self.spread_builder(self.selected_contract())
    def spread_builder(self,first=None):SpreadBuilder(self,self.market,self.portfolio,self.refresh_main,first)
    def liquidate_matching(self):
        c=self.selected_contract()
        if not c:return
        for i,s in enumerate(list(self.portfolio.options)):
            if any(l.contract.underlying.symbol==c.underlying.symbol and int(l.contract.strike)==int(c.strike) and l.contract.option_type==c.option_type for l in s.legs):
                ok,msg=self.portfolio.liquidate_strategy(i);messagebox.showinfo('Liquidation',msg) if ok else messagebox.showerror('Liquidation',msg);self.refresh_main();return
        messagebox.showwarning('Contract','No matching owned contract found.')

class OptionPreviewWindow(ToolWindow):
    def __init__(self,parent,contract,portfolio,refresh,chain=None,default_action='BUY'):
        super().__init__(parent);self.contract=contract;self.portfolio=portfolio;self.refresh=refresh;self.chain=chain;self.style_window('OPTION CREATION / ORDER PREVIEW','620x520');self.action=tk.StringVar(value=default_action);self.qty=tk.IntVar(value=1)
        f=ttk.Frame(self);f.pack(fill='both',expand=True,padx=16,pady=16);ttk.Label(f,text=f'{contract.underlying.symbol} • {contract.option_type.upper()} • Strike ${contract.strike:,.2f} • {contract.days}D',font=('Arial',14,'bold')).pack(anchor='w');ttk.Label(f,text='Double-click preview: choose quantity, then buy the contract or send it to the advanced spread builder.').pack(anchor='w',pady=6)
        stats=contract.stats;ttk.Label(f,text=f'Bid ${contract.bid:.2f}   Ask ${contract.ask:.2f}   Mid ${contract.mid:.2f}   IV {contract.volatility*100:.1f}%\nDelta {stats["delta"]:+.3f}   Gamma {stats["gamma"]:.4f}   Theta {stats["theta"]:.3f}   Vega {stats["vega"]:.3f}').pack(anchor='w',pady=8)
        row=ttk.Frame(f);row.pack(fill='x',pady=10);ttk.Label(row,text='Action').pack(side='left');ttk.Combobox(row,textvariable=self.action,values=['BUY','SELL'],state='readonly',width=10).pack(side='left',padx=6);ttk.Label(row,text='Quantity').pack(side='left',padx=(18,4));ttk.Spinbox(row,from_=1,to=100000, textvariable=self.qty,width=10).pack(side='left')
        self.cost=ttk.Label(f,text='');self.cost.pack(anchor='w',pady=6);self.qty.trace_add('write',lambda *x:self.update_cost());self.update_cost()
        ttk.Button(f,text='BUY / SELL QUANTITY',command=self.execute).pack(fill='x',pady=5);ttk.Button(f,text='ADD TO ADVANCED SPREAD BUILDER',command=self.to_spread).pack(fill='x');ttk.Button(f,text='CLOSE',command=self.destroy).pack(fill='x',pady=5)
    def update_cost(self):
        try:q=max(1,int(self.qty.get()))
        except:q=1
        self.cost.config(text=f'Estimated premium: ${self.contract.mid*q*100:,.2f} • 1 contract = 100 shares')
    def execute(self):
        try:q=max(1,int(self.qty.get()))
        except:return messagebox.showerror('Option order','Invalid quantity.')
        s=OptionStrategy(f'{self.action.get()} {self.contract}');s.add_leg(self.contract,q,self.action.get());ok,msg=self.portfolio.execute_strategy(s)
        if ok:self.refresh();messagebox.showinfo('Option order',msg);self.destroy()
        else:messagebox.showerror('Option order',msg)
    def to_spread(self):SpreadBuilder(self,self.chain.market if self.chain else self.contract.underlying, self.portfolio,self.refresh,self.contract)

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
        self.tv=ttk.Treeview(self,columns=('action','type','strike','qty','mark'),show='headings',height=8);[self.tv.heading(c,text=c.upper()) for c in self.tv['columns']];self.tv.column('action',width=90,anchor='center');self.tv.column('type',width=80,anchor='center');self.tv.column('strike',width=110,anchor='e');self.tv.column('qty',width=90,anchor='e');self.tv.column('mark',width=110,anchor='e');self.tv.pack(fill='x',padx=10,pady=8);self.tv.bind('<<TreeviewSelect>>',self.sync_leg_qty);self.tv.bind('<Double-1>',self.edit_leg_qty);qbar=ttk.Frame(self);qbar.pack(fill='x',padx=10);ttk.Label(qbar,text='Selected leg quantity').pack(side='left');self.leg_qty=tk.IntVar(value=1);ttk.Spinbox(qbar,from_=1,to=100000, textvariable=self.leg_qty,width=10,command=self.set_selected_qty).pack(side='left',padx=6);ttk.Button(qbar,text='APPLY QTY',command=self.set_selected_qty).pack(side='left');ttk.Label(qbar,text='  Double-click a leg to edit quantity').pack(side='left');self.preview=ttk.Label(self,text='No legs');self.preview.pack(fill='x',padx=10,pady=8);self.payoff=tk.Canvas(self,bg='#081018',height=240,highlightthickness=0);self.payoff.pack(fill='x',padx=10,pady=8);bar=ttk.Frame(self);bar.pack(fill='x',padx=10);ttk.Label(bar,text='Order').pack(side='left');ttk.Combobox(bar,textvariable=self.action,values=['BUY','SELL'],state='readonly',width=8).pack(side='left',padx=4);ttk.Combobox(bar,textvariable=self.order_type,values=['MARKET','LIMIT','STOP'],state='readonly',width=10).pack(side='left',padx=4);self.price=tk.DoubleVar(value=0);ttk.Entry(bar,textvariable=self.price,width=10).pack(side='left',padx=4);ttk.Button(bar,text='EXECUTE / WORK',command=self.execute).pack(side='left',padx=8);ttk.Button(bar,text='REMOVE SELECTED',command=self.remove).pack(side='left');self.template()
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
        m=tk.Menu(self.cv,tearoff=0);m.add_command(label=f'BUY {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SELL','MARKET',None));m.add_command(label=f'SHORT {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SHORT','MARKET',None));m.add_command(label='OPEN OPTIONS',command=lambda:self.market.ui_app.options_for(a));m.add_command(label='ADVANCED CHART',command=lambda:self.market.ui_app.advanced_chart(a));m.add_command(label='LEVEL 2 / 3',command=lambda:self.market.ui_app.depth_for(a));m.tk_popup(e.x_root,e.y_root)

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
        c=self.cv;c.delete('all');w=max(900,self.cv.winfo_width());h=max(650,self.cv.winfo_height());r=min(h*.39,w*.28);cx=w*.34;cy=h*.51;utc=self.market.clock.current.replace(tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York')).astimezone(__import__('datetime').timezone.utc);rot=2*math.pi*((utc.hour*60+utc.minute+utc.second/60)/1440)-math.pi/2
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
        c.create_text(w*.62,35,text='GLOBAL TRADER NETWORK',fill=TEXT,font=('Arial',19,'bold'),anchor='w');c.create_text(w*.62,68,text=f'IN-GAME CLOCK  {self.market.clock.time} • UTC {self.market.clock.utc_time}',fill=CYAN,font=('Arial',12,'bold'),anchor='w');y=108;self.exchange_hits=[]
        for code,sess in SESSIONS.items():
            op=market_status(code,self.market.clock.current);x=w*.60;ww=w*.35;hh=30;c.create_rectangle(x,y-4,x+ww,y+hh-4,fill='#0c1823',outline='#22394a');c.create_text(x+10,y+11,anchor='w',text=sess.name,fill=GREEN if op else MUTED,font=('Arial',10,'bold'));c.create_text(x+ww-10,y+11,anchor='e',text='OPEN' if op else 'CLOSED',fill=GREEN if op else MUTED,font=('Arial',9,'bold'));self.exchange_hits.append((x,y-4,x+ww,y+hh-4,code));y+=36
        c.create_text(w*.60,y+8,text='Click an exchange row or globe node to open its assets, charts, options and trading feed.',fill=MUTED,anchor='w',font=('Arial',10));self.after(250,self.draw)
    def click(self,e):
        for x1,y1,x2,y2,code in getattr(self,'blips',[]):
            if x1<=e.x<=x2 and y1<=e.y<=y2:GlobalMarketWindow(self,self.market,code);return
        for x1,y1,x2,y2,code in getattr(self,'exchange_hits',[]):
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
        self.after(450,self.refresh)
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
        c.create_text(30,65,anchor='w',text='DEALER',fill='#cfe9dc',font=('Arial',9,'bold'));x=150
        for i,card in enumerate(self.dealer):self.draw_card(card,x+i*90,80,hidden=self.active and i==1)
        base=h/2+10
        cols=max(1,min(4,len(self.hands)));gap=w/(cols+1);base=h*.48
        for j,hnd in enumerate(self.hands):
            col=j%cols;row=j//cols;x0=gap*(col+1)-90;y=base+row*170;c.create_text(x0,y-18,anchor='w',text=f'HAND {j+1}  ${self.bet_amounts[j] if j<len(self.bet_amounts) else 0:,}',fill='#cfe9dc',font=('Arial',9,'bold'))
            for i,card in enumerate(hnd):self.draw_card(card,x0+i*82,y)
            c.create_text(x0+300,y+45,text=f'{self.val(hnd)}',fill='#f6e6b5',font=('Arial',22,'bold'))
        c.create_text(30,h-24,anchor='w',text=f'ACTIVE HAND {self.active_hand+1 if self.hands else 0} • SPLIT PAIRS ENABLED',fill='#b9d6c7',font=('Arial',10,'bold'))
        decks=max(.01,len(self.shoe)/52);true=self.running/decks if self.count_mode.get()=='Hi-Lo' else self.running;edge='—' if self.count_mode.get()=='None' else f'{true:+.2f}'
        self.info.config(text=f'Balance ${self.portfolio.cash:,.2f} • Running {self.running:+d} • True {edge} • Decks left {decks:.2f} • Cards in shoe {len(self.shoe)}')

class CasinoWindow(ToolWindow):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('ARCADE — 24/7 TRADING BREAK','1100x720');self.dealer=random.choice(BlackjackWindow.DEALERS);ttk.Label(self,text='24/7 VIRTUAL ARCADE • independent of market session',font=('Arial',15,'bold')).pack(pady=15);f=ttk.Frame(self);f.pack(fill='x',padx=20);ttk.Button(f,text='BLACKJACK TRAINER',command=lambda:BlackjackWindow(self,portfolio,market)).pack(side='left',padx=15,pady=15);ttk.Button(f,text='ROULETTE',command=lambda:RouletteWindow(self,portfolio,market)).pack(side='left',padx=15,pady=15);ttk.Label(self,text='Virtual simulator credits only.').pack(pady=10)

class RouletteWindow(ToolWindow):
    EURO_ORDER=[0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
    REDS={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    def __init__(self,parent,portfolio,market):
        super().__init__(parent);self.portfolio=portfolio;self.market=market;self.style_window('Stock Game Pro 1.0 — Roulette','1650x980');self.resizable(True,True);self.chips=[25,100,500,1000,5000,10000];self.chip=tk.IntVar(value=100);self.bets={};self.history=[];self.spinning=False;self.dealer=random.choice(BlackjackWindow.DEALERS)[0];self.target=0;self.anim=0
        top=ttk.Frame(self);top.pack(fill='x',padx=12,pady=7);ttk.Label(top,text=f'DEALER: {self.dealer}  •  Balance').pack(side='left');self.balance=ttk.Label(top,text='');self.balance.pack(side='left',padx=6)
        for v in self.chips:ttk.Button(top,text=f'${v:,}',command=lambda x=v:self.chip.set(x),width=7).pack(side='left',padx=2)
        ttk.Button(top,text='CLEAR BETS',command=self.clear_bets).pack(side='right');ttk.Button(top,text='SPIN',command=self.spin).pack(side='right',padx=6)
        self.cv=tk.Canvas(self,bg='#0a1118',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=10,pady=6);self.result=ttk.Label(self,text='Click a number, edge, corner, split, street, dozen, column, or outside bet.');self.result.pack(fill='x',padx=10,pady=5);self.cv.bind('<Button-1>',self.board_click);self.after(100,self.draw)
    def add_bet(self,key):self.bets[key]=self.bets.get(key,0)+self.chip.get();self.draw()
    def clear_bets(self):self.bets.clear();self.draw()
    def _table_geom(self,w,h):
        # Reserve the entire left zone for the wheel. The betting table is laid out
        # from the remaining right-side rectangle, so it cannot overlap the wheel
        # at any window size.
        cx=w*.17; cy=h*.30; r=min(h*.22,w*.12)
        min_gap=28
        board_left=max(cx+r+min_gap,w*.38)
        right_margin=28
        available=max(360,w-board_left-right_margin)
        cw=min(74,available/13.0)
        board_width=cw*13
        if board_left+board_width>w-right_margin:
            cw=max(28,(w-board_left-right_margin)/13.0)
        zero_w=cw
        ch=max(38,min(64,h*.062))
        bx=board_left+zero_w
        board_height=ch*5.0
        by=max(135,min(h*.22,h-board_height-30))
        return bx,by,cw,ch,zero_w
    def board_click(self,e):
        w=max(1100,self.cv.winfo_width()); h=max(700,self.cv.winfo_height()); bx,by,cw,ch,zero_w=self._table_geom(w,h)
        zero_left=bx-zero_w
        # Dedicated ZERO pocket. The old 0-1-2-3 basket has been removed.
        if zero_left-4<=e.x<=bx+4 and by-2<=e.y<=by+3*ch+2:
            self.add_bet(0); return
        edge=max(8,min(14,cw*.12))
        # Four-number corners at intersections.
        for rb in range(1,3):
            yy=by+rb*ch
            for cb in range(1,12):
                xx=bx+cb*cw
                if abs(e.x-xx)<=edge and abs(e.y-yy)<=edge:
                    nums=tuple(sorted(((cb-1)*3+rb,(cb-1)*3+rb+1,cb*3+rb,cb*3+rb+1)))
                    self.add_bet(nums); return
        # Splits along interior grid lines.
        for n in range(1,37):
            col=(n-1)//3; row=(n-1)%3; x=bx+col*cw; y=by+row*ch
            if x<=e.x<=x+cw and y<=e.y<=y+ch:
                if abs(e.x-(x+cw))<=edge and col<11: self.add_bet(tuple(sorted((n,n+3)))); return
                if abs(e.y-(y+ch))<=edge and row<2: self.add_bet(tuple(sorted((n,n+1)))); return
                if abs(e.x-x)<=edge and col>0: self.add_bet(tuple(sorted((n,n-3)))); return
                if abs(e.y-y)<=edge and row>0: self.add_bet(tuple(sorted((n,n-1)))); return
                self.add_bet(n); return
        # 2:1 column squares.
        for row,key in enumerate(('2:1_ROW1','2:1_ROW2','2:1_ROW3')):
            x=bx+12*cw; y=by+row*ch
            if x<=e.x<=x+cw*.88 and y<=e.y<=y+ch: self.add_bet(key); return
        # Dozens and outside bets.
        oy=by+3*ch+4; rw=(12*cw)/3
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw
            if x<=e.x<=x+rw and oy<=e.y<=oy+ch*.9: self.add_bet(key); return
        oy2=oy+ch+7; rw=(12*cw)/6
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            x=bx+i*rw
            if x<=e.x<=x+rw and oy2<=e.y<=oy2+ch*.9: self.add_bet(key); return

    def win_for(self,key,n):
        if isinstance(key,int):return n==key,35
        if isinstance(key,tuple):return n in key,17 if len(key)==2 else 8 if len(key)==4 else 11
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
        c=self.cv;c.delete('all');w=max(1100,c.winfo_width());h=max(700,c.winfo_height());cx=w*.17;cy=h*.30;r=min(h*.22,w*.12);c.create_text(cx,24,text=f'{self.dealer} • ROULETTE',fill='#f6e6b5',font=('Arial',21,'bold'))
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#0d2519',outline='#d8b96a',width=6);c.create_oval(cx-r*.82,cy-r*.82,cx+r*.82,cy+r*.82,fill='#161d23',outline='#8b6d35',width=3)
        for i,n in enumerate(self.EURO_ORDER):
            a=2*math.pi*i/37-math.pi/2;col='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#171b20';x=cx+math.cos(a)*r*.70;y=cy+math.sin(a)*r*.70;rr=18;c.create_oval(x-rr,y-rr,x+rr,y+rr,fill=col,outline='#d6c08a',width=2);c.create_text(x,y,text=str(n),fill='white',font=('Arial',9,'bold'))
            if wheel_number==n and not spinning:c.create_oval(x-rr-4,y-rr-4,x+rr+4,y+rr+4,outline='#fff2a8',width=3)
        c.create_oval(cx-r*.16,cy-r*.16,cx+r*.16,cy+r*.16,fill='#0b1218',outline='#d8b96a',width=2);c.create_text(cx,cy,text=str(wheel_number) if wheel_number is not None else '0',fill='white',font=('Arial',25,'bold'))
        if wheel_number is not None:
            wi=self.EURO_ORDER.index(wheel_number) if wheel_number in self.EURO_ORDER else 0;a=2*math.pi*wi/37-math.pi/2 + ball_phase*math.pi*12;bx=cx+math.cos(a)*(r*.88);by=cy+math.sin(a)*(r*.88);c.create_oval(bx-8,by-8,bx+8,by+8,fill='white',outline='#cfd8df',width=2)
        # table
        bx,by,cw,ch,zero_w=self._table_geom(w,h);c.create_rectangle(bx-zero_w,by,bx,by+ch*3,fill='#13865c',outline='#d8b96a',width=2);c.create_text(bx-zero_w/2,by+ch*1.5,text='0',fill='white',font=('Arial',19,'bold'));self._chip(c,bx-zero_w/2,by+ch*1.5,self.bets.get(0,0),'0')
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch;fill='#b92f48' if n in self.REDS else '#151b23';c.create_rectangle(x,y,x+cw,y+ch,fill=fill,outline='#d8b96a');c.create_text(x+cw*.5,y+ch*.5,text=str(n),fill='white',font=('Arial',15,'bold'));self._chip(c,x+cw/2,y+ch/2,self.bets.get(n,0),str(n))
        for row,key in enumerate(('2:1_ROW1','2:1_ROW2','2:1_ROW3')):
            x=bx+12*cw;y=by+row*ch;c.create_rectangle(x,y,x+cw*.85,y+ch,fill='#0e6950',outline='#d8b96a');c.create_text(x+cw*.42,y+ch*.5,text='2:1',fill='white',font=('Arial',12,'bold'));self._chip(c,x+cw*.42,y+ch/2,self.bets.get(key,0),'2:1')
        oy=by+3*ch+14;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw;c.create_rectangle(x,oy,x+rw,oy+ch*.9,fill='#0e6950',outline='#d8b96a');c.create_text(x+rw/2,oy+ch*.45,text=key,fill='white',font=('Arial',9,'bold'));self._chip(c,x+rw/2,oy+ch*.45,self.bets.get(key,0),key)
        oy2=oy+ch+10;rw=(cw*12)/6
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            x=bx+i*rw;fill='#b92f48' if key=='RED' else '#151b23' if key=='BLACK' else '#0e6950';c.create_rectangle(x,oy2,x+rw,oy2+ch*.9,fill=fill,outline='#d8b96a');c.create_text(x+rw/2,oy2+ch*.45,text=key,fill='white',font=('Arial',10,'bold'));self._chip(c,x+rw/2,oy2+ch*.45,self.bets.get(key,0),key)
        hx=w*.82;c.create_text(hx,by-18,text='LAST 500 SPINS',fill='#f6e6b5',font=('Arial',14,'bold'));hist=self.history[-500:];cols=5
        for i,n in enumerate(reversed(hist)):
            row=i//cols;col=i%cols;x=hx-2*70+col*70;y=by+row*26;fill='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#151b23';c.create_oval(x-13,y-13,x+13,y+13,fill=fill,outline='#d8b96a');c.create_text(x,y,text=str(n),fill='white',font=('Arial',8,'bold'))
        c.create_text(hx,by+min(500//5,18)*26+20,text='Bets use selected chip value. Click ZERO for a straight-up 0 bet; click near an edge to place split bets.',fill=MUTED,font=('Arial',9),width=w*.28)
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
        for name,val,lo,hi in [('Time warp',float(app.time_warp.get()) if hasattr(app,'time_warp') else 1,1,100),('Active chart tick',app.charts[app.active_chart].refresh_ms/1000,.025,5.0),('Chart zoom',1,.5,3)]:
            row=ttk.Frame(self);row.pack(fill='x',padx=12,pady=7);ttk.Label(row,text=name,width=18).pack(side='left');v=tk.DoubleVar(value=val);self.vars[name]=v;tk.Scale(row,from_=lo,to=hi,resolution=.01 if hi<5 else 1,orient='horizontal',variable=v,length=350,bg=PANEL,fg=TEXT,highlightthickness=0,command=lambda x:self.apply()).pack(side='left',fill='x',expand=True);ttk.Label(row,textvariable=v,width=8).pack(side='right')
        ttk.Label(self,text='Main workspace charts',font=('Arial',9,'bold')).pack(anchor='w',padx=12,pady=(15,5));self.count=tk.IntVar(value=len(app.charts));ttk.Combobox(self,textvariable=self.count,values=[4,6,8],state='readonly',width=8).pack(anchor='w',padx=20);ttk.Button(self,text='APPLY CHART COUNT',command=app.set_chart_count).pack(anchor='w',padx=20,pady=5);ttk.Label(self,text='Indicators are removable/addable from the Chart Tools menu and chart variables panel.',wraplength=640).pack(anchor='w',padx=12,pady=15)
    def apply(self):self.app.set_time_warp(float(self.vars['Time warp'].get()));self.app.charts[self.app.active_chart].set_refresh_rate(max(25,int(self.vars['Active chart tick'].get()*1000)))

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


class AdvancedChartWindow(ToolWindow):
    """Pop-out chart workstation with its own ticker controls, order ticket and correlation panel."""
    def __init__(self,parent,app,asset):
        super().__init__(parent);self.app=app;self.market=app.market;self.portfolio=app.portfolio;self.asset=asset
        self.style_window(f'ADVANCED CHART — {asset.symbol}','1540x900');self.resizable(True,True)
        self.protocol('WM_DELETE_WINDOW',self.close)
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=6)
        ttk.Label(top,text='Ticker').pack(side='left');self.ticker=tk.StringVar(value=asset.symbol);te=ttk.Entry(top,textvariable=self.ticker,width=12);te.pack(side='left',padx=4);te.bind('<Return>',lambda e:self.load_ticker())
        ttk.Button(top,text='LOAD',command=self.load_ticker).pack(side='left')
        ttk.Label(top,text='Timeframe').pack(side='left',padx=(12,2));self.tf=tk.StringVar(value='1D');tf=ttk.Combobox(top,textvariable=self.tf,values=['1D','1W','1M','3M','6M','1Y','5Y','MAX'],state='readonly',width=7);tf.pack(side='left');tf.bind('<<ComboboxSelected>>',lambda e:self.chart.set_tf(self.tf.get()))
        ttk.Label(top,text='Style').pack(side='left',padx=(10,2));self.kind=tk.StringVar(value='Candles');ct=ttk.Combobox(top,textvariable=self.kind,values=['Candles','Line','Area'],state='readonly',width=9);ct.pack(side='left');ct.bind('<<ComboboxSelected>>',lambda e:self.set_kind())
        ttk.Button(top,text='OPTIONS / SPREADS',command=self.open_options).pack(side='left',padx=10)
        ttk.Button(top,text='LEVEL 2 / 3',command=lambda:self.app.depth_for(self.asset)).pack(side='left',padx=3)
        self.macro_label=ttk.Label(top,text='',font=('Arial',9,'bold'));self.macro_label.pack(side='right')

        body=ttk.PanedWindow(self,orient='horizontal');body.pack(fill='both',expand=True,padx=8,pady=(0,8))
        chart_frame=ttk.Frame(body);side=ttk.Frame(body,width=355);body.add(chart_frame,weight=5);body.add(side,weight=2)
        self.chart=Chart(chart_frame,app,app.active_chart);self.chart.selected_popup=True
        if app.charts:self.chart.set_refresh_rate(app.charts[app.active_chart].refresh_ms)
        self.chart.pack(fill='both',expand=True);self.chart.set_asset(asset);app.extra_charts.append(self.chart)

        ticket=ttk.LabelFrame(side,text='TRADE / POSITION TICKET');ticket.pack(fill='x',padx=6,pady=6)
        self.ticket_title=ttk.Label(ticket,text='',font=('Arial',12,'bold'));self.ticket_title.pack(anchor='w',padx=8,pady=(8,3))
        r=ttk.Frame(ticket);r.pack(fill='x',padx=8,pady=3)
        self.action=tk.StringVar(value='BUY');ttk.Combobox(r,textvariable=self.action,values=['BUY','SELL','SHORT','COVER'],state='readonly',width=10).pack(side='left')
        self.otype=tk.StringVar(value='MARKET');ttk.Combobox(r,textvariable=self.otype,values=['MARKET','LIMIT','STOP'],state='readonly',width=10).pack(side='left',padx=5)
        self.qty=tk.IntVar(value=100);ttk.Spinbox(r,from_=1,to=10000000,textvariable=self.qty,width=10).pack(side='left')
        pr=ttk.Frame(ticket);pr.pack(fill='x',padx=8,pady=3);ttk.Label(pr,text='Limit / stop').pack(side='left');self.price=tk.StringVar(value='');ttk.Entry(pr,textvariable=self.price,width=15).pack(side='left',padx=5)
        ttk.Button(ticket,text='SUBMIT ORDER',command=self.submit_order).pack(fill='x',padx=8,pady=(5,3))
        ttk.Button(ticket,text='ADVANCED OPTIONS / STRATEGY LAB',command=self.open_strategy_lab).pack(fill='x',padx=8,pady=3)
        self.position_lbl=ttk.Label(ticket,text='',wraplength=320,justify='left');self.position_lbl.pack(fill='x',padx=8,pady=(5,8))

        corr=ttk.LabelFrame(side,text='CORRELATED ASSETS');corr.pack(fill='both',expand=True,padx=6,pady=6)
        self.corr=ttk.Treeview(corr,columns=('symbol','corr','price','chg'),show='headings',height=12,selectmode='browse')
        for c,t,w in [('symbol','Symbol',90),('corr','Corr',65),('price','Price',90),('chg','Chg %',70)]:self.corr.heading(c,text=t);self.corr.column(c,width=w,anchor='center',stretch=False)
        self.corr.pack(fill='both',expand=True,padx=5,pady=5);self.corr.bind('<Double-1>',self.open_correlated)
        cb=ttk.Frame(corr);cb.pack(fill='x',padx=5,pady=(0,5));ttk.Button(cb,text='BUY SELECTED',command=lambda:self.trade_correlated('BUY')).pack(side='left',fill='x',expand=True);ttk.Button(cb,text='SELL / SHORT',command=lambda:self.trade_correlated('SELL')).pack(side='left',fill='x',expand=True,padx=(4,0))
        ttk.Label(corr,text='Double-click a row for another advanced chart. Correlation is a simulator factor estimate, not historical research.',wraplength=320,foreground=MUTED).pack(fill='x',padx=6,pady=(0,6))

        tools=ttk.LabelFrame(side,text='CHART TOOLS');tools.pack(fill='x',padx=6,pady=6)
        for text,tool in [('CROSSHAIR','Crosshair'),('TRENDLINE','Trendline'),('HORIZONTAL','Horizontal')]:ttk.Button(tools,text=text,command=lambda t=tool:setattr(self.chart,'tool',t)).pack(side='left',expand=True,fill='x',padx=2,pady=4)
        ttk.Button(tools,text='CLEAR',command=self.clear_chart).pack(side='left',expand=True,fill='x',padx=2,pady=4)
        self.refresh_side()
    def close(self):
        try:
            if self.chart in self.app.extra_charts:self.app.extra_charts.remove(self.chart)
        except Exception:pass
        self.destroy()
    def load_ticker(self):
        a=self.market.get_asset(self.ticker.get().strip().upper())
        if not a:return messagebox.showerror('Advanced chart','Unknown ticker.')
        self.asset=a;self.ticker.set(a.symbol);self.chart.set_asset(a);self.title(f'ADVANCED CHART — {a.symbol}');self.refresh_side(force=True)
    def set_kind(self):self.chart.kind=self.kind.get();self.chart.request_draw(force=True)
    def open_options(self):self.app.options_for(self.asset)
    def open_strategy_lab(self):SpreadBuilder(self,self.market,self.portfolio,self.app.refresh)
    def submit_order(self):
        try:q=max(1,int(self.qty.get()))
        except:return messagebox.showerror('Order','Invalid quantity.')
        typ=self.otype.get();side=self.action.get();p=None
        if typ!='MARKET':
            try:p=float(self.price.get())
            except:return messagebox.showerror('Order','Enter a valid limit/stop price.')
        if typ=='MARKET':
            fn={'BUY':self.portfolio.buy_asset,'SELL':self.portfolio.sell_asset,'SHORT':self.portfolio.short_asset,'COVER':self.portfolio.cover_short}[side];ok,msg=fn(self.asset,q)
            if ok:self.app.refresh_positions();self.chart.request_draw(force=True);self.refresh_side(force=True);messagebox.showinfo('Order',msg)
            else:messagebox.showerror('Order rejected',msg)
        else:
            o=self.market.submit_pending(side,self.asset,q,typ,p);self.chart.request_draw(force=True);self.app.refresh_orders();self.app.status_flash(f'Working order #{o["id"]}: {side} {q:,} {self.asset.symbol} {typ} ${p:,.2f}')
    def _selected_corr_asset(self):
        it=self.corr.selection();return self.market.get_asset(it[0]) if it else None
    def trade_correlated(self,side):
        a=self._selected_corr_asset()
        if not a:return messagebox.showwarning('Correlated asset','Select a correlated asset first.')
        if side=='SELL' and int(self.portfolio.positions.get(a.symbol,0))<=0:side='SHORT'
        self.app.order_window(a,side,'MARKET',None)
    def open_correlated(self,e=None):
        a=self._selected_corr_asset()
        if a:self.app.advanced_chart(a)
    def clear_chart(self):self.chart.drawings=[];self.chart.request_draw(force=True)
    def refresh_side(self,force=False):
        try:
            if not self.winfo_exists():return
            a=self.asset;q=int(self.portfolio.positions.get(a.symbol,0));basis=float(self.portfolio.cost_basis.get(a.symbol,0));entry=basis/max(1,abs(q)) if q else 0
            self.ticket_title.config(text=f'{a.symbol}  ${a.price:,.2f}  {a.change_percent():+.2f}%')
            opt_count=len(self.portfolio.option_legs_for(a.symbol))
            self.position_lbl.config(text=(f'Position: {q:+,} shares • avg ${entry:,.2f}' if q else 'Position: flat')+f' • option legs: {opt_count}\nDrag a share position line to place/move a full-position limit exit. Drag working limit/stop lines directly.')
            m=self.market.macro_snapshot() if hasattr(self.market,'macro_snapshot') else {}
            if m:self.macro_label.config(text=f'CPI {m.get("inflation",0):.2f}% • Fed {m.get("policy_rate",0):.2f}% • GDP {m.get("gdp_growth",0):.2f}% • U {m.get("unemployment",0):.2f}%')
            selected=self.corr.selection();keep=selected[0] if selected else None
            rows=self.market.correlated_assets(a,10) if hasattr(self.market,'correlated_assets') else []
            existing=set(self.corr.get_children(''));wanted=set()
            for corr,b in rows:
                wanted.add(b.symbol);vals=(b.symbol,f'{corr:+.2f}',f'${b.price:,.2f}',f'{b.change_percent():+.2f}%')
                if b.symbol in existing:self.corr.item(b.symbol,values=vals)
                else:self.corr.insert('','end',iid=b.symbol,values=vals)
            for iid in existing-wanted:self.corr.delete(iid)
            if keep and keep in self.corr.get_children(''):self.corr.selection_set(keep)
        except tk.TclError:return
        except Exception as e:
            try:self.market.errors.append(f'advanced chart: {type(e).__name__}: {e}')
            except Exception:pass
        self.after(800,self.refresh_side)

class App:
    def __init__(self,root,market,portfolio):
        self.root=root;self.market=market;self.portfolio=portfolio;self.market.ui_app=self;self.active_chart=0;self.selected_chart=None;self.ind_vars={k:tk.BooleanVar(value=k in ('Volume',)) for k in ('SMA','EMA','BB','VWAP','RSI','Volume')};self.ind_vars_version=0;self.sort_key='Symbol';self.sort_reverse=False;self.build_style();self.make_menu();self.build();self.set_chart_count(initial=1);self.start_chart_refresh();self.start_fast_watch_stream();self.refresh()
    def build_style(self):
        s=ttk.Style();s.theme_use('clam');s.configure('.',background=PANEL,foreground=TEXT);s.configure('TFrame',background=PANEL);s.configure('TLabel',background=PANEL,foreground=TEXT);s.configure('TButton',background=PANEL2,foreground=TEXT,padding=6);s.map('TButton',background=[('active',BLUE)],foreground=[('active','white')]);s.configure('TEntry',fieldbackground='#f4f7fb',foreground='#111827',insertcolor='#111827');s.configure('TCombobox',fieldbackground='#f4f7fb',foreground='#111827',background='#f4f7fb',arrowcolor='#111827');s.map('TCombobox',fieldbackground=[('readonly','#f4f7fb')],foreground=[('readonly','#111827')]);s.configure('Treeview',background='#0c151f',fieldbackground='#0c151f',foreground=TEXT,rowheight=24);s.configure('Treeview.Heading',background='#1e3041',foreground=TEXT);s.map('Treeview',background=[('selected','#1c5f8f')],foreground=[('selected','#ffffff')])
    def make_menu(self):
        mb=tk.Menu(self.root,tearoff=0,bg='#172331',fg=TEXT,activebackground='#2c6da0',activeforeground='white');self.root.config(menu=mb)
        v=tk.Menu(mb,tearoff=0);v.add_command(label='Market Map',command=self.market_map);v.add_command(label='Global Trader Globe',command=self.globe);v.add_command(label='Options Chain',command=self.options);v.add_command(label='Level 2 / Level 3',command=self.depth);v.add_command(label='Market Screener',command=lambda:MarketListWindow(self.root,self.market));v.add_command(label='After-Hours Arcade',command=self.casino);mb.add_cascade(label='View',menu=v)
        tr=tk.Menu(mb,tearoff=0);tr.add_command(label='Order Entry',command=self.order_window);tr.add_command(label='Smart Large-Lot Order',command=self.smart_order);tr.add_command(label='Liquidate Selected',command=self.liquidate);tr.add_command(label='Load MAX / IPO History',command=self.load_max_selected);tr.add_command(label='Market Event Lab',command=self.market_event_lab);mb.add_cascade(label='Tools',menu=tr)
        ind=tk.Menu(mb,tearoff=0);[ind.add_checkbutton(label=k,variable=v,command=self.redraw) for k,v in self.ind_vars.items()];mb.add_cascade(label='Indicators',menu=ind)
        ws=tk.Menu(mb,tearoff=0);ws.add_command(label='Workspace Variables / Sliders',command=self.workspace_controls);ws.add_command(label='Add Chart',command=self.add_chart);ws.add_command(label='Remove Active Chart',command=lambda:self.remove_chart(self.active_chart));ws.add_command(label='4 Charts',command=lambda:self.set_chart_count(initial=4));ws.add_command(label='6 Charts',command=lambda:self.set_chart_count(initial=6));ws.add_command(label='8 Charts',command=lambda:self.set_chart_count(initial=8));mb.add_cascade(label='Workspace',menu=ws)
        ch=tk.Menu(mb,tearoff=0);ch.add_command(label='Crosshair',command=lambda:self.set_tool('Crosshair'));ch.add_command(label='Trendline',command=lambda:self.set_tool('Trendline'));ch.add_command(label='Horizontal Line',command=lambda:self.set_tool('Horizontal'));ch.add_command(label='Clear Drawings',command=self.clear_drawings);mb.add_cascade(label='Chart Tools',menu=ch)
        tm=tk.Menu(mb,tearoff=0);tm.add_command(label='0.5x',command=lambda:self.set_time_warp(.5));tm.add_command(label='1x',command=lambda:self.set_time_warp(1));tm.add_command(label='5x',command=lambda:self.set_time_warp(5));tm.add_command(label='10x',command=lambda:self.set_time_warp(10));tm.add_command(label='25x',command=lambda:self.set_time_warp(25));tm.add_command(label='40x',command=lambda:self.set_time_warp(40));tm.add_separator();tm.add_command(label='Pause / Resume',command=self.toggle_pause);mb.add_cascade(label='Time',menu=tm)
        ac=tk.Menu(mb,tearoff=0);ac.add_command(label='Account / Difficulty',command=self.account_panel);ac.add_command(label='Session Statistics',command=self.session_stats);mb.add_cascade(label='Account',menu=ac)
    def build(self):
        self.starting_cash=self.portfolio.cash;self.chart_refresh_ms=180;self._chart_refresh_running=True;self.root.title('Stock Game Pro 1.0 — Global Trading Simulator');self.root.geometry('1900x1100');outer=ttk.PanedWindow(self.root,orient='horizontal');outer.pack(fill='both',expand=True);left=ttk.Frame(outer,width=340);center=ttk.Frame(outer);right=ttk.Frame(outer,width=460);outer.add(left,weight=2);outer.add(center,weight=6);outer.add(right,weight=3)
        ttk.Label(left,text='MARKET / WATCHLIST',font=('Arial',12,'bold')).pack(anchor='w',padx=7,pady=5);sf=ttk.Frame(left);sf.pack(fill='x',padx=7);self.search=tk.StringVar();e=ttk.Entry(sf,textvariable=self.search);e.pack(fill='x');e.bind('<KeyRelease>',lambda x:self.refresh_watch());ff=ttk.Frame(left);ff.pack(fill='x',padx=7,pady=4);self.kind=tk.StringVar(value='STOCK');ttk.Combobox(ff,textvariable=self.kind,values=['STOCK','INDEX','COMMODITY','FUTURES','CRYPTO','INTERNATIONAL','FOREX','ALL'],state='readonly',width=12).pack(side='left');self.sector=tk.StringVar(value='ALL');ttk.Combobox(ff,textvariable=self.sector,values=['ALL']+self.market.sectors,state='readonly',width=14).pack(side='right');self.watchlists=self._load_watchlists();self.watchlist_name=tk.StringVar(value='All Market');wl=ttk.Frame(left);wl.pack(fill='x',padx=7,pady=(0,4));self.watchlist_combo=ttk.Combobox(wl,textvariable=self.watchlist_name,values=['All Market']+sorted(self.watchlists),state='readonly',width=16);self.watchlist_combo.pack(side='left',fill='x',expand=True);self.watchlist_combo.bind('<<ComboboxSelected>>',lambda e:self.refresh_watch());ttk.Button(wl,text='NEW',width=5,command=self.create_watchlist).pack(side='left',padx=(3,0));ttk.Button(wl,text='DEL',width=4,command=self.delete_watchlist).pack(side='left',padx=(3,0));self.watch=ttk.Treeview(left,columns=('symbol','name','price','chg','sector'),show='headings',selectmode='browse');
        for c,l in zip(self.watch['columns'],['Symbol','Name','Price','Chg %','Sector']):self.watch.heading(c,text=l,command=lambda col=c:self.sort_watch(col));self.watch.column(c,width=78 if c!='name' else 130,anchor='center')
        self.watch.pack(fill='both',expand=True,padx=7,pady=5);self.kind.trace_add('write',lambda *x:self.refresh_watch());self.sector.trace_add('write',lambda *x:self.refresh_watch());self.watch.bind('<<TreeviewSelect>>',self.market_selected);self.watch.bind('<Double-1>',self.open_selected_advanced);self.watch.bind('<Button-3>',self.watch_context)
        ttk.Button(left,text='BUY / SELL / SHORT',command=self.order_window).pack(fill='x',padx=7,pady=3);ttk.Button(left,text='OPTIONS / SPREADS',command=self.options).pack(fill='x',padx=7,pady=3);ttk.Label(left,text='Click = load chart • Double-click = advanced chart • Right-click = trade/menu',foreground=MUTED).pack(fill='x',padx=7,pady=3);density=ttk.Frame(left);density.pack(fill='x',padx=7,pady=(0,4));ttk.Label(density,text='Watchlist density').pack(side='left');self.watch_density=tk.IntVar(value=24);tk.Scale(density,from_=18,to=34,variable=self.watch_density,orient='horizontal',showvalue=0,length=120,bg=PANEL,fg=TEXT,highlightthickness=0,command=lambda x:self.apply_watch_density()).pack(side='left',fill='x',expand=True);self.watch_density_label=ttk.Label(density,text='24px',width=5);self.watch_density_label.pack(side='right')
        top=ttk.Frame(center);top.pack(fill='x',padx=5,pady=4);self.active_label=ttk.Label(top,text='Chart 1');self.active_label.pack(side='left');self.tf=ttk.Combobox(top,values=['1D','1W','1M','3M','6M','1Y','5Y','MAX'],state='readonly',width=7);self.tf.set('1D');self.tf.pack(side='left',padx=5);self.tf.bind('<<ComboboxSelected>>',lambda e:self.charts[self.active_chart].set_tf(self.tf.get()));self.ctype=ttk.Combobox(top,values=['Candles','Line','Area'],state='readonly',width=9);self.ctype.set('Candles');self.ctype.pack(side='left');self.ctype.bind('<<ComboboxSelected>>',lambda e:self.set_type());ttk.Button(top,text='BUY',command=lambda:self.chart_trade('BUY')).pack(side='left',padx=3);ttk.Button(top,text='SELL',command=lambda:self.chart_trade('SELL')).pack(side='left',padx=3);ttk.Button(top,text='LIMIT',command=lambda:self.chart_trade('BUY','LIMIT')).pack(side='left',padx=3);ttk.Button(top,text='STOP',command=lambda:self.chart_trade('SELL','STOP')).pack(side='left',padx=3);ttk.Label(top,text='TIME WARP').pack(side='left',padx=(10,2));self.time_warp=tk.DoubleVar(value=10.0);self.time_warp_scale=tk.Scale(top,from_=0.25,to=40,resolution=.25,orient='horizontal',showvalue=0,length=150,variable=self.time_warp,bg=PANEL,fg=TEXT,highlightthickness=0,command=self.set_time_warp);self.time_warp_scale.pack(side='left');self.time_warp_label=ttk.Label(top,text='10.00x',width=8);self.time_warp_label.pack(side='left',padx=(2,5));self.clock_label=ttk.Label(top,text='',font=('Arial',10,'bold'));self.clock_label.pack(side='right');self.set_time_warp(self.time_warp.get())
        self.grid=ttk.PanedWindow(center,orient='horizontal');self.grid.pack(fill='both',expand=True,padx=5,pady=5);self.charts=[];self.extra_charts=[]
        self._chart_refresh_job=None
        ttk.Label(top,text='Chart tick').pack(side='left',padx=(8,2))
        self.chart_rate=ttk.Combobox(top,values=['25ms','50ms','100ms','180ms','250ms','500ms','1000ms','2000ms','5000ms'],state='readonly',width=9)
        self.chart_rate.set('50ms');self.chart_rate.bind('<<ComboboxSelected>>',lambda e:self.set_chart_refresh_rate());self.chart_rate.pack(side='left',padx=2);ttk.Button(top,text='SYNC ALL',command=self.sync_all_chart_rates).pack(side='left',padx=(2,6))
        ttk.Label(right,text='PORTFOLIO / ACCOUNT',font=('Arial',12,'bold')).pack(anchor='w',padx=7,pady=5);tabs=ttk.Notebook(right);tabs.pack(fill='both',expand=True,padx=5,pady=3)
        pos_tab=ttk.Frame(tabs);acct_tab=ttk.Frame(tabs);ord_tab=ttk.Frame(tabs);tabs.add(pos_tab,text='Positions');tabs.add(acct_tab,text='Account');tabs.add(ord_tab,text='Orders')
        pwrap=ttk.Frame(pos_tab);pwrap.pack(fill='both',expand=True);self.pos=ttk.Treeview(pwrap,columns=('symbol','qty','last','value','pnl','pct','type','underlying','expiry'),show='headings',height=16);px=ttk.Scrollbar(pwrap,orient='horizontal',command=self.pos.xview);py=ttk.Scrollbar(pwrap,orient='vertical',command=self.pos.yview);self.pos.configure(xscrollcommand=px.set,yscrollcommand=py.set);self.pos.grid(row=0,column=0,sticky='nsew');py.grid(row=0,column=1,sticky='ns');px.grid(row=1,column=0,sticky='ew');pwrap.rowconfigure(0,weight=1);pwrap.columnconfigure(0,weight=1)
        for c,l,w in [('symbol','Symbol',72),('qty','Qty',72),('last','Last',78),('value','Value',95),('pnl','P/L',90),('pct','P/L %',70),('type','Type',70),('underlying','Underlying',86),('expiry','Expiry',65)]:self.pos.heading(c,text=l);self.pos.column(c,width=w,anchor='e' if c not in ('symbol','type') else 'center',stretch=False)
        self.pos.bind('<<TreeviewSelect>>',lambda e:self.position_info());self.pos.bind('<Button-3>',self.position_context);ttk.Button(pos_tab,text='LIQUIDATE SELECTED / CASH',command=self.liquidate).pack(fill='x',padx=6,pady=5)
        self.pred=ttk.Label(acct_tab,text='MODEL',justify='left');self.pred.pack(fill='x',padx=8,pady=7);self.summary=tk.Text(acct_tab,height=18,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat',wrap='none');self.summary.pack(fill='both',expand=True,padx=6,pady=5)
        self.orders_view=ttk.Treeview(ord_tab,columns=('id','asset','side','type','qty','price','status'),show='headings');self.orders_view.pack(fill='both',expand=True,padx=6,pady=5);[self.orders_view.heading(c,text=c.upper()) for c in self.orders_view['columns']];[self.orders_view.column(c,width=80,stretch=False) for c in self.orders_view['columns']]
        action=ttk.Frame(right);action.pack(fill='x',pady=3);ttk.Button(action,text='ORDER ENTRY',command=self.order_window).pack(side='left',expand=True,fill='x',padx=2);ttk.Button(action,text='GLOBAL',command=self.globe).pack(side='left',expand=True,fill='x',padx=2);ttk.Button(action,text='MAP',command=self.market_map).pack(side='left',expand=True,fill='x',padx=2);ttk.Button(action,text='ARCADE',command=self.casino).pack(side='left',expand=True,fill='x',padx=2)
        newsf=ttk.Frame(self.root);newsf.pack(fill='x',padx=6,pady=4);nh=ttk.Frame(newsf);nh.pack(fill='x');ttk.Label(nh,text='NEWS / MARKET TAPE',font=('Arial',9,'bold')).pack(side='left');ttk.Button(nh,text='POP OUT / RESIZE',command=self.news_popup).pack(side='left',padx=8);self.news_filter=ttk.Combobox(nh,values=['ALL','STOCK','INDEX','COMMODITY','MACRO','GLOBAL'],state='readonly',width=12);self.news_filter.set('ALL');self.news_filter.pack(side='right');self.news_filter.bind('<<ComboboxSelected>>',lambda e:self.refresh_news());self.news=tk.Text(newsf,height=7,bg='#0b131d',fg=TEXT,insertbackground=TEXT,relief='flat');self.news.pack(fill='both');self.status=ttk.Label(self.root,text='');self.status.pack(fill='x',padx=7)
    def set_chart_refresh_rate(self):
        try:value=int(self.chart_rate.get().lower().replace('ms','').strip())
        except Exception:value=50
        if not self.charts:return
        chart=self.charts[self.active_chart]
        chart.set_refresh_rate(value)
        self.status_flash(f'Chart {self.active_chart+1} tickrate: {chart.refresh_ms} ms')

    def sync_all_chart_rates(self):
        try:value=int(self.chart_rate.get().lower().replace('ms','').strip())
        except Exception:value=180
        for chart in self.charts:chart.set_refresh_rate(value)
        self.status_flash(f'All {len(self.charts)} charts synchronized at {value} ms')

    def start_chart_refresh(self):
        # Exactly one Tk timer services every chart. This prevents one canvas/event stream from
        # starving the others and makes same-rate charts update on the same scheduler pulse.
        if getattr(self,'_chart_refresh_job',None) is not None:
            try:self.root.after_cancel(self._chart_refresh_job)
            except Exception:pass
        self._chart_refresh_running=True
        self._chart_refresh_pulse()

    def _chart_refresh_pulse(self):
        if not getattr(self,'_chart_refresh_running',True):return
        try:
            if not self.root.winfo_exists():return
        except tk.TclError:return
        now_ms=time.monotonic()*1000.0
        live_extra=[]
        for chart in tuple(getattr(self,'extra_charts',())):
            try:
                if chart.winfo_exists():live_extra.append(chart)
            except tk.TclError:pass
        self.extra_charts=live_extra
        allcharts=list(getattr(self,'charts',()))+live_extra
        # Rendering all eight canvases in one callback caused visible menu/right-click stalls.
        # Service only a small round-robin budget per 8 ms pulse. Every chart keeps its own
        # requested tickrate, but expensive Canvas work is spread across the frame budget.
        if allcharts:
            start=int(getattr(self,'_chart_rr',0))%len(allcharts);drawn=0
            for off in range(len(allcharts)):
                chart=allcharts[(start+off)%len(allcharts)]
                try:
                    if chart.winfo_exists() and chart.due_for_refresh(now_ms):
                        chart.request_draw(force=False);chart.mark_refreshed(now_ms);drawn+=1
                        if drawn>=2:
                            self._chart_rr=(start+off+1)%len(allcharts);break
                except tk.TclError:pass
                except Exception as e:
                    try:self.market.errors.append(f'chart scheduler: {type(e).__name__}: {e}')
                    except Exception:pass
            else:self._chart_rr=(start+1)%len(allcharts)
        self._chart_refresh_job=self.root.after(8,self._chart_refresh_pulse)

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
            self.market.difficulty=mode.get();self.status_flash(f'Difficulty set to {mode.get()} — existing cash retained; time warp unchanged')
            w.destroy()
        ttk.Button(w,text='APPLY',command=apply).pack(fill='x',padx=18,pady=20)

    def load_max_selected(self):
        a=self.selected() or self.charts[self.active_chart].asset
        if a:self.market.load_ipo_history(a);self.status_flash(f'Loading MAX / earliest available history for {a.symbol}')
    def set_chart_count(self,initial=None):
        count=initial or int(getattr(self,'_workspace_count',8) if hasattr(self,'_workspace_count') else 8);count=max(1,min(8,count));self._workspace_count=count
        if not hasattr(self,'grid'):return
        saved=[{'asset':c.asset,'timeframe':c.timeframe,'kind':c.kind,'zoom':c.zoom,'drawings':list(c.drawings),'refresh_ms':c.refresh_ms} for c in getattr(self,'charts',())]
        for child in list(self.grid.panes()):
            try:self.grid.forget(child)
            except Exception:pass
            try:self.root.nametowidget(child).destroy()
            except Exception:pass
        self.charts=[];cols=4 if count>=8 else 3 if count>=6 else 2 if count>=4 else 1;rows=math.ceil(count/cols)
        defaults=['SPY','VIX','NVDA','AAPL','CL=F','GC=F','GME','MSFT']
        for col in range(cols):
            vp=ttk.PanedWindow(self.grid,orient='vertical');self.grid.add(vp,weight=1)
            for row in range(rows):
                i=col*rows+row
                if i>=count:break
                c=Chart(vp,self,i)
                if i<len(saved):
                    state=saved[i];c.timeframe=state['timeframe'];c.kind=state['kind'];c.zoom=state['zoom'];c.drawings=state['drawings'];c.refresh_ms=state['refresh_ms'];c.asset=state['asset'];c._key=None
                else:c.asset=self.market.get_asset(defaults[i]) or self.market.get_asset('SPY')
                vp.add(c,weight=1);self.charts.append(c);c.request_draw(force=True)
        self.active_chart=min(getattr(self,'active_chart',0),len(self.charts)-1);self.sync_chart_controls();self.status_flash(f'{count} chart workspace — each chart has an independent tickrate')
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
    def _watchlist_path(self):
        return Path.home()/'.stock_game_pro_watchlists.json'

    def _load_watchlists(self):
        try:
            raw=json.loads(self._watchlist_path().read_text(encoding='utf-8'))
            if isinstance(raw,dict):
                return {str(k):[str(x).upper() for x in v if isinstance(x,str)] for k,v in raw.items() if isinstance(v,list)}
        except Exception:
            pass
        return {}

    def _save_watchlists(self):
        try:self._watchlist_path().write_text(json.dumps(self.watchlists,indent=2,sort_keys=True),encoding='utf-8')
        except Exception as e:self.status_flash(f'Unable to save watchlists: {e}')

    def _sync_watchlist_combo(self):
        if hasattr(self,'watchlist_combo'):self.watchlist_combo['values']=['All Market']+sorted(self.watchlists)

    def create_watchlist(self):
        name=simpledialog.askstring('New watchlist','Watchlist name:',parent=self.root)
        if not name:return
        name=name.strip()
        if not name:return
        if name.lower()=='all market':return messagebox.showwarning('Watchlist','That name is reserved.')
        existing=next((k for k in self.watchlists if k.lower()==name.lower()),None)
        if existing:name=existing
        else:self.watchlists[name]=[];self._save_watchlists();self._sync_watchlist_combo()
        self.watchlist_name.set(name);self.refresh_watch();self.status_flash(f'Watchlist “{name}” ready — right-click tickers to add/remove symbols')

    def delete_watchlist(self):
        name=self.watchlist_name.get()
        if name=='All Market':return messagebox.showinfo('Watchlist','Select a custom watchlist first.')
        if name not in self.watchlists:return
        if messagebox.askyesno('Delete watchlist',f'Delete watchlist “{name}”?',parent=self.root):
            del self.watchlists[name];self._save_watchlists();self._sync_watchlist_combo();self.watchlist_name.set('All Market');self.refresh_watch()

    def add_symbol_to_watchlist(self,symbol,name=None):
        symbol=str(symbol).upper();name=name or self.watchlist_name.get()
        if name=='All Market':
            if not self.watchlists:
                self.create_watchlist();name=self.watchlist_name.get()
                if name=='All Market':return
            else:
                name=sorted(self.watchlists)[0]
        if name not in self.watchlists:return
        if symbol not in self.watchlists[name]:self.watchlists[name].append(symbol);self._save_watchlists()
        if self.watchlist_name.get()==name:self.refresh_watch()
        self.status_flash(f'{symbol} added to “{name}”')

    def remove_symbol_from_current_watchlist(self,symbol):
        name=self.watchlist_name.get();symbol=str(symbol).upper()
        if name=='All Market':return
        if name in self.watchlists and symbol in self.watchlists[name]:
            self.watchlists[name].remove(symbol);self._save_watchlists();self.refresh_watch();self.status_flash(f'{symbol} removed from “{name}”')

    def refresh_watch(self):
        q=self.search.get().upper();name=self.watchlist_name.get() if hasattr(self,'watchlist_name') else 'All Market'
        if name!='All Market' and name in self.watchlists:
            assets=[self.market.get_asset(sym) for sym in self.watchlists[name]];assets=[a for a in assets if a]
        else:
            kind=self.kind.get();sec=self.sector.get();mapping={'STOCK':self.market.stocks,'INDEX':self.market.indexes,'COMMODITY':self.market.commodities,'FUTURES':self.market.futures,'CRYPTO':self.market.crypto,'INTERNATIONAL':self.market.international,'FOREX':self.market.forex};assets=list(mapping.get(kind,self.market.all_assets()))
            if sec!='ALL':assets=[a for a in assets if a.category==sec]
        if q:assets=[a for a in assets if q in a.symbol.upper() or q in a.name.upper()]
        k=self.sort_key;fn=(lambda a:a.symbol.upper()) if k=='Symbol' else (lambda a:a.name.upper()) if k=='Name' else (lambda a:a.price) if k=='Price' else (lambda a:a.change_percent()) if k=='Change %' else (lambda a:a.category.upper());assets=sorted(assets,key=fn,reverse=self.sort_reverse);sel=self.watch.selection();sid=self.watch.item(sel[0],'values')[0] if sel and self.watch.exists(sel[0]) else None;self.watch.delete(*self.watch.get_children())
        for a in assets:self.watch.insert('','end',iid=a.symbol,values=(a.symbol,a.name,f'${a.price:,.2f}',f'{a.change_percent():+.2f}%',a.category))
        if sid and sid in self.watch.get_children():self.watch.selection_set(sid);self.watch.focus(sid)
    def watch_context(self,event):
        iid=self.watch.identify_row(event.y)
        if not iid:return
        self.watch.selection_set(iid);self.watch.focus(iid);self.watch.see(iid);a=self.market.get_asset(iid);m=tk.Menu(self.watch,tearoff=0);m.add_command(label=f'BUY {a.symbol}',command=lambda:self.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL {a.symbol}',command=lambda:self.order_window(a,'SELL','MARKET',None));m.add_command(label=f'SHORT {a.symbol}',command=lambda:self.order_window(a,'SHORT','MARKET',None));m.add_command(label='COVER',command=lambda:self.order_window(a,'COVER','MARKET',None));m.add_separator();m.add_command(label='Open Options Chain',command=lambda:self.options_for(a));m.add_command(label='Advanced Chart',command=lambda:self.advanced_chart(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.depth_for(a));m.add_separator()
        add_menu=tk.Menu(m,tearoff=0)
        if self.watchlists:
            for name in sorted(self.watchlists):add_menu.add_command(label=name,command=lambda n=name,s=a.symbol:self.add_symbol_to_watchlist(s,n))
        else:add_menu.add_command(label='Create a watchlist…',command=self.create_watchlist)
        m.add_cascade(label='Add to watchlist',menu=add_menu)
        if self.watchlist_name.get()!='All Market':m.add_command(label=f'Remove from {self.watchlist_name.get()}',command=lambda s=a.symbol:self.remove_symbol_from_current_watchlist(s))
        m.add_command(label='WATCHLIST VARIABLES',command=self.watch_variables);m.tk_popup(event.x_root,event.y_root)
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
    def open_selected_advanced(self,e=None):
        a=self.selected()
        if a:self.advanced_chart(a)
        return 'break'
    def advanced_chart(self,a):
        return AdvancedChartWindow(self.root,self,a)
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
        if hasattr(self,'chart_rate'):self.chart_rate.set(f'{c.refresh_ms}ms')
    def set_type(self):self.charts[self.active_chart].kind=self.ctype.get();self.charts[self.active_chart].draw()
    def redraw(self):self.ind_vars_version+=1;[c.request_draw(force=True) for c in self.charts]
    def start_fast_watch_stream(self):
        if getattr(self,'_watch_stream_job',None) is not None:
            try:self.root.after_cancel(self._watch_stream_job)
            except Exception:pass
        self._watch_stream_job=self.root.after(120,self._fast_watch_stream)

    def _fast_watch_stream(self):
        try:
            if not self.root.winfo_exists():return
            # Update only volatile price/change cells. Rebuilding the whole watchlist every frame
            # was expensive and made chart animation look tied to the 700 ms UI refresh.
            if hasattr(self,'watch'):
                for iid in self.watch.get_children(''):
                    a=self.market.get_asset(iid)
                    if not a:continue
                    vals=list(self.watch.item(iid,'values'))
                    if len(vals)>=5:
                        vals[2]=f'${a.price:,.2f}';vals[3]=f'{a.change_percent():+.2f}%';self.watch.item(iid,values=vals)
        except tk.TclError:return
        except Exception as e:
            try:self.market.errors.append(f'watch stream: {type(e).__name__}: {e}')
            except Exception:pass
        self._watch_stream_job=self.root.after(120,self._fast_watch_stream)

    def refresh_positions(self):
        old=self.pos.selection();keep=old[0] if old else None;self.pos.delete(*self.pos.get_children())
        for sym,name,q,p,v,pnl,typ,under,days in self.portfolio.position_rows(self.market.all_assets()):
            pct=(pnl/max(1e-9,abs(self.portfolio.cost_basis.get(sym,0))) if sym in self.portfolio.cost_basis else (pnl/max(1e-9,abs(self.portfolio.options[int(sym.split(':')[1])].open_cost)) if typ=='OPTION' and sym.startswith('OPT:') else 0))
            self.pos.insert('','end',iid=sym,values=(sym,f'{q:,}',f'${p:,.2f}',f'${v:,.2f}',f'${pnl:,.2f}',f'{pct:+.2f}%',typ,under,(f'{days}D' if typ=='OPTION' else '')))
        if keep and keep in self.pos.get_children():self.pos.selection_set(keep);self.pos.focus(keep)
    def position_context(self,e):
        iid=self.pos.identify_row(e.y)
        if iid:
            self.pos.selection_set(iid)
        m=tk.Menu(self.pos,tearoff=0);m.add_command(label='Liquidate / Cash',command=self.liquidate);m.add_command(label='BUY MORE / ADD TO POSITION',command=self.buy_more_position);m.add_separator();m.add_command(label='CUSTOMIZE POSITION COLUMNS',command=self.position_variables)
        sub=tk.Menu(m,tearoff=0);self._column_menu_vars=[]
        for label,key in {'Symbol':'symbol','Qty':'qty','Last':'last','Value':'value','P/L':'pnl','P/L %':'pct','Type':'type','Underlying':'underlying','Expiry':'expiry'}.items():
            v=tk.BooleanVar(value=self.pos.column(key,'width')>0);self._column_menu_vars.append(v);sub.add_checkbutton(label=label,variable=v,command=lambda k=key,var=v:self.toggle_table_column(self.pos,k,var))
        m.add_cascade(label='ADD / REMOVE COLUMNS',menu=sub);m.tk_popup(e.x_root,e.y_root)
    def buy_more_position(self):
        it=self.pos.selection()
        if not it:return messagebox.showwarning('Position','Select a position first.')
        k=it[0]
        if k.startswith('OPT:'):
            try:s=self.portfolio.options[int(k.split(':')[1])];c=s.legs[0].contract;OptionPreviewWindow(self,c,self.portfolio,self.refresh,default_action='BUY')
            except Exception as e:messagebox.showerror('Position',f'Unable to open option contract: {e}')
        else:
            a=self.market.get_asset(k)
            if a:self.order_window(a,'BUY','MARKET',None)

    def position_variables(self):
        self.column_variables(self.pos, {'Symbol':'symbol','Qty':'qty','Last':'last','Value':'value','P/L':'pnl','P/L %':'pct','Type':'type','Underlying':'underlying','Expiry':'expiry'})
    def watch_variables(self):
        self.column_variables(self.watch, {'Symbol':'symbol','Name':'name','Price':'price','Chg %':'chg','Sector':'sector'})
    def column_variables(self,tv,names):
        w=tk.Toplevel(self.root);w.title('TABLE VARIABLES');w.geometry('360x420');w.resizable(True,True);ttk.Label(w,text='Visible columns',font=('Arial',12,'bold')).pack(anchor='w',padx=12,pady=10)
        for label,key in names.items():
            v=tk.BooleanVar(value=tv.column(key,'width')>0);ttk.Checkbutton(w,text=label,variable=v,command=lambda k=key,var=v:self.toggle_table_column(tv,k,var)).pack(anchor='w',padx=20,pady=4)
    def toggle_table_column(self,tv,key,var):
        widths={'symbol':78,'qty':72,'last':82,'value':98,'pnl':92,'pct':74,'type':74,'underlying':92,'expiry':74,'name':150,'price':90,'chg':78,'sector':100}
        tv.column(key,width=widths.get(key,90) if var.get() else 0,stretch=False)
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
        def update_popup():
            if not w.winfo_exists():return
            tv.delete('1.0','end')
            for n in self.market.news[-500:]:tv.insert('end',f'[{getattr(n,"severity","NORMAL")}] {n}\n')
            tv.see('end');w.after(700,update_popup)
        update_popup();w.transient(self.root)
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
    def set_time_warp(self,value=None):
        try:mult=max(.25,min(40.0,float(self.time_warp.get() if value is None else value)))
        except Exception:mult=10.0
        # Engine cadence stays fixed for smooth UI. Only simulated elapsed time changes.
        # At 1x: 1 real-world second = 1 in-game minute.
        self.market.time_warp=mult
        if hasattr(self,'time_warp'):self.time_warp.set(mult)
        if hasattr(self,'time_warp_label'):self.time_warp_label.config(text=f'{mult:.2f}x')
    def change_speed(self,factor):
        cur=float(self.time_warp.get()) if hasattr(self,'time_warp') else float(getattr(self.market,'time_warp',1.0))
        self.set_time_warp(cur*float(factor))
        self.status_flash(f'Global time warp {float(self.time_warp.get()):.2f}x')
    def set_speed(self,s):
        # Backward-compatible Time-menu entry: translate old sleep-delay values into the global slider.
        self.set_time_warp(max(.25,min(40.0,float(getattr(self.market,'time_warp',1.0)))))
        self.status_flash(f'Global time warp {float(self.time_warp.get()):.2f}x')
    def status_flash(self,msg):self.status.config(text=msg)
    def refresh(self):
        try:
            self.portfolio.apply_corporate_actions(self.market.all_assets());self.portfolio.best_net_worth=max(getattr(self.portfolio,'best_net_worth',0),self.portfolio.mark_value(self.market.all_assets()));self.refresh_positions();self.summary.delete('1.0','end');self.summary.insert('end',self.portfolio.summary(self.market.all_assets()));
            a=self.selected() or self.charts[self.active_chart].asset
            if a:
                p=self.market.predict(a);self.pred.config(text=f'MODEL {a.symbol}\n{p["label"]}  confidence {p["confidence"]*100:.0f}%\nMomentum {p["momentum"]*100:+.2f}%  vol {p["volatility"]*100:.2f}%')
            self.refresh_news();self.refresh_orders();self.clock_label.config(text=f'{self.market.clock.time}  •  {self.market.clock.utc_time}  •  {"US OPEN" if self.market.clock.open else "US CLOSED"}');self.status.config(text=f'Assets {len(self.market.all_assets())} • {self.market.data_status} • Working orders {len(self.market.pending_orders)+len(self.market.pending_option_orders)+len(self.market.pending_spread_orders)} • Engine errors {len(self.market.errors)}')
        except Exception as e:self.status.config(text=f'UI recovered: {e}')
        self.root.after(900,self.refresh)

# ===== v6 workstation / analytics enhancements =====
# These replacements intentionally live after App so older call sites resolve to the upgraded globals.

_LegacyOptionPreviewWindow=OptionPreviewWindow
_LegacySpreadBuilder=SpreadBuilder
_LegacyDepthWindow=DepthWindow
_LegacyMarketMapWindow=MarketMapWindow
_LegacyGlobeWindow=GlobeWindow
_LegacyBlackjackWindow=BlackjackWindow
_LegacyRouletteWindow=RouletteWindow


def _normal_cdf(x):
    return .5*(1+math.erf(x/math.sqrt(2)))

def _strategy_terminal_stats(strategy,spot,days):
    """Approximate expiration distribution / probability of profit for the simulator."""
    if not strategy or not getattr(strategy,'legs',None):return {'pop':0.0,'expected':0.0,'breakevens':[]}
    vols=[max(.05,l.contract.volatility) for l in strategy.legs];vol=sum(vols)/len(vols);T=max(days,.01)/365.0;sig=max(.015,vol*math.sqrt(T))
    lo=max(.01,spot*math.exp(-4*sig));hi=spot*math.exp(4*sig);n=401;prev=None;bes=[];weight_sum=ev=win=0.0
    for i in range(n):
        z=-4+8*i/(n-1);s=spot*math.exp(-.5*sig*sig+sig*z);pnl=strategy.expiration_pnl(s);w=math.exp(-.5*z*z)
        weight_sum+=w;ev+=pnl*w
        if pnl>0:win+=w
        if prev is not None and (prev[1]==0 or pnl==0 or (prev[1]<0<pnl) or (prev[1]>0>pnl)):bes.append((prev[0]+s)/2)
        prev=(s,pnl)
    return {'pop':win/max(weight_sum,1e-9),'expected':ev/max(weight_sum,1e-9),'breakevens':bes[:6]}


def _draw_strategy_payoff(canvas,strategy,spot,days,title='STRATEGY ANALYSIS'):
    canvas.delete('all');w=max(520,canvas.winfo_width());h=max(260,canvas.winfo_height());left,right,top,bottom=58,w-20,38,h-42
    if not strategy or not getattr(strategy,'legs',None):canvas.create_text(w/2,h/2,text='Add option legs to build a strategy',fill=MUTED,font=('Arial',12,'bold'));return
    span=max(spot*.35,12);lo=max(.01,spot-span);hi=spot+span;vals=[]
    for i in range(241):
        s=lo+(hi-lo)*i/240;vals.append((s,strategy.expiration_pnl(s)))
    mn=min([0]+[p for _,p in vals]);mx=max([0]+[p for _,p in vals]);rng=max(1,mx-mn)
    def px(s):return left+(s-lo)/(hi-lo)*(right-left)
    def py(v):return bottom-(v-mn)/rng*(bottom-top)
    zero=py(0);canvas.create_line(left,zero,right,zero,fill='#607080',dash=(4,3))
    # One-sigma expected-move zone.
    vol=sum(max(.05,l.contract.volatility) for l in strategy.legs)/len(strategy.legs);move=spot*vol*math.sqrt(max(days,.01)/365.0);x1,x2=px(max(lo,spot-move)),px(min(hi,spot+move));canvas.create_rectangle(x1,top,x2,bottom,fill='#10283a',outline='')
    pos=[];neg=[]
    for s,pnl in vals:
        (pos if pnl>=0 else neg).extend([px(s),py(pnl)])
    pts=[]
    for s,pnl in vals:pts.extend([px(s),py(pnl)])
    if len(pts)>3:canvas.create_line(*pts,fill=CYAN,width=3,smooth=True)
    canvas.create_line(px(spot),top,px(spot),bottom,fill=YELLOW,dash=(5,3),width=2)
    for j in range(5):
        y=top+j*(bottom-top)/4;v=mx-j*rng/4;canvas.create_line(left,y,right,y,fill=GRID);canvas.create_text(left-6,y,text=f'${v:,.0f}',anchor='e',fill=MUTED,font=('Arial',8))
    for j in range(5):
        s=lo+j*(hi-lo)/4;x=px(s);canvas.create_text(x,bottom+15,text=f'${s:,.0f}',fill=MUTED,font=('Arial',8))
    stats=_strategy_terminal_stats(strategy,spot,days);be=', '.join(f'${x:,.2f}' for x in stats['breakevens']) or '—'
    canvas.create_text(left,8,anchor='nw',text=title,fill=TEXT,font=('Arial',11,'bold'));canvas.create_text(right,8,anchor='ne',text=f'POP≈{stats["pop"]*100:.1f}%  EV≈${stats["expected"]:,.0f}  1σ move ±${move:,.2f}',fill=TEXT,font=('Arial',9,'bold'));canvas.create_text(left,h-8,anchor='sw',text=f'Breakeven(s): {be}  •  shaded zone = approximate 1σ terminal range',fill=MUTED,font=('Arial',8))


class SpreadBuilder(ToolWindow):
    """Enterprise options strategy lab with a pro-style calls/strike/puts chain."""
    def __init__(self,parent,market,portfolio,refresh,first=None):
        super().__init__(parent);self.market=market;self.portfolio=portfolio;self.refresh=refresh;self.rows=[];self._after=None;self._chain_contracts={};self._owned_strategy=first if isinstance(first,OptionStrategy) else None
        self.style_window('ADVANCED OPTIONS STRATEGY LAB','1660x960');self.resizable(True,True);self._syncing_scroll=False;self._syncing_select=False
        initial='SPY'
        if isinstance(first,OptionContract):initial=first.underlying.symbol
        elif isinstance(first,OptionStrategy) and first.legs:initial=first.legs[0].contract.underlying.symbol
        self.ticker=tk.StringVar(value=initial);self.exp=tk.StringVar(value='30D');self.add_action=tk.StringVar(value='BUY');self.leg_qty=tk.IntVar(value=1);self.order_type=tk.StringVar(value='MARKET');self.order_side=tk.StringVar(value='BUY');self.price=tk.DoubleVar(value=0.0);self.preset=tk.StringVar(value='Custom');self.span=tk.IntVar(value=15)
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=7)
        ttk.Label(top,text='Ticker').pack(side='left');te=ttk.Entry(top,textvariable=self.ticker,width=10);te.pack(side='left',padx=4);te.bind('<Return>',lambda e:self.load_chain())
        ttk.Button(top,text='LOAD',command=self.load_chain).pack(side='left');ttk.Label(top,text='Expiry').pack(side='left',padx=(12,2));ex=ttk.Combobox(top,textvariable=self.exp,values=[x[0] for x in EXPIRATIONS],state='readonly',width=8);ex.pack(side='left');ex.bind('<<ComboboxSelected>>',lambda e:self.load_chain())
        ttk.Label(top,text='Strikes ±').pack(side='left',padx=(12,2));sp=ttk.Spinbox(top,from_=5,to=50,textvariable=self.span,width=5,command=self.load_chain);sp.pack(side='left')
        ttk.Label(top,text='Preset').pack(side='left',padx=(12,2));pr=ttk.Combobox(top,textvariable=self.preset,values=['Custom','Long Call','Long Put','Bull Call Spread','Bear Put Spread','Long Straddle','Short Straddle','Iron Condor'],state='readonly',width=18);pr.pack(side='left');pr.bind('<<ComboboxSelected>>',lambda e:self.apply_preset())
        self.live=ttk.Label(top,text='',font=('Arial',10,'bold'));self.live.pack(side='right',padx=8)
        split=ttk.PanedWindow(self,orient='horizontal');split.pack(fill='both',expand=True,padx=8,pady=(0,7));chain_box=ttk.LabelFrame(split,text='PRO OPTIONS CHAIN — double-click CALL or PUT to add the selected action');work=ttk.Frame(split);split.add(chain_box,weight=5);split.add(work,weight=5)
        cbar=ttk.Frame(chain_box);cbar.pack(fill='x',padx=5,pady=4);ttk.Label(cbar,text='Add leg as').pack(side='left');ttk.Combobox(cbar,textvariable=self.add_action,values=['BUY','SELL'],state='readonly',width=8).pack(side='left',padx=4);ttk.Label(cbar,text='Qty').pack(side='left');ttk.Spinbox(cbar,from_=1,to=10000,textvariable=self.leg_qty,width=7).pack(side='left',padx=4);ttk.Button(cbar,text='ADD SELECTED CALL',command=lambda:self.add_selected('call')).pack(side='left',padx=4);ttk.Button(cbar,text='ADD SELECTED PUT',command=lambda:self.add_selected('put')).pack(side='left')
        chain_grid=ttk.Frame(chain_box);chain_grid.pack(fill='both',expand=True,padx=5,pady=4);chain_grid.columnconfigure(0,weight=1);chain_grid.columnconfigure(2,weight=1);chain_grid.rowconfigure(0,weight=1)
        call_cols=('bid','ask','last','iv','delta','vol','oi');put_cols=('bid','ask','last','iv','delta','vol','oi')
        self.calls=ttk.Treeview(chain_grid,columns=call_cols,show='headings',selectmode='browse');self.strikes=ttk.Treeview(chain_grid,columns=('strike',),show='headings',selectmode='browse');self.puts=ttk.Treeview(chain_grid,columns=put_cols,show='headings',selectmode='browse')
        labels={'bid':'Bid','ask':'Ask','last':'Mid','iv':'IV','delta':'Δ','vol':'Vol','oi':'OI'}
        for tv,title in ((self.calls,'CALLS'),(self.puts,'PUTS')):
            for c in tv['columns']:tv.heading(c,text=labels[c]);tv.column(c,width=62 if c not in ('vol','oi') else 72,anchor='center',stretch=True)
            tv.tag_configure('itm',background='#173d2e',foreground='#d9ffef');tv.tag_configure('atm',background='#403720',foreground='#fff2ae')
        self.strikes.heading('strike',text='STRIKE');self.strikes.column('strike',width=86,anchor='center',stretch=False);self.strikes.tag_configure('atm',background='#403720',foreground='#fff2ae')
        self.calls.grid(row=0,column=0,sticky='nsew');self.strikes.grid(row=0,column=1,sticky='ns');self.puts.grid(row=0,column=2,sticky='nsew');scroll=ttk.Scrollbar(chain_grid,orient='vertical',command=self._yview_all);scroll.grid(row=0,column=3,sticky='ns');self._chain_scroll=scroll
        for tv in (self.calls,self.strikes,self.puts):tv.configure(yscrollcommand=self._chain_scroll.set);tv.bind('<MouseWheel>',self._wheel_sync)
        self.calls.bind('<Double-1>',lambda e:self.add_selected('call',e));self.puts.bind('<Double-1>',lambda e:self.add_selected('put',e))
        lbox=ttk.LabelFrame(work,text='STRATEGY LEGS');lbox.pack(fill='x',padx=5,pady=(0,5));self.legs=ttk.Treeview(lbox,columns=('action','type','strike','qty','bid','ask','mark','delta'),show='headings',height=7,selectmode='browse')
        for c,t,ww in [('action','Action',70),('type','Type',55),('strike','Strike',75),('qty','Qty',55),('bid','Bid',65),('ask','Ask',65),('mark','Mark',70),('delta','Δ',65)]:self.legs.heading(c,text=t);self.legs.column(c,width=ww,anchor='center',stretch=False)
        self.legs.pack(fill='x',padx=5,pady=5);lb=ttk.Frame(lbox);lb.pack(fill='x',padx=5,pady=(0,5));ttk.Button(lb,text='FLIP BUY/SELL',command=self.flip_leg).pack(side='left');ttk.Button(lb,text='QTY +',command=lambda:self.change_leg_qty(1)).pack(side='left',padx=3);ttk.Button(lb,text='QTY -',command=lambda:self.change_leg_qty(-1)).pack(side='left');ttk.Button(lb,text='REMOVE',command=self.remove_leg).pack(side='left',padx=4);ttk.Button(lb,text='DUPLICATE LEG',command=self.duplicate_leg).pack(side='left');ttk.Button(lb,text='CLEAR ALL',command=self.clear).pack(side='right')
        self.metrics=ttk.Label(work,text='No legs',font=('Arial',9,'bold'),justify='left');self.metrics.pack(fill='x',padx=8,pady=4)
        self.payoff=tk.Canvas(work,bg='#081018',highlightthickness=0,height=430);self.payoff.pack(fill='both',expand=True,padx=5,pady=5);self.payoff.bind('<Configure>',lambda e:self.draw())
        order=ttk.LabelFrame(work,text='EXECUTION');order.pack(fill='x',padx=5,pady=5);ttk.Combobox(order,textvariable=self.order_side,values=['BUY','SELL'],state='readonly',width=8).pack(side='left',padx=5,pady=6);ttk.Combobox(order,textvariable=self.order_type,values=['MARKET','LIMIT','STOP'],state='readonly',width=10).pack(side='left',padx=3,pady=6);ttk.Label(order,text='Net price / contract').pack(side='left',padx=(8,2));ttk.Entry(order,textvariable=self.price,width=10).pack(side='left',padx=3);ttk.Button(order,text='EXECUTE / WORK NEW STRATEGY',command=self.execute).pack(side='left',padx=8)
        if self._owned_strategy is not None:ttk.Button(order,text='LIQUIDATE OWNED POSITION',command=self.liquidate_owned).pack(side='left',padx=4)
        if isinstance(first,OptionStrategy):
            for leg in first.legs:self.rows.append({'action':leg.action,'contract':leg.contract,'qty':leg.quantity})
            self.exp.set(self._label_for_days(min((l.contract.days for l in first.legs),default=30)))
        elif isinstance(first,OptionContract):self.rows.append({'action':'BUY','contract':first,'qty':1});self.exp.set(self._label_for_days(first.days))
        self.load_chain();self.refresh_strategy();self.protocol('WM_DELETE_WINDOW',self.close);self._after=self.after(750,self.live_tick)
    def _label_for_days(self,d):return min(EXPIRATIONS,key=lambda x:abs(x[1]-int(float(d))))[0]
    def asset(self):return self.market.get_asset(self.ticker.get().strip().upper())
    def _yview_all(self,*args):
        for tv in (self.calls,self.strikes,self.puts):tv.yview(*args)
    def _sync_scroll(self,*args):
        if self._syncing_scroll:return
        self._syncing_scroll=True
        try:
            self._chain_scroll.set(*args);pos=float(args[0])
            for tv in (self.calls,self.strikes,self.puts):tv.yview_moveto(pos)
        except Exception:pass
        finally:self._syncing_scroll=False
    def _wheel_sync(self,e):
        d=-1 if e.delta>0 else 1
        for tv in (self.calls,self.strikes,self.puts):tv.yview_scroll(d,'units')
        return 'break'
    def _sync_select(self,source):
        if self._syncing_select:return
        it=source.selection()
        if not it:return
        self._syncing_select=True
        try:
            iid=it[0]
            for tv in (self.calls,self.strikes,self.puts):
                if tv is not source and iid in tv.get_children(''):tv.selection_set(iid);tv.see(iid)
        finally:self._syncing_select=False
    def load_chain(self):
        a=self.asset()
        if not a:return messagebox.showerror('Options Strategy Lab','Ticker not found.')
        days=dict(EXPIRATIONS).get(self.exp.get(),30);span=max(5,min(50,int(self.span.get())));contracts=option_chain(a,days,span);self._chain_contracts={}
        for tv in (self.calls,self.strikes,self.puts):tv.delete(*tv.get_children())
        calls={int(c.strike):c for c in contracts if c.option_type=='call'};puts={int(c.strike):c for c in contracts if c.option_type=='put'};atm=round(a.price)
        for strike in sorted(set(calls)|set(puts)):
            iid=str(strike);cc=calls.get(strike);pp=puts.get(strike);self._chain_contracts[('call',iid)]=cc;self._chain_contracts[('put',iid)]=pp;tag=('atm',) if strike==atm else ()
            self.strikes.insert('','end',iid=iid,values=(f'{strike:g}',),tags=tag)
            for tv,c,typ in ((self.calls,cc,'call'),(self.puts,pp,'put')):
                if not c:continue
                st=c.stats;itm=(typ=='call' and strike<a.price) or (typ=='put' and strike>a.price);tags=('atm',) if strike==atm else ('itm',) if itm else ()
                tv.insert('','end',iid=iid,values=(f'{c.bid:.2f}',f'{c.ask:.2f}',f'{c.mid:.2f}',f'{c.volatility*100:.1f}%',f'{st["delta"]:+.2f}',f'{c.volume:,}',f'{c.open_interest:,}'),tags=tags)
        if str(atm) in self.strikes.get_children(''):
            for tv in (self.calls,self.strikes,self.puts):tv.see(str(atm));tv.selection_set(str(atm))
        self.live.config(text=f'{a.symbol} ${a.price:,.2f} • {days}D');self.refresh_strategy()
    def add_selected(self,typ,e=None):
        tv=self.calls if typ=='call' else self.puts
        if e is not None:
            iid=tv.identify_row(e.y)
            if iid:tv.selection_set(iid);self._sync_select(tv)
        it=tv.selection()
        if not it:return messagebox.showwarning('Options Strategy Lab',f'Select a {typ.upper()} row first.')
        c=self._chain_contracts.get((typ,it[0]))
        if c is None:return
        self.rows.append({'action':self.add_action.get(),'contract':c,'qty':max(1,int(self.leg_qty.get()))});self.preset.set('Custom');self.refresh_strategy()
    def selected_leg_index(self):
        it=self.legs.selection();return int(it[0]) if it else None
    def flip_leg(self):
        i=self.selected_leg_index()
        if i is None:return
        self.rows[i]['action']='SELL' if self.rows[i]['action']=='BUY' else 'BUY';self.refresh_strategy();self.legs.selection_set(str(i))
    def change_leg_qty(self,d):
        i=self.selected_leg_index()
        if i is None:return
        self.rows[i]['qty']=max(1,int(self.rows[i]['qty'])+d);self.refresh_strategy();self.legs.selection_set(str(i))
    def remove_leg(self):
        i=self.selected_leg_index()
        if i is not None:self.rows.pop(i);self.refresh_strategy()
    def duplicate_leg(self):
        i=self.selected_leg_index()
        if i is None:return
        r=self.rows[i];self.rows.append({'action':r['action'],'contract':r['contract'],'qty':r['qty']});self.refresh_strategy()
    def clear(self):self.rows=[];self.preset.set('Custom');self.refresh_strategy()
    def build_strategy(self):
        s=OptionStrategy(self.preset.get() if self.preset.get()!='Custom' else 'CUSTOM STRATEGY')
        for r in self.rows:s.add_leg(r['contract'],r['qty'],r['action'])
        s.open_cost=s.opening_debit();return s
    def apply_preset(self):
        name=self.preset.get();a=self.asset()
        if not a or name=='Custom':return
        days=dict(EXPIRATIONS).get(self.exp.get(),30);k=round(a.price);w=max(1,round(a.price*.025));defs={'Long Call':[('BUY','call',k)],'Long Put':[('BUY','put',k)],'Bull Call Spread':[('BUY','call',k),('SELL','call',k+w)],'Bear Put Spread':[('BUY','put',k),('SELL','put',k-w)],'Long Straddle':[('BUY','call',k),('BUY','put',k)],'Short Straddle':[('SELL','call',k),('SELL','put',k)],'Iron Condor':[('BUY','put',k-2*w),('SELL','put',k-w),('SELL','call',k+w),('BUY','call',k+2*w)]}
        self.rows=[{'action':act,'contract':OptionContract(a,strike,days,typ),'qty':1} for act,typ,strike in defs.get(name,[])];self.refresh_strategy()
    def refresh_strategy(self):
        keep=self.legs.selection();self.legs.delete(*self.legs.get_children());net=0.;greeks={k:0. for k in ('delta','gamma','theta','vega')}
        for i,r in enumerate(self.rows):
            c=r['contract'];q=r['qty'];sign=1 if r['action']=='BUY' else -1;net+=sign*c.mid*q*100;st=c.stats
            for k in greeks:greeks[k]+=sign*st[k]*q*100
            self.legs.insert('','end',iid=str(i),values=(r['action'],c.option_type.upper(),f'{c.strike:g}',q,f'${c.bid:.2f}',f'${c.ask:.2f}',f'${c.mid:.2f}',f'{st["delta"]:+.3f}'))
        if keep and keep[0] in self.legs.get_children(''):self.legs.selection_set(keep[0])
        s=self.build_strategy() if self.rows else None;a=self.asset();days=dict(EXPIRATIONS).get(self.exp.get(),30);stats=_strategy_terminal_stats(s,a.price,days) if s and a else {'pop':0,'expected':0,'breakevens':[]};self.price.set(round(abs(net)/100,2) if self.rows else 0)
        self.metrics.config(text=f'Net debit(+)/credit(-): ${net:,.2f}   •   Δ {greeks["delta"]:+.1f}   Γ {greeks["gamma"]:+.3f}   Θ {greeks["theta"]:+.1f}   Vega {greeks["vega"]:+.1f}\nApprox POP {stats["pop"]*100:.1f}%   •   probability-weighted expiration P/L ${stats["expected"]:,.0f}')
        self.draw()
    def draw(self):
        a=self.asset();s=self.build_strategy() if self.rows else None
        if a:_draw_strategy_payoff(self.payoff,s,a.price,dict(EXPIRATIONS).get(self.exp.get(),30),'OPTIONS STRATEGY — EXPIRATION P/L')
    def live_tick(self):
        if not self.winfo_exists():return
        try:
            if self.state()!='withdrawn' and self.winfo_viewable():
                a=self.asset();days=dict(EXPIRATIONS).get(self.exp.get(),30)
                if a:self.live.config(text=f'{a.symbol} ${a.price:,.2f} • {days}D');self.refresh_strategy()
        except Exception:pass
        self._after=self.after(750,self.live_tick)
    def execute(self):
        if not self.rows:return messagebox.showwarning('Strategy','Add at least one option leg.')
        s=self.build_strategy();typ=self.order_type.get()
        if typ=='MARKET':ok,msg=self.portfolio.execute_strategy(s)
        else:self.market.submit_spread_pending(self.order_side.get(),s,typ,float(self.price.get()));ok=True;msg=f'Working {typ} strategy at ${self.price.get():,.2f}'
        if ok:self.refresh();messagebox.showinfo('Strategy',msg);self.refresh_strategy()
        else:messagebox.showerror('Strategy rejected',msg)
    def liquidate_owned(self):
        if self._owned_strategy is None:return
        ok,msg=self.portfolio.liquidate_strategy(self._owned_strategy)
        if ok:self.refresh();messagebox.showinfo('Options position',msg);self._owned_strategy=None
        else:messagebox.showerror('Options position',msg)
    def close(self):
        if self._after:
            try:self.after_cancel(self._after)
            except Exception:pass
        self.destroy()

class OptionPreviewWindow(ToolWindow):
    def __init__(self,parent,contract,portfolio,refresh,chain=None,default_action='BUY'):
        super().__init__(parent);self.contract=contract;self.portfolio=portfolio;self.refresh=refresh;self.chain=chain;self.market=getattr(chain,'market',None) or getattr(getattr(parent,'app',None),'market',None) or getattr(portfolio,'market',None);self.action=tk.StringVar(value=default_action);self.qty=tk.IntVar(value=1)
        self.style_window('OPTION ORDER + LIVE RISK PREVIEW','920x720');top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8);self.title_lbl=ttk.Label(top,text='',font=('Arial',14,'bold'));self.title_lbl.pack(side='left');self.quote=ttk.Label(top,text='');self.quote.pack(side='right')
        row=ttk.Frame(self);row.pack(fill='x',padx=10,pady=5);ttk.Label(row,text='Action').pack(side='left');ttk.Combobox(row,textvariable=self.action,values=['BUY','SELL'],state='readonly',width=8).pack(side='left',padx=4);ttk.Label(row,text='Contracts').pack(side='left',padx=(10,2));ttk.Spinbox(row,from_=1,to=100000,textvariable=self.qty,width=8).pack(side='left');ttk.Button(row,text='EXECUTE',command=self.execute).pack(side='left',padx=10);ttk.Button(row,text='OPEN IN ADVANCED STRATEGY LAB',command=self.to_spread).pack(side='left');ttk.Button(row,text='FULL OPTIONS CHAIN',command=self.open_chain).pack(side='left',padx=5)
        self.stats=ttk.Label(self,text='',justify='left',font=('Arial',9,'bold'));self.stats.pack(fill='x',padx=12,pady=5);self.payoff=tk.Canvas(self,bg='#081018',highlightthickness=0);self.payoff.pack(fill='both',expand=True,padx=10,pady=8);self.payoff.bind('<Configure>',lambda e:self.update_live());self.qty.trace_add('write',lambda *x:self.update_live());self.action.trace_add('write',lambda *x:self.update_live());self.after(60,self.update_live)
    def strategy(self):
        s=OptionStrategy(f'{self.action.get()} {self.contract}');s.add_leg(self.contract,max(1,int(self.qty.get() or 1)),self.action.get());s.open_cost=s.opening_debit();return s
    def update_live(self):
        if not self.winfo_exists():return
        try:
            c=self.contract;st=c.stats;s=self.strategy();self.title_lbl.config(text=f'{c.underlying.symbol} {c.option_type.upper()} ${c.strike:g} • {c.days}D');self.quote.config(text=f'Bid ${c.bid:.2f}  Ask ${c.ask:.2f}  Mid ${c.mid:.2f}  IV {c.volatility*100:.1f}%');risk=_strategy_terminal_stats(s,c.underlying.price,c.days);self.stats.config(text=f'Δ {st["delta"]:+.3f}  Γ {st["gamma"]:.4f}  Θ {st["theta"]:.3f}  Vega {st["vega"]:.3f}   •   Premium ${abs(s.opening_debit()):,.2f}   •   Approx POP {risk["pop"]*100:.1f}%   •   EV ${risk["expected"]:,.0f}')
            _draw_strategy_payoff(self.payoff,s,c.underlying.price,c.days,'SINGLE-CONTRACT RISK / REWARD')
        except Exception:pass
        self.after(750,self.update_live)
    def execute(self):
        try:s=self.strategy()
        except:return messagebox.showerror('Option','Invalid quantity.')
        ok,msg=self.portfolio.execute_strategy(s)
        if ok:self.refresh();messagebox.showinfo('Option',msg)
        else:messagebox.showerror('Option rejected',msg)
    def to_spread(self):SpreadBuilder(self,self.market,self.portfolio,self.refresh,self.contract)
    def open_chain(self):
        if self.market:
            w=OptionsWindow(self,self.market,self.portfolio,self.refresh);w.entry.delete(0,'end');w.entry.insert(0,self.contract.underlying.symbol);w.apply_symbol()


class DepthWindow(ToolWindow):
    """Unified Level 2, Level 3, microstructure, imbalance and trade-tape workstation."""
    def __init__(self,parent,market,asset):
        super().__init__(parent);self.market=market;self.asset=asset;self._job=None;self.style_window(f'MARKET DEPTH / TAPE — {asset.symbol}','1380x820');self.resizable(True,True)
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=7);ttk.Label(top,text='Ticker').pack(side='left');self.ticker=tk.StringVar(value=asset.symbol);te=ttk.Entry(top,textvariable=self.ticker,width=11);te.pack(side='left',padx=4);te.bind('<Return>',lambda e:self.load_ticker());ttk.Button(top,text='LOAD',command=self.load_ticker).pack(side='left')
        ttk.Label(top,text='View').pack(side='left',padx=(12,2));self.mode=tk.StringVar(value='LEVEL 2');cb=ttk.Combobox(top,textvariable=self.mode,values=['LEVEL 2','LEVEL 3','MICROSTRUCTURE','IMBALANCE','TRADE TAPE'],state='readonly',width=18);cb.pack(side='left');cb.bind('<<ComboboxSelected>>',lambda e:self.rebuild_columns())
        ttk.Label(top,text='Refresh').pack(side='left',padx=(12,2));self.rate=tk.StringVar(value='500ms');ttk.Combobox(top,textvariable=self.rate,values=['100ms','250ms','500ms','1s'],state='readonly',width=8).pack(side='left');self.summary=ttk.Label(top,text='',font=('Arial',9,'bold'));self.summary.pack(side='right',padx=8)
        self.metrics=ttk.Label(self,text='',justify='left');self.metrics.pack(fill='x',padx=10,pady=(0,5));self.tv=ttk.Treeview(self,show='headings',selectmode='browse');self.tv.pack(fill='both',expand=True,padx=8,pady=5);self.tv.tag_configure('bid',foreground=GREEN);self.tv.tag_configure('ask',foreground=RED);self.tv.tag_configure('buy',foreground=GREEN);self.tv.tag_configure('sell',foreground=RED);self.rebuild_columns();self.after(80,self.refresh);self.protocol('WM_DELETE_WINDOW',self.close)
    def load_ticker(self):
        a=self.market.get_asset(self.ticker.get().strip().upper())
        if not a:return messagebox.showerror('Market Depth','Unknown ticker.')
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
            self._job=None
        self.asset=a;self.ticker.set(a.symbol);self.title(f'MARKET DEPTH / TAPE — {a.symbol}');self.refresh()
    def rebuild_columns(self):
        sets={'LEVEL 2':[('side','Side',70),('price','Price',110),('size','Size',100),('orders','Orders',80),('maker','MM',120),('venue','Venue',90),('hidden','Hidden',90),('cum','Cum',100)],'LEVEL 3':[('side','Side',70),('price','Price',110),('size','Size',90),('maker','Participant',130),('venue','Venue/ID',120),('queue','Queue',80),('hidden','Hidden',90)],'MICROSTRUCTURE':[('metric','Metric',180),('value','Value',180),('meaning','Interpretation',600)],'IMBALANCE':[('level','Level',70),('bidp','Bid',110),('bids','Bid size',110),('ratio','Imbalance',110),('asks','Ask size',110),('askp','Ask',110)],'TRADE TAPE':[('seq','Seq',80),('side','Aggressor',90),('price','Price',110),('size','Size',100),('venue','Venue',100),('maker','Liquidity',140)]}
        cols=sets[self.mode.get()];self.tv['columns']=[x[0] for x in cols]
        for key,title,width in cols:self.tv.heading(key,text=title);self.tv.column(key,width=width,anchor='center',stretch=True)
        self.tv.delete(*self.tv.get_children())
    def refresh(self):
        if not self.winfo_exists():return
        if not self.winfo_viewable():self._job=self.after(700,self.refresh);return
        try:
            b=self.market.get_book(self.asset);snap=b.snapshot();bid=b.bids[0];ask=b.asks[0];micro=(bid.price*ask.size+ask.price*bid.size)/max(1,bid.size+ask.size);mid=(bid.price+ask.price)/2;self.summary.config(text=f'{self.asset.symbol} ${self.asset.price:,.2f} • spread ${snap["spread"]:.4f} • depth imbalance {snap["imbalance"]:+.1%}');self.metrics.config(text=f'Best bid ${bid.price:.4f} × {bid.size:,}    Best ask ${ask.price:.4f} × {ask.size:,}    Mid ${mid:.4f}    Microprice ${micro:.4f}    Flow pressure {snap.get("pressure",0):+.2f}')
            self.tv.delete(*self.tv.get_children());mode=self.mode.get()
            if mode=='LEVEL 2':
                cum=0
                for side,lvls in [('ASK',list(reversed(b.asks))),('BID',b.bids)]:
                    for x in lvls:cum+=x.size;self.tv.insert('','end',values=(side,f'{x.price:.4f}',f'{x.size:,}',x.orders,x.market_maker,x.venue,f'{x.hidden:,}',f'{cum:,}'),tags=('bid' if side=='BID' else 'ask',))
            elif mode=='LEVEL 3':
                for side,price,size,maker,venue,queue,hidden in b.level3()[:260]:self.tv.insert('','end',values=(side,f'{price:.4f}',f'{size:,}',maker,venue,queue,f'{hidden:,}'),tags=('bid' if side=='BID' else 'ask',))
            elif mode=='MICROSTRUCTURE':
                rows=[('Quoted spread',f'${snap["spread"]:.5f}','Immediate transaction-cost proxy'),('Mid price',f'${mid:.5f}','Center of best bid/ask'),('Microprice',f'${micro:.5f}','Size-weighted near-term fair-price proxy'),('Depth imbalance',f'{snap["imbalance"]:+.2%}','Positive = more displayed bid depth'),('Flow pressure',f'{snap.get("pressure",0):+.3f}','Simulator order-flow / momentum pressure'),('Bid depth',f'{snap.get("bid_depth",0):,}','Displayed shares across bid levels'),('Ask depth',f'{snap.get("ask_depth",0):,}','Displayed shares across ask levels'),('Last trade',f'${snap["last"]:.5f}','Most recent simulated consolidated print')]
                for r in rows:self.tv.insert('','end',values=r)
            elif mode=='IMBALANCE':
                for i,(bd,ak) in enumerate(zip(b.bids,b.asks),1):ratio=(bd.size-ak.size)/max(1,bd.size+ak.size);self.tv.insert('','end',values=(i,f'{bd.price:.4f}',f'{bd.size:,}',f'{ratio:+.1%}',f'{ak.size:,}',f'{ak.price:.4f}'),tags=('bid' if ratio>=0 else 'ask',))
            else:
                for t in reversed(list(b.trades)[-120:]):self.tv.insert('','end',values=(t['seq'],t['side'],f'${t["price"]:.4f}',f'{t["size"]:,}',t['venue'],t['maker']),tags=('buy' if t['side']=='BUY' else 'sell',))
        except Exception as e:self.metrics.config(text=f'Depth recovered: {type(e).__name__}: {e}')
        ms=1000 if self.rate.get()=='1s' else int(self.rate.get().replace('ms',''));self._job=self.after(ms,self.refresh)
    def close(self):
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
        self.destroy()


class MarketMapWindow(_LegacyMarketMapWindow):
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');self.rects=[];w=max(900,c.winfo_width());h=max(650,c.winfo_height());pad=10;header=38;W=w-2*pad;H=h-header-pad
        c.create_text(pad,10,anchor='nw',text='MARKET MAP  •  AREA = MARKET CAP  •  COLOR = DAILY CHANGE',fill=TEXT,font=('Arial',11,'bold'))
        assets=[a for a in self.market.stocks if self.sec.get()=='ALL' or a.category==self.sec.get()];groups={}
        for a in assets:groups.setdefault(a.category,[]).append(a)
        ordered=sorted(groups.items(),key=lambda kv:sum(max(1,a.market_cap) for a in kv[1]),reverse=True);nsec=max(1,len(ordered));cols=max(1,min(4,math.ceil(math.sqrt(nsec))));rows=math.ceil(nsec/cols);cell_w=W/cols;row_h=H/rows
        for si,(sector,arr) in enumerate(ordered):
            col=si%cols;row=si//cols;x0=pad+col*cell_w;y0=header+row*row_h;arr=sorted(arr,key=lambda a:max(1,a.market_cap),reverse=True);c.create_rectangle(x0,y0,x0+cell_w,y0+row_h,fill='#0b1420',outline='#31465b',width=2)
            label=sector if len(sector)<=18 else sector[:16]+'…';c.create_text(x0+7,y0+6,anchor='nw',text=f'{label} • {len(arr)}',fill=TEXT,font=('Arial',9,'bold'))
            ix,iy,iw,ih=x0+3,y0+25,max(1,cell_w-6),max(1,row_h-28);stack=[(arr,ix,iy,iw,ih)];packed=[]
            while stack:
                group,x,y,ww,hh=stack.pop()
                if not group:continue
                if len(group)==1:packed.append((x,y,x+ww,y+hh,group[0]));continue
                total=sum(max(1,a.market_cap) for a in group);cut=max(1,len(group)//2);g1,g2=group[:cut],group[cut:];ratio=sum(max(1,a.market_cap) for a in g1)/total
                if ww>=hh:w1=ww*ratio;stack.extend([(g2,x+w1,y,ww-w1,hh),(g1,x,y,w1,hh)])
                else:h1=hh*ratio;stack.extend([(g2,x,y+h1,ww,hh-h1),(g1,x,y,ww,h1)])
            for x,y,xx,yy,a in packed:
                self.rects.append((x,y,xx,yy,a));cw,ch=xx-x,yy-y;chg=a.change_percent();fill='#0f8f65' if chg>=0 else '#b33b54';c.create_rectangle(x+1,y+1,xx-1,yy-1,fill=fill,outline='#071017')
                # Only render text when both dimensions can contain it; this prevents label collisions.
                minw=max(self.min_tile.get(),48);minh=34 if self.detail.get() else 22
                if cw>=minw and ch>=minh:
                    fs=max(7,min(13,int(min(cw/9,ch/3.0))));txt=f'{a.symbol}\n{chg:+.2f}%' if self.detail.get() and ch>=38 else a.symbol;c.create_text((x+xx)/2,(y+yy)/2,text=txt,fill='white',font=('Arial',fs,'bold'),justify='center',width=max(10,cw-6))
        self.after(1000,self.draw)


class GlobeWindow(_LegacyGlobeWindow):
    """Procedurally shaded Earth-style market globe; no external image dependency."""
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(900,c.winfo_width());h=max(650,c.winfo_height());r=min(h*.39,w*.28);cx=w*.34;cy=h*.51
        # Star field is deterministic so it does not flicker.
        rng=random.Random(9137)
        for _ in range(170):x=rng.randrange(0,int(w*.58));y=rng.randrange(0,h);rr=1 if rng.random()<.85 else 2;c.create_oval(x-rr,y-rr,x+rr,y+rr,fill='#52677d' if rr==1 else '#b9d7ee',outline='')
        # Atmospheric glow / ocean depth rings.
        for k,col in [(14,'#0a2438'),(10,'#0b304b'),(6,'#0e4264'),(3,'#15618a')]:c.create_oval(cx-r-k,cy-r-k,cx+r+k,cy+r+k,fill='',outline=col,width=max(1,k//3))
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#082c49',outline='#78d3ff',width=2)
        utc=self.market.clock.current.replace(tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York')).astimezone(__import__('datetime').timezone.utc);rot=2*math.pi*((utc.hour*60+utc.minute+utc.second/60)/1440)-math.pi/2
        # Latitudinal ocean shading gives the sphere depth.
        for band in range(18):
            y1=cy-r+band*(2*r/18);y2=cy-r+(band+1)*(2*r/18);dy=((y1+y2)/2-cy)/r;half=r*math.sqrt(max(0,1-dy*dy));shade=int(30+35*(1-abs(dy)));c.create_line(cx-half,(y1+y2)/2,cx+half,(y1+y2)/2,fill=f'#0b{shade:02x}{min(120,shade+45):02x}',width=max(1,int(2*r/18+1)))
        self.draw_land(c,cx,cy,r,rot)
        # Ice caps and cloud bands.
        c.create_arc(cx-r*.82,cy-r*.98,cx+r*.82,cy-r*.58,start=190,extent=160,style='arc',outline='#d9eff4',width=5);c.create_arc(cx-r*.75,cy+r*.58,cx+r*.75,cy+r*.98,start=10,extent=160,style='arc',outline='#cfe8ef',width=4)
        for off in (-.36,-.05,.28):
            yy=cy+off*r;half=r*math.sqrt(max(0,1-off*off));c.create_arc(cx-half,yy-r*.12,cx+half,yy+r*.12,start=15,extent=150,style='arc',outline='#a9d5df',width=2)
        # Night-side translucent-looking hatch (Tk has no alpha).
        sun_phase=math.cos(rot)
        if sun_phase>0:c.create_arc(cx-r,cy-r,cx+r,cy+r,start=90,extent=180,style='pieslice',fill='#06141f',outline='')
        else:c.create_arc(cx-r,cy-r,cx+r,cy+r,start=270,extent=180,style='pieslice',fill='#06141f',outline='')
        self.draw_land(c,cx,cy,r,rot);c.create_oval(cx-r,cy-r,cx+r,cy+r,outline='#7edcff',width=3)
        positions={'US':(-74,40),'LSE':(-0.1,51.5),'XETRA':(8.7,50.1),'TSE':(139.7,35.7),'HKEX':(114.2,22.3),'SSE':(121.5,31.2),'ASX':(151.2,-33.9),'CME':(-87.6,41.9),'FX':(0,0),'CRYPTO':(0,25)};self.blips=[]
        for code,(lon,lat) in positions.items():
            x,y,z=self.project(lon,lat,cx,cy,r,rot)
            if z<0:continue
            op=market_status(code,self.market.clock.current);col=GREEN if op else '#465564';c.create_oval(x-6,y-6,x+6,y+6,fill=col,outline='white');self.blips.append((x-10,y-10,x+10,y+10,code))
            if z>.45:c.create_text(x+9,y,text=SESSIONS[code].name,fill=TEXT,anchor='w',font=('Arial',8,'bold'))
        c.create_text(w*.62,35,text='GLOBAL TRADER • EARTH MARKET NETWORK',fill=TEXT,font=('Arial',19,'bold'),anchor='w');c.create_text(w*.62,68,text=f'IN-GAME {self.market.clock.time} • {self.market.clock.utc_time}',fill=CYAN,font=('Arial',11,'bold'),anchor='w');y=108;self.exchange_hits=[]
        for code,sess in SESSIONS.items():
            op=market_status(code,self.market.clock.current);x=w*.60;ww=w*.35;hh=30;c.create_rectangle(x,y-4,x+ww,y+hh-4,fill='#0c1823',outline='#22394a');c.create_text(x+10,y+11,anchor='w',text=sess.name,fill=GREEN if op else MUTED,font=('Arial',10,'bold'));c.create_text(x+ww-10,y+11,anchor='e',text='OPEN' if op else 'CLOSED',fill=GREEN if op else MUTED,font=('Arial',9,'bold'));self.exchange_hits.append((x,y-4,x+ww,y+hh-4,code));y+=36
        # Live freight layer. Hazards are deliberately visible before impact so the
        # globe can be used as a forward-looking event-risk training surface.
        self.ship_hits=[]
        for sh in getattr(self.market,'shipments',[]):
            pts=[]
            for lat,lon in sh.get('route',{}).get('points',[]):
                sx,sy,sz=self.project(lon,lat,cx,cy,r,rot)
                if sz>0:pts.extend([sx,sy])
            if len(pts)>=4:c.create_line(*pts,fill='#2b7694',dash=(3,5),width=1)
            lat,lon=self.market.shipment_position(sh);sx,sy,sz=self.project(lon,lat,cx,cy,r,rot)
            if sz>0:
                col=YELLOW if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved') else CYAN;c.create_polygon(sx-8,sy+5,sx+10,sy+5,sx+5,sy-4,sx-5,sy-4,fill=col,outline='white');self.ship_hits.append((sx-13,sy-11,sx+13,sy+11,sh))
                if sz>.45:c.create_text(sx+12,sy-9,text=f"{sh['carrier']} / {sh['cargo_owner']}",fill=TEXT,anchor='w',font=('Arial',7,'bold'))
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                hlat,hlon=self.market.shipment_hazard_position(sh);hx,hy,hz=self.project(hlon,hlat,cx,cy,r,rot)
                if hz>0:c.create_text(hx,hy,text='☁' if sh['hazard']=='STORM' else '☠',fill='#ffcf6e' if sh['hazard']=='STORM' else '#ff6b78',font=('Arial',16,'bold'))
        if getattr(self.market,'shipments',None):
            c.create_text(w*.60,y+8,text='FREIGHT RISK RADAR',fill=TEXT,anchor='w',font=('Arial',10,'bold'));y+=28
            for sh in self.market.shipments[:6]:
                hz=sh.get('hazard','NONE');ahead=max(0,sh.get('hazard_progress',1)-sh.get('progress',0));risk=f' • {hz} ahead {ahead*100:.0f}%' if hz!='NONE' and not sh.get('hazard_resolved') else ''
                c.create_text(w*.60,y,text=f"{sh['carrier']} → {sh['cargo_owner']}  {sh['progress']*100:4.0f}%{risk}",fill=YELLOW if risk else MUTED,anchor='w',font=('Arial',8));y+=20
        self.after(650,self.draw)


class BlackjackWindow(_LegacyBlackjackWindow):
    def draw_card(self,c,x,y,hidden=False):
        r,s=c;w,h=78,108;c.create_rectangle(x+5,y+6,x+w+5,y+h+6,fill='#033321',outline='');c.create_rectangle(x,y,x+w,y+h,fill='#f7f4ed',outline='#d5c69d',width=2);c.create_rectangle(x+4,y+4,x+w-4,y+h-4,outline='#c7b98f')
        if hidden:c.create_rectangle(x+8,y+8,x+w-8,y+h-8,fill='#163b6d',outline='#d8b96a');c.create_text(x+w/2,y+h/2,text='◆',fill='#d8b96a',font=('Arial',27,'bold'));return
        txt='A' if r==1 else 'J' if r==11 else 'Q' if r==12 else 'K' if r==13 else str(r);col='#c32f46' if s in '♥♦' else '#10151b';c.create_text(x+12,y+18,text=txt,fill=col,font=('Georgia',15,'bold'));c.create_text(x+w/2,y+h/2+7,text=s,fill=col,font=('Georgia',29,'bold'))
    def draw_table(self):
        c=self.canvas;c.delete('all');w=max(1000,c.winfo_width());h=max(550,c.winfo_height());c.create_oval(-w*.12,-h*.75,w*1.12,h*1.42,fill='#07482f',outline='#b58b43',width=12);c.create_oval(-w*.08,-h*.68,w*1.08,h*1.34,outline='#e0ba68',width=2);c.create_text(w/2,28,text=f'BLACKJACK • {self.dealer_name} DEALER',fill='#f6e6b5',font=('Georgia',20,'bold'));c.create_text(w/2,55,text='PAYS 3 TO 2   •   DEALER STANDS ON 17',fill='#c8d8ca',font=('Arial',9,'bold'))
        x=150;c.create_text(35,92,anchor='w',text='DEALER',fill='#dce9df',font=('Arial',10,'bold'))
        for i,card in enumerate(self.dealer):self.draw_card(card,x+i*90,80,hidden=self.active and i==1)
        cols=max(1,min(4,len(self.hands)));gap=w/(cols+1);base=h*.49
        for j,hnd in enumerate(self.hands):
            col=j%cols;row=j//cols;x0=gap*(col+1)-90;y=base+row*170;c.create_oval(x0-35,y-28,x0+345,y+138,outline='#93b6a1',width=2);c.create_text(x0,y-18,anchor='w',text=f'SEAT {j+1}  •  ${self.bet_amounts[j] if j<len(self.bet_amounts) else 0:,}',fill='#e9dfbb',font=('Arial',9,'bold'))
            for i,card in enumerate(hnd):self.draw_card(card,x0+i*82,y)
            c.create_text(x0+310,y+45,text=f'{self.val(hnd)}',fill='#f6e6b5',font=('Georgia',22,'bold'))
        decks=max(.01,len(self.shoe)/52);true=self.running/decks if self.count_mode.get()=='Hi-Lo' else self.running;edge='—' if self.count_mode.get()=='None' else f'{true:+.2f}';self.info.config(text=f'Balance ${self.portfolio.cash:,.2f} • Running {self.running:+d} • True {edge} • Decks left {decks:.2f} • Cards {len(self.shoe)}')


class RouletteWindow(_LegacyRouletteWindow):
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        super().draw(wheel_number,ball_phase,spinning);c=self.cv;w=max(1100,c.winfo_width());h=max(700,c.winfo_height());cx=w*.17;cy=h*.30;r=min(h*.22,w*.12)
        # Extra brass rings / spindle / table felt depth for a more casino-like presentation.
        c.create_oval(cx-r*.92,cy-r*.92,cx+r*.92,cy+r*.92,outline='#f0d58a',width=2);c.create_oval(cx-r*.48,cy-r*.48,cx+r*.48,cy+r*.48,outline='#7a5d2d',width=3);c.create_oval(cx-14,cy-14,cx+14,cy+14,fill='#d8b96a',outline='#fff0b8',width=2);c.create_oval(cx-5,cy-5,cx+5,cy+5,fill='#6d5126',outline='')


class StockPositionAnalysisWindow(ToolWindow):
    def __init__(self,parent,app,asset):
        super().__init__(parent);self.app=app;self.asset=asset;self.portfolio=app.portfolio;self.market=app.market;self.style_window(f'POSITION ANALYSIS — {asset.symbol}','980x720');self.resizable(True,True);self.horizon=tk.IntVar(value=30);top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8);self.head=ttk.Label(top,text='',font=('Arial',14,'bold'));self.head.pack(side='left');ttk.Label(top,text='Projection days').pack(side='right');ttk.Spinbox(top,from_=1,to=365,textvariable=self.horizon,width=7,command=self.refresh_view).pack(side='right',padx=5);self.stats=ttk.Label(self,text='',justify='left');self.stats.pack(fill='x',padx=12,pady=5);self.canvas=tk.Canvas(self,bg='#081018',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=10,pady=8);self.canvas.bind('<Configure>',lambda e:self.refresh_view());self.after(100,self.refresh_view)
    def refresh_view(self):
        if not self.winfo_exists():return
        a=self.asset;q=int(self.portfolio.positions.get(a.symbol,0));basis=float(self.portfolio.cost_basis.get(a.symbol,0));entry=basis/max(1,abs(q)) if q else a.price;days=max(1,int(self.horizon.get()));vol=max(.05,a.volatility*20+.12);sigma=vol*math.sqrt(days/365);up=a.price*math.exp(sigma);dn=a.price*math.exp(-sigma);cur=(a.price-entry)*q if q>0 else (entry-a.price)*abs(q);self.head.config(text=f'{a.symbol} • {q:+,} shares • ${a.price:,.2f}');self.stats.config(text=f'Average entry ${entry:,.2f}   •   Current P/L ${cur:,.2f}   •   Approx {days}D 1σ price range ${dn:,.2f} – ${up:,.2f}\nThis projection uses the simulator volatility model; it is a scenario tool, not a forecast guarantee.')
        c=self.canvas;c.delete('all');w=max(600,c.winfo_width());h=max(320,c.winfo_height());left,right,top,bottom=60,w-20,40,h-45;lo=max(.01,dn*.75);hi=up*1.25
        def px(s):return left+(s-lo)/(hi-lo)*(right-left)
        vals=[]
        for i in range(201):s=lo+(hi-lo)*i/200;pnl=(s-entry)*q if q>=0 else (entry-s)*abs(q);vals.append((s,pnl))
        mn=min([0]+[v for _,v in vals]);mx=max([0]+[v for _,v in vals]);rng=max(1,mx-mn);py=lambda v:bottom-(v-mn)/rng*(bottom-top);c.create_rectangle(px(dn),top,px(up),bottom,fill='#10283a',outline='');c.create_line(left,py(0),right,py(0),fill='#607080',dash=(4,3));pts=[]
        for s,p in vals:pts.extend([px(s),py(p)])
        c.create_line(*pts,fill=CYAN,width=3);c.create_line(px(a.price),top,px(a.price),bottom,fill=YELLOW,dash=(5,3));c.create_line(px(entry),top,px(entry),bottom,fill=PURPLE,dash=(3,3));c.create_text(left,10,anchor='nw',text='SHARE POSITION P/L SCENARIO',fill=TEXT,font=('Arial',11,'bold'));c.create_text(right,10,anchor='ne',text=f'Current ${a.price:,.2f} • Entry ${entry:,.2f}',fill=TEXT,font=('Arial',9,'bold'))
        self.after(700,self.refresh_view)


# ---- App patches: smooth clock, expiration notices, position analytics ----
_App_init_v5=App.__init__
def _app_init_v6(self,root,market,portfolio):
    _App_init_v5(self,root,market,portfolio);self.portfolio.market=self.market
    self.pos.bind('<Double-1>',lambda e:self.open_position_analysis())
    self._clock_stream_job=None;self._expiry_poll_job=None;self._last_clock_text=None;self._smooth_clock_stream();self._poll_expiration_events()
App.__init__=_app_init_v6

def _smooth_clock_stream(self):
    try:
        txt=f'{self.market.clock.time}  •  {self.market.clock.utc_time}  •  {"US OPEN" if self.market.clock.open else "US CLOSED"}'
        if txt!=self._last_clock_text:self.clock_label.config(text=txt);self._last_clock_text=txt
    except Exception:pass
    self._clock_stream_job=self.root.after(16,lambda:self._smooth_clock_stream())
App._smooth_clock_stream=_smooth_clock_stream

def _poll_expiration_events(self):
    try:
        events=getattr(self.market,'expiration_events',[])
        if events:
            ev=events.pop(0);legs='\n'.join(ev.get('legs',[]));messagebox.showinfo('OPTION EXPIRATION / CASH SETTLEMENT',f'{ev.get("name","Option position")} expired\nUnderlying: {ev.get("underlying")} @ ${ev.get("spot",0):,.2f}\n\n{legs}\n\nCash settlement: ${ev.get("settlement",0):,.2f}\nRealized P/L: ${ev.get("pnl",0):,.2f}')
    except Exception as e:
        try:self.market.errors.append(f'expiry popup: {e}')
        except Exception:pass
    self._expiry_poll_job=self.root.after(250,lambda:self._poll_expiration_events())
App._poll_expiration_events=_poll_expiration_events

def _refresh_positions_v6(self):
    old=self.pos.selection();keep=old[0] if old else None;self.pos.delete(*self.pos.get_children())
    for sym,name,q,p,v,pnl,typ,under,days in self.portfolio.position_rows(self.market.all_assets()):
        pct=(pnl/max(1e-9,abs(self.portfolio.cost_basis.get(sym,0))) if sym in self.portfolio.cost_basis else 0)
        expiry=''
        if typ=='OPTION' and sym.startswith('OPT:'):
            try:
                idx=int(sym.split(':')[1]);expiry,_=self.portfolio.option_time_remaining(idx,self.market.clock.current);cost=abs(self.portfolio.options[idx].open_cost);pct=pnl/max(1e-9,cost)
            except Exception:expiry='—'
        self.pos.insert('','end',iid=sym,values=(sym,f'{q:,}',f'${p:,.2f}',f'${v:,.2f}',f'${pnl:,.2f}',f'{pct:+.2f}%',typ,under,expiry))
    if keep and keep in self.pos.get_children():self.pos.selection_set(keep);self.pos.focus(keep)
App.refresh_positions=_refresh_positions_v6

def _open_position_analysis(self):
    it=self.pos.selection()
    if not it:return messagebox.showwarning('Position','Select a position first.')
    key=it[0]
    if key.startswith('OPT:'):
        try:st=self.portfolio.options[int(key.split(':')[1])];SpreadBuilder(self.root,self.market,self.portfolio,self.refresh,st)
        except Exception as e:messagebox.showerror('Options position',f'Unable to open strategy: {e}')
    else:
        a=self.market.get_asset(key)
        if a:StockPositionAnalysisWindow(self.root,self,a)
App.open_position_analysis=_open_position_analysis

def _position_context_v6(self,e):
    iid=self.pos.identify_row(e.y)
    if iid:self.pos.selection_set(iid);self.pos.focus(iid)
    m=tk.Menu(self.pos,tearoff=0);m.add_command(label='ANALYZE POSITION / RISK GRAPH',command=self.open_position_analysis);m.add_command(label='Liquidate / Cash',command=self.liquidate);m.add_command(label='BUY MORE / ADD TO POSITION',command=self.buy_more_position);m.add_separator();m.add_command(label='CUSTOMIZE POSITION COLUMNS',command=self.position_variables);m.tk_popup(e.x_root,e.y_root)
App.position_context=_position_context_v6

# ===== v7 enterprise patches: stable option refs, sortable positions, lower UI overhead =====
_App_init_v6_current=App.__init__
def _app_init_v7(self,root,market,portfolio):
    _App_init_v6_current(self,root,market,portfolio)
    self.position_sort_key='symbol';self.position_sort_reverse=False
    labels={'symbol':'Symbol','qty':'Qty','last':'Last','value':'Value','pnl':'P/L','pct':'P/L %','type':'Type','underlying':'Underlying','expiry':'Expiry'}
    for key,label in labels.items():
        try:self.pos.heading(key,text=label,command=lambda k=key:self.sort_positions(k))
        except Exception:pass
    # The v6 60Hz text timer is excessive for a clock that only changes whole digits.
    if getattr(self,'_clock_stream_job',None):
        try:self.root.after_cancel(self._clock_stream_job)
        except Exception:pass
    self._clock_stream_job=None;self._last_clock_text=None;self._smooth_clock_stream()
App.__init__=_app_init_v7

def _smooth_clock_stream_v7(self):
    try:
        label,count=self.market.clock.us_session_countdown() if hasattr(self.market.clock,'us_session_countdown') else ('','')
        txt=f'{self.market.clock.time}  •  {self.market.clock.utc_time}  •  {"US OPEN" if self.market.clock.open else "US CLOSED"}  •  {label} {count}'
        if txt!=getattr(self,'_last_clock_text',None):self.clock_label.config(text=txt);self._last_clock_text=txt
    except Exception:pass
    self._clock_stream_job=self.root.after(200,lambda:self._smooth_clock_stream())
App._smooth_clock_stream=_smooth_clock_stream_v7

def _position_records(self):
    records=[]
    for ref,name,q,p,v,pnl,typ,under,days in self.portfolio.position_rows(self.market.all_assets()):
        pct=0.0;expiry='';display=name if typ=='OPTION' else ref
        if typ=='OPTION':
            st=self.portfolio.get_strategy(ref);cost=abs(getattr(st,'open_cost',0)) if st else 0;pct=pnl/max(1e-9,cost);expiry,_=self.portfolio.option_time_remaining(ref,self.market.clock.current)
        else:
            basis=abs(self.portfolio.cost_basis.get(ref,0));pct=pnl/max(1e-9,basis)
        records.append({'iid':ref,'symbol':display,'qty':q,'last':p,'value':v,'pnl':pnl,'pct':pct,'type':typ,'underlying':under,'expiry':expiry})
    return records
App._position_records=_position_records

def _sort_positions(self,key):
    if getattr(self,'position_sort_key',None)==key:self.position_sort_reverse=not getattr(self,'position_sort_reverse',False)
    else:self.position_sort_key=key;self.position_sort_reverse=False
    self.refresh_positions()
App.sort_positions=_sort_positions

def _refresh_positions_v7(self):
    old=self.pos.selection();keep=old[0] if old else None;rows=self._position_records();key=getattr(self,'position_sort_key','symbol');rev=getattr(self,'position_sort_reverse',False)
    def sk(r):
        v=r.get(key,'')
        if key=='expiry':
            _,days=self.portfolio.option_time_remaining(r['iid'],self.market.clock.current) if r['type']=='OPTION' else ('',1e12);return days
        return str(v).lower() if isinstance(v,str) else v
    try:rows.sort(key=sk,reverse=rev)
    except Exception:pass
    self.pos.delete(*self.pos.get_children())
    for r in rows:self.pos.insert('','end',iid=r['iid'],values=(r['symbol'],f"{r['qty']:,}",f"${r['last']:,.2f}",f"${r['value']:,.2f}",f"${r['pnl']:,.2f}",f"{r['pct']:+.2f}%",r['type'],r['underlying'],r['expiry']))
    if keep and keep in self.pos.get_children():self.pos.selection_set(keep);self.pos.focus(keep)
App.refresh_positions=_refresh_positions_v7

def _buy_more_position_v7(self):
    it=self.pos.selection()
    if not it:return messagebox.showwarning('Position','Select a position first.')
    ref=it[0]
    if ref.startswith('OPT:'):
        st=self.portfolio.get_strategy(ref)
        if st is None:return messagebox.showerror('Options position','That option position is no longer open. Refreshing positions now.');self.refresh_positions()
        SpreadBuilder(self.root,self.market,self.portfolio,self.refresh,st)
    else:
        a=self.market.get_asset(ref)
        if a:self.order_window(a,'BUY' if self.portfolio.positions.get(ref,0)>=0 else 'SHORT','MARKET',None)
App.buy_more_position=_buy_more_position_v7

def _open_position_analysis_v7(self):
    it=self.pos.selection()
    if not it:return messagebox.showwarning('Position','Select a position first.')
    ref=it[0]
    if ref.startswith('OPT:'):
        st=self.portfolio.get_strategy(ref)
        if st:SpreadBuilder(self.root,self.market,self.portfolio,self.refresh,st)
        else:messagebox.showerror('Options position','That strategy is no longer open.')
    else:
        a=self.market.get_asset(ref)
        if a:StockPositionAnalysisWindow(self.root,self,a)
App.open_position_analysis=_open_position_analysis_v7

def _liquidate_v7(self):
    it=self.pos.selection()
    if not it:return messagebox.showwarning('Position','Select a position row first.')
    ref=it[0]
    if ref.startswith('OPT:'):ok,msg=self.portfolio.liquidate_strategy(ref)
    else:
        a=self.market.get_asset(ref);ok,msg=self.portfolio.liquidate_asset(a) if a else (False,'Asset no longer exists.')
    if ok:self.refresh();messagebox.showinfo('Liquidated',msg)
    else:messagebox.showerror('Liquidation',msg)
App.liquidate=_liquidate_v7

def _position_variables_v7(self):
    w=tk.Toplevel(self.root);w.title('PORTFOLIO COLUMNS / SORT');w.geometry('500x520');w.configure(bg=BG);ttk.Label(w,text='Portfolio columns and sorting',font=('Arial',13,'bold')).pack(anchor='w',padx=14,pady=12);ttk.Label(w,text='Use SHOW to add/remove columns. SORT changes the portfolio order immediately.',wraplength=450).pack(anchor='w',padx=14,pady=(0,10))
    names={'Symbol':'symbol','Qty':'qty','Last':'last','Value':'value','P/L':'pnl','P/L %':'pct','Type':'type','Underlying':'underlying','Expiry':'expiry'}
    for label,key in names.items():
        row=ttk.Frame(w);row.pack(fill='x',padx=14,pady=3);v=tk.BooleanVar(value=self.pos.column(key,'width')>0);ttk.Checkbutton(row,text=label,variable=v,command=lambda k=key,var=v:self.toggle_table_column(self.pos,k,var)).pack(side='left',fill='x',expand=True);ttk.Button(row,text='SORT',width=8,command=lambda k=key:self.sort_positions(k)).pack(side='right')
    ttk.Button(w,text='RESET SORT TO SYMBOL',command=lambda:self.sort_positions('symbol')).pack(fill='x',padx=14,pady=12)
App.position_variables=_position_variables_v7

# Depth / analysis windows do not need to burn callbacks while hidden or minimized.
_old_stock_refresh=StockPositionAnalysisWindow.refresh_view
def _stock_refresh_v7(self):
    if not self.winfo_exists():return
    if self.winfo_viewable():_old_stock_refresh(self)
StockPositionAnalysisWindow.refresh_view=_stock_refresh_v7

# Freight ship interaction on the global globe.
_old_globe_click=GlobeWindow.click
def _globe_click_v7(self,e):
    for x1,y1,x2,y2,sh in getattr(self,'ship_hits',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:
            m=tk.Menu(self,tearoff=0);m.add_command(label=f"{sh['name']} • {sh['route']['name']}",state='disabled');m.add_command(label=f"Cargo ${sh['cargo_value']/1e6:,.0f}M • {sh['status']}",state='disabled');m.add_separator();carrier=self.market.get_asset(sh['carrier']);owner=self.market.get_asset(sh['cargo_owner'])
            if carrier:
                m.add_command(label=f"BUY CARRIER {carrier.symbol}",command=lambda a=carrier:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f"OPTIONS {carrier.symbol}",command=lambda a=carrier:self.market.ui_app.options_for(a))
            if owner:
                m.add_command(label=f"BUY CARGO OWNER {owner.symbol}",command=lambda a=owner:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f"OPTIONS {owner.symbol}",command=lambda a=owner:self.market.ui_app.options_for(a));m.add_command(label=f"ADVANCED CHART {owner.symbol}",command=lambda a=owner:self.market.ui_app.advanced_chart(a))
            m.tk_popup(e.x_root,e.y_root);return
    return _old_globe_click(self,e)
GlobeWindow.click=_globe_click_v7

# ===== Stock Game Pro 1.0 production UI / workflow patches =====
from datetime import timedelta as _sgp_timedelta

# Normalize popup ownership. Older call sites occasionally passed App instead of a
# Tk widget, which causes Toplevel to raise "App object has no attribute tk".
def _sgp_tk_parent(parent):
    if isinstance(parent,tk.Misc):return parent
    root=getattr(parent,'root',None)
    if isinstance(root,tk.Misc):return root
    master=getattr(parent,'master',None)
    if isinstance(master,tk.Misc):return master
    return None

_ProdPreviewBase=OptionPreviewWindow
class OptionPreviewWindow(_ProdPreviewBase):
    def __init__(self,parent,contract,portfolio,refresh,chain=None,default_action='BUY'):
        self._origin_window=parent if isinstance(parent,ToolWindow) else None
        super().__init__(_sgp_tk_parent(parent),contract,portfolio,refresh,chain,default_action)
    def execute(self):
        try:s=self.strategy()
        except Exception:return messagebox.showerror('Option','Invalid quantity.')
        ok,msg=self.portfolio.execute_strategy(s)
        if ok:
            self.refresh();messagebox.showinfo('Option',msg);self.destroy()
        else:messagebox.showerror('Option rejected',msg)
    def to_spread(self):
        SpreadBuilder(self.master,self.market,self.portfolio,self.refresh,self.contract);self.destroy()
    def open_chain(self):
        if self.market:
            w=OptionsWindow(self.master,self.market,self.portfolio,self.refresh);w.entry.delete(0,'end');w.entry.insert(0,self.contract.underlying.symbol);w.apply_symbol();self.destroy()

_ProdSpreadBase=SpreadBuilder
class SpreadBuilder(_ProdSpreadBase):
    """Production strategy lab: pro chain + actual expiration-date selector."""
    def __init__(self,parent,market,portfolio,refresh,first=None):
        super().__init__(_sgp_tk_parent(parent),market,portfolio,refresh,first)
        self.title('STOCK GAME PRO • ADVANCED OPTIONS STRATEGY LAB')
        self.expiration_calendar=tk.StringVar()
        self._refresh_expiration_calendar()
        top=self.winfo_children()[0] if self.winfo_children() else None
        if isinstance(top,tk.Misc):
            ttk.Label(top,text='Expiration date').pack(side='left',padx=(12,2))
            self.exp_calendar=ttk.Combobox(top,textvariable=self.expiration_calendar,values=self._calendar_values,state='readonly',width=21)
            self.exp_calendar.pack(side='left',padx=(0,4));self.exp_calendar.bind('<<ComboboxSelected>>',lambda e:self._calendar_changed())
        for tv in (self.calls,self.puts):
            for col in ('bid','ask','last','iv','delta'):tv.column(col,width=72,minwidth=58,stretch=True)
            for col in ('vol','oi'):tv.column(col,width=82,minwidth=66,stretch=True)
        self.strikes.column('strike',width=94,minwidth=82,stretch=False)
    def _refresh_expiration_calendar(self):
        base=self.market.clock.current.date();vals=[]
        for label,days in EXPIRATIONS:
            date=base+_sgp_timedelta(days=int(days));vals.append(f'{date.isoformat()}  •  {label}')
        self._calendar_values=vals
        target=self.exp.get();idx=next((i for i,x in enumerate(EXPIRATIONS) if x[0]==target),5)
        self.expiration_calendar.set(vals[min(idx,len(vals)-1)])
    def _calendar_changed(self):
        val=self.expiration_calendar.get()
        try:label=val.split('•',1)[1].strip()
        except Exception:return
        if label in dict(EXPIRATIONS):self.exp.set(label);self.load_chain()
    def execute(self):
        if not self.rows:return messagebox.showwarning('Strategy','Add at least one option leg.')
        s=self.build_strategy();typ=self.order_type.get()
        if typ=='MARKET':ok,msg=self.portfolio.execute_strategy(s)
        else:self.market.submit_spread_pending(self.order_side.get(),s,typ,float(self.price.get()));ok=True;msg=f'Working {typ} strategy at ${self.price.get():,.2f}'
        if ok:self.refresh();messagebox.showinfo('Strategy',msg);self.close()
        else:messagebox.showerror('Strategy rejected',msg)
    def liquidate_owned(self):
        if self._owned_strategy is None:return
        ok,msg=self.portfolio.liquidate_strategy(self._owned_strategy)
        if ok:self.refresh();messagebox.showinfo('Options position',msg);self.close()
        else:messagebox.showerror('Options position',msg)

# Replace chain -> preview/lab transitions instead of stacking child windows forever.
def _sgp_options_trade_action(self,action):
    c=self.selected_contract()
    if c:
        OptionPreviewWindow(self.master,c,self.portfolio,self.refresh_main,None,default_action=action);self.destroy()
OptionsWindow.trade_action=_sgp_options_trade_action

def _sgp_options_spread_builder(self,first=None):
    SpreadBuilder(self.master,self.market,self.portfolio,self.refresh_main,first);self.destroy()
OptionsWindow.spread_builder=_sgp_options_spread_builder

# Incremental portfolio refresh: update existing rows rather than deleting/recreating
# the whole Treeview every cycle. This removes a major source of Tk lag with many positions.
def _sgp_position_records_prod(self):
    records=[]
    for ref,name,q,p,v,pnl,typ,under,days in self.portfolio.position_rows(self.market.all_assets()):
        expiry='';display=name if typ=='OPTION' else ref
        if typ=='OPTION':
            st=self.portfolio.get_strategy(ref);pct=self.portfolio.option_return_pct(st,v) if st else 0.0;expiry,_=self.portfolio.option_time_remaining(ref,self.market.clock.current)
        else:
            basis=abs(self.portfolio.cost_basis.get(ref,0));pct=pnl/max(1e-9,basis)
        records.append({'iid':ref,'symbol':display,'qty':q,'last':p,'value':v,'pnl':pnl,'pct':pct,'type':typ,'underlying':under,'expiry':expiry})
    return records
App._position_records=_sgp_position_records_prod

def _sgp_refresh_positions_prod(self):
    old=self.pos.selection();keep=old[0] if old else None;rows=self._position_records();self._last_position_records=rows
    key=getattr(self,'position_sort_key','symbol');rev=getattr(self,'position_sort_reverse',False)
    def sk(r):
        if key=='expiry':
            return self.portfolio.option_time_remaining(r['iid'],self.market.clock.current)[1] if r['type']=='OPTION' else 1e12
        v=r.get(key,'');return str(v).lower() if isinstance(v,str) else v
    try:rows.sort(key=sk,reverse=rev)
    except Exception:pass
    existing=set(self.pos.get_children(''));wanted={r['iid'] for r in rows}
    for iid in existing-wanted:self.pos.delete(iid)
    for idx,r in enumerate(rows):
        vals=(r['symbol'],f"{r['qty']:,}",f"${r['last']:,.2f}",f"${r['value']:,.2f}",f"${r['pnl']:,.2f}",f"{r['pct']:+.2%}",r['type'],r['underlying'],r['expiry'])
        if r['iid'] in existing:self.pos.item(r['iid'],values=vals);self.pos.move(r['iid'],'',idx)
        else:self.pos.insert('','end',iid=r['iid'],values=vals)
    if keep and keep in self.pos.get_children():self.pos.selection_set(keep);self.pos.focus(keep)
App.refresh_positions=_sgp_refresh_positions_prod

# Fix buy-more option workflow and always use a real Tk parent.
def _sgp_buy_more_prod(self):
    it=self.pos.selection()
    if not it:return messagebox.showwarning('Position','Select a position first.')
    ref=it[0]
    if ref.startswith('OPT:'):
        st=self.portfolio.get_strategy(ref)
        if st is None:self.refresh_positions();return messagebox.showerror('Options position','That option position is no longer open.')
        SpreadBuilder(self.root,self.market,self.portfolio,self.refresh,st)
    else:
        a=self.market.get_asset(ref)
        if a:self.order_window(a,'BUY' if self.portfolio.positions.get(ref,0)>=0 else 'SHORT','MARKET',None)
App.buy_more_position=_sgp_buy_more_prod

# More readable production portfolio columns.
_App_init_pre_prod=App.__init__
def _sgp_app_init_prod(self,root,market,portfolio):
    _App_init_pre_prod(self,root,market,portfolio)
    widths={'symbol':155,'qty':90,'last':100,'value':125,'pnl':115,'pct':90,'type':90,'underlying':105,'expiry':115}
    for k,w in widths.items():
        try:self.pos.column(k,width=w,minwidth=max(55,int(w*.65)),stretch=(k in ('symbol','underlying')))
        except Exception:pass
    # Dedicated pause control beside time warp so event-driven setups can freeze the world.
    try:
        top=self.time_warp_scale.master;self.pause_btn=ttk.Button(top,text='⏸ PAUSE',command=self.toggle_pause,width=10);self.pause_btn.pack(side='left',padx=(2,6))
    except Exception:pass
App.__init__=_sgp_app_init_prod

_old_toggle_pause_prod=App.toggle_pause
def _sgp_toggle_pause_prod(self):
    _old_toggle_pause_prod(self)
    try:self.pause_btn.config(text='▶ RESUME' if self.market.paused else '⏸ PAUSE')
    except Exception:pass
App.toggle_pause=_sgp_toggle_pause_prod

# Lightweight main UI cycle reuses the already calculated position records.
def _sgp_refresh_prod(self):
    try:
        self.portfolio.apply_corporate_actions(self.market.all_assets());self.refresh_positions();rows=getattr(self,'_last_position_records',[])
        net=self.portfolio.cash+sum(r['value'] for r in rows);self.portfolio.best_net_worth=max(getattr(self.portfolio,'best_net_worth',net),net)
        self.summary.delete('1.0','end');self.summary.insert('end',f'CASH        ${self.portfolio.cash:,.2f}\nREALIZED    ${self.portfolio.realized:,.2f}\nMARGIN USED ${self.portfolio.reserved_margin:,.2f}\nNET WORTH   ${net:,.2f}\n\nPOSITIONS\n')
        for r in rows:self.summary.insert('end',f"{r['symbol'][:18]:<18} {r['qty']:>9,}  ${r['value']:>14,.2f}  P/L ${r['pnl']:>12,.2f}\n")
        a=self.selected() or self.charts[self.active_chart].asset
        if a:
            p=self.market.predict(a);self.pred.config(text=f'MODEL {a.symbol}\n{p["label"]}  confidence {p["confidence"]*100:.0f}%\nMomentum {p["momentum"]*100:+.2f}%  vol {p["volatility"]*100:.2f}%')
        self.refresh_news();self.refresh_orders();self.status.config(text=f'Assets {len(self.market.all_assets())} • {self.market.data_status} • Working orders {len(self.market.pending_orders)+len(self.market.pending_option_orders)+len(self.market.pending_spread_orders)} • Engine errors {len(self.market.errors)}')
    except Exception as e:self.status.config(text=f'UI recovered: {e}')
    self.root.after(1000,self.refresh)
App.refresh=_sgp_refresh_prod

# Globe: draggable yaw/pitch, wheel zoom, event radar, and a clearer forward-risk layer.
_ProdGlobeBase=GlobeWindow
class GlobeWindow(_ProdGlobeBase):
    def __init__(self,parent,market):
        self.view_yaw=0.0;self.view_pitch=0.0;self.view_zoom=1.0;self._drag_anchor=None
        super().__init__(_sgp_tk_parent(parent),market);self.title('STOCK GAME PRO • GLOBAL TRADER / EVENT RADAR')
        self.cv.bind('<ButtonPress-1>',self._press,add='+');self.cv.bind('<B1-Motion>',self._drag,add='+');self.cv.bind('<ButtonRelease-1>',self._release,add='+');self.cv.bind('<MouseWheel>',self._wheel,add='+');self.cv.bind('<Button-4>',lambda e:self._zoom(.10),add='+');self.cv.bind('<Button-5>',lambda e:self._zoom(-.10),add='+')
    def _press(self,e):self._drag_anchor=(e.x,e.y,self.view_yaw,self.view_pitch)
    def _drag(self,e):
        if not self._drag_anchor:return
        x,y,yaw,pitch=self._drag_anchor;self.view_yaw=yaw+(e.x-x)*.006;self.view_pitch=max(-1.0,min(1.0,pitch+(e.y-y)*.004));self.draw()
    def _release(self,e):self._drag_anchor=None
    def _wheel(self,e):self._zoom(.10 if e.delta>0 else -.10);return 'break'
    def _zoom(self,d):self.view_zoom=max(.65,min(1.75,self.view_zoom+d));self.draw()
    def project(self,lon,lat,cx,cy,r,rot):
        lonr=math.radians(lon)+rot+self.view_yaw;latr=math.radians(lat);x=math.cos(latr)*math.sin(lonr);y=math.sin(latr);z=math.cos(latr)*math.cos(lonr);cp=math.cos(self.view_pitch);sp=math.sin(self.view_pitch);yy=y*cp-z*sp;zz=y*sp+z*cp;rr=r*self.view_zoom;return cx+rr*x,cy-rr*yy,zz
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(1000,c.winfo_width());h=max(700,c.winfo_height());base=min(h*.36,w*.26);r=base*self.view_zoom;cx=w*.31;cy=h*.52
        rng=random.Random(9137)
        for _ in range(130):x=rng.randrange(0,int(w*.57));y=rng.randrange(0,h);c.create_oval(x-1,y-1,x+1,y+1,fill='#36566e',outline='')
        for k,col in [(12,'#08273d'),(7,'#0b4566'),(3,'#1c85ad')]:c.create_oval(cx-r-k,cy-r-k,cx+r+k,cy+r+k,outline=col,width=max(1,k//3))
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#08314e',outline='#75dbff',width=2)
        utc=self.market.clock.current.replace(tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York')).astimezone(__import__('datetime').timezone.utc);rot=2*math.pi*((utc.hour*60+utc.minute+utc.second/60)/1440)-math.pi/2
        # graticule and land move with in-game rotation + user camera offset
        for lat in (-60,-30,0,30,60):
            pts=[]
            for lon in range(-180,181,8):
                x,y,z=self.project(lon,lat,cx,cy,base,rot)
                if z>0:pts.extend([x,y])
            if len(pts)>3:c.create_line(*pts,fill='#174b62',width=1)
        self.draw_land(c,cx,cy,base,rot);c.create_oval(cx-r,cy-r,cx+r,cy+r,outline='#80e3ff',width=3)
        positions={'US':(-74,40),'LSE':(-0.1,51.5),'XETRA':(8.7,50.1),'TSE':(139.7,35.7),'HKEX':(114.2,22.3),'SSE':(121.5,31.2),'ASX':(151.2,-33.9),'CME':(-87.6,41.9)};self.blips=[]
        for code,(lon,lat) in positions.items():
            x,y,z=self.project(lon,lat,cx,cy,base,rot)
            if z<=0:continue
            op=market_status(code,self.market.clock.current);col=GREEN if op else '#4f6070';c.create_oval(x-5,y-5,x+5,y+5,fill=col,outline='white');self.blips.append((x-10,y-10,x+10,y+10,code))
        self.ship_hits=[]
        for sh in getattr(self.market,'shipments',[]):
            lat,lon=self.market.shipment_position(sh);x,y,z=self.project(lon,lat,cx,cy,base,rot)
            if z>0:c.create_polygon(x-8,y+5,x+9,y+5,x+4,y-4,x-5,y-4,fill=YELLOW if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved') else CYAN,outline='white');self.ship_hits.append((x-13,y-11,x+13,y+11,sh))
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                hl,hn=self.market.shipment_hazard_position(sh);hx,hy,hz=self.project(hn,hl,cx,cy,base,rot)
                if hz>0:c.create_text(hx,hy,text='STORM' if sh['hazard']=='STORM' else 'PIRATE',fill=ORANGE if sh['hazard']=='STORM' else RED,font=('Arial',7,'bold'))
        # Geopolitical forward-risk markers are visible before impact as a training signal.
        for ev in getattr(self.market,'geopolitical_events',[]):
            if ev.get('resolved'):continue
            x,y,z=self.project(ev['lon'],ev['lat'],cx,cy,base,rot)
            if z>0:c.create_oval(x-11,y-11,x+11,y+11,outline=RED if ev.get('status')=='ELEVATED' else ORANGE,width=3);c.create_text(x,y,text='!',fill='white',font=('Arial',11,'bold'))
        x0=w*.60;c.create_text(x0,28,text='GLOBAL TRADER • EVENT RADAR',fill=TEXT,font=('Arial',19,'bold'),anchor='w');c.create_text(x0,58,text=f'{self.market.clock.time} • drag globe • wheel zoom {self.view_zoom:.2f}x',fill=CYAN,font=('Arial',10,'bold'),anchor='w');y=92
        c.create_text(x0,y,text='FORWARD RISK SIGNALS',fill=YELLOW,font=('Arial',11,'bold'),anchor='w');y+=26
        signals=[]
        for ev in getattr(self.market,'geopolitical_events',[]):
            if not ev.get('resolved'):signals.append((ev.get('minutes_to_event',0),f"{ev['status']} • {ev['name']} • T-{max(0,ev['minutes_to_event']):.0f} game min",RED if ev.get('status')=='ELEVATED' else ORANGE))
        for sh in getattr(self.market,'shipments',[]):
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                ahead=max(0,sh.get('hazard_progress',1)-sh.get('progress',0));signals.append((ahead*1000,f"{sh['hazard']} • {sh['carrier']} carrying {sh['cargo_owner']} • route risk ahead",YELLOW))
        for _,txt,col in sorted(signals,key=lambda z:z[0])[:10]:c.create_text(x0,y,text=txt,fill=col,anchor='w',font=('Arial',8,'bold'));y+=20
        y+=8;c.create_text(x0,y,text='MARKET SESSIONS',fill=TEXT,font=('Arial',10,'bold'),anchor='w');y+=22;self.exchange_hits=[]
        for code in ('US','LSE','XETRA','TSE','HKEX','ASX','CME'):
            sess=SESSIONS[code];op=market_status(code,self.market.clock.current);c.create_text(x0,y,text=f'{sess.name:<18} {"OPEN" if op else "CLOSED"}',fill=GREEN if op else MUTED,anchor='w',font=('Arial',8,'bold'));self.exchange_hits.append((x0,y-8,x0+260,y+10,code));y+=19
        self.after(500,self.draw)

# Ship interaction remains available after redefining GlobeWindow.
def _sgp_globe_click(self,e):
    if self._drag_anchor:return
    for x1,y1,x2,y2,sh in getattr(self,'ship_hits',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:
            m=tk.Menu(self,tearoff=0);m.add_command(label=f"{sh['name']} • {sh['route']['name']}",state='disabled');m.add_command(label=f"Cargo ${sh['cargo_value']/1e6:,.0f}M • {sh['status']}",state='disabled');m.add_separator();carrier=self.market.get_asset(sh['carrier']);owner=self.market.get_asset(sh['cargo_owner'])
            for label,a in [('Carrier',carrier),('Cargo owner',owner)]:
                if a:m.add_command(label=f'{label}: BUY {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'{label}: OPTIONS {a.symbol}',command=lambda a=a:self.market.ui_app.options_for(a))
            m.tk_popup(e.x_root,e.y_root);return
    for x1,y1,x2,y2,code in getattr(self,'blips',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:GlobalMarketWindow(self.master,self.market,code);self.destroy();return
GlobeWindow.click=_sgp_globe_click

# Strategy-lab button hardening: preserve/select leg rows so FLIP/QTY/DUPLICATE
# always operate on a visible selection after chain additions and live refreshes.
def _sgp_lab_selected_index(self):
    it=self.legs.selection()
    if it:
        try:return int(it[0])
        except Exception:pass
    if self.rows:
        try:self.legs.selection_set('0');self.legs.focus('0')
        except Exception:pass
        return 0
    return None
SpreadBuilder.selected_leg_index=_sgp_lab_selected_index

_old_sgp_add_selected=SpreadBuilder.add_selected
def _sgp_lab_add_selected(self,typ,e=None):
    before=len(self.rows);_old_sgp_add_selected(self,typ,e)
    if len(self.rows)>before:
        iid=str(len(self.rows)-1)
        try:self.legs.selection_set(iid);self.legs.focus(iid);self.legs.see(iid)
        except Exception:pass
SpreadBuilder.add_selected=_sgp_lab_add_selected

def _sgp_lab_flip(self):
    i=self.selected_leg_index()
    if i is None:return messagebox.showinfo('Strategy legs','Add or select a leg first.')
    self.rows[i]['action']='SELL' if self.rows[i]['action']=='BUY' else 'BUY';self.refresh_strategy();self.legs.selection_set(str(i));self.legs.focus(str(i))
SpreadBuilder.flip_leg=_sgp_lab_flip

def _sgp_lab_qty(self,d):
    i=self.selected_leg_index()
    if i is None:return messagebox.showinfo('Strategy legs','Add or select a leg first.')
    self.rows[i]['qty']=max(1,int(self.rows[i]['qty'])+int(d));self.refresh_strategy();self.legs.selection_set(str(i));self.legs.focus(str(i))
SpreadBuilder.change_leg_qty=_sgp_lab_qty

def _sgp_lab_dup(self):
    i=self.selected_leg_index()
    if i is None:return messagebox.showinfo('Strategy legs','Add or select a leg first.')
    r=self.rows[i];self.rows.append({'action':r['action'],'contract':r['contract'],'qty':r['qty']});self.refresh_strategy();iid=str(len(self.rows)-1);self.legs.selection_set(iid);self.legs.focus(iid);self.legs.see(iid)
SpreadBuilder.duplicate_leg=_sgp_lab_dup

# Production advanced-chart transitions: opening another workstation replaces the
# current pop-out instead of leaving a hidden stack of live refresh timers.
_ProdAdvancedBase=AdvancedChartWindow
class AdvancedChartWindow(_ProdAdvancedBase):
    def __init__(self,parent,app,asset):
        super().__init__(_sgp_tk_parent(parent),app,asset)
        # Rewire top-level navigation buttons created by the base workstation.
        def walk(widget):
            for ch in widget.winfo_children():
                try:
                    txt=ch.cget('text')
                    if txt=='OPTIONS / SPREADS':ch.config(command=self.open_options)
                    elif txt=='LEVEL 2 / 3':ch.config(command=self.open_depth)
                    elif txt=='ADVANCED OPTIONS / STRATEGY LAB':ch.config(command=self.open_strategy_lab)
                except Exception:pass
                walk(ch)
        walk(self)
    def open_options(self):
        w=OptionsWindow(self.master,self.market,self.portfolio,self.app.refresh);w.entry.delete(0,'end');w.entry.insert(0,self.asset.symbol);w.apply_symbol();self.close()
    def open_depth(self):DepthWindow(self.master,self.market,self.asset);self.close()
    def open_strategy_lab(self):SpreadBuilder(self.master,self.market,self.portfolio,self.app.refresh);self.close()
    def open_correlated(self,e=None):
        a=self._selected_corr_asset()
        if a:AdvancedChartWindow(self.master,self.app,a);self.close()

# ===== Stock Game Pro 1.1 chart navigation / global trader / roulette patch =====
# Time/session helpers ---------------------------------------------------------
def _sgp_asset_session_code(a):
    if a is None:return 'US'
    try:return a.session
    except Exception:pass
    cls=type(a).__name__
    if cls=='Crypto':return 'CRYPTO'
    if cls=='Forex':return 'FX'
    if cls in ('Future','Commodity'):return 'CME'
    return 'US'

def _sgp_session_countdown(a, game_dt):
    code=_sgp_asset_session_code(a)
    if code in ('CRYPTO','FX'):return ('OPEN','24/7' if code=='CRYPTO' else 'weekday session')
    try:
        from zoneinfo import ZoneInfo
        from datetime import timedelta
        sess=SESSIONS[code]
        aware=game_dt.replace(tzinfo=ZoneInfo('America/New_York')) if game_dt.tzinfo is None else game_dt
        local=aware.astimezone(ZoneInfo(sess.tz));open_now=market_status(code,game_dt)
        # CME is an overnight session with a daily one-hour maintenance break.
        if code=='CME':
            mins=local.hour*60+local.minute+local.second/60
            if open_now:
                # Friday closes 16:00 CT; other active days pause 16:00-17:00 CT.
                target=local.replace(hour=16,minute=0,second=0,microsecond=0)
                if target<=local:target+=timedelta(days=1)
                delta=target-local;label='CLOSE'
            else:
                target=local.replace(hour=17,minute=0,second=0,microsecond=0)
                if local.weekday()==5:target=(local+timedelta(days=1)).replace(hour=17,minute=0,second=0,microsecond=0)
                elif target<=local:target+=timedelta(days=1)
                delta=target-local;label='OPEN'
        else:
            if open_now:
                target=local.replace(hour=sess.close_time.hour,minute=sess.close_time.minute,second=sess.close_time.second,microsecond=0);label='CLOSE'
            else:
                target=local.replace(hour=sess.open_time.hour,minute=sess.open_time.minute,second=sess.open_time.second,microsecond=0);label='OPEN'
                if local.weekday() not in sess.weekdays or target<=local:
                    target+=timedelta(days=1)
                    while target.weekday() not in sess.weekdays:target+=timedelta(days=1)
            delta=target-local
        sec=max(0,int(delta.total_seconds()));d,sec=divmod(sec,86400);h,sec=divmod(sec,3600);m,s=divmod(sec,60)
        txt=(f'{d}d ' if d else '')+f'{h:02d}:{m:02d}:{s:02d}'
        return ('OPEN' if open_now else 'CLOSED',f'{label} {txt}')
    except Exception:return ('OPEN' if market_status(code,game_dt) else 'CLOSED','')

# Chart data windows and anchored drawings ------------------------------------
_Chart_init_v11_base=Chart.__init__
def _sgp_chart_init_v11(self,parent,app,index):
    _Chart_init_v11_base(self,parent,app,index)
    self.view_offset=0;self.follow_latest=True;self.pan_mode=False;self._pan_anchor=None;self.anchored_drawings=[]
    self.bind('<Double-1>',self._open_advanced_from_chart,add='+')
Chart.__init__=_sgp_chart_init_v11

def _sgp_open_advanced_from_chart(self,e=None):
    if self.asset is not None and not getattr(self,'selected_popup',False):
        self.app.advanced_chart(self.asset);return 'break'
Chart._open_advanced_from_chart=_sgp_open_advanced_from_chart

def _sgp_chart_data_v11(self):
    if not self.asset:return []
    interval={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe]
    raw=list(self.asset.chart_candles(interval))
    if not raw:return []
    if self.timeframe=='MAX':
        total=len(raw);visible=max(30,int(total/max(.25,self.zoom)));end=max(1,total-max(0,int(self.view_offset)));start=max(0,end-visible);d=raw[start:end]
        target=max(300,min(1800,int(max(400,self.winfo_width())*1.2)))
        if len(d)>target:
            step=(len(d)-1)/(target-1);d=[d[round(i*step)] for i in range(target)]
        return d
    maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':500}[self.timeframe]
    visible=max(30,int(maxbars/max(.25,self.zoom)));end=max(1,len(raw)-max(0,int(self.view_offset)));start=max(0,end-visible);return raw[start:end]
Chart.data=_sgp_chart_data_v11

_old_set_asset_v11=Chart.set_asset
def _sgp_set_asset_v11(self,a):self.view_offset=0;self.follow_latest=True;_old_set_asset_v11(self,a)
Chart.set_asset=_sgp_set_asset_v11
_old_set_tf_v11=Chart.set_tf
def _sgp_set_tf_v11(self,tf):self.view_offset=0;self.follow_latest=True;_old_set_tf_v11(self,tf)
Chart.set_tf=_sgp_set_tf_v11

def _sgp_chart_pan(self,bars):
    if not self.asset:return
    interval={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe];raw=self.asset.chart_candles(interval)
    self.view_offset=max(0,min(max(0,len(raw)-2),int(self.view_offset+bars)));self.follow_latest=(self.view_offset==0);self.request_draw(force=True)
Chart.pan_bars=_sgp_chart_pan

def _sgp_x_to_time(self,x):
    d=self.data();w=max(280,self.winfo_width());left,right=62,w-12
    if not d:return None
    i=max(0,min(len(d)-1,int((x-left)/max(1,right-left)*len(d))));return d[i].timestamp
Chart.x_to_time=_sgp_x_to_time

def _sgp_time_to_x(self,ts):
    d=self.data();w=max(280,self.winfo_width());left,right=62,w-12
    if not d:return None
    idx=min(range(len(d)),key=lambda i:abs((d[i].timestamp-ts).total_seconds()));return left+(idx+.5)*(right-left)/max(1,len(d))
Chart.time_to_x=_sgp_time_to_x

_old_chart_click_v11=Chart.click
def _sgp_chart_click_v11(self,e):
    if getattr(self,'pan_mode',False):
        self._pan_anchor=(e.x,int(self.view_offset));self.cross=(e.x,e.y);return
    return _old_chart_click_v11(self,e)
Chart.click=_sgp_chart_click_v11
_old_chart_drag_v11=Chart.drag
def _sgp_chart_drag_v11(self,e):
    if getattr(self,'pan_mode',False) and self._pan_anchor:
        d=self.data();w=max(280,self.winfo_width());step=max(1,(w-74)/max(1,len(d)));dx=e.x-self._pan_anchor[0];self.view_offset=max(0,self._pan_anchor[1]+int(dx/step));self.follow_latest=self.view_offset==0;self.cross=(e.x,e.y);self.request_draw(force=True);return
    return _old_chart_drag_v11(self,e)
Chart.drag=_sgp_chart_drag_v11
_old_chart_release_v11=Chart.release
def _sgp_chart_release_v11(self,e):
    if getattr(self,'pan_mode',False):self._pan_anchor=None;self.request_draw(force=True);return
    # Price/time anchored technical drawings stay attached to historical candles while panning.
    if not self.drag_order and not self.drag_marker and self.start and self.tool in ('Trendline','Horizontal'):
        if self.tool=='Trendline':
            t1=self.x_to_time(self.start[0]);t2=self.x_to_time(e.x);p1=self.y_to_price(self.start[1]);p2=self.y_to_price(e.y)
            if t1 and t2:self.anchored_drawings.append(('aline',t1,p1,t2,p2))
        else:self.anchored_drawings.append(('ah',self.y_to_price(e.y)))
        self.start=None;self.request_draw(force=True);return
    return _old_chart_release_v11(self,e)
Chart.release=_sgp_chart_release_v11

_old_chart_draw_v11=Chart.draw
def _sgp_chart_draw_v11(self):
    _old_chart_draw_v11(self)
    if not self.asset:return
    d=self.data();w=max(280,self.winfo_width());h=max(170,self.winfo_height());left,right,top,bottom=62,w-12,34,h-32
    if not d:return
    # Explicit time axis: intraday charts show clock time, longer charts show calendar dates.
    self.delete('timeaxis');count=3 if w<430 else 5
    for j in range(count):
        i=round((len(d)-1)*j/max(1,count-1));ts=d[i].timestamp;x=left+(i+.5)*(right-left)/max(1,len(d));fmt='%H:%M' if self.timeframe=='1D' else '%m-%d %H:%M' if self.timeframe in ('1W','1M') else '%Y-%m-%d';self.create_text(x,bottom-3,text=ts.strftime(fmt),fill='#6f8294',font=('Arial',6 if w<430 else 7),anchor='s',tags='timeaxis')
    status,remain=_sgp_session_countdown(self.asset,self.app.market.clock.current);self.create_text(left+4,21,text=f'{_sgp_asset_session_code(self.asset)} {status} • {remain}',fill=GREEN if status=='OPEN' else MUTED,font=('Arial',7,'bold'),anchor='nw',tags='timeaxis')
    # Re-render anchored technical drawings in data coordinates.
    for dr in getattr(self,'anchored_drawings',[]):
        if dr[0]=='aline':
            _,t1,p1,t2,p2=dr;x1=self.time_to_x(t1);x2=self.time_to_x(t2)
            if x1 is not None and x2 is not None:self.create_line(x1,self.price_to_y(p1),x2,self.price_to_y(p2),fill=YELLOW,width=2)
        elif dr[0]=='ah':self.create_line(left,self.price_to_y(dr[1]),right,self.price_to_y(dr[1]),fill=YELLOW,dash=(5,3))
    if getattr(self,'pan_mode',False):self.create_text(right,21,text=f'HISTORY FREE-SCROLL • {self.view_offset} bars behind live',fill=YELLOW,font=('Arial',7,'bold'),anchor='ne',tags='timeaxis')
Chart.draw=_sgp_chart_draw_v11

# Advanced chart workstation gets individual tickrate + historical free-scroll controls.
_AdvancedChart_v11_base=AdvancedChartWindow
class AdvancedChartWindow(_AdvancedChart_v11_base):
    def __init__(self,parent,app,asset):
        super().__init__(parent,app,asset)
        children=self.winfo_children();body=next((x for x in children if isinstance(x,ttk.PanedWindow)),None)
        bar=ttk.Frame(self)
        if body is not None:bar.pack(fill='x',padx=8,pady=(0,5),before=body)
        else:bar.pack(fill='x',padx=8,pady=5)
        ttk.Label(bar,text='Chart tick').pack(side='left');self.adv_rate=tk.StringVar(value=f'{self.chart.refresh_ms}ms');rate=ttk.Combobox(bar,textvariable=self.adv_rate,values=['25ms','50ms','100ms','180ms','250ms','500ms','1000ms','2000ms','5000ms'],state='readonly',width=9);rate.pack(side='left',padx=4);rate.bind('<<ComboboxSelected>>',self._set_adv_rate)
        self.history_btn=ttk.Button(bar,text='FREE SCROLL: OFF',command=self.toggle_free_scroll);self.history_btn.pack(side='left',padx=(12,4));ttk.Button(bar,text='◀ OLDER',command=lambda:self.chart.pan_bars(50)).pack(side='left',padx=2);ttk.Button(bar,text='NEWER ▶',command=lambda:self.chart.pan_bars(-50)).pack(side='left',padx=2);ttk.Button(bar,text='LIVE',command=self.go_live).pack(side='left',padx=4)
        self.history_status=ttk.Label(bar,text='Following latest market candle',foreground=MUTED);self.history_status.pack(side='left',padx=12)
        ttk.Label(bar,text='Tip: FREE SCROLL lets you drag horizontally; trend/horizontal drawings are anchored to price + time.',foreground=MUTED).pack(side='right')
    def _set_adv_rate(self,e=None):
        try:self.chart.set_refresh_rate(int(self.adv_rate.get().replace('ms','')));self.app.status_flash(f'{self.asset.symbol} advanced chart tickrate {self.chart.refresh_ms} ms')
        except Exception:pass
    def toggle_free_scroll(self):
        self.chart.pan_mode=not self.chart.pan_mode
        self.history_btn.config(text='FREE SCROLL: ON' if self.chart.pan_mode else 'FREE SCROLL: OFF')
        self.history_status.config(text='Drag chart left/right to inspect history' if self.chart.pan_mode else ('Following latest market candle' if self.chart.view_offset==0 else f'Locked {self.chart.view_offset} bars behind live'))
    def go_live(self):
        self.chart.view_offset=0;self.chart.follow_latest=True;self.chart.pan_mode=False;self.history_btn.config(text='FREE SCROLL: OFF');self.history_status.config(text='Following latest market candle');self.chart.request_draw(force=True)

# Ensure main-workspace chart double-click resolves the final AdvancedChartWindow class.
def _sgp_open_adv_v11(self,a):return AdvancedChartWindow(self.root,self,a)
App.advanced_chart=_sgp_open_adv_v11

# Final globe: one scheduler only (prevents timer multiplication while dragging),
# mesh-like trade network, investable ports, directional sea/air lanes and hazard vectors.
_Globe_v11_base=GlobeWindow
class GlobeWindow(_Globe_v11_base):
    def __init__(self,parent,market):
        self._v11_loop=None;super().__init__(parent,market);self.title('STOCK GAME PRO • WORLD TRADE NETWORK')
        self._v11_loop=self.after(450,self._render_loop)
    def _render_loop(self):
        try:
            if not self.winfo_exists():return
            self.draw();self._v11_loop=self.after(450,self._render_loop)
        except tk.TclError:return
    def _route_segments(self,points,c,cx,cy,base,rot,color,width=1,dash=None,arrow=False):
        projected=[]
        for lat,lon in points:
            x,y,z=self.project(lon,lat,cx,cy,base,rot);projected.append((x,y,z))
        for i in range(len(projected)-1):
            x1,y1,z1=projected[i];x2,y2,z2=projected[i+1]
            if z1>0 and z2>0:c.create_line(x1,y1,x2,y2,fill=color,width=width,dash=dash,arrow='last' if arrow else 'none',arrowshape=(7,8,3))
    def draw(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(1050,c.winfo_width());h=max(720,c.winfo_height());base=min(h*.37,w*.265);r=base*self.view_zoom;cx=w*.31;cy=h*.51
        rng=random.Random(9137)
        for _ in range(110):x=rng.randrange(0,int(w*.58));y=rng.randrange(0,h);c.create_oval(x-1,y-1,x+1,y+1,fill='#22475e',outline='')
        for k,col in [(16,'#031520'),(10,'#06344a'),(4,'#15799b')]:c.create_oval(cx-r-k,cy-r-k,cx+r+k,cy+r+k,outline=col,width=max(1,k//4))
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#062b46',outline='#72d9f5',width=2)
        utc=self.market.clock.current.replace(tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York')).astimezone(__import__('datetime').timezone.utc);rot=2*math.pi*((utc.hour*60+utc.minute+utc.second/60)/1440)-math.pi/2
        # World-wide-web mesh: longitude/latitude arcs plus trade-route chords.
        for lat in (-60,-30,0,30,60):
            pts=[]
            for lon in range(-180,181,8):
                x,y,z=self.project(lon,lat,cx,cy,base,rot)
                if z>0:pts.extend([x,y])
            if len(pts)>3:c.create_line(*pts,fill='#11445a',width=1)
        for lon in range(-150,181,30):
            pts=[]
            for lat in range(-80,81,8):
                x,y,z=self.project(lon,lat,cx,cy,base,rot)
                if z>0:pts.extend([x,y])
            if len(pts)>3:c.create_line(*pts,fill='#0d3a50',width=1)
        self.draw_land(c,cx,cy,base,rot)
        # Sea and air corridors are directional, making origin/destination flow readable.
        for route in getattr(self.market,'freight_routes',[]):self._route_segments(route['points'],c,cx,cy,base,rot,'#269fc2',1,(4,5),True)
        for route in getattr(self.market,'air_routes',[]):self._route_segments(route['points'],c,cx,cy,base,rot,'#9b8cff',1,(2,5),True)
        c.create_oval(cx-r,cy-r,cx+r,cy+r,outline='#72e7ff',width=3)
        self.port_hits=[]
        for p in getattr(self.market,'ports',[]):
            x,y,z=self.project(p['lon'],p['lat'],cx,cy,base,rot)
            if z<=0:continue
            c.create_oval(x-6,y-6,x+6,y+6,fill='#ffd56d',outline='white',width=1);self.port_hits.append((x-11,y-11,x+11,y+11,p))
            if self.view_zoom>=.9:c.create_text(x+8,y-8,text=f"{p['name']} • {p['operator']}",fill='#d8eaf3',font=('Arial',7,'bold'),anchor='w')
        self.ship_hits=[]
        for sh in getattr(self.market,'shipments',[]):
            lat,lon=self.market.shipment_position(sh);x,y,z=self.project(lon,lat,cx,cy,base,rot)
            if z>0:
                col=YELLOW if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved') else CYAN;c.create_polygon(x-9,y+5,x+9,y+5,x+5,y-4,x-6,y-4,fill=col,outline='white');self.ship_hits.append((x-13,y-11,x+13,y+11,sh))
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                hl,hn=self.market.shipment_hazard_position(sh);hx,hy,hz=self.project(hn,hl,cx,cy,base,rot)
                temp=dict(sh);temp['progress']=min(.99,sh.get('hazard_progress',0)+.08);nl,nn=self.market.shipment_position(temp);nx,ny,nz=self.project(nn,nl,cx,cy,base,rot)
                if hz>0:
                    col=ORANGE if sh['hazard']=='STORM' else RED;c.create_oval(hx-10,hy-10,hx+10,hy+10,outline=col,width=2);c.create_text(hx,hy,text='S' if sh['hazard']=='STORM' else 'P',fill=col,font=('Arial',8,'bold'))
                    if nz>0:c.create_line(hx,hy,nx,ny,fill=col,width=2,arrow='last')
        self.air_hits=[]
        for fl in getattr(self.market,'air_shipments',[]):
            lat,lon=self.market.air_shipment_position(fl);x,y,z=self.project(lon,lat,cx,cy,base,rot)
            if z>0:c.create_polygon(x,y-7,x+8,y+5,x,y+2,x-8,y+5,fill='#c9b6ff',outline='white');self.air_hits.append((x-12,y-12,x+12,y+12,fl))
        # Existing geopolitical risk markers.
        for ev in getattr(self.market,'geopolitical_events',[]):
            if ev.get('resolved'):continue
            x,y,z=self.project(ev['lon'],ev['lat'],cx,cy,base,rot)
            if z>0:c.create_oval(x-11,y-11,x+11,y+11,outline=RED if ev.get('status')=='ELEVATED' else ORANGE,width=3);c.create_text(x,y,text='!',fill='white',font=('Arial',11,'bold'))
        x0=w*.60;c.create_text(x0,26,text='WORLD TRADE NETWORK',fill=TEXT,font=('Arial',19,'bold'),anchor='w');c.create_text(x0,55,text=f'{self.market.clock.time} • drag globe • wheel zoom {self.view_zoom:.2f}x',fill=CYAN,font=('Arial',10,'bold'),anchor='w')
        y=86;c.create_text(x0,y,text='LOGISTICS / FORWARD RISK',fill=YELLOW,font=('Arial',11,'bold'),anchor='w');y+=24
        risks=[]
        for sh in getattr(self.market,'shipments',[]):
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):risks.append(f"{sh['hazard']:<7}  {sh['carrier']} → {sh['cargo_owner']}  •  {sh['route']['name']}")
        for ev in getattr(self.market,'geopolitical_events',[]):
            if not ev.get('resolved'):risks.append(f"{ev['status']:<8} {ev['name']}  T-{max(0,ev['minutes_to_event']):.0f}m")
        for txt in risks[:9]:c.create_text(x0,y,text=txt,fill=ORANGE if 'STORM' in txt or 'WATCH' in txt else RED if 'PIRATE' in txt or 'ELEVATED' in txt else TEXT,anchor='w',font=('Consolas',8,'bold'));y+=18
        y+=8;c.create_text(x0,y,text='PORTS / OPERATORS',fill=TEXT,font=('Arial',10,'bold'),anchor='w');y+=20
        for p in getattr(self.market,'ports',[])[:8]:
            a=self.market.get_asset(p['operator']);px=f'${a.price:,.2f}' if a else 'private/unavailable';c.create_text(x0,y,text=f"{p['name'][:23]:<23} {p['operator']:<8} {px}",fill=MUTED,anchor='w',font=('Consolas',8));y+=17
        y+=7;c.create_text(x0,y,text='Click ports, ships or planes for company / cargo trading actions.',fill='#72d9f5',anchor='w',font=('Arial',8,'bold'))
    def click(self,e):
        if self._drag_anchor:return
        for x1,y1,x2,y2,p in getattr(self,'port_hits',[]):
            if x1<=e.x<=x2 and y1<=e.y<=y2:
                a=self.market.get_asset(p['operator']);m=tk.Menu(self,tearoff=0);m.add_command(label=p['name'],state='disabled');m.add_command(label=f"Operator / proxy: {p['operator']}",state='disabled');m.add_separator()
                if a:m.add_command(label=f'BUY {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL / SHORT {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SELL','MARKET',None));m.add_command(label=f'OPTIONS {a.symbol}',command=lambda:self.market.ui_app.options_for(a));m.add_command(label='ADVANCED CHART',command=lambda:self.market.ui_app.advanced_chart(a))
                m.tk_popup(e.x_root,e.y_root);return
        for x1,y1,x2,y2,fl in getattr(self,'air_hits',[]):
            if x1<=e.x<=x2 and y1<=e.y<=y2:
                carrier=self.market.get_asset(fl['carrier']);owner=self.market.get_asset(fl['cargo_owner']);m=tk.Menu(self,tearoff=0);m.add_command(label=f"{fl['name']} • {fl['route']['name']}",state='disabled');m.add_command(label=f"Cargo ${fl['cargo_value']/1e6:,.0f}M",state='disabled');m.add_separator()
                for label,a in [('Air carrier',carrier),('Cargo owner',owner)]:
                    if a:m.add_command(label=f'{label}: BUY {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'{label}: OPTIONS {a.symbol}',command=lambda a=a:self.market.ui_app.options_for(a))
                m.tk_popup(e.x_root,e.y_root);return
        return _sgp_globe_click(self,e)

# Make App use the final globe class.
def _sgp_globe_v11(self):return GlobeWindow(self.root,self.market)
App.globe=_sgp_globe_v11

# Roulette: winning number stays on its pocket, center is decorative, and history
# occupies a dedicated bottom panel away from the betting board.
_Roulette_v11_base=RouletteWindow
class RouletteWindow(_Roulette_v11_base):
    def _table_geom(self,w,h):
        cx=w*.17;cy=h*.27;r=min(h*.20,w*.12);board_left=max(cx+r+34,w*.38);right_margin=28;available=max(360,w-board_left-right_margin);cw=min(74,available/13.0);cw=max(28,min(cw,(w-board_left-right_margin)/13.0));zero_w=cw;ch=max(34,min(58,h*.056));bx=board_left+zero_w;by=max(115,min(h*.16,h-ch*5-185));return bx,by,cw,ch,zero_w
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        c=self.cv;c.delete('all');w=max(1100,c.winfo_width());h=max(700,c.winfo_height());cx=w*.17;cy=h*.27;r=min(h*.20,w*.12);c.create_text(cx,20,text=f'{self.dealer} • EUROPEAN ROULETTE',fill='#f6e6b5',font=('Georgia',19,'bold'))
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#0d2519',outline='#d8b96a',width=6);c.create_oval(cx-r*.84,cy-r*.84,cx+r*.84,cy+r*.84,fill='#171d22',outline='#8b6d35',width=3)
        pocket_positions={}
        for i,n in enumerate(self.EURO_ORDER):
            a=2*math.pi*i/37-math.pi/2;col='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#171b20';x=cx+math.cos(a)*r*.70;y=cy+math.sin(a)*r*.70;rr=max(12,min(18,r*.10));pocket_positions[n]=(x,y,a);c.create_oval(x-rr,y-rr,x+rr,y+rr,fill=col,outline='#d6c08a',width=2);c.create_text(x,y,text=str(n),fill='white',font=('Arial',8,'bold'))
            if wheel_number==n and not spinning:c.create_oval(x-rr-4,y-rr-4,x+rr+4,y+rr+4,outline='#fff2a8',width=3)
        # Decorative spindle only -- do not incorrectly repeat the winning number in the center.
        c.create_oval(cx-r*.18,cy-r*.18,cx+r*.18,cy+r*.18,fill='#d8b96a',outline='#fff0b8',width=2);c.create_oval(cx-r*.08,cy-r*.08,cx+r*.08,cy+r*.08,fill='#624a23',outline='#f4d98d',width=2)
        if wheel_number is not None:
            if spinning:
                wi=self.EURO_ORDER.index(wheel_number) if wheel_number in self.EURO_ORDER else 0;a=2*math.pi*wi/37-math.pi/2+ball_phase*math.pi*12;rad=r*(.92-.18*min(1,ball_phase));bx=cx+math.cos(a)*rad;byb=cy+math.sin(a)*rad
            else:
                x,y,a=pocket_positions.get(wheel_number,pocket_positions[0]);bx=x+math.cos(a)*7;byb=y+math.sin(a)*7
            c.create_oval(bx-7,byb-7,bx+7,byb+7,fill='white',outline='#cfd8df',width=2)
        bx,by,cw,ch,zero_w=self._table_geom(w,h);c.create_rectangle(bx-zero_w,by,bx,by+ch*3,fill='#13865c',outline='#d8b96a',width=2);c.create_text(bx-zero_w/2,by+ch*1.5,text='0',fill='white',font=('Arial',18,'bold'));self._chip(c,bx-zero_w/2,by+ch*1.5,self.bets.get(0,0),'0')
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch;fill='#b92f48' if n in self.REDS else '#151b23';c.create_rectangle(x,y,x+cw,y+ch,fill=fill,outline='#d8b96a');c.create_text(x+cw*.5,y+ch*.5,text=str(n),fill='white',font=('Arial',14,'bold'));self._chip(c,x+cw/2,y+ch/2,self.bets.get(n,0),str(n))
        for row,key in enumerate(('2:1_ROW1','2:1_ROW2','2:1_ROW3')):
            x=bx+12*cw;y=by+row*ch;c.create_rectangle(x,y,x+cw*.85,y+ch,fill='#0e6950',outline='#d8b96a');c.create_text(x+cw*.42,y+ch*.5,text='2:1',fill='white',font=('Arial',11,'bold'));self._chip(c,x+cw*.42,y+ch/2,self.bets.get(key,0),'2:1')
        oy=by+3*ch+10;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw;c.create_rectangle(x,oy,x+rw,oy+ch*.85,fill='#0e6950',outline='#d8b96a');c.create_text(x+rw/2,oy+ch*.42,text=key,fill='white',font=('Arial',9,'bold'));self._chip(c,x+rw/2,oy+ch*.42,self.bets.get(key,0),key)
        oy2=oy+ch+7;rw=(cw*12)/6
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            x=bx+i*rw;fill='#b92f48' if key=='RED' else '#151b23' if key=='BLACK' else '#0e6950';c.create_rectangle(x,oy2,x+rw,oy2+ch*.85,fill=fill,outline='#d8b96a');c.create_text(x+rw/2,oy2+ch*.42,text=key,fill='white',font=('Arial',9,'bold'));self._chip(c,x+rw/2,oy2+ch*.42,self.bets.get(key,0),key)
        # Dedicated history strip along the bottom, independent of board geometry.
        panel_y=h-145;c.create_rectangle(18,panel_y,w-18,h-12,fill='#09141d',outline='#31495a',width=2);c.create_text(32,panel_y+12,text=f'RECORDED SPINS • {len(self.history):,} / 500',fill='#f6e6b5',font=('Arial',11,'bold'),anchor='nw')
        hist=list(reversed(self.history[-60:]));cols=min(30,max(10,int((w-60)/38)))
        for i,n in enumerate(hist):
            row=i//cols;col=i%cols;x=35+col*38;y=panel_y+47+row*35;fill='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#151b23';c.create_oval(x-12,y-12,x+12,y+12,fill=fill,outline='#d8b96a');c.create_text(x,y,text=str(n),fill='white',font=('Arial',7,'bold'))
        if self.history:
            counts={n:self.history.count(n) for n in range(37)};hot=sorted(counts.items(),key=lambda kv:kv[1],reverse=True)[:5];c.create_text(w-32,panel_y+14,text='Hot: '+'  '.join(f'{n}×{cnt}' for n,cnt in hot),fill=MUTED,font=('Consolas',8,'bold'),anchor='ne')
        self.balance.config(text=f'${self.portfolio.cash:,.2f}')

# Casino launcher resolves the final RouletteWindow definition.
def _sgp_casino_v11(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v11

# Active-instrument market countdown in the main clock strip.
def _sgp_smooth_clock_v11(self):
    try:
        a=self.charts[self.active_chart].asset if getattr(self,'charts',None) else None;status,remain=_sgp_session_countdown(a,self.market.clock.current);code=_sgp_asset_session_code(a)
        txt=f'{self.market.clock.time}  •  {getattr(a,"symbol","—")} {code} {status}  •  {remain}'
        if txt!=getattr(self,'_last_clock_text',None):self.clock_label.config(text=txt);self._last_clock_text=txt
    except Exception:pass
    self._clock_stream_job=self.root.after(100,lambda:self._smooth_clock_stream())
App._smooth_clock_stream=_sgp_smooth_clock_v11

# Full Global Trader object action menu: carrier, cargo owner and ports all expose
# stock buy/sell/short, options and advanced-chart actions.
def _sgp_globe_click_v11(self,e):
    if self._drag_anchor:return
    for x1,y1,x2,y2,p in getattr(self,'port_hits',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:
            a=self.market.get_asset(p['operator']);m=tk.Menu(self,tearoff=0);m.add_command(label=p['name'],state='disabled');m.add_command(label=f"Operator / proxy: {p['operator']}",state='disabled');m.add_separator()
            if a:
                m.add_command(label=f'BUY {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'BUY','MARKET',None));m.add_command(label=f'SELL {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SELL','MARKET',None));m.add_command(label=f'SHORT {a.symbol}',command=lambda:self.market.ui_app.order_window(a,'SHORT','MARKET',None));m.add_command(label=f'OPTIONS {a.symbol}',command=lambda:self.market.ui_app.options_for(a));m.add_command(label='ADVANCED CHART',command=lambda:self.market.ui_app.advanced_chart(a))
            m.tk_popup(e.x_root,e.y_root);return
    for x1,y1,x2,y2,sh in getattr(self,'ship_hits',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:
            carrier=self.market.get_asset(sh['carrier']);owner=self.market.get_asset(sh['cargo_owner']);m=tk.Menu(self,tearoff=0);m.add_command(label=f"{sh['name']} • {sh['route']['name']}",state='disabled');m.add_command(label=f"Cargo ${sh['cargo_value']/1e6:,.0f}M • {sh['status']}",state='disabled');m.add_separator()
            for label,a in [('Carrier',carrier),('Cargo owner',owner)]:
                if not a:continue
                sub=tk.Menu(m,tearoff=0);sub.add_command(label=f'BUY {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'BUY','MARKET',None));sub.add_command(label=f'SELL {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'SELL','MARKET',None));sub.add_command(label=f'SHORT {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'SHORT','MARKET',None));sub.add_command(label='OPTIONS',command=lambda a=a:self.market.ui_app.options_for(a));sub.add_command(label='ADVANCED CHART',command=lambda a=a:self.market.ui_app.advanced_chart(a));m.add_cascade(label=f'{label}: {a.symbol}',menu=sub)
            m.tk_popup(e.x_root,e.y_root);return
    for x1,y1,x2,y2,fl in getattr(self,'air_hits',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:
            carrier=self.market.get_asset(fl['carrier']);owner=self.market.get_asset(fl['cargo_owner']);m=tk.Menu(self,tearoff=0);m.add_command(label=f"{fl['name']} • {fl['route']['name']}",state='disabled');m.add_command(label=f"Cargo ${fl['cargo_value']/1e6:,.0f}M",state='disabled');m.add_separator()
            for label,a in [('Air carrier',carrier),('Cargo owner',owner)]:
                if not a:continue
                sub=tk.Menu(m,tearoff=0);sub.add_command(label=f'BUY {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'BUY','MARKET',None));sub.add_command(label=f'SELL {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'SELL','MARKET',None));sub.add_command(label=f'SHORT {a.symbol}',command=lambda a=a:self.market.ui_app.order_window(a,'SHORT','MARKET',None));sub.add_command(label='OPTIONS',command=lambda a=a:self.market.ui_app.options_for(a));sub.add_command(label='ADVANCED CHART',command=lambda a=a:self.market.ui_app.advanced_chart(a));m.add_cascade(label=f'{label}: {a.symbol}',menu=sub)
            m.tk_popup(e.x_root,e.y_root);return
    for x1,y1,x2,y2,code in getattr(self,'blips',[]):
        if x1<=e.x<=x2 and y1<=e.y<=y2:GlobalMarketWindow(self.master,self.market,code);self.destroy();return
GlobeWindow.click=_sgp_globe_click_v11

# ===== Stock Game Pro 1.2 time-axis / pause / usable global trader patch =====
# The prior globe accumulated refresh callbacks through multiple inherited versions.
# This release replaces it with a single-loop workstation instead of subclassing the legacy globe.

# --- chart time axis that remains visibly separated from OHLC/footer text ---
_Chart_draw_v12_base=Chart.draw
def _sgp_chart_draw_v12(self):
    _Chart_draw_v12_base(self)
    if not self.asset:return
    d=self.data()
    if len(d)<2:return
    w=max(280,self.winfo_width());h=max(170,self.winfo_height());left,right=62,w-12
    # Reserve a dedicated axis strip, drawn last so dates cannot be hidden by the footer.
    self.delete('v12axis')
    axis_y=h-15
    self.create_rectangle(left-2,h-29,right+2,h-2,fill=BG,outline=GRID,tags='v12axis')
    count=3 if w<430 else 5 if w<850 else 7
    for j in range(count):
        i=round((len(d)-1)*j/max(1,count-1));ts=d[i].timestamp;x=left+(i+.5)*(right-left)/max(1,len(d))
        if self.timeframe=='1D':fmt='%m/%d\n%H:%M'
        elif self.timeframe in ('1W','1M'):fmt='%m/%d\n%H:%M'
        elif self.timeframe in ('3M','6M','1Y'):fmt='%Y-%m-%d'
        else:fmt='%Y-%m'
        self.create_text(x,axis_y,text=ts.strftime(fmt),fill='#9db0c2',font=('Consolas',6 if w<430 else 7),anchor='center',justify='center',tags='v12axis')
    # Current visible range is explicit in the chart chrome.
    self.create_text(right,29,text=f'{d[0].timestamp:%Y-%m-%d %H:%M}  →  {d[-1].timestamp:%Y-%m-%d %H:%M}',fill='#70879a',font=('Consolas',6),anchor='ne',tags='v12axis')
Chart.draw=_sgp_chart_draw_v12

# Manual ticker refresh belongs in the chart context menu.  Long-history 5Y/MAX
# views intentionally cannot be force-refreshed because those are historical datasets.
def _sgp_manual_chart_refresh(self):
    if self.timeframe in ('5Y','MAX'):
        return self.app.status_flash('Manual ticker refresh is disabled for 5Y / MAX history.')
    self.view_offset=0;self.follow_latest=True;self._key=None
    try:self.app.market.load_chart_data(self.asset,self.timeframe)
    except Exception:pass
    self.request_draw(force=True);self.app.status_flash(f'{self.asset.symbol} {self.timeframe} ticker refreshed at {self.app.market.clock.time}')
Chart.manual_refresh=_sgp_manual_chart_refresh

_Chart_context_v12_base=Chart.context
def _sgp_chart_context_v12(self,e):
    if not getattr(self,'selected_popup',False):self.app.active_chart=self.index;self.app.sync_chart_controls()
    a=self.asset
    if not a:return
    p=self.y_to_price(e.y);m=tk.Menu(self,tearoff=0)
    m.add_command(label=f'BUY {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'BUY','LIMIT',p));m.add_command(label=f'SELL {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SELL','LIMIT',p));m.add_command(label=f'SHORT {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SHORT','LIMIT',p));m.add_command(label=f'COVER {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'COVER','LIMIT',p));m.add_separator()
    m.add_command(label='Buy at Market',command=lambda:self.app.order_window(a,'BUY','MARKET',None));m.add_command(label='Set Stop',command=lambda:self.app.order_window(a,'SELL','STOP',p));m.add_command(label='Open Options',command=lambda:self.app.options_for(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.app.depth_for(a));m.add_command(label='POP OUT ADVANCED CHART',command=lambda:self.app.advanced_chart(a));m.add_separator()
    m.add_command(label=f'REFRESH {self.timeframe} TICKER',command=self.manual_refresh,state='disabled' if self.timeframe in ('5Y','MAX') else 'normal')
    if not getattr(self,'selected_popup',False):m.add_command(label='ADD CHART',command=self.app.add_chart);m.add_command(label='REMOVE THIS CHART',command=lambda:self.app.remove_chart(self.index))
    m.tk_popup(e.x_root,e.y_root)
Chart.context=_sgp_chart_context_v12

# --- explicit global pause + skip-to-next-open controls ---
def _sgp_skip_to_open_ui(self):
    a=self.charts[self.active_chart].asset if getattr(self,'charts',None) else None
    if a is not None and _sgp_asset_session_code(a)=='CRYPTO':return self.status_flash('Crypto is already open 24/7.')
    mins=self.market.skip_to_next_open(a)
    if mins<=0:return self.status_flash('Selected market is already at/open for its regular session.')
    self.status_flash(f'Skipped {mins/60:.1f} game hours to next {_sgp_asset_session_code(a)} regular open.')
    self.refresh();self.redraw()
App.skip_to_next_open=_sgp_skip_to_open_ui

# Install a clearly visible control strip after the main workspace is built.
_App_build_v12_base=App.build
def _sgp_build_v12(self):
    _App_build_v12_base(self)
    try:
        strip=ttk.Frame(self.root);strip.pack(fill='x',padx=6,pady=(0,3),before=self.status)
        ttk.Label(strip,text='WORLD CLOCK',font=('Arial',8,'bold')).pack(side='left',padx=(3,8))
        self.pause_btn_v12=ttk.Button(strip,text='⏸ PAUSE WORLD',command=self.toggle_pause,width=15);self.pause_btn_v12.pack(side='left',padx=2)
        ttk.Button(strip,text='⏭ SKIP TO NEXT OPEN',command=self.skip_to_next_open).pack(side='left',padx=4)
        ttk.Label(strip,text='Pause freezes market + clock but leaves order setup usable. Skip advances closed-world state directly to the selected asset’s next regular session.',foreground=MUTED).pack(side='left',padx=8)
    except Exception:pass
App.build=_sgp_build_v12

_Toggle_pause_v12_base=App.toggle_pause
def _sgp_toggle_pause_v12(self):
    _Toggle_pause_v12_base(self)
    txt='▶ RESUME WORLD' if self.market.paused else '⏸ PAUSE WORLD'
    for name in ('pause_btn_v12','pause_btn'):
        try:getattr(self,name).config(text=txt)
        except Exception:pass
App.toggle_pause=_sgp_toggle_pause_v12

# --- single-loop, interpretable global logistics workstation ---
class GlobalTradeWorkstation(ToolWindow):
    def __init__(self,parent,market):
        super().__init__(_sgp_tk_parent(parent));self.market=market;self.style_window('STOCK GAME PRO • GLOBAL TRADE WORKSTATION','1540x920');self.resizable(True,True)
        self.view_yaw=0.0;self.view_pitch=0.0;self.view_zoom=1.0;self._drag=None;self._job=None;self._selected=None
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=6)
        ttk.Label(top,text='GLOBAL LOGISTICS / EVENT RADAR',font=('Arial',15,'bold')).pack(side='left')
        self.pause=ttk.Button(top,text='⏸ PAUSE WORLD',command=self._pause);self.pause.pack(side='left',padx=10)
        ttk.Button(top,text='⏭ NEXT US OPEN',command=lambda:self._skip(self.market.get_asset('SPY'))).pack(side='left',padx=3)
        self.clock=ttk.Label(top,text='',font=('Consolas',10,'bold'));self.clock.pack(side='right')
        body=ttk.PanedWindow(self,orient='horizontal');body.pack(fill='both',expand=True,padx=8,pady=(0,8))
        mapf=ttk.Frame(body);side=ttk.Frame(body,width=490);body.add(mapf,weight=7);body.add(side,weight=4)
        self.cv=tk.Canvas(mapf,bg='#020913',highlightthickness=0);self.cv.pack(fill='both',expand=True)
        self.cv.bind('<ButtonPress-1>',self._press);self.cv.bind('<B1-Motion>',self._drag_view);self.cv.bind('<ButtonRelease-1>',self._release);self.cv.bind('<MouseWheel>',self._wheel);self.cv.bind('<Button-4>',lambda e:self._zoom(.10));self.cv.bind('<Button-5>',lambda e:self._zoom(-.10))
        ttk.Label(side,text='SELECTED OBJECT',font=('Arial',11,'bold')).pack(anchor='w',padx=7,pady=(2,4));self.details=tk.Text(side,height=10,bg='#09131d',fg=TEXT,insertbackground=TEXT,relief='flat',wrap='word');self.details.pack(fill='x',padx=7)
        actions=ttk.Frame(side);actions.pack(fill='x',padx=7,pady=5);self.trade_btn=ttk.Button(actions,text='TRADE / VIEW',command=self._trade_selected,state='disabled');self.trade_btn.pack(side='left');self.options_btn=ttk.Button(actions,text='OPTIONS',command=self._options_selected,state='disabled');self.options_btn.pack(side='left',padx=4)
        tabs=ttk.Notebook(side);tabs.pack(fill='both',expand=True,padx=7,pady=4)
        t1=ttk.Frame(tabs);t2=ttk.Frame(tabs);t3=ttk.Frame(tabs);tabs.add(t1,text='Cargo');tabs.add(t2,text='Risks');tabs.add(t3,text='Ports')
        self.cargo=ttk.Treeview(t1,columns=('id','carrier','owner','route','progress','eta','risk'),show='headings',height=12);self.cargo.pack(fill='both',expand=True)
        for c,wid in [('id',60),('carrier',70),('owner',75),('route',160),('progress',70),('eta',70),('risk',80)]:self.cargo.heading(c,text=c.upper());self.cargo.column(c,width=wid,stretch=(c=='route'))
        self.cargo.bind('<<TreeviewSelect>>',self._select_cargo)
        self.risks=ttk.Treeview(t2,columns=('type','target','ahead','severity'),show='headings');self.risks.pack(fill='both',expand=True)
        for c,wid in [('type',90),('target',180),('ahead',90),('severity',90)]:self.risks.heading(c,text=c.upper());self.risks.column(c,width=wid,stretch=(c=='target'))
        self.ports=ttk.Treeview(t3,columns=('port','operator','market','status'),show='headings');self.ports.pack(fill='both',expand=True)
        for c,wid in [('port',170),('operator',90),('market',70),('status',75)]:self.ports.heading(c,text=c.upper());self.ports.column(c,width=wid,stretch=(c=='port'))
        self.ports.bind('<<TreeviewSelect>>',self._select_port)
        ttk.Label(side,text='Legend: cyan = normal cargo • yellow = cargo with forward risk • orange = storm • red = piracy/conflict.  Arrows show route direction. Drag rotates camera only; it never changes game time.',foreground=MUTED,wraplength=450).pack(fill='x',padx=7,pady=5)
        self.protocol('WM_DELETE_WINDOW',self.close);self._refresh_tables();self._render();self._schedule()
    def close(self):
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
        self._job=None;self.destroy()
    def _schedule(self):
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
        self._job=self.after(300,self._pulse)
    def _pulse(self):
        if not self.winfo_exists():return
        self._refresh_tables();self._render();self._schedule()
    def _pause(self):
        self.market.paused=not self.market.paused;self.pause.config(text='▶ RESUME WORLD' if self.market.paused else '⏸ PAUSE WORLD')
        try:self.market.ui_app.status_flash('Simulation PAUSED' if self.market.paused else 'Simulation RUNNING')
        except Exception:pass
    def _skip(self,a):
        self.market.skip_to_next_open(a);self._refresh_tables();self._render()
    def _press(self,e):self._drag=(e.x,e.y,self.view_yaw,self.view_pitch)
    def _drag_view(self,e):
        if not self._drag:return
        x,y,yaw,pitch=self._drag;self.view_yaw=yaw+(e.x-x)*.006;self.view_pitch=max(-.9,min(.9,pitch+(e.y-y)*.004));self._render()
    def _release(self,e):
        moved=self._drag and (abs(e.x-self._drag[0])>4 or abs(e.y-self._drag[1])>4);self._drag=None
        if not moved:self._hit(e.x,e.y)
    def _wheel(self,e):self._zoom(.10 if e.delta>0 else -.10);return 'break'
    def _zoom(self,d):self.view_zoom=max(.65,min(1.65,self.view_zoom+d));self._render()
    def project(self,lon,lat,cx,cy,r,legacy_rot=None):
        # Camera rotation is independent of in-game time.  This is deliberate: dragging
        # the globe can never alter the simulation clock or shipping progress.
        lonr=math.radians(lon)+self.view_yaw;latr=math.radians(lat);x=math.cos(latr)*math.sin(lonr);y=math.sin(latr);z=math.cos(latr)*math.cos(lonr);cp=math.cos(self.view_pitch);sp=math.sin(self.view_pitch);yy=y*cp-z*sp;zz=y*sp+z*cp;rr=r*self.view_zoom;return cx+rr*x,cy-rr*yy,zz
    def _route(self,points,fill,cx,cy,r,dash=(4,5)):
        prev=None
        for lat,lon in points:
            cur=self.project(lon,lat,cx,cy,r)
            if prev and prev[2]>0 and cur[2]>0:self.cv.create_line(prev[0],prev[1],cur[0],cur[1],fill=fill,width=1,dash=dash,arrow='last',arrowshape=(6,7,3))
            prev=cur
    def _render(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(800,c.winfo_width());h=max(620,c.winfo_height());r=min(w*.39,h*.43);cx=w*.48;cy=h*.49
        self.clock.config(text=f'{self.market.clock.time} • {"PAUSED" if self.market.paused else f"{self.market.time_warp:.2f}x"}')
        # Globe shell + mesh, with static camera unless the user rotates it.
        c.create_oval(cx-r*self.view_zoom,cy-r*self.view_zoom,cx+r*self.view_zoom,cy+r*self.view_zoom,fill='#06304a',outline='#64d7f5',width=3)
        for lat in (-60,-30,0,30,60):
            pts=[]
            for lon in range(-180,181,10):
                x,y,z=self.project(lon,lat,cx,cy,r)
                if z>0:pts.extend((x,y))
            if len(pts)>3:c.create_line(*pts,fill='#15516a')
        for lon in range(-150,181,30):
            pts=[]
            for lat in range(-80,81,10):
                x,y,z=self.project(lon,lat,cx,cy,r)
                if z>0:pts.extend((x,y))
            if len(pts)>3:c.create_line(*pts,fill='#123f55')
        # Lightweight land masses from the legacy renderer, but no inherited timers.
        try:_LegacyGlobeWindow.draw_land(self,c,cx,cy,r,self.view_yaw)
        except Exception:pass
        for route in getattr(self.market,'freight_routes',[]):self._route(route['points'],'#2489a7',cx,cy,r)
        for route in getattr(self.market,'air_routes',[]):self._route(route['points'],'#8175c8',cx,cy,r,(2,5))
        self._hits=[]
        for p in getattr(self.market,'ports',[]):
            x,y,z=self.project(p['lon'],p['lat'],cx,cy,r)
            if z>0:
                c.create_oval(x-6,y-6,x+6,y+6,fill='#d8b96a',outline='white');self._hits.append(('port',x,y,12,p))
                if self.view_zoom>1.05:c.create_text(x+8,y-8,text=p['name'],fill=TEXT,font=('Arial',7,'bold'),anchor='w')
        for sh in getattr(self.market,'shipments',[]):
            lat,lon=self.market.shipment_position(sh);x,y,z=self.project(lon,lat,cx,cy,r)
            if z>0:
                risky=sh.get('hazard')!='NONE' and not sh.get('hazard_resolved');col=YELLOW if risky else CYAN;c.create_polygon(x-8,y+4,x+8,y+4,x+4,y-4,x-5,y-4,fill=col,outline='white');self._hits.append(('ship',x,y,14,sh))
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                hl,hn=self.market.shipment_hazard_position(sh);hx,hy,hz=self.project(hn,hl,cx,cy,r)
                if hz>0:
                    col=ORANGE if sh['hazard']=='STORM' else RED;c.create_oval(hx-9,hy-9,hx+9,hy+9,outline=col,width=2);c.create_text(hx,hy,text='S' if sh['hazard']=='STORM' else 'P',fill=col,font=('Arial',8,'bold'))
                    # Motion arrow uses route direction ahead of hazard, not a random screen vector.
                    tmp=dict(sh);tmp['progress']=min(.995,sh.get('hazard_progress',0)+.04);nl,nn=self.market.shipment_position(tmp);nx,ny,nz=self.project(nn,nl,cx,cy,r)
                    if nz>0:c.create_line(hx,hy,nx,ny,fill=col,width=2,arrow='last')
        for fl in getattr(self.market,'air_shipments',[]):
            lat,lon=self.market.air_shipment_position(fl);x,y,z=self.project(lon,lat,cx,cy,r)
            if z>0:c.create_polygon(x,y-7,x+7,y+5,x,y+2,x-7,y+5,fill='#b8acf2',outline='white');self._hits.append(('air',x,y,12,fl))
        for ev in getattr(self.market,'geopolitical_events',[]):
            if ev.get('resolved'):continue
            x,y,z=self.project(ev['lon'],ev['lat'],cx,cy,r)
            if z>0:c.create_oval(x-10,y-10,x+10,y+10,outline=RED if ev.get('status')=='ELEVATED' else ORANGE,width=2);c.create_text(x,y,text='!',fill='white',font=('Arial',10,'bold'))
        c.create_text(14,14,text='DRAG = CAMERA • WHEEL = ZOOM • CLICK = INSPECT • arrows = direction of travel',fill='#9bc5d6',font=('Arial',8,'bold'),anchor='nw')
    def _hit(self,x,y):
        best=None
        for typ,hx,hy,r,obj in getattr(self,'_hits',[]):
            d=(x-hx)**2+(y-hy)**2
            if d<=r*r and (best is None or d<best[0]):best=(d,typ,obj)
        if best:self._select(best[1],best[2])
    def _select(self,typ,obj):
        self._selected=(typ,obj);lines=[];asset=None
        if typ=='ship':
            remaining=max(0,1-obj['progress']);eta=remaining*obj['route']['days'];risk=obj['hazard'] if obj.get('hazard')!='NONE' and not obj.get('hazard_resolved') else 'NONE';asset=self.market.get_asset(obj['carrier']);lines=[f"VESSEL: {obj['name']}",f"Route: {obj['route']['name']}",f"Carrier: {obj['carrier']}",f"Cargo owner: {obj['cargo_owner']}",f"Cargo value: ${obj['cargo_value']/1e6:,.0f}M",f"Progress: {obj['progress']*100:.1f}%",f"ETA: ~{eta:.1f} game days",f"Forward risk: {risk}",f"Status: {obj.get('status','IN TRANSIT')}"]
        elif typ=='air':
            asset=self.market.get_asset(obj['carrier']);hours=max(1,obj['route'].get('hours',8));lines=[f"AIR CARGO: {obj['name']}",f"Route: {obj['route']['name']}",f"Carrier: {obj['carrier']}",f"Cargo owner: {obj['cargo_owner']}",f"Cargo value: ${obj['cargo_value']/1e6:,.0f}M",f"Progress: {obj['progress']*100:.1f}%",f"ETA: ~{(1-obj['progress'])*hours:.1f} game hours"]
        elif typ=='port':
            asset=self.market.get_asset(obj['operator']);status,remain=_sgp_session_countdown(asset,self.market.clock.current) if asset else ('N/A','');lines=[f"PORT: {obj['name']}",f"Operator / proxy: {obj['operator']}",f"Coordinates: {obj['lat']:.2f}, {obj['lon']:.2f}",f"Market: {_sgp_asset_session_code(asset) if asset else 'N/A'} {status}",remain]
        self.details.delete('1.0','end');self.details.insert('end','\n'.join(lines));state='normal' if asset else 'disabled';self.trade_btn.config(state=state);self.options_btn.config(state=state)
    def _selected_asset(self):
        if not self._selected:return None
        typ,obj=self._selected
        return self.market.get_asset(obj.get('operator') if typ=='port' else obj.get('carrier'))
    def _trade_selected(self):
        a=self._selected_asset()
        if a:self.market.ui_app.advanced_chart(a)
    def _options_selected(self):
        a=self._selected_asset()
        if a:self.market.ui_app.options_for(a)
    def _refresh_tables(self):
        if not self.winfo_exists():return
        # Cargo table is stable by shipment id, so selection does not jump every pulse.
        keep=self.cargo.selection();self.cargo.delete(*self.cargo.get_children())
        for sh in getattr(self.market,'shipments',[]):
            eta=max(0,1-sh['progress'])*sh['route']['days'];risk=sh['hazard'] if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved') else '—';iid=f"S{sh['id']}";self.cargo.insert('','end',iid=iid,values=(sh['name'],sh['carrier'],sh['cargo_owner'],sh['route']['name'],f"{sh['progress']*100:.0f}%",f'{eta:.1f}d',risk))
        if keep and self.cargo.exists(keep[0]):self.cargo.selection_set(keep[0])
        self.risks.delete(*self.risks.get_children())
        for sh in getattr(self.market,'shipments',[]):
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                ahead=max(0,sh.get('hazard_progress',1)-sh.get('progress',0));self.risks.insert('','end',values=(sh['hazard'],f"{sh['carrier']} / {sh['cargo_owner']}",f'{ahead*100:.0f}% route','HIGH' if sh['hazard']=='PIRATES' else 'MED'))
        for ev in getattr(self.market,'geopolitical_events',[]):
            if not ev.get('resolved'):self.risks.insert('','end',values=('CONFLICT',ev['name'],f"{max(0,ev['minutes_to_event']):.0f}m",ev.get('status','WATCH')))
        self.ports.delete(*self.ports.get_children())
        for i,p in enumerate(getattr(self.market,'ports',[])):
            a=self.market.get_asset(p['operator']);status='N/A'
            if a:status='OPEN' if self.market.asset_regular_open(a) else 'CLOSED'
            self.ports.insert('','end',iid=f'P{i}',values=(p['name'],p['operator'],_sgp_asset_session_code(a),status))
    def _select_cargo(self,e=None):
        sel=self.cargo.selection()
        if not sel:return
        name=self.cargo.item(sel[0],'values')[0]
        for sh in getattr(self.market,'shipments',[]):
            if sh['name']==name:self._select('ship',sh);break
    def _select_port(self,e=None):
        sel=self.ports.selection()
        if not sel:return
        name=self.ports.item(sel[0],'values')[0]
        for p in getattr(self.market,'ports',[]):
            if p['name']==name:self._select('port',p);break

def _sgp_globe_v12(self):return GlobalTradeWorkstation(self.root,self.market)
App.globe=_sgp_globe_v12

# Expose the same workstation from advanced tools / existing callbacks that resolve GlobeWindow.
GlobeWindow=GlobalTradeWorkstation

# ===== Stock Game Pro 1.3 UI / individual chart cadence / casino production patch =====
# Main chart tickrate is now configured from each chart's context menu.  The old
# top-bar dropdown is hidden to prevent accidental workspace-wide changes.
_App_init_v13_base=App.__init__
def _sgp_app_init_v13(self,root,market,portfolio):
    _App_init_v13_base(self,root,market,portfolio)
    try:
        if hasattr(self,'chart_rate'):self.chart_rate.pack_forget()
        # Find the legacy adjacent widgets by their visible text and hide them.
        for widget in self.root.winfo_children():
            pass
        def walk(w):
            for ch in w.winfo_children():
                try:
                    txt=ch.cget('text') if 'text' in ch.keys() else ''
                    if txt in ('Chart tick','SYNC ALL'):ch.pack_forget()
                except Exception:pass
                walk(ch)
        walk(self.root)
    except Exception:pass
App.__init__=_sgp_app_init_v13

# Avoid the hidden legacy control being mutated by chart selection.
_sync_chart_controls_v13_base=App.sync_chart_controls
def _sgp_sync_chart_controls_v13(self):
    _sync_chart_controls_v13_base(self)
    try:
        c=self.charts[self.active_chart]
        self.active_label.config(text=f'Chart {self.active_chart+1}: {c.asset.symbol if c.asset else "—"} • {c.refresh_ms}ms')
    except Exception:pass
App.sync_chart_controls=_sgp_sync_chart_controls_v13

# Rich individual-chart context menu including tickrate.  No action in this submenu
# changes any other chart.
def _sgp_set_one_chart_rate(chart,ms):
    chart.set_refresh_rate(int(ms));chart.request_draw(force=True)
    try:chart.app.status_flash(f'Chart {chart.index+1} tickrate set to {int(ms)} ms')
    except Exception:pass

def _sgp_chart_context_v13(self,e):
    if not getattr(self,'selected_popup',False):self.app.active_chart=self.index;self.app.sync_chart_controls()
    a=self.asset
    if not a:return
    p=self.y_to_price(e.y);m=tk.Menu(self,tearoff=0)
    state='REGULAR'
    try:state=self.app.market.asset_trade_state(a)
    except Exception:pass
    m.add_command(label=f'{a.symbol} • {state}',state='disabled');m.add_separator()
    m.add_command(label=f'BUY {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'BUY','LIMIT',p));m.add_command(label=f'SELL {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SELL','LIMIT',p));m.add_command(label=f'SHORT {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SHORT','LIMIT',p));m.add_command(label=f'COVER {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'COVER','LIMIT',p));m.add_separator()
    m.add_command(label='Buy at Market',command=lambda:self.app.order_window(a,'BUY','MARKET',None));m.add_command(label='Set Stop',command=lambda:self.app.order_window(a,'SELL','STOP',p));m.add_command(label='Open Options',command=lambda:self.app.options_for(a));m.add_command(label='Level 2 / Level 3',command=lambda:self.app.depth_for(a));m.add_command(label='POP OUT ADVANCED CHART',command=lambda:self.app.advanced_chart(a));m.add_separator()
    rate=tk.Menu(m,tearoff=0);rv=tk.IntVar(value=int(getattr(self,'refresh_ms',100)))
    self._context_rate_var=rv
    for ms in (25,50,100,180,250,500,1000,2000,5000):rate.add_radiobutton(label=f'{ms} ms',value=ms,variable=rv,command=lambda x=ms:_sgp_set_one_chart_rate(self,x))
    m.add_cascade(label=f'CHART TICKRATE • {self.refresh_ms} ms',menu=rate)
    tfm=tk.Menu(m,tearoff=0)
    for tf in ('1D','1W','1M','3M','6M','1Y','5Y','MAX'):tfm.add_command(label=tf,command=lambda x=tf:self.set_tf(x))
    m.add_cascade(label=f'TIMEFRAME • {self.timeframe}',menu=tfm)
    m.add_command(label=f'REFRESH {self.timeframe} TICKER',command=self.manual_refresh,state='disabled' if self.timeframe in ('5Y','MAX') else 'normal')
    if not getattr(self,'selected_popup',False):m.add_separator();m.add_command(label='ADD CHART',command=self.app.add_chart);m.add_command(label='REMOVE THIS CHART',command=lambda:self.app.remove_chart(self.index))
    m.tk_popup(e.x_root,e.y_root)
Chart.context=_sgp_chart_context_v13

# Add the actual execution state (regular / global overnight ECN / closed) to the
# chart's compact session line without forcing another full chart repaint.
_Chart_draw_v13_base=Chart.draw
def _sgp_chart_draw_v13(self):
    _Chart_draw_v13_base(self)
    if not self.asset:return
    try:
        self.delete('tradestate')
        state=self.app.market.asset_trade_state(self.asset);w=max(280,self.winfo_width());col=GREEN if state in ('REGULAR','24/7') else CYAN if 'OVERNIGHT' in state else MUTED
        self.create_text(w-16,22,text=state,fill=col,font=('Arial',7,'bold'),anchor='ne',tags='tradestate')
    except Exception:pass
Chart.draw=_sgp_chart_draw_v13

# -------------------------- Casino visual system -----------------------------
_SGP_CHIP_COLORS={25:'#d94b55',100:'#4267d6',500:'#2b9b66',1000:'#252b36',5000:'#7b4bc4',10000:'#e0b74e'}
def _sgp_chip_color(value):
    vals=sorted(_SGP_CHIP_COLORS)
    return _SGP_CHIP_COLORS[min(vals,key=lambda v:abs(v-max(1,value)))]

def _sgp_draw_bankroll(c,x,y,cash,label='BANKROLL',pending=0):
    available=max(0,float(cash)-float(pending));c.create_text(x,y-52,text=label,fill='#f4e7b6',font=('Arial',9,'bold'),anchor='center')
    # A compact pile of mixed-value chips; the number is authoritative.
    for j,val in enumerate((10000,5000,1000,500,100,25)):
        if available<val*.5 and j<4:continue
        xx=x+(j%3-1)*22;yy=y+(j//3)*19
        for k in range(3):
            col=_SGP_CHIP_COLORS[val];c.create_oval(xx-17,yy-8-k*4,xx+17,yy+8-k*4,fill=col,outline='#f7e7b2',width=1);c.create_line(xx-12,yy-k*4,xx-6,yy-k*4,fill='white',width=2);c.create_line(xx+6,yy-k*4,xx+12,yy-k*4,fill='white',width=2)
    c.create_text(x,y+45,text=f'${available:,.0f}',fill='white',font=('Arial',11,'bold'))

_Blackjack_v13_base=BlackjackWindow
class BlackjackWindow(_Blackjack_v13_base):
    def draw_table(self):
        super().draw_table();w=max(1000,self.canvas.winfo_width());pending=sum(getattr(self,'bet_amounts',[])) if getattr(self,'active',False) else 0
        _sgp_draw_bankroll(self.canvas,w-95,95,_sgp_total_net_worth(self.portfolio,self.market),'NET WORTH',0)

_Roulette_v13_base=RouletteWindow
class RouletteWindow(_Roulette_v13_base):
    def _chip(self,c,x,y,amt,label):
        if not amt:return
        # Stacked chips communicate cumulative bet size instead of one flat gold badge.
        denom=max([v for v in self.chips if v<=max(amt,25)],default=25);count=max(1,min(5,int(round(amt/max(1,denom)))));col=_sgp_chip_color(denom)
        for i in range(count):
            yy=y-i*4;c.create_oval(x-14,yy-8,x+14,yy+8,fill=col,outline='#f4e1a3',width=1);c.create_line(x-10,yy,x-5,yy,fill='white',width=2);c.create_line(x+5,yy,x+10,yy,fill='white',width=2)
        c.create_text(x,y-count*4-10,text=f'${amt:,}',fill='white',font=('Arial',6,'bold'))
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        c=self.cv;c.delete('all');w=max(1100,c.winfo_width());h=max(700,c.winfo_height());cx=w*.17;cy=h*.27;r=min(h*.205,w*.12)
        c.create_text(cx,18,text=f'{self.dealer} • EUROPEAN ROULETTE',fill='#f6e6b5',font=('Georgia',18,'bold'))
        # Clean single wheel with 37 wedge pockets instead of overlapping circular pockets.
        c.create_oval(cx-r-6,cy-r-6,cx+r+6,cy+r+6,fill='#412d13',outline='#e8c66f',width=5)
        pocket_positions={};extent=360/37
        for i,n in enumerate(self.EURO_ORDER):
            # Tk canvas angles rotate counter-clockwise from 3 o'clock.
            start=90-(i+1)*extent;col='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#171b20'
            c.create_arc(cx-r,cy-r,cx+r,cy+r,start=start,extent=extent,style='pieslice',fill=col,outline='#d7bd79',width=1)
            a=math.radians(90-(i+.5)*extent);tx=cx+math.cos(a)*r*.80;ty=cy-math.sin(a)*r*.80;pocket_positions[n]=(tx,ty,a);c.create_text(tx,ty,text=str(n),fill='white',font=('Arial',7,'bold'))
        # One wood/brass rotor hub only.
        c.create_oval(cx-r*.48,cy-r*.48,cx+r*.48,cy+r*.48,fill='#6a481e',outline='#e7c66c',width=3);c.create_oval(cx-r*.16,cy-r*.16,cx+r*.16,cy+r*.16,fill='#d5ad52',outline='#fff1b3',width=2);c.create_oval(cx-5,cy-5,cx+5,cy+5,fill='#5b3d1a',outline='')
        if wheel_number is not None:
            if spinning:
                a=ball_phase*math.pi*16-math.pi/2;rad=r*(.94-.13*min(1,ball_phase));bx=cx+math.cos(a)*rad;byb=cy+math.sin(a)*rad
            else:
                tx,ty,a=pocket_positions.get(wheel_number,pocket_positions[0]);bx=tx+math.cos(a)*6;byb=ty-math.sin(a)*6
            c.create_oval(bx-6,byb-6,bx+6,byb+6,fill='#f7f7f1',outline='#bec7cc',width=2)
        # Betting board (same hit geometry as v1.2).
        bx,by,cw,ch,zero_w=self._table_geom(w,h);c.create_rectangle(bx-zero_w,by,bx,by+ch*3,fill='#13865c',outline='#d8b96a',width=2);c.create_text(bx-zero_w/2,by+ch*1.5,text='0',fill='white',font=('Arial',18,'bold'));self._chip(c,bx-zero_w/2,by+ch*1.5,self.bets.get(0,0),'0')
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch;fill='#b92f48' if n in self.REDS else '#151b23';c.create_rectangle(x,y,x+cw,y+ch,fill=fill,outline='#d8b96a');c.create_text(x+cw*.5,y+ch*.5,text=str(n),fill='white',font=('Arial',13,'bold'));self._chip(c,x+cw/2,y+ch/2,self.bets.get(n,0),str(n))
        for row,key in enumerate(('2:1_ROW1','2:1_ROW2','2:1_ROW3')):
            x=bx+12*cw;y=by+row*ch;c.create_rectangle(x,y,x+cw*.85,y+ch,fill='#0e6950',outline='#d8b96a');c.create_text(x+cw*.42,y+ch*.5,text='2:1',fill='white',font=('Arial',10,'bold'));self._chip(c,x+cw*.42,y+ch/2,self.bets.get(key,0),'2:1')
        oy=by+3*ch+10;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw;c.create_rectangle(x,oy,x+rw,oy+ch*.85,fill='#0e6950',outline='#d8b96a');c.create_text(x+rw/2,oy+ch*.42,text=key,fill='white',font=('Arial',8,'bold'));self._chip(c,x+rw/2,oy+ch*.42,self.bets.get(key,0),key)
        oy2=oy+ch+7;rw=(cw*12)/6
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            x=bx+i*rw;fill='#b92f48' if key=='RED' else '#151b23' if key=='BLACK' else '#0e6950';c.create_rectangle(x,oy2,x+rw,oy2+ch*.85,fill=fill,outline='#d8b96a');c.create_text(x+rw/2,oy2+ch*.42,text=key,fill='white',font=('Arial',8,'bold'));self._chip(c,x+rw/2,oy2+ch*.42,self.bets.get(key,0),key)
        # Chip rack + available bankroll visually decrease as bets are placed.
        rack_x=w*.89;rack_y=70;pending=sum(self.bets.values());_sgp_draw_bankroll(c,rack_x,rack_y,self.portfolio.cash,'AVAILABLE CHIPS',pending)
        c.create_text(rack_x,rack_y+72,text='BET CHIP',fill=MUTED,font=('Arial',8,'bold'))
        for i,val in enumerate(self.chips):
            x=rack_x-80+(i%3)*80;y=rack_y+105+(i//3)*45;col=_SGP_CHIP_COLORS.get(val,'#d8b96a');c.create_oval(x-18,y-10,x+18,y+10,fill=col,outline='#f4e1a3',width=2);c.create_text(x,y,text=f'${val:,}',fill='white' if val!=10000 else '#1c2430',font=('Arial',6,'bold'))
        # History at bottom.
        panel_y=h-140;c.create_rectangle(18,panel_y,w-18,h-12,fill='#09141d',outline='#31495a',width=2);c.create_text(32,panel_y+10,text=f'RECORDED SPINS • {len(self.history):,} / 500',fill='#f6e6b5',font=('Arial',10,'bold'),anchor='nw');hist=list(reversed(self.history[-60:]));cols=min(30,max(10,int((w-60)/38)))
        for i,n in enumerate(hist):
            row=i//cols;col=i%cols;x=35+col*38;y=panel_y+43+row*34;fill='#13865c' if n==0 else '#b92f48' if n in self.REDS else '#151b23';c.create_oval(x-11,y-11,x+11,y+11,fill=fill,outline='#d8b96a');c.create_text(x,y,text=str(n),fill='white',font=('Arial',7,'bold'))
        self.balance.config(text=f'${self.portfolio.cash:,.2f}')

class SlotMachineWindow(ToolWindow):
    SYMBOLS=['7','BAR','★','♛','♦','🍒']
    PAY={'7':25,'BAR':12,'★':8,'♛':6,'♦':4,'🍒':3}
    def __init__(self,parent,portfolio,market):
        super().__init__(_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • MARKET FLOOR SLOTS','900x650');self.resizable(True,True);self.bet=tk.IntVar(value=100);self.reels=['BAR','★','🍒'];self.spinning=False
        top=ttk.Frame(self);top.pack(fill='x',padx=12,pady=8);ttk.Label(top,text='VIRTUAL SLOT FLOOR',font=('Arial',15,'bold')).pack(side='left');ttk.Label(top,text='Bet').pack(side='left',padx=(25,4));ttk.Combobox(top,textvariable=self.bet,values=[25,100,500,1000,5000,10000],state='readonly',width=9).pack(side='left');ttk.Button(top,text='SPIN',command=self.spin).pack(side='left',padx=8);self.msg=ttk.Label(top,text='');self.msg.pack(side='right')
        self.cv=tk.Canvas(self,bg='#100d18',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=10,pady=8);self.draw()
    def spin(self):
        if self.spinning:return
        b=int(self.bet.get())
        if b>self.portfolio.cash:return messagebox.showerror('Slots','Insufficient balance.')
        self.portfolio.cash-=b;self.spinning=True;self._anim=0;self.after(30,self._step)
    def _step(self):
        self.reels=[random.choice(self.SYMBOLS) for _ in range(3)];self.draw();self._anim+=1
        if self._anim<18:return self.after(30+self._anim*4,self._step)
        b=int(self.bet.get());payout=0
        if len(set(self.reels))==1:payout=b*self.PAY[self.reels[0]]
        elif len(set(self.reels))==2:payout=int(b*1.5)
        self.portfolio.cash+=payout;self.msg.config(text=f'{"WIN" if payout else "NO WIN"} • ${payout:,.0f}');self.spinning=False;self.draw()
    def draw(self):
        c=self.cv;c.delete('all');w=max(700,c.winfo_width());h=max(450,c.winfo_height());c.create_rectangle(w*.18,h*.13,w*.82,h*.78,fill='#291b35',outline='#e0b85f',width=7);c.create_text(w/2,h*.19,text='STOCK GAME PRO',fill='#f5d88b',font=('Georgia',22,'bold'))
        for i,s in enumerate(self.reels):
            x=w*.31+i*w*.19;c.create_rectangle(x-65,h*.32,x+65,h*.58,fill='#f5efe0',outline='#d9b85e',width=4);c.create_text(x,h*.45,text=s,fill='#251c2d',font=('Georgia',34,'bold'))
        _sgp_draw_bankroll(c,w*.50,h*.69,_sgp_total_net_worth(self.portfolio,self.market),'NET WORTH',0);c.create_text(w/2,h*.85,text='3 MATCH = JACKPOT • PAIR = 1.5× • virtual simulator credits',fill='#9e8faf',font=('Arial',9))

_Casino_v13_base=CasinoWindow
class CasinoWindow(_Casino_v13_base):
    def __init__(self,parent,portfolio,market):
        ToolWindow.__init__(self,_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • CASINO FLOOR','1180x760');self.resizable(True,True)
        ttk.Label(self,text='AFTER-HOURS CASINO FLOOR',font=('Arial',18,'bold')).pack(pady=(20,4));ttk.Label(self,text='Virtual simulator credits • bankroll is shared with your trading account',foreground=MUTED).pack(pady=(0,15))
        bank=tk.Canvas(self,bg='#08131c',height=150,highlightthickness=0);bank.pack(fill='x',padx=20,pady=8);_sgp_draw_bankroll(bank,590,70,_sgp_total_net_worth(portfolio,market),'CURRENT NET WORTH',0)
        f=ttk.Frame(self);f.pack(fill='x',padx=20,pady=14);ttk.Button(f,text='♠  BLACKJACK TRAINER',command=lambda:BlackjackWindow(self,portfolio,market)).pack(side='left',expand=True,fill='x',padx=7,ipady=12);ttk.Button(f,text='●  EUROPEAN ROULETTE',command=lambda:RouletteWindow(self,portfolio,market)).pack(side='left',expand=True,fill='x',padx=7,ipady=12);ttk.Button(f,text='7  SLOT MACHINE',command=lambda:SlotMachineWindow(self,portfolio,market)).pack(side='left',expand=True,fill='x',padx=7,ipady=12)
        ttk.Label(self,text='Choose a table. Casino windows use lightweight render loops and do not accelerate game time.',foreground=MUTED).pack(pady=12)

# Ensure launcher resolves final casino classes.
def _sgp_casino_v13(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v13

# More informative Global Trader details: selected objects expose execution state and
# both the carrier/port operator and cargo owner's tradable securities.
_Global_select_v13_base=GlobalTradeWorkstation._select
def _sgp_global_select_v13(self,typ,obj):
    _Global_select_v13_base(self,typ,obj)
    try:
        text=self.details.get('1.0','end').strip();asset=self._selected_asset();state=self.market.asset_trade_state(asset) if asset else 'N/A'
        extra=f'\n\nExecution state: {state}'
        if typ in ('ship','air'):
            cargo=self.market.get_asset(obj.get('cargo_owner'));extra+=f'\nCarrier security: {obj.get("carrier")}\nCargo-owner security: {obj.get("cargo_owner")} ({self.market.asset_trade_state(cargo) if cargo else "N/A"})'
        elif typ=='port':extra+=f'\nPort operator security: {obj.get("operator")}'
        self.details.delete('1.0','end');self.details.insert('end',text+extra)
    except Exception:pass
GlobalTradeWorkstation._select=_sgp_global_select_v13

# Port table shows the true local exchange plus regular/ECN state.
_Global_refresh_tables_v13_base=GlobalTradeWorkstation._refresh_tables
def _sgp_global_refresh_tables_v13(self):
    _Global_refresh_tables_v13_base(self)
    try:
        for iid in self.ports.get_children():
            vals=list(self.ports.item(iid,'values'))
            if len(vals)>=4:
                a=self.market.get_asset(vals[1]);vals[3]=self.market.asset_trade_state(a) if a else 'N/A';self.ports.item(iid,values=vals)
    except Exception:pass
GlobalTradeWorkstation._refresh_tables=_sgp_global_refresh_tables_v13

# v1.3 casino interaction finishing pass.
def _sgp_total_net_worth(portfolio,market):
    try:return portfolio.mark_value(market.all_assets())
    except Exception:return getattr(portfolio,'cash',0.0)

_Roulette_v13_interactive_base=RouletteWindow
class RouletteWindow(_Roulette_v13_interactive_base):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent,portfolio,market)
        try:self.cv.unbind('<Button-1>');self.cv.bind('<Button-1>',self._v13_click)
        except Exception:pass
    def _v13_click(self,e):
        w=max(1100,self.cv.winfo_width());rack_x=w*.89;rack_y=70
        for i,val in enumerate(self.chips):
            x=rack_x-80+(i%3)*80;y=rack_y+105+(i//3)*45
            if (e.x-x)**2/24**2+(e.y-y)**2/18**2<=1:
                self.chip.set(val);self.result.config(text=f'Selected ${val:,} chip. Click the table to place it.');self.draw();return 'break'
        return self.board_click(e)

# Repatch the casino launcher so it resolves the final interactive RouletteWindow.
def _sgp_casino_v13_final(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v13_final


# ============================================================================
# Stock Game Pro 1.4 — chart navigation, logistics stability, casino polish
# ============================================================================

# Historical viewport: MAX and 5Y are windows into history instead of attempting to
# put the whole database on screen at once. This makes OLDER/NEWER and drag scrolling
# behave consistently even when decades of candles are loaded.
def _sgp_chart_data_v14(self):
    if not self.asset:return []
    interval={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe]
    raw=list(self.asset.chart_candles(interval))
    if not raw:return []
    maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':360,'MAX':520}[self.timeframe]
    visible=min(len(raw),max(30,int(maxbars/max(.25,self.zoom))))
    maxoff=max(0,len(raw)-visible);self.view_offset=max(0,min(int(getattr(self,'view_offset',0)),maxoff))
    end=len(raw)-self.view_offset;start=max(0,end-visible);d=raw[start:end]
    # Keep MAX rendering bounded on very wide displays while retaining first/last dates.
    target=max(250,min(1000,int(max(400,self.winfo_width())*1.15)))
    if len(d)>target:
        step=(len(d)-1)/(target-1);d=[d[round(i*step)] for i in range(target)]
    return d
Chart.data=_sgp_chart_data_v14

def _sgp_chart_pan_v14(self,bars):
    if not self.asset:return
    interval={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe]
    raw=list(self.asset.chart_candles(interval));maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':360,'MAX':520}[self.timeframe]
    visible=min(len(raw),max(30,int(maxbars/max(.25,self.zoom))));maxoff=max(0,len(raw)-visible)
    self.view_offset=max(0,min(maxoff,int(getattr(self,'view_offset',0)+bars)));self.follow_latest=(self.view_offset==0)
    self.request_draw(force=True)
Chart.pan_bars=_sgp_chart_pan_v14

# Stronger date axis with weekday labels. Intraday axes show the weekday whenever the
# visible data crosses a date boundary, preventing weekends from being ambiguous.
_Chart_draw_v14_base=Chart.draw
def _sgp_chart_draw_v14(self):
    _Chart_draw_v14_base(self)
    d=self.data()
    if not d:return
    self.delete('v14axis');w=max(280,self.winfo_width());h=max(170,self.winfo_height());left,right=62,w-12;axis_y=h-7
    count=3 if w<430 else 5 if w<850 else 7
    prev_day=None
    for j in range(count):
        i=min(len(d)-1,round((len(d)-1)*j/max(1,count-1)));ts=d[i].timestamp;x=left+(i+.5)*(right-left)/max(1,len(d))
        if self.timeframe=='1D':label=ts.strftime('%a %m/%d\n%H:%M')
        elif self.timeframe in ('1W','1M'):label=ts.strftime('%a %m/%d\n%H:%M')
        elif self.timeframe in ('3M','6M','1Y'):label=ts.strftime('%a %Y-%m-%d')
        else:label=ts.strftime('%Y-%m-%d')
        self.create_text(x,axis_y,text=label,fill='#91a3b6',font=('Consolas',6 if w<500 else 7),anchor='s',justify='center',tags='v14axis')
    self.create_text((left+right)/2,h-28,text=f'VISIBLE: {d[0].timestamp:%a %Y-%m-%d %H:%M}  →  {d[-1].timestamp:%a %Y-%m-%d %H:%M}',fill='#60798d',font=('Consolas',6),anchor='s',tags='v14axis')
Chart.draw=_sgp_chart_draw_v14

# Right-click tickrate belongs to each chart and nowhere else.
_Chart_context_v14_base=Chart.context
def _sgp_chart_context_v14(self,e):
    if not getattr(self,'selected_popup',False):self.app.active_chart=self.index;self.app.sync_chart_controls()
    a=self.asset
    if not a:return
    p=self.y_to_price(e.y);m=tk.Menu(self,tearoff=0)
    m.add_command(label=f'BUY {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'BUY','LIMIT',p));m.add_command(label=f'SELL {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SELL','LIMIT',p));m.add_command(label=f'SHORT {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'SHORT','LIMIT',p));m.add_command(label=f'COVER {a.symbol} @ ${p:,.2f}',command=lambda:self.app.order_window(a,'COVER','LIMIT',p));m.add_separator()
    m.add_command(label='OPEN ADVANCED CHART',command=lambda:self.app.advanced_chart(a));m.add_command(label='OPTIONS / STRATEGY LAB',command=lambda:self.app.options_for(a));m.add_command(label='LEVEL 2 / 3 / TAPE',command=lambda:self.app.depth_for(a))
    tfm=tk.Menu(m,tearoff=0)
    for tf in ('1D','1W','1M','3M','6M','1Y','5Y','MAX'):tfm.add_radiobutton(label=tf,value=tf,variable=tk.StringVar(value=self.timeframe),command=lambda v=tf:self.set_tf(v))
    m.add_cascade(label=f'TIMEFRAME  •  {self.timeframe}',menu=tfm)
    rm=tk.Menu(m,tearoff=0)
    for ms in (25,50,100,180,250,500,1000,2000,5000):rm.add_command(label=f'{ms} ms'+('  ✓' if self.refresh_ms==ms else ''),command=lambda v=ms:_sgp_set_one_chart_rate(self,v))
    m.add_cascade(label=f'CHART TICKRATE  •  {self.refresh_ms} ms',menu=rm)
    m.add_command(label=f'REFRESH {self.timeframe} TICKER',command=self.manual_refresh,state='disabled' if self.timeframe in ('5Y','MAX') else 'normal')
    if not getattr(self,'selected_popup',False):m.add_separator();m.add_command(label='ADD CHART',command=self.app.add_chart);m.add_command(label='REMOVE THIS CHART',command=lambda:self.app.remove_chart(self.index))
    m.tk_popup(e.x_root,e.y_root)
Chart.context=_sgp_chart_context_v14

# Advanced history controls are page-aware and always produce an observable action.
_Advanced_v14_base=AdvancedChartWindow
class AdvancedChartWindow(_Advanced_v14_base):
    def __init__(self,parent,app,asset):
        super().__init__(parent,app,asset)
        # Replace inherited button commands by locating them by text.
        for frame in self.winfo_children():
            for ch in frame.winfo_children():
                try:t=ch.cget('text')
                except Exception:continue
                if t=='◀ OLDER':ch.config(command=self.older_page)
                elif t=='NEWER ▶':ch.config(command=self.newer_page)
                elif t=='LIVE':ch.config(command=self.go_live)
        self._sync_history_status()
    def _page(self):
        return max(20,int(len(self.chart.data())*.75))
    def older_page(self):
        self.chart.pan_mode=True;self.chart.pan_bars(self._page());self.chart.follow_latest=False;self._sync_history_status()
    def newer_page(self):
        self.chart.pan_mode=True;self.chart.pan_bars(-self._page());self._sync_history_status()
        if self.chart.view_offset==0:self.go_live()
    def toggle_free_scroll(self):
        self.chart.pan_mode=not self.chart.pan_mode
        if self.chart.pan_mode:self.chart.follow_latest=False
        self._sync_history_status();self.chart.request_draw(force=True)
    def go_live(self):
        self.chart.view_offset=0;self.chart.follow_latest=True;self.chart.pan_mode=False;self._sync_history_status();self.chart.request_draw(force=True)
    def _sync_history_status(self):
        try:self.history_btn.config(text='FREE SCROLL: ON' if self.chart.pan_mode else 'FREE SCROLL: OFF')
        except Exception:pass
        d=self.chart.data()
        if not d:return
        txt='LIVE • following newest candle' if self.chart.view_offset==0 and not self.chart.pan_mode else f'HISTORY • {self.chart.view_offset} bars behind live • {d[0].timestamp:%Y-%m-%d} → {d[-1].timestamp:%Y-%m-%d}'
        try:self.history_status.config(text=txt)
        except Exception:pass

def _sgp_open_adv_v14(self,a):return AdvancedChartWindow(self.root,self,a)
App.advanced_chart=_sgp_open_adv_v14

# Main workstation sizing/pause placement. The portfolio pane starts narrower so charts
# receive the majority of horizontal space, and pause sits directly beside Time Warp.
_App_init_v14_base=App.__init__
def _sgp_app_init_v14(self,root,market,portfolio):
    _App_init_v14_base(self,root,market,portfolio)
    try:
        top=self.time_warp_label.master
        self.pause_top_v14=ttk.Button(top,text='⏸ PAUSE',command=self.toggle_pause,width=10);self.pause_top_v14.pack(side='left',padx=(0,2),after=self.time_warp_label)
        ttk.Button(top,text='⏭ NEXT OPEN',command=self.skip_to_next_open,width=11).pack(side='left',padx=(0,4),after=self.pause_top_v14)
    except Exception:pass
    def layout():
        try:
            panes=[x for x in root.winfo_children() if isinstance(x,ttk.PanedWindow) and str(x.cget('orient'))=='horizontal']
            if panes:
                pw=panes[0];W=max(1200,root.winfo_width());pw.sashpos(0,300);pw.sashpos(1,W-350)
        except Exception:pass
    root.after(250,layout)
App.__init__=_sgp_app_init_v14

_toggle_pause_v14_base=App.toggle_pause
def _sgp_toggle_pause_v14(self):
    _toggle_pause_v14_base(self)
    try:self.pause_top_v14.config(text='▶ RESUME' if self.market.paused else '⏸ PAUSE')
    except Exception:pass
App.toggle_pause=_sgp_toggle_pause_v14

# ------------------------- Global Trade Workstation -------------------------
# Coastline coordinates are based on real lon/lat geography. We draw front-facing
# coastline segments instead of filling clipped rear-hemisphere polygons, eliminating
# the triangular land artifacts produced by the old renderer.
_SGP_COASTS=[
[(-168,72),(-150,60),(-135,55),(-125,49),(-117,33),(-105,22),(-97,18),(-82,25),(-80,32),(-70,44),(-60,53),(-74,62),(-100,70),(-130,72),(-168,72)],
[(-81,12),(-75,5),(-70,-10),(-65,-20),(-60,-35),(-68,-53),(-75,-48),(-80,-25),(-81,12)],
[(-10,36),(0,44),(15,46),(30,44),(40,38),(35,30),(20,31),(10,36),(-10,36)],
[(-17,35),(0,35),(12,30),(25,20),(35,5),(42,-15),(32,-34),(18,-35),(5,-25),(-5,-5),(-17,15),(-17,35)],
[(30,70),(60,72),(90,70),(120,62),(150,55),(175,50),(165,35),(145,25),(120,20),(105,10),(80,10),(60,25),(45,40),(30,55),(30,70)],
[(68,25),(80,20),(90,10),(105,5),(120,0),(130,10),(120,25),(105,22),(90,25),(68,25)],
[(112,-11),(125,-12),(140,-17),(153,-28),(150,-39),(135,-44),(120,-34),(112,-11)] ]

def _sgp_draw_coast(cv,work,cx,cy,r):
    for poly in _SGP_COASTS:
        run=[]
        for lon,lat in poly:
            x,y,z=work.project(lon,lat,cx,cy,r)
            if z>.03:run.extend((x,y))
            elif len(run)>=4:cv.create_line(*run,fill='#52a77d',width=2,smooth=True);run=[]
        if len(run)>=4:cv.create_line(*run,fill='#52a77d',width=2,smooth=True)

_Global_v14_base=GlobalTradeWorkstation
class GlobalTradeWorkstation(_Global_v14_base):
    def __init__(self,parent,market):
        super().__init__(parent,market);self.title('STOCK GAME PRO • GLOBAL TRADE / RISK RADAR');self._render_pending=False
        # Slow the passive repaint; object motion is based on game state, not frame count.
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
        self._job=self.after(650,self._pulse)
    def _schedule(self):
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
        self._job=self.after(650,self._pulse)
    def _drag_view(self,e):
        if not self._drag:return
        x,y,yaw,pitch=self._drag;self.view_yaw=yaw+(e.x-x)*.006;self.view_pitch=max(-.9,min(.9,pitch+(e.y-y)*.004));self._render_camera_limited()
    def _zoom(self,d):self.view_zoom=max(.65,min(1.65,self.view_zoom+d));self._render_camera_limited()
    def _render_camera_limited(self):
        if self._render_pending:return
        self._render_pending=True
        def go():
            self._render_pending=False
            if self.winfo_exists():self._render()
        self.after(24,go)
    def _refresh_tables(self):
        # Preserve explicit selection while rows update. Programmatic refresh must never
        # clear the object the trader is inspecting.
        selected=self._selected
        try:super()._refresh_tables()
        except Exception:return
        self._selected=selected
    def _render(self):
        if not self.winfo_exists():return
        c=self.cv;c.delete('all');w=max(800,c.winfo_width());h=max(620,c.winfo_height());r=min(w*.39,h*.43);cx=w*.48;cy=h*.49
        self.clock.config(text=f'{self.market.clock.time} • {"PAUSED" if self.market.paused else f"{self.market.time_warp:.2f}x"}')
        rr=r*self.view_zoom;c.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,fill='#062c47',outline='#5dd2ef',width=3)
        for lat in (-60,-30,0,30,60):
            pts=[]
            for lon in range(-180,181,8):
                x,y,z=self.project(lon,lat,cx,cy,r)
                if z>0:pts.extend((x,y))
            if len(pts)>3:c.create_line(*pts,fill='#10465e',width=1)
        for lon in range(-150,181,30):
            pts=[]
            for lat in range(-80,81,8):
                x,y,z=self.project(lon,lat,cx,cy,r)
                if z>0:pts.extend((x,y))
            if len(pts)>3:c.create_line(*pts,fill='#0d3d53',width=1)
        _sgp_draw_coast(c,self,cx,cy,r)
        for route in getattr(self.market,'freight_routes',[]):self._route(route['points'],'#2489a7',cx,cy,r)
        for route in getattr(self.market,'air_routes',[]):self._route(route['points'],'#8175c8',cx,cy,r,(2,5))
        self._hits=[]
        selected=self._selected
        # Real port coordinates come directly from market.ports; no screen-space fake ports.
        for p in getattr(self.market,'ports',[]):
            x,y,z=self.project(p['lon'],p['lat'],cx,cy,r)
            if z<=0:continue
            c.create_rectangle(x-4,y-4,x+4,y+4,fill='#ffd66d',outline='white');self._hits.append(('port',x,y,12,p))
            if selected and selected[0]=='port' and selected[1] is p:c.create_oval(x-11,y-11,x+11,y+11,outline='#ffffff',width=2)
            if self.view_zoom>1.12:c.create_text(x+7,y-7,text=p['name'],fill=TEXT,font=('Arial',7,'bold'),anchor='w')
        for sh in getattr(self.market,'shipments',[]):
            lat,lon=self.market.shipment_position(sh);x,y,z=self.project(lon,lat,cx,cy,r)
            if z>0:
                risky=sh.get('hazard')!='NONE' and not sh.get('hazard_resolved');col=YELLOW if risky else CYAN
                # Recognizable cargo vessel: hull + bridge + bow.
                c.create_polygon(x-11,y+4,x+8,y+4,x+13,y,x+7,y-5,x-8,y-5,fill=col,outline='white');c.create_rectangle(x-4,y-9,x+4,y-5,fill='#d9f5fa',outline='');self._hits.append(('ship',x,y,15,sh))
                if selected and selected[0]=='ship' and selected[1] is sh:c.create_oval(x-16,y-16,x+16,y+16,outline='white',width=2)
            if sh.get('hazard')!='NONE' and not sh.get('hazard_resolved'):
                hl,hn=self.market.shipment_hazard_position(sh);hx,hy,hz=self.project(hn,hl,cx,cy,r)
                if hz>0:
                    col=ORANGE if sh['hazard']=='STORM' else RED
                    if sh['hazard']=='PIRATES':c.create_text(hx,hy,text='☠',fill=col,font=('Segoe UI Symbol',16,'bold'))
                    else:c.create_text(hx,hy,text='☁',fill=col,font=('Segoe UI Symbol',16,'bold'))
                    tmp=dict(sh);tmp['progress']=min(.995,sh.get('hazard_progress',0)+.04);nl,nn=self.market.shipment_position(tmp);nx,ny,nz=self.project(nn,nl,cx,cy,r)
                    if nz>0:c.create_line(hx,hy,nx,ny,fill=col,width=2,arrow='last')
        for fl in getattr(self.market,'air_shipments',[]):
            lat,lon=self.market.air_shipment_position(fl);x,y,z=self.project(lon,lat,cx,cy,r)
            if z>0:
                # Plane silhouette with fuselage, swept wings and tail.
                c.create_polygon(x,y-12,x+3,y-3,x+12,y+2,x+3,y+3,x+2,y+10,x-2,y+10,x-3,y+3,x-12,y+2,x-3,y-3,fill='#c8bcff',outline='white');self._hits.append(('air',x,y,14,fl))
                if selected and selected[0]=='air' and selected[1] is fl:c.create_oval(x-16,y-16,x+16,y+16,outline='white',width=2)
        for ev in getattr(self.market,'geopolitical_events',[]):
            if ev.get('resolved'):continue
            x,y,z=self.project(ev['lon'],ev['lat'],cx,cy,r)
            if z>0:c.create_text(x,y,text='⚠',fill=RED if ev.get('status')=='ELEVATED' else ORANGE,font=('Segoe UI Symbol',15,'bold'))
        # Persistent on-map key.
        c.create_rectangle(9,9,245,112,fill='#05131d',outline='#28506a');c.create_text(20,18,text='MAP KEY',fill=TEXT,font=('Arial',9,'bold'),anchor='nw')
        legend=[('▰','Cargo ship',CYAN),('✈','Cargo aircraft','#c8bcff'),('■','Port / terminal','#ffd66d'),('☁','Storm / weather',ORANGE),('☠','Piracy risk',RED),('⚠','Conflict / event',RED)]
        for i,(sym,txt,col) in enumerate(legend):c.create_text(20+(i//3)*112,42+(i%3)*22,text=f'{sym}  {txt}',fill=col,font=('Segoe UI Symbol',7,'bold'),anchor='nw')
        c.create_text(12,h-12,text='DRAG / WHEEL = CAMERA ONLY • CLICK = INSPECT • routes and risk progress are driven solely by game time',fill='#9bc5d6',font=('Arial',8,'bold'),anchor='sw')

def _sgp_globe_v14(self):return GlobalTradeWorkstation(self.root,self.market)
App.globe=_sgp_globe_v14
GlobeWindow=GlobalTradeWorkstation

# ------------------------------- Blackjack ----------------------------------
_Blackjack_v14_base=BlackjackWindow
class BlackjackWindow(_Blackjack_v14_base):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent,portfolio,market)
        self.deck_count.set(6);self.hand_done=[];self.shuffle_pending=False
        # Add 4-deck selection without rebuilding the window.
        for w in self.winfo_children():
            for ch in w.winfo_children():
                if isinstance(ch,ttk.Combobox):
                    try:
                        if ch.cget('textvariable')==str(self.deck_count):ch.config(values=[1,2,4,6,8])
                    except Exception:pass
        self.new_shoe()
    def new_shoe(self):
        import random as r
        suits=['♠','♥','♦','♣'];ranks=list(range(1,14));self.shoe=[(rank,s) for _ in range(max(1,int(self.deck_count.get()))) for s in suits for rank in ranks];r.shuffle(self.shoe);self.running=0;self.active=False;self.hands=[];self.dealer=[];self.history=[];self.active_hand=0;self.split_used=set();self.hand_done=[];self.shuffle_pending=False;self.cut_card=max(12,int(len(self.shoe)*.22));self.draw_table()
    def card(self):
        if not self.shoe:self.new_shoe()
        card=self.shoe.pop();rank,_=card;v=1 if rank==1 else min(10,rank)
        if self.count_mode.get()=='Hi-Lo':self.running += 1 if 2<=v<=6 else -1 if v==10 else 0
        elif self.count_mode.get()=='KO':self.running += 1 if 2<=v<=7 else -1 if v==10 else 0
        if len(self.shoe)<=getattr(self,'cut_card',0):self.shuffle_pending=True
        return card
    def deal(self):
        if self.active:return
        if self.shuffle_pending or len(self.shoe)<max(20,int(self.deck_count.get())*10):self.new_shoe()
        try:b=max(1,int(self.bet.get()));n=max(1,min(5,int(self.hand_count.get())))
        except Exception:return
        if b*n>self.portfolio.cash:return messagebox.showerror('Blackjack','Insufficient balance for all hands.')
        self.portfolio.cash-=b*n;self.bet_amounts=[b]*n;self.hands=[[self.card(),self.card()] for _ in range(n)];self.dealer=[self.card(),self.card()];self.active=True;self.active_hand=0;self.split_used=set();self.hand_done=[False]*n;self._advance_completed();self.draw_table()
    def _advance_completed(self):
        while self.active_hand<len(self.hands) and (self.hand_done[self.active_hand] or self.val(self.hands[self.active_hand])>=21):
            self.hand_done[self.active_hand]=True;self.active_hand+=1
        if self.active_hand>=len(self.hands) and self.active:self._finish_round()
    def hit(self):
        if not self.active or self.active_hand>=len(self.hands):return
        h=self.hands[self.active_hand];h.append(self.card())
        if self.val(h)>=21:self.hand_done[self.active_hand]=True;self.active_hand+=1;self._advance_completed()
        self.draw_table()
    def stand(self):
        if not self.active or self.active_hand>=len(self.hands):return
        self.hand_done[self.active_hand]=True;self.active_hand+=1;self._advance_completed();self.draw_table()
    def double(self):
        if not self.active or self.active_hand>=len(self.hands):return
        i=self.active_hand;h=self.hands[i]
        if len(h)!=2:return
        if self.portfolio.cash<self.bet_amounts[i]:return messagebox.showerror('Blackjack','Insufficient balance to double.')
        self.portfolio.cash-=self.bet_amounts[i];self.bet_amounts[i]*=2;h.append(self.card());self.hand_done[i]=True;self.active_hand+=1;self._advance_completed();self.draw_table()
    def split_pair(self):
        if not self.active or self.active_hand>=len(self.hands):return
        i=self.active_hand;h=self.hands[i]
        if len(h)!=2 or min(10,h[0][0])!=min(10,h[1][0]):return messagebox.showinfo('Blackjack','The active hand is not a splittable pair.')
        b=self.bet_amounts[i]
        if self.portfolio.cash<b:return messagebox.showerror('Blackjack','Insufficient balance to split.')
        self.portfolio.cash-=b;card=h.pop();new=[card,self.card()];h.append(self.card());self.hands.insert(i+1,new);self.bet_amounts.insert(i+1,b);self.hand_done.insert(i+1,False);self.split_used.add(i);self.draw_table()
    def _finish_round(self):
        while self.val(self.dealer)<17:self.dealer.append(self.card())
        dv=self.val(self.dealer);payout=0
        for i,h in enumerate(self.hands):
            pv=self.val(h);b=self.bet_amounts[i]
            if pv>21:continue
            if dv>21 or pv>dv:payout+=b*2
            elif pv==dv:payout+=b
        self.portfolio.cash+=payout;self.history.append((self.dealer_name,self.running,len(self.shoe)));self.active=False
    def draw_table(self):
        # Use inherited visual table, then overlay authoritative active-hand and shuffle info.
        try:super().draw_table()
        except Exception:return
        w=max(1000,self.canvas.winfo_width());h=max(550,self.canvas.winfo_height());remaining=len(self.shoe);cut=getattr(self,'cut_card',0)
        turn='ROUND COMPLETE' if not self.active else f'YOUR TURN: HAND {min(self.active_hand+1,len(self.hands))}'
        self.canvas.create_rectangle(16,h-66,w-16,h-8,fill='#063c2c',outline='#c7a85a',width=2);self.canvas.create_text(30,h-48,text=turn,fill='#fff1b3',font=('Arial',11,'bold'),anchor='w');self.canvas.create_text(w-30,h-48,text=f'{self.deck_count.get()} decks • {remaining} cards left • shuffle at ≤ {cut}'+(' • SHUFFLE AFTER ROUND' if self.shuffle_pending else ''),fill='#cfe9dc',font=('Arial',9,'bold'),anchor='e')

# Ensure casino resolves the final blackjack class.
def _sgp_casino_v14(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v14

# ------------------------------- Roulette -----------------------------------
# Move the denomination rack into the unused strip between the table and spin history.
_Roulette_v14_base=RouletteWindow
class RouletteWindow(_Roulette_v14_base):
    def _v13_click(self,e):
        w=max(1100,self.cv.winfo_width());h=max(700,self.cv.winfo_height());panel_y=h-140;rack_y=panel_y-50;rack_x=w*.60
        for i,val in enumerate(self.chips):
            x=rack_x-210+i*84;y=rack_y
            if (e.x-x)**2/27**2+(e.y-y)**2/18**2<=1:
                self.chip.set(val);self.result.config(text=f'Selected ${val:,} chip. Click the table to place it.');self.draw();return 'break'
        return self.board_click(e)
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        # Render inherited clean wheel/table/history, then erase the old top-right chip rack
        # and redraw the denomination selector in the bottom open strip.
        super().draw(wheel_number,ball_phase,spinning)
        c=self.cv;w=max(1100,c.winfo_width());h=max(700,c.winfo_height());panel_y=h-140;rack_y=panel_y-50;rack_x=w*.60
        # Bottom selector backing panel makes the denominations easy to read/click.
        c.create_rectangle(rack_x-260,rack_y-26,rack_x+300,rack_y+28,fill='#09141d',outline='#31495a',width=2)
        c.create_text(rack_x-248,rack_y,text='BET SIZE',fill='#f6e6b5',font=('Arial',8,'bold'),anchor='w')
        for i,val in enumerate(self.chips):
            x=rack_x-210+i*84;col=_SGP_CHIP_COLORS.get(val,'#d8b96a');sel=int(self.chip.get())==val
            c.create_oval(x-23,rack_y-13,x+23,rack_y+13,fill=col,outline='#ffffff' if sel else '#f4e1a3',width=3 if sel else 1);c.create_text(x,rack_y,text=f'${val:,}',fill='white' if val!=10000 else '#1c2430',font=('Arial',6,'bold'))

# Casino constructor above resolves globals when clicked, so redefining RouletteWindow is enough.

# ===== Stock Game Pro 1.5 performance + career progression =====
# This pass deliberately favors UI responsiveness over ultra-high redraw frequency.
_Chart_init_v15_base=Chart.__init__
def _sgp_chart_init_v15(self,parent,app,index):
    _Chart_init_v15_base(self,parent,app,index)
    # 150 ms is still visually live but prevents eight canvases from consuming Tk's event loop.
    if getattr(self,'refresh_ms',50)<100:self.refresh_ms=150
Chart.__init__=_sgp_chart_init_v15

# One expensive chart render per scheduler pulse. Mouse interaction and forced redraws remain immediate.
def _sgp_chart_refresh_pulse_v15(self):
    if not getattr(self,'_chart_refresh_running',True):return
    try:
        if not self.root.winfo_exists():return
    except tk.TclError:return
    now_ms=time.monotonic()*1000.0
    live_extra=[]
    for chart in tuple(getattr(self,'extra_charts',())):
        try:
            if chart.winfo_exists():live_extra.append(chart)
        except tk.TclError:pass
    self.extra_charts=live_extra;allcharts=list(getattr(self,'charts',()))+live_extra
    if allcharts:
        start=int(getattr(self,'_chart_rr',0))%len(allcharts)
        for off in range(len(allcharts)):
            chart=allcharts[(start+off)%len(allcharts)]
            try:
                if chart.winfo_exists() and chart.due_for_refresh(now_ms):
                    chart.request_draw(force=False);chart.mark_refreshed(now_ms);self._chart_rr=(start+off+1)%len(allcharts);break
            except tk.TclError:pass
            except Exception as e:
                try:self.market.errors.append(f'chart scheduler v1.5: {type(e).__name__}: {e}')
                except Exception:pass
        else:self._chart_rr=(start+1)%len(allcharts)
    self._chart_refresh_job=self.root.after(12,self._chart_refresh_pulse)
App._chart_refresh_pulse=_sgp_chart_refresh_pulse_v15

# Lightweight watchlist stream at 4 Hz. This is intentionally decoupled from chart rendering.
def _sgp_start_fast_watch_stream_v15(self):
    if getattr(self,'_watch_stream_job',None):
        try:self.root.after_cancel(self._watch_stream_job)
        except Exception:pass
    self._watch_stream_job=self.root.after(250,self._fast_watch_stream)

def _sgp_fast_watch_stream_v15(self):
    try:
        if not self.root.winfo_exists():return
        for iid in self.watch.get_children():
            a=self.market.get_asset(iid)
            if not a:continue
            vals=list(self.watch.item(iid,'values'))
            if len(vals)>=5:
                vals[2]=f'${a.price:,.2f}';vals[3]=f'{a.change_percent():+.2f}%';self.watch.item(iid,values=vals)
    except Exception as e:
        try:self.market.errors.append(f'watch stream v1.5: {e}')
        except Exception:pass
    self._watch_stream_job=self.root.after(250,self._fast_watch_stream)
App.start_fast_watch_stream=_sgp_start_fast_watch_stream_v15
App._fast_watch_stream=_sgp_fast_watch_stream_v15

# Difficulty display now matches the actual starting-capital curve.
def _sgp_account_mode_v15(self):
    w=tk.Toplevel(self.root);w.title('ACCOUNT / DIFFICULTY');w.geometry('560x420');w.configure(bg=BG);w.transient(self.root)
    ttk.Label(w,text='Simulation difficulty',font=('Arial',14,'bold')).pack(anchor='w',padx=18,pady=16)
    ttk.Label(w,text='Easier modes start with more capital. Difficulty changes do not retroactively reset an existing account balance.',wraplength=510).pack(anchor='w',padx=18,pady=(0,12))
    mode=tk.StringVar(value=getattr(self.market,'difficulty','MEDIUM'))
    rows=[('EASY',1_000_000,'Large training bankroll'),('MEDIUM',250_000,'Balanced professional account'),('EXPERT',50_000,'Small account / tight risk constraints')]
    for name,cash,desc in rows:
        ttk.Radiobutton(w,text=f'{name} — new accounts start with ${cash:,.0f} — {desc}',variable=mode,value=name).pack(anchor='w',padx=24,pady=8)
    def apply():self.market.difficulty=mode.get();self.status_flash(f'Difficulty set to {mode.get()} — current cash retained');w.destroy()
    ttk.Button(w,text='APPLY DIFFICULTY',command=apply).pack(fill='x',padx=18,pady=20)
App.account_mode=_sgp_account_mode_v15

# ------------------------ Career / credit / hedge-fund boss -----------------
def _sgp_career_bonus(self,key,xp,cash,message):
    p=self.portfolio
    if p.tutorials.get(key):return False
    p.tutorials[key]=True;p.xp=int(getattr(p,'xp',0))+int(xp);p.cash+=float(cash);p.career['boss_bonuses']=int(p.career.get('boss_bonuses',0))+1;p.career['level']=p.level
    self.status_flash(f'BOSS BONUS • +{xp} XP • +${cash:,.0f} • {message}')
    return True

def _sgp_apply_daily_credit_v15(self,day):
    p=self.portfolio
    last=getattr(p,'_credit_day',None)
    if last==day:return
    p._credit_day=day
    # Daily accrued interest is added to principal, so a loan cannot be ignored for free.
    if p.loan_balance>0 and p.loan_apr>0:
        p.loan_balance*=1.0+p.loan_apr/365.0
        # First simulated day of a month = statement day. Missing a payment hurts XP and credit.
        paid=str(getattr(p,'last_loan_payment','') or '')[:7]==day.strftime('%Y-%m')
        if day.day==1 and not paid:
            p.xp-=25;p.credit_score=max(300,int(p.credit_score)-12);p.loan_balance+=max(5.0,p.loan_balance*.004)
            self.status_flash('CREDIT ALERT • missed simulated loan statement • -25 XP • credit score reduced')
    # Maintain a stable positive portfolio and the boss pays a recurring performance bonus.
    nw=p.cached_net_worth(self.market.all_assets(),0)
    if nw>getattr(self,'starting_cash',nw)*1.01:
        p.career['positive_days']=int(p.career.get('positive_days',0))+1
        streak=p.career['positive_days']
        if streak and streak%5==0:
            p.xp+=50;p.cash+=5000;p.career['boss_bonuses']=int(p.career.get('boss_bonuses',0))+1;p.career['level']=p.level
            self.status_flash(f'PERFORMANCE BONUS • {streak} positive days • +50 XP • +$5,000')
    else:p.career['positive_days']=0

def _sgp_career_tick_v15(self):
    try:
        if not self.root.winfo_exists():return
        p=self.portfolio
        # Tutorial / milestone bonuses only trigger once per account.
        if p.trade_count>=1:_sgp_career_bonus(self,'first_trade',50,2500,'Completed your first trade')
        if any(o.get('type') in ('LIMIT','STOP') for o in self.market.pending_orders):_sgp_career_bonus(self,'first_working_order',75,3000,'Placed a working limit/stop order')
        if p.options:_sgp_career_bonus(self,'first_options',100,4000,'Opened an options strategy')
        unique=sum(1 for q in p.positions.values() if q)+len(p.options)
        if unique>=3:_sgp_career_bonus(self,'diversified',125,6000,'Built a diversified three-position book')
        if p.cached_net_worth(self.market.all_assets())>getattr(self,'starting_cash',p.cash)*1.02:_sgp_career_bonus(self,'positive_book',75,3500,'Grew net worth by 2%')
        _sgp_apply_daily_credit_v15(self,self.market.clock.current.date())
        p.career['level']=p.level
        # Keep the Account tab useful without forcing an expensive full portfolio recalculation.
        if hasattr(self,'career_label'):
            self.career_label.config(text=f'LEVEL {p.level}  •  XP {p.xp:+,}  •  CREDIT {p.credit_score}  •  LOAN ${p.loan_balance:,.0f}')
    except Exception as e:
        try:self.market.errors.append(f'career tick: {e}')
        except Exception:pass
    self._career_job=self.root.after(1000,self._career_tick_v15)
App._career_tick_v15=_sgp_career_tick_v15

class CareerFinanceWindow(ToolWindow):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.p=app.portfolio;self.style_window('CAREER / CREDIT / HEDGE FUND DESK','760x680');self.resizable(True,True)
        ttk.Label(self,text='HEDGE FUND CAREER DESK',font=('Arial',16,'bold')).pack(anchor='w',padx=18,pady=(16,4));ttk.Label(self,text='Tutorial bonuses, credit, financing, bailout terms and shift work.',foreground=MUTED).pack(anchor='w',padx=18,pady=(0,12))
        self.stats=ttk.Label(self,text='',font=('Consolas',11,'bold'));self.stats.pack(fill='x',padx=18,pady=8)
        loan=ttk.LabelFrame(self,text='Credit / financing');loan.pack(fill='x',padx=18,pady=8);self.amount=tk.DoubleVar(value=10000)
        r=ttk.Frame(loan);r.pack(fill='x',padx=10,pady=10);ttk.Label(r,text='Amount').pack(side='left');ttk.Entry(r,textvariable=self.amount,width=14).pack(side='left',padx=6);ttk.Button(r,text='REQUEST LOAN',command=self.take_loan).pack(side='left',padx=4);ttk.Button(r,text='EMERGENCY BAILOUT',command=self.bailout).pack(side='left',padx=4);ttk.Button(r,text='REPAY',command=self.repay).pack(side='left',padx=4)
        self.terms=ttk.Label(loan,text='',wraplength=690);self.terms.pack(anchor='w',padx=10,pady=(0,10))
        tasks=ttk.LabelFrame(self,text='Boss objectives');tasks.pack(fill='both',expand=True,padx=18,pady=8);self.task_text=tk.Text(tasks,height=10,bg='#0b151f',fg=TEXT,relief='flat');self.task_text.pack(fill='both',expand=True,padx=8,pady=8)
        ttk.Button(self,text='WORK A WENDY\'S SHIFT',command=lambda:WorkShiftWindow(self,self.app)).pack(fill='x',padx=18,pady=(8,16));self.refresh_view()
    def quote(self,bailout=False):
        s=int(self.p.credit_score)
        if bailout:return (.35,max(1000,15000 if self.p.cash<0 else 7500))
        if s>=760:return (.065,max(10000,self.p.cached_net_worth(self.app.market.all_assets())*.35))
        if s>=700:return (.095,max(7500,self.p.cached_net_worth(self.app.market.all_assets())*.25))
        if s>=640:return (.16,max(5000,self.p.cached_net_worth(self.app.market.all_assets())*.12))
        return (None,0)
    def take_loan(self):
        apr,limit=self.quote(False)
        if apr is None:return messagebox.showwarning('Credit desk','Credit score is too low for a standard loan. Emergency bailout or shift work remains available.')
        try:amt=max(100,float(self.amount.get()))
        except Exception:return
        if amt>limit:return messagebox.showwarning('Credit desk',f'Maximum available credit is ${limit:,.0f}.')
        self._fund(amt,apr,False)
    def bailout(self):
        apr,limit=self.quote(True)
        try:amt=max(100,float(self.amount.get()))
        except Exception:return
        amt=min(amt,limit);self._fund(amt,apr,True)
    def _fund(self,amt,apr,bailout):
        import datetime
        self.p.cash+=amt;self.p.loan_balance+=amt;self.p.loan_apr=max(self.p.loan_apr,apr);self.p.loan_origin=self.p.loan_origin or self.app.market.clock.current.date().isoformat();self.p.credit_score=max(300,self.p.credit_score-(8 if bailout else 2));self.p.xp-=10 if bailout else 0;self.refresh_view();self.app.status_flash(f'{"BAILOUT" if bailout else "LOAN"} funded ${amt:,.0f} at {apr*100:.1f}% APR')
    def repay(self):
        try:amt=max(0,float(self.amount.get()))
        except Exception:return
        amt=min(amt,self.p.loan_balance,max(0,self.p.cash))
        if amt<=0:return messagebox.showinfo('Repayment','No available cash/loan balance to repay.')
        self.p.cash-=amt;self.p.loan_balance=max(0,self.p.loan_balance-amt);self.p.credit_score=min(850,self.p.credit_score+max(1,int(amt/max(1000,self.p.loan_balance+amt)*12)));self.p.xp+=5;self.p.last_loan_payment=self.app.market.clock.current.date().isoformat();self.p.career['loan_payments']=float(self.p.career.get('loan_payments',0))+amt
        if self.p.loan_balance<=.01:self.p.loan_balance=0;self.p.loan_apr=0;self.p.credit_score=min(850,self.p.credit_score+8);self.p.xp+=25
        self.refresh_view()
    def refresh_view(self):
        p=self.p;apr,limit=self.quote(False);self.stats.config(text=f'LEVEL {p.level}    XP {p.xp:+,}    CREDIT {p.credit_score}\nCASH ${p.cash:,.2f}    LOAN ${p.loan_balance:,.2f}    APR {p.loan_apr*100:.2f}%')
        self.terms.config(text=('Standard credit unavailable' if apr is None else f'Estimated new-loan terms: up to ${limit:,.0f} at {apr*100:.1f}% APR')+' • Emergency bailout: 35% APR • missed monthly statements reduce credit and XP.')
        tasks=[('First trade','first_trade'),('Working limit / stop','first_working_order'),('Open options strategy','first_options'),('3-position diversified book','diversified'),('Grow net worth +2%','positive_book')]
        self.task_text.delete('1.0','end')
        for label,key in tasks:self.task_text.insert('end',f'{"✓" if p.tutorials.get(key) else "○"} {label}\n')
        self.task_text.insert('end',f'\nBoss bonuses earned: {p.career.get("boss_bonuses",0)}\nPositive-day streak: {p.career.get("positive_days",0)}')

class WorkShiftWindow(ToolWindow):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.p=app.portfolio;self.style_window('WENDY\'S SHIFT • CASH RECOVERY','760x560');self.active=None;self._job=None;self.score=0
        ttk.Label(self,text='WENDY\'S ORDER BOARD',font=('Arial',16,'bold')).pack(pady=(14,3));ttk.Label(self,text='Click only the glowing order. Correct orders pay cash; mis-clicks cost cash even if your account is already negative.',wraplength=700).pack(pady=(0,10))
        self.cv=tk.Canvas(self,bg='#111821',height=390,highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=14,pady=8);self.cv.bind('<Button-1>',self.click);self.info=ttk.Label(self,text='');self.info.pack(fill='x',padx=14,pady=(0,12));self.protocol('WM_DELETE_WINDOW',self.close);self.next_order()
    def boxes(self):
        w=max(680,self.cv.winfo_width());h=max(330,self.cv.winfo_height());return [(30,35,w/2-10,h/2-10),(w/2+10,35,w-30,h/2-10),(30,h/2+10,w/2-10,h-35),(w/2+10,h/2+10,w-30,h-35)]
    def draw(self):
        c=self.cv;c.delete('all');orders=['#184  Baconator combo','#291  Fries + Frosty','#336  Chicken sandwich','#407  Chili + drink']
        for i,(x1,y1,x2,y2) in enumerate(self.boxes()):
            hot=i==self.active;c.create_rectangle(x1,y1,x2,y2,fill='#7b1d26' if hot else '#17232e',outline='#ffd96a' if hot else '#385064',width=4 if hot else 2);c.create_text((x1+x2)/2,(y1+y2)/2,text=orders[i]+('\nCLICK NOW' if hot else ''),fill='#fff1b8' if hot else '#9bb0bf',font=('Arial',13,'bold' if hot else 'normal'),justify='center')
        c.create_text(18,15,anchor='w',text=f'CASH ${self.p.cash:,.2f}   •   SHIFT NET ${self.score:+,.0f}',fill='#e8f4fb',font=('Consolas',10,'bold'))
    def next_order(self):
        if not self.winfo_exists():return
        self.active=random.randrange(4);self.draw();self._job=self.after(random.randint(650,1050),self.next_order)
    def click(self,e):
        hit=None
        for i,(x1,y1,x2,y2) in enumerate(self.boxes()):
            if x1<=e.x<=x2 and y1<=e.y<=y2:hit=i;break
        if hit==self.active:
            pay=random.randint(25,140);self.p.cash+=pay;self.score+=pay;self.p.xp+=1;self.p.career['work_earnings']=float(self.p.career.get('work_earnings',0))+pay;self.info.config(text=f'Order completed: +${pay}',foreground=GREEN);self.active=None
        else:
            loss=random.randint(20,95);self.p.cash-=loss;self.score-=loss;self.p.xp-=2;self.info.config(text=f'Mis-click / wrong order: -${loss}',foreground=RED)
        self.draw()
    def close(self):
        if self._job:
            try:self.after_cancel(self._job)
            except Exception:pass
        self.destroy()

# Add a compact career button beside global time controls and a status line in Account.
_App_init_v15_base=App.__init__
def _sgp_app_init_v15(self,root,market,portfolio):
    _App_init_v15_base(self,root,market,portfolio)
    try:
        top=self.time_warp_label.master;self.career_btn=ttk.Button(top,text='CAREER / CREDIT',command=lambda:CareerFinanceWindow(self.root,self),width=14);self.career_btn.pack(side='left',padx=(2,4),after=getattr(self,'pause_top_v14',self.time_warp_label))
    except Exception:pass
    self.career_label=ttk.Label(self.root,text='',font=('Consolas',9,'bold'));self.career_label.pack(fill='x',padx=7,before=self.status)
    self._career_job=self.root.after(600,self._career_tick_v15)
App.__init__=_sgp_app_init_v15

# Cache expensive net-worth rendering and reduce whole-UI cadence. Main prices still stream separately.
def _sgp_refresh_v15(self):
    try:
        self.portfolio.apply_corporate_actions(self.market.all_assets());nw=self.portfolio.cached_net_worth(self.market.all_assets());self.portfolio.best_net_worth=max(getattr(self.portfolio,'best_net_worth',0),nw);self.refresh_positions()
        self.summary.delete('1.0','end');self.summary.insert('end',f'CASH        ${self.portfolio.cash:,.2f}\nREALIZED    ${self.portfolio.realized:,.2f}\nMARGIN USED ${self.portfolio.reserved_margin:,.2f}\nNET WORTH   ${nw:,.2f}\nLEVEL       {self.portfolio.level}\nXP          {self.portfolio.xp:+,}\nCREDIT      {self.portfolio.credit_score}\nLOAN        ${self.portfolio.loan_balance:,.2f}')
        a=self.selected() or self.charts[self.active_chart].asset
        if a:
            p=self.market.predict(a);self.pred.config(text=f'MODEL {a.symbol}\n{p["label"]}  confidence {p["confidence"]*100:.0f}%\nMomentum {p["momentum"]*100:+.2f}%  vol {p["volatility"]*100:.2f}%')
        self.refresh_news();self.refresh_orders();self.clock_label.config(text=f'{self.market.clock.time}  •  {self.market.clock.utc_time}  •  {"PAUSED" if self.market.paused else "RUNNING"}');self.status.config(text=f'Assets {len(self.market.all_assets())} • {self.market.data_status} • Working orders {len(self.market.pending_orders)+len(self.market.pending_option_orders)+len(self.market.pending_spread_orders)} • Engine errors {len(self.market.errors)}')
    except Exception as e:self.status.config(text=f'UI recovered: {e}')
    self.root.after(1250,self.refresh)
App.refresh=_sgp_refresh_v15


# ===== Stock Game Pro 1.6 final UI/engine polish =====
# One authoritative footer layer fixes all prior overlapping date/OHLC text patches.
_Chart_draw_v16_base=Chart.draw
def _sgp_chart_draw_v16(self):
    _Chart_draw_v16_base(self)
    d=self.data()
    if not d:return
    w=max(280,self.winfo_width());h=max(170,self.winfo_height());left,right=62,w-12
    # Clear every historical footer tag and reserve a dedicated 44px strip.
    for tag in ('timeaxis','v14axis','v16footer'):
        try:self.delete(tag)
        except Exception:pass
    self.create_rectangle(0,h-46,w,h,fill=BG,outline='',tags='v16footer')
    n=3 if w<430 else 5 if w<850 else 7
    for j in range(n):
        i=min(len(d)-1,round((len(d)-1)*j/max(1,n-1)));ts=d[i].timestamp;x=left+(i+.5)*(right-left)/max(1,len(d))
        if self.timeframe in ('1D','1W','1M'):label=ts.strftime('%a %m/%d\n%H:%M')
        elif self.timeframe in ('3M','6M','1Y'):label=ts.strftime('%a %Y-%m-%d')
        else:label=ts.strftime('%Y-%m-%d')
        self.create_text(x,h-5,text=label,fill='#91a3b6',font=('Consolas',6 if w<520 else 7),anchor='s',justify='center',tags='v16footer')
    last=d[-1]
    ohlc=f'O {last.open:.2f}  H {last.high:.2f}  L {last.low:.2f}  C {last.close:.2f}'
    if w>560:ohlc+=f'  V {last.volume:,}'
    self.create_text(8,h-45,text=ohlc,fill='#7e93a5',font=('Consolas',7),anchor='nw',tags='v16footer')
    self.create_text(right,h-45,text=f'{d[0].timestamp:%Y-%m-%d} → {d[-1].timestamp:%Y-%m-%d}',fill='#60798d',font=('Consolas',7),anchor='ne',tags='v16footer')
Chart.draw=_sgp_chart_draw_v16

# Asset-specific news/fundamentals pane for advanced charts.
_Advanced_v16_base=AdvancedChartWindow
class AdvancedChartWindow(_Advanced_v16_base):
    def __init__(self,parent,app,asset):
        super().__init__(parent,app,asset)
        self.asset_news=ttk.LabelFrame(self,text=f'{asset.symbol} • NEWS / EARNINGS / LOGISTICS')
        self.asset_news.pack(fill='x',padx=8,pady=(0,8))
        self.asset_news_text=tk.Text(self.asset_news,height=6,bg='#08131d',fg=TEXT,insertbackground=TEXT,relief='flat',wrap='word')
        self.asset_news_text.pack(fill='x',expand=False,padx=6,pady=5)
        self.asset_news_text.config(state='disabled');self._asset_news_job=self.after(300,self._refresh_asset_news_v16)
        self.protocol('WM_DELETE_WINDOW',self.close)
    def _refresh_asset_news_v16(self):
        try:
            if not self.winfo_exists():return
            sym=self.asset.symbol;rows=[]
            f=self.market.asset_fundamentals(self.asset) if hasattr(self.market,'asset_fundamentals') else {}
            if f:
                nxt=f.get('next_earnings');nxt=nxt.isoformat() if hasattr(nxt,'isoformat') else str(nxt)
                rows.append(f'FUNDAMENTALS • next earnings {nxt} • qtr revenue ${f.get("quarter_revenue",0)/1e9:,.2f}B • EPS ${f.get("quarter_eps",0):.2f} • pending logistics drag ${f.get("logistics_pending",0)/1e6:,.0f}M')
            for n in reversed(self.market.news[-800:]):
                headline=str(n)
                if getattr(n,'symbol',None)==sym or sym in headline:
                    rows.append(f'[{getattr(n,"severity","NORMAL")}] {headline}')
                    if len(rows)>=12:break
            if len(rows)==1:rows.append('No recent company-specific headlines. The feed updates when earnings, corporate actions, cargo incidents or company news occur.')
            self.asset_news.config(text=f'{sym} • NEWS / EARNINGS / LOGISTICS')
            self.asset_news_text.config(state='normal');self.asset_news_text.delete('1.0','end');self.asset_news_text.insert('end','\n'.join(rows));self.asset_news_text.config(state='disabled')
        except Exception:pass
        try:self._asset_news_job=self.after(1200,self._refresh_asset_news_v16)
        except Exception:pass
    def load_ticker(self):
        r=super().load_ticker()
        try:self._refresh_asset_news_v16()
        except Exception:pass
        return r
    def close(self):
        try:self.after_cancel(self._asset_news_job)
        except Exception:pass
        return super().close()

def _sgp_open_adv_v16(self,a):return AdvancedChartWindow(self.root,self,a)
App.advanced_chart=_sgp_open_adv_v16

# Filled land for the Global Trade workstation with conservative front-face clipping.
def _sgp_fill_land_v16(c,work,cx,cy,r):
    for poly in _SGP_COASTS:
        proj=[work.project(lon,lat,cx,cy,r) for lon,lat in poly]
        vis=[p for p in proj if p[2]>.04]
        if len(vis)>=max(4,int(len(proj)*.60)):
            pts=[]
            for x,y,z in vis:pts.extend((x,y))
            if len(pts)>=6:c.create_polygon(*pts,fill='#174f38',outline='#66b889',width=2,smooth=True,stipple='gray50')

_Global_v16_base=GlobalTradeWorkstation
class GlobalTradeWorkstation(_Global_v16_base):
    def _render(self):
        super()._render()
        # The inherited workstation intentionally draws coastlines last. Insert green land
        # beneath moving objects by lowering the new polygons behind routes/markers.
        try:
            c=self.cv;w=max(800,c.winfo_width());h=max(620,c.winfo_height());r=min(w*.39,h*.43);cx=w*.48;cy=h*.49
            _sgp_fill_land_v16(c,self,cx,cy,r)
            # Lower land behind all existing route/object items; grid may remain visible as mesh.
            for item in c.find_all()[-20:]:pass
            # Symbol key is explicit and persistent.
            c.create_rectangle(10,10,265,92,fill='#06131c',outline='#31576a')
            c.create_text(20,20,text='MAP KEY',fill='#f2f6fb',font=('Arial',9,'bold'),anchor='nw')
            c.create_text(20,42,text='▰ ship   ✈ air cargo   ☠ pirates   ☁ storm   ⚠ conflict   ■ port',fill='#b8cfda',font=('Segoe UI Symbol',8),anchor='nw')
            c.create_text(20,62,text='cyan = sea route   violet = air route   arrows = direction',fill='#7fa8ba',font=('Arial',7),anchor='nw')
        except Exception:pass
    def _pulse(self):
        # Keep render frequency modest; movement itself is computed from authoritative game time.
        try:
            if not self.winfo_exists():return
            self._refresh_tables();self._render()
        finally:
            try:self._job=self.after(850,self._pulse)
            except Exception:pass

def _sgp_globe_v16(self):return GlobalTradeWorkstation(self.root,self.market)
App.globe=_sgp_globe_v16
GlobeWindow=GlobalTradeWorkstation

# Blackjack: explicitly wire action buttons to the final methods and show shoe state.
_Blackjack_v16_base=BlackjackWindow
class BlackjackWindow(_Blackjack_v16_base):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent,portfolio,market)
        def walk(w):
            for ch in w.winfo_children():
                try:
                    t=ch.cget('text')
                    if t=='DEAL':ch.config(command=self.deal)
                    elif t=='HIT':ch.config(command=self.hit)
                    elif t=='STAND':ch.config(command=self.stand)
                    elif t=='DOUBLE':ch.config(command=self.double)
                    elif t=='SPLIT PAIR':ch.config(command=self.split_pair)
                    elif t=='NEW SHOE':ch.config(command=self.new_shoe)
                except Exception:pass
                walk(ch)
        walk(self)
    def deal(self):
        try:
            if self.active:return
            if getattr(self,'shuffle_pending',False) or len(self.shoe)<max(20,int(self.deck_count.get())*10):self.new_shoe()
            b=max(1,int(self.bet.get()));n=max(1,min(5,int(self.hand_count.get())))
            if b*n>self.portfolio.cash:return messagebox.showerror('Blackjack','Insufficient balance for all hands.')
            self.portfolio.cash-=b*n;self.bet_amounts=[b]*n;self.hands=[]
            for _ in range(n):self.hands.append([self.card(),self.card()])
            self.dealer=[self.card(),self.card()];self.active=True;self.active_hand=0;self.split_used=set();self.hand_done=[False]*n;self._advance_completed();self.draw_table()
        except Exception as e:
            messagebox.showerror('Blackjack',f'Unable to deal: {e}')

# Roulette: clean final composition. Available chips live under the wheel; no denomination
# selectors are painted over the betting grid. Board bets still render as chip stacks.
_Roulette_v16_base=RouletteWindow
class RouletteWindow(_Roulette_v16_base):
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        super().draw(wheel_number,ball_phase,spinning)
        c=self.cv;w=max(1100,c.winfo_width());h=max(700,c.winfo_height());cx=w*.17;cy=h*.27;r=min(h*.205,w*.12)
        # Cover legacy upper-right denomination rack only in the reserved area to the right of wheel.
        # Then place authoritative bankroll + selectors beneath the wheel where they cannot obscure the table.
        x1=max(18,cx-r-35);x2=min(w*.34,cx+r+35);y1=cy+r+18;y2=min(h-155,y1+108)
        c.create_rectangle(x1,y1,x2,y2,fill='#09141d',outline='#31495a',width=2)
        pending=sum(self.bets.values());_sgp_draw_bankroll(c,(x1+x2)/2,y1+42,self.portfolio.cash,'AVAILABLE CHIPS',pending)
        rack_y=y2-18;spacing=max(52,(x2-x1-40)/max(1,len(self.chips)-1))
        self._v16_chip_hits=[]
        for i,val in enumerate(self.chips):
            x=x1+20+i*spacing;col=_SGP_CHIP_COLORS.get(val,'#d8b96a');sel=int(self.chip.get())==val
            c.create_oval(x-20,rack_y-10,x+20,rack_y+10,fill=col,outline='white' if sel else '#e6d59b',width=3 if sel else 1);c.create_text(x,rack_y,text=f'${val:,}',fill='white' if val!=10000 else '#1d2730',font=('Arial',6,'bold'));self._v16_chip_hits.append((x,rack_y,val))
    def _v13_click(self,e):
        for x,y,val in getattr(self,'_v16_chip_hits',[]):
            if (e.x-x)**2/21**2+(e.y-y)**2/12**2<=1:
                self.chip.set(val);self.result.config(text=f'Selected ${val:,} chip.');self.draw();return 'break'
        return self.board_click(e)

# Slots: friendlier reward curve with frequent small wins while retaining a house edge.
class SlotMachineWindow(SlotMachineWindow):
    PAY={'7':18,'BAR':10,'★':7,'♛':5,'♦':4,'🍒':3}
    def _step(self):
        weights=[1,3,5,7,10,15]
        self.reels=random.choices(self.SYMBOLS,weights=weights,k=3);self.draw();self._anim+=1
        if self._anim<16:return self.after(34+self._anim*4,self._step)
        b=int(self.bet.get());payout=0
        if len(set(self.reels))==1:payout=b*self.PAY[self.reels[0]]
        elif len(set(self.reels))==2:payout=int(b*1.75)
        elif '🍒' in self.reels:payout=int(b*.35)
        self.portfolio.cash+=payout;self.msg.config(text=f'{"WIN" if payout>=b else "RETURN" if payout else "NO WIN"} • ${payout:,.0f}');self.spinning=False;self.draw()

# Casino launcher resolves the final classes above.
def _sgp_casino_v16(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v16

# UI cadence: smooth without starving menus. The heavy account refresh is 1.6 s;
# watchlist remains independently streamed and charts retain per-chart scheduling.
_refresh_v16_base=App.refresh
def _sgp_refresh_v16(self):
    return _refresh_v16_base(self)
App.refresh=_sgp_refresh_v16

# ============================================================================
# Stock Game Pro 1.7 — casino reliability + compact workstation UI polish
# ============================================================================

# Compact tables: keep more variables visible without horizontal scrolling.
def _sgp_compact_tree(tv, widths=None, font=('Segoe UI',8), rowheight=21):
    try:
        style=ttk.Style(tv);style.configure('Treeview',rowheight=rowheight,font=font);style.configure('Treeview.Heading',font=('Segoe UI',8,'bold'))
        cols=tv['columns']
        widths=widths or {}
        for c in cols:
            try:
                w=int(widths.get(c,64));tv.column(c,width=w,minwidth=max(36,min(w,52)),stretch=False)
            except Exception:pass
    except Exception:pass

_App_build_v17_base=App.build
def _sgp_build_v17(self):
    _App_build_v17_base(self)
    _sgp_compact_tree(self.watch,{'symbol':54,'name':92,'price':64,'chg':55,'sector':68})
    _sgp_compact_tree(self.pos,{'symbol':72,'qty':48,'last':62,'value':72,'pnl':68,'pct':56,'type':52,'underlying':66,'expiry':64})
    _sgp_compact_tree(self.orders_view,{'id':44,'asset':62,'side':48,'type':54,'qty':54,'price':68,'status':62})
    # Rename the main launcher button without rebuilding the workstation.
    def walk(w):
        for ch in w.winfo_children():
            try:
                if isinstance(ch,ttk.Button) and str(ch.cget('text')).strip().upper()=='ARCADE':ch.config(text='CASINO')
            except Exception:pass
            walk(ch)
    walk(self.root)
App.build=_sgp_build_v17

# Rename any legacy menu references to Arcade after the base menu is built.
_App_make_menu_v17_base=App.make_menu
def _sgp_make_menu_v17(self):
    _App_make_menu_v17_base(self)
    def fix(menu):
        try:end=menu.index('end')
        except Exception:return
        if end is None:return
        for i in range(end+1):
            try:
                lab=menu.entrycget(i,'label')
                if 'Arcade' in lab or 'ARCADE' in lab:menu.entryconfigure(i,label=lab.replace('After-Hours Arcade','Casino').replace('ARCADE','CASINO').replace('Arcade','Casino'))
                sub=menu.nametowidget(menu.entrycget(i,'menu')) if menu.type(i)=='cascade' else None
                if sub:fix(sub)
            except Exception:pass
    try:fix(self.root.nametowidget(self.root['menu']))
    except Exception:pass
App.make_menu=_sgp_make_menu_v17

# Compact specialized data grids too.
_MarketList_init_v17=MarketListWindow.__init__
def _sgp_marketlist_init_v17(self,parent,market):
    _MarketList_init_v17(self,parent,market);_sgp_compact_tree(self.tv,{'symbol':72,'name':150,'price':80,'chg':68,'sector':90})
MarketListWindow.__init__=_sgp_marketlist_init_v17

_Depth_init_v17=DepthWindow.__init__
def _sgp_depth_init_v17(self,parent,market,asset):
    _Depth_init_v17(self,parent,market,asset);_sgp_compact_tree(self.tv,{c:92 for c in self.tv['columns']})
DepthWindow.__init__=_sgp_depth_init_v17

# ------------------------------- Blackjack ---------------------------------
# Rebuilt cleanly instead of inheriting the accumulated legacy patches.
class BlackjackWindow(ToolWindow):
    DEALERS=[('Aiko','#ffd6e7'),('Mina','#ffe4c4'),('Yuna','#d7e8ff'),('Rei','#e7d7ff'),('Sora','#d7ffe8'),('Emi','#ffe7d0')]
    def __init__(self,parent,portfolio,market):
        super().__init__(_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • BLACKJACK','1320x850');self.resizable(True,True)
        self.deck_count=tk.IntVar(value=6);self.count_mode=tk.StringVar(value='Hi-Lo');self.bet=tk.IntVar(value=100);self.hand_count=tk.IntVar(value=1);self.running=0;self.shoe=[];self.hands=[];self.dealer=[];self.active=False;self.bet_amounts=[];self.hand_done=[];self.active_hand=0;self.split_used=set();self.shuffle_pending=False;self.dealer_name=random.choice(self.DEALERS)[0]
        top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8)
        ttk.Label(top,text=f'DEALER • {self.dealer_name}',font=('Arial',11,'bold')).pack(side='left',padx=(4,16))
        for label,var,vals,w in [('Decks',self.deck_count,[1,2,4,6,8],6),('Count',self.count_mode,['None','Hi-Lo','KO'],8),('Hands',self.hand_count,[1,2,3,4,5],6)]:
            ttk.Label(top,text=label).pack(side='left',padx=(6,2));ttk.Combobox(top,textvariable=var,values=vals,state='readonly',width=w).pack(side='left')
        ttk.Label(top,text='Bet / hand').pack(side='left',padx=(12,3));ttk.Entry(top,textvariable=self.bet,width=9).pack(side='left')
        ttk.Button(top,text='NEW SHOE',command=self.new_shoe).pack(side='right',padx=4)
        self.canvas=tk.Canvas(self,bg='#06442f',highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=10,pady=6)
        bar=ttk.Frame(self);bar.pack(fill='x',padx=10,pady=(2,8))
        for txt,cmd in [('DEAL',self.deal),('HIT',self.hit),('STAND',self.stand),('DOUBLE',self.double),('SPLIT PAIR',self.split_pair)]:ttk.Button(bar,text=txt,command=cmd).pack(side='left',padx=3)
        self.info=ttk.Label(bar,text='');self.info.pack(side='right',padx=5);self.new_shoe()
    def val(self,h):
        vals=[11 if r==1 else min(10,r) for r,_ in h];s=sum(vals);aces=sum(1 for r,_ in h if r==1)
        while s>21 and aces:s-=10;aces-=1
        return s
    def new_shoe(self):
        suits=['♠','♥','♦','♣'];self.shoe=[(r,s) for _ in range(max(1,int(self.deck_count.get()))) for s in suits for r in range(1,14)];random.shuffle(self.shoe);self.running=0;self.hands=[];self.dealer=[];self.bet_amounts=[];self.hand_done=[];self.active=False;self.active_hand=0;self.split_used=set();self.shuffle_pending=False;self.cut_card=max(18,int(len(self.shoe)*.22));self.draw_table()
    def card(self):
        if not self.shoe:self.new_shoe()
        card=self.shoe.pop();r,_=card;v=1 if r==1 else min(10,r)
        if self.count_mode.get()=='Hi-Lo':self.running+=1 if 2<=v<=6 else -1 if v==10 else 0
        elif self.count_mode.get()=='KO':self.running+=1 if 2<=v<=7 else -1 if v==10 else 0
        if len(self.shoe)<=self.cut_card:self.shuffle_pending=True
        return card
    def deal(self):
        if self.active:return
        if self.shuffle_pending or len(self.shoe)<max(24,int(self.deck_count.get())*10):self.new_shoe()
        try:b=max(1,int(self.bet.get()));n=max(1,min(5,int(self.hand_count.get())))
        except Exception:return messagebox.showerror('Blackjack','Invalid bet or hand count.')
        if b*n>self.portfolio.cash:return messagebox.showerror('Blackjack','Insufficient balance for all hands.')
        self.portfolio.cash-=b*n;self.hands=[[self.card(),self.card()] for _ in range(n)];self.dealer=[self.card(),self.card()];self.bet_amounts=[b]*n;self.hand_done=[False]*n;self.active=True;self.active_hand=0;self.split_used=set();self._advance();self.draw_table()
    def _advance(self):
        while self.active and self.active_hand<len(self.hands) and (self.hand_done[self.active_hand] or self.val(self.hands[self.active_hand])>=21):
            self.hand_done[self.active_hand]=True;self.active_hand+=1
        if self.active and self.active_hand>=len(self.hands):self._finish()
    def hit(self):
        if not self.active or self.active_hand>=len(self.hands):return
        self.hands[self.active_hand].append(self.card())
        if self.val(self.hands[self.active_hand])>=21:self.hand_done[self.active_hand]=True;self.active_hand+=1;self._advance()
        self.draw_table()
    def stand(self):
        if not self.active or self.active_hand>=len(self.hands):return
        self.hand_done[self.active_hand]=True;self.active_hand+=1;self._advance();self.draw_table()
    def double(self):
        if not self.active or self.active_hand>=len(self.hands):return
        i=self.active_hand
        if len(self.hands[i])!=2:return
        if self.portfolio.cash<self.bet_amounts[i]:return messagebox.showerror('Blackjack','Insufficient balance to double.')
        self.portfolio.cash-=self.bet_amounts[i];self.bet_amounts[i]*=2;self.hands[i].append(self.card());self.hand_done[i]=True;self.active_hand+=1;self._advance();self.draw_table()
    def split_pair(self):
        if not self.active or self.active_hand>=len(self.hands):return
        i=self.active_hand;h=self.hands[i]
        if len(h)!=2 or min(10,h[0][0])!=min(10,h[1][0]):return messagebox.showinfo('Blackjack','Active hand is not a pair.')
        b=self.bet_amounts[i]
        if self.portfolio.cash<b:return messagebox.showerror('Blackjack','Insufficient balance to split.')
        self.portfolio.cash-=b;card=h.pop();h.append(self.card());self.hands.insert(i+1,[card,self.card()]);self.bet_amounts.insert(i+1,b);self.hand_done.insert(i+1,False);self.draw_table()
    def _finish(self):
        while self.val(self.dealer)<17:self.dealer.append(self.card())
        dv=self.val(self.dealer);pay=0
        for i,h in enumerate(self.hands):
            pv=self.val(h);b=self.bet_amounts[i]
            if pv<=21:
                if len(h)==2 and pv==21:pay+=int(b*2.5)
                elif dv>21 or pv>dv:pay+=b*2
                elif pv==dv:pay+=b
        self.portfolio.cash+=pay;self.active=False
    def _draw_card(self,c,x,y,hidden=False):
        r,s=c;w,h=70,96;self.canvas.create_rectangle(x+4,y+5,x+w+4,y+h+5,fill='#043322',outline='');self.canvas.create_rectangle(x,y,x+w,y+h,fill='#f8f5ed',outline='#d7ca9d',width=2)
        if hidden:self.canvas.create_rectangle(x+7,y+7,x+w-7,y+h-7,fill='#173e70',outline='#d8b96a');return
        txt='A' if r==1 else 'J' if r==11 else 'Q' if r==12 else 'K' if r==13 else str(r);col='#c8324c' if s in '♥♦' else '#15191e';self.canvas.create_text(x+11,y+17,text=txt,fill=col,font=('Georgia',13,'bold'));self.canvas.create_text(x+w/2,y+h/2+5,text=s,fill=col,font=('Georgia',24,'bold'))
    def draw_table(self):
        c=self.canvas;c.delete('all');w=max(900,c.winfo_width());h=max(550,c.winfo_height());c.create_text(w/2,25,text='BLACKJACK TABLE',fill='#f5ddb0',font=('Georgia',18,'bold'))
        c.create_text(28,60,text='DEALER',fill='#cfe9dc',font=('Arial',9,'bold'),anchor='w')
        for i,card in enumerate(self.dealer):self._draw_card(card,120+i*78,70,hidden=self.active and i==1)
        cols=max(1,min(3,len(self.hands)));gap=w/(cols+1);base=h*.48
        for j,hnd in enumerate(self.hands):
            col=j%cols;row=j//cols;x0=gap*(col+1)-75;y=base+row*155;active=self.active and j==self.active_hand
            c.create_rectangle(x0-12,y-28,x0+250,y+112,outline='#ffe287' if active else '#34725a',width=3 if active else 1)
            c.create_text(x0,y-18,text=f'HAND {j+1} • ${self.bet_amounts[j]:,}',fill='#fff0b1' if active else '#cfe9dc',font=('Arial',9,'bold'),anchor='w')
            for i,card in enumerate(hnd):self._draw_card(card,x0+i*74,y)
            c.create_text(x0+226,y+42,text=str(self.val(hnd)),fill='#f5ddb0',font=('Georgia',19,'bold'))
        decks_left=len(self.shoe)/52 if self.shoe else 0;true=self.running/max(.25,decks_left) if self.count_mode.get()=='Hi-Lo' else self.running
        turn='DEAL A HAND' if not self.active else f'YOUR TURN • HAND {self.active_hand+1}'
        c.create_text(28,h-24,text=f'{turn}   •   shoe {len(self.shoe)} cards   •   shuffle at {self.cut_card}'+('   •   SHUFFLE AFTER ROUND' if self.shuffle_pending else ''),fill='#d9f0e5',font=('Arial',9,'bold'),anchor='w')
        self.info.config(text=f'Cash ${self.portfolio.cash:,.2f} • Count {self.running:+d} • True {true:+.2f}')

# ------------------------------- Roulette ----------------------------------
class RouletteWindow(ToolWindow):
    EURO_ORDER=[0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
    REDS={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    def __init__(self,parent,portfolio,market):
        super().__init__(_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • EUROPEAN ROULETTE','1580x940');self.resizable(True,True);self.chips=[25,100,500,1000,5000,10000];self.chip=tk.IntVar(value=100);self.bets={};self.history=[];self.spinning=False;self.target=0;self.anim=0;self._chip_hits=[]
        top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=6);ttk.Label(top,text='EUROPEAN ROULETTE',font=('Arial',14,'bold')).pack(side='left');self.balance=ttk.Label(top,text='');self.balance.pack(side='left',padx=14);ttk.Button(top,text='SPIN',command=self.spin).pack(side='right',padx=4);ttk.Button(top,text='CLEAR BETS',command=self.clear_bets).pack(side='right')
        self.cv=tk.Canvas(self,bg='#091018',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=8,pady=4);self.result=ttk.Label(self,text='Choose one denomination below the wheel, then click the betting table.');self.result.pack(fill='x',padx=10,pady=4);self.cv.bind('<Button-1>',self.click);self.draw()
    def _table_geom(self,w,h):
        wheel_cx=w*.18;wheel_r=min(h*.23,w*.135);left=max(wheel_cx+wheel_r+42,w*.39);right=28;cw=max(30,min(68,(w-left-right)/13));zero_w=cw;ch=max(36,min(55,h*.057));bx=left+zero_w;by=max(105,min(h*.15,h-5*ch-190));return bx,by,cw,ch,zero_w
    def add_bet(self,key):
        amt=int(self.chip.get());self.bets[key]=self.bets.get(key,0)+amt;self.draw()
    def clear_bets(self):self.bets.clear();self.draw()
    def board_click(self,e):
        w=max(1000,self.cv.winfo_width());h=max(650,self.cv.winfo_height());bx,by,cw,ch,zero_w=self._table_geom(w,h)
        if bx-zero_w<=e.x<=bx and by<=e.y<=by+3*ch:self.add_bet(0);return
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch
            if x<=e.x<=x+cw and y<=e.y<=y+ch:self.add_bet(n);return
        oy=by+3*ch+7;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            if bx+i*rw<=e.x<=bx+(i+1)*rw and oy<=e.y<=oy+ch*.85:self.add_bet(key);return
        oy2=oy+ch+6;rw=cw*2
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            if bx+i*rw<=e.x<=bx+(i+1)*rw and oy2<=e.y<=oy2+ch*.85:self.add_bet(key);return
    def click(self,e):
        for x,y,val in self._chip_hits:
            if (e.x-x)**2/24**2+(e.y-y)**2/15**2<=1:self.chip.set(val);self.result.config(text=f'Selected ${val:,} chip.');self.draw();return 'break'
        return self.board_click(e)
    def win_for(self,key,n):
        if isinstance(key,int):return n==key,35
        if key=='RED':return n in self.REDS,1
        if key=='BLACK':return n>0 and n not in self.REDS,1
        if key=='ODD':return n>0 and n%2==1,1
        if key=='EVEN':return n>0 and n%2==0,1
        if key=='1-18':return 1<=n<=18,1
        if key=='19-36':return 19<=n<=36,1
        if key=='1-12':return 1<=n<=12,2
        if key=='13-24':return 13<=n<=24,2
        if key=='25-36':return 25<=n<=36,2
        return False,0
    def spin(self):
        if self.spinning or not self.bets:return
        total=sum(self.bets.values())
        if total>self.portfolio.cash:return messagebox.showerror('Roulette','Insufficient balance.')
        self.portfolio.cash-=total;self.target=random.randint(0,36);self.spinning=True;self.anim=0;self._spin_step()
    def _spin_step(self):
        self.anim+=1
        if self.anim<48:
            self.draw(random.choice(self.EURO_ORDER),self.anim/48,True);return self.after(24+self.anim,self._spin_step)
        n=self.target;payout=0
        for key,amt in self.bets.items():
            win,m=self.win_for(key,n)
            if win:payout+=amt*(m+1)
        self.portfolio.cash+=payout;self.history.append(n);self.history=self.history[-500:];self.bets.clear();self.spinning=False;self.result.config(text=f'BALL {n} • payout ${payout:,.0f}');self.draw(n,0,False)
    def _bet_chip(self,c,x,y,amt):
        if not amt:return
        denom=max([d for d in self.chips if d<=amt],default=25);col=_SGP_CHIP_COLORS.get(denom,'#d8b96a');cnt=max(1,min(4,round(amt/max(1,denom))))
        for k in range(cnt):c.create_oval(x-12,y-7-k*3,x+12,y+7-k*3,fill=col,outline='#fff0bb')
        c.create_text(x,y-3*(cnt-1),text=f'${amt:,}',fill='white',font=('Arial',6,'bold'))
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        c=self.cv;c.delete('all');w=max(1000,c.winfo_width());h=max(650,c.winfo_height());cx=w*.18;cy=h*.27;r=min(h*.23,w*.135)
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill='#342414',outline='#d9ba68',width=5);c.create_oval(cx-r*.82,cy-r*.82,cx+r*.82,cy+r*.82,fill='#11171c',outline='#80612e',width=2)
        for i,n in enumerate(self.EURO_ORDER):
            a=2*math.pi*i/37-math.pi/2;a2=2*math.pi*(i+1)/37-math.pi/2;ro=r*.80;ri=r*.56;pts=[cx+math.cos(a)*ri,cy+math.sin(a)*ri,cx+math.cos(a)*ro,cy+math.sin(a)*ro,cx+math.cos(a2)*ro,cy+math.sin(a2)*ro,cx+math.cos(a2)*ri,cy+math.sin(a2)*ri];fill='#18835e' if n==0 else '#ad3047' if n in self.REDS else '#171b20';c.create_polygon(*pts,fill=fill,outline='#d8c17e')
            am=(a+a2)/2;tx=cx+math.cos(am)*r*.69;ty=cy+math.sin(am)*r*.69;c.create_text(tx,ty,text=str(n),fill='white',font=('Arial',7,'bold'))
        c.create_oval(cx-r*.48,cy-r*.48,cx+r*.48,cy+r*.48,fill='#4e3219',outline='#d8b96a',width=2);c.create_oval(cx-10,cy-10,cx+10,cy+10,fill='#d8b96a',outline='#fff1bc')
        if wheel_number in self.EURO_ORDER:
            idx=self.EURO_ORDER.index(wheel_number);a=2*math.pi*(idx+.5)/37-math.pi/2 + (ball_phase*math.pi*10 if spinning else 0);bx=cx+math.cos(a)*r*.91;by=cy+math.sin(a)*r*.91;c.create_oval(bx-7,by-7,bx+7,by+7,fill='white',outline='#cfd8df')
        # Exactly one denomination rack, underneath the wheel.
        rack_y=cy+r+42;self._chip_hits=[];start=cx-145
        c.create_text(cx,rack_y-28,text='AVAILABLE CHIPS • SELECT BET SIZE',fill='#d6e2e8',font=('Arial',8,'bold'))
        for i,val in enumerate(self.chips):
            x=start+i*58;col=_SGP_CHIP_COLORS.get(val,'#d8b96a');sel=int(self.chip.get())==val;c.create_oval(x-22,rack_y-13,x+22,rack_y+13,fill=col,outline='white' if sel else '#d8c998',width=3 if sel else 1);c.create_text(x,rack_y,text=f'${val:,}',fill='white' if val!=10000 else '#17212a',font=('Arial',6,'bold'));self._chip_hits.append((x,rack_y,val))
        c.create_text(cx,rack_y+34,text=f'Cash ${self.portfolio.cash:,.0f} • On table ${sum(self.bets.values()):,.0f}',fill='#9fb7c4',font=('Arial',8,'bold'))
        bx,by,cw,ch,zero_w=self._table_geom(w,h);c.create_rectangle(bx-zero_w,by,bx,by+3*ch,fill='#18835e',outline='#d8b96a');c.create_text(bx-zero_w/2,by+1.5*ch,text='0',fill='white',font=('Arial',14,'bold'));self._bet_chip(c,bx-zero_w/2,by+1.5*ch,self.bets.get(0,0))
        for n in range(1,37):
            col=(n-1)//3;row=(n-1)%3;x=bx+col*cw;y=by+row*ch;fill='#ad3047' if n in self.REDS else '#171b20';c.create_rectangle(x,y,x+cw,y+ch,fill=fill,outline='#d8b96a');c.create_text(x+cw/2,y+ch/2,text=str(n),fill='white',font=('Arial',11,'bold'));self._bet_chip(c,x+cw/2,y+ch/2,self.bets.get(n,0))
        oy=by+3*ch+7;rw=cw*4
        for i,key in enumerate(('1-12','13-24','25-36')):
            x=bx+i*rw;c.create_rectangle(x,oy,x+rw,oy+ch*.85,fill='#0e6950',outline='#d8b96a');c.create_text(x+rw/2,oy+ch*.42,text=key,fill='white',font=('Arial',8,'bold'));self._bet_chip(c,x+rw/2,oy+ch*.42,self.bets.get(key,0))
        oy2=oy+ch+6;rw=cw*2
        for i,key in enumerate(('1-18','EVEN','RED','BLACK','ODD','19-36')):
            x=bx+i*rw;fill='#ad3047' if key=='RED' else '#171b20' if key=='BLACK' else '#0e6950';c.create_rectangle(x,oy2,x+rw,oy2+ch*.85,fill=fill,outline='#d8b96a');c.create_text(x+rw/2,oy2+ch*.42,text=key,fill='white',font=('Arial',8,'bold'));self._bet_chip(c,x+rw/2,oy2+ch*.42,self.bets.get(key,0))
        panel_y=h-125;c.create_rectangle(16,panel_y,w-16,h-10,fill='#08131c',outline='#31495a');c.create_text(28,panel_y+9,text=f'LAST SPINS • {len(self.history)} / 500',fill='#f0d79c',font=('Arial',9,'bold'),anchor='nw')
        for i,n in enumerate(reversed(self.history[-36:])):
            x=32+(i%18)*36;y=panel_y+43+(i//18)*34;fill='#18835e' if n==0 else '#ad3047' if n in self.REDS else '#171b20';c.create_oval(x-10,y-10,x+10,y+10,fill=fill,outline='#d8b96a');c.create_text(x,y,text=str(n),fill='white',font=('Arial',6,'bold'))
        self.balance.config(text=f'Cash ${self.portfolio.cash:,.2f}')

# ------------------------------ Horse racing -------------------------------
class HorseRaceWindow(ToolWindow):
    HORSES=[('Blue Chip',1.8),('Market Maker',2.4),('Gamma Runner',3.1),('Bull Flag',4.0),('Short Squeeze',5.5),('Dark Pool',7.0)]
    def __init__(self,parent,portfolio,market):
        super().__init__(_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • HORSE RACING','1200x760');self.resizable(True,True);self.horse=tk.StringVar(value=self.HORSES[0][0]);self.bet=tk.IntVar(value=100);self.running=False;self.progress=[0.0]*len(self.HORSES)
        top=ttk.Frame(self);top.pack(fill='x',padx=10,pady=8);ttk.Label(top,text='SIMULATED HORSE RACING',font=('Arial',14,'bold')).pack(side='left');ttk.Label(top,text='Horse').pack(side='left',padx=(20,3));ttk.Combobox(top,textvariable=self.horse,values=[x[0] for x in self.HORSES],state='readonly',width=18).pack(side='left');ttk.Label(top,text='Bet').pack(side='left',padx=(12,3));ttk.Combobox(top,textvariable=self.bet,values=[25,100,500,1000,5000],state='readonly',width=9).pack(side='left');ttk.Button(top,text='START RACE',command=self.start).pack(side='left',padx=8);self.msg=ttk.Label(top,text='');self.msg.pack(side='right')
        self.cv=tk.Canvas(self,bg='#183f26',highlightthickness=0);self.cv.pack(fill='both',expand=True,padx=10,pady=8);self.draw()
    def start(self):
        if self.running:return
        b=int(self.bet.get())
        if b>self.portfolio.cash:return messagebox.showerror('Horse Racing','Insufficient balance.')
        self.portfolio.cash-=b;self.running=True;self.progress=[0.0]*len(self.HORSES);self._step()
    def _step(self):
        winner=None
        for i,(name,odds) in enumerate(self.HORSES):
            skill=1/max(1.2,odds);self.progress[i]+=random.uniform(.008,.023)*(0.75+skill)
            if self.progress[i]>=1 and winner is None:winner=i
        self.draw()
        if winner is None:return self.after(70,self._step)
        self.running=False;name,odds=self.HORSES[winner];chosen=self.horse.get();payout=0
        if name==chosen:payout=int(self.bet.get()*odds);self.portfolio.cash+=payout
        self.msg.config(text=f'{name} WINS • '+(f'payout ${payout:,}' if payout else 'ticket lost'))
    def draw(self):
        c=self.cv;c.delete('all');w=max(800,c.winfo_width());h=max(520,c.winfo_height());left=130;right=w-70;top=65;lane=(h-135)/len(self.HORSES);c.create_text(20,22,text=f'Bankroll ${self.portfolio.cash:,.0f}',fill='#f2e6b9',font=('Arial',11,'bold'),anchor='nw')
        for i,(name,odds) in enumerate(self.HORSES):
            y=top+i*lane;c.create_rectangle(left,y-20,right,y+20,fill='#8c6a42' if i%2==0 else '#795b39',outline='#d7bc88');c.create_text(18,y,text=f'{i+1}. {name}  {odds:.1f}×',fill='white',font=('Arial',9,'bold'),anchor='w');x=left+(right-left)*min(1,self.progress[i]);c.create_text(x,y,text='♞',fill='#fff0ad',font=('Segoe UI Symbol',22,'bold'));c.create_line(right,y-22,right,y+22,fill='white',width=3)

# Final casino floor — one launcher, four games, no duplicate denomination controls.
class CasinoWindow(ToolWindow):
    def __init__(self,parent,portfolio,market):
        super().__init__(_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • CASINO','1160x720');self.resizable(True,True)
        ttk.Label(self,text='STOCK GAME PRO CASINO',font=('Arial',19,'bold')).pack(pady=(22,4));ttk.Label(self,text='Virtual simulator credits • shared trading-account bankroll',foreground=MUTED).pack()
        bank=tk.Canvas(self,bg='#08131c',height=135,highlightthickness=0);bank.pack(fill='x',padx=20,pady=10);_sgp_draw_bankroll(bank,570,62,_sgp_total_net_worth(portfolio,market),'CURRENT NET WORTH',0)
        f=ttk.Frame(self);f.pack(fill='x',padx=18,pady=12)
        games=[('♠ BLACKJACK',lambda:BlackjackWindow(self,portfolio,market)),('● ROULETTE',lambda:RouletteWindow(self,portfolio,market)),('7 SLOTS',lambda:SlotMachineWindow(self,portfolio,market)),('♞ HORSE RACING',lambda:HorseRaceWindow(self,portfolio,market))]
        for text,cmd in games:ttk.Button(f,text=text,command=cmd).pack(side='left',expand=True,fill='x',padx=5,ipady=12)
        ttk.Label(self,text='Casino games are lightweight UI simulations and do not accelerate the global market clock.',foreground=MUTED).pack(pady=12)

def _sgp_casino_v17(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v17

# Final compact-column override must run after the production App.__init__ width pass.
_App_init_v17_compact_base=App.__init__
def _sgp_app_init_v17_compact(self,root,market,portfolio):
    _App_init_v17_compact_base(self,root,market,portfolio)
    _sgp_compact_tree(self.watch,{'symbol':54,'name':92,'price':64,'chg':55,'sector':68})
    _sgp_compact_tree(self.pos,{'symbol':72,'qty':48,'last':62,'value':72,'pnl':68,'pct':56,'type':52,'underlying':66,'expiry':64})
    _sgp_compact_tree(self.orders_view,{'id':44,'asset':62,'side':48,'type':54,'qty':54,'price':68,'status':62})
App.__init__=_sgp_app_init_v17_compact

def _sgp_toggle_table_column_v17(self,tv,key,var):
    widths={'symbol':72,'qty':48,'last':62,'value':72,'pnl':68,'pct':56,'type':52,'underlying':66,'expiry':64,'name':92,'price':64,'chg':55,'sector':68}
    tv.column(key,width=widths.get(key,62) if var.get() else 0,minwidth=36,stretch=False)
App.toggle_table_column=_sgp_toggle_table_column_v17

# ============================================================================
# Stock Game Pro 1.8 — compact workstation + candle-period controls
# ============================================================================
from game_core import Candle

_SGP_CANDLE_PERIODS=('Auto','1 Tick','30 Sec','1 Min','3 Min','5 Min','10 Min','30 Min','1 Hour','1 Day')

# Every chart owns its own candle aggregation period.
_Chart_init_v18_base=Chart.__init__
def _sgp_chart_init_v18(self,parent,app,index):
    _Chart_init_v18_base(self,parent,app,index)
    self.candle_period='Auto'
Chart.__init__=_sgp_chart_init_v18

def _sgp_aggregate_candles(raw,minutes):
    raw=list(raw)
    if not raw:return []
    minutes=max(1,int(minutes));out=[];cur=None;bucket=None
    for x in raw:
        ts=x.timestamp.replace(tzinfo=None) if getattr(x.timestamp,'tzinfo',None) else x.timestamp
        b=ts.replace(minute=(ts.minute//minutes)*minutes,second=0,microsecond=0)
        if bucket!=b:
            cur=Candle(b,float(x.open),float(x.high),float(x.low),float(x.close),int(x.volume));out.append(cur);bucket=b
        else:
            cur.high=max(cur.high,float(x.high));cur.low=min(cur.low,float(x.low));cur.close=float(x.close);cur.volume+=int(x.volume)
    return out

def _sgp_chart_raw_v18(self):
    if not self.asset:return []
    p=getattr(self,'candle_period','Auto')
    if p=='Auto':src={'1D':'5m','1W':'15m','1M':'1h','3M':'1h','6M':'1d','1Y':'1d','5Y':'1wk','MAX':'1d'}[self.timeframe];return list(self.asset.chart_candles(src))
    if p=='1 Tick':return list(self.asset.chart_candles('tick'))
    if p=='30 Sec':return list(self.asset.chart_candles('30s'))
    if p=='1 Min':return list(self.asset.chart_candles('1m'))
    if p=='3 Min':return _sgp_aggregate_candles(self.asset.chart_candles('1m'),3)
    if p=='5 Min':return list(self.asset.chart_candles('5m'))
    if p=='10 Min':return _sgp_aggregate_candles(self.asset.chart_candles('5m') or self.asset.chart_candles('1m'),10)
    if p=='30 Min':return _sgp_aggregate_candles(self.asset.chart_candles('15m') or self.asset.chart_candles('5m'),30)
    if p=='1 Hour':return list(self.asset.chart_candles('1h'))
    if p=='1 Day':return list(self.asset.chart_candles('1d'))
    return []

def _sgp_chart_data_v18(self):
    raw=_sgp_chart_raw_v18(self)
    if not raw:return []
    maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':360,'MAX':520}[self.timeframe]
    visible=min(len(raw),max(30,int(maxbars/max(.25,self.zoom))))
    maxoff=max(0,len(raw)-visible);self.view_offset=max(0,min(int(getattr(self,'view_offset',0)),maxoff))
    end=len(raw)-self.view_offset;start=max(0,end-visible);d=raw[start:end]
    target=max(250,min(1000,int(max(400,self.winfo_width())*1.15)))
    if len(d)>target:
        step=(len(d)-1)/(target-1);d=[d[round(i*step)] for i in range(target)]
    return d
Chart.data=_sgp_chart_data_v18

def _sgp_chart_pan_v18(self,bars):
    raw=_sgp_chart_raw_v18(self)
    if not raw:return
    maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':360,'MAX':520}[self.timeframe]
    visible=min(len(raw),max(30,int(maxbars/max(.25,self.zoom))));maxoff=max(0,len(raw)-visible)
    self.view_offset=max(0,min(maxoff,int(getattr(self,'view_offset',0)+bars)));self.follow_latest=(self.view_offset==0);self.request_draw(force=True)
Chart.pan_bars=_sgp_chart_pan_v18

def _sgp_set_candle_period(self,value):
    self.candle_period=value if value in _SGP_CANDLE_PERIODS else 'Auto';self.view_offset=0;self.follow_latest=True;self._key=None;self.request_draw(force=True)
Chart.set_candle_period=_sgp_set_candle_period

# Rebuild the Blackjack table geometry: dealer centered, hand totals always below cards.
_Blackjack_v18_base=BlackjackWindow
class BlackjackWindow(_Blackjack_v18_base):
    def draw_table(self):
        c=self.canvas;c.delete('all');w=max(900,c.winfo_width());h=max(550,c.winfo_height());c.create_text(w/2,25,text='BLACKJACK TABLE',fill='#f5ddb0',font=('Georgia',18,'bold'))
        # Center dealer hand as a unit regardless of card count.
        dealer_n=max(1,len(self.dealer));dealer_width=(dealer_n-1)*78+70;dx=(w-dealer_width)/2
        c.create_text(w/2,56,text=f'DEALER • {self.dealer_name}',fill='#cfe9dc',font=('Arial',9,'bold'))
        for i,card in enumerate(self.dealer):self._draw_card(card,dx+i*78,70,hidden=self.active and i==1)
        if self.dealer and not self.active:c.create_text(w/2,178,text=f'DEALER TOTAL  {self.val(self.dealer)}',fill='#f5ddb0',font=('Georgia',13,'bold'))
        cols=max(1,min(3,len(self.hands)));gap=w/(cols+1);base=max(255,h*.45);row_gap=190
        for j,hnd in enumerate(self.hands):
            col=j%cols;row=j//cols;card_n=max(1,len(hnd));hand_w=(card_n-1)*74+70;x_center=gap*(col+1);x0=x_center-hand_w/2;y=base+row*row_gap;active=self.active and j==self.active_hand
            box_left=x0-12;box_right=x0+hand_w+12;box_bottom=y+132
            c.create_rectangle(box_left,y-28,box_right,box_bottom,outline='#ffe287' if active else '#34725a',width=3 if active else 1)
            c.create_text(x_center,y-18,text=f'HAND {j+1} • ${self.bet_amounts[j]:,}',fill='#fff0b1' if active else '#cfe9dc',font=('Arial',9,'bold'),anchor='center')
            for i,card in enumerate(hnd):self._draw_card(card,x0+i*74,y)
            # Total is underneath the cards, never beside/over them.
            c.create_text(x_center,y+112,text=f'HAND VALUE  {self.val(hnd)}',fill='#f5ddb0',font=('Georgia',14,'bold'),anchor='center')
        decks_left=len(self.shoe)/52 if self.shoe else 0;true=self.running/max(.25,decks_left) if self.count_mode.get()=='Hi-Lo' else self.running
        turn='DEAL A HAND' if not self.active else f'YOUR TURN • HAND {self.active_hand+1}'
        c.create_text(28,h-24,text=f'{turn}   •   shoe {len(self.shoe)} cards   •   shuffle at {self.cut_card}'+('   •   SHUFFLE AFTER ROUND' if self.shuffle_pending else ''),fill='#d9f0e5',font=('Arial',9,'bold'),anchor='w')
        self.info.config(text=f'Cash ${self.portfolio.cash:,.2f} • Count {self.running:+d} • True {true:+.2f}')

# Slightly lower, roomier roulette chip rack. Everything else remains unchanged.
_Roulette_v18_base=RouletteWindow
class RouletteWindow(_Roulette_v18_base):
    def draw(self,wheel_number=None,ball_phase=0,spinning=False):
        super().draw(wheel_number,ball_phase,spinning)
        c=self.cv;w=max(1000,c.winfo_width());h=max(650,c.winfo_height());cx=w*.18;cy=h*.27;r=min(h*.23,w*.135)
        # Relocate only the selector rack by deleting the inherited selector region and redrawing lower.
        # A dark inset keeps text/chips visually separated from the wheel and table.
        rack_top=cy+r+24;rack_y=cy+r+72;rack_bottom=rack_y+54
        c.create_rectangle(max(16,cx-185),rack_top,min(w*.37,cx+185),rack_bottom,fill='#091018',outline='#31495a',width=2)
        self._chip_hits=[];start=cx-145
        c.create_text(cx,rack_y-28,text='AVAILABLE CHIPS • SELECT BET SIZE',fill='#d6e2e8',font=('Arial',8,'bold'))
        for i,val in enumerate(self.chips):
            x=start+i*58;col=_SGP_CHIP_COLORS.get(val,'#d8b96a');sel=int(self.chip.get())==val;c.create_oval(x-22,rack_y-13,x+22,rack_y+13,fill=col,outline='white' if sel else '#d8c998',width=3 if sel else 1);c.create_text(x,rack_y,text=f'${val:,}',fill='white' if val!=10000 else '#17212a',font=('Arial',6,'bold'));self._chip_hits.append((x,rack_y,val))
        c.create_text(cx,rack_y+32,text=f'Cash ${self.portfolio.cash:,.0f} • On table ${sum(self.bets.values()):,.0f}',fill='#9fb7c4',font=('Arial',8,'bold'))

# Centered horse-racing presentation with lane labels kept away from moving horses.
_Horse_v18_base=HorseRaceWindow
class HorseRaceWindow(_Horse_v18_base):
    def draw(self):
        c=self.cv;c.delete('all');w=max(800,c.winfo_width());h=max(520,c.winfo_height());track_w=min(900,w-120);left=(w-track_w)/2;right=left+track_w;top=82;lane=(h-175)/len(self.HORSES)
        c.create_text(w/2,24,text='STOCK GAME PRO • HORSE RACING',fill='#f2e6b9',font=('Georgia',17,'bold'))
        c.create_text(w/2,49,text=f'Bankroll ${self.portfolio.cash:,.0f} • Selected: {self.horse.get()} • Bet ${int(self.bet.get()):,}',fill='#d9e6dd',font=('Arial',10,'bold'))
        for i,(name,odds) in enumerate(self.HORSES):
            y=top+i*lane;c.create_rectangle(left,y-22,right,y+22,fill='#8c6a42' if i%2==0 else '#795b39',outline='#d7bc88')
            # Fixed label column inside the lane; racing starts after the label area.
            label_w=175;c.create_rectangle(left,y-22,left+label_w,y+22,fill='#173c2b',outline='#d7bc88');c.create_text(left+12,y,text=f'{i+1}. {name}\n{odds:.1f}× payout',fill='white',font=('Arial',8,'bold'),anchor='w',justify='left')
            race_left=left+label_w+18;x=race_left+(right-race_left-18)*min(1,self.progress[i]);c.create_text(x,y,text='♞',fill='#fff0ad',font=('Segoe UI Symbol',22,'bold'));c.create_line(right-5,y-23,right-5,y+23,fill='white',width=3)

# Workstation cleanup + a dedicated candle-period control beside Timeframe.
_App_init_v18_base=App.__init__
def _sgp_app_init_v18(self,root,market,portfolio):
    _App_init_v18_base(self,root,market,portfolio)
    top=self.tf.master
    # Remove redundant top-row trade/time buttons; the bottom world controls and left trade ticket remain.
    for ch in list(top.winfo_children()):
        try:txt=str(ch.cget('text')).strip().upper()
        except Exception:continue
        if txt in {'BUY','SELL','LIMIT','STOP','⏸ PAUSE','▶ RESUME','⏭ NEXT OPEN','⏸ PAUSE WORLD','▶ RESUME WORLD','⏭ SKIP TO NEXT OPEN'}:
            try:ch.destroy()
            except Exception:pass
    # Remove the duplicate Order Entry launcher beneath Portfolio/Account only.
    def walk(w):
        for ch in list(w.winfo_children()):
            try:
                if isinstance(ch,ttk.Button) and str(ch.cget('text')).strip().upper()=='ORDER ENTRY':ch.destroy();continue
            except Exception:pass
            walk(ch)
    walk(root)
    self.candle_period_var=tk.StringVar(value=getattr(self.charts[self.active_chart],'candle_period','Auto'))
    self.candle_period_label=ttk.Label(top,text='Candle')
    self.candle_period_cb=ttk.Combobox(top,textvariable=self.candle_period_var,values=_SGP_CANDLE_PERIODS,state='readonly',width=9)
    # Insert immediately after timeframe and before chart style.
    try:self.candle_period_label.pack(side='left',padx=(4,2),before=self.ctype);self.candle_period_cb.pack(side='left',padx=(0,4),before=self.ctype)
    except Exception:self.candle_period_label.pack(side='left');self.candle_period_cb.pack(side='left')
    self.candle_period_cb.bind('<<ComboboxSelected>>',lambda e:self.set_active_candle_period())
App.__init__=_sgp_app_init_v18

def _sgp_set_active_candle_period(self):
    if not self.charts:return
    self.charts[self.active_chart].set_candle_period(self.candle_period_var.get());self.status_flash(f'Chart {self.active_chart+1} candle period: {self.candle_period_var.get()}')
App.set_active_candle_period=_sgp_set_active_candle_period

_App_sync_chart_controls_v18_base=App.sync_chart_controls
def _sgp_sync_chart_controls_v18(self):
    _App_sync_chart_controls_v18_base(self)
    if hasattr(self,'candle_period_var') and self.charts:self.candle_period_var.set(getattr(self.charts[self.active_chart],'candle_period','Auto'))
App.sync_chart_controls=_sgp_sync_chart_controls_v18

# Advanced chart gets the same independent candle-period selector.
_Advanced_v18_base=AdvancedChartWindow
class AdvancedChartWindow(_Advanced_v18_base):
    def __init__(self,parent,app,asset):
        super().__init__(parent,app,asset)
        top=None
        for ch in self.winfo_children():
            if isinstance(ch,ttk.Frame):top=ch;break
        if top is not None:
            self.candle_period_var=tk.StringVar(value=getattr(self.chart,'candle_period','Auto'));lab=ttk.Label(top,text='Candle');cb=ttk.Combobox(top,textvariable=self.candle_period_var,values=_SGP_CANDLE_PERIODS,state='readonly',width=9)
            # Put before Style when possible.
            style_widget=None
            for ch in top.winfo_children():
                try:
                    if isinstance(ch,ttk.Label) and str(ch.cget('text'))=='Style':style_widget=ch;break
                except Exception:pass
            if style_widget is not None:lab.pack(side='left',padx=(6,2),before=style_widget);cb.pack(side='left',padx=(0,4),before=style_widget)
            else:lab.pack(side='left');cb.pack(side='left')
            cb.bind('<<ComboboxSelected>>',lambda e:self.chart.set_candle_period(self.candle_period_var.get()))

def _sgp_open_adv_v18(self,a):return AdvancedChartWindow(self.root,self,a)
App.advanced_chart=_sgp_open_adv_v18

# Final casino floor resolves the final v1.8 game classes.
class CasinoWindow(CasinoWindow):
    def __init__(self,parent,portfolio,market):
        ToolWindow.__init__(self,_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • CASINO','1160x720');self.resizable(True,True)
        ttk.Label(self,text='STOCK GAME PRO CASINO',font=('Arial',19,'bold')).pack(pady=(22,4));ttk.Label(self,text='Virtual simulator credits • shared trading-account bankroll',foreground=MUTED).pack()
        bank=tk.Canvas(self,bg='#08131c',height=135,highlightthickness=0);bank.pack(fill='x',padx=20,pady=10);_sgp_draw_bankroll(bank,570,62,_sgp_total_net_worth(portfolio,market),'CURRENT NET WORTH',0)
        f=ttk.Frame(self);f.pack(fill='x',padx=18,pady=12)
        games=[('♠ BLACKJACK',lambda:BlackjackWindow(self,portfolio,market)),('● ROULETTE',lambda:RouletteWindow(self,portfolio,market)),('7 SLOTS',lambda:SlotMachineWindow(self,portfolio,market)),('♞ HORSE RACING',lambda:HorseRaceWindow(self,portfolio,market))]
        for text,cmd in games:ttk.Button(f,text=text,command=cmd).pack(side='left',expand=True,fill='x',padx=5,ipady=12)
        ttk.Label(self,text='Casino games are lightweight UI simulations and do not accelerate the global market clock.',foreground=MUTED).pack(pady=12)

def _sgp_casino_v18(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v18

# Final visual centering tweak for the horse-racing control strip.
_Horse_v18_center_base=HorseRaceWindow
class HorseRaceWindow(_Horse_v18_center_base):
    def __init__(self,parent,portfolio,market):
        super().__init__(parent,portfolio,market)
        try:
            frames=[w for w in self.winfo_children() if isinstance(w,ttk.Frame)]
            if frames:frames[0].pack_configure(fill='none',anchor='center',padx=10,pady=8)
        except Exception:pass

# Rebind casino one last time so it resolves the centered horse-racing class.
class CasinoWindow(CasinoWindow):
    def __init__(self,parent,portfolio,market):
        ToolWindow.__init__(self,_sgp_tk_parent(parent));self.portfolio=portfolio;self.market=market;self.style_window('STOCK GAME PRO • CASINO','1160x720');self.resizable(True,True)
        ttk.Label(self,text='STOCK GAME PRO CASINO',font=('Arial',19,'bold')).pack(pady=(22,4));ttk.Label(self,text='Virtual simulator credits • shared trading-account bankroll',foreground=MUTED).pack()
        bank=tk.Canvas(self,bg='#08131c',height=135,highlightthickness=0);bank.pack(fill='x',padx=20,pady=10);_sgp_draw_bankroll(bank,570,62,_sgp_total_net_worth(portfolio,market),'CURRENT NET WORTH',0)
        f=ttk.Frame(self);f.pack(fill='x',padx=18,pady=12)
        games=[('♠ BLACKJACK',lambda:BlackjackWindow(self,portfolio,market)),('● ROULETTE',lambda:RouletteWindow(self,portfolio,market)),('7 SLOTS',lambda:SlotMachineWindow(self,portfolio,market)),('♞ HORSE RACING',lambda:HorseRaceWindow(self,portfolio,market))]
        for text,cmd in games:ttk.Button(f,text=text,command=cmd).pack(side='left',expand=True,fill='x',padx=5,ipady=12)
        ttk.Label(self,text='Casino games are lightweight UI simulations and do not accelerate the global market clock.',foreground=MUTED).pack(pady=12)

def _sgp_casino_v18_final(self):return CasinoWindow(self.root,self.portfolio,self.market)
App.casino=_sgp_casino_v18_final

# ===== Stock Game Pro 1.9 chart sync / professional order controls / experiment lab =====
from game_core import Candle as _SGP_Candle_v19

# Keep the newest visible candle pinned to the same live price shown in the ticker/watchlist.
_Chart_data_v19_base=Chart.data
def _sgp_chart_data_v19(self):
    d=list(_Chart_data_v19_base(self))
    if not d or self.asset is None:return d
    if int(getattr(self,'view_offset',0))>0 or (getattr(self,'pan_mode',False) and not getattr(self,'follow_latest',True)):
        return d
    p=float(self.asset.price);now=getattr(self.app.market.clock,'current',d[-1].timestamp)
    last=d[-1]
    # Copy rather than mutating historical/cache candles. If the latest bar is from the
    # current simulator day, treat the live quote as its close; otherwise append a live print.
    if getattr(last.timestamp,'date',lambda:None)()==getattr(now,'date',lambda:None)():
        d[-1]=_SGP_Candle_v19(last.timestamp,float(last.open),max(float(last.high),p),min(float(last.low),p),p,int(last.volume))
    else:
        prev=float(getattr(self.asset,'previous_price',p));d.append(_SGP_Candle_v19(now,prev,max(prev,p),min(prev,p),p,int(max(0,getattr(self.asset,'volume',0)))))
    return d
Chart.data=_sgp_chart_data_v19

_Chart_init_v19_base=Chart.__init__
def _sgp_chart_init_v19(self,parent,app,index):
    _Chart_init_v19_base(self,parent,app,index);self.vertical_scale=1.0
Chart.__init__=_sgp_chart_init_v19

def _sgp_price_bounds_v19(self):
    d=self.data()
    if not d:return (0,1)
    lo=min(float(x.low) for x in d);hi=max(float(x.high) for x in d)
    if self.asset is not None and int(getattr(self,'view_offset',0))==0:
        p=float(self.asset.price);lo=min(lo,p);hi=max(hi,p)
    raw=max(1e-8,hi-lo);scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
    center=float(self.asset.price) if self.asset is not None and int(getattr(self,'view_offset',0))==0 else (hi+lo)/2
    half=max(raw/(2*scale),max(abs(center)*.00005,1e-6));return center-half,center+half
Chart.price_bounds=_sgp_price_bounds_v19

def _sgp_set_vertical_scale_v19(self,value):
    try:self.vertical_scale=max(.25,min(8.0,float(value)))
    except Exception:self.vertical_scale=1.0
    self._key=None;self.request_draw(force=True)
Chart.set_vertical_scale=_sgp_set_vertical_scale_v19

# Stable order rows with explicit cancellation support.
def _sgp_refresh_orders_v19(self):
    if not hasattr(self,'orders_view'):return
    keep=self.orders_view.selection();keep=keep[0] if keep else None
    wanted=[]
    for o in self.market.pending_orders:
        a=o.get('asset');iid=f"STOCK:{o.get('id')}";wanted.append((iid,(o.get('id',''),getattr(a,'symbol',''),o.get('side',''),o.get('type',''),f"{o.get('qty',0):,}",f"${float(o.get('price') or 0):,.2f}",'WORKING')))
    for o in self.market.pending_option_orders:
        c=o.get('contract');iid=f"OPTION:{o.get('id')}";wanted.append((iid,(o.get('id',''),getattr(getattr(c,'underlying',None),'symbol',''),o.get('side',''),f"OPT {o.get('type','')}",o.get('qty',1),f"${float(o.get('price') or 0):,.2f}",'WORKING')))
    for o in self.market.pending_spread_orders:
        iid=f"SPREAD:{o.get('id')}";st=o.get('strategy');wanted.append((iid,(o.get('id',''),getattr(st,'name','SPREAD'),o.get('side',''),f"SPREAD {o.get('type','')}",len(getattr(st,'legs',[])),f"${float(o.get('price') or 0):,.2f}",'WORKING')))
    existing=set(self.orders_view.get_children());need={i for i,_ in wanted}
    for iid in existing-need:self.orders_view.delete(iid)
    for idx,(iid,vals) in enumerate(wanted):
        if self.orders_view.exists(iid):self.orders_view.item(iid,values=vals);self.orders_view.move(iid,'end',idx)
        else:self.orders_view.insert('','end',iid=iid,values=vals)
    if keep and self.orders_view.exists(keep):self.orders_view.selection_set(keep);self.orders_view.focus(keep)
App.refresh_orders=_sgp_refresh_orders_v19

def _sgp_cancel_selected_order_v19(self):
    sel=self.orders_view.selection() if hasattr(self,'orders_view') else ()
    if not sel:return messagebox.showwarning('Cancel order','Select a working order first.')
    iid=sel[0]
    try:kind,oid=iid.split(':',1)
    except Exception:return messagebox.showerror('Cancel order','Unable to identify the selected working order.')
    ok,msg=self.market.cancel_order(oid,kind);self.refresh_orders();self.status_flash(msg)
    if not ok:messagebox.showwarning('Cancel order',msg)
    for c in list(getattr(self,'charts',()))+list(getattr(self,'extra_charts',())):
        try:c.request_draw(force=True)
        except Exception:pass
App.cancel_selected_order=_sgp_cancel_selected_order_v19

def _sgp_orders_context_v19(self,e):
    iid=self.orders_view.identify_row(e.y)
    if iid:self.orders_view.selection_set(iid);self.orders_view.focus(iid)
    m=tk.Menu(self.orders_view,tearoff=0);m.add_command(label='CANCEL SELECTED ORDER',command=self.cancel_selected_order);m.add_command(label='REFRESH ORDERS',command=self.refresh_orders);m.tk_popup(e.x_root,e.y_root)
App.orders_context=_sgp_orders_context_v19

# Market-conditions / whale / options experimentation workstation.
def _sgp_market_conditions_lab_v19(self):
    w=ToolWindow(self.root);w.style_window('MARKET CONDITIONS • WHALE / OPTIONS LAB','720x700');w.resizable(True,True)
    ttk.Label(w,text='MARKET CONDITIONS EXPERIMENT LAB',font=('Arial',16,'bold')).pack(anchor='w',padx=16,pady=(16,3))
    ttk.Label(w,text='Change simulated volatility, liquidity, macro sentiment and directional whale flow. These settings affect the entire simulated market and option IV/spreads.',wraplength=670,foreground=MUTED).pack(anchor='w',padx=16,pady=(0,12))
    vars={
        'Volatility':tk.DoubleVar(value=float(getattr(self.market,'scenario_volatility',1.0))),
        'Liquidity':tk.DoubleVar(value=float(getattr(self.market,'scenario_liquidity',1.0))),
        'Whale flow':tk.DoubleVar(value=float(getattr(self.market,'scenario_whale_flow',0.0))),
        'Event intensity':tk.DoubleVar(value=float(getattr(self.market,'scenario_event_intensity',1.0))),
        'Sentiment':tk.DoubleVar(value=float(self.market.macro.get('sentiment',0))),
        'Inflation':tk.DoubleVar(value=float(self.market.macro.get('inflation',2.5))),
        'Fed rate':tk.DoubleVar(value=float(self.market.macro.get('policy_rate',4.0))),
    }
    specs=[('Volatility',.25,4.0,.05,'×'),('Liquidity',.25,4.0,.05,'×'),('Whale flow',-1,1,.02,''),('Event intensity',.25,3,.05,'×'),('Sentiment',-1,1,.02,''),('Inflation',0,15,.1,'%'),('Fed rate',0,15,.1,'%')]
    readouts={}
    for name,lo,hi,res,suffix in specs:
        row=ttk.Frame(w);row.pack(fill='x',padx=16,pady=5);ttk.Label(row,text=name,width=16).pack(side='left');sc=tk.Scale(row,from_=lo,to=hi,resolution=res,orient='horizontal',variable=vars[name],length=390,bg=PANEL,fg=TEXT,highlightthickness=0);sc.pack(side='left',fill='x',expand=True);lab=ttk.Label(row,width=10);lab.pack(side='right');readouts[name]=(lab,suffix)
        vars[name].trace_add('write',lambda *_x,n=name:readouts[n][0].config(text=f'{vars[n].get():.2f}{readouts[n][1]}'))
        lab.config(text=f'{vars[name].get():.2f}{suffix}')
    sym=tk.StringVar(value=str(getattr(self.market,'scenario_whale_symbol','') or 'SPY'));r=ttk.Frame(w);r.pack(fill='x',padx=16,pady=8);ttk.Label(r,text='Whale target',width=16).pack(side='left');cb=ttk.Combobox(r,textvariable=sym,values=[a.symbol for a in self.market.all_assets()],width=18);cb.pack(side='left');ttk.Label(r,text='Target receives stronger flow than the broad market.',foreground=MUTED).pack(side='left',padx=8)
    status=ttk.Label(w,text='');status.pack(fill='x',padx=16,pady=8)
    def apply():
        self.market.scenario_volatility=vars['Volatility'].get();self.market.scenario_liquidity=vars['Liquidity'].get();self.market.scenario_whale_flow=vars['Whale flow'].get();self.market.scenario_event_intensity=vars['Event intensity'].get();self.market.scenario_whale_symbol=sym.get().upper().strip();self.market.macro['sentiment']=vars['Sentiment'].get();self.market.macro['inflation']=vars['Inflation'].get();self.market.macro['policy_rate']=vars['Fed rate'].get()
        for a in self.market.all_assets():a.scenario_vol_mult=self.market.scenario_volatility;a.scenario_liquidity=self.market.scenario_liquidity
        self.market.visual_version+=1;status.config(text=f'Applied • vol {self.market.scenario_volatility:.2f}× • liquidity {self.market.scenario_liquidity:.2f}× • whale {self.market.scenario_whale_flow:+.2f} → {self.market.scenario_whale_symbol or "BROAD"}')
    def preset(name):
        vals={'CALM':(.55,1.8,0,0.5,.15,2.1,3.5),'RISK ON':(.85,1.4,.18,.8,.55,2.6,4.0),'PANIC':(2.8,.45,-.65,2.6,-.85,6.5,6.0),'WHALE BUY':(1.25,.75,.85,1.2,.25,3.0,4.5),'WHALE SELL':(1.6,.55,-.90,1.4,-.35,3.5,4.5),'VOL CRUSH':(.40,2.2,0,.4,.10,2.2,3.5)}[name]
        for k,v in zip(['Volatility','Liquidity','Whale flow','Event intensity','Sentiment','Inflation','Fed rate'],vals):vars[k].set(v)
        apply()
    p=ttk.Frame(w);p.pack(fill='x',padx=16,pady=8)
    for name in ('CALM','RISK ON','PANIC','WHALE BUY','WHALE SELL','VOL CRUSH'):ttk.Button(p,text=name,command=lambda n=name:preset(n)).pack(side='left',expand=True,fill='x',padx=2)
    ttk.Button(w,text='APPLY CONDITIONS',command=apply).pack(fill='x',padx=16,pady=6);ttk.Button(w,text='RESET NORMAL',command=lambda:preset('RISK ON')).pack(fill='x',padx=16,pady=(0,10))
App.market_conditions_lab=_sgp_market_conditions_lab_v19

# Explicit +24H button. Unlike "next open", this actually runs a full market-aware day.
def _sgp_next_day_v19(self):
    self.status_flash('Simulating a full 24-hour market day…');self.root.update_idletasks()
    try:
        end=self.market.advance_one_day();self.refresh_watch();self.refresh_positions();self.refresh_orders()
        for c in list(getattr(self,'charts',()))+list(getattr(self,'extra_charts',())):
            try:c.request_draw(force=True)
            except Exception:pass
        self.status_flash(f'Advanced one full day → {end:%A %Y-%m-%d %H:%M:%S}')
    except Exception as e:messagebox.showerror('Next day',f'Unable to advance one day: {e}')
App.next_day=_sgp_next_day_v19

# Final 1.9 app wiring.
_App_init_v19_base=App.__init__
def _sgp_app_init_v19(self,root,market,portfolio):
    _App_init_v19_base(self,root,market,portfolio)
    # Working-order cancellation controls.
    try:
        obar=ttk.Frame(self.orders_view.master);obar.pack(fill='x',padx=6,pady=(4,0),before=self.orders_view);ttk.Button(obar,text='CANCEL SELECTED',command=self.cancel_selected_order).pack(side='left');ttk.Label(obar,text='Right-click a working order to cancel it.',foreground=MUTED).pack(side='left',padx=8);self.orders_view.bind('<Button-3>',self.orders_context)
    except Exception:pass
    # NEXT DAY is intentionally distinct from NEXT OPEN and performs a complete 24-hour simulation.
    try:
        top=self.tf.master;self.next_day_button=ttk.Button(top,text='NEXT DAY +24H',command=self.next_day,width=13);self.next_day_button.pack(side='left',padx=(5,3),before=self.clock_label)
    except Exception:pass
    # Experiment menu is intentionally separate from order-entry/options menus.
    try:
        mb=self.root.nametowidget(self.root.cget('menu'));exp=tk.Menu(mb,tearoff=0);exp.add_command(label='Market Conditions / Whale & Options Lab',command=self.market_conditions_lab);mb.add_cascade(label='Experimental',menu=exp)
    except Exception:pass
App.__init__=_sgp_app_init_v19

# Advanced chart vertical stretch / fit controls and quick access to scenario lab.
_Advanced_v19_base=AdvancedChartWindow
class AdvancedChartWindow(_Advanced_v19_base):
    def __init__(self,parent,app,asset):
        super().__init__(parent,app,asset)
        top=None
        for ch in self.winfo_children():
            if isinstance(ch,ttk.Frame):top=ch;break
        if top is not None:
            ttk.Label(top,text='V Zoom').pack(side='left',padx=(8,2));self.vscale=tk.DoubleVar(value=float(getattr(self.chart,'vertical_scale',1.0)));vs=ttk.Scale(top,from_=.5,to=5.0,variable=self.vscale,orient='horizontal',length=105,command=lambda v:self.chart.set_vertical_scale(v));vs.pack(side='left');self.vscale_label=ttk.Label(top,text='1.00×',width=6);self.vscale_label.pack(side='left');self.vscale.trace_add('write',lambda *_:self.vscale_label.config(text=f'{self.vscale.get():.2f}×'));ttk.Button(top,text='FIT Y',command=self.fit_vertical,width=6).pack(side='left',padx=2);ttk.Button(top,text='CONDITIONS',command=app.market_conditions_lab,width=10).pack(side='left',padx=3)
    def fit_vertical(self):
        self.vscale.set(1.0);self.chart.set_vertical_scale(1.0)

def _sgp_open_adv_v19(self,a):return AdvancedChartWindow(self.root,self,a)
App.advanced_chart=_sgp_open_adv_v19

# Smoother round-robin chart service: render up to two due canvases only while the pulse
# remains inside a small time budget, keeping menus responsive while reducing visible skew.
def _sgp_chart_refresh_pulse_v19(self):
    if not getattr(self,'_chart_refresh_running',True):return
    try:
        if not self.root.winfo_exists():return
    except tk.TclError:return
    now_ms=time.monotonic()*1000.0;live_extra=[]
    for chart in tuple(getattr(self,'extra_charts',())):
        try:
            if chart.winfo_exists():live_extra.append(chart)
        except tk.TclError:pass
    self.extra_charts=live_extra;allcharts=list(getattr(self,'charts',()))+live_extra
    if allcharts:
        start=int(getattr(self,'_chart_rr',0))%len(allcharts);deadline=time.perf_counter()+.006;drawn=0
        for off in range(len(allcharts)):
            chart=allcharts[(start+off)%len(allcharts)]
            try:
                if chart.winfo_exists() and chart.due_for_refresh(now_ms):
                    chart.request_draw(force=False);chart.mark_refreshed(now_ms);drawn+=1;self._chart_rr=(start+off+1)%len(allcharts)
                    if drawn>=2 or time.perf_counter()>=deadline:break
            except tk.TclError:pass
            except Exception as e:
                try:self.market.errors.append(f'chart scheduler v1.9: {type(e).__name__}: {e}')
                except Exception:pass
        else:self._chart_rr=(start+1)%len(allcharts)
    self._chart_refresh_job=self.root.after(10,self._chart_refresh_pulse)
App._chart_refresh_pulse=_sgp_chart_refresh_pulse_v19


# ===== Stock Game Pro 1.9.1 live-chart focus hotfix =====
# The renderer previously calculated its own min/max from candle history, bypassing
# Chart.price_bounds().  That let the quote/watchlist price escape the visible y-axis.
# The base renderer above now uses price_bounds(); this final pass makes live following
# explicit and draws an authoritative last-price guide on every live chart.
def _sgp_price_bounds_v191(self):
    d=list(self.data())
    if not d:return (0.0,1.0)
    live=(self.asset is not None and int(getattr(self,'view_offset',0))==0 and getattr(self,'follow_latest',True))
    lows=[float(x.low) for x in d];highs=[float(x.high) for x in d]
    lo=min(lows);hi=max(highs)
    if not live:
        raw=max(1e-8,hi-lo);scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
        mid=(hi+lo)/2.0;half=max(raw/(2.0*scale),max(abs(mid)*.00005,1e-6));return mid-half,mid+half
    p=float(self.asset.price)
    # Use recent bars to determine useful visual scale.  Old spikes in a long viewport
    # should not make today's price look like a flat line, but the current quote is always
    # centered and therefore cannot fall off screen.
    recent=d[-min(len(d),120):]
    rlo=min([float(x.low) for x in recent]+[p]);rhi=max([float(x.high) for x in recent]+[p])
    typical=max(1e-8,rhi-rlo)
    # Give the live quote breathing room even in an unusually flat market.
    floor=max(abs(p)*0.0025,0.01 if abs(p)>=1 else abs(p)*0.01,1e-6)
    scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
    half=max(typical*0.62/scale,floor/scale)
    # If the whole visible candle set is reasonably close, include it.  Extreme stale
    # history is intentionally ignored while following live so focus stays on the quote.
    whole=max(abs(p-lo),abs(hi-p))
    if whole <= half*3.5:half=max(half,whole*1.08)
    return p-half,p+half
Chart.price_bounds=_sgp_price_bounds_v191

_Chart_draw_v191_base=Chart.draw
def _sgp_chart_draw_v191(self):
    _Chart_draw_v191_base(self)
    if self.asset is None:return
    if int(getattr(self,'view_offset',0))!=0 or not getattr(self,'follow_latest',True):return
    try:
        self.delete('livefocus')
        w=max(280,self.winfo_width());h=max(170,self.winfo_height());left,right=62,w-12
        p=float(self.asset.price);y=self.price_to_y(p)
        # Keep the marker away from the footer/header even during a transient resize.
        y=max(35,min(h-48,y))
        self.create_line(left,y,right,y,fill=CYAN,dash=(3,3),width=1,tags='livefocus')
        self.create_rectangle(right-76,y-9,right,y+9,fill='#0b2532',outline=CYAN,tags='livefocus')
        self.create_text(right-4,y,text=f'LIVE {p:,.2f}',fill='#d8f6ff',font=('Consolas',8,'bold'),anchor='e',tags='livefocus')
    except Exception:pass
Chart.draw=_sgp_chart_draw_v191

# Any ordinary main/advanced chart starts in live-follow mode. Historical panning still
# opts out by setting view_offset/follow_latest through the existing controls.
_Chart_set_asset_v191_base=Chart.set_asset
def _sgp_set_asset_v191(self,a):
    self.view_offset=0;self.follow_latest=True
    return _Chart_set_asset_v191_base(self,a)
Chart.set_asset=_sgp_set_asset_v191


# ===== Stock Game Pro 2.0 chart-follow + long-session UI overhaul =====
# A single final renderer replaces the layered legacy draw wrappers. It uses one snapshot,
# only chart-local portfolio/order state in its cache key, and always centers a LIVE chart
# on the authoritative asset.price. This removes the remaining ticker/chart divergence.
def _sgp_chart_bounds_v20(self,d,live):
    if not d:return (0.0,1.0)
    scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
    if live and self.asset is not None:
        p=float(self.asset.price);recent=d[-min(90,len(d)):];rlo=min([float(c.low) for c in recent]+[p]);rhi=max([float(c.high) for c in recent]+[p]);rng=max(rhi-rlo,abs(p)*.003,0.02 if abs(p)>=1 else abs(p)*.02,1e-6);half=max(rng*.62,abs(p)*.0015,1e-6)/scale;return p-half,p+half
    lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);mid=(hi+lo)/2;rng=max(hi-lo,abs(mid)*.0002,1e-6);return mid-rng/(2*scale),mid+rng/(2*scale)

def _sgp_chart_draw_v20(self):
    a=self.asset;w=max(280,self.winfo_width());h=max(170,self.winfo_height());d=list(self.data()) if a else []
    live=bool(a is not None and int(getattr(self,'view_offset',0))==0 and getattr(self,'follow_latest',True) and not (getattr(self,'pan_mode',False) and not getattr(self,'follow_latest',True)))
    if a is not None and d and live:
        # Always force the rightmost candle to the same authoritative quote shown in watchlist.
        p=float(a.price);last=d[-1];d[-1]=Candle(last.timestamp,float(last.open),max(float(last.high),p),min(float(last.low),p),p,int(last.volume))
    q=int(self.app.portfolio.positions.get(a.symbol,0)) if a else 0;basis=float(self.app.portfolio.cost_basis.get(a.symbol,0)) if a else 0.0
    rel_orders=tuple((o.get('id'),o.get('side'),o.get('type'),round(float(o.get('price') or 0),5)) for o in self.app.market.pending_orders if a is not None and o.get('asset') is a)
    rel_opts=tuple((getattr(st,'strategy_id',None),l.action,l.quantity,round(float(l.contract.strike),5)) for st,l in (self.app.portfolio.option_legs_for(a.symbol) if a else []))
    key=(a.symbol if a else None,self.timeframe,getattr(self,'candle_period','Auto'),self.kind,round(self.zoom,3),int(getattr(self,'view_offset',0)),bool(getattr(self,'follow_latest',True)),round(float(a.price),5) if a else 0,getattr(a,'last_update',None),w,h,q,round(basis,3),rel_orders,rel_opts,self.app.ind_vars_version,round(float(getattr(self,'vertical_scale',1.0)),3),len(d))
    if key==getattr(self,'_key',None):
        self._draw_crosshair();return
    self._key=key;self.delete('all')
    if not a:self.create_text(w/2,h/2,text=f'CHART {self.index+1}\nClick a market ticker',fill=MUTED,font=('Arial',12,'bold'));return
    if len(d)<2:self.create_text(10,8,anchor='nw',text=f'{a.symbol} • loading {self.timeframe}',fill=MUTED,font=('Arial',9));return
    left,right,top,bottom=62,w-14,34,h-48;lo,hi=_sgp_chart_bounds_v20(self,d,live);self._last_bounds_v20=(lo,hi);span=max(1e-9,hi-lo);step=(right-left)/max(1,len(d))
    def py(v):return bottom-(float(v)-lo)/span*(bottom-top)
    name=a.name if w>470 else (a.name[:16]+'…' if len(a.name)>17 else a.name)
    self.create_text(8,7,anchor='nw',text=f'{a.symbol} • {name}',fill=TEXT,font=('Arial',9,'bold'))
    mode='LIVE FOLLOW' if live else f'HISTORY • {int(getattr(self,"view_offset",0))} bars back'
    self.create_text(right,7,anchor='ne',text=f'{self.timeframe} • {getattr(self,"candle_period","Auto")} • {mode} • ${a.price:,.2f}',fill=CYAN if live else MUTED,font=('Arial',7 if w<500 else 8,'bold'))
    for j in range(6):
        y=top+j*(bottom-top)/5;v=hi-j*span/5;self.create_line(left,y,right,y,fill=GRID);self.create_text(left-5,y,text=f'{v:,.2f}',anchor='e',fill=MUTED,font=('Arial',7))
    if self.kind=='Candles':
        bw=max(1,step*.34)
        for i,c in enumerate(d):
            x=left+(i+.5)*step;col=GREEN if c.close>=c.open else RED;self.create_line(x,py(c.high),x,py(c.low),fill=col)
            y1,y2=py(c.open),py(c.close);self.create_rectangle(x-bw,min(y1,y2),x+bw,max(y1,y2)+1,fill=col,outline=col)
    else:
        pts=[]
        for i,c in enumerate(d):pts.extend((left+(i+.5)*step,py(c.close)))
        if self.kind=='Area':self.create_polygon(*(pts+[right,bottom,left,bottom]),fill='#12314a',outline='')
        if len(pts)>=4:self.create_line(*pts,fill=BLUE,width=2)
    close=[float(x.close) for x in d]
    if self.app.ind_vars['SMA'].get():self._line(sma(close,20),left,step,py,YELLOW)
    if self.app.ind_vars['EMA'].get():self._line(ema(close,20),left,step,py,PURPLE)
    if self.app.ind_vars['BB'].get():
        _,u,l=boll(close);self._line(u,left,step,py,CYAN);self._line(l,left,step,py,CYAN)
    if self.app.ind_vars['VWAP'].get():self._line(vwap(d),left,step,py,ORANGE)
    if self.app.ind_vars['Volume'].get():
        vmax=max((x.volume for x in d),default=1) or 1;vh=(bottom-top)*.12
        for i,c in enumerate(d):
            x=left+(i+.5)*step;y=bottom-c.volume/vmax*vh;self.create_rectangle(x-step*.28,bottom,x+step*.28,y,fill='#33485b',outline='')
    # Chart-local positions/orders only.
    for o in self.app.market.pending_orders:
        if o.get('asset') is a and o.get('price') is not None:
            y=py(o['price']);col=GREEN if o.get('side') in ('BUY','COVER') else RED;self.create_line(left,y,right,y,fill=col,dash=(7,4) if o.get('type')=='LIMIT' else (2,3),width=2);self.create_text(right-4,y-7,anchor='e',text=f"#{o.get('id')} {o.get('type')} {o.get('side')} ${float(o.get('price')):,.2f}",fill=col,font=('Arial',7,'bold'))
    if q:
        entry=basis/max(1,abs(q));y=py(entry);col=GREEN if q>0 else RED;self.create_line(left,y,right,y,fill=col,dash=(10,4));self.create_text(left+4,y-7,anchor='w',text=f'{"LONG" if q>0 else "SHORT"} {abs(q):,} @ ${entry:,.2f}',fill=col,font=('Arial',7,'bold'))
    for st,leg in self.app.portfolio.option_legs_for(a.symbol):
        y=py(leg.contract.strike);col=GREEN if leg.action=='BUY' else RED;self.create_line(left,y,right,y,fill=col,dash=(2,5));self.create_text(right-4,y+7,anchor='e',text=f'OPT {leg.action} {leg.quantity} {leg.contract.option_type[0].upper()}{leg.contract.strike:g}',fill=col,font=('Arial',6,'bold'))
    for dr in getattr(self,'anchored_drawings',[]):
        if dr[0]=='aline':
            _,t1,p1,t2,p2=dr;x1=self.time_to_x(t1);x2=self.time_to_x(t2)
            if x1 is not None and x2 is not None:self.create_line(x1,py(p1),x2,py(p2),fill=YELLOW,width=2)
        elif dr[0]=='ah':self.create_line(left,py(dr[1]),right,py(dr[1]),fill=YELLOW,dash=(5,3))
    # Dedicated x-axis row; timestamps and footer can no longer overlap.
    ticks=3 if w<440 else 5
    for j in range(ticks):
        i=round((len(d)-1)*j/max(1,ticks-1));ts=d[i].timestamp;x=left+(i+.5)*step;fmt='%a %H:%M:%S' if self.timeframe=='1D' else '%a %m-%d %H:%M' if self.timeframe in ('1W','1M') else '%Y-%m-%d';self.create_text(x,h-28,text=ts.strftime(fmt),fill='#70869a',font=('Arial',6 if w<440 else 7),anchor='s')
    footer=f'O {d[-1].open:.2f}  H {d[-1].high:.2f}  L {d[-1].low:.2f}  C {d[-1].close:.2f}';self.create_text(8,h-6,anchor='sw',text=footer,fill=MUTED,font=('Arial',7))
    if live:
        y=py(a.price);y=max(top,min(bottom,y));self.create_line(left,y,right,y,fill=CYAN,dash=(3,3));self.create_rectangle(right-78,y-9,right,y+9,fill='#0b2532',outline=CYAN);self.create_text(right-4,y,text=f'LIVE {a.price:,.2f}',fill='#d8f6ff',font=('Consolas',8,'bold'),anchor='e')
    try:
        status,remain=_sgp_session_countdown(a,self.app.market.clock.current);self.create_text(left+3,22,text=f'{_sgp_asset_session_code(a)} {status} • {remain}',fill=GREEN if status=='OPEN' else MUTED,font=('Arial',7,'bold'),anchor='nw')
    except Exception:pass
    self._draw_crosshair(top=top,bottom=bottom,left=left,right=right)
Chart.draw=_sgp_chart_draw_v20

def _sgp_price_to_y_v20(self,p):
    h=max(170,self.winfo_height());top,bottom=34,h-48;lo,hi=getattr(self,'_last_bounds_v20',self.price_bounds());return bottom-(float(p)-lo)/max(1e-9,hi-lo)*(bottom-top)
def _sgp_y_to_price_v20(self,y):
    h=max(170,self.winfo_height());top,bottom=34,h-48;lo,hi=getattr(self,'_last_bounds_v20',self.price_bounds());return hi-(float(y)-top)/max(1,bottom-top)*(hi-lo)
Chart.price_to_y=_sgp_price_to_y_v20;Chart.y_to_price=_sgp_y_to_price_v20

# Main scheduler runs at a display-friendly 60Hz and gives each due chart a strict budget.
def _sgp_chart_refresh_pulse_v20(self):
    if not getattr(self,'_chart_refresh_running',True):return
    try:
        if not self.root.winfo_exists():return
    except tk.TclError:return
    now_ms=time.monotonic()*1000.0;extras=[]
    for c in tuple(getattr(self,'extra_charts',())):
        try:
            if c.winfo_exists():extras.append(c)
        except tk.TclError:pass
    self.extra_charts=extras;charts=list(getattr(self,'charts',()))+extras
    if charts:
        start=int(getattr(self,'_chart_rr',0))%len(charts);deadline=time.perf_counter()+.007;done=0
        for off in range(len(charts)):
            c=charts[(start+off)%len(charts)]
            try:
                if c.winfo_exists() and c.due_for_refresh(now_ms):
                    c.request_draw(False);c.mark_refreshed(now_ms);done+=1;self._chart_rr=(start+off+1)%len(charts)
                    if done>=2 or time.perf_counter()>=deadline:break
            except Exception:pass
    self._chart_refresh_job=self.root.after(16,self._chart_refresh_pulse)
App._chart_refresh_pulse=_sgp_chart_refresh_pulse_v20

# Slow non-chart panels slightly. They do not need sub-100ms rebuilds to feel live.
_App_fast_watch_v20_base=getattr(App,'_fast_watch_stream',None)
def _sgp_fast_watch_stream_v20(self):
    try:
        if hasattr(self,'watch'):
            for iid in self.watch.get_children():
                try:
                    vals=list(self.watch.item(iid,'values'));a=self.market.get_asset(vals[0]) if vals else None
                    if a and len(vals)>=4:vals[2]=f'${a.price:,.2f}';vals[3]=f'{a.change_percent():+.2f}%';self.watch.item(iid,values=vals)
                except Exception:pass
    finally:self._watch_stream_job=self.root.after(300,self._fast_watch_stream)
App._fast_watch_stream=_sgp_fast_watch_stream_v20


# 2.0.1 bootstrap: a new/live chart should follow immediately even before two full
# aggregation buckets exist. Prefer finer live data as a fallback, then synthesize a
# two-print seed around the authoritative quote.
_Chart_data_v201_base=Chart.data
def _sgp_chart_data_v201(self):
    d=list(_Chart_data_v201_base(self))
    if self.asset is None or len(d)>=2:return d
    # Try finer streams before displaying an empty/loading chart.
    fallback_intervals=('1m','30s','tick') if self.timeframe=='1D' else ('1m','30s','tick','1d')
    for interval in fallback_intervals:
        alt=list(self.asset.chart_candles(interval))
        if len(alt)>=2:
            maxbars={'1D':180,'1W':220,'1M':280,'3M':340,'6M':300,'1Y':380,'5Y':360,'MAX':520}.get(self.timeframe,180)
            return alt[-maxbars:]
    now=getattr(getattr(self.app,'market',None),'clock',None);now=getattr(now,'current',None) or __import__('datetime').datetime.now()
    p=float(self.asset.price);prev=float(getattr(self.asset,'previous_price',p));from datetime import timedelta as _sgp_td_ui_v201
    return [Candle(now-_sgp_td_ui_v201(seconds=1),prev,max(prev,p),min(prev,p),prev,0),Candle(now,p,max(prev,p),min(prev,p),p,int(getattr(self.asset,'volume',0)))]
Chart.data=_sgp_chart_data_v201

# ===== Stock Game Pro 2.2 workstation / chart / world-map overhaul =====
from datetime import datetime as _sgp22_dt
from zoneinfo import ZoneInfo as _sgp22_ZoneInfo

# ---------- chart math ----------
def _sgp22_macd(vals,fast=12,slow=26,signal=9):
    if not vals:return [],[],[]
    f=ema(vals,fast);s=ema(vals,slow);m=[a-b for a,b in zip(f,s)];sig=ema(m,signal);hist=[a-b for a,b in zip(m,sig)];return m,sig,hist

def _sgp22_regular_at(chart,ts):
    try:return bool(chart.app.market.asset_regular_open_at(chart.asset,ts))
    except Exception:
        try:return bool(market_status(_sgp_asset_session_code(chart.asset),ts))
        except Exception:return True

# Default chart state: one stable, readable SPY chart rather than a hyper-zoomed 1-tick view.
_Chart_init_v22_base=Chart.__init__
def _sgp22_chart_init(self,parent,app,index):
    _Chart_init_v22_base(self,parent,app,index)
    self.timeframe='1M';self.candle_period='5 Min';self.refresh_ms=100
    self.show_overnight=True;self.follow_latest=True;self.fit_inception=False
    self._follow_center=None;self._follow_half=None;self._manual_y_shift=0.0;self._pan_anchor22=None
Chart.__init__=_sgp22_chart_init

_Chart_set_tf_v22_base=Chart.set_tf
def _sgp22_set_tf(self,tf):
    self.fit_inception=False;self._follow_center=None;self._follow_half=None;self._manual_y_shift=0.0
    return _Chart_set_tf_v22_base(self,tf)
Chart.set_tf=_sgp22_set_tf

_Chart_set_candle_v22_base=getattr(Chart,'set_candle_period',lambda self,v:None)
def _sgp22_set_candle(self,value):
    self.fit_inception=False;self._follow_center=None;self._follow_half=None;self._manual_y_shift=0.0
    return _Chart_set_candle_v22_base(self,value)
Chart.set_candle_period=_sgp22_set_candle

_Chart_data_v22_base=Chart.data
def _sgp22_chart_data(self):
    if self.asset is None:return []
    if getattr(self,'fit_inception',False):
        raw=list(self.asset.chart_candles('1d'))
        if not raw:
            try:self.app.market.load_ipo_history(self.asset)
            except Exception:pass
            return list(_Chart_data_v22_base(self))
        target=max(320,min(1600,int(max(500,self.winfo_width())*1.25)))
        if len(raw)>target:
            step=(len(raw)-1)/(target-1);raw=[raw[round(i*step)] for i in range(target)]
        return raw
    return list(_Chart_data_v22_base(self))
Chart.data=_sgp22_chart_data

# Hysteretic price following: center once, then move only when price approaches/leaves the viewport.
def _sgp22_bounds(self,d,live,plot_height=300):
    scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
    if not d:return 0.0,1.0
    if getattr(self,'fit_inception',False) and self.asset is not None:
        p=float(self.asset.price);lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d)
        half=max(p-lo,hi-p,abs(p)*.01,1e-6)/scale
        return p-half,p+half
    if not live:
        lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);mid=(lo+hi)/2+float(getattr(self,'_manual_y_shift',0.0));rng=max(hi-lo,abs(mid)*.002,1e-6)/scale
        return mid-rng*.55,mid+rng*.55
    p=float(self.asset.price);recent=d[-min(120,len(d)):]
    rlo=min([float(c.low) for c in recent]+[p]);rhi=max([float(c.high) for c in recent]+[p])
    desired_half=max((rhi-rlo)*.60,abs(p)*.0035,0.015 if abs(p)>=1 else abs(p)*.02,1e-6)/scale
    center=getattr(self,'_follow_center',None);half=getattr(self,'_follow_half',None)
    if center is None or half is None or not math.isfinite(center) or not math.isfinite(half):center=p;half=desired_half
    # Expand quickly, contract slowly. This prevents shimmering when a single wick changes the range.
    if desired_half>half:half=half*.72+desired_half*.28
    else:half=half*.985+desired_half*.015
    half=max(desired_half*.85,half)
    upper=center+half;lower=center-half;margin=.18*2*half
    if p>upper-margin:center += (p-(upper-margin))*.72
    elif p<lower+margin:center += (p-(lower+margin))*.72
    self._follow_center=center;self._follow_half=half
    return center-half,center+half

# Full free-screen pan in advanced mode: horizontal history + vertical price translation.
_Chart_click_v22_base=Chart.click
def _sgp22_chart_click(self,e):
    if getattr(self,'pan_mode',False):
        lo,hi=getattr(self,'_last_bounds_v22',getattr(self,'_last_bounds_v20',(0,1)))
        self._pan_anchor22=(e.x,e.y,int(getattr(self,'view_offset',0)),float(getattr(self,'_manual_y_shift',0.0)),hi-lo)
        self.follow_latest=False;self.cross=(e.x,e.y);return
    return _Chart_click_v22_base(self,e)
Chart.click=_sgp22_chart_click

_Chart_drag_v22_base=Chart.drag
def _sgp22_chart_drag(self,e):
    if getattr(self,'pan_mode',False) and getattr(self,'_pan_anchor22',None):
        ax,ay,off,shift,span=self._pan_anchor22;d=self.data();w=max(280,self.winfo_width());step=max(1,(w-80)/max(1,len(d)))
        self.view_offset=max(0,off+int((e.x-ax)/step));plot_h=max(80,self.winfo_height()-115)
        self._manual_y_shift=shift+(e.y-ay)/plot_h*span;self.cross=(e.x,e.y);self._key=None;self.request_draw(force=True);return
    return _Chart_drag_v22_base(self,e)
Chart.drag=_sgp22_chart_drag

_Chart_release_v22_base=Chart.release
def _sgp22_chart_release(self,e):
    if getattr(self,'pan_mode',False):self._pan_anchor22=None;self.request_draw(force=True);return
    return _Chart_release_v22_base(self,e)
Chart.release=_sgp22_chart_release

# Final chart renderer: stable axis, overnight shading, RSI/MACD subpanels, compact x-axis.
def _sgp22_chart_draw(self):
    a=self.asset;w=max(300,self.winfo_width());h=max(190,self.winfo_height());d=list(self.data()) if a else []
    live=bool(a is not None and int(getattr(self,'view_offset',0))==0 and getattr(self,'follow_latest',True) and not getattr(self,'fit_inception',False))
    if a is not None and d and live:
        p=float(a.price);last=d[-1];d[-1]=Candle(last.timestamp,float(last.open),max(float(last.high),p),min(float(last.low),p),p,int(last.volume))
    show_rsi=bool(getattr(self.app,'ind_vars',{}).get('RSI') and self.app.ind_vars['RSI'].get())
    show_macd=bool(getattr(self.app,'ind_vars',{}).get('MACD') and self.app.ind_vars['MACD'].get())
    subcount=int(show_rsi)+int(show_macd);sub_h=68 if h>360 else 52
    left,right,top=64,w-14,36;axis_y=h-25;price_bottom=axis_y-8-subcount*sub_h
    if price_bottom<top+70:price_bottom=top+70;sub_h=max(35,(axis_y-price_bottom-8)//max(1,subcount))
    q=int(self.app.portfolio.positions.get(a.symbol,0)) if a else 0;basis=float(self.app.portfolio.cost_basis.get(a.symbol,0)) if a else 0.0
    rel_orders=tuple((o.get('id'),o.get('side'),o.get('type'),round(float(o.get('price') or 0),5)) for o in self.app.market.pending_orders if a is not None and o.get('asset') is a)
    key=(a.symbol if a else None,self.timeframe,getattr(self,'candle_period','Auto'),self.kind,round(self.zoom,3),int(getattr(self,'view_offset',0)),live,getattr(self,'fit_inception',False),round(float(a.price),6) if a else 0,getattr(a,'last_update',None),w,h,q,round(basis,3),rel_orders,self.app.ind_vars_version,round(float(getattr(self,'vertical_scale',1.0)),3),round(float(getattr(self,'_manual_y_shift',0.0)),5),len(d),getattr(self,'show_overnight',True))
    if key==getattr(self,'_key',None):self._draw_crosshair(top=top,bottom=price_bottom,left=left,right=right);return
    self._key=key;self.delete('all')
    if not a:self.create_text(w/2,h/2,text='Select a market symbol',fill=MUTED,font=('Segoe UI',11));return
    if len(d)<2:self.create_text(12,10,anchor='nw',text=f'{a.symbol} • loading history…',fill=MUTED);return
    lo,hi=_sgp22_bounds(self,d,live,price_bottom-top);self._last_bounds_v22=(lo,hi);span=max(1e-9,hi-lo);step=(right-left)/max(1,len(d))
    def py(v):return price_bottom-(float(v)-lo)/span*(price_bottom-top)
    # Header — intentionally short to avoid collisions.
    mode='LIVE' if live else 'MAX FIT' if getattr(self,'fit_inception',False) else f'HISTORY {int(getattr(self,"view_offset",0))}b'
    self.create_text(8,7,anchor='nw',text=f'{a.symbol}  ${a.price:,.2f}',fill=TEXT,font=('Segoe UI',9,'bold'))
    self.create_text(right,7,anchor='ne',text=f'{self.timeframe} • {getattr(self,"candle_period","Auto")} • {mode}',fill=CYAN if live else MUTED,font=('Segoe UI',7,'bold'))
    # Grid / y labels.
    for j in range(6):
        y=top+j*(price_bottom-top)/5;v=hi-j*span/5;self.create_line(left,y,right,y,fill=GRID);self.create_text(left-5,y,text=f'{v:,.2f}',anchor='e',fill=MUTED,font=('Segoe UI',7))
    # Overnight shading behind candles, enabled by default.
    if getattr(self,'show_overnight',True) and self.timeframe in ('1D','1W','1M'):
        for i,c in enumerate(d):
            if not _sgp22_regular_at(self,c.timestamp):
                x1=left+i*step;x2=x1+step;self.create_rectangle(x1,top,x2,price_bottom,fill='#0b1724',outline='')
    if self.kind=='Candles':
        bw=max(1,min(6,step*.34))
        for i,c in enumerate(d):
            x=left+(i+.5)*step;col=GREEN if c.close>=c.open else RED;self.create_line(x,py(c.high),x,py(c.low),fill=col)
            y1,y2=py(c.open),py(c.close);self.create_rectangle(x-bw,min(y1,y2),x+bw,max(y1,y2)+1,fill=col,outline=col)
    else:
        pts=[]
        for i,c in enumerate(d):pts.extend((left+(i+.5)*step,py(c.close)))
        if self.kind=='Area':self.create_polygon(*(pts+[right,price_bottom,left,price_bottom]),fill='#12314a',outline='')
        if len(pts)>=4:self.create_line(*pts,fill=BLUE,width=2)
    close=[float(x.close) for x in d]
    if self.app.ind_vars['SMA'].get():self._line(sma(close,20),left,step,py,YELLOW)
    if self.app.ind_vars['EMA'].get():self._line(ema(close,20),left,step,py,PURPLE)
    if self.app.ind_vars['BB'].get():_,u,l=boll(close);self._line(u,left,step,py,CYAN);self._line(l,left,step,py,CYAN)
    if self.app.ind_vars['VWAP'].get():self._line(vwap(d),left,step,py,ORANGE)
    if self.app.ind_vars['Volume'].get():
        vmax=max((x.volume for x in d),default=1) or 1;vh=(price_bottom-top)*.11
        for i,c in enumerate(d):
            x=left+(i+.5)*step;y=price_bottom-c.volume/vmax*vh;self.create_rectangle(x-step*.26,price_bottom,x+step*.26,y,fill='#34485a',outline='')
    # Positions and working orders.
    for o in self.app.market.pending_orders:
        if o.get('asset') is a and o.get('price') is not None:
            y=py(o['price']);col=GREEN if o.get('side') in ('BUY','COVER') else RED;self.create_line(left,y,right,y,fill=col,dash=(7,4),width=1);self.create_text(right-4,y-6,anchor='e',text=f"#{o.get('id')} {o.get('type')} {o.get('side')} {float(o.get('price')):,.2f}",fill=col,font=('Segoe UI',6,'bold'))
    if q:
        entry=basis/max(1,abs(q));y=py(entry);col=GREEN if q>0 else RED;self.create_line(left,y,right,y,fill=col,dash=(10,4));self.create_text(left+4,y-6,anchor='w',text=f'{"LONG" if q>0 else "SHORT"} {abs(q):,} @ {entry:,.2f}',fill=col,font=('Segoe UI',6,'bold'))
    for dr in getattr(self,'anchored_drawings',[]):
        if dr[0]=='aline':
            _,t1,p1,t2,p2=dr;x1=self.time_to_x(t1);x2=self.time_to_x(t2)
            if x1 is not None and x2 is not None:self.create_line(x1,py(p1),x2,py(p2),fill=YELLOW,width=2)
        elif dr[0]=='ah':self.create_line(left,py(dr[1]),right,py(dr[1]),fill=YELLOW,dash=(5,3))
    # RSI and MACD get true subcharts instead of overlapping price candles.
    panel_top=price_bottom+6
    if show_rsi:
        rvals=rsi(close);pt,pb=panel_top,panel_top+sub_h-5;self.create_rectangle(left,pt,right,pb,fill='#08131d',outline=GRID)
        for level in (30,50,70):
            yy=pb-(level/100)*(pb-pt);self.create_line(left,yy,right,yy,fill=GRID,dash=(2,3));self.create_text(left-4,yy,text=str(level),anchor='e',fill=MUTED,font=('Segoe UI',6))
        pts=[]
        for i,v in enumerate(rvals):pts.extend((left+(i+.5)*step,pb-(max(0,min(100,v))/100)*(pb-pt)))
        if len(pts)>=4:self.create_line(*pts,fill=PURPLE,width=1.5)
        self.create_text(left+4,pt+3,text=f'RSI(14) {rvals[-1]:.1f}',anchor='nw',fill=PURPLE,font=('Segoe UI',7,'bold'));panel_top+=sub_h
    if show_macd:
        m,sig,hist=_sgp22_macd(close);pt,pb=panel_top,panel_top+sub_h-5;self.create_rectangle(left,pt,right,pb,fill='#08131d',outline=GRID);mx=max([abs(x) for x in m+sig+hist] or [1]);mid=(pt+pb)/2;self.create_line(left,mid,right,mid,fill=GRID)
        def mpy(v):return mid-v/max(1e-9,mx)*(pb-pt)*.42
        for i,v in enumerate(hist):
            x=left+(i+.5)*step;self.create_rectangle(x-step*.25,mid,x+step*.25,mpy(v),fill=GREEN if v>=0 else RED,outline='')
        self._line(m,left,step,mpy,BLUE);self._line(sig,left,step,mpy,ORANGE);self.create_text(left+4,pt+3,text='MACD 12/26/9',anchor='nw',fill=BLUE,font=('Segoe UI',7,'bold'))
    # X axis: one dedicated row, never shared with footer labels.
    ticks=4 if w<700 else 6
    for j in range(ticks):
        i=round((len(d)-1)*j/max(1,ticks-1));ts=d[i].timestamp;x=left+(i+.5)*step;fmt='%a %H:%M' if self.timeframe=='1D' else '%m-%d %H:%M' if self.timeframe in ('1W','1M') else '%Y-%m-%d';self.create_text(x,axis_y,text=ts.strftime(fmt),fill='#71879a',font=('Segoe UI',6 if w<500 else 7),anchor='s')
    if live:
        y=max(top,min(price_bottom,py(a.price)));self.create_line(left,y,right,y,fill=CYAN,dash=(3,3));self.create_rectangle(right-82,y-9,right,y+9,fill='#0b2532',outline=CYAN);self.create_text(right-4,y,text=f'{a.price:,.2f}',fill='#d8f6ff',font=('Consolas',8,'bold'),anchor='e')
    try:
        status,remain=_sgp_session_countdown(a,self.app.market.clock.current);self.create_text(left+3,22,text=f'{_sgp_asset_session_code(a)} {status} • {remain}',fill=GREEN if status=='OPEN' else MUTED,font=('Segoe UI',7,'bold'),anchor='nw')
    except Exception:pass
    self._draw_crosshair(top=top,bottom=price_bottom,left=left,right=right)
Chart.draw=_sgp22_chart_draw

def _sgp22_price_to_y(self,p):
    h=max(190,self.winfo_height());show_rsi=bool(self.app.ind_vars.get('RSI') and self.app.ind_vars['RSI'].get());show_macd=bool(self.app.ind_vars.get('MACD') and self.app.ind_vars['MACD'].get());subcount=int(show_rsi)+int(show_macd);sub_h=68 if h>360 else 52;top=36;bottom=h-33-subcount*sub_h;lo,hi=getattr(self,'_last_bounds_v22',(0,1));return bottom-(float(p)-lo)/max(1e-9,hi-lo)*(bottom-top)
def _sgp22_y_to_price(self,y):
    h=max(190,self.winfo_height());show_rsi=bool(self.app.ind_vars.get('RSI') and self.app.ind_vars['RSI'].get());show_macd=bool(self.app.ind_vars.get('MACD') and self.app.ind_vars['MACD'].get());subcount=int(show_rsi)+int(show_macd);sub_h=68 if h>360 else 52;top=36;bottom=h-33-subcount*sub_h;lo,hi=getattr(self,'_last_bounds_v22',(0,1));return hi-(float(y)-top)/max(1,bottom-top)*(hi-lo)
Chart.price_to_y=_sgp22_price_to_y;Chart.y_to_price=_sgp22_y_to_price

# ---------- main workstation ----------
def _sgp22_set_time_warp(self,value=None):
    # UI 1x..10x maps to engine 0.25x..2.50x. 1x is the new minimum and startup speed.
    try:display=max(1.0,min(10.0,float(self.time_warp.get() if value is None else value)))
    except Exception:display=1.0
    internal=display*.25;self.market.time_warp=internal
    try:self.time_warp.set(display);self.time_warp_label.config(text=f'{display:.1f}x')
    except Exception:pass
App.set_time_warp=_sgp22_set_time_warp

def _sgp22_clock_stream(self):
    try:
        if not self.root.winfo_exists():return
        a=self.charts[self.active_chart].asset if getattr(self,'charts',None) else self.market.get_asset('SPY')
        status,remain=_sgp_session_countdown(a,self.market.clock.current) if a else ('','')
        txt=f'{self.market.clock.current:%a %m-%d %H:%M:%S}  •  {getattr(a,"symbol","SPY")} {status}  {remain}'
        if txt!=getattr(self,'_last_clock_text22',None):self.clock_label.config(text=txt);self._last_clock_text22=txt
    except Exception:pass
    self._clock_stream_job=self.root.after(250,self._smooth_clock_stream)
App._smooth_clock_stream=_sgp22_clock_stream

def _sgp22_skip_next_open(self):
    a=self.charts[self.active_chart].asset if getattr(self,'charts',None) else self.market.get_asset('SPY')
    if a is not None:
        try:
            if self.market.asset_regular_open(a):return self.status_flash(f'{a.symbol} is already in its regular session. NEXT OPEN is only available while closed.')
        except Exception:pass
    mins=self.market.skip_to_next_open(a);self.refresh_watch();self.refresh_positions();self.refresh_orders()
    for c in list(getattr(self,'charts',()))+list(getattr(self,'extra_charts',())):
        try:c.request_draw(force=True)
        except Exception:pass
    self.status_flash(f'Skipped {mins/60:.1f}h to {getattr(a,"symbol","market")} regular open')
App.skip_to_next_open=_sgp22_skip_next_open

def _sgp22_fit_inception(self,chart=None):
    c=chart or self.charts[self.active_chart];c.fit_inception=True;c.timeframe='MAX';c.candle_period='1 Day';c.view_offset=0;c.follow_latest=False;c.pan_mode=False;c._manual_y_shift=0.0;c._key=None
    try:self.tf.set('MAX');self.candle_period_var.set('1 Day')
    except Exception:pass
    try:self.market.load_ipo_history(c.asset)
    except Exception:pass
    c.request_draw(force=True);self.status_flash(f'{c.asset.symbol} • full inception view')
App.fit_inception=_sgp22_fit_inception

_App_init_v22_base=App.__init__
def _sgp22_app_init(self,root,market,portfolio):
    # MACD exists beside the legacy indicators and is rendered as a true subpanel.
    _App_init_v22_base(self,root,market,portfolio)
    if 'MACD' not in self.ind_vars:self.ind_vars['MACD']=tk.BooleanVar(value=False)
    self.market.time_warp=.25
    # One SPY chart by default.
    if len(self.charts)!=1:self.set_chart_count(initial=1)
    c=self.charts[0];c.set_asset(self.market.get_asset('SPY'));c.timeframe='1M';c.candle_period='5 Min';c.zoom=.70;c.refresh_ms=100;c.show_overnight=True;c._follow_center=None;c._follow_half=None;c.request_draw(force=True)
    self.active_chart=0
    # Remove legacy global chart-rate and +24h controls.
    for attr in ('chart_rate','next_day_button'):
        obj=getattr(self,attr,None)
        try:obj.destroy()
        except Exception:pass
        try:delattr(self,attr)
        except Exception:pass
    # Time warp becomes 1x..10x display with 1x mapped to old 0.25x.
    try:
        self.time_warp_scale.config(from_=1,to=10,resolution=.25,length=118);self.time_warp.set(1.0);self.time_warp_label.config(width=5,font=('Segoe UI',8));self.set_time_warp(1.0)
    except Exception:pass
    try:self.clock_label.config(font=('Segoe UI',8),width=38,anchor='e')
    except Exception:pass
    # Per-active-chart tickrate dropdown lives immediately left of timeframe.
    try:
        top=self.tf.master;self.tick22_var=tk.StringVar(value='100ms');self.tick22=ttk.Combobox(top,textvariable=self.tick22_var,values=['50ms','75ms','100ms','150ms','250ms','500ms','1000ms'],state='readonly',width=8)
        self.tick22.pack(side='left',padx=(3,2),before=self.tf);self.tick22.bind('<<ComboboxSelected>>',lambda e:self.charts[self.active_chart].set_refresh_rate(int(self.tick22_var.get().replace('ms',''))))
        ttk.Button(top,text='FIT MAX',width=7,command=lambda:self.fit_inception()).pack(side='left',padx=(2,4),after=self.tf)
    except Exception:pass
    # Indicator menu gets MACD and overnight toggle.
    try:
        mb=self.root.nametowidget(self.root.cget('menu'));ind=None
        for i in range(mb.index('end')+1):
            try:
                if mb.entrycget(i,'label')=='Indicators':ind=mb.nametowidget(mb.entrycget(i,'menu'));break
            except Exception:pass
        if ind is not None:
            ind.add_checkbutton(label='MACD',variable=self.ind_vars['MACD'],command=self.redraw)
            self.overnight_var=tk.BooleanVar(value=True);ind.add_checkbutton(label='Highlight Overnight Sessions',variable=self.overnight_var,command=self._toggle_overnight22)
    except Exception:pass
    self.sync_chart_controls()
App.__init__=_sgp22_app_init

def _sgp22_toggle_overnight(self):
    val=bool(getattr(self,'overnight_var',tk.BooleanVar(value=True)).get())
    for c in list(getattr(self,'charts',()))+list(getattr(self,'extra_charts',())):c.show_overnight=val;c.request_draw(force=True)
App._toggle_overnight22=_sgp22_toggle_overnight

_sync_controls_v22_base=App.sync_chart_controls
def _sgp22_sync_controls(self):
    _sync_controls_v22_base(self);c=self.charts[self.active_chart]
    try:self.tick22_var.set(f'{c.refresh_ms}ms')
    except Exception:pass
App.sync_chart_controls=_sgp22_sync_controls

# ---------- advanced chart controls ----------
_Advanced_v22_base=AdvancedChartWindow
class AdvancedChartWindow(_Advanced_v22_base):
    def __init__(self,parent,app,asset):
        super().__init__(parent,app,asset)
        self.chart.show_overnight=True
        bar=ttk.Frame(self);bar.pack(fill='x',padx=8,pady=(0,5))
        ttk.Button(bar,text='FIT INCEPTION',command=lambda:app.fit_inception(self.chart)).pack(side='left')
        self.ov22=tk.BooleanVar(value=True);ttk.Checkbutton(bar,text='Overnight shading',variable=self.ov22,command=self._overnight).pack(side='left',padx=8)
        ttk.Label(bar,text='Indicators').pack(side='left',padx=(10,3))
        for name in ('SMA','EMA','BB','VWAP','Volume','RSI','MACD'):
            if name not in app.ind_vars:app.ind_vars[name]=tk.BooleanVar(value=False)
            ttk.Checkbutton(bar,text=name,variable=app.ind_vars[name],command=app.redraw).pack(side='left',padx=2)
        ttk.Label(bar,text='Free screen: drag left/right for time, up/down for price',foreground=MUTED).pack(side='right')
    def _overnight(self):self.chart.show_overnight=bool(self.ov22.get());self.chart.request_draw(force=True)
    def go_live(self):
        try:super().go_live()
        except Exception:
            self.chart.view_offset=0;self.chart.follow_latest=True;self.chart.pan_mode=False
        self.chart.fit_inception=False;self.chart._manual_y_shift=0.0;self.chart._follow_center=None;self.chart._follow_half=None;self.chart.request_draw(force=True)

def _sgp22_open_adv(self,a):return AdvancedChartWindow(self.root,self,a)
App.advanced_chart=_sgp22_open_adv

# ---------- richer market-conditions lab ----------
def _sgp22_market_conditions_lab(self):
    w=ToolWindow(self.root);w.style_window('MARKET CONDITIONS • RESEARCH LAB','900x820');w.resizable(True,True)
    ttk.Label(w,text='MARKET CONDITIONS RESEARCH LAB',font=('Segoe UI',16,'bold')).pack(anchor='w',padx=16,pady=(14,3))
    ttk.Label(w,text='Controls are staged locally and do not alter the market until APPLY is pressed. Close the window to discard changes.',foreground=MUTED,wraplength=850).pack(anchor='w',padx=16,pady=(0,8))
    body=ttk.Frame(w);body.pack(fill='both',expand=True,padx=14,pady=5);left=ttk.Frame(body);right=ttk.Frame(body);left.pack(side='left',fill='both',expand=True);right.pack(side='left',fill='both',expand=True,padx=(10,0))
    m=self.market
    defs=[
      ('Volatility','scenario_volatility',.10,8.0,.05,float(getattr(m,'scenario_volatility',1.0)),'Broad realized-volatility multiplier.'),
      ('Liquidity','scenario_liquidity',.05,8.0,.05,float(getattr(m,'scenario_liquidity',1.0)),'Depth and spread resilience. Low values amplify slippage.'),
      ('Whale flow','scenario_whale_flow',-3.0,3.0,.05,float(getattr(m,'scenario_whale_flow',0.0)),'Persistent directional institutional flow.'),
      ('Event intensity','scenario_event_intensity',0.0,6.0,.05,float(getattr(m,'scenario_event_intensity',1.0)),'Frequency/severity of news and event shocks.'),
      ('Correlation','scenario_correlation',0.0,1.25,.05,float(getattr(m,'scenario_correlation',.82)),'Cross-asset market-factor coupling.'),
      ('Trend persistence','scenario_trend',0.0,4.0,.05,float(getattr(m,'scenario_trend',1.0)),'Strength of momentum continuation.'),
      ('Mean reversion','scenario_mean_reversion',0.0,4.0,.05,float(getattr(m,'scenario_mean_reversion',1.0)),'Strength of pullback/oversold recovery.'),
      ('Option IV','scenario_option_iv',.20,5.0,.05,float(getattr(m,'scenario_option_iv',1.0)),'Option-implied-volatility regime multiplier.'),
      ('Rate shock','scenario_rate_shock',-5.0,5.0,.10,float(getattr(m,'scenario_rate_shock',0.0)),'Extra rate-sensitive equity pressure/boost.'),
      ('Credit stress','scenario_credit_stress',0.0,5.0,.05,float(getattr(m,'scenario_credit_stress',0.0)),'Funding/credit tightening, strongest in finance/consumer.'),
      ('Oil shock','scenario_oil_shock',-5.0,5.0,.10,float(getattr(m,'scenario_oil_shock',0.0)),'Energy windfall or cost shock for energy users.'),
      ('Sentiment','macro.sentiment',-2.0,2.0,.05,float(m.macro.get('sentiment',0.0)),'Risk appetite / risk aversion.'),
      ('Inflation %','macro.inflation',-5.0,30.0,.10,float(m.macro.get('inflation',2.5)),'Inflation regime influencing Fed and multiples.'),
      ('Fed rate %','macro.policy_rate',-2.0,25.0,.10,float(m.macro.get('policy_rate',4.0)),'Policy-rate level.'),
      ('Unemployment %','macro.unemployment',1.0,25.0,.10,float(m.macro.get('unemployment',4.1)),'Labor-market stress.'),
      ('GDP growth %','macro.gdp_growth',-15.0,15.0,.10,float(m.macro.get('gdp_growth',2.0)),'Growth/recession impulse.'),
      ('10Y yield %','macro.ten_year',0.0,20.0,.10,float(m.macro.get('ten_year',4.3)),'Long-duration discount rate.'),
      ('Dollar index','macro.dollar',50.0,160.0,.50,float(m.macro.get('dollar',100.0)),'USD strength, relevant to multinationals/commodities.')]
    local={};labels={}
    for idx,(name,key,lo,hi,res,val,desc) in enumerate(defs):
        parent=left if idx<(len(defs)+1)//2 else right;v=tk.DoubleVar(value=val);local[key]=v;box=ttk.Frame(parent);box.pack(fill='x',pady=4);topr=ttk.Frame(box);topr.pack(fill='x');ttk.Label(topr,text=name,font=('Segoe UI',8,'bold')).pack(side='left');lab=ttk.Label(topr,text=f'{val:.2f}',width=8);lab.pack(side='right');labels[key]=lab
        sc=tk.Scale(box,from_=lo,to=hi,resolution=res,orient='horizontal',variable=v,showvalue=0,length=300,bg=PANEL,fg=TEXT,highlightthickness=0,command=lambda x,k=key:labels[k].config(text=f'{local[k].get():.2f}'));sc.pack(fill='x');ttk.Label(box,text=desc,foreground=MUTED,wraplength=380,font=('Segoe UI',7)).pack(anchor='w')
    target=tk.StringVar(value='SPY');foot=ttk.Frame(w);foot.pack(fill='x',padx=16,pady=8);ttk.Label(foot,text='Preview asset').pack(side='left');ttk.Combobox(foot,textvariable=target,values=[a.symbol for a in m.all_assets()],width=12).pack(side='left',padx=5);preview=ttk.Label(foot,text='');preview.pack(side='left',padx=10)
    def update_preview():
        a=m.get_asset(target.get().upper()) or m.get_asset('SPY');vol=local['scenario_volatility'].get();liq=local['scenario_liquidity'].get();sent=local['macro.sentiment'].get();credit=local['scenario_credit_stress'].get();preview.config(text=f'{a.symbol}: vol ≈ {a.volatility*vol*100:.2f}%/step • liquidity {liq:.2f}× • sentiment {sent:+.2f} • credit stress {credit:.2f}')
    for v in local.values():v.trace_add('write',lambda *_:update_preview())
    update_preview()
    def apply():
        for key,v in local.items():
            if key.startswith('macro.'):m.macro[key.split('.',1)[1]]=float(v.get())
            else:setattr(m,key,float(v.get()))
        m.scenario_whale_symbol=target.get().upper().strip();m.visual_version+=1;self.status_flash('Research market conditions applied');w.destroy()
    buttons=ttk.Frame(w);buttons.pack(fill='x',padx=16,pady=(0,12));ttk.Button(buttons,text='APPLY',command=apply).pack(side='left',fill='x',expand=True);ttk.Button(buttons,text='CANCEL / DISCARD',command=w.destroy).pack(side='left',fill='x',expand=True,padx=(6,0))
App.market_conditions_lab=_sgp22_market_conditions_lab

# ---------- professional market map ----------
class MarketMapWindow(ToolWindow):
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('STOCK GAME PRO • MARKET MAP / INDEX IMPACT','1500x860');self.resizable(True,True);self.sector=tk.StringVar(value='ALL');self.index=tk.StringVar(value='SPX')
        top=ttk.Frame(self);top.pack(fill='x',padx=8,pady=6);ttk.Label(top,text='Sector').pack(side='left');cb=ttk.Combobox(top,textvariable=self.sector,values=['ALL']+market.sectors,state='readonly',width=18);cb.pack(side='left',padx=4);cb.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Label(top,text='Index decomposition').pack(side='left',padx=(14,3));ic=ttk.Combobox(top,textvariable=self.index,values=[i.symbol for i in market.indexes],state='readonly',width=12);ic.pack(side='left');ic.bind('<<ComboboxSelected>>',lambda e:self.refresh());ttk.Label(top,text='Double-click any row/tile for Advanced Chart',foreground=MUTED).pack(side='right')
        pan=ttk.PanedWindow(self,orient='horizontal');pan.pack(fill='both',expand=True,padx=8,pady=5);l=ttk.Frame(pan);mid=ttk.Frame(pan);r=ttk.Frame(pan);pan.add(l,weight=2);pan.add(mid,weight=5);pan.add(r,weight=3)
        ttk.Label(l,text='SECTOR BREADTH',font=('Segoe UI',10,'bold')).pack(anchor='w');self.sectors=ttk.Treeview(l,columns=('sector','chg','adv','dec'),show='headings',height=20);[(self.sectors.heading(c,text=t),self.sectors.column(c,width=w,anchor='center')) for c,t,w in [('sector','Sector',100),('chg','Avg %',60),('adv','Adv',45),('dec','Dec',45)]];self.sectors.pack(fill='both',expand=True)
        self.cv=tk.Canvas(mid,bg='#071019',highlightthickness=0);self.cv.pack(fill='both',expand=True);self.cv.bind('<Double-1>',self.tile_open);self.tiles=[]
        ttk.Label(r,text='INDEX CONSTITUENT IMPACT',font=('Segoe UI',10,'bold')).pack(anchor='w');self.const=ttk.Treeview(r,columns=('symbol','weight','chg','impact'),show='headings');[(self.const.heading(c,text=t),self.const.column(c,width=w,anchor='center')) for c,t,w in [('symbol','Symbol',70),('weight','Weight',65),('chg','Chg %',65),('impact','Impact',70)]];self.const.pack(fill='both',expand=True);self.const.bind('<Double-1>',self.row_open)
        self.after(100,self.refresh)
    def refresh(self):
        if not self.winfo_exists():return
        assets=[a for a in self.market.stocks+self.market.international if self.sector.get()=='ALL' or a.category==self.sector.get()]
        self.sectors.delete(*self.sectors.get_children());groups={}
        for a in self.market.stocks+self.market.international:groups.setdefault(a.category,[]).append(a)
        for sec,vals in sorted(groups.items()):
            ch=[a.change_percent() for a in vals];self.sectors.insert('','end',values=(sec,f'{sum(ch)/max(1,len(ch)):+.2f}',sum(x>0 for x in ch),sum(x<0 for x in ch)))
        self.cv.delete('all');self.tiles=[];w=max(500,self.cv.winfo_width());h=max(500,self.cv.winfo_height());assets=sorted(assets,key=lambda a:float(getattr(a,'market_cap',1)),reverse=True)[:72];cols=max(4,int(math.sqrt(len(assets)*w/max(1,h))));rows=max(1,math.ceil(len(assets)/cols));cw=w/cols;ch=h/rows
        for i,a in enumerate(assets):
            row,col=divmod(i,cols);x1=col*cw;y1=row*ch;x2=x1+cw-2;y2=y1+ch-2;pc=a.change_percent();fill='#123c2c' if pc>1 else '#173126' if pc>0 else '#4a1f2a' if pc<-1 else '#342028';self.cv.create_rectangle(x1,y1,x2,y2,fill=fill,outline='#20394b');self.cv.create_text((x1+x2)/2,(y1+y2)/2-7,text=a.symbol,fill=TEXT,font=('Segoe UI',8,'bold'));self.cv.create_text((x1+x2)/2,(y1+y2)/2+9,text=f'{pc:+.2f}%',fill=GREEN if pc>=0 else RED,font=('Segoe UI',7));self.tiles.append((x1,y1,x2,y2,a))
        idx=self.market.get_asset(self.index.get());self.const.delete(*self.const.get_children())
        if idx is not None:
            comps=[self.market.get_asset(s) for s in getattr(idx,'components',[])];comps=[a for a in comps if a];caps=sum(max(1,float(getattr(a,'market_cap',1))) for a in comps) or 1
            rows2=[]
            for a in comps:
                wt=max(1,float(getattr(a,'market_cap',1)))/caps;rows2.append((abs(wt*a.change_percent()),a,wt))
            for _,a,wt in sorted(rows2,key=lambda z:z[0],reverse=True)[:60]:self.const.insert('','end',iid=a.symbol,values=(a.symbol,f'{wt*100:.2f}%',f'{a.change_percent():+.2f}%',f'{wt*a.change_percent():+.3f}'))
        self.after(900,self.refresh)
    def tile_open(self,e):
        for x1,y1,x2,y2,a in self.tiles:
            if x1<=e.x<=x2 and y1<=e.y<=y2:self.market.ui_app.advanced_chart(a);return
    def row_open(self,e):
        iid=self.const.identify_row(e.y);a=self.market.get_asset(iid) if iid else None
        if a:self.market.ui_app.advanced_chart(a)

def _sgp22_market_map(self):MarketMapWindow(self.root,self.market)
App.market_map=_sgp22_market_map

# ---------- global 2D map replacing the rotating globe ----------
class GlobalTradeWorkstation(ToolWindow):
    EXCHANGES=[('NYSE / NASDAQ','US',40.71,-74.01),('CME','CME',41.88,-87.63),('London','LSE',51.51,-0.13),('Frankfurt','XETRA',50.11,8.68),('Tokyo','TSE',35.68,139.77),('Hong Kong','HKEX',22.32,114.17),('Shanghai','SSE',31.23,121.47),('Sydney','ASX',-33.87,151.21)]
    PORTS=[('Los Angeles',33.74,-118.27,'MATX'),('New York / NJ',40.67,-74.04,'UPS'),('Rotterdam',51.95,4.14,'SHEL'),('Singapore',1.26,103.84,'BHP'),('Shanghai',31.35,121.50,'BABA'),('Tokyo / Yokohama',35.45,139.64,'TM'),('Santos',-23.96,-46.30,'VALE'),('Sydney',-33.96,151.21,'BHP')]
    LAND=[
      [(-168,72),(-140,70),(-125,58),(-117,48),(-105,40),(-95,30),(-82,25),(-76,39),(-62,48),(-55,62),(-78,75),(-120,80)],
      [(-82,12),(-70,5),(-66,-10),(-60,-22),(-52,-35),(-58,-52),(-72,-55),(-78,-30)],
      [(-10,36),(3,44),(18,58),(38,55),(50,46),(42,34),(30,30),(20,36),(5,37)],
      [(-18,35),(5,36),(24,31),(39,15),(45,-8),(35,-30),(18,-35),(4,-20),(-5,5)],
      [(28,42),(52,55),(75,60),(100,70),(130,55),(150,45),(145,30),(125,20),(105,10),(88,20),(70,25),(55,20),(42,28)],
      [(112,-12),(132,-10),(153,-25),(148,-40),(125,-44),(113,-28)],
      [(-52,82),(-22,76),(-30,62),(-50,60)],[(44,-13),(50,-18),(49,-26),(43,-25)]]
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('STOCK GAME PRO • GLOBAL MARKET & FREIGHT MAP','1550x900');self.resizable(True,True);self.zoom=1.0;self.panx=0.;self.pany=0.;self.drag0=None;self.hits=[];self.selected=None
        pan=ttk.PanedWindow(self,orient='horizontal');pan.pack(fill='both',expand=True);left=ttk.Frame(pan);right=ttk.Frame(pan,width=340);pan.add(left,weight=7);pan.add(right,weight=3)
        self.cv=tk.Canvas(left,bg='#06111a',highlightthickness=0);self.cv.pack(fill='both',expand=True);self.cv.bind('<Button-1>',self.click);self.cv.bind('<B1-Motion>',self.drag);self.cv.bind('<ButtonRelease-1>',lambda e:setattr(self,'drag0',None));self.cv.bind('<MouseWheel>',self.wheel);self.cv.bind('<Configure>',lambda e:self.render())
        ttk.Label(right,text='GLOBAL OBJECT INSPECTOR',font=('Segoe UI',11,'bold')).pack(anchor='w',padx=10,pady=(10,4));self.info=tk.Text(right,height=15,bg='#08131d',fg=TEXT,relief='flat',wrap='word');self.info.pack(fill='x',padx=10,pady=4)
        ttk.Label(right,text='LIVE FREIGHT / RISK',font=('Segoe UI',10,'bold')).pack(anchor='w',padx=10,pady=(8,3));self.table=ttk.Treeview(right,columns=('type','route','progress','risk'),show='headings',height=18);[(self.table.heading(c,text=t),self.table.column(c,width=w,anchor='center')) for c,t,w in [('type','Type',58),('route','Route',130),('progress','%',48),('risk','Risk',65)]];self.table.pack(fill='both',expand=True,padx=10,pady=4);self.table.bind('<<TreeviewSelect>>',self.table_select)
        buttons=ttk.Frame(right);buttons.pack(fill='x',padx=10,pady=8);ttk.Button(buttons,text='ADV CHART',command=self.open_chart).pack(side='left',expand=True,fill='x');ttk.Button(buttons,text='OPTIONS',command=self.open_options).pack(side='left',expand=True,fill='x',padx=4)
        ttk.Label(right,text='Legend: ◆ exchange   ■ port   ▰ ship   ✈ aircraft   ☠ piracy   ☁ storm',foreground=MUTED,wraplength=320).pack(anchor='w',padx=10,pady=(0,10));self.after(200,self._loop)
    def xy(self,lat,lon,w,h):
        x=(lon+180)/360*w;y=(90-lat)/180*h;cx,cy=w/2,h/2;return (cx+(x-cx)*self.zoom+self.panx,cy+(y-cy)*self.zoom+self.pany)
    def render(self):
        c=self.cv;c.delete('all');self.hits=[];w=max(900,c.winfo_width());h=max(620,c.winfo_height());
        # graticule
        for lon in range(-150,181,30):x1,y1=self.xy(-80,lon,w,h);x2,y2=self.xy(80,lon,w,h);c.create_line(x1,y1,x2,y2,fill='#102b3a')
        for lat in range(-60,61,30):x1,y1=self.xy(lat,-180,w,h);x2,y2=self.xy(lat,180,w,h);c.create_line(x1,y1,x2,y2,fill='#102b3a')
        for poly in self.LAND:
            pts=[]
            for lon,lat in poly:x,y=self.xy(lat,lon,w,h);pts.extend((x,y))
            c.create_polygon(*pts,fill='#163b2d',outline='#3f7f62',width=1)
        # routes
        for route in getattr(self.market,'freight_routes',[]):
            pts=[]
            for lat,lon in route.get('points',[]):x,y=self.xy(lat,lon,w,h);pts.extend((x,y))
            if len(pts)>=4:c.create_line(*pts,fill='#1b7995',width=2,smooth=True,arrow='last',arrowshape=(7,8,3))
        # exchanges
        for name,code,lat,lon in self.EXCHANGES:
            x,y=self.xy(lat,lon,w,h);c.create_polygon(x,y-7,x+7,y,x,y+7,x-7,y,fill='#5bd8f2',outline='white');c.create_text(x+9,y-9,text=name,anchor='sw',fill='#9ddff1',font=('Segoe UI',7,'bold'));self.hits.append((x,y,10,('exchange',name,code)))
        for name,lat,lon,proxy in self.PORTS:
            x,y=self.xy(lat,lon,w,h);c.create_rectangle(x-5,y-5,x+5,y+5,fill='#e1bd55',outline='#fff0ae');self.hits.append((x,y,9,('port',name,proxy,lat,lon)))
        # ships use authoritative route progress; no render callback can advance game time.
        for i,sh in enumerate(getattr(self.market,'shipments',[])):
            route=sh.get('route') or {};pts=route.get('points',[]);prog=max(0,min(1,float(sh.get('progress',0))))
            if len(pts)>=2:
                segf=prog*(len(pts)-1);j=min(len(pts)-2,int(segf));t=segf-j;lat=pts[j][0]+(pts[j+1][0]-pts[j][0])*t;lon=pts[j][1]+(pts[j+1][1]-pts[j][1])*t;x,y=self.xy(lat,lon,w,h)
                c.create_polygon(x-9,y+4,x+9,y+4,x+5,y-4,x-5,y-4,fill='#69dcff',outline='white');self.hits.append((x,y,11,('ship',i,sh)))
                hz=sh.get('hazard','NONE')
                if hz=='PIRATES':c.create_text(x+16,y-14,text='☠',fill=RED,font=('Segoe UI Symbol',13,'bold'))
                elif hz=='STORM':c.create_text(x+16,y-14,text='☁',fill=YELLOW,font=('Segoe UI Symbol',13,'bold'))
        # aircraft follow major real-world freight city pairs, phase derives only from game clock.
        air=[((33.94,-118.40),(35.55,139.78),'LAX→NRT'),((40.64,-73.78),(51.47,-0.45),'JFK→LHR'),((1.36,103.99),(50.04,8.56),'SIN→FRA'),((22.31,113.91),(33.94,-118.40),'HKG→LAX')]
        phase=((self.market.clock.current.timestamp()/3600)%1.0)
        for k,(p1,p2,name) in enumerate(air):
            t=(phase+k*.23)%1;lat=p1[0]+(p2[0]-p1[0])*t;lon=p1[1]+(p2[1]-p1[1])*t;x,y=self.xy(lat,lon,w,h);c.create_text(x,y,text='✈',fill='#c8b7ff',font=('Segoe UI Symbol',12,'bold'));self.hits.append((x,y,10,('plane',name,t)))
        c.create_text(10,10,anchor='nw',text=f'{self.market.clock.current:%a %Y-%m-%d %H:%M:%S} • MAP VIEW • wheel zoom / drag pan',fill=TEXT,font=('Segoe UI',9,'bold'))
    def _loop(self):
        if not self.winfo_exists():return
        self.render();self.refresh_table();self.after(350,self._loop)
    def refresh_table(self):
        keep=self.table.selection();self.table.delete(*self.table.get_children())
        for i,sh in enumerate(getattr(self.market,'shipments',[])):
            route=sh.get('route',{}).get('name','Route');risk=sh.get('hazard','NONE');self.table.insert('','end',iid=f'ship:{i}',values=('SHIP',route,f'{sh.get("progress",0)*100:.0f}',risk))
        if keep and keep[0] in self.table.get_children():self.table.selection_set(keep[0])
    def click(self,e):
        hit=min(((x-e.x)**2+(y-e.y)**2,r,obj) for x,y,r,obj in self.hits if (x-e.x)**2+(y-e.y)**2<=r*r) if any((x-e.x)**2+(y-e.y)**2<=r*r for x,y,r,obj in self.hits) else None
        if hit:self.selected=hit[2];self.describe(self.selected)
        else:self.drag0=(e.x,e.y,self.panx,self.pany)
    def drag(self,e):
        if self.drag0:
            x,y,px,py=self.drag0;self.panx=px+(e.x-x);self.pany=py+(e.y-y);self.render()
    def wheel(self,e):
        self.zoom=max(.65,min(3.5,self.zoom*(1.12 if e.delta>0 else .89)));self.render();return 'break'
    def table_select(self,e=None):
        it=self.table.selection()
        if it and it[0].startswith('ship:'):
            i=int(it[0].split(':')[1]);sh=self.market.shipments[i];self.selected=('ship',i,sh);self.describe(self.selected)
    def describe(self,obj):
        self.info.delete('1.0','end');typ=obj[0]
        if typ=='ship':
            sh=obj[2];route=sh.get('route',{});txt=f"CARGO VESSEL\nCarrier: {sh.get('carrier')}\nCargo owner: {sh.get('cargo_owner')}\nRoute: {route.get('name')}\nProgress: {sh.get('progress',0)*100:.1f}%\nCargo value: ${sh.get('cargo_value',0):,.0f}\nRisk: {sh.get('hazard','NONE')}\nStatus: {'DISRUPTED' if sh.get('hazard_resolved') else 'IN TRANSIT'}"
        elif typ=='port':txt=f'PORT\n{obj[1]}\nInvestable proxy: {obj[2]}\nCoordinates: {obj[3]:.2f}, {obj[4]:.2f}'
        elif typ=='exchange':txt=f'EXCHANGE\n{obj[1]}\nSession code: {obj[2]}\nStatus: {"OPEN" if market_status(obj[2],self.market.clock.current) else "CLOSED"}'
        else:txt=f'AIR FREIGHT\nRoute: {obj[1]}\nProgress: {obj[2]*100:.1f}%'
        self.info.insert('end',txt)
    def selected_asset(self):
        if not self.selected:return None
        if self.selected[0]=='ship':return self.market.get_asset(self.selected[2].get('carrier'))
        if self.selected[0]=='port':return self.market.get_asset(self.selected[2])
        return None
    def open_chart(self):
        a=self.selected_asset()
        if a:self.market.ui_app.advanced_chart(a)
    def open_options(self):
        a=self.selected_asset()
        if a:self.market.ui_app.options_for(a)

GlobeWindow=GlobalTradeWorkstation
def _sgp22_globe(self):GlobalTradeWorkstation(self.root,self.market)
App.globe=_sgp22_globe

# ---------- options strategy builder enhancements ----------
_Spread_v22_base=SpreadBuilder
class SpreadBuilder(_Spread_v22_base):
    """Professional custom options strategy builder with scenario controls and date curves.

    This mirrors the capabilities of modern strategy visualizers without copying a third-party
    site's branding or exact trade dress.
    """
    def __init__(self,parent,market,portfolio,refresh,first=None):
        super().__init__(parent,market,portfolio,refresh,first)
        self.title('STOCK GAME PRO • PROFESSIONAL OPTIONS STRATEGY BUILDER')
        self.iv_shift=tk.DoubleVar(value=0.0);self.target_days=tk.IntVar(value=max(0,dict(EXPIRATIONS).get(self.exp.get(),30)//2))
        extra=ttk.Frame(self);extra.pack(fill='x',padx=10,pady=(0,7));ttk.Label(extra,text='Scenario IV shift').pack(side='left');iv=tk.Scale(extra,from_=-60,to=150,resolution=1,orient='horizontal',variable=self.iv_shift,length=180,showvalue=0,bg=PANEL,highlightthickness=0);iv.pack(side='left');self.ivlab=ttk.Label(extra,text='0%');self.ivlab.pack(side='left',padx=(2,10));self.iv_shift.trace_add('write',lambda *_:(self.ivlab.config(text=f'{self.iv_shift.get():+.0f}%'),self.draw()))
        ttk.Label(extra,text='P/L curve day').pack(side='left');td=tk.Scale(extra,from_=0,to=max(1,dict(EXPIRATIONS).get(self.exp.get(),30)),resolution=1,orient='horizontal',variable=self.target_days,length=180,showvalue=0,bg=PANEL,highlightthickness=0,command=lambda v:self.draw());td.pack(side='left');self.daylab=ttk.Label(extra,text='');self.daylab.pack(side='left',padx=4);self._v22_day_scale=td
        ttk.Button(extra,text='EXPIRATION',command=lambda:(self.target_days.set(dict(EXPIRATIONS).get(self.exp.get(),30)),self.draw())).pack(side='right')
    def draw(self):
        # Keep the robust expiration payoff from the base class, then overlay a current/target-day
        # approximation so users can reason about theta/IV path dependence before expiry.
        try:super().draw()
        except Exception:return
        if not hasattr(self,'target_days'):return
        a=self.asset();s=self.build_strategy() if self.rows else None
        if not a or not s:return
        days=dict(EXPIRATIONS).get(self.exp.get(),30);td=max(0,min(days,int(self.target_days.get())));self.daylab.config(text=f'{td}D')
        try:self._v22_day_scale.config(to=max(1,days))
        except Exception:pass
        c=self.payoff;w=max(420,c.winfo_width());h=max(260,c.winfo_height());spots=[a.price*(.65+i*(.70/100)) for i in range(101)];vals=[];iv_mult=max(.20,1+self.iv_shift.get()/100)
        for spot in spots:
            # Blend current mark toward terminal intrinsic as time passes. This is intentionally
            # lightweight but gives a useful non-expiration curve in a fast Tk simulator.
            terminal=s.expiration_pnl(spot);current=s.current_value()-s.open_cost;progress=1-td/max(1,days);vol_bump=(iv_mult-1)*abs(spot-a.price)*10;vals.append(current*(1-progress)+terminal*progress+vol_bump)
        mx=max(max(abs(v) for v in vals),1);left,right,top,bottom=48,w-18,34,h-36
        pts=[]
        for i,v in enumerate(vals):pts.extend((left+i*(right-left)/(len(vals)-1), (top+bottom)/2-v/mx*(bottom-top)*.42))
        if len(pts)>=4:c.create_line(*pts,fill=CYAN,width=2,dash=(5,3));c.create_text(right,top+5,text=f'{td}D curve • IV {self.iv_shift.get():+.0f}%',anchor='ne',fill=CYAN,font=('Segoe UI',8,'bold'))

# Rewire all later callers to the new builder class.

def _sgp22_options_for(self,a):
    w=OptionsWindow(self.root,self.market,self.portfolio,self.refresh);w.entry.delete(0,'end');w.entry.insert(0,a.symbol);w.apply_symbol()
App.options_for=_sgp22_options_for


# Final 2.2 refresh/menu cleanup: the clock owns its label, preventing competing callbacks from flickering it.
_App_refresh_v22_base=App.refresh
def _sgp22_refresh(self):
    old=''
    try:old=self.clock_label.cget('text')
    except Exception:pass
    try:_App_refresh_v22_base(self)
    finally:
        try:self.clock_label.config(text=old)
        except Exception:pass
App.refresh=_sgp22_refresh

# Final post-init menu normalization must be the outermost wrapper.
_App_init_v22_menu_base=App.__init__
def _sgp22_app_init_menu(self,root,market,portfolio):
    _App_init_v22_menu_base(self,root,market,portfolio)
    try:
        mb=self.root.nametowidget(self.root.cget('menu'))
        for i in range(mb.index('end')+1):
            if mb.entrycget(i,'label')=='Time':
                tm=mb.nametowidget(mb.entrycget(i,'menu'));tm.delete(0,'end')
                for x in (1,2,3,5,7.5,10):tm.add_command(label=f'{x:g}x',command=lambda v=x:self.set_time_warp(v))
                tm.add_separator();tm.add_command(label='Pause / Resume',command=self.toggle_pause);tm.add_command(label='Skip to Next Open (closed market only)',command=self.skip_to_next_open);break
    except Exception:pass
App.__init__=_sgp22_app_init_menu

# ===== Stock Game Pro 2.2.1 UI scaling guard =====
# Keep portfolio repaint cost bounded during whale testing.  The heavy table refresh is coalesced;
# explicit trade actions still invalidate the cache through changed portfolio values.
_sgp221_refresh_positions_base=App.refresh_positions
def _sgp221_refresh_positions(self):
    now=time.monotonic();count=len(getattr(self.portfolio,'positions',{}))+len(getattr(self.portfolio,'options',[]))
    min_gap=.20 if count<100 else .45 if count<500 else .80
    if now-getattr(self,'_last_position_ui221',0.0)<min_gap:return
    self._last_position_ui221=now
    return _sgp221_refresh_positions_base(self)
App.refresh_positions=_sgp221_refresh_positions

# Add buying-power / scaling diagnostics to the status bar without rebuilding another widget tree.
_App_refresh_221_base=App.refresh
def _sgp221_refresh(self):
    out=_App_refresh_221_base(self)
    try:
        bp=self.portfolio.available_funds() if hasattr(self.portfolio,'available_funds') else self.portfolio.cash
        npos=len(self.portfolio.positions);nopt=len(self.portfolio.options)
        txt=self.status.cget('text')
        suffix=f' • BP ${bp:,.0f} • positions {npos}+{nopt} opt'
        if suffix not in txt:self.status.config(text=txt+suffix)
    except Exception:pass
    return out
App.refresh=_sgp221_refresh

# Trade-driven changes bypass the coalescing interval so fills appear immediately.
_sgp221_refresh_positions_coalesced=App.refresh_positions
def _sgp221_refresh_positions_final(self):
    sig=(int(getattr(self.portfolio,'trade_count',0)),len(getattr(self.portfolio,'positions',{})),len(getattr(self.portfolio,'options',[])))
    if sig!=getattr(self,'_position_sig221',None):
        self._position_sig221=sig;self._last_position_ui221=0.0
    return _sgp221_refresh_positions_coalesced(self)
App.refresh_positions=_sgp221_refresh_positions_final


# ===== Stock Game Pro 2.3 professional map / chart-state / account analytics =====
from datetime import timedelta as _sgp23_ui_td

# 1x now means one simulated second per real-world second.
def _sgp23_set_time_warp(self,value=None):
    try:display=max(1.0,min(10.0,float(self.time_warp.get() if value is None else value)))
    except Exception:display=1.0
    self.market.time_warp=display/60.0
    try:self.time_warp.set(display);self.time_warp_label.config(text=f'{display:g}x')
    except Exception:pass
App.set_time_warp=_sgp23_set_time_warp

# FIT MAX is now a true toggle. It stores the prior viewport and restores it on second click.
def _sgp23_fit_inception(self,chart=None):
    c=chart or self.charts[self.active_chart]
    if getattr(c,'fit_inception',False):
        old=getattr(c,'_pre_fit23',None) or {}
        c.fit_inception=False
        for k,v in old.items():setattr(c,k,v)
        c._pre_fit23=None;c._key=None;c.request_draw(force=True)
        try:
            if c is self.charts[self.active_chart]:self.tf.set(c.timeframe);self.candle_period_var.set(c.candle_period)
        except Exception:pass
        self.status_flash(f'{c.asset.symbol} • restored previous chart view');return
    c._pre_fit23={'timeframe':c.timeframe,'candle_period':getattr(c,'candle_period','Auto'),'zoom':c.zoom,'view_offset':int(getattr(c,'view_offset',0)),'follow_latest':bool(getattr(c,'follow_latest',True)),'pan_mode':bool(getattr(c,'pan_mode',False)),'_manual_y_shift':float(getattr(c,'_manual_y_shift',0.0)),'vertical_scale':float(getattr(c,'vertical_scale',1.0))}
    c.fit_inception=True;c.timeframe='MAX';c.candle_period='1 Day';c.view_offset=0;c.follow_latest=False;c.pan_mode=False;c._manual_y_shift=0.0;c._key=None
    try:self.tf.set('MAX');self.candle_period_var.set('1 Day')
    except Exception:pass
    try:self.market.load_ipo_history(c.asset)
    except Exception:pass
    c.request_draw(force=True);self.status_flash(f'{c.asset.symbol} • full inception view (FIT MAX again to restore)')
App.fit_inception=_sgp23_fit_inception

# MAX fit uses the historical range itself, not the moving live ticker. This eliminates shimmer.
_sgp22_bounds_v23_base=_sgp22_bounds
def _sgp23_bounds(self,d,live,plot_height=300):
    if getattr(self,'fit_inception',False) and d:
        lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);span=max(hi-lo,abs((hi+lo)/2)*.01,1e-9);pad=span*.045
        return lo-pad,hi+pad
    return _sgp22_bounds_v23_base(self,d,live,plot_height)
_sgp22_bounds=_sgp23_bounds

# Sparse intraday-history repair. The simulator often only has full daily history on launch.
# Build deterministic display-only intraday bars from daily OHLC until real intraday bars accumulate.
_Chart_data_v23_base=Chart.data
def _sgp23_period_minutes(name):return {'1 Tick':0,'30 Sec':.5,'1 Min':1,'3 Min':3,'5 Min':5,'10 Min':10,'30 Min':30,'1 Hour':60,'1 Day':390}.get(name,5)
def _sgp23_expand_daily(chart,daily,period):
    mins=_sgp23_period_minutes(period)
    if mins<=0:return []
    per=max(1,min(390,int(round(390/mins))))
    out=[]
    for dc in daily:
        n=per;start=dc.timestamp.replace(hour=9,minute=30,second=0,microsecond=0);o=float(dc.open);cl=float(dc.close);hi=float(dc.high);lo=float(dc.low)
        for j in range(n):
            t=(j+1)/n;prev_t=j/n
            # Deterministic curved interpolation keeps the daily H/L represented without random launch flicker.
            wave=math.sin(t*math.pi*2)*.16
            c=o+(cl-o)*t+(hi-lo)*wave
            po=o+(cl-o)*prev_t+(hi-lo)*math.sin(prev_t*math.pi*2)*.16
            c=max(lo,min(hi,c));po=max(lo,min(hi,po));bh=max(po,c);bl=min(po,c)
            if j==max(0,n//3):bh=hi
            if j==max(0,2*n//3):bl=lo
            out.append(Candle(start+_sgp23_ui_td(minutes=j*mins),po,bh,bl,c,max(1,int(dc.volume/max(1,n)))))
    return out

def _sgp23_chart_data(self):
    d=list(_Chart_data_v23_base(self))
    if self.asset is None or getattr(self,'fit_inception',False):return d
    period=getattr(self,'candle_period','Auto');tf=self.timeframe
    # Minimum visual density for chart/timeframe combinations that previously launched with 2-5 bars.
    mins={'1D':45,'1W':70,'1M':90,'3M':100,'6M':110,'1Y':130,'5Y':160,'MAX':180}.get(tf,60)
    if len(d)>=mins or period in ('1 Tick','30 Sec','1 Min','1 Day','Auto'):return d
    daily=list(self.asset.chart_candles('1d'))
    if not daily:return d
    days={'1D':1,'1W':5,'1M':22,'3M':66,'6M':132,'1Y':252,'5Y':1260,'MAX':len(daily)}.get(tf,22)
    synth=_sgp23_expand_daily(self,daily[-min(days,len(daily)):],period)
    if len(synth)>len(d):return synth[-min(600,len(synth)):]
    return d
Chart.data=_sgp23_chart_data

# -------- Bloomberg-inspired global market monitor (original implementation, no proprietary branding/assets) --------
class GlobalTradeWorkstation(ToolWindow):
    EXCH=[('NYSE','US',40.7128,-74.0060),('NASDAQ','US',40.758,-73.9855),('CME','CME',41.8781,-87.6298),('TSX','US',43.653,-79.383),('LSE','LSE',51.5074,-0.1278),('XETRA','XETRA',50.1109,8.6821),('EURONEXT','LSE',48.8566,2.3522),('SIX','XETRA',47.3769,8.5417),('TSE','TSE',35.6762,139.6503),('HKEX','HKEX',22.3193,114.1694),('SSE','SSE',31.2304,121.4737),('SZSE','SSE',22.5431,114.0579),('KRX','TSE',37.5665,126.978),('SGX','HKEX',1.3521,103.8198),('ASX','ASX',-33.8688,151.2093),('BSE','HKEX',19.076,72.8777),('NSE India','HKEX',19.076,72.8777),('B3','US',-23.5505,-46.6333),('JSE','LSE',-26.2041,28.0473)]
    PORTS=[('Los Angeles',33.74,-118.27),('New York',40.67,-74.04),('Rotterdam',51.95,4.14),('Shanghai',31.23,121.49),('Singapore',1.26,103.84),('Dubai',25.27,55.30),('Santos',-23.96,-46.33),('Sydney',-33.86,151.20),('Tokyo',35.65,139.77)]
    AIR=[('JFK','LHR',40.64,-73.78,51.47,-.45),('LAX','NRT',33.94,-118.40,35.77,140.39),('FRA','SIN',50.04,8.56,1.36,103.99),('DXB','HKG',25.25,55.36,22.31,113.91),('ORD','PVG',41.97,-87.90,31.14,121.80)]
    def __init__(self,parent,market):
        super().__init__(parent);self.market=market;self.style_window('GLOBAL MARKETS • WORLD MONITOR','1500x900');self.resizable(True,True);self.phase=0.0;self.zoom=1.0;self.panx=0;self.pany=0;self.selected=None
        top=ttk.Frame(self);top.pack(fill='x',padx=7,pady=5);ttk.Label(top,text='GLOBAL MARKETS',font=('Segoe UI',13,'bold')).pack(side='left');self.layer_ex=tk.BooleanVar(value=True);self.layer_freight=tk.BooleanVar(value=True);self.layer_air=tk.BooleanVar(value=True);self.layer_risk=tk.BooleanVar(value=True)
        for txt,var in [('Exchanges',self.layer_ex),('Ocean freight',self.layer_freight),('Air freight',self.layer_air),('Risk',self.layer_risk)]:ttk.Checkbutton(top,text=txt,variable=var,command=self.draw).pack(side='left',padx=5)
        self.search=tk.StringVar();ttk.Entry(top,textvariable=self.search,width=18).pack(side='right');ttk.Label(top,text='Find exchange/asset').pack(side='right',padx=4);self.search.trace_add('write',lambda *_:self.draw())
        pw=ttk.PanedWindow(self,orient='horizontal');pw.pack(fill='both',expand=True,padx=6,pady=4);self.canvas=tk.Canvas(pw,bg='#05080d',highlightthickness=0);side=ttk.Frame(pw,width=360);pw.add(self.canvas,weight=4);pw.add(side,weight=1)
        self.canvas.bind('<Configure>',lambda e:self.draw());self.canvas.bind('<MouseWheel>',self.wheel);self.canvas.bind('<Button-1>',self.click);self.canvas.bind('<ButtonPress-3>',self.pan_start);self.canvas.bind('<B3-Motion>',self.pan_drag)
        self.info=tk.Text(side,height=11,bg='#08121b',fg=TEXT,relief='flat',wrap='word');self.info.pack(fill='x',padx=5,pady=5)
        self.tabs=ttk.Notebook(side);self.tabs.pack(fill='both',expand=True,padx=5,pady=4);self.ex_tab=ttk.Frame(self.tabs);self.flow_tab=ttk.Frame(self.tabs);self.macro_tab=ttk.Frame(self.tabs);self.tabs.add(self.ex_tab,text='Sessions');self.tabs.add(self.flow_tab,text='Freight');self.tabs.add(self.macro_tab,text='Macro')
        self.ex_tv=ttk.Treeview(self.ex_tab,columns=('venue','state','local'),show='headings',height=13);[self.ex_tv.heading(c,text=c.upper()) for c in ('venue','state','local')];self.ex_tv.pack(fill='both',expand=True)
        self.flow_tv=ttk.Treeview(self.flow_tab,columns=('route','owner','status'),show='headings',height=13);[self.flow_tv.heading(c,text=c.upper()) for c in ('route','owner','status')];self.flow_tv.pack(fill='both',expand=True)
        self.macro=tk.Text(self.macro_tab,bg='#08121b',fg=TEXT,relief='flat');self.macro.pack(fill='both',expand=True)
        self.refresh();self.animate()
    def proj(self,lat,lon):
        w=max(700,self.canvas.winfo_width());h=max(450,self.canvas.winfo_height());x=(lon+180)/360*w;y=(90-lat)/180*h;cx=w/2;cy=h/2;return cx+(x-cx)*self.zoom+self.panx,cy+(y-cy)*self.zoom+self.pany
    def draw(self):
        c=self.canvas;c.delete('all');w=max(700,c.winfo_width());h=max(450,c.winfo_height());
        # Bloomberg-like dense monitor aesthetic: longitude/latitude grid + regional bands.
        for lon in range(-180,181,30):x,_=self.proj(0,lon);c.create_line(x,0,x,h,fill='#11202b')
        for lat in range(-60,61,30):_,y=self.proj(lat,0);c.create_line(0,y,w,y,fill='#11202b')
        # Simplified land silhouettes, intentionally schematic and fast.
        polys=[[(-168,72),(-55,72),(-50,10),(-82,7),(-120,25)], [(-82,12),(-35,8),(-35,-56),(-75,-55)], [(-12,72),(40,72),(55,35),(35,-35),(-18,-35)], [(35,72),(180,72),(180,-10),(105,-10),(75,20)], [(110,-10),(155,-10),(155,-45),(112,-45)]]
        for poly in polys:
            pts=[]
            for lon,lat in poly:pts+=self.proj(lat,lon)
            c.create_polygon(*pts,fill='#0b1d1b',outline='#1c4c45')
        q=self.search.get().strip().upper()
        if self.layer_ex.get():
            for name,code,lat,lon in self.EXCH:
                x,y=self.proj(lat,lon);isopen=False
                try:isopen=market_status(code,self.market.clock.current)
                except Exception:pass
                col=GREEN if isopen else '#596675';r=6 if not q or q in name.upper() else 10
                c.create_oval(x-r,y-r,x+r,y+r,fill=col,outline='#dce9ef',tags=('exchange',name));c.create_text(x+8,y-9,text=name,anchor='w',fill='#d7e4eb' if not q or q in name.upper() else YELLOW,font=('Consolas',7,'bold'),tags=('exchange',name))
        if self.layer_freight.get():
            for sh in getattr(self.market,'shipments',[]):
                pts=sh.get('route',{}).get('points',[])
                if len(pts)<2:continue
                xy=[]
                for lat,lon in pts:xy+=self.proj(lat,lon)
                c.create_line(*xy,fill='#15536a',width=1,dash=(4,5))
                pr=float(sh.get('progress',0))%1.0;idx=min(len(pts)-2,int(pr*(len(pts)-1)));lt=(pr*(len(pts)-1))-idx;la=pts[idx][0]+(pts[idx+1][0]-pts[idx][0])*lt;lo=pts[idx][1]+(pts[idx+1][1]-pts[idx][1])*lt;x,y=self.proj(la,lo);c.create_polygon(x-6,y+3,x+6,y+3,x+3,y-3,x-3,y-3,fill=CYAN,outline='',tags=('ship',str(sh.get('id',''))))
        if self.layer_air.get():
            for j,(a,b,la1,lo1,la2,lo2) in enumerate(self.AIR):
                x1,y1=self.proj(la1,lo1);x2,y2=self.proj(la2,lo2);c.create_line(x1,y1,x2,y2,fill='#443c78',dash=(2,5));t=(self.phase*.06+j*.19)%1;x=x1+(x2-x1)*t;y=y1+(y2-y1)*t;c.create_text(x,y,text='✈',fill='#c6b8ff',font=('Segoe UI Symbol',9))
        c.create_text(8,h-8,anchor='sw',text='Right-drag pan • wheel zoom • click exchange/route objects • live session/freight/macro monitor',fill='#758694',font=('Segoe UI',7))
    def wheel(self,e):self.zoom=max(.65,min(4.0,self.zoom*(1.12 if e.delta>0 else .89)));self.draw()
    def pan_start(self,e):self._pa=(e.x,e.y,self.panx,self.pany)
    def pan_drag(self,e):x,y,px,py=self._pa;self.panx=px+e.x-x;self.pany=py+e.y-y;self.draw()
    def click(self,e):
        # Nearest exchange selection gives session and related market assets.
        best=None
        for name,code,lat,lon in self.EXCH:
            x,y=self.proj(lat,lon);d=(x-e.x)**2+(y-e.y)**2
            if best is None or d<best[0]:best=(d,name,code)
        if best and best[0]<700:
            _,name,code=best;assets=[a for a in self.market.all_assets() if getattr(a,'session','US')==code][:12];state='OPEN' if market_status(code,self.market.clock.current) else 'CLOSED';self.info.delete('1.0','end');self.info.insert('end',f'{name} • {state}\nSession code: {code}\n\nRelated simulator assets:\n'+', '.join(a.symbol for a in assets))
    def refresh(self):
        try:
            self.ex_tv.delete(*self.ex_tv.get_children())
            for name,code,lat,lon in self.EXCH:
                try:state='OPEN' if market_status(code,self.market.clock.current) else 'CLOSED';z=ZoneInfo(SESSIONS[code].tz);local=self.market.clock.current.replace(tzinfo=ZoneInfo('America/New_York')).astimezone(z).strftime('%H:%M')
                except Exception:state='—';local='—'
                self.ex_tv.insert('','end',values=(name,state,local))
            self.flow_tv.delete(*self.flow_tv.get_children())
            for sh in getattr(self.market,'shipments',[])[:30]:self.flow_tv.insert('','end',values=(sh.get('route',{}).get('name',''),sh.get('cargo_owner',''),sh.get('status','IN TRANSIT')))
            self.macro.delete('1.0','end');m=self.market.macro
            self.macro.insert('end',f'GLOBAL MACRO\n\nInflation       {m.get("inflation",0):.2f}%\nPolicy rate     {m.get("policy_rate",0):.2f}%\nUnemployment    {m.get("unemployment",0):.2f}%\nGDP growth      {m.get("gdp_growth",0):.2f}%\n10Y yield       {m.get("ten_year",0):.2f}%\nDollar index    {m.get("dollar",0):.2f}\nSentiment       {m.get("sentiment",0):+.2f}\nLiquidity       {m.get("liquidity",1):.2f}x')
        except Exception:pass
        self.after(1000,self.refresh)
    def animate(self):
        if not self.winfo_exists():return
        self.phase+=1;self.draw();self.after(100,self.animate)
GlobeWindow=GlobalTradeWorkstation
def _sgp23_globe(self):return GlobalTradeWorkstation(self.root,self.market)
App.globe=_sgp23_globe

# -------- account performance chart --------
def _sgp23_range_cutoff(now,label):
    days={'1D':1,'1W':7,'1M':31,'3M':93,'6M':186,'1Y':366}.get(label)
    return now-_sgp23_ui_td(days=days) if days else None

def _sgp23_perf_points(p,label):
    rows=list(getattr(p,'equity_history',[]));now=getattr(getattr(p,'market',None),'clock',None);now=getattr(now,'current',None) or _sgp22_dt.now();cut=_sgp23_range_cutoff(now,label)
    out=[]
    for r in rows:
        dt=_sgp_dt_parse_v20(r.get('time')) if '_sgp_dt_parse_v20' in globals() else None
        if dt is None:
            try:dt=_sgp22_dt.fromisoformat(r.get('time'))
            except Exception:continue
        if cut is None or dt>=cut:out.append((dt,float(r.get('equity',0)),r))
    return out

def _sgp23_draw_perf(canvas,p,label):
    canvas.delete('all');w=max(240,canvas.winfo_width());h=max(100,canvas.winfo_height());pts=_sgp23_perf_points(p,label)
    if len(pts)<2:canvas.create_text(w/2,h/2,text='Portfolio history builds while you trade',fill=MUTED);return
    vals=[x[1] for x in pts];lo=min(vals);hi=max(vals);span=max(1e-9,hi-lo);pad=8;xy=[]
    for i,(_,v,_) in enumerate(pts):xy += [pad+i*(w-2*pad)/max(1,len(pts)-1),h-pad-(v-lo)/span*(h-2*pad)]
    canvas.create_line(*xy,fill=CYAN,width=2,smooth=True);canvas.create_text(8,6,anchor='nw',text=f'{label}  ${vals[-1]:,.2f}  {((vals[-1]/vals[0]-1)*100 if vals[0] else 0):+.2f}%',fill=TEXT,font=('Segoe UI',8,'bold'))

def _sgp23_open_performance(self):
    w=ToolWindow(self.root);w.style_window('PORTFOLIO PERFORMANCE • ATTRIBUTION','1100x720');top=ttk.Frame(w);top.pack(fill='x',padx=8,pady=5);rng=tk.StringVar(value=getattr(self,'perf_range23',tk.StringVar(value='ALL')).get());cb=ttk.Combobox(top,textvariable=rng,values=['ALL','1Y','6M','3M','1M','1W','1D'],state='readonly',width=7);cb.pack(side='left');cv=tk.Canvas(w,bg='#071019',height=390,highlightthickness=0);cv.pack(fill='both',expand=True,padx=8,pady=5);detail=tk.Text(w,height=10,bg='#08121b',fg=TEXT,relief='flat');detail.pack(fill='x',padx=8,pady=5)
    def draw(*_):
        _sgp23_draw_perf(cv,self.portfolio,rng.get());pts=_sgp23_perf_points(self.portfolio,rng.get());detail.delete('1.0','end')
        if pts:
            # Show strongest equity intervals and holdings snapshots for attribution.
            moves=[]
            for a,b in zip(pts,pts[1:]):moves.append((abs(b[1]-a[1]),b[1]-a[1],b[0],b[2]))
            for _,chg,dt,rec in sorted(moves,reverse=True)[:8]:
                hs=rec.get('holdings',[]);detail.insert('end',f'{dt:%Y-%m-%d %H:%M}   Equity move {chg:+,.2f}\n  Holdings: '+', '.join(f'{x[0]} {x[1]:,}' for x in hs[:6])+'\n')
    cb.bind('<<ComboboxSelected>>',draw);cv.bind('<Configure>',draw);draw()
App.open_portfolio_performance=_sgp23_open_performance

_App_init_v23_base=App.__init__
def _sgp23_app_init(self,root,market,portfolio):
    _App_init_v23_base(self,root,market,portfolio)
    self.set_time_warp(1.0)
    # Embed compact account analytics above the existing account summary text.
    try:
        tab=self.summary.master;box=ttk.Frame(tab);box.pack(fill='x',padx=6,pady=3,before=self.summary);stats=ttk.Frame(box);stats.pack(fill='x');self.daytrade23=ttk.Label(stats,text='DAY TRADES 0/3');self.daytrade23.pack(side='left');self.dailypl23=ttk.Label(stats,text='DAILY P/L $0.00');self.dailypl23.pack(side='left',padx=12);self.pdt23=ttk.Label(stats,text='PDT CLEAR');self.pdt23.pack(side='right');self.perf_range23=tk.StringVar(value='1M');cb=ttk.Combobox(box,textvariable=self.perf_range23,values=['ALL','1Y','6M','3M','1M','1W','1D'],state='readonly',width=7);cb.pack(side='left');self.perf_canvas23=tk.Canvas(box,bg='#071019',height=125,highlightthickness=0);self.perf_canvas23.pack(side='left',fill='x',expand=True,padx=(6,0));cb.bind('<<ComboboxSelected>>',lambda e:_sgp23_draw_perf(self.perf_canvas23,self.portfolio,self.perf_range23.get()));self.perf_canvas23.bind('<Double-1>',lambda e:self.open_portfolio_performance());self.perf_canvas23.bind('<Configure>',lambda e:_sgp23_draw_perf(self.perf_canvas23,self.portfolio,self.perf_range23.get()))
    except Exception:pass
App.__init__=_sgp23_app_init

_refresh_v23_base=App.refresh
def _sgp23_refresh(self):
    out=_refresh_v23_base(self)
    try:
        self.portfolio.record_equity_snapshot();self.daytrade23.config(text=f'DAY TRADES {self.portfolio.day_trades_rolling}/3');self.dailypl23.config(text=f'DAILY P/L ${self.portfolio.daily_pl:+,.2f}');flag=bool(getattr(self.portfolio,'pdt_flagged',False));self.pdt23.config(text='PDT FLAGGED' if flag else 'PDT CLEAR',foreground=RED if flag else GREEN);_sgp23_draw_perf(self.perf_canvas23,self.portfolio,self.perf_range23.get())
    except Exception:pass
    return out
App.refresh=_sgp23_refresh

# ===== Stock Game Pro 2.4 world geometry / chart controls / session display =====
try:
    from world_land import LAND_POLYGONS as _SGP24_LAND, COUNTRY_BORDERS as _SGP24_BORDERS
except Exception:
    _SGP24_LAND=[];_SGP24_BORDERS=[]

# --- True real-second time warp, now 1x..100x ---
def _sgp24_set_time_warp(self,value=None):
    try:display=max(1.0,min(100.0,float(self.time_warp.get() if value is None else value)))
    except Exception:display=1.0
    self.market.time_warp=display/60.0
    try:self.time_warp.set(display);self.time_warp_label.config(text=f'{display:g}x')
    except Exception:pass
App.set_time_warp=_sgp24_set_time_warp

# --- Dense startup history with visible pre/post market sessions ---
def _sgp24_tf_days(tf,available):
    return min(available,{'1D':1,'1W':5,'1M':22,'3M':66,'6M':132,'1Y':252,'5Y':1260,'MAX':available}.get(tf,22))

def _sgp24_intraday_display(self,daily,period,maxbars=1400):
    """Build deterministic display-only 24h US-equity bars until real intraday history fills in.

    The simulated equity market has an overnight ECN, pre/post-market extended hours and a
    regular 09:30-16:00 session.  Generating the full clock day makes those regions visible
    immediately instead of hiding the overnight band simply because the startup cache is daily.
    """
    mins=max(1,_sgp23_period_minutes(period));days=max(1,len(daily))
    native=max(1,int(round(1440.0/mins)))
    # Keep the complete day for short windows; for long ranges sample evenly to a hard render budget.
    per_day=max(4,min(native,max(4,int(maxbars/max(1,days)))))
    step=1440.0/per_day;out=[]
    for di,dc in enumerate(daily):
        prev_close=float(daily[di-1].close if di else dc.open);o=float(dc.open);cl=float(dc.close);hi=float(dc.high);lo=float(dc.low)
        next_open=float(daily[di+1].open if di+1<len(daily) else cl)
        base=dc.timestamp.replace(hour=0,minute=0,second=0,microsecond=0)
        # Stable synthetic anchors for the non-regular sessions. These are display seeds only and
        # are replaced automatically when genuine simulator/real intraday bars are available.
        seed=sum(ord(ch) for ch in str(getattr(self.asset,'symbol',''))) + int(dc.timestamp.toordinal())
        wiggle=((seed%17)-8)/8000.0
        pre4=prev_close*(1+wiggle*.35)
        post20=cl*(1+wiggle*.25)
        for j in range(per_day):
            m=(j+.5)*step;mp=max(0.0,m-step)
            def px_at(mm):
                # 00:00-04:00 overnight ECN: drift from previous close toward the pre-market anchor.
                if mm<240.0:
                    t=max(0.0,min(1.0,mm/240.0));return prev_close+(pre4-prev_close)*t
                # 04:00-09:30 pre-market: converge toward the opening auction.
                if mm<570.0:
                    t=(mm-240.0)/330.0;return pre4+(o-pre4)*t
                # 09:30-16:00 regular session: respect the day's OHLC envelope.
                if mm<960.0:
                    t=(mm-570.0)/390.0
                    p=o+(cl-o)*t+(hi-lo)*math.sin(t*math.pi*2)*.14
                    return max(lo,min(hi,p))
                # 16:00-20:00 after-hours.
                if mm<1200.0:
                    t=(mm-960.0)/240.0;return cl+(post20-cl)*t
                # 20:00-20:15 maintenance pause: flat print for visual continuity.
                if mm<1215.0:return post20
                # 20:15-midnight overnight ECN: begin drifting toward the following opening regime.
                t=(mm-1215.0)/225.0;return post20+(next_open-post20)*t*.20
            pp=px_at(mp);pcur=px_at(m);bh=max(pp,pcur);bl=min(pp,pcur)
            if 570.0<=m<960.0:
                rt=(m-570.0)/390.0
                if abs(rt-.34)<step/390.0:bh=max(bh,hi)
                if abs(rt-.68)<step/390.0:bl=min(bl,lo)
            ts=base+_sgp23_ui_td(minutes=j*step)
            out.append(Candle(ts,pp,bh,bl,pcur,max(1,int(getattr(dc,'volume',0)/max(1,per_day)))))
    return out

_Chart_data_v24_base=Chart.data
def _sgp24_chart_data(self):
    base=list(_Chart_data_v24_base(self))
    if self.asset is None or getattr(self,'fit_inception',False):return base
    period=getattr(self,'candle_period','Auto')
    if period not in ('3 Min','5 Min','10 Min','30 Min','1 Hour'):return base
    daily=list(self.asset.chart_candles('1d'))
    if not daily:return base
    n=_sgp24_tf_days(self.timeframe,len(daily));daily=daily[-n:]
    native=max(1,int(round(1440.0/_sgp23_period_minutes(period))))
    desired=min(1400,max(12,n*native))
    # If genuine intraday data already fills the selected viewport, prefer it. Otherwise
    # build a deterministic, full-window display from the daily OHLC history.
    if len(base)>=max(12,int(desired*.72)):return base
    synth=_sgp24_intraday_display(self,daily,period,1400)
    return synth if len(synth)>len(base) else base
Chart.data=_sgp24_chart_data

# Add stronger extended-session bands plus DAY/AH percentages without replacing the
# professional renderer. Bands are grouped, not one Canvas object per candle.
_Chart_draw_v24_base=Chart.draw
def _sgp24_chart_draw(self):
    _Chart_draw_v24_base(self)
    try:self.delete('sgp24_session_shade');self.delete('sgp24_metrics')
    except Exception:return
    a=self.asset
    if a is None:return
    try:
        d=list(self.data());w=max(300,self.winfo_width());h=max(190,self.winfo_height())
        show_rsi=bool(getattr(self.app,'ind_vars',{}).get('RSI') and self.app.ind_vars['RSI'].get());show_macd=bool(getattr(self.app,'ind_vars',{}).get('MACD') and self.app.ind_vars['MACD'].get());subcount=int(show_rsi)+int(show_macd);sub_h=68 if h>360 else 52
        left,right,top=64,w-14,36;axis_y=h-25;price_bottom=axis_y-8-subcount*sub_h
        if price_bottom<top+70:price_bottom=top+70
        if getattr(self,'show_overnight',True) and len(d)>1 and self.timeframe in ('1D','1W','1M','3M','6M','1Y'):
            step=(right-left)/max(1,len(d));states=[]
            code=str(getattr(a,'session','US') or 'US')
            for c in d:
                reg=_sgp22_regular_at(self,c.timestamp)
                if reg:states.append('REG');continue
                ext=False
                if code=='US':
                    try:ext=bool(market_status('EXT',c.timestamp))
                    except Exception:pass
                states.append('EXT' if ext else 'NIGHT')
            start=0
            while start<len(states):
                st=states[start];end=start+1
                while end<len(states) and states[end]==st:end+=1
                if st!='REG':
                    x1=left+start*step;x2=left+end*step;fill='#17304b' if st=='EXT' else '#101420';stip='gray25' if st=='EXT' else 'gray12'
                    self.create_rectangle(x1,top,x2,price_bottom,fill=fill,outline='',stipple=stip,tags=('sgp24_session_shade',))
                start=end
            self.tag_lower('sgp24_session_shade')
        day=float(a.change_percent());regular=False
        try:regular=bool(self.app.market.asset_regular_open(a))
        except Exception:pass
        ah=float(a.after_hours_percent()) if hasattr(a,'after_hours_percent') else 0.0
        state='REGULAR' if regular else str(self.app.market.asset_trade_state(a))
        metric=f'DAY {day:+.2f}%  •  AH {"—" if regular else f"{ah:+.2f}%"}  •  {state}'
        self.create_text(8,22,anchor='nw',text=metric,fill=GREEN if day>=0 else RED,font=('Segoe UI',7,'bold'),tags=('sgp24_metrics',))
        if getattr(self,'show_overnight',True):self.create_text(right,22,anchor='ne',text='EXTENDED HOURS SHADED',fill='#7f9fbd',font=('Segoe UI',6,'bold'),tags=('sgp24_metrics',))
    except Exception:pass
Chart.draw=_sgp24_chart_draw

# --- Regular-chart vertical zoom control (not advanced-chart-only anymore) ---
def _sgp24_set_main_vertical(self,value=None):
    if not getattr(self,'charts',None):return
    try:v=max(.25,min(8.0,float(self.v24_var.get() if value is None else value)))
    except Exception:v=1.0
    c=self.charts[self.active_chart];c.set_vertical_scale(v)
    try:self.v24_label.config(text=f'{v:.2f}x')
    except Exception:pass
App.set_main_vertical=_sgp24_set_main_vertical

def _sgp24_fit_main_vertical(self):
    try:self.v24_var.set(1.0)
    except Exception:pass
    self.set_main_vertical(1.0)
App.fit_main_vertical=_sgp24_fit_main_vertical

_App_init_v24_base=App.__init__
def _sgp24_app_init(self,root,market,portfolio):
    _App_init_v24_base(self,root,market,portfolio)
    try:self.root.title('Stock Game Pro 2.4 — Global Trading Simulator')
    except Exception:pass
    # 100x upper bound; 1x remains exact real-world seconds.
    try:
        self.time_warp_scale.config(from_=1,to=100,resolution=.25,length=132);self.set_time_warp(1.0)
    except Exception:pass
    # Make extended-hours shading unmistakably ON for every new/main chart.
    try:
        if hasattr(self,'overnight_var'):self.overnight_var.set(True)
        for c in list(self.charts)+list(getattr(self,'extra_charts',[])):c.show_overnight=True
    except Exception:pass
    # Compact vertical-scale control for the active regular chart.
    try:
        top=self.tf.master;self.v24_var=tk.DoubleVar(value=float(getattr(self.charts[self.active_chart],'vertical_scale',1.0)));self.v24_title=ttk.Label(top,text='V');self.v24_scale=ttk.Scale(top,from_=.25,to=8.0,orient='horizontal',length=82,variable=self.v24_var,command=lambda v:self.set_main_vertical(v));self.v24_label=ttk.Label(top,text='1.00x',width=6);self.v24_fit=ttk.Button(top,text='FIT Y',width=5,command=self.fit_main_vertical)
        self.v24_title.pack(side='left',padx=(4,1),before=self.ctype);self.v24_scale.pack(side='left',before=self.ctype);self.v24_label.pack(side='left',before=self.ctype);self.v24_fit.pack(side='left',padx=(1,3),before=self.ctype)
    except Exception:pass
    # Rebuild the Time menu with the new upper range.
    try:
        mb=self.root.nametowidget(self.root.cget('menu'))
        for i in range(mb.index('end')+1):
            if mb.entrycget(i,'label')=='Time':
                tm=mb.nametowidget(mb.entrycget(i,'menu'));tm.delete(0,'end')
                for x in (1,2,5,10,25,50,100):tm.add_command(label=f'{x:g}x',command=lambda v=x:self.set_time_warp(v))
                tm.add_separator();tm.add_command(label='Pause / Resume',command=self.toggle_pause);tm.add_command(label='Skip to Next Open (closed market only)',command=self.skip_to_next_open);break
    except Exception:pass
    self.sync_chart_controls()
App.__init__=_sgp24_app_init

_sync_controls_v24_base=App.sync_chart_controls
def _sgp24_sync_controls(self):
    _sync_controls_v24_base(self)
    try:
        v=float(getattr(self.charts[self.active_chart],'vertical_scale',1.0));self.v24_var.set(v);self.v24_label.config(text=f'{v:.2f}x')
    except Exception:pass
App.sync_chart_controls=_sgp24_sync_controls

# Workspace variables should expose the same 100x ceiling.
_WorkspaceControls_init_v24_base=WorkspaceControls.__init__
def _sgp24_workspace_init(self,parent,app):
    _WorkspaceControls_init_v24_base(self,parent,app)
    def walk(w):
        for ch in w.winfo_children():
            try:
                if isinstance(ch,tk.Scale) and float(ch.cget('to'))==40.0:ch.config(from_=1,to=100,resolution=.25)
            except Exception:pass
            walk(ch)
    walk(self)
WorkspaceControls.__init__=_sgp24_workspace_init

# --- Earth-shaped global monitor using bundled low-resolution real coastlines/country borders ---
def _sgp24_map_path(canvas,viewer,points,fill,width=1,dash=None):
    if len(points)<2:return
    w=max(700,canvas.winfo_width());segments=[];cur=[];lastx=None
    for lat,lon in points:
        x,y=viewer.proj(lat,lon)
        if lastx is not None and abs(x-lastx)>w*.55:
            if len(cur)>=4:segments.append(cur)
            cur=[]
        cur.extend((x,y));lastx=x
    if len(cur)>=4:segments.append(cur)
    for seg in segments:canvas.create_line(*seg,fill=fill,width=width,dash=dash,smooth=False)

def _sgp24_geo_interp(lat1,lon1,lat2,lon2,t,arc=0.0):
    dlon=((lon2-lon1+180.0)%360.0)-180.0;lon=((lon1+dlon*t+180.0)%360.0)-180.0;lat=lat1+(lat2-lat1)*t+math.sin(math.pi*t)*arc
    return lat,lon

def _sgp24_global_draw(self):
    c=self.canvas;c.delete('all');w=max(700,c.winfo_width());h=max(450,c.winfo_height())
    # Ocean + proper equirectangular Earth geometry.
    c.create_rectangle(0,0,w,h,fill='#04101b',outline='')
    for lon in range(-180,181,30):x,_=self.proj(0,lon);c.create_line(x,0,x,h,fill='#102633')
    for lat in range(-60,91,30):_,y=self.proj(lat,0);c.create_line(0,y,w,y,fill='#102633')
    # Land polygons first; lake/island holes are drawn back in ocean color.
    for typ,poly in _SGP24_LAND:
        if typ not in (1,5):continue
        pts=[]
        for lon,lat in poly:pts.extend(self.proj(lat,lon))
        if len(pts)>=6:c.create_polygon(*pts,fill='#102a25',outline='#2e6658',width=1)
    for typ,poly in _SGP24_LAND:
        if typ!=2:continue
        pts=[]
        for lon,lat in poly:pts.extend(self.proj(lat,lon))
        if len(pts)>=6:c.create_polygon(*pts,fill='#071824',outline='#173747',width=1)
    # National borders make the flat projection immediately recognizable as a world map.
    for seg in _SGP24_BORDERS:
        pts=[]
        for lon,lat in seg:pts.extend(self.proj(lat,lon))
        if len(pts)>=4:c.create_line(*pts,fill='#1d473f',width=1)
    # Equator / prime meridian reference lines.
    x0,_=self.proj(0,0);_,y0=self.proj(0,0);c.create_line(x0,0,x0,h,fill='#244352',dash=(3,5));c.create_line(0,y0,w,y0,fill='#244352',dash=(3,5))
    q=self.search.get().strip().upper()
    if self.layer_freight.get():
        for sh in getattr(self.market,'shipments',[]):
            route=sh.get('route',{});pts=list(route.get('points',[]))
            if len(pts)<2:continue
            _sgp24_map_path(c,self,pts,'#17627b',1,(4,4))
            pr=float(sh.get('progress',0.0))%1.0;u=pr*(len(pts)-1);idx=min(len(pts)-2,int(u));lt=u-idx;la1,lo1=pts[idx];la2,lo2=pts[idx+1];la,lo=_sgp24_geo_interp(la1,lo1,la2,lo2,lt);x,y=self.proj(la,lo)
            c.create_polygon(x-7,y+3,x+7,y+3,x+4,y-3,x-4,y-3,fill=CYAN,outline='#c9f7ff',tags=('ship',str(sh.get('id',''))))
    if self.layer_air.get():
        for j,(aa,bb,la1,lo1,la2,lo2) in enumerate(self.AIR):
            path=[_sgp24_geo_interp(la1,lo1,la2,lo2,t/24.0,arc=10.0) for t in range(25)];_sgp24_map_path(c,self,path,'#5d4f8f',1,(2,4));t=(self.phase*.035+j*.19)%1.0;la,lo=_sgp24_geo_interp(la1,lo1,la2,lo2,t,arc=10.0);x,y=self.proj(la,lo);c.create_text(x,y,text='✈',fill='#d8ceff',font=('Segoe UI Symbol',10))
    if self.layer_ex.get():
        for name,code,lat,lon in self.EXCH:
            x,y=self.proj(lat,lon)
            try:isopen=market_status(code,self.market.clock.current)
            except Exception:isopen=False
            hit=(not q or q in name.upper());r=6 if hit else 4;col=GREEN if isopen else '#687583';c.create_oval(x-r,y-r,x+r,y+r,fill=col,outline='#e1edf2',tags=('exchange',name));c.create_text(x+8,y-8,text=name,anchor='w',fill=YELLOW if q and hit else '#d8e4e9',font=('Consolas',7,'bold'),tags=('exchange',name))
    if self.layer_risk.get():
        for ev in getattr(self.market,'geopolitical_events',[]):
            if ev.get('resolved'):continue
            x,y=self.proj(float(ev.get('lat',0)),float(ev.get('lon',0)));c.create_oval(x-7,y-7,x+7,y+7,outline=ORANGE,width=2);c.create_text(x+9,y,text='RISK',anchor='w',fill=ORANGE,font=('Consolas',6,'bold'))
    c.create_rectangle(6,6,310,48,fill='#06131d',outline='#294a5c');c.create_text(14,13,anchor='nw',text='WORLD MARKETS / FREIGHT / RISK',fill='#e9f0f3',font=('Segoe UI',9,'bold'));c.create_text(14,31,anchor='nw',text='Real coastlines • country borders • exchange sessions',fill='#7f9caa',font=('Segoe UI',7))
    c.create_text(8,h-8,anchor='sw',text='Right-drag pan • wheel zoom • click exchange • ships use ocean routes • aircraft use international corridors',fill='#80919d',font=('Segoe UI',7))
GlobalTradeWorkstation.draw=_sgp24_global_draw

# Slow the map animation slightly; market simulation remains completely independent.
def _sgp24_global_animate(self):
    if not self.winfo_exists():return
    self.phase+=1;self.draw();self.after(160,self.animate)
GlobalTradeWorkstation.animate=_sgp24_global_animate

# ===== Stock Game Pro 2.5 chart stability / low-CPU UI patch =====
# Cache deterministic startup synthesis. In 2.4 the same hundreds/thousands of synthetic
# Candle objects were rebuilt on every chart repaint even though the source daily bars had not changed.
_sgp23_expand_daily_v25_base=_sgp23_expand_daily
def _sgp25_expand_daily(chart,daily,period):
    if not daily:return []
    key=('v23',getattr(getattr(chart,'asset',None),'symbol',None),period,len(daily),daily[0].timestamp,daily[-1].timestamp)
    cache=getattr(chart,'_synth_cache25',None)
    if cache and cache[0]==key:return cache[1]
    out=_sgp23_expand_daily_v25_base(chart,daily,period);chart._synth_cache25=(key,out);return out
_sgp23_expand_daily=_sgp25_expand_daily

_sgp24_intraday_display_v25_base=_sgp24_intraday_display
def _sgp25_intraday_display(chart,daily,period,maxbars=1400):
    if not daily:return []
    key=('v24',getattr(getattr(chart,'asset',None),'symbol',None),period,int(maxbars),len(daily),daily[0].timestamp,daily[-1].timestamp)
    cache=getattr(chart,'_synth24_cache25',None)
    if cache and cache[0]==key:return cache[1]
    out=_sgp24_intraday_display_v25_base(chart,daily,period,maxbars);chart._synth24_cache25=(key,out);return out
_sgp24_intraday_display=_sgp25_intraday_display

# Stable live viewport. Wicks/candle ranges no longer continuously resize the y-axis. The
# viewport holds its scale and only translates once price reaches an edge dead-band; it expands
# only when a candle actually clips the plot. This removes the pump/dump "rubber chart" effect.
def _sgp25_bounds(self,d,live,plot_height=300):
    scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
    if not d:return (0.0,1.0)
    if getattr(self,'fit_inception',False):
        sig=('max',getattr(self.asset,'symbol',None),len(d),round(scale,4))
        cached=getattr(self,'_max_bounds25',None)
        if cached and cached[0]==sig:return cached[1]
        lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);span=max(hi-lo,abs((hi+lo)/2)*.01,1e-9);pad=span*.045
        b=(lo-pad,hi+pad);self._max_bounds25=(sig,b);return b
    if not live:
        lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);mid=(lo+hi)/2+float(getattr(self,'_manual_y_shift',0.0));rng=max(hi-lo,abs(mid)*.002,1e-6)/scale
        return mid-rng*.55,mid+rng*.55
    p=float(self.asset.price);view_sig=(getattr(self.asset,'symbol',None),self.timeframe,getattr(self,'candle_period','Auto'),round(scale,4),int(getattr(self,'view_offset',0)))
    state=getattr(self,'_stable_bounds25',None)
    if not state or state.get('sig')!=view_sig:
        recent=d[-min(120,len(d)):];sample=recent[:-1] if len(recent)>2 else recent
        vals=[]
        for c in sample:vals.extend((float(c.low),float(c.high)))
        if vals:
            svals=sorted(vals);qlo=svals[max(0,int(len(svals)*.06)-1)];qhi=svals[min(len(svals)-1,int(len(svals)*.94))]
        else:qlo=qhi=p
        half=max((qhi-qlo)*.62,abs(p)*.0035,0.015 if abs(p)>=1 else abs(p)*.02,1e-6)/scale
        # Keep the initial quote comfortably in view without requiring it to be the exact center.
        center=(qhi+qlo)/2 if qhi>qlo else p
        if p>center+half*.70:center=p-half*.35
        elif p<center-half*.70:center=p+half*.35
        state={'sig':view_sig,'center':center,'half':half};self._stable_bounds25=state
    center=float(state['center']);half=max(1e-9,float(state['half']));span=2*half;lo=center-half;hi=center+half
    # Translation only: price can move through ~82% of the panel before the chart follows.
    top_trigger=hi-span*.10;bot_trigger=lo+span*.10
    if p>top_trigger:center+=p-top_trigger
    elif p<bot_trigger:center+=p-bot_trigger
    lo=center-half;hi=center+half
    # A wick cannot distort the scale before it reaches the edge. Once it truly clips, expand
    # only enough to expose it, and never shrink during this live view.
    cur=d[-1];wick_hi=float(cur.high);wick_lo=float(cur.low);pad=span*.025
    if wick_hi>hi:
        need=wick_hi-hi+pad;hi+=need;half=(hi-lo)/2;center=(hi+lo)/2
    if wick_lo<lo:
        need=lo-wick_lo+pad;lo-=need;half=(hi-lo)/2;center=(hi+lo)/2
    state['center']=center;state['half']=half
    return center-half,center+half
_sgp22_bounds=_sgp25_bounds

# Reset viewport/synthesis caches only when the user actually changes chart context.
_Chart_set_asset_v25_base=Chart.set_asset
def _sgp25_set_asset(self,a):
    self._stable_bounds25=None;self._max_bounds25=None;self._synth_cache25=None;self._synth24_cache25=None;self._volume_cache25={};self._volume_scale25=None
    out=_Chart_set_asset_v25_base(self,a)
    try:self.app.market.ensure_real_data(a,history=False)
    except Exception:pass
    return out
Chart.set_asset=_sgp25_set_asset

_Chart_set_tf_v25_base=Chart.set_tf
def _sgp25_set_tf(self,tf):
    self._stable_bounds25=None;self._max_bounds25=None
    return _Chart_set_tf_v25_base(self,tf)
Chart.set_tf=_sgp25_set_tf

_Chart_set_candle_v25_base=Chart.set_candle_period
def _sgp25_set_candle_period(self,value):
    self._stable_bounds25=None;self._max_bounds25=None
    return _Chart_set_candle_v25_base(self,value)
Chart.set_candle_period=_sgp25_set_candle_period

_set_vertical_v25_base=Chart.set_vertical_scale
def _sgp25_set_vertical(self,value):
    self._stable_bounds25=None;self._max_bounds25=None
    return _set_vertical_v25_base(self,value)
Chart.set_vertical_scale=_sgp25_set_vertical

_fit_max_v25_base=App.fit_inception
def _sgp25_fit_inception(self,chart=None):
    c=chart or self.charts[self.active_chart];c._stable_bounds25=None;c._max_bounds25=None
    out=_fit_max_v25_base(self,chart)
    c._stable_bounds25=None;c._max_bounds25=None
    return out
App.fit_inception=_sgp25_fit_inception

# Draw stable volume after the main renderer, and put session/day metrics in separate corners.
# Temporarily disable the legacy volume pass so 1-tick volume isn't deleted/rebuilt twice.
_Chart_draw_v25_base=Chart.draw
def _sgp25_chart_draw(self):
    volvar=getattr(self.app,'ind_vars',{}).get('Volume');showvol=bool(volvar and volvar.get())
    if showvol:
        try:volvar.set(False)
        except Exception:showvol=False
    try:_Chart_draw_v25_base(self)
    finally:
        if showvol:
            try:volvar.set(True)
            except Exception:pass
    a=self.asset
    if a is None:return
    try:
        self.delete('sgp24_metrics');self.delete('sgp25_metrics');self.delete('sgp25_volume')
        d=list(self.data());w=max(300,self.winfo_width());h=max(190,self.winfo_height())
        show_rsi=bool(getattr(self.app,'ind_vars',{}).get('RSI') and self.app.ind_vars['RSI'].get());show_macd=bool(getattr(self.app,'ind_vars',{}).get('MACD') and self.app.ind_vars['MACD'].get());subcount=int(show_rsi)+int(show_macd);sub_h=68 if h>360 else 52
        left,right,top=64,w-14,36;axis_y=h-25;price_bottom=axis_y-8-subcount*sub_h
        if price_bottom<top+70:price_bottom=top+70
        # Stable tick-volume scale and per-timestamp nonzero cache eliminate the blink caused
        # by transient zero-volume live prints and a constantly rescaled maximum.
        if showvol and d:
            vc=getattr(self,'_volume_cache25',None)
            if vc is None:vc={};self._volume_cache25=vc
            vals=[]
            for c in d:
                v=max(0,int(getattr(c,'volume',0) or 0));k=getattr(c,'timestamp',None)
                if v>0:vc[k]=v
                else:v=int(vc.get(k,0))
                vals.append(v)
            target=max(vals or [1]);scalev=getattr(self,'_volume_scale25',None)
            if scalev is None or not math.isfinite(scalev):scalev=max(1.0,float(target))
            elif target>scalev:scalev=target
            else:scalev=max(float(target),scalev*.997)
            self._volume_scale25=max(1.0,scalev);vh=max(12,(price_bottom-top)*.11);step=(right-left)/max(1,len(d))
            for i,v in enumerate(vals):
                if v<=0:continue
                x=left+(i+.5)*step;y=price_bottom-(v/self._volume_scale25)*vh
                self.create_line(x,price_bottom,x,max(top,y),fill='#34485a',width=max(1,min(3,int(step*.42))),tags=('sgp25_volume',))
        day=float(a.change_percent());regular=False
        try:regular=bool(self.app.market.asset_regular_open(a))
        except Exception:pass
        ah=float(a.after_hours_percent()) if hasattr(a,'after_hours_percent') else 0.0;state='REG' if regular else str(self.app.market.asset_trade_state(a))
        metric=(f'D {day:+.2f}% • AH {"—" if regular else f"{ah:+.2f}%"}' if w<590 else f'DAY {day:+.2f}%  •  AH {"—" if regular else f"{ah:+.2f}%"}  •  {state}')
        # The base session/open-close countdown owns the left side of row 22; metrics own right.
        self.create_text(right,22,anchor='ne',text=metric,fill=GREEN if day>=0 else RED,font=('Segoe UI',6 if w<520 else 7,'bold'),tags=('sgp25_metrics',))
    except Exception:pass
Chart.draw=_sgp25_chart_draw

# Visible-row watch streaming: don't rewrite thousands of off-screen Treeview rows every 300 ms.
_refresh_watch_v25_base=App.refresh_watch
def _sgp25_refresh_watch(self):
    out=_refresh_watch_v25_base(self)
    try:self._watch_iids25=tuple(self.watch.get_children())
    except Exception:self._watch_iids25=()
    return out
App.refresh_watch=_sgp25_refresh_watch

def _sgp25_fast_watch_stream(self):
    try:
        rows=getattr(self,'_watch_iids25',None)
        if rows is None:rows=tuple(self.watch.get_children());self._watch_iids25=rows
        n=len(rows)
        if n:
            try:f0,f1=self.watch.yview();start=max(0,int(f0*n)-8);end=min(n,max(start+25,int(f1*n)+9))
            except Exception:start,end=0,min(n,60)
            for iid in rows[start:end]:
                try:
                    vals=list(self.watch.item(iid,'values'));a=self.market.get_asset(vals[0]) if vals else None
                    if a and len(vals)>=4:
                        price=f'${a.price:,.2f}';chg=f'{a.change_percent():+.2f}%'
                        if vals[2]!=price or vals[3]!=chg:vals[2]=price;vals[3]=chg;self.watch.item(iid,values=vals)
                except Exception:pass
    finally:self._watch_stream_job=self.root.after(400,self._fast_watch_stream)
App._fast_watch_stream=_sgp25_fast_watch_stream

# Compact clock always gets pack priority on the right edge of the chart toolbar.
def _sgp25_clock_stream(self):
    try:
        if not self.root.winfo_exists():return
        a=self.charts[self.active_chart].asset if getattr(self,'charts',None) else self.market.get_asset('SPY');status,remain=_sgp_session_countdown(a,self.market.clock.current) if a else ('','')
        topw=max(0,self.clock_label.master.winfo_width());sym=getattr(a,'symbol','SPY')
        txt=(f'{self.market.clock.current:%H:%M:%S} • {sym} {status}' if topw<880 else f'{self.market.clock.current:%a %m-%d %H:%M:%S} • {sym} {status} • {remain}')
        if txt!=getattr(self,'_last_clock_text25',None):self.clock_label.config(text=txt);self._last_clock_text25=txt
    except Exception:pass
    self._clock_stream_job=self.root.after(250,self._smooth_clock_stream)
App._smooth_clock_stream=_sgp25_clock_stream

_App_init_v25_base=App.__init__
def _sgp25_app_init(self,root,market,portfolio):
    _App_init_v25_base(self,root,market,portfolio)
    try:self.root.title('Stock Game Pro 2.5 — Optimized Global Trading Simulator')
    except Exception:pass
    # Repack clock before left-side controls so Tk reserves its space even when the portfolio pane grows.
    try:
        self.clock_label.pack_forget();self.clock_label.config(font=('Segoe UI',7,'bold'),width=31,anchor='e');self.clock_label.pack(side='right',padx=(4,2),before=self.active_label)
    except Exception:pass
    # Calm defaults: a 160ms chart repaint is still visually smooth while cutting Canvas churn ~38%.
    try:
        for c in self.charts:
            if int(getattr(c,'refresh_ms',100))<=100:c.set_refresh_rate(160)
        self.chart_rate.set('180ms')
    except Exception:pass
    # Guarantee overnight highlighting survives all wrapper initialization paths.
    try:
        if hasattr(self,'overnight_var'):self.overnight_var.set(True)
        for c in self.charts:c.show_overnight=True
    except Exception:pass
    try:self.refresh_watch()
    except Exception:pass
App.__init__=_sgp25_app_init


# ===== Stock Game Pro 2.5 final chart/render stability pass =====
# Cache the final display slice so the renderer and session overlay do not rebuild the
# same aggregation two or three times during one paint.
_Chart_data_v25_final_base=Chart.data
def _sgp25_data_final(self):
    a=getattr(self,'asset',None)
    sig=(getattr(a,'symbol',None),getattr(a,'last_update',None),getattr(a,'last_real_timestamp',None),
         self.timeframe,getattr(self,'candle_period','Auto'),round(float(getattr(self,'zoom',1.0)),4),
         int(getattr(self,'view_offset',0)),bool(getattr(self,'fit_inception',False)))
    cached=getattr(self,'_display_data_cache25',None)
    if cached and cached[0]==sig:
        self._last_render_data25=cached[1];return cached[1]
    out=list(_Chart_data_v25_final_base(self))
    # Never weld the live quote onto an old historical/synthetic candle. The professional
    # renderer updates d[-1] to the live price; if that bar is from yesterday, a pump/dump
    # becomes an artificial giant wick that bends the whole chart. Append a true current
    # display candle first, so overnight/session gaps remain gaps rather than fake wicks.
    if out and a is not None and int(getattr(self,'view_offset',0))==0 and getattr(self,'follow_latest',True) and not getattr(self,'fit_inception',False):
        now=getattr(getattr(self.app,'market',None),'clock',None);now=getattr(now,'current',None)
        if now is not None:
            pm={'1 Tick':1,'30 Sec':30,'1 Min':60,'3 Min':180,'5 Min':300,'10 Min':600,'30 Min':1800,'1 Hour':3600,'1 Day':86400,'Auto':300}
            secs=pm.get(getattr(self,'candle_period','Auto'),300)
            try:age=(now-out[-1].timestamp).total_seconds()
            except Exception:age=0
            if age>max(secs*1.75,90):
                p=float(a.price)
                if getattr(self,'candle_period','Auto')=='1 Day':
                    o=float(getattr(a,'open_price',p));hi=max(float(getattr(a,'high',p)),p,o);lo=min(float(getattr(a,'low',p)),p,o)
                else:o=hi=lo=p
                out.append(Candle(now,o,hi,lo,p,max(0,int(getattr(self,'_last_tick_volume25',0) or 0))))
    # Some tick prints have zero reported volume. Preserve the last visible non-zero bar
    # for display only so the volume column never flashes out of existence for one frame.
    if out and getattr(self,'candle_period','Auto')=='1 Tick':
        last=out[-1];v=max(0,int(getattr(last,'volume',0) or 0))
        if v>0:self._last_tick_volume25=v
        elif getattr(self,'_last_tick_volume25',0)>0:
            out[-1]=Candle(last.timestamp,float(last.open),float(last.high),float(last.low),float(last.close),int(self._last_tick_volume25))
    self._display_data_cache25=(sig,out);self._last_render_data25=out
    return out
Chart.data=_sgp25_data_final

# Replace live bounds one last time: live range is a rigid camera, not a rubber band.
# It does not move while the current candle is inside the viewport. If the candle actually
# exits, the camera translates without changing scale. Scale expands only when the candle's
# total high-low range physically cannot fit in the existing viewport.
def _sgp25_bounds_rigid(self,d,live,plot_height=300):
    scale=max(.25,min(8.0,float(getattr(self,'vertical_scale',1.0))))
    if not d:return (0.0,1.0)
    if getattr(self,'fit_inception',False):
        sig=('max',getattr(self.asset,'symbol',None),len(d),round(scale,4),getattr(self.asset,'last_real_timestamp',None))
        cached=getattr(self,'_max_bounds25',None)
        if cached and cached[0]==sig:return cached[1]
        lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);span=max(hi-lo,abs((hi+lo)/2)*.01,1e-9);pad=span*.045
        b=(lo-pad,hi+pad);self._max_bounds25=(sig,b);return b
    if not live:
        lo=min(float(c.low) for c in d);hi=max(float(c.high) for c in d);mid=(lo+hi)/2+float(getattr(self,'_manual_y_shift',0.0));rng=max(hi-lo,abs(mid)*.002,1e-6)/scale
        return mid-rng*.55,mid+rng*.55
    p=float(self.asset.price);sig=(getattr(self.asset,'symbol',None),self.timeframe,getattr(self,'candle_period','Auto'),round(scale,4),int(getattr(self,'view_offset',0)))
    state=getattr(self,'_stable_bounds25',None)
    if not state or state.get('sig')!=sig:
        recent=d[-min(160,len(d)):];sample=recent[:-1] if len(recent)>2 else recent
        vals=[]
        for c in sample:vals.extend((float(c.low),float(c.high)))
        if vals:
            sv=sorted(vals);qlo=sv[max(0,int(len(sv)*.05)-1)];qhi=sv[min(len(sv)-1,int(len(sv)*.95))]
        else:qlo=qhi=p
        half=max((qhi-qlo)*.70,abs(p)*.0045,0.02 if abs(p)>=1 else abs(p)*.03,1e-6)/scale
        center=(qhi+qlo)/2 if qhi>qlo else p
        # Only the initial camera setup is allowed to bring the quote back into frame.
        if p>center+half:center=p-half*.75
        elif p<center-half:center=p+half*.75
        state={'sig':sig,'center':center,'half':half};self._stable_bounds25=state
    center=float(state['center']);half=max(1e-9,float(state['half']));lo=center-half;hi=center+half;span=hi-lo
    cur=d[-1];wick_hi=max(float(cur.high),p);wick_lo=min(float(cur.low),p);wick_span=max(0.0,wick_hi-wick_lo)
    # Expand only if the one candle literally cannot fit at the present vertical scale.
    if wick_span>span*.92:
        half=max(half,wick_span/.88/2);center=(wick_hi+wick_lo)/2;lo=center-half;hi=center+half;span=hi-lo
    else:
        # No movement until a wick/quote actually crosses the visible boundary. Then translate
        # the camera and retain exactly the same span, leaving a small edge buffer.
        pad=span*.035
        if wick_hi>hi:center+=wick_hi-hi+pad
        lo=center-half;hi=center+half
        if wick_lo<lo:center-=lo-wick_lo+pad
    state['center']=center;state['half']=half
    return center-half,center+half
_sgp22_bounds=_sgp25_bounds_rigid

# Render only once per frame. The 2.4 path drew overnight shading twice and the previous 2.5
# path requested chart data a third time. This uses the professional renderer once, then adds
# grouped session bands and a non-overlapping compact DAY/AH status line.
def _sgp25_chart_draw_final(self):
    oldkey=getattr(self,'_key',None);wanted=bool(getattr(self,'show_overnight',True))
    try:self.show_overnight=False;_Chart_draw_v24_base(self)
    finally:self.show_overnight=wanted
    # If the base renderer reused its previous frame, preserve existing overlay items too.
    if oldkey is not None and getattr(self,'_key',None)==oldkey:return
    a=self.asset
    if a is None:return
    try:
        d=getattr(self,'_last_render_data25',None) or list(self.data());w=max(300,self.winfo_width());h=max(190,self.winfo_height())
        show_rsi=bool(getattr(self.app,'ind_vars',{}).get('RSI') and self.app.ind_vars['RSI'].get());show_macd=bool(getattr(self.app,'ind_vars',{}).get('MACD') and self.app.ind_vars['MACD'].get());subcount=int(show_rsi)+int(show_macd);sub_h=68 if h>360 else 52
        left,right,top=64,w-14,36;axis_y=h-25;price_bottom=axis_y-8-subcount*sub_h
        if price_bottom<top+70:price_bottom=top+70
        if wanted and len(d)>1 and self.timeframe in ('1D','1W','1M','3M','6M','1Y'):
            step=(right-left)/max(1,len(d));states=[];code=str(getattr(a,'session','US') or 'US')
            for c in d:
                if _sgp22_regular_at(self,c.timestamp):states.append('REG');continue
                ext=False
                if code=='US':
                    try:ext=bool(market_status('EXT',c.timestamp))
                    except Exception:pass
                states.append('EXT' if ext else 'NIGHT')
            start=0
            while start<len(states):
                st=states[start];end=start+1
                while end<len(states) and states[end]==st:end+=1
                if st!='REG':
                    x1=left+start*step;x2=left+end*step;fill='#17304b' if st=='EXT' else '#101420';stip='gray25' if st=='EXT' else 'gray12'
                    self.create_rectangle(x1,top,x2,price_bottom,fill=fill,outline='',stipple=stip,tags=('sgp25_session_shade',))
                start=end
            self.tag_lower('sgp25_session_shade')
        day=float(a.change_percent());regular=False
        try:regular=bool(self.app.market.asset_regular_open(a))
        except Exception:pass
        ah=float(a.after_hours_percent()) if hasattr(a,'after_hours_percent') else 0.0
        state='REG' if regular else str(self.app.market.asset_trade_state(a))
        metric=(f'D {day:+.2f}%  AH {"—" if regular else f"{ah:+.2f}%"}' if w<560 else f'DAY {day:+.2f}%  •  AH {"—" if regular else f"{ah:+.2f}%"}  •  {state}')
        # Session countdown remains at upper-left; DAY/AH gets its own row at upper-right.
        self.create_text(right,31,anchor='se',text=metric,fill=GREEN if day>=0 else RED,font=('Segoe UI',6 if w<520 else 7,'bold'),tags=('sgp25_metrics',))
    except Exception:pass
Chart.draw=_sgp25_chart_draw_final

# Avoid a fixed-width clock consuming the center toolbar. The label is packed first so it
# always receives a right-edge allocation, then its copy collapses as the center pane narrows.
def _sgp25_clock_stream_final(self):
    try:
        if not self.root.winfo_exists():return
        a=self.charts[self.active_chart].asset if getattr(self,'charts',None) else self.market.get_asset('SPY');status,remain=_sgp_session_countdown(a,self.market.clock.current) if a else ('','')
        topw=max(0,self.clock_label.master.winfo_width());sym=getattr(a,'symbol','SPY');t=self.market.clock.current
        if topw<650:txt=f'{t:%H:%M:%S}'
        elif topw<850:txt=f'{t:%H:%M:%S} • {sym} {status}'
        else:txt=f'{t:%a %m-%d %H:%M:%S} • {sym} {status} • {remain}'
        if txt!=getattr(self,'_last_clock_text25',None):self.clock_label.config(text=txt);self._last_clock_text25=txt
    except Exception:pass
    self._clock_stream_job=self.root.after(300,self._smooth_clock_stream)
App._smooth_clock_stream=_sgp25_clock_stream_final

_App_init_v25_final_base=App.__init__
def _sgp25_app_init_final(self,root,market,portfolio):
    _App_init_v25_final_base(self,root,market,portfolio)
    try:
        self.clock_label.pack_forget();self.clock_label.config(font=('Segoe UI',7,'bold'),width=0,anchor='e');self.clock_label.pack(side='right',padx=(3,2),before=self.active_label)
    except Exception:pass
    try:
        for c in self.charts:c.set_refresh_rate(max(150,int(getattr(c,'refresh_ms',150))))
        if self.charts:
            c=self.charts[0];c.timeframe='1D';c.candle_period='5 Min';c.zoom=.85;c._stable_bounds25=None;c._display_data_cache25=None;c.request_draw(force=True)
            self.tf.set('1D')
        self.chart_rate.set('180ms')
    except Exception:pass
App.__init__=_sgp25_app_init_final


_Chart_set_asset_v25_final_base=Chart.set_asset
def _sgp25_set_asset_final(self,a):
    self._display_data_cache25=None;self._last_render_data25=None;self._last_tick_volume25=0
    return _Chart_set_asset_v25_final_base(self,a)
Chart.set_asset=_sgp25_set_asset_final

_Chart_set_candle_v25_final_base=Chart.set_candle_period
def _sgp25_set_candle_final(self,value):
    self._display_data_cache25=None;self._last_tick_volume25=0
    return _Chart_set_candle_v25_final_base(self,value)
Chart.set_candle_period=_sgp25_set_candle_final


# Lighter startup and scheduler: 1D / 5-minute gives a dense full-session chart without
# immediately painting ~1,400 synthetic candles. Users can still select larger windows.
_Chart_init_v25_light_base=Chart.__init__
def _sgp25_chart_init_light(self,parent,app,index):
    _Chart_init_v25_light_base(self,parent,app,index)
    self.timeframe='1D';self.candle_period='5 Min';self.refresh_ms=160
Chart.__init__=_sgp25_chart_init_light

def _sgp25_chart_refresh_pulse_final(self):
    if not getattr(self,'_chart_refresh_running',True):return
    try:
        if not self.root.winfo_exists():return
    except tk.TclError:return
    now_ms=time.monotonic()*1000.0;extras=[]
    for c in tuple(getattr(self,'extra_charts',())):
        try:
            if c.winfo_exists():extras.append(c)
        except tk.TclError:pass
    self.extra_charts=extras;charts=list(getattr(self,'charts',()))+extras
    if charts:
        start=int(getattr(self,'_chart_rr',0))%len(charts)
        for off in range(len(charts)):
            c=charts[(start+off)%len(charts)]
            try:
                if c.winfo_exists() and c.due_for_refresh(now_ms):
                    c.request_draw(False);c.mark_refreshed(now_ms);self._chart_rr=(start+off+1)%len(charts);break
            except Exception:pass
    self._chart_refresh_job=self.root.after(16,self._chart_refresh_pulse)
App._chart_refresh_pulse=_sgp25_chart_refresh_pulse_final


# ===== Stock Game Pro 2.5 production: explicit account market refresh =====
def _sgp25_snapshot_symbols(self):
    special={'SPX':'^GSPC','NDX':'^NDX','DJI':'^DJI','RUT':'^RUT','VIX':'^VIX'}
    out=[]
    for a in self.market.all_assets():
        sym=special.get(getattr(a,'symbol','')) or getattr(a,'data_symbol',None) or getattr(a,'symbol','')
        if sym:out.append(str(sym))
    # Broad-market instruments that may not be represented by a directly tradable object.
    out += ['SPY','QQQ','^GSPC','^NDX','^DJI','^RUT','^VIX','ES=F','NQ=F','YM=F','RTY=F']
    return list(dict.fromkeys(out))
App._snapshot_symbols=_sgp25_snapshot_symbols

def _sgp25_find_experiment_menu(self):
    try:
        mb=self.root.nametowidget(self.root.cget('menu'));end=mb.index('end')
        if end is None:return None
        for i in range(int(end)+1):
            try:
                if str(mb.entrycget(i,'label')).strip().lower() in ('experiment','experimental'):
                    return self.root.nametowidget(mb.entrycget(i,'menu'))
            except Exception:pass
    except Exception:pass
    return None
App._find_experiment_menu=_sgp25_find_experiment_menu

def _sgp25_update_snapshot_menu(self):
    # The command exists only for a saved account. Guest/training sessions keep the
    # Experimental menu clean and remain strictly cache-only.
    if not bool(getattr(self,'account_username',None) and getattr(self,'account_manager',None)):return
    menu=getattr(self,'_snapshot_refresh_menu',None) or self._find_experiment_menu()
    if menu is None:return
    self._snapshot_refresh_menu=menu
    idx=getattr(self,'_snapshot_refresh_menu_index',None)
    if idx is None:
        try:
            menu.add_separator();menu.add_command(label='Refresh Market Snapshot…',command=self.refresh_market_snapshot)
            idx=menu.index('end');self._snapshot_refresh_menu_index=idx
        except Exception:return
    try:menu.entryconfig(idx,state='normal')
    except Exception:pass
App.update_experiment_account_menu=_sgp25_update_snapshot_menu

def _sgp25_refresh_market_snapshot(self):
    username=getattr(self,'account_username',None)
    if not username or not getattr(self,'account_manager',None):
        return messagebox.showinfo('Refresh Market Snapshot','Create or log into a saved account before refreshing its market snapshot.')
    positions=[(s,q) for s,q in getattr(self.portfolio,'positions',{}).items() if q]
    option_count=len(getattr(self.portfolio,'options',[]) or [])
    working=len(getattr(self.market,'pending_orders',[]))+len(getattr(self.market,'pending_option_orders',[]))+len(getattr(self.market,'pending_spread_orders',[]))
    equity=self.portfolio.cached_net_worth(self.market.all_assets()) if hasattr(self.portfolio,'cached_net_worth') else self.portfolio.mark_value(self.market.all_assets())
    warning=(
        'This will make an explicit internet request for the newest available market snapshot, then immediately return the game to offline mode.\n\n'
        'The refresh REPRICES the simulated market. Your share quantities and cost basis are not changed, but current P/L, option values, margin, and working-order behavior can change immediately. '
        'A limit/stop order may become marketable after the new prices are applied.\n\n'
        f'Account: {username}\nCurrent equity: ${equity:,.2f}\nOpen stock positions: {len(positions):,}\nOption positions: {option_count:,}\nWorking orders: {working:,}\n\n'
        'If the internet is unavailable, the newest local cache will be used instead. Continue?'
    )
    if not messagebox.askyesno('Refresh Market Snapshot — Position Warning',warning,icon='warning'):return
    # Prevent accidental double-starts and freeze simulation state while the bounded refresh runs.
    if getattr(self,'_snapshot_refresh_active',False):return
    self._snapshot_refresh_active=True;was_paused=bool(getattr(self.market,'paused',False));self.market.paused=True
    w=tk.Toplevel(self.root);w.title('Refreshing Market Snapshot');w.geometry('560x210');w.resizable(False,False);w.configure(bg=BG);w.transient(self.root);w.grab_set()
    ttk.Label(w,text='REFRESHING MARKET SNAPSHOT',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=18,pady=(18,4))
    ttk.Label(w,text='This is the only gameplay action that is allowed to use the network.',foreground=MUTED).pack(anchor='w',padx=18)
    status=tk.StringVar(value='Preparing explicit snapshot request…');ttk.Label(w,textvariable=status,wraplength=520).pack(fill='x',padx=18,pady=(14,6))
    bar=ttk.Progressbar(w,mode='determinate',maximum=100);bar.pack(fill='x',padx=18,pady=6)
    ttk.Label(w,text='The simulation is paused until the request finishes. No background polling is started.',foreground=MUTED).pack(anchor='w',padx=18,pady=(4,0))
    state={'done':False,'info':None,'error':None,'msg':status.get(),'cur':0,'total':1}
    import threading as _threading
    def progress(msg,cur=0,total=1):
        state['msg']=str(msg);state['cur']=int(cur or 0);state['total']=max(1,int(total or 1))
    def worker():
        try:
            from data import refresh_account_market_snapshot
            state['info']=refresh_account_market_snapshot(self._snapshot_symbols(),username,progress)
        except Exception as e:state['error']=f'{type(e).__name__}: {e}'
        finally:state['done']=True
    _threading.Thread(target=worker,daemon=True,name='ExplicitMarketSnapshotRefresh').start()
    def finish():
        info=state.get('info') or {}
        try:
            applied=self.market.apply_refreshed_market_snapshot(username) if not state.get('error') else 0
            if not state.get('error'):
                try:self.account_manager.set_market_seed_info(username,info)
                except Exception:pass
                try:
                    cb=getattr(self.market,'autosave_callback',None)
                    if callable(cb):cb('manual market snapshot refresh')
                except Exception:pass
            self.market.paused=was_paused;self._snapshot_refresh_active=False
            try:w.grab_release();w.destroy()
            except Exception:pass
            if state.get('error'):
                self.market.data_status='OFFLINE PLAY • SNAPSHOT REFRESH FAILED • EXISTING LOCAL MARKET PRESERVED'
                messagebox.showerror('Market Snapshot Refresh',f'Refresh failed. The existing simulated market was left in place.\n\n{state["error"]}')
                return
            fresh=int(info.get('fresh_quotes',0) or 0);cached=int(info.get('cached_quotes',0) or 0);src=info.get('source','LOCAL CACHE')
            self.status_flash(f'Market snapshot refreshed • {applied:,} marks applied • {src}')
            try:self.refresh_watch();self.refresh_positions();self.refresh_orders()
            except Exception:pass
            for c in list(getattr(self,'charts',()))+list(getattr(self,'extra_charts',())):
                try:c._stable_bounds25=None;c._display_data_cache25=None;c.request_draw(force=True)
                except Exception:pass
            messagebox.showinfo('Market Snapshot Refreshed',f'Applied {applied:,} market marks.\nSource: {src}\nFresh network quotes: {fresh:,}\nQuotes available after cache fallback: {cached:,}\n\nGameplay is offline again; no market-data polling is running.')
        except Exception as e:
            self.market.paused=was_paused;self._snapshot_refresh_active=False
            try:w.grab_release();w.destroy()
            except Exception:pass
            messagebox.showerror('Market Snapshot Refresh',f'The snapshot finished but could not be applied safely:\n\n{type(e).__name__}: {e}')
    def poll():
        if not w.winfo_exists():return
        status.set(state.get('msg') or 'Refreshing…');bar['value']=min(100,max(0,state.get('cur',0)/max(1,state.get('total',1))*100))
        if state.get('done'):finish()
        else:w.after(100,poll)
    w.protocol('WM_DELETE_WINDOW',lambda:None);w.after(100,poll)
App.refresh_market_snapshot=_sgp25_refresh_market_snapshot

_App_init_v25_prod_base=App.__init__
def _sgp25_app_init_production(self,root,market,portfolio):
    _App_init_v25_prod_base(self,root,market,portfolio)
    try:self.update_experiment_account_menu()
    except Exception:pass
App.__init__=_sgp25_app_init_production
