import uuid

import pytest

from app.db.models import DocTable
from app.rag.table_qa import TableRef, describe_tables, execute_sql, looks_computational, slug, validate_sql


def _ref(name="ventes", rows=None, cols=None):
    cols = cols or [{"name": "Produit", "dtype": "TEXT"}, {"name": "Quantité", "dtype": "INTEGER"}, {"name": "Montant", "dtype": "REAL"}]
    rows = rows or [["A", 2, 10.5], ["B", 3, 20.0], ["A", 5, 4.5], ["TOTAL", 10, 35.0]]
    dt = DocTable(name=name, sql_name=name, columns=cols, rows=rows, n_rows=len(rows), table_metadata={"sheet": "Ventes"})
    return TableRef(sql_name=name, doc_table=dt, filename="x.xlsx", document_id=uuid.uuid4())


def test_execute_real_aggregation():
    cols, rows = execute_sql("SELECT SUM(quantite) AS q FROM ventes WHERE produit <> 'TOTAL'", [_ref()])
    assert cols == ["q"] and rows == [[10]]
    cols, rows = execute_sql(
        "SELECT produit, SUM(montant) FROM ventes WHERE LOWER(produit) NOT LIKE 'total%' GROUP BY 1 ORDER BY 1", [_ref()])
    assert rows == [["A", 15.0], ["B", 20.0]]


@pytest.mark.parametrize("sql", [
    "DROP TABLE ventes",
    "SELECT 1; DROP TABLE ventes",
    "DELETE FROM ventes",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA table_info(ventes)",
    "WITH x AS (SELECT 1) INSERT INTO ventes VALUES (1,2,3)",
])
def test_rejects_non_select(sql):
    with pytest.raises(Exception):
        execute_sql(sql, [_ref()])


def test_validate_strips_trailing_semicolon():
    assert validate_sql("SELECT 1;") == "SELECT 1"


def test_runaway_query_is_aborted():
    with pytest.raises(Exception):
        execute_sql("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c", [_ref()])


def test_describe_warns_about_total_rows_and_maps_columns():
    d = describe_tables([_ref()])
    assert "lignes de total" in d
    assert "quantite INTEGER (« Quantité »)" in d


def test_sql_columns_are_unique_identifiers():
    from app.rag.table_qa import sql_columns
    cols = [{"name": "Total (TND)", "dtype": "INTEGER"}, {"name": "Total TND", "dtype": "INTEGER"}, {"name": "2024", "dtype": "REAL"}]
    assert sql_columns(_ref(cols=cols, rows=[[1, 2, 3]]).doc_table) == ["total_tnd", "total_tnd_2", "c_2024"]


def test_computational_heuristic():
    assert looks_computational("Quel est le total des ventes ?")
    assert looks_computational("Combien de tickets sont résolus ?")
    assert looks_computational("Quelle est la durée moyenne de résolution ?")
    assert not looks_computational("Qui est la directrice générale ?")


def test_slug():
    assert slug("10_metrics Ventes T3") == "t_10_metrics_ventes_t3"
    assert slug("Données clients") == "donnees_clients"


def test_unknown_quoted_identifier_is_rejected_not_silently_string():
    with pytest.raises(ValueError, match="Identifiant inconnu"):
        execute_sql('SELECT SUM("Quantité") FROM ventes', [_ref()])
    cols, rows = execute_sql('SELECT SUM("quantite") AS "total" FROM "ventes"', [_ref()])
    assert rows == [[20]]
