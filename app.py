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


# ============================================================
# LER SECRETS DO STREAMLIT
# ============================================================

def obter_secret(nome, padrao=""):

    # Primeiro tenta Streamlit Secrets
    try:
        valor = st.secrets.get(nome, "")
        if valor:
            return str(valor).strip()
    except Exception:
        pass

    # Depois tenta variável de ambiente
    valor = os.getenv(nome, padrao)

    if valor:
        return str(valor).strip()

    return padrao


OPENROUTER_API_KEY = obter_secret(
    "OPENROUTER_API_KEY"
)

OPENROUTER_MODEL = obter_secret(
    "OPENROUTER_MODEL",
    "openrouter/free"
)


# ============================================================
# FUNÇÃO PARA TESTAR A CHAVE
# ============================================================

def testar_openrouter():

    if not OPENROUTER_API_KEY:
        return False, "OPENROUTER_API_KEY não encontrada."

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    try:

        resposta = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=30
        )

        if resposta.status_code == 200:
            return True, "OpenRouter conectado."

        try:
            erro = resposta.json()
        except Exception:
            erro = resposta.text

        return False, f"HTTP {resposta.status_code}: {erro}"

    except Exception as e:

        return False, str(e)


# ============================================================
# CONSULTAR IA
# ============================================================

def consultar_ia(pergunta):

    if not OPENROUTER_API_KEY:

        return {
            "ok": False,
            "texto": (
                "❌ OPENROUTER_API_KEY não encontrada.\n\n"
                "Configure a chave em Streamlit Cloud → "
                "Settings → Secrets."
            )
        }

    system_prompt = """
Você é uma IA especializada em futebol e pesquisa
estatística de partidas.

RESPONDA SEMPRE EM PORTUGUÊS BRASILEIRO.

============================================================
OBJETIVO
============================================================

O usuário quer encontrar jogos de futebol e analisar
os possíveis vencedores.

Quando o usuário pedir jogos de hoje ou de uma data:

1. PESQUISE A WEB.
2. Procure o maior número possível de partidas.
3. Considere diferentes países e competições.
4. Não fique limitado às principais ligas.
5. Não invente partidas.

Procure:

- campeonatos nacionais
- copas nacionais
- competições continentais
- competições internacionais
- divisões inferiores
- futebol feminino quando relevante
- categorias disponíveis nas fontes pesquisadas

============================================================
DADOS DE CADA JOGO
============================================================

Para cada partida encontrada, tente obter:

- horário
- competição
- país
- mandante
- visitante
- forma recente
- posição na competição
- gols marcados
- gols sofridos
- desempenho em casa
- desempenho fora
- confrontos diretos
- notícias recentes
- desfalques
- contexto da partida

Não invente nenhum desses dados.

Se não encontrar:

"Não encontrado."

============================================================
PREVISÃO 1X2
============================================================

Analise:

1 = vitória do mandante

X = empate

2 = vitória do visitante

Para cada jogo informe:

Mandante: XX%
Empate: XX%
Visitante: XX%

Depois:

Vencedor projetado:
TIME

A porcentagem é uma ESTIMATIVA da análise e não uma
garantia de resultado.

============================================================
FORMATO
============================================================

Comece com:

⚽ JOGOS DE HOJE

Depois uma tabela:

| Horário | Competição | Jogo | Previsão | Probabilidade |
|---------|------------|------|----------|---------------|

Exemplo:

| 19:00 | Campeonato | Time A x Time B | 1 | 72% |

Depois detalhe os jogos.

============================================================
VENCEDORES
============================================================

Depois da lista completa, crie:

🔥 VENCEDORES PROJETADOS

Mostre os jogos onde a análise encontrou maior
probabilidade de vitória.

Formato:

🏆 Time A
🆚 Time B

Previsão: 1
Probabilidade: 74%

Justificativa:
...

============================================================
EMPATES
============================================================

Crie também:

🤝 POSSÍVEIS EMPATES

Liste os jogos em que X apresentar probabilidade
relevante.

============================================================
OUTROS MERCADOS
============================================================

Quando houver dados suficientes, analise também:

BTTS
Over 1.5
Over 2.5
Under 3.5

Mas a previsão principal deve continuar sendo 1X2.

============================================================
IMPORTANTE
============================================================

Não invente:

- jogos
- horários
- resultados
- estatísticas
- odds
- jogadores
- desfalques
- probabilidades

Diferencie:

DADOS ENCONTRADOS
de
ESTIMATIVAS DA IA.

Se não for possível confirmar todas as partidas do dia,
informe:

"A lista depende da cobertura das fontes pesquisadas e
pode não representar todas as partidas existentes."

============================================================
FONTES
============================================================

Quando pesquisar a web, utilize fontes atuais e confiáveis.

Inclua as fontes relevantes quando possível.

============================================================
"""

    payload = {

        "model": OPENROUTER_MODEL,

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

        # ====================================================
        # WEB SEARCH
        # ====================================================

        "plugins": [
            {
                "id": "web",
                "max_results": 10
            }
        ],

        "temperature": 0.15,

        "max_tokens": 12000
    }

    headers = {

        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            "https://github.com/",

        "X-Title":
            "IA Futebol Jogos do Dia"
    }

    try:

        resposta = requests.post(

            OPENROUTER_URL,

            headers=headers,

            json=payload,

            timeout=180
        )

        # ====================================================
        # ERRO
        # ====================================================

        if resposta.status_code != 200:

            try:
                erro = resposta.json()
            except Exception:
                erro = resposta.text

            return {
                "ok": False,
                "texto": (
                    f"❌ ERRO OPENROUTER "
                    f"{resposta.status_code}\n\n"
                    f"{erro}"
                )
            }

        # ====================================================
        # RESPOSTA
        # ====================================================

        dados = resposta.json()

        escolhas = dados.get(
            "choices",
            []
        )

        if not escolhas:

            return {
                "ok": False,
                "texto": (
                    "❌ A OpenRouter não retornou "
                    "nenhuma resposta."
                )
            }

        mensagem = escolhas[0].get(
            "message",
            {}
        )

        texto = mensagem.get(
            "content",
            ""
        )

        if not texto:

            return {
                "ok": False,
                "texto": (
                    "❌ A IA retornou uma resposta vazia.\n\n"
                    + str(mensagem)
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
                "⏱️ A consulta demorou mais de "
                "180 segundos."
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
                f"❌ Erro inesperado:\n\n{e}"
            )
        }


# ============================================================
# INTERFACE
# ============================================================

st.title("⚽ IA FUTEBOL")

st.subheader(
    "🔎 Todos os jogos do dia + vencedores"
)

st.caption(
    "Pesquisa e análise realizadas pela IA através da web."
)


# ============================================================
# STATUS
# ============================================================

with st.sidebar:

    st.header("⚙️ Status")

    if OPENROUTER_API_KEY:

        st.success(
            "🟢 Chave OpenRouter encontrada"
        )

        if st.button(
            "🔌 Testar conexão",
            use_container_width=True
        ):

            ok, mensagem = testar_openrouter()

            if ok:
                st.success(
                    "🟢 " + mensagem
                )
            else:
                st.error(
                    "🔴 " + mensagem
                )

    else:

        st.error(
            "🔴 Chave não encontrada"
        )

    st.divider()

    st.write("### Modelo")

    st.code(
        OPENROUTER_MODEL
    )

    st.divider()

    st.write(
        "### O bot pesquisa"
    )

    st.write(
        """
⚽ Jogos do dia

🌎 Vários países

🏆 Competições

🕐 Horários

🏠 Mandante

✈️ Visitante

🏆 Vencedor

📊 Probabilidades

🤝 Empates

⚽ Gols

🎯 BTTS

📈 Over/Under
"""
    )


# ============================================================
# DATA
# ============================================================

data_atual = datetime.now().strftime(
    "%d/%m/%Y"
)


# ============================================================
# CAMPO DE PESQUISA
# ============================================================

st.markdown(
    "## 🔎 Pesquisa"
)

pergunta = st.text_area(

    "Digite sua pesquisa",

    value=(
        f"Pesquise TODOS os jogos de futebol de hoje "
        f"({data_atual}). "
        "Procure o maior número possível de jogos "
        "em diferentes países e competições. "
        "Traga horário, competição, mandante, visitante "
        "e faça uma análise 1X2 para cada partida. "
        "Depois mostre os vencedores projetados e suas "
        "probabilidades."
    ),

    height=220
)


# ============================================================
# BOTÕES
# ============================================================

col1, col2 = st.columns(2)


with col1:

    buscar_todos = st.button(

        "🔎 BUSCAR TODOS OS JOGOS",

        type="primary",

        use_container_width=True
    )


with col2:

    buscar_vencedores = st.button(

        "🏆 BUSCAR VENCEDORES",

        use_container_width=True
    )


# ============================================================
# TODOS OS JOGOS
# ============================================================

if buscar_todos:

    if not OPENROUTER_API_KEY:

        st.error(
            "❌ Configure OPENROUTER_API_KEY "
            "nos Secrets do Streamlit."
        )

    else:

        with st.spinner(
            "🌐 Pesquisando jogos na web..."
        ):

            resultado = consultar_ia(
                pergunta
            )

        st.divider()

        if resultado["ok"]:

            st.markdown(
                "## ⚽ JOGOS ENCONTRADOS"
            )

            st.markdown(
                resultado["texto"]
            )

        else:

            st.error(
                resultado["texto"]
            )


# ============================================================
# SOMENTE VENCEDORES
# ============================================================

if buscar_vencedores:

    pergunta_vencedores = f"""

Pesquise na web TODOS os jogos de futebol de hoje
({data_atual}) que conseguir encontrar.

Procure diferentes países e competições.

Para cada jogo encontrado:

- horário
- competição
- mandante
- visitante
- probabilidade mandante
- probabilidade empate
- probabilidade visitante
- vencedor projetado

Depois mostre:

🔥 VENCEDORES PROJETADOS

Organize:

| Horário | Competição | Jogo | Vencedor | Probabilidade |

Inclua somente análises em que exista uma indicação
estatística de vitória.

Depois explique brevemente os principais dados que
sustentam cada previsão.

Também mostre:

🤝 POSSÍVEIS EMPATES

⚠️ JOGOS EQUILIBRADOS

Não invente dados.

As probabilidades são estimativas e não garantias.

Informe as fontes pesquisadas quando possível.
"""

    if not OPENROUTER_API_KEY:

        st.error(
            "❌ Configure OPENROUTER_API_KEY "
            "nos Secrets do Streamlit."
        )

    else:

        with st.spinner(
            "🏆 Pesquisando vencedores..."
        ):

            resultado = consultar_ia(
                pergunta_vencedores
            )

        st.divider()

        if resultado["ok"]:

            st.markdown(
                "## 🏆 VENCEDORES DO DIA"
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
    "⚠️ As probabilidades são estimativas estatísticas. "
    "Não representam garantia de resultado."
)
