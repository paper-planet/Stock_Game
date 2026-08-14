import math,random
from dataclasses import dataclass
CONTRACT_SIZE=100;RISK_FREE=.04
EXPIRATIONS=[('0DTE',0),('1D',1),('3D',3),('7D',7),('14D',14),('30D',30),('45D',45),('60D',60),('90D',180),('1Y',365)]
def norm_pdf(x):return math.exp(-.5*x*x)/math.sqrt(2*math.pi)
def norm_cdf(x):return .5*(1+math.erf(x/math.sqrt(2)))
def bs_all(spot,strike,days,vol,rate,typ):
    spot=max(float(spot),.0001);strike=max(float(strike),.0001);T=max(float(days),.01)/365;vol=max(.05,float(vol));s=math.sqrt(T);d1=(math.log(spot/strike)+(rate+.5*vol*vol)*T)/(vol*s);d2=d1-vol*s
    if typ=='call': price=spot*norm_cdf(d1)-strike*math.exp(-rate*T)*norm_cdf(d2);delta=norm_cdf(d1);theta=(-spot*norm_pdf(d1)*vol/(2*s)-rate*strike*math.exp(-rate*T)*norm_cdf(d2))/365;rho=strike*T*math.exp(-rate*T)*norm_cdf(d2)/100
    else: price=strike*math.exp(-rate*T)*norm_cdf(-d2)-spot*norm_cdf(-d1);delta=norm_cdf(d1)-1;theta=(-spot*norm_pdf(d1)*vol/(2*s)+rate*strike*math.exp(-rate*T)*norm_cdf(-d2))/365;rho=-strike*T*math.exp(-rate*T)*norm_cdf(-d2)/100
    return {'price':max(.005,price),'delta':delta,'gamma':norm_pdf(d1)/(spot*vol*s),'theta':theta,'vega':spot*norm_pdf(d1)*s/100,'rho':rho}
@dataclass
class OptionContract:
    underlying:object;strike:float;days:int;option_type:str;liquidity:float=1.;open_interest:int=0;volume:int=0
    @property
    def volatility(self):return max(.10,self.underlying.volatility*20+.12+abs(self.strike/self.underlying.price-1)*.30)
    @property
    def stats(self):return bs_all(self.underlying.price,self.strike,self.days,self.volatility,RISK_FREE,self.option_type)
    @property
    def premium(self):return self.stats['price']
    @property
    def spread(self):return max(.005,self.premium*(.004+.020*(1-self.liquidity)))
    @property
    def bid(self):return max(.005,self.premium-self.spread/2)
    @property
    def ask(self):return self.premium+self.spread/2
    @property
    def mid(self):return (self.bid+self.ask)/2
    def intrinsic(self,spot):return max(spot-self.strike,0) if self.option_type=='call' else max(self.strike-spot,0)
    def itm(self):return self.intrinsic(self.underlying.price)>0
    def __str__(self):return f'{self.underlying.symbol} {self.option_type.upper()} {self.strike:.0f} {self.days}D'
@dataclass
class StrategyLeg:
    contract:OptionContract;quantity:int;action:str
    @property
    def sign(self):return 1 if self.action=='BUY' else -1
    @property
    def mark(self):return self.contract.ask if self.action=='BUY' else self.contract.bid
    @property
    def cash_flow(self):return -self.sign*self.mark*self.quantity*CONTRACT_SIZE
class OptionStrategy:
    def __init__(self,name='Custom'):self.name=name;self.legs=[];self.open_cost=0.;self.opened=False
    def add_leg(self,c,q,a):
        q=int(q);a=a.upper()
        if q<=0 or q>1000000:raise ValueError('Invalid option quantity.')
        self.legs.append(StrategyLeg(c,q,a))
    def current_value(self):return sum((l.contract.bid if l.action=='BUY' else l.contract.ask)*l.quantity*CONTRACT_SIZE*l.sign for l in self.legs)
    def opening_debit(self):return sum(l.sign*l.mark*l.quantity*CONTRACT_SIZE for l in self.legs)
    def expiration_pnl(self,spot):return sum(l.sign*l.contract.intrinsic(spot)*l.quantity*CONTRACT_SIZE for l in self.legs)-self.open_cost
    def greeks(self):
        r={k:0. for k in ('delta','gamma','theta','vega','rho')}
        for l in self.legs:
            s=l.contract.stats
            for k in r:r[k]+=l.sign*l.quantity*CONTRACT_SIZE*s[k]
        return r
def option_chain(asset,days,span=25):
    p=max(asset.price,.01);center=round(p);out=[]
    for k in sorted(set(max(1,center+i) for i in range(-span,span+1))):
        liq=max(.15,1-abs(k/p-1)*1.8);base=int(1000*liq*random.uniform(.75,1.25));oi=int(5000*liq*random.uniform(.7,1.4));out.extend([OptionContract(asset,k,days,'call',liq,oi,base),OptionContract(asset,k,days,'put',liq,oi,base)])
    return out
