# Football Scanner 90+

App Streamlit para navegador/iPhone com busca automática e manual de jogos, mercados de gols, BTTS, 1X2, escanteios e cartões, usando somente odds encontradas para Betano, Superbet e Betão.

## Deploy
1. Suba `app.py` e `requirements.txt` para um repositório GitHub.
2. Publique no Streamlit Community Cloud.
3. Em Secrets, use:

```toml
[api]
football_key = "SUA_CHAVE_DA_API_FOOTBALL"
```

A chave fica no servidor, não no navegador.
