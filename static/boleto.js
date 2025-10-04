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
    const normalizePath = (p) => {
      if (!p) {
        return null;
      }
      if (typeof p !== 'string') {
        p = String(p);
      }
      if (p.startsWith('/')) {
        return p;
      }
      const cleaned = p.replace(/\\/g, '/');
      const idx = cleaned.indexOf('/uploads/');
      if (idx >= 0) {
        return cleaned.substring(idx);
      }
      return cleaned;
    };
    const pdfTargets = (data.pdf_urls && data.pdf_urls.length ? data.pdf_urls : data.pdfs) || [];
    pdfTargets.forEach((p) => {
      const url = normalizePath(p) || p;
      if (url) {
        window.location.href = url;
      }
    });
    const remessaTarget = data.remessa_url || data.remessa;
    if (remessaTarget) {
      const remUrl = normalizePath(remessaTarget) || remessaTarget;
      window.open(remUrl, '_blank');
    }
  } catch (err) {
    alert((err && err.message) || 'Erro ao gerar boleto');
  }
}

(function () {
  const currencyFmt = new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
  });

  const escapeMap = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };

  const state = {
    titulos: [],
    selecionados: new Set(),
  };

  let nodes = null;
  let initialized = false;

  const getNodes = () => nodes || {};

  const escapeHtml = (value) => {
    if (value == null) {
      return '';
    }
    return String(value).replace(/[&<>"']/g, (ch) => escapeMap[ch] || ch);
  };

  const formatDate = (value) => {
    if (!value) {
      return '';
    }
    const parts = String(value).split('-');
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return value;
  };

  const resetState = () => {
    state.titulos = [];
    state.selecionados = new Set();
    if (!nodes) {
      return;
    }
    nodes.tbody.innerHTML = '';
    nodes.total.textContent = '';
    nodes.selectAll.checked = false;
    nodes.result.style.display = 'none';
  };

  const updateSummary = () => {
    if (!nodes) {
      return;
    }
    const totalSelecionados = state.selecionados.size;
    const totalTitulos = state.titulos.length;
    nodes.total.textContent = `Selecionados: ${totalSelecionados} de ${totalTitulos}`;
    nodes.selectAll.checked = totalTitulos > 0 && totalSelecionados === totalTitulos;
  };

  const handleRowSelection = (event) => {
    const input = event.target;
    const id = parseInt(input.value, 10);
    if (Number.isNaN(id)) {
      return;
    }
    if (input.checked) {
      state.selecionados.add(id);
    } else {
      state.selecionados.delete(id);
    }
    updateSummary();
  };

  const renderTitulos = () => {
    if (!nodes) {
      return;
    }
    const rows = state.titulos
      .map((titulo) => {
        const checked = state.selecionados.has(titulo.id) ? 'checked' : '';
        return (
          '<tr>' +
          `<td class="px-3 py-2"><input type="checkbox" class="form-checkbox" value="${titulo.id}" ${checked} /></td>` +
          `<td class="px-3 py-2 text-gray-700">#${titulo.id}</td>` +
          `<td class="px-3 py-2 text-gray-700">${escapeHtml(titulo.titulo)}</td>` +
          `<td class="px-3 py-2 text-gray-700">${formatDate(titulo.data_vencimento)}</td>` +
          `<td class="px-3 py-2 text-gray-700">${currencyFmt.format(titulo.valor_previsto || 0)}</td>` +
          `<td class="px-3 py-2 text-gray-700">${escapeHtml(titulo.status_conta || '')}</td>` +
          `<td class="px-3 py-2 text-gray-700">${escapeHtml(titulo.contrato_label || '')}</td>` +
          '</tr>'
        );
      })
      .join('');

    nodes.tbody.innerHTML = rows;
    Array.from(nodes.tbody.querySelectorAll("input[type='checkbox']")).forEach((input) => {
      input.addEventListener('change', handleRowSelection);
    });

    nodes.result.style.display = state.titulos.length ? 'block' : 'none';
    updateSummary();
  };

  const carregarContratos = async (clienteId) => {
    nodes.contrato.disabled = true;
    nodes.contrato.innerHTML = '<option value="">Todos</option>';
    if (!clienteId) {
      return;
    }
    try {
      const resp = await fetch(`/api/contas-receber/clientes/${clienteId}/contratos`);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        nodes.feedback.textContent = data.error || 'Falha ao carregar contratos.';
        return;
      }
      const contratos = data.contratos || [];
      contratos.forEach((contrato) => {
        const opt = document.createElement('option');
        opt.value = contrato.id;
        opt.textContent = contrato.descricao || `Contrato ${contrato.id}`;
        nodes.contrato.appendChild(opt);
      });
      nodes.contrato.disabled = contratos.length === 0;
    } catch (err) {
      nodes.feedback.textContent = (err && err.message) || 'Falha ao carregar contratos.';
    }
  };

  const buscarTitulos = async () => {
    nodes.feedback.textContent = '';
    resetState();
    const clienteId = (nodes.cliente.value || '').trim();
    if (!clienteId) {
      nodes.feedback.textContent = 'Selecione um cliente.';
      return;
    }
    const contratoId = (nodes.contrato.value || '').trim();
    const params = new URLSearchParams();
    params.append('cliente_id', clienteId);
    if (contratoId) {
      params.append('contrato_id', contratoId);
    }
    try {
      const resp = await fetch(`/api/contas-receber/titulos?${params.toString()}`);
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        nodes.feedback.textContent = data.error || 'Falha ao carregar titulos.';
        return;
      }
      state.titulos = data.titulos || [];
      if (!state.titulos.length) {
        nodes.feedback.textContent = 'Nenhum titulo encontrado para os filtros informados.';
        return;
      }
      state.selecionados = new Set(state.titulos.map((item) => item.id));
      nodes.selectAll.checked = true;
      renderTitulos();
    } catch (err) {
      nodes.feedback.textContent = (err && err.message) || 'Falha ao carregar titulos.';
    }
  };

  const toggleSelectAll = (checked) => {
    if (!state.titulos.length) {
      nodes.selectAll.checked = false;
      return;
    }
    state.selecionados = checked
      ? new Set(state.titulos.map((item) => item.id))
      : new Set();
    Array.from(nodes.tbody.querySelectorAll("input[type='checkbox']")).forEach((input) => {
      const id = parseInt(input.value, 10);
      input.checked = state.selecionados.has(id);
    });
    updateSummary();
  };

  const openModal = () => {
    resetState();
    nodes.feedback.textContent = '';
    nodes.cliente.value = '';
    nodes.contrato.innerHTML = '<option value="">Todos</option>';
    nodes.contrato.disabled = true;
    nodes.modal.style.display = 'flex';
  };

  const closeModal = () => {
    nodes.modal.style.display = 'none';
  };

  const abrirPreview = () => {
    if (!state.selecionados.size) {
      nodes.feedback.textContent = 'Selecione ao menos um titulo.';
      return;
    }
    const ids = Array.from(state.selecionados).join(',');
    const url = `/api/contas-receber/boleto/lote?ids=${ids}`;
    window.location.href = url;
    closeModal();
  };

  const onClienteChange = (event) => {
    nodes.feedback.textContent = '';
    carregarContratos(event.target.value);
  };

  const onBackdropClick = (event) => {
    if (event.target === nodes.modal) {
      closeModal();
    }
  };

  const onKeyDown = (event) => {
    if (event.key === 'Escape' && nodes.modal.style.display === 'flex') {
      closeModal();
    }
  };

  const cacheNodes = () => {
    nodes = {
      modal: document.getElementById('lote-modal'),
      cliente: document.getElementById('lote-cliente'),
      contrato: document.getElementById('lote-contrato'),
      feedback: document.getElementById('lote-feedback'),
      result: document.getElementById('lote-result'),
      tbody: document.getElementById('lote-tbody'),
      total: document.getElementById('lote-total'),
      selectAll: document.getElementById('lote-select-all'),
    };
    return Object.values(nodes).every(Boolean);
  };

  const init = () => {
    if (initialized) {
      return true;
    }
    if (!cacheNodes()) {
      nodes = null;
      return false;
    }
    nodes.cliente.addEventListener('change', onClienteChange);
    nodes.modal.addEventListener('click', onBackdropClick);
    window.addEventListener('keydown', onKeyDown);
    nodes.selectAll.addEventListener('change', (event) => {
      toggleSelectAll(event.target.checked);
    });
    initialized = true;
    resetState();
    return true;
  };

  const ensureInit = () => {
    if (initialized) {
      return true;
    }
    return init();
  };

  const wrap = (fn) => {
    return function wrapped() {
      if (!ensureInit()) {
        return;
      }
      return fn.apply(null, arguments);
    };
  };

  window.openLoteModal = wrap(openModal);
  window.closeLoteModal = wrap(closeModal);
  window.buscarTitulosLote = wrap(buscarTitulos);
  window.toggleSelectAllLote = (element) => {
    if (!ensureInit()) {
      return;
    }
    toggleSelectAll(element && element.checked);
  };
  window.abrirPreviewLote = wrap(abrirPreview);

  if (document.readyState !== 'loading') {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
