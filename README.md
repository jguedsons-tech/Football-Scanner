# Football Scanner ⚽

Aplicativo Streamlit para análise de partidas com API-Football.

## Deploy no Streamlit Community Cloud

1. Crie um repositório no GitHub.
2. Envie `app.py`, `requirements.txt` e `README.md`.
3. No Streamlit Community Cloud, selecione o repositório e `app.py`.
4. Em **Settings → Secrets**, configure:

```toml
[api]
football_key = "SUA_API_KEY"
```

Nunca publique a API Key no GitHub.

## Recursos

- Busca de jogos hoje/amanhã
- Scanner automático
- 1X2
- Over/Under
- BTTS
- Escanteios
- Cartões
- Odds de Betano, Superbet e Betão
- Probabilidade estimada, odd justa e EV
- Predictions e estatísticas da API-Football quando disponíveis

## Limitações

O plano Free da API-Football possui limites de requisições e cobertura de dados. O aplicativo usa cache para reduzir chamadas. As probabilidades são estimativas estatísticas e não garantem resultados ou lucro.

## Execução local (opcional)

```bash
pip install -r requirements.txt
streamlit run app.py
```
