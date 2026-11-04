import sys
import websocket

if len(sys.argv) < 3:
    print("Uso: python escuchar.py <ID_PROYECTO> <TOKEN_ACCESS>")
    sys.exit(1)

proyecto, token = sys.argv[1], sys.argv[2]
ws = websocket.create_connection(f"ws://127.0.0.1:8000/ws/projects/{proyecto}/?token={token}")
print("Conectado. Esperando mensajes (Ctrl+C para salir)...")
try:
    while True:
        print(ws.recv())
except KeyboardInterrupt:
    print("\nDesconectado.")
