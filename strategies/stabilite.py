"""Stratégie stabilité : l'espion est celui dont les valeurs bougent le plus.

Une vraie température ne change presque pas en 25 s, alors que l'espion
réinvente sa valeur à chaque tour. On ignore volontairement l'écart entre
villes : une ville simplement plus chaude que ses voisines n'est pas suspecte.
C'est ce qui piège la médiane par temps froid (10 % de 7 °C = 0,7 °C, moins
que l'écart normal entre deux villes).

Limite : un espion qui garderait un décalage constant ne serait pas détecté.
"""
from statistics import pstdev

from strategies.base import autres
from strategies.mediane import scores


def choisir_suspect(mon_id, historique):
    candidats = autres(mon_id, historique)
    if not candidats:
        raise ValueError("historique vide")
    ecarts = scores(historique)   # départage si deux capteurs sont aussi stables
    return max(candidats, key=lambda i: (pstdev(candidats[i]), ecarts.get(i, 0)))
