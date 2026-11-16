"""Stratégie LLM : un modèle local (Ollama) lit les mesures et désigne l'espion.

Comme le demande la consigne (2.2), chaque RPi exécute sa propre instance
Ollama : le capteur interroge toujours celle de sa machine.
"""
import json

import requests

from strategies.base import autres

URL = "http://localhost:11434"
MODELE = "qwen3:1.7b"
DELAI = 120     # s ; le premier appel charge le modèle en mémoire, c'est lent

derniere_raison = None   # explication donnée par le modèle au dernier vote


def configurer(url=None, modele=None):
    """Appelé par le capteur avec ses arguments de lancement."""
    global URL, MODELE
    URL = (url or URL).rstrip("/")
    MODELE = modele or MODELE


def construire_prompt(mon_id, historique, candidats):
    lignes = []
    for i in sorted(historique):
        valeurs = ", ".join(f"{t:.1f}" for t in historique[i])
        lignes.append(f"capteur {i}{' (toi)' if i == mon_id else ''} : {valeurs}")
    return (
        f"Jeu de l'espion entre {len(historique)} capteurs de température placés dans "
        "des villes voisines. Chaque capteur publie une mesure toutes les 5 secondes.\n"
        "- Un capteur honnête publie la vraie température de sa ville. Les villes sont "
        "proches, donc les températures se ressemblent sans être identiques, et une vraie "
        "température ne change presque pas en quelques secondes.\n"
        "- Un seul capteur est l'espion : il invente ses valeurs, à environ 10 % de "
        "celles des autres, pour passer inaperçu.\n\n"
        f"Tu es le capteur {mon_id}. Voici les mesures reçues (°C, dans l'ordre des tours) :\n"
        + "\n".join(lignes)
        + f"\n\nQuel capteur parmi {', '.join(candidats)} est l'espion ? "
        "Explique en une phrase courte, puis donne son numéro."
    )


def choisir_suspect(mon_id, historique):
    global derniere_raison
    candidats = sorted(autres(mon_id, historique))
    if not candidats:
        raise ValueError("historique vide")
    if len(candidats) == 1:
        return candidats[0]

    reponse = requests.post(f"{URL}/api/chat", timeout=DELAI, json={
        "model": MODELE,
        "messages": [{"role": "user",
                      "content": construire_prompt(mon_id, historique, candidats)}],
        "stream": False,
        "think": False,   # qwen3 « réfléchit » sinon pendant des centaines de tokens
        # Sortie structurée : Ollama force un JSON conforme, et l'enum interdit
        # au modèle de répondre autre chose qu'un des candidats.
        "format": {
            "type": "object",
            "properties": {
                "raison": {"type": "string"},
                "suspect": {"type": "string", "enum": candidats},
            },
            "required": ["raison", "suspect"],
        },
        # 3 threads sur 4 cœurs : llama.cpp attend son thread le plus lent, donc si
        # un seul cœur est pris par autre chose (broker, capteur...), 4 threads
        # rendent la génération des dizaines de fois plus lente (mesuré : 90 s -> 7 s).
        "options": {"temperature": 0, "num_predict": 200, "num_thread": 3},
    })
    reponse.raise_for_status()
    contenu = json.loads(reponse.json()["message"]["content"])
    suspect = str(contenu["suspect"])
    if suspect not in candidats:
        raise ValueError(f"réponse hors candidats : {contenu}")
    derniere_raison = contenu.get("raison")
    return suspect
