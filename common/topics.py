"""Tous les topics MQTT du jeu, définis à un seul endroit."""

def temperature(id_capteur):
    return f"iot/capteurs/{id_capteur}/temperature"

def role(id_capteur):
    return f"iot/role/{id_capteur}"

def vote(id_capteur):
    return f"iot/votes/{id_capteur}"

TOUTES_TEMPERATURES = "iot/capteurs/+/temperature"
TOUS_VOTES = "iot/votes/+"
JEU_START = "iot/jeu/start"
JEU_RESULTAT = "iot/jeu/resultat"

def id_depuis_topic(topic):
    """'iot/capteurs/2/temperature' -> '2'"""
    return topic.split("/")[2]
