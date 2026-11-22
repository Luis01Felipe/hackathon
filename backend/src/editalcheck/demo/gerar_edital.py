"""Gera o edital PDF fictício da demo (texto selecionável, 5 páginas).

O texto é de autoria do time e não reproduz edital real. Ele mistura cláusulas
verificáveis, termos vagos, itens mínimos ausentes e uma contradição, para
exercitar as três análises. O gabarito está em data/demo/gabarito.json.
"""

from pathlib import Path

import pymupdf

CSS = """
* { font-family: sans-serif; }
body { font-size: 10.5pt; line-height: 1.45; color: #111; }
h1 { font-size: 13pt; text-align: center; margin: 0 0 4pt 0; }
h2 { font-size: 11pt; margin: 14pt 0 4pt 0; }
h3 { font-size: 10.5pt; margin: 10pt 0 3pt 0; }
p { margin: 0 0 6pt 0; text-align: justify; }
.centro { text-align: center; }
.aviso { text-align: center; font-size: 9pt; color: #a00; }
"""

PAGINAS: list[str] = [
    """
<h1>PREFEITURA MUNICIPAL DE VILA EXEMPLO</h1>
<p class="centro">SECRETARIA MUNICIPAL DE OBRAS E INFRAESTRUTURA</p>
<p class="centro"><b>EDITAL DE CONCORRÊNCIA Nº 001/2026</b></p>
<p class="aviso">Documento fictício, criado pelo time EditalCheck para demonstração no Hackathon Open BIM + IA.</p>
<p>Objeto: contratação de empresa especializada para elaborar o projeto executivo de arquitetura e engenharia da Escola Municipal de Ensino Fundamental Vila Exemplo, com uso da Modelagem da Informação da Construção (BIM).</p>
<h2>1 DO OBJETO</h2>
<p>1.1.1 O objeto desta concorrência é a elaboração do projeto executivo da Escola Municipal Vila Exemplo, edificação de 2 pavimentos com área construída aproximada de 1.120 m².</p>
<p>1.1.2 Os projetos deverão ser desenvolvidos em BIM, com entrega de modelo de informação e documentação técnica.</p>
<p>1.1.3 Os serviços deverão observar as melhores práticas de engenharia.</p>
<h2>2 DAS CONDIÇÕES DE PARTICIPAÇÃO</h2>
<p>2.1.1 Poderão participar empresas do ramo de projetos de engenharia e arquitetura, com registro ativo no conselho profissional competente.</p>
<p>2.1.2 A licitante deverá comprovar experiência anterior na elaboração de projetos de edificações escolares.</p>
""",
    """
<h2>3 DOS PRAZOS E DO PAGAMENTO</h2>
<p>3.1.1 O prazo de execução dos serviços será de 120 (cento e vinte) dias corridos, contados da ordem de serviço.</p>
<p>3.1.2 O pagamento será realizado em 3 (três) parcelas, após o aceite de cada etapa pela comissão de fiscalização.</p>
<h2>4 DA MODELAGEM DA INFORMAÇÃO (BIM)</h2>
<h3>4.1 Formato e entrega do modelo</h3>
<p>4.1.1 O modelo deverá ser entregue no formato aberto IFC 4 (ISO 16739-1:2018), acompanhado dos arquivos nativos.</p>
<p>4.1.2 As entregas do modelo deverão ocorrer em três marcos: estudo preliminar, em até 30 dias; anteprojeto, em até 60 dias; e projeto executivo, em até 120 dias.</p>
<p>4.1.3 Os arquivos deverão seguir convenção de nomenclatura adequada, a critério da fiscalização.</p>
<h3>4.2 Qualidade do modelo</h3>
<p>4.2.1 O modelo deverá ser desenvolvido com qualidade suficiente para cada fase do projeto.</p>
<p>4.2.2 Os elementos deverão ser modelados com as classes IFC corretas, sem uso de objetos genéricos quando houver classe específica.</p>
<h3>4.3 Colaboração</h3>
<p>4.3.1 A troca de arquivos entre as disciplinas ocorrerá por meio de plataforma de colaboração compatível, sempre que possível.</p>
""",
    """
<h2>5 DOS REQUISITOS DE INFORMAÇÃO DOS ELEMENTOS</h2>
<p>Esta seção define as informações que cada tipo de elemento do modelo deve conter, com base nos conjuntos de propriedades (Psets) oficiais da buildingSMART.</p>
<h3>5.1 Portas</h3>
<p>5.1.1 Todas as portas deverão conter a propriedade FireRating do Pset_DoorCommon, com a resistência ao fogo da porta.</p>
<p>5.1.2 Todas as portas deverão indicar se fazem parte de rota de fuga, na propriedade FireExit do Pset_DoorCommon.</p>
<p>5.1.3 As portas deverão informar se são externas ou internas (propriedade IsExternal).</p>
<h3>5.2 Paredes</h3>
<p>5.2.1 As paredes deverão informar se são externas ou internas por meio da propriedade IsExternal do Pset_WallCommon.</p>
<p>5.2.2 As paredes deverão ser executadas com materiais de boa qualidade, conforme normas vigentes.</p>
<h3>5.3 Janelas</h3>
<p>5.3.1 Todas as janelas deverão informar a transmitância térmica (ThermalTransmittance), em W/(m²·K).</p>
<p>5.3.2 As janelas deverão garantir iluminação natural adequada aos ambientes.</p>
""",
    """
<h3>5.4 Ambientes</h3>
<p>5.4.1 Cada ambiente deverá possuir o atributo LongName preenchido com a denominação do uso, por exemplo "Sala de aula 01".</p>
<p>5.4.2 Os ambientes deverão ser dimensionados de forma adequada ao número de alunos.</p>
<h3>5.5 Escadas</h3>
<p>5.5.1 As escadas deverão informar o número de degraus (NumberOfRiser) e a altura do espelho (RiserHeight), que deverá estar entre 0,16 m e 0,18 m.</p>
<h3>5.6 Segurança contra incêndio</h3>
<p>5.6.1 Os extintores deverão ser modelados quando necessário, a critério da fiscalização.</p>
<p>5.6.2 O projeto de prevenção e combate a incêndio deverá ser aprovado pelo Corpo de Bombeiros.</p>
<h2>6 DA VERIFICAÇÃO E DO ACEITE</h2>
<p>6.1.1 A fiscalização verificará o modelo segundo o padrão de mercado e emitirá o termo de aceite de cada etapa.</p>
<p>6.1.2 Os arquivos IFC deverão ser entregues também na versão IFC 2x3, para compatibilidade com o sistema da prefeitura.</p>
""",
    """
<h2>7 DAS RESPONSABILIDADES</h2>
<p>7.1.1 A contratada indicará um responsável técnico pelo modelo, com registro no conselho profissional competente.</p>
<p>7.1.2 A contratada deverá corrigir os apontamentos da fiscalização em até 10 (dez) dias.</p>
<p>7.1.3 A contratada deverá manter equipe técnica suficiente durante toda a execução.</p>
<h2>8 DAS DISPOSIÇÕES GERAIS</h2>
<p>8.1.1 Os casos omissos serão resolvidos pela comissão de licitação.</p>
<p>8.1.2 Fica eleito o foro da Comarca de Vila Exemplo para dirimir questões deste edital.</p>
<p class="centro">Vila Exemplo, 22 de novembro de 2026.</p>
<p class="centro">Comissão Permanente de Licitação</p>
""",
]

LARGURA_A4, ALTURA_A4 = pymupdf.paper_size("a4")
MARGEM = 56


def gerar(destino: Path) -> Path:
    documento = pymupdf.open()
    total = len(PAGINAS)
    for numero, html in enumerate(PAGINAS, start=1):
        pagina = documento.new_page(width=LARGURA_A4, height=ALTURA_A4)
        area = pymupdf.Rect(MARGEM, MARGEM, LARGURA_A4 - MARGEM, ALTURA_A4 - MARGEM - 20)
        sobra, escala = pagina.insert_htmlbox(area, html, css=CSS)
        if sobra < 0 or escala < 1:
            raise RuntimeError(f"O conteúdo da página {numero} não coube na folha.")
        rodape = pymupdf.Rect(
            MARGEM, ALTURA_A4 - MARGEM, LARGURA_A4 - MARGEM, ALTURA_A4 - MARGEM + 16
        )
        pagina.insert_htmlbox(
            rodape,
            f"<p style='font-size:8pt;text-align:center;color:#555'>Edital de Concorrência nº 001/2026 — documento fictício — página {numero} de {total}</p>",
            css=CSS,
        )
    documento.set_metadata(
        {"title": "Edital fictício de demonstração — EditalCheck", "author": "Time EditalCheck"}
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.save(str(destino))
    documento.close()
    return destino
