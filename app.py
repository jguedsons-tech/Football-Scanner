import os, math, re
from datetime import date, timedelta
import pandas as pd
import requests
import streamlit as st

API_BASE='https://v3.football.api-sports.io'
BOOKS={
 'Betano':['betano','betano brasil','betano.com','betano.pt'],
 'Superbet':['superbet','superbet brasil','superbet.ro'],
 'Betão':['betao','betão','betao.bet','betão.bet']}

st.set_page_config(page_title='Football Scanner 90+',page_icon='⚽',layout='wide')

def key_from_config():
    try: return st.secrets['api']['football_key']
    except Exception: return os.getenv('API_FOOTBALL_KEY','')

def norm(s): return re.sub(r'[^a-z0-9áéíóúãõâêôçü ]+','',str(s or '').lower()).strip()

@st.cache_data(ttl=120,show_spinner=False)
def api_get(endpoint,key,params_tuple=()):
    r=requests.get(API_BASE+endpoint,headers={'x-apisports-key':key},params=dict(params_tuple),timeout=30)
    r.raise_for_status(); d=r.json()
    if d.get('errors'): raise RuntimeError(str(d['errors']))
    return d.get('response',[])

def api(endpoint,key,params=None): return api_get(endpoint,key,tuple(sorted((params or {}).items())))

def pois(k,l):
    if l<=0:return 1.0 if k==0 else 0.0
    return math.exp(-l)*l**k/math.factorial(k)
def cdf(k,l): return 0 if k<0 else sum(pois(i,l) for i in range(k+1))
def over(l,line): return 1-cdf(math.ceil(line)-1,l)
def under(l,line): return cdf(math.floor(line),l)
def btts(h,a): return (1-math.exp(-h))*(1-math.exp(-a))
def one_x_two(h,a):
    x=[0,0,0]
    for i in range(11):
      for j in range(11):
        p=pois(i,h)*pois(j,a); x[0 if i>j else 1 if i==j else 2]+=p
    s=sum(x); return [v/s for v in x]

def fixture_name(f): return f'{f["teams"]["home"]["name"]} x {f["teams"]["away"]["name"]}'
def fixtures(key,start,end): return api('/fixtures',key,{'from':str(start),'to':str(end)})

def search_games(key,text,start,end):
    fs=fixtures(key,start,end); q=norm(text); parts=[p.strip() for p in re.split(r'\s+x\s+|\s+vs?\s+|[-–—]',q) if p.strip()]
    if len(parts)>=2:
      hit=[]
      for f in fs:
        h=norm(f['teams']['home']['name']); a=norm(f['teams']['away']['name'])
        if (parts[0] in h and parts[1] in a) or (parts[1] in h and parts[0] in a): hit.append(f)
      if hit:return hit
    scored=[]
    for f in fs:
      n=norm(fixture_name(f)); score=sum(1 for t in q.split() if len(t)>2 and t in n)
      if score: scored.append((score,f))
    return [f for _,f in sorted(scored,key=lambda z:z[0],reverse=True)[:15]]

def recent(key,team,n): return api('/fixtures',key,{'team':team,'last':n,'status':'FT'})

def team_metrics(key,team,n):
    fs=recent(key,team,n); gf=ga=cf=ca=yf=ya=0.; cn=yn=0
    for f in fs:
      home=f['teams']['home']['id']==team; hs=f['goals']['home'] or 0; aw=f['goals']['away'] or 0
      gf += hs if home else aw; ga += aw if home else hs
      try:
        ss=api('/fixtures/statistics',key,{'fixture':f['fixture']['id']})
        me=next((z for z in ss if z['team']['id']==team),None); op=next((z for z in ss if z['team']['id']!=team),None)
        def vals(z): return {norm(x.get('type')):x.get('value') for x in (z or {}).get('statistics',[])}
        vm,vo=vals(me),vals(op)
        c=vm.get('corner kicks'); oc=vo.get('corner kicks'); y=vm.get('yellow cards'); oy=vo.get('yellow cards')
        if c is not None:
          cf+=float(c); cn+=1
        if oc is not None: ca+=float(oc)
        if y is not None:
          yf+=float(y); yn+=1
        if oy is not None: ya+=float(oy)
      except Exception: pass
    d=max(len(fs),1)
    return dict(gf=gf/d,ga=ga/d,cf=cf/max(cn,1),ca=ca/max(cn,1),yf=yf/max(yn,1),ya=ya/max(yn,1),games=len(fs))

def h2h(key,h,a):
    fs=api('/fixtures/headtohead',key,{'h2h':f'{h}-{a}'})[:8]
    if not fs:return (1.2,1.0)
    hg=sum((f['goals']['home'] or 0) for f in fs)/len(fs); ag=sum((f['goals']['away'] or 0) for f in fs)/len(fs)
    return hg,ag

def model(key,f,n):
    h,a=f['teams']['home']['id'],f['teams']['away']['id']; hm=team_metrics(key,h,n); am=team_metrics(key,a,n); hh=h2h(key,h,a)
    hl=max(.15,.52*hm['gf']+.28*am['ga']+.20*hh[0]); al=max(.15,.52*am['gf']+.28*hm['ga']+.20*hh[1])
    return {'h':hl,'a':al,'g':hl+al,'c':max(.1,(hm['cf']+am['cf']+hm['ca']+am['ca'])/2),'y':max(.1,(hm['yf']+am['yf']+hm['ya']+am['ya'])/2)}

def target_book(name):
    n=norm(name)
    for k,als in BOOKS.items():
      if any(norm(a)==n or norm(a) in n or n in norm(a) for a in als): return k

def parse_odds(key,fid):
    out=[]
    for item in api('/odds',key,{'fixture':fid}):
      for bm in item.get('bookmakers',[]):
        book=target_book(bm.get('name',''))
        if not book: continue
        for bet in bm.get('bets',[]):
          market=bet.get('name','')
          for v in bet.get('values',[]):
            try:o=float(v.get('odd'))
            except:continue
            out.append((book,market,str(v.get('value','')),o))
    return out

def signal_label(market,label):
    x=norm(market+' '+label); l=norm(label)
    if 'match winner' in x:
      if 'home' in l:return 'Casa vence'
      if 'draw' in l or 'empate' in l:return 'Empate'
      if 'away' in l:return 'Visitante vence'
    if 'both teams score' in x or 'btts' in x:
      if l in ('yes','sim'):return 'BTTS Sim'
      if l in ('no','nao','não'):return 'BTTS Não'
    kind='gols' if 'goal' in x else 'escanteios' if 'corner' in x else 'cartões' if 'card' in x else None
    if kind:
      m=re.search(r'(over|under|mais de|menos de)\s*([0-9]+(?:[.,][0-9]+)?)',l)
      if m:return ('Over' if m.group(1) in ('over','mais de') else 'Under')+' '+m.group(2).replace(',','.')+' '+kind
    return None

def signals(m):
    h,a=m['h'],m['a']; ph,pd,pa=one_x_two(h,a); out=[('Casa vence',ph),('Empate',pd),('Visitante vence',pa),('BTTS Sim',btts(h,a)),('BTTS Não',1-btts(h,a))]
    for line in (.5,1.5,2.5,3.5,4.5):out += [(f'Over {line} gols',over(m['g'],line)),(f'Under {line} gols',under(m['g'],line))]
    for line in (7.5,8.5,9.5,10.5,11.5,12.5):out += [(f'Over {line} escanteios',over(m['c'],line)),(f'Under {line} escanteios',under(m['c'],line))]
    for line in (2.5,3.5,4.5,5.5,6.5):out += [(f'Over {line} cartões',over(m['y'],line)),(f'Under {line} cartões',under(m['y'],line))]
    return out

def analyze(key,f,n,minp):
    m=model(key,f,n); odds={}
    for book,market,label,odd in parse_odds(key,f['fixture']['id']):
      s=signal_label(market,label)
      if s: odds.setdefault(s,[]).append((book,odd))
    rows=[]
    for s,p in signals(m):
      if p<minp:continue
      offers=odds.get(s,[])
      if not offers: rows.append([fixture_name(f),s,p,1/p,'Sem odd',None,None]); continue
      for book,o in offers: rows.append([fixture_name(f),s,p,1/p,book,o,p*o-1])
    df=pd.DataFrame(rows,columns=['Jogo','Mercado','Prob. modelo','Odd justa','Casa','Odd','EV'])
    if not df.empty:df=df.sort_values(['EV','Prob. modelo'],ascending=False,na_position='last')
    return m,df

def show(df):
    if df.empty: st.info('Nenhuma oportunidade encontrou os filtros atuais.'); return
    v=df.copy(); v['Prob. modelo']=(v['Prob. modelo']*100).round(1).astype(str)+'%'; v['Odd justa']=v['Odd justa'].map(lambda x:f'{x:.2f}'); v['Odd']=v['Odd'].map(lambda x:'' if pd.isna(x) else f'{x:.2f}'); v['EV']=v['EV'].map(lambda x:'' if pd.isna(x) else f'{x*100:.1f}%'); st.dataframe(v,use_container_width=True,hide_index=True)

def main():
    st.title('⚽ Football Scanner 90+'); st.caption('Automático + busca manual | Betano • Superbet • Betão')
    with st.sidebar:
      k=key_from_config()
      if not k:k=st.text_input('API-Football Key',type='password')
      days=st.slider('Janela de jogos',0,7,2); n=st.selectbox('Últimos jogos', [5,8,10,15,20],index=2); minp=st.slider('Probabilidade mínima (%)',70,99,90)/100; minev=st.slider('EV mínimo (%)',-30,50,0)/100; maxg=st.slider('Máximo de jogos',5,100,30)
    if not k:st.info('Configure sua API-Football Key nos Secrets do Streamlit.');return
    auto,manual,info=st.tabs(['🔥 Automático','🎯 Buscar jogo','📊 Informações'])
    with auto:
      if st.button('🔎 Escanear jogos agora',type='primary',use_container_width=True):
        fs=[f for f in fixtures(k,date.today(),date.today()+timedelta(days=days)) if f['fixture']['status']['short'] in ('NS','TBD')][:maxg]; all=[]; bar=st.progress(0)
        for i,f in enumerate(fs,1):
          try:
            _,df=analyze(k,f,n,minp)
            if not df.empty:all.append(df[df['EV'].fillna(-999)>=minev])
          except Exception as e:st.warning(f'{fixture_name(f)}: {e}')
          bar.progress(i/max(len(fs),1))
        final=pd.concat(all,ignore_index=True) if all else pd.DataFrame()
        if final.empty:st.warning('Nenhuma oportunidade encontrada.')
        else:
          show(final.head(50));st.download_button('⬇️ Baixar CSV',final.to_csv(index=False).encode('utf-8-sig'),'football_scanner.csv','text/csv',use_container_width=True)
    with manual:
      q=st.text_input('Digite o jogo',placeholder='Flamengo x Palmeiras'); md=st.slider('Procurar nos próximos dias',0,7,2,key='md')
      if st.button('🔍 Procurar jogo',type='primary',use_container_width=True) and q:
        ms=search_games(k,q,date.today(),date.today()+timedelta(days=md))
        if not ms:st.warning('Jogo não encontrado.')
        else:
          opts={f'{fixture_name(f)} — {f["fixture"]["date"]}':f for f in ms}; choice=st.selectbox('Partida',list(opts)); f=opts[choice]
          if st.button('📊 Analisar partida',use_container_width=True):
            with st.spinner('Analisando...'):m,df=analyze(k,f,n,minp)
            a,b,c,d=st.columns(4);a.metric('λ casa',f'{m["h"]:.2f}');b.metric('λ visitante',f'{m["a"]:.2f}');c.metric('λ gols',f'{m["g"]:.2f}');d.metric('λ escanteios',f'{m["c"]:.2f}');show(df[df['EV'].fillna(-999)>=minev])
    with info:
      st.markdown('''### Como funciona\n\nO app usa dados da API-Football, forma recente e H2H para estimar gols com Poisson; também estima BTTS, 1X2, escanteios e cartões. As odds são filtradas para Betano, Superbet e Betão quando disponíveis na fonte.\n\n**Importante:** 90% é probabilidade estimada, não garantia de acerto ou lucro. A cobertura de bookmakers/mercados depende da sua conta e dos dados disponíveis na API.''')

if __name__=='__main__':main()
