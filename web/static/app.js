// Page du jeu : reçoit l'état complet par Server-Sent Events et redessine.
"use strict";

const $ = (id) => document.getElementById(id);
const MOI = window.JOUEUR;
const MES_CAPTEURS = new Set(window.MES_CAPTEURS || []);
let etat = null;

// Tout ce qui vient de MQTT est échappé : n'importe qui peut publier sur le broker.
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function connecter() {
  const flux = new EventSource("/flux");
  flux.onopen = () => { $("direct").textContent = "en direct"; $("direct").classList.add("actif"); };
  flux.onerror = () => { $("direct").textContent = "reconnexion"; $("direct").classList.remove("actif"); };
  flux.onmessage = (e) => { etat = JSON.parse(e.data); dessiner(); };
}

function dessiner() {
  dessinerStatut();
  dessinerCapteurs();
  dessinerPrets();
  dessinerJournal();
}

// ---------- Statut + résultat ----------
function dessinerStatut() {
  const n = etat.nb_tours;
  const tour = Math.max(0, ...Object.values(etat.temperatures).map((v) => v.length));
  const nbVotes = Object.keys(etat.votes).length;
  let phase = "En attente";
  if (etat.partie != null) {
    if (etat.resultat) phase = `Partie ${etat.partie} · terminée`;
    else if (!etat.en_cours) phase = `Partie ${etat.partie} · interrompue`;
    else if (tour < n) phase = `Partie ${etat.partie} · tour ${tour || 1}/${n}`;
    else phase = `Partie ${etat.partie} · vote ${nbVotes}/${Object.keys(etat.capteurs).length}`;
  }
  $("phase").textContent = phase;
  const s = etat.serveur;
  $("serveur").textContent = s.en_ligne ? `serveur : ${s.mode}` : "serveur hors ligne";

  const r = etat.resultat;
  $("resultat").hidden = !r;
  if (r) {
    const ville = etat.capteurs[r.espion]?.ville ?? "?";
    $("resultat").className = `panneau resultat ${r.gagnant === "capteurs" ? "capteurs" : "espion"}`;
    $("resultat").innerHTML = (r.gagnant === "capteurs"
      ? `Espion démasqué : capteur ${esc(r.espion)}`
      : `L'espion s'échappe : c'était le capteur ${esc(r.espion)}`)
      + `<small>${esc(ville)} · désigné : ${r.designe ? `capteur ${esc(r.designe)}` : "personne"}</small>`;
  }
}

// ---------- Capteurs : une ligne chacun ----------
function strategie(id, c) {
  if (!MES_CAPTEURS.has(id)) return esc(c.strategie || "–");
  const choisie = c.demande || c.strategie;
  const bloque = !c.en_ligne || etat.en_cours;
  return `<select data-capteur="${esc(id)}" ${bloque ? "disabled" : ""} title="stratégie de vote">
    ${etat.strategies.map((s) => `<option value="${esc(s.nom)}" title="${esc(s.description)}"
      ${s.nom === choisie ? "selected" : ""}>${esc(s.nom)}</option>`).join("")}</select>`;
}

function dessinerCapteurs() {
  // Ne pas fermer un menu déroulant pendant que le joueur choisit.
  if (document.activeElement?.closest?.("#capteurs select")) return;
  const r = etat.resultat;
  $("capteurs").innerHTML = Object.entries(etat.capteurs).map(([id, c]) => {
    const vote = etat.votes[id];
    const classes = [MES_CAPTEURS.has(id) && "mien", r?.espion === id && "espion", !c.en_ligne && "hors"];
    const tags = (r?.espion === id ? `<span class="tag espion">espion</span>` : "")
               + (r?.designe === id ? `<span class="tag designe">désigné</span>` : "");
    const note = MES_CAPTEURS.has(id) && c.erreur ? `<span class="note">${esc(c.erreur)}</span>` : "";
    return `<li class="${classes.filter(Boolean).join(" ")}">
      <span class="point ${c.en_ligne ? "on" : ""}" title="${c.en_ligne ? "en ligne" : "hors ligne"}"></span>
      <span class="num">${esc(id)}</span>
      <span class="ville">${esc(c.ville)}${tags}</span>
      <span class="strat">${strategie(id, c)}</span>
      <span class="vote">${vote ? `vote → <b>${esc(vote.suspect)}</b>` : ""}</span>
      ${note}
    </li>`;
  }).join("");
}

$("capteurs").addEventListener("change", async (e) => {
  const menu = e.target.closest("select[data-capteur]");
  if (!menu) return;
  menu.blur();
  montrerErreur(await envoyer("/strategie", { capteur: menu.dataset.capteur, strategie: menu.value }));
  dessiner();
});

// ---------- Prêts ----------
function dessinerPrets() {
  $("joueurs").innerHTML = etat.joueurs.map((j) =>
    `<li class="${j.pret ? "pret" : ""}">${esc(j.nom)}</li>`).join("") || `<li>aucun compte</li>`;
  const bloquant = etat.conditions.find((c) => !c.ok);
  $("attente").textContent = bloquant ? bloquant.texte : "";

  const bouton = $("bouton-pret");
  if (!bouton) return;
  const pret = !!etat.joueurs.find((j) => j.nom === MOI)?.pret;
  bouton.textContent = pret ? "Annuler" : "Prêt";
  bouton.classList.toggle("annuler", pret);
  bouton.disabled = etat.en_cours;
  bouton.dataset.pret = pret ? "1" : "";
}

$("bouton-pret")?.addEventListener("click", async (e) => {
  montrerErreur(await envoyer("/pret", { pret: !e.currentTarget.dataset.pret }));
});

async function envoyer(url, corps) {
  try {
    const rep = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                   body: JSON.stringify(corps) });
    if (rep.ok) return null;
    return (await rep.json().catch(() => ({}))).erreur || `erreur ${rep.status}`;
  } catch {
    return "le site ne répond pas";
  }
}

function montrerErreur(texte) {
  $("erreur").hidden = !texte;
  $("erreur").textContent = texte || "";
}

// ---------- Journal ----------
function dessinerJournal() {
  const liste = $("journal");
  const enBas = liste.scrollHeight - liste.scrollTop - liste.clientHeight < 30;
  liste.innerHTML = etat.journal.map((l) =>
    `<li><time>${esc(l.heure)}</time><span class="g-${esc(l.genre)}">${esc(l.texte)}</span></li>`
  ).join("") || `<li class="vide">rien pour l'instant</li>`;
  if (enBas) liste.scrollTop = liste.scrollHeight;
}

connecter();
