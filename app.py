import math
import re
from datetime import date, timedelta, datetime, timezone
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Football Scanner Pro - OpenFootAPI", page_icon="⚽", layout="wide")

API = "https://openfootapi.com/v1"
TIMEOUT = 15

if "games" not in st.session_state:
    st.session_state.games = []
if "analysis" not in st.session_state:
    st.session_state.analysis = None


def key():
    try:
        return st.secrets["OPENFOOT_API_KEY"].strip()
    except Exception:
        try:
            return st.secrets["api"]["OPENFOOT_API_KEY"].strip()
        except Exception:
            return os.getenv("OPENFOOT_API_KEY", "").strip()


def api(endpoint, params=None, show_error=True):
    k = key()
    if not k:
        return []
    try:
        r = requests.get(
            f"{API}/{endpoint.lstrip('/')}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {k}"},
            params=params or {}, timeout=TIMEOUT,
        )
        try:
            body = r.json()
        except Exception:
            body = {}
        if not r.ok:
            err = body.get("error", {}) if isinstance(body, dict) else {}
            msg = err.get("message", f"HTTP {r.status_code}")
            code = err.get("code", "")
            if show_error:
                st.warning(f"OpenFootAPI: {code} — {msg}" if code else f"OpenFootAPI: {msg}")
            return []
        return body.get("data", []) if isinstance(body, dict) else []
    except requests.RequestException as e:
        if show_error:
            st.warning(f"Erro de conexão com a OpenFootAPI: {e}")
    return []


@st.cache_data(ttl=300, show_spinner=False)
def matches(day, status="scheduled"):
    return api("matches", {"date": day, "status": status}, show_error=False)


@st.cache_data(ttl=1800, show_spinner=False)
def context(match_id):
    x = api(f"matches/{match_id}/context", show_error=False)
    return x if isinstance(x, dict) else {}


@st.cache_data(ttl=1800, show_spinner=False)
def standings(competition):
    return api("standings", {"competition": competition}, show_error=False)


@st.cache_data(ttl=1800, show_spinner=False)
def competitions():
    return api("competitions", show_error=False)


def num(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", ".").replace("%", ""))
    except Exception:
        return default


def norm(s):
    s = str(s).lower()
    table = str.maketrans("ãáàâäéèêëíìîïóòôöúùûüçñ", "aaaaaeeeeiiiioooouuuucn")
    return re.sub(r"[^a-z0-9 ]", "", s.translate(table)).strip()


def deep_find(obj, names):
    """Busca recursivamente campos numéricos em respostas que podem variar por competição."""
    wanted = {norm(x).replace(" ", "") for x in names}
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = norm(k).replace(" ", "")
            if nk in wanted and isinstance(v, (int, float, str)):
                x = num(v, None)
                if x is not None:
                    return x
            got = deep_find(v, names)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = deep_find(v, names)
            if got is not None:
                return got
    return None


def pmf(lmb, goals):
    return math.exp(-lmb) * lmb ** goals / math.factorial(goals)


def poisson_total(lmb, line, over=True):
    if lmb <= 0:
        return 0.0 if over else 1.0
    n = math.floor(line)
    p = sum(pmf(lmb, i) for i in range(n + 1))
    return max(0.0, min(1.0, 1 - p if over else p))


def one_x_two(h, a, max_goals=12):
    p = [0.0, 0.0, 0.0]
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            q = pmf(h, hg) * pmf(a, ag)
            if hg > ag: p[0] += q
            elif hg == ag: p[1] += q
            else: p[2] += q
    total = sum(p)
    return [x / total for x in p] if total else [0.0, 0.0, 0.0]


def btts(h, a):
    return max(0.0, min(1.0, 1 - math.exp(-h) - math.exp(-a) + math.exp(-(h + a))))


def iso_time(v):
    if not v:
        return "--:--"
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone().strftime("%H:%M")
        return local
    except Exception:
        return "--:--"


def fixture_label(g):
    h = g.get("homeTeam", {}).get("name", "Casa")
    a = g.get("awayTeam", {}).get("name", "Fora")
    comp = g.get("competitionName") or g.get("competition", {}).get("name") or g.get("competitionId", "")
    return f"{iso_time(g.get('kickoffAt'))} | {h} x {a} | {comp}"


def team_blob(ctx, side):
    if not isinstance(ctx, dict):
        return {}
    x = ctx.get(side)
    return x if isinstance(x, dict) else {}


def form_points(form):
    if not form:
        return None
    s = str(form).upper()
    vals = {"W": 3, "D": 1, "L": 0}
    pts = [vals[c] for c in s if c in vals]
    return sum(pts) / (len(pts) * 3) if pts else None


def model(g):
    mid = g.get("id")
    ctx = context(mid) if mid else {}
    home = team_blob(ctx, "home")
    away = team_blob(ctx, "away")
    analytics = ctx.get("analytics", {}) if isinstance(ctx, dict) else {}

    # Se o plano devolver expectativa/xG, usa-a; caso contrário usa Elo + forma como ajuste.
    xg = analytics.get("expectedGoals", {}) if isinstance(analytics, dict) else {}
    h = deep_find(xg, ["home", "homeXg", "expectedHomeGoals", "homeExpectedGoals"])
    a = deep_find(xg, ["away", "awayXg", "expectedAwayGoals", "awayExpectedGoals"])

    if h is None or a is None:
        h = deep_find(ctx, ["homeGoalsExpected", "expectedHomeGoals", "homeGoalExpectation"])
        a = deep_find(ctx, ["awayGoalsExpected", "expectedAwayGoals", "awayGoalExpectation"])

    # Baseline moderado quando xG/goal expectation não está disponível.
    h = h if h is not None and h > 0 else 1.25
    a = a if a is not None and a > 0 else 1.05

    helo = deep_find(home, ["elo", "rating"])
    aelo = deep_find(away, ["elo", "rating"])
    if helo is not None and aelo is not None:
        diff = max(-400, min(400, helo - aelo))
        adj = diff / 1800.0
        h *= max(0.75, min(1.30, 1 + adj))
        a *= max(0.75, min(1.30, 1 - adj * 0.55))

    hf = form_points(home.get("form"))
    af = form_points(away.get("form"))
    if hf is not None and af is not None:
        d = hf - af
        h *= max(0.88, min(1.14, 1 + d * 0.18))
        a *= max(0.90, min(1.12, 1 - d * 0.12))

    h = max(0.10, min(h, 4.5))
    a = max(0.10, min(a, 4.5))

    points = sum(v is not None for v in (helo, aelo, hf, af))
    xg_available = (deep_find(xg, ["home", "homeXg", "expectedHomeGoals"]) is not None and
                    deep_find(xg, ["away", "awayXg", "expectedAwayGoals"]) is not None)
    if xg_available:
        points += 2
    completeness = min(1.0, points / 6)
    return h, a, ctx, completeness


def probability(market, selection, h, a, corner_total=9.0, card_total=4.2):
    m, s = norm(market), norm(selection)
    p = one_x_two(h, a)
    if any(x in m for x in ("match winner", "1x2", "winner", "resultado")):
        if s in ("home", "1", "casa"): return p[0]
        if s in ("draw", "x", "empate"): return p[1]
        if s in ("away", "2", "fora", "visitante"): return p[2]
    if any(x in m for x in ("btts", "both teams", "ambas")):
        q = btts(h, a)
        if s in ("yes", "sim"): return q
        if s in ("no", "nao"): return 1-q
    nums = re.findall(r"\d+(?:\.\d+)?", s.replace(",", "."))
    line = float(nums[-1]) if nums else None
    if line is None: return None
    total = h + a
    if any(x in m for x in ("goals", "goal", "total goals", "gols")):
        if "over" in s or "mais" in s: return poisson_total(total, line, True)
        if "under" in s or "menos" in s: return poisson_total(total, line, False)
    if any(x in m for x in ("corner", "escanteio")):
        if "over" in s or "mais" in s: return poisson_total(corner_total, line, True)
        if "under" in s or "menos" in s: return poisson_total(corner_total, line, False)
    if any(x in m for x in ("card", "yellow", "cartao")):
        if "over" in s or "mais" in s: return poisson_total(card_total, line, True)
        if "under" in s or "menos" in s: return poisson_total(card_total, line, False)
    return None


def suggested_market(h, a):
    p = one_x_two(h, a)
    bt = btts(h, a)
    candidates = [
        (p[0], "Casa vence (1)", "1X2"),
        (p[1], "Empate (X)", "1X2"),
        (p[2], "Fora vence (2)", "1X2"),
        (bt, "Ambas marcam — SIM", "BTTS"),
        (1-bt, "Ambas marcam — NÃO", "BTTS"),
    ]
    for line in (1.5, 2.5, 3.5):
        candidates.append((poisson_total(h+a, line, True), f"Over {line}", "Gols"))
        candidates.append((poisson_total(h+a, line, False), f"Under {line}", "Gols"))
    candidates.sort(reverse=True, key=lambda x: x[0])
    return candidates[0]


def confidence(p, completeness):
    score = p * 0.70 + completeness * 0.30
    if score >= 0.78 and completeness >= 0.50: return "🟢 FORTE"
    if score >= 0.68 and completeness >= 0.33: return "🟢 BOA"
    if score >= 0.60: return "🟡 MODERADA"
    return "🔴 FRACA"


if not key():
    st.title("⚽ Football Scanner Pro")
    st.warning("Configure sua chave da OpenFootAPI nos Secrets do Streamlit.")
    st.code('OPENFOOT_API_KEY = "of_live_SUA_CHAVE"', language="toml")
    st.stop()

st.title("⚽ Football Scanner Pro")
st.caption("OpenFootAPI • 1X2 • Gols • BTTS • Escanteios • Cartões • Probabilidades")

with st.sidebar:
    st.header("Filtros")
    minp = st.slider("Probabilidade mínima", 50, 90, 65) / 100
    maxgames = st.slider("Máximo de jogos no scanner", 1, 30, 10)
    st.caption("A versão OpenFootAPI não calcula EV nem odd justa.")

b1, b2, b3, b4 = st.tabs(["🔎 Buscar jogo", "🤖 Scanner automático", "📊 Análise", "ℹ️ Informações"])

with b1:
    selected_date = st.selectbox("Data", [date.today(), date.today()+timedelta(days=1)], format_func=lambda x: x.strftime("%d/%m/%Y"))
    if st.button("🔍 Procurar jogos", type="primary", use_container_width=True):
        with st.spinner("Buscando jogos na OpenFootAPI..."):
            st.session_state.games = matches(selected_date.isoformat())
            st.session_state.analysis = None
    if st.session_state.games:
        idx = st.selectbox("Partida", range(len(st.session_state.games)), format_func=lambda i: fixture_label(st.session_state.games[i]))
        if st.button("📊 Analisar jogo selecionado", type="primary", use_container_width=True):
            g = st.session_state.games[idx]
            with st.spinner("Analisando contexto e forma..."):
                h, a, ctx, comp = model(g)
                st.session_state.analysis = {"g":g,"h":h,"a":a,"ctx":ctx,"comp":comp}
        st.success(f"{len(st.session_state.games)} jogos encontrados")

with b2:
    st.write("Scanner automático usando os jogos disponíveis para a data selecionada.")
    scan_date = st.date_input("Data do scanner", value=date.today())
    if st.button("🚀 Executar scanner", type="primary", use_container_width=True):
        games = matches(scan_date.isoformat())[:maxgames]
        rows = []
        if not games:
            st.warning("Nenhum jogo encontrado para esta data.")
        else:
            bar = st.progress(0)
            for j,g in enumerate(games):
                try:
                    h,a,ctx,comp = model(g)
                    if comp < 0.15:
                        bar.progress((j+1)/len(games)); continue
                    p = one_x_two(h,a)
                    bt = btts(h,a)
                    opts = [
                        (p[0],"1X2","Casa vence (1)"),(p[1],"1X2","Empate (X)"),(p[2],"1X2","Fora vence (2)"),
                        (bt,"BTTS","Ambas marcam — SIM"),(1-bt,"BTTS","Ambas marcam — NÃO")]
                    for line in (1.5,2.5,3.5):
                        opts += [(poisson_total(h+a,line,True),"Gols",f"Over {line}"),(poisson_total(h+a,line,False),"Gols",f"Under {line}")]
                    pbest, market, selection = max(opts, key=lambda x:x[0])
                    if pbest >= minp:
                        rows.append({"Jogo":fixture_label(g),"Mercado":market,"Sugestão":selection,"Probabilidade":round(pbest*100,1),"Confiança":confidence(pbest,comp),"Dados":round(comp*100)})
                except Exception as e:
                    st.warning(f"Erro em {fixture_label(g)}: {e}")
                bar.progress((j+1)/len(games))
            if rows:
                df=pd.DataFrame(rows).sort_values(["Probabilidade","Dados"],ascending=False)
                st.subheader("🏆 Melhores jogadas")
                st.dataframe(df,use_container_width=True,hide_index=True)
                best=df.iloc[0]
                st.success(f"🎯 JOGADA SUGERIDA: {best['Jogo']} — {best['Mercado']} / {best['Sugestão']} | Prob. {best['Probabilidade']:.1f}% | {best['Confiança']}")
            else:
                st.info("Nenhuma sugestão atingiu a probabilidade mínima.")

with b3:
    r=st.session_state.analysis
    if not r:
        st.info("Selecione um jogo na aba Buscar jogo.")
    else:
        st.header(fixture_label(r["g"]))
        h,a=r["h"],r["a"]
        p=one_x_two(h,a); bt=btts(h,a)
        c=st.columns(5)
        c[0].metric("Casa",f"{p[0]*100:.1f}%")
        c[1].metric("Empate",f"{p[1]*100:.1f}%")
        c[2].metric("Fora",f"{p[2]*100:.1f}%")
        c[3].metric("BTTS",f"{bt*100:.1f}%")
        c[4].metric("Dados",f"{r['comp']*100:.0f}%")
        st.write(f"**Gols esperados estimados:** {h:.2f} x {a:.2f} — total {h+a:.2f}")
        st.subheader("Over/Under")
        ou=pd.DataFrame([{"Linha":x,"Over %":round(poisson_total(h+a,x,True)*100,1),"Under %":round(poisson_total(h+a,x,False)*100,1)} for x in (0.5,1.5,2.5,3.5,4.5)])
        st.dataframe(ou,use_container_width=True,hide_index=True)
        pbest,market,selection=suggested_market(h,a)
        st.success(f"🎯 JOGADA SUGERIDA: {market} — {selection} | Probabilidade estimada: {pbest*100:.1f}% | {confidence(pbest,r['comp'])}")
        ctx=r.get("ctx",{})
        if ctx:
            st.subheader("📋 Contexto disponível")
            cols=st.columns(2)
            for col,side,label in [(cols[0],"home","Mandante"),(cols[1],"away","Visitante")]:
                t=ctx.get(side,{}) if isinstance(ctx,dict) else {}
                col.write(f"**{label}:** {t.get('form','não informado')}")
                if t.get('elo') is not None: col.write(f"Elo: {t.get('elo')}")
                if t.get('restDays') is not None: col.write(f"Descanso: {t.get('restDays')} dias")

with b4:
    st.subheader("ℹ️ Sobre esta versão")
    st.markdown("""
    **Fonte:** OpenFootAPI.

    Esta conversão removeu **EV** e **odd justa**, conforme solicitado. A análise mostra probabilidades estimadas, confiança e a jogada sugerida.

    O OpenFootAPI fornece partidas, competições, classificação/form e, em planos compatíveis, contexto avançado, xG e odds. A disponibilidade varia por plano e competição.

    **Betano, Superbet e Betão:** esta versão não inventa odds dessas casas. O endpoint de odds da OpenFootAPI é de benchmark/modelo e não representa automaticamente as odds comerciais dessas três casas. Se quiser odds reais dessas casas, será necessário conectar uma fonte que realmente forneça essas cotações.

    Escanteios e cartões ficam como mercados de referência quando o usuário os solicitar, mas o Starter não garante estatísticas específicas para eles. Não há promessa de 90%, 95% ou qualquer taxa garantida de acerto.
    """)
    st.caption("Chave esperada nos Streamlit Secrets: OPENFOOT_API_KEY = \"of_live_...\"")
