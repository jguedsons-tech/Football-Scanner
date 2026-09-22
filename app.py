import os
import requests
import streamlit as st
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="⚽ IA Futebol",
    page_icon="⚽",
    layout="wide"
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"


# ============================================================
# SECRET
# ============================================================

def obter_secret(nome, padrao=""):

    try:
        valor = st.secrets.get(nome)

        if valor:
            return str(valor).strip()

    except Exception:
        pass

    valor = os.getenv(nome, "")

    if valor:
        return str(valor).strip()

    return padrao


OPENROUTER_API_KEY = obter_secret(
    "OPENROUTER_API_KEY"
)


# ============================================================
# MODELOS
# ============================================================

# IMPORTANTE:
# Você pode trocar essa lista pelos modelos gratuitos
# disponíveis atualmente na sua conta.

MODELOS_GRATUITOS = [
    "openrouter/free",
]


# ============================================================
# HEADERS
# ============================================================

def headers_openrouter():

    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "IA Futebol"
    }


# ============================================================
# TESTAR CHAVE
# ============================================================

def testar_chave():

    if not OPENROUTER_API_KEY:

        return False, "Chave não encontrada."

    try:

        resposta = requests.get(
            MODELS_URL,
            headers={
                "Authorization":
                    f"Bearer {OPENROUTER_API_KEY}"
            },
            timeout=30
        )

        if resposta.status_code == 200:

            return True, "Chave válida."

        try:
            erro = resposta.json()
        except:
            erro = resposta.text

        return False, (
            f"HTTP {resposta.status_code}\n"
            f"{erro}"
        )

    except Exception as e:

        return False, str(e)


# ============================================================
# TESTE DE GERAÇÃO
# ============================================================

def testar_geracao():

    if not OPENROUTER_API_KEY:

        return False, "Chave não encontrada."

    payload = {

        "model": "openrouter/free",

        "messages": [
            {
                "role": "user",
                "content": "Responda apenas: CONEXÃO OK"
            }
        ],

        "temperature": 0,

        "max_tokens": 20
    }

    try:

        resposta = requests.post(
            OPENROUTER_URL,
            headers=headers_openrouter(),
            json=payload,
            timeout=90
        )

        try:
            dados = resposta.json()
        except:
            dados = {}

        if resposta.status_code != 200:

            return False, (
                f"HTTP {resposta.status_code}\n\n"
                f"{dados if dados else resposta.text}"
            )

        choices = dados.get(
            "choices",
            []
        )

        if not choices:

            return False, (
                "A API respondeu, mas não retornou choices."
            )

        texto = choices[0] \
            .get("message", {}) \
            .get("content", "")

        return True, texto

    except Exception as e:

        return False, str(e)


# ============================================================
# CONSULTAR IA
# ============================================================

def consultar_ia(pergunta):

    if not OPENROUTER_API_KEY:

        return {
            "ok": False,
            "texto": "❌ Chave OpenRouter não encontrada."
        }


    system_prompt = """
Você é uma IA especializada em análise estatística
de futebol.

Responda em português brasileiro.

O usuário quer analisar partidas de futebol.

Analise:

- mandante
- visitante
- forma recente
- desempenho em casa
- desempenho fora
- gols
- posição
- confrontos diretos quando disponíveis
- contexto da competição

Faça uma estimativa:

1 = vitória do mandante
X = empate
2 = vitória do visitante

Informe:

Mandante: XX%
Empate: XX%
Visitante: XX%

Previsão: 1/X/2

Vencedor projetado:
TIME

IMPORTANTE:

As probabilidades são estimativas.

Não são garantias.

Não invente dados.

Se não houver informação suficiente,
diga "Não encontrado".

Também analise quando houver dados suficientes:

BTTS
Over 1.5
Over 2.5
Under 3.5

Para várias partidas, organize em tabela.
"""


    payload = {

        "model": "openrouter/free",

        "messages": [

            {
                "role": "system",
                "content": system_prompt
            },

            {
                "role": "user",
                "content": pergunta
            }

        ],

        "temperature": 0.15,

        "max_tokens": 12000
    }


    try:

        resposta = requests.post(

            OPENROUTER_URL,

            headers=headers_openrouter(),

            json=payload,

            timeout=180
        )


        try:

            dados = resposta.json()

        except:

            dados = {}


        # ====================================================
        # ERRO
        # ====================================================

        if resposta.status_code != 200:

            erro = dados.get(
                "error",
                resposta.text
            )

            return {
                "ok": False,
                "texto": (
                    f"❌ ERRO OPENROUTER\n\n"
                    f"HTTP {resposta.status_code}\n\n"
                    f"{erro}"
                )
            }


        # ====================================================
        # RESPOSTA
        # ====================================================

        choices = dados.get(
            "choices",
            []
        )

        if not choices:

            return {
                "ok": False,
                "texto": (
                    "❌ A IA não retornou resposta."
                )
            }


        message = choices[0].get(
            "message",
            {}
        )


        texto = message.get(
            "content",
            ""
        )


        if not texto:

            return {
                "ok": False,
                "texto": (
                    "❌ A resposta veio vazia.\n\n"
                    + str(message)
                )
            }


        return {
            "ok": True,
            "texto": texto
        }


    except requests.Timeout:

        return {
            "ok": False,
            "texto": (
                "⏱️ A OpenRouter demorou demais."
            )
        }


    except requests.RequestException as e:

        return {
            "ok": False,
            "texto": (
                f"❌ Erro de conexão:\n\n{e}"
            )
        }


    except Exception as e:

        return {
            "ok": False,
            "texto": (
                f"❌ Erro:\n\n{e}"
            )
        }


# ============================================================
# INTERFACE
# ============================================================

st.title("⚽ IA FUTEBOL")

st.subheader(
    "Análise de jogos e vencedores"
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Diagnóstico")


    if OPENROUTER_API_KEY:

        st.success(
            "🟢 Chave encontrada"
        )

    else:

        st.error(
            "🔴 Chave não encontrada"
        )


    st.divider()


    # --------------------------------------------------------
    # TESTE 1
    # --------------------------------------------------------

    if st.button(
        "1️⃣ Testar chave",
        use_container_width=True
    ):

        ok, mensagem = testar_chave()

        if ok:

            st.success(
                "🟢 " + mensagem
            )

        else:

            st.error(
                mensagem
            )


    # --------------------------------------------------------
    # TESTE 2
    # --------------------------------------------------------

    if st.button(
        "2️⃣ Testar geração",
        use_container_width=True
    ):

        with st.spinner(
            "Testando geração..."
        ):

            ok, mensagem = testar_geracao()

        if ok:

            st.success(
                "🟢 Geração funcionando"
            )

            st.code(
                mensagem
            )

        else:

            st.error(
                "🔴 Geração falhou"
            )

            st.code(
                mensagem
            )


    st.divider()

    st.write(
        "### Modelo"
    )

    st.code(
        "openrouter/free"
    )


# ============================================================
# DATA
# ============================================================

data_atual = datetime.now().strftime(
    "%d/%m/%Y"
)


# ============================================================
# BUSCA
# ============================================================

st.markdown(
    "## 🔎 Análise"
)


pergunta = st.text_area(

    "Digite o que deseja analisar",

    value=(
        f"Analise os jogos de futebol de hoje "
        f"({data_atual}). "
        "Para cada jogo disponível nos dados fornecidos, "
        "mostre mandante, visitante, previsão 1X2, "
        "probabilidades de mandante, empate e visitante, "
        "vencedor projetado e justificativa."
    ),

    height=200
)


# ============================================================
# BOTÃO
# ============================================================

if st.button(
    "🤖 ANALISAR",
    type="primary",
    use_container_width=True
):

    if not OPENROUTER_API_KEY:

        st.error(
            "Configure OPENROUTER_API_KEY."
        )

        st.stop()


    with st.spinner(
        "🤖 IA analisando..."
    ):

        resultado = consultar_ia(
            pergunta
        )


    st.divider()


    if resultado["ok"]:

        st.markdown(
            "## 🏆 RESULTADO"
        )

        st.markdown(
            resultado["texto"]
        )

    else:

        st.error(
            resultado["texto"]
        )


# ============================================================
# RODAPÉ
# ============================================================

st.divider()

st.caption(
    "⚠️ Probabilidades são estimativas e não garantem "
    "resultados."
)
