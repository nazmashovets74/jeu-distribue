#!/bin/bash
# Raccourcis du jeu (marche depuis n'importe quel dossier) :
#   ./jeu.sh serveur          une partie à chaque Entrée
#   ./jeu.sh serveur 10       10 parties d'affilée
#   ./jeu.sh serveur --web    une partie quand tous sont « Prêt » sur le site
#   ./jeu.sh capteur 2        capteur n°2 (vote avec la médiane)
#   ./jeu.sh capteur 2 llm    capteur n°2 (vote avec Ollama)
#   ./jeu.sh capteur 4        capteur virtuel, sur RPi A
#   ./jeu.sh trafic           voir tous les messages MQTT
#   ./jeu.sh bilan            statistiques des parties jouées
#   ./jeu.sh web              site : http://<machine>:5000
cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
commande=$1
shift
case "$commande" in
    serveur) exec venv/bin/python -m serveur.serveur "$@" ;;
    capteur) exec venv/bin/python -m capteur.capteur "$@" ;;
    bilan)   exec venv/bin/python -m serveur.bilan "$@" ;;
    web)     exec venv/bin/python -m web.app "$@" ;;
    trafic)  exec mosquitto_sub -h "${BROKER_HOST:-rpi-a.local}" -v -t 'iot/#' ;;
    *)       sed -n '2,11p' "$0" | cut -c3- ; exit 1 ;;
esac
