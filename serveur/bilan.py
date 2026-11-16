"""Bilan des parties archivées par le serveur.

    python -m serveur.bilan                       # journal par défaut
    python -m serveur.bilan autre.jsonl --rejouer mediane,aleatoire

Pour chaque stratégie : part des votes des capteurs honnêtes qui désignent le
vrai espion. Les parties sont aussi rejouées hors ligne avec d'autres
stratégies sur exactement les mêmes mesures (par ex. LLM contre médiane).
"""
import argparse
import json
from collections import Counter, defaultdict

import strategies
from serveur.serveur import IDS, JOURNAL


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def votes_honnetes(partie):
    """[(votant, suspect)] des capteurs honnêtes qui ont voté dans cette partie."""
    return [(v, s) for v, s in partie["votes"].items() if v != partie["espion"]]


def main():
    parser = argparse.ArgumentParser(description="Bilan des parties archivées")
    parser.add_argument("journal", nargs="?", default=JOURNAL)
    parser.add_argument("--rejouer", default="mediane",
                        help="stratégies à rejouer sur les mêmes mesures ('' pour aucune)")
    args = parser.parse_args()

    try:
        parties = lire(args.journal)
    except FileNotFoundError:
        raise SystemExit(f"pas de journal : {args.journal} (lancez d'abord des parties)")
    gagnants = Counter(p["gagnant"] for p in parties)
    incompletes = sum(len(p["votes"]) < len(IDS) for p in parties)
    print(f"{len(parties)} parties : capteurs {gagnants['capteurs']}, espion "
          f"{gagnants['espion']} ({incompletes} avec des votes manquants)\n")

    # stats[nom] = [votes justes, votes] ; seuls les honnêtes comptent,
    # l'espion vote toujours contre un innocent.
    stats = defaultdict(lambda: [0, 0])
    for p in parties:
        for votant, suspect in votes_honnetes(p):
            nom = p.get("strategies", {}).get(votant, "?")
            stats[nom][0] += suspect == p["espion"]
            stats[nom][1] += 1

    for nom in filter(None, args.rejouer.split(",")):
        strategie = strategies.charger(nom)
        for p in parties:
            if not p.get("temperatures"):
                continue
            for votant, _ in votes_honnetes(p):
                try:
                    juste = strategie.choisir_suspect(votant, p["temperatures"]) == p["espion"]
                except Exception:
                    juste = False
                stats[f"{nom} (rejouée)"][0] += juste
                stats[f"{nom} (rejouée)"][1] += 1

    print(f"{'stratégie':<28} {'votes justes':>14}")
    for nom, (justes, total) in sorted(stats.items()):
        print(f"{nom:<28} {justes:>4}/{total:<4} {100 * justes / total:5.1f} %")


if __name__ == "__main__":
    main()
