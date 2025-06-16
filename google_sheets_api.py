#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo para interação com a API Google Sheets.
Este módulo fornece uma interface para operações de leitura de dados
de planilhas do Google Sheets usando variáveis de ambiente.
"""

import json
import os
from typing import Dict, Any, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSheetsAPI:
    """
    Classe para interagir com a API Google Sheets (somente leitura).
    
    Esta classe fornece métodos para ler dados de planilhas do Google Sheets
    usando uma conta de serviço (service account) para autenticação via variáveis de ambiente.
    
    Attributes:
        service: Objeto de serviço para interagir com a API Google Sheets.
        credentials: Credenciais de autenticação da conta de serviço.
    """
    
    # Escopo necessário para leitura de planilhas
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    
    def __init__(self, credentials_source: Optional[str] = None):
        """
        Inicializa a instância da classe GoogleSheetsAPI.
        
        Args:
            credentials_source (Optional[str]): Pode ser:
                - None: Usa variável de ambiente GOOGLE_CREDENTIALS_JSON (recomendado)
                - String JSON: Credenciais diretas em formato JSON
                - Caminho de arquivo: Para compatibilidade (deprecated)
                
        Raises:
            ValueError: Se as credenciais não forem encontradas ou forem inválidas.
        """
        if credentials_source is None:
            # Modo padrão: usar variável de ambiente
            self._init_from_env_var()
        elif credentials_source.strip().startswith('{'):
            # String JSON direta
            self._init_from_json_string(credentials_source)
        elif os.path.isfile(credentials_source):
            # Arquivo JSON (deprecated mas mantido para compatibilidade)
            self._init_from_file(credentials_source)
        else:
            # Assumir que é uma variável de ambiente personalizada
            self._init_from_env_var(credentials_source)
    
    def _init_from_env_var(self, env_var_name: str = 'GOOGLE_CREDENTIALS_JSON'):
        """Inicializa usando variável de ambiente."""
        credentials_json = os.getenv(env_var_name)
        if not credentials_json:
            raise ValueError(f"Variável de ambiente '{env_var_name}' não encontrada. "
                           f"Configure com o JSON das credenciais do Google Service Account.")
        
        try:
            credentials_dict = json.loads(credentials_json)
            self.credentials = Credentials.from_service_account_info(
                credentials_dict, 
                scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.credentials)
        except json.JSONDecodeError:
            raise ValueError(f"JSON inválido na variável de ambiente '{env_var_name}'")
        except Exception as e:
            raise ValueError(f"Erro ao carregar credenciais da variável de ambiente: {str(e)}")
    
    def _init_from_json_string(self, json_string: str):
        """Inicializa usando string JSON direta."""
        try:
            credentials_dict = json.loads(json_string)
            self.credentials = Credentials.from_service_account_info(
                credentials_dict, 
                scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.credentials)
        except json.JSONDecodeError:
            raise ValueError("JSON de credenciais inválido")
        except Exception as e:
            raise ValueError(f"Erro ao carregar credenciais do JSON: {str(e)}")
    
    def _init_from_file(self, credentials_path: str):
        """Inicializa usando arquivo JSON (deprecated)."""
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(f"Arquivo de credenciais não encontrado: {credentials_path}")
        
        try:
            self.credentials = Credentials.from_service_account_file(
                credentials_path, 
                scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.credentials)
        except Exception as e:
            raise ValueError(f"Erro ao carregar credenciais do arquivo: {str(e)}")

    @classmethod
    def from_credentials_dict(cls, credentials_dict: Dict[str, Any]) -> 'GoogleSheetsAPI':
        """
        Cria uma instância da classe usando um dicionário de credenciais.
        
        Args:
            credentials_dict (Dict[str, Any]): Dicionário com as credenciais
                da conta de serviço.
                
        Returns:
            GoogleSheetsAPI: Nova instância da classe.
        """
        instance = cls.__new__(cls)
        instance.credentials = Credentials.from_service_account_info(
            credentials_dict, 
            scopes=cls.SCOPES
        )
        instance.service = build('sheets', 'v4', credentials=instance.credentials)
        return instance
    
    @classmethod
    def from_env_credentials(cls, env_var_name: str = 'GOOGLE_CREDENTIALS_JSON') -> 'GoogleSheetsAPI':
        """
        Cria uma instância da classe usando credenciais de uma variável de ambiente.
        
        Args:
            env_var_name (str): Nome da variável de ambiente que contém
                o JSON das credenciais.
                
        Returns:
            GoogleSheetsAPI: Nova instância da classe.
        """
        return cls(credentials_source=None)  # Usa o novo construtor padrão
    
    def get_spreadsheet_info(self, spreadsheet_id: str) -> Dict[str, Any]:
        """
        Obtém informações sobre uma planilha.
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets.
                
        Returns:
            Dict[str, Any]: Informações da planilha incluindo título, sheets, etc.
        """
        try:
            result = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            return result
        except HttpError as e:
            raise Exception(f"Erro ao acessar planilha: {str(e)}")
    
    def get_sheets_names_and_ids(self, spreadsheet_id: str) -> Dict[str, Any]:
        """
        Obtém os nomes e IDs de todas as abas (sheets) de uma planilha.
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets.
            
        Returns:
            Dict[str, Any]: Dicionário com 'name' e 'id' de cada aba.
                
        Example:
            >>> sheets_api = GoogleSheetsAPI("credentials.json")
            >>> sheets = sheets_api.get_sheets_names_and_ids("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
            >>> for sheet in sheets:
            ...     print(f"Aba: {sheet['name']} (ID: {sheet['id']})")
        """
        spreadsheet_info = self.get_spreadsheet_info(spreadsheet_id)
        sheets_info = [sheet['properties'] for sheet in spreadsheet_info['sheets']]
        return [
            {
                'name': sheet['title'],
                'id': sheet['sheetId'],
                'index': sheet['index']
            } 
            for sheet in sheets_info
        ]
    
    def get_sheet_data_as_json(self, 
                              spreadsheet_id: str, 
                              sheet_id: int,
                              header_row: int = 1) -> Dict[str, Any]:
        """
        Obtém todos os dados de uma aba específica em formato JSON.
        
        Args:
            spreadsheet_id (str): ID da planilha do Google Sheets.
            sheet_id (int): ID interno da aba (sheetId).
            header_row (int): Número da linha que contém os cabeçalhos (base 1).
                Padrão é 1 (primeira linha).
                
        Returns:
            Dict[str, Any]: Dados da aba em formato JSON com estrutura:
                {
                    "sheet_info": {
                        "spreadsheet_id": str,
                        "sheet_id": int,
                        "sheet_name": str,
                        "total_rows": int,
                        "total_columns": int
                    },
                    "headers": List[str],
                    "data": List[Dict[str, Any]]
                }
                
        Example:
            >>> sheets_api = GoogleSheetsAPI("credentials.json")
            >>> data = sheets_api.get_sheet_data_as_json("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", 0)
            >>> print(data["sheet_info"]["sheet_name"])
            >>> for row in data["data"]:
            ...     print(row)
        """
        try:
            # Obter informações da planilha para encontrar o nome da aba
            spreadsheet_info = self.get_spreadsheet_info(spreadsheet_id)
            
            # Encontrar a aba com o ID especificado
            target_sheet = None
            for sheet in spreadsheet_info['sheets']:
                if sheet['properties']['sheetId'] == sheet_id:
                    target_sheet = sheet['properties']
                    break
            
            if target_sheet is None:
                raise Exception(f"Aba com ID {sheet_id} não encontrada na planilha")
            
            sheet_name = target_sheet['title']
            
            # Obter dados da aba
            range_name = f"'{sheet_name}'!A:Z"  # Aspas simples para nomes com espaços
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption='FORMATTED_VALUE',
                dateTimeRenderOption='FORMATTED_STRING'
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return {
                    "sheet_info": {
                        "spreadsheet_id": spreadsheet_id,
                        "sheet_id": sheet_id,
                        "sheet_name": sheet_name,
                        "total_rows": 0,
                        "total_columns": 0
                    },
                    "headers": [],
                    "data": []
                }
            
            # Verificar se há dados suficientes para os cabeçalhos
            if len(values) < header_row:
                raise Exception(f"Aba não possui linha {header_row} para cabeçalhos")
            
            # Extrair cabeçalhos
            headers = values[header_row - 1]  # -1 porque header_row é base 1
            
            # Converter dados em lista de dicionários
            data_rows = []
            for row_data in values[header_row:]:  # Pular linha de cabeçalho
                # Garantir que a linha tenha o mesmo número de colunas que os cabeçalhos
                while len(row_data) < len(headers):
                    row_data.append('')
                
                # Criar dicionário para esta linha
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row_data):
                        row_dict[header] = row_data[i]
                    else:
                        row_dict[header] = ''
                
                data_rows.append(row_dict)
            
            # Informações da grade
            grid_props = target_sheet.get('gridProperties', {})
            
            return {
                "sheet_info": {
                    "spreadsheet_id": spreadsheet_id,
                    "sheet_id": sheet_id,
                    "sheet_name": sheet_name,
                    "total_rows": len(values),
                    "total_columns": len(headers),
                    "grid_rows": grid_props.get('rowCount', len(values)),
                    "grid_columns": grid_props.get('columnCount', len(headers))
                },
                "headers": headers,
                "data": data_rows
            }
            
        except HttpError as e:
            raise Exception(f"Erro ao ler dados da aba: {str(e)}")
        except Exception as e:
            raise Exception(f"Erro ao processar dados: {str(e)}")