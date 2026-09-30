/**
 * Front-end do Agregador de Pesquisas Presidenciais 2026.
 * Lê dados/planopolitico.json (coletado de planopolitico.com.br por coleta/planopolitico.py)
 * e oferece filtros por turno, base de votos, território e período, mapa de estados,
 * pesquisas individuais sobre a curva, tabela ordenável e exportação CSV.
 */

const CANDIDATE_COLORS = {
  "Lula": { line: "#ef4444", fill: "rgba(239, 68, 68, 0.15)" },
  "Flávio Bolsonaro": { line: "#3b82f6", fill: "rgba(59, 130, 246, 0.15)" },
  "Augusto Cury": { line: "#f59e0b", fill: "rgba(245, 158, 11, 0.15)" },
  "Ronaldo Caiado": { line: "#10b981", fill: "rgba(16, 185, 129, 0.15)" },
  "Ciro Gomes": { line: "#ec4899", fill: "rgba(236, 72, 153, 0.15)" },
  "Romeu Zema": { line: "#f97316", fill: "rgba(249, 115, 22, 0.15)" },
  "Renan Santos": { line: "#06b6d4", fill: "rgba(6, 182, 212, 0.15)" },
  "Outros": { line: "#78716c", fill: "rgba(120, 113, 108, 0.12)" },
  "Indecisos": { line: "#a855f7", fill: "rgba(168, 85, 247, 0.12)" }
};
const DEFAULT_COLOR = { line: "#64748b", fill: "rgba(100, 116, 139, 0.15)" };
const PALETA = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#a855f7", "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#14b8a6", "#6366f1", "#eab308", "#0ea5e9", "#d946ef"];
const hexFill = (hex, a = 0.15) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
const corDe = (nome) => CANDIDATE_COLORS[nome] || appState.cores[nome] || DEFAULT_COLOR;
const CARGOS = { presidente: "Presidente", governador: "Governador", senado: "Senador" };
const NAO_NOMINAIS = ["Outros", "Indecisos"];
const POR_PAGINA = 15;

// Posição (coluna, linha) de cada UF no mapa de blocos
const MAPA_UF = {
  RR: [2, 0], AP: [4, 0],
  AM: [1, 1], PA: [3, 1], MA: [4, 1], CE: [5, 1], RN: [6, 1],
  AC: [0, 2], RO: [1, 2], MT: [2, 2], TO: [3, 2], PI: [4, 2], PE: [5, 2], PB: [6, 2],
  MS: [2, 3], GO: [3, 3], DF: [4, 3], BA: [5, 3], AL: [6, 3],
  PR: [2, 4], SP: [3, 4], MG: [4, 4], ES: [5, 4], SE: [6, 4],
  SC: [2, 5], RJ: [5, 5],
  RS: [2, 6]
};

const appState = {
  turno: 1,
  tipoVoto: "validos",
  cargo: "presidente",       // "presidente" | "governador" | "senado"
  cenario: 0,                // índice do cenário (governador: pares do 2º turno)
  cores: {},                 // cores de candidatos de governador/senado
  ufPref: (() => { try { return localStorage.getItem("uf_pref") || "RN"; } catch (e) { return "RN"; } })(),
  resetOcultos: true,
  dataSel: null,             // data escolhida na linha do tempo do painel (null = hoje)
  dataHover: null,           // data sob o mouse no gráfico de tendência ("hoje" = ponto mais recente)
  territorio: "BR",          // "BR" | "COMB" | sigla de UF
  periodo: 180,              // dias; 0 = tudo
  mostrarPesquisas: true,
  semLideres: false,
  ocultos: new Set(["Outros"]),
  filtroTabela: "",
  institutoTabela: "",
  institutoGrafico: "",
  ordem: { col: "dt_fim", dir: -1 },
  pagina: 1,
  tema: localStorage.getItem("tema_eleicoes_2026") || "dark",
  dados: null
};

const ICONES = {"refresh": "<path d='M21 12a9 9 0 1 1-3-6.7L21 8'/><path d='M21 3v5h-5'/>", "download": "<path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/><path d='m7 10 5 5 5-5'/><path d='M12 15V3'/>", "sun": "<circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41'/>", "moon": "<path d='M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z'/>", "search": "<circle cx='11' cy='11' r='8'/><path d='m21 21-4.3-4.3'/>", "link": "<path d='M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'/><path d='M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'/>", "vote": "<path d='m9 11 3 3L22 4'/><path d='M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11'/>", "map": "<path d='M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3Z'/><path d='M9 3v15M15 6v15'/>", "ruler": "<path d='M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.4 2.4 0 0 1 0-3.4l2.6-2.6a2.4 2.4 0 0 1 3.4 0Z'/><path d='m14.5 12.5 2-2M11.5 9.5l2-2M8.5 6.5l2-2M17.5 15.5l2-2'/>", "alert": "<path d='m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z'/><path d='M12 9v4M12 17h.01'/>", "up": "<path d='m5 12 7-7 7 7'/><path d='M12 19V5'/>", "down": "<path d='M12 5v14'/><path d='m19 12-7 7-7-7'/>", "minus": "<path d='M5 12h14'/>", "left": "<path d='m12 19-7-7 7-7'/><path d='M19 12H5'/>", "right": "<path d='M5 12h14'/><path d='m12 5 7 7-7 7'/>"};
const ico = (n) => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONES[n]}</svg>`;

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 1) => (v == null || isNaN(v) ? "-" : Number(v).toFixed(d).replace(".", ","));
const ehUF = (t) => t !== "BR" && t !== "COMB";
const cargoUF = () => appState.cargo !== "presidente";
const estadoCargo = (uf) => appState.dados?.[appState.cargo]?.states?.[uf];

document.addEventListener("DOMContentLoaded", () => {
  lerHash();
  aplicarTema(appState.tema);
  configurarEventos();
  carregarDados();
});

// ---------------------------------------------------------------- estado na URL
function lerHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("t") === "2") appState.turno = 2;
  if (p.get("b") === "total") appState.tipoVoto = "total";
  if (CARGOS[p.get("c")]) appState.cargo = p.get("c");
  if (p.get("u")) appState.territorio = p.get("u");
  if (cargoUF() && !ehUF(appState.territorio)) appState.territorio = appState.ufPref;
  if (appState.cargo === "senado") appState.turno = 1;
  if (p.has("p") && !isNaN(+p.get("p"))) appState.periodo = +p.get("p");
}

function gravarHash() {
  const p = new URLSearchParams();
  p.set("c", appState.cargo);
  p.set("t", appState.turno);
  p.set("b", appState.tipoVoto);
  p.set("u", appState.territorio);
  p.set("p", appState.periodo);
  history.replaceState(null, "", "#" + p.toString());
}

// ---------------------------------------------------------------- tema
function aplicarTema(tema) {
  document.documentElement.setAttribute("data-theme", tema);
  localStorage.setItem("tema_eleicoes_2026", tema);
  const icon = $("theme-icon");
  if (icon) icon.innerHTML = ico(tema === "dark" ? "sun" : "moon");
  if (appState.dados) {
    atribuirCores();
    atualizarLinhasPainel();
    renderizarGraficoPrincipal();
    renderizarGraficoInstituto();
  }
}

// ---------------------------------------------------------------- eventos
function marcarAtivo(seletor, atributo, valor) {
  document.querySelectorAll(seletor).forEach((b) => b.classList.toggle("active", b.getAttribute(atributo) === String(valor)));
}

function configurarEventos() {
  $("btn-theme-toggle")?.addEventListener("click", () => {
    appState.tema = appState.tema === "dark" ? "light" : "dark";
    aplicarTema(appState.tema);
  });

  document.querySelectorAll("[data-turno]").forEach((btn) => btn.addEventListener("click", () => {
    appState.turno = +btn.dataset.turno;
    appState.cenario = 0;
    appState.resetOcultos = true;
    appState.pagina = 1;
    atualizarVisualizacao();
  }));

  document.querySelectorAll("[data-voto]").forEach((btn) => btn.addEventListener("click", () => {
    appState.tipoVoto = btn.dataset.voto;
    atualizarVisualizacao();
  }));

  document.querySelectorAll("[data-periodo]").forEach((btn) => btn.addEventListener("click", () => {
    appState.periodo = +btn.dataset.periodo;
    atualizarVisualizacao();
  }));

  document.querySelectorAll("[data-cargo]").forEach((btn) => btn.addEventListener("click", () => definirCargo(btn.dataset.cargo)));
  $("sel-cenario")?.addEventListener("change", (e) => {
    appState.cenario = +e.target.value;
    appState.resetOcultos = true;
    appState.pagina = 1;
    atualizarVisualizacao();
  });
  $("sel-territorio")?.addEventListener("change", (e) => definirTerritorio(e.target.value));
  $("chk-zoom")?.addEventListener("change", (e) => {
    appState.semLideres = e.target.checked;
    renderizarGraficoPrincipal();
  });
  $("chk-pesquisas")?.addEventListener("change", (e) => {
    appState.mostrarPesquisas = e.target.checked;
    renderizarGraficoPrincipal();
  });

  $("tabela-busca")?.addEventListener("input", (e) => {
    appState.filtroTabela = e.target.value.toLowerCase().trim();
    appState.pagina = 1;
    renderizarTabelaPesquisas();
  });
  $("sel-instituto-tabela")?.addEventListener("change", (e) => {
    appState.institutoTabela = e.target.value;
    appState.pagina = 1;
    renderizarTabelaPesquisas();
  });
  $("sel-instituto-grafico")?.addEventListener("change", (e) => {
    appState.institutoGrafico = e.target.value;
    renderizarGraficoInstituto();
  });

  document.querySelectorAll("th[data-ordem]").forEach((th) => th.addEventListener("click", () => {
    const col = th.dataset.ordem;
    appState.ordem = appState.ordem.col === col
      ? { col, dir: -appState.ordem.dir }
      : { col, dir: col === "instituto" || col === "scope" ? 1 : -1 };
    renderizarTabelaPesquisas();
  }));

  $("slider-data")?.addEventListener("input", (e) => {
    const datas = appState._painel?.datas || [];
    const i = +e.target.value;
    appState.dataSel = i >= datas.length - 1 ? null : datas[i];
    atualizarLinhasPainel();
  });
  $("btn-hoje")?.addEventListener("click", () => {
    appState.dataSel = null;
    const datas = appState._painel?.datas || [];
    $("slider-data").value = Math.max(datas.length - 1, 0);
    atualizarLinhasPainel();
  });
  $("btn-voltar-presidente")?.addEventListener("click", () => definirCargo("presidente"));
  $("btn-compartilhar")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      mostrarAviso("Link desta visão copiado.");
    } catch (e) {
      mostrarAviso("Não foi possível copiar: copie o endereço na barra do navegador.", true);
    }
  });
  $("btn-csv")?.addEventListener("click", exportarCSV);
  $("btn-atualizar")?.addEventListener("click", atualizarDoSite);
  window.addEventListener("hashchange", () => {
    lerHash();
    appState.resetOcultos = true;
    atualizarVisualizacao(false);
  });
}

function definirTerritorio(t) {
  appState.territorio = t;
  appState.pagina = 1;
  appState.cenario = 0;
  appState.resetOcultos = true;
  appState.institutoTabela = "";
  appState.institutoGrafico = "";
  if (ehUF(t)) {
    appState.ufPref = t;
    try { localStorage.setItem("uf_pref", t); } catch (e) { /* sem storage */ }
  }
  atualizarVisualizacao();
}

function definirCargo(c) {
  if (!CARGOS[c] || appState.cargo === c) return;
  if (c !== "presidente" && !appState.dados?.[c]) return mostrarAviso("Dados de " + CARGOS[c].toLowerCase() + " ainda não coletados: clique em Atualizar.", true);
  appState.cargo = c;
  appState.cenario = 0;
  appState.resetOcultos = true;
  appState.semLideres = false;
  appState.pagina = 1;
  appState.institutoTabela = "";
  appState.institutoGrafico = "";
  if (c === "presidente") {
    appState.territorio = "BR";
  } else {   // governador/senado abrem sempre no Rio Grande do Norte, com indecisos
    appState.territorio = "RN";
    appState.tipoVoto = "total";
  }
  if (c === "senado") appState.turno = 1;
  preencherSeletores();
  atualizarVisualizacao();
}

// ---------------------------------------------------------------- dados
async function carregarDados() {
  for (const url of ["dados/planopolitico.json", "../dados/planopolitico.json"]) {
    try {
      const resp = await fetch(url, { cache: "no-store" });
      if (resp.ok) {
        appState.dados = await resp.json();
        break;
      }
    } catch (e) { /* tenta a próxima */ }
  }

  if (!appState.dados) {
    $("grafico-serie").innerHTML = `
      <div class="loading-indicator">
        <p>${ico("alert")} Não foi possível carregar os dados.</p>
        <p style="font-size:0.85rem; color:var(--text-muted);">Execute <code>python -m coleta.planopolitico</code> (ou abra o site pelo <code>rodar.bat</code>) e recarregue.</p>
      </div>`;
    return;
  }
  if (cargoUF() && !appState.dados[appState.cargo]) {   // link antigo/ dados sem esse cargo
    appState.cargo = "presidente";
    appState.territorio = "BR";
  }
  preencherSeletores();
  atualizarCabecalhoStatus();
  atualizarVisualizacao(false);
}

async function atualizarDoSite() {
  const btn = $("btn-atualizar");
  btn.disabled = true;
  btn.classList.add("girando");
  try {
    const resp = await fetch("/api/atualizar", { method: "POST" });
    const corpo = await resp.json().catch(() => ({}));
    if (!resp.ok || !corpo.ok) throw new Error(corpo.erro || `HTTP ${resp.status}`);
    const antes = appState.dados?.generated_at;
    appState.dados = null;
    await carregarDados();
    mostrarAviso(appState.dados?.generated_at !== antes
      ? "Dados atualizados com novas pesquisas."
      : "Já estava na versão mais recente do Plano Político.");
  } catch (e) {
    mostrarAviso("Não foi possível atualizar: abra o site pelo rodar.bat (ou rode python -m coleta.planopolitico).", true);
  } finally {
    btn.disabled = false;
    btn.classList.remove("girando");
  }
}

function mostrarAviso(msg, erro = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast show" + (erro ? " erro" : "");
  clearTimeout(mostrarAviso._id);
  mostrarAviso._id = setTimeout(() => (t.className = "toast"), 5000);
}

/** Bloco (cenário) atual de governador/senado para uma UF. */
function blocoCargo(uf = appState.territorio, turno = appState.turno, idx = appState.cenario) {
  const st = estadoCargo(uf);
  if (!st) return null;
  if (appState.cargo === "senado") return st.t1;
  const lista = turno === 2 ? st.t2_scenarios : st.t1_scenarios;
  return (lista && (lista[idx] || lista[0])) || (turno === 2 ? st.t2 : st.t1);
}

function cenariosDisponiveis() {
  if (appState.cargo !== "governador") return [];
  const st = estadoCargo(appState.territorio);
  if (!st) return [];
  const lista = appState.turno === 2 ? st.t2_scenarios : st.t1_scenarios;
  return (lista || []).map((s, i) => s.pair ? s.pair.join(" × ") : (s.label || `Cenário ${i + 1}`));
}

/** Normaliza para votos válidos: divide pela soma dos candidatos (tira indecisos). */
function normalizarLista(lista) {
  const soma = lista.reduce((t, c) => t + (c.share || 0), 0);
  if (!soma) return lista;
  const f = 100 / soma;
  return lista.map((c) => ({ ...c, share: c.share * f, ci_lo: c.ci_lo == null ? null : c.ci_lo * f, ci_hi: c.ci_hi == null ? null : c.ci_hi * f }));
}

function pesquisasDoTurno() {
  if (cargoUF()) {
    const st = estadoCargo(appState.territorio);
    if (!st) return [];
    let lista = (appState.turno === 2 ? st.recent_polls?.t2 : st.recent_polls?.t1) || [];
    if (appState.cargo === "governador" && appState.turno === 2) {
      const par = blocoCargo()?.pair;
      if (par) lista = lista.filter((p) => p.pair && p.pair.length === par.length && par.every((n) => p.pair.includes(n)));
    }
    return lista.map((p) => (p.scope ? p : { ...p, scope: appState.territorio }));
  }
  const rp = appState.dados.presidente_t1.recent_polls;
  return (appState.turno === 2 ? rp.t2 : rp.t1) || [];
}

function nomesEstados() {
  const est = appState.dados.presidente_state.states;
  const ordem = appState.dados.presidente_state.state_order || Object.keys(est);
  return ordem.map((uf) => ({ uf, nome: est[uf]?.name || uf }));
}

function preencherSeletores() {
  const sel = $("sel-territorio");
  if (cargoUF()) {
    sel.innerHTML = nomesEstados().map((e) => `<option value="${esc(e.uf)}">${esc(e.nome)}</option>`).join("");
    return;
  }
  sel.innerHTML =
    `<option value="BR">Brasil (pesquisas nacionais)</option>` +
    `<option value="COMB">Brasil + estados (combinada)</option>` +
    `<optgroup label="Estados">` +
    nomesEstados().map((e) => `<option value="${esc(e.uf)}">${esc(e.nome)}</option>`).join("") +
    `</optgroup>`;
}

function atualizarCabecalhoStatus() {
  const d = appState.dados;
  if (cargoUF()) {
    const sts = Object.values(d[appState.cargo]?.states || {});
    const total = sts.reduce((t, s) => t + (s.t1?.n_polls || 0), 0);
    $("badge-total-pesquisas").innerText = `${total} pesquisas de ${CARGOS[appState.cargo].toLowerCase()} em ${sts.length} UFs`;
  } else {
    const total = d.presidente_t1.modes.national_valid.n_polls;
    const est = d.presidente_t1.modes.blended_valid.n_state_polls;
    $("badge-total-pesquisas").innerText = `${total} nacionais + ${est} estaduais`;
  }
  const quando = d.coletado_em ? new Date(d.coletado_em) : null;
  $("badge-data-atualizacao").innerText = quando
    ? `Coletado em ${quando.toLocaleDateString("pt-BR")} às ${quando.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })} (dados de ${formatarData(d.generated_at)})`
    : `Dados de ${formatarData(d.generated_at)}`;
}

// ---------------------------------------------------------------- consultas
function nomeTerritorio() {
  const t = appState.territorio;
  if (t === "BR") return "Brasil";
  if (t === "COMB") return "Brasil + estados";
  return appState.dados.presidente_state.states[t]?.name || t;
}

/** Atribui cores aos candidatos de governador/senado (partido no senado, paleta no governador). */
function atribuirCores() {
  appState.cores = {};
  if (!cargoUF() || !appState.dados) return;
  const st = estadoCargo(appState.territorio);
  if (!st) return;
  const nomes = [];
  const add = (n, c) => { if (!NAO_NOMINAIS.includes(n) && !nomes.some((x) => x.n === n)) nomes.push({ n, c }); };
  (st.t1?.candidates || []).forEach((c) => add(c.name, c));
  (st.t2_scenarios || []).forEach((s) => (s.candidates || []).forEach((c) => add(c.name, c)));
  const dark = appState.tema === "dark";
  nomes.forEach(({ n, c }, i) => {
    const cor = (dark ? c?.color_dark : c?.color) || c?.color || appState.dados.meta?.cores?.[n] || PALETA[i % PALETA.length];
    appState.cores[n] = { line: cor, fill: hexFill(cor) };
  });
}

function aplicarResetOcultos() {
  appState.resetOcultos = false;
  appState.dataSel = null;
  appState.dataHover = null;
  appState.ocultos = new Set(["Outros"]);
  if (!cargoUF()) return;
  // Candidatos com menos de 1,5% ficam ocultos no início (senado tem mais de 10); o chip traz de volta
  (obterSnapshot()?.lista || []).forEach((c) => { if ((c.share ?? 0) < 1.5) appState.ocultos.add(c.name); });
}

/** Estimativa atual do território: { lista:[{name,share,ci_lo,ci_hi}], asOf, n } */
function obterSnapshot(territorio = appState.territorio, turno = appState.turno, validos = appState.tipoVoto === "validos", idx = appState.cenario) {
  const d = appState.dados;
  if (cargoUF()) {
    const blk = blocoCargo(territorio, turno, idx);
    if (!blk || !blk.candidates?.length) return null;
    const lista = appState.cargo === "governador" && validos ? normalizarLista(blk.candidates) : blk.candidates;
    return { lista, asOf: blk.as_of, n: blk.n_polls, pair: blk.pair, indecisos: blk.indecisos };
  }
  if (ehUF(territorio)) {
    const blk = d.presidente_state.states[territorio]?.["t" + turno];
    if (!blk) return null;
    return { lista: (validos ? blk.candidates : blk.candidates_raw) || [], asOf: blk.as_of, n: blk.n_polls };
  }
  if (turno === 1) {
    const m = d.presidente_t1.modes[(territorio === "BR" ? "national_" : "blended_") + (validos ? "valid" : "raw")];
    return { lista: m.candidates, asOf: m.as_of, n: m.n_polls };
  }
  const b = territorio === "BR" ? d.presidente_t2.national_only : d.presidente_t2.blended;
  const r = validos ? "" : "raw_";
  const lista = [
    { name: "Lula", share: b[`lula_${r}share`], ci_lo: b[`lula_${r}ci_lo`] ?? b.lula_ci_lo, ci_hi: b[`lula_${r}ci_hi`] ?? b.lula_ci_hi },
    { name: "Flávio Bolsonaro", share: b[`flavio_${r}share`], ci_lo: b[`flavio_${r}ci_lo`] ?? b.flavio_ci_lo, ci_hi: b[`flavio_${r}ci_hi`] ?? b.flavio_ci_hi }
  ];
  if (!validos && b.indecisos_share != null) lista.push({ name: "Indecisos", share: b.indecisos_share, ci_lo: b.indecisos_share, ci_hi: b.indecisos_share });
  return { lista, asOf: b.as_of, n: b.n_polls };
}

/** Série temporal por candidato para Brasil/Combinada: { nome: {x,y,lo,hi} } */
function obterSerie() {
  const d = appState.dados;
  const validos = appState.tipoVoto === "validos";
  const nacional = appState.territorio === "BR";
  const serie = {};
  const add = (nome, p, chave, chaveLo, chaveHi) => {
    if (p[chave] == null) return;
    const s = (serie[nome] ||= { x: [], y: [], lo: [], hi: [] });
    s.x.push(p.week_end);
    s.y.push(p[chave]);
    s.lo.push(p[chaveLo] ?? null);
    s.hi.push(p[chaveHi] ?? null);
  };

  if (cargoUF()) {
    const blk = blocoCargo();
    const nomes = (blk?.candidates || []).map((c) => c.name);
    const norm = appState.cargo === "governador" && validos;
    (blk?.trajectory || []).forEach((p) => {
      const soma = norm ? nomes.reduce((t, n) => t + (p[n] || 0), 0) : 0;
      const f = norm && soma ? 100 / soma : 1;
      nomes.forEach((n) => {
        if (p[n] == null) return;
        const s = (serie[n] ||= { x: [], y: [], lo: [], hi: [] });
        s.x.push(p.week_end);
        s.y.push(p[n] * f);
        s.lo.push(p[n + "_lo"] == null ? null : p[n + "_lo"] * f);
        s.hi.push(p[n + "_hi"] == null ? null : p[n + "_hi"] * f);
      });
    });
  } else if (appState.turno === 1) {
    const m = d.presidente_t1.modes[(nacional ? "national_" : "blended_") + (validos ? "valid" : "raw")];
    const nomes = m.candidates.map((c) => c.name);
    m.trajectory.forEach((p) => nomes.forEach((n) => add(n, p, n, n + "_lo", n + "_hi")));
  } else {
    const traj = (nacional ? d.presidente_t2.national_only : d.presidente_t2.blended).trajectory;
    const sufixo = validos ? "" : "_raw";
    traj.forEach((p) => {
      add("Lula", p, "Lula" + sufixo);
      add("Flávio Bolsonaro", p, "Flávio Bolsonaro" + sufixo);
      if (!validos) add("Indecisos", p, "Indecisos");
    });
  }
  return serie;
}

function pontosPesquisas() {
  if (cargoUF()) {
    const nomes = (obterSnapshot()?.lista || []).map((c) => c.name);
    if (appState.cargo === "senado") {
      return (estadoCargo(appState.territorio)?.recent_polls?.t1 || []).map((p) => {
        const o = { date: p.dt_fim, registro: p.registro, instituto: p.instituto };
        nomes.forEach((n) => { if (p.shares[n] != null) { o[n] = p.shares[n]; o[n + "_raw"] = p.shares[n]; } });
        return o;
      });
    }
    if (appState.turno !== 1) return [];
    return (estadoCargo(appState.territorio)?.poll_scatter || []).map((p) => {
      const soma = nomes.reduce((t, n) => t + (p[n] || 0), 0);
      const o = { date: p.date, registro: p.registro };
      nomes.forEach((n) => { if (p[n] != null) { o[n + "_raw"] = p[n]; o[n] = soma ? (p[n] * 100) / soma : p[n]; } });
      return o;
    });
  }
  const d = appState.dados;
  const nacional = appState.territorio === "BR";
  const bloco = appState.turno === 1 ? d.presidente_t1.poll_scatter : d.presidente_t2.poll_scatter;
  return (bloco || []).filter((p) => !nacional || p.scope === "BR");
}

function dataCorte(ultima) {
  if (!appState.periodo) return null;
  const dt = new Date(ultima + "T00:00:00");
  dt.setDate(dt.getDate() - appState.periodo);
  return dt.toISOString().slice(0, 10);
}

function pesquisasFiltradas() {
  const t = appState.territorio;
  const termo = appState.filtroTabela;
  let lista = pesquisasDoTurno().filter((p) => {
    if (t === "BR" && p.scope !== "BR") return false;
    if (ehUF(t) && p.scope !== t) return false;
    if (appState.institutoTabela && p.instituto !== appState.institutoTabela) return false;
    if (termo) {
      const texto = `${p.instituto} ${p.registro} ${p.method || ""} ${p.scope}`.toLowerCase();
      if (!texto.includes(termo)) return false;
    }
    return true;
  });
  const { col, dir } = appState.ordem;
  lista = lista.slice().sort((a, b) => {
    const va = a[col] ?? "", vb = b[col] ?? "";
    return (va > vb ? 1 : va < vb ? -1 : 0) * dir || (a.dt_fim < b.dt_fim ? 1 : -1);
  });
  return lista;
}

// ---------------------------------------------------------------- renderização geral
function atualizarVisualizacao(gravar = true) {
  if (!appState.dados) return;
  if (appState.resetOcultos) { atribuirCores(); aplicarResetOcultos(); }
  marcarAtivo("[data-cargo]", "data-cargo", appState.cargo);
  marcarAtivo("[data-turno]", "data-turno", appState.turno);
  marcarAtivo("[data-voto]", "data-voto", appState.tipoVoto);
  marcarAtivo("[data-periodo]", "data-periodo", appState.periodo);
  const barrasPres = !cargoUF() && ehUF(appState.territorio);   // presidente num estado: só barras
  $("sel-territorio").value = appState.territorio;
  $("pill-territorio").textContent = nomeTerritorio().toUpperCase();
  $("grupo-voto").style.display = appState.cargo === "senado" ? "none" : "";
  $("grupo-periodo").style.display = barrasPres ? "none" : "";
  $("wrap-pontos").style.display = barrasPres ? "none" : "";
  $("wrap-zoom").style.display = barrasPres ? "none" : "";
  $("card-serie").style.display = barrasPres ? "none" : "";
  $("hero-titulo").textContent = {
    presidente: "Eleição Presidencial Brasil 2026",
    governador: `Governador · ${nomeTerritorio()}`,
    senado: `Senado · ${nomeTerritorio()}`
  }[appState.cargo];
  $("hero-sub").textContent = cargoUF()
    ? "Escolha o estado no mapa ou na lista. Os gráficos mostram a tendência, as estimativas com margem de incerteza e as pesquisas registradas."
    : "Escolha turno, base de votos, território e período. Clique num estado do mapa para aprofundar.";
  const cen = cenariosDisponiveis();
  $("grupo-cenario").style.display = cen.length > 1 ? "" : "none";
  $("sel-cenario").innerHTML = cen.map((c, i) => `<option value="${i}">${esc(c)}</option>`).join("");
  $("sel-cenario").value = appState.cenario;
  atualizarCabecalhoStatus();
  $("tabela-busca").value = appState.filtroTabela;
  if (gravar) gravarHash();

  renderizarMapa();
  renderizarPainel();
  renderizarChips();
  renderizarGraficoPrincipal();
  renderizarSeletoresInstituto();
  renderizarGraficoInstituto();
  renderizarTabelaPesquisas();
}

// ---------------------------------------------------------------- mapa de estados
function nominaisDe(uf) {
  const snap = obterSnapshot(uf, appState.turno, appState.tipoVoto === "validos", 0);
  const nom = (snap?.lista || []).filter((x) => !NAO_NOMINAIS.includes(x.name) && x.share != null).sort((a, b) => b.share - a.share);
  return { snap, nom };
}

function clicarUF(uf) {
  if (cargoUF()) definirTerritorio(uf);
  else definirTerritorio(appState.territorio === uf ? "BR" : uf);
}

function renderizarMapa() {
  const cont = $("mapa-brasil");
  const mapa = appState.dados.mapa;
  $("mapa-legenda").textContent = cargoUF()
    ? "Clique num estado para ver o cenário dele. Quanto mais escura a cor, maior a vantagem do líder."
    : "Clique num estado para ver as estimativas e pesquisas dele. A cor indica quem lidera; quanto mais intensa, maior a vantagem.";
  $("mapa-titulo").textContent = { presidente: "Eleição presidencial", governador: "Governos estaduais", senado: "Senado federal" }[appState.cargo];
  if (!mapa?.states) return renderizarMapaBlocos(cont);

  let html = `<svg class="mapa-svg" viewBox="${esc(mapa.viewBox)}" role="img" aria-label="Mapa do Brasil por estado">`;
  Object.entries(mapa.states).forEach(([uf, m]) => {
    const { snap, nom } = nominaisDe(uf);
    let fill = "var(--bg-surface)", titulo = `${m.name}: sem estimativa`;
    if (nom.length >= 2) {
      const dif = nom[0].share - nom[1].share;
      const alfa = Math.min(0.3 + dif / 35, 0.95);
      fill = hexFill(cargoUF() ? "#6366f1" : corDe(nom[0].name).line, alfa);
      titulo = `${m.name}: ${nom[0].name} ${fmt(nom[0].share)}% × ${nom[1].name} ${fmt(nom[1].share)}% (${snap.n} pesquisas)`;
    } else if (nom.length === 1) {
      fill = hexFill("#6366f1", 0.5);
      titulo = `${m.name}: ${nom[0].name} ${fmt(nom[0].share)}%`;
    }
    html += `<g class="uf${appState.territorio === uf ? " selecionado" : ""}" data-uf="${uf}"><path d="${m.d}" fill="${fill}"></path><title>${esc(titulo)}</title></g>`;
  });
  cont.className = "mapa-wrap";
  cont.style.cssText = "";
  cont.innerHTML = html + "</svg>";
  cont.querySelectorAll(".uf").forEach((g) => {
    try {   // rótulo da sigla no centro de cada estado
      const b = g.querySelector("path").getBBox();
      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", b.x + b.width / 2);
      t.setAttribute("y", b.y + b.height / 2);
      t.setAttribute("class", "uf-label");
      t.textContent = g.dataset.uf;
      g.appendChild(t);
    } catch (e) { /* sem layout disponível */ }
    g.addEventListener("click", () => clicarUF(g.dataset.uf));
  });
}

function renderizarMapaBlocos(cont) {
  const est = appState.dados.presidente_state.states;
  const linhas = 7, colunas = 7;
  let html = "";
  Object.entries(MAPA_UF).forEach(([uf, [c, l]]) => {
    const { snap, nom } = nominaisDe(uf);
    let estilo = "", txt = "";
    if (nom.length >= 2) {
      const dif = nom[0].share - nom[1].share;
      const cor = cargoUF() ? "#6366f1" : corDe(nom[0].name).line;
      const alfa = Math.min(0.25 + dif / 40, 0.95).toFixed(2);
      estilo = `background:${cor}${Math.round(alfa * 255).toString(16).padStart(2, "0")};`;
      txt = `<span class="tile-uf">${uf}</span><span class="tile-val">+${fmt(dif, 0)}</span>`;
    } else {
      txt = `<span class="tile-uf">${uf}</span><span class="tile-val">s/d</span>`;
    }
    const titulo = nom.length >= 2
      ? `${est[uf].name}: ${nom[0].name} ${fmt(nom[0].share)}% × ${nom[1].name} ${fmt(nom[1].share)}% (${snap.n} pesquisas)`
      : `${est[uf]?.name || uf}: sem estimativa`;
    html += `<button class="tile${appState.territorio === uf ? " selecionado" : ""}" data-uf="${uf}" title="${esc(titulo)}" style="grid-column:${c + 1};grid-row:${l + 1};${estilo}">${txt}</button>`;
  });
  cont.style.gridTemplateColumns = `repeat(${colunas}, 1fr)`;
  cont.style.gridTemplateRows = `repeat(${linhas}, 1fr)`;
  cont.innerHTML = html;
  cont.className = "tile-map";
  cont.querySelectorAll(".tile").forEach((b) => b.addEventListener("click", () => clicarUF(b.dataset.uf)));
}

// ---------------------------------------------------------------- painel de detalhe (barras + linha do tempo)
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const DIAS_SEMANA = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"];
const dataUTC = (s) => new Date(s + "T00:00:00Z");

function formatarDataCurta(s) {
  if (!s) return "-";
  const [a, m, d] = String(s).slice(0, 10).split("-");
  return `${d}/${m}/${a.slice(2)}`;
}

function partidoDe(nome, lista) {
  return lista?.find((c) => c.name === nome)?.party || appState.dados.meta?.partido?.[nome] || "";
}

function indiceData(datas, data) {
  if (!data) return datas.length - 1;
  let i = 0;
  datas.forEach((d, k) => { if (d <= data) i = k; });
  return i;
}

function contextoPainel() {
  const semSerie = !cargoUF() && ehUF(appState.territorio);
  const serie = semSerie ? {} : obterSerie();
  const datas = [...new Set(Object.values(serie).flatMap((s) => s.x))].sort();
  return { serie, datas, snap: obterSnapshot() };
}

function linhasPainel(ctx, data) {
  let base;
  if (!data || !ctx.datas.length) {
    base = ctx.snap?.lista || [];                 // "hoje": estimativa oficial mais recente
  } else {
    base = Object.entries(ctx.serie).map(([name, s]) => {
      let i = -1;
      for (let k = 0; k < s.x.length && s.x[k] <= data; k++) i = k;
      return i < 0 ? null : { name, share: s.y[i], ci_lo: s.lo[i], ci_hi: s.hi[i] };
    }).filter(Boolean);
  }
  return base
    .filter((c) => c.share != null && (c.name !== "Indecisos" || appState.tipoVoto === "total"))
    .sort((a, b) => b.share - a.share)
    .slice(0, 10);
}

/** Data de fim de campo da pesquisa mais recente do território atual. */
function dataUltimaPesquisa() {
  const t = appState.territorio;
  return pesquisasDoTurno()
    .filter((p) => cargoUF() || t === "COMB" || p.scope === t)
    .reduce((m, p) => (p.dt_fim > m ? p.dt_fim : m), "") || null;
}

function renderizarPainel() {
  const ctx = contextoPainel();
  appState._painel = ctx;
  const uf = ehUF(appState.territorio) ? appState.territorio : "BR";
  $("painel-kicker").textContent = `${uf} — ${CARGOS[appState.cargo].toUpperCase()}`;
  $("painel-nome").textContent = nomeTerritorio();
  $("btn-voltar-presidente").style.display = cargoUF() ? "" : "none";
  $("painel-turnos").style.display = appState.cargo === "senado" ? "none" : "";

  const tem = ctx.datas.length > 1;
  $("painel-tempo").style.display = tem ? "" : "none";
  $("tempo-rodape").style.display = tem ? "" : "none";
  if (tem) {
    const sl = $("slider-data");
    sl.max = ctx.datas.length - 1;
    sl.value = indiceData(ctx.datas, appState.dataSel);
    const t0 = dataUTC(ctx.datas[0]).getTime(), t1 = dataUTC(ctx.datas[ctx.datas.length - 1]).getTime();
    let meses = `<span style="left:0%">${MESES[new Date(t0).getUTCMonth()]}</span>`;
    const d = new Date(t0);
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + 1);
    while (d.getTime() <= t1) {
      meses += `<span style="left:${(((d.getTime() - t0) / (t1 - t0)) * 100).toFixed(1)}%">${MESES[d.getUTCMonth()]}</span>`;
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
    $("tempo-meses").innerHTML = meses;
  }
  atualizarLinhasPainel();
}

function atualizarLinhasPainel() {
  const ctx = appState._painel;
  if (!ctx) return;
  const data = dataAtualPainel();
  atualizarRotulosGrafico();
  const linhas = linhasPainel(ctx, data);
  const snap = ctx.snap;

  if (!linhas.length) {
    $("painel-info").textContent = `${nomeTerritorio()} ainda não tem estimativa para este cenário.`;
    $("painel-linhas").innerHTML = "";
    $("data-chip").innerHTML = "";
    return;
  }

  const ultima = ctx.datas[ctx.datas.length - 1] || snap?.asOf;
  $("painel-info").textContent = data
    ? `Estimativa em ${formatarDataCurta(data)}`
    : `${snap?.n ?? "-"} pesquisas · até ${formatarDataCurta(dataUltimaPesquisa() || snap?.asOf || ultima)}${snap?.pair ? " · " + snap.pair.join(" × ") : ""}`;

  const escala = Math.max(...linhas.map((c) => c.ci_hi ?? c.share), 1) * 1.04;
  const pct = (v) => (Math.max(v, 0) / escala * 100).toFixed(1);
  $("painel-linhas").innerHTML = linhas.map((c) => {
    const lo = c.ci_lo != null ? Math.max(c.ci_lo, 0) : null, hi = c.ci_hi;
    const temIC = lo != null && hi != null && hi > lo;
    const partido = partidoDe(c.name, snap?.lista);
    return `<div class="linha-cand">
      <div class="cand-nome"><strong>${esc(c.name)}</strong>${partido ? `<span>${esc(partido)}</span>` : ""}</div>
      <div class="barra-track">
        <div class="barra-fill" style="width:${pct(c.share)}%; background:${corDe(c.name).line}"></div>
        ${temIC ? `<div class="barra-ic" style="left:${pct(lo)}%; width:${pct(hi - lo)}%"></div>` : ""}
      </div>
      <div class="cand-valor"><strong>${fmt(c.share)}%</strong>${temIC ? `<span>[${fmt(lo)}, ${fmt(hi)}]</span>` : ""}</div>
    </div>`;
  }).join("");

  if (ctx.datas.length > 1) {
    $("slider-data").value = indiceData(ctx.datas, data);
    const dt = dataUTC(data || dataUltimaPesquisa() || ultima);   // "hoje" mostra a última pesquisa, não o fim da semana do modelo
    $("data-chip").innerHTML =
      `<span class="chip-mes">${MESES[dt.getUTCMonth()].toUpperCase()}</span><span class="chip-dia">${dt.getUTCDate()}</span><span class="chip-sem">${DIAS_SEMANA[dt.getUTCDay()]}</span>`;
  }
}

// ---------------------------------------------------------------- chips de candidatos
function nomesVisiveisDisponiveis() {
  const snap = obterSnapshot();
  return (snap?.lista || []).map((c) => c.name);
}

function renderizarChips() {
  const cont = $("chips-candidatos");
  cont.innerHTML = nomesVisiveisDisponiveis().map((n) => {
    const off = appState.ocultos.has(n);
    return `<button class="chip-cand${off ? " off" : ""}" data-cand="${esc(n)}" style="--c:${corDe(n).line}"><span class="dot"></span>${esc(n)}</button>`;
  }).join("");
  cont.querySelectorAll(".chip-cand").forEach((b) => b.addEventListener("click", () => {
    const n = b.dataset.cand;
    appState.ocultos.has(n) ? appState.ocultos.delete(n) : appState.ocultos.add(n);
    renderizarChips();
    renderizarGraficoPrincipal();
  }));
}

// ---------------------------------------------------------------- gráfico principal
/** Remove spinner/mensagem que ficou dentro do contêiner antes de o Plotly desenhar. */
function limparContainer(cont) {
  if (cont.querySelector(".loading-indicator")) {
    try { Plotly.purge(cont); } catch (e) { /* sem gráfico anterior */ }
    cont.innerHTML = "";
  }
}

function estiloEixos() {
  const dark = appState.tema === "dark";
  const grade = dark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.06)";
  const tick = dark ? "#94a3b8" : "#64748b";
  return { dark, grade, tick, linha: dark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)" };
}

function renderizarGraficoPrincipal() {
  const cont = $("grafico-serie");
  if (!cont || typeof Plotly === "undefined" || !appState.dados) return;
  const titulo = $("serie-titulo"), desc = $("serie-desc");
  const turnoTxt = appState.turno === 1 ? "1º turno" : "2º turno";

  if (!cargoUF() && ehUF(appState.territorio)) return;   // presidente num estado: só o painel (não há série)

  const pref = cargoUF() ? `${CARGOS[appState.cargo]} · ` : "";
  const cen = cenariosDisponiveis();
  titulo.textContent = `${pref}${nomeTerritorio()} · tendência${appState.cargo === "senado" ? "" : ` (${turnoTxt}${cen.length > 1 ? `: ${cen[appState.cenario] || cen[0]}` : ""})`}`;
  desc.textContent = "Linhas: média ponderada; faixa: intervalo de confiança dos dois líderes; pontos: pesquisas individuais dos líderes (veja o instituto na tabela abaixo).";

  const serie = obterSerie();
  const todasDatas = Object.values(serie).flatMap((s) => s.x);
  if (!todasDatas.length) {
    cont.innerHTML = `<div class="loading-indicator"><p>${esc(nomeTerritorio())} ainda não tem série histórica para este cenário.</p></div>`;
    return;
  }
  const corte = dataCorte(todasDatas.reduce((a, b) => (a > b ? a : b)));
  const validos = appState.tipoVoto === "validos";
  const ultimo = (n) => serie[n].y[serie[n].y.length - 1];
  // Ordena pelo valor atual: define a ordem do tooltip e quem são os líderes
  const ordenados = Object.keys(serie).sort((a, b) => ultimo(b) - ultimo(a));
  const lideres = ordenados.filter((n) => !NAO_NOMINAIS.includes(n)).slice(0, 2);
  const nomes = ordenados.filter((n) => !appState.ocultos.has(n) && !(appState.semLideres && lideres.includes(n)));
  const e = estiloEixos();
  const traces = [];
  const fins = [];

  nomes.forEach((nome) => {
    const s = serie[nome], cores = corDe(nome), lider = lideres.includes(nome);
    const idx = s.x.map((x, i) => i).filter((i) => !corte || s.x[i] >= corte);
    const x = idx.map((i) => s.x[i]), y = idx.map((i) => s.y[i]);
    const lo = idx.map((i) => s.lo[i]), hi = idx.map((i) => s.hi[i]);
    if (!x.length) return;

    if (lider && lo.every((v) => v != null)) {
      traces.push({ x, y: lo, type: "scatter", mode: "lines", line: { width: 0 }, showlegend: false, hoverinfo: "skip" });
      traces.push({ x, y: hi, type: "scatter", mode: "lines", fill: "tonexty", fillcolor: cores.fill, line: { width: 0 }, showlegend: false, hoverinfo: "skip" });
    }
    traces.push({
      name: nome, x, y, type: "scatter", mode: "lines",
      line: { color: cores.line, width: lider ? 3 : 2.4, shape: "spline", smoothing: 0.6 },
      opacity: 1,
      hoverinfo: "skip"    // os valores aparecem no painel da direita conforme o mouse se move
    });
    if (fins.length < 8) fins.push({ nome, x: x[x.length - 1], y: y[y.length - 1], cor: cores.line });   // nomes já vêm em ordem de liderança
  });

  if (appState.mostrarPesquisas) {
    const pts = pontosPesquisas().filter((p) => !corte || p.date >= corte);
    const fundo = e.dark ? "#0f172a" : "#ffffff";
    nomes.forEach((nome) => {
      const chave = validos ? nome : nome + "_raw";
      const sel = pts.filter((p) => p[chave] != null);
      if (!sel.length) return;
      const lider = lideres.includes(nome);
      traces.push({
        name: `${nome} (pesquisas)`, x: sel.map((p) => p.date), y: sel.map((p) => p[chave]),
        type: "scatter", mode: "markers", showlegend: false, hoverinfo: "none",   // "none" não desenha etiqueta, mas ainda dispara o evento de hover
        marker: { color: corDe(nome).line, size: lider ? 8 : 6, opacity: lider ? 0.85 : 0.75, line: { width: 1.5, color: fundo } },
        meta: { pesq: true, nome, cor: corDe(nome).line, pts: sel.map((p) => ({ date: p.date, registro: p.registro, instituto: p.instituto, v: p[chave] })) }
      });
    });
  }

  // Rótulos no fim das linhas, afastados entre si para não se sobreporem
  const topoEscala = Math.max(...traces.flatMap((t) => (t.y || []).filter((v) => typeof v === "number")), 1) * 1.1;
  espalharRotulos(fins.map((f) => f.y), topoEscala).forEach((ry, i) => { fins[i].ry = ry; });
  cont._topo = topoEscala;
  const rotuloDe = (nome) => (cargoUF() ? nome : nome.split(" ").slice(-1)[0]);
  const rotulos = fins.map((f) => ({
    x: f.x, y: f.ry, xref: "x", yref: "y", xanchor: "left", xshift: 8, showarrow: false,
    text: `<b>${rotuloDe(f.nome)}</b> ${fmt(f.y)}%`,
    font: { color: f.cor, size: 12, family: "Inter, sans-serif" }
  }));
  cont._rotulos = fins.map((f) => ({ nome: f.nome, label: rotuloDe(f.nome) }));   // mesma ordem das anotações
  cont._serieRot = serie;

  // Escalas fixas: os rótulos do fim das linhas mudam de altura com o mouse e, sem isso, o Plotly
  // recalcularia o eixo a cada movimento (o gráfico "tremia").
  const todosY = traces.flatMap((t) => (t.y || []).filter((v) => typeof v === "number"));
  const todosX = traces.flatMap((t) => t.x || []).map(String).sort();
  const topo = Math.max(...todosY, 1) * 1.1;
  const dia = 86400000, fmtDia = (ms) => new Date(ms).toISOString().slice(0, 10);
  const rangeX = todosX.length
    ? [fmtDia(dataUTC(todosX[0].slice(0, 10)).getTime() - 2 * dia), fmtDia(dataUTC(todosX[todosX.length - 1].slice(0, 10)).getTime() + 2 * dia)]
    : undefined;   // tudo oculto: deixa o Plotly decidir

  limparContainer(cont);
  Plotly.react("grafico-serie", traces, {
    paper_bgcolor: "transparent", plot_bgcolor: "transparent", autosize: true, height: 520,
    font: { family: "Inter, sans-serif", color: e.tick },
    margin: { l: 44, r: cargoUF() ? 165 : 120, t: 10, b: 40 }, showlegend: false, annotations: rotulos,
    hovermode: "closest", hoverdistance: 12, dragmode: false,
    xaxis: {
      gridcolor: "transparent", tickfont: { color: e.tick, size: 12 }, linecolor: e.linha, tickformat: "%b/%y",
      range: rangeX, autorange: !rangeX, fixedrange: true
    },
    yaxis: {
      ticksuffix: "%", gridcolor: e.grade, griddash: "dot", tickfont: { color: e.tick, size: 12 },
      zeroline: false, showline: false, range: [0, topo], autorange: false, fixedrange: true
    }
  }, { responsive: true, displayModeBar: false }).then(() => ligarHoverPainel(cont));
}

/** Data que o painel está mostrando agora (mouse > controle > hoje). null = hoje. */
function dataAtualPainel() {
  const d = appState.dataHover != null ? appState.dataHover : appState.dataSel;
  return d === "hoje" ? null : d;
}

/** Afasta rótulos que ficariam sobrepostos: devolve a altura (y) ajustada de cada item, na mesma ordem. */
function espalharRotulos(valores, escala) {
  // O espaço mínimo depende da ESCALA FIXA do gráfico (altura do texto ≈ 3,4% do eixo), não dos valores do momento
  const gap = escala * 0.034;
  const ordem = valores.map((v, i) => ({ v, i })).filter((o) => o.v != null).sort((a, b) => a.v - b.v);
  const ry = valores.map(() => null);
  ordem.forEach((o, k) => { ry[o.i] = k === 0 ? o.v : Math.max(o.v, ry[ordem[k - 1].i] + gap); });
  return ry;
}

/** Atualiza texto E posição dos rótulos no fim das linhas para a data sob o mouse: eles sobem, descem e trocam de lugar. */
function atualizarRotulosGrafico() {
  const cont = $("grafico-serie");
  const rot = cont?._rotulos;
  if (!rot || !cont._fullLayout || typeof Plotly === "undefined" || !Plotly.relayout) return;
  const data = dataAtualPainel();
  const valores = rot.map((r) => {
    const s = cont._serieRot?.[r.nome];
    if (!s || !s.x.length) return null;
    let k = s.x.length - 1;
    if (data) {
      k = -1;
      for (let m = 0; m < s.x.length && s.x[m] <= data; m++) k = m;
    }
    return k < 0 ? null : s.y[k];
  });
  const ry = espalharRotulos(valores, cont._topo || 50);
  const upd = {};
  rot.forEach((r, i) => {
    const sem = valores[i] == null;   // candidato ainda sem dado nessa data: esconde o rótulo
    upd[`annotations[${i}].text`] = sem ? "" : `<b>${r.label}</b> ${fmt(valores[i])}%`;
    if (!sem) upd[`annotations[${i}].y`] = ry[i];
  });
  Plotly.relayout(cont, upd);
}

// ---------------------------------------------------------------- hover do gráfico de tendência: o painel acompanha o mouse
function ligarHoverPainel(cont) {
  ligarTooltipPesquisa(cont);      // os ouvintes do Plotly são refeitos a cada redesenho
  if (cont._hoverLigado) return;   // os ouvintes do mouse ficam no elemento, que sobrevive aos redesenhos
  cont._hoverLigado = true;
  let quadro = false;

  const sair = () => {
    if (appState.dataHover == null) return;
    appState.dataHover = null;
    atualizarLinhasPainel();
  };

  cont.addEventListener("mousemove", (ev) => {
    if (quadro) return;
    const clientX = ev.clientX;
    quadro = true;
    requestAnimationFrame(() => {
      quadro = false;
      const fl = cont._fullLayout;
      const datas = appState._painel?.datas || [];
      if (!fl?.xaxis?.range || datas.length < 2) return;
      const r = cont.getBoundingClientRect(), s = fl._size;
      const px = clientX - r.left;
      if (px < s.l || px > s.l + s.w) return sair();

      const ms = (v) => {
        if (typeof v === "number") return v;
        const t = String(v).replace(" ", "T").replace(/(\.\d{3})\d+/, "$1");
        return Date.parse((t.includes("T") ? t : t + "T00:00:00") + "Z");
      };
      const [a, b] = fl.xaxis.range.map(ms);
      const alvo = a + ((px - s.l) / s.w) * (b - a);
      let melhor = 0, dist = Infinity;
      datas.forEach((d, i) => {
        const dd = Math.abs(dataUTC(d).getTime() - alvo);
        if (dd < dist) { dist = dd; melhor = i; }
      });
      const nova = melhor === datas.length - 1 ? "hoje" : datas[melhor];
      if (nova !== appState.dataHover) {
        appState.dataHover = nova;
        atualizarLinhasPainel();
      }
    });
  });
  cont.addEventListener("mouseleave", sair);
}

// ---------------------------------------------------------------- cartão ao passar o mouse sobre uma pesquisa (ponto)
function ligarTooltipPesquisa(cont) {
  if (!cont.on) return;
  let tip = cont.querySelector(".tip-pesquisa");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tip-grafico tip-pesquisa";
    cont.appendChild(tip);
  }
  cont.removeAllListeners?.("plotly_hover");
  cont.removeAllListeners?.("plotly_unhover");
  cont.on("plotly_hover", (ev) => mostrarTooltipPesquisa(cont, tip, ev));
  cont.on("plotly_unhover", () => tip.classList.remove("visivel"));
}

function mostrarTooltipPesquisa(cont, tip, ev) {
  const ponto = (ev.points || []).find((p) => p.data?.meta?.pesq);
  if (!ponto) return;
  const m = ponto.data.meta, d = m.pts?.[ponto.pointIndex];
  if (!d) return;
  const q = pesquisasDoTurno().find((x) => x.registro === d.registro);   // amostra, método e período de campo
  const campo = q?.dt_inicio && q?.dt_fim ? `${formatarDataCurta(q.dt_inicio)} a ${formatarDataCurta(q.dt_fim)}` : formatarDataCurta(d.date);
  const linha = (k, v) => (v ? `<div class="tp-k">${k}</div><div class="tp-v">${v}</div>` : "");

  tip.style.setProperty("--c", m.cor);
  tip.innerHTML = `
    <div class="tp-head">
      <span class="tip-dot" style="background:${m.cor}"></span>
      <span class="tp-cand">${esc(m.nome)}</span>
      <span class="tp-valor">${fmt(d.v)}%</span>
    </div>
    <div class="tp-inst">${esc(d.instituto || q?.instituto || "Pesquisa")}</div>
    <div class="tp-grid">
      ${linha("Campo", esc(campo))}
      ${linha("Amostra", q?.n != null ? Number(q.n).toLocaleString("pt-BR") + " entrevistas" : "")}
      ${linha("Método", esc(q?.method || ""))}
      ${linha("Registro", `<span class="tp-reg">${esc(d.registro)}</span>`)}
    </div>`;

  const r = cont.getBoundingClientRect();
  const x = ev.event.clientX - r.left, y = ev.event.clientY - r.top;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = `${x + 16 + w > r.width ? Math.max(x - 16 - w, 4) : x + 16}px`;
  tip.style.top = `${Math.min(Math.max(y - h - 12, 4), Math.max(r.height - h - 4, 4))}px`;
  tip.classList.add("visivel");
}

// ---------------------------------------------------------------- tooltip (cartão) do gráfico por instituto
function ligarTooltipSerie(cont) {
  if (!cont.on) return;
  let tip = cont.querySelector(".tip-grafico");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tip-grafico";
    cont.appendChild(tip);
  }
  cont.removeAllListeners?.("plotly_hover");
  cont.removeAllListeners?.("plotly_unhover");
  cont.on("plotly_hover", (ev) => mostrarTooltipSerie(cont, tip, ev));
  cont.on("plotly_unhover", () => tip.classList.remove("visivel"));
}

function mostrarTooltipSerie(cont, tip, ev) {
  const todos = ev.points || [];
  const pts = todos.filter((p) => p.data?.meta?.nome && !p.data.meta.pesq);
  if (!pts.length) return;
  const linhas = pts.map((p) => ({ nome: p.data.meta.nome, lider: p.data.meta.lider, v: p.y, lo: p.data.meta.lo?.[p.pointIndex], hi: p.data.meta.hi?.[p.pointIndex], cor: p.data.line.color }))
    .sort((a, b) => b.v - a.v);
  const dt = dataUTC(String(pts[0].x).slice(0, 10));
  const data = dt.toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const info = pts[0].data.meta.info?.[pts[0].pointIndex];
  const semana = info || dt.toLocaleDateString("pt-BR", { weekday: "long", timeZone: "UTC" });

  const nominais = linhas.filter((l) => !NAO_NOMINAIS.includes(l.nome));
  const dif = nominais.length >= 2 ? nominais[0].v - nominais[1].v : null;

  // Pesquisas divulgadas exatamente neste dia (pontos do gráfico)
  const dia = String(pts[0].x).slice(0, 10);
  const grupos = {};
  todos.filter((p) => p.data?.meta?.pesq && String(p.x).slice(0, 10) === dia).forEach((p) => {
    const k = p.data.meta.info?.[p.pointIndex] || "Pesquisa";
    (grupos[k] ||= []).push({ nome: p.data.meta.nome, v: p.y });
  });
  const pesquisas = Object.entries(grupos).slice(0, 4).map(([info, vs]) => ({ info, vs: vs.sort((a, b) => b.v - a.v).slice(0, 3) }));

  tip.innerHTML = `
    <div class="tip-data"><strong>${esc(data)}</strong><span class="${info ? "tip-info" : ""}">${esc(semana)}</span></div>
    ${linhas.map((l) => `
      <div class="tip-linha${l.lider ? " tip-lider" : ""}">
        <span class="tip-dot" style="background:${l.cor}"></span>
        <span class="tip-nome">${esc(l.nome)}</span>
        <span class="tip-valor">${fmt(l.v)}%</span>
        ${l.lider && l.lo != null && l.hi != null ? `<span class="tip-ic">${fmt(Math.max(l.lo, 0))}–${fmt(l.hi)}</span>` : ""}
      </div>`).join("")}
    ${pesquisas.length ? `<div class="tip-pesq"><div class="tip-pesq-tit">Pesquisas neste dia</div>${pesquisas.map((g) => `
      <div class="tip-pesq-item"><strong>${esc(g.info)}</strong><span>${g.vs.map((v) => `${esc(v.nome.split(" ")[0])} ${fmt(v.v)}%`).join(" · ")}</span></div>`).join("")}</div>` : ""}
    ${dif != null ? `<div class="tip-dif"><span>Vantagem de ${esc(nominais[0].nome.split(" ")[0])}</span><strong>${fmt(dif)} p.p.</strong></div>` : ""}`;

  const r = cont.getBoundingClientRect();
  const x = ev.event.clientX - r.left, y = ev.event.clientY - r.top;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = `${x + 18 + w > r.width ? Math.max(x - 18 - w, 4) : x + 18}px`;
  tip.style.top = `${Math.min(Math.max(y - h / 2, 4), Math.max(r.height - h - 4, 4))}px`;
  tip.classList.add("visivel");
}

// ---------------------------------------------------------------- gráfico por instituto
const escopoInstituto = (p) => cargoUF() || p.scope === "BR";

function institutosNacionais() {
  const cont = {};
  pesquisasDoTurno().filter(escopoInstituto).forEach((p) => (cont[p.instituto] = (cont[p.instituto] || 0) + 1));
  return Object.entries(cont).sort((a, b) => b[1] - a[1]);
}

function renderizarSeletoresInstituto() {
  const nac = institutosNacionais();
  const g = $("sel-instituto-grafico");
  if (!nac.some(([n]) => n === appState.institutoGrafico)) appState.institutoGrafico = nac[0]?.[0] || "";
  g.innerHTML = nac.map(([n, c]) => `<option value="${esc(n)}">${esc(n)} (${c})</option>`).join("");
  g.value = appState.institutoGrafico;

  const t = $("sel-instituto-tabela");
  const escopo = pesquisasDoTurno().filter((p) => appState.territorio === "COMB" || (appState.territorio === "BR" ? p.scope === "BR" : p.scope === appState.territorio));
  const nomes = [...new Set(escopo.map((p) => p.instituto))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  if (appState.institutoTabela && !nomes.includes(appState.institutoTabela)) appState.institutoTabela = "";
  t.innerHTML = `<option value="">Todos os institutos</option>` + nomes.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  t.value = appState.institutoTabela;
}

function renderizarGraficoInstituto() {
  const cont = $("grafico-institutos");
  if (!cont || typeof Plotly === "undefined" || !appState.dados) return;
  $("inst-desc").textContent = cargoUF()
    ? "Evolução das pesquisas de um único instituto neste estado, como divulgadas."
    : "Evolução das pesquisas nacionais de um único instituto, como divulgadas (inclui indecisos).";
  const pesq = pesquisasDoTurno().filter((p) => escopoInstituto(p) && p.instituto === appState.institutoGrafico)
    .sort((a, b) => (a.dt_fim > b.dt_fim ? 1 : -1));
  if (!pesq.length) {
    cont.innerHTML = `<div class="loading-indicator"><p>Sem pesquisas deste instituto para o filtro atual.</p></div>`;
    return;
  }
  const media = (n) => pesq.reduce((t, p) => t + (p.shares[n] || 0), 0) / pesq.length;
  const nomes = [...new Set(pesq.flatMap((p) => Object.keys(p.shares)))].filter((n) => pesq.some((p) => p.shares[n] != null))
    .sort((a, b) => media(b) - media(a)).slice(0, 8);
  const e = estiloEixos();
  const lideres = nomes.filter((n) => !NAO_NOMINAIS.includes(n)).slice(0, 2);
  const traces = nomes.map((n) => {
    const sel = pesq.filter((p) => p.shares[n] != null);
    return {
      name: n, x: sel.map((p) => p.dt_fim), y: sel.map((p) => p.shares[n]), type: "scatter", mode: "lines+markers",
      line: { color: corDe(n).line, width: 2 }, marker: { size: 6 },
      hoverinfo: "none",   // cartão desenhado por mostrarTooltipSerie
      meta: { nome: n, lider: lideres.includes(n), info: sel.map((p) => `${p.instituto} · ${p.n != null ? "n=" + Number(p.n).toLocaleString("pt-BR") + " · " : ""}${p.registro}`) }
    };
  });
  limparContainer(cont);
  Plotly.react("grafico-institutos", traces, {
    paper_bgcolor: "transparent", plot_bgcolor: "transparent", autosize: true, height: 340,
    font: { family: "Inter, sans-serif", color: e.tick },
    margin: { l: 45, r: 25, t: 20, b: 45 }, hovermode: "x",
    legend: { orientation: "h", x: 0, y: 1.18, font: { color: e.dark ? "#e2e8f0" : "#1e293b", size: 12 } },
    xaxis: { gridcolor: e.grade, tickfont: { color: e.tick }, tickformat: "%b/%y", showspikes: true, spikemode: "across", spikethickness: 1, spikedash: "dot", spikecolor: e.tick },
    yaxis: { ticksuffix: "%", gridcolor: e.grade, griddash: "dot", tickfont: { color: e.tick }, rangemode: "tozero", zeroline: false, fixedrange: true }
  }, { responsive: true, displayModeBar: false }).then(() => ligarTooltipSerie(cont));
}

// ---------------------------------------------------------------- tabela
function renderizarTabelaPesquisas() {
  const tbody = $("tabela-corpo");
  if (!tbody || !appState.dados) return;
  const lista = pesquisasFiltradas();
  const paginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA));
  appState.pagina = Math.min(appState.pagina, paginas);
  const inicio = (appState.pagina - 1) * POR_PAGINA;

  $("tabela-titulo").textContent = `Pesquisas · ${cargoUF() ? CARGOS[appState.cargo] + " · " : ""}${nomeTerritorio()}${appState.cargo === "senado" ? "" : ` · ${appState.turno}º turno`} (${lista.length})`;
  document.querySelectorAll("th[data-ordem]").forEach((th) => {
    th.classList.toggle("ordenado", th.dataset.ordem === appState.ordem.col);
    th.dataset.dir = th.dataset.ordem === appState.ordem.col ? (appState.ordem.dir > 0 ? "asc" : "desc") : "";
  });

  if (!lista.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:2rem; color:var(--text-muted);">Nenhuma pesquisa encontrada para os filtros selecionados.</td></tr>`;
    $("tabela-pager").innerHTML = "";
    return;
  }

  tbody.innerHTML = lista.slice(inicio, inicio + POR_PAGINA).map((p) => {
    const chips = Object.entries(p.shares).filter(([, v]) => v != null)
      .sort((a, b) => b[1] - a[1]).slice(0, 6)
      .map(([n, v]) => `<span class="result-chip"><span class="dot-cor" style="background:${corDe(n).line}"></span> ${esc(n)}: <strong>${fmt(v)}%</strong></span>`).join("");
    const nome = p.url
      ? `<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer"><strong>${esc(p.instituto)}</strong></a>`
      : `<strong>${esc(p.instituto)}</strong>`;
    return `<tr>
      <td>${nome}</td>
      <td>${esc(p.scope)}</td>
      <td>${formatarData(p.dt_inicio)} a ${formatarData(p.dt_fim)}</td>
      <td>${p.n != null ? Number(p.n).toLocaleString("pt-BR") : "-"}</td>
      <td>${esc(p.method || "-")}</td>
      <td><span class="badge badge-tse">${esc(p.registro)}</span></td>
      <td><div class="results-mini-grid">${chips}</div></td>
    </tr>`;
  }).join("");

  const pager = $("tabela-pager");
  pager.innerHTML = paginas > 1
    ? `<button class="btn-action" id="pg-ant" ${appState.pagina === 1 ? "disabled" : ""}>${ico("left")} Anterior</button>
       <span>Página ${appState.pagina} de ${paginas}</span>
       <button class="btn-action" id="pg-prox" ${appState.pagina === paginas ? "disabled" : ""}>Próxima ${ico("right")}</button>`
    : "";
  $("pg-ant")?.addEventListener("click", () => { appState.pagina--; renderizarTabelaPesquisas(); });
  $("pg-prox")?.addEventListener("click", () => { appState.pagina++; renderizarTabelaPesquisas(); });
}

function exportarCSV() {
  const lista = pesquisasFiltradas();
  if (!lista.length) return mostrarAviso("Não há pesquisas para exportar com estes filtros.", true);
  const cands = [...new Set(lista.flatMap((p) => Object.keys(p.shares)))];
  const aspas = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const linhas = [["instituto", "uf", "registro", "inicio", "fim", "divulgacao", "amostra", "metodo", "url", ...cands].map(aspas).join(";")];
  lista.forEach((p) => linhas.push([p.instituto, p.scope, p.registro, p.dt_inicio, p.dt_fim, p.dt_divulgacao, p.n, p.method, p.url,
    ...cands.map((c) => (p.shares[c] == null ? "" : String(p.shares[c]).replace(".", ",")))].map(aspas).join(";")));
  const blob = new Blob(["﻿" + linhas.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `pesquisas_${appState.cargo}_${appState.territorio}_turno${appState.turno}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function formatarData(dataStr) {
  if (!dataStr) return "-";
  const [ano, mes, dia] = String(dataStr).slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}
