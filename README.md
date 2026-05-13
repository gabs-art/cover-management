# N-able Cove — Web Terminal

Terminal interativo no navegador usando xterm.js + WebSocket + PTY.
Roda connect.py no servidor e transmite o terminal para o browser em tempo real.

## Arquivos do repositório GitHub
```
connect.py          ← seu monitor (renomeie se necessário)
server.py           ← servidor WebSocket + PTY
requirements.txt    ← dependências
Procfile            ← comando de start para o Railway
runtime.txt         ← versão do Python
static/
  index.html        ← frontend xterm.js
```

## Variáveis de ambiente (configure no Railway)
```
NABLE_PARTNER   = Trust IT (claudiney.alves@...)
NABLE_USERNAME  = Trust
NABLE_PASSWORD  = sua_senha
NABLE_URL       = https://api.backup.management/jsonapi
WEB_PASSWORD    = senha_para_acessar_o_terminal_web
PORT            = 8080 (Railway define automaticamente)
```

## Deploy Railway
1. Suba todos os arquivos para um repositório GitHub
2. Railway → New Project → Deploy from GitHub
3. Configure as variáveis de ambiente acima
4. Deploy automático — link público gerado em ~2 minutos

## Acesso
- Abra o link gerado pelo Railway
- Digite a WEB_PASSWORD configurada
- O terminal abre e o monitor começa automaticamente
- Funciona em qualquer navegador, celular incluso
- Totalmente interativo — P para pesquisar, Ctrl+C para encerrar
