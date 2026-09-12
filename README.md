# ⚽ Football Scanner — temporada 2026

Aplicativo Streamlit + API-Football para análise de partidas.

## Temporada

O módulo de estatísticas foi configurado explicitamente para **2026** (`SEASON=2026`).
Isso evita que o app use automaticamente a temporada enviada pelo cadastro da partida.

**Atenção:** o plano Free da API-Football limita as temporadas disponíveis. Se a API retornar que sua chave Free não tem acesso à temporada 2026 para determinada competição, o app não consegue liberar esse acesso por código; nesse caso, a própria API precisa disponibilizar a temporada para sua chave/plano.

## Recursos

- Jogos de hoje e amanhã
- Scanner automático
- 1X2
- Over/Under
- BTTS
- Escanteios
- Cartões
- Odds
- Odd justa
- EV
- Predictions da API-Football
- Estatísticas usando temporada 2026 quando disponíveis
- Betano, Superbet e Betão

## Streamlit Cloud

1. Envie `app.py`, `requirements.txt` e `README.md` para o GitHub.
2. Crie o app no Streamlit Community Cloud.
3. Em **Settings → Secrets**, configure:

```toml
[api]
football_key = "SUA_API_KEY"
```

Não publique a API Key no GitHub.

## Dependências

```bash
pip install -r requirements.txt
```

As probabilidades são estimativas estatísticas e não garantem acerto ou lucro.
