"""Comptes des joueurs du site (mots de passe hachés, fichier hors git).

    python -m web.comptes ajouter nazar --capteurs 1,4     (demande le mot de passe)
    python -m web.comptes supprimer nazar
    python -m web.comptes liste

Chaque compte est lié aux capteurs de sa Raspberry Pi : le bouton « Prêt »
n'est accepté que si ces capteurs sont lancés. Une partie démarre quand
TOUS les comptes sont prêts.
"""
import argparse
import getpass
import json
import os

from werkzeug.security import check_password_hash, generate_password_hash

from config import CAPTEURS

FICHIER = os.path.join(os.path.dirname(__file__), "comptes.json")


def lire(chemin=FICHIER):
    """{nom: {"hash": ..., "capteurs": ["1", "4"]}} ; {} si pas encore de fichier."""
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def ecrire(comptes, chemin=FICHIER):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(comptes, f, indent=2, ensure_ascii=False)
    os.chmod(chemin, 0o600)   # hachés, mais inutile de les laisser lisibles par tous


def verifier(comptes, nom, mot_de_passe):
    compte = comptes.get(nom)
    return compte is not None and check_password_hash(compte["hash"], mot_de_passe)


def main():
    parser = argparse.ArgumentParser(description="Comptes des joueurs du site")
    parser.add_argument("--fichier", default=FICHIER)
    sous = parser.add_subparsers(dest="action", required=True)
    p = sous.add_parser("ajouter", help="créer un compte ou changer son mot de passe")
    p.add_argument("nom")
    p.add_argument("--capteurs", required=True,
                   help=f"capteurs de sa Raspberry Pi, séparés par des virgules ({','.join(CAPTEURS)})")
    p.add_argument("--mot-de-passe", help="sinon demandé au clavier (conseillé)")
    sous.add_parser("supprimer").add_argument("nom")
    sous.add_parser("liste")
    args = parser.parse_args()

    comptes = lire(args.fichier)
    if args.action == "ajouter":
        capteurs = [c.strip() for c in args.capteurs.split(",") if c.strip()]
        inconnus = [c for c in capteurs if c not in CAPTEURS]
        if inconnus or not capteurs:
            raise SystemExit(f"capteurs invalides : {inconnus or capteurs} (attendu : {', '.join(CAPTEURS)})")
        mdp = args.mot_de_passe or getpass.getpass(f"Mot de passe pour {args.nom} : ")
        if not mdp or (not args.mot_de_passe and mdp != getpass.getpass("Encore une fois : ")):
            raise SystemExit("mots de passe vides ou différents, rien n'est changé")
        comptes[args.nom] = {"hash": generate_password_hash(mdp), "capteurs": capteurs}
        ecrire(comptes, args.fichier)
        print(f"compte {args.nom} enregistré (capteurs {', '.join(capteurs)})")
    elif args.action == "supprimer":
        if comptes.pop(args.nom, None) is None:
            raise SystemExit(f"pas de compte {args.nom}")
        ecrire(comptes, args.fichier)
        print(f"compte {args.nom} supprimé")
    else:
        for nom, c in comptes.items():
            print(f"{nom:<15} capteurs {', '.join(c['capteurs'])}")
        if not comptes:
            print("aucun compte : python -m web.comptes ajouter <nom> --capteurs 2")


if __name__ == "__main__":
    main()
