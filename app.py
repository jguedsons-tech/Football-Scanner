import math
import re
from datetime import date, timedelta, datetime
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Football Scanner Pro", page_icon="⚽", layout="wide")

API = "https://v3.football.api-sports.io"
TIMEOUT = 15
DEFAULT_SEASON = 2026
BOOKS = {
    "Betano": ["betano"],
    "Superbet": ["superbet"],
    "Betão": ["betao", "betão"],
}

if "games" not in st.session_state:
    st.session_state.games = []
if "analysis" not in st.session_state:
    st.session_state.analysis = None


def key():
    try:
        return st.secrets["api"]["football_key"].strip()
    except Exception:
        return ""


def api(endpoint, params=None):
    k = key()
    if not k:
        return []
    try:
        r = requests.get(
            f"{API}/{endpoint}",
            headers={"x-apisports-key": k},
            params=params or {},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            st.error(f"API-Football: {data['errors']}")
            return []
        return data.get("response", []) or []
    except requests.RequestException as e:
        st.error(f"Erro de conexão com a API-Football: {e}")
    except Exception as e:
        st.error(f"Erro na API: {e}")
    return []


@st.cache_data(ttl=300, show_spinner=False)
def fixtures(day, status="NS-TBD"):
    return api("fixtures", {"date": day, "timezone": "America/Sao_Paulo", "status": status})


@st.cache_data(ttl=1800, show_spinner=False)
def prediction(fid):
    x = api("predictions", {"fixture": fid})
    return x[0] if x else {}


@st.cache_data(ttl=1800, show_spinner=False)
def team_stats(team, league, season):
    if not team or not league or not season:
        return {}
    x = api("teams/statistics", {"team": team, "league": league, "season": season})
    return x[0] if x else {}


@st.cache_data(ttl=600, show_spinner=False)
def odds(fid):
    return api("odds", {"fixture": fid})


def f(v, default=0.0):
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


def pmf(lmb, goals):
    return math.exp(-lmb) * lmb ** goals / math.factorial(goals)


def poisson_total(lmb, line, over_market=True):
    if lmb <= 0:
        return 0.0 if over_market else 1.0
    # Para linhas .5, a fórmula é exata com floor(line).
    n = math.floor(line)
    p_under_or_equal = sum(pmf(lmb, i) for i in range(n + 1))
    return max(0.0, min(1.0, 1 - p_under_or_equal if over_market else p_under_or_equal))


def one_x_two(home_lmb, away_lmb, max_goals=12):
    probs = [0.0, 0.0, 0.0]
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            p = pmf(home_lmb, hg) * pmf(away_lmb, ag)
            if hg > ag:
                probs[0] += p
            elif hg == ag:
                probs[1] += p
            else:
                probs[2] += p
    total = sum(probs)
    return [p / total for p in probs] if total else [0.0, 0.0, 0.0]


def btts(home_lmb, away_lmb):
    return max(0.0, min(1.0, 1 - math.exp(-home_lmb) - math.exp(-away_lmb) + math.exp(-(home_lmb + away_lmb))))


def avg_goals(stats, side, kind):
    try:
        value = stats.get("goals", {}).get(kind, {}).get("average", {}).get(side)
        return f(value, 0.0)
    except Exception:
        return 0.0


def safe_prediction_goal(pred, side):
    try:
        return f(pred.get("goals", {}).get(side), 0.0)
    except Exception:
        return 0.0


def model(game):
    teams = game.get("teams", {})
    league = game.get("league", {})
    home = teams.get("home", {})
    away = teams.get("away", {})
    lid = league.get("id")
    season = league.get("season") or DEFAULT_SEASON

    hs = team_stats(home.get("id"), lid, season) if lid else {}
    aws = team_stats(away.get("id"), lid, season) if lid else {}
    pred = prediction(game.get("fixture", {}).get("id"))

    # Baseia-se primeiro nos dados da própria API. Quando faltam dados,
    # usa apenas um baseline moderado e marca a qualidade posteriormente.
    h_for = avg_goals(hs, "home", "for")
    h_against = avg_goals(hs, "home", "against")
    a_for = avg_goals(aws, "away", "for")
    a_against = avg_goals(aws, "away", "against")

    components_h = [x for x in (h_for, a_against) if x > 0]
    components_a = [x for x in (a_for, h_against) if x > 0]

    h = sum(components_h) / len(components_h) if components_h else 1.25
    a = sum(components_a) / len(components_a) if components_a else 1.05

    ph = safe_prediction_goal(pred, "home")
    pa = safe_prediction_goal(pred, "away")
    if ph > 0:
        h = 0.65 * ph + 0.35 * h
    if pa > 0:
        a = 0.65 * pa + 0.35 * a

    h = max(0.05, min(h, 5.0))
    a = max(0.05, min(a, 5.0))

    data_points = sum(x > 0 for x in (h_for, h_against, a_for, a_against))
    if ph > 0:
        data_points += 1
    if pa > 0:
        data_points += 1
    completeness = data_points / 6

    return h, a, pred, completeness


def bookmaker(name):
    n = norm(name)
    for canonical, aliases in BOOKS.items():
        if any(norm(alias) in n for alias in aliases):
            return canonical
    return None


def parse_odds(raw):
    result = []
    for item in raw:
        bm = item.get("bookmaker", {})
        bn = bookmaker(bm.get("name", ""))
        if not bn:
            continue
        for bet in bm.get("bets", []) or []:
            market = bet.get("name", "")
            for value in bet.get("values", []) or []:
                odd = f(value.get("odd"), 0)
                if odd > 1:
                    result.append({
                        "Casa": bn,
                        "Mercado": market,
                        "Seleção": value.get("value", ""),
                        "Odd": odd,
                    })
    return result


def extract_line(selection):
    nums = re.findall(r"\d+(?:\.\d+)?", str(selection).replace(",", "."))
    return float(nums[-1]) if nums else None


def probability(market, selection, home_lmb, away_lmb, corner_total=9.0, card_total=4.2):
    m = norm(market)
    s = norm(selection)
    total = home_lmb + away_lmb
    p_1x2 = one_x_two(home_lmb, away_lmb)

    if any(x in m for x in ("match winner", "1x2", "winner", "resultado")):
        if s in ("home", "1", "casa"):
            return p_1x2[0]
        if s in ("draw", "x", "empate"):
            return p_1x2[1]
        if s in ("away", "2", "fora", "visitante"):
            return p_1x2[2]

    if "both teams" in m or "btts" in m or "ambas" in m:
        q = btts(home_lmb, away_lmb)
        if s in ("yes", "sim"):
            return q
        if s in ("no", "nao"):
            return 1 - q

    line = extract_line(selection)
    if line is None:
        return None

    if any(x in m for x in ("goals", "goal", "total goals", "gols")):
        if "over" in s or "mais" in s:
            return poisson_total(total, line, True)
        if "under" in s or "menos" in s:
            return poisson_total(total, line, False)

    if any(x in m for x in ("corner", "escanteio")):
        if "over" in s or "mais" in s:
            return poisson_total(corner_total, line, True)
        if "under" in s or "menos" in s:
            return poisson_total(corner_total, line, False)

    if any(x in m for x in ("card", "yellow", "cartao")):
        if "over" in s or "mais" in s:
            return poisson_total(card_total, line, True)
        if "under" in s or "menos" in s:
            return poisson_total(card_total, line, False)

    return None


def fixture_label(game):
    ts = game.get("fixture", {}).get("timestamp")
    if ts:
        try:
            hhmm = datetime.fromtimestamp(ts).strftime("%H:%M")
        except Exception:
            hhmm = "--:--"
    else:
        hhmm = "--:--"
    h = game.get("teams", {}).get("home", {}).get("name", "Casa")
    a = game.get("teams", {}).get("away", {}).get("name", "Fora")
    return f"{hhmm} | {h} x {a}"


def decision(prob, ev, odd, min_prob, min_ev):
    if prob >= min_prob and ev >= min_ev and 1.30 <= odd <= 3.50:
        if ev >= 0.15 and prob >= 0.70:
            return "🟢 ENTRADA FORTE"
        return "🟢 ENTRADA"
    if prob >= min_prob and ev >= 0:
        return "🟡 VALOR PEQUENO"
    return "🔴 NÃO APOSTAR"


if not key():
    st.title("⚽ Football Scanner Pro")
    st.warning("Configure a API Key nos Secrets do Streamlit.")
    st.code('[api]\nfootball_key = "SUA_API_KEY"', language="toml")
    st.stop()

st.title("⚽ Football Scanner Pro")
st.caption("API-Football • 1X2 • Gols • BTTS • Escanteios • Cartões • Odds")

with st.sidebar:
    st.header("Filtros")
    minp = st.slider("Probabilidade mínima", 50, 90, 65) / 100
    minev = st.slider("EV mínimo (%)", -20, 30, 5) / 100
    minodd = st.number_input("Odd mínima", 1.01, 10.0, 1.30, 0.05)
    maxodd = st.number_input("Odd máxima", 1.05, 20.0, 3.50, 0.05)
    maxgames = st.slider("Máximo de jogos", 1, 15, 8)
    st.caption("Casas consideradas: Betano • Superbet • Betão")

b1, b2, b3, b4 = st.tabs(["🔎 Buscar jogo", "🤖 Scanner automático", "📊 Análise", "ℹ️ Informações"])

with b1:
    selected_date = st.selectbox(
        "Data",
        [date.today(), date.today() + timedelta(days=1)],
        format_func=lambda x: x.strftime("%d/%m/%Y"),
    )
    if st.button("🔍 Procurar jogos", type="primary", use_container_width=True):
        with st.spinner("Buscando jogos..."):
            st.session_state.games = fixtures(selected_date.isoformat())
            st.session_state.analysis = None

    if st.session_state.games:
        idx = st.selectbox(
            "Partida",
            range(len(st.session_state.games)),
            format_func=lambda i: fixture_label(st.session_state.games[i]),
        )
        if st.button("📊 Analisar jogo selecionado", type="primary", use_container_width=True):
            g = st.session_state.games[idx]
            with st.spinner("Consultando estatísticas, prediction e odds..."):
                h, a, pr, completeness = model(g)
                raw = parse_odds(odds(g["fixture"]["id"]))
                rows = []
                for item in raw:
                    p = probability(item["Mercado"], item["Seleção"], h, a)
                    if p is None or p <= 0:
                        continue
                    ev = p * item["Odd"] - 1
                    item = dict(item)
                    item["Probabilidade"] = p * 100
                    item["Odd justa"] = 1 / p
                    item["EV"] = ev * 100
                    item["Decisão"] = decision(p, ev, item["Odd"], minp, minev)
                    if p >= minp and ev >= minev and minodd <= item["Odd"] <= maxodd:
                        rows.append(item)
                rows.sort(key=lambda x: x["EV"], reverse=True)
                st.session_state.analysis = {
                    "g": g, "h": h, "a": a, "p": one_x_two(h, a),
                    "btts": btts(h, a), "rows": rows, "pr": pr,
                    "completeness": completeness,
                }

        st.success(f"{len(st.session_state.games)} jogos encontrados")

with b2:
    st.write("O scanner usa apenas as casas configuradas: **Betano, Superbet e Betão**.")
    if st.button("🚀 Executar scanner", type="primary", use_container_width=True):
        games = fixtures(date.today().isoformat())[:maxgames]
        rows = []
        if not games:
            st.warning("Nenhum jogo encontrado para hoje.")
        else:
            bar = st.progress(0)
            for j, game in enumerate(games):
                try:
                    h, a, _, completeness = model(game)
                    if completeness < 0.33:
                        bar.progress((j + 1) / len(games))
                        continue
                    for item in parse_odds(odds(game["fixture"]["id"])):
                        p = probability(item["Mercado"], item["Seleção"], h, a)
                        if p is None or p <= 0:
                            continue
                        ev = p * item["Odd"] - 1
                        if p >= minp and ev >= minev and minodd <= item["Odd"] <= maxodd:
                            rows.append({
                                "Jogo": fixture_label(game),
                                "Casa": item["Casa"],
                                "Mercado": item["Mercado"],
                                "Seleção": item["Seleção"],
                                "Odd": item["Odd"],
                                "Probabilidade": round(p * 100, 2),
                                "Odd justa": round(1 / p, 2),
                                "EV": round(ev * 100, 2),
                                "Decisão": decision(p, ev, item["Odd"], minp, minev),
                            })
                except Exception as e:
                    st.warning(f"Erro em {fixture_label(game)}: {e}")
                bar.progress((j + 1) / len(games))

            if rows:
                df = pd.DataFrame(rows).sort_values("EV", ascending=False)
                st.subheader("🏆 Melhores jogadas")
                st.dataframe(df, use_container_width=True, hide_index=True)
                best = df.iloc[0]
                st.success(
                    f"🎯 JOGADA SUGERIDA: {best['Jogo']} — {best['Mercado']} {best['Seleção']} "
                    f"@ {best['Odd']:.2f} | Prob. {best['Probabilidade']:.1f}% | EV {best['EV']:.1f}%"
                )
            else:
                st.info("Nenhuma oportunidade passou pelos filtros.")

with b3:
    result = st.session_state.analysis
    if not result:
        st.info("Selecione um jogo na aba Buscar jogo.")
    else:
        st.header(fixture_label(result["g"]))
        h, a = result["h"], result["a"]
        p = result["p"]
        cols = st.columns(5)
        cols[0].metric("Casa", f"{p[0] * 100:.1f}%")
        cols[1].metric("Empate", f"{p[1] * 100:.1f}%")
        cols[2].metric("Fora", f"{p[2] * 100:.1f}%")
        cols[3].metric("BTTS", f"{result['btts'] * 100:.1f}%")
        cols[4].metric("Dados", f"{result['completeness'] * 100:.0f}%")

        st.write(f"**Gols esperados:** {h:.2f} x {a:.2f} — total {h + a:.2f}")
        st.subheader("Over/Under")
        ou = pd.DataFrame([
            {"Linha": x, "Over %": round(poisson_total(h + a, x, True) * 100, 2),
             "Under %": round(poisson_total(h + a, x, False) * 100, 2)}
            for x in (0.5, 1.5, 2.5, 3.5, 4.5)
        ])
        st.dataframe(ou, use_container_width=True, hide_index=True)

        st.subheader("💰 Oportunidades")
        if result["rows"]:
            df = pd.DataFrame(result["rows"])
            st.dataframe(df, use_container_width=True, hide_index=True)
            best = df.iloc[0]
            st.success(
                f"🎯 JOGADA SUGERIDA: {best['Casa']} — {best['Mercado']} {best['Seleção']} "
                f"@ {best['Odd']:.2f} | Prob. {best['Probabilidade']:.1f}% | EV {best['EV']:.1f}%"
            )
        else:
            st.info("Nenhuma odd das casas selecionadas passou pelos filtros.")

        pr = result["pr"].get("predictions", {})
        winner = pr.get("winner", {}) if isinstance(pr, dict) else {}
        if pr:
            st.info(
                f"Prediction API-Football: {winner.get('name', 'não informado')} • "
                f"{pr.get('under_over', '')} • {pr.get('advice', '')}"
            )

with b4:
    st.subheader("ℹ️ Como funciona")
    st.markdown(
        """
        **Fonte:** API-Football.

        O programa consulta jogos, estatísticas das equipes, Prediction e odds disponíveis. "Odd justa" é calculada como `1 / probabilidade` e o EV como `probabilidade × odd − 1`.

        A recomendação só aparece quando a probabilidade, EV e faixa de odd passam pelos filtros. O programa não promete 90%, 95% ou qualquer taxa garantida de acerto.

        **Importante:** escanteios e cartões podem não estar disponíveis para todas as competições. Quando não existem dados específicos suficientes, o programa usa uma referência estatística-base e reduz a confiança da análise.

        O cache foi mantido para reduzir o número de chamadas à API-Football.
        """
    )
