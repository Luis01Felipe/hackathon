# Visão geral

> Hackathon Open BIM + IA · Sinaenco · 22–23/11/2026. Nome do produto provisório.

O EditalCheck transforma as exigências de um edital, escritas em linguagem natural, num **contrato de dados** operacional: os **requisitos de informação (IR)** e o **IDS**. Depois, verifica o modelo IFC contra esse contrato e o edital contra boas práticas. O objetivo é chegar a um **consenso** entre contratante e contratado antes que o problema chegue à obra.

Entradas: **edital em PDF**, **modelo IFC** (opcional) e **lições aprendidas** em TXT ou PDF (opcional, ciclo PDCA).

1. **O IFC cumpre o edital?** O sistema extrai os IR do edital e das lições aprendidas. Uma pessoa revisa e aprova. O sistema gera o **IDS** por código, para o contrato inteiro ou para um marco de entrega, e valida o IFC.
2. **O edital está bom?** O sistema aponta termos vagos, requisitos não verificáveis, itens mínimos ausentes, contradições, texto repetido e lições aprendidas que o edital não explicita.
3. **O edital cobre o modelo?** O sistema mede quanto do modelo o edital especifica e sugere requisitos com Psets oficiais para as lacunas.

Cada apontamento diz **onde está o problema** (no **edital**, o contratante corrige; no **modelo**, o contratado corrige), **o que** está errado, **onde** (página e/ou GlobalId com coordenada XYZ), **como agir** e **por que**. Cada parte registra a decisão (aceito, rejeitado, em discussão, dispensado). Os apontamentos do modelo aparecem num **visualizador 3D** e num **BCF**. Os do edital saem num **edital anotado em PDF** e numa **matriz de esclarecimentos**.

**Revisão dos IR (Information Requirements).** Cada requisito mostra o tópico de origem, os ambientes a que se aplica, o item de checagem (disciplina) e o tipo de verificação (IDS, IDS + script, script geométrico ou manual). A planilha exportada segue o template de IR do time: Resumo, Requisitos, Matriz ambiente × item, Categorias, Itens de checagem, e Aceitação e qualidade. Todas as páginas têm busca (sem diferenciar acento e caixa) e filtros.

**Edital na tela (só leitura).** O edital em PDF aparece em dois momentos:

- **Antes de gerar os IR:** o PDF mostra os tópicos selecionados grifados e, tracejados, os relevantes para BIM que ficaram de fora. Dá para marcar ou desmarcar ali mesmo e voltar.
- **Nos resultados (aba "Edital com os ajustes"):** o PDF fica à esquerda, com um grifo por apontamento, e os ajustes à direita. Clicar num ajuste leva ao trecho e abre o detalhe; clicar num grifo abre o ajuste. O relatório HTML tem um link "Ver no edital" em cada apontamento.

O **PDF com as sugestões** traz o mesmo conteúdo para uso sem o sistema: sumário com links para cada trecho, grifos com notas, etiquetas na margem que voltam ao sumário, links para buildingSMART e bSDD e um índice lateral (bookmarks) separado em "Corrigir no edital" e "Corrigir no modelo".

> Sem IFC, o sistema revisa só o edital. Esse é o uso do contratante antes de publicar a licitação.

**Tese:** a IA interpreta o texto. Tudo o que precisa ser exato (IDS, validação, BCF, métricas) é código determinístico sobre padrões abertos. Toda citação da IA é conferida literalmente contra o texto do PDF.

## Padrões Open BIM usados

| Padrão / serviço | Uso |
|---|---|
| **IFC** (IFC2X3, IFC4, IFC4X3) | Entrada do modelo, classes, Psets, GlobalIds e saúde do modelo |
| **IDS 1.0** | Contrato de dados gerado dos requisitos de informação (IR) aprovados, com `purpose` e `milestone`, validado contra o XSD oficial e usado na verificação |
| **BCF 2.1** | Um tópico por apontamento do modelo, com um viewpoint por elemento (seleção, destaque em vermelho e câmera enquadrando o elemento), uma visão geral e um comentário ligado a cada viewpoint |
| **bSDD** | URIs de propriedades e busca de termos (API REST pública) |
| **Psets oficiais** | Vocabulário controlado dos requisitos e das sugestões de lacuna |
| **IDM** (ISO 29481-1:2025) | Mapa de processo: atores, marcos de entrega e trocas de informação ([docs/idm.md](idm.md)) |
| **ISO 19650** | Inspiração da checklist do edital e dos termos de requisitos de informação |

## Trabalhos relacionados

Pesquisas recentes sobre IA e IDS (preprints de 2026; confira a versão publicada antes de citar):

- Ishigaki-IDS-Bench, arXiv:2605.22079 — benchmark de geração de IDS 1.0 por LLMs a partir de documentos práticos. Conclui que os modelos ainda erram o XML e o vocabulário IFC com frequência. <https://arxiv.org/abs/2605.22079>
- Ishigaki-IDS, arXiv:2606.08545 — modelo aberto para rascunhar IDS, treinado com recompensas de um verificador de IDS. <https://arxiv.org/abs/2606.08545>
- Hosseini et al., *Natural-language-to-IFC mapping for IDS authoring* (capítulo, Taylor & Francis) — fluxo em etapas com termos IFC sugeridos e confirmação de especialista. Aponta que IDS estruturalmente válidos podem representar mal o requisito. <https://www.taylorfrancis.com/chapters/oa-edit/10.1201/9781042025374-23/natural-language-ifc-mapping-ids-authoring-hosseini-gourabpasi-jalaei-khodabakhshi>

O EditalCheck segue a mesma conclusão: o LLM não escreve XML; o IDS é gerado por código a partir de requisitos aprovados por uma pessoa.

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
