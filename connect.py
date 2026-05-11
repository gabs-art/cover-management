import requests
import json

PARTNER  = "*"
USERNAME = "*"
PASSWORD = "*"

URL = "https://api.backup.management/jsonapi"

payload = {
    "jsonrpc": "2.0",
    "method":  "Login",
    "id":      "1",
    "params": {
        "partner":  PARTNER,
        "username": USERNAME,
        "password": PASSWORD,
    }
}

try:
    print("Conectando...")
    resp = requests.post(URL, json=payload, timeout=15)
    print(f"Status HTTP: {resp.status_code}")
    data = resp.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"ERRO: {e}")

input("\nPressione ENTER para fechar...")
