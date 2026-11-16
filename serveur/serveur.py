"""Serveur de jeu : choisit l'espion, lance la partie, compte les votes."""
import random
import threading
import time
from collections import Counter

from config import CAPTEURS, NB_TOURS, INTERVALLE
from common import topics
from common.mqtt_client import creer_client, publier

IDS = list(CAPTEURS.keys())                 # ["1", "2", "3"]
MAJORITE = len(IDS) // 2 + 1                # 2 sur 3
DELAI_VOTES = NB_TOURS * INTERVALLE + 30    # attente max des votes (s)


class Serveur:
    def __init__(self):
        self.votes = {}                         # {id_votant: id_suspect}
        self.collecte_ouverte = False           # accepte-t-on des votes ?
        self.tous_ont_vote = threading.Event()  # signal "les 3 ont voté"
        self.verrou = threading.Lock()          # protège self.votes
        self.client = creer_client("serveur", self.traiter_message, [topics.TOUS_VOTES])

    # ---------- Réception des votes (thread réseau de paho) ----------
    def traiter_message(self, topic, donnees):
        votant = topics.id_depuis_topic(topic)
        suspect = str(donnees.get("suspect"))

        with self.verrou:
            if not self.collecte_ouverte:
                print(f"  vote de {votant} ignoré (pas de partie en cours)")
                return
            if votant not in IDS:
                print(f"  vote d'un capteur inconnu ignoré : {votant}")
                return
            if votant in self.votes:
                print(f"  {votant} a déjà voté, nouveau vote ignoré")
                return

            self.votes[votant] = suspect
            print(f"  vote reçu : {votant} -> soupçonne {suspect}")
            if len(self.votes) == len(IDS):
                self.tous_ont_vote.set()

    # ---------- Étapes d'une partie ----------
    def distribuer_roles(self):
        espion = random.choice(IDS)
        for id_capteur in IDS:
            role = "espion" if id_capteur == espion else "normal"
            publier(self.client, topics.role(id_capteur), {"role": role}, retain=True)
        return espion

    def compter_votes(self, espion):
        with self.verrou:
            votes = dict(self.votes)

        decompte = Counter(votes.values())
        designe = None
        if decompte:
            suspect, nb_voix = decompte.most_common(1)[0]
            if nb_voix >= MAJORITE:
                designe = suspect

        return {
            "espion": espion,
            "designe": designe,
            "votes": votes,
            "gagnant": "capteurs" if designe == espion else "espion",
        }

    def jouer(self, numero_partie):
        with self.verrou:
            self.votes.clear()
            self.collecte_ouverte = True
        self.tous_ont_vote.clear()

        espion = self.distribuer_roles()
        print(f"[partie {numero_partie}] espion choisi : {espion}")
        time.sleep(1)  # laisser les rôles arriver avant le départ

        publier(self.client, topics.JEU_START, {"partie": numero_partie})
        print(f"[partie {numero_partie}] départ ! attente des votes (max {DELAI_VOTES} s)")

        complet = self.tous_ont_vote.wait(timeout=DELAI_VOTES)
        with self.verrou:
            self.collecte_ouverte = False
            manquants = [i for i in IDS if i not in self.votes]
        if not complet:
            print(f"[partie {numero_partie}] délai dépassé, pas de vote de : {manquants}")

        resultat = self.compter_votes(espion)
        resultat["partie"] = numero_partie
        publier(self.client, topics.JEU_RESULTAT, resultat)
        print(f"[partie {numero_partie}] désigné : {resultat['designe']} "
              f"-> victoire des {resultat['gagnant'].upper()}")


def main():
    serveur = Serveur()
    serveur.client.loop_start()   # réseau dans un thread à part
    numero_partie = 1
    try:
        while True:
            input(f"\nEntrée pour lancer la partie {numero_partie} (Ctrl+C pour quitter)... ")
            serveur.jouer(numero_partie)
            numero_partie += 1
    except KeyboardInterrupt:
        print("\nArrêt du serveur")
    finally:
        serveur.client.loop_stop()
        serveur.client.disconnect()


if __name__ == "__main__":
    main()