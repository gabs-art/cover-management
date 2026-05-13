import requests
import datetime
import time
import os
import threading
# msvcrt importado condicionalmente abaixo quando necessário

PARTNER  = "Trust IT (claudiney.alves@confiancaetecnologia.com.br)"
USERNAME = "Trust"
PASSWORD = "jHe%8R49B1ng#&Ql?7^#p8go"
URL      = "https://api.backup.management/jsonapi"

TEMPO_CRITICO = 480
TEMPO_NORMAL  = 330
TW = 118

FONTES_DEF = {
    "D01":("Files & Folders","F","📁"), "D1":("Files & Folders","F","📁"),
    "D02":("System State","S","🗄"),    "D2":("System State","S","🗄"),
    "D06":("Network Shares","N","🌐"),  "D6":("Network Shares","N","🌐"),
    "D03":("MS SQL","Z","🗃"),          "D3":("MS SQL","Z","🗃"),
    "D04":("VSS Exchange","X","📧"),    "D4":("VSS Exchange","X","📧"),
    "D05":("M365 SharePoint","P","📋"), "D5":("M365 SharePoint","P","📋"),
    "D08":("VMware","W","🖥"),          "D8":("VMware","W","🖥"),
    "D10":("VSS MS SQL","Z","🗃"),
    "D11":("VSS SharePoint","P","📋"),
    "D12":("Oracle","Y","🔶"),
    "D14":("Hyper-V","H","💠"),
    "D15":("MySQL","L","🐬"),
    "D17":("Bare Metal Restore","B","💾"),
    "D19":("M365 Exchange","G","📨"),
    "D20":("M365 OneDrive","J","☁"),
}

PRIORIDADE_STATUS = {"5":0,"8":1,"6":2,"9":3,"2":4,"3":5,"1":6,"0":7,"7":8}

def login():
    r = requests.post(URL, json={
        "jsonrpc":"2.0","method":"Login","id":"1",
        "params":{"partner":PARTNER,"username":USERNAME,"password":PASSWORD}
    }, timeout=15).json()
    return r.get("visa"), r["result"]["result"]["PartnerId"]

def fetch_todos(visa, partner_id):
    colunas_base = [
        "I1","I8","I18","I16","I17","I14","I78",
        "T0","TL","T3","T4","T5","T6",
        "D1F8","D2F8",
    ]
    prefixos = ["F","S","N","Z","X","P","Y","W","H","L","G","J"]
    colunas_fontes = []
    for pref in prefixos:
        for campo in ["0","1","2","3","4","5","6","7","A","L"]:
            colunas_fontes.append(f"{pref}{campo}")
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
        # Contador ao vivo durante o carregamento
        criticos_até_agora = sum(1 for d in todos if status_nivel(c(d.get("Settings") or [],"T0"))=="CRITICO")
        print(f"\r   ⠿  Carregando... {len(todos)} dispositivos encontrados"
              f"  |  ❌ {criticos_até_agora} com erro", end="", flush=True)
        if len(lote) < batch: break
        start += batch
    print(f"\r   ✅  {len(todos)} dispositivos carregados"+" "*30, flush=True)
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
    """
    Considera offline se: último backup OK > 3 dias E não está concluído nem em andamento.
    T0=1 (em andamento) nunca é offline — está ativo agora.
    T0=5 (OK) nunca é offline — acabou de concluir.
    """
    try:
        tl   = int(c(s,"TL"))
        t0   = c(s,"T0")
        dias = (datetime.datetime.now().timestamp() - tl) / 86400
        # Não é offline se: concluiu recentemente OU está rodando agora
        if t0 in ("5","1"): return False
        return dias > 3
    except: return False

STATUS = {
    "1": ("🔄","EM ANDAMENTO","NEUTRO"),   # Sessão rodando agora
    "2": ("❌","FALHOU","CRITICO"),         # Falha total
    "3": ("⛔","ABORTADO","CRITICO"),       # Abortado manualmente
    "5": ("✅","CONCLUÍDO","OK"),           # Sucesso
    "6": ("🟠","INTERROMPIDO","AVISO"),    # Interrompido (ex: desligamento)
    "7": ("⬜","NÃO INICIADO","NEUTRO"),   # Nunca rodou
    "8": ("🟠","COM ERROS","AVISO"),       # Terminou mas com erros parciais
    "9": ("🟡","COM FALHAS","AVISO"),      # Em andamento com falhas parciais
    "10":("🔴","COTA EXCEDIDA","CRITICO"), # Storage cheio
    "0": ("⬜","SEM DADOS","NEUTRO"),      # Fonte sem dados ainda
}
# T0=EmAndamento (1) + fontes já concluídas = normal — uma fonte ainda está rodando
# T0 sempre reflete o status GERAL (pior/atual entre todas as fontes)
def status_fmt(v):
    if not v: return "⬜ DESCONHECIDO"
    ico, label, _ = STATUS.get(v, ("❓", str(v), "NEUTRO"))
    return f"{ico} {label}"

def status_fmt_fonte(sv, t0_geral):
    """
    Formata o status de uma fonte individual com contexto do T0 geral.
    Se T0=EmAndamento e a fonte=OK, explica que outra fonte ainda está rodando.
    """
    if not sv: return "⬜ SEM DADOS"
    ico, label, _ = STATUS.get(sv, ("❓", str(sv), "NEUTRO"))
    resultado = f"{ico} {label}"
    # Contexto extra quando T0=EmAndamento mas esta fonte já concluiu
    if t0_geral == "1" and sv == "5":
        resultado += " (outra fonte em andamento)"
    return resultado

def status_nivel(v):
    return STATUS.get(v, ("","","NEUTRO"))[2]

def extrair_municipio(dev):
    cliente = c(dev.get("Settings") or [], "I8") or ""
    for p in ["PM_","CM_","Prefeitura_","Camara_","Prefeitura ","Camara "]:
        if cliente.startswith(p): cliente = cliente[len(p):]
    return cliente.strip().upper() or "ZZZZZ"

def prioridade_dispositivo(dev):
    """
    Determina a prioridade de exibição do dispositivo.
    T0=EmAndamento (1): verifica fontes individuais para prioridade real.
    T0 pode ser OK mas uma fonte secundária estar falhando.
    """
    s     = dev.get("Settings") or []
    t0    = c(s,"T0")
    nivel = status_nivel(t0)

    # Crítico direto
    if nivel == "CRITICO": return 0

    # Offline — sem backup há mais de 3 dias
    if esta_offline(s): return 1

    # Aviso direto
    if nivel == "AVISO": return 2

    # T0=OK mas verifica se alguma fonte individual tem erro
    # Ex: T0=5(OK) mas H=2(Hyper-V falhou)
    if nivel == "OK":
        FONTES_PREF = ["F","S","N","Z","X","W","H","L","G","J","Y","B"]
        for pref in FONTES_PREF:
            sv = c(s,f"{pref}0")
            ts = c(s,f"{pref}3")
            if sv in ("2","3") and ts:
                try:
                    if int(ts) > 0: return 2  # fonte com erro → aviso
                except: pass
        return 3

    # T0=EmAndamento (1): backup rodando agora
    # Não é erro — apenas monitora normalmente
    if t0 == "1": return 3

    return 4

def ordenar_dispositivos(dispositivos):
    prob = [d for d in dispositivos if prioridade_dispositivo(d) <= 2]
    norm = [d for d in dispositivos if prioridade_dispositivo(d) >  2]
    prob.sort(key=lambda d: (extrair_municipio(d), prioridade_dispositivo(d)))
    norm.sort(key=lambda d: (extrair_municipio(d), prioridade_dispositivo(d)))
    return prob + norm

def combinar_barras(*barras):
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
    Calendário preciso — cada dia alinhado exatamente ao dia da semana correto.
    - Último char da barra = hoje
    - Primeiro char = hoje - (len(barra)-1) dias
    - Alinhamento baseado no dia da semana real do primeiro dia
    """
    if not barra:
        return ["  Sem dados de histórico disponíveis."]

    hoje    = datetime.date.today()
    ini     = hoje - datetime.timedelta(days=len(barra)-1)
    dow_cal = (ini.weekday() + 1) % 7   # 0=Dom ... 6=Sab

    # Status → (ícone, rótulo curto)
    COR = {
        "5": ("✅", "OK "),
        "8": ("🟠", "ERR"),
        "6": ("🟠", "INT"),
        "9": ("🟠", "FAL"),
        "2": ("❌", "FLH"),
        "3": ("❌", "ABT"),
        "1": ("🔄", "..."),
        "0": ("  ", "---"),
        "7": ("  ", "---"),
    }

    COLS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"]
    CW   = 7   # largura fixa de cada célula

    # Monta lista de células: None para dias vazios no início
    celulas = [None] * dow_cal
    for i, ch in enumerate(barra):
        celulas.append((ini + datetime.timedelta(days=i), ch))
    # Preenche até completar a última semana
    while len(celulas) % 7 != 0:
        celulas.append(None)

    semanas = [celulas[i:i+7] for i in range(0, len(celulas), 7)]

    out = []

    # Cabeçalho fixo
    out.append("  " + "".join(f"  {col:<5}" for col in COLS))
    out.append("  " + ("─" * (CW * 7)))

    for semana in semanas:
        row_ico = "  "   # linha dos ícones de status
        row_dia = "  "   # linha dos números dos dias

        for cel in semana:
            if cel is None:
                row_ico += " " * CW
                row_dia += " " * CW
            else:
                d, ch = cel
                ico, lbl = COR.get(ch, ("  ", "---"))
                eh_hoje  = (d == hoje)
                # Dia atual: colchetes + negrito visual
                dia_str  = f"[{d.day}]" if eh_hoje else f" {d.day} "
                row_ico += f" {ico} {lbl} "   # 7 chars: spc ico spc lbl spc
                row_dia += f"  {dia_str:<5}"  # 7 chars: 2 spc + dia + pad

        out.append(row_ico)
        out.append(row_dia)
        out.append("  " + ("─" * (CW * 7)))

    return out


def calendario_footer(barras_dict, fontes_ativas):
    """
    Rodapé do calendário com detalhe por fonte e resumo estatístico.
    barras_dict = {"📁 Files & Folders": "55555...", "🗄 System State": "55555..."}
    """
    ICO = {"5":"✅","8":"🟠","6":"🟠","9":"🟠","2":"❌","3":"❌","1":"🔄","0":"░","7":"░"}
    out = []

    if not barras_dict:
        return out

    out.append("  Detalhe por fonte — últimos 14 dias:")

    hoje = datetime.date.today()
    datas_14 = [(hoje - datetime.timedelta(days=13-i)) for i in range(14)]
    header   = "  " + " " * 26 + "".join(f"{d.day:>3}" for d in datas_14)
    out.append(header)
    out.append("  " + " " * 26 + "  " + "─" * 41)

    resumo_combinado = {}  # date → best status

    for nome_fonte, barra in barras_dict.items():
        if not barra: continue

        # Mapeia cada char da barra ao dia correspondente
        ini_b  = hoje - datetime.timedelta(days=len(barra)-1)
        dia_map = {}
        for i, ch in enumerate(barra):
            d = ini_b + datetime.timedelta(days=i)
            dia_map[d] = ch

        # Últimos 14 dias
        icons = ""
        for d in datas_14:
            ch  = dia_map.get(d, "0")
            ico = ICO.get(ch, "░")
            icons += f"  {ico}"
            # Combina para resumo
            if d not in resumo_combinado:
                resumo_combinado[d] = ch
            else:
                # Mantém o melhor status
                PRIO = {"5":0,"8":1,"6":2,"9":3,"2":4,"3":5,"1":6,"0":7,"7":8}
                if PRIO.get(ch,9) < PRIO.get(resumo_combinado[d],9):
                    resumo_combinado[d] = ch

        # Trunca nome para caber
        nome_curto = nome_fonte[:24]
        out.append(f"  {nome_curto:<26}{icons}")

    # Linha de resumo combinado
    if len(barras_dict) > 1:
        out.append("  " + " " * 26 + "  " + "─" * 41)
        icons_comb = "".join(f"  {ICO.get(resumo_combinado.get(d,'0'),'░')}" for d in datas_14)
        out.append(f"  {'  Combinado':<26}{icons_comb}")

    # Estatísticas dos últimos 28 dias — usa maior barra disponível
    maior_barra = max(barras_dict.values(), key=len, default="")
    if maior_barra:
        from collections import Counter
        ultimos28 = maior_barra[-28:]
        ct = Counter(ultimos28)
        ok     = ct.get("5",0)
        erros  = sum(ct.get(k,0) for k in "896")
        falhou = sum(ct.get(k,0) for k in "23")
        sem    = sum(ct.get(k,0) for k in "07")
        total  = ok+erros+falhou+sem
        out.append("")
        out.append(f"  Resumo 28 dias:  ✅ {ok} OK  ({ok/total*100:.0f}%)   "
                   f"🟠 {erros} com erros   ❌ {falhou} falhou   ░ {sem} sem backup")

    return out


# ── Animações ─────────────────────────────────────────────────────────────────
SPIN = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
WAVE = ["▁","▂","▃","▄","▅","▆","▇","█","▇","▆","▅","▄","▃","▂"]

def spinner(msg, seg=1.8):
    fim = time.time()+seg; i = 0
    while time.time()<fim:
        print(f"\r   {SPIN[i%len(SPIN)]}  {msg}", end="", flush=True)
        time.sleep(0.07); i += 1
    print(f"\r   ✅  {msg}          ", flush=True)

def wave_loading(msg, seg=2.0):
    fim = time.time()+seg; i = 0
    while time.time()<fim:
        onda = "".join(WAVE[(i+j)%len(WAVE)] for j in range(12))
        print(f"\r   {onda}  {msg}  {onda}", end="", flush=True)
        time.sleep(0.07); i += 1
    print(f"\r   {'─'*40}   ", flush=True)

def barra_animada(label, val, total, largura=28):
    try:    pct = min(int(val)/int(total), 1.0)
    except: pct = 0.0
    val_str = gb(val)
    for step in range(int(pct*largura)+1):
        bar = "█"*step+"░"*(largura-step)
        print(f"\r   │  {label:<20} {val_str:<10} [{bar}] {step/largura*100:.0f}%   ", end="", flush=True)
        time.sleep(0.018)
    bf = "█"*int(pct*largura)+"░"*(largura-int(pct*largura))
    print(f"\r   │  {label:<20} {val_str:<10} [{bf}] {pct*100:.1f}%   ", flush=True)

# ── Countdown com detecção de tecla P ────────────────────────────────────────
def countdown_com_pesquisa(seg, idx, total, tem_erro, dispositivos):
    """
    Countdown que detecta P sem bloquear — usa polling de teclado no Windows
    e thread não-bloqueante no Linux.
    """
    tecla_p = [False]

    # Cross-platform: thread com input() funciona em Windows e Linux
    def ouvir():
        try:
            entrada = input()
            if entrada.strip().lower() == "p":
                tecla_p[0] = True
        except: pass
    threading.Thread(target=ouvir, daemon=True).start()

    icone = "🔴" if tem_erro else "🟢"
    m_tot, s_tot = divmod(seg, 60)

    tick = [0]
    for s in range(seg, 0, -1):
        if tecla_p[0]: break
        m, sc  = divmod(s, 60)
        prog   = int((seg-s)/seg*50)
        tick[0] += 1

        # Efeito de pulso no bloco da frente da barra
        for micro in range(4):
            if tecla_p[0]: break
            # Pulso: bloco da frente alterna entre █ e ▓
            brilho = "▓" if micro % 2 == 0 else "█"
            if prog > 0:
                bar = "█"*(prog-1) + brilho + "░"*(50-prog)
            else:
                bar = "░"*50
            # Ícone pulsa no segundo crítico
            ico_atual = icone if micro % 2 == 0 or not tem_erro else "⚠️ "
            print(
                f"\r   {ico_atual}  Próximo em {m:02d}:{sc:02d}  (de {m_tot:02d}:{s_tot:02d})   [{bar}]   {idx}/{total}   [P = pesquisar]",
                end="", flush=True
            )

    print()

    if tecla_p[0]:
        tela_pesquisa(dispositivos)

# ── Layout ────────────────────────────────────────────────────────────────────
CW = (TW-5)//2

def topo(char="█"):   print(f"   {char*TW}")
def cab(t, e=""):
    pad = TW-len(t)-len(e)-8
    print(f"\n   ╔══ {e}{t} {'═'*max(pad,2)}╗")
def cab2(t1,t2,e1="",e2=""):
    p1=CW-len(t1)-len(e1)-6; p2=CW-len(t2)-len(e2)-6
    print(f"\n   ╔══ {e1}{t1} {'═'*max(p1,2)}╗   ╔══ {e2}{t2} {'═'*max(p2,2)}╗")
def row(l,v):   print(f"   ║  {l:<22} {v}")
def row2(l1,v1,l2,v2):
    esq=f"   ║  {l1:<20} {str(v1):<16}"
    print(f"{esq:<{CW+7}}   ║  {l2:<20} {str(v2)}")
def sep2():        print(f"   ╟{'─'*CW}╢   ╟{'─'*CW}╢")
def fim():         print(f"   ╚{'═'*(TW-2)}╝")
def fim2():        print(f"   ╚{'═'*CW}╝   ╚{'═'*CW}╝")
def sep_linha():   print(f"   ╟{'─'*(TW-2)}╢")
def linha_cheia(): print(f"   ║")

def quebrar(texto, larg=100):
    words=texto.split(); l=""; ls=[]
    for w in words:
        if len(l)+len(w)+1>larg: ls.append(l); l=w
        else: l=(l+" "+w).strip()
    if l: ls.append(l)
    return ls

# ── Detecta fontes ativas ─────────────────────────────────────────────────────
def detectar_fontes_ativas(s):
    fontes_raw = c(s,"I78") or ""
    ativas = []; vistas = set()
    for codigo,(nome,prefixo,emoji) in FONTES_DEF.items():
        if codigo in fontes_raw and nome not in vistas:
            ativas.append((nome,emoji,prefixo)); vistas.add(nome)
    extras = [
        ("N","Network Shares","🌐"),("Z","MS SQL","🗃"),("X","VSS Exchange","📧"),
        ("P","SharePoint","📋"),("Y","Oracle","🔶"),("W","VMware","🖥"),
        ("H","Hyper-V","💠"),("L","MySQL","🐬"),("G","M365 Exchange","📨"),("J","M365 OneDrive","☁"),
    ]
    for prefixo,nome,emoji in extras:
        if nome not in vistas and (c(s,f"{prefixo}0") or c(s,f"{prefixo}3")):
            ativas.append((nome,emoji,prefixo)); vistas.add(nome)
    return ativas

def bloco_fonte(s, nome, emoji, prefixo):
    t0    = c(s,"T0")   # status geral para contexto
    sv=c(s,f"{prefixo}0"); as_=c(s,f"{prefixo}1"); aa=c(s,f"{prefixo}2")
    ts=c(s,f"{prefixo}3"); tp=c(s,f"{prefixo}4"); te=c(s,f"{prefixo}5")
    tprot=c(s,f"{prefixo}6"); ev=c(s,f"{prefixo}7")
    ok=c(s,f"{prefixo}L"); dv=c(s,f"{prefixo}A")
    concluiu = sv in ("5","8")
    rows = [
        ("Status",         status_fmt_fonte(sv, t0) if sv else "— Sem dados"),
        ("Último OK",      f"{dt(ok)} ({dias_atras(ok)})" if ok else "—"),
        ("Duração sessão", dur(dv, concluiu)),
        ("SEP",""),
    ]
    if as_: rows.append(("Arq. selecionados", n(as_)))
    if aa:
        rows.append(("Arq. atualizados", n(aa)))
        try: rows.append(("  % atualizados", f"{int(aa)/int(as_)*100:.1f}% do total"))
        except: pass
    rows.append(("Erros", erros_fmt(ev) if ev else "0"))
    rows += [
        ("SEP",""),
        ("Tam. selecionado", gb(ts) if ts else "—"),
        ("Tam. enviado",     gb(te) if te else "—"),
        ("Tam. protegido",   gb(tprot) if tprot else "—"),
    ]
    try:
        e=int(te); p=int(tp)
        if p>0 and e<p: rows.append(("Deduplicação", f"{(1-e/p)*100:.1f}% reduzido"))
    except: pass
    return rows

# ── Diagnóstico com passos práticos ──────────────────────────────────────────
def gerar_diagnostico(s, fontes_ativas):
    """
    Diagnóstico sem falsos positivos.
    Cada verificação tem condições claras e considera o contexto completo.
    Retorna lista de (nivel, titulo, explicacao, passos[])
    """
    problemas = []
    alertas_gerados = set()  # evita duplicatas

    def add(nivel, titulo, exp, passos):
        chave = titulo[:50]
        if chave not in alertas_gerados:
            alertas_gerados.add(chave)
            problemas.append((nivel, titulo, exp, passos))

    # ── Helpers de contexto ───────────────────────────────────────────────────
    tl_ts      = int(c(s,"TL")) if c(s,"TL") else 0
    dias_sem_ok = (datetime.datetime.now().timestamp()-tl_ts)/86400 if tl_ts>0 else 99
    criado_ts  = int(c(s,"I4")) if c(s,"I4") else 0
    dias_criado = (datetime.datetime.now().timestamp()-criado_ts)/86400 if criado_ts>0 else 99
    # Dispositivo novo (<7 dias): pode ainda não ter completado o primeiro backup
    dispositivo_novo = dias_criado < 7

    t0_geral = c(s,"T0")  # status geral do dispositivo

    for nome, emoji, prefixo in fontes_ativas:
        sv    = c(s,f"{prefixo}0")   # status da sessão desta fonte
        as_   = c(s,f"{prefixo}1")   # arquivos selecionados
        aa    = c(s,f"{prefixo}2")   # arquivos alterados
        ts    = c(s,f"{prefixo}3")   # tamanho selecionado
        tp    = c(s,f"{prefixo}4")   # tamanho processado
        te    = c(s,f"{prefixo}5")   # tamanho enviado
        tprot = c(s,f"{prefixo}6")   # tamanho protegido
        ev    = c(s,f"{prefixo}7")   # erros
        ok_ts = c(s,f"{prefixo}L")   # timestamp último OK desta fonte
        dv    = c(s,f"{prefixo}A")   # duração

        def _i(v):
            try: return int(v) if v else 0
            except: return 0

        sv_int    = _i(sv)
        ts_int    = _i(ts)
        tp_int    = _i(tp)
        te_int    = _i(te)
        tprot_int = _i(tprot)
        as_int    = _i(as_)
        aa_int    = _i(aa)
        ev_int    = _i(ev)
        ok_ts_int = _i(ok_ts)

        dias_fonte_ok = (datetime.datetime.now().timestamp()-ok_ts_int)/86400 if ok_ts_int>0 else 99
        sessao_concluiu     = sv in ("5","8")
        sessao_ok           = sv == "5"
        sessao_com_erros    = sv == "8"
        sessao_falhou       = sv in ("2","3")
        sessao_interrompida = sv in ("6","9")
        sessao_em_andamento = sv == "1"
        sessao_nao_iniciada = sv in ("7","","0") or not sv

        # ── REGRAS ANTI-FALSO-POSITIVO ────────────────────────────────────────
        # 1. T0=EmAndamento + ESTA fonte=OK = normal, outra fonte ainda está rodando
        #    Não gerar alerta para esta fonte, pois ela já terminou bem
        fonte_ok_enquanto_outra_roda = (t0_geral == "1" and sv == "5")

        # 2. T0=EmAndamento + ESTA fonte=EmAndamento = backup em curso, não é erro
        esta_fonte_em_andamento = (sv == "1")

        # 3. Fonte sem dados (ts=0) = fonte configurada mas sem seleção ainda
        fonte_sem_selecao = ts_int == 0

        # Se esta fonte está ok enquanto outra ainda roda: pula diagnóstico dela
        if fonte_ok_enquanto_outra_roda:
            continue

        # Se esta fonte está em andamento: pula — não é erro
        if esta_fonte_em_andamento:
            continue

        # Se fonte não tem seleção: pula — não há o que diagnosticar
        if fonte_sem_selecao:
            continue

        # ── 1. Sessão falhou ─────────────────────────────────────────────────
        if sessao_falhou and not dispositivo_novo:
            add("❌ CRÍTICO",
                f"{emoji} {nome} — Sessão FALHOU",
                f"O backup de {nome} foi iniciado mas encerrou com falha total. "
                f"Nenhum dado novo chegou ao storage nesta rodada.",
                [
                    "1. Abra o Backup Manager na máquina → aba 'Visão Geral'",
                    "2. Clique no histórico e veja a mensagem de erro exata da última sessão",
                    "3. Disco cheio? Execute no CMD como admin:",
                    "   cleanmgr /sagerun:1",
                    "   Get-PSDrive C | Select-Object Used,Free",
                    "4. Serviço parado? Execute no CMD como admin:",
                    "   net stop 'Backup Manager' && net start 'Backup Manager'",
                    "5. Problema de rede? Teste:",
                    "   ping br-sp-03-14.cloudbackup.management",
                    "   Test-NetConnection br-sp-03-14.cloudbackup.management -Port 443",
                    "6. Logs detalhados: C:\\ProgramData\\MXB\\Backup Manager\\logs\\",
                ]
            )

        # ── 2. Sessão COM ERROS (parcial) ────────────────────────────────────
        elif sessao_com_erros:
            # Conta erros reais (ignora overflow)
            erros_reais = ev_int if ev_int < 1_000_000_000 else None
            desc_erros  = f" ({n(str(erros_reais))} erros)" if erros_reais and erros_reais>0 else ""
            add("🟠 ATENÇÃO",
                f"{emoji} {nome} — Concluído COM ERROS{desc_erros}",
                f"O backup de {nome} terminou mas alguns arquivos não puderam ser copiados. "
                f"A maior parte dos dados está protegida — apenas os arquivos com erro ficaram sem backup.",
                [
                    "1. Backup Manager → aba 'Backup' → clique no ícone ⓘ ao lado da última sessão",
                    "2. Identifique quais arquivos falharam na lista de erros",
                    "3. Causa mais comum — arquivos em uso/travados. Adicione exclusões:",
                    "   Ex: *.tmp, *.log, ~$*.docx, *.ldf, pagefile.sys, hiberfil.sys",
                    "4. Se erro de VSS, execute no CMD como admin:",
                    "   vssadmin list writers",
                    "   Se writer com erro: net stop vss && net start vss",
                    "5. Antivírus bloqueando? Adicione o Backup Manager como exclusão",
                ]
            )

        # ── 3. Sessão INTERROMPIDA ────────────────────────────────────────────
        elif sessao_interrompida and not dispositivo_novo:
            add("🟠 ATENÇÃO",
                f"{emoji} {nome} — Sessão INTERROMPIDA",
                f"O backup de {nome} foi interrompido antes de terminar. "
                f"Os dados processados até o momento estão protegidos, mas a sessão não concluiu.",
                [
                    "1. Verifique se a máquina foi desligada/reiniciada durante o backup:",
                    "   eventvwr.msc → Logs do Windows → Sistema → evento ID 6006",
                    "2. Windows Update reiniciando? Desative reinicialização automática:",
                    "   Windows Update → Opções avançadas → desative 'Reinicialização automática'",
                    "3. Reinicie o serviço do agente:",
                    "   net stop 'Backup Manager' && net start 'Backup Manager'",
                    "4. Verifique se há tarefa agendada que mata o processo",
                ]
            )

        # ── 4. Pouco processado (< 10%) — só se sessão não OK e não em andamento
        if ts_int > 0 and tp_int >= 0 and not sessao_ok and not sessao_em_andamento and not dispositivo_novo:
            try:
                pct_proc = tp_int / ts_int * 100
                if pct_proc < 10 and not sessao_nao_iniciada:
                    add("🟠 ATENÇÃO",
                        f"{emoji} {nome} — Apenas {pct_proc:.0f}% processado antes de parar",
                        f"De {gb(ts)} selecionados somente {gb(tp)} foram lidos. "
                        f"A sessão foi interrompida muito cedo — provável problema de serviço ou rede.",
                        [
                            "1. Mais provável: máquina reiniciada durante o backup",
                            "   eventvwr.msc → Logs do Windows → Sistema → ID 6006",
                            "2. Reinicie o serviço: net stop 'Backup Manager' && net start 'Backup Manager'",
                            "3. Verifique conexão de rede durante o horário do backup",
                            "4. Logs: C:\\ProgramData\\MXB\\Backup Manager\\logs\\",
                        ]
                    )
                elif 10 <= pct_proc < 50 and not sessao_nao_iniciada:
                    add("🟠 ATENÇÃO",
                        f"{emoji} {nome} — Apenas {pct_proc:.0f}% do selecionado foi processado",
                        f"De {gb(ts)} selecionados apenas {gb(tp)} foram processados. "
                        f"Pode ter atingido o limite de tempo da sessão.",
                        [
                            "1. Verifique o limite de tempo configurado:",
                            "   Backup Manager → Preferências → 'Duração máxima da sessão'",
                            "2. Considere aumentar o limite ou reduzir a seleção de backup",
                            "3. Verifique se a conexão de rede é estável no horário do backup",
                            "4. Get-EventLog -LogName System -Source 'Tcpip' -Newest 20",
                        ]
                    )
            except: pass

        # ── 5. Nenhum dado enviado — com contexto completo ───────────────────
        if te_int == 0 and ts_int > 0 and not sessao_em_andamento:
            if sessao_ok and tprot_int > 0:
                # NORMAL: backup incremental sem alterações
                pass

            elif sessao_ok and tprot_int <= 1 and not dispositivo_novo:
                # Backup "concluiu" mas nada chegou ao storage nunca
                add("❌ CRÍTICO",
                    f"{emoji} {nome} — Status OK mas storage registra 0 bytes protegidos",
                    f"O agente reporta sucesso mas o storage não tem dados de {nome}. "
                    f"Indica problema de sincronização ou política de retenção zerada.",
                    [
                        "1. Verifique política de retenção: painel N-able → Dispositivo → Armazenamento",
                        "   O valor de retenção não deve ser 0 dias",
                        "2. Teste conectividade: Test-NetConnection br-sp-03-14.cloudbackup.management -Port 443",
                        "3. Force backup manual: Backup Manager → Executar Backup",
                        "4. Se persistir, acione o suporte N-able",
                    ]
                )

            elif sessao_falhou and dias_sem_ok > 2 and not dispositivo_novo:
                # Sessão falhou E nada foi enviado (não duplica com alerta #1 acima)
                # Alerta #1 já foi gerado, não precisa repetir
                pass

        # ── 6. Dados enviados mas protegido zerado (anomalia real) ───────────
        if te_int > 0 and tprot_int <= 1 and ts_int > 0 and sessao_concluiu and not dispositivo_novo:
            add("❌ CRÍTICO",
                f"{emoji} {nome} — Dados enviados mas storage registra 0 bytes",
                f"O agente enviou {gb(te)} mas o storage registra 0 bytes protegidos. "
                f"Anomalia de sincronização no storage.",
                [
                    "1. Verifique política de retenção no painel N-able",
                    "2. Force backup manual e aguarde: Backup Manager → Executar Backup",
                    "3. Se persistir após 2 sessões, acione suporte N-able",
                ]
            )

        # ── 7. Todos os arquivos como alterados (após contexto) ──────────────
        if as_int > 500 and aa_int > 0 and sessao_concluiu:
            try:
                pct_upd = aa_int / as_int * 100
                # Só alerta se > 99% E não é o primeiro backup (protegido já existia antes)
                if pct_upd >= 99.5 and tprot_int > 0 and not dispositivo_novo:
                    add("⚠️  AVISO",
                        f"{emoji} {nome} — {pct_upd:.0f}% dos arquivos marcados como alterados",
                        f"{n(str(aa_int))} de {n(str(as_int))} itens identificados como modificados. "
                        f"Indica perda do histórico de comparação (reinstalação do agente ou mudança de token).",
                        [
                            "1. Se agente foi reinstalado recentemente: aguarde — próximas sessões normalizam",
                            "2. Caso contrário, recrie o índice de comparação:",
                            "   Backup Manager → Preferências → Avançado → Recriar Índice",
                            "3. Alternativa via CMD como admin:",
                             "   cd 'C:\\Program Files\\MXB\\Backup Manager'",
                            "   BackupFP.exe -reindex",
                        ]
                    )
            except: pass

        # ── 8. Overflow de erros (informativo, não crítico) ──────────────────
        if ev_int > 1_000_000_000 and sessao_ok:
            # Só avisa se o backup está OK — caso contrário o alerta de falha é mais importante
            add("⚠️  AVISO",
                f"{emoji} {nome} — Contador de erros com valor inválido",
                f"O campo de erros tem um número absurdo — bug cosmético do agente. "
                f"Não afeta o backup enquanto o status for Concluído.",
                [
                    "1. Bug conhecido — verifique se há atualização do agente disponível",
                    "2. Painel N-able → Dispositivo → Ações → Atualizar Agente",
                    "3. Se já está na versão mais recente, apenas monitore o status geral",
                ]
            )

    # ── System State — verificação dedicada ──────────────────────────────────
    ss_sv = c(s,"S0")
    if ss_sv == "2" and not dispositivo_novo:
        add("❌ CRÍTICO",
            "🗄 System State — Sessão FALHOU",
            "O backup do estado do sistema (registro, boot, configurações) falhou. "
            "Sem ele, a restauração completa do sistema pode não ser possível.",
            [
                "1. Verifique o VSS no CMD como admin:",
                "   vssadmin list writers",
                "   Todos devem estar 'Estável' — se não:",
                "   net stop vss && net start vss",
                "   net stop swprv && net start swprv",
                "2. Espaço em disco (VSS precisa de ao menos 10% livre):",
                "   Get-PSDrive C | Select-Object Used,Free",
                "3. Integridade do sistema:",
                "   sfc /scannow",
                "4. Eventos de erro VSS:",
                "   eventvwr.msc → Logs do Windows → Aplicativo → filtrar por 'VSS'",
            ]
        )

    # ── Offline ───────────────────────────────────────────────────────────────
    if esta_offline(s) and not dispositivo_novo:
        add("🔌 OFFLINE",
            "Dispositivo sem comunicação há mais de 3 dias",
            "O agente não registra backup bem-sucedido há mais de 3 dias. "
            "Máquina desligada, sem rede ou serviço parado.",
            [
                "1. Verifique se a máquina está ligada e acessível na rede",
                "2. Acesse via RDP/VNC e verifique o serviço:",
                "   services.msc → 'Backup Manager' → deve estar 'Em execução'",
                "3. Se parado: net start 'Backup Manager'",
                "4. Se não existir (desinstalado): painel N-able → Dispositivo → Instalar Agente",
                "5. Teste conectividade: ping br-sp-03-14.cloudbackup.management",
            ]
        )

    # ── T0=OK mas fonte individual com erro — alerta específico ────────────────
    if not dispositivo_novo:
        FONTES_PREF = [("F","Files & Folders","📁"),("S","System State","🗄"),
                       ("N","Network Shares","🌐"),("Z","MS SQL","🗃"),
                       ("X","VSS Exchange","📧"),("W","VMware","🖥"),
                       ("H","Hyper-V","💠"),("L","MySQL","🐬")]
        t0_g = c(s,"T0")
        if t0_g == "5":  # T0 diz OK mas...
            for pref, nome_f, emo_f in FONTES_PREF:
                sv_f = c(s,f"{pref}0")
                ts_f = c(s,f"{pref}3")
                if sv_f in ("2","3") and ts_f:
                    try:
                        if int(ts_f) > 0:
                            add("🟠 ATENÇÃO",
                                f"{emo_f} {nome_f} — Falhou enquanto outras fontes concluíram",
                                f"O status geral aparece como OK porque outras fontes concluíram, "
                                f"mas {nome_f} falhou nesta sessão. Os dados desta fonte não foram atualizados.",
                                [
                                    f"1. Verifique especificamente o {nome_f} no Backup Manager",
                                    "2. Backup Manager → Histórico → filtre por esta fonte",
                                    "3. Veja a mensagem de erro específica desta fonte",
                                    "4. Resolva o problema e force um backup manual",
                                ]
                            )
                    except: pass

    # ── Dias sem backup OK — só se não há outro alerta crítico de sessão ─────
    tem_critico_sessao = any("Sessão FALHOU" in t or "INTERROMPIDA" in t or "OFFLINE" in t
                             for _,t,_,_ in problemas)
    try:
        if not tem_critico_sessao and not dispositivo_novo:
            if 2 < dias_sem_ok <= 7:
                add("🟠 ATENÇÃO",
                    f"Último backup bem-sucedido há {dias_sem_ok:.0f} dia(s)",
                    f"O último backup OK foi em {dt(c(s,'TL'))}. "
                    f"Mais de 2 dias sem backup OK merece verificação.",
                    [
                        "1. Verifique se a máquina ficou desligada nesse período",
                        "2. Backup Manager → Histórico → veja o motivo das sessões recentes",
                        "3. Confirme que o agendamento está ativo:",
                        "   Backup Manager → Preferências → Agendamento",
                        "4. Force uma sessão manual: Backup Manager → Executar Backup",
                    ]
                )
            elif dias_sem_ok > 7:
                add("❌ CRÍTICO",
                    f"Sem backup OK há {dias_sem_ok:.0f} dias — DADOS DESPROTEGIDOS",
                    f"O último backup OK foi em {dt(c(s,'TL'))}. "
                    f"Mais de uma semana sem backup — risco real de perda de dados.",
                    [
                        "1. AÇÃO IMEDIATA: acesse a máquina",
                        "2. services.msc → Backup Manager → deve estar Em execução",
                        "3. Se parado: net start 'Backup Manager'",
                        "4. Se pedir login, o token pode ter expirado — reinsira as credenciais",
                        "5. Force backup: Backup Manager → Executar Backup",
                        "6. Último recurso: desinstale e reinstale o agente pelo painel N-able",
                    ]
                )
    except: pass

    return problemas


# ── Tela de pesquisa ──────────────────────────────────────────────────────────
def tela_pesquisa(dispositivos):
    """Tela de busca — não usa input() durante countdown para não buggar."""
    while True:
        # Transição suave de entrada
        _clr()
        for i in range(0, TW+1, 8):
            print(f"\r   {'░'*min(i,TW)}", end="", flush=True)
            time.sleep(0.005)
        _clr()
        topo()
        # Título aparece letra a letra
        titulo_p = f"   {'🔎  PESQUISA DE DISPOSITIVO':^{TW}}"
        for ch in titulo_p:
            print(ch, end="", flush=True)
            time.sleep(0.008)
        print()
        topo("─")
        print()
        print(f"   Total disponível: {len(dispositivos)} dispositivos")
        print(f"   Digite nome, computador ou cliente. ENTER vazio = voltar.")
        print()
        try:
            termo = input("   🔎  Buscar: ").strip().lower()
        except:
            return

        if not termo:
            return

        resultados = [
            dev for dev in dispositivos
            if termo in (c(dev.get("Settings") or [],"I1") or "").lower()
            or termo in (c(dev.get("Settings") or [],"I18") or "").lower()
            or termo in (c(dev.get("Settings") or [],"I8") or "").lower()
        ]

        if not resultados:
            print(f"\n   ⚠️  Nenhum resultado para '{termo}'.")
            print(f"   Pressione ENTER para tentar novamente.")
            try: input()
            except: return
            continue

        if len(resultados) > 1:
            os.system("cls" if os.name=="nt" else "clear")
            topo()
            print(f"   {'🔎  RESULTADOS — ' + str(len(resultados)) + ' encontrado(s)':^{TW}}")
            topo("─")
            print(f"\n   {'#':<4} {'Nome':<35} {'Computador':<22} {'Cliente':<22} {'Status'}")
            print(f"   {'─'*TW}")
            for i, dev in enumerate(resultados, 1):
                ss = dev.get("Settings") or []
                print(f"   {i:<4} {c(ss,'I1')[:33]:<35} {c(ss,'I18')[:20]:<22} {c(ss,'I8')[:20]:<22} {status_fmt(c(ss,'T0'))}")
            print(f"\n   Digite o número e ENTER para ver, ou ENTER vazio para nova busca: ", end="")
            try:
                escolha = input().strip()
            except:
                return
            if not escolha:
                continue
            try:
                dev_escolhido = resultados[int(escolha)-1]
            except:
                continue
        else:
            dev_escolhido = resultados[0]

        exibir(dev_escolhido, 1, 1, "pesquisa", False)

        print(f"\n   {'─'*TW}")
        print(f"   P = Nova pesquisa   ENTER = Voltar ao carrossel")
        try:
            acao = input("   → ").strip().lower()
        except:
            return
        if acao == "p":
            continue
        return

# ── Telas principais ──────────────────────────────────────────────────────────
# ── Boot animation data ──────────────────────────────────────────────────────
LOGO_LINES = [
    "  ███╗   ██╗      █████╗ ██████╗ ██╗     ███████╗  ",
    "  ████╗  ██║     ██╔══██╗██╔══██╗██║     ██╔════╝  ",
    "  ██╔██╗ ██║     ███████║██████╔╝██║     █████╗    ",
    "  ██║╚██╗██║     ██╔══██║██╔══██╗██║     ██╔══╝    ",
    "  ██║ ╚████║     ██║  ██║██████╔╝███████╗███████╗  ",
    "  ╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝  ",
]
TAGLINE    = "C O V E   ·   M O N I T O R   D E   B A C K U P"
COMPANY    = "T R U S T   I T   S O L U Ç Õ E S"
VERSION    = "v3.0  |  N-able Cove API"

def _clr(): os.system("cls" if os.name=="nt" else "clear")

def _center(text, width=None):
    w = width or TW
    return text.center(w)

def tela_loading():
    _clr()
    bw = TW  # banner width

    # ── FASE 1: Escuridão → linha de scan desce pela tela ────────────────────
    altura = 16
    for i in range(altura):
        _clr()
        for j in range(altura):
            if j < i:
                print()
            elif j == i:
                print(f"   {'▓' * bw}")
            else:
                print()
        time.sleep(0.025)

    # ── FASE 2: Logo cresce do centro com efeito de reveal ───────────────────
    _clr()
    logo_w  = max(len(l) for l in LOGO_LINES)
    borda   = "═" * (logo_w + 6)
    pad_top = 3

    for _ in range(pad_top):
        print()

    # Borda superior pisca
    for _ in range(2):
        print(f"\r   {_center('╔' + borda + '╗')}", end="", flush=True)
        time.sleep(0.08)
        print(f"\r   {' ' * (bw)}", end="", flush=True)
        time.sleep(0.05)
    print(f"\r   {_center('╔' + borda + '╗')}", flush=True)

    # Linhas do logo surgem com efeito de digitação parcial
    for i, linha in enumerate(LOGO_LINES):
        conteudo = f"║  {linha}  ║"
        # Aparece caractere por caractere mas rápido
        for k in range(0, len(conteudo)+1, 4):
            parcial = conteudo[:k].ljust(len(conteudo))
            print(f"\r   {_center(parcial)}", end="", flush=True)
            time.sleep(0.008)
        print(f"\r   {_center(conteudo)}", flush=True)

    print(f"   {_center('╚' + borda + '╝')}")
    time.sleep(0.12)

    # ── FASE 3: Taglines surgem letra por letra ───────────────────────────────
    print()
    # Linha decorativa pulsante
    for _ in range(3):
        print(f"\r   {_center('· ' * (bw//4))}", end="", flush=True)
        time.sleep(0.06)
        print(f"\r   {_center('─' * (bw-6))}", end="", flush=True)
        time.sleep(0.06)
    print(f"\r   {_center('─' * (bw-6))}", flush=True)

    print()
    # TAGLINE letra por letra com aceleração no final
    tagline_centrada = _center(TAGLINE)
    delays = [0.035] * (len(tagline_centrada)//2) + [0.015] * (len(tagline_centrada) - len(tagline_centrada)//2)
    for ch, d in zip(tagline_centrada, delays):
        print(ch, end="", flush=True)
        time.sleep(d)
    print()
    time.sleep(0.04)

    # COMPANY mais rápido
    company_centrada = _center(COMPANY)
    for ch in company_centrada:
        print(ch, end="", flush=True)
        time.sleep(0.012)
    print()

    time.sleep(0.06)
    print(f"   {_center(VERSION)}")
    print()

    # ── FASE 4: Barra de boot em blocos com brilho ───────────────────────────
    print(f"   {'─' * bw}")
    print()

    ETAPAS = [
        (12,  "SYS",  "Iniciando módulos do sistema...              "),
        (25,  "SEC",  "Verificando integridade e segurança...       "),
        (42,  "NET",  "Estabelecendo conexão TLS com API N-able...  "),
        (60,  "AUTH", "Autenticando credenciais de acesso...        "),
        (78,  "SYNC", "Sincronizando configurações de backup...     "),
        (95,  "DATA", "Carregando inventário de dispositivos...     "),
        (100, " OK ", "Sistema operacional. Iniciando monitoramento."),
    ]

    barra_w = bw - 26
    pct_ant = 0

    for pct_alvo, tag, msg in ETAPAS:
        for pct in range(pct_ant, pct_alvo + 1):
            filled  = int(pct / 100 * barra_w)
            # Efeito de brilho: último bloco preenchido fica diferente
            if filled > 0:
                bar = "█" * (filled-1) + "▓" + "░" * (barra_w - filled)
            else:
                bar = "░" * barra_w
            cor_tag = "✅" if pct == 100 else "⚙️ "
            print(f"\r   {cor_tag} [{tag}]  [{bar}]  {pct:3d}%   {msg}",
                  end="", flush=True)
            time.sleep(0.008)
        pct_ant = pct_alvo
        time.sleep(0.06)

    # Barra completa — brilho final
    for _ in range(3):
        bar_full  = "█" * barra_w
        bar_pulse = "▓" * barra_w
        print(f"\r   ✅ [ OK ]  [{bar_full}]  100%   Sistema pronto.              ",
              end="", flush=True)
        time.sleep(0.07)
        print(f"\r   ✅ [ OK ]  [{bar_pulse}]  100%   Sistema pronto.              ",
              end="", flush=True)
        time.sleep(0.07)

    print(f"\r   ✅ [ OK ]  [{'█' * barra_w}]  100%   Sistema pronto. Entrando...  ",
          flush=True)
    print()
    time.sleep(0.25)


def tela_resumo(dispositivos):
    _clr()
    total    = len(dispositivos)
    criticos = [d for d in dispositivos if prioridade_dispositivo(d)==0]
    offline  = [d for d in dispositivos if prioridade_dispositivo(d)==1]
    avisos   = [d for d in dispositivos if prioridade_dispositivo(d)==2]
    oks      = [d for d in dispositivos if prioridade_dispositivo(d)==3]
    prob     = criticos + offline + avisos

    # ── Header animado ────────────────────────────────────────────────────────
    # Linha de topo cresce da esquerda para a direita
    for i in range(0, TW+1, 6):
        print(f"\r   {'█'*min(i,TW)}", end="", flush=True)
        time.sleep(0.012)
    print(f"\r   {'█'*TW}", flush=True)

    titulo = "N-ABLE COVE  —  RESUMO GERAL"
    # Título aparece letra a letra
    linha_titulo = f"   {titulo:^{TW}}"
    for ch in linha_titulo:
        print(ch, end="", flush=True)
        time.sleep(0.012)
    print()

    for i in range(0, TW+1, 6):
        print(f"\r   {'─'*min(i,TW)}", end="", flush=True)
        time.sleep(0.008)
    print(f"\r   {'─'*TW}", flush=True)
    print()

    # ── Cards com contadores animados ─────────────────────────────────────────
    lc = TW//5 - 2
    cards = [
        ("TOTAL",       total,         "⬜", total),
        ("❌  ERRO",     len(criticos), "🔴", total),
        ("🔌  OFFLINE",  len(offline),  "⚫", total),
        ("🟠  AVISO",   len(avisos),   "🟡", total),
        ("✅  OK",       len(oks),      "🟢", total),
    ]

    # Desenha moldura dos cards primeiro
    t1=t2=t4="   "
    for label,_,ico,_ in cards:
        t1+=f"┌{'─'*lc}┐  "
        t2+=f"│{label:^{lc}}│  "
        t4+=f"└{'─'*lc}┘  "
    print(t1); print(t2)

    # Anima os números contando de 0 até o valor real
    max_val  = max(v for _,v,_,_ in cards) or 1
    passos   = 12
    for step in range(passos+1):
        frac = step/passos
        # Ease-out: começa rápido, termina devagar
        frac_ease = 1 - (1-frac)**2
        t3 = "   "
        for label, valor, ico, _ in cards:
            atual = int(valor * frac_ease)
            if step == passos: atual = valor  # garante valor final exato
            t3 += f"│{f'{ico} {atual}':^{lc}}│  "
        print(f"\r{t3}", end="", flush=True)
        time.sleep(0.04)
    print()
    print(t4)
    print()

    # ── Lista de problemas com entrada animada ────────────────────────────────
    if prob:
        # Título da lista aparece
        titulo_prob = f"   ❌  Dispositivos com atenção ({len(prob)}) — por município"
        for ch in titulo_prob:
            print(ch, end="", flush=True)
            time.sleep(0.008)
        print()
        print(f"   {'─'*TW}")

        mun_atual = None
        for i, d in enumerate(prob[:18]):
            ss  = d.get("Settings") or []
            mun = extrair_municipio(d)

            if mun != mun_atual:
                if mun_atual is not None:
                    print(f"   │")
                # Município aparece com efeito
                mun_linha = f"   │  📍 {mun}"
                for ch in mun_linha:
                    print(ch, end="", flush=True)
                    time.sleep(0.006)
                print()
                mun_atual = mun

            prio  = prioridade_dispositivo(d)
            tag   = {0:"❌ ERRO",1:"🔌 OFFLINE",2:"🟠 AVISO"}.get(prio,"")
            spark = sparkline_7dias(c(ss,"D1F8") or "")
            nome  = c(ss,"I1")[:32]
            cli   = c(ss,"I8")[:22]
            st    = status_fmt(c(ss,"T0"))

            # Cada linha desliza da esquerda
            linha = f"   │  {tag:<12} {nome:<33} {cli:<23} {spark}  {st}"
            for ch in linha:
                print(ch, end="", flush=True)
                time.sleep(0.004)
            print()

        if len(prob) > 18:
            print(f"   │  ... e mais {len(prob)-18} dispositivo(s)")
        print(f"   {'─'*TW}")

    # ── Rodapé com ETA e dica ─────────────────────────────────────────────────
    print()
    m_c,s_c = divmod(TEMPO_CRITICO,60)
    m_n,s_n = divmod(TEMPO_NORMAL, 60)
    eta      = calcular_eta(dispositivos, 0)
    agora_s  = datetime.datetime.now().strftime("%H:%M:%S")

    rodape = (f"   🕐  {agora_s}   │   ETA ciclo: {eta}   │   "
              f"Problema: {m_c:02d}:{s_c:02d}  OK: {m_n:02d}:{s_n:02d}")
    for ch in rodape:
        print(ch, end="", flush=True)
        time.sleep(0.006)
    print()

    hint = "P + ENTER = pesquisar"
    print(f"   [{hint}]   [Ctrl+C = encerrar e salvar log]")
    print()

    # ── Barra de contagem regressiva antes de iniciar ─────────────────────────
    espera = 5
    bw_esp = TW - 20
    for s in range(espera, 0, -1):
        prog  = int((espera-s)/espera * bw_esp)
        bar   = "█"*prog + "░"*(bw_esp-prog)
        print(f"\r   ▶  Iniciando em {s}s   [{bar}]", end="", flush=True)
        time.sleep(1)
    print(f"\r   ▶  Iniciando...   [{'█'*bw_esp}]", flush=True)
    print()

    if criticos:
        beep_critico()


# ── Exibe um dispositivo ──────────────────────────────────────────────────────
def exibir(dev, idx, total, rodada, tem_erro):
    s         = dev.get("Settings") or []
    agora     = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    municipio = extrair_municipio(dev)
    prio      = prioridade_dispositivo(dev)
    icone     = {0:"❌",1:"🔌",2:"🟠",3:"✅"}.get(prio,"⬜")

    # ── Transição: wipe rápido ────────────────────────────────────────────────
    _clr()
    cor_wipe = "█" if prio == 0 else ("▒" if prio <= 2 else "░")
    for i in range(0, TW+1, 10):
        print(f"\r   {cor_wipe*min(i,TW)}", end="", flush=True)
        time.sleep(0.006)
    time.sleep(0.03)
    _clr()

    fontes_ativas = detectar_fontes_ativas(s)
    nomes_fontes  = [f"{e} {nm}" for nm,e,_ in fontes_ativas]

    # Beep se dispositivo crítico
    if prio == 0 and rodada != "pesquisa":
        beep_critico()

    topo()
    print(f"   {'N-ABLE COVE  —  MONITOR DE BACKUP  '+icone:^{TW}}")
    topo("─")
    print(f"   Rodada #{rodada}   {agora}   Dispositivo {idx}/{total}   📍 {municipio}")
    DOTS_W = TW-2
    pos = int((idx-1)/max(total-1,1)*(DOTS_W-1))
    print(f"   {'·'*pos}●{'·'*(DOTS_W-pos-1)}")
    # Tag principal baseada na prioridade calculada
    tags = {
        0:"   🔴  PRIORIDADE ALTA — DISPOSITIVO COM ERRO — REQUER ATENÇÃO IMEDIATA",
        1:"   🔌  DISPOSITIVO OFFLINE — Sem comunicação há mais de 3 dias",
        2:"   🟠  ATENÇÃO — Backup com problemas em alguma fonte",
        3:"   🟢  Backup operando normalmente",
    }
    tag_linha = tags.get(prio,"   ⬜  Status desconhecido")

    # Se T0=EmAndamento: adiciona contexto informativo
    t0_dev = c(s,"T0")
    if t0_dev == "1":
        # Conta quantas fontes já terminaram vs ainda rodando
        fontes_ok   = sum(1 for _,_,p in fontes_ativas if c(s,f"{p}0") == "5")
        fontes_and  = sum(1 for _,_,p in fontes_ativas if c(s,f"{p}0") == "1")
        total_f     = len(fontes_ativas)
        tag_linha   = (f"   🔄  BACKUP EM ANDAMENTO — "
                      f"{fontes_ok}/{total_f} fonte(s) concluída(s), "
                      f"{fontes_and} ainda rodando")

    print(tag_linha)
    hint = "P + ENTER = pesquisar"
    print(f"   [{hint}]")
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

    # ── Fontes em pares ───────────────────────────────────────────────────────
    i = 0
    while i < len(fontes_ativas):
        if i+1 < len(fontes_ativas):
            nm1,e1,p1 = fontes_ativas[i];  nm2,e2,p2 = fontes_ativas[i+1]
            cab2(nm1,nm2,e1+"  ",e2+"  ")
            r1=bloco_fonte(s,nm1,e1,p1); r2=bloco_fonte(s,nm2,e2,p2)
            for j in range(max(len(r1),len(r2))):
                l1=v1=l2=v2=""
                if j<len(r1): l1,v1=r1[j]
                if j<len(r2): l2,v2=r2[j]
                if l1=="SEP" or l2=="SEP": sep2(); continue
                esq=f"   ║  {l1:<20} {str(v1):<16}"
                print(f"{esq:<{CW+7}}   ║  {l2:<20} {str(v2)}")
            fim2(); i+=2
        else:
            nm1,e1,p1=fontes_ativas[i]
            cab(nm1,e1+"  ")
            for l,v in bloco_fonte(s,nm1,e1,p1):
                if l=="SEP": print(f"   ╟{'─'*(TW-2)}╢"); continue
                row(l,v)
            fim(); i+=1

    if not fontes_ativas:
        cab("FONTES DE DADOS","⚠️  ")
        row("Aviso","Nenhuma fonte de dados ativa detectada.")
        fim()

    # ── Transferência animada ─────────────────────────────────────────────────
    fontes_com_tam = [(nm,e,p) for nm,e,p in fontes_ativas
                     if c(s,f"{p}3") and int(c(s,f"{p}3") or 0)>0]
    if fontes_com_tam:
        cab("TRANSFERÊNCIA DE DADOS","📤  ")
        for idx_f, (nm_f,e_f,p_f) in enumerate(fontes_com_tam):
            # Separador entre fontes (não antes da primeira)
            if idx_f > 0:
                print(f"   ╟{'─'*(TW-2)}╢")
            row(f"{e_f} {nm_f} — Selecionado", gb(c(s,f"{p_f}3")))
            barra_animada("  Processado",     c(s,f"{p_f}4"), c(s,f"{p_f}3"))
            barra_animada("  Enviado (novo)",  c(s,f"{p_f}5"), c(s,f"{p_f}3"))
        fim()

    # ── Calendário combinado ──────────────────────────────────────────────────
    barras = []
    # Usa APENAS barras no formato novo (D1F8, D2F8) — confiáveis e com 28+ chars
    # As barras legadas (F8, S8, N8) retornam "0" como placeholder — ignorar
    def barra_valida(b):
        """Barra válida = tem mais de 1 char E não é tudo zeros/placeholders."""
        if not b or len(b) <= 1: return False
        if all(ch in "07" for ch in b): return False  # tudo sem backup = placeholder
        return True

    barra_d1 = c(s,"D1F8") if barra_valida(c(s,"D1F8")) else None
    barra_d2 = c(s,"D2F8") if barra_valida(c(s,"D2F8")) else None
    if barra_d1: barras.append(barra_d1)
    if barra_d2: barras.append(barra_d2)
    # Barras legadas: só usa se tiver conteúdo real (>1 char e não placeholder)
    for pref in ["N","W","H","Z","X","P","Y","L","G","J"]:
        b = c(s,f"{pref}8")
        if barra_valida(b): barras.append(b)

    if barras:
        barra_comb = combinar_barras(*barras)

        # Monta título — só inclui fonte se tiver barra VÁLIDA
        nomes_hist = []
        if barra_d1: nomes_hist.append("📁 F&F")
        if barra_d2: nomes_hist.append("🗄 SS")
        for pref,nm in [("N","🌐 Net"),("W","🖥 VMw"),("H","💠 HV")]:
            if barra_valida(c(s,f"{pref}8")): nomes_hist.append(nm)
        titulo = "HISTÓRICO — ÚLTIMOS 28 DIAS"
        if nomes_hist: titulo += f"  ({'  +  '.join(nomes_hist[:3])})"

        cab(titulo,"📅  ")
        print(f"   ║   ✅ OK    🟠 Com erros / Interrompido    ❌ Falhou / Abortado    ░ Sem backup")
        linha_cheia()

        # Calendário principal com barra combinada
        for l in calendario(barra_comb):
            print(f"   ║   {l}")

        # Footer com detalhe por fonte
        if len(barras) >= 1:
            # Monta dict de barras por nome de fonte
            barras_dict = {}
            if barra_d1: barras_dict["📁 Files & Folders"] = barra_d1
            if barra_d2: barras_dict["🗄 System State"]    = barra_d2
            # Barras legadas: só inclui se forem válidas
            for pref, nm in [("N","🌐 Network Shares"),("W","🖥 VMware"),
                              ("H","💠 Hyper-V"),("Z","🗃 MS SQL")]:
                b = c(s,f"{pref}8")
                if barra_valida(b): barras_dict[nm] = b
            # Fontes com dados mas sem barra histórica: registra como nota
            fontes_sem_barra = []
            for pref, nm in [("N","🌐 Network Shares"),("W","🖥 VMware"),
                              ("H","💠 Hyper-V"),("Z","🗃 MS SQL")]:
                sv = c(s,f"{pref}0"); ts = c(s,f"{pref}3")
                b  = c(s,f"{pref}8")
                if sv and ts and not barra_valida(b):
                    try:
                        if int(ts) > 0:
                            fontes_sem_barra.append((nm, status_fmt(sv)))
                    except: pass

            footer = calendario_footer(barras_dict, fontes_ativas)
            if footer:
                linha_cheia()
                for l in footer:
                    print(f"   ║   {l}")

            # Nota sobre fontes sem histórico de barra (ex: Network Shares)
            if fontes_sem_barra:
                linha_cheia()
                print(f"   ║   ℹ️  Fontes sem histórico de 28 dias (API não retorna barra):")
                for nm_sb, st_sb in fontes_sem_barra:
                    print(f"   ║      {nm_sb:<28} Status atual: {st_sb}")

        fim()

    # ── Diagnóstico ───────────────────────────────────────────────────────────
    cab("DIAGNÓSTICO DETALHADO","🔍  ")
    problemas = gerar_diagnostico(s, fontes_ativas)

    if not problemas:
        linha_cheia()
        print(f"   ║  ✅  TUDO OK — Todas as fontes funcionando corretamente.")
        print(f"   ║  Dados processados e enviados ao storage sem erros.")
        print(f"   ║  Nenhuma ação necessária.")
        linha_cheia()
    else:
        for i,(nivel_d,titulo,explicacao,passos) in enumerate(problemas):
            if i>0: linha_cheia()
            print(f"   ║  {nivel_d}  {titulo}")
            linha_cheia()
            for l in quebrar(explicacao):
                print(f"   ║     📋  {l}")
            linha_cheia()
            print(f"   ║     🔧  COMO RESOLVER:")
            for passo in passos:
                for l in quebrar(passo, 95):
                    print(f"   ║        {l}")
    fim()

# ── Utilitários extras ───────────────────────────────────────────────────────

def beep_critico():
    """Beep sonoro — só no Windows."""
    if os.name == "nt":
        try:
            import winsound
            winsound.Beep(880, 200)
            time.sleep(0.1)
            winsound.Beep(880, 200)
        except: pass
    # Linux: sem beep (terminal web não suporta)

def sparkline_7dias(barra):
    """Retorna mini linha dos últimos 7 dias para a tela de resumo."""
    if not barra: return "░░░░░░░"
    ultimos = barra[-7:].ljust(7,"0")
    mapa = {"5":"✅","8":"🟠","2":"❌","3":"❌","6":"🟠","9":"🟠","0":"░","7":"░","1":"🔄"}
    return "".join(mapa.get(ch,"░") for ch in ultimos)

def calcular_eta(dispositivos, idx_atual):
    """Calcula tempo estimado para ver todos os dispositivos restantes."""
    restantes = len(dispositivos) - idx_atual
    if restantes <= 0: return "—"
    # Estima baseado na proporção de críticos vs normais restantes
    criticos_rest = sum(1 for d in dispositivos[idx_atual:] if prioridade_dispositivo(d) <= 2)
    normais_rest  = restantes - criticos_rest
    segundos_est  = criticos_rest * TEMPO_CRITICO + normais_rest * TEMPO_NORMAL
    h, r = divmod(segundos_est, 3600)
    m, _ = divmod(r, 60)
    if h > 0: return f"{h}h {m:02d}m"
    return f"{m}m"

def salvar_log(dispositivos, rodada):
    """Salva resumo em arquivo .txt na área de trabalho ao encerrar."""
    try:
        # Cria pasta em Documentos
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        if not os.path.exists(docs):
            docs = os.path.join(os.path.expanduser("~"), "Documentos")  # PT
        if not os.path.exists(docs):
            docs = os.path.expanduser("~")

        pasta = os.path.join(docs, "Monitor Backup N-able")
        os.makedirs(pasta, exist_ok=True)

        agora    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(pasta, f"backup_monitor_{agora}.txt")

        criticos = [d for d in dispositivos if prioridade_dispositivo(d) == 0]
        offline  = [d for d in dispositivos if prioridade_dispositivo(d) == 1]
        avisos   = [d for d in dispositivos if prioridade_dispositivo(d) == 2]
        oks      = [d for d in dispositivos if prioridade_dispositivo(d) == 3]

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO DE BACKUP — N-ABLE COVE\n")
            f.write(f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"Rodadas executadas: {rodada}\n")
            f.write("="*70 + "\n\n")
            f.write(f"RESUMO:\n")
            f.write(f"  Total de dispositivos : {len(dispositivos)}\n")
            f.write(f"  Com erro (crítico)    : {len(criticos)}\n")
            f.write(f"  Offline               : {len(offline)}\n")
            f.write(f"  Com avisos            : {len(avisos)}\n")
            f.write(f"  OK                    : {len(oks)}\n\n")

            if criticos or offline:
                f.write("DISPOSITIVOS QUE PRECISAM DE ATENÇÃO:\n")
                f.write("-"*70 + "\n")
                for d in criticos + offline:
                    s   = d.get("Settings") or []
                    tag = "ERRO" if prioridade_dispositivo(d)==0 else "OFFLINE"
                    f.write(f"  [{tag}] {c(s,'I1'):<35} {c(s,'I8'):<25} {status_fmt(c(s,'T0'))}\n")
                f.write("\n")

            f.write("TODOS OS DISPOSITIVOS:\n")
            f.write("-"*70 + "\n")
            mun_atual = None
            for d in dispositivos:
                s   = d.get("Settings") or []
                mun = extrair_municipio(d)
                if mun != mun_atual:
                    f.write(f"\n  📍 {mun}\n")
                    mun_atual = mun
                spark = sparkline_7dias(c(s,"D1F8") or c(s,"F8") or "")
                f.write(f"    {c(s,'I1'):<35} {spark}  {status_fmt(c(s,'T0'))}\n")

        print(f"\n   💾  Log salvo em: {filepath}")
    except Exception as e:
        print(f"\n   ⚠️  Não foi possível salvar o log: {e}")

# ── Loop principal ────────────────────────────────────────────────────────────
rodada=0; visa=None; pid=None

try:
    while True:
        tela_loading(); print()
        spinner("Autenticando na API N-able Cove...", 1.5)
        if visa is None or rodada%5==0:
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
            tem_erro = prio<=2
            tempo    = TEMPO_CRITICO if tem_erro else TEMPO_NORMAL
            exibir(dev, idx, total, rodada, tem_erro)
            countdown_com_pesquisa(tempo, idx, total, tem_erro, dispositivos)

except KeyboardInterrupt:
    print()
    _clr()
    # Animação de encerramento — wipe reverso
    for i in range(TW, -1, -10):
        print(f"\r   {chr(9608)*max(i,0)}", end="", flush=True)
        time.sleep(0.015)
    _clr()

    # Tela de saída
    for _ in range(4): print()
    msg_saida = "MONITORAMENTO ENCERRADO"
    for ch in f"   {_center(msg_saida)}":
        print(ch, end="", flush=True)
        time.sleep(0.018)
    print()
    time.sleep(0.1)
    for ch in f"   {_center('Encerrando com segurança...')}":
        print(ch, end="", flush=True)
        time.sleep(0.012)
    print()
    print()

    if dispositivos:
        spinner("Salvando relatório final...", 1.2)
        salvar_log(dispositivos, rodada)
    print()
except Exception as e:
    print(f"\n   ❌ ERRO: {e}")
    import traceback; traceback.print_exc()

input("\n   Pressione ENTER para fechar...")
