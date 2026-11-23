"""Tous les topics MQTT du jeu, définis à un seul endroit."""

def temperature(id_capteur):
    return f"iot/capteurs/{id_capteur}/temperature"

def etat_capteur(id_capteur):
    """Retenu : {"etat": "en ligne" | "hors ligne", ...} (testament MQTT si coupure)."""
    return f"iot/capteurs/{id_capteur}/etat"

def strategie(id_capteur):
    """Site web -> capteur : {"strategie": nom, "par": joueur}, appliquée entre 2 parties."""
    return f"iot/capteurs/{id_capteur}/strategie"

def role(id_capteur):
    return f"iot/role/{id_capteur}"

def vote(id_capteur):
    return f"iot/votes/{id_capteur}"

TOUTES_TEMPERATURES = "iot/capteurs/+/temperature"
TOUS_ETATS = "iot/capteurs/+/etat"
TOUS_VOTES = "iot/votes/+"
JEU_START = "iot/jeu/start"
JEU_RESULTAT = "iot/jeu/resultat"
# Site web -> serveur (mode --web) : tout le monde est prêt, lancer une partie.
JEU_LANCER = "iot/jeu/lancer"
# Retenu : {"etat": "en ligne" | "hors ligne", "mode": "web" | "clavier"}
ETAT_SERVEUR = "iot/serveur/etat"

def id_depuis_topic(topic):
    """'iot/capteurs/2/temperature' -> '2'"""
    return topic.split("/")[2]
