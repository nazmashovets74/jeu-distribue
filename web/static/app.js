// Page spectateur : reçoit l'état complet par Server-Sent Events et redessine.
"use strict";

const $ = (id) => document.getElementById(id);
let etat = null;

// Tout ce qui vient de MQTT est échappé : n'importe qui peut publier sur le broker.
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function connecter() {
  const flux = new EventSource("/flux");   // se reconnecte tout seul si le site redémarre
  flux.onmessage = (e) => { etat = JSON.parse(e.data); dessiner(); };
}

function dessiner() {
  $("serveur").textContent = etat.serveur_en_ligne ? "serveur en ligne" : "serveur hors ligne";
  dessinerStatut();
  dessinerResultat();
  dessinerCapteurs();
  dessinerJournal();
}

// ---------- Où en est la partie ----------
function dessinerStatut() {
  const n = etat.nb_tours;
  const tour = Math.max(0, ...Object.values(etat.temperatures).map((v) => v.length));
  const nbVotes = Object.keys(etat.votes).length;
  let phase = "En attente d'une partie";
  if (etat.partie != null) {
    if (etat.resultat) phase = `Partie ${etat.partie} · terminée`;
    else if (!etat.en_cours) phase = `Partie ${etat.partie} · interrompue`;
    else if (tour < n) phase = `Partie ${etat.partie} · tour ${tour || 1}/${n}`;
    else phase = `Partie ${etat.partie} · vote ${nbVotes}/${Object.keys(etat.capteurs).length}`;
  }
  $("phase").textContent = phase;
}

// ---------- Fin de partie : l'espion et les votes ----------
function dessinerResultat() {
  const r = etat.resultat;
  $("resultat").hidden = !r;
  if (!r) return;
  const ville = etat.capteurs[r.espion]?.ville ?? "?";
  const votes = Object.entries(r.votes || {})
    .map(([votant, suspect]) => `${esc(votant)} → ${esc(suspect)}`).join(" · ");
  $("resultat").className = `panneau resultat ${r.gagnant === "capteurs" ? "capteurs" : "espion"}`;
  $("resultat").innerHTML =
    (r.gagnant === "capteurs"
      ? `Espion démasqué : capteur ${esc(r.espion)}`
      : `L'espion s'échappe : c'était le capteur ${esc(r.espion)}`)
    + `<small>${esc(ville)} · désigné : ${r.designe ? `capteur ${esc(r.designe)}` : "personne"}</small>`
    + `<small>votes : ${votes || "aucun"}</small>`;
}

// ---------- Capteurs : ville, stratégie, mesures, vote ----------
function dessinerCapteurs() {
  const r = etat.resultat;
  $("capteurs").innerHTML = Object.entries(etat.capteurs).map(([id, c]) => {
    const vote = etat.votes[id];
    const mesures = (etat.temperatures[id] || []).map((t) => Number(t).toFixed(1)).join("  ");
    const classes = [r?.espion === id && "espion", !c.en_ligne && "hors"].filter(Boolean).join(" ");
    const tags = (r?.espion === id ? `<span class="tag espion">espion</span>` : "")
               + (r?.designe === id ? `<span class="tag designe">désigné</span>` : "");
    return `<li class="${classes}">
      <span class="point ${c.en_ligne ? "on" : ""}" title="${c.en_ligne ? "en ligne" : "hors ligne"}"></span>
      <span class="num">${esc(id)}</span>
      <span class="ville">${esc(c.ville)}${tags}</span>
      <span class="strat">${esc(c.strategie || "–")}</span>
      <span class="mesures">${mesures}</span>
      <span class="vote">${vote ? `vote → <b>${esc(vote.suspect)}</b>` : ""}</span>
    </li>`;
  }).join("");
}

// ---------- Terminal ----------
function dessinerJournal() {
  const liste = $("journal");
  const enBas = liste.scrollHeight - liste.scrollTop - liste.clientHeight < 30;
  liste.innerHTML = etat.journal.map((l) =>
    `<li><time>${esc(l.heure)}</time><span class="g-${esc(l.genre)}">${esc(l.texte)}</span></li>`
  ).join("") || `<li class="vide">rien pour l'instant</li>`;
  if (enBas) liste.scrollTop = liste.scrollHeight;
}

connecter();
