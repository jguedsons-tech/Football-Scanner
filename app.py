import math
import re
import unicodedata
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

API_BASE = "https://v3.football.api-sports.io"

BOOKS = {
    "Betano": ["betano", "betano brasil", "betano.com", "betano.pt"],
    "Superbet": ["superbet", "superbet brasil", "superbet.ro"],
    "Betão": ["betao", "betão", "betao.bet", "betão.bet"],
}

st.set_page_config(page_title="Football Scanner", page_icon="⚽", layout="wide")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def get_key():
    try:
        return st.secrets["api"]["football_key"]
    except Exception:
        return ""


@st.cache_data(ttl=120, show_spinner=False)
def api_get(endpoint, key, params_tuple=()):
    if not key:
        raise RuntimeError("Chave da API-Football não configurada nos Secrets do Streamlit.")
    params = dict(params_tuple)
    try:
        r = requests.get(
            API_BASE + endpoint,
            headers={"x-apisports-key": key},
            params=params,
            timeout=25,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de conexão com a API-Football: {e}") from e
    except ValueError as e:
        raise RuntimeError("A API-Football devolveu uma resposta inválida.") from e

    errors = data.get("errors") or {}
    if errors:
        raise RuntimeError("API-Football: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))
    return data.get("response", [])


def api(endpoint, key, params=None):
    return api_get(endpoint, key, tuple(sorted((params or {}).items())))


def fixtures_on_date(key, day):
    # A API-Football aceita 'date' diretamente; evita o erro de usar from/to sem os demais parâmetros.
    return api("/fixtures", key, {"date": str(day), "timezone": "America/Sao_Paulo"})


FREE_MAX_DAYS_AHEAD = 1  # No plano Free, mantemos a busca em hoje + amanhã.

def allowed_fixture_window():
    today = date.today()
    return today, today + timedelta(days=FREE_MAX_DAYS_AHEAD)

@st.cache_data(ttl=120, show_spinner=False)
def fixtures_range(key, start_day, end_day):
    # O plano Free da API-Football limita o acesso a uma janela curta de datas.
    # Clampar a consulta evita que o app tente buscar datas bloqueadas.
    allowed_start, allowed_end = allowed_fixture_window()
    start_day = max(start_day, allowed_start)
    end_day = min(end_day, allowed_end)

    if start_day > end_day:
        return []

    all_fixtures = []
    d = start_day
    while d <= end_day:
        try:
            all_fixtures.extend(fixtures_on_date(key, d))
        except RuntimeError as e:
            msg = str(e)
            if "do not have access to this date" in msg.lower() or "try from" in msg.lower():
                continue
            raise
        d += timedelta(days=1)
    return all_fixtures


def fixture_name(f):
    return f'{f["teams"]["home"]["name"]} x {f["teams"]["away"]["name"]}'


def parse_query(text):
    q = norm(text)
    parts = re.split(r"\s+x\s+|\s+vs?\.?\s+|\s+-\s+", q)
    return [p.strip() for p in parts if p.strip()]


def search_games(key, text, start_day, end_day):
    fs = fixtures_range(key, start_day, end_day)
    q = norm(text)
    parts = parse_query(text)

    upcoming = [f for f in fs if f.get("fixture", {}).get("status", {}).get("short") in ("NS", "TBD")]
    if not parts:
        return upcoming

    if len(parts) >= 2:
        a, b = parts[0], parts[1]
        exact = []
        for f in upcoming:
            h = norm(f["teams"]["home"]["name"])
            aw = norm(f["teams"]["away"]["name"])
            if (a in h and b in aw) or (a in aw and b in h):
                exact.append(f)
        if exact:
            return exact

    tokens = [t for t in q.split() if len(t) >= 3]
    scored = []
    for f in upcoming:
        names = norm(fixture_name(f))
        score = sum(1 for t in tokens if t in names)
        if score:
            scored.append((score, f))
    scored.sort(key=lambda x: (-x[0], x[1]["fixture"]["date"]))
    return [f for _, f in scored]


def pois(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def poisson_probs(lam, max_goals=10):
    vals = [pois(k, lam) for k in range(max_goals + 1)]
    s = sum(vals)
    return [v / s for v in vals]


def over_prob(lam, line):
    # Whole-number line: P(total > line); half line: equivalent threshold via ceil.
    threshold = math.floor(line) if float(line).is_integer() else math.floor(line)
    return 1.0 - sum(pois(k, lam) for k in range(threshold + 1))


def under_prob(lam, line):
    if float(line).is_integer():
        return sum(pois(k, lam) for k in range(int(line)))
    return sum(pois(k, lam) for k in range(math.floor(line) + 1))


def one_x_two(lh, la):
    ph = pa = pd = 0.0
    for i in range(11):
        for j in range(11):
            p = pois(i, lh) * pois(j, la)
            if i > j:
                ph += p
            elif i < j:
                pa += p
            else:
                pd += p
    s = ph + pd + pa
    return ph / s, pd / s, pa / s


def btts_prob(lh, la):
    return 1 - math.exp(-lh) - math.exp(-la) + math.exp(-(lh + la))


def safe_num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def stat_value(stats, *wanted):
    wanted = {norm(x) for x in wanted}
    for item in stats or []:
        name = norm(item.get("type", ""))
        if name in wanted:
            val = item.get("value")
            if val is None:
                return 0.0
            if isinstance(val, str):
                val = val.replace("%", "").replace("-", "0")
            return safe_num(val)
    return 0.0


@st.cache_data(ttl=300, show_spinner=False)
def fixture_stats(key, fixture_id):
    try:
        return api("/fixtures/statistics", key, {"fixture": fixture_id})
    except RuntimeError:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def team_recent(key, team_id, before_day, n):
    # 'last' is valid with team. It avoids from/to entirely.
    fs = api("/fixtures", key, {"team": team_id, "last": n, "status": "FT", "timezone": "America/Sao_Paulo"})
    return [f for f in fs if f.get("fixture", {}).get("date", "")[:10] < str(before_day)]


def team_metrics(key, team_id, before_day, n=8):
    fs = team_recent(key, team_id, before_day, n)
    gf = ga = corners_for = corners_against = cards_for = cards_against = 0.0
    games = 0

    for f in fs:
        h = f["teams"]["home"]["id"] == team_id
        goals_h = safe_num(f.get("goals", {}).get("home"))
        goals_a = safe_num(f.get("goals", {}).get("away"))
        if h:
            gf += goals_h
            ga += goals_a
        else:
            gf += goals_a
            ga += goals_h

        ss = fixture_stats(key, f["fixture"]["id"])
        mine = {}
        other = {}
        for side in ss:
            tid = side.get("team", {}).get("id")
            if tid == team_id:
                mine = side.get("statistics", [])
            else:
                other = side.get("statistics", [])
        corners_for += stat_value(mine, "Corner Kicks", "Corners")
        corners_against += stat_value(other, "Corner Kicks", "Corners")
        cards_for += stat_value(mine, "Yellow Cards", "Yellow card")
        cards_against += stat_value(other, "Yellow Cards", "Yellow card")
        games += 1

    if games == 0:
        return {"gf": 1.2, "ga": 1.2, "cf": 4.5, "ca": 4.5, "yf": 1.5, "ya": 1.5, "games": 0}

    return {
        "gf": gf / games,
        "ga": ga / games,
        "cf": corners_for / games,
        "ca": corners_against / games,
        "yf": cards_for / games,
        "ya": cards_against / games,
        "games": games,
    }


@st.cache_data(ttl=300, show_spinner=False)
def h2h(key, home_id, away_id, n=8):
    try:
        return api("/fixtures/headtohead", key, {"h2h": f"{home_id}-{away_id}", "last": n})
    except RuntimeError:
        return []


def model_for_fixture(key, f, n=8):
    home_id = f["teams"]["home"]["id"]
    away_id = f["teams"]["away"]["id"]
    match_day = f["fixture"]["date"][:10]

    hm = team_metrics(key, home_id, match_day, n)
    am = team_metrics(key, away_id, match_day, n)

    hs = [x for x in h2h(key, home_id, away_id, min(n, 5)) if x.get("fixture", {}).get("status", {}).get("short") == "FT"]
    h2h_h = h2h_a = 0.0
    if hs:
        for x in hs:
            h2h_h += safe_num(x.get("goals", {}).get("home"))
            h2h_a += safe_num(x.get("goals", {}).get("away"))
        h2h_h /= len(hs)
        h2h_a /= len(hs)

    lh = max(0.15, 0.55 * hm["gf"] + 0.25 * am["ga"] + 0.20 * (h2h_h or hm["gf"]))
    la = max(0.15, 0.55 * am["gf"] + 0.25 * hm["ga"] + 0.20 * (h2h_a or am["gf"]))

    corners = max(2.0, (hm["cf"] + am["ca"] + am["cf"] + hm["ca"]) / 2)
    cards = max(1.0, (hm["yf"] + am["ya"] + am["yf"] + hm["ya"]) / 2)

    ph, px, pa = one_x_two(lh, la)
    btts = btts_prob(lh, la)

    return {
        "home_lambda": lh,
        "away_lambda": la,
        "goals_lambda": lh + la,
        "corners_lambda": corners,
        "cards_lambda": cards,
        "home": ph,
        "draw": px,
        "away": pa,
        "btts_yes": btts,
        "btts_no": 1 - btts,
        "home_stats": hm,
        "away_stats": am,
    }


def bookmaker_match(name):
    n = norm(name)
    for canonical, aliases in BOOKS.items():
        if any(norm(a) == n or norm(a) in n or n in norm(a) for a in aliases):
            return canonical
    return None


@st.cache_data(ttl=120, show_spinner=False)
def get_odds(key, fixture_id):
    return api("/odds", key, {"fixture": fixture_id})


def parse_odd_value(v):
    try:
        x = float(str(v).replace(",", "."))
        return x if x > 1 else None
    except Exception:
        return None


def extract_target_odds(raw):
    rows = []
    for block in raw or []:
        for bm in block.get("bookmakers", []):
            canonical = bookmaker_match(bm.get("name", ""))
            if not canonical:
                continue
            for bet in bm.get("bets", []):
                market = norm(bet.get("name", ""))
                for value in bet.get("values", []):
                    odd = parse_odd_value(value.get("odd"))
                    if not odd:
                        continue
                    label = str(value.get("value", "")).strip()
                    rows.append({
                        "Casa": canonical,
                        "Mercado API": bet.get("name", ""),
                        "Seleção": label,
                        "Odd": odd,
                        "market_norm": market,
                    })
    return rows


def probability_for_row(row, m):
    market = row["market_norm"]
    sel = norm(row["Seleção"])

    if "match winner" in market or market == "1x2" or "moneyline" in market:
        if sel in ("home", "1"):
            return m["home"]
        if sel in ("draw", "x"):
            return m["draw"]
        if sel in ("away", "2"):
            return m["away"]

    if "both teams to score" in market or "both teams score" in market or "btts" in market:
        if "yes" in sel or "sim" in sel:
            return m["btts_yes"]
        if "no" in sel or "nao" in sel:
            return m["btts_no"]

    # Goals totals
    if "total" in market or "goals" in market or "over under" in market:
        match = re.search(r"(\d+(?:\.\d+)?)", sel)
        if match:
            line = float(match.group(1))
            if "over" in sel or "mais" in sel:
                return over_prob(m["goals_lambda"], line)
            if "under" in sel or "menos" in sel:
                return under_prob(m["goals_lambda"], line)

    # Corners/cards are approximate Poisson models based on recent statistics.
    if "corner" in market:
        match = re.search(r"(\d+(?:\.\d+)?)", sel)
        if match:
            line = float(match.group(1))
            if "over" in sel or "mais" in sel:
                return over_prob(m["corners_lambda"], line)
            if "under" in sel or "menos" in sel:
                return under_prob(m["corners_lambda"], line)

    if "card" in market or "yellow" in market:
        match = re.search(r"(\d+(?:\.\d+)?)", sel)
        if match:
            line = float(match.group(1))
            if "over" in sel or "mais" in sel:
                return over_prob(m["cards_lambda"], line)
            if "under" in sel or "menos" in sel:
                return under_prob(m["cards_lambda"], line)

    return None


def analyze_fixture(key, f, n, min_prob):
    model = model_for_fixture(key, f, n)
    rows = []
    try:
        odds_raw = get_odds(key, f["fixture"]["id"])
        odds = extract_target_odds(odds_raw)
    except RuntimeError as e:
        odds = []
        st.warning(str(e))

    for row in odds:
        p = probability_for_row(row, model)
        if p is None:
            continue
        fair = 1 / p if p > 0 else 0
        ev = p * row["Odd"] - 1
        if p >= min_prob:
            rows.append({
                "Jogo": fixture_name(f),
                "Casa": row["Casa"],
                "Mercado": row["Mercado API"],
                "Seleção": row["Seleção"],
                "Prob. modelo": round(p * 100, 2),
                "Odd": row["Odd"],
                "Odd justa": round(fair, 2),
                "EV": round(ev * 100, 2),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["EV", "Prob. modelo"], ascending=False)
    return model, df


def main():
    st.title("⚽ Football Scanner")
    st.caption("Scanner estatístico para Betano, Superbet e Betão")

    key = get_key()
    if not key:
        st.error("Chave da API-Football não encontrada. No Streamlit Cloud, use Settings → Secrets.")
        st.code('[api]\nfootball_key = "SUA_CHAVE_AQUI"', language="toml")
        st.stop()

    with st.sidebar:
        st.header("⚙️ Configuração")
        days = st.slider("Dias para pesquisar", 1, FREE_MAX_DAYS_AHEAD, FREE_MAX_DAYS_AHEAD)
        sample = st.slider("Jogos recentes por time", 5, 10, 8)
        min_prob = st.slider("Probabilidade mínima", 50, 90, 65) / 100
        max_games = st.slider("Máximo de jogos no automático", 1, 20, 5)
        st.divider()
        st.write("Casas: Betano · Superbet · Betão")
        st.caption("As probabilidades são estimativas estatísticas; não há garantia de lucro.")

    auto, manual, info = st.tabs(["🔥 Automático", "🎯 Buscar jogo", "📊 Informações"])

    with auto:
        allowed_start, allowed_end = allowed_fixture_window()
        st.write(f"Plano Free: pesquisa de **{allowed_start.strftime('%d/%m')}** até **{allowed_end.strftime('%d/%m')}** (hoje + amanhã).")
        if st.button("🔎 Escanear jogos agora", type="primary", use_container_width=True):
            try:
                start = date.today()
                end = start + timedelta(days=days)
                fs = [f for f in fixtures_range(key, start, end)
                      if f.get("fixture", {}).get("status", {}).get("short") in ("NS", "TBD")]
                fs = fs[:max_games]
                if not fs:
                    st.info("Nenhum jogo próximo encontrado no período escolhido.")
                else:
                    bar = st.progress(0)
                    all_rows = []
                    for i, f in enumerate(fs, 1):
                        try:
                            _, df = analyze_fixture(key, f, sample, min_prob)
                            if not df.empty:
                                all_rows.append(df)
                        except Exception as e:
                            st.warning(f"{fixture_name(f)}: {e}")
                        bar.progress(i / len(fs))
                    if all_rows:
                        result = pd.concat(all_rows, ignore_index=True)
                        st.dataframe(result, use_container_width=True, hide_index=True)
                        st.download_button("⬇️ Baixar CSV", result.to_csv(index=False).encode("utf-8-sig"), "football_scanner.csv", "text/csv", use_container_width=True)
                    else:
                        st.info("Nenhuma oportunidade atingiu a probabilidade mínima com as odds disponíveis das casas selecionadas.")
            except Exception as e:
                st.error(str(e))

    with manual:
        q = st.text_input("Digite o jogo", placeholder="Ex.: Flamengo x Palmeiras")
        if st.button("🔍 Procurar jogo", type="primary", use_container_width=True):
            if not q.strip():
                st.warning("Digite o nome dos dois times.")
            else:
                try:
                    _, allowed_end = allowed_fixture_window()
                    ms = search_games(key, q, date.today(), allowed_end)
                    if not ms:
                        st.warning("Jogo não encontrado na janela disponível do plano Free (hoje + amanhã).")
                    else:
                        options = {f'{fixture_name(f)} — {f["fixture"]["date"]}': f for f in ms[:20]}
                        selected = st.selectbox("Selecione o jogo", list(options))
                        if st.button("📊 Analisar jogo", use_container_width=True):
                            f = options[selected]
                            try:
                                model, df = analyze_fixture(key, f, sample, min_prob)
                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric("1", f'{model["home"]*100:.1f}%')
                                c2.metric("X", f'{model["draw"]*100:.1f}%')
                                c3.metric("2", f'{model["away"]*100:.1f}%')
                                c4.metric("BTTS Sim", f'{model["btts_yes"]*100:.1f}%')
                                st.write(f"Gols esperados: **{model['goals_lambda']:.2f}** · Escanteios: **{model['corners_lambda']:.2f}** · Cartões: **{model['cards_lambda']:.2f}**")
                                if df.empty:
                                    st.info("Nenhuma oportunidade acima do filtro com odds disponíveis.")
                                else:
                                    st.dataframe(df, use_container_width=True, hide_index=True)
                            except Exception as e:
                                st.error(str(e))
                except Exception as e:
                    st.error(str(e))

    with info:
        st.markdown("""
### Como funciona

O app consulta a API-Football e usa jogos recentes, gols, escanteios, cartões e H2H para estimar probabilidades.

**Plano Free:** a busca de jogos futuros fica limitada à janela de datas permitida pela API (neste app: hoje + amanhã). Para ampliar o horizonte, é necessário um plano da API que permita essas datas.

**EV** = probabilidade estimada × odd − 1.

A **odd justa** é aproximadamente 1 ÷ probabilidade.

As odds exibidas são filtradas para **Betano, Superbet e Betão**. A disponibilidade de casas e mercados depende dos dados fornecidos pela API para cada competição/jogo.

> Importante: probabilidade estatística não é garantia de acerto nem de lucro. Uma aposta só tem valor quando a estimativa é suficientemente superior à probabilidade implícita da odd.
""")


if __name__ == "__main__":
    main()
