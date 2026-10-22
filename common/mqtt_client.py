"""Client MQTT avec messages JSON."""
import json
import paho.mqtt.client as mqtt
from config import BROKER_HOST, BROKER_PORT


def creer_client(client_id, on_message, abonnements):
    """client_id doit être UNIQUE sur le broker (ex: 'serveur', 'capteur-1')."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)

    def _on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{client_id}] connexion refusée : {reason_code}")
            return
        print(f"[{client_id}] connecté au broker")
        for topic in abonnements:
            client.subscribe(topic, qos=1)

    def _on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            print(f"[{client_id}] message non JSON ignoré sur {msg.topic}")
            return
        on_message(msg.topic, data)

    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    return client


def publier(client, topic, data, retain=False):
    client.publish(topic, json.dumps(data), qos=1, retain=retain)
