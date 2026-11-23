"""État de la partie vu par le site, reconstruit à partir des messages MQTT.

Le site est un simple spectateur MQTT de plus (comme ./jeu.sh trafic) : il ne
s'abonne PAS à iot/role/#, donc il ne connaît l'espion qu'au résultat.
Il gère aussi la salle d'attente : quand tous les joueurs sont « Prêt », il
publie iot/jeu/lancer, que le serveur lancé avec --web attend.
"""
import queue
import threading
import time
from collections import deque
from datetime import datetime

import strategies
from config import CAPTEURS, NB_TOURS
from common import topics
from common.mqtt_client import creer_client, publier

TAILLE_JOURNAL = 300                     # lignes de journal gardées en mémoire
DELAI_LANCEMENT = 10                     # s sans start après la demande -> on réessaie

# Affiché dans le menu de chaque capteur (même ordre que strategies.NOMS).
DESCRIPTIONS = {
    "mediane": "écart à la médiane des autres + instabilité",
    "stabilite": "le capteur dont les valeurs bougent le plus",
    "aleatoire": "au hasard (référence)",
    "llm": "modèle Ollama local (lent : 10 à 20 s)",
}


def heure():
    return datetime.now().strftime("%H:%M:%S")


class EtatJeu:
    def __init__(self, comptes):
        self.comptes = comptes               # {nom: {"hash", "capteurs"}}
        self.verrou = threading.Lock()
        self.abonnes = set()                 # files des navigateurs connectés (flux SSE)
        self.journal = deque(maxlen=TAILLE_JOURNAL)
        self.capteurs = {i: {"en_ligne": False, "strategie": None, "erreur": None,
                             "demande": None} for i in CAPTEURS}
        self.serveur = {"en_ligne": False, "mode": None}
        self.prets = set()
        self.demande_envoyee = None          # time.monotonic() de la dernière demande
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
            "strategies": [{"nom": n, "description": DESCRIPTIONS.get(n, "")}
                           for n in strategies.NOMS],
            "capteurs": {i: {**CAPTEURS[i], **self.capteurs[i]} for i in CAPTEURS},
            "serveur": self.serveur,
            "joueurs": [{"nom": n, "capteurs": c["capteurs"], "pret": n in self.prets}
                        for n, c in self.comptes.items()],
            "conditions": self.conditions(),
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

    # ================= Salle d'attente =================
    def conditions(self):
        """[(texte, ok)] : tout doit être vrai pour lancer une partie."""
        hors_ligne = [i for i, c in self.capteurs.items() if not c["en_ligne"]]
        pas_prets = [n for n in self.comptes if n not in self.prets]
        # Le texte décrit ce qui bloque (la page affiche la première condition fausse).
        serveur_ok = self.serveur["en_ligne"] and self.serveur["mode"] == "web"
        return [
            {"texte": "serveur prêt" if serveur_ok
             else "le serveur doit tourner avec ./jeu.sh serveur --web", "ok": serveur_ok},
            {"texte": "4 capteurs en ligne" if not hors_ligne
             else f"capteur {', '.join(hors_ligne)} hors ligne", "ok": not hors_ligne},
            {"texte": "pas de partie en cours" if not self.en_cours else "partie en cours",
             "ok": not self.en_cours},
            {"texte": "tout le monde est prêt" if not pas_prets
             else f"attente de {', '.join(pas_prets)}", "ok": bool(self.comptes) and not pas_prets},
        ]

    def changer_pret(self, nom, pret):
        """-> message d'erreur, ou None si c'est fait."""
        with self.verrou:
            if nom not in self.comptes:
                return "compte inconnu"
            if pret:
                if self.en_cours:
                    return "une partie est déjà en cours"
                mes_hors_ligne = [i for i in self.comptes[nom]["capteurs"]
                                  if not self.capteurs[i]["en_ligne"]]
                if mes_hors_ligne:
                    cmds = " et ".join(f"./jeu.sh capteur {i}" for i in mes_hors_ligne)
                    return f"votre capteur {', '.join(mes_hors_ligne)} est hors ligne : lancez {cmds}"
                if nom not in self.prets:
                    self.prets.add(nom)
                    self._noter(f"{nom} est prêt", "joueur")
            elif nom in self.prets:
                self.prets.discard(nom)
                self._noter(f"{nom} n'est plus prêt", "joueur")
            self._essayer_lancer()
            self._diffuser()
        return None

    def changer_strategie(self, nom, id_capteur, strategie):
        """Le joueur choisit la stratégie d'un de SES capteurs. -> erreur ou None."""
        with self.verrou:
            if id_capteur not in self.comptes.get(nom, {}).get("capteurs", []):
                return f"le capteur {id_capteur} n'est pas à vous"
            if strategie not in strategies.NOMS:
                return f"stratégie inconnue : {strategie}"
            if not self.capteurs[id_capteur]["en_ligne"]:
                return f"le capteur {id_capteur} est hors ligne"
            if self.en_cours:
                return "attendez la fin de la partie pour changer de stratégie"
            self.capteurs[id_capteur]["demande"] = strategie   # en attente de confirmation
            publier(self.client, topics.strategie(id_capteur), {"strategie": strategie, "par": nom})
            self._noter(f"{nom} choisit la stratégie {strategie} pour le capteur {id_capteur}",
                        "joueur")
            self._diffuser()
        return None

    def _essayer_lancer(self):
        if not all(c["ok"] for c in self.conditions()):
            return
        if self.demande_envoyee and time.monotonic() - self.demande_envoyee < DELAI_LANCEMENT:
            return
        self.demande_envoyee = time.monotonic()
        publier(self.client, topics.JEU_LANCER, {"prets": sorted(self.prets)})
        self._noter("Tout le monde est prêt : lancement demandé au serveur", "joueur")

    def verifier_lancement(self):
        """Appelé chaque seconde : relance la demande si le serveur ne l'a pas reçue."""
        with self.verrou:
            if self.demande_envoyee and time.monotonic() - self.demande_envoyee >= DELAI_LANCEMENT:
                self._noter("Le serveur n'a pas démarré la partie, nouvelle demande", "alerte")
                self._essayer_lancer()
                self._diffuser()

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
            self._essayer_lancer()
            self._diffuser()

    def _start(self, d):
        self.partie, self.en_cours = d.get("partie"), True
        self.temperatures, self.votes, self.resultat = {}, {}, None
        self.prets.clear()               # il faudra se remettre prêt pour la suivante
        self.demande_envoyee = None
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
        self.capteurs[i] = {"en_ligne": en_ligne, "strategie": d.get("strategie"),
                            "erreur": d.get("erreur"), "demande": None}
        if en_ligne != avant["en_ligne"]:
            self._noter(f"Capteur {i} ({CAPTEURS[i]['ville']}) "
                        + (f"en ligne, stratégie {d.get('strategie')}" if en_ligne else "hors ligne"),
                        "connexion" if en_ligne else "alerte")
        elif en_ligne and d.get("erreur") and d.get("erreur") != avant["erreur"]:
            self._noter(f"Capteur {i} : {d['erreur']}, il garde {d.get('strategie')}", "alerte")
        elif en_ligne and d.get("strategie") != avant["strategie"]:
            self._noter(f"Capteur {i} utilise maintenant la stratégie {d.get('strategie')}",
                        "connexion")
        if not en_ligne:   # un joueur dont le capteur tombe n'est plus prêt
            for nom, c in self.comptes.items():
                if i in c["capteurs"] and nom in self.prets:
                    self.prets.discard(nom)
                    self._noter(f"{nom} n'est plus prêt (capteur {i} hors ligne)", "alerte")

    def _etat_serveur(self, d):
        en_ligne = d.get("etat") == "en ligne"
        self.serveur = {"en_ligne": en_ligne, "mode": d.get("mode") if en_ligne else None}
        if en_ligne:
            mode = "web : il attend les « Prêt »" if d.get("mode") == "web" else \
                   "clavier : les parties se lancent avec Entrée"
            self._noter(f"Serveur en ligne, mode {mode}", "connexion")
        else:
            self._noter("Serveur hors ligne", "alerte")
            if self.en_cours:
                self.en_cours = False
                self._noter(f"Partie {self.partie} interrompue (serveur arrêté)", "alerte")
