from dataclasses import dataclass
from datetime import datetime,time
from zoneinfo import ZoneInfo
@dataclass(frozen=True)
class Session:
    code:str; name:str; tz:str; open_time:time; close_time:time; weekdays:tuple=(0,1,2,3,4)
    def is_open(self,dt=None):
        dt=dt or datetime.now(ZoneInfo(self.tz)); dt=dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt
        local=dt.astimezone(ZoneInfo(self.tz)); return local.weekday() in self.weekdays and self.open_time<=local.time().replace(tzinfo=None)<self.close_time
SESSIONS={'US':Session('US','United States','America/New_York',time(9,30),time(16,0)),'EXT':Session('EXT','US Extended','America/New_York',time(4),time(20)),'LSE':Session('LSE','London','Europe/London',time(8),time(16,30)),'XETRA':Session('XETRA','Frankfurt','Europe/Berlin',time(9),time(17,30)),'TSE':Session('TSE','Tokyo','Asia/Tokyo',time(9),time(15,30)),'HKEX':Session('HKEX','Hong Kong','Asia/Hong_Kong',time(9,30),time(16)),'SSE':Session('SSE','Shanghai','Asia/Shanghai',time(9,30),time(15)),'ASX':Session('ASX','Sydney','Australia/Sydney',time(10),time(16)),'FX':Session('FX','Global FX','UTC',time(0),time(23,59,59),(0,1,2,3,4)),'CRYPTO':Session('CRYPTO','Crypto 24/7','UTC',time(0),time(23,59,59),(0,1,2,3,4,5,6)),'CME':Session('CME','CME Futures','America/Chicago',time(17),time(16),(0,1,2,3,4,6))}
def market_status(code,dt=None):
    if code!='CME': return SESSIONS[code].is_open(dt)
    s=SESSIONS[code]; local=(dt or datetime.now(ZoneInfo(s.tz))); local=local.replace(tzinfo=ZoneInfo('UTC')) if local.tzinfo is None else local; local=local.astimezone(ZoneInfo(s.tz)); wd=local.weekday(); m=local.hour*60+local.minute
    if wd==5:return False
    if wd==6:return m>=1020
    if wd==4:return m<960
    return not 960<=m<1020
