```python
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.util import spec_from_file_location, module_from_spec
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIGURAÇÃO
# ============================================================

# Pasta onde este app.py está localizado.
# Funciona tanto localmente quanto no Streamlit Cloud.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Arquivo do scanner original.
# O padrão agora é scanner.py, que deve estar no mesmo
# diretório deste app.py.
SCANNER_FILE = os.getenv(
    "SCANNER_FILE",
    os.path.join(BASE_DIR, "scanner.py")
)


# Intervalo entre ciclos
POLL_INTERVAL = float(
    os.getenv("GOAL_POLL_INTERVAL", "2.0")
)


# Timeout das APIs
FAST_TIMEOUT = float(
    os.getenv("GOAL_FAST_TIMEOUT", "4")
)


BRT = ZoneInfo("America/Sao_Paulo")


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
)


# ============================================================
# ALERTAS
# ============================================================

CONSOLE_ALERT = True

# No Streamlit Cloud não existe winsound.
# A função abaixo trata isso automaticamente.
WINDOWS_BEEP = True


# ============================================================
# CARREGAR O SCANNER ORIGINAL
# ============================================================

def carregar_scanner():

    caminho = os.path.abspath(SCANNER_FILE)

    print(
        f"[SCANNER] Procurando arquivo: {caminho}"
    )

    # --------------------------------------------------------
    # Verifica se o arquivo existe
    # --------------------------------------------------------

    if not os.path.isfile(caminho):

        try:
            arquivos = sorted(
                os.listdir(BASE_DIR)
            )

        except Exception:
            arquivos = []

        lista_arquivos = "\n".join(
            f"  - {arquivo}"
            for arquivo in arquivos
        )

        raise FileNotFoundError(
            "\n"
            "SCANNER NÃO ENCONTRADO\n"
            "======================\n\n"
            f"Caminho procurado:\n"
            f"{caminho}\n\n"
            "Arquivos encontrados no projeto:\n"
            f"{lista_arquivos}\n\n"
            "O arquivo scanner.py precisa estar "
            "no mesmo diretório do app.py."
        )

    # --------------------------------------------------------
    # Carrega scanner.py como módulo
    # --------------------------------------------------------

    spec = spec_from_file_location(
        "scanner_original",
        caminho
    )

    if spec is None:
        raise RuntimeError(
            f"Não foi possível criar o módulo para:\n{caminho}"
        )

    if spec.loader is None:
        raise RuntimeError(
            f"Loader inválido para:\n{caminho}"
        )

    scanner = module_from_spec(spec)

    # Executa o scanner original
    spec.loader.exec_module(scanner)

    # --------------------------------------------------------
    # Ajusta TIMEOUT
    # --------------------------------------------------------

    scanner.TIMEOUT = FAST_TIMEOUT

    print(
        f"[SCANNER] Carregado com sucesso: {caminho}"
    )

    return scanner


scanner = carregar_scanner()


# ============================================================
# TELEGRAM
# ============================================================

def telegram_configurado():

    return bool(
        TELEGRAM_BOT_TOKEN.strip()
        and TELEGRAM_CHAT_ID.strip()
    )


def enviar_telegram(texto):

    if not telegram_configurado():
        return False

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}"
        "/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texto,
        "disable_web_page_preview": True,
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=5
        )

        return response.ok

    except Exception as exc:

        print(
            f"[TELEGRAM] erro: {exc}"
        )

        return False


# ============================================================
# ALERTA LOCAL
# ============================================================

def alerta_local():

    if not WINDOWS_BEEP:
        return

    try:

        import winsound

        winsound.Beep(
            1200,
            180
        )

        winsound.Beep(
            1500,
            220
        )

    except Exception:
        # Streamlit Cloud/Linux não possui winsound.
        pass


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def numero_score(valor):

    if valor is None:
        return None

    try:
        return int(float(valor))

    except Exception:
        return None


def placar(evento):

    h = numero_score(
        evento.get("home_score")
    )

    a = numero_score(
        evento.get("away_score")
    )

    if h is None or a is None:
        return None

    return h, a


def chave_base(evento):

    source = str(
        evento.get("source") or ""
    ).strip().lower()

    source_id = str(
        evento.get("source_id") or ""
    ).strip()

    if source_id:
        return (
            f"{source}:{source_id}"
        )

    home_id = str(
        evento.get("home_id") or ""
    ).strip()

    away_id = str(
        evento.get("away_id") or ""
    ).strip()

    if home_id or away_id:
        return (
            f"teams:{home_id}:{away_id}"
        )

    home = str(
        evento.get("home") or ""
    ).strip().lower()

    away = str(
        evento.get("away") or ""
    ).strip().lower()

    league = str(
        evento.get("league") or ""
    ).strip().lower()

    return (
        f"name:{home}:{away}:{league}"
    )


# ============================================================
# BUSCAS
# ============================================================

def buscar_tsdb():

    hoje = datetime.now(BRT).date()

    try:

        return [
            scanner.normalize_tsdb_event(ev)
            for ev in scanner.tsdb_day(hoje)
        ]

    except Exception as exc:

        print(
            f"[TheSportsDB] {exc}"
        )

        return []


def buscar_football_data():

    hoje = datetime.now(BRT).date()

    if not scanner.FD_TOKEN:
        return []

    try:

        return [
            scanner.normalize_fd_event(ev)
            for ev in scanner.fd_matches(
                hoje,
                hoje
            )
        ]

    except Exception as exc:

        print(
            f"[football-data.org] {exc}"
        )

        return []


def buscar_openfoot():

    if not scanner.OPENFOOT_TOKEN:
        return []

    try:

        resultado = []

        for ev in scanner.openfoot_matches():

            item = (
                scanner.normalize_openfoot_event(ev)
            )

            dt = scanner.parse_kickoff(
                item.get("kickoff")
            )

            if (
                not dt
                or dt.date()
                == datetime.now(BRT).date()
            ):
                resultado.append(item)

        return resultado

    except Exception as exc:

        print(
            f"[OpenFoot] {exc}"
        )

        return []


def buscar_5dollar():

    hoje = datetime.now(BRT).date()

    if not scanner.FD5_TOKEN:
        return []

    try:

        return [
            scanner.normalize_fd5_event(ev)
            for ev in scanner.fd5_day(hoje)
        ]

    except Exception as exc:

        print(
            f"[5Dollar] {exc}"
        )

        return []


# ============================================================
# CARREGAR EVENTOS
# ============================================================

def carregar_eventos_rapido():

    funcoes = [
        (
            "TheSportsDB",
            buscar_tsdb
        ),
        (
            "football-data.org",
            buscar_football_data
        ),
        (
            "OpenFoot",
            buscar_openfoot
        ),
        (
            "5Dollar",
            buscar_5dollar
        ),
    ]

    bruto = []

    with ThreadPoolExecutor(
        max_workers=len(funcoes)
    ) as executor:

        futuros = {
            executor.submit(
                funcao
            ): nome

            for nome, funcao in funcoes
        }

        for futuro in as_completed(
            futuros
        ):

            nome = futuros[futuro]

            try:

                eventos = futuro.result()

                if eventos:
                    bruto.extend(eventos)

            except Exception as exc:

                print(
                    f"[{nome}] erro: {exc}"
                )

    try:

        return scanner.merge_events(
            bruto
        )

    except Exception as exc:

        print(
            f"[MERGE] {exc}"
        )

        return bruto


# ============================================================
# AO VIVO
# ============================================================

def esta_ao_vivo(evento):

    try:

        return (
            scanner.classify_event(evento)
            == "live"
        )

    except Exception:

        status = str(
            evento.get("status") or ""
        ).strip().upper()

        return status in {
            "LIVE",
            "IN_PLAY",
            "INPLAY",
            "1H",
            "2H",
            "HT",
            "ET",
            "P",
            "HALF_TIME",
            "SECOND_HALF",
        }


# ============================================================
# MENSAGEM DE GOL
# ============================================================

def mensagem_gol(
    evento,
    anterior,
    atual
):

    old_h, old_a = anterior
    new_h, new_a = atual

    delta_h = new_h - old_h
    delta_a = new_a - old_a

    if delta_h > 0 and delta_a == 0:

        lado = "🏠 GOL DO MANDANTE"
        gols = delta_h

    elif delta_a > 0 and delta_h == 0:

        lado = "✈️ GOL DO VISITANTE"
        gols = delta_a

    elif delta_h > 0 or delta_a > 0:

        lado = "⚽ GOL"
        gols = delta_h + delta_a

    else:

        return None

    home = (
        evento.get("home")
        or "Mandante"
    )

    away = (
        evento.get("away")
        or "Visitante"
    )

    league = (
        evento.get("league")
        or "-"
    )

    source = (
        evento.get("source")
        or "-"
    )

    agora = datetime.now(
        BRT
    ).strftime("%H:%M:%S")

    return (
        f"⚽ {lado}\n\n"
        f"{home} {new_h} x {new_a} {away}\n\n"
        f"📊 Placar anterior: "
        f"{old_h}-{old_a}\n"
        f"🔥 Gol detectado: +{gols}\n"
        f"🏆 Liga: {league}\n"
        f"📡 Fonte: {source}\n"
        f"🕐 Detecção: {agora} BRT"
    )


# ============================================================
# MONITOR
# ============================================================

class MonitorGols:

    def __init__(self):

        self.placares = {}

        self.gols_notificados = set()

        self.running = False

        self.ciclos = 0

        self.ultima_quantidade_live = 0

    def notificar(self, texto):

        if CONSOLE_ALERT:

            print(
                "\n"
                + "=" * 60
            )

            print(texto)

            print(
                "=" * 60
                + "\n"
            )

        alerta_local()

        if telegram_configurado():

            ok = enviar_telegram(
                texto
            )

            if ok:
                print(
                    "[TELEGRAM] alerta enviado."
                )

    def detectar(self, eventos):

        vivos = [
            ev
            for ev in eventos
            if (
                esta_ao_vivo(ev)
                and placar(ev) is not None
            )
        ]

        self.ultima_quantidade_live = (
            len(vivos)
        )

        for evento in vivos:

            atual = placar(evento)

            if atual is None:
                continue

            chave = chave_base(
                evento
            )

            anterior = self.placares.get(
                chave
            )

            if anterior is None:

                self.placares[chave] = atual

                continue

            old_total = (
                anterior[0]
                + anterior[1]
            )

            new_total = (
                atual[0]
                + atual[1]
            )

            if new_total <= old_total:

                self.placares[chave] = atual

                continue

            assinatura = (
                chave,
                atual[0],
                atual[1],
            )

            self.placares[chave] = atual

            if assinatura in self.gols_notificados:
                continue

            texto = mensagem_gol(
                evento,
                anterior,
                atual
            )

            if texto:

                self.gols_notificados.add(
                    assinatura
                )

                self.notificar(
                    texto
                )

        chaves_vivas = {
            chave_base(ev)
            for ev in vivos
        }

        antigas = [
            chave
            for chave in self.placares
            if chave not in chaves_vivas
        ]

        for chave in antigas:

            self.placares.pop(
                chave,
                None
            )

    def ciclo(self):

        inicio = time.monotonic()

        eventos = (
            carregar_eventos_rapido()
        )

        self.detectar(eventos)

        duracao = (
            time.monotonic()
            - inicio
        )

        return (
            len(eventos),
            duracao
        )

    def iniciar(self):

        self.running = True

        print("=" * 60)
        print(
            "⚽ BOT DE GOLS — "
            "MONITORAMENTO RÁPIDO"
        )
        print("=" * 60)

        print(
            f"Intervalo: "
            f"{POLL_INTERVAL:.1f}s"
        )

        print(
            f"Timeout API: "
            f"{FAST_TIMEOUT:.1f}s"
        )

        print(
            "Telegram:",
            (
                "CONFIGURADO"
                if telegram_configurado()
                else "não configurado"
            )
        )

        print("=" * 60)

        while self.running:

            try:

                self.ciclos += 1

                quantidade, duracao = (
                    self.ciclo()
                )

                agora = datetime.now(
                    BRT
                ).strftime("%H:%M:%S")

                print(
                    f"[{agora}] "
                    f"ciclo={self.ciclos} | "
                    f"eventos={quantidade} | "
                    f"ao vivo="
                    f"{self.ultima_quantidade_live} | "
                    f"tempo={duracao:.2f}s"
                )

                espera = max(
                    0.1,
                    POLL_INTERVAL - duracao
                )

                time.sleep(espera)

            except KeyboardInterrupt:

                print(
                    "\nBot encerrado."
                )

                self.running = False

            except Exception as exc:

                print(
                    "[ERRO MONITOR] "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                time.sleep(1)

    def parar(self):

        self.running = False


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    bot = MonitorGols()

    try:

        bot.iniciar()

    except KeyboardInterrupt:

        bot.parar()

        print(
            "Encerrado."
        )
```
