import os
import requests

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")


def buscar_ia(pergunta):
    if not API_KEY:
        return "ERRO: OPENROUTER_API_KEY não configurada."

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Busca IA Gratuita",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é uma IA de pesquisa e análise. "
                    "Responda em português brasileiro, "
                    "de forma objetiva e organizada."
                ),
            },
            {
                "role": "user",
                "content": pergunta,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 3000,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90
        )

        if response.status_code != 200:
            return f"ERRO HTTP {response.status_code}\n\n{response.text}"

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except requests.RequestException as e:
        return f"ERRO DE CONEXÃO: {e}"

    except Exception as e:
        return f"ERRO: {e}"


def main():

    print("=" * 70)
    print("🤖 BUSCA IA GRATUITA - OPENROUTER")
    print("=" * 70)

    if not API_KEY:
        print("\nOPENROUTER_API_KEY não configurada.")
        print("Configure a variável antes de executar.")
        return

    print("Digite sua pergunta.")
    print("Digite SAIR para encerrar.\n")

    while True:

        pergunta = input("🔎 Busca: ").strip()

        if pergunta.lower() == "sair":
            print("\nEncerrado.")
            break

        if not pergunta:
            continue

        print("\nConsultando IA...\n")

        resposta = buscar_ia(pergunta)

        print("=" * 70)
        print("RESPOSTA")
        print("=" * 70)
        print(resposta)
        print("=" * 70)
        print()


if __name__ == "__main__":
    main()
