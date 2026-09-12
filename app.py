import math,re
from datetime import date,timedelta,datetime
import requests,pandas as pd,streamlit as st

st.set_page_config(page_title='Football Scanner',page_icon='⚽',layout='wide')
API='https://v3.football.api-sports.io'; TIMEOUT=15
BOOKS={'Betano':['betano'],'Superbet':['superbet'],'Betão':['betao','betão']}
if 'games' not in st.session_state: st.session_state.games=[]
if 'analysis' not in st.session_state: st.session_state.analysis=None

def key():
    try:return st.secrets['api']['football_key'].strip()
    except:return ''

def api(endpoint,params):
    try:
        r=requests.get(API+'/'+endpoint,headers={'x-apisports-key':key()},params=params,timeout=TIMEOUT); d=r.json()
        if d.get('errors'): st.error(str(d['errors'])); return []
        return d.get('response',[]) or []
    except Exception as e: st.error(f'Erro na API: {e}'); return []

@st.cache_data(ttl=300)
def fixtures(day): return api('fixtures',{'date':day,'timezone':'America/Sao_Paulo'})
@st.cache_data(ttl=1800)
def prediction(fid):
    x=api('predictions',{'fixture':fid}); return x[0] if x else {}
@st.cache_data(ttl=1800)
def stats(team,league,season):
    x=api('teams/statistics',{'team':team,'league':league,'season':season}); return x[0] if x else {}
@st.cache_data(ttl=600)
def odds(fid): return api('odds',{'fixture':fid})

def f(v,d=0):
    try:return float(str(v).replace(',','.').replace('%',''))
    except:return d
def norm(s): return re.sub(r'[^a-z0-9 ]','',str(s).lower().replace('ã','a').replace('á','a').replace('é','e').replace('ê','e').replace('í','i').replace('ó','o').replace('ô','o').replace('ú','u').replace('ç','c')).strip()
def pmf(l,g): return math.exp(-l)*l**g/math.factorial(g)
def over(l,line):
    n=math.floor(line); return max(0,min(1,1-sum(pmf(l,i) for i in range(n+1))))
def under(l,line): return max(0,min(1,sum(pmf(l,i) for i in range(math.floor(line)+1))))
def one_x_two(h,a):
    x=[0,0,0]
    for hg in range(10):
      for ag in range(10):
        p=pmf(h,hg)*pmf(a,ag); x[0 if hg>ag else 1 if hg==ag else 2]+=p
    s=sum(x); return [v/s for v in x]
def btts(h,a): return 1-math.exp(-h)-math.exp(-a)+math.exp(-(h+a))
def avg(s,kind,side):
    v=s.get('goals',{}).get(kind,{}).get('average',{})
    if isinstance(v,dict): return f(v.get(side),0)
    return f(v,0)
def model(g):
    t=g['teams']; l=g['league']; pr=prediction(g['fixture']['id']); hs=stats(t['home']['id'],l['id'],l.get('season')) if l.get('id') and l.get('season') else {}; a_s=stats(t['away']['id'],l['id'],l.get('season')) if l.get('id') and l.get('season') else {}
    pg=pr.get('predictions',{}); goals=pr.get('goals',{})
    h=0.55*max(avg(hs,'for','home'),1.2)+0.25*max(avg(a_s,'against','away'),1.2)+.2*1.25
    a=.55*max(avg(a_s,'for','away'),1.1)+.25*max(avg(hs,'against','home'),1.2)+.2*1.05
    ph,pa=f(goals.get('home')),f(goals.get('away'))
    if ph>0:h=.6*ph+.4*h
    if pa>0:a=.6*pa+.4*a
    return h,a,pr

def book(name):
    n=norm(name)
    for k,aliases in BOOKS.items():
      if any(norm(x) in n or n in norm(x) for x in aliases):return k

def parse_odds(raw):
    out=[]
    for b in raw:
      bn=book(b.get('bookmaker',{}).get('name',''))
      if not bn:continue
      for bet in b.get('bookmaker',{}).get('bets',[]):
       for v in bet.get('values',[]):
        try:o=float(str(v.get('odd')).replace(',','.'))
        except:continue
        if o>1:out.append((bn,bet.get('name',''),v.get('value',''),o))
    return out

def prob(m,s,h,a):
    m,s=norm(m),norm(s); total=h+a; p=one_x_two(h,a)
    if 'match winner' in m or m in ('1x2','winner'):
      return p[0] if s in ('home','1') else p[1] if s in ('draw','x') else p[2] if s in ('away','2') else None
    if 'both teams' in m or m=='btts':
      q=btts(h,a); return q if s in ('yes','sim') else 1-q if s in ('no','nao') else None
    nums=re.findall(r'\d+(?:\.\d+)?',s)
    if nums and ('over' in s or 'under' in s or 'mais' in s or 'menos' in s):
      line=float(nums[-1]); return over(total,line) if ('over' in s or 'mais' in s) else under(total,line)
    if nums and ('corner' in m or 'escanteio' in m):
      line=float(nums[-1]); return over(9,line) if 'over' in s else under(9,line) if 'under' in s else None
    if nums and ('card' in m or 'yellow' in m or 'cartao' in m):
      line=float(nums[-1]); return over(4.2,line) if 'over' in s else under(4.2,line) if 'under' in s else None

def label(g):
    ts=g['fixture'].get('timestamp'); h=datetime.fromtimestamp(ts).strftime('%H:%M') if ts else '--:--'
    return f"{h} | {g['teams']['home']['name']} x {g['teams']['away']['name']}"

if not key():
    st.title('⚽ Football Scanner'); st.warning('Configure a API Key nos Secrets do Streamlit.'); st.code('[api]\nfootball_key = "SUA_API_KEY"',language='toml'); st.stop()

st.title('⚽ Football Scanner'); st.caption('Análise estatística • 1X2 • Gols • BTTS • Escanteios • Cartões • Odds')
with st.sidebar:
    minp=st.slider('Probabilidade mínima',50,90,65)/100
    minev=st.slider('EV mínimo (%)',-20,30,0)/100
    maxgames=st.slider('Máximo de jogos',1,8,5)
    st.caption('Casas: Betano • Superbet • Betão')

b1,b2,b3,b4=st.tabs(['🔎 Buscar jogo','🤖 Scanner automático','📊 Análise','ℹ️ Informações'])
with b1:
    d=st.selectbox('Data',[date.today(),date.today()+timedelta(1)],format_func=lambda x:x.strftime('%d/%m/%Y'))
    if st.button('🔍 Procurar jogos',type='primary',use_container_width=True):
        st.session_state.games=[x for x in fixtures(d.isoformat()) if x.get('fixture',{}).get('status',{}).get('short') in ('NS','TBD')]
    if st.session_state.games:
        i=st.selectbox('Partida',range(len(st.session_state.games)),format_func=lambda i:label(st.session_state.games[i]))
        if st.button('📊 Analisar jogo selecionado',type='primary',use_container_width=True):
            g=st.session_state.games[i]
            with st.spinner('Analisando...'):
                h,a,pr=model(g); raw=parse_odds(odds(g['fixture']['id'])); rows=[]
                for bn,m,s,o in raw:
                    p=prob(m,s,h,a)
                    if p is not None:
                        ev=p*o-1
                        if p>=minp and ev>=minev:rows.append({'Casa':bn,'Mercado':m,'Seleção':s,'Odd':o,'Probabilidade':p*100,'Odd justa':1/p,'EV':ev*100})
                st.session_state.analysis={'g':g,'h':h,'a':a,'p':one_x_two(h,a),'b':btts(h,a),'rows':rows,'pr':pr}
        st.success(f'{len(st.session_state.games)} jogos encontrados')

with b2:
    if st.button('🚀 Executar scanner',type='primary',use_container_width=True):
        gs=[x for x in fixtures(date.today().isoformat()) if x.get('fixture',{}).get('status',{}).get('short') in ('NS','TBD')][:maxgames]; rows=[]
        bar=st.progress(0)
        for j,g in enumerate(gs):
            try:
                h,a,_=model(g)
                for bn,m,s,o in parse_odds(odds(g['fixture']['id'])):
                    p=prob(m,s,h,a)
                    if p is not None and p>=minp and p*o-1>=minev:rows.append({'Jogo':label(g),'Casa':bn,'Mercado':m,'Seleção':s,'Odd':o,'Probabilidade':p*100,'Odd justa':1/p,'EV':(p*o-1)*100})
            except Exception as e: st.warning(str(e))
            bar.progress((j+1)/max(1,len(gs)))
        if rows:st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        else:st.info('Nenhuma oportunidade passou pelos filtros.')

with b3:
    r=st.session_state.analysis
    if not r: st.info('Selecione um jogo na aba Buscar jogo.')
    else:
        st.header(label(r['g'])); h,a=r['h'],r['a']; p=r['p']
        c=st.columns(4); c[0].metric('Casa',f'{p[0]*100:.1f}%'); c[1].metric('Empate',f'{p[1]*100:.1f}%'); c[2].metric('Fora',f'{p[2]*100:.1f}%'); c[3].metric('BTTS',f'{r["b"]*100:.1f}%')
        st.write(f'**Gols esperados:** {h:.2f} x {a:.2f} — total {h+a:.2f}')
        st.subheader('Over/Under')
        st.dataframe(pd.DataFrame([{'Linha':x,'Over %':over(h+a,x)*100,'Under %':under(h+a,x)*100} for x in (.5,1.5,2.5,3.5,4.5)]),use_container_width=True,hide_index=True)
        st.subheader('💰 Oportunidades')
        if r['rows']:st.dataframe(pd.DataFrame(r['rows']),use_container_width=True,hide_index=True)
        else:st.info('Nenhuma odd das casas selecionadas passou pelos filtros.')
        pr=r['pr'].get('predictions',{}); w=pr.get('winner',{})
        if pr:st.info(f"Prediction API-Football: {w.get('name','não informado')} • {pr.get('under_over','')} • {pr.get('advice','')}")

with b4:
    st.subheader('ℹ️ Como funciona')
    st.markdown('''O app consulta a API-Football, combina estatísticas disponíveis com a previsão da API e usa um modelo de Poisson para estimar gols. **Odd justa = 1/probabilidade** e **EV = probabilidade × odd − 1**. Escanteios e cartões usam referências-base quando não há métricas confiáveis disponíveis. Probabilidades são estimativas, não garantias de acerto ou lucro. O plano Free possui limite diário de requisições; o app usa cache e limita o scanner.''')
