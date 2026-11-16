"""Serveur de jeu : choisit l'espion, lance la partie, compte les votes.

    ./jeu.sh serveur        une partie à chaque Entrée
    ./jeu.sh serveur 10     10 parties d'affilée
"""
import argparse
import json
import os
import random
import threading
import time
from collections import Counter
from datetime import datetime

from config import CAPTEURS, NB_TOURS, INTERVALLE
from common import topics
from common.mqtt_client import creer_client, publier

IDS = list(CAPTEURS.keys())                 # ["1", "2", "3"]
MAJORITE = len(IDS) // 2 + 1                # 3 sur 4
DELAI_VOTES = NB_TOURS * INTERVALLE + 60    # attente max des votes (s), le LLM est lent
PAUSE = 5                                   # entre deux parties d'affilée (s)
JOURNAL = "docs/parties.jsonl"              # une ligne JSON par partie (lu par serveur.bilan)


def compter_votes(votes, espion):
    """votes = {votant: {"suspect": id, "strategie": nom}} -> résultat de la partie."""
    decompte = Counter(v["suspect"] for v in votes.values())
    designe = None
    if decompte:
        suspect, nb_voix = decompte.most_common(1)[0]
        if nb_voix >= MAJORITE:
            designe = suspect
    return {
        "espion": espion,
        "designe": designe,
        "votes": {votant: v["suspect"] for votant, v in votes.items()},
        "strategies": {votant: v["strategie"] for votant, v in votes.items()},
        "gagnant": "capteurs" if designe == espion else "espion",
    }


class Serveur:
    def __init__(self):
        # Partagé avec le thread réseau -> toujours lu/écrit sous le verrou.
        self.partie = None                      # numéro de la partie en cours, None entre deux
        self.votes = {}                         # {votant: {"suspect": id, "strategie": nom}}
        self.temperatures = {}                  # {id_capteur: [valeur du tour 1, 2, ...]}
        self.verrou = threading.Lock()
        self.tous_ont_vote = threading.Event()  # signal "tout le monde a voté"
        self.client = creer_client("serveur", self.traiter_message,
                                   [topics.TOUS_VOTES, topics.TOUTES_TEMPERATURES])

    # ================= Une partie, étape par étape =================
    def jouer(self, partie):
        espion = random.choice(IDS)
        print(f"\n=== Partie {partie} : l'espion est le capteur {espion} ===")

        self.ouvrir(partie)              # 1. accepter mesures et votes de CETTE partie
        self.envoyer_roles(espion)       # 2. chaque capteur reçoit son rôle en secret
        time.sleep(1)                    #    (laisser les rôles arriver avant le départ)
        publier(self.client, topics.JEU_START, {"partie": partie})   # 3. départ
        print(f"Départ ! Attente des votes (max {DELAI_VOTES} s)")

        votes, temperatures = self.attendre_votes()                  # 4. tous les votes
        resultat = {"partie": partie, **compter_votes(votes, espion)}  # 5. majorité
        publier(self.client, topics.JEU_RESULTAT, resultat)          # 6. annonce
        print(f"Désigné : {resultat['designe']} -> victoire des {resultat['gagnant'].upper()}")
        self.archiver(resultat, temperatures)
        return resultat

    def ouvrir(self, partie):
        with self.verrou:
            self.partie = partie
            self.votes = {}
            self.temperatures = {}
            self.tous_ont_vote.clear()

    def envoyer_roles(self, espion):
        for id_capteur in IDS:
            role = "espion" if id_capteur == espion else "normal"
            # Pas de retain : sinon le broker garde le rôle de la partie précédente
            # et un capteur qui démarre l'affiche comme s'il était encore valable.
            publier(self.client, topics.role(id_capteur), {"role": role})

    def attendre_votes(self):
        """Attend tous les votes (ou le délai), puis ferme la partie."""
        complet = self.tous_ont_vote.wait(timeout=DELAI_VOTES)
        with self.verrou:
            self.partie = None           # plus aucun vote ni mesure n'est accepté
            votes, temperatures = self.votes, self.temperatures
        if not complet:
            print(f"Délai dépassé, pas de vote de : {[i for i in IDS if i not in votes]}")
        return votes, temperatures

    def archiver(self, resultat, temperatures):
        ligne = {"date": datetime.now().isoformat(timespec="seconds"),
                 **resultat, "temperatures": temperatures}
        try:
            os.makedirs(os.path.dirname(JOURNAL), exist_ok=True)
            with open(JOURNAL, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"Journal non écrit ({JOURNAL}) : {e}")

    # ================= Réception (thread réseau de paho) =================
    def traiter_message(self, topic, donnees):
        id_capteur = topics.id_depuis_topic(topic)
        if topic == topics.vote(id_capteur):
            self.noter_vote(id_capteur, donnees)
        elif topic == topics.temperature(id_capteur):
            self.noter_temperature(id_capteur, donnees)

    def noter_temperature(self, id_capteur, donnees):
        valeur = donnees.get("temperature")
        with self.verrou:
            # Les mesures d'une autre partie (en retard) ne comptent pas.
            if self.partie is None or donnees.get("partie") != self.partie:
                return
            if id_capteur not in IDS or not isinstance(valeur, (int, float)):
                return
            self.temperatures.setdefault(id_capteur, []).append(valeur)
        print(f"  tour {donnees.get('tour')} : capteur {id_capteur} -> {valeur} °C")

    def noter_vote(self, votant, donnees):
        suspect = donnees.get("suspect")
        with self.verrou:
            if votant not in IDS:
                print(f"  vote d'un capteur inconnu ignoré : {votant}")
                return
            if self.partie is None:
                print(f"  vote de {votant} ignoré (pas de partie en cours)")
                return
            # Sans ce contrôle, un vote en retard de la partie précédente
            # prendrait la place du vrai vote de ce capteur.
            if donnees.get("partie") != self.partie:
                print(f"  vote de {votant} ignoré : il concerne la partie "
                      f"{donnees.get('partie')!r}, en cours : {self.partie}")
                return
            if suspect not in IDS or suspect == votant:
                print(f"  vote de {votant} ignoré : suspect invalide {suspect!r}")
                return
            if votant in self.votes:
                print(f"  {votant} a déjà voté, nouveau vote ignoré")
                return

            strategie = donnees.get("strategie", "?")
            self.votes[votant] = {"suspect": suspect, "strategie": strategie}
            print(f"  vote reçu : {votant} -> soupçonne {suspect} ({strategie})")
            if len(self.votes) == len(IDS):
                self.tous_ont_vote.set()


def main():
    parser = argparse.ArgumentParser(description="Serveur du jeu de l'espion")
    parser.add_argument("parties", type=int, nargs="?", default=0,
                        help="nombre de parties d'affilée (sans : une partie à chaque Entrée)")
    nb_parties = parser.parse_args().parties

    serveur = Serveur()
    serveur.client.loop_start()   # réseau dans un thread à part
    time.sleep(1)                 # laisser le temps de s'abonner aux votes
    try:
        if nb_parties:
            for partie in range(1, nb_parties + 1):
                serveur.jouer(partie)
                time.sleep(PAUSE)
        else:
            partie = 1
            while True:
                input(f"\nEntrée pour lancer la partie {partie} (Ctrl+C pour quitter)... ")
                serveur.jouer(partie)
                partie += 1
    except (KeyboardInterrupt, EOFError):
        print("\nArrêt du serveur")
    finally:
        serveur.client.loop_stop()
        serveur.client.disconnect()


if __name__ == "__main__":
    main()
