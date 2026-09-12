importimport math
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

API_BASE = "https://v3.football.api-sports.io"
TIMEOUT = 20

# Histórico máximo desejado.
# Se o plano Free não permitir "last", o app tenta buscar por datas.
HISTORY_DAYS = 30

# Máximo de jogos no scanner automático
MAX_AUTO_GAMES = 5


# ============================================================
# SESSION STATE
# ============================================================

if "games" not in st.session_state:
    st.session_state.games = []

if "analysis" not in st.session_state:
    st.session_state.analysis = None

if "api_calls" not in st.session_state:
    st.session_state.api_calls = 0

if "last_api_error" not in st.session_state:
    st.session_state.last_api_error = ""


# ============================================================
# API KEY
# ============================================================

def get_api_key():
    try:
        return st.secrets["api"]["football_key"].strip()
    except Exception:
        return ""


# ============================================================
# CHAMADA DA API
# ============================================================

def api_request(endpoint, params=None):
    """
    Faz uma chamada para API-Football.

    Retorna:
        (response, error)
    """

    api_key = get_api_key()

    if not api_key:
        return [], "API Key não configurada."

    try:

        response = requests.get(
            f"{API_BASE}/{endpoint}",
            headers={
                "x-apisports-key": api_key
            },
            params=params or {},
            timeout=TIMEOUT
        )

        st.session_state.api_calls += 1

        try:
            data = response.json()
        except Exception:
            return [], (
                f"Resposta inválida da API. "
                f"HTTP {response.status_code}"
            )

        errors = data.get("errors")

        if errors:
            error_text = str(errors)
            st.session_state.last_api_error = error_text
            return [], error_text

        if response.status_code >= 400:
            return [], (
                f"Erro HTTP {response.status_code}"
            )

        return data.get("response", []) or [], None

    except requests.exceptions.Timeout:
        return [], "Tempo limite da API excedido."

    except requests.exceptions.ConnectionError:
        return [], "Não foi possível conectar à API."

    except Exception as e:
        return [], str(e)


# ============================================================
# FIXTURES POR DATA
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def get_fixtures(day):

    data, error = api_request(
        "fixtures",
        {
            "date": str(day),
            "timezone": "America/Sao_Paulo"
        }
    )

    return data, error


# ============================================================
# HISTÓRICO DA EQUIPE
#
# Primeiro tenta buscar por intervalo de datas.
#
# Isso evita:
#
# - teams/statistics
# - season=2026
# - last=10
#
# ============================================================

@st.cache_data(ttl=1800, show_spinner=False)
def get_team_history(team_id):

    end_date = date.today()
    start_date = end_date - timedelta(days=HISTORY_DAYS)

    data, error = api_request(
        "fixtures",
        {
            "team": team_id,
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "status": "FT"
        }
    )

    if error:
        return [], error

    # Apenas partidas finalizadas
    finished = []

    for game in data:

        status = (
            game
            .get("fixture", {})
            .get("status", {})
            .get("short", "")
        )

        if status == "FT":
            finished.append(game)

    # Ordenar da mais recente para a mais antiga
    finished.sort(
        key=lambda x: (
            x
            .get("fixture", {})
            .get("timestamp", 0)
        ),
        reverse=True
    )

    return finished, None


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def safe_float(value, default=0.0):

    try:

        if value is None:
            return default

        return float(
            str(value)
            .replace(",", ".")
            .replace("%", "")
        )

    except Exception:
        return default


def game_label(game):

    timestamp = (
        game
        .get("fixture", {})
        .get("timestamp")
    )

    if timestamp:

        try:

            hour = datetime.fromtimestamp(
                timestamp
            ).strftime("%H:%M")

        except Exception:

            hour = "--:--"

    else:

        hour = "--:--"

    home = (
        game
        .get("teams", {})
        .get("home", {})
        .get("name", "Casa")
    )

    away = (
        game
        .get("teams", {})
        .get("away", {})
        .get("name", "Fora")
    )

    return f"{hour} | {home} x {away}"


# ============================================================
# CALCULAR ESTATÍSTICAS
# ============================================================

def calculate_team_stats(
    games,
    team_id,
    venue=None
):

    goals_for = []
    goals_against = []

    wins = 0
    draws = 0
    losses = 0

    over_05 = 0
    over_15 = 0
    over_25 = 0

    under_25 = 0
    under_35 = 0
    under_45 = 0

    btts_yes = 0

    used_games = 0


    for game in games:

        teams = game.get("teams", {})
        goals = game.get("goals", {})

        home_team = teams.get("home", {})
        away_team = teams.get("away", {})

        home_id = home_team.get("id")
        away_id = away_team.get("id")

        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None:
            continue

        if away_goals is None:
            continue

        is_home = home_id == team_id

        is_away = away_id == team_id

        if not is_home and not is_away:
            continue

        # Filtrar mando
        if venue == "home" and not is_home:
            continue

        if venue == "away" and not is_away:
            continue

        # Definir gols do time
        if is_home:

            gf = safe_float(home_goals)
            ga = safe_float(away_goals)

        else:

            gf = safe_float(away_goals)
            ga = safe_float(home_goals)

        used_games += 1

        goals_for.append(gf)
        goals_against.append(ga)

        # Resultado
        if gf > ga:

            wins += 1

        elif gf == ga:

            draws += 1

        else:

            losses += 1

        total_goals = gf + ga

        # Over
        if total_goals >= 1:
            over_05 += 1

        if total_goals >= 2:
            over_15 += 1

        if total_goals >= 3:
            over_25 += 1

        # Under
        if total_goals <= 2:
            under_25 += 1

        if total_goals <= 3:
            under_35 += 1

        if total_goals <= 4:
            under_45 += 1

        # Ambas marcam
        if gf > 0 and ga > 0:
            btts_yes += 1


    if used_games == 0:

        return {

            "games": 0,

            "gf_avg": 0.0,

            "ga_avg": 0.0,

            "win": 0.0,

            "draw": 0.0,

            "loss": 0.0,

            "over05": 0.0,

            "over15": 0.0,

            "over25": 0.0,

            "under25": 0.0,

            "under35": 0.0,

            "under45": 0.0,

            "btts": 0.0

        }


    return {

        "games": used_games,

        "gf_avg":
        sum(goals_for) / used_games,

        "ga_avg":
        sum(goals_against) / used_games,

        "win":
        wins / used_games,

        "draw":
        draws / used_games,

        "loss":
        losses / used_games,

        "over05":
        over_05 / used_games,

        "over15":
        over_15 / used_games,

        "over25":
        over_25 / used_games,

        "under25":
        under_25 / used_games,

        "under35":
        under_35 / used_games,

        "under45":
        under_45 / used_games,

        "btts":
        btts_yes / used_games

    }


# ============================================================
# POISSON
# ============================================================

def poisson_pmf(lam, goals):

    lam = max(float(lam), 0.01)

    return (
        math.exp(-lam)
        *
        (lam ** goals)
        /
        math.factorial(goals)
    )


def probability_over(lam, line):

    maximum = math.floor(line)

    probability = 1 - sum(
        poisson_pmf(lam, i)
        for i in range(maximum + 1)
    )

    return max(
        0.0,
        min(1.0, probability)
    )


def probability_under(lam, line):

    maximum = math.floor(line)

    probability = sum(
        poisson_pmf(lam, i)
        for i in range(maximum + 1)
    )

    return max(
        0.0,
        min(1.0, probability)
    )


# ============================================================
# 1X2
# ============================================================

def one_x_two(
    home_lambda,
    away_lambda
):

    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    for home_goals in range(10):

        for away_goals in range(10):

            probability = (
                poisson_pmf(
                    home_lambda,
                    home_goals
                )
                *
                poisson_pmf(
                    away_lambda,
                    away_goals
                )
            )

            if home_goals > away_goals:

                home_win += probability

            elif home_goals == away_goals:

                draw += probability

            else:

                away_win += probability


    total = (
        home_win
        +
        draw
        +
        away_win
    )

    if total <= 0:

        return (
            0.0,
            0.0,
            0.0
        )


    return (

        home_win / total,

        draw / total,

        away_win / total

    )


# ============================================================
# BTTS
# ============================================================

def probability_btts(
    home_lambda,
    away_lambda
):

    probability = (

        1

        - math.exp(-home_lambda)

        - math.exp(-away_lambda)

        + math.exp(
            -(home_lambda + away_lambda)
        )

    )

    return max(
        0.0,
        min(1.0, probability)
    )


# ============================================================
# CONSTRUIR MODELO
# ============================================================

def build_model(
    home_stats,
    away_stats
):

    # Médias reais
    home_attack = (
        home_stats["gf_avg"]
    )

    home_defense = (
        home_stats["ga_avg"]
    )

    away_attack = (
        away_stats["gf_avg"]
    )

    away_defense = (
        away_stats["ga_avg"]
    )


    # Valores de segurança
    if home_attack <= 0:
        home_attack = 1.0

    if home_defense <= 0:
        home_defense = 1.2

    if away_attack <= 0:
        away_attack = 1.0

    if away_defense <= 0:
        away_defense = 1.2


    # Modelo simples combinando
    # ataque próprio + defesa adversária

    expected_home = (

        0.60 * home_attack

        +

        0.40 * away_defense

    )


    expected_away = (

        0.60 * away_attack

        +

        0.40 * home_defense

    )


    return (

        max(expected_home, 0.20),

        max(expected_away, 0.20)

    )


# ============================================================
# ANALISAR PARTIDA
# ============================================================

def analyze_game(game):

    home = (
        game
        .get("teams", {})
        .get("home", {})
    )

    away = (
        game
        .get("teams", {})
        .get("away", {})
    )

    home_id = home.get("id")
    away_id = away.get("id")


    if not home_id or not away_id:

        return None, (
            "IDs das equipes não encontrados."
        )


    # Histórico
    home_history, home_error = (
        get_team_history(home_id)
    )

    away_history, away_error = (
        get_team_history(away_id)
    )


    if home_error:

        return None, (
            f"Erro no histórico do "
            f"{home.get('name')}: "
            f"{home_error}"
        )


    if away_error:

        return None, (
            f"Erro no histórico do "
            f"{away.get('name')}: "
            f"{away_error}"
        )


    # Estatísticas gerais
    home_all = calculate_team_stats(
        home_history,
        home_id
    )

    away_all = calculate_team_stats(
        away_history,
        away_id
    )


    # Estatísticas por mando
    home_specific = calculate_team_stats(
        home_history,
        home_id,
        venue="home"
    )

    away_specific = calculate_team_stats(
        away_history,
        away_id,
        venue="away"
    )


    # Se houver poucos jogos específicos,
    # usar o histórico geral.

    if home_specific["games"] < 3:

        home_specific = home_all


    if away_specific["games"] < 3:

        away_specific = away_all


    # Não há dados suficientes
    if (
        home_specific["games"] == 0
        or
        away_specific["games"] == 0
    ):

        return None, (
            "A API não retornou histórico "
            "finalizado suficiente para "
            "uma ou ambas as equipes."
        )


    # Modelo
    home_lambda, away_lambda = (
        build_model(
            home_specific,
            away_specific
        )
    )


    home_win, draw, away_win = (
        one_x_two(
            home_lambda,
            away_lambda
        )
    )


    total_goals = (
        home_lambda
        +
        away_lambda
    )


    return {

        "game": game,

        "home_stats":
        home_specific,

        "away_stats":
        away_specific,

        "home_all":
        home_all,

        "away_all":
        away_all,

        "home_lambda":
        home_lambda,

        "away_lambda":
        away_lambda,

        "total_goals":
        total_goals,

        "home_win":
        home_win,

        "draw":
        draw,

        "away_win":
        away_win,

        "btts":
        probability_btts(
            home_lambda,
            away_lambda
        )

    }, None


# ============================================================
# VERIFICAR API KEY
# ============================================================

if not get_api_key():

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


# ============================================================
# TÍTULO
# ============================================================

st.title("⚽ Football Scanner")

st.caption(
    "Estatísticas • Gols • Over/Under "
    "• Ambas Marcam • 1X2"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Configurações")

    max_games = st.slider(
        "Máximo de jogos no scanner",
        min_value=1,
        max_value=MAX_AUTO_GAMES,
        value=3
    )


    st.divider()


    st.metric(
        "Chamadas nesta sessão",
        st.session_state.api_calls
    )


    st.caption(
        "Modo econômico"
    )

    st.caption(
        "Sem odds • Sem predictions "
        "• Sem teams/statistics"
    )


# ============================================================
# ABAS
# ============================================================

tab_search, tab_scanner, tab_analysis, tab_info = (
    st.tabs(
        [
            "🔎 Buscar jogo",
            "🤖 Scanner",
            "📊 Análise",
            "ℹ️ Informações"
        ]
    )
)


# ============================================================
# BUSCAR JOGO
# ============================================================

with tab_search:

    selected_date = st.selectbox(

        "Data",

        [
            date.today(),
            date.today() + timedelta(days=1)
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
            "Consultando jogos..."
        ):

            games, error = get_fixtures(
                selected_date.isoformat()
            )


        if error:

            st.error(
                f"Erro da API: {error}"
            )

            st.session_state.games = []


        else:

            # IMPORTANTE:
            # Não filtramos apenas NS/TBD.
            # Todo jogo retornado será exibido.

            st.session_state.games = games


            if games:

                st.success(
                    f"{len(games)} jogos "
                    "retornados pela API."
                )

            else:

                st.warning(
                    "A API retornou 0 jogos "
                    f"para {selected_date.strftime('%d/%m/%Y')}."
                )

                st.info(
                    "Isso pode ser uma limitação "
                    "do plano da API ou simplesmente "
                    "não haver jogos cadastrados "
                    "para a data."
                )


    if st.session_state.games:

        selected_index = st.selectbox(

            "Escolha a partida",

            range(
                len(
                    st.session_state.games
                )
            ),

            format_func=lambda i:
            game_label(
                st.session_state.games[i]
            )

        )


        selected_game = (
            st.session_state.games[
                selected_index
            ]
        )


        status = (
            selected_game
            .get("fixture", {})
            .get("status", {})
            .get("short", "")
        )


        st.caption(
            f"Status API: {status}"
        )


        if st.button(

            "📊 Analisar jogo",

            type="primary",

            use_container_width=True

        ):

            with st.spinner(

                "Buscando histórico "
                "das equipes..."

            ):

                result, error = (
                    analyze_game(
                        selected_game
                    )
                )


            if error:

                st.error(
                    f"Não foi possível analisar: "
                    f"{error}"
                )

            else:

                st.session_state.analysis = (
                    result
                )

                st.success(
                    "Análise concluída!"
                )


# ============================================================
# SCANNER
# ============================================================

with tab_scanner:

    st.write(
        "O scanner analisa jogos retornados "
        "pela API para a data atual."
    )


    if st.button(

        "🚀 Executar scanner",

        type="primary",

        use_container_width=True

    ):

        with st.spinner(
            "Buscando jogos..."
        ):

            games, error = get_fixtures(
                date.today().isoformat()
            )


        if error:

            st.error(
                f"Erro ao buscar jogos: {error}"
            )

        else:

            # Não usar filtro NS/TBD
            games = games[:max_games]


            if not games:

                st.warning(
                    "A API não retornou jogos "
                    "para hoje."
                )

            else:

                progress = st.progress(0)

                results = []


                for index, game in enumerate(games):

                    result, game_error = (
                        analyze_game(
                            game
                        )
                    )


                    if result:

                        results.append(

                            {

                                "Jogo":
                                game_label(game),

                                "Casa %":
                                round(
                                    result["home_win"]
                                    * 100,
                                    1
                                ),

                                "Empate %":
                                round(
                                    result["draw"]
                                    * 100,
                                    1
                                ),

                                "Fora %":
                                round(
                                    result["away_win"]
                                    * 100,
                                    1
                                ),

                                "BTTS %":
                                round(
                                    result["btts"]
                                    * 100,
                                    1
                                ),

                                "Over 1.5 %":
                                round(
                                    probability_over(
                                        result[
                                            "total_goals"
                                        ],
                                        1.5
                                    )
                                    * 100,
                                    1
                                ),

                                "Over 2.5 %":
                                round(
                                    probability_over(
                                        result[
                                            "total_goals"
                                        ],
                                        2.5
                                    )
                                    * 100,
                                    1
                                ),

                                "Under 3.5 %":
                                round(
                                    probability_under(
                                        result[
                                            "total_goals"
                                        ],
                                        3.5
                                    )
                                    * 100,
                                    1
                                )

                            }

                        )


                    progress.progress(

                        (
                            index + 1
                        )
                        /
                        len(games)

                    )


                if results:

                    dataframe = (
                        pd.DataFrame(
                            results
                        )
                    )

                    st.dataframe(

                        dataframe,

                        use_container_width=True,

                        hide_index=True

                    )

                else:

                    st.warning(
                        "Nenhuma partida pôde "
                        "ser analisada. "
                        "Verifique se sua API "
                        "permite consultar "
                        "histórico por datas."
                    )


# ============================================================
# ANÁLISE
# ============================================================

with tab_analysis:

    result = (
        st.session_state.analysis
    )


    if not result:

        st.info(
            "Busque uma partida e clique "
            "em Analisar jogo."
        )


    else:

        game = result["game"]

        home_name = (
            game
            .get("teams", {})
            .get("home", {})
            .get("name", "Casa")
        )

        away_name = (
            game
            .get("teams", {})
            .get("away", {})
            .get("name", "Fora")
        )


        st.header(
            f"{home_name} x {away_name}"
        )


        col1, col2, col3, col4 = (
            st.columns(4)
        )


        col1.metric(

            "Vitória Casa",

            f"{result['home_win'] * 100:.1f}%"

        )


        col2.metric(

            "Empate",

            f"{result['draw'] * 100:.1f}%"

        )


        col3.metric(

            "Vitória Fora",

            f"{result['away_win'] * 100:.1f}%"

        )


        col4.metric(

            "Ambas Marcam",

            f"{result['btts'] * 100:.1f}%"

        )


        st.subheader(
            "⚽ Gols esperados"
        )


        g1, g2, g3 = st.columns(3)


        g1.metric(

            home_name,

            f"{result['home_lambda']:.2f}"

        )


        g2.metric(

            away_name,

            f"{result['away_lambda']:.2f}"

        )


        g3.metric(

            "Total",

            f"{result['total_goals']:.2f}"

        )


        # ----------------------------------------------------
        # OVER / UNDER
        # ----------------------------------------------------

        st.subheader(
            "📈 Probabilidades de gols"
        )


        total = (
            result["total_goals"]
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

                    "Linha":

                    f"{line}",


                    "Over %":

                    round(

                        probability_over(
                            total,
                            line
                        )
                        * 100,

                        1

                    ),


                    "Under %":

                    round(

                        probability_under(
                            total,
                            line
                        )
                        * 100,

                        1

                    )

                }

            )


        st.dataframe(

            pd.DataFrame(
                goal_rows
            ),

            use_container_width=True,

            hide_index=True

        )


        # ----------------------------------------------------
        # ESTATÍSTICAS RECENTES
        # ----------------------------------------------------

        st.subheader(
            "📊 Estatísticas recentes"
        )


        home_stats = (
            result["home_stats"]
        )

        away_stats = (
            result["away_stats"]
        )


        statistics_rows = [

            {

                "Estatística":
                "Jogos utilizados",

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
                    home_stats["gf_avg"],
                    2
                ),

                away_name:
                round(
                    away_stats["gf_avg"],
                    2
                )

            },


            {

                "Estatística":
                "Média gols sofridos",

                home_name:
                round(
                    home_stats["ga_avg"],
                    2
                ),

                away_name:
                round(
                    away_stats["ga_avg"],
                    2
                )

            },


            {

                "Estatística":
                "Vitórias",

                home_name:
                f"{home_stats['win'] * 100:.1f}%",

                away_name:
                f"{away_stats['win'] * 100:.1f}%"

            },


            {

                "Estatística":
                "Empates",

                home_name:
                f"{home_stats['draw'] * 100:.1f}%",

                away_name:
                f"{away_stats['draw'] * 100:.1f}%"

            },


            {

                "Estatística":
                "Derrotas",

                home_name:
                f"{home_stats['loss'] * 100:.1f}%",

                away_name:
                f"{away_stats['loss'] * 100:.1f}%"

            },


            {

                "Estatística":
                "Over 1.5 histórico",

                home_name:
                f"{home_stats['over15'] * 100:.1f}%",

                away_name:
                f"{away_stats['over15'] * 100:.1f}%"

            },


            {

                "Estatística":
                "Over 2.5 histórico",

                home_name:
                f"{home_stats['over25'] * 100:.1f}%",

                away_name:
                f"{away_stats['over25'] * 100:.1f}%"

            },


            {

                "Estatística":
                "Under 3.5 histórico",

                home_name:
                f"{home_stats['under35'] * 100:.1f}%",

                away_name:
                f"{away_stats['under35'] * 100:.1f}%"

            },


            {

                "Estatística":
                "BTTS histórico",

                home_name:
                f"{home_stats['btts'] * 100:.1f}%",

                away_name:
                f"{away_stats['btts'] * 100:.1f}%"

            }

        ]


        st.dataframe(

            pd.DataFrame(
                statistics_rows
            ),

            use_container_width=True,

            hide_index=True

        )


# ============================================================
# INFORMAÇÕES
# ============================================================

with tab_info:

    st.subheader(
        "ℹ️ Football Scanner Econômico"
    )


    st.markdown(
        """
### Esta versão não utiliza:

- Odds;
- Betano;
- Superbet;
- Betão;
- API Predictions;
- `teams/statistics`;
- Temporada 2026.

### Esta versão utiliza:

- `fixtures?date=`;
- Histórico de partidas das equipes;
- Média de gols marcados;
- Média de gols sofridos;
- Desempenho recente;
- Mandante e visitante;
- Over/Under;
- Ambas marcam;
- Modelo de Poisson;
- Probabilidades 1X2.

### Importante

As probabilidades apresentadas são estimativas matemáticas.
Elas não representam garantia de acerto, lucro ou probabilidade real
superior a 90%.

O aplicativo agora também não elimina automaticamente os jogos por
status `NS` ou `TBD`. Portanto, se a API retornar partidas para a data,
elas deverão aparecer na lista.
        """
    )
```
