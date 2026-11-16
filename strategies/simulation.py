"""Compare les stratégies hors réseau, sur des parties simulées.

Les parties suivent le vrai jeu : les capteurs honnêtes publient la vraie
température de leur ville (constante pendant une partie) et l'espion appelle
capteur.espion.fausse_temperature comme le vrai capteur. Toutes les
stratégies votent sur les MÊMES parties.

    python -m strategies.simulation                         # températures de VRAIES
    python -m strategies.simulation --reel                  # températures actuelles
    python -m strategies.simulation --temperatures 12 12.2 15 12.1
    python -m strategies.simulation --strategies mediane,llm -n 20
"""
import argparse
import random
import time

import strategies
from config import CAPTEURS, NB_TOURS
from capteur.espion import fausse_temperature

VRAIES = {"1": 11.8, "2": 12.3, "3": 11.5, "4": 11.7}   # exemple de relevé (id -> °C)


def generer_partie(vraies):
    """-> (espion, historique) d'une partie, comme la produiraient les capteurs."""
    ids = list(vraies)
    espion = random.choice(ids)
    honnetes = [i for i in ids if i != espion]
    historique = {i: [vraies[i]] * NB_TOURS for i in honnetes}
    # Comme dans capteur.py : au tour 1 l'espion n'a encore rien reçu et part de
    # sa propre vraie valeur, ensuite des dernières valeurs des autres.
    historique[espion] = [fausse_temperature([vraies[espion]])] + [
        fausse_temperature([vraies[i] for i in honnetes]) for _ in range(NB_TOURS - 1)]
    return espion, historique


def evaluer(strategie, parties):
    """-> (% votes justes des honnêtes, % parties gagnées par les capteurs, s par vote, erreurs)."""
    justes = gagnees = nb_votes = erreurs = 0
    debut = time.monotonic()
    for espion, historique in parties:
        bons = []
        for votant in historique:
            if votant == espion:
                continue
            try:
                bons.append(strategie.choisir_suspect(votant, historique) == espion)
            except Exception:
                erreurs += 1
                bons.append(False)
        justes += sum(bons)
        nb_votes += len(bons)
        # L'espion ne vote jamais contre lui-même : il faut les 2 honnêtes.
        gagnees += all(bons)
    duree = (time.monotonic() - debut) / nb_votes
    return 100 * justes / nb_votes, 100 * gagnees / len(parties), duree, erreurs


def main():
    parser = argparse.ArgumentParser(description="Comparaison des stratégies sur parties simulées")
    parser.add_argument("--strategies", default="mediane,aleatoire",
                        help=f"liste séparée par des virgules parmi {','.join(strategies.NOMS)}")
    parser.add_argument("-n", type=int, default=2000, help="nombre de parties (défaut : 2000)")
    parser.add_argument("--reel", action="store_true",
                        help="prendre les températures actuelles sur Open-Meteo")
    parser.add_argument("--temperatures", type=float, nargs=len(CAPTEURS),
                        metavar="T", help=f"températures des capteurs {', '.join(CAPTEURS)}")
    parser.add_argument("--graine", type=int, help="graine du hasard (parties reproductibles)")
    parser.add_argument("--ollama", help="adresse d'Ollama pour llm")
    parser.add_argument("--modele", help="modèle Ollama pour llm")
    args = parser.parse_args()

    if args.reel:
        from capteur.meteo import get_temperature
        vraies = {i: get_temperature(c["lat"], c["lon"]) for i, c in CAPTEURS.items()}
    elif args.temperatures:
        vraies = dict(zip(CAPTEURS, args.temperatures))
    else:
        vraies = VRAIES

    random.seed(args.graine)
    parties = [generer_partie(vraies) for _ in range(args.n)]

    print(f"Températures : {vraies} - {args.n} parties")
    print(f"{'stratégie':<12} {'votes justes':>13} {'parties gagnées':>16} {'s/vote':>8}")
    for nom in args.strategies.split(","):
        strategie = strategies.charger(nom)
        if nom == "llm":
            strategie.configurer(args.ollama, args.modele)
        justes, gagnees, duree, erreurs = evaluer(strategie, parties)
        print(f"{nom:<12} {justes:12.1f} % {gagnees:15.1f} % {duree:8.3f}"
              + (f"   ({erreurs} erreurs)" if erreurs else ""))


if __name__ == "__main__":
    main()
