from statistics import median, pstdev

from strategies.base import aligner, autres


def scores(historique):
    """Score de suspicion en degres C : ecart au consensus + instabilite."""
    h = aligner(historique)
    n = len(next(iter(h.values())))
    consensus = [median(v[r] for v in h.values()) for r in range(n)]
    return {
        i: sum(abs(v[r] - consensus[r]) for r in range(n)) / n + pstdev(v)
        for i, v in h.items()
    }


def choisir_suspect(mon_id, historique):
    s = scores(historique)
    candidats = {i: s[i] for i in autres(mon_id, historique)}
    if not candidats:
        raise ValueError("historique vide")
    return max(candidats, key=candidats.get)
