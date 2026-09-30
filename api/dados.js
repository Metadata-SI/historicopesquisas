// Função da Vercel: busca os dados atuais do Plano Político (equivalente ao coleta/planopolitico.py).
// GET /api/dados?cargo=presidente|governador|senado
// Cada cargo é uma chamada separada para ficar abaixo do limite de 4,5 MB de resposta da Vercel.

const BASE = "https://planopolitico.com.br/agregador/";
const PAGINAS = { presidente: "presidente/", governador: "governadores/", senado: "senado/" };
const UA = "Mozilla/5.0 (compatible; AgregadorPesquisas/1.0)";

function bloco(html, id) {
  const m = html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)</script>`));
  return m ? JSON.parse(m[1]) : null;
}

// var NOME = { 'Candidato': 'valor', ... };
function dicionario(html, nome) {
  const m = html.match(new RegExp(`var ${nome} = \\{([\\s\\S]*?)\\n\\s*\\};`));
  const out = {};
  if (m) for (const [, k, v] of m[1].matchAll(/'([^']+)'\s*:\s*'([^']*)'/g)) out[k] = v;
  return out;
}

module.exports = async (req, res) => {
  const cargo = String(req.query?.cargo || "presidente");
  if (!PAGINAS[cargo]) return res.status(400).json({ ok: false, erro: "cargo inválido" });

  try {
    const r = await fetch(BASE + PAGINAS[cargo], { headers: { "User-Agent": UA } });
    if (!r.ok) throw new Error(`Plano Político respondeu HTTP ${r.status}`);
    const html = await r.text();
    const agg = bloco(html, "agg-data");
    if (!agg) throw new Error("Bloco agg-data não encontrado: o layout do Plano Político mudou.");

    let corpo;
    if (cargo === "presidente") {
      for (const k of ["presidente_t1", "presidente_t2", "presidente_state"]) {
        if (!agg[k]) throw new Error(`Campo ${k} ausente nos dados do Plano Político.`);
      }
      corpo = { ...agg, mapa: bloco(html, "br-map-data"), meta: { partido: dicionario(html, "PARTY"), cores: dicionario(html, "COLORS") } };
    } else {
      if (!agg[cargo]?.states) throw new Error(`Campo ${cargo} ausente nos dados do Plano Político.`);
      corpo = { [cargo]: agg[cargo] };
    }

    // 5 min no cache da Vercel: muitos cliques em "Atualizar" não sobrecarregam o Plano Político
    res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=600");
    return res.status(200).json(corpo);
  } catch (e) {
    return res.status(502).json({ ok: false, erro: String(e.message || e) });
  }
};
