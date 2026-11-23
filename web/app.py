"""Site du jeu de l'espion, en mode spectateur : la partie en direct, sans compte.

    ./jeu.sh web                 http://<machine>:5000
    ./jeu.sh web --port 8080

Le site écoute les messages MQTT, comme ./jeu.sh trafic, et les affiche :
capteurs, villes, stratégies, journal façon terminal, puis le résultat.
Il ne commande rien : les parties se lancent depuis le serveur (./jeu.sh serveur).
"""
import argparse
import json
import os
import queue

from flask import Flask, Response, render_template

from config import BROKER_HOST
from web.etat import EtatJeu

# root_path explicite : les templates sont trouvés quelle que soit la façon de lancer.
app = Flask(__name__, root_path=os.path.dirname(os.path.abspath(__file__)))
jeu = None          # EtatJeu, créé dans main()


@app.get("/")
def accueil():
    return render_template("index.html")


@app.get("/flux")
def flux():
    """Server-Sent Events : l'état complet est renvoyé à chaque changement."""
    file = jeu.abonner()

    def generer():
        try:
            while True:
                try:
                    donnees = file.get(timeout=15)
                    yield f"data: {json.dumps(donnees, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ": rien de neuf\n\n"      # garde la connexion ouverte
        finally:
            jeu.desabonner(file)

    return Response(generer(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def main():
    global jeu
    parser = argparse.ArgumentParser(description="Site du jeu de l'espion (spectateur)")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    jeu = EtatJeu()
    jeu.client.loop_start()
    print(f"Site : http://<cette machine>:{args.port}  (broker {BROKER_HOST})")
    try:
        app.run(host="0.0.0.0", port=args.port, threaded=True)
    finally:
        jeu.client.disconnect()
        jeu.client.loop_stop()


if __name__ == "__main__":
    main()
