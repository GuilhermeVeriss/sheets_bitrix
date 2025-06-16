#!/bin/bash

echo "🚀 Iniciando Interface de Monitoramento Aliest"
echo "=============================================="

# Função para verificar e parar processos na porta
check_and_kill_port() {
    local port=$1
    local pid=$(lsof -ti:$port)
    
    if [ ! -z "$pid" ]; then
        echo "⚠️  Processo detectado na porta $port (PID: $pid)"
        read -p "🔄 Deseja parar este processo? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill -9 $pid
            echo "✅ Processo parado"
            sleep 2
        else
            echo "⏭️  Continuando sem parar o processo (será usada outra porta)"
        fi
    fi
}

# Verificar se o arquivo .env existe
if [ ! -f .env ]; then
    echo "❌ Arquivo .env não encontrado!"
    echo "📝 Crie o arquivo .env com as configurações necessárias"
    exit 1
fi

# Verificar processos nas portas mais comuns
echo "🔍 Verificando portas em uso..."
for port in 8080 8081 8082; do
    check_and_kill_port $port
done

# Verificar se as dependências estão instaladas
echo "📦 Verificando dependências..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "📥 Instalando dependências do monitoring..."
    pip install -r monitoring_requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Erro ao instalar dependências"
        exit 1
    fi
fi

echo "✅ Dependências verificadas"

# Verificar conexão com banco
echo "🔗 Testando conexão com banco de dados..."
python3 -c "
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
database_url = os.getenv('DATABASE_URL')

if not database_url:
    print('❌ DATABASE_URL não encontrada no .env')
    exit(1)

try:
    conn = psycopg2.connect(database_url)
    conn.close()
    print('✅ Conexão com banco OK')
except Exception as e:
    print(f'❌ Erro de conexão: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Problema com conexão ao banco"
    exit 1
fi

echo ""
echo "🌐 Iniciando servidor de monitoramento..."
echo "🔄 Auto-refresh a cada 30 segundos"
echo "📊 O dashboard será aberto automaticamente no navegador"
echo ""
echo "Para parar o servidor, pressione Ctrl+C"
echo ""

# Iniciar o servidor
python3 monitoring_app.py