"""Stratégies de vote : chaque module expose choisir_suspect(mon_id, historique) -> str."""
import importlib

NOMS = ("mediane", "stabilite", "aleatoire", "llm")


def charger(nom):
    """Importe la stratégie à la demande (llm n'est chargé que si on l'utilise)."""
    if nom not in NOMS:
        raise ValueError(f"stratégie inconnue : {nom} (attendu : {', '.join(NOMS)})")
    return importlib.import_module(f"strategies.{nom}")