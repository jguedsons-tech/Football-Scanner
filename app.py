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
# LER CHAVE
# ============================================================

def obter_secret(nome, padrao=""):

    try:
        valor = st.secrets.get(nome)

        if valor:
            return str(valor).strip()

    except Exception:
        pass

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
# TESTAR OPENROUTER
# ============================================================

def testar_openrouter():

    if not OPENROUTER_API_KEY:

        return False, "Chave não encontrada."

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    try:

        r = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=30
        )

        if r.status_code == 200:

            return True, "OpenRouter conectado."

        try:
            erro = r.json()
        except:
            erro = r.text

        return False, f"HTTP {r.status_code}: {erro}"

    except Exception as e:

        return False, str(e)


# ============================================================
# BUSCA WEB
# ============================================================

def buscar_web(consulta):

    """
    Usa o mecanismo de busca do próprio OpenRouter.

    NÃO usa:
    - TheSportsDB
    - football-data.org
    - OpenFoot
    - 5DollarFootballAPI
    """

    if not OPENROUTER_API_KEY:

        return []

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "IA Futebol"
    }

    payload = {

        "model": "openai/gpt-4o-mini",

        "messages": [
            {
                "role": "user",
                "content": consulta
            }
        ],

        "plugins": [
            {
                "id": "web",
                "max_results": 10
            }
        ],

        "temperature": 0,

        "max_tokens": 6000
    }

    try:

        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120
        )

        if r.status_code != 200:

            return [{
                "erro": r.text
            }]

        data = r.json()

        choices = data.get(
            "choices",
            []
        )

        if not choices:

            return []

        message = choices[0].get(
            "message",
            {}
        )

        texto = message.get(
            "content",
            ""
        )

        if not texto:

            return []

        return [{
            "texto": texto
        }]

    except Exception as e:

        return [{
            "erro": str(e)
        }]


# ============================================================
# IA ANALISTA
# ============================================================

def analisar_com_ia(pergunta, dados_web):

    if not OPENROUTER_API_KEY:

        return {
            "ok": False,
            "texto": "❌ Chave OpenRouter não encontrada."
        }

    contexto = ""

    for item in dados_web:

        if "texto" in item:

            contexto += "\n\n"
            contexto += item["texto"]

        elif "erro" in item:

            contexto += "\n\nERRO DE PESQUISA:\n"
            contexto += item["erro"]


    # ========================================================
    # PROMPT
    # ========================================================

    system_prompt = """
Você é um ANALISTA PROFISSIONAL DE FUTEBOL.

Responda sempre em português brasileiro.

Você receberá resultados de pesquisa da internet.

Sua tarefa é transformar esses dados em uma análise
estatística organizada.

============================================================
OBJETIVO
============================================================

Encontrar:

- jogos do dia
- vencedores projetados
- empates possíveis
- probabilidades
- análise 1X2
- gols
- BTTS
- Over/Under

============================================================
1X2
============================================================

1 = vitória do mandante

X = empate

2 = vitória do visitante

Para cada jogo:

Mandante: XX%
Empate: XX%
Visitante: XX%

Previsão:

1
X
ou
2

============================================================
FORMATO
============================================================

Comece com:

# ⚽ JOGOS ENCONTRADOS

Depois:

| Horário | Competição | Jogo | Previsão | Probabilidade |
|---|---|---|---|---|

Depois faça uma análise de cada partida.

============================================================
VENCEDORES
============================================================

Depois:

# 🏆 VENCEDORES PROJETADOS

Liste os times que apresentarem maior probabilidade
estatística de vitória.

Formato:

🏆 TIME

🆚 Adversário

Previsão: 1

Probabilidade: 72%

Justificativa:
...

============================================================
EMPATES
============================================================

Depois:

# 🤝 POSSÍVEIS EMPATES

Mostre os jogos onde X tenha probabilidade relevante.

============================================================
JOGOS EQUILIBRADOS
============================================================

Depois:

# ⚠️ JOGOS EQUILIBRADOS

Mostre partidas onde as probabilidades estejam próximas.

============================================================
OUTROS MERCADOS
============================================================

Quando houver dados suficientes:

BTTS
OVER 1.5
OVER 2.5
UNDER 3.5

============================================================
REGRAS
============================================================

NÃO invente:

- jogos
- horários
- resultados
- estatísticas
- jogadores
- desfalques
- odds

Se um dado não estiver disponível:

"Não encontrado."

As probabilidades são estimativas.

Nunca diga que uma aposta é garantida.

============================================================
"""

    user_prompt = f"""
{pergunta}

============================================================
DADOS ENCONTRADOS NA PESQUISA WEB
============================================================

{contexto}

============================================================

Com base nos dados acima:

1. Organize todos os jogos encontrados.
2. Identifique mandante e visitante.
3. Analise 1X2.
4. Calcule uma estimativa de probabilidade.
5. Mostre os vencedores projetados.
6. Mostre possíveis empates.
7. Mostre jogos equilibrados.
8. Não invente informações.
"""

    headers = {

        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            "https://github.com/",

        "X-Title":
            "IA Futebol"
    }

    payload = {

        "model": OPENROUTER_MODEL,

        "messages": [

            {
                "role": "system",
                "content": system_prompt
            },

            {
                "role": "user",
                "content": user_prompt
            }

        ],

        "temperature": 0.15,

        "max_tokens": 12000
    }

    try:

        r = requests.post(

            OPENROUTER_URL,

            headers=headers,

            json=payload,

            timeout=180
        )

        # ====================================================
        # ERRO
        # ====================================================

        if r.status_code != 200:

            try:
                erro = r.json()
            except:
                erro = r.text

            return {
                "ok": False,
                "texto": (
                    f"❌ ERRO NA ANÁLISE\n\n"
                    f"HTTP {r.status_code}\n\n"
                    f"{erro}"
                )
            }

        data = r.json()

        choices = data.get(
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

        texto = choices[0] \
            .get("message", {}) \
            .get("content", "")

        if not texto:

            return {
                "ok": False,
                "texto": (
                    "❌ Resposta vazia da IA."
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
                "⏱️ A análise demorou demais."
            )
        }

    except Exception as e:

        return {
            "ok": False,
            "texto": f"❌ {e}"
        }


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "⚽ IA FUTEBOL"
)

st.subheader(
    "🔎 Jogos do dia + vencedores"
)

st.caption(
    "Busca web + análise por IA. "
    "Sem APIs de futebol."
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Status")

    if OPENROUTER_API_KEY:

        st.success(
            "🟢 Chave OpenRouter encontrada"
        )

    else:

        st.error(
            "🔴 Chave não encontrada"
        )

    if st.button(
        "🔌 Testar conexão",
        use_container_width=True
    ):

        ok, msg = testar_openrouter()

        if ok:

            st.success(
                "🟢 " + msg
            )

        else:

            st.error(
                "🔴 " + msg
            )

    st.divider()

    st.write("Modelo da análise:")

    st.code(
        OPENROUTER_MODEL
    )

    st.divider()

    st.write(
        """
O sistema faz:

🌐 Busca na web

↓

⚽ Lista de jogos

↓

📊 Análise estatística

↓

1X2

↓

🏆 Vencedores

↓

🤝 Empates

↓

⚠️ Jogos equilibrados
"""
    )


# ============================================================
# DATA
# ============================================================

data_atual = datetime.now().strftime(
    "%d/%m/%Y"
)


# ============================================================
# PESQUISA
# ============================================================

st.markdown(
    "## 🔎 Pesquisa dos jogos"
)

pergunta = st.text_area(

    "Digite o que deseja buscar",

    value=(
        f"Pesquise os jogos de futebol de hoje "
        f"({data_atual}). "
        "Procure o maior número possível de partidas "
        "em diferentes países e competições. "
        "Traga horário, competição, mandante e visitante."
    ),

    height=180
)


# ============================================================
# BOTÕES
# ============================================================

col1, col2 = st.columns(2)


with col1:

    buscar = st.button(
        "🔎 BUSCAR JOGOS",
        type="primary",
        use_container_width=True
    )


with col2:

    vencedores = st.button(
        "🏆 BUSCAR VENCEDORES",
        use_container_width=True
    )


# ============================================================
# EXECUTAR
# ============================================================

if buscar or vencedores:

    if not OPENROUTER_API_KEY:

        st.error(
            "❌ Configure a chave OpenRouter."
        )

        st.stop()


    # ========================================================
    # PERGUNTA
    # ========================================================

    if vencedores:

        consulta = f"""
Pesquise na internet os jogos de futebol de hoje
({data_atual}).

Procure o maior número possível de partidas.

Procure diferentes países e competições.

Para cada partida encontrada informe:

- horário
- competição
- mandante
- visitante
- forma recente quando disponível
- posição quando disponível
- resultados recentes quando disponíveis
- notícias relevantes

Depois identifique quais equipes possuem maior indicação
estatística de vitória.

NÃO invente jogos.

Traga os dados encontrados.
"""

    else:

        consulta = f"""
Pesquise na internet os jogos de futebol de hoje
({data_atual}).

Procure o maior número possível de partidas de futebol
em diferentes países e competições.

Para cada jogo encontrado procure:

- horário
- competição
- país
- mandante
- visitante
- situação da partida

Não invente partidas.

Apresente uma lista organizada dos jogos encontrados.
"""


    # ========================================================
    # BUSCA
    # ========================================================

    with st.spinner(
        "🌐 Pesquisando jogos na web..."
    ):

        dados = buscar_web(
            consulta
        )


    # ========================================================
    # VERIFICAR BUSCA
    # ========================================================

    if not dados:

        st.error(
            "❌ Nenhum resultado encontrado na pesquisa."
        )

        st.stop()


    # ========================================================
    # ANALISAR
    # ========================================================

    with st.spinner(
        "🤖 IA analisando os jogos..."
    ):

        resultado = analisar_com_ia(

            pergunta=(
                pergunta
                if not vencedores
                else
                f"""
Analise os jogos de hoje ({data_atual})
e identifique os vencedores projetados.
"""
            ),

            dados_web=dados
        )


    # ========================================================
    # RESULTADO
    # ========================================================

    st.divider()

    if resultado["ok"]:

        if vencedores:

            st.markdown(
                "# 🏆 VENCEDORES DO DIA"
            )

        else:

            st.markdown(
                "# ⚽ JOGOS DO DIA"
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
    "⚠️ As probabilidades são estimativas da IA e "
    "não representam garantia de resultado."
)
