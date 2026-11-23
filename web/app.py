"""Site du jeu de l'espion : suivre les parties en direct et se déclarer « Prêt ».

    ./jeu.sh web                 http://<machine>:5000  (sur RPi A, à côté du serveur)
    ./jeu.sh web --port 8080

La page est visible par tous (spectateurs). Se connecter sert à choisir la
stratégie de ses capteurs et à cliquer « Prêt » : la partie démarre quand tous
les joueurs le sont et que le serveur tourne en mode --web.
Comptes : python -m web.comptes.
"""
import argparse
import json
import os
import queue
import secrets
import threading
import time
from functools import wraps

from flask import (Flask, Response, jsonify, redirect, render_template, request,
                   session, url_for)

from config import BROKER_HOST
from web import comptes as gestion_comptes
from web.etat import EtatJeu

CLE = os.path.join(os.path.dirname(__file__), ".cle_secrete")

app = Flask(__name__)
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)
jeu = None          # EtatJeu, créé dans main()


def cle_secrete():
    """Clé des cookies de session, créée au premier lancement (hors git)."""
    try:
        with open(CLE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        cle = secrets.token_hex(32)
        with open(CLE, "w", encoding="utf-8") as f:
            f.write(cle)
        os.chmod(CLE, 0o600)
        return cle


def connecte_requis(vue):
    @wraps(vue)
    def verifiee(*args, **kwargs):
        if session.get("joueur") not in jeu.comptes:
            return jsonify(erreur="connectez-vous d'abord"), 401
        return vue(*args, **kwargs)
    return verifiee


@app.get("/")
def accueil():
    joueur = session.get("joueur")
    if joueur not in jeu.comptes:
        joueur = None
    return render_template("index.html", joueur=joueur,
                           capteurs=jeu.comptes[joueur]["capteurs"] if joueur else [])


@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    erreur = None
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        if gestion_comptes.verifier(jeu.comptes, nom, request.form.get("mot_de_passe", "")):
            session.clear()
            session["joueur"] = nom
            with jeu.verrou:
                jeu._noter(f"{nom} s'est connecté au site", "joueur")
                jeu._diffuser()
            return redirect(url_for("accueil"))
        erreur = "Nom ou mot de passe incorrect."
    return render_template("connexion.html", erreur=erreur, aucun_compte=not jeu.comptes)


@app.post("/deconnexion")
def deconnexion():
    nom = session.pop("joueur", None)
    if nom in jeu.comptes:
        jeu.changer_pret(nom, False)
    return redirect(url_for("accueil"))


@app.post("/pret")
@connecte_requis
def pret():
    demande = request.get_json(silent=True, force=True) or {}
    erreur = jeu.changer_pret(session["joueur"], bool(demande.get("pret", True)))
    if erreur:
        return jsonify(erreur=erreur), 409
    return jsonify(ok=True)


@app.post("/strategie")
@connecte_requis
def strategie():
    demande = request.get_json(silent=True, force=True) or {}
    erreur = jeu.changer_strategie(session["joueur"], str(demande.get("capteur")),
                                   str(demande.get("strategie")))
    if erreur:
        return jsonify(erreur=erreur), 409
    return jsonify(ok=True)


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


def surveiller():
    while True:
        time.sleep(1)
        jeu.verifier_lancement()


def main():
    global jeu
    parser = argparse.ArgumentParser(description="Site du jeu de l'espion")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--comptes", default=gestion_comptes.FICHIER,
                        help="fichier des comptes (défaut : web/comptes.json)")
    args = parser.parse_args()

    comptes = gestion_comptes.lire(args.comptes)
    if not comptes:
        print("Aucun compte joueur : la page marche, mais personne ne peut cliquer « Prêt ».\n"
              "Créer les comptes : venv/bin/python -m web.comptes ajouter <nom> --capteurs 2")
    app.secret_key = cle_secrete()
    jeu = EtatJeu(comptes)
    jeu.client.loop_start()
    threading.Thread(target=surveiller, daemon=True).start()
    print(f"Site : http://<cette machine>:{args.port}  (broker {BROKER_HOST}, "
          f"joueurs : {', '.join(comptes) or 'aucun'})")
    try:
        app.run(host="0.0.0.0", port=args.port, threaded=True)
    finally:
        jeu.client.disconnect()
        jeu.client.loop_stop()


if __name__ == "__main__":
    main()
