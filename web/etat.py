"""État de la partie vu par le site, reconstruit à partir des messages MQTT.

Le site est un simple spectateur MQTT (comme ./jeu.sh trafic) : il ne publie
rien et ne s'abonne PAS à iot/role/#, donc il ne connaît l'espion qu'au résultat.
"""
import queue
import threading
from collections import deque
from datetime import datetime

from config import CAPTEURS, NB_TOURS
from common import topics
from common.mqtt_client import creer_client

TAILLE_JOURNAL = 300                     # lignes de journal gardées en mémoire


def heure():
    return datetime.now().strftime("%H:%M:%S")


class EtatJeu:
    def __init__(self):
        self.verrou = threading.Lock()
        self.abonnes = set()                 # files des navigateurs connectés (flux SSE)
        self.journal = deque(maxlen=TAILLE_JOURNAL)
        self.capteurs = {i: {"en_ligne": False, "strategie": None} for i in CAPTEURS}
        self.serveur_en_ligne = False
        self.partie = None                   # partie affichée (en cours ou dernière)
        self.en_cours = False
        self.temperatures = {}               # {id: [t1, t2, ...]} de la partie affichée
        self.votes = {}                      # {votant: {"suspect", "strategie"}}
        self.resultat = None
        self.client = creer_client(
            "web", self.traiter_message,
            [topics.JEU_START, topics.JEU_RESULTAT, topics.TOUTES_TEMPERATURES,
             topics.TOUS_VOTES, topics.TOUS_ETATS, topics.ETAT_SERVEUR],
        )

    # ================= Données pour le navigateur =================
    def instantane(self):
        """Tout ce que la page affiche, en un objet JSON (envoyé à chaque changement)."""
        return {
            "nb_tours": NB_TOURS,
            "capteurs": {i: {**CAPTEURS[i], **self.capteurs[i]} for i in CAPTEURS},
            "serveur_en_ligne": self.serveur_en_ligne,
            "partie": self.partie,
            "en_cours": self.en_cours,
            "temperatures": self.temperatures,
            "votes": self.votes,
            "resultat": self.resultat,
            "journal": list(self.journal),
        }

    def abonner(self):
        file = queue.Queue(maxsize=50)
        with self.verrou:
            self.abonnes.add(file)
            file.put(self.instantane())
        return file

    def desabonner(self, file):
        with self.verrou:
            self.abonnes.discard(file)

    def _diffuser(self):
        """À appeler sous le verrou après chaque changement."""
        donnees = self.instantane()
        for file in list(self.abonnes):
            try:
                file.put_nowait(donnees)
            except queue.Full:       # navigateur trop lent ou parti : on le lâche
                self.abonnes.discard(file)

    def _noter(self, texte, genre="info"):
        self.journal.append({"heure": heure(), "texte": texte, "genre": genre})

    # ================= Messages MQTT (thread réseau de paho) =================
    def traiter_message(self, topic, d):
        with self.verrou:
            if topic == topics.JEU_START:
                self._start(d)
            elif topic == topics.JEU_RESULTAT:
                self._resultat(d)
            elif topic == topics.ETAT_SERVEUR:
                self._etat_serveur(d)
            else:
                id_capteur = topics.id_depuis_topic(topic)
                if id_capteur not in CAPTEURS:
                    return
                if topic == topics.temperature(id_capteur):
                    self._temperature(id_capteur, d)
                elif topic == topics.vote(id_capteur):
                    self._vote(id_capteur, d)
                elif topic == topics.etat_capteur(id_capteur):
                    self._etat_capteur(id_capteur, d)
            self._diffuser()

    def _start(self, d):
        self.partie, self.en_cours = d.get("partie"), True
        self.temperatures, self.votes, self.resultat = {}, {}, None
        self._noter(f"Partie {self.partie} : départ !", "partie")

    def _temperature(self, i, d):
        valeur = d.get("temperature")
        if d.get("partie") != self.partie or not isinstance(valeur, (int, float)):
            return
        self.temperatures.setdefault(i, []).append(valeur)
        self._noter(f"Tour {d.get('tour')} · capteur {i} ({CAPTEURS[i]['ville']}) : {valeur} °C",
                    "mesure")

    def _vote(self, i, d):
        if d.get("partie") != self.partie or i in self.votes:
            return
        self.votes[i] = {"suspect": str(d.get("suspect")), "strategie": d.get("strategie", "?")}
        self._noter(f"Vote · capteur {i} soupçonne le capteur {d.get('suspect')} "
                    f"({d.get('strategie', '?')})", "vote")

    def _resultat(self, d):
        if d.get("partie") != self.partie:
            return
        self.en_cours, self.resultat = False, d
        gagnant = "des CAPTEURS" if d.get("gagnant") == "capteurs" else "de l'ESPION"
        self._noter(f"Résultat : l'espion était le capteur {d.get('espion')}, désigné : "
                    f"{d.get('designe') or 'personne'} → victoire {gagnant}", "resultat")

    def _etat_capteur(self, i, d):
        en_ligne = d.get("etat") == "en ligne"
        avant = self.capteurs[i]
        # Hors ligne, le testament MQTT ne dit pas la stratégie : on garde la dernière connue.
        self.capteurs[i] = {"en_ligne": en_ligne,
                            "strategie": d.get("strategie") or avant["strategie"]}
        if en_ligne != avant["en_ligne"]:
            self._noter(f"Capteur {i} ({CAPTEURS[i]['ville']}) "
                        + (f"en ligne, stratégie {d.get('strategie')}" if en_ligne else "hors ligne"),
                        "connexion" if en_ligne else "alerte")
        elif en_ligne and d.get("strategie") != avant["strategie"]:
            self._noter(f"Capteur {i} utilise maintenant la stratégie {d.get('strategie')}",
                        "connexion")

    def _etat_serveur(self, d):
        en_ligne = d.get("etat") == "en ligne"
        if en_ligne == self.serveur_en_ligne:
            return
        self.serveur_en_ligne = en_ligne
        if en_ligne:
            self._noter("Serveur en ligne", "connexion")
        else:
            self._noter("Serveur hors ligne", "alerte")
            if self.en_cours:
                self.en_cours = False
                self._noter(f"Partie {self.partie} interrompue (serveur arrêté)", "alerte")
