#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Aplicação Principal de Sincronização Contínua
===========================================

Esta aplicação:
1. Executa startup.py uma única vez para inicializar o sistema
2. Mantém sincronização contínua dos dados entre Google Sheets e banco de dados
3. Permite configuração de intervalos de sincronização
4. Inclui tratamento de erros e recuperação automática
5. Fornece logs detalhados e estatísticas

Author: Sistema Aliest
Date: June 2025
"""

import os
import sys
import time
import signal
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Importar módulos locais
from startup import StartupModule
from sync_manager import SyncManager, SyncResult


@dataclass
class AppConfig:
    """Configuração da aplicação."""
    sync_interval_seconds: int = 300  # 5 minutos por padrão
    max_retries: int = 3
    retry_delay_seconds: int = 60
    enable_continuous_sync: bool = True
    log_level: str = "INFO"


class MainApp:
    """
    Aplicação principal que gerencia o ciclo completo de sincronização.
    
    Responsabilidades:
    1. Inicialização única do sistema via startup.py
    2. Sincronização contínua em loop
    3. Tratamento de erros e recuperação
    4. Controle de execução e parada graceful
    5. Estatísticas e monitoramento
    """
    
    def __init__(self, config: AppConfig = None):
        """
        Inicializa a aplicação principal.
        
        Args:
            config (AppConfig): Configurações da aplicação
        """
        self.config = config or AppConfig()
        self.startup_module: Optional[StartupModule] = None
        self.sync_manager: Optional[SyncManager] = None
        self.is_running = False
        self.sync_thread: Optional[threading.Thread] = None
        
        # Configurar logging
        self._setup_logging()
        
        # Configurar handlers para parada graceful
        self._setup_signal_handlers()
        
        # Estatísticas da aplicação
        self.app_stats = {
            'start_time': None,
            'total_sync_cycles': 0,
            'successful_syncs': 0,
            'failed_syncs': 0,
            'last_sync_time': None,
            'last_sync_result': None
        }
        
    def _setup_logging(self):
        """Configura o sistema de logging para a aplicação."""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        # Configurar handler para arquivo
        file_handler = logging.FileHandler('main_app.log', encoding='utf-8')
        file_handler.setLevel(log_level)
        
        # Configurar handler para console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        
        # Formato dos logs
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Configurar logger principal
        self.logger = logging.getLogger('MainApp')
        self.logger.setLevel(log_level)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Evitar duplicação de logs
        self.logger.propagate = False
        
    def _setup_signal_handlers(self):
        """Configura handlers para parada graceful."""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 Sinal recebido ({signum}). Iniciando parada graceful...")
            self.stop()
            
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
        
    def initialize_system(self) -> bool:
        """
        Executa a inicialização completa do sistema (startup.py).
        
        Returns:
            bool: True se inicialização foi bem-sucedida
        """
        self.logger.info("🚀 Iniciando sistema de sincronização...")
        
        try:
            # Executar startup
            self.startup_module = StartupModule()
            
            if not self.startup_module.startup():
                self.logger.error("❌ Falha na inicialização do sistema")
                return False
                
            # Executar sincronização inicial com dados das planilhas
            spreadsheet_id = os.getenv('SPREADSHEET_ID')
            sheet_ids = [0, 829477907, 797561708, 1064048522]  # IDs das abas
            
            if spreadsheet_id:
                self.logger.info("📊 Executando carga inicial de dados...")
                initial_sync = self.startup_module.populate_table_from_sheets(
                    spreadsheet_id, sheet_ids
                )
                
                if initial_sync:
                    self.logger.info("✅ Carga inicial de dados concluída")
                else:
                    self.logger.warning("⚠️ Carga inicial teve problemas, mas continuando...")
            else:
                self.logger.warning("⚠️ SPREADSHEET_ID não configurado - pulando carga inicial")
            
            # Inicializar gerenciador de sincronização
            self.sync_manager = SyncManager(self.startup_module)
            
            self.logger.info("🎉 Sistema inicializado com sucesso!")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro durante inicialização: {str(e)}")
            return False
    
    def _perform_sync_cycle(self) -> bool:
        """
        Executa um ciclo de sincronização.
        
        Returns:
            bool: True se sincronização foi bem-sucedida
        """
        if not self.sync_manager:
            self.logger.error("❌ Sync manager não inicializado")
            return False
            
        try:
            spreadsheet_id = os.getenv('SPREADSHEET_ID')
            sheet_ids = [0, 829477907, 797561708, 1064048522]
            
            if not spreadsheet_id:
                self.logger.error("❌ SPREADSHEET_ID não configurado")
                return False
            
            self.logger.info("🔄 Iniciando ciclo de sincronização...")
            
            # Executar sincronização com detecção de mudanças
            result = self.sync_manager.clear_and_resync_database(spreadsheet_id, sheet_ids)
            
            # Atualizar estatísticas
            self.app_stats['total_sync_cycles'] += 1
            self.app_stats['last_sync_time'] = datetime.now()
            self.app_stats['last_sync_result'] = result
            
            if result.error_message:
                self.app_stats['failed_syncs'] += 1
                self.logger.error(f"❌ Sincronização falhou: {result.error_message}")
                return False
            else:
                self.app_stats['successful_syncs'] += 1
                
                # Log das mudanças detectadas
                changes = result.changes_detected
                if changes['total_new'] > 0 or changes['total_removed'] > 0:
                    self.logger.info(f"🔍 Mudanças detectadas: {changes['summary']}")
                    
                    # Log detalhado de novos registros
                    if result.new_records:
                        self.logger.info(f"➕ Novos registros:")
                        for i, record in enumerate(result.new_records[:5]):  # Mostrar apenas os primeiros 5
                            nome = record.get('nome', 'N/A')
                            empresa = record.get('empresa', 'N/A')
                            banco = record.get('banco', 'N/A')
                            self.logger.info(f"   {i+1}. {nome} - {empresa} ({banco})")
                        if len(result.new_records) > 5:
                            self.logger.info(f"   ... e mais {len(result.new_records) - 5} registros")
                    
                    # Log detalhado de registros removidos
                    if result.removed_records:
                        self.logger.info(f"🗑️ Registros removidos:")
                        for i, record in enumerate(result.removed_records[:3]):  # Mostrar apenas os primeiros 3
                            nome = record.get('nome', 'N/A')
                            empresa = record.get('empresa', 'N/A')
                            banco = record.get('banco', 'N/A')
                            self.logger.info(f"   {i+1}. {nome} - {empresa} ({banco})")
                        if len(result.removed_records) > 3:
                            self.logger.info(f"   ... e mais {len(result.removed_records) - 3} registros")
                else:
                    self.logger.info("✔️ Nenhuma mudança detectada nos dados")
                
                self.logger.info(f"✅ Sincronização concluída: {result.total_inserted} registros, {result.sync_duration:.2f}s")
                return True
                
        except Exception as e:
            self.app_stats['failed_syncs'] += 1
            self.logger.error(f"❌ Erro durante sincronização: {str(e)}")
            return False
    
    def _continuous_sync_loop(self):
        """Loop principal de sincronização contínua."""
        self.logger.info(f"🔄 Iniciando loop de sincronização contínua (intervalo: {self.config.sync_interval_seconds}s)")
        
        while self.is_running:
            try:
                # Executar ciclo de sincronização
                success = self._perform_sync_cycle()
                
                if not success:
                    # Em caso de falha, tentar novamente com delay
                    retry_count = 0
                    while retry_count < self.config.max_retries and self.is_running:
                        self.logger.warning(f"⚠️ Tentativa {retry_count + 1}/{self.config.max_retries} após falha")
                        time.sleep(self.config.retry_delay_seconds)
                        
                        if self._perform_sync_cycle():
                            self.logger.info("✅ Recuperação bem-sucedida")
                            break
                            
                        retry_count += 1
                    
                    if retry_count >= self.config.max_retries:
                        self.logger.error(f"❌ Máximo de tentativas ({self.config.max_retries}) excedido")
                
                # Aguardar próximo ciclo
                if self.is_running:
                    self.logger.debug(f"⏸️ Aguardando {self.config.sync_interval_seconds}s para próximo ciclo...")
                    time.sleep(self.config.sync_interval_seconds)
                    
            except Exception as e:
                self.logger.error(f"❌ Erro no loop de sincronização: {str(e)}")
                if self.is_running:
                    time.sleep(self.config.retry_delay_seconds)
        
        self.logger.info("🛑 Loop de sincronização finalizado")
    
    def start(self) -> bool:
        """
        Inicia a aplicação completa.
        
        Returns:
            bool: True se aplicação foi iniciada com sucesso
        """
        self.logger.info("🚀 Iniciando aplicação de sincronização...")
        
        # 1. Inicializar sistema
        if not self.initialize_system():
            return False
        
        # 2. Marcar como executando
        self.is_running = True
        self.app_stats['start_time'] = datetime.now()
        
        # 3. Verificar se deve executar sincronização contínua
        if not self.config.enable_continuous_sync:
            self.logger.info("ℹ️ Sincronização contínua desabilitada. Executando apenas inicialização.")
            return True
        
        # 4. Iniciar thread de sincronização contínua
        self.sync_thread = threading.Thread(target=self._continuous_sync_loop, daemon=True)
        self.sync_thread.start()
        
        self.logger.info("✅ Aplicação iniciada com sucesso!")
        self.logger.info("💡 Use Ctrl+C para parar a aplicação gracefully")
        
        return True
    
    def stop(self):
        """Para a aplicação gracefully."""
        self.logger.info("🛑 Parando aplicação...")
        
        self.is_running = False
        
        # Aguardar thread de sincronização terminar
        if self.sync_thread and self.sync_thread.is_alive():
            self.logger.info("⏳ Aguardando thread de sincronização finalizar...")
            self.sync_thread.join(timeout=30)
        
        # Fechar conexões
        if self.startup_module:
            self.startup_module.close()
            
        self.logger.info("✅ Aplicação parada com sucesso")
    
    def get_app_statistics(self) -> Dict[str, Any]:
        """
        Obtém estatísticas da aplicação.
        
        Returns:
            Dict: Estatísticas detalhadas
        """
        uptime = None
        if self.app_stats['start_time']:
            uptime = (datetime.now() - self.app_stats['start_time']).total_seconds()
        
        stats = {
            'application': {
                'is_running': self.is_running,
                'start_time': self.app_stats['start_time'],
                'uptime_seconds': uptime,
                'total_sync_cycles': self.app_stats['total_sync_cycles'],
                'successful_syncs': self.app_stats['successful_syncs'],
                'failed_syncs': self.app_stats['failed_syncs'],
                'success_rate_percent': (
                    (self.app_stats['successful_syncs'] / self.app_stats['total_sync_cycles'] * 100)
                    if self.app_stats['total_sync_cycles'] > 0 else 0
                ),
                'last_sync_time': self.app_stats['last_sync_time']
            },
            'configuration': {
                'sync_interval_seconds': self.config.sync_interval_seconds,
                'max_retries': self.config.max_retries,
                'retry_delay_seconds': self.config.retry_delay_seconds,
                'continuous_sync_enabled': self.config.enable_continuous_sync
            }
        }
        
        # Adicionar estatísticas do banco se disponível
        if self.sync_manager:
            try:
                data_summary = self.sync_manager.get_current_data_summary()
                sync_stats = self.sync_manager.get_sync_statistics(24)
                
                stats['database'] = data_summary
                stats['sync_history'] = sync_stats
            except Exception as e:
                self.logger.warning(f"⚠️ Erro ao obter estatísticas do banco: {str(e)}")
        
        return stats
    
    def print_status_report(self):
        """Imprime relatório de status da aplicação."""
        stats = self.get_app_statistics()
        
        print("\n" + "="*60)
        print("📊 RELATÓRIO DE STATUS DA APLICAÇÃO")
        print("="*60)
        
        # Status da aplicação
        app_stats = stats['application']
        print(f"🔹 Status: {'🟢 Executando' if app_stats['is_running'] else '🔴 Parado'}")
        if app_stats['start_time']:
            print(f"🔹 Iniciado em: {app_stats['start_time'].strftime('%d/%m/%Y %H:%M:%S')}")
        if app_stats['uptime_seconds']:
            uptime_str = str(timedelta(seconds=int(app_stats['uptime_seconds'])))
            print(f"🔹 Tempo ativo: {uptime_str}")
        
        print(f"🔹 Ciclos de sincronização: {app_stats['total_sync_cycles']}")
        print(f"🔹 Sucessos: {app_stats['successful_syncs']} | Falhas: {app_stats['failed_syncs']}")
        print(f"🔹 Taxa de sucesso: {app_stats['success_rate_percent']:.1f}%")
        
        if app_stats['last_sync_time']:
            print(f"🔹 Última sincronização: {app_stats['last_sync_time'].strftime('%d/%m/%Y %H:%M:%S')}")
        
        # Configuração
        config_stats = stats['configuration']
        print(f"\n⚙️ CONFIGURAÇÃO:")
        print(f"🔹 Intervalo de sincronização: {config_stats['sync_interval_seconds']}s")
        print(f"🔹 Máximo de tentativas: {config_stats['max_retries']}")
        print(f"🔹 Delay entre tentativas: {config_stats['retry_delay_seconds']}s")
        
        # Dados do banco
        if 'database' in stats and stats['database']:
            db_stats = stats['database']
            print(f"\n💾 DADOS NO BANCO:")
            print(f"🔹 Total de registros: {db_stats.get('total_records', 'N/A')}")
            
            if db_stats.get('records_by_banco'):
                print(f"🔹 Registros por aba:")
                for banco_stat in db_stats['records_by_banco'][:5]:  # Top 5
                    print(f"   📋 {banco_stat['banco']}: {banco_stat['count']} registros")
        
        print("="*60)
    
    def run_forever(self):
        """
        Executa a aplicação indefinidamente até ser interrompida.
        """
        if not self.start():
            self.logger.error("❌ Falha ao iniciar aplicação")
            return
        
        try:
            # Imprimir status inicial
            time.sleep(2)  # Aguardar um pouco para logs se estabilizarem
            self.print_status_report()
            
            # Loop principal - aguardar até ser interrompido
            while self.is_running:
                time.sleep(10)  # Check a cada 10 segundos
                
        except KeyboardInterrupt:
            self.logger.info("⏹️ Interrupção do usuário detectada")
        finally:
            self.stop()


def main():
    """Função principal da aplicação."""
    print("🚀 Aplicação de Sincronização Aliest")
    print("=====================================")
    
    # Configurar aplicação baseado em variáveis de ambiente
    config = AppConfig(
        sync_interval_seconds=int(os.getenv('SYNC_INTERVAL_SECONDS', '120')),  # 2 minutos padrão
        max_retries=int(os.getenv('MAX_RETRIES', '3')),
        retry_delay_seconds=int(os.getenv('RETRY_DELAY_SECONDS', '60')),
        enable_continuous_sync=os.getenv('ENABLE_CONTINUOUS_SYNC', 'true').lower() == 'true',
        log_level=os.getenv('LOG_LEVEL', 'INFO')
    )
    
    app = MainApp(config)
    
    # Verificar se é execução única ou contínua
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        print("🔄 Modo execução única (sem sincronização contínua)")
        config.enable_continuous_sync = False
        
        if app.start():
            print("✅ Execução única concluída com sucesso!")
            app.print_status_report()
        else:
            print("❌ Falha na execução única")
        
        app.stop()
    else:
        print("🔄 Modo sincronização contínua")
        print(f"⏱️ Intervalo de sincronização: {config.sync_interval_seconds} segundos")
        print("💡 Use Ctrl+C para parar ou execute com --once para execução única")
        
        app.run_forever()


if __name__ == "__main__":
    main()