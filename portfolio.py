class Portfolio:
    def __init__(self,cash=100_000_000):
        self.cash=float(cash);self.positions={};self.cost_basis={};self.options=[];self.realized=0.;self.reserved_margin=0.;self.orders=[];self.trade_count=0;self.best_net_worth=float(cash)
    def _qty(self,sym):return int(self.positions.get(sym,0))
    def buy_asset(self,a,qty):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        if q<=0:return False,'Quantity must be positive.'
        cost=a.ask*q
        if cost>self.cash:return False,f'Insufficient cash. Need ${cost:,.2f}.'
        old=self._qty(a.symbol);self.cash-=cost;self.positions[a.symbol]=old+q;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+cost;self.trade_count+=1;return True,f'Bought {q:,} {a.symbol} @ ${a.ask:.2f}'
    def sell_asset(self,a,qty):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        owned=self._qty(a.symbol)
        if q<=0:return False,'Quantity must be positive.'
        if owned<=0:return False,f'No long {a.symbol} position.'
        if q>owned:return False,f'Only {owned:,} shares are held.'
        proceeds=a.bid*q;basis=self.cost_basis.get(a.symbol,0)*(q/owned);self.cash+=proceeds;self.realized+=proceeds-basis;remain=owned-q
        if remain:self.positions[a.symbol]=remain;self.cost_basis[a.symbol]=max(0,self.cost_basis.get(a.symbol,0)-basis)
        else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
        self.trade_count+=1;return True,f'Sold {q:,} {a.symbol} @ ${a.bid:.2f}'
    def short_asset(self,a,qty,margin_rate=.5):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        if q<=0:return False,'Quantity must be positive.'
        req=a.price*q*margin_rate
        if self.cash<req:return False,f'Margin required ${req:,.2f}; available ${self.cash:,.2f}.'
        old=self._qty(a.symbol);self.positions[a.symbol]=old-q;self.cost_basis[a.symbol]=self.cost_basis.get(a.symbol,0)+a.bid*q;self.cash+=a.bid*q;self.reserved_margin+=req;self.trade_count+=1;return True,f'Shorted {q:,} {a.symbol} @ ${a.bid:.2f} — margin ${req:,.2f}'
    def cover_short(self,a,qty):
        try:q=int(qty)
        except:return False,'Invalid quantity.'
        short=-self._qty(a.symbol)
        if short<=0:return False,'No short position.'
        if q<=0 or q>short:return False,f'Short position is {short:,} shares.'
        cost=a.ask*q;self.cash-=cost;entry=self.cost_basis.get(a.symbol,0)*(q/short);self.realized+=entry-cost;remain=short-q;self.reserved_margin=max(0,self.reserved_margin-a.price*q*.5)
        if remain:self.positions[a.symbol]=-remain;self.cost_basis[a.symbol]=max(0,self.cost_basis.get(a.symbol,0)-entry)
        else:self.positions.pop(a.symbol,None);self.cost_basis.pop(a.symbol,None)
        self.trade_count+=1;return True,f'Covered {q:,} {a.symbol} @ ${a.ask:.2f}'
    def execute_strategy(self,s):
        debit=s.opening_debit();margin=max(0,-debit*1.5)
        if debit>self.cash:return False,f'Insufficient cash. Need ${debit:,.2f}.'
        if debit<0 and self.cash+(-debit)<margin:return False,f'Short option margin required ${margin:,.2f}.'
        self.cash-=debit;self.reserved_margin+=margin;s.open_cost=debit;s.opened=True;self.options.append(s);self.trade_count+=1;return True,f'Opened {s.name}: ${debit:,.2f} net cash flow'
    def liquidate_strategy(self,index):
        if not 0<=index<len(self.options):return False,'Invalid strategy.'
        s=self.options.pop(index);proceeds=s.current_value();self.cash+=proceeds;self.realized+=proceeds-s.open_cost;self.reserved_margin=max(0,self.reserved_margin);self.trade_count+=1;return True,f'Liquidated {s.name}: ${proceeds-s.open_cost:,.2f} P/L'
    def liquidate_asset(self,a):q=self._qty(a.symbol);return self.sell_asset(a,q) if q>0 else self.cover_short(a,-q) if q<0 else (False,'No position.')
    def apply_corporate_actions(self,assets):
        for a in assets:
            ratio=getattr(a,'pending_split',None)
            if not ratio:continue
            if a.symbol in self.positions:self.positions[a.symbol]=int(round(self.positions[a.symbol]*ratio))
            for s in self.options:
                for leg in s.legs:
                    if leg.contract.underlying.symbol==a.symbol:leg.contract.strike/=ratio
            a.pending_split=None
    def mark_value(self,assets):
        total=self.cash
        for a in assets:total+=self._qty(a.symbol)*a.price
        for s in self.options:total+=s.current_value()
        return total
    def position_rows(self,assets):
        rows=[]
        for a in assets:
            q=self._qty(a.symbol)
            if q:
                basis=self.cost_basis.get(a.symbol,0);value=q*a.price;pnl=(value-basis) if q>0 else (basis+value);rows.append((a.symbol,a.name,q,a.price,value,pnl,'LONG' if q>0 else 'SHORT'))
        for i,s in enumerate(self.options):
            v=s.current_value();rows.append((f'OPT:{i}',s.name,1,v,v,v-s.open_cost,'OPTION'))
        return rows
    def summary(self,assets):
        lines=[f'CASH        ${self.cash:,.2f}',f'REALIZED    ${self.realized:,.2f}',f'MARGIN USED ${self.reserved_margin:,.2f}',f'NET WORTH   ${self.mark_value(assets):,.2f}','','POSITIONS'];rows=self.position_rows(assets)
        if not rows:lines.append('None')
        for sym,name,q,price,value,pnl,typ in rows:lines.append(f'{sym:<10} {q:>10,}  ${value:>15,.2f}  P/L ${pnl:>12,.2f}  {typ}')
        return '\n'.join(lines)
