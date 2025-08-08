async function gerarBoleto(id) {
  try {
    const resp = await fetch(`/api/contas-receber/${id}/boleto`, { method: 'POST' });
    if (!resp.ok) throw new Error('Erro ao gerar boleto');
    const data = await resp.json();
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
    alert('Erro ao gerar boleto');
  }
}