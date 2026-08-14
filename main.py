import asyncio,threading,tkinter as tk,sys
from market import Market
from portfolio import Portfolio
from ui import App
from account import AccountManager
async def _simulation(market):
    while market.running: await market.tick()
def simulation(market):
    try:asyncio.run(_simulation(market))
    except Exception as e:market.errors.append(f'simulation thread: {type(e).__name__}: {e}')
def main_menu(root,accounts):
    result={'action':'cancel','mode':'MEDIUM','cash':250000,'username':None};w=tk.Toplevel(root);w.title('STOCK_GAME PRO — MAIN MENU');w.geometry('760x620');w.configure(bg='#071019');w.protocol('WM_DELETE_WINDOW',w.destroy)
    tk.Label(w,text='STOCK_GAME PRO',bg='#071019',fg='#f2f6fb',font=('Arial',28,'bold')).pack(pady=(34,6));tk.Label(w,text='Professional market training simulator',bg='#071019',fg='#91a3b6',font=('Arial',11)).pack(pady=(0,22))
    form=tk.Frame(w,bg='#101a25');form.pack(fill='x',padx=80,pady=8);tk.Label(form,text='Username',bg='#101a25',fg='white').grid(row=0,column=0,padx=18,pady=8);user=tk.Entry(form);user.grid(row=0,column=1,sticky='ew',padx=18);tk.Label(form,text='Password',bg='#101a25',fg='white').grid(row=1,column=0,padx=18,pady=8);pw=tk.Entry(form,show='•');pw.grid(row=1,column=1,sticky='ew',padx=18);form.columnconfigure(1,weight=1);mode=tk.StringVar(value='MEDIUM');tk.Label(form,text='New account difficulty',bg='#101a25',fg='white').grid(row=2,column=0,padx=18,pady=8);from tkinter import ttk;ttk.Combobox(form,textvariable=mode,values=['EASY','MEDIUM','EXPERT'],state='readonly').grid(row=2,column=1,sticky='w',padx=18);status=tk.Label(w,text='Create an account or log in to continue.',bg='#071019',fg='#91a3b6');status.pack(pady=10)
    def create():
        ok,msg=accounts.create(user.get(),pw.get(),mode.get());status.config(text=msg,fg='#26d69a' if ok else '#ff5d73')
        if ok:result.update(action='start',username=user.get().strip().lower(),mode=mode.get(),cash={'EASY':50000,'MEDIUM':250000,'EXPERT':1000000}[mode.get()]);w.destroy()
    def login():
        rec=accounts.login(user.get(),pw.get())
        if not rec:status.config(text='Login failed — check username/password.',fg='#ff5d73');return
        result.update(action='start',username=rec['username'],mode=rec.get('mode','MEDIUM'),cash=float(rec.get('cash',250000)));w.destroy()
    def guest():result.update(action='start',username=None,mode=mode.get(),cash={'EASY':50000,'MEDIUM':250000,'EXPERT':1000000}[mode.get()]);w.destroy()
    b=tk.Frame(w,bg='#071019');b.pack(pady=8)
    for text,cmd in [('CREATE ACCOUNT',create),('LOG IN',login),('GUEST / TRAINING',guest),('EXIT',w.destroy)]:tk.Button(b,text=text,command=cmd,bg='#1b3347',fg='white',relief='flat',padx=16,pady=9).pack(side='left',padx=5)
    root.wait_window(w);return result
def main():
    root=tk.Tk();root.withdraw();accounts=AccountManager();choice={'action':'start','username':None,'mode':'MEDIUM','cash':250000} if '--guest' in sys.argv else main_menu(root,accounts)
    if choice['action']!='start':root.destroy();return
    root.deiconify();market=Market();market.difficulty=choice['mode'];market.speed={'EASY':.14,'MEDIUM':.08,'EXPERT':.045}.get(choice['mode'],.08);portfolio=Portfolio(choice['cash']);market.portfolio=portfolio;app=App(root,market,portfolio);app.account_username=choice.get('username');app.account_manager=accounts
    sim=threading.Thread(target=simulation,args=(market,),daemon=True,name='MarketSimulation');sim.start();root.after(800,market.start_background_loaders)
    def stop():
        market.running=False
        if app.account_username:accounts.save_session(app.account_username,portfolio.cash,market.difficulty,{'trades':portfolio.trade_count,'realized':portfolio.realized,'best_net_worth':portfolio.best_net_worth})
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',stop);root.mainloop();market.running=False
if __name__=='__main__':main()
