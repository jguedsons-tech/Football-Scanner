import math
from datetime import date, timedelta, datetime

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Football Scanner - Estatísticas",
    page_icon="⚽",
    layout="wide"
)

API = "https://v3.football.api-sports.io"
TIMEOUT = 15

# Quantidade máxima de jogos analisados automaticamente
MAX_AUTO_GAMES = 5

# Quantidade de jogos históricos por equipe
HISTORY_GAMES = 10

if "games" not in st.session_state:
    st.session_state.games = []

if "analysis" not in st.session_state:
    st.session_state.analysis = None

if "requests_used" not in st.session_state:
    st.session_state.requests_used = 0


# ============================================================
# API KEY
# ============================================================

def key():
    try:
        return st.secrets["api"]["football_key"].strip()
    except Exception:
        return ""


# ============================================================
# FUNÇÃO CENTRAL DA API
# ============================================================

def api(endpoint, params=None):

    try:

        response = requests.get(
            API + "/" + endpoint,
            headers={
                "x-apisports-key": key()
            },
            params=params or {},
            timeout=TIMEOUT
        )

        st.session_state.requests_used += 1

        data = response.json()

        errors = data.get("errors", {})

        if errors:
            return [], errors

        return data.get("response", []) or [], None

    except requests.RequestException as e:
        return [], {
            "connection": str(e)
        }

    except Exception as e:
        return [], {
            "error": str(e)
        }


# ============================================================
# BUSCAR JOGOS POR DATA
# ============================================================

@st.cache_data(ttl=600)
def fixtures(day):

    data, error = api(
        "fixtures",
        {
            "date": day,
            "timezone": "America/Sao_Paulo"
        }
    )

    return data


# ============================================================
# HISTÓRICO DA EQUIPE
#
# NÃO USA:
#
# teams/statistics
# season=2026
#
# ============================================================

@st.cache_data(ttl=3600)
def team_history(team_id):

    data, error = api(
        "fixtures",
        {
            "team": team_id,
            "last": HISTORY_GAMES,
            "status": "FT"
        }
    )

    if error:
        return []

    return data


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def f(value, default=0):

    try:
        return float(
            str(value)
            .replace(",", ".")
            .replace("%", "")
        )

    except Exception:
        return default


def label(game):

    timestamp = game["fixture"].get("timestamp")

    if timestamp:
        hour = datetime.fromtimestamp(timestamp).strftime("%H:%M")
    else:
        hour = "--:--"

    home = game["teams"]["home"]["name"]
    away = game["teams"]["away"]["name"]

    return f"{hour} | {home} x {away}"


# ============================================================
# CALCULAR ESTATÍSTICAS DO HISTÓRICO
# ============================================================

def calculate_team_stats(games, team_id, venue=None):

    played = []

    goals_for = []
    goals_against = []

    wins = 0
    draws = 0
    losses = 0

    over15 = 0
    over25 = 0
    under35 = 0

    btts_yes = 0

    for game in games:

        home_id = game["teams"]["home"]["id"]
        away_id = game["teams"]["away"]["id"]

        home_goals = game["goals"].get("home")
        away_goals = game["goals"].get("away")

        if home_goals is None or away_goals is None:
            continue

        is_home = home_id == team_id

        if venue == "home" and not is_home:
            continue

        if venue == "away" and is_home:
            continue

        if is_home:

            gf = home_goals
            ga = away_goals

        else:

            gf = away_goals
            ga = home_goals

        played.append(game)

        goals_for.append(gf)
        goals_against.append(ga)

        if gf > ga:
            wins += 1

        elif gf == ga:
            draws += 1

        else:
            losses += 1

        total = gf + ga

        if total >= 2:
            over15 += 1

        if total >= 3:
            over25 += 1

        if total <= 3:
            under35 += 1

        if gf > 0 and ga > 0:
            btts_yes += 1

    n = len(played)

    if n == 0:

        return {
            "games": 0,
            "gf_avg": 0,
            "ga_avg": 0,
            "win": 0,
            "draw": 0,
            "loss": 0,
            "over15": 0,
            "over25": 0,
            "under35": 0,
            "btts": 0
        }

    return {

        "games": n,

        "gf_avg": sum(goals_for) / n,

        "ga_avg": sum(goals_against) / n,

        "win": wins / n,

        "draw": draws / n,

        "loss": losses / n,

        "over15": over15 / n,

        "over25": over25 / n,

        "under35": under35 / n,

        "btts": btts_yes / n
    }


# ============================================================
# DISTRIBUIÇÃO DE POISSON
# ============================================================

def pmf(lam, goals):

    lam = max(lam, 0.01)

    return (
        math.exp(-lam)
        * lam ** goals
        / math.factorial(goals)
    )


def over(lam, line):

    n = math.floor(line)

    return max(
        0,
        min(
            1,
            1 - sum(
                pmf(lam, i)
                for i in range(n + 1)
            )
        )
    )


def under(lam, line):

    return max(
        0,
        min(
            1,
            sum(
                pmf(lam, i)
                for i in range(
                    math.floor(line) + 1
                )
            )
        )
    )


# ============================================================
# 1X2
# ============================================================

def one_x_two(home_lambda, away_lambda):

    probabilities = [0, 0, 0]

    for home_goals in range(10):

        for away_goals in range(10):

            probability = (
                pmf(home_lambda, home_goals)
                * pmf(away_lambda, away_goals)
            )

            if home_goals > away_goals:

                probabilities[0] += probability

            elif home_goals == away_goals:

                probabilities[1] += probability

            else:

                probabilities[2] += probability

    total = sum(probabilities)

    if total == 0:

        return [0, 0, 0]

    return [

        probabilities[0] / total,
        probabilities[1] / total,
        probabilities[2] / total

    ]


# ============================================================
# AMBAS MARCAM
# ============================================================

def btts(home_lambda, away_lambda):

    return max(
        0,
        min(
            1,
            1
            - math.exp(-home_lambda)
            - math.exp(-away_lambda)
            + math.exp(
                -(home_lambda + away_lambda)
            )
        )
    )


# ============================================================
# MODELO DE GOLS
# ============================================================

def build_model(home_stats, away_stats):

    home_attack = home_stats["gf_avg"]

    home_defense = home_stats["ga_avg"]

    away_attack = away_stats["gf_avg"]

    away_defense = away_stats["ga_avg"]

    # Valores mínimos para evitar modelo zerado
    if home_attack == 0:
        home_attack = 1.0

    if home_defense == 0:
        home_defense = 1.2

    if away_attack == 0:
        away_attack = 1.0

    if away_defense == 0:
        away_defense = 1.2

    expected_home = (
        0.55 * home_attack
        + 0.30 * away_defense
        + 0.15 * 1.25
    )

    expected_away = (
        0.55 * away_attack
        + 0.30 * home_defense
        + 0.15 * 1.05
    )

    return (
        max(expected_home, 0.20),
        max(expected_away, 0.20)
    )


# ============================================================
# ANÁLISE DA PARTIDA
# ============================================================

def analyze(game):

    home = game["teams"]["home"]

    away = game["teams"]["away"]

    home_history = team_history(
        home["id"]
    )

    away_history = team_history(
        away["id"]
    )

    # Estatística geral
    home_all = calculate_team_stats(
        home_history,
        home["id"]
    )

    away_all = calculate_team_stats(
        away_history,
        away["id"]
    )

    # Estatística específica de mando
    home_venue = calculate_team_stats(
        home_history,
        home["id"],
        "home"
    )

    away_venue = calculate_team_stats(
        away_history,
        away["id"],
        "away"
    )

    # Se houver poucos jogos específicos,
    # usa estatística geral
    if home_venue["games"] < 3:

        home_venue = home_all

    if away_venue["games"] < 3:

        away_venue = away_all

    home_lambda, away_lambda = build_model(
        home_venue,
        away_venue
    )

    probabilities = one_x_two(
        home_lambda,
        away_lambda
    )

    return {

        "game": game,

        "home_stats": home_venue,

        "away_stats": away_venue,

        "home_all": home_all,

        "away_all": away_all,

        "home_lambda": home_lambda,

        "away_lambda": away_lambda,

        "probabilities": probabilities,

        "btts": btts(
            home_lambda,
            away_lambda
        )

    }


# ============================================================
# INTERFACE
# ============================================================

if not key():

    st.title("⚽ Football Scanner")

    st.warning(
        "Configure sua API Key "
        "nos Secrets do Streamlit."
    )

    st.code(
        '[api]\nfootball_key = "SUA_API_KEY"',
        language="toml"
    )

    st.stop()


st.title(
    "⚽ Football Scanner"
)

st.caption(
    "Estatísticas • Gols • 1X2 • Over/Under • BTTS"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Configurações")

    maxgames = st.slider(
        "Máximo de jogos no scanner",
        1,
        MAX_AUTO_GAMES,
        3
    )

    st.divider()

    st.metric(
        "Consultas nesta sessão",
        st.session_state.requests_used
    )

    st.caption(
        "Versão econômica: sem odds, "
        "sem predictions e sem "
        "teams/statistics."
    )


# ============================================================
# ABAS
# ============================================================

b1, b2, b3, b4 = st.tabs(

    [

        "🔎 Buscar jogo",

        "🤖 Scanner",

        "📊 Análise",

        "ℹ️ Informações"

    ]

)


# ============================================================
# BUSCAR JOGO
# ============================================================

with b1:

    selected_date = st.selectbox(

        "Data",

        [

            date.today(),

            date.today()
            + timedelta(days=1)

        ],

        format_func=lambda x:
        x.strftime("%d/%m/%Y")

    )

    if st.button(

        "🔍 Procurar jogos",

        type="primary",

        use_container_width=True

    ):

        with st.spinner(
            "Buscando partidas..."
        ):

            games = fixtures(
                selected_date.isoformat()
            )

            st.session_state.games = [

                game

                for game in games

                if game
                .get(
                    "fixture",
                    {}
                )
                .get(
                    "status",
                    {}
                )
                .get(
                    "short"
                )

                in ("NS", "TBD")

            ]

        if st.session_state.games:

            st.success(
                f"{len(st.session_state.games)} "
                "jogos encontrados."
            )

        else:

            st.warning(
                "Nenhum jogo futuro encontrado."
            )

    if st.session_state.games:

        index = st.selectbox(

            "Escolha a partida",

            range(
                len(
                    st.session_state.games
                )
            ),

            format_func=lambda i:
            label(
                st.session_state.games[i]
            )

        )

        if st.button(

            "📊 Analisar jogo",

            type="primary",

            use_container_width=True

        ):

            game = (
                st.session_state.games[
                    index
                ]
            )

            with st.spinner(
                "Buscando histórico "
                "das equipes..."
            ):

                st.session_state.analysis = (
                    analyze(game)
                )

            st.success(
                "Análise concluída."
            )


# ============================================================
# SCANNER
# ============================================================

with b2:

    st.write(
        "O scanner analisa os primeiros "
        "jogos disponíveis."
    )

    if st.button(

        "🚀 Executar scanner",

        type="primary",

        use_container_width=True

    ):

        games = fixtures(
            date.today().isoformat()
        )

        games = [

            game

            for game in games

            if game
            .get(
                "fixture",
                {}
            )
            .get(
                "status",
                {}
            )
            .get(
                "short"
            )

            in ("NS", "TBD")

        ]

        games = games[:maxgames]

        results = []

        progress = st.progress(0)

        for i, game in enumerate(games):

            try:

                result = analyze(game)

                home = (
                    game["teams"]
                    ["home"]
                    ["name"]
                )

                away = (
                    game["teams"]
                    ["away"]
                    ["name"]
                )

                p = (
                    result[
                        "probabilities"
                    ]
                )

                results.append(

                    {

                        "Jogo":
                        f"{home} x {away}",

                        "Casa":
                        p[0] * 100,

                        "Empate":
                        p[1] * 100,

                        "Fora":
                        p[2] * 100,

                        "BTTS":
                        result["btts"]
                        * 100,

                        "Over 1.5":
                        over(
                            result[
                                "home_lambda"
                            ]
                            +
                            result[
                                "away_lambda"
                            ],
                            1.5
                        )
                        * 100,

                        "Over 2.5":
                        over(
                            result[
                                "home_lambda"
                            ]
                            +
                            result[
                                "away_lambda"
                            ],
                            2.5
                        )
                        * 100

                    }

                )

            except Exception as e:

                st.warning(
                    f"Erro em "
                    f"{label(game)}: {e}"
                )

            progress.progress(

                (i + 1)
                /
                max(
                    1,
                    len(games)
                )

            )

        if results:

            dataframe = pd.DataFrame(
                results
            )

            st.dataframe(

                dataframe,

                use_container_width=True,

                hide_index=True

            )

        else:

            st.info(
                "Nenhuma partida "
                "foi analisada."
            )


# ============================================================
# ANÁLISE
# ============================================================

with b3:

    result = (
        st.session_state.analysis
    )

    if not result:

        st.info(
            "Selecione uma partida "
            "na aba Buscar jogo."
        )

    else:

        game = result["game"]

        home_name = (
            game["teams"]
            ["home"]
            ["name"]
        )

        away_name = (
            game["teams"]
            ["away"]
            ["name"]
        )

        st.header(
            f"{home_name} x {away_name}"
        )

        p = (
            result[
                "probabilities"
            ]
        )

        columns = st.columns(4)

        columns[0].metric(
            "Vitória Casa",
            f"{p[0]*100:.1f}%"
        )

        columns[1].metric(
            "Empate",
            f"{p[1]*100:.1f}%"
        )

        columns[2].metric(
            "Vitória Fora",
            f"{p[2]*100:.1f}%"
        )

        columns[3].metric(
            "Ambas Marcam",
            f"{result['btts']*100:.1f}%"
        )

        st.subheader(
            "⚽ Gols esperados"
        )

        st.write(

            f"**{home_name}:** "
            f"{result['home_lambda']:.2f}"

        )

        st.write(

            f"**{away_name}:** "
            f"{result['away_lambda']:.2f}"

        )

        total = (

            result["home_lambda"]

            +

            result["away_lambda"]

        )

        st.write(
            f"**Total esperado:** "
            f"{total:.2f}"
        )


        # -----------------------------------------------
        # OVER / UNDER
        # -----------------------------------------------

        st.subheader(
            "📈 Over / Under"
        )

        goal_rows = []

        for line in [

            0.5,

            1.5,

            2.5,

            3.5,

            4.5

        ]:

            goal_rows.append(

                {

                    "Linha": line,

                    "Over":
                    over(
                        total,
                        line
                    )
                    * 100,

                    "Under":
                    under(
                        total,
                        line
                    )
                    * 100

                }

            )

        st.dataframe(

            pd.DataFrame(
                goal_rows
            ),

            use_container_width=True,

            hide_index=True

        )


        # -----------------------------------------------
        # ESTATÍSTICAS
        # -----------------------------------------------

        st.subheader(
            "📊 Estatísticas recentes"
        )

        home_stats = (
            result["home_stats"]
        )

        away_stats = (
            result["away_stats"]
        )

        stats_rows = [

            {

                "Estatística":
                "Jogos usados",

                home_name:
                home_stats["games"],

                away_name:
                away_stats["games"]

            },

            {

                "Estatística":
                "Média gols marcados",

                home_name:
                round(
                    home_stats[
                        "gf_avg"
                    ],
                    2
                ),

                away_name:
                round(
                    away_stats[
                        "gf_avg"
                    ],
                    2
                )

            },

            {

                "Estatística":
                "Média gols sofridos",

                home_name:
                round(
                    home_stats[
                        "ga_avg"
                    ],
                    2
                ),

                away_name:
                round(
                    away_stats[
                        "ga_avg"
                    ],
                    2
                )

            },

            {

                "Estatística":
                "Vitórias",

                home_name:
                f"{home_stats['win']*100:.1f}%",

                away_name:
                f"{away_stats['win']*100:.1f}%"

            },

            {

                "Estatística":
                "Empates",

                home_name:
                f"{home_stats['draw']*100:.1f}%",

                away_name:
                f"{away_stats['draw']*100:.1f}%"

            },

            {

                "Estatística":
                "Derrotas",

                home_name:
                f"{home_stats['loss']*100:.1f}%",

                away_name:
                f"{away_stats['loss']*100:.1f}%"

            },

            {

                "Estatística":
                "Over 1.5",

                home_name:
                f"{home_stats['over15']*100:.1f}%",

                away_name:
                f"{away_stats['over15']*100:.1f}%"

            },

            {

                "Estatística":
                "Over 2.5",

                home_name:
                f"{home_stats['over25']*100:.1f}%",

                away_name:
                f"{away_stats['over25']*100:.1f}%"

            },

            {

                "Estatística":
                "Under 3.5",

                home_name:
                f"{home_stats['under35']*100:.1f}%",

                away_name:
                f"{away_stats['under35']*100:.1f}%"

            },

            {

                "Estatística":
                "Ambas marcam",

                home_name:
                f"{home_stats['btts']*100:.1f}%",

                away_name:
                f"{away_stats['btts']*100:.1f}%"

            }

        ]

        st.dataframe(

            pd.DataFrame(
                stats_rows
            ),

            use_container_width=True,

            hide_index=True

        )


# ============================================================
# INFORMAÇÕES
# ============================================================

with b4:

    st.subheader(
        "ℹ️ Versão econômica"
    )

    st.markdown(
        """
Esta versão foi criada para reduzir o consumo
da API-Football.

### Não utiliza

- Odds;
- Betano;
- Superbet;
- Betão;
- Predictions;
- `teams/statistics`;
- Consulta forçada de temporada 2026.

### Utiliza

- Jogos disponíveis por data;
- Histórico recente de cada equipe;
- Média de gols;
- Desempenho casa/fora;
- Over/Under;
- BTTS;
- Modelo de Poisson;
- Probabilidades 1X2.

### Consumo esperado

Ao buscar jogos:

**aproximadamente 1 consulta.**

Ao analisar uma partida:

**aproximadamente 2 consultas**, uma para cada equipe.

O cache evita repetir consultas durante o período configurado.

⚠️ As probabilidades são estimativas estatísticas.
Não existe garantia de 90%, lucro ou acerto.
        """
    )
