import os
import time
import hashlib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import streamlit as st


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Football Scanner",
    page_icon="⚽",
    layout="wide",
)

REQUEST_TIMEOUT = 8
OPENROUTER_TIMEOUT = 15

DEFAULT_INTERVAL = 15
MIN_INTERVAL = 5
MAX_INTERVAL = 300

SOURCE_WORKERS = 6
ESPN_COOLDOWN = 120

ESPN_LEAGUES = [
    "eng.1",
    "esp.1",
    "ita.1",
    "ger.1",
    "fra.1",
    "bra.1",
    "arg.1",
    "mex.1",
    "usa.1",
    "col.1",
    "chi.1",
    "bol.1",
    "par.1",
    "uru.1",
    "per.1",
]


# ============================================================
# FUNÇÃO PARA LER SECRETS
# ============================================================

def get_secret(name, default=""):
    try:
        value = st.secrets.get(name)
        if value:
            return str(value).strip()
    except Exception:
        pass

    return os.getenv(name, default).strip()


FOOTBALL_DATA_TOKEN = get_secret(
    "FOOTBALL_DATA_API_TOKEN"
)

FIVEDOLLAR_KEY = get_secret(
    "FIVEDOLLAR_FOOTBALL_API_KEY"
)

THESPORTSDB_KEY = get_secret(
    "THESPORTSDB_API_KEY"
)

OPENFOOT_KEY = get_secret(
    "OPENFOOT_API_KEY"
)

API_FOOTBALL_KEY = get_secret(
    "API_FOOTBALL_KEY"
)

OPENROUTER_API_KEY = get_secret(
    "OPENROUTER_API_KEY"
)

OPENROUTER_MODEL = get_secret(
    "OPENROUTER_MODEL",
    "openrouter/free"
)

TELEGRAM_BOT_TOKEN = get_secret(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = get_secret(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# SESSION STATE
# ============================================================

if "score_cache" not in st.session_state:
    st.session_state.score_cache = {}

if "goal_history" not in st.session_state:
    st.session_state.goal_history = []

if "source_stats" not in st.session_state:
    st.session_state.source_stats = {}

if "espn_block_until" not in st.session_state:
    st.session_state.espn_block_until = 0

if "analysis_cache" not in st.session_state:
    st.session_state.analysis_cache = {}

if "sent_goal_ids" not in st.session_state:
    st.session_state.sent_goal_ids = set()

if "last_cycle" not in st.session_state:
    st.session_state.last_cycle = None


# ============================================================
# UTILITÁRIOS
# ============================================================

def agora():
    return datetime.now().strftime("%H:%M:%S")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default

        return int(float(value))

    except Exception:
        return default


def text(value):
    if value is None:
        return ""

    return str(value).strip()


def path(obj, *keys):
    current = obj

    for key in keys:

        if isinstance(current, dict):
            current = current.get(key)

        elif isinstance(current, list):

            if isinstance(key, int):
                if 0 <= key < len(current):
                    current = current[key]
                else:
                    return None

            else:
                return None

        else:
            return None

    return current


def first(obj, keys, default=None):

    if not isinstance(obj, dict):
        return default

    for key in keys:

        value = obj.get(key)

        if value not in (None, ""):
            return value

    return default


def parse_score(value):

    if isinstance(value, dict):

        home = first(
            value,
            [
                "home",
                "home_score",
                "homeScore",
                "local",
            ],
        )

        away = first(
            value,
            [
                "away",
                "away_score",
                "awayScore",
                "visitor",
            ],
        )

        if home is not None and away is not None:

            return (
                safe_int(home),
                safe_int(away),
            )

    if isinstance(value, (list, tuple)):

        if len(value) >= 2:

            return (
                safe_int(value[0]),
                safe_int(value[1]),
            )

    return 0, 0


def create_id(
    source,
    raw_id,
    home,
    away,
    kickoff="",
):

    if raw_id not in (None, ""):
        return f"{source}:{raw_id}"

    base = (
        f"{home}|{away}|{kickoff}"
        .lower()
        .encode()
    )

    digest = hashlib.sha1(
        base
    ).hexdigest()[:16]

    return f"{source}:{digest}"


# ============================================================
# EVENTO PADRONIZADO
# ============================================================

def make_event(
    source,
    raw_id,
    home,
    away,
    home_score,
    away_score,
    status="",
    minute="",
    kickoff="",
    league="",
    country="",
    raw=None,
):

    home = text(home) or "Casa"
    away = text(away) or "Fora"

    home_score = safe_int(home_score)
    away_score = safe_int(away_score)

    return {
        "id": create_id(
            source,
            raw_id,
            home,
            away,
            kickoff,
        ),
        "raw_id": raw_id,
        "source": source,
        "home": home,
        "away": away,
        "home_score": home_score,
        "away_score": away_score,
        "score": f"{home_score}-{away_score}",
        "status": text(status),
        "minute": text(minute),
        "kickoff": text(kickoff),
        "league": text(league),
        "country": text(country),

        # Momento exato da chegada da resposta
        "received_at": time.perf_counter(),

        "received_wall": utc_now(),
        "raw": raw,
    }


# ============================================================
# HTTP
# ============================================================

def get_json(
    url,
    headers=None,
    params=None,
    timeout=REQUEST_TIMEOUT,
):

    response = requests.get(
        url,
        headers=headers or {},
        params=params or {},
        timeout=timeout,
    )

    try:
        data = response.json()

    except Exception:
        data = {}

    return response, data


def source_result(
    name,
    events=None,
    ok=True,
    status=None,
    error="",
    elapsed=0,
):

    return {
        "source": name,
        "events": events or [],
        "ok": ok,
        "status": status,
        "error": error,
        "elapsed": elapsed,
        "received_at": time.perf_counter(),
    }


# ============================================================
# ESPN
# ============================================================

def normalize_espn(item):

    competitions = (
        item.get("competitions")
        or []
    )

    competition = (
        competitions[0]
        if competitions
        else {}
    )

    competitors = (
        competition.get("competitors")
        or []
    )

    home = {}
    away = {}

    for competitor in competitors:

        if competitor.get("homeAway") == "home":
            home = competitor

        elif competitor.get("homeAway") == "away":
            away = competitor

    return make_event(

        "ESPN",

        item.get("id"),

        path(
            home,
            "team",
            "displayName",
        ),

        path(
            away,
            "team",
            "displayName",
        ),

        first(
            home,
            ["score"],
            0,
        ),

        first(
            away,
            ["score"],
            0,
        ),

        status=path(
            competition,
            "status",
            "type",
            "name",
        ),

        minute=(
            path(
                competition,
                "status",
                "displayClock",
            )
            or
            path(
                competition,
                "status",
                "type",
                "shortDetail",
            )
        ),

        kickoff=item.get(
            "date",
            "",
        ),

        league=path(
            item,
            "league",
            "name",
        ),

        raw=item,
    )


def fetch_espn_league(league):

    start = time.perf_counter()

    if (
        time.time()
        < st.session_state.espn_block_until
    ):

        return source_result(
            f"ESPN/{league}",
            ok=False,
            status=403,
            error="ESPN em cooldown após HTTP 403",
            elapsed=time.perf_counter() - start,
        )

    urls = [
        (
            "https://site.web.api.espn.com"
            f"/apis/site/v2/sports/soccer/"
            f"{league}/scoreboard"
        ),
        (
            "https://site.api.espn.com"
            f"/apis/site/v2/sports/soccer/"
            f"{league}/scoreboard"
        ),
    ]

    last_status = None
    last_error = ""

    for url in urls:

        try:

            response, data = get_json(
                url,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
            )

            last_status = response.status_code

            if response.status_code == 403:

                last_error = "HTTP 403"
                continue

            if response.status_code == 429:

                last_error = "HTTP 429"
                break

            if response.status_code >= 400:

                last_error = (
                    f"HTTP {response.status_code}"
                )
                continue

            raw_events = (
                data.get("events")
                or []
            )

            events = []

            for item in raw_events:

                try:
                    events.append(
                        normalize_espn(item)
                    )

                except Exception:
                    pass

            return source_result(
                f"ESPN/{league}",
                events=events,
                ok=True,
                status=response.status_code,
                elapsed=time.perf_counter() - start,
            )

        except Exception as exc:

            last_error = str(exc)

    if last_status == 403:

        st.session_state.espn_block_until = (
            time.time() + ESPN_COOLDOWN
        )

    return source_result(
        f"ESPN/{league}",
        ok=False,
        status=last_status,
        error=last_error,
        elapsed=time.perf_counter() - start,
    )


def fetch_espn():

    start = time.perf_counter()

    if (
        time.time()
        < st.session_state.espn_block_until
    ):

        return source_result(
            "ESPN",
            ok=False,
            status=403,
            error="ESPN em cooldown após HTTP 403",
            elapsed=time.perf_counter() - start,
        )

    results = []

    with ThreadPoolExecutor(
        max_workers=8
    ) as executor:

        futures = {
            executor.submit(
                fetch_espn_league,
                league,
            ): league
            for league in ESPN_LEAGUES
        }

        for future in as_completed(
            futures
        ):

            try:
                results.append(
                    future.result()
                )

            except Exception as exc:

                results.append(
                    source_result(
                        f"ESPN/{futures[future]}",
                        ok=False,
                        error=str(exc),
                    )
                )

    events = []
    errors = []
    any_ok = False

    for result in results:

        if result.get("ok"):
            any_ok = True

        events.extend(
            result.get("events", [])
        )

        if result.get("error"):
            errors.append(
                f"{result['source']}: "
                f"{result['error']}"
            )

    return source_result(
        "ESPN",
        events=events,
        ok=any_ok,
        status=200 if any_ok else None,
        error=" | ".join(errors[:5]),
        elapsed=time.perf_counter() - start,
    )


# ============================================================
# FOOTBALL-DATA
# ============================================================

def normalize_football_data(item):

    score = (
        item.get("score")
        or {}
    )

    full_time = (
        score.get("fullTime")
        or {}
    )

    return make_event(

        "FootballData",

        item.get("id"),

        path(
            item,
            "homeTeam",
            "name",
        ),

        path(
            item,
            "awayTeam",
            "name",
        ),

        full_time.get(
            "home",
            0,
        ),

        full_time.get(
            "away",
            0,
        ),

        status=item.get(
            "status",
            "",
        ),

        kickoff=item.get(
            "utcDate",
            "",
        ),

        league=path(
            item,
            "competition",
            "name",
        ),

        country=path(
            item,
            "area",
            "name",
        ),

        raw=item,
    )


def fetch_football_data():

    start = time.perf_counter()

    if not FOOTBALL_DATA_TOKEN:

        return source_result(
            "FootballData",
            ok=False,
            error=(
                "FOOTBALL_DATA_API_TOKEN "
                "não configurada"
            ),
            elapsed=time.perf_counter() - start,
        )

    try:

        response, data = get_json(

            "https://api.football-data.org/v4/matches",

            headers={
                "X-Auth-Token":
                    FOOTBALL_DATA_TOKEN,
                "Accept":
                    "application/json",
            },

            params={
                "status": "IN_PLAY",
            },
        )

        if response.status_code >= 400:

            return source_result(
                "FootballData",
                ok=False,
                status=response.status_code,
                error=str(data)[:500],
                elapsed=time.perf_counter() - start,
            )

        raw = (
            data.get("matches")
            or []
        )

        events = []

        for item in raw:

            try:
                events.append(
                    normalize_football_data(
                        item
                    )
                )

            except Exception:
                pass

        return source_result(
            "FootballData",
            events=events,
            ok=True,
            status=response.status_code,
            elapsed=time.perf_counter() - start,
        )

    except Exception as exc:

        return source_result(
            "FootballData",
            ok=False,
            error=str(exc),
            elapsed=time.perf_counter() - start,
        )


# ============================================================
# API-FOOTBALL
# ============================================================

def normalize_api_football(item):

    fixture = (
        item.get("fixture")
        or {}
    )

    teams = (
        item.get("teams")
        or {}
    )

    goals = (
        item.get("goals")
        or {}
    )

    return make_event(

        "APIFootball",

        fixture.get("id"),

        path(
            teams,
            "home",
            "name",
        ),

        path(
            teams,
            "away",
            "name",
        ),

        goals.get(
            "home",
            0,
        ),

        goals.get(
            "away",
            0,
        ),

        status=path(
            fixture,
            "status",
            "short",
        ),

        minute=path(
            fixture,
            "status",
            "elapsed",
        ),

        kickoff=fixture.get(
            "date",
            "",
        ),

        league=path(
            item,
            "league",
            "name",
        ),

        country=path(
            item,
            "league",
            "country",
        ),

        raw=item,
    )


def fetch_api_football():

    start = time.perf_counter()

    if not API_FOOTBALL_KEY:

        return source_result(
            "APIFootball",
            ok=False,
            error=(
                "API_FOOTBALL_KEY "
                "não configurada"
            ),
            elapsed=time.perf_counter() - start,
        )

    try:

        response, data = get_json(

            "https://v3.football.api-sports.io/fixtures",

            headers={
                "x-apisports-key":
                    API_FOOTBALL_KEY,
                "Accept":
                    "application/json",
            },

            params={
                "live": "all",
            },
        )

        if response.status_code >= 400:

            return source_result(
                "APIFootball",
                ok=False,
                status=response.status_code,
                error=str(data)[:500],
                elapsed=time.perf_counter() - start,
            )

        raw = (
            data.get("response")
            or []
        )

        events = []

        for item in raw:

            try:
                events.append(
                    normalize_api_football(
                        item
                    )
                )

            except Exception:
                pass

        return source_result(
            "APIFootball",
            events=events,
            ok=True,
            status=response.status_code,
            elapsed=time.perf_counter() - start,
        )

    except Exception as exc:

        return source_result(
            "APIFootball",
            ok=False,
            error=str(exc),
            elapsed=time.perf_counter() - start,
        )


# ============================================================
# THESPORTSDB
# ============================================================

def normalize_tsdb(item):

    return make_event(

        "TheSportsDB",

        item.get("idEvent"),

        item.get(
            "strHomeTeam"
        ),

        item.get(
            "strAwayTeam"
        ),

        item.get(
            "intHomeScore",
            0,
        ),

        item.get(
            "intAwayScore",
            0,
        ),

        status=item.get(
            "strStatus",
            "",
        ),

        minute=item.get(
            "strProgress",
            "",
        ),

        kickoff=(
            item.get(
                "strEventTime"
            )
            or item.get(
                "dateEvent"
            )
            or ""
        ),

        league=item.get(
            "strLeague",
            "",
        ),

        raw=item,
    )


def fetch_tsdb():

    start = time.perf_counter()

    if not THESPORTSDB_KEY:

        return source_result(
            "TheSportsDB",
            ok=False,
            error=(
                "THESPORTSDB_API_KEY "
                "não configurada"
            ),
            elapsed=time.perf_counter() - start,
        )

    try:

        response, data = get_json(

            "https://www.thesportsdb.com/api/v2/json/livescore/soccer",

            headers={
                "X-API-KEY":
                    THESPORTSDB_KEY,
                "Accept":
                    "application/json",
            },
        )

        if response.status_code >= 400:

            return source_result(
                "TheSportsDB",
                ok=False,
                status=response.status_code,
                error=str(data)[:500],
                elapsed=time.perf_counter() - start,
            )

        raw = []

        if isinstance(data, list):

            raw = data

        elif isinstance(data, dict):

            for key in (
                "data",
                "events",
                "livescore",
                "results",
            ):

                if isinstance(
                    data.get(key),
                    list,
                ):

                    raw = data[key]
                    break

        events = []

        for item in raw:

            try:
                events.append(
                    normalize_tsdb(item)
                )

            except Exception:
                pass

        return source_result(
            "TheSportsDB",
            events=events,
            ok=True,
            status=response.status_code,
            elapsed=time.perf_counter() - start,
        )

    except Exception as exc:

        return source_result(
            "TheSportsDB",
            ok=False,
            error=str(exc),
            elapsed=time.perf_counter() - start,
        )


# ============================================================
# 5DOLLAR
# ============================================================

def normalize_5dollar(item):

    teams = (
        item.get("teams")
        or {}
    )

    home = (
        teams.get("home")
        or {}
    )

    away = (
        teams.get("away")
        or {}
    )

    goals = (
        item.get("goals")
        or {}
    )

    return make_event(

        "5Dollar",

        item.get("id"),

        home.get("name"),
        away.get("name"),

        goals.get("home", 0),
        goals.get("away", 0),

        status=item.get(
            "status",
            "",
        ),

        minute=(
            item.get("minute")
            or ""
        ),

        kickoff=(
            item.get(
                "kickoff_utc",
                "",
            )
        ),

        league=path(
            item,
            "league",
            "name",
        ),

        raw=item,
    )


def fetch_5dollar():

    start = time.perf_counter()

    if not FIVEDOLLAR_KEY:

        return source_result(
            "5Dollar",
            ok=False,
            error=(
                "FIVEDOLLAR_FOOTBALL_API_KEY "
                "não configurada"
            ),
            elapsed=time.perf_counter() - start,
        )

    try:

        response, data = get_json(

            "https://api.5dollarfootballapi.com/v1/fixtures",

            headers={
                "Authorization":
                    f"Bearer {FIVEDOLLAR_KEY}",
                "Accept":
                    "application/json",
            },

            params={
                "status": "live",
            },
        )

        if response.status_code >= 400:

            return source_result(
                "5Dollar",
                ok=False,
                status=response.status_code,
                error=str(data)[:500],
                elapsed=time.perf_counter() - start,
            )

        raw = []

        if isinstance(data, list):

            raw = data

        elif isinstance(data, dict):

            for key in (
                "data",
                "fixtures",
                "matches",
                "results",
            ):

                if isinstance(
                    data.get(key),
                    list,
                ):

                    raw = data[key]
                    break

        events = []

        for item in raw:

            try:
                events.append(
                    normalize_5dollar(
                        item
                    )
                )

            except Exception:
                pass

        return source_result(
            "5Dollar",
            events=events,
            ok=True,
            status=response.status_code,
            elapsed=time.perf_counter() - start,
        )

    except Exception as exc:

        return source_result(
            "5Dollar",
            ok=False,
            error=str(exc),
            elapsed=time.perf_counter() - start,
        )


# ============================================================
# OPENFOOT
# ============================================================

def normalize_openfoot(item):

    home = (
        item.get("homeTeam")
        or {}
    )

    away = (
        item.get("awayTeam")
        or {}
    )

    score = (
        item.get("score")
        or item.get("goals")
        or {}
    )

    hs, aws = parse_score(score)

    return make_event(

        "OpenFoot",

        item.get("id"),

        home.get("name")
        or item.get("home"),

        away.get("name")
        or item.get("away"),

        hs,
        aws,

        status=item.get(
            "status",
            "",
        ),

        minute=(
            item.get("minute")
            or item.get("elapsed")
            or ""
        ),

        kickoff=(
            item.get("kickoffAt")
            or item.get("kickoff")
            or ""
        ),

        league=path(
            item,
            "competition",
            "name",
        ),

        raw=item,
    )


def fetch_openfoot():

    start = time.perf_counter()

    headers = {
        "Accept":
            "application/json"
    }

    if OPENFOOT_KEY:

        headers[
            "Authorization"
        ] = (
            f"Bearer {OPENFOOT_KEY}"
        )

    try:

        response, data = get_json(

            "https://openfootapi.com/v1/matches",

            headers=headers,
        )

        if response.status_code >= 400:

            return source_result(
                "OpenFoot",
                ok=False,
                status=response.status_code,
                error=str(data)[:500],
                elapsed=time.perf_counter() - start,
            )

        raw = []

        if isinstance(data, list):

            raw = data

        elif isinstance(data, dict):

            for key in (
                "data",
                "matches",
                "fixtures",
                "events",
                "results",
            ):

                if isinstance(
                    data.get(key),
                    list,
                ):

                    raw = data[key]
                    break

        events = []

        for item in raw:

            try:
                events.append(
                    normalize_openfoot(
                        item
                    )
                )

            except Exception:
                pass

        return source_result(
            "OpenFoot",
            events=events,
            ok=True,
            status=response.status_code,
            elapsed=time.perf_counter() - start,
        )

    except Exception as exc:

        return source_result(
            "OpenFoot",
            ok=False,
            error=str(exc),
            elapsed=time.perf_counter() - start,
        )


# ============================================================
# FONTES
# ============================================================

SOURCE_FUNCTIONS = [
    ("ESPN", fetch_espn),
    ("5Dollar", fetch_5dollar),
    ("OpenFoot", fetch_openfoot),
    ("FootballData", fetch_football_data),
    ("APIFootball", fetch_api_football),
    ("TheSportsDB", fetch_tsdb),
]


# ============================================================
# ESTATÍSTICAS
# ============================================================

def register_source(result):

    name = result["source"]

    stats = st.session_state.source_stats.setdefault(
        name,
        {
            "calls": 0,
            "ok": 0,
            "errors": 0,
            "last_status": None,
            "last_error": "",
            "last_ms": 0,
        },
    )

    stats["calls"] += 1

    stats["last_status"] = result.get(
        "status"
    )

    stats["last_error"] = result.get(
        "error",
        "",
    )

    if result.get("ok"):
        stats["ok"] += 1
    else:
        stats["errors"] += 1

    stats["last_ms"] = round(
        result.get("elapsed", 0) * 1000,
        1,
    )


# ============================================================
# DETECÇÃO DE GOL
# ============================================================

def detect_goals(events):

    detected = []

    for ev in events:

        cache_key = ev["id"]

        previous = (
            st.session_state.score_cache.get(
                cache_key
            )
        )

        current_home = ev[
            "home_score"
        ]

        current_away = ev[
            "away_score"
        ]

        if previous:

            old_home = previous[
                "home_score"
            ]

            old_away = previous[
                "away_score"
            ]

            changed = (
                current_home != old_home
                or
                current_away != old_away
            )

            goals_added = (
                current_home - old_home
                +
                current_away - old_away
            )

            if changed and goals_added > 0:

                detected.append(
                    {
                        "event": ev,
                        "old_score":
                            previous["score"],
                        "new_score":
                            ev["score"],
                    }
                )

        st.session_state.score_cache[
            cache_key
        ] = ev

    return detected


# ============================================================
# OPENROUTER
# ============================================================

def analyze_goal(goal):

    if not OPENROUTER_API_KEY:
        return "OpenRouter não configurado."

    ev = goal["event"]

    cache_key = (
        ev["id"],
        goal["new_score"],
    )

    cached = (
        st.session_state.analysis_cache.get(
            cache_key
        )
    )

    if cached:
        return cached

    prompt = (
        "Analise objetivamente um gol em uma "
        "partida de futebol.\n\n"
        f"Jogo: {ev['home']} x {ev['away']}\n"
        f"Placar anterior: {goal['old_score']}\n"
        f"Novo placar: {goal['new_score']}\n"
        f"Minuto: {ev.get('minute') or '-'}\n"
        f"Liga: {ev.get('league') or '-'}\n"
        f"Fonte: {ev['source']}\n\n"
        "Responda em português:\n"
        "1. Impacto do gol\n"
        "2. Cenário do jogo\n"
        "3. Mercados que merecem observação\n"
        "4. Riscos\n\n"
        "Não invente estatísticas e não trate "
        "qualquer cenário como garantia."
    )

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é um analista "
                    "estatístico de futebol."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }

    try:

        response = requests.post(

            "https://openrouter.ai/api/v1/chat/completions",

            headers={
                "Authorization":
                    f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type":
                    "application/json",
                "HTTP-Referer":
                    "https://streamlit.io",
                "X-Title":
                    "Football Scanner",
            },

            json=payload,

            timeout=OPENROUTER_TIMEOUT,
        )

        try:
            data = response.json()

        except Exception:
            data = {}

        if response.status_code >= 400:

            return (
                f"OpenRouter HTTP "
                f"{response.status_code}: "
                f"{str(data)[:300]}"
            )

        choices = (
            data.get("choices")
            or []
        )

        if not choices:
            return "OpenRouter não retornou resposta."

        message = (
            choices[0].get(
                "message"
            )
            or {}
        )

        answer = (
            message.get("content")
            or "Resposta vazia."
        )

        st.session_state.analysis_cache[
            cache_key
        ] = answer

        return answer

    except Exception as exc:

        return f"Erro OpenRouter: {exc}"


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN:
        return False, "Bot Telegram não configurado."

    if not TELEGRAM_CHAT_ID:
        return False, "Chat ID do Telegram não configurado."

    try:

        response = requests.post(

            (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_BOT_TOKEN}/"
                "sendMessage"
            ),

            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },

            timeout=10,
        )

        if response.status_code >= 400:
            return False, response.text[:300]

        return True, "OK"

    except Exception as exc:

        return False, str(exc)


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def run_cycle():

    cycle_start = time.perf_counter()

    results = []

    # TODAS AS FONTES AO MESMO TEMPO
    with ThreadPoolExecutor(
        max_workers=SOURCE_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                function
            ): name
            for name, function
            in SOURCE_FUNCTIONS
        }

        for future in as_completed(
            futures
        ):

            name = futures[future]

            try:

                result = future.result()

            except Exception as exc:

                result = source_result(
                    name,
                    ok=False,
                    error=str(exc),
                )

            register_source(result)

            results.append(result)

    events = []

    for result in results:

        events.extend(
            result.get(
                "events",
                []
            )
        )

    goals = detect_goals(
        events
    )

    ranking = sorted(
        events,
        key=lambda x:
            x["received_at"],
    )

    elapsed = (
        time.perf_counter()
        - cycle_start
    )

    st.session_state.last_cycle = {
        "time": agora(),
        "elapsed": elapsed,
        "events": len(events),
        "goals": len(goals),
    }

    for goal in goals:

        ev = goal["event"]

        goal_id = (
            f"{ev['id']}|"
            f"{goal['new_score']}"
        )

        if (
            goal_id
            in st.session_state.sent_goal_ids
        ):
            continue

        st.session_state.sent_goal_ids.add(
            goal_id
        )

        ai_text = ""

        if OPENROUTER_API_KEY:
            ai_text = analyze_goal(
                goal
            )

        telegram_status = ""

        if (
            TELEGRAM_BOT_TOKEN
            and TELEGRAM_CHAT_ID
        ):

            message = (
                "⚽ GOL DETECTADO\n\n"
                f"{ev['home']} "
                f"{goal['new_score']} "
                f"{ev['away']}\n"
                f"Fonte: {ev['source']}\n"
                f"Minuto: "
                f"{ev.get('minute') or '-'}"
            )

            if ai_text:
                message += (
                    "\n\n🤖 IA:\n"
                    + ai_text[:2000]
                )

            ok, tg_message = telegram_send(
                message
            )

            telegram_status = (
                "Enviado"
                if ok
                else tg_message
            )

        st.session_state.goal_history.insert(
            0,
            {
                "Hora": agora(),
                "Jogo":
                    f"{ev['home']} x "
                    f"{ev['away']}",
                "Placar":
                    goal["new_score"],
                "Fonte":
                    ev["source"],
                "Minuto":
                    ev.get("minute") or "-",
                "Telegram":
                    telegram_status,
            },
        )

    st.session_state.goal_history = (
        st.session_state.goal_history[:50]
    )

    return (
        results,
        events,
        goals,
        ranking,
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Configuração")

    intervalo = st.number_input(
        "Intervalo",
        min_value=MIN_INTERVAL,
        max_value=MAX_INTERVAL,
        value=DEFAULT_INTERVAL,
        step=1,
    )

    auto_refresh = st.checkbox(
        "Atualização automática",
        value=True,
    )

    st.divider()

    st.subheader("🔑 Fontes configuradas")

    source_keys = {
        "5Dollar":
            bool(FIVEDOLLAR_KEY),
        "OpenFoot":
            bool(OPENFOOT_KEY),
        "FootballData":
            bool(FOOTBALL_DATA_TOKEN),
        "API-Football":
            bool(API_FOOTBALL_KEY),
        "TheSportsDB":
            bool(THESPORTSDB_KEY),
        "OpenRouter":
            bool(OPENROUTER_API_KEY),
        "Telegram":
            bool(
                TELEGRAM_BOT_TOKEN
                and TELEGRAM_CHAT_ID
            ),
    }

    for name, active in source_keys.items():

        if active:
            st.write(
                f"🟢 {name}"
            )
        else:
            st.write(
                f"⚪ {name}"
            )

    st.divider()

    if (
        time.time()
        <
        st.session_state.espn_block_until
    ):

        remaining = int(
            st.session_state.espn_block_until
            - time.time()
        )

        st.warning(
            f"ESPN em cooldown: "
            f"{remaining}s"
        )

    if st.button(
        "🔄 Executar agora",
        use_container_width=True,
    ):

        st.rerun()


# ============================================================
# EXECUTAR
# ============================================================

results, events, goals, ranking = (
    run_cycle()
)


# ============================================================
# CABEÇALHO
# ============================================================

st.title(
    "⚽ Football Scanner"
)

st.caption(
    "Monitoramento simultâneo de "
    "fontes de futebol ao vivo"
)


# ============================================================
# MÉTRICAS
# ============================================================

ok_count = sum(
    1
    for result in results
    if result["ok"]
)

error_count = (
    len(results)
    - ok_count
)

cycle_time = (
    st.session_state.last_cycle["elapsed"]
    if st.session_state.last_cycle
    else 0
)

col1, col2, col3, col4, col5 = (
    st.columns(5)
)

with col1:
    st.metric(
        "Fontes OK",
        ok_count,
    )

with col2:
    st.metric(
        "Erros",
        error_count,
    )

with col3:
    st.metric(
        "Jogos",
        len(events),
    )

with col4:
    st.metric(
        "Gols novos",
        len(goals),
    )

with col5:
    st.metric(
        "Tempo",
        f"{cycle_time:.2f}s",
    )


# ============================================================
# GOLS
# ============================================================

st.subheader(
    "🚨 Gols detectados"
)

if not goals:

    st.info(
        "Nenhuma mudança de placar "
        "detectada neste ciclo."
    )

else:

    for goal in goals:

        ev = goal["event"]

        st.success(
            f"⚽ {ev['home']} "
            f"{goal['new_score']} "
            f"{ev['away']} | "
            f"Fonte: {ev['source']} | "
            f"Minuto: "
            f"{ev.get('minute') or '-'}"
        )

        if OPENROUTER_API_KEY:

            with st.expander(
                "🤖 Análise OpenRouter"
            ):

                st.write(
                    analyze_goal(
                        goal
                    )
                )


# ============================================================
# RANKING
# ============================================================

st.subheader(
    "🏁 Ranking de chegada das fontes"
)

st.caption(
    "Compara o instante absoluto em que "
    "cada resposta foi recebida pelo scanner."
)

if ranking:

    first_time = ranking[0][
        "received_at"
    ]

    rows = []

    for position, ev in enumerate(
        ranking[:100],
        start=1,
    ):

        difference = (
            ev["received_at"]
            - first_time
        ) * 1000

        rows.append(
            {
                "#": position,
                "Fonte": ev["source"],
                "Jogo":
                    f"{ev['home']} x "
                    f"{ev['away']}",
                "Placar":
                    ev["score"],
                "Diferença":
                    f"{difference:.0f} ms",
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "Nenhum jogo retornado."
    )


# ============================================================
# STATUS DAS FONTES
# ============================================================

st.subheader(
    "📡 Status das APIs"
)

status_rows = []

for result in sorted(
    results,
    key=lambda x:
        x["source"],
):

    status_rows.append(
        {
            "Fonte":
                result["source"],

            "Status":
                "🟢 OK"
                if result["ok"]
                else "🔴 ERRO",

            "HTTP":
                result.get(
                    "status"
                )
                or "-",

            "Jogos":
                len(
                    result.get(
                        "events",
                        [],
                    )
                ),

            "Tempo":
                f"{result.get('elapsed', 0) * 1000:.0f} ms",

            "Erro":
                result.get(
                    "error"
                )
                or "-",
        }
    )

st.dataframe(
    status_rows,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# JOGOS
# ============================================================

st.subheader(
    "🟢 Jogos monitorados"
)

if events:

    game_rows = []

    for ev in events:

        game_rows.append(
            {
                "Fonte":
                    ev["source"],

                "Casa":
                    ev["home"],

                "Placar":
                    ev["score"],

                "Fora":
                    ev["away"],

                "Minuto":
                    ev.get("minute")
                    or "-",

                "Status":
                    ev.get("status")
                    or "-",

                "Liga":
                    ev.get("league")
                    or "-",
            }
        )

    st.dataframe(
        game_rows,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "Nenhum jogo retornado pelas fontes."
    )


# ============================================================
# HISTÓRICO
# ============================================================

st.subheader(
    "📜 Histórico de gols"
)

if st.session_state.goal_history:

    st.dataframe(
        st.session_state.goal_history,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "Nenhum gol detectado nesta sessão."
    )


# ============================================================
# CONFIGURAÇÃO
# ============================================================

with st.expander(
    "🔐 Como configurar as chaves"
):

    st.code(
        """
FOOTBALL_DATA_API_TOKEN = "SUA_CHAVE"

FIVEDOLLAR_FOOTBALL_API_KEY = "SUA_CHAVE"

THESPORTSDB_API_KEY = "SUA_CHAVE"

OPENFOOT_API_KEY = "SUA_CHAVE"

API_FOOTBALL_KEY = "SUA_CHAVE"

OPENROUTER_API_KEY = "SUA_CHAVE"

OPENROUTER_MODEL = "openrouter/free"

TELEGRAM_BOT_TOKEN = "SEU_TOKEN"

TELEGRAM_CHAT_ID = "SEU_CHAT_ID"
""".strip(),
        language="toml",
    )

    st.write(
        "Configure essas variáveis em "
        "Settings → Secrets no Streamlit Cloud."
    )


# ============================================================
# RODAPÉ
# ============================================================

if st.session_state.last_cycle:

    ultima_hora = (
        st.session_state.last_cycle["time"]
    )

else:

    ultima_hora = agora()

st.caption(
    f"Último ciclo: {ultima_hora} | "
    f"Próxima atualização em {intervalo}s"
)


# ============================================================
# AUTO REFRESH
# ============================================================

if auto_refresh:

    time.sleep(
        int(intervalo)
    )

    st.rerun()
