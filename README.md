# Football Scanner — OpenFootAPI

Scanner em Streamlit para uso no navegador/iPhone.

## Streamlit Secrets

Configure:

`OPENFOOT_API_KEY = "SUA_CHAVE"`

Nunca coloque a chave diretamente no código público.

## Publicação

1. Crie um repositório no GitHub.
2. Envie `app.py` e `requirements.txt`.
3. No Streamlit Community Cloud, selecione `app.py`.
4. Em Settings > Secrets, informe a chave.

## Observação

A aplicação foi preparada para trabalhar com o catálogo de competições retornado pela API e não fixa uma lista pequena de campeonatos. A disponibilidade de contexto, eventos, xG e outros dados depende da API/plano/competição.

O cálculo de probabilidade usa Poisson como estimativa e não representa garantia de acerto ou lucro. Odds de Betano, Superbet e Betão são usadas pelo usuário para calcular EV; o scanner não promete obter automaticamente essas odds.
