"""CLI do EditalCheck (Typer): roda o pipeline sem interface, para testes e demo."""

import json
import time
from pathlib import Path
from typing import Annotated

import typer

from editalcheck.application.errors import EditalCheckError
from editalcheck.bootstrap import Container, configurar_logs, construir
from editalcheck.config import RAIZ_REPO, carregar
from editalcheck.domain.models import Projeto, Relatorio
from editalcheck.entrypoints.api import dto
from editalcheck.evaluation import Metricas, avaliar, carregar_gabarito

app = typer.Typer(
    help="EditalCheck — verificador bidirecional Edital × IFC.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
PASTA_DEMO = RAIZ_REPO / "data" / "demo"


def _container(verbose: bool) -> Container:
    settings = carregar()
    configurar_logs("INFO" if verbose else "WARNING")
    return construir(settings)


def _percentual(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.1f}%".replace(".", ",")


def _selecionar(projeto: Projeto, numeros: list[str] | None) -> list[str]:
    if numeros:
        return [t.id for t in projeto.topicos if t.numero in numeros]
    return [t.id for t in projeto.topicos if t.relevante_bim]


def _imprimir_relatorio(relatorio: Relatorio) -> None:
    i = relatorio.indicadores
    typer.secho("\nIndicadores", bold=True)
    typer.echo(
        f"  Conformidade do modelo: {_percentual(i.conformidade_percentual)} "
        f"({i.especificacoes_aprovadas}/{i.especificacoes_total} especificações IDS)"
    )
    typer.echo(
        f"  Cobertura do edital:    {_percentual(i.cobertura_percentual)} "
        f"({i.classes_cobertas}/{i.classes_especificaveis} classes)"
    )
    typer.echo(
        f"  Checklist do edital:    {i.checklist_presentes}/{i.checklist_total} presentes, "
        f"{i.checklist_parciais} parciais"
    )
    typer.echo(
        f"  Elementos não conformes: {i.elementos_nao_conformes} de {i.elementos_verificados}"
    )
    typer.echo(
        f"  Apontamentos: {len(relatorio.apontamentos)} {dict(i.apontamentos_por_severidade)}"
    )
    typer.echo(
        f"  Por origem: edital {i.apontamentos_por_origem.get('edital', 0)} · "
        f"modelo {i.apontamentos_por_origem.get('modelo', 0)} · "
        f"verificação manual {i.verificacao_manual}"
    )
    if i.licoes_total:
        typer.echo(
            f"  Lições aprendidas ausentes do edital: {i.licoes_nao_explicitas}/{i.licoes_total}"
        )
    if relatorio.custo:
        typer.echo(
            f"  Consumo de IA: {relatorio.custo.tokens_entrada} tokens de entrada, "
            f"{relatorio.custo.tokens_saida} de saída"
        )
    typer.secho("\nApontamentos", bold=True)
    for a in relatorio.apontamentos:
        typer.echo(
            f"  {a.id} [{a.severidade.value:5}] {a.origem.value.upper():6} {a.tipo.value:19} {a.titulo}"
        )
    for aviso in relatorio.avisos:
        typer.secho(f"  aviso: {aviso}", fg="yellow")


def _imprimir_metricas(m: Metricas) -> None:
    typer.secho("\nMétricas contra o gabarito (seção 14.3)", bold=True)
    typer.echo(
        f"  Recall de extração:    {_percentual(m.recall)} ({m.requisitos_encontrados}/{m.requisitos_gabarito})"
    )
    typer.echo(
        f"  Precisão de extração:  {_percentual(m.precisao)} ({m.requisitos_corretos}/{m.requisitos_extraidos})"
    )
    typer.echo(
        f"  Citações conferidas:   {_percentual(m.citacoes_percentual)} ({m.citacoes_conferidas}/{m.citacoes_geradas})"
    )
    typer.echo(f"  IDS válido (S6):       {'sim' if m.ids_valido else 'não'}")
    typer.echo(
        f"  Acerto da checklist:   {_percentual(m.checklist_percentual)} ({m.checklist_acertos}/{m.checklist_total})"
    )
    typer.echo(
        f"  Precisão ambiguidade:  {_percentual(m.ambiguidade_precisao)} ({m.ambiguidades_corretas}/{m.ambiguidades_apontadas})"
    )
    typer.echo(
        f"  Recall ambiguidade:    {_percentual(m.ambiguidade_recall)} ({m.trechos_vagos_encontrados}/{m.trechos_vagos_gabarito})"
    )
    if m.tempo_pipeline_s is not None:
        typer.echo(f"  Tempo do pipeline:     {m.tempo_pipeline_s:.1f} s")
    for item in m.nao_encontrados:
        typer.secho(f"  não encontrado: {item}", fg="yellow")
    for item in m.extras:
        typer.secho(f"  extra: {item}", fg="yellow")
    for item in m.checklist_divergencias:
        typer.secho(f"  checklist: {item}", fg="yellow")


@app.command()
def topicos(edital: Annotated[Path, typer.Argument(exists=True, help="Edital em PDF")]) -> None:
    """Lista os tópicos do edital, com páginas e relevância para BIM."""
    from editalcheck.adapters.pdf.pymupdf_reader import PyMuPdfEditalReader
    from editalcheck.domain.topics import segmentar

    for t in segmentar(PyMuPdfEditalReader().read(edital.read_bytes(), edital.name)):
        selo = "BIM" if t.relevante_bim else "   "
        typer.echo(f"{t.id} {selo} p.{t.pagina_inicio}-{t.pagina_fim}  {t.numero} {t.titulo}")


@app.command()
def modelo(ifc: Annotated[Path, typer.Argument(exists=True, help="Modelo IFC")]) -> None:
    """Mostra o schema, as classes e a saúde do modelo IFC."""
    from editalcheck.adapters.ifc.ifcopenshell_model import IfcOpenShellModelReader

    resumo = IfcOpenShellModelReader().load(ifc.read_bytes(), ifc.name)
    typer.echo(f"Schema: {resumo.schema} · {resumo.total_elementos} elementos")
    for c in resumo.classes:
        typer.echo(
            f"  {c.nome:32} {c.contagem:5} {'especificável' if c.especificavel else 'proxy'}"
        )
    s = resumo.saude
    typer.echo(
        f"Proxies: {s.proxies} · sem pavimento: {len(s.sem_pavimento)} · "
        f"GUIDs duplicados: {len(s.guids_duplicados)} · IfcSpace: {s.espacos}"
    )


@app.command()
def pipeline(
    edital: Annotated[Path, typer.Option(exists=True, help="Edital em PDF")],
    modelo_ifc: Annotated[Path, typer.Option("--modelo", exists=True, help="Modelo IFC")],
    topicos_numeros: Annotated[
        str | None,
        typer.Option(
            "--topicos", help="Números dos tópicos, ex.: 5.1,5.2 (padrão: relevantes BIM)"
        ),
    ] = None,
    saida: Annotated[Path, typer.Option(help="Pasta de saída")] = Path("saida"),
    gabarito: Annotated[
        Path | None, typer.Option(help="gabarito.json para medir as métricas")
    ] = None,
    licoes: Annotated[
        list[Path] | None,
        typer.Option(exists=True, help="Documento de lições aprendidas (.txt ou .pdf)"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Edital + IFC (+ lições) → IR (aprovação automática) → IDS → verificação → relatório e BCF."""
    c = _container(verbose)
    gab = carregar_gabarito(gabarito) if gabarito else None
    numeros = topicos_numeros.split(",") if topicos_numeros else (gab or {}).get("topicos_demo")
    inicio = time.perf_counter()
    try:
        projeto = c.importar.executar(
            edital.read_bytes(),
            edital.name,
            modelo_ifc.read_bytes(),
            modelo_ifc.name,
            [(arquivo.read_bytes(), arquivo.name) for arquivo in licoes or []],
        )
        typer.echo(
            f"Projeto {projeto.id}: {len(projeto.edital.paginas)} páginas, "
            f"{len(projeto.topicos)} tópicos, schema {projeto.modelo.schema}, "
            f"{len(projeto.licoes)} lições aprendidas, modo IA: {c.settings.modo_ia}"
        )
        selecionados = _selecionar(projeto, numeros)
        resultado_eir = c.gerar_eir.executar(projeto.id, selecionados)
        typer.echo(
            f"IR: {len(resultado_eir.eir.requisitos)} requisitos ({resultado_eir.descartados} descartados por S2)"
        )
        for aviso in resultado_eir.avisos:
            typer.secho(f"  aviso: {aviso}", fg="yellow")
        c.revisar_eir.aprovar_todos(projeto.id, somente_verificaveis=True)
        resultado_ids = c.gerar_ids.executar(projeto.id)
        typer.echo(
            f"IDS: {resultado_ids.especificacoes} especificações, válido: {resultado_ids.valido}"
        )
        for erro in resultado_ids.erros:
            typer.secho(f"  erro: {erro}", fg="red")
        verificacao = c.verificar.iniciar(projeto.id)
        verificacao = c.verificar.executar(verificacao.id)
    except EditalCheckError as erro:
        typer.secho(f"Erro: {erro}", fg="red")
        raise typer.Exit(1) from erro
    duracao = time.perf_counter() - inicio
    relatorio = c.repositorio.get_relatorio(verificacao.id)
    if relatorio is None:
        typer.secho(f"Verificação falhou: {verificacao.erro}", fg="red")
        raise typer.Exit(1)

    saida.mkdir(parents=True, exist_ok=True)
    (saida / "relatorio.json").write_text(
        json.dumps(dto.relatorio(relatorio, projeto.modelo), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for nome in ("relatorio.html", "resultado.bcf"):
        conteudo = c.repositorio.read_relatorio_file(verificacao.id, nome)
        if conteudo:
            (saida / nome).write_bytes(conteudo)
    ids_xml = c.repositorio.read_file(projeto.id, "ids.xml")
    if ids_xml:
        (saida / "editalcheck.ids").write_bytes(ids_xml)
    projeto = c.repositorio.get(projeto.id)
    if projeto and projeto.eir:
        (saida / "requisitos-informacao.xlsx").write_bytes(
            c.exportador_eir.to_xlsx(projeto.eir, projeto)
        )
    (saida / "edital-anotado.pdf").write_bytes(c.exportar_edital.anotado(verificacao.id))
    (saida / "esclarecimentos.xlsx").write_bytes(c.exportar_edital.matriz(verificacao.id))

    _imprimir_relatorio(relatorio)
    typer.echo(f"\nTempo total: {duracao:.1f} s · arquivos em {saida.resolve()}")
    if gab and projeto and projeto.eir:
        _imprimir_metricas(
            avaliar(
                gab,
                projeto.eir.requisitos,
                resultado_eir.descartados,
                relatorio,
                resultado_ids.valido,
                duracao,
            )
        )


@app.command()
def demo(
    saida: Annotated[Path, typer.Option(help="Pasta de saída")] = Path("saida-demo"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Roda o pipeline com os dados de data/demo e mede as métricas do gabarito."""
    licoes = PASTA_DEMO / "licoes_aprendidas.txt"
    pipeline(
        edital=PASTA_DEMO / "edital.pdf",
        modelo_ifc=PASTA_DEMO / "modelo.ifc",
        topicos_numeros=None,
        saida=saida,
        gabarito=PASTA_DEMO / "gabarito.json",
        licoes=[licoes] if licoes.exists() else None,
        verbose=verbose,
    )


@app.command("gerar-demo")
def gerar_demo() -> None:
    """Regera o edital PDF e o IFC sintéticos de data/demo."""
    from editalcheck.demo import gerar_edital, gerar_ifc

    typer.echo(f"Edital: {gerar_edital.gerar(PASTA_DEMO / 'edital.pdf')}")
    typer.echo(f"Modelo: {gerar_ifc.gerar(PASTA_DEMO / 'modelo.ifc')}")


@app.command()
def servidor(
    host: Annotated[str, typer.Option(help="Endereço")] = "127.0.0.1",
    porta: Annotated[int, typer.Option(help="Porta")] = 8000,
) -> None:
    """Sobe a API e o frontend em http://host:porta.

    Atrás de um proxy que remove um prefixo (ex.: Traefik em /editalcheck), defina
    EDITALCHECK_ROOT_PATH=/editalcheck para o /docs achar o /openapi.json.
    """
    import uvicorn

    uvicorn.run(
        "editalcheck.entrypoints.api.main:criar_app",
        factory=True,
        host=host,
        port=porta,
        root_path=carregar().caminho_raiz,
    )


if __name__ == "__main__":
    app()
