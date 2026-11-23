# jeu-distribue

Jeu de l'espion sur MQTT (TP R5.A.05). Chaque Raspberry Pi publie la température
de sa ville (Open-Meteo). Le serveur désigne en secret un espion qui publie de
fausses valeurs (±5-10 % des autres). Après 5 tours, chaque capteur vote ; si la
majorité désigne l'espion, les capteurs gagnent, sinon l'espion gagne.

La consigne demande 4 RPi, nous en avons 3 : le capteur 4 (Rumilly) est **virtuel**.
C'est le même programme que les autres, lancé en plus sur RPi A ; il reçoit un rôle,
peut être l'espion et vote comme les autres. La majorité est donc de 3 votes sur 4.
Les capteurs sont listés dans `config.py`.

## Installation (sur chaque Raspberry Pi)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Lancer une partie

D'abord les capteurs, **puis** le serveur (le start n'est pas gardé par le broker) :

| Machine | Commande |
|---|---|
| RPi A | `./jeu.sh capteur 1` |
| RPi B | `./jeu.sh capteur 2` |
| RPi C | `./jeu.sh capteur 3` |
| RPi A | `./jeu.sh capteur 4` (capteur virtuel) |
| RPi A | `./jeu.sh serveur` puis Entrée pour chaque partie |

- `./jeu.sh capteur 2 llm` : le capteur vote avec Ollama (`aleatoire` : vote au hasard).
- `./jeu.sh serveur 10` : 10 parties d'affilée sans appuyer sur Entrée.
- `./jeu.sh trafic` : affiche tous les messages MQTT.
- `./jeu.sh bilan` : statistiques des parties jouées.

Les capteurs enchaînent les parties jusqu'à Ctrl+C. `./jeu.sh` active le venv
tout seul et marche depuis n'importe quel dossier.

## Protocole MQTT (JSON, QoS 1)

| Topic | Sens | Contenu |
|---|---|---|
| `iot/role/<id>` | serveur → capteur | `{"role": "normal" \| "espion"}` |
| `iot/jeu/start` | serveur → tous | `{"partie": n}` |
| `iot/capteurs/<id>/temperature` | capteur → tous | `{"id", "ville", "partie", "tour", "temperature"}` |
| `iot/votes/<id>` | capteur → serveur | `{"id", "partie", "suspect", "strategie"}` |
| `iot/jeu/resultat` | serveur → tous | `{"partie", "espion", "designe", "votes", "strategies", "gagnant"}` |
| `iot/capteurs/<id>/etat` (retain) | capteur → site | `{"etat": "en ligne" \| "hors ligne", "ville", "strategie", "erreur"}`, testament MQTT si coupure |
| `iot/serveur/etat` (retain) | serveur → site | `{"etat", "mode": "web" \| "clavier"}` |
| `iot/capteurs/<id>/strategie` | site → capteur | `{"strategie", "par"}`, appliquée entre deux parties |
| `iot/jeu/lancer` | site → serveur | `{"prets": [...]}`, seulement en mode `--web` |

Le serveur et les capteurs ignorent les températures et les votes dont `partie`
n'est pas la partie en cours. Ainsi, un message en retard ne compte jamais
dans la partie suivante.

## Site web (suivre les parties, « Prêt », stratégies)

Un site Flask, en français, sur RPi A à côté du serveur. Il suit tout en direct
(mesures, votes, résultat, journal, historique de `docs/parties.jsonl`) et ne
s'abonne pas à `iot/role/#` : l'espion n'apparaît qu'au résultat.

```bash
venv/bin/pip install -r requirements.txt              # Flask, une fois
venv/bin/python -m web.comptes ajouter nazar --capteurs 1,4   # un compte par RPi
venv/bin/python -m web.comptes ajouter <nom> --capteurs 2
venv/bin/python -m web.comptes ajouter <nom> --capteurs 3
./jeu.sh web                                          # http://rpi-a.local:5000
./jeu.sh serveur --web                                # au lieu de ./jeu.sh serveur
```

- Tout le monde peut regarder la page ; se connecter permet de choisir la
  stratégie de **ses** capteurs et de cliquer « Je suis prêt ».
- La partie démarre seule quand le serveur tourne en `--web`, que les 4 capteurs
  sont en ligne et que tous les joueurs sont prêts. Il faut se remettre prêt
  pour la partie suivante.
- Une stratégie choisie sur le site s'applique entre deux parties ; si elle
  est impossible (ex. modèle Ollama absent), le capteur garde l'ancienne et le
  site affiche pourquoi.
- Les comptes (`web/comptes.json`, mots de passe hachés) et la clé des sessions
  restent sur la machine, hors git.
- Sans `--web`, tout marche comme avant (Entrée ou `./jeu.sh serveur 10`).
- Tester seul sur sa machine avec un broker local : `BROKER_HOST=localhost ./jeu.sh ...`

## Tester le serveur sans capteurs

```bash
# terminal 1 : tout le trafic
./jeu.sh trafic
# terminal 2
./jeu.sh serveur                   # Entrée -> partie 1, noter l'espion affiché
# terminal 3 : les 4 votes de la partie 1 (ici contre le capteur 2)
mosquitto_pub -h rpi-a.local -t iot/votes/1 -m '{"partie": 1, "suspect": "2", "strategie": "main"}'
mosquitto_pub -h rpi-a.local -t iot/votes/3 -m '{"partie": 1, "suspect": "2", "strategie": "main"}'
mosquitto_pub -h rpi-a.local -t iot/votes/4 -m '{"partie": 1, "suspect": "2", "strategie": "main"}'
mosquitto_pub -h rpi-a.local -t iot/votes/2 -m '{"partie": 1, "suspect": "1", "strategie": "main"}'
```

## Comparer les stratégies

- `python -m strategies.simulation` : parties simulées hors réseau, avec la vraie
  `fausse_temperature`. Options : `--reel` (températures actuelles),
  `--temperatures 12 12.2 15 12.1`, `--strategies mediane,aleatoire,llm`, `-n`.
- `./jeu.sh bilan` : bilan des vraies parties archivées par le serveur
  dans `docs/parties.jsonl`. Ces parties sont aussi rejouées avec `mediane`
  sur exactement les mêmes mesures (`--rejouer mediane,aleatoire`).

## Stratégie LLM (Ollama)

Comme le demande la consigne, chaque RPi exécute sa propre instance Ollama.
Installation, une fois par RPi :

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b
```

Puis le capteur vote avec le LLM :

```bash
./jeu.sh capteur 2 llm
```

La stratégie limite llama.cpp à 3 threads. Avec 4 threads sur 4 cœurs, il suffit
qu'un seul cœur soit occupé ailleurs pour que la génération devienne des dizaines
de fois plus lente (mesuré : 90 s au lieu de 7 s par vote).
