import os, math
from datetime import date
import requests
import streamlit as st

BASE='https://openfootapi.com/v1'
TIMEOUT=20
st.set_page_config(page_title='Football Scanner Pro',page_icon='⚽',layout='wide')

@st.cache_data(ttl=300, show_spinner=False)
def request_api(path, params=None):
    key=st.secrets.get('OPENFOOT_API_KEY', os.getenv('OPENFOOT_API_KEY',''))
    try:
        r=requests.get(BASE+path,params=params or {},headers={'Accept':'application/json','Authorization':f'Bearer {key}'},timeout=TIMEOUT)
        try: data=r.json()
        except Exception: data={'error':{'message':r.text[:500]}}
        data['_status']=r.status_code
        return data
    except Exception as e:
        return {'error':{'code':'network_error','message':str(e)},'_status':0}

def items(b):
    x=b.get('data',[]); return x if isinstance(x,list) else []
def error(b): return b.get('error')
def names(m):
    h=m.get('homeTeam') or m.get('home') or {}; a=m.get('awayTeam') or m.get('away') or {}
    return ((h.get('name','?') if isinstance(h,dict) else str(h)),(a.get('name','?') if isinstance(a,dict) else str(a)))
def poisson(k,l): return math.exp(-l)*l**k/math.factorial(k)
def probabilities(lh,la):
    n=8; ph=[poisson(i,lh) for i in range(n+1)]; pa=[poisson(i,la) for i in range(n+1)]
    s=sum(ph[i]*pa[j] for i in range(n+1) for j in range(n+1)) or 1
    p1=sum(ph[i]*pa[j] for i in range(n+1) for j in range(n+1) if i>j)/s
    px=sum(ph[i]*pa[j] for i in range(n+1) for j in range(n+1) if i==j)/s
    p2=max(0,1-p1-px)
    u25=sum(ph[i]*pa[j] for i in range(n+1) for j in range(n+1) if i+j<=2)/s
    btts=sum(ph[i]*pa[j] for i in range(1,n+1) for j in range(1,n+1))/s
    return {'Casa':p1,'Empate':px,'Fora':p2,'Over 2.5':1-u25,'Under 2.5':u25,'BTTS Sim':btts,'BTTS Não':1-btts}
def fair(p): return 1/p if p>0 else 999
def ev(p,o): return (p*o-1)*100

def lambdas(ctx):
    d=ctx.get('data',{}) if isinstance(ctx.get('data',{}),dict) else {}
    h=d.get('home',{}) if isinstance(d.get('home',{}),dict) else {}; a=d.get('away',{}) if isinstance(d.get('away',{}),dict) else {}
    def get(x):
        for k in ('expectedGoals','xg','goalExpectation','goalsForAvg','goalsAverage','attack'):
            v=x.get(k)
            if isinstance(v,(int,float)) and 0<v<8: return float(v)
            if isinstance(v,dict):
                for q in ('value','avg','average','expected'):
                    if isinstance(v.get(q),(int,float)) and 0<v[q]<8: return float(v[q])
        return None
    return get(h) or 1.25, get(a) or 1.05

def verdict(p,o,minp,minev,minodd,maxodd):
    e=ev(p,o)
    if not(minodd<=o<=maxodd): return '⚪ FORA DA FAIXA'
    if p>=.75 and e>=max(minev,5): return '🟢 ENTRADA FORTE'
    if p>=minp and e>=minev: return '🟢 ENTRADA'
    if e>=0: return '🟡 VALOR PEQUENO'
    return '🔴 NÃO APOSTAR'

key=st.secrets.get('OPENFOOT_API_KEY',os.getenv('OPENFOOT_API_KEY',''))
if not key:
    st.error('OPENFOOT_API_KEY não encontrada nos Secrets.'); st.stop()

with st.sidebar:
    st.header('⚙️ Scanner Pro')
    minp=st.slider('Probabilidade mínima',.50,.90,.65,.01)
    minev=st.slider('EV mínimo (%)',0.,20.,5.,.5)
    minodd=st.number_input('Odd mínima',1.01,20.,1.30,.01)
    maxodd=st.number_input('Odd máxima',1.01,50.,3.00,.05)
    st.caption('A recomendação depende da odd realmente oferecida.')

st.title('⚽ Football Scanner Pro')
st.caption('Probabilidade • odd justa • EV • sugestão de jogada')
mode=st.radio('Modo',['Scanner de hoje','Buscar equipe','Analisar ID','Diagnóstico'],horizontal=True)

if mode=='Diagnóstico':
    b=request_api('/health'); st.write('HTTP:',b.get('_status')); st.json(b); st.stop()
if mode=='Buscar equipe':
    q=st.text_input('Equipe ou competição','Palmeiras')
    if q:
        b=request_api('/search',{'q':q})
        if error(b): st.error(error(b).get('message','Erro'))
        else: st.dataframe(items(b),use_container_width=True,hide_index=True)
    st.stop()
if mode=='Analisar ID':
    mid=st.text_input('ID do jogo')
    if mid:
        b=request_api(f'/matches/{mid}/context')
        if error(b): st.error(error(b).get('message','Erro'))
        else:
            lh,la=lambdas(b); ps=probabilities(lh,la)
            st.write(f'λ estimado: **{lh:.2f} x {la:.2f}**')
            st.dataframe([{'Mercado':k,'Probabilidade':f'{p*100:.1f}%','Odd justa':f'{fair(p):.2f}'} for k,p in ps.items()],use_container_width=True,hide_index=True)
    st.stop()

b=request_api('/matches',{'date':date.today().isoformat()})
if error(b): st.error(error(b).get('message','Erro ao buscar jogos')); st.stop()
matches=items(b)
st.subheader(f'📅 Jogos de hoje — {len(matches)} encontrados')
st.info('As odds das casas são informadas por você quando não estiverem disponíveis na API. O scanner então transforma a probabilidade em uma recomendação baseada em EV.')
best=[]
for m in matches:
    mid=m.get('id'); hn,an=names(m)
    if not mid: continue
    with st.expander(f'⚽ {hn} x {an}'):
        ctx=request_api(f'/matches/{mid}/context')
        lh,la=lambdas(ctx) if not error(ctx) else (1.25,1.05)
        ps=probabilities(lh,la)
        market=st.selectbox('Mercado',list(ps),key=f'm_{mid}')
        p=ps[market]; f=fair(p)
        c1,c2,c3=st.columns(3)
        c1.metric('Probabilidade',f'{p*100:.1f}%'); c2.metric('Odd justa',f'{f:.2f}')
        odd=c3.number_input('Odd disponível',1.01,50.,round(max(f,1.30),2),.01,key=f'o_{mid}')
        e=ev(p,odd); v=verdict(p,odd,minp,minev,minodd,maxodd)
        c1,c2,c3=st.columns(3); c1.metric('EV',f'{e:+.2f}%'); c2.metric('Diferença vs justa',f'{(odd/f-1)*100:+.1f}%'); c3.metric('Decisão',v)
        if p>=minp and e>=minev and minodd<=odd<=maxodd:
            st.success(f'🎯 JOGADA SUGERIDA: **{market.upper()}**')
            best.append({'Jogo':f'{hn} x {an}','Mercado':market,'Prob.':p,'Odd':odd,'EV':e,'Decisão':v})

st.divider(); st.header('🏆 Melhores jogadas')
if best:
    best.sort(key=lambda x:(x['EV'],x['Prob.']),reverse=True)
    st.dataframe([{'Jogo':x['Jogo'],'Mercado':x['Mercado'],'Probabilidade':f"{x['Prob.']*100:.1f}%",'Odd':f"{x['Odd']:.2f}",'EV':f"{x['EV']:+.2f}%",'Decisão':x['Decisão']} for x in best],use_container_width=True,hide_index=True)
    x=best[0]; st.success(f"🏆 MELHOR JOGADA: **{x['Mercado'].upper()} — {x['Jogo']}** | {x['Prob.']*100:.1f}% | odd {x['Odd']:.2f} | EV {x['EV']:+.2f}%")
else: st.warning('Nenhuma jogada atingiu todos os filtros.')
st.caption('⚠️ Estimativas não são garantia de acerto ou lucro. EV depende da odd real e da qualidade dos dados.')
