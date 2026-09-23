import os
import time
import requests
import streamlit as st

from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Football Multi-Source Scanner",
    page_icon="⚽",
    layout="wide"
)

BRT = ZoneInfo("America/Sao_Paulo")

TIMEOUT = 5
MAX_WORKERS = 12

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
THESPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json"


# ============================================================
# SECRETS / VARIÁVEIS
# ============================================================

def get_secret(nome, default=""):
    try:
        valor = st.secrets.get(nome, "")
        if valor:
            return str(valor)
    except Exception:
        pass

    return os.getenv(nome, default)


API_FOOTBALL_KEY = get_secret("API_FOOTBALL_KEY")
FOOTBALL_DATA_TOKEN = get_secret("FOOTBALL_DATA_TOKEN")

# TheSportsDB:
# 123 = chave pública de teste da V1.
# Para livescore V2 é necessária chave Premium.
THESPORTSDB_KEY = get_secret(
    "THESPORTSDB_KEY",
    "123"
)

TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")


# ============================================================
# LIGAS ESPN
# ============================================================

LIGAS_ESPN = {
    "Brasil Série A": "bra.1",
    "Brasil Série B": "bra.2",
    "Brasil Série C": "bra.3",
    "Brasil Série D": "bra.4",

    "Inglaterra Premier League": "eng.1",
    "Inglaterra Championship": "eng.2",

    "Espanha LaLiga": "esp.1",
    "Espanha Segunda": "esp.2",

    "Itália Serie A": "ita.1",
    "Itália Serie B": "ita.2",

    "Alemanha Bundesliga": "ger.1",
    "Alemanha 2. Bundesliga": "ger.2",

    "França Ligue 1": "fra.1",
    "França Ligue 2": "fra.2",

    "Portugal": "por.1",
    "Holanda": "ned.1",
    "Bélgica": "bel.1",
    "Turquia": "tur.1",
    "Grécia": "gre.1",
    "Escócia": "sco.1",

    "Argentina": "arg.1",
    "Colômbia": "col.1",
    "Chile": "chi.1",
    "Paraguai": "par.1",
    "Uruguai": "uru.1",
    "Peru": "per.1",
    "Equador": "ecu.1",
    "Bolívia": "bol.1",
    "México": "mex.1",

    "MLS": "usa.1",

    "Japão": "jpn.1",
    "Coreia do Sul": "kor.1",
    "Austrália": "aus.1",

    "Áustria": "aut.1",
    "Suíça": "sui.1",
    "Noruega": "nor.1",
    "Suécia": "swe.1",
    "Dinamarca": "den.1",
    "Polônia": "pol.1",
}


# ============================================================
# FOOTBALL-DATA.ORG
# ============================================================

FOOTBALL_DATA_COMPETITIONS = {
    "Premier League": "PL",
    "Championship": "ELC",
    "Bundesliga": "BL1",
    "LaLiga": "PD",
    "Serie A": "SA",
    "Ligue 1": "FL1",
    "Primeira Liga": "PPL",
    "Eredivisie": "DED",
    "Brasileirão": "BSA",
}


# ============================================================
# API-FOOTBALL
# IDs MAIS USADOS
# ============================================================

API_FOOTBALL_LEAGUES = {
    "Premier League": 39,
    "Championship": 40,
    "LaLiga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
    "Ligue 1": 61,
    "Primeira Liga": 94,
    "Eredivisie": 88,
    "Brasileirão": 71,
    "Argentina": 128,
    "Colômbia": 239,
    "Chile": 265,
    "Paraguai": 250,
    "Uruguai": 268,
    "Peru": 281,
    "Equador": 242,
    "México": 262,
    "MLS": 253,
    "Japão": 98,
    "Coreia do Sul": 292,
    "Austrália": 188,
}


# ============================================================
# UTILIDADES
# ============================================================

def agora_brt():
    return datetime.now(BRT)


def horario():
    return agora_brt().strftime("%H:%M:%S.%f")[:-3]


def normalizar_nome(nome):
    if not nome:
        return ""

    return (
        nome.lower()
        .replace(" fc", "")
        .replace(" cf", "")
        .replace(" sc", "")
        .replace(" ac", "")
        .replace(".", "")
        .strip()
    )


def chave_jogo(casa, fora):
    return (
        normalizar_nome(casa),
        normalizar_nome(fora)
    )


def criar_jogo(
    fonte,
    evento_id,
    liga,
    casa,
    fora,
    gols_casa,
    gols_fora,
    status="",
    minuto=None
):

    try:
        gols_casa = int(gols_casa or 0)
    except Exception:
        gols_casa = 0

    try:
        gols_fora = int(gols_fora or 0)
    except Exception:
        gols_fora = 0

    return {
        "fonte": fonte,
        "id": str(evento_id),
        "liga": liga or "",
        "casa": casa or "Casa",
        "fora": fora or "Fora",
        "gols_casa": gols_casa,
        "gols_fora": gols_fora,
        "status": status or "",
        "minuto": minuto,
        "hora_resposta": horario(),
        "timestamp_resposta": time.perf_counter(),
    }


# ============================================================
# ESPN
# ============================================================

def consultar_espn(nome_liga, codigo):

    inicio = time.perf_counter()

    url = f"{ESPN_BASE}/{codigo}/scoreboard"

    try:

        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        duracao = time.perf_counter() - inicio

        if response.status_code != 200:
            return {
                "fonte": "ESPN",
                "eventos": [],
                "erro": f"HTTP {response.status_code}",
                "tempo": duracao
            }

        data = response.json()

        jogos = []

        for evento in data.get("events", []):

            try:

                competicao = evento.get(
                    "competitions",
                    [{}]
                )[0]

                equipes = competicao.get(
                    "competitors",
                    []
                )

                casa = None
                fora = None

                for equipe in equipes:

                    if equipe.get("homeAway") == "home":
                        casa = equipe

                    elif equipe.get("homeAway") == "away":
                        fora = equipe

                if not casa or not fora:
                    continue

                status_obj = competicao.get(
                    "status",
                    {}
                )

                status_type = status_obj.get(
                    "type",
                    {}
                )

                estado = status_type.get(
                    "state",
                    ""
                )

                status = status_type.get(
                    "shortDetail",
                    status_type.get(
                        "description",
                        ""
                    )
                )

                minuto = status_obj.get(
                    "displayClock"
                )

                jogo = criar_jogo(
                    fonte="ESPN",
                    evento_id=evento.get("id"),
                    liga=nome_liga,
                    casa=casa.get(
                        "team",
                        {}
                    ).get(
                        "displayName",
                        "Casa"
                    ),
                    fora=fora.get(
                        "team",
                        {}
                    ).get(
                        "displayName",
                        "Fora"
                    ),
                    gols_casa=casa.get(
                        "score",
                        0
                    ),
                    gols_fora=fora.get(
                        "score",
                        0
                    ),
                    status=status,
                    minuto=minuto
                )

                jogo["ao_vivo"] = (
                    estado == "in"
                )

                jogos.append(jogo)

            except Exception:
                continue

        return {
            "fonte": "ESPN",
            "eventos": jogos,
            "erro": None,
            "tempo": duracao
        }

    except Exception as e:

        return {
            "fonte": "ESPN",
            "eventos": [],
            "erro": str(e),
            "tempo": time.perf_counter() - inicio
        }


# ============================================================
# API-FOOTBALL
# ============================================================

def consultar_api_football():

    inicio = time.perf_counter()

    if not API_FOOTBALL_KEY:

        return {
            "fonte": "API-Football",
            "eventos": [],
            "erro": "API_FOOTBALL_KEY não configurada",
            "tempo": 0
        }

    try:

        response = requests.get(
            f"{API_FOOTBALL_BASE}/fixtures",
            params={
                "live": "all"
            },
            headers={
                "x-apisports-key": API_FOOTBALL_KEY
            },
            timeout=TIMEOUT
        )

        duracao = time.perf_counter() - inicio

        if response.status_code != 200:

            return {
                "fonte": "API-Football",
                "eventos": [],
                "erro": f"HTTP {response.status_code}",
                "tempo": duracao
            }

        data = response.json()

        jogos = []

        for item in data.get(
            "response",
            []
        ):

            try:

                fixture = item.get(
                    "fixture",
                    {}
                )

                teams = item.get(
                    "teams",
                    {}
                )

                goals = item.get(
                    "goals",
                    {}
                )

                league = item.get(
                    "league",
                    {}
                )

                status = fixture.get(
                    "status",
                    {}
                )

                jogo = criar_jogo(
                    fonte="API-Football",
                    evento_id=fixture.get(
                        "id"
                    ),
                    liga=league.get(
                        "name",
                        ""
                    ),
                    casa=teams.get(
                        "home",
                        {}
                    ).get(
                        "name",
                        "Casa"
                    ),
                    fora=teams.get(
                        "away",
                        {}
                    ).get(
                        "name",
                        "Fora"
                    ),
                    gols_casa=goals.get(
                        "home",
                        0
                    ),
                    gols_fora=goals.get(
                        "away",
                        0
                    ),
                    status=status.get(
                        "long",
                        ""
                    ),
                    minuto=status.get(
                        "elapsed"
                    )
                )

                jogo["ao_vivo"] = True

                jogos.append(jogo)

            except Exception:
                continue

        return {
            "fonte": "API-Football",
            "eventos": jogos,
            "erro": None,
            "tempo": duracao
        }

    except Exception as e:

        return {
            "fonte": "API-Football",
            "eventos": [],
            "erro": str(e),
            "tempo": time.perf_counter() - inicio
        }


# ============================================================
# FOOTBALL-DATA.ORG
# ============================================================

def consultar_football_data():

    inicio = time.perf_counter()

    if not FOOTBALL_DATA_TOKEN:

        return {
            "fonte": "football-data.org",
            "eventos": [],
            "erro": "FOOTBALL_DATA_TOKEN não configurado",
            "tempo": 0
        }

    try:

        response = requests.get(
            f"{FOOTBALL_DATA_BASE}/matches",
            params={
                "status": "IN_PLAY"
            },
            headers={
                "X-Auth-Token": FOOTBALL_DATA_TOKEN
            },
            timeout=TIMEOUT
        )

        duracao = time.perf_counter() - inicio

        if response.status_code != 200:

            return {
                "fonte": "football-data.org",
                "eventos": [],
                "erro": f"HTTP {response.status_code}",
                "tempo": duracao
            }

        data = response.json()

        jogos = []

        for item in data.get(
            "matches",
            []
        ):

            try:

                score = item.get(
                    "score",
                    {}
                )

                fulltime = score.get(
                    "fullTime",
                    {}
                )

                jogo = criar_jogo(
                    fonte="football-data.org",
                    evento_id=item.get(
                        "id"
                    ),
                    liga=item.get(
                        "competition",
                        {}
                    ).get(
                        "name",
                        ""
                    ),
                    casa=item.get(
                        "homeTeam",
                        {}
                    ).get(
                        "name",
                        "Casa"
                    ),
                    fora=item.get(
                        "awayTeam",
                        {}
                    ).get(
                        "name",
                        "Fora"
                    ),
                    gols_casa=fulltime.get(
                        "home",
                        0
                    ),
                    gols_fora=fulltime.get(
                        "away",
                        0
                    ),
                    status=item.get(
                        "status",
                        ""
                    ),
                    minuto=None
                )

                jogo["ao_vivo"] = (
                    item.get("status")
                    in [
                        "IN_PLAY",
                        "PAUSED"
                    ]
                )

                jogos.append(jogo)

            except Exception:
                continue

        return {
            "fonte": "football-data.org",
            "eventos": jogos,
            "erro": None,
            "tempo": duracao
        }

    except Exception as e:

        return {
            "fonte": "football-data.org",
            "eventos": [],
            "erro": str(e),
            "tempo": time.perf_counter() - inicio
        }


# ============================================================
# THESPORTSDB
# ============================================================

def consultar_thesportsdb():

    inicio = time.perf_counter()

    # Livescore real da V2 requer chave Premium.
    # Se uma chave Premium estiver configurada,
    # utilizamos o endpoint V2.

    if not THESPORTSDB_KEY:

        return {
            "fonte": "TheSportsDB",
            "eventos": [],
            "erro": "THESPORTSDB_KEY não configurada",
            "tempo": 0
        }

    try:

        if THESPORTSDB_KEY != "123":

            url = (
                "https://www.thesportsdb.com/"
                "api/v2/json/livescore/soccer"
            )

            response = requests.get(
                url,
                headers={
                    "X-API-KEY": THESPORTSDB_KEY
                },
                timeout=TIMEOUT
            )

        else:

            # A chave 123 é útil para testes da V1,
            # mas não é equivalente ao livescore Premium.

            return {
                "fonte": "TheSportsDB",
                "eventos": [],
                "erro": (
                    "Livescore requer chave Premium "
                    "THESPORTSDB_KEY"
                ),
                "tempo": 0
            }

        duracao = time.perf_counter() - inicio

        if response.status_code != 200:

            return {
                "fonte": "TheSportsDB",
                "eventos": [],
                "erro": f"HTTP {response.status_code}",
                "tempo": duracao
            }

        data = response.json()

        # A estrutura pode variar conforme versão/plano.
        lista = (
            data.get("livescores")
            or data.get("events")
            or data.get("data")
            or []
        )

        jogos = []

        for item in lista:

            try:

                jogo = criar_jogo(
                    fonte="TheSportsDB",
                    evento_id=(
                        item.get("idEvent")
                        or item.get("idLiveScore")
                        or item.get("id")
                    ),
                    liga=(
                        item.get("strLeague")
                        or item.get("league")
                        or ""
                    ),
                    casa=(
                        item.get("strHomeTeam")
                        or item.get("homeTeam")
                        or "Casa"
                    ),
                    fora=(
                        item.get("strAwayTeam")
                        or item.get("awayTeam")
                        or "Fora"
                    ),
                    gols_casa=(
                        item.get("intHomeScore")
                        or item.get("homeScore")
                        or 0
                    ),
                    gols_fora=(
                        item.get("intAwayScore")
                        or item.get("awayScore")
                        or 0
                    ),
                    status=(
                        item.get("strStatus")
                        or item.get("status")
                        or ""
                    ),
                    minuto=(
                        item.get("intProgress")
                        or item.get("strProgress")
                    )
                )

                jogo["ao_vivo"] = True

                jogos.append(jogo)

            except Exception:
                continue

        return {
            "fonte": "TheSportsDB",
            "eventos": jogos,
            "erro": None,
            "tempo": duracao
        }

    except Exception as e:

        return {
            "fonte": "TheSportsDB",
            "eventos": [],
            "erro": str(e),
            "tempo": time.perf_counter() - inicio
        }


# ============================================================
# EXECUTAR TODAS AS FONTES EM PARALELO
# ============================================================

def consultar_todas_as_fontes(
    ligas_selecionadas
):

    inicio = time.perf_counter()

    tarefas = []

    # --------------------------------------------------------
    # ESPN
    # --------------------------------------------------------

    for nome_liga in ligas_selecionadas:

        codigo = LIGAS_ESPN.get(
            nome_liga
        )

        if codigo:

            tarefas.append(
                (
                    f"ESPN - {nome_liga}",
                    consultar_espn,
                    (
                        nome_liga,
                        codigo
                    )
                )
            )

    # --------------------------------------------------------
    # API-FOOTBALL
    # --------------------------------------------------------

    tarefas.append(
        (
            "API-Football",
            consultar_api_football,
            ()
        )
    )

    # --------------------------------------------------------
    # FOOTBALL-DATA
    # --------------------------------------------------------

    tarefas.append(
        (
            "football-data.org",
            consultar_football_data,
            ()
        )
    )

    # --------------------------------------------------------
    # THESPORTSDB
    # --------------------------------------------------------

    tarefas.append(
        (
            "TheSportsDB",
            consultar_thesportsdb,
            ()
        )
    )

    resultados = []

    workers = min(
        MAX_WORKERS,
        len(tarefas)
    )

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:

        futuros = {}

        for nome, funcao, args in tarefas:

            futuro = executor.submit(
                funcao,
                *args
            )

            futuros[futuro] = nome

        for futuro in as_completed(
            futuros
        ):

            nome = futuros[futuro]

            try:

                resultado = futuro.result()

                resultados.append(
                    resultado
                )

            except Exception as e:

                resultados.append({
                    "fonte": nome,
                    "eventos": [],
                    "erro": str(e),
                    "tempo": 0
                })

    duracao = time.perf_counter() - inicio

    return resultados, duracao


# ============================================================
# AGRUPAMENTO DAS PARTIDAS
# ============================================================

def agrupar_partidas(resultados):

    grupos = {}

    for resultado in resultados:

        for jogo in resultado.get(
            "eventos",
            []
        ):

            chave = chave_jogo(
                jogo["casa"],
                jogo["fora"]
            )

            if chave not in grupos:
                grupos[chave] = []

            grupos[chave].append(
                jogo
            )

    return grupos


# ============================================================
# DETECÇÃO MULTIFONTE
# ============================================================

def detectar_gols_multifonte(
    grupos
):

    if "placares_multifonte" not in st.session_state:
        st.session_state.placares_multifonte = {}

    if "alertas_gol" not in st.session_state:
        st.session_state.alertas_gol = set()

    novos_gols = []

    for chave, fontes in grupos.items():

        if not fontes:
            continue

        # ----------------------------------------------------
        # Encontra o maior placar observado
        # ----------------------------------------------------

        maior_casa = max(
            x["gols_casa"]
            for x in fontes
        )

        maior_fora = max(
            x["gols_fora"]
            for x in fontes
        )

        placar_atual = (
            maior_casa,
            maior_fora
        )

        placar_anterior = (
            st.session_state
            .placares_multifonte
            .get(chave)
        )

        # Primeiro ciclo
        if placar_anterior is None:

            st.session_state\
                .placares_multifonte[chave] = \
                placar_atual

            continue

        gols_antigos = sum(
            placar_anterior
        )

        gols_novos = sum(
            placar_atual
        )

        if gols_novos <= gols_antigos:

            st.session_state\
                .placares_multifonte[chave] = \
                placar_atual

            continue

        # ----------------------------------------------------
        # Qual fonte viu o novo placar?
        # ----------------------------------------------------

        fontes_com_novo_placar = [
            x
            for x in fontes
            if (
                x["gols_casa"],
                x["gols_fora"]
            ) == placar_atual
        ]

        if not fontes_com_novo_placar:

            fontes_com_novo_placar = fontes

        # A primeira resposta registrada neste ciclo
        # com o novo placar é considerada vencedora.
        primeira = min(
            fontes_com_novo_placar,
            key=lambda x:
            x["timestamp_resposta"]
        )

        evento_id = (
            chave,
            placar_atual
        )

        if evento_id not in st.session_state.alertas_gol:

            st.session_state.alertas_gol.add(
                evento_id
            )

            novo = {
                "hora": horario(),
                "casa": primeira["casa"],
                "fora": primeira["fora"],
                "liga": primeira["liga"],
                "placar_anterior": placar_anterior,
                "placar_novo": placar_atual,
                "primeira_fonte": primeira["fonte"],
                "fontes": fontes,
                "minuto": primeira.get(
                    "minuto"
                )
            }

            novos_gols.append(
                novo
            )

        st.session_state\
            .placares_multifonte[chave] = \
            placar_atual

    return novos_gols


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(
    gol
):

    if not TELEGRAM_BOT_TOKEN:
        return False

    if not TELEGRAM_CHAT_ID:
        return False

    try:

        fontes = ", ".join(
            sorted(
                set(
                    x["fonte"]
                    for x in gol["fontes"]
                )
            )
        )

        mensagem = (
            "⚽ GOL DETECTADO\n\n"
            f"{gol['casa']} "
            f"{gol['placar_novo'][0]} x "
            f"{gol['placar_novo'][1]} "
            f"{gol['fora']}\n\n"
            f"🏆 {gol['liga']}\n"
            f"🕐 {gol['hora']}\n"
            f"🚀 Primeira fonte: "
            f"{gol['primeira_fonte']}\n"
            f"📡 Fontes: {fontes}"
        )

        url = (
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensagem
            },
            timeout=5
        )

        return response.ok

    except Exception:
        return False


# ============================================================
# SESSION STATE
# ============================================================

if "placares_multifonte" not in st.session_state:
    st.session_state.placares_multifonte = {}

if "alertas_gol" not in st.session_state:
    st.session_state.alertas_gol = set()

if "historico_gols" not in st.session_state:
    st.session_state.historico_gols = []

if "historico_fontes" not in st.session_state:
    st.session_state.historico_fontes = []


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "⚽ Football Multi-Source Scanner"
)

st.caption(
    "ESPN + API-Football + football-data.org + TheSportsDB"
)


# ============================================================
# CONTROLES
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:

    ligas = st.multiselect(
        "Ligas ESPN",
        list(LIGAS_ESPN.keys()),
        default=[
            "Brasil Série A",
            "Brasil Série B",
            "Inglaterra Premier League",
            "Espanha LaLiga",
            "Itália Serie A",
            "Alemanha Bundesliga",
            "França Ligue 1",
            "Argentina",
            "Colômbia"
        ]
    )

with col2:

    intervalo = st.slider(
        "Atualização",
        2,
        30,
        5,
        1
    )

with col3:

    somente_ao_vivo = st.checkbox(
        "Somente ao vivo",
        True
    )


# ============================================================
# BOTÕES
# ============================================================

if st.button(
    "🗑️ Limpar histórico"
):

    st.session_state.placares_multifonte = {}
    st.session_state.alertas_gol = set()
    st.session_state.historico_gols = []
    st.session_state.historico_fontes = []

    st.rerun()


# ============================================================
# EXECUÇÃO
# ============================================================

inicio_ciclo = time.perf_counter()

resultados, tempo_consulta = \
    consultar_todas_as_fontes(
        ligas
    )


# ============================================================
# AGRUPAMENTO
# ============================================================

grupos = agrupar_partidas(
    resultados
)


# ============================================================
# GOLS
# ============================================================

novos_gols = detectar_gols_multifonte(
    grupos
)


for gol in novos_gols:

    st.session_state\
        .historico_gols\
        .insert(
            0,
            gol
        )

    enviar_telegram(
        gol
    )


# ============================================================
# JOGOS
# ============================================================

jogos_unicos = []

for chave, fontes in grupos.items():

    if not fontes:
        continue

    principal = max(
        fontes,
        key=lambda x:
        (
            x["gols_casa"] +
            x["gols_fora"],
            x["timestamp_resposta"]
        )
    )

    jogos_unicos.append(
        principal
    )


if somente_ao_vivo:

    jogos_exibidos = [
        x
        for x in jogos_unicos
        if x.get("ao_vivo")
    ]

else:

    jogos_exibidos = jogos_unicos


# ============================================================
# MÉTRICAS
# ============================================================

tempo_total = (
    time.perf_counter()
    - inicio_ciclo
)

fontes_ativas = sum(
    1
    for r in resultados
    if not r.get("erro")
)

total_respostas = sum(
    len(
        r.get(
            "eventos",
            []
        )
    )
    for r in resultados
)


m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    st.metric(
        "Fontes",
        len(resultados)
    )

with m2:
    st.metric(
        "Ativas",
        fontes_ativas
    )

with m3:
    st.metric(
        "Jogos",
        len(jogos_exibidos)
    )

with m4:
    st.metric(
        "Respostas",
        total_respostas
    )

with m5:
    st.metric(
        "Ciclo",
        f"{tempo_total:.2f}s"
    )


st.caption(
    f"🚀 Consultas paralelas | "
    f"Tempo das APIs: {tempo_consulta:.2f}s | "
    f"Atualização: {intervalo}s"
)


# ============================================================
# ALERTAS
# ============================================================

if novos_gols:

    st.subheader(
        "🚨 GOLS DETECTADOS"
    )

    for gol in novos_gols:

        st.error(
            f"⚽ {gol['casa']} "
            f"{gol['placar_novo'][0]} x "
            f"{gol['placar_novo'][1]} "
            f"{gol['fora']} | "
            f"🚀 {gol['primeira_fonte']} | "
            f"🕐 {gol['hora']}"
        )


# ============================================================
# JOGOS AO VIVO
# ============================================================

st.subheader(
    "🔴 Jogos monitorados"
)

for jogo in jogos_exibidos:

    st.markdown(
        f"""
### 🔴 {jogo['casa']}
**{jogo['gols_casa']} x {jogo['gols_fora']}**
{jogo['fora']}

🏆 {jogo['liga']}  
⏱️ {jogo['status']}
"""
    )


# ============================================================
# PAINEL DE FONTES
# ============================================================

st.subheader(
    "📡 Desempenho das fontes"
)

for resultado in sorted(
    resultados,
    key=lambda x: x.get(
        "tempo",
        999
    )
):

    fonte = resultado["fonte"]
    erro = resultado.get("erro")
    tempo = resultado.get(
        "tempo",
        0
    )

    if erro:

        st.write(
            f"🔴 **{fonte}** — "
            f"erro: {erro}"
        )

    else:

        quantidade = len(
            resultado.get(
                "eventos",
                []
            )
        )

        st.write(
            f"🟢 **{fonte}** — "
            f"{tempo:.3f}s — "
            f"{quantidade} jogos"
        )


# ============================================================
# HISTÓRICO DE GOLS
# ============================================================

st.subheader(
    "📋 Histórico de detecção"
)

if st.session_state.historico_gols:

    for gol in st.session_state.historico_gols[:30]:

        st.markdown(
            f"""
**{gol['hora']}**

⚽ **{gol['casa']}**
{gol['placar_anterior'][0]} →
{gol['placar_novo'][0]}

**{gol['fora']}**
{gol['placar_anterior'][1]} →
{gol['placar_novo'][1]}

🚀 Primeira fonte:
**{gol['primeira_fonte']}**

🏆 {gol['liga']}
"""
        )

else:

    st.info(
        "Nenhum gol detectado desde o início."
    )


# ============================================================
# ATUALIZAÇÃO
# ============================================================

time.sleep(
    intervalo
)

st.rerun()
