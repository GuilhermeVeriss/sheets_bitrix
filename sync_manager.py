#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo de Sincronização Contínua para Google Sheets e Banco de Dados.

Este módulo utiliza os objetos já inicializados do startup para realizar
sincronização contínua entre Google Sheets e PostgreSQL, limpando e
reinserindo todos os dados a cada execução, mas retornando as diferenças detectadas.

Author: Sistema de Sincronização Aliest
Date: June 2025
"""

import os
import logging
import hashlib
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from psycopg2.extras import execute_values
from dataclasses import dataclass


@dataclass
class SyncResult:
    """
    Classe para representar o resultado de uma sincronização.
    
    Attributes:
        total_processed (int): Total de registros processados das planilhas
        total_inserted (int): Total de registros inseridos no banco
        failed_records (int): Registros que falharam no processamento
        sync_duration (float): Duração da sincronização em segundos
        error_message (str): Mensagem de erro, se houver
        sheets_data (Dict): Dados detalhados por aba processada
        changes_detected (Dict): Diferenças detectadas entre antes/depois
        new_records (List[Dict]): Registros que são novos
        removed_records (List[Dict]): Registros que foram removidos
        unchanged_records (List[Dict]): Registros que permaneceram iguais
    """
    total_processed: int = 0
    total_inserted: int = 0
    failed_records: int = 0
    sync_duration: float = 0.0
    error_message: str = None
    sheets_data: Dict = None
    changes_detected: Dict = None
    new_records: List[Dict] = None
    removed_records: List[Dict] = None
    unchanged_records: List[Dict] = None
    
    def __post_init__(self):
        if self.sheets_data is None:
            self.sheets_data = {}
        if self.changes_detected is None:
            self.changes_detected = {}
        if self.new_records is None:
            self.new_records = []
        if self.removed_records is None:
            self.removed_records = []
        if self.unchanged_records is None:
            self.unchanged_records = []


class SyncManager:
    """
    Gerenciador de Sincronização Contínua.
    
    Esta classe é responsável por:
    1. Capturar snapshot dos dados antes da limpeza
    2. Limpar completamente a tabela leads_data
    3. Recarregar todos os dados das planilhas especificadas
    4. Comparar antes/depois para detectar mudanças
    5. Retornar relatório detalhado das diferenças
    
    Utiliza os objetos já inicializados pelo StartupModule para realizar as operações.
    Estratégia: Limpeza total + reinserção + detecção de diferenças
    """
    
    def __init__(self, startup_instance):
        """
        Inicializa o gerenciador de sincronização.
        
        Args:
            startup_instance: Instância do StartupModule já inicializada
        """
        self.startup = startup_instance
        self.logger = logging.getLogger(__name__)
        
        # Validar se o startup foi inicializado corretamente
        if not self.startup.connection:
            raise ValueError("StartupModule não possui conexão com banco de dados")
        if not self.startup.google_sheets:
            raise ValueError("StartupModule não possui API do Google Sheets inicializada")
            
        self.logger.info("✅ SyncManager inicializado com sucesso")
    
    def _calculate_record_hash(self, record: Dict[str, Any]) -> str:
        """
        Calcula hash de um registro para detectar mudanças.
        
        Args:
            record (Dict): Registro de dados
            
        Returns:
            str: Hash MD5 do registro
        """
        # Campos relevantes para comparação (excluindo IDs e timestamps)
        relevant_fields = ['data', 'cnpj', 'telefone', 'nome', 'empresa', 
                          'consultor', 'forma_prospeccao', 'etapa', 'banco']
        
        # Criar string normalizada dos dados relevantes
        data_string = ""
        for field in relevant_fields:
            value = str(record.get(field, '')).strip().lower()
            # Normalizar data se existir
            if field == 'data' and value:
                try:
                    # Tentar converter para formato padrão
                    if '/' in value:
                        dt = datetime.strptime(value, '%Y-%m-%d')
                        value = dt.strftime('%d/%m/%Y')
                except:
                    pass
            data_string += f"{field}:{value}|"
        
        return hashlib.md5(data_string.encode('utf-8')).hexdigest()
    
    def _capture_current_snapshot(self) -> Dict[str, Dict]:
        """
        Captura snapshot dos dados atualmente no banco antes da limpeza.
        
        Returns:
            Dict: Dicionário com hash como chave e dados completos como valor
        """
        try:
            with self.startup.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, data, cnpj, telefone, nome, empresa, 
                           consultor, forma_prospeccao, etapa, banco, 
                           created_at, updated_at
                    FROM leads_data 
                    ORDER BY id;
                """)
                
                records = cursor.fetchall()
                snapshot = {}
                
                for record in records:
                    # Converter record para dict
                    record_dict = dict(record) if hasattr(record, 'keys') else record
                    
                    # Calcular hash para este registro
                    record_hash = self._calculate_record_hash(record_dict)
                    snapshot[record_hash] = record_dict
                
                self.logger.info(f"📸 Snapshot antes da limpeza: {len(snapshot)} registros")
                return snapshot
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao capturar snapshot: {str(e)}")
            return {}
    
    def _create_new_data_snapshot(self, all_insert_values: List[tuple], sheet_names: List[str]) -> Dict[str, Dict]:
        """
        Cria snapshot dos novos dados que serão inseridos.
        
        Args:
            all_insert_values: Lista de tuplas com dados para inserção
            sheet_names: Lista com nomes das abas correspondentes
            
        Returns:
            Dict: Dicionário com hash como chave e dados como valor
        """
        snapshot = {}
        duplicate_count = 0
        
        try:
            # Mapeamento dos campos conforme a ordem da inserção
            field_names = ['data', 'cnpj', 'telefone', 'nome', 'empresa', 
                          'consultor', 'forma_prospeccao', 'etapa', 'banco']
            
            for values in all_insert_values:
                # Criar dicionário do registro
                record_dict = {}
                for i, field in enumerate(field_names):
                    if i < len(values):
                        record_dict[field] = values[i]
                    else:
                        record_dict[field] = None
                
                # Calcular hash
                record_hash = self._calculate_record_hash(record_dict)
                
                # Verificar se já existe este hash (duplicata)
                if record_hash in snapshot:
                    duplicate_count += 1
                else:
                    snapshot[record_hash] = record_dict
            
            total_records = len(all_insert_values)
            unique_records = len(snapshot)
            
            self.logger.info(f"📸 Snapshot dos novos dados: {unique_records} registros únicos de {total_records} totais")
            if duplicate_count > 0:
                self.logger.warning(f"⚠️ {duplicate_count} registros duplicados detectados (mesmo conteúdo)")
                
            return snapshot
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao criar snapshot dos novos dados: {str(e)}")
            return {}
    
    def _compare_snapshots(self, old_snapshot: Dict, new_snapshot: Dict) -> Dict[str, List]:
        """
        Compara snapshots antes e depois para detectar mudanças.
        
        Args:
            old_snapshot: Dados antes da sincronização
            new_snapshot: Dados após a sincronização
            
        Returns:
            Dict: Dicionário com listas de novos, removidos e inalterados
        """
        # Detectar registros novos (existem no novo mas não no antigo)
        new_records = []
        for new_hash, new_data in new_snapshot.items():
            if new_hash not in old_snapshot:
                new_records.append(new_data)
        
        # Detectar registros removidos (existem no antigo mas não no novo)
        removed_records = []
        for old_hash, old_data in old_snapshot.items():
            if old_hash not in new_snapshot:
                removed_records.append(old_data)
        
        # Detectar registros inalterados (existem em ambos com mesmo hash)
        unchanged_records = []
        for old_hash, old_data in old_snapshot.items():
            if old_hash in new_snapshot:
                unchanged_records.append(old_data)
        
        self.logger.info(f"🔍 Mudanças detectadas: {len(new_records)} novos, {len(removed_records)} removidos, {len(unchanged_records)} inalterados")
        
        return {
            'new': new_records,
            'removed': removed_records,
            'unchanged': unchanged_records
        }

    def clear_and_resync_database(self, spreadsheet_id: str, sheet_ids: List[int]) -> SyncResult:
        """
        Método principal para sincronização por limpeza total e reinserção com detecção de mudanças.
        
        Este método:
        1. Captura snapshot dos dados atuais
        2. Remove todos os dados da tabela leads_data
        3. Carrega dados frescos de todas as abas especificadas
        4. Insere todos os dados no banco
        5. Compara antes/depois para detectar mudanças
        6. Retorna relatório detalhado das diferenças
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets
            sheet_ids (List[int]): Lista de IDs das abas para sincronizar
            
        Returns:
            SyncResult: Resultado detalhado da sincronização com mudanças detectadas
        """
        start_time = datetime.now()
        self.logger.info("🔄 Iniciando sincronização com detecção de mudanças...")
        
        # Registrar início da sincronização
        log_id = self.startup.log_sync_start(
            "clear_and_resync_with_changes", 
            f"sheets_{sheet_ids}",
            {"spreadsheet_id": spreadsheet_id, "sheet_ids": sheet_ids}
        )
        
        result = SyncResult()
        
        try:
            # 1. Capturar snapshot dos dados atuais ANTES da limpeza
            self.logger.info("📸 Capturando snapshot dos dados atuais...")
            old_snapshot = self._capture_current_snapshot()
            
            # 2. Limpar todos os dados da tabela
            self.logger.info("🗑️ Limpando tabela leads_data...")
            with self.startup.connection.cursor() as cursor:
                cursor.execute("DELETE FROM leads_data;")
                self.logger.info("✅ Tabela leads_data limpa com sucesso")
            
            # 3. Processar cada aba e coletar dados
            all_insert_values = []
            sheet_names = []
            
            for sheet_id in sheet_ids:
                try:
                    self.logger.info(f"📊 Processando aba ID: {sheet_id}")
                    
                    # Obter dados da aba
                    sheet_data = self.startup.google_sheets.get_sheet_data_as_json(
                        spreadsheet_id, sheet_id
                    )
                    
                    sheet_name = sheet_data['sheet_info']['sheet_name']
                    rows_data = sheet_data['data']
                    
                    self.logger.info(f"📋 Aba '{sheet_name}': {len(rows_data)} registros encontrados")
                    
                    # Processar cada linha da aba
                    processed_count = 0
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
                            
                            # Adicionar valores à lista para inserção
                            all_insert_values.append((
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
                            
                            sheet_names.append(sheet_name)
                            processed_count += 1
                            
                        except Exception as row_error:
                            failed_count += 1
                            self.logger.warning(f"⚠️ Erro ao processar registro da aba '{sheet_name}': {str(row_error)}")
                    
                    # Registrar estatísticas da aba
                    result.sheets_data[sheet_name] = {
                        'total_rows': len(rows_data),
                        'processed': processed_count,
                        'failed': failed_count
                    }
                    
                    result.total_processed += processed_count
                    result.failed_records += failed_count
                    
                    self.logger.info(f"✅ Aba '{sheet_name}': {processed_count} processados, {failed_count} falharam")
                    
                except Exception as sheet_error:
                    self.logger.error(f"❌ Erro ao processar aba ID {sheet_id}: {str(sheet_error)}")
                    result.failed_records += 1
            
            # 4. Criar snapshot dos novos dados
            self.logger.info("📸 Criando snapshot dos novos dados...")
            new_snapshot = self._create_new_data_snapshot(all_insert_values, sheet_names)
            
            # 5. Inserir todos os dados coletados no banco
            if all_insert_values:
                self.logger.info(f"💾 Inserindo {len(all_insert_values)} registros no banco...")
                
                with self.startup.connection.cursor() as cursor:
                    insert_sql = """
                    INSERT INTO leads_data 
                    (data, cnpj, telefone, nome, empresa, consultor, forma_prospeccao, etapa, banco)
                    VALUES %s
                    """
                    
                    # Executar inserção em massa
                    execute_values(cursor, insert_sql, all_insert_values)
                    result.total_inserted = len(all_insert_values)
                
                self.logger.info(f"✅ {result.total_inserted} registros inseridos com sucesso")
            else:
                self.logger.warning("⚠️ Nenhum registro válido encontrado para inserir")
            
            # 6. Comparar snapshots para detectar mudanças
            self.logger.info("🔍 Detectando mudanças...")
            changes = self._compare_snapshots(old_snapshot, new_snapshot)
            
            # Atribuir mudanças ao resultado
            result.new_records = changes['new']
            result.removed_records = changes['removed']
            result.unchanged_records = changes['unchanged']
            
            # Resumo das mudanças
            result.changes_detected = {
                'total_new': len(result.new_records),
                'total_removed': len(result.removed_records),
                'total_unchanged': len(result.unchanged_records),
                'summary': f"{len(result.new_records)} novos, {len(result.removed_records)} removidos, {len(result.unchanged_records)} inalterados"
            }
            
            # 7. Calcular estatísticas finais
            end_time = datetime.now()
            result.sync_duration = (end_time - start_time).total_seconds()
            
            # 8. Registrar fim da sincronização
            self.startup.log_sync_end(
                log_id,
                processed=result.total_processed,
                inserted=result.total_inserted,
                updated=0,
                failed=result.failed_records,
                status='SUCCESS' if not result.error_message else 'PARTIAL'
            )
            
            self.logger.info(f"🎉 Sincronização concluída em {result.sync_duration:.2f}s")
            self.logger.info(f"📊 Resumo: {result.total_processed} processados, {result.total_inserted} inseridos, {result.failed_records} falharam")
            self.logger.info(f"🔍 Mudanças: {result.changes_detected['summary']}")
            
            # Log detalhado dos novos registros inseridos
            if result.new_records:
                self.logger.info("📝 Detalhes dos novos registros inseridos:")
                for record in result.new_records:
                    self.logger.info(f"   - {json.dumps(record, ensure_ascii=False)}")
            
            return result
            
        except Exception as e:
            error_msg = f"Erro durante sincronização: {str(e)}"
            result.error_message = error_msg
            self.logger.error(f"❌ {error_msg}")
            
            # Calcular duração mesmo em caso de erro
            end_time = datetime.now()
            result.sync_duration = (end_time - start_time).total_seconds()
            
            self.startup.log_sync_end(log_id, status='ERROR', error_message=error_msg)
            return result

    def get_current_data_summary(self) -> Dict[str, Any]:
        """
        Obtém resumo dos dados atualmente no banco.
        
        Returns:
            Dict: Estatísticas dos dados atuais
        """
        try:
            with self.startup.connection.cursor() as cursor:
                # Total de registros
                cursor.execute("SELECT COUNT(*) as total FROM leads_data;")
                total_records = cursor.fetchone()['total']
                
                # Registros por banco (aba)
                cursor.execute("""
                    SELECT banco, COUNT(*) as count 
                    FROM leads_data 
                    WHERE banco IS NOT NULL
                    GROUP BY banco 
                    ORDER BY count DESC;
                """)
                by_banco = cursor.fetchall()
                
                # Registros por consultor
                cursor.execute("""
                    SELECT consultor, COUNT(*) as count 
                    FROM leads_data 
                    WHERE consultor IS NOT NULL AND consultor != ''
                    GROUP BY consultor 
                    ORDER BY count DESC 
                    LIMIT 10;
                """)
                by_consultor = cursor.fetchall()
                
                # Últimas atualizações
                cursor.execute("""
                    SELECT MAX(created_at) as last_insert,
                           MAX(updated_at) as last_update
                    FROM leads_data;
                """)
                timestamps = cursor.fetchone()
                
                return {
                    'total_records': total_records,
                    'records_by_banco': [dict(r) for r in by_banco],
                    'records_by_consultor': [dict(r) for r in by_consultor],
                    'last_insert': timestamps['last_insert'],
                    'last_update': timestamps['last_update']
                }
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter resumo dos dados: {str(e)}")
            return {}
    
    def get_sync_statistics(self, hours_back: int = 24) -> Dict[str, Any]:
        """
        Obtém estatísticas das sincronizações realizadas.
        
        Args:
            hours_back (int): Número de horas para trás para analisar
            
        Returns:
            Dict: Estatísticas detalhadas das sincronizações
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            with self.startup.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_syncs,
                        SUM(records_processed) as total_processed,
                        SUM(records_inserted) as total_inserted,
                        SUM(records_failed) as total_failed,
                        AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration,
                        COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful_syncs,
                        COUNT(CASE WHEN status = 'ERROR' THEN 1 END) as failed_syncs,
                        MAX(finished_at) as last_sync
                    FROM sync_log 
                    WHERE started_at >= %s 
                    AND sync_type IN ('clear_and_resync', 'sheets_to_db');
                """, (cutoff_time,))
                
                stats = cursor.fetchone()
                
                return {
                    'period_hours': hours_back,
                    'total_synchronizations': stats['total_syncs'] or 0,
                    'total_records_processed': stats['total_processed'] or 0,
                    'total_records_inserted': stats['total_inserted'] or 0,
                    'total_records_failed': stats['total_failed'] or 0,
                    'average_duration_seconds': float(stats['avg_duration'] or 0),
                    'successful_synchronizations': stats['successful_syncs'] or 0,
                    'failed_synchronizations': stats['failed_syncs'] or 0,
                    'last_sync_time': stats['last_sync'],
                    'success_rate_percent': (
                        (stats['successful_syncs'] / stats['total_syncs'] * 100) 
                        if stats['total_syncs'] and stats['total_syncs'] > 0 else 0
                    )
                }
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter estatísticas: {str(e)}")
            return {}

    # Manter método antigo para compatibilidade, mas direcionando para o novo
    def sync_sheets_to_database(self, spreadsheet_id: str, sheet_ids: List[int]) -> SyncResult:
        """
        Método de compatibilidade que direciona para clear_and_resync_database.
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets
            sheet_ids (List[int]): Lista de IDs das abas para sincronizar
            
        Returns:
            SyncResult: Resultado detalhado da sincronização com mudanças detectadas
        """
        self.logger.info("📌 Redirecionando para sincronização com detecção de mudanças...")
        return self.clear_and_resync_database(spreadsheet_id, sheet_ids)


def main():
    """
    Função principal para demonstrar o uso do SyncManager com detecção de mudanças.
    """
    from startup import StartupModule
    
    print("🚀 Inicializando sistema de sincronização com detecção de mudanças...")
    
    # 1. Inicializar startup
    startup = StartupModule()
    if not startup.startup():
        print("❌ Falha na inicialização do sistema")
        return
    
    # 2. Inicializar gerenciador de sincronização
    try:
        sync_manager = SyncManager(startup)
        
        # 3. Configurar parâmetros de sincronização
        spreadsheet_id = os.getenv('SPREADSHEET_ID')
        sheet_ids = [0, 829477907, 797561708, 1064048522]  # IDs das abas
        
        if not spreadsheet_id:
            print("❌ SPREADSHEET_ID não configurado no arquivo .env")
            return
        
        # 4. Executar sincronização com detecção de mudanças
        print("🔄 Executando sincronização com detecção de mudanças...")
        result = sync_manager.clear_and_resync_database(spreadsheet_id, sheet_ids)
        
        # 5. Exibir resultados
        print(f"\n📊 Resultado da Sincronização:")
        print(f"   ⏱️ Duração: {result.sync_duration:.2f} segundos")
        print(f"   📋 Total processado: {result.total_processed}")
        print(f"   💾 Total inserido: {result.total_inserted}")
        print(f"   ❌ Falhas: {result.failed_records}")
        
        # 6. Exibir mudanças detectadas
        print(f"\n🔍 Mudanças Detectadas:")
        print(f"   ➕ Novos registros: {len(result.new_records)}")
        print(f"   🗑️ Registros removidos: {len(result.removed_records)}")
        print(f"   ✔️ Registros inalterados: {len(result.unchanged_records)}")
        
        # 7. Mostrar exemplos dos novos registros (primeiros 3)
        if result.new_records:
            print(f"\n📝 Exemplos de novos registros:")
            for i, record in enumerate(result.new_records[:3]):
                print(f"   {i+1}. {record.get('nome', 'N/A')} - {record.get('empresa', 'N/A')} ({record.get('banco', 'N/A')})")
            if len(result.new_records) > 3:
                print(f"   ... e mais {len(result.new_records) - 3} novos registros")
        
        # 8. Mostrar exemplos dos registros removidos (primeiros 3)
        if result.removed_records:
            print(f"\n🗑️ Exemplos de registros removidos:")
            for i, record in enumerate(result.removed_records[:3]):
                print(f"   {i+1}. {record.get('nome', 'N/A')} - {record.get('empresa', 'N/A')} ({record.get('banco', 'N/A')})")
            if len(result.removed_records) > 3:
                print(f"   ... e mais {len(result.removed_records) - 3} registros removidos")
        
        # Detalhes por aba
        if result.sheets_data:
            print(f"\n📋 Detalhes por aba:")
            for sheet_name, data in result.sheets_data.items():
                print(f"   📊 {sheet_name}: {data['processed']} processados, {data['failed']} falharam")
        
        if result.error_message:
            print(f"   ❌ Erro: {result.error_message}")
        else:
            print("   ✅ Sincronização concluída com sucesso!")
        
        print(f"\n💡 Você pode acessar as mudanças através de:")
        print(f"   - result.new_records (lista dos novos registros)")
        print(f"   - result.removed_records (lista dos registros removidos)")
        print(f"   - result.unchanged_records (lista dos registros inalterados)")
        
    except Exception as e:
        print(f"❌ Erro no gerenciador de sincronização: {str(e)}")
    
    finally:
        startup.close()


if __name__ == "__main__":
    main()