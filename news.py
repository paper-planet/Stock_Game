import random

COMPANY = [
("{s} beats earnings expectations.",.025),("{s} misses earnings expectations.",-.028),
("{s} wins a major contract.",.020),("{s} loses a major contract.",-.021),
("Analysts upgrade {s}.",.014),("Analysts downgrade {s}.",-.014),
("{s} announces a major technology breakthrough.",.035),
("{s} faces regulatory pressure.",-.024),("{s} announces a buyback.",.018),
("{s} raises guidance.",.023),("{s} warns of weaker demand.",-.024),
]
MACRO = [
("Inflation prints hotter than expected.",-.012,.025),
("Inflation cools more than expected.",.014,-.028),
("Economic growth beats expectations.",.010,.004),
("Economic growth disappoints.",-.012,-.004),
("Geopolitical tensions rise.",-.018,.018),
("Global risk appetite improves.",.015,-.008),
("A major supply-chain disruption emerges.",-.014,.020),
]
COMMS = [
("Crude inventories fall sharply.","CL=F",.030,.014),
("Crude inventories rise sharply.","CL=F",-.028,-.012),
("Major oil supply disruption reported.","CL=F",.050,.025),
("Gold demand rises on safe-haven flows.","GC=F",.024,.006),
("Gold demand falls as risk appetite returns.","GC=F",-.018,-.004),
("Copper demand jumps.","HG=F",.028,.010),
("Agricultural supply disruption reported.","ZC=F",.035,.016),
("Natural gas storage surprises lower.","NG=F",.038,.016),
("Natural gas storage surprises higher.","NG=F",-.032,-.014),
]
class NewsEvent:
    def __init__(self,headline,symbol=None,impact=0,inflation=0,severity="NORMAL"):
        self.headline=headline;self.symbol=symbol;self.impact=impact;self.inflation=inflation;self.severity=severity
    def __str__(self):return self.headline

def generate_news(stocks,commodities):
    r=random.random()
    if r<.58:
        a=random.choice(stocks);text,impact=random.choice(COMPANY)
        return NewsEvent(text.format(s=a.symbol),a.symbol,impact,0)
    if r<.82:
        text,impact,inf=random.choice(MACRO)
        return NewsEvent(text,None,impact,inf,"MACRO")
    text,sym,impact,inf=random.choice(COMMS)
    return NewsEvent(text,sym,impact,inf,"COMMODITY")

def major():
    choices=[
        ("🚨 Emergency financial conditions trigger a broad risk-off move.",None,-.035,.018),
        ("🚨 Surprise fiscal stimulus boosts growth expectations.",None,.028,-.008),
        ("🚨 Major commodity supply shock hits oil markets.","CL=F",-.018,.040),
        ("🚨 Unexpectedly strong economic data sparks a risk-on rally.",None,.032,-.010),
    ]
    x=random.choice(choices)
    return NewsEvent(*x,"MAJOR")
