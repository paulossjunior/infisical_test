# infisical_test

Script em Python que verifica se uma Machine Identity do [Infisical](https://infisical.com) consegue autenticar e acessar secrets de um projeto, usando o SDK oficial [`infisicalsdk`](https://pypi.org/project/infisicalsdk/).

Serve para:

- validar credenciais novas antes de usá-las numa aplicação;
- conferir se as permissões da identity no projeto estão corretas (leitura e escrita);
- diagnosticar erros de acesso (401, 403, 404) com mensagens claras;
- rodar como checagem em CI (exit code `0` = OK, `1` = falha).

## Sumário

- [Requisitos](#requisitos)
- [Configurar o Infisical](#configurar-o-infisical)
- [Instalação](#instalação)
- [Configuração (`.env`)](#configuração-env)
- [Uso](#uso)
- [Usar `print_secrets` no seu código](#usar-print_secrets-no-seu-código)
- [Como o código funciona](#como-o-código-funciona)
- [Erros comuns](#erros-comuns)
- [Segurança](#segurança)

## Requisitos

- Python 3.10 ou superior
- Acesso a uma instância Infisical (cloud ou self-hosted)
- Permissão para criar Machine Identities na organização

## Configurar o Infisical

### 1. Criar a Machine Identity

1. Acesse **Organization Settings → Access Control → Identities**.
2. Clique em **Create Identity**, dê um nome (ex.: `sdk-test`) e escolha a role de organização `Member`.

### 2. Gerar Client ID e Client Secret

1. Abra a identity criada. Em **Authentication**, o método **Universal Auth** já vem configurado. Se não estiver, adicione-o em **Add Auth Method**.
2. Copie o **Client ID**.
3. Em **Client Secrets**, clique em **Create Client Secret** e copie o valor gerado.

> O Client Secret é exibido **uma única vez**. Se perder, crie outro e revogue o antigo.

### 3. Dar acesso ao projeto

1. No projeto, vá em **Access Control → Machine Identities → Add Identity**.
2. Selecione a identity e escolha a role:
   - `Viewer`: somente leitura (suficiente para o modo padrão e `--print`);
   - `Developer`: leitura e escrita (necessária para `--write`).

### 4. Anotar o Project ID

Em **Project Settings**, copie o **Project ID**. O slug do ambiente (`dev`, `staging`, `prod`) aparece na aba de secrets.

## Instalação

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Depois, preencha o `.env` com os dados obtidos acima.

## Configuração (`.env`)

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `INFISICAL_HOST` | não | `https://app.infisical.com` | URL da instância. EU: `https://eu.infisical.com`. Self-hosted: URL do seu servidor. |
| `INFISICAL_CLIENT_ID` | sim | — | Client ID da Machine Identity (Universal Auth). |
| `INFISICAL_CLIENT_SECRET` | sim | — | Client Secret da Machine Identity. |
| `INFISICAL_PROJECT_ID` | sim | — | ID do projeto. |
| `INFISICAL_ENV` | não | `dev` | Slug do ambiente. |
| `INFISICAL_SECRET_PATH` | não | `/` | Pasta dos secrets dentro do ambiente. |
| `INFISICAL_TEST_SECRET_NAME` | não | — | Nome de um secret existente para testar a leitura individual. |

## Uso

```bash
.venv/bin/python test_credentials.py [--write] [--show] [--print]
```

| Comando | O que faz |
|---|---|
| *(sem flags)* | Login + listagem dos secrets com valores mascarados. Se `INFISICAL_TEST_SECRET_NAME` estiver definido, também lê esse secret. |
| `--show` | Igual ao padrão, mas exibe os valores sem máscara. |
| `--write` | Além da leitura, cria um secret temporário `SDK_TEST_XXXXXXXX`, lê de volta conferindo o valor, atualiza e exclui. |
| `--print` | Faz login e imprime todos os secrets com valor, versão e comentário. Não executa as demais etapas. |

### Exemplo de saída (`--write`)

```text
Host: https://app.infisical.com | Projeto: 0867c1af-... | Env: dev | Path: /

[OK ] Login Universal Auth (516 ms) token Bearer, expira em 2592000s
        - Teste = 12***
[OK ] Listar secrets (257 ms) 1 secret(s), 0 import(s)
[OK ] Criar secret 'SDK_TEST_236B81C8' (329 ms) SDK_TEST_236B81C8 v1
[OK ] Ler secret criado (226 ms) valor confere
[OK ] Atualizar secret (316 ms) v2
[OK ] Excluir secret (286 ms) SDK_TEST_236B81C8 removido

Resumo: 6/6 etapas OK
```

### Exemplo de saída (`--print`)

```text
[OK ] Login Universal Auth (581 ms) token Bearer, expira em 2592000s

Secrets em dev:/ (1)
  Teste = 123  (v1)  # Teste
[OK ] Imprimir secrets (339 ms)
```

### Exit code

- `0`: todas as etapas passaram.
- `1`: alguma etapa falhou ou falta uma variável obrigatória.

## Usar `print_secrets` no seu código

A função pode ser importada e usada com qualquer cliente já autenticado:

```python
from infisical_sdk import InfisicalSDKClient
from test_credentials import print_secrets

with InfisicalSDKClient(host="https://app.infisical.com") as client:
    client.auth.universal_auth.login(client_id="...", client_secret="...")
    print_secrets(client, project_id="...", environment_slug="dev",
                  secret_path="/", recursive=True)
```

Com `recursive=True`, os secrets das subpastas também são listados, com o caminho no início de cada linha.

## Como o código funciona

Todo o código está em [`test_credentials.py`](test_credentials.py).

| Componente | Responsabilidade |
|---|---|
| `main()` | Lê o `.env`, cria o `InfisicalSDKClient`, autentica e executa as etapas conforme as flags. |
| `Runner` | Executa cada etapa, mede o tempo, captura erros do SDK e gera o resumo e o exit code. |
| `print_secrets()` | Lista e imprime os secrets de um ambiente/pasta sem máscara. |
| `mask()` | Esconde o valor de um secret, mantendo só os 2 primeiros caracteres. |
| `require_env()` | Lê uma variável obrigatória ou encerra com erro. |

Fluxo de execução:

1. **Login**: `client.auth.universal_auth.login()` troca Client ID/Secret por um access token, que o SDK guarda e usa nas chamadas seguintes. Se o login falhar, o script para aqui.
2. **Leitura**: `client.secrets.list_secrets()` e, opcionalmente, `get_secret_by_name()`.
3. **Escrita** (`--write`): `create_secret_by_name()` → `get_secret_by_name()` → `update_secret_by_name()` → `delete_secret_by_name()`. Se a criação passar, a exclusão é sempre tentada, para não deixar lixo no projeto.

O cliente é criado com `cache_ttl=None` para desligar o cache do SDK. Assim, a leitura feita logo após a escrita vem da API, e não de uma cópia antiga em memória.

Erros do SDK (`APIError`, `InfisicalError`) são registrados como falha da etapa, com o status HTTP. Outras exceções interrompem o script, pois indicam bug no código.

## Erros comuns

| Erro | Causa provável | Solução |
|---|---|---|
| `APIError 401: Invalid credentials` | Client ID ou Secret errado, ou secret revogado/expirado. | Gere um novo Client Secret e atualize o `.env`. |
| `APIError 403` na listagem | A identity não foi adicionada ao projeto ou não tem permissão no ambiente. | Adicione a identity ao projeto (passo 3). |
| `APIError 403` em `--write` | A role é `Viewer`. | Troque para `Developer` ou outra role com escrita. |
| `APIError 404` | Project ID, ambiente ou pasta inexistente. | Confira `INFISICAL_PROJECT_ID`, `INFISICAL_ENV` e `INFISICAL_SECRET_PATH`. |
| `InfisicalError: Request failed` | Host inacessível ou URL errada. | Confira `INFISICAL_HOST` e a conectividade de rede. |
| `Variável de ambiente obrigatória ausente` | `.env` não existe ou está incompleto. | Copie `.env.example` para `.env` e preencha. |

## Segurança

- **Nunca faça commit do `.env`.** Ele já está no `.gitignore`. Não coloque credenciais reais no `.env.example`.
- **Use HTTPS.** Com `http://`, Client Secret, token e valores dos secrets trafegam em texto puro pela rede.
- **`--show` e `--print` exibem valores reais** no terminal, que podem acabar no histórico do shell ou em logs. Evite usá-los em CI ou com o ambiente `prod`.
- **Menor privilégio.** Para testes de leitura, use a role `Viewer`. Dê `Developer` só quando precisar testar escrita.
- **TTL do token.** Configure um TTL curto no Universal Auth da identity. O padrão (30 dias) é longo para um teste.
- **Vazou?** Revogue o Client Secret em **Client Secrets** e gere outro.
