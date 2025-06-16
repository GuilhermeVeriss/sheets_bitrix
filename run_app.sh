#!/bin/bash

# Script para executar a aplicação de sincronização Aliest
# Usage: ./run_app.sh [once|daemon|status]

APP_NAME="Aliest Sync App"
PYTHON_SCRIPT="main_app.py"
PID_FILE="app.pid"
LOG_FILE="main_app.log"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log colorido
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Verificar se Python está disponível
check_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python3 não encontrado. Instale Python3 para continuar."
        exit 1
    fi
}

# Verificar se dependências estão instaladas
check_dependencies() {
    log "Verificando dependências..."
    
    if [ -f "requirements.txt" ]; then
        python3 -c "
import sys
try:
    import psycopg2, google.oauth2, requests, dotenv
    print('✅ Todas as dependências estão instaladas')
    sys.exit(0)
except ImportError as e:
    print(f'❌ Dependência faltando: {e}')
    print('💡 Execute: pip install -r requirements.txt')
    sys.exit(1)
"
        if [ $? -ne 0 ]; then
            exit 1
        fi
    else
        warning "Arquivo requirements.txt não encontrado"
    fi
}

# Verificar se arquivo .env existe
check_env_file() {
    if [ ! -f ".env" ]; then
        warning "Arquivo .env não encontrado"
        echo "Crie um arquivo .env com as seguintes variáveis:"
        echo "DATABASE_URL=postgresql://user:password@localhost/database"
        echo "BITRIX_URL=https://your-domain.bitrix24.com.br/rest/user_id/webhook_key/"
        echo "GOOGLE_CREDENTIALS=path/to/credentials.json"
        echo "SPREADSHEET_ID=your_spreadsheet_id"
        echo ""
        echo "Variáveis opcionais:"
        echo "SYNC_INTERVAL_SECONDS=300"
        echo "MAX_RETRIES=3"
        echo "RETRY_DELAY_SECONDS=60"
        echo "ENABLE_CONTINUOUS_SYNC=true"
        echo "LOG_LEVEL=INFO"
        return 1
    fi
    return 0
}

# Executar aplicação uma vez
run_once() {
    log "Executando $APP_NAME em modo único..."
    check_python
    check_dependencies
    
    if ! check_env_file; then
        error "Configure o arquivo .env antes de continuar"
        exit 1
    fi
    
    python3 "$PYTHON_SCRIPT" --once
}

# Executar aplicação em modo daemon
run_daemon() {
    log "Iniciando $APP_NAME em modo daemon..."
    check_python
    check_dependencies
    
    if ! check_env_file; then
        error "Configure o arquivo .env antes de continuar"
        exit 1
    fi
    
    # Verificar se já está executando
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            warning "Aplicação já está executando (PID: $PID)"
            exit 1
        else
            # Arquivo PID existe mas processo não, remover arquivo
            rm "$PID_FILE"
        fi
    fi
    
    # Iniciar em background
    nohup python3 "$PYTHON_SCRIPT" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    sleep 2
    
    # Verificar se processo está executando
    if ps -p "$PID" > /dev/null 2>&1; then
        success "Aplicação iniciada com sucesso (PID: $PID)"
        log "Logs: tail -f $LOG_FILE"
        log "Status: ./run_app.sh status"
        log "Parar: ./run_app.sh stop"
    else
        error "Falha ao iniciar aplicação"
        cat "$LOG_FILE" | tail -n 20
        exit 1
    fi
}

# Parar aplicação daemon
stop_daemon() {
    if [ ! -f "$PID_FILE" ]; then
        warning "Aplicação não está executando (arquivo PID não encontrado)"
        exit 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p "$PID" > /dev/null 2>&1; then
        log "Parando aplicação (PID: $PID)..."
        
        # Tentar parada graceful primeiro
        kill -TERM "$PID"
        
        # Aguardar até 30 segundos para parada graceful
        for i in {1..30}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                success "Aplicação parada gracefully"
                rm "$PID_FILE"
                exit 0
            fi
            sleep 1
        done
        
        # Se ainda estiver executando, forçar parada
        warning "Forçando parada da aplicação..."
        kill -KILL "$PID"
        sleep 2
        
        if ! ps -p "$PID" > /dev/null 2>&1; then
            success "Aplicação parada forçadamente"
            rm "$PID_FILE"
        else
            error "Não foi possível parar a aplicação"
            exit 1
        fi
    else
        warning "Processo não está executando, removendo arquivo PID"
        rm "$PID_FILE"
    fi
}

# Verificar status da aplicação
check_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            success "Aplicação está executando (PID: $PID)"
            
            # Mostrar informações do processo
            echo ""
            echo "Informações do processo:"
            ps -p "$PID" -o pid,ppid,cmd,etime,pcpu,pmem --no-headers
            
            # Mostrar últimas linhas do log
            if [ -f "$LOG_FILE" ]; then
                echo ""
                echo "Últimas 10 linhas do log:"
                tail -n 10 "$LOG_FILE"
            fi
            
            return 0
        else
            warning "Arquivo PID existe mas processo não está executando"
            rm "$PID_FILE"
            return 1
        fi
    else
        warning "Aplicação não está executando"
        return 1
    fi
}

# Mostrar logs em tempo real
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        log "Mostrando logs em tempo real (Ctrl+C para sair):"
        tail -f "$LOG_FILE"
    else
        warning "Arquivo de log não encontrado: $LOG_FILE"
    fi
}

# Instalar dependências
install_deps() {
    log "Instalando dependências..."
    check_python
    
    if [ -f "requirements.txt" ]; then
        python3 -m pip install --upgrade pip
        python3 -m pip install -r requirements.txt
        success "Dependências instaladas"
    else
        error "Arquivo requirements.txt não encontrado"
        exit 1
    fi
}

# Função principal
main() {
    case "${1:-help}" in
        "once")
            run_once
            ;;
        "start"|"daemon")
            run_daemon
            ;;
        "stop")
            stop_daemon
            ;;
        "restart")
            log "Reiniciando aplicação..."
            stop_daemon
            sleep 2
            run_daemon
            ;;
        "status")
            check_status
            ;;
        "logs")
            show_logs
            ;;
        "install")
            install_deps
            ;;
        "help"|*)
            echo "$APP_NAME - Script de Controle"
            echo ""
            echo "Uso: $0 {once|start|stop|restart|status|logs|install|help}"
            echo ""
            echo "Comandos:"
            echo "  once     - Executa sincronização uma única vez"
            echo "  start    - Inicia aplicação em modo daemon (contínuo)"
            echo "  stop     - Para aplicação daemon"
            echo "  restart  - Reinicia aplicação daemon"
            echo "  status   - Mostra status da aplicação"
            echo "  logs     - Mostra logs em tempo real"
            echo "  install  - Instala dependências Python"
            echo "  help     - Mostra esta ajuda"
            echo ""
            echo "Exemplos:"
            echo "  $0 install           # Instalar dependências"
            echo "  $0 once              # Executar uma vez"
            echo "  $0 start             # Iniciar modo contínuo"
            echo "  $0 status            # Ver status"
            echo "  $0 logs              # Ver logs em tempo real"
            echo "  $0 stop              # Parar aplicação"
            ;;
    esac
}

# Executar função principal
main "$@"