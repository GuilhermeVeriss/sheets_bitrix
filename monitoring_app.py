#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Interface de Monitoramento para Sistema de Sincronização Aliest
FastAPI Dashboard para acompanhar sincronizações em tempo real
"""

import os
import asyncio
import logging
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Conversor customizado para JSON
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def convert_datetime_fields(data):
    """Converte campos datetime e decimal para string de forma recursiva"""
    if isinstance(data, dict):
        return {key: convert_datetime_fields(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_datetime_fields(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return float(data)
    else:
        return data

app = FastAPI(
    title="Aliest Sync Monitor",
    description="Dashboard de monitoramento do sistema de sincronização",
    version="1.0.0"
)

# Configurar templates
templates = Jinja2Templates(directory="templates")

class DatabaseMonitor:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Conecta ao banco de dados"""
        try:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise Exception("DATABASE_URL não encontrada")
            
            self.connection = psycopg2.connect(
                database_url,
                cursor_factory=RealDictCursor
            )
            self.connection.autocommit = True
        except Exception as e:
            logging.error(f"Erro ao conectar ao banco: {str(e)}")
            raise
    
    def get_sync_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas gerais de sincronização"""
        try:
            with self.connection.cursor() as cursor:
                # Total de registros
                cursor.execute("SELECT COUNT(*) as total FROM leads_data;")
                total_leads = cursor.fetchone()['total']
                
                # Últimas sincronizações
                cursor.execute("""
                    SELECT COUNT(*) as total_syncs,
                           MAX(started_at) as last_sync,
                           AVG(records_processed) as avg_records
                    FROM sync_log
                    WHERE started_at >= NOW() - INTERVAL '24 hours';
                """)
                sync_stats = cursor.fetchone()
                
                # Registros por banco (aba)
                cursor.execute("""
                    SELECT banco, COUNT(*) as count 
                    FROM leads_data 
                    WHERE banco IS NOT NULL
                    GROUP BY banco 
                    ORDER BY count DESC;
                """)
                by_banco = cursor.fetchall()
                
                # Status das últimas sincronizações
                cursor.execute("""
                    SELECT status, COUNT(*) as count
                    FROM sync_log
                    WHERE started_at >= NOW() - INTERVAL '24 hours'
                    GROUP BY status;
                """)
                sync_status = cursor.fetchall()
                
                result = {
                    'total_leads': total_leads,
                    'total_syncs_24h': sync_stats['total_syncs'] or 0,
                    'last_sync': sync_stats['last_sync'],
                    'avg_records': float(sync_stats['avg_records']) if sync_stats['avg_records'] else 0,
                    'leads_by_banco': [dict(r) for r in by_banco],
                    'sync_status': [dict(r) for r in sync_status]
                }
                
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter estatísticas: {str(e)}")
            return {}
    
    def get_recent_syncs(self, limit: int = 10) -> List[Dict]:
        """Obtém as sincronizações mais recentes"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, sync_type, source, status,
                           records_processed, records_inserted, records_updated, records_failed,
                           started_at, finished_at, error_message,
                           EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_seconds
                    FROM sync_log
                    ORDER BY started_at DESC
                    LIMIT %s;
                """, (limit,))
                
                syncs = cursor.fetchall()
                result = [dict(sync) for sync in syncs]
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter sincronizações recentes: {str(e)}")
            return []
    
    def get_leads_by_consultor(self, limit: int = 10) -> List[Dict]:
        """Obtém estatísticas por consultor"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT consultor, COUNT(*) as total_leads,
                           COUNT(DISTINCT banco) as bancos_count,
                           MAX(created_at) as last_update
                    FROM leads_data
                    WHERE consultor IS NOT NULL AND consultor != ''
                    GROUP BY consultor
                    ORDER BY total_leads DESC
                    LIMIT %s;
                """, (limit,))
                
                result = [dict(r) for r in cursor.fetchall()]
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter dados por consultor: {str(e)}")
            return []
    
    def get_bitrix_processing_stats(self, hours_back: int = 24) -> Dict[str, Any]:
        """Obtém estatísticas do processamento Bitrix"""
        try:
            with self.connection.cursor() as cursor:
                cutoff_time = datetime.now() - timedelta(hours=hours_back)
                
                # Estatísticas gerais do processamento Bitrix
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_processed,
                        COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful,
                        COUNT(CASE WHEN status = 'FAILED' THEN 1 END) as failed,
                        COUNT(CASE WHEN status = 'SKIPPED' THEN 1 END) as skipped,
                        COUNT(CASE WHEN action_type = 'created' THEN 1 END) as deals_created,
                        COUNT(CASE WHEN action_type = 'updated' THEN 1 END) as deals_updated,
                        MAX(processed_at) as last_processing
                    FROM bitrix_processing_log
                    WHERE processed_at >= %s;
                """, (cutoff_time,))
                
                stats = cursor.fetchone()
                
                # Taxa de sucesso
                total = stats['total_processed'] or 0
                success_rate = (stats['successful'] / total * 100) if total > 0 else 0
                
                result = {
                    'period_hours': hours_back,
                    'total_processed': total,
                    'successful': stats['successful'] or 0,
                    'failed': stats['failed'] or 0,
                    'skipped': stats['skipped'] or 0,
                    'deals_created': stats['deals_created'] or 0,
                    'deals_updated': stats['deals_updated'] or 0,
                    'success_rate': round(success_rate, 1),
                    'last_processing': stats['last_processing']
                }
                
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter estatísticas Bitrix: {str(e)}")
            return {}
    
    def get_recent_bitrix_processing(self, limit: int = 20) -> List[Dict]:
        """Obtém processamentos Bitrix mais recentes"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        id, empresa, cnpj, telefone, consultor, banco,
                        status, action_type, deal_id, contact_id,
                        error_message, processed_at
                    FROM bitrix_processing_log
                    ORDER BY processed_at DESC
                    LIMIT %s;
                """, (limit,))
                
                records = cursor.fetchall()
                result = [dict(record) for record in records]
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter processamentos Bitrix recentes: {str(e)}")
            return []
    
    def get_bitrix_processing_by_status(self, hours_back: int = 24) -> List[Dict]:
        """Obtém contagem de processamentos por status"""
        try:
            with self.connection.cursor() as cursor:
                cutoff_time = datetime.now() - timedelta(hours=hours_back)
                
                cursor.execute("""
                    SELECT 
                        status,
                        action_type,
                        COUNT(*) as count,
                        MAX(processed_at) as last_occurrence
                    FROM bitrix_processing_log
                    WHERE processed_at >= %s
                    GROUP BY status, action_type
                    ORDER BY count DESC;
                """, (cutoff_time,))
                
                result = [dict(record) for record in cursor.fetchall()]
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter dados por status: {str(e)}")
            return []
    
    def get_bitrix_errors(self, limit: int = 10) -> List[Dict]:
        """Obtém os erros mais recentes do processamento Bitrix"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        empresa, cnpj, telefone, consultor, banco,
                        error_message, processed_at,
                        action_type
                    FROM bitrix_processing_log
                    WHERE status = 'FAILED' AND error_message IS NOT NULL
                    ORDER BY processed_at DESC
                    LIMIT %s;
                """, (limit,))
                
                result = [dict(record) for record in cursor.fetchall()]
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao obter erros Bitrix: {str(e)}")
            return []

    def get_system_health(self) -> Dict[str, Any]:
        """Verifica a saúde do sistema"""
        try:
            with self.connection.cursor() as cursor:
                # Verificar se há sincronizações recentes
                cursor.execute("""
                    SELECT COUNT(*) as recent_syncs
                    FROM sync_log
                    WHERE started_at >= NOW() - INTERVAL '1 hour';
                """)
                recent_syncs = cursor.fetchone()['recent_syncs']
                
                # Verificar se há erros recentes
                cursor.execute("""
                    SELECT COUNT(*) as recent_errors
                    FROM sync_log
                    WHERE status = 'ERROR' AND started_at >= NOW() - INTERVAL '24 hours';
                """)
                recent_errors = cursor.fetchone()['recent_errors']
                
                # Verificar última atualização de dados
                cursor.execute("""
                    SELECT MAX(updated_at) as last_data_update
                    FROM leads_data;
                """)
                last_update = cursor.fetchone()['last_data_update']
                
                # Determinar status geral
                if recent_errors > 0:
                    status = "warning"
                elif recent_syncs == 0:
                    status = "error"
                else:
                    status = "healthy"
                
                result = {
                    'status': status,
                    'recent_syncs': recent_syncs,
                    'recent_errors': recent_errors,
                    'last_data_update': last_update,
                    'database_connected': True
                }
                
                return convert_datetime_fields(result)
        except Exception as e:
            logging.error(f"Erro ao verificar saúde do sistema: {str(e)}")
            return {
                'status': 'error',
                'database_connected': False,
                'error': str(e)
            }

# Instância global do monitor
db_monitor = None

def get_monitor():
    """Lazy loading do monitor do banco"""
    global db_monitor
    if db_monitor is None:
        try:
            db_monitor = DatabaseMonitor()
        except Exception as e:
            logging.error(f"Erro ao inicializar monitor: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Erro de conexão com banco: {str(e)}")
    return db_monitor

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal do dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/stats")
async def get_stats():
    """API endpoint para estatísticas gerais"""
    try:
        monitor = get_monitor()
        stats = monitor.get_sync_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logging.error(f"Erro em /api/stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recent-syncs")
async def get_recent_syncs(limit: int = 10):
    """API endpoint para sincronizações recentes"""
    try:
        monitor = get_monitor()
        syncs = monitor.get_recent_syncs(limit)
        return JSONResponse(content=syncs)
    except Exception as e:
        logging.error(f"Erro em /api/recent-syncs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/consultores")
async def get_consultores(limit: int = 10):
    """API endpoint para estatísticas por consultor"""
    try:
        monitor = get_monitor()
        consultores = monitor.get_leads_by_consultor(limit)
        return JSONResponse(content=consultores)
    except Exception as e:
        logging.error(f"Erro em /api/consultores: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def get_health():
    """API endpoint para saúde do sistema"""
    try:
        monitor = get_monitor()
        health = monitor.get_system_health()
        return JSONResponse(content=health)
    except Exception as e:
        logging.error(f"Erro em /api/health: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bitrix/stats")
async def get_bitrix_stats(hours: int = 24):
    """API endpoint para estatísticas do processamento Bitrix"""
    try:
        monitor = get_monitor()
        stats = monitor.get_bitrix_processing_stats(hours)
        return JSONResponse(content=stats)
    except Exception as e:
        logging.error(f"Erro em /api/bitrix/stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bitrix/recent")
async def get_recent_bitrix_processing(limit: int = 20):
    """API endpoint para processamentos Bitrix recentes"""
    try:
        monitor = get_monitor()
        records = monitor.get_recent_bitrix_processing(limit)
        return JSONResponse(content=records)
    except Exception as e:
        logging.error(f"Erro em /api/bitrix/recent: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bitrix/status")
async def get_bitrix_status(hours: int = 24):
    """API endpoint para status dos processamentos Bitrix"""
    try:
        monitor = get_monitor()
        status_data = monitor.get_bitrix_processing_by_status(hours)
        return JSONResponse(content=status_data)
    except Exception as e:
        logging.error(f"Erro em /api/bitrix/status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bitrix/errors")
async def get_bitrix_errors(limit: int = 10):
    """API endpoint para erros do processamento Bitrix"""
    try:
        monitor = get_monitor()
        errors = monitor.get_bitrix_errors(limit)
        return JSONResponse(content=errors)
    except Exception as e:
        logging.error(f"Erro em /api/bitrix/errors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/live-data")
async def get_live_data():
    """API endpoint para dados ao vivo (usado pelo WebSocket simulation)"""
    try:
        monitor = get_monitor()
        stats = monitor.get_sync_stats()
        health = monitor.get_system_health()
        recent_syncs = monitor.get_recent_syncs(5)
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'stats': stats,
            'health': health,
            'recent_syncs': recent_syncs
        }
        
        return JSONResponse(content=result)
    except Exception as e:
        logging.error(f"Erro em /api/live-data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import socket
    
    def find_free_port(start_port=8080):
        """Encontra uma porta livre começando pela porta especificada"""
        for port in range(start_port, start_port + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('0.0.0.0', port))
                    return port
                except OSError:
                    continue
        raise Exception("Nenhuma porta livre encontrada")
    
    try:
        port = find_free_port(8080)
        print(f"🌐 Iniciando servidor na porta {port}")
        print(f"📊 Dashboard: http://localhost:{port}")
        
        uvicorn.run(
            "monitoring_app:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")
        print("💡 Tente parar outros serviços ou usar uma porta diferente")