#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo para interação com a API Bitrix24.
Este módulo fornece uma interface para operações de CRM na Bitrix24,
especificamente para gerenciamento de contatos e leads.
"""

import requests
import json
from typing import Dict, List, Any, Optional, Union


class BitrixAPI:
    """
    Classe para interagir com a API Bitrix24.
    
    Esta classe fornece métodos para criar, buscar, atualizar e gerenciar
    contatos e leads na plataforma Bitrix24 através de sua API REST.
    
    Attributes:
        webhook_url (str): URL do webhook para autenticação na API Bitrix24.
    """
    
    def __init__(self, webhook_url: str):
        """
        Inicializa a instância da classe BitrixAPI.
        
        Args:
            webhook_url (str): URL do webhook para autenticação na API Bitrix24.
                Formato: https://{domain}/rest/{user_id}/{webhook_key}/
        """
        self.webhook_url = webhook_url.rstrip("/")
        
    def _make_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        """
        Método interno para realizar requisições à API Bitrix24.
        
        Args:
            method (str): Método da API a ser chamado.
            params (Dict, optional): Parâmetros a serem enviados com a requisição.
        
        Returns:
            Dict: Resposta da API em formato de dicionário.
            
        Raises:
            Exception: Se a requisição falhar ou retornar um erro.
        """
        url = f"{self.webhook_url}/{method}"
        
        try:
            response = requests.post(url, json=params)
                
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"Erro na requisição à API Bitrix24: {str(e)}")
        
        except json.JSONDecodeError:
            raise Exception("Erro ao decodificar resposta da API como JSON")
    
    # ===== MÉTODOS PARA CONTATOS =====
    
    def add_contact(self, fields: Dict[str, Any]) -> int:
        """
        Adiciona um novo contato ao Bitrix24.
        
        Args:
            fields (Dict[str, Any]): Campos do contato a ser criado.
                Campos comuns incluem:
                - NAME: Nome do contato
                - LAST_NAME: Sobrenome do contato
                - EMAIL: Lista de emails [{VALUE: "email@exemplo.com", VALUE_TYPE: "WORK"}]
                - PHONE: Lista de telefones [{VALUE: "+123456789", VALUE_TYPE: "WORK"}]
                - COMPANY_ID: ID da empresa associada
                - ASSIGNED_BY_ID: ID do usuário responsável
        
        Returns:
            int: ID do contato criado.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> contact_fields = {
            ...     "NAME": "João",
            ...     "LAST_NAME": "Silva",
            ...     "EMAIL": [{"VALUE": "joao@exemplo.com", "VALUE_TYPE": "WORK"}],
            ...     "PHONE": [{"VALUE": "+5511987654321", "VALUE_TYPE": "WORK"}]
            ... }
            >>> contact_id = api.add_contact(contact_fields)
            >>> print(f"Contato criado com ID: {contact_id}")
        """
        params = {"fields": fields}
        result = self._make_request("crm.contact.add", params)
        
        if not result.get("result"):
            raise Exception(f"Erro ao adicionar contato: {result}")
            
        return result["result"]
    
    def list_contacts(self, 
                      filter_params: Optional[Dict] = None, 
                      select: Optional[List[str]] = None, 
                      order: Optional[Dict[str, str]] = None,
                      start: int = 0) -> Dict:
        """
        Lista contatos do Bitrix24 com opções de filtragem e paginação.
        
        Args:
            filter_params (Dict, optional): Filtros para a busca de contatos.
                Aceita prefixos especiais para operações:
                - '>=' — maior ou igual a
                - '>' — maior que
                - '<=' — menor ou igual a
                - '<' — menor que
                - '@' — IN, um array é passado como valor
                - '!@' — NOT IN, um array é passado como valor
                - '%' — LIKE, busca por substring
                - '=%' — LIKE, busca por substring com caractere %
                - '%=' — LIKE (similar a =%)
                - '=' — igual, correspondência exata (usado por padrão)
                - '!=' — diferente
                - '!' — diferente
                
                Exemplos:
                {">=DATE_CREATE": "2022-01-01"} - contatos criados a partir de 01/01/2022
                {"NAME": "João"} - contatos com nome exatamente "João"
                {"%NAME": "Jo"} - contatos com nome contendo "Jo"
                {"@COMPANY_ID": [1, 2, 3]} - contatos vinculados às empresas 1, 2 ou 3
                
            select (List[str], optional): Campos a serem retornados. 
                Se None, todos os campos serão retornados ('*' + 'UF_*').
                Valores especiais:
                - '*' — para selecionar todos os campos (excluindo campos personalizados e múltiplos)
                - 'UF_*' — para selecionar todos os campos personalizados (excluindo campos múltiplos)
                
            order (Dict[str, str], optional): Ordenação dos resultados.
                Formato: {"CAMPO": "ASC|DESC"}
                Exemplo: {"DATE_CREATE": "DESC", "NAME": "ASC"}
                Se None, a ordenação padrão será por data de criação decrescente.
                
            start (int, optional): Índice inicial para paginação. Padrão é 0.
                A API Bitrix24 sempre retorna 50 registros por página.
                Para selecionar a segunda página, use start=50,
                para a terceira página, use start=100, e assim por diante.
        
        Returns:
            Dict: Dicionário contendo os contatos encontrados na chave "result".
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> # Buscar contatos com email contendo "exemplo.com"
            >>> contacts = api.list_contacts(
            ...     filter_params={"%EMAIL": "exemplo.com"},
            ...     select=["ID", "NAME", "LAST_NAME", "EMAIL", "PHONE"]
            ... )
            >>> for contact in contacts["result"]:
            ...     print(f"{contact['NAME']} {contact['LAST_NAME']}")
        """
        params = {"start": start}
        
        if order:
            params["order"] = order
        else:
            params["order"] = {"DATE_CREATE": "DESC"}  # Ordenação padrão
            
        if filter_params:
            params["filter"] = filter_params
            
        if select:
            params["select"] = select
            
        return self._make_request("crm.contact.list", params)
    
    def get_contact_by_id(self, contact_id: int) -> Dict:
        """
        Obtém um contato específico pelo ID.
        
        Args:
            contact_id (int): ID do contato a ser obtido.
            
        Returns:
            Dict: Dados do contato.
            
        Raises:
            Exception: Se o contato não for encontrado.
        """
        params = {"id": contact_id}
        result = self._make_request("crm.contact.get", params)
        
        if not result.get("result"):
            raise Exception(f"Contato com ID {contact_id} não encontrado")
            
        return result["result"]
    
    def find_contact_by_email(self, email: str) -> List[Dict]:
        """
        Encontra contatos pelo endereço de email.
        
        Args:
            email (str): Endereço de email para busca.
                Para busca exata, passe o email completo.
                Para busca por substring, use find_contact_by_email_substring.
            
        Returns:
            List[Dict]: Lista de contatos que possuem o email especificado.
        """
        params = {
            "filter": {"EMAIL": email},
        }
        
        result = self._make_request("crm.contact.list", params)
        return result.get("result", [])
    
    def find_contact_by_email_substring(self, email_substring: str) -> List[Dict]:
        """
        Encontra contatos que contenham um determinado texto no email.
        
        Args:
            email_substring (str): Parte do email para busca.
            
        Returns:
            List[Dict]: Lista de contatos que possuem o substring no email.
            
        Note:
            Para campos múltiplos como EMAIL, a busca LIKE só funciona com
            correspondências exatas. Este método é uma implementação específica
            que pode ter limitações conforme a documentação da API.
        """
        params = {
            "filter": {"%EMAIL": email_substring},
        }
        
        result = self._make_request("crm.contact.list", params)
        return result.get("result", [])
    
    def find_contact_by_phone(self, phone: str) -> List[Dict]:
        """
        Encontra contatos pelo número de telefone.
        
        Args:
            phone (str): Número de telefone para busca.
                Note que a API Bitrix24 só suporta correspondência exata
                para campos múltiplos como PHONE.
            
        Returns:
            List[Dict]: Lista de contatos que possuem o telefone especificado.
        """
        params = {
            "filter": {"PHONE": phone},
        }
        
        result = self._make_request("crm.contact.list", params)
        return result.get("result", [])
    
    def get_contact_company_items(self, contact_id: int) -> List[Dict]:
        # Ainda não implementado
        """
        Obtém a lista de empresas associadas a um contato.
        
        Args:
            contact_id (int): ID do contato.
            
        Returns:
            List[Dict]: Lista de empresas associadas ao contato.
        """
        params = {"id": contact_id}
        result = self._make_request("crm.contact.company.items.get", params)
        
        if not result.get("result"):
            return []
            
        return result["result"]
    
    # ===== MÉTODOS PARA LEADS =====
    # Ainda não implementado
    
    def add_lead(self, fields: Dict[str, Any]) -> int:
        """
        Adiciona um novo lead ao Bitrix24.
        
        Args:
            fields (Dict[str, Any]): Campos do lead a ser criado.
                Campos comuns incluem:
                - TITLE: Título do lead
                - NAME: Nome
                - LAST_NAME: Sobrenome
                - EMAIL: Lista de emails [{VALUE: "email@exemplo.com", VALUE_TYPE: "WORK"}]
                - PHONE: Lista de telefones [{VALUE: "+123456789", VALUE_TYPE: "WORK"}]
                - ASSIGNED_BY_ID: ID do usuário responsável
                - STATUS_ID: Status do lead
        
        Returns:
            int: ID do lead criado.
        """
        params = {"fields": fields}
        result = self._make_request("crm.lead.add", params)
        
        if not result.get("result"):
            raise Exception(f"Erro ao adicionar lead: {result}")
            
        return result["result"]
    
    def list_leads(self, 
                   filter_params: Optional[Dict] = None, 
                   select: Optional[List[str]] = None, 
                   order: Optional[Dict[str, str]] = None,
                   start: int = 0) -> Dict:
        """
        Lista leads do Bitrix24 com opções de filtragem e paginação.
        
        Args:
            filter_params (Dict, optional): Filtros para a busca de leads.
                Ver documentação de list_contacts para exemplos de filtros.
                
            select (List[str], optional): Campos a serem retornados.
                
            order (Dict[str, str], optional): Ordenação dos resultados.
                Formato: {"CAMPO": "ASC|DESC"}
                
            start (int, optional): Índice inicial para paginação. Padrão é 0.
                A API Bitrix24 sempre retorna 50 registros por página.
        
        Returns:
            Dict: Dicionário contendo os leads encontrados na chave "result".
        """
        params = {"start": start}
        
        if order:
            params["order"] = order
        else:
            params["order"] = {"DATE_CREATE": "DESC"}
            
        if filter_params:
            params["filter"] = filter_params
            
        if select:
            params["select"] = select
            
        return self._make_request("crm.lead.list", params)
    
    def get_lead_by_id(self, lead_id: int) -> Dict:
        """
        Obtém um lead específico pelo ID.
        
        Args:
            lead_id (int): ID do lead a ser obtido.
            
        Returns:
            Dict: Dados do lead.
            
        Raises:
            Exception: Se o lead não for encontrado.
        """
        params = {"id": lead_id}
        result = self._make_request("crm.lead.get", params)
        
        if not result.get("result"):
            raise Exception(f"Lead com ID {lead_id} não encontrado")
            
        return result["result"]