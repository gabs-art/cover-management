"""
Web Terminal — N-able Cove Monitor
Roda connect.py em um pseudo-terminal Linux e expõe via WebSocket.
"""
import os, sys, pty, select, threading, signal, termios, struct, fcntl
from flask import Flask, send_from_directory
from flask_sock import Sock

app  = Flask(__name__, static_folder="static")
sock = Sock(app)

WEB_PASSWORD = os.getenv("WEB_PASSWORD", "trustit")
SCRIPT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connect.py")

def spawn_terminal(cols=220, rows=50):
    env = os.environ.copy()
    env["TERM"]            = "xterm-256color"
    env["COLUMNS"]         = str(cols)
    env["LINES"]           = str(rows)
    env["PYTHONUNBUFFERED"] = "1"
    env["FORCE_COLOR"]     = "1"
    # Passa todas as variáveis N-able para o processo filho
    for k in ["NABLE_PARTNER","NABLE_USERNAME","NABLE_PASSWORD","NABLE_URL"]:
        if k in os.environ:
            env[k] = os.environ[k]

    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(sys.executable, [sys.executable, "-u", SCRIPT_PATH], env)
    else:
        # Define tamanho do terminal
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except: pass
        return pid, fd

def set_winsize(fd, rows, cols):
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except: pass

@sock.route("/ws")
def terminal_ws(ws):
    # Autenticação
    try:
        auth = ws.receive(timeout=10)
        if auth != WEB_PASSWORD:
            ws.send("\r\n\x1b[31m✗ ACESSO NEGADO\x1b[0m\r\n")
            return
        ws.send("\x1b[32m✓ Autenticado — iniciando monitor...\x1b[0m\r\n\r\n")
    except Exception as e:
        return

    # Inicia o terminal
    try:
        pid, fd = spawn_terminal()
    except Exception as e:
        ws.send(f"\r\n\x1b[31mERRO ao iniciar processo: {e}\x1b[0m\r\n")
        return

    closed = threading.Event()

    # PTY → WebSocket
    def read_pty():
        while not closed.is_set():
            try:
                r, _, _ = select.select([fd], [], [], 0.02)
                if r:
                    data = os.read(fd, 8192)
                    if data:
                        try:
                            ws.send(data.decode("utf-8", errors="replace"))
                        except:
                            closed.set()
                            break
            except (OSError, EOFError):
                closed.set()
                break
            except:
                break

    threading.Thread(target=read_pty, daemon=True).start()

    # WebSocket → PTY
    try:
        while not closed.is_set():
            try:
                msg = ws.receive(timeout=30)
                if msg is None:
                    break
                if isinstance(msg, str) and msg.startswith("RESIZE:"):
                    _, cols, rows = msg.split(":")
                    set_winsize(fd, int(rows), int(cols))
                    continue
                data = msg.encode() if isinstance(msg, str) else msg
                os.write(fd, data)
            except Exception:
                break
    finally:
        closed.set()
        try: os.kill(pid, signal.SIGTERM)
        except: pass
        try: os.close(fd)
        except: pass

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/health")
def health():
    return {"status":"ok","script":SCRIPT_PATH,"exists":os.path.exists(SCRIPT_PATH)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"Web Terminal rodando em http://0.0.0.0:{port}")
    print(f"Script: {SCRIPT_PATH} — existe: {os.path.exists(SCRIPT_PATH)}")
    app.run(host="0.0.0.0", port=port, debug=False)
