"""Contrat commun : toutes les strategies exposent choisir_suspect()."""


def choisir_suspect(mon_id: str, historique: dict[str, list[float]]) -> str:
    """historique = {id: [valeurs recues dans l'ordre des rounds]}, MOI INCLUS."""
    raise NotImplementedError


def autres(mon_id, historique):
    """Capteurs autres que moi, avec au moins une valeur."""
    return {i: v for i, v in historique.items() if i != mon_id and v}


def aligner(historique):
    """Tronque toutes les listes a la meme longueur (messages perdus / en retard)."""
    h = {i: v for i, v in historique.items() if v}
    n = min(len(v) for v in h.values())
    return {i: v[-n:] for i, v in h.items()}
