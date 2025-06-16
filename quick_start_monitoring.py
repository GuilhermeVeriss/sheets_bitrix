#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script simples para iniciar o monitoramento
Resolve automaticamente conflitos de porta
"""

import os
import sys
import subprocess
import socket
import time

def find_free_port(start_port=8080):
    """Encontra uma porta livre"""
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return None

def kill_process_on_port(port):
    """Para processo na porta especificada"""
    try:
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'], 
            capture_output=True, text=True
        )
        if result.stdout.strip():
            pid = result.stdout.strip()
            subprocess.run(['kill', '-9', pid])
            print(f"✅ Processo {pid} parado na porta {port}")
            time.sleep(2)
            return True
    except:
        pass
    return False

def main():
    print("🚀 Quick Start - Aliest Monitoring")
    print("=================================")
    
    # Verificar .env
    if not os.path.exists('.env'):
        print("❌ Arquivo .env não encontrado!")
        sys.exit(1)
    
    # Tentar liberar porta 8080 primeiro
    if kill_process_on_port(8080):
        port = 8080
    else:
        port = find_free_port(8080)
    
    if not port:
        print("❌ Nenhuma porta disponível encontrada")
        sys.exit(1)
    
    print(f"🌐 Iniciando na porta {port}")
    print(f"📊 Dashboard: http://localhost:{port}")
    print("\nPressione Ctrl+C para parar\n")
    
    # Iniciar servidor
    os.environ['MONITORING_PORT'] = str(port)
    exec(open('monitoring_app.py').read())

if __name__ == "__main__":
    main()