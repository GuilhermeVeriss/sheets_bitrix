#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo de inicialização para sincronização com banco de dados PostgreSQL.
Este módulo gerencia a conexão com o banco e cria/atualiza a estrutura de tabelas necessárias.
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values, Json
from psycopg2 import sql
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from datetime import datetime

# Importar módulos locais
from google_sheets_api import GoogleSheetsAPI
from bitrix_api import BitrixAPI


class StartupModule:
    """
    Módulo de inicialização responsável por:
    1. Configurar logging
    2. Conectar ao banco PostgreSQL
    3. Criar/atualizar estrutura de tabelas
    4. Inicializar APIs (Google Sheets e Bitrix24)
    5. Sincronizar dados conforme necessário
    """
    
    def __init__(self, env_file: str = ".env"):
        """
        Inicializa o módulo de startup.
        
        Args:
            env_file (str): Caminho para o arquivo .env com configurações
        """
        self.env_file = env_file
        self.connection = None
        self.google_sheets = None
        self.bitrix = None
        
        # Configurar logging
        self._setup_logging()
        
        # Carregar variáveis de ambiente
        self._load_environment()
        
    def _setup_logging(self):
        """Configura o sistema de logging."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _load_environment(self):
        """Carrega variáveis de ambiente do arquivo .env."""
        load_dotenv(self.env_file)
        
        # Validar variáveis obrigatórias
        required_vars = ['DATABASE_URL', 'BITRIX_URL', 'GOOGLE_CREDENTIALS_JSON']
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
                
        if missing_vars:
            raise ValueError(f"Variáveis de ambiente obrigatórias não encontradas: {missing_vars}")
            
        self.logger.info("✅ Variáveis de ambiente carregadas com sucesso")
        
    def connect_database(self) -> bool:
        """
        Conecta ao banco de dados PostgreSQL.
        
        Returns:
            bool: True se conectado com sucesso, False caso contrário
        """
        try:
            database_url = os.getenv('DATABASE_URL')
            self.connection = psycopg2.connect(
                database_url,
                cursor_factory=RealDictCursor
            )
            self.connection.autocommit = True
            
            # Testar conexão
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT version();")
                result = cursor.fetchone()
                # Com RealDictCursor, precisamos acessar pelo nome da coluna
                version = result['version'] if result else "Unknown version"
                
            self.logger.info(f"✅ Conectado ao PostgreSQL: {version}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao conectar ao banco de dados: {str(e)}")
            return False
            
    def create_tables(self) -> bool:
        """
        Cria as tabelas necessárias no banco de dados.
        
        Returns:
            bool: True se tabelas foram criadas/atualizadas com sucesso
        """
        if not self.connection:
            self.logger.error("❌ Conexão com banco não estabelecida")
            return False
            
        try:
            with self.connection.cursor() as cursor:
                # Sempre dropar e recriar a tabela leads_data para garantir estrutura correta
                self.logger.info("🔄 Recriando tabela leads_data...")
                
                drop_and_create_sql = """
                -- Dropar tabela existente se houver
                DROP TABLE IF EXISTS leads_data CASCADE;
                
                -- Criar tabela principal de dados (sem UNIQUE constraints)
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
                    banco VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Criar índices para otimizar consultas (sem UNIQUE)
                CREATE INDEX idx_leads_cnpj ON leads_data(cnpj);
                CREATE INDEX idx_leads_telefone ON leads_data(telefone);
                CREATE INDEX idx_leads_consultor ON leads_data(consultor);
                CREATE INDEX idx_leads_banco ON leads_data(banco);
                CREATE INDEX idx_leads_data ON leads_data(data);
                
                -- Criar tabela de log de sincronização (se não existir)
                CREATE TABLE IF NOT EXISTS sync_log (
                    id SERIAL PRIMARY KEY,
                    sync_type VARCHAR(50) NOT NULL,
                    source VARCHAR(100) NOT NULL,
                    records_processed INTEGER DEFAULT 0,
                    records_inserted INTEGER DEFAULT 0,
                    records_updated INTEGER DEFAULT 0,
                    records_failed INTEGER DEFAULT 0,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'RUNNING',
                    error_message TEXT,
                    details JSONB
                );
                
                -- Criar tabela de log de processamento Bitrix (nova)
                CREATE TABLE IF NOT EXISTS bitrix_processing_log (
                    id SERIAL PRIMARY KEY,
                    data DATE,
                    cnpj VARCHAR(20),
                    telefone VARCHAR(20),
                    nome VARCHAR(255),
                    empresa VARCHAR(500),
                    consultor VARCHAR(255),
                    forma_prospeccao VARCHAR(255),
                    etapa VARCHAR(255),
                    banco VARCHAR(255),
                    status VARCHAR(20) NOT NULL,  -- 'SUCCESS', 'FAILED', 'SKIPPED'
                    action_type VARCHAR(20),     -- 'created', 'updated', 'skipped'
                    deal_id INTEGER,             -- ID do deal no Bitrix
                    contact_id INTEGER,          -- ID do contato no Bitrix
                    error_message TEXT,          -- Mensagem de erro se houver
                    processing_details JSONB,    -- Detalhes completos do processamento
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sync_session_id INTEGER REFERENCES sync_log(id) ON DELETE SET NULL
                );
                
                -- Criar índices para a nova tabela
                CREATE INDEX IF NOT EXISTS idx_bitrix_log_status ON bitrix_processing_log(status);
                CREATE INDEX IF NOT EXISTS idx_bitrix_log_empresa ON bitrix_processing_log(empresa);
                CREATE INDEX IF NOT EXISTS idx_bitrix_log_consultor ON bitrix_processing_log(consultor);
                CREATE INDEX IF NOT EXISTS idx_bitrix_log_processed_at ON bitrix_processing_log(processed_at);
                CREATE INDEX IF NOT EXISTS idx_bitrix_log_sync_session ON bitrix_processing_log(sync_session_id);
                CREATE INDEX IF NOT EXISTS idx_bitrix_log_deal_id ON bitrix_processing_log(deal_id);
                
                -- Função para atualizar updated_at automaticamente
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
                
                -- Trigger para atualizar updated_at
                CREATE TRIGGER update_leads_data_updated_at
                    BEFORE UPDATE ON leads_data
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
                """
                
                cursor.execute(drop_and_create_sql)
                self.logger.info("✅ Tabela leads_data recriada com sucesso (permite duplicatas)")
                
                # Verificar estrutura da tabela
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'leads_data'
                    ORDER BY ordinal_position;
                """)
                
                columns = cursor.fetchall()
                self.logger.info(f"📋 Estrutura da tabela 'leads_data': {len(columns)} colunas")
                for col in columns:
                    self.logger.debug(f"  - {col['column_name']}: {col['data_type']} (NULL: {col['is_nullable']})")
                    
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao criar tabelas: {str(e)}")
            return False
            
    def initialize_apis(self) -> bool:
        """
        Inicializa as APIs do Google Sheets e Bitrix24.
        
        Returns:
            bool: True se APIs foram inicializadas com sucesso
        """
        try:
            # Inicializar Google Sheets API usando variáveis de ambiente
            self.google_sheets = GoogleSheetsAPI()  # Agora usa GOOGLE_CREDENTIALS_JSON por padrão
            self.logger.info("✅ Google Sheets API inicializada")
            
            # Inicializar Bitrix24 API
            bitrix_url = os.getenv('BITRIX_URL')
            self.bitrix = BitrixAPI(bitrix_url)
            self.logger.info("✅ Bitrix24 API inicializada")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar APIs: {str(e)}")
            return False
            
    def test_connections(self) -> Dict[str, bool]:
        """
        Testa todas as conexões (banco, APIs).
        
        Returns:
            Dict[str, bool]: Status de cada conexão
        """
        results = {}
        
        # Testar banco de dados
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                results['database'] = True
                self.logger.info("✅ Conexão com banco de dados: OK")
        except Exception as e:
            results['database'] = False
            self.logger.error(f"❌ Conexão com banco de dados: {str(e)}")
            
        # Testar Google Sheets
        try:
            spreadsheet_id = os.getenv('SPREADSHEET_ID', '')
            sheets_info = self.google_sheets.get_sheets_names_and_ids(spreadsheet_id)
            results['google_sheets'] = len(sheets_info) > 0
            self.logger.info(f"✅ Google Sheets API: OK ({len(sheets_info)} abas encontradas)")
        except Exception as e:
            results['google_sheets'] = False
            self.logger.error(f"❌ Google Sheets API: {str(e)}")
            
        # Testar Bitrix24
        try:
            # Fazer uma requisição simples para testar
            test_result = self.bitrix._make_request('crm.contact.list', {'start': 0, 'select': ['ID']})
            results['bitrix'] = 'result' in test_result
            self.logger.info("✅ Bitrix24 API: OK")
        except Exception as e:
            results['bitrix'] = False
            self.logger.error(f"❌ Bitrix24 API: {str(e)}")
            
        return results
        
    def log_sync_start(self, sync_type: str, source: str, details: Dict = None) -> int:
        """
        Registra o início de uma sincronização no log.
        
        Args:
            sync_type (str): Tipo de sincronização (ex: 'sheets_to_db', 'db_to_bitrix')
            source (str): Fonte dos dados
            details (Dict): Detalhes adicionais
            
        Returns:
            int: ID do registro de log criado
        """
        try:
            with self.connection.cursor() as cursor:
                # Converter dict para JSON usando psycopg2.extras.Json
                details_json = Json(details) if details is not None else None
                
                cursor.execute("""
                    INSERT INTO sync_log (sync_type, source, started_at, details)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id;
                """, (sync_type, source, datetime.now(), details_json))
                
                log_id = cursor.fetchone()['id']
                self.logger.info(f"📝 Sincronização iniciada: {sync_type} (Log ID: {log_id})")
                return log_id
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao registrar início da sincronização: {str(e)}")
            return -1
            
    def log_sync_end(self, log_id: int, processed: int = 0, inserted: int = 0, 
                     updated: int = 0, failed: int = 0, status: str = 'SUCCESS', 
                     error_message: str = None):
        """
        Registra o fim de uma sincronização no log.
        
        Args:
            log_id (int): ID do registro de log
            processed (int): Número de registros processados
            inserted (int): Número de registros inseridos
            updated (int): Número de registros atualizados
            failed (int): Número de registros que falharam
            status (str): Status final ('SUCCESS', 'ERROR', 'PARTIAL')
            error_message (str): Mensagem de erro, se houver
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE sync_log 
                    SET finished_at = %s, records_processed = %s, records_inserted = %s,
                        records_updated = %s, records_failed = %s, status = %s, error_message = %s
                    WHERE id = %s;
                """, (datetime.now(), processed, inserted, updated, failed, status, error_message, log_id))
                
                self.logger.info(f"📝 Sincronização finalizada: Log ID {log_id} - {status}")
                self.logger.info(f"   Processados: {processed}, Inseridos: {inserted}, Atualizados: {updated}, Falharam: {failed}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao registrar fim da sincronização: {str(e)}")
            
    def startup(self) -> bool:
        """
        Executa todo o processo de inicialização.
        
        Returns:
            bool: True se inicialização foi bem-sucedida
        """
        self.logger.info("🚀 Iniciando processo de startup...")
        
        # 1. Conectar ao banco
        if not self.connect_database():
            return False
            
        # 2. Criar/atualizar tabelas
        if not self.create_tables():
            return False
            
        # 3. Inicializar APIs
        if not self.initialize_apis():
            return False
            
        # 4. Testar todas as conexões
        test_results = self.test_connections()
        
        all_success = all(test_results.values())
        
        if all_success:
            self.logger.info("🎉 Startup concluído com sucesso!")
            self.logger.info("💡 Sistema pronto para sincronização de dados")
        else:
            failed_connections = [k for k, v in test_results.items() if not v]
            self.logger.warning(f"⚠️ Startup parcialmente bem-sucedido. Falhas em: {failed_connections}")
            
        return all_success
        
    def close(self):
        """Fecha todas as conexões."""
        if self.connection:
            self.connection.close()
            self.logger.info("🔌 Conexão com banco de dados fechada")
            
    def _validate_all_sheets_data(self, spreadsheet_id: str, sheet_ids: List[int]) -> Dict[str, Any]:
        """
        Valida e busca dados de TODAS as abas especificadas ANTES de fazer qualquer alteração no banco.
        
        Esta função é crítica para garantir que nenhuma atualização do banco aconteça se houver
        qualquer erro ao buscar dados das planilhas.
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets
            sheet_ids (List[int]): Lista de IDs das abas para validar
            
        Returns:
            Dict[str, Any]: Resultado da validação com dados de todas as abas ou erro
            
        Raises:
            Exception: Se qualquer aba falhar na busca dos dados
        """
        validation_result = {
            'success': False,
            'sheets_data': {},
            'total_records': 0,
            'failed_sheets': [],
            'error_message': None
        }
        
        try:
            self.logger.info(f"🔍 Validando dados de {len(sheet_ids)} abas ANTES de atualizar banco...")
            
            # Tentar buscar dados de TODAS as abas primeiro
            for sheet_id in sheet_ids:
                try:
                    self.logger.info(f"📊 Validando aba ID: {sheet_id}")
                    
                    # Tentar obter dados da aba - SE FALHAR AQUI, PARAR TUDO
                    sheet_data = self.google_sheets.get_sheet_data_as_json(
                        spreadsheet_id, 
                        sheet_id
                    )
                    
                    sheet_name = sheet_data['sheet_info']['sheet_name']
                    rows_data = sheet_data['data']
                    
                    # Validar se a aba tem estrutura mínima esperada
                    if 'sheet_info' not in sheet_data or 'data' not in sheet_data:
                        raise Exception(f"Estrutura de dados inválida retornada pela aba '{sheet_name}'")
                    
                    # Armazenar dados da aba
                    validation_result['sheets_data'][sheet_id] = {
                        'sheet_name': sheet_name,
                        'data': rows_data,
                        'total_rows': len(rows_data),
                        'sheet_info': sheet_data['sheet_info']
                    }
                    
                    validation_result['total_records'] += len(rows_data)
                    
                    self.logger.info(f"✅ Aba '{sheet_name}' validada: {len(rows_data)} registros")
                    
                except Exception as sheet_error:
                    error_msg = f"Erro ao buscar dados da aba ID {sheet_id}: {str(sheet_error)}"
                    self.logger.error(f"❌ {error_msg}")
                    
                    validation_result['failed_sheets'].append({
                        'sheet_id': sheet_id,
                        'error': str(sheet_error)
                    })
                    
                    # SE QUALQUER ABA FALHAR, PARAR IMEDIATAMENTE
                    validation_result['error_message'] = error_msg
                    raise Exception(error_msg)
            
            # Se chegou aqui, todas as abas foram validadas com sucesso
            validation_result['success'] = True
            self.logger.info(f"✅ Todas as {len(sheet_ids)} abas validadas com sucesso!")
            self.logger.info(f"📊 Total de registros encontrados: {validation_result['total_records']}")
            
            return validation_result
            
        except Exception as e:
            validation_result['error_message'] = str(e)
            self.logger.error(f"❌ Falha na validação das abas: {str(e)}")
            self.logger.error("🚫 ATUALIZAÇÃO DO BANCO CANCELADA - dados das planilhas não puderam ser obtidos")
            raise e
    
    def populate_table_from_sheets(self, spreadsheet_id: str, sheet_ids: List[int]) -> bool:
        """
        Popula a tabela leads_data com dados do Google Sheets.
        Remove todos os dados existentes e popula com dados das abas especificadas.
        
        IMPORTANTE: Valida TODAS as abas ANTES de fazer qualquer alteração no banco.
        Se qualquer aba falhar na busca, a atualização do banco é cancelada.
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets
            sheet_ids (List[int]): Lista de IDs das abas para processar
            
        Returns:
            bool: True se a operação foi bem-sucedida
        """
        if not self.connection or not self.google_sheets:
            self.logger.error("❌ Conexão com banco ou Google Sheets não estabelecida")
            return False
            
        log_id = self.log_sync_start("sheets_to_db_validated", f"sheets_{sheet_ids}")
        
        try:
            # 1. PRIMEIRO: Validar TODAS as abas antes de fazer qualquer alteração no banco
            self.logger.info("🔒 VALIDAÇÃO CRÍTICA: Verificando dados de todas as abas antes de atualizar banco...")
            
            try:
                validation_result = self._validate_all_sheets_data(spreadsheet_id, sheet_ids)
            except Exception as validation_error:
                self.logger.error(f"❌ VALIDAÇÃO FALHOU: {str(validation_error)}")
                self.logger.error("🚫 Atualização do banco CANCELADA por falha na validação das planilhas")
                self.log_sync_end(log_id, status='ERROR', error_message=f"Validação falhou: {str(validation_error)}")
                return False
            
            if not validation_result['success']:
                self.logger.error("❌ VALIDAÇÃO FALHOU: Nem todas as abas puderam ser carregadas")
                self.logger.error("🚫 Atualização do banco CANCELADA")
                self.log_sync_end(log_id, status='ERROR', error_message=validation_result['error_message'])
                return False
            
            self.logger.info("✅ VALIDAÇÃO APROVADA: Todas as abas carregadas com sucesso")
            self.logger.info(f"📊 Total de {validation_result['total_records']} registros validados")
            
            # 2. AGORA é seguro limpar e atualizar o banco (dados já validados)
            self.logger.info("🗑️ Limpando tabela leads_data (dados validados, operação segura)...")
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM leads_data;")
                self.logger.info("✅ Dados existentes removidos da tabela leads_data")
            
            total_processed = 0
            total_inserted = 0
            total_failed = 0
            
            # 3. Processar cada aba usando os dados já validados
            for sheet_id in sheet_ids:
                try:
                    # Usar dados já validados ao invés de buscar novamente
                    validated_sheet = validation_result['sheets_data'][sheet_id]
                    sheet_name = validated_sheet['sheet_name']
                    rows_data = validated_sheet['data']
                    
                    self.logger.info(f"📊 Processando aba '{sheet_name}': {len(rows_data)} registros")
                    
                    # Preparar lista para inserção em massa
                    insert_values = []
                    failed_count = 0
                    
                    for row in rows_data:
                        try:
                            # Mapear campos do Google Sheets para campos da tabela
                            data_value = row.get('Data', row.get('data', ''))
                            cnpj_value = row.get('CNPJ', row.get('cnpj', ''))
                            telefone_value = row.get('TELEFONE', row.get('telefone', ''))
                            nome_value = row.get('NOME', row.get('nome', ''))
                            empresa_value = row.get('EMPRESA', row.get('empresa', ''))
                            consultor_value = row.get('CONSULTOR', row.get('consultor', ''))
                            forma_prospeccao_value = row.get('Forma Prospecção', row.get('forma_prospeccao', ''))
                            etapa_value = row.get('Etapa', row.get('etapa', ''))
                            
                            # Validar se tem CNPJ OU TELEFONE (pelo menos um dos dois)
                            has_cnpj = cnpj_value and cnpj_value.strip()
                            has_telefone = telefone_value and telefone_value.strip()
                            
                            if not (has_cnpj or has_telefone):
                                continue  # Pular se não tem nem CNPJ nem telefone
                                
                            # Converter data para o formato adequado
                            parsed_date = None
                            if data_value and isinstance(data_value, str) and data_value.strip():
                                try:
                                    parsed_date = datetime.strptime(data_value.strip(), '%d/%m/%Y').date()
                                except ValueError:
                                    self.logger.warning(f"⚠️ Formato de data inválido: {data_value}")
                            
                            # Adicionar valores à lista para inserção em massa
                            insert_values.append((
                                parsed_date,
                                cnpj_value or None,
                                telefone_value or None,
                                nome_value or None,
                                empresa_value or None,
                                consultor_value or None,
                                forma_prospeccao_value or None,
                                etapa_value or None,
                                sheet_name  # Usar nome da aba como "Banco"
                            ))
                            
                        except Exception as row_error:
                            failed_count += 1
                            self.logger.warning(f"⚠️ Erro ao preparar registro: {str(row_error)}")
                            
                    # 4. Inserir dados em massa na tabela (permitindo duplicatas)
                    inserted_count = 0
                    if insert_values:
                        with self.connection.cursor() as cursor:
                            insert_sql = """
                            INSERT INTO leads_data 
                            (data, cnpj, telefone, nome, empresa, consultor, forma_prospeccao, etapa, banco)
                            VALUES %s
                            """
                            
                            # Executar inserção em massa
                            execute_values(cursor, insert_sql, insert_values)
                            inserted_count = len(insert_values)

                    total_processed += len(rows_data)
                    total_inserted += inserted_count
                    total_failed += failed_count
                    
                    self.logger.info(f"✅ Aba '{sheet_name}': {inserted_count} inseridos, {failed_count} falharam")
                    
                except Exception as sheet_error:
                    self.logger.error(f"❌ Erro ao processar aba ID {sheet_id}: {str(sheet_error)}")
                    total_failed += 1
                    
            # 5. Log final da sincronização
            self.log_sync_end(
                log_id, 
                processed=total_processed, 
                inserted=total_inserted, 
                failed=total_failed,
                status='SUCCESS' if total_failed == 0 else 'PARTIAL'
            )
            
            self.logger.info(f"🎉 Sincronização concluída com validação!")
            self.logger.info(f"📊 Total: {total_processed} processados, {total_inserted} inseridos, {total_failed} falharam")
            
            return True
            
        except Exception as e:
            self.log_sync_end(log_id, status='ERROR', error_message=str(e))
            self.logger.error(f"❌ Erro durante sincronização: {str(e)}")
            return False

def main():
    """Função principal para executar o startup."""
    startup = StartupModule()
    
    try:
        success = startup.startup()
        
        if success:
            print("✅ Sistema inicializado com sucesso!")
            
            # Definir as configurações para sincronização com Google Sheets
            spreadsheet_id = os.getenv('SPREADSHEET_ID')
            
            # Obter IDs das abas via variável de ambiente
            sheet_ids_str = os.getenv('SHEET_IDS', '0,829477907,797561708,1064048522')
            sheet_ids = [int(id.strip()) for id in sheet_ids_str.split(',')]
            
            if spreadsheet_id:
                print("🔄 Iniciando sincronização com Google Sheets...")
                print(f"📋 IDs das abas: {sheet_ids}")
                sync_success = startup.populate_table_from_sheets(spreadsheet_id, sheet_ids)
                
                if sync_success:
                    print("✅ Sincronização com Google Sheets concluída com sucesso!")
                    print("📊 Dados das planilhas foram carregados na tabela leads_data")
                    
                    # Mostrar estatísticas simples
                    try:
                        with startup.connection.cursor() as cursor:
                            cursor.execute("SELECT COUNT(*) as total FROM leads_data;")
                            total_records = cursor.fetchone()['total']
                            
                            cursor.execute("SELECT banco, COUNT(*) as count FROM leads_data GROUP BY banco ORDER BY count DESC;")
                            bank_stats = cursor.fetchall()
                            
                            print(f"📈 Total de registros inseridos: {total_records}")
                            print("📋 Registros por aba:")
                            for stat in bank_stats:
                                print(f"   - {stat['banco']}: {stat['count']} registros")
                                
                    except Exception as stats_error:
                        print(f"⚠️ Erro ao obter estatísticas: {stats_error}")
                        
                else:
                    print("❌ Falha na sincronização com Google Sheets")
                    print("📋 Verifique os logs para mais detalhes")
            else:
                print("⚠️ SPREADSHEET_ID não configurado - pulando sincronização")
                print("💡 Configure a variável SPREADSHEET_ID no arquivo .env para habilitar a sincronização")
                
            print("💡 Sistema pronto para uso!")
        else:
            print("❌ Falha na inicialização do sistema")
            print("📋 Verifique os logs para mais detalhes")
            
    except KeyboardInterrupt:
        print("\n⏹️ Processo interrompido pelo usuário")
    except Exception as e:
        print(f"❌ Erro durante inicialização: {str(e)}")
    finally:
        startup.close()


# if __name__ == "__main__":
#     main()
