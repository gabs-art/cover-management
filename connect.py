import requests
import datetime
import time
import os
import threading

PARTNER  = "*"
USERNAME = "*"
PASSWORD = "*"
URL      = "*"

TEMPO_CRITICO = 480  # 8 minutos
TEMPO_NORMAL  = 330  # 5:30
TW = 118

# ── Todas as fontes de dados disponíveis na API ───────────────────────────────
# Código legado: letra = fonte, número/letra = campo
# F=Files&Folders, S=SystemState, N=NetworkShares, Z=VssMsSql,
# X=Exchange, P=SharePoint, Y=Oracle, W=VMware, H=HyperV, L=MySQL
# G=M365Exchange, J=M365OneDrive

FONTES_DEF = {
    # (codigo_i78, nome_exibicao, prefixo_legado, emoji)
    "D01": ("Files & Folders",       "F",  "📁"),
    "D1":  ("Files & Folders",       "F",  "📁"),
    "D02": ("System State",          "S",  "🗄"),
    "D2":  ("System State",          "S",  "🗄"),
    "D06": ("Network Shares",        "N",  "🌐"),
    "D6":  ("Network Shares",        "N",  "🌐"),
    "D03": ("MS SQL",                "Z",  "🗃"),
    "D3":  ("MS SQL",                "Z",  "🗃"),
    "D04": ("VSS Exchange",          "X",  "📧"),
    "D4":  ("VSS Exchange",          "X",  "📧"),
    "D05": ("M365 SharePoint",       "P",  "📋"),
    "D5":  ("M365 SharePoint",       "P",  "📋"),
    "D08": ("VMware",                "W",  "🖥"),
    "D8":  ("VMware",                "W",  "🖥"),
    "D10": ("VSS MS SQL",            "Z",  "🗃"),
    "D11": ("VSS SharePoint",        "P",  "📋"),
    "D12": ("Oracle",                "Y",  "🔶"),
    "D14": ("Hyper-V",               "H",  "💠"),
    "D15": ("MySQL",                 "L",  "🐬"),
    "D17": ("Bare Metal Restore",    "B",  "💾"),
    "D19": ("M365 Exchange",         "G",  "📨"),
    "D20": ("M365 OneDrive",         "J",  "☁"),
}

# Mapeamento de prefixo legado → campos
# Ex: "F" → status=F0, arq_sel=F1, arq_alt=F2, tam_sel=F3,
#            tam_proc=F4, tam_env=F5, tam_prot=F6, erros=F7,
#            barra=F8 (nem todas têm), ultimo_ok=FL, duracao=FA
CAMPOS = {
    "status":    "0",
    "arq_sel":   "1",
    "arq_alt":   "2",
    "tam_sel":   "3",
    "tam_proc":  "4",
    "tam_env":   "5",
    "tam_prot":  "6",
    "erros":     "7",
    "barra":     "8",
    "ultimo_ok": "L",
    "duracao":   "A",
}

def col_fonte(prefixo, campo):
    """Retorna o código de coluna legado. Ex: col_fonte('F','0') → 'F0'"""
    return f"{prefixo}{CAMPOS[campo]}"

# ─────────────────────────────────────────────────────────────────────────────
def login():
    r = requests.post(URL, json={
        "jsonrpc":"2.0","method":"Login","id":"1",
        "params":{"partner":PARTNER,"username":USERNAME,"password":PASSWORD}
    }, timeout=15).json()
    return r.get("visa"), r["result"]["result"]["PartnerId"]

def fetch_todos(visa, partner_id):
    # Monta lista de colunas — fontes principais + todas as fontes legadas
    colunas_base = [
        "I1","I8","I18","I16","I17","I14","I78",
        "T0","TL","T3","T4","T5","T6",
        "D1F8","D2F8",  # Barras 28 dias formato novo
    ]
    # Fontes que têm colunas legadas
    prefixos = ["F","S","N","Z","X","P","Y","W","H","L","G","J"]
    colunas_fontes = []
    for pref in prefixos:
        for campo in ["0","1","2","3","4","5","6","7","A","L"]:
            colunas_fontes.append(f"{pref}{campo}")
        # Barra 28 dias — solicita para todas as fontes que possam ter
        if pref in ("F","S","N","W","H","Z","X","P","Y","L","G","J"):
            colunas_fontes.append(f"{pref}8")

    todos = []; start = 0; batch = 250
    while True:
        r = requests.post(URL, json={
            "jsonrpc":"2.0","method":"EnumerateAccountStatistics","id":"2","visa":visa,
            "params":{"query":{
                "PartnerId":partner_id,"SelectionMode":"Merged",
                "StartRecordNumber":start,"RecordsCount":batch,
                "Columns": colunas_base + colunas_fontes
            }}
        }, timeout=30).json()
        lote = r.get("result",{}).get("result",[])
        todos.extend(lote); visa = r.get("visa", visa)
        if len(lote) < batch: break
        start += batch
    return todos, visa

def c(s,k):
    for i in (s or []):
        if k in i: return i[k]
    return ""

def gb(val):
    try:
        b = int(val)
        if b <= 0: return "0 B"
        for u in ["B","KB","MB","GB","TB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
    except: return "—"

def n(val):
    try: return f"{int(val):,}".replace(",",".")
    except: return "—"

def dt(val):
    try:
        ts = int(val)
        return "—" if ts <= 0 else datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except: return "—"

def dur(val, concluiu):
    if not concluiu or not val: return "não concluiu"
    try:
        s = int(val)
        if s <= 0: return "não concluiu"
        h,r = divmod(s,3600); m,s = divmod(r,60)
        return f"{h}h {m}m" if h else f"{m}m {s}s"
    except: return "—"

def dias_atras(val):
    try:
        d = (datetime.datetime.now().timestamp() - int(val)) / 86400
        if d < 1: return "hoje"
        if d < 2: return "ontem"
        return f"{d:.0f}d atrás"
    except: return "—"

def erros_fmt(val):
    try:
        v = int(val)
        return "Overflow/bug agente" if v > 1_000_000_000 else n(val)
    except: return "—"

def esta_offline(s):
    try:
        tl = int(c(s,"TL"))
        dias = (datetime.datetime.now().timestamp() - tl) / 86400
        return dias > 3 and c(s,"T0") not in ("5",)
    except: return False

STATUS = {
    "2":("❌","FALHOU","CRITICO"),
    "3":("⛔","ABORTADO","CRITICO"),
    "5":("✅","CONCLUÍDO","OK"),
    "6":("🟠","INTERROMPIDO","AVISO"),
    "7":("⬜","NÃO INICIADO","NEUTRO"),
    "8":("🟠","COM ERROS","AVISO"),
    "9":("🟡","COM FALHAS","AVISO"),
    "10":("🔴","COTA EXCEDIDA","CRITICO"),
}
def status_fmt(v):
    if not v: return "⬜ DESCONHECIDO"
    ico, label, _ = STATUS.get(v, ("❓", v, "NEUTRO"))
    return f"{ico} {label}"
def status_nivel(v):
    return STATUS.get(v, ("","","NEUTRO"))[2]

def extrair_municipio(dev):
    cliente = c(dev.get("Settings") or [], "I8") or ""
    for p in ["PM_","CM_","Prefeitura_","Camara_","Prefeitura ","Camara "]:
        if cliente.startswith(p): cliente = cliente[len(p):]
    return cliente.strip().upper() or "ZZZZZ"

def prioridade_dispositivo(dev):
    s     = dev.get("Settings") or []
    nivel = status_nivel(c(s,"T0"))
    if nivel == "CRITICO": return 0
    if esta_offline(s):    return 1
    if nivel == "AVISO":   return 2
    if nivel == "OK":      return 3
    return 4

def ordenar_dispositivos(dispositivos):
    prob = [d for d in dispositivos if prioridade_dispositivo(d) <= 2]
    norm = [d for d in dispositivos if prioridade_dispositivo(d) >  2]
    prob.sort(key=lambda d: (extrair_municipio(d), prioridade_dispositivo(d)))
    norm.sort(key=lambda d: (extrair_municipio(d), prioridade_dispositivo(d)))
    return prob + norm

PRIORIDADE_STATUS = {"5":0,"8":1,"6":2,"9":3,"2":4,"3":5,"1":6,"0":7,"7":8}

def combinar_barras(*barras):
    """
    Combina barras de múltiplas fontes em uma barra única.
    Para cada dia, usa o MELHOR status entre todas as fontes ativas.
    Isso replica o comportamento da plataforma web que mostra sessões de todas as fontes.
    Barras de tamanhos diferentes são alinhadas pelo dia mais recente (último char = hoje).
    """
    barras = [b for b in barras if b]
    if not barras: return ""
    max_len = max(len(b) for b in barras)
    resultado = []
    for i in range(max_len):
        melhor = "0"
        for b in barras:
            offset = max_len - len(b)
            idx = i - offset
            if 0 <= idx < len(b):
                ch = b[idx]
                if PRIORIDADE_STATUS.get(ch,9) < PRIORIDADE_STATUS.get(melhor,9):
                    melhor = ch
        resultado.append(melhor)
    return "".join(resultado)

def calendario(barra):
    """
    Calendário idêntico à interface web da N-able:
    ✅  = Concluído (verde)
    🟠  = Com erros / Interrompido (laranja)
    ❌  = Falhou / Abortado (vermelho)
    ░░  = Sem backup / Não iniciado (cinza)
    [ ] = Dia atual (destaque)
    """
    if not barra:
        return ["  Sem dados de histórico disponíveis."]

    COR_LABEL = {
        "5": "✅ ", "8": "🟠", "6": "🟠", "9": "🟠",
        "2": "❌ ", "3": "❌ ", "0": "░░", "7": "░░", "1": "🔄",
    }
    COR_DESC = {
        "5": "OK", "8": "ERR", "6": "ERR", "9": "ERR",
        "2": "FLH", "3": "FLH", "0": "---", "7": "---", "1": "...",
    }

    hoje = datetime.date.today()
    ini  = hoje - datetime.timedelta(days=len(barra)-1)
    dow_cal = (ini.weekday() + 1) % 7  # 0=Dom ... 6=Sab

    DIAS_SEMANA = ["  Dom  ", "  Seg  ", "  Ter  ", "  Qua  ", "  Qui  ", "  Sex  ", "  Sab  "]
    CEL = 7

    out = []

    # Cabeçalho
    out.append("  " + "".join(DIAS_SEMANA))
    out.append("  " + ("─" * 7 + " ") * 7)

    # Monta células: None para dias vazios
    celulas = [None] * dow_cal
    for i, ch in enumerate(barra):
        celulas.append((ini + datetime.timedelta(days=i), ch))
    while len(celulas) % 7 != 0:
        celulas.append(None)

    semanas = [celulas[i:i+7] for i in range(0, len(celulas), 7)]

    for semana in semanas:
        linha_ico = "  "
        linha_dia = "  "
        for cel in semana:
            if cel is None:
                linha_ico += "       "
                linha_dia += "       "
            else:
                d, ch = cel
                ico   = COR_LABEL.get(ch, "░░")
                desc  = COR_DESC.get(ch, "---")
                eh_hoje = (d == hoje)
                dia_str = f"[{d.day:2d}]" if eh_hoje else f" {d.day:2d} "
                linha_ico += f" {ico} {desc} "
                linha_dia += f"  {dia_str}  "
        out.append(linha_ico)
        out.append(linha_dia)
        out.append("  " + ("─" * 7 + " ") * 7)

    return out

# ── Animações ─────────────────────────────────────────────────────────────────
SPIN = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
WAVE = ["▁","▂","▃","▄","▅","▆","▇","█","▇","▆","▅","▄","▃","▂"]

def spinner(msg, seg=1.8):
    fim = time.time() + seg; i = 0
    while time.time() < fim:
        print(f"\r   {SPIN[i%len(SPIN)]}  {msg}", end="", flush=True)
        time.sleep(0.07); i += 1
    print(f"\r   ✅  {msg}          ", flush=True)

def wave_loading(msg, seg=2.0):
    fim = time.time() + seg; i = 0
    while time.time() < fim:
        onda = "".join(WAVE[(i+j)%len(WAVE)] for j in range(12))
        print(f"\r   {onda}  {msg}  {onda}", end="", flush=True)
        time.sleep(0.07); i += 1
    print(f"\r   {'─'*40}   ", flush=True)

def barra_animada(label, val, total, largura=28):
    try:    pct = min(int(val)/int(total), 1.0)
    except: pct = 0.0
    val_str = gb(val)
    for step in range(int(pct * largura) + 1):
        bar = "█"*step + "░"*(largura-step)
        frac = step/largura
        print(f"\r   │  {label:<20} {val_str:<10} [{bar}] {frac*100:.0f}%   ", end="", flush=True)
        time.sleep(0.018)
    bar_fim = "█"*int(pct*largura) + "░"*(largura-int(pct*largura))
    print(f"\r   │  {label:<20} {val_str:<10} [{bar_fim}] {pct*100:.1f}%   ", flush=True)

def countdown_com_pesquisa(seg, idx, total, tem_erro, dispositivos):
    pesquisa = [False]
    def ouvir():
        try:
            if input().strip().lower() == "p":
                pesquisa[0] = True
        except: pass
    threading.Thread(target=ouvir, daemon=True).start()
    icone = "🔴" if tem_erro else "🟢"
    m_tot, s_tot = divmod(seg, 60)
    for s in range(seg, 0, -1):
        if pesquisa[0]: break
        m, sc = divmod(s, 60)
        prog  = int((seg-s)/seg*50)
        bar   = "█"*prog + "░"*(50-prog)
        print(
            f"\r   {icone}  Próximo em {m:02d}:{sc:02d}  (de {m_tot:02d}:{s_tot:02d})"
            f"   [{bar}]   {idx}/{total}   [P+ENTER = pesquisar]",
            end="", flush=True
        )
        time.sleep(1)
    print()
    if pesquisa[0]:
        tela_pesquisa(dispositivos)

# ── Layout ────────────────────────────────────────────────────────────────────
CW = (TW - 5) // 2

def topo(char="█"): print(f"   {char*TW}")
def cab(titulo, emoji=""):
    pad = TW - len(titulo) - len(emoji) - 8
    print(f"\n   ╔══ {emoji}{titulo} {'═'*max(pad,2)}╗")
def cab2(t1, t2, e1="", e2=""):
    p1 = CW - len(t1) - len(e1) - 6
    p2 = CW - len(t2) - len(e2) - 6
    print(f"\n   ╔══ {e1}{t1} {'═'*max(p1,2)}╗   ╔══ {e2}{t2} {'═'*max(p2,2)}╗")
def row(l,v):   print(f"   ║  {l:<22} {v}")
def row2(l1,v1,l2,v2):
    esq = f"   ║  {l1:<20} {str(v1):<16}"
    dir = f"   ║  {l2:<20} {str(v2)}"
    print(f"{esq:<{CW+7}}   {dir}")
def sep2():        print(f"   ╟{'─'*CW}╢   ╟{'─'*CW}╢")
def fim():         print(f"   ╚{'═'*(TW-2)}╝")
def fim2():        print(f"   ╚{'═'*CW}╝   ╚{'═'*CW}╝")
def linha_cheia(): print(f"   ║")

def quebrar_texto(texto, largura=100):
    palavras = texto.split(); linha = ""; linhas = []
    for p in palavras:
        if len(linha) + len(p) + 1 > largura:
            linhas.append(linha); linha = p
        else:
            linha = (linha + " " + p).strip()
    if linha: linhas.append(linha)
    return linhas

# ── Detecta fontes ativas no dispositivo ─────────────────────────────────────
def detectar_fontes_ativas(s):
    """
    Retorna lista de (nome, emoji, prefixo_legado) das fontes que têm dados.
    Verifica tanto o campo I78 quanto a presença de colunas com dados.
    """
    fontes_raw = c(s,"I78") or ""
    ativas = []
    vistas = set()

    # Via I78
    for codigo, (nome, prefixo, emoji) in FONTES_DEF.items():
        if codigo in fontes_raw and nome not in vistas:
            ativas.append((nome, emoji, prefixo))
            vistas.add(nome)

    # Fallback: verifica se há dados nas colunas mesmo sem I78
    extras = [
        ("N", "Network Shares",   "🌐"),
        ("Z", "MS SQL",           "🗃"),
        ("X", "VSS Exchange",     "📧"),
        ("P", "SharePoint",       "📋"),
        ("Y", "Oracle",           "🔶"),
        ("W", "VMware",           "🖥"),
        ("H", "Hyper-V",          "💠"),
        ("L", "MySQL",            "🐬"),
        ("G", "M365 Exchange",    "📨"),
        ("J", "M365 OneDrive",    "☁"),
    ]
    for prefixo, nome, emoji in extras:
        if nome not in vistas:
            status_col = c(s, f"{prefixo}0")
            sel_col    = c(s, f"{prefixo}3")
            if status_col or sel_col:
                ativas.append((nome, emoji, prefixo))
                vistas.add(nome)

    return ativas

# ── Bloco de uma fonte de dados ───────────────────────────────────────────────
def bloco_fonte(s, nome, emoji, prefixo):
    """Retorna lista de (label, valor) para exibição de uma fonte."""
    status_v  = c(s, f"{prefixo}0")
    arq_sel   = c(s, f"{prefixo}1")
    arq_alt   = c(s, f"{prefixo}2")
    tam_sel   = c(s, f"{prefixo}3")
    tam_proc  = c(s, f"{prefixo}4")
    tam_env   = c(s, f"{prefixo}5")
    tam_prot  = c(s, f"{prefixo}6")
    erros_v   = c(s, f"{prefixo}7")
    ultimo_ok = c(s, f"{prefixo}L")
    duracao_v = c(s, f"{prefixo}A")

    concluiu  = status_v in ("5","8")

    rows = []
    rows.append(("Status",            status_fmt(status_v) if status_v else "— Sem dados"))
    rows.append(("Último OK",         f"{dt(ultimo_ok)} ({dias_atras(ultimo_ok)})" if ultimo_ok else "—"))
    rows.append(("Duração sessão",    dur(duracao_v, concluiu)))
    rows.append(("SEP",""))
    if arq_sel:
        rows.append(("Arq. selecionados", n(arq_sel)))
    if arq_alt:
        rows.append(("Arq. atualizados",  n(arq_alt)))
        try:
            rows.append(("  % atualizados", f"{int(arq_alt)/int(arq_sel)*100:.1f}% do total"))
        except: pass
    rows.append(("Erros",             erros_fmt(erros_v) if erros_v else "0"))
    rows.append(("SEP",""))
    rows.append(("Tam. selecionado",  gb(tam_sel) if tam_sel else "—"))
    rows.append(("Tam. enviado",      gb(tam_env)  if tam_env else "—"))
    rows.append(("Tam. protegido",    gb(tam_prot) if tam_prot else "—"))
    try:
        e=int(tam_env); p=int(tam_proc)
        if p > 0 and e < p:
            rows.append(("Deduplicação", f"{(1-e/p)*100:.1f}% reduzido"))
    except: pass
    return rows

# ── Diagnóstico ───────────────────────────────────────────────────────────────
def gerar_diagnostico(s, fontes_ativas):
    problemas = []

    for nome, emoji, prefixo in fontes_ativas:
        status_v  = c(s, f"{prefixo}0")
        tam_sel   = c(s, f"{prefixo}3")
        tam_env   = c(s, f"{prefixo}5")
        tam_prot  = c(s, f"{prefixo}6")
        erros_v   = c(s, f"{prefixo}7")
        arq_sel   = c(s, f"{prefixo}1")
        arq_alt   = c(s, f"{prefixo}2")
        tam_proc  = c(s, f"{prefixo}4")

        if status_v == "2":
            problemas.append((
                f"❌ CRÍTICO",
                f"{emoji} {nome} — Sessão FALHOU",
                f"A última sessão de backup de {nome} não chegou ao fim. "
                f"Os dados NÃO foram copiados para o storage nesta rodada.",
                f"Verifique o log do agente. Causas comuns: disco cheio, serviço parado, "
                f"falha de rede com o storage ou timeout da sessão."
            ))
        elif status_v == "8":
            problemas.append((
                f"🟠 ATENÇÃO",
                f"{emoji} {nome} — Concluído COM ERROS",
                f"O backup de {nome} terminou mas alguns itens não puderam ser copiados. "
                f"Geralmente causado por arquivos travados, permissões insuficientes ou problemas no VSS.",
                f"Verifique quais itens geraram erro no log do agente e considere ajustar a seleção."
            ))

        try:
            if int(tam_env) == 0 and int(tam_sel) > 0:
                problemas.append((
                    f"❌ CRÍTICO",
                    f"{emoji} {nome} — Nenhum dado enviado ao storage",
                    f"Há {gb(tam_sel)} selecionados em {nome} mas 0 bytes foram enviados. "
                    f"O agente processou localmente mas não transmitiu ao storage.",
                    f"Verifique conectividade com o storage e se não há firewall bloqueando a saída."
                ))
        except: pass

        try:
            if int(tam_prot) <= 1 and int(tam_sel) > 0:
                problemas.append((
                    f"❌ CRÍTICO",
                    f"{emoji} {nome} — Tamanho protegido no storage = 0",
                    f"O storage registra zero bytes protegidos para {nome}. "
                    f"Os dados nunca chegaram ao destino ou foram removidos pela retenção.",
                    f"Confira se o dispositivo aponta para o storage correto e verifique a política de retenção."
                ))
        except: pass

        try:
            pct_proc = int(tam_proc)/int(tam_sel)*100
            if pct_proc < 50:
                problemas.append((
                    f"🟠 ATENÇÃO",
                    f"{emoji} {nome} — Apenas {pct_proc:.0f}% processado",
                    f"De {gb(tam_sel)} selecionados apenas {gb(tam_proc)} foram processados em {nome}. "
                    f"A sessão foi interrompida antes de terminar.",
                    f"Verifique agendamento conflitante ou desligamento da máquina durante o backup."
                ))
        except: pass

        try:
            pct_upd = int(arq_alt)/int(arq_sel)*100
            if pct_upd >= 99.5 and int(arq_sel) > 1000:
                problemas.append((
                    f"⚠️  AVISO",
                    f"{emoji} {nome} — Quase 100% dos itens marcados como alterados ({pct_upd:.1f}%)",
                    f"{n(arq_alt)} de {n(arq_sel)} itens identificados como novos/modificados em {nome}. "
                    f"Pode indicar perda do histórico de comparação (reinstalação do agente ou mudança de token).",
                    f"Se o agente foi reinstalado recentemente a primeira sessão completa é esperada e nas próximas deve normalizar."
                ))
        except: pass

        try:
            if int(erros_v) > 1_000_000_000:
                problemas.append((
                    f"⚠️  AVISO",
                    f"{emoji} {nome} — Contador de erros com overflow",
                    f"O campo de erros de {nome} retornou um número absurdamente grande, "
                    f"indicando um bug interno do agente Cove ao registrar o contador.",
                    f"Problema conhecido em algumas versões. Verifique se há atualização disponível para o agente."
                ))
        except: pass

    # Offline
    if esta_offline(s):
        problemas.append((
            f"🔌 OFFLINE",
            f"Dispositivo sem comunicação recente",
            f"O agente não registra backup bem-sucedido há mais de 3 dias e o status não é OK. "
            f"O dispositivo pode estar desligado, sem rede ou com o serviço parado.",
            f"Verifique se a máquina está ligada e se o serviço 'Backup Manager' está rodando. "
            f"Tente acessar remotamente para verificar o estado do agente."
        ))

    # Dias sem backup OK
    try:
        dias = (datetime.datetime.now().timestamp() - int(c(s,"TL"))) / 86400
        if 2 < dias <= 7:
            problemas.append((
                f"🟠 ATENÇÃO",
                f"Último backup bem-sucedido há {dias:.0f} dia(s)",
                f"O último backup OK foi em {dt(c(s,'TL'))}. "
                f"Mais de 2 dias sem backup OK é um sinal de alerta.",
                f"Verifique se a máquina ficou desligada ou se há falhas recorrentes no agendamento."
            ))
        elif dias > 7:
            problemas.append((
                f"❌ CRÍTICO",
                f"Sem backup bem-sucedido há {dias:.0f} dias",
                f"O último backup OK foi em {dt(c(s,'TL'))}. "
                f"Mais de uma semana sem backup — dados completamente desprotegidos.",
                f"Ação imediata: verifique se o agente está instalado e rodando e se há comunicação com o storage."
            ))
    except: pass

    return problemas

# ── Tela de pesquisa ──────────────────────────────────────────────────────────
def tela_pesquisa(dispositivos):
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        topo()
        print(f"   {'🔎  PESQUISA DE DISPOSITIVO':^{TW}}")
        topo("─")
        print()
        print(f"   Digite o nome do dispositivo, computador ou cliente.")
        print(f"   Deixe em branco e ENTER para voltar ao carrossel.")
        print(f"   Total disponível: {len(dispositivos)} dispositivos")
        print()
        try:
            termo = input("   🔎  Buscar: ").strip().lower()
        except: return True
        if not termo: return True

        resultados = []
        for dev in dispositivos:
            s = dev.get("Settings") or []
            if (termo in (c(s,"I1") or "").lower() or
                termo in (c(s,"I18") or "").lower() or
                termo in (c(s,"I8") or "").lower()):
                resultados.append(dev)

        if not resultados:
            print(f"\n   ⚠️  Nenhum resultado para '{termo}'. ENTER para tentar novamente.")
            input(); continue

        if len(resultados) > 1:
            os.system("cls" if os.name == "nt" else "clear")
            topo()
            print(f"   {'🔎  RESULTADOS':^{TW}}")
            topo("─")
            print(f"\n   {len(resultados)} dispositivo(s) encontrado(s):\n")
            print(f"   {'#':<4} {'Nome':<35} {'Computador':<25} {'Cliente':<25} {'Status'}")
            print(f"   {'─'*TW}")
            for i, dev in enumerate(resultados, 1):
                s = dev.get("Settings") or []
                print(f"   {i:<4} {c(s,'I1')[:33]:<35} {c(s,'I18')[:23]:<25} {c(s,'I8')[:23]:<25} {status_fmt(c(s,'T0'))}")
            print(f"\n   Número para ver o dispositivo ou ENTER para nova busca: ", end="")
            try:
                escolha = input().strip()
            except: return True
            if not escolha: continue
            try:
                dev_escolhido = resultados[int(escolha)-1]
            except: continue
        else:
            dev_escolhido = resultados[0]

        exibir(dev_escolhido, 1, 1, "pesquisa", False)
        print(f"\n   P = Nova pesquisa   ENTER = Voltar ao carrossel")
        try:
            acao = input("   → ").strip().lower()
        except: return True
        if acao == "p": continue
        return True

# ── Telas ─────────────────────────────────────────────────────────────────────
def tela_loading():
    os.system("cls" if os.name == "nt" else "clear")
    topo()
    print(f"   {'':^{TW}}")
    print(f"   {'N-ABLE COVE  —  MONITOR DE BACKUP':^{TW}}")
    print(f"   {'':^{TW}}")
    topo()

def tela_resumo(dispositivos):
    os.system("cls" if os.name == "nt" else "clear")
    total    = len(dispositivos)
    criticos = [d for d in dispositivos if prioridade_dispositivo(d) == 0]
    offline  = [d for d in dispositivos if prioridade_dispositivo(d) == 1]
    avisos   = [d for d in dispositivos if prioridade_dispositivo(d) == 2]
    oks      = [d for d in dispositivos if prioridade_dispositivo(d) == 3]

    topo()
    print(f"   {'N-ABLE COVE  —  RESUMO GERAL':^{TW}}")
    topo("─")
    print()
    lc = TW // 5 - 2
    cards = [
        ("TOTAL",       str(total),         "⬜"),
        ("❌  ERRO",     str(len(criticos)), "🔴"),
        ("🔌  OFFLINE",  str(len(offline)),  "⚫"),
        ("🟠  AVISO",   str(len(avisos)),   "🟡"),
        ("✅  OK",       str(len(oks)),      "🟢"),
    ]
    t1=t2=t3=t4="   "
    for label,valor,ico in cards:
        t1 += f"┌{'─'*lc}┐  "; t2 += f"│{label:^{lc}}│  "
        t3 += f"│{f'{ico} {valor}':^{lc}}│  "; t4 += f"└{'─'*lc}┘  "
    for t in [t1,t2,t3,t4]: print(t)
    print()

    problematicos = [d for d in dispositivos if prioridade_dispositivo(d) <= 2]
    if problematicos:
        municipio_atual = None
        print(f"   ❌  Dispositivos que precisam de atenção ({len(problematicos)}) — por município:\n")
        print(f"   {'─'*TW}")
        for d in problematicos[:20]:
            s   = d.get("Settings") or []
            mun = extrair_municipio(d)
            if mun != municipio_atual:
                if municipio_atual is not None: print(f"   │")
                print(f"   │  📍 {mun}")
                municipio_atual = mun
            prio = prioridade_dispositivo(d)
            tag  = {0:"❌ ERRO",1:"🔌 OFFLINE",2:"🟠 AVISO"}.get(prio,"")
            print(f"   │     {tag:<12} {c(s,'I1')[:35]:<36} {c(s,'I8')[:30]}")
        if len(problematicos) > 20:
            print(f"   │  ... e mais {len(problematicos)-20} dispositivo(s)")
        print(f"   {'─'*TW}")

    print()
    m_c,s_c = divmod(TEMPO_CRITICO,60); m_n,s_n = divmod(TEMPO_NORMAL,60)
    print(f"   ▶  Erros/Offline/Avisos primeiro → agrupados por município → OK")
    print(f"   ▶  Com problema: {m_c:02d}:{s_c:02d} por dispositivo   │   OK: {m_n:02d}:{s_n:02d} por dispositivo")
    print(f"   ▶  P+ENTER a qualquer momento para pesquisar   │   Ctrl+C para encerrar")
    print()
    time.sleep(4)

# ── Exibe um dispositivo ──────────────────────────────────────────────────────
def exibir(dev, idx, total, rodada, tem_erro):
    os.system("cls" if os.name == "nt" else "clear")
    s      = dev.get("Settings") or []
    agora  = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    municipio = extrair_municipio(dev)
    prio   = prioridade_dispositivo(dev)
    icone_nivel = {0:"❌",1:"🔌",2:"🟠",3:"✅"}.get(prio,"⬜")

    fontes_ativas = detectar_fontes_ativas(s)
    nomes_fontes  = [f"{e} {n}" for n,e,_ in fontes_ativas]

    topo()
    print(f"   {'N-ABLE COVE  —  MONITOR DE BACKUP  ' + icone_nivel:^{TW}}")
    topo("─")
    print(f"   Rodada #{rodada}   {agora}   Dispositivo {idx}/{total}   📍 {municipio}")
    DOTS_W = TW - 2
    pos = int((idx-1)/max(total-1,1)*(DOTS_W-1))
    print(f"   {'·'*pos}●{'·'*(DOTS_W-pos-1)}")
    tag = {
        0:"   🔴  PRIORIDADE ALTA — DISPOSITIVO COM ERRO — REQUER ATENÇÃO IMEDIATA",
        1:"   🔌  DISPOSITIVO OFFLINE — Sem comunicação há mais de 3 dias",
        2:"   🟠  ATENÇÃO — Backup concluído com erros",
        3:"   🟢  Backup operando normalmente",
    }.get(prio,"   ⬜  Status desconhecido")
    print(tag)
    print(f"   Pressione P + ENTER para pesquisar um dispositivo específico")
    topo("─")

    # ── Dispositivo + Status Geral ────────────────────────────────────────────
    cab2("DISPOSITIVO","STATUS GERAL","🖥  ","📊  ")
    row2("Nome",          c(s,"I1")[:30],   "Situação atual",   status_fmt(c(s,"T0")))
    row2("Computador",    c(s,"I18")[:30],  "Último backup OK", f"{dt(c(s,'TL'))} ({dias_atras(c(s,'TL'))})")
    row2("Cliente",       c(s,"I8")[:30],   "Selecionado",      gb(c(s,"T3")))
    row2("Sistema",       c(s,"I16")[:30],  "Processado",       gb(c(s,"T4")))
    row2("Agente",        c(s,"I17")[:30],  "Enviado",          gb(c(s,"T5")))
    row2("Storage usado", gb(c(s,"I14")),   "Protegido total",  gb(c(s,"T6")))
    row2("Município",     municipio[:30],   "Fontes ativas",    ", ".join(nomes_fontes)[:30])
    fim2()

    # ── Fontes em pares de 2 colunas ─────────────────────────────────────────
    # Divide as fontes em pares para exibição lado a lado
    i = 0
    while i < len(fontes_ativas):
        if i + 1 < len(fontes_ativas):
            # Par de fontes lado a lado
            n1, e1, p1 = fontes_ativas[i]
            n2, e2, p2 = fontes_ativas[i+1]
            cab2(n1, n2, e1+"  ", e2+"  ")
            rows1 = bloco_fonte(s, n1, e1, p1)
            rows2 = bloco_fonte(s, n2, e2, p2)
            max_r = max(len(rows1), len(rows2))
            for j in range(max_r):
                l1=v1=l2=v2=""
                if j < len(rows1): l1,v1 = rows1[j]
                if j < len(rows2): l2,v2 = rows2[j]
                if l1=="SEP" or l2=="SEP": sep2(); continue
                esq = f"   ║  {l1:<20} {str(v1):<16}"
                dir = f"   ║  {l2:<20} {str(v2)}"
                print(f"{esq:<{CW+7}}   {dir}")
            fim2()
            i += 2
        else:
            # Fonte solitária — ocupa largura total
            n1, e1, p1 = fontes_ativas[i]
            cab(n1, e1+"  ")
            for l, v in bloco_fonte(s, n1, e1, p1):
                if l == "SEP": print(f"   ╟{'─'*(TW-2)}╢"); continue
                row(l, v)
            fim()
            i += 1

    if not fontes_ativas:
        cab("FONTES DE DADOS","⚠️  ")
        row("Aviso", "Nenhuma fonte de dados ativa detectada para este dispositivo.")
        fim()

    # ── Transferência animada — apenas F&F e Network Shares se existirem ─────
    fontes_com_tam = [(n,e,p) for n,e,p in fontes_ativas
                     if c(s,f"{p}3") and int(c(s,f"{p}3") or 0) > 0]
    if fontes_com_tam:
        cab("TRANSFERÊNCIA DE DADOS","📤  ")
        for nome_f, emoji_f, pref_f in fontes_com_tam:
            tam_sel_f = c(s, f"{pref_f}3")
            tam_proc_f = c(s, f"{pref_f}4")
            tam_env_f  = c(s, f"{pref_f}5")
            row(f"{emoji_f} {nome_f} — Selecionado", gb(tam_sel_f))
            barra_animada(f"  Processado",   tam_proc_f, tam_sel_f)
            barra_animada(f"  Enviado (novo)", tam_env_f, tam_sel_f)
        fim()

    # ── Calendário combinado de todas as fontes ──────────────────────────────
    # Coleta barras de todas as fontes ativas para combinar em uma visão unificada
    # igual à plataforma web que mostra sessões de todas as fontes juntas
    barras_fontes = []

    # Barras no formato novo (D1F8, D2F8)
    barra_d1 = c(s,"D1F8") or c(s,"F8")
    barra_d2 = c(s,"D2F8") or c(s,"S8")
    if barra_d1: barras_fontes.append(barra_d1)
    if barra_d2: barras_fontes.append(barra_d2)

    # Barras legadas de outras fontes (N8=NetworkShares, W8=VMware, H8=HyperV, etc.)
    for pref in ["N","W","H","Z","X","P","Y","L","G","J"]:
        b = c(s, f"{pref}8")
        if b: barras_fontes.append(b)

    if barras_fontes:
        # Combina todas as barras: para cada dia usa o melhor status entre as fontes
        barra_combinada = combinar_barras(*barras_fontes)

        # Monta título mostrando quais fontes estão no histórico
        nomes_hist = []
        if barra_d1: nomes_hist.append("📁 F&F")
        if barra_d2: nomes_hist.append("🗄 System State")
        for pref, nome in [("N","🌐 Net Shares"),("W","🖥 VMware"),("H","💠 Hyper-V")]:
            if c(s, f"{pref}8"): nomes_hist.append(nome)
        titulo_hist = "HISTÓRICO — ÚLTIMOS 28 DIAS"
        if len(nomes_hist) > 1:
            titulo_hist += f"  ({' + '.join(nomes_hist[:3])})"
        elif nomes_hist:
            titulo_hist += f"  ({nomes_hist[0]})"

        cab(titulo_hist,"📅  ")
        print(f"   ║   ✅ Concluído    🟠 Com erros / Interrompido    ❌ Falhou / Abortado    ░░ Sem backup")
        linha_cheia()
        for l in calendario(barra_combinada):
            print(f"   ║   {l}")

        # Se houver múltiplas fontes, mostra as barras individuais também
        if len(barras_fontes) > 1:
            linha_cheia()
            print(f"   ║   Detalhe por fonte:")
            if barra_d1:
                resumo = "".join({"5":"✅","8":"🟠","2":"❌","0":"░","7":"░","1":"🔄"}.get(ch,"░") for ch in barra_d1[-14:])
                print(f"   ║     📁 Files & Folders (14d):  {resumo}")
            if barra_d2:
                resumo = "".join({"5":"✅","8":"🟠","2":"❌","0":"░","7":"░","1":"🔄"}.get(ch,"░") for ch in barra_d2[-14:])
                print(f"   ║     🗄 System State   (14d):  {resumo}")

        fim()

    # ── Diagnóstico ───────────────────────────────────────────────────────────
    cab("DIAGNÓSTICO DETALHADO","🔍  ")
    problemas = gerar_diagnostico(s, fontes_ativas)

    if not problemas:
        linha_cheia()
        print(f"   ║  ✅  TUDO OK — Todas as fontes funcionando corretamente.")
        print(f"   ║  Todos os dados foram processados e enviados ao storage.")
        print(f"   ║  Nenhuma ação necessária.")
        linha_cheia()
    else:
        for i, (nivel_d, titulo, explicacao, acao) in enumerate(problemas):
            if i > 0: linha_cheia()
            print(f"   ║  {nivel_d}  {titulo}")
            print(f"   ║")
            for l in quebrar_texto(explicacao):
                print(f"   ║     📋  {l}")
            print(f"   ║")
            for l in quebrar_texto(acao):
                print(f"   ║     🔧  {l}")
    fim()

# ── Loop principal ─────────────────────────────────────────────────────────────
rodada = 0; visa = None; pid = None

try:
    while True:
        tela_loading(); print()
        spinner("Autenticando na API N-able Cove...", 1.5)
        if visa is None or rodada % 5 == 0:
            visa, pid = login()
        wave_loading("Buscando dispositivos...", 2.0)
        spinner("Carregando estatísticas de backup...", 1.5)
        dispositivos, visa = fetch_todos(visa, pid)
        rodada += 1

        dispositivos = ordenar_dispositivos(dispositivos)
        tela_resumo(dispositivos)
        total = len(dispositivos)

        for idx, dev in enumerate(dispositivos, 1):
            prio     = prioridade_dispositivo(dev)
            tem_erro = prio <= 2
            tempo    = TEMPO_CRITICO if tem_erro else TEMPO_NORMAL
            exibir(dev, idx, total, rodada, tem_erro)
            countdown_com_pesquisa(tempo, idx, total, tem_erro, dispositivos)

except KeyboardInterrupt:
    print(f"\n\n   Monitoramento encerrado.")
except Exception as e:
    print(f"\n   ❌ ERRO: {e}")
    import traceback; traceback.print_exc()

input("\n   Pressione ENTER para fechar...")
