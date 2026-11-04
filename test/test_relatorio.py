import io
import sys
from datetime import datetime

import pytest

import painel
import relatorio
from test_painel import criar_marts


def _relogio(quando):
    """Substitui relatorio.datetime: só now() é usado pelo relatório."""
    class Relogio:
        @staticmethod
        def now():
            return quando
    return Relogio


def _preparar(tmp_path, monkeypatch, **kwargs):
    banco = tmp_path / "t.duckdb"
    criar_marts(banco, **kwargs)
    arquivo = tmp_path / "relatorio.html"
    monkeypatch.setattr(painel, "BANCO", banco)
    monkeypatch.setattr(relatorio, "ARQUIVO", arquivo)
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    monkeypatch.setattr(sys, "stdout", saida)
    return arquivo, saida


def _gerar(monkeypatch, quando):
    monkeypatch.setattr(relatorio, "datetime", _relogio(quando))
    relatorio.main()


def test_gera_o_arquivo_dentro_do_tmp_path(tmp_path, monkeypatch):
    arquivo, saida = _preparar(tmp_path, monkeypatch)
    _gerar(monkeypatch, datetime(2026, 10, 25, 14, 3))
    saida.flush()
    impresso = saida.buffer.getvalue().decode("utf-8")
    assert arquivo.is_file()
    assert impresso.startswith(str(arquivo))
    assert impresso.rstrip().endswith("KB")


def test_rodape_tem_data_e_hora_da_geracao(tmp_path, monkeypatch):
    arquivo, _ = _preparar(tmp_path, monkeypatch)
    _gerar(monkeypatch, datetime(2026, 10, 25, 14, 3))
    assert "<footer>Dados de 25/10/2026 14:03</footer>" in arquivo.read_text(encoding="utf-8")


def test_rodar_duas_vezes_muda_so_o_rodape(tmp_path, monkeypatch):
    arquivo, _ = _preparar(tmp_path, monkeypatch)
    _gerar(monkeypatch, datetime(2026, 10, 25, 14, 3))
    primeira = arquivo.read_text(encoding="utf-8").splitlines()
    _gerar(monkeypatch, datetime(2026, 10, 26, 9, 30))
    segunda = arquivo.read_text(encoding="utf-8").splitlines()
    diferentes = [(a, b) for a, b in zip(primeira, segunda) if a != b]
    assert len(primeira) == len(segunda)
    assert diferentes == [("<footer>Dados de 25/10/2026 14:03</footer>",
                           "<footer>Dados de 26/10/2026 09:30</footer>")]


def test_cartoes_tem_os_mesmos_valores_do_painel(tmp_path, monkeypatch):
    arquivo, _ = _preparar(tmp_path, monkeypatch)
    _gerar(monkeypatch, datetime(2026, 10, 25, 14, 3))
    html = arquivo.read_text(encoding="utf-8")
    for valor in ["R$ 150,25", "1,50%", "12,3%", "10,00%", "80,5%", "11,5", "4,25"]:
        assert f'<div class="valor">{valor}</div>' in html


def test_plotly_vem_do_cdn_uma_vez_e_cada_grafico_tem_id_fixo(tmp_path, monkeypatch):
    arquivo, _ = _preparar(tmp_path, monkeypatch)
    _gerar(monkeypatch, datetime(2026, 10, 25, 14, 3))
    html = arquivo.read_text(encoding="utf-8")
    assert html.count("cdn.plot.ly") == 1
    for i in range(1, 8):
        assert f'id="g{i:02d}"' in html


def test_titulo_do_faturamento_diz_o_periodo(tmp_path, monkeypatch):
    arquivo, _ = _preparar(tmp_path, monkeypatch)
    _gerar(monkeypatch, datetime(2026, 10, 25, 14, 3))
    # O plotly escreve "/" como / dentro do JSON da figura.
    assert "jan\\u002f2017 a ago\\u002f2018" in arquivo.read_text(encoding="utf-8")


def test_sem_mart_encerra_sem_gerar_arquivo(tmp_path, monkeypatch):
    arquivo, _ = _preparar(tmp_path, monkeypatch, sem=("kpis",))
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    with pytest.raises(SystemExit):
        relatorio.main()
    assert not arquivo.exists()
