"""Client MQTT avec messages JSON."""
import json
import traceback

import paho.mqtt.client as mqtt
from config import BROKER_HOST, BROKER_PORT


def creer_client(client_id, on_message, abonnements):
    """client_id doit être UNIQUE sur le broker (ex: 'serveur', 'capteur-1').

    on_message(topic, donnees) ne reçoit que des objets JSON (dict).
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    def _on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{client_id}] connexion refusée : {reason_code}")
            return
        print(f"[{client_id}] connecté au broker")
        for topic in abonnements:
            client.subscribe(topic, qos=1)

    def _on_message(client, userdata, msg):
        # Ce code tourne dans le thread réseau de paho : une exception qui
        # s'en échappe tue ce thread et le client devient sourd sans le dire.
        try:
            donnees = json.loads(msg.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            print(f"[{client_id}] message non JSON ignoré sur {msg.topic}")
            return
        if not isinstance(donnees, dict):
            print(f"[{client_id}] message ignoré sur {msg.topic} : objet JSON attendu")
            return
        try:
            on_message(msg.topic, donnees)
        except Exception:
            print(f"[{client_id}] erreur en traitant {msg.topic} {donnees} :")
            traceback.print_exc()

    def _on_disconnect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:      # déconnexion voulue (fin du programme)
            return
        # Le broker coupe l'ancien client quand un nouveau arrive avec le même nom :
        # deux programmes avec le même id se chassent alors chaque seconde.
        print(f"[{client_id}] déconnecté du broker ({reason_code}), reconnexion... "
              f"Si ce message se répète, un autre programme tourne déjà sous le nom "
              f"'{client_id}' : arrêtez-le ou vérifiez l'id.")

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    return client


def publier(client, topic, donnees, retain=False):
    client.publish(topic, json.dumps(donnees), qos=1, retain=retain)
