import os
import re
import time
import unicodedata
import threading
from datetime import datetime, timezone

import requests
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Football Goal Race",
    page_icon="⚽",
    layout="wide",
)

# ------------------------------------------------------------
# CHAVES
# ------------------------------------------------------------
# IMPORTANTE:
# Em produção, prefira colocar essas chaves no Streamlit Secrets.
#
# Exemplo:
#
# [api]
# football_data = "..."
# fivedollar = "..."
# thesportsdb = "123"
# openfoot = "..."
# openrouter = "..."
#
# [telegram]
# bot_token = "..."
# chat_id = "..."
#
# O código abaixo aceita também variáveis de ambiente.

FOOTBALL_DATA_API_TOKEN = os.getenv(
    "FOOTBALL_DATA_API_TOKEN",
    ""
)

FIVEDOLLAR_FOOTBALL_API_KEY = os.getenv(
    "FIVEDOLLAR_FOOTBALL_API_KEY",
    ""
)

THESPORTSDB_API_KEY = os.getenv(
    "THESPORTSDB_API_KEY",
    "123"
)

OPENFOOT_API_KEY = os.getenv(
    "OPENFOOT_API_KEY",
    ""
)

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
)

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
)


# ============================================================
# TENTAR STREAMLIT SECRETS
# ============================================================

def secret_value(section, key, default=""):
    try:
        if section in st.secrets:
            value = st.secrets[section].get(key, default)
            if value:
                return value
    except Exception:
        pass

    return default


FOOTBALL_DATA_API_TOKEN = secret_value(
    "api",
    "football_data",
    FOOTBALL_DATA_API_TOKEN
)

FIVEDOLLAR_FOOTBALL_API_KEY = secret_value(
    "api",
    "fivedollar",
    FIVEDOLLAR_FOOTBALL_API_KEY
)

THESPORTSDB_API_KEY = secret_value(
    "api",
    "thesportsdb",
    THESPORTSDB_API_KEY
)

OPENFOOT_API_KEY = secret_value(
    "api",
    "openfoot",
    OPENFOOT_API_KEY
)

OPENROUTER_API_KEY = secret_value(
    "api",
    "openrouter",
    OPENROUTER_API_KEY
)

OPENROUTER_MODEL = secret_value(
    "api",
    "openrouter_model",
    OPENROUTER_MODEL
)

TELEGRAM_BOT_TOKEN = secret_value(
    "telegram",
    "bot_token",
    TELEGRAM_BOT_TOKEN
)

TELEGRAM_CHAT_ID = secret_value(
    "telegram",
    "chat_id",
    TELEGRAM_CHAT_ID
)


# ============================================================
# CONSTANTES
# ============================================================

TIMEOUT = 8

DEFAULT_REFRESH = 5

ESPN_BASE = (
    "https://site.web.api.espn.com"
    "/apis/site/v2/sports/soccer"
)

FIVEDOLLAR_BASE = (
    "https://api.5dollarfootballapi.com/v1"
)

OPENFOOT_BASE = (
    "https://openfootapi.com/v1"
)

FOOTBALL_DATA_BASE = (
    "https://api.football-data.org/v4"
)

THESPORTSDB_BASE = (
    "https://www.thesportsdb.com/api/v2/json"
)


# ============================================================
# LIGAS ESPN
# ============================================================

ESPN_LEAGUES = {
    "Brasil Série A": "bra.1",
    "Brasil Série B": "bra.2",
    "Inglaterra Premier League": "eng.1",
    "Espanha LaLiga": "esp.1",
    "Itália Serie A": "ita.1",
    "Alemanha Bundesliga": "ger.1",
    "França Ligue 1": "fra.1",
    "Argentina": "arg.1",
    "México Liga MX": "mex.1",
    "Colômbia": "col.1",
    "Chile": "chi.1",
    "Portugal": "por.1",
    "Holanda Eredivisie": "ned.1",
    "Turquia": "tur.1",
    "Estados Unidos MLS": "usa.1",
}


# ============================================================
# ESTADO
# ============================================================

if "score_state" not in st.session_state:
    st.session_state.score_state = {}

if "initialized" not in st.session_state:
    st.session_state.initialized = False

if "goal_history" not in st.session_state:
    st.session_state.goal_history = []

if "source_stats" not in st.session_state:
    st.session_state.source_stats = {}

if "espn_block_until" not in st.session_state:
    st.session_state.espn_block_until = 0.0

if "last_cycle" not in st.session_state:
    st.session_state.last_cycle = None

if "cycle_count" not in st.session_state:
    st.session_state.cycle_count = 0


# ============================================================
# UTILITÁRIOS
# ============================================================

def agora_str():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def normalizar_texto(texto):
    if not texto:
        return ""

    texto = str(texto)

    texto = unicodedata.normalize(
        "NFKD",
        texto
    ).encode(
        "ascii",
        "ignore"
    ).decode(
        "ascii"
    )

    texto = texto.lower()

    texto = re.sub(
        r"[^a-z0-9]+",
        " ",
        texto
    )

    return " ".join(texto.split())


def nome_jogo(home, away):
    return f"{home} x {away}"


def chave_jogo(home, away):
    return (
        normalizar_texto(home),
        normalizar_texto(away)
    )


def score_valido(home_score, away_score):
    try:
        if home_score is None:
            home_score = 0

        if away_score is None:
            away_score = 0

        return (
            int(home_score),
            int(away_score)
        )
    except Exception:
        return None


def status_live(status):
    if status is None:
        return True

    s = str(status).upper()

    encerrados = {
        "FT",
        "AET",
        "PEN",
        "FINISHED",
        "FINISH",
        "ENDED",
        "CANCELLED",
        "CANCELED",
        "POSTPONED",
        "PST",
    }

    return s not in encerrados


def http_get(
    url,
    headers=None,
    params=None,
    timeout=TIMEOUT
):
    inicio = time.perf_counter()

    try:
        resposta = requests.get(
            url,
            headers=headers or {},
            params=params or {},
            timeout=timeout
        )

        recebido = time.perf_counter()

        return {
            "ok": resposta.ok,
            "status": resposta.status_code,
            "json": (
                resposta.json()
                if resposta.content
                else {}
            ),
            "inicio": inicio,
            "recebido": recebido,
            "duracao": recebido - inicio,
            "erro": None,
        }

    except Exception as e:
        recebido = time.perf_counter()

        return {
            "ok": False,
            "status": 0,
            "json": {},
            "inicio": inicio,
            "recebido": recebido,
            "duracao": recebido - inicio,
            "erro": str(e),
        }


# ============================================================
# NORMALIZAÇÃO PADRÃO
# ============================================================

def evento(
    source,
    home,
    away,
    home_score,
    away_score,
    status="LIVE",
    minute=None,
    league=None,
    external_id=None,
    recebido=None,
    duracao=None
):
    score = score_valido(
        home_score,
        away_score
    )

    if not score:
        return None

    return {
        "source": source,
        "home": str(home or "").strip(),
        "away": str(away or "").strip(),
        "home_score": score[0],
        "away_score": score[1],
        "status": status,
        "minute": minute,
        "league": league or "",
        "external_id": external_id,
        "received_at": recebido,
        "duration": duracao,
    }


# ============================================================
# ESPN
# ============================================================

def buscar_espn_league(nome_league, league_code):
    agora = time.time()

    # Circuit breaker para 403.
    if agora < st.session_state.espn_block_until:
        return {
            "source": "ESPN",
            "league": nome_league,
            "events": [],
            "status": "PAUSADA_APOS_403",
            "duracao": 0,
            "recebido": time.perf_counter(),
        }

    url = (
        f"{ESPN_BASE}/"
        f"{league_code}/scoreboard"
    )

    inicio = time.perf_counter()

    try:
        # Não utilizar User-Agent de navegador.
        resposta = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            },
            timeout=TIMEOUT
        )

        recebido = time.perf_counter()
        duracao = recebido - inicio

        if resposta.status_code == 403:
            # Pausa por 2 minutos para não martelar
            # a API com vários 403.
            st.session_state.espn_block_until = (
                time.time() + 120
            )

            return {
                "source": "ESPN",
                "league": nome_league,
                "events": [],
                "status": "403_PAUSADA_120S",
                "duracao": duracao,
                "recebido": recebido,
            }

        if not resposta.ok:
            return {
                "source": "ESPN",
                "league": nome_league,
                "events": [],
                "status": f"HTTP_{resposta.status_code}",
                "duracao": duracao,
                "recebido": recebido,
            }

        data = resposta.json()

        eventos = []

        for item in data.get("events", []):
            try:
                comp = item.get(
                    "competitions",
                    [{}]
                )[0]

                competitors = comp.get(
                    "competitors",
                    []
                )

                home = None
                away = None

                for c in competitors:
                    if c.get("homeAway") == "home":
                        home = c
                    elif c.get("homeAway") == "away":
                        away = c

                if not home or not away:
                    continue

                home_name = (
                    home.get("team", {})
                    .get("displayName")
                    or home.get("team", {})
                    .get("name")
                )

                away_name = (
                    away.get("team", {})
                    .get("displayName")
                    or away.get("team", {})
                    .get("name")
                )

                hs = home.get("score", 0)
                aws = away.get("score", 0)

                status_obj = item.get(
                    "status",
                    {}
                )

                status_type = (
                    status_obj
                    .get("type", {})
                    .get("shortDetail")
                    or status_obj
                    .get("type", {})
                    .get("name")
                    or "LIVE"
                )

                minuto = (
                    status_obj
                    .get("displayClock")
                )

                ev = evento(
                    "ESPN",
                    home_name,
                    away_name,
                    hs,
                    aws,
                    status=status_type,
                    minute=minuto,
                    league=nome_league,
                    external_id=item.get("id"),
                    recebido=recebido,
                    duracao=duracao
                )

                if ev and status_live(status_type):
                    eventos.append(ev)

            except Exception:
                continue

        return {
            "source": "ESPN",
            "league": nome_league,
            "events": eventos,
            "status": "OK",
            "duracao": duracao,
            "recebido": recebido,
        }

    except Exception as e:
        recebido = time.perf_counter()

        return {
            "source": "ESPN",
            "league": nome_league,
            "events": [],
            "status": f"ERRO: {str(e)[:80]}",
            "duracao": recebido - inicio,
            "recebido": recebido,
        }


def buscar_espn():
    resultados = []

    # Se ESPN estiver temporariamente bloqueada,
    # não faz várias chamadas inúteis.
    if time.time() < st.session_state.espn_block_until:
        return [{
            "source": "ESPN",
            "league": "Todas",
            "events": [],
            "status": "PAUSADA_APOS_403",
            "duracao": 0,
            "recebido": time.perf_counter(),
        }]

    with ThreadPoolExecutor(
        max_workers=min(8, len(ESPN_LEAGUES))
    ) as executor:

        futures = {
            executor.submit(
                buscar_espn_league,
                nome,
                codigo
            ): nome
            for nome, codigo in ESPN_LEAGUES.items()
        }

        for future in as_completed(futures):
            try:
                resultados.append(
                    future.result()
                )
            except Exception as e:
                resultados.append({
                    "source": "ESPN",
                    "league": futures[future],
                    "events": [],
                    "status": f"ERRO: {e}",
                    "duracao": 0,
                    "recebido": time.perf_counter(),
                })

    return resultados


# ============================================================
# FIVE DOLLAR FOOTBALL
# ============================================================

def buscar_fivedollar():
    if not FIVEDOLLAR_FOOTBALL_API_KEY:
        return {
            "source": "FiveDollar",
            "events": [],
            "status": "SEM_CHAVE",
            "duracao": 0,
            "recebido": time.perf_counter(),
        }

    url = (
        f"{FIVEDOLLAR_BASE}/fixtures"
    )

    headers = {
        "Authorization":
            f"Bearer {FIVEDOLLAR_FOOTBALL_API_KEY}",
        "Accept": "application/json",
    }

    r = http_get(
        url,
        headers=headers,
        params={
            "status": "live",
            "per_page": 500,
        }
    )

    if not r["ok"]:
        return {
            "source": "FiveDollar",
            "events": [],
            "status": (
                f"HTTP_{r['status']}"
                if r["status"]
                else f"ERRO_{r['erro']}"
            ),
            "duracao": r["duracao"],
            "recebido": r["recebido"],
        }

    data = r["json"]

    rows = data.get("data", [])

    eventos = []

    for item in rows:
        try:
            teams = item.get(
                "teams",
                {}
            )

            home = (
                teams.get("home", {})
                .get("name")
            )

            away = (
                teams.get("away", {})
                .get("name")
            )

            goals = item.get(
                "goals",
                {}
            )

            hs = goals.get("home")
            aws = goals.get("away")

            ev = evento(
                "FiveDollar",
                home,
                away,
                hs,
                aws,
                status=item.get("status"),
                league=(
                    item.get("league", {})
                    .get("name")
                ),
                external_id=item.get("id"),
                recebido=r["recebido"],
                duracao=r["duracao"]
            )

            if ev:
                eventos.append(ev)

        except Exception:
            continue

    return {
        "source": "FiveDollar",
        "events": eventos,
        "status": "OK",
        "duracao": r["duracao"],
        "recebido": r["recebido"],
    }


# ============================================================
# OPENFOOT
# ============================================================

def buscar_openfoot():
    if not OPENFOOT_API_KEY:
        return {
            "source": "OpenFoot",
            "events": [],
            "status": "SEM_CHAVE",
            "duracao": 0,
            "recebido": time.perf_counter(),
        }

    url = (
        f"{OPENFOOT_BASE}/matches"
    )

    headers = {
        "Authorization":
            f"Bearer {OPENFOOT_API_KEY}",
        "Accept": "application/json",
    }

    r = http_get(
        url,
        headers=headers,
        params={
            "status": "live",
        }
    )

    if not r["ok"]:
        return {
            "source": "OpenFoot",
            "events": [],
            "status": (
                f"HTTP_{r['status']}"
                if r["status"]
                else f"ERRO_{r['erro']}"
            ),
            "duracao": r["duracao"],
            "recebido": r["recebido"],
        }

    data = r["json"]

    rows = data.get("data", [])

    eventos = []

    for item in rows:
        try:
            home = (
                item.get("homeTeam", {})
                .get("name")
            )

            away = (
                item.get("awayTeam", {})
                .get("name")
            )

            # O contrato do OpenFoot pode apresentar
            # placares em diferentes objetos conforme o
            # endpoint/plano.
            score = (
                item.get("score")
                or item.get("scores")
                or {}
            )

            hs = (
                score.get("home")
                if isinstance(score, dict)
                else None
            )

            aws = (
                score.get("away")
                if isinstance(score, dict)
                else None
            )

            if hs is None:
                hs = (
                    item.get("homeScore")
                    or item.get("homeGoals")
                )

            if aws is None:
                aws = (
                    item.get("awayScore")
                    or item.get("awayGoals")
                )

            ev = evento(
                "OpenFoot",
                home,
                away,
                hs,
                aws,
                status=item.get("status"),
                minute=item.get("minute"),
                league=(
                    item.get("competition", {})
                    .get("name")
                    if isinstance(
                        item.get("competition"),
                        dict
                    )
                    else ""
                ),
                external_id=item.get("id"),
                recebido=r["recebido"],
                duracao=r["duracao"]
            )

            if ev:
                eventos.append(ev)

        except Exception:
            continue

    return {
        "source": "OpenFoot",
        "events": eventos,
        "status": "OK",
        "duracao": r["duracao"],
        "recebido": r["recebido"],
    }


# ============================================================
# FOOTBALL-DATA.ORG
# ============================================================

def buscar_football_data():
    if not FOOTBALL_DATA_API_TOKEN:
        return {
            "source": "FootballData",
            "events": [],
            "status": "SEM_TOKEN",
            "duracao": 0,
            "recebido": time.perf_counter(),
        }

    url = (
        f"{FOOTBALL_DATA_BASE}/matches"
    )

    headers = {
        "X-Auth-Token":
            FOOTBALL_DATA_API_TOKEN,
        "Accept": "application/json",
    }

    r = http_get(
        url,
        headers=headers,
        params={
            "status": "IN_PLAY"
        }
    )

    if not r["ok"]:
        return {
            "source": "FootballData",
            "events": [],
            "status": (
                f"HTTP_{r['status']}"
                if r["status"]
                else f"ERRO_{r['erro']}"
            ),
            "duracao": r["duracao"],
            "recebido": r["recebido"],
        }

    data = r["json"]

    rows = data.get(
        "matches",
        []
    )

    eventos = []

    for item in rows:
        try:
            home = (
                item.get("homeTeam", {})
                .get("name")
            )

            away = (
                item.get("awayTeam", {})
                .get("name")
            )

            score = item.get(
                "score",
                {}
            )

            full = score.get(
                "fullTime",
                {}
            )

            hs = full.get("home")
            aws = full.get("away")

            # Algumas respostas podem fornecer
            # halfTime enquanto fullTime ainda não
            # estiver atualizado.
            if hs is None:
                hs = score.get("halfTime", {}).get("home")

            if aws is None:
                aws = score.get("halfTime", {}).get("away")

            ev = evento(
                "FootballData",
                home,
                away,
                hs,
                aws,
                status=item.get("status"),
                minute=item.get("minute"),
                league=(
                    item.get("competition", {})
                    .get("name")
                ),
                external_id=item.get("id"),
                recebido=r["recebido"],
                duracao=r["duracao"]
            )

            if ev:
                eventos.append(ev)

        except Exception:
            continue

    return {
        "source": "FootballData",
        "events": eventos,
        "status": "OK",
        "duracao": r["duracao"],
        "recebido": r["recebido"],
    }


# ============================================================
# THESPORTSDB
# ============================================================

def buscar_thesportsdb():
    if not THESPORTSDB_API_KEY:
        return {
            "source": "TheSportsDB",
            "events": [],
            "status": "SEM_CHAVE",
            "duracao": 0,
            "recebido": time.perf_counter(),
        }

    url = (
        f"{THESPORTSDB_BASE}/"
        f"livescore/soccer"
    )

    headers = {
        "X-API-KEY":
            THESPORTSDB_API_KEY,
        "Accept": "application/json",
    }

    r = http_get(
        url,
        headers=headers
    )

    if not r["ok"]:
        return {
            "source": "TheSportsDB",
            "events": [],
            "status": (
                f"HTTP_{r['status']}"
                if r["status"]
                else f"ERRO_{r['erro']}"
            ),
            "duracao": r["duracao"],
            "recebido": r["recebido"],
        }

    data = r["json"]

    # Diferentes versões podem devolver
    # livescore ou livescores.
    rows = (
        data.get("livescore")
        or data.get("livescores")
        or data.get("data")
        or []
    )

    if isinstance(rows, dict):
        rows = [rows]

    eventos = []

    for item in rows:
        try:
            home = (
                item.get("strHomeTeam")
                or item.get("homeTeam")
                or item.get("home")
            )

            away = (
                item.get("strAwayTeam")
                or item.get("awayTeam")
                or item.get("away")
            )

            hs = (
                item.get("intHomeScore")
                or item.get("homeScore")
            )

            aws = (
                item.get("intAwayScore")
                or item.get("awayScore")
            )

            ev = evento(
                "TheSportsDB",
                home,
                away,
                hs,
                aws,
                status=item.get("strStatus"),
                minute=item.get("strProgress"),
                league=(
                    item.get("strLeague")
                    or item.get("league")
                    or ""
                ),
                external_id=(
                    item.get("idEvent")
                    or item.get("eventId")
                ),
                recebido=r["recebido"],
                duracao=r["duracao"]
            )

            if ev:
                eventos.append(ev)

        except Exception:
            continue

    return {
        "source": "TheSportsDB",
        "events": eventos,
        "status": "OK",
        "duracao": r["duracao"],
        "recebido": r["recebido"],
    }


# ============================================================
# OPENROUTER
# ============================================================

def analisar_gol_openrouter(
    jogo,
    placar_anterior,
    placar_novo,
    fonte
):
    if not OPENROUTER_API_KEY:
        return "OpenRouter desativado: chave não configurada."

    url = (
        "https://openrouter.ai/api/v1/chat/completions"
    )

    headers = {
        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer":
            "https://football-scanner.streamlit.app",
        "X-Title":
            "Football Goal Race",
    }

    prompt = f"""
Você é um analista de futebol.

Foi detectada uma mudança de placar ao vivo.

Jogo: {jogo}
Placar anterior: {placar_anterior}
Novo placar: {placar_novo}
Primeira fonte que reportou: {fonte}

Faça uma análise MUITO curta, sem inventar estatísticas.

Responda exatamente em 3 linhas:

EVENTO: descreva a mudança do placar.
LEITURA: explique somente o que pode ser concluído do placar.
ATENÇÃO: diga que um placar confirmado por uma API não garante atraso ou vantagem de aposta.
"""

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 180,
    }

    try:
        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        if not r.ok:
            return (
                f"OpenRouter HTTP {r.status_code}: "
                f"{r.text[:150]}"
            )

        data = r.json()

        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

    except Exception as e:
        return f"Erro OpenRouter: {e}"


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(mensagem):
    if not TELEGRAM_BOT_TOKEN:
        return False, "BOT_TOKEN não configurado"

    if not TELEGRAM_CHAT_ID:
        return False, "CHAT_ID não configurado"

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    try:
        r = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensagem,
            },
            timeout=10
        )

        if r.ok:
            return True, "OK"

        return False, f"HTTP {r.status_code}"

    except Exception as e:
        return False, str(e)


# ============================================================
# TODAS AS FONTES EM PARALELO
# ============================================================

def consultar_fontes():
    fontes = [
        ("ESPN", buscar_espn),
        ("FiveDollar", buscar_fivedollar),
        ("OpenFoot", buscar_openfoot),
        ("FootballData", buscar_football_data),
        ("TheSportsDB", buscar_thesportsdb),
    ]

    resultados = []

    inicio_ciclo = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=5
    ) as executor:

        futures = {
            executor.submit(func): nome
            for nome, func in fontes
        }

        for future in as_completed(futures):
            nome = futures[future]

            try:
                resultado = future.result()

            except Exception as e:
                resultado = {
                    "source": nome,
                    "events": [],
                    "status": f"ERRO: {e}",
                    "duracao": 0,
                    "recebido": time.perf_counter(),
                }

            resultados.append(resultado)

    fim_ciclo = time.perf_counter()

    # Ordena pela hora REAL de recebimento.
    resultados.sort(
        key=lambda x: x.get(
            "recebido",
            float("inf")
        )
    )

    return resultados, (
        fim_ciclo - inicio_ciclo
    )


# ============================================================
# INDEXAÇÃO
# ============================================================

def indexar_resultados(resultados):
    jogos = {}

    for resultado in resultados:

        source = resultado.get(
            "source",
            ""
        )

        recebido = resultado.get(
            "recebido",
            time.perf_counter()
        )

        duracao = resultado.get(
            "duracao",
            0
        )

        for ev in resultado.get(
            "events",
            []
        ):

            home = ev.get("home")
            away = ev.get("away")

            if not home or not away:
                continue

            chave = chave_jogo(
                home,
                away
            )

            ev["received_at"] = recebido
            ev["duration"] = duracao

            if chave not in jogos:
                jogos[chave] = []

            jogos[chave].append(ev)

    return jogos


# ============================================================
# DETECÇÃO DE GOLS
# ============================================================

def detectar_gols(jogos):
    novos_gols = []

    # Cada jogo é analisado separadamente.
    for chave, eventos in jogos.items():

        if not eventos:
            continue

        # Ordem REAL em que as respostas chegaram.
        eventos_ordenados = sorted(
            eventos,
            key=lambda x: x.get(
                "received_at",
                float("inf")
            )
        )

        # Último placar conhecido pelo conjunto das fontes.
        placares = []

        for ev in eventos_ordenados:
            placares.append(
                (
                    ev["home_score"],
                    ev["away_score"]
                )
            )

        if not placares:
            continue

        melhor_score = max(
            placares,
            key=lambda x: sum(x)
        )

        home = eventos_ordenados[0]["home"]
        away = eventos_ordenados[0]["away"]

        nome = nome_jogo(
            home,
            away
        )

        estado_anterior = st.session_state.score_state.get(
            chave
        )

        # Primeiro ciclo:
        # apenas cria baseline.
        if estado_anterior is None:

            st.session_state.score_state[
                chave
            ] = melhor_score

            continue

        # Não houve mudança.
        if (
            melhor_score[0] <= estado_anterior[0]
            and
            melhor_score[1] <= estado_anterior[1]
        ):
            continue

        # Encontrar a PRIMEIRA fonte que já
        # havia recebido o novo placar.
        fonte_primeira = None
        evento_primeiro = None

        for ev in eventos_ordenados:

            score_ev = (
                ev["home_score"],
                ev["away_score"]
            )

            if (
                score_ev[0] >= melhor_score[0]
                and
                score_ev[1] >= melhor_score[1]
            ):
                fonte_primeira = ev["source"]
                evento_primeiro = ev
                break

        if not fonte_primeira:
            fonte_primeira = eventos_ordenados[0]["source"]
            evento_primeiro = eventos_ordenados[0]

        # Timestamp de chegada da primeira fonte.
        primeiro_recebimento = (
            evento_primeiro.get(
                "received_at"
            )
        )

        # Ranking das fontes para esse jogo.
        ranking = []

        for ev in eventos_ordenados:

            score_ev = (
                ev["home_score"],
                ev["away_score"]
            )

            if (
                score_ev[0] >= melhor_score[0]
                and
                score_ev[1] >= melhor_score[1]
            ):
                ranking.append({
                    "source": ev["source"],
                    "received_at": ev.get(
                        "received_at"
                    ),
                    "duration": ev.get(
                        "duration",
                        0
                    ),
                    "score": score_ev,
                })

        # Atualiza baseline.
        st.session_state.score_state[
            chave
        ] = melhor_score

        novos_gols.append({
            "jogo": nome,
            "home": home,
            "away": away,
            "anterior": estado_anterior,
            "novo": melhor_score,
            "fonte_primeira": fonte_primeira,
            "evento": evento_primeiro,
            "ranking": ranking,
            "hora": agora_str(),
            "league": evento_primeiro.get(
                "league",
                ""
            ),
        })

    return novos_gols


# ============================================================
# ATUALIZAÇÃO DAS ESTATÍSTICAS DAS FONTES
# ============================================================

def atualizar_ranking_fontes(
    resultados,
    gols
):
    for resultado in resultados:

        source = resultado.get(
            "source"
        )

        if source not in st.session_state.source_stats:
            st.session_state.source_stats[
                source
            ] = {
                "consultas": 0,
                "sucesso": 0,
                "erros": 0,
                "primeiros": 0,
                "latencias": [],
            }

        stats = st.session_state.source_stats[
            source
        ]

        stats["consultas"] += 1

        status = str(
            resultado.get(
                "status",
                ""
            )
        )

        if status == "OK":
            stats["sucesso"] += 1
        else:
            stats["erros"] += 1

        duracao = resultado.get(
            "duracao"
        )

        if duracao:
            stats["latencias"].append(
                duracao
            )

            # Limita memória.
            stats["latencias"] = (
                stats["latencias"][-500:]
            )

    # Quem ganhou cada corrida de gol?
    for gol in gols:

        vencedor = gol.get(
            "fonte_primeira"
        )

        if not vencedor:
            continue

        if vencedor not in st.session_state.source_stats:
            st.session_state.source_stats[
                vencedor
            ] = {
                "consultas": 0,
                "sucesso": 0,
                "erros": 0,
                "primeiros": 0,
                "latencias": [],
            }

        st.session_state.source_stats[
            vencedor
        ]["primeiros"] += 1


# ============================================================
# PROCESSAMENTO DO CICLO
# ============================================================

def executar_ciclo():
    resultados, tempo_ciclo = consultar_fontes()

    jogos = indexar_resultados(
        resultados
    )

    gols = detectar_gols(
        jogos
    )

    atualizar_ranking_fontes(
        resultados,
        gols
    )

    st.session_state.last_cycle = {
        "resultados": resultados,
        "jogos": jogos,
        "gols": gols,
        "tempo": tempo_ciclo,
        "hora": agora_str(),
    }

    st.session_state.cycle_count += 1

    return (
        resultados,
        jogos,
        gols,
        tempo_ciclo
    )


# ============================================================
# ALERTAS DE GOL
# ============================================================

def processar_alertas(gols):
    for gol in gols:

        jogo = gol["jogo"]

        anterior = gol["anterior"]

        novo = gol["novo"]

        fonte = gol["fonte_primeira"]

        mensagem = (
            "⚽ GOL DETECTADO\n\n"
            f"{jogo}\n"
            f"{anterior[0]} x {anterior[1]}"
            " → "
            f"{novo[0]} x {novo[1]}\n\n"
            f"🥇 Primeira fonte: {fonte}\n"
            f"⏱️ Detecção: {gol['hora']}\n"
        )

        # ----------------------------------------------------
        # OPENROUTER
        # ----------------------------------------------------

        analise = analisar_gol_openrouter(
            jogo,
            f"{anterior[0]} x {anterior[1]}",
            f"{novo[0]} x {novo[1]}",
            fonte
        )

        mensagem_completa = (
            mensagem
            + "\n🤖 ANÁLISE\n"
            + analise
        )

        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        registro = {
            "hora": gol["hora"],
            "jogo": jogo,
            "anterior": (
                f"{anterior[0]} x "
                f"{anterior[1]}"
            ),
            "novo": (
                f"{novo[0]} x "
                f"{novo[1]}"
            ),
            "primeira_fonte": fonte,
            "analise": analise,
            "ranking": gol["ranking"],
        }

        st.session_state.goal_history.insert(
            0,
            registro
        )

        # máximo 100 eventos
        st.session_state.goal_history = (
            st.session_state.goal_history[:100]
        )

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            enviar_telegram(
                mensagem_completa
            )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("⚙️ Configuração")

intervalo = st.sidebar.slider(
    "Intervalo de atualização",
    min_value=2,
    max_value=30,
    value=DEFAULT_REFRESH,
    step=1
)

st.sidebar.markdown("---")

st.sidebar.subheader(
    "🏆 Ligas ESPN"
)

ligas_selecionadas = st.sidebar.multiselect(
    "Ligas consultadas pela ESPN",
    list(ESPN_LEAGUES.keys()),
    default=[
        "Brasil Série A",
        "Brasil Série B",
        "Inglaterra Premier League",
        "Espanha LaLiga",
        "Itália Serie A",
        "Alemanha Bundesliga",
        "França Ligue 1",
    ]
)

# Atualiza globalmente para esta execução.
if ligas_selecionadas:
    ESPN_LEAGUES_ATIVAS = {
        nome: ESPN_LEAGUES[nome]
        for nome in ligas_selecionadas
    }
else:
    ESPN_LEAGUES_ATIVAS = {}


# Substitui o conjunto usado pela função.
ESPN_LEAGUES = ESPN_LEAGUES_ATIVAS


st.sidebar.markdown("---")

st.sidebar.subheader(
    "🔔 Alertas"
)

telegram_ativo = bool(
    TELEGRAM_BOT_TOKEN
    and TELEGRAM_CHAT_ID
)

openrouter_ativo = bool(
    OPENROUTER_API_KEY
)


# ============================================================
# CABEÇALHO
# ============================================================

st.title(
    "⚽ Football Goal Race"
)

st.caption(
    "Monitoramento simultâneo de fontes "
    "com corrida de chegada do placar."
)


# ============================================================
# STATUS DAS FONTES
# ============================================================

st.subheader(
    "📡 Status das fontes"
)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "ESPN",
        (
            "🟢 ATIVA"
            if time.time() >= st.session_state.espn_block_until
            else "🟠 PAUSADA"
        )
    )

with col2:
    st.metric(
        "FiveDollar",
        (
            "🟢 ATIVA"
            if FIVEDOLLAR_FOOTBALL_API_KEY
            else "🟡 SEM CHAVE"
        )
    )

with col3:
    st.metric(
        "OpenFoot",
        (
            "🟢 ATIVA"
            if OPENFOOT_API_KEY
            else "🟡 SEM CHAVE"
        )
    )

with col4:
    st.metric(
        "FootballData",
        (
            "🟢 ATIVA"
            if FOOTBALL_DATA_API_TOKEN
            else "🟡 SEM TOKEN"
        )
    )

with col5:
    st.metric(
        "TheSportsDB",
        (
            "🟢 CONFIGURADA"
            if THESPORTSDB_API_KEY
            else "🟡 SEM CHAVE"
        )
    )


# ============================================================
# OPENROUTER / TELEGRAM
# ============================================================

col_a, col_b = st.columns(2)

with col_a:
    st.info(
        "🤖 OpenRouter: "
        + (
            "ATIVO"
            if openrouter_ativo
            else "DESATIVADO"
        )
    )

with col_b:
    st.info(
        "📲 Telegram: "
        + (
            "ATIVO"
            if telegram_ativo
            else "DESATIVADO"
        )
    )


# ============================================================
# EXECUTAR
# ============================================================

with st.spinner(
    "Consultando as 5 fontes simultaneamente..."
):
    (
        resultados,
        jogos,
        gols,
        tempo_ciclo
    ) = executar_ciclo()


# Processar alertas somente após
# detectar as mudanças.
processar_alertas(
    gols
)


# ============================================================
# RESUMO
# ============================================================

st.markdown("---")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Jogos encontrados",
        len(jogos)
    )

with col2:
    st.metric(
        "Gols neste ciclo",
        len(gols)
    )

with col3:
    st.metric(
        "Tempo do ciclo",
        f"{tempo_ciclo:.3f}s"
    )

with col4:
    st.metric(
        "Ciclo",
        st.session_state.cycle_count
    )


# ============================================================
# GOLS DETECTADOS
# ============================================================

if gols:

    st.markdown("---")

    st.subheader(
        "🚨 GOL(S) DETECTADO(S)"
    )

    for gol in gols:

        st.success(
            f"⚽ {gol['jogo']}  |  "
            f"{gol['anterior'][0]} x "
            f"{gol['anterior'][1]}"
            " → "
            f"{gol['novo'][0]} x "
            f"{gol['novo'][1]}"
        )

        st.write(
            f"🥇 **Primeira fonte:** "
            f"{gol['fonte_primeira']}"
        )

        if gol.get("league"):
            st.write(
                f"🏆 **Liga:** "
                f"{gol['league']}"
            )

        st.write(
            f"🕐 **Detectado às:** "
            f"{gol['hora']}"
        )

        if gol["ranking"]:

            tabela = []

            base = (
                gol["ranking"][0]
                ["received_at"]
            )

            for pos, item in enumerate(
                gol["ranking"],
                start=1
            ):

                atraso = (
                    item["received_at"]
                    - base
                )

                tabela.append({
                    "#": pos,
                    "Fonte": item["source"],
                    "Placar": (
                        f"{item['score'][0]} x "
                        f"{item['score'][1]}"
                    ),
                    "Tempo requisição": (
                        f"{item['duration']:.3f}s"
                    ),
                    "Atraso após 1ª": (
                        f"+{atraso:.3f}s"
                    ),
                })

            st.dataframe(
                tabela,
                use_container_width=True,
                hide_index=True
            )

        # análise OpenRouter
        if st.session_state.goal_history:

            analise_atual = (
                st.session_state.goal_history[0]
                .get("analise", "")
            )

            if analise_atual:
                st.markdown(
                    "**🤖 OpenRouter**"
                )

                st.code(
                    analise_atual,
                    language="text"
                )


# ============================================================
# JOGOS AO VIVO
# ============================================================

st.markdown("---")

st.subheader(
    "🔴 Jogos monitorados"
)

linhas = []

for chave, eventos in jogos.items():

    if not eventos:
        continue

    # Preferir o último placar conhecido.
    eventos_ordenados = sorted(
        eventos,
        key=lambda x: x.get(
            "received_at",
            0
        )
    )

    ultimo = eventos_ordenados[-1]

    fontes = sorted(
        set(
            e["source"]
            for e in eventos
        )
    )

    linhas.append({
        "Jogo": nome_jogo(
            ultimo["home"],
            ultimo["away"]
        ),
        "Placar": (
            f"{ultimo['home_score']} x "
            f"{ultimo['away_score']}"
        ),
        "Minuto": (
            ultimo.get("minute")
            or "-"
        ),
        "Liga": (
            ultimo.get("league")
            or "-"
        ),
        "Fontes": ", ".join(fontes),
    })


if linhas:

    linhas.sort(
        key=lambda x: x["Jogo"]
    )

    st.dataframe(
        linhas,
        use_container_width=True,
        hide_index=True
    )

else:

    st.warning(
        "Nenhum jogo ao vivo foi retornado "
        "pelas fontes neste ciclo."
    )


# ============================================================
# RANKING DAS FONTES
# ============================================================

st.markdown("---")

st.subheader(
    "🏁 Ranking de velocidade das fontes"
)

ranking_fontes = []

for source, stats in (
    st.session_state.source_stats.items()
):

    latencias = stats.get(
        "latencias",
        []
    )

    media = (
        sum(latencias) / len(latencias)
        if latencias
        else 0
    )

    ranking_fontes.append({
        "Fonte": source,
        "🥇 Primeiras": stats.get(
            "primeiros",
            0
        ),
        "Consultas": stats.get(
            "consultas",
            0
        ),
        "Sucesso": stats.get(
            "sucesso",
            0
        ),
        "Erros": stats.get(
            "erros",
            0
        ),
        "Latência média": (
            f"{media:.3f}s"
            if media
            else "-"
        ),
    })


ranking_fontes.sort(
    key=lambda x: (
        -x["🥇 Primeiras"],
        float(
            x["Latência média"]
            .replace("s", "")
        )
        if x["Latência média"] != "-"
        else 999
    )
)

if ranking_fontes:

    st.dataframe(
        ranking_fontes,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# HISTÓRICO
# ============================================================

st.markdown("---")

st.subheader(
    "📜 Histórico de gols"
)

if st.session_state.goal_history:

    historico = []

    for item in (
        st.session_state.goal_history
    ):

        historico.append({
            "Hora": item["hora"],
            "Jogo": item["jogo"],
            "Anterior": item["anterior"],
            "Novo": item["novo"],
            "Primeira fonte": (
                item["primeira_fonte"]
            ),
        })

    st.dataframe(
        historico,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Nenhum gol novo detectado desde "
        "o início do monitor."
    )


# ============================================================
# DIAGNÓSTICO DAS FONTES
# ============================================================

st.markdown("---")

st.subheader(
    "🔧 Diagnóstico"
)

diagnostico = []

for resultado in sorted(
    resultados,
    key=lambda x: x.get(
        "recebido",
        float("inf")
    )
):

    diagnostico.append({
        "Fonte": resultado.get(
            "source"
        ),
        "Status": resultado.get(
            "status"
        ),
        "Jogos": len(
            resultado.get(
                "events",
                []
            )
        ),
        "Resposta": (
            f"{resultado.get('duracao', 0):.3f}s"
        ),
    })


st.dataframe(
    diagnostico,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# RODAPÉ
# ============================================================

st.caption(
    f"Último ciclo: "
    f"{st.session_state.last_cycle['hora'] "
    if st.session_state.last_cycle else agora_str()} "
    f"| Próxima atualização em {intervalo}s"
)


# ============================================================
# AUTO REFRESH
# ============================================================

time.sleep(intervalo)

st.rerun()
