# Documentação - Administração de Contatos Bitrix24

Este documento explica como usar as funções criadas para administrar contatos no Bitrix24 com gestão automática de duplicados.

## Funções Principais

### 1. `find_contacts_by_criteria(name, phone, cnpj)`

Busca contatos existentes usando um ou mais critérios:
- **name**: Nome da empresa (campo NAME)
- **phone**: Telefone (campo PHONE)
- **cnpj**: CNPJ (campo UF_CRM_1734528621)

**Exemplo:**
```python
api = BitrixAPI(webhook_url)
contacts = api.find_contacts_by_criteria(
    name="Empresa ABC",
    phone="11999887766",
    cnpj="12345678000199"
)
```

### 2. `create_or_update_contact(contact_data)`

Função principal que cria um novo contato ou atualiza um existente. Realiza gestão automática de duplicados.

**Formato de entrada esperado:**
```python
contact_data = {
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
```

**Mapeamento de campos:**
- `empresa` → `NAME` (Nome da empresa no Bitrix)
- `telefone` → `PHONE` (Telefone de trabalho)
- `cnpj` → `UF_CRM_1734528621` (Campo personalizado CNPJ)
- `consultor` → `ASSIGNED_BY_ID` (ID do usuário responsável via find_user_by_name)

**Retorno:**
```python
{
    "action": "created" | "updated",
    "contact_id": int,
    "message": str,
    "contact_data": Dict,
    "duplicates_found": int
}
```

### 3. `process_contact_batch(contacts_data)`

Processa uma lista de contatos em lote. Útil para importações em massa.

**Exemplo:**
```python
contacts_list = [contact_data1, contact_data2, contact_data3]
results = api.process_contact_batch(contacts_list)
```

### 4. `get_contact_summary(contact_id)`

Obtém um resumo completo de um contato incluindo dados do responsável e empresas associadas.

## Gestão de Duplicados

O sistema realiza busca por duplicados usando os seguintes critérios:

1. **Nome da empresa** (correspondência exata)
2. **Telefone** (correspondência exata)
3. **CNPJ** (correspondência exata)

Se encontrar duplicados:
- **Atualiza** o primeiro contato encontrado
- **Não cria** novos contatos
- **Retorna** quantos duplicados foram encontrados

Se não encontrar duplicados:
- **Cria** um novo contato
- **Retorna** os dados do contato criado

## Busca de Usuários (Consultores)

A função `find_user_by_name()` busca usuários no Bitrix24 por:
1. Nome completo (nome + sobrenome)
2. Substring no nome
3. Substring no sobrenome

**Prioriza usuários ativos** (ACTIVE = "Y")

## Campos Obrigatórios vs Opcionais

### Regra de Validação:
- **Pelo menos um campo** deve estar preenchido entre: `empresa`, `telefone` ou `cnpj`
- **Nenhum campo é individualmente obrigatório**

### Campos Disponíveis:
- `empresa`: Nome da empresa (se fornecido, será usado como NAME)
- `telefone`: Se fornecido, será adicionado como telefone de trabalho
- `cnpj`: Se fornecido, será adicionado no campo personalizado UF_CRM_1734528621
- `consultor`: Se fornecido e encontrado, será definido como responsável

### Comportamento Especial:
Quando não há nome da empresa mas outros campos estão presentes, o sistema automaticamente gera um nome baseado nos dados disponíveis:
- Se tem telefone e CNPJ: `"Contato - CNPJ: {cnpj}"`
- Se tem apenas telefone: `"Contato - Tel: {telefone}"`
- Se tem apenas CNPJ: `"Contato - CNPJ: {cnpj}"`

## Exemplo de Uso Completo

```python
from bitrix_api import BitrixAPI

# Configuração
api = BitrixAPI("https://seudominio.bitrix24.com.br/rest/USER_ID/WEBHOOK_KEY/")

# Dados do contato
contact_data = {
    "data": None,
    "cnpj": "12345678000199",
    "telefone": "11999887766",
    "nome": "Contato Teste",
    "empresa": "Empresa Teste Ltda",
    "consultor": "João Silva",
    "forma_prospeccao": None,
    "etapa": "Contato novo", 
    "banco": "Banco Teste"
}

# Processa o contato
try:
    result = api.create_or_update_contact(contact_data)
    
    if result['action'] == 'created':
        print(f"Novo contato criado: ID {result['contact_id']}")
    elif result['action'] == 'updated':
        print(f"Contato atualizado: ID {result['contact_id']}")
        print(f"Duplicados encontrados: {result['duplicates_found']}")
    
    # Obtém resumo do contato
    summary = api.get_contact_summary(result['contact_id'])
    print(f"Responsável: {summary['summary']['assigned_to']}")
    
except Exception as e:
    print(f"Erro: {str(e)}")
```

## Tratamento de Erros

As funções são robustas e tratam os seguintes cenários:
- Empresa não informada (obrigatório)
- Consultor não encontrado (aviso, mas continua)
- Usuário inativo (busca outros usuários)
- Erro na API do Bitrix24
- Campos vazios ou nulos

## Configuração Necessária

1. **Webhook URL**: Configure no arquivo ou passe como parâmetro
2. **Campo CNPJ**: Verifique se o campo `UF_CRM_1734528621` existe no seu Bitrix24
3. **Usuários**: Certifique-se que os consultores estão cadastrados no sistema