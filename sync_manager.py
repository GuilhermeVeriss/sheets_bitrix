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
        bitrix_processing (Dict): Resultado do processamento no Bitrix
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
    bitrix_processing: Dict = None
    
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
        if self.bitrix_processing is None:
            self.bitrix_processing = {}


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

    def _process_bitrix_updates(self, new_records: List[Dict], updated_records: List[Dict] = None) -> Dict[str, Any]:
        """
        Processa novos registros e atualizações no Bitrix através da função create_or_update_deal.
        
        Args:
            new_records: Lista de novos registros detectados
            updated_records: Lista de registros atualizados (opcional)
            
        Returns:
            Dict: Resultado do processamento com estatísticas e logs
        """
        from bitrix_api import BitrixAPI
        import os
        
        self.logger.info("🎯 Iniciando processamento de registros no Bitrix...")
        
        # Verificar se BitrixAPI está disponível e configurada
        webhook_url = os.getenv('BITRIX_URL')
        if not webhook_url:
            self.logger.warning("⚠️ BITRIX_URL não configurada. Pulando integração com Bitrix.")
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'skipped': 0,
                'error': 'BITRIX_URL não configurada'
            }
        
        try:
            bitrix_api = BitrixAPI(webhook_url)
            
            # Combinar novos registros e atualizações
            all_records_to_process = []
            if new_records:
                all_records_to_process.extend(new_records)
            if updated_records:
                all_records_to_process.extend(updated_records)
            
            if not all_records_to_process:
                self.logger.info("📝 Nenhum registro novo ou atualizado para processar no Bitrix")
                return {
                    'processed': 0,
                    'successful': 0,
                    'failed': 0,
                    'skipped': 0,
                    'message': 'Nenhum registro para processar'
                }
            
            # Processar cada registro
            processed = 0
            successful = 0
            failed = 0
            skipped = 0
            failed_records = []
            successful_records = []
            
            self.logger.info(f"📊 Processando {len(all_records_to_process)} registros no Bitrix...")
            
            for i, record in enumerate(all_records_to_process[:50], 1):
                try:
                    # Validar se o registro tem dados mínimos necessários
                    cnpj = record.get('cnpj', '').strip() if record.get('cnpj') else ''
                    telefone = record.get('telefone', '').strip() if record.get('telefone') else ''
                    
                    if not cnpj and not telefone:
                        self.logger.warning(f"⚠️ Registro {i} pulado: sem CNPJ nem telefone")
                        skipped += 1
                        continue
                    
                    # Log do registro sendo processado
                    empresa = record.get('empresa', '').strip() if record.get('empresa') else ''
                    log_info = f"CNPJ: {cnpj or 'N/A'}, Telefone: {telefone or 'N/A'}, Empresa: {empresa or 'N/A'}"
                    self.logger.info(f"🔄 Processando registro {i}/{len(all_records_to_process)}: {log_info}")
                    
                    # Chamar create_or_update_deal do Bitrix
                    result = bitrix_api.create_or_update_deal(record)
                    
                    # Log do resultado
                    action = result.get('action', 'unknown')
                    deal_id = result.get('deal_id', 'N/A')
                    message = result.get('message', 'Sem mensagem')
                    
                    if action in ['created', 'updated']:
                        self.logger.info(f"✅ Deal {action}: ID {deal_id} - {message}")
                        successful += 1
                        successful_records.append({
                            'record': record,
                            'result': result,
                            'action': action
                        })
                    else:
                        self.logger.warning(f"⚠️ Resultado inesperado: {message}")
                        failed += 1
                        failed_records.append({
                            'record': record,
                            'error': f"Resultado inesperado: {message}"
                        })
                    
                    processed += 1
                    
                except Exception as e:
                    error_msg = str(e)
                    self.logger.error(f"❌ Erro ao processar registro {i}: {error_msg}")
                    self.logger.error(f"   Dados do registro: {json.dumps(record, ensure_ascii=False)}")
                    
                    failed += 1
                    failed_records.append({
                        'record': record,
                        'error': error_msg
                    })
                    processed += 1
            
            # Log do resumo final
            self.logger.info(f"🏁 Processamento Bitrix concluído:")
            self.logger.info(f"   📊 Total processado: {processed}")
            self.logger.info(f"   ✅ Sucessos: {successful}")
            self.logger.info(f"   ❌ Falhas: {failed}")
            self.logger.info(f"   ⏭️ Pulados: {skipped}")
            
            # Log detalhado dos sucessos
            if successful_records:
                self.logger.info("🎉 Deals processados com sucesso:")
                for success in successful_records[:5]:  # Mostrar até 5 sucessos
                    deal_id = success['result'].get('deal_id', 'N/A')
                    action = success['action']
                    empresa = success['record'].get('empresa', 'N/A')
                    self.logger.info(f"   - Deal {action}: ID {deal_id} - {empresa}")
                if len(successful_records) > 5:
                    self.logger.info(f"   ... e mais {len(successful_records) - 5} deals processados")
            
            # Log detalhado das falhas
            if failed_records:
                self.logger.warning("💥 Erros encontrados:")
                for failure in failed_records[:3]:  # Mostrar até 3 erros
                    empresa = failure['record'].get('empresa', 'N/A')
                    error = failure['error']
                    self.logger.warning(f"   - {empresa}: {error}")
                if len(failed_records) > 3:
                    self.logger.warning(f"   ... e mais {len(failed_records) - 3} erros")
            
            return {
                'processed': processed,
                'successful': successful,
                'failed': failed,
                'skipped': skipped,
                'successful_records': successful_records,
                'failed_records': failed_records,
                'message': f"{successful} sucessos, {failed} falhas, {skipped} pulados de {len(all_records_to_process)} registros"
            }
            
        except Exception as e:
            error_msg = f"Erro na integração com Bitrix: {str(e)}"
            self.logger.error(f"❌ {error_msg}")
            return {
                'processed': 0,
                'successful': 0,
                'failed': len(all_records_to_process) if all_records_to_process else 0,
                'skipped': 0,
                'error': error_msg
            }
    
    def _validate_all_sheets_data_before_sync(self, spreadsheet_id: str, sheet_ids: List[int]) -> Dict[str, Any]:
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
            self.logger.info(f"🔍 VALIDAÇÃO CRÍTICA: Verificando dados de {len(sheet_ids)} abas ANTES de qualquer alteração no banco...")
            
            # Tentar buscar dados de TODAS as abas primeiro
            for sheet_id in sheet_ids:
                try:
                    self.logger.info(f"📊 Validando aba ID: {sheet_id}")
                    
                    # Tentar obter dados da aba - SE FALHAR AQUI, PARAR TUDO
                    sheet_data = self.startup.google_sheets.get_sheet_data_as_json(
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
            self.logger.error("🚫 SINCRONIZAÇÃO CANCELADA - dados das planilhas não puderam ser obtidos")
            raise e

    def clear_and_resync_database(self, spreadsheet_id: str, sheet_ids: List[int]) -> SyncResult:
        """
        Método principal para sincronização por limpeza total e reinserção com detecção de mudanças.
        
        IMPORTANTE: Valida TODAS as abas ANTES de fazer qualquer alteração no banco.
        Se qualquer aba falhar na busca, a sincronização é cancelada.
        
        Este método:
        1. PRIMEIRO: Valida todas as abas das planilhas
        2. Captura snapshot dos dados atuais
        3. Remove todos os dados da tabela leads_data
        4. Carrega dados frescos de todas as abas especificadas (dados já validados)
        5. Insere todos os dados no banco
        6. Compara antes/depois para detectar mudanças
        7. Retorna relatório detalhado das diferenças
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets
            sheet_ids (List[int]): Lista de IDs das abas para sincronizar
            
        Returns:
            SyncResult: Resultado detalhado da sincronização com mudanças detectadas
        """
        start_time = datetime.now()
        self.logger.info("🔄 Iniciando sincronização com validação e detecção de mudanças...")
        
        # Registrar início da sincronização
        log_id = self.startup.log_sync_start(
            "clear_and_resync_validated", 
            f"sheets_{sheet_ids}",
            {"spreadsheet_id": spreadsheet_id, "sheet_ids": sheet_ids}
        )
        
        result = SyncResult()
        
        try:
            # 1. PRIMEIRO: VALIDAR TODAS as abas ANTES de fazer qualquer alteração no banco
            self.logger.info("🔒 VALIDAÇÃO CRÍTICA: Verificando dados de todas as abas antes de qualquer alteração no banco...")
            
            try:
                validation_result = self._validate_all_sheets_data_before_sync(spreadsheet_id, sheet_ids)
            except Exception as validation_error:
                self.logger.error(f"❌ VALIDAÇÃO FALHOU: {str(validation_error)}")
                self.logger.error("🚫 Sincronização CANCELADA por falha na validação das planilhas")
                
                result.error_message = f"Validação falhou: {str(validation_error)}"
                result.sync_duration = (datetime.now() - start_time).total_seconds()
                
                self.startup.log_sync_end(log_id, status='ERROR', error_message=result.error_message)
                return result
            
            if not validation_result['success']:
                self.logger.error("❌ VALIDAÇÃO FALHOU: Nem todas as abas puderam ser carregadas")
                self.logger.error("🚫 Sincronização CANCELADA")
                
                result.error_message = validation_result['error_message']
                result.sync_duration = (datetime.now() - start_time).total_seconds()
                
                self.startup.log_sync_end(log_id, status='ERROR', error_message=result.error_message)
                return result
            
            self.logger.info("✅ VALIDAÇÃO APROVADA: Todas as abas carregadas com sucesso")
            self.logger.info(f"📊 Total de {validation_result['total_records']} registros validados")
            
            # 2. Capturar snapshot dos dados atuais ANTES da limpeza
            self.logger.info("📸 Capturando snapshot dos dados atuais...")
            old_snapshot = self._capture_current_snapshot()
            
            # 3. AGORA é seguro limpar o banco (dados já validados)
            self.logger.info("🗑️ Limpando tabela leads_data (dados validados, operação segura)...")
            with self.startup.connection.cursor() as cursor:
                cursor.execute("DELETE FROM leads_data;")
                self.logger.info("✅ Tabela leads_data limpa com sucesso")
            
            # 4. Processar cada aba usando os dados já validados
            all_insert_values = []
            sheet_names = []
            
            for sheet_id in sheet_ids:
                try:
                    # Usar dados já validados ao invés de buscar novamente
                    validated_sheet = validation_result['sheets_data'][sheet_id]
                    sheet_name = validated_sheet['sheet_name']
                    rows_data = validated_sheet['data']
                    
                    self.logger.info(f"📊 Processando aba '{sheet_name}': {len(rows_data)} registros")
                    
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
                    # Como os dados já foram validados, isso só aconteceria em caso de erro de processamento interno
                    self.logger.error(f"❌ Erro interno ao processar aba ID {sheet_id}: {str(sheet_error)}")
                    result.failed_records += 1
            
            # 5. Criar snapshot dos novos dados
            self.logger.info("📸 Criando snapshot dos novos dados...")
            new_snapshot = self._create_new_data_snapshot(all_insert_values, sheet_names)
            
            # 6. Inserir todos os dados coletados no banco
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
            
            # 7. Comparar snapshots para detectar mudanças
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
            
            # 8. Calcular estatísticas finais
            end_time = datetime.now()
            result.sync_duration = (end_time - start_time).total_seconds()
            
            # 9. Registrar fim da sincronização
            self.startup.log_sync_end(
                log_id,
                processed=result.total_processed,
                inserted=result.total_inserted,
                updated=0,
                failed=result.failed_records,
                status='SUCCESS' if not result.error_message else 'PARTIAL'
            )
            
            self.logger.info(f"🎉 Sincronização concluída com validação em {result.sync_duration:.2f}s")
            self.logger.info(f"📊 Resumo: {result.total_processed} processados, {result.total_inserted} inseridos, {result.failed_records} falharam")
            self.logger.info(f"🔍 Mudanças: {result.changes_detected['summary']}")
            
            # 10. Processar atualizações no Bitrix
            if result.new_records:
                self.logger.info("🎯 Processando novos registros no Bitrix...")
                
                bitrix_result = self._process_bitrix_updates(result.new_records)
                
                # Adicionar resultado do Bitrix ao resultado da sincronização
                result.bitrix_processing = bitrix_result
                
                # Log resumido do processamento no Bitrix
                if bitrix_result.get('error'):
                    self.logger.warning(f"⚠️ Erro no processamento Bitrix: {bitrix_result['error']}")
                else:
                    self.logger.info(f"🎉 Processamento Bitrix concluído: {bitrix_result.get('message', 'Sem detalhes')}")
            else:
                self.logger.info("📝 Nenhum registro novo para processar no Bitrix")
                result.bitrix_processing = {
                    'processed': 0,
                    'successful': 0,
                    'failed': 0,
                    'skipped': 0,
                    'message': 'Nenhum registro novo para processar'
                }
            
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
        
        # 9. Exibir resultado do processamento no Bitrix
        if hasattr(result, 'bitrix_processing') and result.bitrix_processing:
            print(f"\n🎯 Processamento no Bitrix:")
            bitrix = result.bitrix_processing
            if bitrix.get('error'):
                print(f"   ❌ Erro: {bitrix['error']}")
            else:
                print(f"   📊 Total processado: {bitrix.get('processed', 0)}")
                print(f"   ✅ Sucessos: {bitrix.get('successful', 0)}")
                print(f"   ❌ Falhas: {bitrix.get('failed', 0)}")
                print(f"   ⏭️ Pulados: {bitrix.get('skipped', 0)}")
                print(f"   💬 Resumo: {bitrix.get('message', 'Sem detalhes')}")
                
                # Mostrar alguns deals criados/atualizados
                if bitrix.get('successful_records'):
                    print(f"\n🎉 Exemplos de deals processados no Bitrix:")
                    for i, success in enumerate(bitrix['successful_records'][:3]):
                        deal_id = success['result'].get('deal_id', 'N/A')
                        action = success['action']
                        empresa = success['record'].get('empresa', 'N/A')
                        print(f"   {i+1}. Deal {action}: ID {deal_id} - {empresa}")
                    if len(bitrix['successful_records']) > 3:
                        print(f"   ... e mais {len(bitrix['successful_records']) - 3} deals processados")
        
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


# if __name__ == "__main__":
#     main()