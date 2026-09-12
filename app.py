import os
import requests
import streamlit as st

st.title("🔑 Teste OpenFootAPI")

try:
    key = st.secrets["OPENFOOT_API_KEY"]
except Exception:
    key = ""

st.write("Chave carregada:", "SIM" if key else "NÃO")

if key:
    r = requests.get(
        "https://openfootapi.com/v1/matches",
        params={"date": "2026-09-12"},
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
        },
        timeout=20,
    )

    st.write("HTTP:", r.status_code)
    st.json(r.json())
else:
    st.error("OPENFOOT_API_KEY não encontrada nos Secrets.")
