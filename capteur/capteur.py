"""Capteur de température : reçoit son rôle, publie 5 mesures, puis vote.

    ./jeu.sh capteur 2          capteur n°2, vote avec la stratégie médiane
    ./jeu.sh capteur 2 llm      capteur n°2, vote avec Ollama
Le capteur enchaîne les parties jusqu'à Ctrl+C. Sa stratégie peut aussi être
changée depuis le site (iot/capteurs/<id>/strategie) : elle s'applique entre
deux parties, jamais au milieu d'une partie.
"""
import argparse
import random
import threading
import time

import strategies
from config import CAPTEURS, NB_TOURS, INTERVALLE
from common import topics
from common.mqtt_client import creer_client, deconnecter, publier
from capteur.meteo import get_temperature
from capteur.espion import fausse_temperature

# Après mon 5e tour, j'attends que tous les capteurs aient publié leurs 5 mesures
# avant de voter (un capteur en retard, ex. Open-Meteo lent, serait jugé sans
# sa dernière valeur). Au-delà de ce délai, je vote avec ce que j'ai reçu.
ATTENTE_MAX_AVANT_VOTE = 10   # secondes
PAUSE_AVANT_VOTE = 3          # s une fois tout reçu : le vote commence après le tour 5 de TOUS


def preparer_strategie(nom, modele=None):
    """-> (module de la stratégie, None) ou (None, problème expliqué)."""
    if nom not in strategies.NOMS:
        return None, f"stratégie inconnue : {nom!r} (attendu : {', '.join(strategies.NOMS)})"
    strategie = strategies.charger(nom)
    if nom == "llm":
        strategie.configurer(modele=modele)
        probleme = strategie.verifier()
        if probleme:
            return None, f"stratégie llm impossible : {probleme}"
    return strategie, None


class Capteur:
    def __init__(self, mon_id, nom_strategie, strategie, modele=None):
        self.mon_id = mon_id
        self.info = CAPTEURS[mon_id]
        self.nom_strategie = nom_strategie
        self.strategie = strategie
        self.modele = modele            # modèle Ollama si on passe à llm
        self.demande_strategie = None   # stratégie demandée par le site, appliquée entre 2 parties
        self.derniere_vraie = None      # secours si Open-Meteo ne répond pas
        # Partagé avec le thread réseau -> protégé par le verrou.
        self.role = "normal"
        self.partie = None              # numéro reçu dans le dernier start
        self.historique = {}            # {id: [températures de la partie]}, moi inclus
        self.verrou = threading.Lock()
        self.depart = threading.Event()
        # Annoncé au site à chaque (re)connexion ; modifié sur place quand la
        # stratégie change. Jamais le rôle : il est secret.
        self.infos_etat = {"ville": self.info["ville"], "strategie": nom_strategie}
        self.client = creer_client(
            f"capteur-{mon_id}", self.traiter_message,
            [topics.role(mon_id), topics.JEU_START, topics.strategie(mon_id),
             topics.TOUTES_TEMPERATURES, topics.JEU_RESULTAT],
            topic_etat=topics.etat_capteur(mon_id), infos_etat=self.infos_etat,
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
        elif topic == topics.strategie(self.mon_id):
            with self.verrou:
                self.demande_strategie = str(donnees.get("strategie"))
            self.log(f"le site demande la stratégie {self.demande_strategie} "
                     f"({donnees.get('par', '?')}), appliquée avant la prochaine partie")
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
        if self.attendre_mesures(partie):
            self.voter(partie)

    def manquants(self):
        """Capteurs qui n'ont pas encore publié leurs NB_TOURS mesures (sous le verrou)."""
        return [i for i in CAPTEURS if len(self.historique.get(i, [])) < NB_TOURS]

    def attendre_mesures(self, partie):
        """Attend les 5 mesures de tout le monde (max ATTENTE_MAX_AVANT_VOTE s).

        -> False si une nouvelle partie a commencé entre-temps (ne pas voter).
        """
        limite = time.monotonic() + ATTENTE_MAX_AVANT_VOTE
        annonce = False   # le message d'attente n'est affiché qu'une fois
        while True:
            with self.verrou:
                if self.partie != partie:
                    self.log(f"nouveau start reçu, partie {partie} abandonnée")
                    return False
                manquants = self.manquants()
                recues = {i: len(self.historique.get(i, [])) for i in manquants}
            if not manquants:
                self.log(f"les {len(CAPTEURS)} capteurs ont fini leurs {NB_TOURS} tours, "
                         f"vote dans {PAUSE_AVANT_VOTE} s")
                time.sleep(PAUSE_AVANT_VOTE)
                with self.verrou:
                    return self.partie == partie
            if time.monotonic() >= limite:
                detail = ", ".join(f"capteur {i} ({n}/{NB_TOURS})" for i, n in recues.items())
                self.log(f"délai de {ATTENTE_MAX_AVANT_VOTE} s dépassé, je vote sans : {detail}")
                return True
            # Ma propre mesure revient du broker en quelques ms : inutile de l'annoncer.
            autres = [i for i in manquants if i != self.mon_id]
            if autres and not annonce:
                self.log(f"attente des dernières mesures de : {', '.join(autres)} "
                         f"(max {ATTENTE_MAX_AVANT_VOTE} s)")
                annonce = True
            time.sleep(0.2)

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

    def appliquer_demande_strategie(self):
        """Hors partie seulement : changer de stratégie en plein vote fausserait le bilan."""
        with self.verrou:
            nom, self.demande_strategie = self.demande_strategie, None
        if nom is None:
            return
        erreur = None
        if nom != self.nom_strategie:
            strategie, erreur = preparer_strategie(nom, self.modele)
            if erreur:
                self.log(f"stratégie {nom} refusée : {erreur} ; je garde {self.nom_strategie}")
            else:
                self.strategie, self.nom_strategie = strategie, nom
                self.log(f"nouvelle stratégie : {nom}")
        self.infos_etat.update(strategie=self.nom_strategie, erreur=erreur)
        publier(self.client, topics.etat_capteur(self.mon_id),
                {"etat": "en ligne", **self.infos_etat}, retain=True)

    def boucle(self):
        self.log(f"{self.info['ville']}, stratégie {self.nom_strategie} - attente du start...")
        while True:
            # timeout : vérifier régulièrement si le site a demandé une autre stratégie
            if not self.depart.wait(timeout=0.5):
                self.appliquer_demande_strategie()
                continue
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

    strategie, probleme = preparer_strategie(args.strategie, args.modele)
    if probleme:
        raise SystemExit(f"[capteur-{args.id}] {probleme}")

    capteur = Capteur(args.id, args.strategie, strategie, args.modele)
    capteur.client.loop_start()   # réception MQTT dans un thread séparé
    try:
        capteur.boucle()
    except KeyboardInterrupt:
        print()
        capteur.log("arrêt")
    finally:
        deconnecter(capteur.client)


if __name__ == "__main__":
    main()
