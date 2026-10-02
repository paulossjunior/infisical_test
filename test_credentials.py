"""Teste de uso de credenciais do Infisical via infisicalsdk.

Etapas:
  1. Login com Machine Identity (Universal Auth)
  2. Listar secrets do projeto/ambiente/pasta
  3. Ler um secret específico (opcional, INFISICAL_TEST_SECRET_NAME)
  4. Ciclo criar -> ler -> atualizar -> excluir (somente com --write)

Uso:
  python test_credentials.py            # somente leitura
  python test_credentials.py --write    # inclui teste de escrita
  python test_credentials.py --show     # mostra valores (cuidado!)
  python test_credentials.py --print    # só imprime secrets e valores
"""

import argparse
import os
import sys
import time
import uuid

from dotenv import load_dotenv
from infisical_sdk import InfisicalSDKClient
from infisical_sdk.infisical_requests import APIError, InfisicalError


def mask(value: str, show: bool) -> str:
    """Mascara o valor de um secret para exibição no terminal.

    Args:
        value: Valor original do secret.
        show: Se True, retorna o valor sem máscara.

    Returns:
        Os 2 primeiros caracteres seguidos de asteriscos, ``<vazio>`` para
        valores vazios, ou o valor original quando ``show`` é True.
    """
    if show:
        return value
    if not value:
        return "<vazio>"
    return value[:2] + "*" * max(len(value) - 2, 3)


def print_secrets(client: InfisicalSDKClient, project_id: str, environment_slug: str,
                  secret_path: str = "/", recursive: bool = False) -> None:
    """Imprime nome e valor (sem máscara) de todos os secrets do ambiente/pasta.

    Cada linha mostra ``NOME = valor (vN) # comentário``, com os nomes
    alinhados e em ordem alfabética.

    Args:
        client: Cliente já autenticado (após ``universal_auth.login``).
        project_id: ID do projeto no Infisical.
        environment_slug: Slug do ambiente (ex.: ``dev``, ``prod``).
        secret_path: Pasta dos secrets. Padrão ``/``.
        recursive: Se True, inclui subpastas e prefixa cada linha com o caminho.

    Raises:
        APIError: Falha na API (ex.: 403 se a identity não tem acesso ao projeto).
    """
    resp = client.secrets.list_secrets(
        project_id=project_id, environment_slug=environment_slug,
        secret_path=secret_path, recursive=recursive)
    print(f"\nSecrets em {environment_slug}:{secret_path} ({len(resp.secrets)})")
    if not resp.secrets:
        print("  <nenhum secret>")
        return
    width = max(len(s.secretKey) for s in resp.secrets)
    for s in sorted(resp.secrets, key=lambda s: (s.secretPath or "", s.secretKey)):
        path = f"{s.secretPath} " if recursive and s.secretPath else ""
        comment = f"  # {s.secretComment}" if s.secretComment else ""
        print(f"  {path}{s.secretKey.ljust(width)} = {s.secretValue}  (v{s.version}){comment}")


def require_env(name: str) -> str:
    """Lê uma variável de ambiente obrigatória.

    Encerra o programa com mensagem de erro (exit code 1) se ela estiver
    ausente ou vazia.
    """
    value = os.getenv(name)
    if not value:
        sys.exit(f"[ERRO] Variável de ambiente obrigatória ausente: {name}")
    return value


class Runner:
    """Executa as etapas do teste e acumula o resultado de cada uma.

    Cada etapa é uma função sem argumentos. Exceções do SDK
    (``APIError``/``InfisicalError``) são capturadas e registradas como falha;
    qualquer outra exceção é propagada, pois indica bug no script.
    """

    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def step(self, name, fn):
        """Executa ``fn``, imprime ``[OK]``/``[FALHA]`` com o tempo gasto.

        Args:
            name: Descrição da etapa exibida no terminal.
            fn: Função sem argumentos; o texto retornado vira o detalhe da linha.

        Returns:
            True se a etapa passou, False caso contrário.
        """
        start = time.perf_counter()
        try:
            detail = fn() or ""
            ok = True
        except APIError as e:
            detail = f"APIError {e.status_code}: {e}"
            ok = False
        except InfisicalError as e:
            detail = f"InfisicalError: {e}"
            ok = False
        elapsed = (time.perf_counter() - start) * 1000
        print(f"[{'OK ' if ok else 'FALHA'}] {name} ({elapsed:.0f} ms) {detail}")
        self.results.append((name, ok, detail))
        return ok

    def summary(self) -> int:
        """Imprime o resumo e retorna o exit code: 0 se tudo passou, 1 se não."""
        failed = [r for r in self.results if not r[1]]
        print(f"\nResumo: {len(self.results) - len(failed)}/{len(self.results)} etapas OK")
        return 1 if failed else 0


def main() -> int:
    """Lê a configuração do ``.env``, autentica e executa as etapas pedidas.

    Returns:
        Exit code do processo (0 = todas as etapas OK).
    """
    parser = argparse.ArgumentParser(description="Teste de credenciais Infisical")
    parser.add_argument("--write", action="store_true", help="testa criar/atualizar/excluir secret")
    parser.add_argument("--show", action="store_true", help="exibe valores dos secrets sem máscara")
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="apenas faz login e imprime todos os secrets com valores")
    args = parser.parse_args()

    load_dotenv()
    host = os.getenv("INFISICAL_HOST", "https://app.infisical.com")
    client_id = require_env("INFISICAL_CLIENT_ID")
    client_secret = require_env("INFISICAL_CLIENT_SECRET")
    project_id = require_env("INFISICAL_PROJECT_ID")
    env_slug = os.getenv("INFISICAL_ENV", "dev")
    secret_path = os.getenv("INFISICAL_SECRET_PATH", "/")
    test_secret = os.getenv("INFISICAL_TEST_SECRET_NAME")

    print(f"Host: {host} | Projeto: {project_id} | Env: {env_slug} | Path: {secret_path}\n")

    runner = Runner()
    # cache_ttl=None: evita que leituras após escrita venham do cache
    with InfisicalSDKClient(host=host, cache_ttl=None) as client:

        def login():
            resp = client.auth.universal_auth.login(client_id=client_id, client_secret=client_secret)
            return f"token {resp.tokenType}, expira em {resp.expiresIn}s"

        if not runner.step("Login Universal Auth", login):
            return runner.summary()

        if args.print_only:
            runner.step("Imprimir secrets",
                        lambda: print_secrets(client, project_id, env_slug, secret_path))
            return runner.summary()

        common = dict(project_id=project_id, environment_slug=env_slug, secret_path=secret_path)

        def list_secrets():
            resp = client.secrets.list_secrets(**common)
            for s in resp.secrets:
                print(f"        - {s.secretKey} = {mask(s.secretValue, args.show)}")
            return f"{len(resp.secrets)} secret(s), {len(resp.imports)} import(s)"

        runner.step("Listar secrets", list_secrets)

        if test_secret:
            def get_secret():
                s = client.secrets.get_secret_by_name(secret_name=test_secret, **common)
                return f"{s.secretKey} v{s.version} = {mask(s.secretValue, args.show)}"

            runner.step(f"Ler secret '{test_secret}'", get_secret)

        if args.write:
            name = f"SDK_TEST_{uuid.uuid4().hex[:8].upper()}"
            value = uuid.uuid4().hex

            def create():
                s = client.secrets.create_secret_by_name(
                    secret_name=name, secret_value=value,
                    secret_comment="criado por test_credentials.py", **common)
                return f"{s.secretKey} v{s.version}"

            def read_back():
                s = client.secrets.get_secret_by_name(secret_name=name, **common)
                if s.secretValue != value:
                    raise InfisicalError("valor lido difere do valor gravado")
                return "valor confere"

            def update():
                s = client.secrets.update_secret_by_name(
                    current_secret_name=name, secret_value=value + "_v2", **common)
                return f"v{s.version}"

            def delete():
                client.secrets.delete_secret_by_name(secret_name=name, **common)
                return f"{name} removido"

            if runner.step(f"Criar secret '{name}'", create):
                runner.step("Ler secret criado", read_back)
                runner.step("Atualizar secret", update)
                # sempre tenta limpar o secret criado
                runner.step("Excluir secret", delete)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
