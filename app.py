import os
import requests
import streamlit as st
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="⚽ IA Futebol - Jogos do Dia",
    page_icon="⚽",
    layout="wide"
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# ============================================================
# FUNÇÃO OPENROUTER
# ============================================================

def consultar_ia(pergunta):

    if not OPENROUTER_API_KEY:
        return {
            "ok": False,
            "texto": "❌ OPENROUTER_API_KEY não configurada."
        }

    system_prompt = """
Você é um ANALISTA DE FUTEBOL especializado em pesquisa
de partidas e análise estatística.

RESPONDA SEMPRE EM PORTUGUÊS DO BRASIL.

============================================================
OBJETIVO PRINCIPAL
============================================================

Quando o usuário pedir:

- jogos de hoje
- todos os jogos do dia
- jogos de determinada data
- jogos a partir de determinado horário
- vencedores
- melhores vencedores
- partidas para análise
- jogos de futebol de hoje

VOCÊ DEVE PRIMEIRO PESQUISAR A INTERNET.

Não dependa apenas do seu conhecimento interno.

============================================================
PESQUISA DOS JOGOS
============================================================

Quando procurar os jogos do dia:

1. Pesquise partidas de futebol da data solicitada.
2. Procure várias competições.
3. Procure diferentes países.
4. Procure:
   - campeonatos nacionais
   - copas
   - competições continentais
   - competições internacionais
   - divisões inferiores quando encontradas
5. Tente obter:
   - horário
   - mandante
   - visitante
   - competição
   - país
   - situação da partida

NÃO invente partidas.

Se não conseguir confirmar uma partida através de fonte
atual, não coloque como partida confirmada.

============================================================
ANÁLISE DO VENCEDOR
============================================================

Para cada partida encontrada, analise:

- forma recente
- desempenho como mandante
- desempenho como visitante
- gols marcados
- gols sofridos
- confrontos quando disponíveis
- posição/classificação quando disponível
- resultados recentes
- desfalques quando disponíveis
- notícias recentes
- contexto da competição
- mando de campo

Depois estime:

1 = vitória do mandante
X = empate
2 = vitória do visitante

IMPORTANTE:

A probabilidade é uma ESTIMATIVA.

Nunca apresente como garantia.

============================================================
FORMATO OBRIGATÓRIO
============================================================

Para cada jogo:

⚽ TIME A x TIME B
🏆 Competição:
🕐 Horário:

🎯 PREVISÃO:
→ 1
ou
→ X
ou
→ 2

📊 Probabilidade estimada:
Mandante: XX%
Empate: XX%
Visitante: XX%

🏆 Vencedor projetado:
TIME

📌 Confiança:
Baixa / Média / Alta

📊 Justificativa:
resumo objetivo dos dados encontrados.

============================================================
TABELA PRINCIPAL
============================================================

Quando houver muitos jogos, primeiro apresente:

| Horário | Competição | Jogo | Previsão | Prob. |
|---------|------------|------|----------|-------|

Use:

1 = mandante
X = empate
2 = visitante

============================================================
CLASSIFICAÇÃO DAS ANÁLISES
============================================================

Depois da tabela, mostre:

🔥 VENCEDORES COM MAIOR PROBABILIDADE

Liste os jogos que apresentarem maior probabilidade
estatística de vitória.

Depois:

⚠️ JOGOS MAIS EQUILIBRADOS

Mostre partidas onde a diferença entre as equipes
for pequena.

Depois:

🎯 POSSÍVEIS EMPATES

Liste as partidas onde X tiver uma probabilidade
relevante.

============================================================
OUTROS MERCADOS
============================================================

Quando houver dados suficientes, também analise:

BTTS
OVER 1.5
OVER 2.5
UNDER 3.5

Mas NÃO substitua a previsão de vencedor.

============================================================
REGRAS IMPORTANTES
============================================================

NÃO invente:

- resultados
- estatísticas
- odds
- jogadores
- desfalques
- horários
- partidas
- probabilidades apresentadas como fatos

Se um dado não puder ser confirmado:

"Não encontrado".

Diferencie claramente:

DADO ENCONTRADO
de
ESTIMATIVA DA IA.

Se o número de partidas encontradas não puder ser
garantidamente completo, diga:

"Lista baseada nas partidas encontradas nas fontes
pesquisadas; a cobertura pode não incluir todas as
competições existentes."

============================================================
DATA
============================================================

Considere a data atual fornecida pelo sistema.

Se o usuário disser "hoje", procure a data atual.

Se o usuário fornecer uma data específica, use essa data.

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

        # Permite à IA pesquisar a web.
        "tools": [
            {
                "type": "openrouter:web_search",
                "parameters": {
                    "max_results": 10,
                    "search_context_size": "high"
                }
            }
        ],

        "temperature": 0.15,
        "max_tokens": 12000
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "IA Futebol - Jogos do Dia"
    }

    try:

        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=180
        )

        if response.status_code != 200:

            try:
                erro = response.json()
            except Exception:
                erro = response.text

            return {
                "ok": False,
                "texto": (
                    f"❌ Erro OpenRouter "
                    f"{response.status_code}\n\n{erro}"
                )
            }

        data = response.json()

        choices = data.get("choices", [])

        if not choices:
            return {
                "ok": False,
                "texto": "❌ A IA não retornou resposta."
            }

        message = choices[0].get("message", {})

        texto = message.get("content", "")

        if not texto:

            # Algumas respostas podem trazer conteúdo
            # estruturado diferente.
            texto = str(message)

        return {
            "ok": True,
            "texto": texto
        }

    except requests.Timeout:

        return {
            "ok": False,
            "texto": "⏱️ A pesquisa demorou demais."
        }

    except requests.RequestException as e:

        return {
            "ok": False,
            "texto": f"❌ Erro de conexão:\n\n{e}"
        }

    except Exception as e:

        return {
            "ok": False,
            "texto": f"❌ Erro:\n\n{e}"
        }


# ============================================================
# CABEÇALHO
# ============================================================

st.title("⚽ IA FUTEBOL")

st.subheader("🔎 Jogos do dia + previsão de vencedores")

st.caption(
    "Pesquisa realizada pela IA através da web. "
    "Sem TheSportsDB, football-data.org, OpenFoot ou outras APIs de futebol."
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Configuração")

    if OPENROUTER_API_KEY:
        st.success("🟢 OpenRouter conectado")
    else:
        st.error("🔴 OpenRouter não configurado")

    st.write("Modelo:")

    st.code(OPENROUTER_MODEL)

    st.divider()

    st.write("### 🔎 Pesquisas")

    st.write("""
A IA pode pesquisar:

• Jogos de hoje
• Todos os campeonatos
• Horários
• Mandante
• Visitante
• Vencedor
• Empate
• Probabilidades
• BTTS
• Over/Under
• Forma recente
• Notícias
• Desfalques
""")

    st.divider()

    st.warning(
        "As probabilidades são estimativas estatísticas "
        "e não garantem resultados."
    )


# ============================================================
# DATA AUTOMÁTICA
# ============================================================

data_atual = datetime.now().strftime("%d/%m/%Y")


# ============================================================
# BUSCA PRINCIPAL
# ============================================================

st.markdown("## 🔎 Buscar jogos")

pergunta = st.text_area(
    "O que você quer pesquisar?",
    value=(
        f"Pesquise TODOS os jogos de futebol de hoje "
        f"({data_atual}) que conseguir encontrar na web. "
        "Considere todas as competições e países disponíveis. "
        "Para cada partida, traga horário, competição, "
        "mandante, visitante, previsão 1/X/2, probabilidade "
        "de mandante, empate e visitante, vencedor projetado "
        "e justificativa estatística. "
        "Depois faça uma lista dos vencedores com maior "
        "probabilidade."
    ),
    height=220
)


# ============================================================
# BOTÕES
# ============================================================

col1, col2 = st.columns(2)


with col1:

    buscar = st.button(
        "🔎 BUSCAR TODOS OS JOGOS",
        type="primary",
        use_container_width=True
    )


with col2:

    melhores = st.button(
        "🏆 BUSCAR VENCEDORES",
        use_container_width=True
    )


# ============================================================
# BUSCA TODOS
# ============================================================

if buscar:

    if not OPENROUTER_API_KEY:

        st.error(
            "Configure OPENROUTER_API_KEY antes de continuar."
        )

    else:

        with st.spinner(
            "🔎 Pesquisando jogos na web e analisando..."
        ):

            resultado = consultar_ia(pergunta)

        st.divider()

        if resultado["ok"]:

            st.markdown("## ⚽ JOGOS ENCONTRADOS")

            st.markdown(resultado["texto"])

        else:

            st.error(resultado["texto"])


# ============================================================
# BUSCAR VENCEDORES
# ============================================================

if melhores:

    pergunta_vencedores = f"""
Pesquise na internet TODOS os jogos de futebol de hoje
({data_atual}) que você conseguir encontrar.

Procure o maior número possível de competições e países.

Para cada jogo:

- horário
- competição
- mandante
- visitante
- probabilidade de vitória do mandante
- probabilidade de empate
- probabilidade de vitória do visitante
- vencedor projetado

Depois selecione somente os jogos onde exista uma indicação
estatística clara de vencedor.

Monte uma tabela:

| Horário | Competição | Jogo | Vencedor | Probabilidade |

Depois faça:

🔥 VENCEDORES COM MAIOR PROBABILIDADE

Inclua também uma justificativa resumida para cada seleção.

Não invente partidas ou estatísticas.

Informe as fontes/dados encontrados quando possível.

Deixe claro que as probabilidades são estimativas e não
garantias.
"""

    if not OPENROUTER_API_KEY:

        st.error(
            "Configure OPENROUTER_API_KEY antes de continuar."
        )

    else:

        with st.spinner(
            "🏆 Pesquisando e analisando os vencedores..."
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
    "⚠️ A lista depende da cobertura das fontes encontradas "
    "pela pesquisa na web. Probabilidades não são garantias."
)
