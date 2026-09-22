import os
import requests
import streamlit as st

# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Busca IA Gratuita",
    page_icon="🤖",
    layout="wide"
)

API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

# ============================================================
# FUNÇÃO DA IA
# ============================================================

def buscar_ia(pergunta):

    if not API_KEY:
        return "❌ OPENROUTER_API_KEY não configurada."

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://scanner-football-2.streamlit.app",
        "X-Title": "Busca IA Gratuita"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": """
Você é uma IA de pesquisa e análise.

Responda em português brasileiro.

Seja objetiva, organizada e explique os pontos
importantes da pergunta do usuário.
"""
            },
            {
                "role": "user",
                "content": pergunta
            }
        ],
        "temperature": 0.2,
        "max_tokens": 3000
    }

    try:

        resposta = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90
        )

        if resposta.status_code != 200:

            return (
                f"❌ Erro HTTP {resposta.status_code}\n\n"
                f"{resposta.text}"
            )

        dados = resposta.json()

        return dados["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:

        return "⏱️ Tempo limite excedido."

    except requests.exceptions.RequestException as e:

        return f"❌ Erro de conexão: {e}"

    except Exception as e:

        return f"❌ Erro: {e}"


# ============================================================
# INTERFACE
# ============================================================

st.title("🤖 Busca IA Gratuita")

st.caption(
    "Pesquisa e análise utilizando OpenRouter"
)

# ============================================================
# STATUS
# ============================================================

with st.sidebar:

    st.header("⚙️ Configuração")

    if API_KEY:

        st.success("🟢 OpenRouter conectado")

    else:

        st.error("🔴 OpenRouter não configurado")

    st.write("Modelo:")
    st.code(MODEL)

# ============================================================
# CAMPO DE BUSCA
# ============================================================

pergunta = st.text_area(
    "🔎 O que você quer pesquisar?",
    placeholder=(
        "Exemplo:\n"
        "Analise Juventus x Inter de Milão\n\n"
        "ou\n\n"
        "Quais são os principais acontecimentos "
        "econômicos desta semana?"
    ),
    height=150
)

# ============================================================
# BOTÃO
# ============================================================

if st.button(
    "🤖 Consultar IA",
    type="primary",
    use_container_width=True
):

    if not pergunta.strip():

        st.warning("Digite uma pergunta.")

    else:

        with st.spinner("Consultando a IA..."):

            resposta = buscar_ia(pergunta)

        st.subheader("📊 Resposta")

        st.markdown(resposta)

# ============================================================
# INFORMAÇÕES
# ============================================================

st.divider()

st.caption(
    "Modelo utilizado: openrouter/free"
)
