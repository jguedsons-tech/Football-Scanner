import os
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.util import spec_from_file_location, module_from_spec
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIGURAÇÃO
# ============================================================

SCANNER_FILE = os.getenv(
    "SCANNER_FILE",
    r"Texto colado(5).txt"
)

# Intervalo entre ciclos.
# 2 segundos é agressivo, mas leve o suficiente para um PC fraco.
POLL_INTERVAL = float(os.getenv("GOAL_POLL_INTERVAL", "2.0"))

# Timeout específico do monitor.
# As funções do scanner usam a variável TIMEOUT global.
FAST_TIMEOUT = float(os.getenv("GOAL_FAST_TIMEOUT", "4"))

BRT = ZoneInfo("America/Sao_Paulo")

# Telegram — opcional.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Se True, mostra também as atualizações no console.
CONSOLE_ALERT = True

# Som do Windows.
WINDOWS_BEEP = True


# ============================================================
# CARREGAR O SCANNER ORIGINAL
# ============================================================

def carregar_scanner():
    """
    Carrega o arquivo original sem executar o main() do Streamlit.
    O arquivo original só chama main() quando __name__ == '__main__',
    portanto a importação é segura.
    """
    caminho = os.path.abspath(SCANNER_FILE)

    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"Scanner não encontrado:\n{caminho}\n\n"
            "Defina SCANNER_FILE com o caminho completo do seu arquivo."
        )

    spec = spec_from_file_location("scanner_original", caminho)

    if spec is None or spec.loader is None:
        raise RuntimeError("Não foi possível carregar o scanner original.")

    scanner = module_from_spec(spec)
    spec.loader.exec_module(scanner)

    # O scanner original usa TIMEOUT no request_json().
    # Reduzimos somente para este monitor.
    scanner.TIMEOUT = FAST_TIMEOUT

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
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
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
        print(f"[TELEGRAM] erro: {exc}")
        return False


# ============================================================
# ALERTA LOCAL
# ============================================================

def alerta_local():
    if not WINDOWS_BEEP:
        return

    try:
        import winsound

        winsound.Beep(1200, 180)
        winsound.Beep(1500, 220)

    except Exception:
        pass


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def numero_score(valor):
    """
    Converte placar para inteiro.
    Retorna None quando a fonte não informou um placar válido.
    """
    if valor is None:
        return None

    try:
        return int(float(valor))
    except Exception:
        return None


def placar(evento):
    h = numero_score(evento.get("home_score"))
    a = numero_score(evento.get("away_score"))

    if h is None or a is None:
        return None

    return h, a


def chave_base(evento):
    """
    Identidade estável da partida.

    Prioridade:
      1. source + source_id
      2. IDs dos times
      3. nomes + liga
    """
    source = str(evento.get("source") or "").strip().lower()
    source_id = str(evento.get("source_id") or "").strip()

    if source_id:
        return f"{source}:{source_id}"

    home_id = str(evento.get("home_id") or "").strip()
    away_id = str(evento.get("away_id") or "").strip()

    if home_id or away_id:
        return f"teams:{home_id}:{away_id}"

    home = str(evento.get("home") or "").strip().lower()
    away = str(evento.get("away") or "").strip().lower()
    league = str(evento.get("league") or "").strip().lower()

    return f"name:{home}:{away}:{league}"


# ============================================================
# BUSCA RÁPIDA
# ============================================================

def buscar_tsdb():
    hoje = datetime.now(BRT).date()

    try:
        return [
            scanner.normalize_tsdb_event(ev)
            for ev in scanner.tsdb_day(hoje)
        ]
    except Exception as exc:
        print(f"[TheSportsDB] {exc}")
        return []


def buscar_football_data():
    hoje = datetime.now(BRT).date()

    if not scanner.FD_TOKEN:
        return []

    try:
        return [
            scanner.normalize_fd_event(ev)
            for ev in scanner.fd_matches(hoje, hoje)
        ]
    except Exception as exc:
        print(f"[football-data.org] {exc}")
        return []


def buscar_openfoot():
    if not scanner.OPENFOOT_TOKEN:
        return []

    try:
        resultado = []

        for ev in scanner.openfoot_matches():
            item = scanner.normalize_openfoot_event(ev)

            dt = scanner.parse_kickoff(
                item.get("kickoff")
            )

            if not dt or dt.date() == datetime.now(BRT).date():
                resultado.append(item)

        return resultado

    except Exception as exc:
        print(f"[OpenFoot] {exc}")
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
        print(f"[5Dollar] {exc}")
        return []


def carregar_eventos_rapido():
    """
    Diferente do load_global_events() original, as fontes são
    consultadas simultaneamente. Isso reduz a latência total
    do ciclo quando existem várias APIs configuradas.
    """
    funcoes = [
        ("TheSportsDB", buscar_tsdb),
        ("football-data.org", buscar_football_data),
        ("OpenFoot", buscar_openfoot),
        ("5Dollar", buscar_5dollar),
    ]

    bruto = []

    with ThreadPoolExecutor(
        max_workers=len(funcoes)
    ) as executor:

        futuros = {
            executor.submit(funcao): nome
            for nome, funcao in funcoes
        }

        for futuro in as_completed(futuros):
            nome = futuros[futuro]

            try:
                eventos = futuro.result()

                if eventos:
                    bruto.extend(eventos)

            except Exception as exc:
                print(f"[{nome}] erro: {exc}")

    # Usa a mesma lógica de merge/deduplicação do scanner original.
    try:
        return scanner.merge_events(bruto)
    except Exception as exc:
        print(f"[MERGE] {exc}")
        return bruto


# ============================================================
# FILTRAR PARTIDAS AO VIVO
# ============================================================

def esta_ao_vivo(evento):
    try:
        return scanner.classify_event(evento) == "live"
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
# MENSAGEM
# ============================================================

def mensagem_gol(evento, anterior, atual):
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

    home = evento.get("home") or "Mandante"
    away = evento.get("away") or "Visitante"

    league = evento.get("league") or "-"
    source = evento.get("source") or "-"

    agora = datetime.now(BRT).strftime("%H:%M:%S")

    texto = (
        f"⚽ {lado}\n\n"
        f"{home} {new_h} x {new_a} {away}\n\n"
        f"📊 Placar anterior: {old_h}-{old_a}\n"
        f"🔥 Gol detectado: +{gols}\n"
        f"🏆 Liga: {league}\n"
        f"📡 Fonte: {source}\n"
        f"🕐 Detecção: {agora} BRT"
    )

    return texto


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
            print("\n" + "=" * 60)
            print(texto)
            print("=" * 60 + "\n")

        alerta_local()

        if telegram_configurado():
            ok = enviar_telegram(texto)

            if ok:
                print("[TELEGRAM] alerta enviado.")

    def detectar(self, eventos):
        """
        Detecta somente aumento do placar.

        Isso evita alertar quando:
          - uma API corrige o placar;
          - uma partida muda de fonte;
          - o placar inicial já era 1-0;
          - a mesma atualização é recebida várias vezes.
        """

        vivos = [
            ev for ev in eventos
            if esta_ao_vivo(ev)
            and placar(ev) is not None
        ]

        self.ultima_quantidade_live = len(vivos)

        for evento in vivos:

            atual = placar(evento)

            if atual is None:
                continue

            chave = chave_base(evento)

            anterior = self.placares.get(chave)

            # Primeiro contato: apenas registra.
            # Não dispara alerta de gol que ocorreu antes do bot iniciar.
            if anterior is None:
                self.placares[chave] = atual
                continue

            old_total = anterior[0] + anterior[1]
            new_total = atual[0] + atual[1]

            # Nenhum gol novo.
            if new_total <= old_total:
                self.placares[chave] = atual
                continue

            # Garante que só notificamos cada mudança de placar uma vez.
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
                self.gols_notificados.add(assinatura)
                self.notificar(texto)

        # Limpa partidas antigas do dicionário para não crescer
        # indefinidamente durante vários dias de execução.
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
            self.placares.pop(chave, None)

    def ciclo(self):
        inicio = time.monotonic()

        eventos = carregar_eventos_rapido()

        self.detectar(eventos)

        duracao = time.monotonic() - inicio

        return len(eventos), duracao

    def iniciar(self):
        self.running = True

        print("=" * 60)
        print("⚽ BOT DE GOLS — MONITORAMENTO RÁPIDO")
        print("=" * 60)
        print(f"Intervalo: {POLL_INTERVAL:.1f}s")
        print(f"Timeout API: {FAST_TIMEOUT:.1f}s")
        print(
            "Telegram:",
            "CONFIGURADO" if telegram_configurado()
            else "não configurado"
        )
        print("=" * 60)

        # Carrega o placar inicial antes de começar a detectar.
        # Assim o bot não dispara falsos gols ao iniciar.
        primeiro = True

        while self.running:

            try:
                self.ciclos += 1

                quantidade, duracao = self.ciclo()

                agora = datetime.now(BRT).strftime(
                    "%H:%M:%S"
                )

                print(
                    f"[{agora}] "
                    f"ciclo={self.ciclos} | "
                    f"eventos={quantidade} | "
                    f"ao vivo={self.ultima_quantidade_live} | "
                    f"tempo={duracao:.2f}s"
                )

                # Se o ciclo demorou mais que o intervalo,
                # inicia o próximo imediatamente.
                espera = max(
                    0.1,
                    POLL_INTERVAL - duracao
                )

                time.sleep(espera)

            except KeyboardInterrupt:
                print("\nBot encerrado pelo usuário.")
                self.running = False

            except Exception as exc:
                print(
                    f"[ERRO MONITOR] {type(exc).__name__}: {exc}"
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
        print("Encerrado.")
