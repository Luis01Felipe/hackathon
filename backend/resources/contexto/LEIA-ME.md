# Documentos de referência (contexto do LLM)

Coloque aqui documentos de referência **autorizados**, em `.txt`, `.md` ou `.pdf`.
Exemplo: o documento de requisitos de informação cedido pela banca do hackathon,
com autorização de uso.

Como o sistema usa estes arquivos:

- Na extração dos requisitos de informação (IR), o sistema escolhe só os
  parágrafos mais parecidos com o tópico do edital, até cerca de 6.000 caracteres
  por chamada. Assim o contexto ajuda sem inflar o prompt.
- O texto vai ao LLM entre delimitadores, como **dado**. O LLM recebe a ordem de
  não seguir instruções escritas nele.
- Requisitos e evidências vêm sempre do edital. Um documento de referência nunca
  vira evidência nem remove apontamentos.
- O relatório lista os documentos de referência usados.

Regras:

- Não coloque aqui texto de norma ISO, CEN ou ABNT sem licença (RNF-17).
- Não coloque dados de clientes.
- O Git ignora os documentos desta pasta (só este `LEIA-ME.md` é versionado): um
  documento licenciado não vai para o repositório por engano.
- No servidor, copie os documentos para esta pasta antes do `docker compose build`.
  Eles entram na imagem junto com os demais recursos.
- Este arquivo (`LEIA-ME.md`) é ignorado pelo carregador.
