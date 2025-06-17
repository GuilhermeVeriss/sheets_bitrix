#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Módulo para interação com a API Bitrix24.
Este módulo fornece uma interface para operações de CRM na Bitrix24,
especificamente para gerenciamento de contatos e deals (negócios).
"""

import requests
import json
from typing import Dict, List, Any, Optional, Union


class BitrixAPI:
    """
    Classe para interagir com a API Bitrix24.
    
    Esta classe fornece métodos para criar, buscar, atualizar e gerenciar
    contatos e deals (negócios) na plataforma Bitrix24 através de sua API REST.
    
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
        
    def _safe_strip(self, value: Any) -> str:
        """
        Método auxiliar para aplicar strip() de forma segura, tratando valores None.
        
        Args:
            value (Any): Valor a ser processado (pode ser None, string ou qualquer tipo).
            
        Returns:
            str: String processada com strip() ou string vazia se None.
        """
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
    
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

    def update_contact(self, contact_id: int, fields: Dict[str, Any]) -> bool:
        """
        Atualiza um contato existente no Bitrix24.
        
        Args:
            contact_id (int): ID do contato a ser atualizado.
            fields (Dict[str, Any]): Campos a serem atualizados.
                Os campos seguem a mesma estrutura do método add_contact:
                - NAME: Nome do contato
                - LAST_NAME: Sobrenome do contato
                - EMAIL: Lista de emails [{VALUE: "email@exemplo.com", VALUE_TYPE: "WORK"}]
                - PHONE: Lista de telefones [{VALUE: "+123456789", VALUE_TYPE: "WORK"}]
                - COMPANY_ID: ID da empresa associada
                - ASSIGNED_BY_ID: ID do usuário responsável
                - COMMENTS: Comentários sobre o contato
                - POST: Cargo do contato
                - ADDRESS: Endereço do contato
                - WEB: Lista de sites [{VALUE: "www.exemplo.com", VALUE_TYPE: "WORK"}]
        
        Returns:
            bool: True se a atualização foi bem-sucedida.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> # Atualizar nome e telefone de um contato
            >>> success = api.update_contact(123, {
            ...     "NAME": "João Carlos",
            ...     "PHONE": [{"VALUE": "+5511999887766", "VALUE_TYPE": "MOBILE"}]
            ... })
            >>> print(f"Contato atualizado: {success}")
        """
        params = {"id": contact_id, "fields": fields}
        result = self._make_request("crm.contact.update", params)
        
        if not result.get("result"):
            raise Exception(f"Erro ao atualizar contato {contact_id}: {result}")
            
        return result["result"]

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
    
    # ===== MÉTODOS PARA USUÁRIOS =====
    
    def list_users(self, 
                   filter_params: Optional[Dict] = None, 
                   select: Optional[List[str]] = None, 
                   order: Optional[Dict[str, str]] = None,
                   start: int = 0) -> Dict:
        """
        Lista usuários do Bitrix24 com opções de filtragem e paginação.
        
        Args:
            filter_params (Dict, optional): Filtros para a busca de usuários.
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
                {"NAME": "João"} - usuários com nome exatamente "João"
                {"%NAME": "João"} - usuários com nome contendo "João"
                {"%LAST_NAME": "Silva"} - usuários com sobrenome contendo "Silva"
                {"ACTIVE": "Y"} - usuários ativos
                {"@ID": [1, 2, 3]} - usuários com IDs específicos
                
            select (List[str], optional): Campos a serem retornados.
                Se None, todos os campos básicos serão retornados.
                Campos comuns incluem:
                - ID: ID do usuário
                - NAME: Nome do usuário
                - LAST_NAME: Sobrenome do usuário
                - EMAIL: Email do usuário
                - WORK_POSITION: Cargo do usuário
                - ACTIVE: Status do usuário (Y/N)
                - DATE_REGISTER: Data de registro
                - LAST_LOGIN: Último login
                - PERSONAL_PHONE: Telefone pessoal
                - WORK_PHONE: Telefone comercial
                - UF_DEPARTMENT: Departamento
                
            order (Dict[str, str], optional): Ordenação dos resultados.
                Formato: {"CAMPO": "ASC|DESC"}
                Exemplo: {"NAME": "ASC", "LAST_NAME": "ASC"}
                Se None, a ordenação padrão será por nome.
                
            start (int, optional): Índice inicial para paginação. Padrão é 0.
                A API Bitrix24 sempre retorna 50 registros por página.
                Para selecionar a segunda página, use start=50,
                para a terceira página, use start=100, e assim por diante.
        
        Returns:
            Dict: Dicionário contendo os usuários encontrados na chave "result".
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> # Buscar usuários com nome contendo "João"
            >>> users = api.list_users(
            ...     filter_params={"%NAME": "João"},
            ...     select=["ID", "NAME", "LAST_NAME", "EMAIL", "WORK_POSITION"]
            ... )
            >>> for user in users["result"]:
            ...     print(f"{user['NAME']} {user['LAST_NAME']} - {user.get('WORK_POSITION', '')}")
        """
        params = {"start": start}
        
        if order:
            params["order"] = order
        else:
            params["order"] = {"NAME": "ASC", "LAST_NAME": "ASC"}  # Ordenação padrão
            
        if filter_params:
            params["filter"] = filter_params
            
        if select:
            params["select"] = select
        else:
            # Campos padrão se não especificado
            params["select"] = ["ID", "NAME", "LAST_NAME", "EMAIL", "WORK_POSITION", "ACTIVE"]
            
        return self._make_request("user.get", params)

    # ===== MÉTODOS PARA STATUS =====
    
    def find_status_by_name(self, status_name: str, entity_id: str = 'DEAL_STAGE') -> Optional[Dict]:
        """
        Busca um status específico pelo nome dentro de uma entidade.
        
        Args:
            status_name (str): Nome do status a ser buscado.
            entity_id (str): ID da entidade (padrão: 'DEAL_STAGE').
                Valores comuns:
                - 'DEAL_STAGE' - Etapas de deals
                - 'DEAL_STAGE_4' - Etapas específicas do funil 4
                - 'CONTACT_TYPE' - Tipos de contato
                - 'COMPANY_TYPE' - Tipos de empresa
                - 'SOURCE' - Fontes
                - 'STATUS' - Status gerais
        
        Returns:
            Optional[Dict]: Dicionário com os dados do status encontrado ou None se não encontrado.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> status = api.find_status_by_name("Novo", "DEAL_STAGE")
            >>> if status:
            ...     print(f"Status encontrado: {status['NAME']} (ID: {status['STATUS_ID']})")
            ... else:
            ...     print("Status não encontrado")
        """
        try:
            # Busca todos os status da entidade especificada
            result = self._make_request('crm.status.list', {
                'filter': {
                    'ENTITY_ID': entity_id
                }
            })
            
            if not result.get("result"):
                return None
            
            # Procura pelo status com o nome especificado
            for status in result["result"]:
                if status.get("NAME", "").lower() == status_name.lower():
                    return status
            
            # Se não encontrou correspondência exata, procura por substring
            for status in result["result"]:
                if status_name.lower() in status.get("NAME", "").lower():
                    return status
            
            return None
            
        except Exception as e:
            raise Exception(f"Erro ao buscar status '{status_name}': {str(e)}")
    
    def find_user_by_name(self, user_name: str) -> Optional[Dict]:
        """
        Busca um usuário específico pelo nome (busca em NAME e LAST_NAME).
        
        Args:
            user_name (str): Nome do usuário a ser buscado.
                Pode ser o nome completo, nome ou sobrenome.
        
        Returns:
            Optional[Dict]: Dicionário com os dados do usuário encontrado ou None se não encontrado.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> user = api.find_user_by_name("João Silva")
            >>> if user:
            ...     print(f"Usuário encontrado: {user['NAME']} {user['LAST_NAME']} (ID: {user['ID']})")
            ... else:
            ...     print("Usuário não encontrado")
        """
        try:
            # Primeiro, tenta buscar por correspondência exata no nome completo
            parts = user_name.strip().split()
            
            if len(parts) >= 2:
                # Se há mais de uma palavra, tenta buscar por nome e sobrenome
                first_name = parts[0]
                last_name = " ".join(parts[1:])
                
                # Busca por nome e sobrenome específicos
                result = self._make_request('user.get', {
                    'filter': {
                        'NAME': first_name,
                        'LAST_NAME': last_name
                    },
                    'select': ['ID', 'NAME', 'LAST_NAME', 'EMAIL', 'WORK_POSITION', 'ACTIVE']
                })
                
                if result.get("result") and len(result["result"]) > 0:
                    return result["result"][0]
            
            # Se não encontrou, busca por substring no nome
            result = self._make_request('user.get', {
                'filter': {
                    '%NAME': user_name
                },
                'select': ['ID', 'NAME', 'LAST_NAME', 'EMAIL', 'WORK_POSITION', 'ACTIVE']
            })
            
            if result.get("result") and len(result["result"]) > 0:
                # Se encontrou múltiplos, retorna o primeiro ativo
                for user in result["result"]:
                    if user.get("ACTIVE") == "Y":
                        return user
                # Se nenhum ativo, retorna o primeiro
                return result["result"][0]
            
            # Se não encontrou por nome, busca por sobrenome
            result = self._make_request('user.get', {
                'filter': {
                    '%LAST_NAME': user_name
                },
                'select': ['ID', 'NAME', 'LAST_NAME', 'EMAIL', 'WORK_POSITION', 'ACTIVE']
            })
            
            if result.get("result") and len(result["result"]) > 0:
                # Se encontrou múltiplos, retorna o primeiro ativo
                for user in result["result"]:
                    if user.get("ACTIVE") == "Y":
                        return user
                # Se nenhum ativo, retorna o primeiro
                return result["result"][0]
            
            return None
            
        except Exception as e:
            raise Exception(f"Erro ao buscar usuário '{user_name}': {str(e)}")

    # ===== MÉTODOS PARA DEALS (NEGÓCIOS) =====
    
    def add_deal(self, fields: Dict[str, Any]) -> int:
        """
        Adiciona um novo deal (negócio) ao Bitrix24.
        
        Args:
            fields (Dict[str, Any]): Campos do deal a ser criado.
                Campos comuns incluem:
                - TITLE: Título do deal (obrigatório)
                - TYPE_ID: Tipo do deal (SALE, etc.)
                - STAGE_ID: Estágio do deal no funil de vendas
                - CONTACT_ID: ID do contato principal
                - COMPANY_ID: ID da empresa
                - OPPORTUNITY: Valor do deal
                - CURRENCY_ID: Moeda (BRL, USD, etc.)
                - PROBABILITY: Probabilidade de fechamento (0-100)
                - ASSIGNED_BY_ID: ID do usuário responsável
                - OPENED: Y/N - se o deal está aberto para todos
                - CLOSEDATE: Data prevista de fechamento (YYYY-MM-DD)
                - COMMENTS: Comentários sobre o deal
                - SOURCE_ID: Fonte do deal
                - SOURCE_DESCRIPTION: Descrição da fonte
        
        Returns:
            int: ID do deal criado.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> deal_fields = {
            ...     "TITLE": "Venda de Software",
            ...     "TYPE_ID": "SALE",
            ...     "STAGE_ID": "NEW",
            ...     "CONTACT_ID": 123,
            ...     "OPPORTUNITY": 5000.00,
            ...     "CURRENCY_ID": "BRL",
            ...     "ASSIGNED_BY_ID": 1
            ... }
            >>> deal_id = api.add_deal(deal_fields)
            >>> print(f"Deal criado com ID: {deal_id}")
        """
        params = {"fields": fields}
        result = self._make_request("crm.deal.add", params)
        
        if not result.get("result"):
            raise Exception(f"Erro ao adicionar deal: {result}")
            
        return result["result"]
    
    def list_deals(self, 
                   filter_params: Optional[Dict] = None, 
                   select: Optional[List[str]] = None, 
                   order: Optional[Dict[str, str]] = None,
                   start: int = 0) -> Dict:
        """
        Lista deals (negócios) do Bitrix24 com opções de filtragem e paginação.
        
        Args:
            filter_params (Dict, optional): Filtros para a busca de deals.
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
                {">=DATE_CREATE": "2022-01-01"} - deals criados a partir de 01/01/2022
                {"TITLE": "Venda"} - deals com título exatamente "Venda"
                {"%TITLE": "Software"} - deals com título contendo "Software"
                {"@STAGE_ID": ["NEW", "PREPARATION"]} - deals nos estágios NEW ou PREPARATION
                {">=OPPORTUNITY": 1000} - deals com valor maior ou igual a 1000
                
            select (List[str], optional): Campos a serem retornados.
                Se None, todos os campos serão retornados ('*' + 'UF_*').
                Valores especiais:
                - '*' — para selecionar todos os campos (excluindo campos personalizados e múltiplos)
                - 'UF_*' — para selecionar todos os campos personalizados (excluindo campos múltiplos)
                
            order (Dict[str, str], optional): Ordenação dos resultados.
                Formato: {"CAMPO": "ASC|DESC"}
                Exemplo: {"DATE_CREATE": "DESC", "OPPORTUNITY": "ASC"}
                Se None, a ordenação padrão será por data de criação decrescente.
                
            start (int, optional): Índice inicial para paginação. Padrão é 0.
                A API Bitrix24 sempre retorna 50 registros por página.
                Para selecionar a segunda página, use start=50,
                para a terceira página, use start=100, e assim por diante.
        
        Returns:
            Dict: Dicionário contendo os deals encontrados na chave "result".
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> # Buscar deals com valor maior que 1000
            >>> deals = api.list_deals(
            ...     filter_params={">OPPORTUNITY": 1000},
            ...     select=["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "CONTACT_ID"]
            ... )
            >>> for deal in deals["result"]:
            ...     print(f"{deal['TITLE']} - R$ {deal['OPPORTUNITY']}")
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
            
        return self._make_request("crm.deal.list", params)
    
    def get_deal_by_id(self, deal_id: int) -> Dict:
        """
        Obtém um deal (negócio) específico pelo ID.
        
        Args:
            deal_id (int): ID do deal a ser obtido.
            
        Returns:
            Dict: Dados do deal.
            
        Raises:
            Exception: Se o deal não for encontrado.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> deal = api.get_deal_by_id(123)
            >>> print(f"Deal: {deal['TITLE']} - Valor: R$ {deal['OPPORTUNITY']}")
        """
        params = {"id": deal_id}
        result = self._make_request("crm.deal.get", params)
        
        if not result.get("result"):
            raise Exception(f"Deal com ID {deal_id} não encontrado")
            
        return result["result"]
    
    def update_deal(self, deal_id: int, fields: Dict[str, Any]) -> bool:
        """
        Atualiza um deal (negócio) existente.
        
        Args:
            deal_id (int): ID do deal a ser atualizado.
            fields (Dict[str, Any]): Campos a serem atualizados.
                Os campos seguem a mesma estrutura do método add_deal.
        
        Returns:
            bool: True se a atualização foi bem-sucedida.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> success = api.update_deal(123, {"STAGE_ID": "PREPARATION", "OPPORTUNITY": 7500.00})
            >>> print(f"Deal atualizado: {success}")
        """
        params = {"id": deal_id, "fields": fields}
        result = self._make_request("crm.deal.update", params)
        
        if not result.get("result"):
            raise Exception(f"Erro ao atualizar deal {deal_id}: {result}")
            
        return result["result"]
    
    def delete_deal(self, deal_id: int) -> bool:
        """
        Remove um deal (negócio) do Bitrix24.
        
        Args:
            deal_id (int): ID do deal a ser removido.
        
        Returns:
            bool: True se a remoção foi bem-sucedida.
            
        Example:
            >>> api = BitrixAPI("https://exemplo.bitrix24.com.br/rest/1/abc123xyz/")
            >>> success = api.delete_deal(123)
            >>> print(f"Deal removido: {success}")
        """
        params = {"id": deal_id}
        result = self._make_request("crm.deal.delete", params)
        
        if not result.get("result"):
            raise Exception(f"Erro ao remover deal {deal_id}: {result}")
            
        return result["result"]

    # ===== MÉTODOS PARA ADMINISTRAÇÃO DE CONTATOS =====
    
    def find_contacts_by_criteria(self, phone: str = None, cnpj: str = None) -> List[Dict]:
        """
        Busca contatos existentes pelos critérios especificados (PHONE ou CNPJ apenas).
        Removido o parâmetro 'name' para tornar a busca mais assertiva.
        
        Args:
            phone (str, optional): Telefone para busca.
            cnpj (str, optional): CNPJ para busca (campo UF_CRM_1734528621).
        
        Returns:
            List[Dict]: Lista de contatos encontrados que correspondem aos critérios.
        """
        contacts = []
        
        try:
            # Busca por telefone
            if phone:
                result = self.list_contacts(
                    filter_params={"PHONE": phone},
                    select=["ID", "NAME", "PHONE", "UF_CRM_1734528621", "ASSIGNED_BY_ID"]
                )
                if result.get("result"):
                    contacts.extend(result["result"])
            
            # Busca por CNPJ
            if cnpj:
                result = self.list_contacts(
                    filter_params={"UF_CRM_1734528621": cnpj},
                    select=["ID", "NAME", "PHONE", "UF_CRM_1734528621", "ASSIGNED_BY_ID"]
                )
                if result.get("result"):
                    # Evita duplicatas
                    existing_ids = {contact["ID"] for contact in contacts}
                    for contact in result["result"]:
                        if contact["ID"] not in existing_ids:
                            contacts.append(contact)
            
            return contacts
            
        except Exception as e:
            raise Exception(f"Erro ao buscar contatos pelos critérios especificados: {str(e)}")
    
    def create_or_update_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria um novo contato ou atualiza um existente baseado nos dados fornecidos.
        Realiza gestão de duplicados buscando por NAME, PHONE ou CNPJ.
        
        Args:
            contact_data (Dict[str, Any]): Dados do contato no formato:
                {
                    "data": null,
                    "cnpj": "35167389312",
                    "telefone": "4191574642",
                    "nome": "Teste Criação de contato",
                    "empresa": "Testando criação de contato",
                    "consultor": "Guilherme Verissimo",
                    "forma_prospeccao": null,
                    "etapa": "Contato novo",
                    "banco": "C6 - Planilha Geral"
                }
        
        Returns:
            Dict[str, Any]: Dicionário com informações sobre a operação:
                {
                    "action": "created" | "updated",
                    "contact_id": int,
                    "message": str,
                    "contact_data": Dict
                }
        """
        try:
            # Extrai dados necessários com tratamento seguro de None
            empresa = self._safe_strip(contact_data.get("empresa"))
            telefone = self._safe_strip(contact_data.get("telefone"))
            cnpj = self._safe_strip(contact_data.get("cnpj"))
            consultor = self._safe_strip(contact_data.get("consultor"))
            
            # Validação: pelo menos um campo de busca deve estar preenchido
            if not telefone and not cnpj:
                raise Exception("É necessário fornecer pelo menos um dos campos: telefone ou CNPJ")
            
            # Busca por contatos existentes
            existing_contacts = self.find_contacts_by_criteria(
                phone=telefone if telefone else None,
                cnpj=cnpj if cnpj else None
            )
            
            # Busca o ID do consultor se fornecido
            assigned_by_id = None
            if consultor:
                user = self.find_user_by_name(consultor)
                if user:
                    assigned_by_id = int(user["ID"])
                else:
                    print(f"Aviso: Consultor '{consultor}' não encontrado no Bitrix24")
            
            # Prepara os campos do contato
            contact_fields = {}
            
            # Adiciona nome da empresa se fornecido
            if empresa:
                contact_fields["NAME"] = empresa
            
            # Adiciona telefone se fornecido
            if telefone:
                contact_fields["PHONE"] = [{"VALUE": telefone, "VALUE_TYPE": "WORK"}]
            
            # Adiciona CNPJ se fornecido
            if cnpj:
                contact_fields["UF_CRM_1734528621"] = cnpj
            
            # Adiciona consultor se encontrado
            if assigned_by_id:
                contact_fields["ASSIGNED_BY_ID"] = assigned_by_id
            
            # Para criação de contato, é necessário pelo menos o campo NAME
            # Se não tiver empresa, usa uma identificação baseada nos outros campos
            if not empresa and not existing_contacts:
                if telefone and cnpj:
                    contact_fields["NAME"] = f"Contato - CNPJ: {cnpj}"
                elif telefone:
                    contact_fields["NAME"] = f"Contato - Tel: {telefone}"
                elif cnpj:
                    contact_fields["NAME"] = f"Contato - CNPJ: {cnpj}"
            
            # Se encontrou contatos existentes, atualiza o primeiro
            if existing_contacts:
                contact_id = int(existing_contacts[0]["ID"])
                
                # Para telefones, precisamos mesclar com os existentes em vez de sobrescrever
                update_fields = {}
                
                # Processa telefone especialmente para não sobrescrever
                if telefone:
                    # Obtém os telefones existentes do contato
                    existing_phones = existing_contacts[0].get("PHONE", [])
                    if not isinstance(existing_phones, list):
                        existing_phones = []
                    
                    # Mescla o novo telefone com os existentes
                    merged_phones = self._merge_phone_numbers(existing_phones, telefone)
                    update_fields["PHONE"] = merged_phones
                
                # Adiciona outros campos que não estão vazios
                for key, value in contact_fields.items():
                    if value and key != "PHONE":  # PHONE já foi processado especialmente
                        update_fields[key] = value
                
                if update_fields:  # Só atualiza se há campos para atualizar
                    self.update_contact(contact_id, update_fields)
                
                contact_name = existing_contacts[0].get("NAME", "Contato sem nome")
                phone_info = f" (telefone adicionado: {telefone})" if telefone and telefone not in str(existing_contacts[0].get("PHONE", [])) else ""
                return {
                    "action": "updated",
                    "contact_id": contact_id,
                    "message": f"Contato atualizado: {contact_name}{phone_info}",
                    "contact_data": existing_contacts[0],
                    "duplicates_found": len(existing_contacts)
                }
            
            # Se não encontrou contatos existentes, cria um novo
            else:
                # Verifica se há campos suficientes para criar o contato
                if not contact_fields:
                    raise Exception("Não há dados suficientes para criar um contato")
                
                contact_id = self.add_contact(contact_fields)
                
                # Busca os dados do contato criado para retornar
                created_contact = self.get_contact_by_id(contact_id)
                
                contact_name = created_contact.get("NAME", "Contato sem nome")
                return {
                    "action": "created",
                    "contact_id": contact_id,
                    "message": f"Novo contato criado: {contact_name}",
                    "contact_data": created_contact,
                    "duplicates_found": 0
                }
                
        except Exception as e:
            raise Exception(f"Erro ao criar/atualizar contato: {str(e)}")
    
    def process_contact_batch(self, contacts_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processa uma lista de contatos em lote, criando ou atualizando cada um.
        
        Args:
            contacts_data (List[Dict[str, Any]]): Lista de dados de contatos.
        
        Returns:
            List[Dict[str, Any]]: Lista com os resultados de cada operação.
        """
        results = []
        
        for i, contact_data in enumerate(contacts_data):
            try:
                result = self.create_or_update_contact(contact_data)
                results.append(result)
                print(f"Processado {i+1}/{len(contacts_data)}: {result['message']}")
                
            except Exception as e:
                error_result = {
                    "action": "error",
                    "contact_id": None,
                    "message": f"Erro ao processar contato: {str(e)}",
                    "contact_data": contact_data,
                    "duplicates_found": 0
                }
                results.append(error_result)
                print(f"Erro no contato {i+1}/{len(contacts_data)}: {str(e)}")
        
        return results
    
    def get_contact_summary(self, contact_id: int) -> Dict[str, Any]:
        """
        Obtém um resumo completo de um contato incluindo dados básicos e relacionamentos.
        
        Args:
            contact_id (int): ID do contato.
        
        Returns:
            Dict[str, Any]: Resumo completo do contato.
        """
        try:
            # Obtém dados básicos do contato
            contact = self.get_contact_by_id(contact_id)
            
            # Obtém empresas associadas
            companies = self.get_contact_company_items(contact_id)
            
            # Obtém dados do usuário responsável se existir
            assigned_user = None
            if contact.get("ASSIGNED_BY_ID"):
                try:
                    users_result = self.list_users(
                        filter_params={"ID": contact["ASSIGNED_BY_ID"]},
                        select=["ID", "NAME", "LAST_NAME", "EMAIL"]
                    )
                    if users_result.get("result"):
                        assigned_user = users_result["result"][0]
                except:
                    pass  # Ignora erro se usuário não encontrado
            
            return {
                "contact": contact,
                "companies": companies,
                "assigned_user": assigned_user,
                "summary": {
                    "id": contact.get("ID"),
                    "name": contact.get("NAME"),
                    "phone": contact.get("PHONE"),
                    "cnpj": contact.get("UF_CRM_1734528621"),
                    "assigned_to": f"{assigned_user.get('NAME', '')} {assigned_user.get('LAST_NAME', '')}" if assigned_user else None,
                    "companies_count": len(companies) if companies else 0
                }
            }
            
        except Exception as e:
            raise Exception(f"Erro ao obter resumo do contato {contact_id}: {str(e)}")
    
    # ===== MÉTODOS PARA ADMINISTRAÇÃO DE DEALS (NEGÓCIOS) =====
    
    def find_deals_by_criteria(self, cnpj: str = None) -> List[Dict]:
        """
        Busca deals existentes pelos critérios especificados (CNPJ apenas).
        Removido o parâmetro 'title' para tornar a busca mais assertiva.
        NÃO busca por CONTACT_ID para permitir múltiplos deals por contato.
        
        Args:
            cnpj (str, optional): CNPJ para busca (campo UF_CRM_1741653424).
        
        Returns:
            List[Dict]: Lista de deals encontrados que correspondem aos critérios.
        """
        deals = []
        
        try:
            # Busca por CNPJ
            if cnpj:
                result = self.list_deals(
                    filter_params={"UF_CRM_1741653424": cnpj},
                    select=["ID", "TITLE", "UF_CRM_1741653424", "CONTACT_ID", "CATEGORY_ID", 
                           "UF_CRM_1748264680989", "ASSIGNED_BY_ID", "STAGE_ID"]
                )
                if result.get("result"):
                    deals.extend(result["result"])
            
            return deals
            
        except Exception as e:
            raise Exception(f"Erro ao buscar deals pelos critérios especificados: {str(e)}")
    
    def create_or_update_deal(self, deal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria um novo deal ou atualiza um existente baseado nos dados fornecidos.
        Realiza gestão de duplicados buscando APENAS por TITLE ou CNPJ (não por CONTACT_ID).
        Também verifica/cria o contato associado se necessário.
        
        Args:
            deal_data (Dict[str, Any]): Dados do deal no formato:
                {
                    "data": null,
                    "cnpj": "35167389312",
                    "telefone": "4191574642",
                    "nome": "Teste Criação de contato",
                    "empresa": "Testando criação de contato",
                    "consultor": "Guilherme Verissimo",
                    "forma_prospeccao": "Email",
                    "etapa": "Contato novo",
                    "banco": "C6 - Planilha Geral"
                }
        
        Returns:
            Dict[str, Any]: Dicionário com informações sobre a operação:
                {
                    "action": "created" | "updated",
                    "deal_id": int,
                    "contact_id": int,
                    "message": str,
                    "deal_data": Dict
                }
        """
        try:
            # Extrai dados necessários com tratamento seguro de None
            empresa = self._safe_strip(deal_data.get("empresa"))
            cnpj = self._safe_strip(deal_data.get("cnpj"))
            consultor = self._safe_strip(deal_data.get("consultor"))
            forma_prospeccao = self._safe_strip(deal_data.get("forma_prospeccao"))
            etapa = self._safe_strip(deal_data.get("etapa"))
            banco = self._safe_strip(deal_data.get("banco"))
            
            # Validação: CNPJ é obrigatório para deals
            if not cnpj:
                raise Exception("É necessário fornecer o CNPJ para criar/atualizar um deal")
            
            # 1. Primeiro, verifica/cria o contato associado
            contact_result = self.create_or_update_contact(deal_data)
            contact_id = contact_result["contact_id"]
            
            # 2. Busca por deals existentes APENAS por CNPJ (não por contact_id)
            existing_deals = self.find_deals_by_criteria(
                cnpj=cnpj if cnpj else None
            )
            
            # 3. Busca o ID do consultor se fornecido
            assigned_by_id = None
            if consultor:
                user = self.find_user_by_name(consultor)
                if user:
                    assigned_by_id = int(user["ID"])
                else:
                    print(f"Aviso: Consultor '{consultor}' não encontrado no Bitrix24")
            
            # 4. Busca o ID do status se fornecido
            stage_id = None
            if etapa:
                status = self.find_status_by_name(etapa, "DEAL_STAGE_4")  # Sempre DEAL_STAGE_4
                if status:
                    stage_id = status["STATUS_ID"]
                else:
                    print(f"Aviso: Etapa '{etapa}' não encontrada no funil DEAL_STAGE_4")
            
            # 5. Processa o campo banco se fornecido
            banco_id = None
            if banco:
                # Dicionário de mapeamento dos bancos
                bancos_map = {
                    'C6': '116',
                    'BS2': '118', 
                    'SANTANDER': '120'
                }
                
                # Extrai o nome do banco (parte antes do " - ")
                banco_nome = banco.split(' - ')[0].strip().upper()
                
                # Busca o ID correspondente
                if banco_nome in bancos_map:
                    banco_id = bancos_map[banco_nome]
                else:
                    print(f"Aviso: Banco '{banco_nome}' não encontrado no mapeamento. Bancos disponíveis: {list(bancos_map.keys())}")
            
            # 6. Prepara os campos do deal
            deal_fields = {
                "CATEGORY_ID": 4,  # Sempre 4 (Vendas)
                "CONTACT_ID": contact_id,  # ID do contato associado
            }
            
            # Adiciona título (empresa) se fornecido
            if empresa:
                deal_fields["TITLE"] = empresa
            else:
                # Se não tem empresa, usa uma identificação baseada no CNPJ
                deal_fields["TITLE"] = f"Deal - CNPJ: {cnpj}" if cnpj else f"Deal - Contato ID: {contact_id}"
            
            # Adiciona CNPJ se fornecido
            if cnpj:
                deal_fields["UF_CRM_1741653424"] = cnpj
            
            # Adiciona forma de prospecção se fornecida
            if forma_prospeccao:
                deal_fields["UF_CRM_1748264680989"] = forma_prospeccao
            
            # Adiciona banco se encontrado
            if banco_id:
                deal_fields["UF_CRM_1743684072273"] = banco_id
            
            # Adiciona consultor se encontrado
            if assigned_by_id:
                deal_fields["ASSIGNED_BY_ID"] = assigned_by_id
            
            # Adiciona estágio se encontrado
            if stage_id:
                deal_fields["STAGE_ID"] = stage_id
            
            # 7. Se encontrou deals existentes, atualiza o primeiro
            if existing_deals:
                deal_id = int(existing_deals[0]["ID"])
                
                # Atualiza apenas campos que não estão vazios
                update_fields = {}
                for key, value in deal_fields.items():
                    if value:  # Só atualiza se o valor não estiver vazio
                        update_fields[key] = value
                
                if update_fields:  # Só atualiza se há campos para atualizar
                    self.update_deal(deal_id, update_fields)
                
                deal_title = existing_deals[0].get("TITLE", "Deal sem título")
                return {
                    "action": "updated",
                    "deal_id": deal_id,
                    "contact_id": contact_id,
                    "message": f"Deal atualizado: {deal_title}",
                    "deal_data": existing_deals[0],
                    "contact_action": contact_result["action"],
                    "duplicates_found": len(existing_deals)
                }
            
            # 8. Se não encontrou deals existentes, cria um novo
            else:
                # Verifica se há campos suficientes para criar o deal
                if not deal_fields.get("TITLE"):
                    raise Exception("Não há dados suficientes para criar um deal")
                
                deal_id = self.add_deal(deal_fields)
                
                # Busca os dados do deal criado para retornar
                created_deal = self.get_deal_by_id(deal_id)
                
                deal_title = created_deal.get("TITLE", "Deal sem título")
                return {
                    "action": "created",
                    "deal_id": deal_id,
                    "contact_id": contact_id,
                    "message": f"Novo deal criado: {deal_title}",
                    "deal_data": created_deal,
                    "contact_action": contact_result["action"],
                    "duplicates_found": 0
                }
                
        except Exception as e:
            raise Exception(f"Erro ao criar/atualizar deal: {str(e)}")
    
    def process_deal_batch(self, deals_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processa uma lista de deals em lote, criando ou atualizando cada um.
        Também processa os contatos associados automaticamente.
        
        Args:
            deals_data (List[Dict[str, Any]]): Lista de dados de deals.
        
        Returns:
            List[Dict[str, Any]]: Lista com os resultados de cada operação.
        """
        results = []
        
        for i, deal_data in enumerate(deals_data):
            try:
                result = self.create_or_update_deal(deal_data)
                results.append(result)
                print(f"Processado {i+1}/{len(deals_data)}: {result['message']}")
                
            except Exception as e:
                error_result = {
                    "action": "error",
                    "deal_id": None,
                    "contact_id": None,
                    "message": f"Erro ao processar deal: {str(e)}",
                    "deal_data": deal_data,
                    "contact_action": "error",
                    "duplicates_found": 0
                }
                results.append(error_result)
                print(f"Erro no deal {i+1}/{len(deals_data)}: {str(e)}")
        
        return results
    
    def get_deal_summary(self, deal_id: int) -> Dict[str, Any]:
        """
        Obtém um resumo completo de um deal incluindo dados básicos, contato e responsável.
        
        Args:
            deal_id (int): ID do deal.
        
        Returns:
            Dict[str, Any]: Resumo completo do deal.
        """
        try:
            # Obtém dados básicos do deal
            deal = self.get_deal_by_id(deal_id)
            
            # Obtém dados do contato associado se existir
            contact = None
            if deal.get("CONTACT_ID"):
                try:
                    contact = self.get_contact_by_id(int(deal["CONTACT_ID"]))
                except:
                    pass  # Ignora erro se contato não encontrado
            
            # Obtém dados do usuário responsável se existir
            assigned_user = None
            if deal.get("ASSIGNED_BY_ID"):
                try:
                    users_result = self.list_users(
                        filter_params={"ID": deal["ASSIGNED_BY_ID"]},
                        select=["ID", "NAME", "LAST_NAME", "EMAIL"]
                    )
                    if users_result.get("result"):
                        assigned_user = users_result["result"][0]
                except:
                    pass  # Ignora erro se usuário não encontrado
            
            # Obtém informações do estágio atual
            stage_info = None
            if deal.get("STAGE_ID"):
                try:
                    stages_result = self._make_request('crm.status.list', {
                        'filter': {
                            'ENTITY_ID': 'DEAL_STAGE_4',
                            'STATUS_ID': deal["STAGE_ID"]
                        }
                    })
                    if stages_result.get("result"):
                        stage_info = stages_result["result"][0]
                except:
                    pass  # Ignora erro se estágio não encontrado
            
            return {
                "deal": deal,
                "contact": contact,
                "assigned_user": assigned_user,
                "stage_info": stage_info,
                "summary": {
                    "id": deal.get("ID"),
                    "title": deal.get("TITLE"),
                    "cnpj": deal.get("UF_CRM_1741653424"),
                    "forma_prospeccao": deal.get("UF_CRM_1748264680989"),
                    "contact_id": deal.get("CONTACT_ID"),
                    "contact_name": contact.get("NAME") if contact else None,
                    "assigned_to": f"{assigned_user.get('NAME', '')} {assigned_user.get('LAST_NAME', '')}" if assigned_user else None,
                    "stage_name": stage_info.get("NAME") if stage_info else None,
                    "category_id": deal.get("CATEGORY_ID")
                }
            }
            
        except Exception as e:
            raise Exception(f"Erro ao obter resumo do deal {deal_id}: {str(e)}")
    
    def _merge_phone_numbers(self, existing_phones: List[Dict], new_phone: str) -> List[Dict]:
        """
        Método auxiliar para mesclar números de telefone, evitando duplicatas.
        
        Args:
            existing_phones (List[Dict]): Lista de telefones existentes no formato Bitrix24.
            new_phone (str): Novo número de telefone a ser adicionado.
        
        Returns:
            List[Dict]: Lista combinada de telefones sem duplicatas.
        """
        if not new_phone:
            return existing_phones
        
        # Normaliza o novo telefone removendo espaços e caracteres especiais para comparação
        new_phone_normalized = ''.join(filter(str.isdigit, new_phone))
        
        # Verifica se o telefone já existe
        for phone in existing_phones:
            existing_phone_normalized = ''.join(filter(str.isdigit, phone.get("VALUE", "")))
            if existing_phone_normalized == new_phone_normalized:
                # Telefone já existe, não adiciona
                return existing_phones
        
        # Telefone não existe, adiciona à lista
        combined_phones = existing_phones.copy()
        combined_phones.append({"VALUE": new_phone, "VALUE_TYPE": "WORK"})
        
        return combined_phones