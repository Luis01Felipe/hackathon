# Dados e segurança

## Tratamento de dados (LGPD)

- **Modo efêmero (padrão).** Edital, IFC, lições, IR, IDS, relatórios e BCF ficam só na memória do servidor. Nada é gravado em disco. Os dados somem quando o usuário clica em **Encerrar e apagar dados**, após 120 minutos sem uso (`EDITALCHECK_TTL_MIN`) ou quando o processo reinicia.
- **Sem cache do LLM em disco** no modo efêmero: as respostas trazem trechos do edital.
- **Log de auditoria sem conteúdo** (`var/auditoria/auditoria.jsonl`): data, etapa, ID aleatório do projeto, tamanhos e status. Nunca guarda texto de documento.
- **Aviso antes da IA.** A interface informa que trechos são enviados à API paga do Google Gemini, que não usa esses dados para treinar modelos.
- **Validação humana no meio do fluxo:** nenhum requisito vira IDS sem aprovação de uma pessoa.
- O modo `persistente` grava em `var/` e serve só para desenvolvimento.

**Modo offline:** sem chave do Gemini, ou se o LLM falhar, o sistema usa regras determinísticas (extrator por vocabulário, léxico de termos vagos, checklist por padrões). A demo nunca fica sem resposta (RNF-02).

## Segurança da aplicação

- **Erros sem vazamento.** Um erro interno mostra ao usuário uma mensagem com um código. O mesmo código vai no cabeçalho `X-Request-ID` e no log do servidor. O detalhe técnico fica só no log.
- **Cabeçalhos de segurança** em todas as respostas (`nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`). As páginas HTML trazem `Content-Security-Policy`.
- **Acesso por id.** Não há login. O acesso a um projeto depende do id dele, com 128 bits, inviável de adivinhar por tentativa. Autenticação e limite de requisições, se forem necessários, ficam a cargo do proxy reverso.
- **Entrada validada.** Os campos editáveis têm tipo e tamanho máximo. Padrões regex que poderiam travar a validação do IDS são recusados.
- **Uploads limitados** por arquivo (`LIMITE_UPLOAD_MB`), pela soma dos arquivos e pela quantidade de lições (até 10).
- **Concorrência.** Edições simultâneas no mesmo projeto não se perdem, e cada projeto roda uma verificação por vez.
- **Contêiner endurecido** em produção: veja [Deploy em produção](deploy.md#segurança-do-contêiner).

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
