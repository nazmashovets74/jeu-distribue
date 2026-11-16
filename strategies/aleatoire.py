"""Stratégie de référence : vote au hasard parmi les autres capteurs."""
import random

from strategies.base import autres


def choisir_suspect(mon_id, historique):
    candidats = list(autres(mon_id, historique))
    if not candidats:
        raise ValueError("historique vide")
    return random.choice(candidats)
