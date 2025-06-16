# Documentação - Administração de Deals (Negócios) Bitrix24

Este documento explica como usar as funções criadas para administrar deals no Bitrix24 com gestão automática de duplicados e criação automática de contatos.

## Funções Principais para Deals

### 1. `find_deals_by_criteria(title, cnpj, contact_id)`

Busca deals existentes usando um ou mais critérios:
- **title**: Título do deal (empresa)
- **cnpj**: CNPJ (campo UF_CRM_1741653424)
- **contact_id**: ID do contato associado

**Exemplo:**
```python
api = BitrixAPI(webhook_url)
deals = api.find_deals_by_criteria(
    title="Empresa ABC",
    cnpj="12345678000199",
    contact_id=123
)
```

### 2. `create_or_update_deal(deal_data)`

Função principal que cria um novo deal ou atualiza um existente. Também verifica/cria o contato associado automaticamente.

**Formato de entrada esperado:**
```python
deal_data = {
    "data": null,
    "cnpj": "35167389312",
    "telefone": "4191574642", 
    "nome": "Teste Criação de contato",
    "empresa": "Testando criação de deal",
    "consultor": "Guilherme Verissimo",
    "forma_prospeccao": "Email Marketing",
    "etapa": "Contato novo",
    "banco": "C6 - Planilha Geral"
}
```

**Mapeamento de campos para deals:**
- `empresa` → `TITLE` (Título do deal)
- `cnpj` → `UF_CRM_1741653424` (Campo personalizado CNPJ)
- `consultor` → `ASSIGNED_BY_ID` (ID do usuário responsável via find_user_by_name)
- `forma_prospeccao` → `UF_CRM_1748264680989` (Forma de prospecção)
- `etapa` → `STAGE_ID` (ID do status via find_status_by_name com entity_id="DEAL_STAGE_4")
- `CATEGORY_ID` → **4** (Sempre 4 - Vendas, valor fixo)
- `CONTACT_ID` → ID do contato (criado/atualizado automaticamente)

**Retorno:**
```python
{
    "action": "created" | "updated",
    "deal_id": int,
    "contact_id": int,
    "message": str,
    "deal_data": Dict,
    "contact_action": "created" | "updated",
    "duplicates_found": int
}
```

### 3. `process_deal_batch(deals_data)`

Processa uma lista de deals em lote. Também processa os contatos associados automaticamente.

**Exemplo:**
```python
deals_list = [deal_data1, deal_data2, deal_data3]
results = api.process_deal_batch(deals_list)
```

### 4. `get_deal_summary(deal_id)`

Obtém um resumo completo de um deal incluindo dados do contato associado, responsável e informações do estágio.

## Configurações Específicas para Deals

### Campos Fixos (Sempre os mesmos valores):
- **CATEGORY_ID**: 4 (Vendas - conforme especificado)
- **Entity ID para Status**: "DEAL_STAGE_4" (sempre este funil)

### Campos Personalizados:
- **UF_CRM_1741653424**: CNPJ
- **UF_CRM_1748264680989**: Forma de Prospecção

## Gestão de Duplicados para Deals (CORRIGIDO)

O sistema realiza busca por duplicados usando APENAS os seguintes critérios:

1. **Título do deal** (correspondência exata)
2. **CNPJ** (correspondência exata)

**IMPORTANTE**: O sistema **NÃO** busca por `contact_id` para permitir que uma empresa (contato) tenha múltiplos deals diferentes.

Se encontrar duplicados:
- **Atualiza** o primeiro deal encontrado
- **Não cria** novos deals
- **Retorna** quantos duplicados foram encontrados

Se não encontrar duplicados:
- **Cria** um novo deal
- **Retorna** os dados do deal criado

### Cenários Práticos:

**✅ Permitido - Múltiplos Deals por Empresa:**
```python
# Mesmo contato, deals com títulos diferentes
deal1 = {"empresa": "ABC Corp", "cnpj": ""}           # Novo deal
deal2 = {"empresa": "ABC Corp - Projeto X", "cnpj": ""} # Novo deal  
deal3 = {"empresa": "ABC Corp - Projeto Y", "cnpj": ""} # Novo deal
```

**🔄 Atualização - Mesmo Título ou CNPJ:**
```python
# Estes atualizariam o mesmo deal
deal1 = {"empresa": "ABC Corp", "cnpj": "12345678000199"}
deal2 = {"empresa": "ABC Corp", "cnpj": "98765432000100"} # Mesmo título = atualiza deal1
deal3 = {"empresa": "XYZ Ltda", "cnpj": "12345678000199"} # Mesmo CNPJ = atualiza deal1
```
## Integração Automática com Contatos

A função `create_or_update_deal()` **automaticamente**:
1. Chama `create_or_update_contact()` primeiro
2. Usa o ID do contato retornado no campo `CONTACT_ID` do deal
3. Retorna informações sobre ambas as operações (deal e contato)

## Campos Obrigatórios vs Opcionais para Deals

### Regra de Validação:
- **Pelo menos um campo** deve estar preenchido entre: `empresa` ou `cnpj`
- **Nenhum campo é individualmente obrigatório**

### Campos Disponíveis:
- `empresa`: Nome da empresa (se fornecido, será usado como TITLE)
- `cnpj`: Se fornecido, será adicionado no campo personalizado UF_CRM_1741653424
- `consultor`: Se fornecido e encontrado, será definido como responsável
- `forma_prospeccao`: Se fornecida, será adicionada no campo UF_CRM_1748264680989
- `etapa`: Se fornecida e encontrada no funil DEAL_STAGE_4, será definida como STAGE_ID

### Comportamento Especial:
Quando não há nome da empresa mas CNPJ está presente, o sistema automaticamente gera um título:
- `"Deal - CNPJ: {cnpj}"` (se tem CNPJ)
- `"Deal - Contato ID: {contact_id}"` (se não tem CNPJ nem empresa)

## Exemplo de Uso Completo

```python
from bitrix_api import BitrixAPI

# Configuração
api = BitrixAPI("https://seudominio.bitrix24.com.br/rest/USER_ID/WEBHOOK_KEY/")

# Dados do deal
deal_data = {
    "data": None,
    "cnpj": "12345678000199",
    "telefone": "11999887766",
    "nome": "Deal Teste",
    "empresa": "Empresa Deal Teste Ltda",
    "consultor": "João Silva",
    "forma_prospeccao": "Email Marketing",
    "etapa": "Qualificação", 
    "banco": "Banco Teste"
}

# Processa o deal (e contato automaticamente)
try:
    result = api.create_or_update_deal(deal_data)
    
    if result['action'] == 'created':
        print(f"Novo deal criado: ID {result['deal_id']}")
    elif result['action'] == 'updated':
        print(f"Deal atualizado: ID {result['deal_id']}")
    
    print(f"Contato: {result['contact_action']} - ID {result['contact_id']}")
    print(f"Duplicados encontrados: {result['duplicates_found']}")
    
    # Obtém resumo completo
    summary = api.get_deal_summary(result['deal_id'])
    print(f"Título: {summary['summary']['title']}")
    print(f"Contato: {summary['summary']['contact_name']}")
    print(f"Responsável: {summary['summary']['assigned_to']}")
    print(f"Estágio: {summary['summary']['stage_name']}")
    
except Exception as e:
    print(f"Erro: {str(e)}")
```

## Fluxo de Processamento

1. **Validação**: Verifica se pelo menos empresa ou CNPJ estão preenchidos
2. **Contato**: Chama `create_or_update_contact()` para garantir que existe um contato
3. **Busca de Duplicados**: Procura deals existentes pelos critérios
4. **Consultor**: Busca o usuário pelo nome (se fornecido)
5. **Estágio**: Busca o status no funil DEAL_STAGE_4 (se fornecido)
6. **Criação/Atualização**: Cria novo deal ou atualiza existente
7. **Retorno**: Fornece informações completas sobre a operação

## Tratamento de Erros

As funções tratam os seguintes cenários:
- Empresa e CNPJ não informados (erro)
- Consultor não encontrado (aviso, mas continua)
- Etapa não encontrada no funil DEAL_STAGE_4 (aviso, mas continua)
- Usuário inativo (busca outros usuários)
- Erro na API do Bitrix24
- Campos vazios ou nulos

## Configuração Necessária

1. **Webhook URL**: Configure no arquivo ou passe como parâmetro
2. **Campos Personalizados**:
   - `UF_CRM_1741653424` (CNPJ) deve existir nos deals
   - `UF_CRM_1748264680989` (Forma Prospecção) deve existir nos deals
   - `UF_CRM_1734528621` (CNPJ) deve existir nos contatos
3. **Funil de Vendas**: Verifique se o funil `DEAL_STAGE_4` existe e tem as etapas corretas
4. **Categoria**: Categoria ID 4 (Vendas) deve existir
5. **Usuários**: Certifique-se que os consultores estão cadastrados no sistema