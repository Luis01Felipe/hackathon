"""BCF gerado: um viewpoint por elemento de cada apontamento, relido pelo bcf-client."""

import zipfile
from pathlib import Path

from bcf.v2.bcfxml import BcfXml

from editalcheck.bootstrap import Container
from editalcheck.domain.models import TipoApontamento


def test_bcf_tem_um_viewpoint_por_elemento(
    container: Container, arquivos_demo, tmp_path: Path
) -> None:
    edital, modelo = arquivos_demo
    projeto = container.importar.executar(edital, "edital.pdf", modelo, "modelo.ifc")
    topicos = [t.id for t in projeto.topicos if t.numero in ("5.1", "5.3", "5.5")]
    container.gerar_eir.executar(projeto.id, topicos)
    container.revisar_eir.aprovar_todos(projeto.id)
    verificacao = container.verificar.executar(container.verificar.iniciar(projeto.id).id)
    relatorio = container.repositorio.get_relatorio(verificacao.id)
    conteudo = container.repositorio.read_relatorio_file(verificacao.id, "resultado.bcf")
    assert relatorio is not None and conteudo is not None
    caminho = tmp_path / "resultado.bcf"
    caminho.write_bytes(conteudo)

    esperados = {
        a.id: a
        for a in relatorio.apontamentos
        if a.tipo
        in (
            TipoApontamento.NAO_CONFORMIDADE,
            TipoApontamento.QUALIDADE_MODELO,
            TipoApontamento.LICAO_NAO_EXPLICITA,
        )
        and a.elementos
    }
    nomes = zipfile.ZipFile(caminho).namelist()

    with BcfXml.load(Path(caminho)) as bcf:
        assert len(bcf.topics) == len(esperados)
        for topico in bcf.topics.values():
            apontamento = esperados[topico.topic.title.split(" · ")[0]]
            elementos = list(dict.fromkeys(apontamento.elementos))
            visoes = topico.markup.viewpoints
            geral = 1 if len(elementos) > 1 else 0
            assert len(visoes) == len(elementos) + geral, apontamento.id
            assert visoes[0].viewpoint == "viewpoint.bcfv"
            assert [v.index for v in visoes] == list(range(len(visoes)))
            assert f"{topico.guid}/viewpoint.bcfv" in nomes

            selecionados = []
            for entrada in visoes:
                info = topico.viewpoints[entrada.viewpoint].visualization_info
                guids = [c.ifc_guid for c in info.components.selection.component]
                assert info.perspective_camera is not None
                assert info.components.coloring.color[0].color == "FF0000"
                if len(guids) == 1:
                    selecionados.append(guids[0])
            assert selecionados == elementos, apontamento.id

            vinculados = {c.viewpoint.guid for c in topico.markup.comment if c.viewpoint}
            assert vinculados == {v.guid for v in visoes}
            assert topico.topic.priority in ("Alta", "Média")
