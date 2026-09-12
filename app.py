import os
import math
from datetime import date
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

BASE_URL = "https://openfootapi.com/v1"
TIMEOUT = 20

st.set_page_config(page_title="Football Scanner", page_icon="⚽", layout="wide")
st.title("⚽ Football Scanner")
st.caption("OpenFootAPI • scanner de futebol no navegador")


def get_key() -> str:
    try:
        k = st.secrets.get("OPENFOOT_API_KEY", "")
    except Exception:
        k = ""
    return str(k or os.getenv("OPENFOOT_API_KEY", "")).strip()

API_KEY = get_key()


def api_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    url = BASE_URL + path
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=TIMEOUT)
        try:
            data = r.json()
        except Exception:
            data = {"error": {"message": r.text[:500]}}
        if not r.ok:
            data["_http_error"] = True
            data["_status"] = r.status_code
        return data
    except requests.RequestException as e:
        return {"_http_error": True, "_status": 0, "error": {"message": str(e)}}


def items(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    x = body.get("data", [])
    return x if isinstance(x, list) else []


def show_error(body: Dict[str, Any]):
    if body.get("_http_error") or body.get("error"):
        err = body.get("error", {})
        st.error(err.get("message", f"Erro HTTP {body.get('_status', '')}"))


def name(m: Dict[str, Any], side: str) -> str:
    x = m.get(side + "Team") or m.get(side) or {}
    return x.get("name", "?") if isinstance(x, dict) else str(x)


def score(m: Dict[str, Any]) -> str:
    s = m.get("score") or {}
    if isinstance(s, dict) and s.get("home") is not None and s.get("away") is not None:
        return f"{s['home']} x {s['away']}"
    return "-"


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def probabilities(lh: float = 1.25, la: float = 1.05) -> Dict[str, float]:
    n = 8
    ph = [poisson(i, lh) for i in range(n + 1)]
    pa = [poisson(i, la) for i in range(n + 1)]
    total = sum(ph[i] * pa[j] for i in range(n + 1) for j in range(n + 1))
    p1 = sum(ph[i] * pa[j] for i in range(n + 1) for j in range(n + 1) if i > j) / total
    px = sum(ph[i] * pa[i] for i in range(n + 1)) / total
    p2 = max(0, 1 - p1 - px)
    u25 = sum(ph[i] * pa[j] for i in range(n + 1) for j in range(n + 1) if i + j <= 2) / total
    o25 = 1 - u25
    btts = sum(ph[i] * pa[j] for i in range(1, n + 1) for j in range(1, n + 1)) / total
    return {"1": p1, "X": px, "2": p2, "Over 2.5": o25, "Under 2.5": u25, "BTTS Sim": btts, "BTTS Não": 1-btts}


def fair(p: float) -> float:
    return 1 / p if p > 0 else 999.0


def ev(p: float, odd: float) -> float:
    return (p * odd - 1) * 100


with st.sidebar:
    st.header("⚙️ Configuração")
    if API_KEY:
        st.success("API key carregada")
    else:
        st.warning("Configure OPENFOOT_API_KEY nos Secrets")
    houses = st.multiselect("Casas-alvo", ["Betano", "Superbet", "Betão"], ["Betano", "Superbet", "Betão"])
    mode = st.radio("Modo", ["Jogos por data", "Buscar", "Scanner automático", "Diagnóstico"])

if mode == "Diagnóstico":
    st.header("🔧 Diagnóstico")
    for endpoint in ["/health", "/competitions"]:
        st.subheader(endpoint)
        b = api_get(endpoint)
        show_error(b)
        st.json(b)
    st.stop()

comp_body = api_get("/competitions")
competitions = items(comp_body)
comp_map = {}
for c in competitions:
    cid = c.get("id")
    cn = c.get("name") or c.get("shortName")
    if cid is not None and cn:
        comp_map[str(cn)] = cid

if mode == "Jogos por data":
    st.header("📅 Jogos")
    d = st.date_input("Data", date.today())
    comp = st.selectbox("Competição", ["Todas"] + sorted(comp_map))
    params = {"date": d.isoformat()}
    if comp != "Todas":
        params["competition"] = comp_map[comp]
    b = api_get("/matches", params)
    show_error(b)
    ms = items(b)
    st.write(f"**{len(ms)} jogos encontrados**")
    if ms:
        st.dataframe([
            {"ID": m.get("id"), "Competição": (m.get("competition") or {}).get("name", "-"),
             "Mandante": name(m, "home"), "Visitante": name(m, "away"),
             "Status": m.get("status", "-"), "Placar": score(m), "Início": m.get("kickoffAt", "-")}
            for m in ms
        ], use_container_width=True, hide_index=True)
        mid = st.selectbox("Jogo", [m.get("id") for m in ms if m.get("id")])
        if mid:
            m = next(x for x in ms if x.get("id") == mid)
            st.subheader(f"{name(m,'home')} x {name(m,'away')}")
            ctx = api_get(f"/matches/{mid}/context")
            if ctx.get("_http_error"):
                st.info("Contexto detalhado não disponível para esta partida/plano. O modelo abaixo usa parâmetros conservadores.")
            p = probabilities()
            cols = st.columns(len(p))
            for col, (market, prob) in zip(cols, p.items()):
                col.metric(market, f"{prob*100:.1f}%", f"odd justa {fair(prob):.2f}")
            with st.expander("Contexto bruto"):
                st.json(ctx)
            with st.expander("Eventos"):
                st.json(api_get(f"/matches/{mid}/events"))
            with st.expander("xG"):
                st.json(api_get(f"/matches/{mid}/xg"))

elif mode == "Buscar":
    st.header("🔎 Buscar equipe/jogo")
    q = st.text_input("Nome", placeholder="Palmeiras, Flamengo, Colo-Colo...")
    if q:
        b = api_get("/search", {"q": q})
        show_error(b)
        st.json(b)

else:
    st.header("🤖 Scanner automático")
    d = st.date_input("Data", date.today())
    comp = st.selectbox("Competição", ["Todas"] + sorted(comp_map))
    min_prob = st.slider("Probabilidade mínima", 0.50, 0.95, 0.65, 0.01)
    if st.button("🚀 Escanear jogos", type="primary"):
        params = {"date": d.isoformat()}
        if comp != "Todas":
            params["competition"] = comp_map[comp]
        b = api_get("/matches", params)
        show_error(b)
        ms = items(b)
        rows = []
        for m in ms:
            for market, p in probabilities().items():
                if p >= min_prob:
                    rows.append({"Jogo": f"{name(m,'home')} x {name(m,'away')}", "Mercado": market,
                                 "Probabilidade": round(p*100, 1), "Odd justa": round(fair(p), 2), "ID": m.get("id")})
        rows.sort(key=lambda x: x["Probabilidade"], reverse=True)
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if rows:
            st.subheader("💰 EV")
            house = st.selectbox("Casa", houses or ["Não selecionada"])
            row = st.selectbox("Oportunidade", rows, format_func=lambda x: f"{x['Jogo']} | {x['Mercado']} | {x['Probabilidade']}%")
            odd = st.number_input("Odd oferecida", 1.01, 100.0, float(row["Odd justa"]), 0.01)
            value = ev(row["Probabilidade"]/100, odd)
            st.metric(f"EV {house}", f"{value:+.2f}%")
            if value > 0:
                st.success("EV positivo segundo a estimativa do modelo.")
            else:
                st.warning("EV não positivo segundo a estimativa do modelo.")

st.divider()
st.caption("⚠️ Probabilidades são estimativas, não garantias. Recursos avançados e cobertura estatística dependem do plano e da competição.")
