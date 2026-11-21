from app.retrieval.query import split_compound_question
from app.retrieval.hybrid import build_tsquery


def test_tsquery_or_semantics_accents_and_stopwords():
    q = build_tsquery("Quelle est la durée du contrat ?")
    assert q == "duree:* | contrat:*"
    assert build_tsquery("le la les ?") is None
    assert build_tsquery("ventes 2026") == "ventes:* | 2026"


def test_tsquery_cannot_inject_sql_or_operators():
    q = build_tsquery("x'); DROP TABLE chunks; -- & ! |")
    assert q is not None and all(ch.isalnum() or ch in " |:*" for ch in q)


def test_split_compound_questions():
    assert split_compound_question("Quel est le total des ventes et quelle est la durée du contrat ?") == [
        "Quel est le total des ventes ?", "quelle est la durée du contrat ?"]
    assert split_compound_question("Le MFA est-il obligatoire ? Quelle est la longueur minimale du mot de passe ?") == [
        "Le MFA est-il obligatoire ?", "Quelle est la longueur minimale du mot de passe ?"]
    assert split_compound_question("Qui est la directrice générale ?") == ["Qui est la directrice générale ?"]
    # "et" inside a noun phrase is not a split point
    assert len(split_compound_question("Quels sont les droits et obligations du client ?")) == 1
