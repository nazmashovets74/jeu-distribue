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
const fmt = (t) => (typeof t === "number" ? t.toFixed(1) : "–");

// ---------- Flux en direct ----------
function connecter() {
  const flux = new EventSource("/flux");
  flux.onopen = () => { $("direct").textContent = "en direct"; $("direct").classList.add("actif"); };
  flux.onerror = () => { $("direct").textContent = "reconnexion…"; $("direct").classList.remove("actif"); };
  flux.onmessage = (e) => { etat = JSON.parse(e.data); dessiner(); };
}

function dessiner() {
  dessinerPartie();
  dessinerResultat();
  dessinerCapteurs();
  dessinerSalle();
  dessinerJournal();
  dessinerHistorique();
}

// ---------- Avancement ----------
function phase() {
  const n = etat.nb_tours;
  const tour = Math.max(0, ...Object.values(etat.temperatures).map((v) => v.length));
  const nbVotes = Object.keys(etat.votes).length;
  if (etat.partie == null) return { texte: "En attente de la première partie", tour: 0, vote: false };
  if (etat.resultat) return { texte: "Partie terminée", tour: n, vote: true };
  if (!etat.en_cours) return { texte: "Partie interrompue", tour, vote: false };
  if (tour < n) return { texte: tour ? `Tour ${tour} sur ${n}` : "Départ…", tour, vote: false };
  return { texte: `Vote en cours (${nbVotes}/${Object.keys(etat.capteurs).length})`, tour: n, vote: nbVotes > 0 };
}

function dessinerPartie() {
  const p = phase();
  $("partie-numero").textContent = etat.partie == null ? "Partie" : `Partie n° ${etat.partie}`;
  $("phase").textContent = p.texte;
  let html = "";
  for (let t = 1; t <= etat.nb_tours; t++) html += `<li class="${t <= p.tour ? "fait" : ""}">${t}</li>`;
  html += `<li class="vote ${p.vote ? "fait" : ""}">vote</li>`;
  $("tours").innerHTML = html;
  const s = etat.serveur;
  const mode = s.mode === "web" ? "mode web" : s.mode === "clavier" ? "mode clavier" : "";
  $("serveur").innerHTML = `<span class="pastille ${s.en_ligne ? "en-ligne" : "hors-ligne"}"></span>
    Serveur ${s.en_ligne ? "en ligne" : "hors ligne"}${mode ? ` · ${mode}` : ""}`;
}

// ---------- Résultat ----------
function dessinerResultat() {
  const r = etat.resultat;
  const bloc = $("resultat");
  bloc.hidden = !r;
  if (!r) return;
  const ville = (i) => etat.capteurs[i]?.ville ?? "?";
  const voix = Object.values(r.votes || {}).filter((s) => s === r.espion).length;
  const total = Object.keys(r.votes || {}).length;
  bloc.className = `resultat ${r.gagnant === "capteurs" ? "capteurs" : "espion"}`;
  bloc.innerHTML = `
    <div>
      <h2>${r.gagnant === "capteurs" ? "Les capteurs ont démasqué l'espion !" : "L'espion s'en sort !"}</h2>
      <p>L'espion était le capteur <strong>${esc(r.espion)}</strong> (${esc(ville(r.espion))}),
         ${voix} vote${voix > 1 ? "s" : ""} contre lui sur ${total}.</p>
    </div>
    <p>Désigné par la majorité : <strong>${r.designe ? `capteur ${esc(r.designe)}` : "personne"}</strong></p>`;
}

// ---------- Capteurs ----------
function courbe(valeurs, min, max) {
  if (!valeurs.length) return `<svg class="courbe" viewBox="0 0 100 38" aria-hidden="true"></svg>`;
  const n = etat.nb_tours;
  const x = (k) => 4 + (k * 92) / Math.max(1, n - 1);
  const y = (v) => (max === min ? 19 : 34 - ((v - min) * 30) / (max - min));
  const pts = valeurs.map((v, k) => `${x(k).toFixed(1)},${y(v).toFixed(1)}`);
  return `<svg class="courbe" viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="${pts.join(" ")}" vector-effect="non-scaling-stroke"/></svg>`;
}

function menuStrategie(id, c) {
  const choisie = c.demande || c.strategie;
  const options = etat.strategies.map((s) =>
    `<option value="${esc(s.nom)}" ${s.nom === choisie ? "selected" : ""}>${esc(s.nom)}</option>`).join("");
  const description = etat.strategies.find((s) => s.nom === choisie)?.description;
  const bloque = !c.en_ligne || etat.en_cours;
  return `<label class="choix-strategie">Stratégie de vote
      <select data-capteur="${esc(id)}" ${bloque ? "disabled" : ""}>${options}</select></label>
    ${description ? `<span class="description">${esc(description)}</span>` : ""}
    ${c.demande && c.demande !== c.strategie ? `<span class="aide">en attente du capteur…</span>` : ""}
    ${c.erreur ? `<span class="erreur">${esc(c.erreur)}</span>` : ""}`;
}

function dessinerCapteurs() {
  // Ne pas fermer un menu déroulant pendant que le joueur choisit.
  if (document.activeElement?.closest?.("#capteurs select")) return;
  const toutes = Object.values(etat.temperatures).flat();
  const min = Math.min(...toutes), max = Math.max(...toutes);
  const r = etat.resultat;
  $("capteurs").innerHTML = Object.entries(etat.capteurs).map(([id, c]) => {
    const valeurs = etat.temperatures[id] || [];
    const vote = etat.votes[id];
    const derniere = valeurs[valeurs.length - 1];
    const mien = MES_CAPTEURS.has(id);
    const classes = ["capteur", mien && "a-moi", r?.espion === id && "espion", !c.en_ligne && "hors"];
    const cases = Array.from({ length: etat.nb_tours }, (_, k) =>
      `<span class="${valeurs[k] != null ? "plein" : ""}">${fmt(valeurs[k])}</span>`).join("");
    return `<article class="${classes.filter(Boolean).join(" ")}">
      <div class="capteur-tete">
        <div><h4>${esc(c.ville)}</h4><span class="num">capteur ${esc(id)}</span></div>
        <div class="badges">
          ${mien ? `<span class="badge moi">à vous</span>` : ""}
          ${r?.espion === id ? `<span class="badge espion">ESPION</span>` : ""}
          ${r?.designe === id ? `<span class="badge designe">désigné</span>` : ""}
          <span class="badge"><span class="pastille ${c.en_ligne ? "en-ligne" : "hors-ligne"}"></span>
            ${c.en_ligne ? "en ligne" : "hors ligne"}</span>
        </div>
      </div>
      <p class="temp-actuelle">${fmt(derniere)} <small>°C</small></p>
      ${courbe(valeurs, min, max)}
      <div class="valeurs">${cases}</div>
      <div class="capteur-pied">
        <span>${vote ? `Soupçonne <strong>capteur ${esc(vote.suspect)}</strong>` : "Pas encore voté"}</span>
        ${mien ? "" : `<span>${esc(vote?.strategie || c.strategie || "–")}</span>`}
      </div>
      ${mien ? `<div class="capteur-strategie">${menuStrategie(id, c)}</div>` : ""}
    </article>`;
  }).join("");
}

$("capteurs").addEventListener("change", async (e) => {
  const menu = e.target.closest("select[data-capteur]");
  if (!menu) return;
  menu.blur();
  const erreur = await envoyer("/strategie", { capteur: menu.dataset.capteur, strategie: menu.value });
  if (erreur) { alerter(erreur); dessiner(); }
});

// ---------- Salle d'attente ----------
function dessinerSalle() {
  $("joueurs").innerHTML = etat.joueurs.map((j) => `
    <li>
      <span><span class="nom">${esc(j.nom)}</span>
        <span class="ses-capteurs">${j.capteurs.map((i) =>
          `<span><span class="pastille ${etat.capteurs[i]?.en_ligne ? "en-ligne" : "hors-ligne"}"></span>${esc(i)}</span>`).join("")}</span>
      </span>
      <span class="badge ${j.pret ? "pret" : ""}">${j.pret ? "prêt" : "pas prêt"}</span>
    </li>`).join("") || `<li class="aide">Aucun compte joueur.</li>`;
  $("conditions").innerHTML = etat.conditions.map((c) =>
    `<li class="${c.ok ? "ok" : ""}">${esc(c.texte)}</li>`).join("");

  const bouton = $("bouton-pret");
  if (!bouton) return;
  const moi = etat.joueurs.find((j) => j.nom === MOI);
  const pret = !!moi?.pret;
  bouton.textContent = etat.en_cours ? "Partie en cours…" : pret ? "Je ne suis plus prêt" : "Je suis prêt";
  bouton.classList.toggle("annuler", pret);
  bouton.disabled = etat.en_cours;
  bouton.dataset.pret = pret ? "1" : "";
}

$("bouton-pret")?.addEventListener("click", async (e) => {
  const erreur = await envoyer("/pret", { pret: !e.currentTarget.dataset.pret });
  alerter(erreur);
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

function alerter(texte) {
  const p = $("erreur-pret");
  if (!p) return;
  p.hidden = !texte;
  p.textContent = texte || "";
}

// ---------- Journal ----------
const GENRES = { partie: "partie", vote: "vote", resultat: "resultat-ligne", alerte: "alerte",
                 connexion: "connexion", mesure: "mesure", joueur: "joueur" };

function dessinerJournal() {
  const liste = $("journal");
  const enBas = liste.scrollHeight - liste.scrollTop - liste.clientHeight < 30;
  liste.innerHTML = etat.journal.map((l) =>
    `<li class="l-${esc(l.genre)}"><time>${esc(l.heure)}</time><span class="${GENRES[l.genre] || ""}">${esc(l.texte)}</span></li>`
  ).join("") || `<li class="vide">Rien pour l'instant : lancez les capteurs et le serveur.</li>`;
  if (enBas) liste.scrollTop = liste.scrollHeight;
}

$("masquer-mesures").addEventListener("change", (e) => {
  $("journal").classList.toggle("sans-mesures", e.target.checked);
});

// ---------- Historique ----------
function dessinerHistorique() {
  const h = etat.historique;
  const gagnees = h.filter((p) => p.gagnant === "capteurs").length;
  $("score").innerHTML = h.length
    ? `Capteurs <strong>${gagnees}</strong> – <strong>${h.length - gagnees}</strong> Espion
       <span class="aide">(${h.length} dernières parties)</span>` : "";
  $("historique").innerHTML = h.map((p) => {
    const date = p.date ? new Date(p.date).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "–";
    const votes = Object.entries(p.votes || {}).sort().map(([v, s]) => `${esc(v)}→${esc(s)}`).join("  ");
    return `<tr><td>${esc(date)}</td><td>${esc(p.partie)}</td><td>capteur ${esc(p.espion)}</td>
      <td>${p.designe ? `capteur ${esc(p.designe)}` : "personne"}</td><td class="votes">${votes}</td>
      <td class="${p.gagnant === "capteurs" ? "gagne-capteurs" : "gagne-espion"}">${p.gagnant === "capteurs" ? "capteurs" : "espion"}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="aide">Aucune partie jouée.</td></tr>`;
}

connecter();
