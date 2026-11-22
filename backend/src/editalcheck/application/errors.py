"""Erros da aplicação, traduzidos para HTTP pelos entrypoints."""


class EditalCheckError(Exception):
    """Erro de negócio com mensagem em português para o usuário."""


class NaoEncontradoError(EditalCheckError):
    pass


class ConflitoError(EditalCheckError):
    pass


class EntradaInvalidaError(EditalCheckError):
    pass
