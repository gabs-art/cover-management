"""
Web Terminal — N-able Cove Monitor
Roda connect.py em um pseudo-terminal e expõe via WebSocket.
Funciona no Railway (Linux). Interativo via xterm.js no navegador.
"""
import os, sys, pty, select, threading, signal, termios, struct, fcntl
from flask import Flask, send_from_directory
from flask_sock import Sock

app  = Flask(__name__, static_folder="static")
sock = Sock(app)

# Senha de acesso ao terminal web (configure via variável de ambiente)
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "trustit")
SCRIPT_PATH  = os.path.join(os.path.dirname(__file__), "connect.py")

# ── Sessões ativas ────────────────────────────────────────────────────────────
sessions = {}  # ws_id → {pid, fd}

def spawn_terminal():
    """Cria um pseudo-terminal e lança connect.py dentro dele."""
    env = os.environ.copy()
    env["TERM"]     = "xterm-256color"
    env["COLUMNS"]  = "118"
    env["LINES"]    = "40"
    env["PYTHONUNBUFFERED"] = "1"

    pid, fd = pty.fork()

    if pid == 0:
        # Processo filho — executa o script
        os.execvpe(sys.executable, [sys.executable, SCRIPT_PATH], env)
    else:
        # Processo pai — retorna fd para comunicação
        return pid, fd

def set_winsize(fd, rows, cols):
    """Redimensiona o terminal."""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except: pass

@sock.route("/ws")
def terminal_ws(ws):
    """WebSocket — bridge entre o navegador e o PTY."""
    # Autenticação simples
    try:
        auth = ws.receive(timeout=5)
        if auth != WEB_PASSWORD:
            ws.send("\r\n\x1b[31m[ACESSO NEGADO]\x1b[0m\r\n")
            ws.close()
            return
        ws.send("\r\n\x1b[32m[CONECTADO — iniciando monitor...]\x1b[0m\r\n\r\n")
    except:
        return

    # Spawna o terminal
    try:
        pid, fd = spawn_terminal()
    except Exception as e:
        ws.send(f"\r\n\x1b[31mERRO ao iniciar: {e}\x1b[0m\r\n")
        return

    closed = threading.Event()

    # Thread: lê output do PTY → envia para o browser
    def pty_to_ws():
        while not closed.is_set():
            try:
                r, _, _ = select.select([fd], [], [], 0.04)
                if r:
                    data = os.read(fd, 4096)
                    if data:
                        ws.send(data.decode("utf-8", errors="replace"))
            except (OSError, EOFError):
                break
            except Exception:
                break
        closed.set()

    t = threading.Thread(target=pty_to_ws, daemon=True)
    t.start()

    # Loop principal: recebe input do browser → envia para o PTY
    try:
        while not closed.is_set():
            try:
                msg = ws.receive(timeout=0.1)
                if msg is None:
                    break

                # Mensagem especial de resize: "RESIZE:cols:rows"
                if isinstance(msg, str) and msg.startswith("RESIZE:"):
                    _, cols, rows = msg.split(":")
                    set_winsize(fd, int(rows), int(cols))
                    continue

                # Input normal — envia ao PTY
                data = msg.encode() if isinstance(msg, str) else msg
                os.write(fd, data)

            except Exception:
                break
    finally:
        closed.set()
        try:
            os.kill(pid, signal.SIGTERM)
        except: pass
        try:
            os.close(fd)
        except: pass

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Web Terminal rodando em http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
