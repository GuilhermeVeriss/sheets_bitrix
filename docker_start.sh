#!/bin/bash

echo "🚀 Iniciando Aplicações Aliest no Docker"
echo "========================================"

# Função para aguardar serviço estar pronto
wait_for_service() {
    local url=$1
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "✅ Serviço disponível em $url"
            return 0
        fi
        echo "⏳ Aguardando serviço ($attempt/$max_attempts)..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ Timeout aguardando serviço em $url"
    return 1
}

# Verificar variáveis de ambiente essenciais
echo "🔍 Verificando configuração..."
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL não configurada"
    exit 1
fi

if [ -z "$GOOGLE_CREDENTIALS_JSON" ]; then
    echo "❌ GOOGLE_CREDENTIALS_JSON não configurada"
    exit 1
fi

echo "✅ Configuração verificada"

# Instalar curl se não estiver disponível (para health checks)
if ! command -v curl &> /dev/null; then
    echo "📦 Instalando curl..."
    apt-get update && apt-get install -y curl
fi

# Função para cleanup na saída
cleanup() {
    echo "🛑 Parando aplicações..."
    kill $MAIN_PID $MONITOR_PID 2>/dev/null
    wait $MAIN_PID $MONITOR_PID 2>/dev/null
    echo "✅ Aplicações paradas"
    exit 0
}

# Capturar sinais para cleanup
trap cleanup SIGTERM SIGINT

echo "🔄 Iniciando aplicação principal..."
python main_app.py &
MAIN_PID=$!

# Aguardar um pouco para a aplicação principal inicializar
sleep 5

echo "📊 Iniciando interface de monitoramento..."
python monitoring_app.py &
MONITOR_PID=$!

# Aguardar um pouco para o monitoramento inicializar
sleep 3

echo ""
echo "🎯 Aplicações iniciadas:"
echo "   📈 Principal: Background process (sincronização contínua)"
echo "   📊 Monitoramento: http://localhost:8080"
echo ""
echo "✅ Sistema pronto! Logs abaixo:"
echo "================================"

# Aguardar os processos (para manter o container rodando)
wait $MAIN_PID $MONITOR_PID

# Se chegou aqui, um dos processos terminou
echo "⚠️  Um dos processos terminou. Verificando status..."

# Verificar qual processo terminou
if ! kill -0 $MAIN_PID 2>/dev/null; then
    echo "❌ Aplicação principal terminou"
    exit 1
fi

if ! kill -0 $MONITOR_PID 2>/dev/null; then
    echo "❌ Interface de monitoramento terminou"
    exit 1
fi