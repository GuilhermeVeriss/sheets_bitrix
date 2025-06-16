# Aplicação de Sincronização Aliest

Sistema completo de sincronização contínua entre Google Sheets e banco de dados PostgreSQL, com integração Bitrix24.

## 🚀 Funcionalidades

- **Inicialização Única**: Executa startup.py uma vez para configurar o sistema
- **Sincronização Contínua**: Mantém dados sempre atualizados entre Google Sheets e banco
- **Detecção de Mudanças**: Identifica registros novos, removidos e inalterados
- **Recuperação Automática**: Sistema robusto com retry automático em caso de falhas
- **Logs Detalhados**: Monitoramento completo de todas as operações
- **Controle Flexível**: Modo daemon ou execução única
- **Estatísticas**: Relatórios de performance e status do sistema

## 📋 Pré-requisitos

- Python 3.8+
- PostgreSQL
- Credenciais do Google Sheets API
- Webhook do Bitrix24 (opcional)

## 🛠️ Instalação

1. **Clone o repositório** (se necessário):
   ```bash
   git clone <repository-url>
   cd sheets_bitrix
   ```

2. **Instale as dependências**:
   ```bash
   ./run_app.sh install
   # ou
   pip install -r requirements.txt
   ```

3. **Configure as variáveis de ambiente**:
   ```bash
   cp .env.example .env
   # Edite o arquivo .env com suas configurações
   ```

4. **Configure o arquivo .env** com as seguintes variáveis obrigatórias:
   ```bash
   DATABASE_URL=postgresql://user:password@localhost:5432/database
   BITRIX_URL=https://your-domain.bitrix24.com.br/rest/user_id/webhook_key/
   GOOGLE_CREDENTIALS=path/to/credentials.json
   SPREADSHEET_ID=your_spreadsheet_id
   ```

## 🎯 Uso Rápido

### Execução Única
```bash
# Executa startup + uma sincronização
./run_app.sh once
```

### Modo Contínuo (Daemon)
```bash
# Inicia sincronização contínua em background
./run_app.sh start

# Verifica status
./run_app.sh status

# Acompanha logs em tempo real
./run_app.sh logs

# Para a aplicação
./run_app.sh stop
```

## 📚 Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `./run_app.sh install` | Instala dependências Python |
| `./run_app.sh once` | Execução única (startup + sync) |
| `./run_app.sh start` | Inicia modo contínuo |
| `./run_app.sh stop` | Para aplicação daemon |
| `./run_app.sh restart` | Reinicia aplicação |
| `./run_app.sh status` | Mostra status e estatísticas |
| `./run_app.sh logs` | Exibe logs em tempo real |
| `./run_app.sh help` | Mostra ajuda |

## ⚙️ Configuração Avançada

### Variáveis de Ambiente Opcionais

```bash
# Intervalo entre sincronizações (segundos)
SYNC_INTERVAL_SECONDS=300          # 5 minutos (padrão)

# Tentativas em caso de falha
MAX_RETRIES=3                      # Padrão: 3 tentativas
RETRY_DELAY_SECONDS=60             # Padrão: 60 segundos entre tentativas

# Controle de execução
ENABLE_CONTINUOUS_SYNC=true        # true/false
LOG_LEVEL=INFO                     # DEBUG/INFO/WARNING/ERROR
```

### Execução Direta com Python

```bash
# Modo contínuo
python3 main_app.py

# Execução única
python3 main_app.py --once
```

## 📊 Estrutura do Sistema

```
├── main_app.py           # Aplicação principal (NOVO)
├── run_app.sh           # Script de controle (NOVO)
├── startup.py           # Inicialização do sistema
├── sync_manager.py      # Gerenciador de sincronização
├── google_sheets_api.py # API Google Sheets
├── bitrix_api.py        # API Bitrix24
├── requirements.txt     # Dependências Python
├── .env.example         # Template de configuração
└── logs/                # Arquivos de log
```

## 🔄 Fluxo de Funcionamento

1. **Inicialização** (`startup.py`):
   - Conecta ao banco PostgreSQL
   - Cria/atualiza estrutura de tabelas
   - Inicializa APIs (Google Sheets, Bitrix24)
   - Carrega dados iniciais das planilhas

2. **Sincronização Contínua** (`sync_manager.py`):
   - Captura snapshot dos dados atuais
   - Remove todos os dados da tabela
   - Recarrega dados frescos das planilhas
   - Detecta mudanças (novos, removidos, inalterados)
   - Gera relatórios detalhados

3. **Monitoramento**:
   - Logs detalhados de todas as operações
   - Estatísticas de performance
   - Recuperação automática em falhas

## 📈 Monitoramento e Logs

### Visualizar Status
```bash
./run_app.sh status
```

Mostra:
- Status da aplicação (executando/parado)
- Tempo de atividade
- Número de ciclos de sincronização
- Taxa de sucesso
- Última sincronização
- Estatísticas do banco de dados

### Logs em Tempo Real
```bash
./run_app.sh logs
```

### Arquivos de Log
- `main_app.log` - Log principal da aplicação
- `startup.log` - Log de inicialização

## 🗄️ Estrutura do Banco de Dados

### Tabela Principal: `leads_data`
```sql
CREATE TABLE leads_data (
    id SERIAL PRIMARY KEY,
    data DATE,
    cnpj VARCHAR(20),
    telefone VARCHAR(20),
    nome VARCHAR(255),
    empresa VARCHAR(500),
    consultor VARCHAR(255),
    forma_prospeccao VARCHAR(255),
    etapa VARCHAR(255),
    banco VARCHAR(255),           -- Nome da aba do Google Sheets
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabela de Log: `sync_log`
Registra histórico de todas as sincronizações com detalhes de performance.

## 🔧 Solução de Problemas

### Verificar Dependências
```bash
./run_app.sh install
```

### Verificar Configuração
```bash
# Verifica se .env está configurado
cat .env

# Testa conexões
./run_app.sh once
```

### Logs de Debug
```bash
# Alterar nível de log para DEBUG
echo "LOG_LEVEL=DEBUG" >> .env

# Reiniciar aplicação
./run_app.sh restart
```

### Problemas Comuns

1. **Erro de conexão PostgreSQL**:
   - Verifique `DATABASE_URL` no .env
   - Confirme se PostgreSQL está executando

2. **Erro Google Sheets API**:
   - Verifique `GOOGLE_CREDENTIALS` e `SPREADSHEET_ID`
   - Confirme permissões do arquivo de credenciais

3. **Erro Bitrix24**:
   - Verifique `BITRIX_URL`
   - Confirme se webhook está ativo

## 🚀 Colocando em Produção

### Systemd Service (Linux)
```bash
# Criar service file
sudo nano /etc/systemd/system/aliest-sync.service
```

```ini
[Unit]
Description=Aliest Sync Application
After=network.target postgresql.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/sheets_bitrix
ExecStart=/usr/bin/python3 main_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Habilitar e iniciar
sudo systemctl enable aliest-sync
sudo systemctl start aliest-sync
```

### Docker (Opcional)
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python3", "main_app.py"]
```

## 📝 Changelog

### v2.0 - Aplicação Integrada
- ✅ Aplicação principal unificada (`main_app.py`)
- ✅ Script de controle (`run_app.sh`)
- ✅ Modo daemon com controle de PID
- ✅ Sincronização contínua com detecção de mudanças
- ✅ Sistema robusto de logs e monitoramento
- ✅ Recuperação automática de falhas
- ✅ Configuração flexível via variáveis de ambiente

### v1.0 - Módulos Separados
- ✅ Módulo de inicialização (`startup.py`)
- ✅ Gerenciador de sincronização (`sync_manager.py`)
- ✅ APIs Google Sheets e Bitrix24

## 📞 Suporte

Para problemas ou dúvidas:
1. Verifique os logs: `./run_app.sh logs`
2. Execute diagnóstico: `./run_app.sh once`
3. Consulte a documentação acima