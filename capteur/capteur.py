"""Capteur de température : reçoit son rôle, publie 5 mesures, puis vote.

    ./jeu.sh capteur 2          capteur n°2, vote avec la stratégie médiane
    ./jeu.sh capteur 2 llm      capteur n°2, vote avec Ollama
Le capteur enchaîne les parties jusqu'à Ctrl+C.
"""
import argparse
import random
import threading
import time

import strategies
from config import CAPTEURS, NB_TOURS, INTERVALLE
from common import topics
from common.mqtt_client import creer_client, publier
from capteur.meteo import get_temperature
from capteur.espion import fausse_temperature


class Capteur:
    def __init__(self, mon_id, nom_strategie, strategie):
        self.mon_id = mon_id
        self.info = CAPTEURS[mon_id]
        self.nom_strategie = nom_strategie
        self.strategie = strategie
        self.derniere_vraie = None      # secours si Open-Meteo ne répond pas
        # Partagé avec le thread réseau -> protégé par le verrou.
        self.role = "normal"
        self.partie = None              # numéro reçu dans le dernier start
        self.historique = {}            # {id: [températures de la partie]}, moi inclus
        self.verrou = threading.Lock()
        self.depart = threading.Event()
        self.client = creer_client(
            f"capteur-{mon_id}", self.traiter_message,
            [topics.role(mon_id), topics.JEU_START,
             topics.TOUTES_TEMPERATURES, topics.JEU_RESULTAT],
        )

    def log(self, texte):
        print(f"[capteur-{self.mon_id}] {texte}")

    # ---------- Réception (thread réseau de paho) ----------
    def traiter_message(self, topic, donnees):
        if topic == topics.role(self.mon_id):
            # Pas d'affichage ici : le rôle n'est montré qu'au départ de la partie,
            # pour qu'un vieux rôle resté sur le broker ne passe pas pour le tirage.
            with self.verrou:
                self.role = donnees.get("role", "normal")
        elif topic == topics.JEU_START:
            with self.verrou:
                self.partie = donnees.get("partie")
                self.historique = {}
            self.depart.set()
        elif topic == topics.JEU_RESULTAT:
            if donnees.get("partie") == self.partie:
                self.log(f"résultat : espion {donnees.get('espion')}, désigné "
                         f"{donnees.get('designe')} -> victoire des "
                         f"{str(donnees.get('gagnant')).upper()} (votes {donnees.get('votes')})")
        elif topic == topics.temperature(topics.id_depuis_topic(topic)):
            valeur = donnees.get("temperature")
            with self.verrou:
                # Une mesure en retard de la partie précédente fausserait l'historique.
                if donnees.get("partie") == self.partie and isinstance(valeur, (int, float)):
                    self.historique.setdefault(topics.id_depuis_topic(topic), []).append(valeur)

    # ---------- Une partie ----------
    def mesurer(self, role):
        """Température à publier : la vraie, ou une fausse si je suis l'espion."""
        try:
            vraie = get_temperature(self.info["lat"], self.info["lon"])
            self.derniere_vraie = vraie
        except Exception as e:
            self.log(f"erreur Open-Meteo : {e}")
            vraie = self.derniere_vraie if self.derniere_vraie is not None else 15.0

        if role != "espion":
            return vraie
        with self.verrou:
            autres = [v[-1] for i, v in self.historique.items() if i != self.mon_id and v]
        # Au tour 1 l'espion n'a encore rien reçu : il part de sa propre vraie valeur.
        return fausse_temperature(autres or [vraie])

    def jouer(self):
        with self.verrou:
            partie, role = self.partie, self.role
        self.log(f"=== partie {partie} : mon rôle = {role.upper()} ===")
        debut = time.monotonic()
        for tour in range(1, NB_TOURS + 1):
            with self.verrou:
                nouvelle = self.partie != partie
            if nouvelle:
                self.log(f"nouveau start reçu, partie {partie} abandonnée")
                return
            t = self.mesurer(role)
            publier(self.client, topics.temperature(self.mon_id),
                    {"id": self.mon_id, "ville": self.info["ville"],
                     "partie": partie, "tour": tour, "temperature": t})
            self.log(f"tour {tour} : {t} °C ({role})")
            # Cadence fixe : un appel Open-Meteo lent ne décale pas les tours suivants.
            time.sleep(max(0.0, debut + tour * INTERVALLE - time.monotonic()))
        self.voter(partie)

    def voter(self, partie):
        with self.verrou:
            historique = {i: list(v) for i, v in self.historique.items()}
        nom = self.nom_strategie
        try:
            suspect = self.strategie.choisir_suspect(self.mon_id, historique)
            if suspect not in CAPTEURS or suspect == self.mon_id:
                raise ValueError(f"suspect invalide : {suspect!r}")
        except Exception as e:
            # Un vote au hasard vaut mieux que pas de vote ; le nom de la
            # stratégie le dit, pour ne pas fausser la comparaison.
            self.log(f"stratégie {nom} en échec ({e}), vote au hasard")
            suspect = random.choice([i for i in CAPTEURS if i != self.mon_id])
            nom = f"aleatoire (échec {nom})"

        publier(self.client, topics.vote(self.mon_id),
                {"id": self.mon_id, "partie": partie, "suspect": suspect, "strategie": nom})
        raison = getattr(self.strategie, "derniere_raison", None) if nom == self.nom_strategie else None
        self.log(f"vote : {suspect} ({nom})" + (f" - {raison}" if raison else ""))

    def boucle(self):
        self.log(f"{self.info['ville']}, stratégie {self.nom_strategie} - attente du start...")
        while True:
            self.depart.wait()
            self.depart.clear()
            self.jouer()
            self.log("attente de la partie suivante...")


def main():
    parser = argparse.ArgumentParser(description="Capteur du jeu de l'espion")
    parser.add_argument("id", choices=list(CAPTEURS), help="identifiant de ce capteur")
    parser.add_argument("strategie", nargs="?", choices=strategies.NOMS, default="mediane",
                        help="façon de choisir le suspect (défaut : mediane)")
    parser.add_argument("--modele", help="modèle Ollama pour llm (défaut : qwen3:1.7b)")
    args = parser.parse_args()

    strategie = strategies.charger(args.strategie)
    if args.strategie == "llm":
        strategie.configurer(modele=args.modele)
        print(f"[capteur-{args.id}] vérification d'Ollama et chargement du modèle...")
        probleme = strategie.verifier()
        if probleme:
            raise SystemExit(f"[capteur-{args.id}] stratégie llm impossible : {probleme}")

    capteur = Capteur(args.id, args.strategie, strategie)
    capteur.client.loop_start()   # réception MQTT dans un thread séparé
    try:
        capteur.boucle()
    except KeyboardInterrupt:
        print()
        capteur.log("arrêt")
    finally:
        capteur.client.loop_stop()
        capteur.client.disconnect()


if __name__ == "__main__":
    main()
