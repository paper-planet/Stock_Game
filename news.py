import random
COMPANY=[('{s} beats earnings expectations.',.025),('{s} misses earnings expectations.',-.028),('{s} wins a major contract.',.020),('{s} loses a major contract.',-.021),('Analysts upgrade {s}.',.014),('Analysts downgrade {s}.',-.014),('{s} announces a buyback.',.018),('{s} raises guidance.',.023),('{s} warns of weaker demand.',-.024)]
MACRO=[('Inflation prints hotter than expected.',-.012,.025),('Inflation cools more than expected.',.014,-.028),('Economic growth beats expectations.',.010,.004),('Economic growth disappoints.',-.012,-.004),('Geopolitical tensions rise.',-.018,.018),('Global risk appetite improves.',.015,-.008)]
COMMS=[('Crude inventories fall sharply.','CL=F',.030,.014),('Crude inventories rise sharply.','CL=F',-.028,-.012),('Gold demand rises on safe-haven flows.','GC=F',.024,.006),('Copper demand jumps.','HG=F',.028,.010)]
class NewsEvent:
    def __init__(self,headline,symbol=None,impact=0,inflation=0,severity='NORMAL'): self.headline=headline;self.symbol=symbol;self.impact=impact;self.inflation=inflation;self.severity=severity
    def __str__(self): return self.headline
def generate_news(stocks,commodities):
    r=random.random()
    if r<.58:
        a=random.choice(stocks);t,i=random.choice(COMPANY);return NewsEvent(t.format(s=a.symbol),a.symbol,i,0)
    if r<.82:
        t,i,inf=random.choice(MACRO);return NewsEvent(t,None,i,inf,'MACRO')
    t,s,i,inf=random.choice(COMMS);return NewsEvent(t,s,i,inf,'COMMODITY')
def major():
    return NewsEvent(*random.choice([('🚨 Broad risk-off move.',None,-.035,.018),('🚨 Surprise fiscal stimulus boosts growth.',None,.028,-.008),('🚨 Major oil supply shock.','CL=F',-.018,.040),('🚨 Strong economic data sparks a rally.',None,.032,-.010)]),'MAJOR')
