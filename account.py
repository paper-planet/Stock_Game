import json,hashlib,time
from pathlib import Path
APP_DIR=Path.home()/'.stock_game_pro';ACCOUNTS=APP_DIR/'accounts.json'
def _hash(password):return hashlib.sha256(password.encode('utf-8')).hexdigest()
class AccountManager:
    def __init__(self,path=ACCOUNTS):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.accounts=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text())
        except Exception:return {}
    def _save(self):
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.accounts,indent=2));tmp.replace(self.path)
    def create(self,username,password,mode):
        username=username.strip().lower()
        if not username or not password:return False,'Username and password are required.'
        if username in self.accounts:return False,'That account already exists.'
        cash={'EASY':50000,'MEDIUM':250000,'EXPERT':1000000}[mode];self.accounts[username]={'password':_hash(password),'mode':mode,'cash':cash,'created':time.time(),'stats':{'trades':0,'realized':0.0,'best_net_worth':cash}};self._save();return True,'Account created.'
    def login(self,username,password):
        username=username.strip().lower();rec=self.accounts.get(username)
        if not rec or rec.get('password')!=_hash(password):return None
        return dict(rec,username=username)
    def save_session(self,username,cash,mode,stats):
        if username not in self.accounts:return
        rec=self.accounts[username];rec.update(cash=float(cash),mode=mode,stats=stats,last_login=time.time());self._save()
