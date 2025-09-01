function visualizarBoleto(id) {
  window.open(`/api/contas-receber/${id}/boleto`, '_blank');
}

async function gerarBoleto(id) {
  try {
    const resp = await fetch(`/api/contas-receber/${id}/boleto`, { method: 'POST' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      alert(data.error || 'Erro ao gerar boleto');
      return;
    }
    const toUrl = (p) => {
      const unixIdx = p.indexOf('/uploads/');
      if (unixIdx >= 0) {
        return '/uploads/' + p.substring(unixIdx + 9);
      }
      const winIdx = p.indexOf('\\uploads\\');
      if (winIdx >= 0) {
        return '/uploads/' + p.substring(winIdx + 9).replace(/\\\\/g, '/');
      }
      return p;
    };
    (data.pdfs || []).forEach((p) => {
      window.open(toUrl(p), '_blank');
    });
    if (data.remessa) {
      window.open(toUrl(data.remessa), '_blank');
    }
  } catch (err) {
    alert(err.message || 'Erro ao gerar boleto');
  }
}