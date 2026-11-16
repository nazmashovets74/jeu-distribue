"""Capteur de température : reçoit son rôle, publie 5 mesures, puis vote."""
import random
import sys
import threading
import time

from config import CAPTEURS, NB_TOURS, INTERVALLE
from common import topics
from common.mqtt_client import creer_client, publier
from capteur.meteo import get_temperature
from capteur.espion import fausse_temperature

MON_ID = sys.argv[1] if len(sys.argv) > 1 else "2"

etat = {"role": "normal"}      # rôle reçu du serveur
historique = {}                # id capteur -> liste de températures reçues
depart = threading.Event()     # déclenché par le message start
fin = threading.Event()        # déclenché par le résultat


def on_message(topic, data):
    """Appelé pour chaque message MQTT reçu (déjà décodé en JSON)."""
    if topic == topics.role(MON_ID):
        etat["role"] = data.get("role", "normal")
        print(f"[capteur-{MON_ID}] rôle reçu : {etat['role']}")
    elif topic == topics.JEU_START:
        print(f"[capteur-{MON_ID}] start reçu")
        depart.set()
    elif topic == topics.JEU_RESULTAT:
        print(f"[capteur-{MON_ID}] résultat : {data}")
        fin.set()
    elif topic.endswith("/temperature"):
        id_c = topics.id_depuis_topic(topic)
        historique.setdefault(id_c, []).append(data["temperature"])


def mesurer(info, derniere_vraie):
    """Retourne (vraie température, température publiée)."""
    try:
        vraie = get_temperature(info["lat"], info["lon"])
    except Exception as e:
        print(f"[capteur-{MON_ID}] erreur Open-Meteo : {e}")
        vraie = derniere_vraie if derniere_vraie is not None else 15.0

    if etat["role"] == "espion":
        autres = [v[-1] for i, v in historique.items() if i != MON_ID and v]
        return vraie, fausse_temperature(autres or [vraie])
    return vraie, vraie


def choisir_suspect():
    """Provisoire : vote au hasard (remplacé plus tard par strategies/)."""
    autres = [i for i in CAPTEURS if i != MON_ID]
    return random.choice(autres)


def main():
    if MON_ID not in CAPTEURS:
        sys.exit(f"id inconnu : {MON_ID} (attendu : {list(CAPTEURS)})")
    info = CAPTEURS[MON_ID]

    client = creer_client(
        f"capteur-{MON_ID}", on_message,
        [topics.role(MON_ID), topics.JEU_START,
         topics.TOUTES_TEMPERATURES, topics.JEU_RESULTAT],
    )
    client.loop_start()  # réception MQTT dans un thread séparé

    print(f"[capteur-{MON_ID}] {info['ville']} - attente du start...")
    depart.wait()

    derniere_vraie = None
    for tour in range(1, NB_TOURS + 1):
        derniere_vraie, t = mesurer(info, derniere_vraie)
        publier(client, topics.temperature(MON_ID),
                {"id": MON_ID, "tour": tour, "temperature": t})
        print(f"[capteur-{MON_ID}] tour {tour} : {t} °C ({etat['role']})")
        time.sleep(INTERVALLE)

    suspect = choisir_suspect()
    publier(client, topics.vote(MON_ID), {"votant": MON_ID, "suspect": suspect})
    print(f"[capteur-{MON_ID}] vote : {suspect}")

    fin.wait(timeout=30)  # attendre le résultat du serveur
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()