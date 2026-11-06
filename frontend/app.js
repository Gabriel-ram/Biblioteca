/**
 * BiblioTech — Sistema de Gestión de Biblioteca Universitaria
 * Controlador Frontend Modernizado
 */

// Rutas de API a través del reverse proxy Caddy
const API = {
    cat: '/api/catalogo',
    pre: '/api/prestamos',
    not: '/api/notificaciones'
};

// Selectores auxiliares
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// Escape seguro de caracteres HTML
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
}[c]));

// Extracción de datos de formularios
const fd = f => Object.fromEntries(new FormData(f));

// Renderizado de etiquetas visuales (badges)
const bd = (text, cls, dot = true) => `
  <span class="b ${cls || ''}">
    ${dot ? '<span class="badge-dot"></span>' : ''}
    ${esc(text)}
  </span>
`;

// Variables globales de estado
let curTab = 'estado';
let autoRefreshTimer = null;

// Caché local para filtrado y búsqueda instantánea en cliente
const cache = {
    libros: [],
    autoresMap: {},
    usuarios: [],
    prestamos: [],
    notificaciones: []
};

// =============================================================================
// SISTEMA DE NOTIFICACIONES TOAST
// =============================================================================

function toast(msg, isError = false, title = null) {
    const container = $('#toast-container');
    if (!container) return;

    const item = document.createElement('div');
    const type = isError ? 'toast-error' : 'toast-success';
    item.className = `toast-item ${type}`;

    const defaultTitle = isError ? 'Atención / Error' : 'Operación exitosa';
    const iconSvg = isError
        ? `<svg class="toast-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
         <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>
       </svg>`
        : `<svg class="toast-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
         <polyline points="20 6 9 17 4 12"/>
       </svg>`;

    item.innerHTML = `
    ${iconSvg}
    <div class="toast-body">
      <div class="toast-title">${esc(title || defaultTitle)}</div>
      <div class="toast-msg">${esc(msg)}</div>
    </div>
    <button type="button" class="toast-dismiss" aria-label="Cerrar notificación">
      <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/>
      </svg>
    </button>
  `;

    const dismiss = () => {
        item.classList.add('removing');
        setTimeout(() => { if (item.parentNode) item.remove(); }, 200);
    };

    item.querySelector('.toast-dismiss').onclick = dismiss;
    container.appendChild(item);

    // Auto-cierre tras 5.5 segundos
    setTimeout(dismiss, 5500);

    // Mantener compatibilidad con elemento #toast oculto
    const legacyToast = $('#toast');
    if (legacyToast) {
        legacyToast.textContent = msg;
        legacyToast.className = isError ? 'er' : '';
    }
}

// =============================================================================
// SISTEMA DE MODAL REUTILIZABLE
// =============================================================================

function showModal({ title, bodyHtml, confirmText = 'Aceptar', cancelText = 'Cancelar', confirmClass = 'btn-primary', onConfirm = null }) {
    const backdrop = $('#modalBackdrop');
    const titleEl = $('#modalTitle');
    const bodyEl = $('#modalBody');
    const footerEl = $('#modalFooter');

    titleEl.textContent = title;
    bodyEl.innerHTML = bodyHtml;

    footerEl.innerHTML = `
    <button type="button" class="btn btn-secondary" id="modalBtnCancel">${esc(cancelText)}</button>
    <button type="button" class="btn ${confirmClass}" id="modalBtnConfirm">${esc(confirmText)}</button>
  `;

    const closeModal = () => {
        backdrop.classList.remove('open');
        backdrop.setAttribute('aria-hidden', 'true');
    };

    $('#modalCloseBtn').onclick = closeModal;
    $('#modalBtnCancel').onclick = closeModal;
    backdrop.onclick = e => { if (e.target === backdrop) closeModal(); };

    $('#modalBtnConfirm').onclick = async () => {
        if (onConfirm) {
            const shouldClose = await onConfirm();
            if (shouldClose !== false) closeModal();
        } else {
            closeModal();
        }
    };

    backdrop.classList.add('open');
    backdrop.setAttribute('aria-hidden', 'false');
}

// =============================================================================
// COMUNICACIÓN ASÍNCRONA CON MICROSERVICIOS (FETCH WRAPPER)
// =============================================================================

async function api(url, method = 'GET', body = null) {
    const options = {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : {}
    };
    if (body) {
        options.body = JSON.stringify(body);
    }

    const r = await fetch(url, options);

    // DELETE y respuestas sin contenido (204)
    if (r.status === 204) return null;

    let data = null;
    try {
        data = await r.json();
    } catch {
        // Si no es JSON legible
    }

    if (!r.ok) {
        const errorMsg = (data && (data.error || data.mensaje || data.detalle)) || `Error HTTP ${r.status}`;
        throw new Error(errorMsg);
    }

    return data;
}

// Formateo de fecha legible
function formatearFecha(isoDate) {
    if (!isoDate) return '—';
    try {
        const d = new Date(isoDate);
        if (isNaN(d.getTime())) return String(isoDate).slice(0, 10);
        return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
        return String(isoDate).slice(0, 10);
    }
}

// Comprobación de préstamo vencido
function esPrestamoVencido(fechaLimiteStr) {
    if (!fechaLimiteStr) return { vencido: false, dias: 0 };
    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);

    const limite = new Date(fechaLimiteStr);
    limite.setHours(0, 0, 0, 0);

    const diffMs = hoy.getTime() - limite.getTime();
    const diffDias = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    return { vencido: diffDias > 0, dias: diffDias };
}

// =============================================================================
// 1. PANEL PRINCIPAL Y MONITOREO DE MICROSERVICIOS
// =============================================================================

async function loadEstado() {
    const servicios = [
        { name: 'Catálogo', port: 8001, url: API.cat, pillId: '#pill-cat' },
        { name: 'Préstamos', port: 8002, url: API.pre, pillId: '#pill-pre' },
        { name: 'Notificaciones', port: 8003, url: API.not, pillId: '#pill-not' }
    ];

    // Comprobar salud con timeout de 3 segundos
    const resultados = await Promise.all(servicios.map(async s => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const start = performance.now();
        try {
            const res = await fetch(s.url + '/health', { signal: controller.signal });
            const elapsed = Math.round(performance.now() - start);
            const isOk = res.ok;
            const data = isOk ? await res.json() : null;
            return { ...s, ok: isOk, data, latency: elapsed };
        } catch {
            return { ...s, ok: false, data: null, latency: null };
        } finally {
            clearTimeout(timeout);
        }
    }));

    // Actualizar indicadores compactos en la barra superior
    resultados.forEach(s => {
        const pill = $(s.pillId);
        if (pill) {
            pill.className = `service-pill ${s.ok ? 'up' : 'down'}`;
        }
    });

    // Renderizar tarjetas de microservicios
    $('#svc').innerHTML = resultados.map(s => `
    <div class="service-card ${s.ok ? 'is-up' : 'is-down'}">
      <div class="service-card-header">
        <div class="service-title-wrap">
          <div class="service-icon-box">
            <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
              <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
              <line x1="6" x2="6.01" y1="6" y2="6"/>
              <line x1="6" x2="6.01" y1="18" y2="18"/>
            </svg>
          </div>
          <div>
            <h3 class="service-name">Servicio de ${esc(s.name)}</h3>
            <span class="service-endpoint">:${s.port} · ${esc(s.url)}/health</span>
          </div>
        </div>
        <span class="service-status-pill ${s.ok ? 'up' : 'down'}">
          <span class="status-dot"></span>
          ${s.ok ? 'EN LÍNEA' : 'FUERA DE SERVICIO'}
        </span>
      </div>
      <div class="service-card-body">
        <div class="service-meta-row">
          <span class="service-meta-label">Latencia de respuesta:</span>
          <span class="service-meta-val">${s.latency !== null ? `${s.latency} ms` : 'Sin respuesta'}</span>
        </div>
        <div class="service-meta-row">
          <span class="service-meta-label">Estado de conexión:</span>
          <span class="service-meta-val">${s.ok ? 'Operativo y saludable' : 'Contenedor inaccesible'}</span>
        </div>
        ${s.data && s.data.pendientes !== undefined ? `
          <div class="service-meta-row">
            <span class="service-meta-label">Cola de correos:</span>
            <span class="service-meta-val" style="color: ${s.data.pendientes > 0 ? 'var(--warning-tx)' : 'var(--success-tx)'}; font-weight:700;">
              ${s.data.pendientes} pendiente(s)
            </span>
          </div>
        ` : ''}
      </div>
    </div>
  `).join('');

    // Cargar métricas reales en segundo plano sin bloquear
    cargarMetricasDashboard(resultados);
}

async function cargarMetricasDashboard(serviciosSalud) {
    const catSalud = serviciosSalud.find(x => x.name === 'Catálogo');
    const preSalud = serviciosSalud.find(x => x.name === 'Préstamos');
    const notSalud = serviciosSalud.find(x => x.name === 'Notificaciones');

    // 1. Estadísticas de Catálogo
    if (catSalud && catSalud.ok) {
        try {
            const libros = await api(API.cat + '/libros');
            const totalLibros = libros.length;
            const totalEjemplares = libros.reduce((acc, l) => acc + (l.ejemplares_totales || 0), 0);
            const totalDisponibles = libros.reduce((acc, l) => acc + (l.ejemplares_disponibles || 0), 0);
            $('#stat-total-libros').textContent = totalLibros;
            $('#stat-libros-sub').textContent = `${totalDisponibles} de ${totalEjemplares} ejemplares disponibles`;
        } catch {
            $('#stat-total-libros').textContent = '—';
            $('#stat-libros-sub').textContent = 'Error al cargar inventario';
        }
    } else {
        $('#stat-total-libros').textContent = '—';
        $('#stat-libros-sub').textContent = 'Catálogo fuera de servicio';
    }

    // 2. Estadísticas de Usuarios
    if (preSalud && preSalud.ok) {
        try {
            const usuarios = await api(API.pre + '/usuarios');
            const activos = usuarios.filter(u => +u.activo === 1).length;
            const estudiantes = usuarios.filter(u => u.tipo === 'ESTUDIANTE').length;
            const docentes = usuarios.filter(u => u.tipo === 'DOCENTE').length;
            $('#stat-total-usuarios').textContent = activos;
            $('#stat-usuarios-sub').textContent = `${estudiantes} estudiantes · ${docentes} docentes`;
        } catch {
            $('#stat-total-usuarios').textContent = '—';
            $('#stat-usuarios-sub').textContent = 'Error al cargar usuarios';
        }
    } else {
        $('#stat-total-usuarios').textContent = '—';
        $('#stat-usuarios-sub').textContent = 'Préstamos fuera de servicio';
    }

    // 3. Estadísticas de Préstamos
    if (preSalud && preSalud.ok) {
        try {
            const prestamos = await api(API.pre + '/prestamos');
            const activos = prestamos.filter(p => p.estado === 'ACTIVO');
            const vencidos = activos.filter(p => esPrestamoVencido(p.fecha_limite).vencido).length;
            $('#stat-total-prestamos').textContent = activos.length;
            $('#stat-prestamos-sub').textContent = vencidos > 0
                ? `⚠️ ${vencidos} préstamo(s) con retraso`
                : 'Todos los préstamos al día';
            if (vencidos > 0) {
                $('#stat-prestamos-sub').style.color = 'var(--danger)';
                $('#stat-prestamos-sub').style.fontWeight = '700';
            } else {
                $('#stat-prestamos-sub').style.color = '';
                $('#stat-prestamos-sub').style.fontWeight = '';
            }
        } catch {
            $('#stat-total-prestamos').textContent = '—';
            $('#stat-prestamos-sub').textContent = 'Error al cargar préstamos';
        }
    } else {
        $('#stat-total-prestamos').textContent = '—';
        $('#stat-prestamos-sub').textContent = 'Préstamos fuera de servicio';
    }

    // 4. Estadísticas de Notificaciones
    if (notSalud && notSalud.ok) {
        try {
            const notifs = await api(API.not + '/notificaciones');
            const enviadas = notifs.filter(n => n.estado === 'ENVIADA').length;
            const fallidas = notifs.filter(n => n.estado === 'FALLIDA').length;
            const pendientes = notifs.filter(n => n.estado === 'PENDIENTE').length;
            $('#stat-total-notifs').textContent = notifs.length;
            $('#stat-notifs-sub').textContent = `${enviadas} enviadas · ${pendientes} en cola · ${fallidas} fallidas`;

            // Badge en el sidebar si hay pendientes o fallidas
            const badge = $('#sidebar-notif-badge');
            if (badge) {
                const atencion = pendientes + fallidas;
                if (atencion > 0) {
                    badge.textContent = atencion;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            }
        } catch {
            $('#stat-total-notifs').textContent = '—';
            $('#stat-notifs-sub').textContent = 'Error al cargar historial';
        }
    } else {
        $('#stat-total-notifs').textContent = '—';
        $('#stat-notifs-sub').textContent = 'Notificaciones fuera de línea';
    }
}

// =============================================================================
// VISTA DE USUARIO / LECTOR (CONSULTA Y DISPONIBILIDAD DE UNIDADES)
// =============================================================================

async function loadVistaUsuario() {
    try {
        const [autores, libros] = await Promise.all([
            api(API.cat + '/autores'),
            api(API.cat + '/libros')
        ]);
        cache.libros = libros || [];
        cache.autoresMap = Object.fromEntries((autores || []).map(a => [a.id, a.nombre]));

        const selAutor = $('#filter-user-autor');
        if (selAutor) {
            const curVal = selAutor.value;
            selAutor.innerHTML = '<option value="">Todos los autores</option>' +
                (autores || []).map(a => `<option value="${a.id}">${esc(a.nombre)}</option>`).join('');
            if (curVal) selAutor.value = curVal;
        }

        renderTablaUserLibros();
    } catch (err) {
        const countBadge = $('#count-user-libros');
        if (countBadge) countBadge.textContent = '0 libros (fuera de línea)';
        const container = $('#t-user-libros');
        if (container) {
            container.innerHTML = `
                <div class="empty-state">
                  <h4 class="empty-state-title">Servicio de Catálogo Inaccesible</h4>
                  <p class="empty-state-desc">No se pudo conectar con el microservicio de Catálogo para cargar los libros.</p>
                </div>
            `;
        }
    }
}

function renderTablaUserLibros() {
    const searchVal = ($('#filter-user-search')?.value || '').toLowerCase().trim();
    const autorFilter = $('#filter-user-autor')?.value || '';
    const activePill = $('.filter-pill[data-user-filter-disp].active');
    const dispFilter = activePill ? activePill.dataset.userFilterDisp : 'all';

    let list = (cache.libros || []).filter(libro => {
        const autorNombre = cache.autoresMap[libro.autor_id] || '';
        const matchSearch = !searchVal ||
            String(libro.titulo || '').toLowerCase().includes(searchVal) ||
            autorNombre.toLowerCase().includes(searchVal) ||
            String(libro.id).includes(searchVal);

        if (!matchSearch) return false;
        if (autorFilter && String(libro.autor_id) !== String(autorFilter)) return false;

        if (dispFilter === 'available') return Number(libro.ejemplares_disponibles) > 0;
        if (dispFilter === 'out') return Number(libro.ejemplares_disponibles) <= 0;
        return true;
    });

    const countBadge = $('#count-user-libros');
    if (countBadge) countBadge.textContent = `${list.length} de ${(cache.libros || []).length} libros`;

    const container = $('#t-user-libros');
    if (!container) return;

    if (list.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
              <h4 class="empty-state-title">No se encontraron libros</h4>
              <p class="empty-state-desc">Ningún libro coincide con el criterio de búsqueda o filtros seleccionados.</p>
            </div>
        `;
        return;
    }

    const rows = list.map(x => {
        const autor = cache.autoresMap[x.autor_id] || '—';
        const isDisponible = x.estado === 'DISPONIBLE' && Number(x.ejemplares_disponibles) > 0;
        const total = Number(x.ejemplares_totales) || 1;
        const disp = Number(x.ejemplares_disponibles) || 0;
        const ratio = total > 0 ? Math.round((disp / total) * 100) : 0;

        return `
            <tr>
              <td class="td-id">#${x.id}</td>
              <td>
                <div class="td-title-cell">
                  <svg class="svg-icon" style="color:var(--primary); width:16px; height:16px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                  </svg>
                  <strong style="color:var(--text);">${esc(x.titulo)}</strong>
                </div>
              </td>
              <td>${esc(autor)}</td>
              <td>
                <div class="stock-pill" title="${disp} de ${total} unidades disponibles">
                  <span style="font-weight: 600;">${disp} de ${total} disp.</span>
                  <div class="stock-bar-wrap">
                    <div class="stock-bar-fill ${ratio === 0 ? 'empty' : ''}" style="width: ${ratio}%; ${isDisponible ? 'background: #10b981;' : 'background: #ef4444;'}"></div>
                  </div>
                </div>
              </td>
              <td>${bd(isDisponible ? 'DISPONIBLE' : 'AGOTADO', isDisponible ? 'ok' : 'er')}</td>
              <td>
                <span class="badge badge-neutral" style="font-size: 11px;">Solo consulta</span>
              </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Título</th>
              <th>Autor</th>
              <th>Unidades Disponibles</th>
              <th>Estado</th>
              <th>Acceso</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
    `;
}

// =============================================================================
// 2. CATÁLOGO DE LIBROS Y AUTORES
// =============================================================================

async function loadCatalogo() {
    const alertBanner = $('#cat-down-alert');
    try {
        const [autores, libros] = await Promise.all([
            api(API.cat + '/autores'),
            api(API.cat + '/libros')
        ]);

        if (alertBanner) alertBanner.style.display = 'none';
        cache.libros = libros || [];
        cache.autoresMap = Object.fromEntries((autores || []).map(a => [a.id, a.nombre]));

        // Actualizar selector de autores en el formulario de nuevo libro
        const selAutor = $('#sel-autor');
        if (selAutor) {
            selAutor.innerHTML = '<option value="">(Opcional) Sin autor asignado</option>' +
                (autores || []).map(a => `<option value="${a.id}">${esc(a.nombre)}${a.nacionalidad ? ` (${esc(a.nacionalidad)})` : ''}</option>`).join('');
        }

        const btnSaveAutor = $('#btn-save-autor');
        const btnSaveLibro = $('#btn-save-libro');
        if (btnSaveAutor) btnSaveAutor.disabled = false;
        if (btnSaveLibro) btnSaveLibro.disabled = false;

        renderTablaLibros();
    } catch (err) {
        if (alertBanner) alertBanner.style.display = 'flex';
        cache.libros = [];
        cache.autoresMap = {};
        const selAutor = $('#sel-autor');
        if (selAutor) selAutor.innerHTML = '<option value="">⚠️ Catálogo no disponible</option>';
        const btnSaveAutor = $('#btn-save-autor');
        const btnSaveLibro = $('#btn-save-libro');
        if (btnSaveAutor) btnSaveAutor.disabled = true;
        if (btnSaveLibro) btnSaveLibro.disabled = true;

        const countBadge = $('#count-libros');
        if (countBadge) countBadge.textContent = '0 libros (fuera de línea)';

        const container = $('#t-libros');
        if (container) {
            container.innerHTML = `
        <div class="empty-state">
          <svg class="empty-state-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" x2="12" y1="8" y2="12"/>
            <line x1="12" x2="12.01" y1="16" y2="16"/>
          </svg>
          <h4 class="empty-state-title">Servicio de Catálogo Inaccesible</h4>
          <p class="empty-state-desc">No se puede conectar con el microservicio de Catálogo. El microservicio de Préstamos sigue disponible con su historial local.</p>
        </div>
      `;
        }
    }
}

function renderTablaLibros() {
    const searchVal = ($('#filter-libros-search')?.value || '').toLowerCase().trim();
    const activePill = $('.filter-pill[data-filter-disp].active');
    const dispFilter = activePill ? activePill.dataset.filterDisp : 'all';

    let list = cache.libros.filter(libro => {
        const autorNombre = cache.autoresMap[libro.autor_id] || '';
        const matchSearch = !searchVal ||
            String(libro.titulo || '').toLowerCase().includes(searchVal) ||
            autorNombre.toLowerCase().includes(searchVal) ||
            String(libro.id).includes(searchVal);

        if (!matchSearch) return false;

        if (dispFilter === 'available') return libro.ejemplares_disponibles > 0;
        if (dispFilter === 'out') return libro.ejemplares_disponibles <= 0;
        return true;
    });

    const countBadge = $('#count-libros');
    if (countBadge) countBadge.textContent = `${list.length} de ${cache.libros.length} libros`;

    const container = $('#t-libros');
    if (!container) return;

    if (list.length === 0) {
        container.innerHTML = `
      <div class="empty-state">
        <svg class="empty-state-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        <h4 class="empty-state-title">No se encontraron libros</h4>
        <p class="empty-state-desc">${cache.libros.length === 0 ? 'Aún no hay obras registradas en el catálogo. Utiliza el formulario superior para añadir libros.' : 'Ningún libro coincide con el criterio de búsqueda o filtro seleccionado.'}</p>
      </div>
    `;
        return;
    }

    const rows = list.map(x => {
        const autor = cache.autoresMap[x.autor_id] || '—';
        const isDisponible = x.estado === 'DISPONIBLE' && x.ejemplares_disponibles > 0;
        const ratio = x.ejemplares_totales > 0 ? Math.round((x.ejemplares_disponibles / x.ejemplares_totales) * 100) : 0;

        return `
      <tr>
        <td class="td-id">#${x.id}</td>
        <td>
          <div class="td-title-cell">
            <svg class="svg-icon" style="color:var(--primary); width:16px; height:16px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <span>${esc(x.titulo)}</span>
          </div>
        </td>
        <td>${esc(autor)}</td>
        <td>
          <div class="stock-pill">
            <span>${x.ejemplares_disponibles} / ${x.ejemplares_totales}</span>
            <div class="stock-bar-wrap" title="${x.ejemplares_disponibles} disponibles de ${x.ejemplares_totales}">
              <div class="stock-bar-fill ${ratio === 0 ? 'empty' : ''}" style="width: ${ratio}%;"></div>
            </div>
          </div>
        </td>
        <td>${bd(x.estado, isDisponible ? 'ok' : 'er')}</td>
        <td>
          <div class="td-actions">
            <button class="action-btn" data-act="edit-libro" data-id="${x.id}" data-t="${esc(x.titulo)}" data-n="${x.ejemplares_totales}" data-disp="${x.ejemplares_disponibles}">
              <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                <path d="m15 5 4 4"/>
              </svg>
              <span>Editar</span>
            </button>
            <button class="action-btn btn-action-danger" data-act="del-libro" data-id="${x.id}" data-t="${esc(x.titulo)}">
              <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
              </svg>
              <span>Eliminar</span>
            </button>
          </div>
        </td>
      </tr>
    `;
    });

    container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Título</th>
          <th>Autor</th>
          <th>Ejemplares</th>
          <th>Estado</th>
          <th style="text-align:right;">Acciones</th>
        </tr>
      </thead>
      <tbody>${rows.join('')}</tbody>
    </table>
  `;
}

// =============================================================================
// 3. GESTIÓN DE USUARIOS
// =============================================================================

async function loadUsuarios() {
    const usuarios = await api(API.pre + '/usuarios');
    cache.usuarios = usuarios || [];
    renderTablaUsuarios();
}

function renderTablaUsuarios() {
    const searchVal = ($('#filter-users-search')?.value || '').toLowerCase().trim();
    const activePill = $('.filter-pill[data-filter-tipo].active');
    const tipoFilter = activePill ? activePill.dataset.filterTipo : 'all';

    let list = cache.usuarios.filter(u => {
        const matchSearch = !searchVal ||
            String(u.nombre || '').toLowerCase().includes(searchVal) ||
            String(u.codigo || '').toLowerCase().includes(searchVal) ||
            String(u.correo || '').toLowerCase().includes(searchVal);

        if (!matchSearch) return false;

        if (tipoFilter !== 'all' && u.tipo !== tipoFilter) return false;
        return true;
    });

    const countBadge = $('#count-users');
    if (countBadge) countBadge.textContent = `${list.length} de ${cache.usuarios.length} usuarios`;

    const container = $('#t-users');
    if (!container) return;

    if (list.length === 0) {
        container.innerHTML = `
      <div class="empty-state">
        <svg class="empty-state-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
        </svg>
        <h4 class="empty-state-title">No se encontraron usuarios</h4>
        <p class="empty-state-desc">${cache.usuarios.length === 0 ? 'No hay usuarios registrados actualmente.' : 'Ningún usuario coincide con los filtros aplicados.'}</p>
      </div>
    `;
        return;
    }

    const rows = list.map(x => {
        const isActivo = +x.activo === 1;
        const tipoClass = x.tipo === 'DOCENTE' ? 'tipo-docente' : 'tipo-estudiante';

        return `
      <tr>
        <td class="td-code">${esc(x.codigo)}</td>
        <td>
          <div class="td-title-cell">
            <div class="user-avatar" style="width:28px; height:28px; font-size:0.68rem; background: ${x.tipo === 'DOCENTE' ? '#4f46e5' : '#2563eb'};">
              ${esc((x.nombre || 'U').slice(0, 2).toUpperCase())}
            </div>
            <strong>${esc(x.nombre)}</strong>
          </div>
        </td>
        <td>
          <span style="color:var(--tx-secondary); font-family:var(--font-mono); font-size:0.8rem;">
            ${esc(x.correo || '—')}
          </span>
        </td>
        <td><span class="user-tipo-label ${tipoClass}">${esc(x.tipo)}</span></td>
        <td>${bd(isActivo ? 'ACTIVO' : 'INACTIVO', isActivo ? 'ok' : 'er')}</td>
        <td>
          <div class="td-actions">
            ${isActivo ? `
              <button class="action-btn btn-action-danger" data-act="baja" data-id="${x.id}" data-nom="${esc(x.nombre)}">
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                  <line x1="18" x2="23" y1="11" y2="11"/>
                </svg>
                <span>Dar de baja</span>
              </button>
            ` : '<span class="mu" style="font-size:0.75rem;">Inactivo</span>'}
          </div>
        </td>
      </tr>
    `;
    });

    container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Código</th>
          <th>Nombre del usuario</th>
          <th>Correo institucional</th>
          <th>Tipo</th>
          <th>Estado</th>
          <th style="text-align:right;">Acciones</th>
        </tr>
      </thead>
      <tbody>${rows.join('')}</tbody>
    </table>
  `;
}

// =============================================================================
// 4. GESTIÓN DE PRÉSTAMOS Y DEVOLUCIONES
// =============================================================================

async function loadPrestamos() {
    const estVal = $('#f-est')?.value || '';
    const alertBanner = $('#cat-down-prestamos-alert');

    // Carga resiliente: Promise.allSettled para que la caída de Catálogo no impida ver préstamos ni usuarios
    const [usuariosRes, librosRes, prestamosRes] = await Promise.allSettled([
        api(API.pre + '/usuarios'),
        api(API.cat + '/libros'),
        api(API.pre + '/prestamos' + (estVal ? `?estado=${estVal}` : ''))
    ]);

    const usuarios = usuariosRes.status === 'fulfilled' ? usuariosRes.value : [];
    const libros = librosRes.status === 'fulfilled' ? librosRes.value : null;
    const prestamos = prestamosRes.status === 'fulfilled' ? prestamosRes.value : [];

    cache.prestamos = prestamos || [];
    const isCatDown = librosRes.status === 'rejected';
    cache.catalogo_disponible = !isCatDown;

    if (alertBanner) {
        alertBanner.style.display = isCatDown ? 'flex' : 'none';
    }

    // Actualizar dropdowns del formulario de préstamo
    const selUser = $('#sel-user');
    if (selUser) {
        const usuariosActivos = (usuarios || []).filter(x => +x.activo === 1);
        selUser.innerHTML = usuariosActivos.length
            ? '<option value="">Seleccione un usuario solicitante...</option>' +
            usuariosActivos.map(x => `<option value="${x.id}">${esc(x.nombre)} (${esc(x.codigo)}) — ${esc(x.tipo)}</option>`).join('')
            : '<option value="">No hay usuarios activos registrados</option>';
    }

    const selLibro = $('#sel-libro');
    const btnPrestar = $('#btn-prestar');
    if (selLibro) {
        if (isCatDown) {
            selLibro.innerHTML = '<option value="">⚠️ Catálogo fuera de línea (no disponible)</option>';
            selLibro.disabled = true;
            if (btnPrestar) {
                btnPrestar.disabled = true;
                btnPrestar.title = 'No se pueden registrar préstamos: Catálogo fuera de servicio';
            }
        } else {
            selLibro.disabled = false;
            if (btnPrestar) {
                btnPrestar.disabled = false;
                btnPrestar.title = '';
            }
            const librosDisponibles = (libros || []).filter(x => x.ejemplares_disponibles > 0);
            selLibro.innerHTML = librosDisponibles.length
                ? '<option value="">Seleccione una obra con stock disponible...</option>' +
                librosDisponibles.map(x => `<option value="${x.id}">${esc(x.titulo)} · ${x.ejemplares_disponibles} disponibles</option>`).join('')
                : '<option value="">No hay libros disponibles actualmente</option>';
        }
    }

    renderTablaPrestamos();
}

function renderTablaPrestamos() {
    const searchVal = ($('#filter-prest-search')?.value || '').toLowerCase().trim();

    let list = cache.prestamos.filter(p => {
        if (!searchVal) return true;
        return String(p.usuario || '').toLowerCase().includes(searchVal) ||
            String(p.libro_titulo || p.libro_id || '').toLowerCase().includes(searchVal) ||
            String(p.id).includes(searchVal);
    });

    const countBadge = $('#count-prest');
    if (countBadge) countBadge.textContent = `${list.length} de ${cache.prestamos.length} préstamos`;

    const container = $('#t-prest');
    if (!container) return;

    if (list.length === 0) {
        container.innerHTML = `
      <div class="empty-state">
        <svg class="empty-state-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="m16 3 4 4-4 4"/>
          <path d="M20 7H4"/>
          <path d="m8 21-4-4 4-4"/>
          <path d="M4 17h16"/>
        </svg>
        <h4 class="empty-state-title">No hay préstamos para mostrar</h4>
        <p class="empty-state-desc">Registra un nuevo préstamo utilizando el formulario superior o ajusta los filtros de búsqueda.</p>
      </div>
    `;
        return;
    }

    const rows = list.map(x => {
        const isActivo = x.estado === 'ACTIVO';
        const overdue = isActivo ? esPrestamoVencido(x.fecha_limite) : { vencido: false, dias: 0 };

        let estadoBadge;
        if (!isActivo) {
            estadoBadge = bd('DEVUELTO', 'ok');
        } else if (overdue.vencido) {
            estadoBadge = bd(`VENCIDO (+${overdue.dias}d)`, 'er');
        } else {
            estadoBadge = bd('ACTIVO', 'wa');
        }

        const diasNum = x.dias_prestamo || 7;
        return `
      <tr>
        <td class="td-id">#${x.id}</td>
        <td>
          <div class="td-title-cell">
            <svg class="svg-icon" style="color:var(--tx-muted); width:15px; height:15px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
            <strong>${esc(x.usuario)}</strong>
          </div>
        </td>
        <td>
          <span style="font-weight:600; color:var(--tx-main);">
            ${esc(x.libro_titulo || `Libro #${x.libro_id}`)}
          </span>
        </td>
        <td>
          <span class="plazo-pill" title="Duración acordada: ${diasNum} días">
            <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
            <span>${diasNum} d</span>
          </span>
        </td>
        <td>
          <span style="font-family:var(--font-mono); font-size:0.82rem; ${overdue.vencido ? 'color:var(--danger); font-weight:700;' : ''}">
            ${formatearFecha(x.fecha_limite)}
          </span>
        </td>
        <td>${estadoBadge}</td>
        <td>
          <div class="td-actions">
            ${isActivo ? `
              <button class="action-btn btn-action-primary" data-act="devolver" data-id="${x.id}" data-tit="${esc(x.libro_titulo || 'Libro')}" ${cache.catalogo_disponible === false ? 'disabled title="Catálogo fuera de línea: reposición deshabilitada"' : ''}>
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="9 11 12 14 22 4"/>
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
                <span>Devolver libro</span>
              </button>
            ` : '<span class="mu" style="font-size:0.75rem;">Completado</span>'}
          </div>
        </td>
      </tr>
    `;
    });

    container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Usuario solicitante</th>
          <th>Libro en préstamo</th>
          <th>Plazo</th>
          <th>Fecha límite</th>
          <th>Estado</th>
          <th style="text-align:right;">Acciones</th>
        </tr>
      </thead>
      <tbody>${rows.join('')}</tbody>
    </table>
  `;
}

// =============================================================================
// 5. GESTIÓN Y SEGUIMIENTO DE NOTIFICACIONES
// =============================================================================

async function loadNotifs() {
    const query = new URLSearchParams();
    const nEst = $('#n-est')?.value;
    const nTipo = $('#n-tipo')?.value;

    if (nEst) query.set('estado', nEst);
    if (nTipo) query.set('tipo', nTipo);

    const alertBanner = $('#notif-down-alert');

    try {
        const url = API.not + '/notificaciones' + (query.toString() ? '?' + query.toString() : '');
        const data = await api(url);
        if (alertBanner) alertBanner.style.display = 'none';
        cache.notificaciones = data || [];
        renderTablaNotificaciones();
    } catch (err) {
        if (alertBanner) alertBanner.style.display = 'flex';
        const container = $('#t-notif');
        if (container) {
            container.innerHTML = `
        <div class="empty-state">
          <svg class="empty-state-icon svg-icon" style="color:var(--warning);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>
          </svg>
          <h4 class="empty-state-title">Servicio de Notificaciones no disponible</h4>
          <p class="empty-state-desc">No se puede comunicar con el microservicio en el puerto 8003. Los préstamos continúan funcionando normalmente sin interrupciones.</p>
        </div>
      `;
        }
    }
}

function renderTablaNotificaciones() {
    const searchVal = ($('#filter-notif-search')?.value || '').toLowerCase().trim();

    let list = cache.notificaciones.filter(n => {
        if (!searchVal) return true;
        return String(n.usuario || '').toLowerCase().includes(searchVal) ||
            String(n.correo_destino || '').toLowerCase().includes(searchVal) ||
            String(n.id).includes(searchVal);
    });

    const countBadge = $('#count-notif');
    if (countBadge) countBadge.textContent = `${list.length} de ${cache.notificaciones.length} registros`;

    const container = $('#t-notif');
    if (!container) return;

    if (list.length === 0) {
        container.innerHTML = `
      <div class="empty-state">
        <svg class="empty-state-icon svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
        </svg>
        <h4 class="empty-state-title">No hay notificaciones registradas</h4>
        <p class="empty-state-desc">Las notificaciones por correo de préstamos, avisos de vencimiento y multas aparecerán aquí automáticamente.</p>
      </div>
    `;
        return;
    }

    const estadoClases = { ENVIADA: 'ok', PENDIENTE: 'wa', FALLIDA: 'er' };

    const rows = list.map(x => {
        let tipoBadge = `<span class="badge badge-info">${esc(x.tipo)}</span>`;
        if (x.tipo === 'POR_VENCER') tipoBadge = `<span class="badge badge-wa">${esc(x.tipo)}</span>`;
        if (x.tipo === 'MULTA') tipoBadge = `<span class="badge badge-er">${esc(x.tipo)}</span>`;

        const rawError = x.ultimo_error || '';
        const errorHtml = rawError
            ? `<span class="error-cell error-cell-click" data-err="${esc(rawError)}" title="Clic para ver detalle">${esc(rawError)}</span>`
            : '<span class="mu">—</span>';

        return `
      <tr>
        <td class="td-id">#${x.id}</td>
        <td>${tipoBadge}</td>
        <td><strong>${esc(x.usuario)}</strong></td>
        <td>
          <span style="font-family:var(--font-mono); font-size:0.8rem; color:var(--tx-secondary);">
            ${esc(x.correo_destino || '—')}
          </span>
        </td>
        <td>${bd(x.estado, estadoClases[x.estado])}</td>
        <td style="font-family:var(--font-mono); font-size:0.8rem; text-align:center;">${x.intentos}</td>
        <td>${errorHtml}</td>
        <td>
          <div class="td-actions">
            ${x.estado === 'FALLIDA' && x.correo_destino ? `
              <button class="action-btn btn-action-primary" data-act="reintentar" data-id="${x.id}">
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                  <path d="M3 3v5h5"/>
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
                  <path d="M16 16h5v5"/>
                </svg>
                <span>Reintentar</span>
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
    });

    container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Tipo</th>
          <th>Destinatario</th>
          <th>Correo electrónico</th>
          <th>Estado</th>
          <th style="text-align:center;">Intentos</th>
          <th>Último error</th>
          <th style="text-align:right;">Acciones</th>
        </tr>
      </thead>
      <tbody>${rows.join('')}</tbody>
    </table>
  `;
}

// =============================================================================
// NAVEGACIÓN Y CAMBIO DE VISTAS
// =============================================================================

const tabs = {
    estado: loadEstado,
    catalogo: loadCatalogo,
    usuarios: loadUsuarios,
    prestamos: loadPrestamos,
    notificaciones: loadNotifs,
    'vista-usuario': loadVistaUsuario
};

const tabMetas = {
    estado: {
        title: 'Panel Principal',
        desc: 'Resumen general del sistema, salud de microservicios y métricas operativas en tiempo real.'
    },
    catalogo: {
        title: 'Catálogo de Libros y Autores',
        desc: 'Administración del acervo bibliográfico, control de ejemplares disponibles y registro de autores.'
    },
    usuarios: {
        title: 'Gestión de Usuarios',
        desc: 'Directorio y registro de estudiantes y docentes autorizados para préstamos universitarios.'
    },
    prestamos: {
        title: 'Préstamos y Devoluciones',
        desc: 'Control de circulación bibliográfica, revisión de vencimientos y cálculo de multas.'
    },
    notificaciones: {
        title: 'Seguimiento de Notificaciones',
        desc: 'Historial de correos automáticos emitidos, reintentos de entrega y tolerancia a fallos.'
    },
    'vista-usuario': {
        title: 'Catálogo de Lectores — Vista de Usuario',
        desc: 'Consulta pública de obras y unidades físicas disponibles en sala. Vista exclusiva de información (sin préstamos directos).'
    }
};

async function run(fn) {
    try {
        await fn();
    } catch (e) {
        toast(e.message, true);
    }
}

function show(t) {
    if (!tabs[t]) return;
    curTab = t;

    // Actualizar botones de navegación en sidebar
    $$('.sidebar-nav .nav-item').forEach(b => {
        const isCurrent = b.dataset.t === t;
        b.classList.toggle('on', isCurrent);
        b.setAttribute('aria-current', isCurrent ? 'page' : 'false');
    });

    // Mostrar sección activa y ocultar las demás
    $$('main.content-area > section').forEach(s => {
        s.hidden = s.id !== t;
    });

    // Actualizar títulos en la barra superior
    const meta = tabMetas[t] || { title: 'Biblioteca', desc: '' };
    const pageTitle = $('#pageTitle');
    const pageDesc = $('#pageDesc');
    if (pageTitle) pageTitle.textContent = meta.title;
    if (pageDesc) pageDesc.textContent = meta.desc;

    // En móvil: cerrar sidebar si estaba abierto
    closeSidebarMobile();

    // Ejecutar carga de datos de la sección
    run(tabs[t]);
}

// Eventos de botones de navegación del sidebar
$$('.sidebar-nav .nav-item').forEach(b => {
    b.onclick = () => show(b.dataset.t);
});

// Control de apertura/cierre de sidebar en dispositivos móviles
function openSidebarMobile() {
    $('#sidebar')?.classList.add('open');
    $('#sidebarBackdrop')?.classList.add('open');
}

function closeSidebarMobile() {
    $('#sidebar')?.classList.remove('open');
    $('#sidebarBackdrop')?.classList.remove('open');
}

$('#btnToggleMenu')?.addEventListener('click', () => {
    const sidebar = $('#sidebar');
    if (sidebar?.classList.contains('open')) {
        closeSidebarMobile();
    } else {
        openSidebarMobile();
    }
});

$('#sidebarBackdrop')?.addEventListener('click', closeSidebarMobile);

// Botón de recarga manual en la barra superior
$('#btnRefresh')?.addEventListener('click', async () => {
    const btn = $('#btnRefresh');
    btn?.classList.add('spinning');
    try {
        await tabs[curTab]();
        toast('Datos actualizados correctamente', false);
    } catch (err) {
        toast(err.message, true);
    } finally {
        setTimeout(() => btn?.classList.remove('spinning'), 500);
    }
});

// =============================================================================
// CONTROL DE ENVÍO DE FORMULARIOS CON VALIDACIÓN Y ESTADO DE CARGA
// =============================================================================

function setupForm(formId, submitBtnId, submitFn, successMsg) {
    const formEl = $(formId);
    const btnEl = $(submitBtnId);
    if (!formEl) return;

    formEl.onsubmit = async e => {
        e.preventDefault();
        if (btnEl) {
            btnEl.disabled = true;
            btnEl.dataset.originalHtml = btnEl.innerHTML;
            btnEl.innerHTML = `
        <svg class="svg-icon" style="animation:spin 0.8s linear infinite;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
        <span>Guardando...</span>
      `;
        }

        try {
            const data = fd(formEl);
            await submitFn(data);
            formEl.reset();
            toast(successMsg);
        } catch (err) {
            toast(err.message, true);
        } finally {
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerHTML = btnEl.dataset.originalHtml;
            }
        }
    };
}

// 1. Guardar Autor
setupForm('#f-autor', '#btn-save-autor', async d => {
    await api(API.cat + '/autores', 'POST', d);
    await loadCatalogo();
}, 'Autor guardado exitosamente');

// 2. Guardar Libro (con detección y suma inteligente de ejemplares para evitar duplicados)
setupForm('#f-libro', '#btn-save-libro', async d => {
    const payload = {
        titulo: (d.titulo || '').trim(),
        ejemplares_totales: +d.ejemplares_totales || 1,
        sumar_si_existe: true
    };
    if (d.autor_id) payload.autor_id = +d.autor_id;
    const res = await api(API.cat + '/libros', 'POST', payload);
    await loadCatalogo();
    if (res && res.ejemplares_totales > (+d.ejemplares_totales || 1)) {
        toast(`La obra ya existía; se sumaron ${+d.ejemplares_totales || 1} unidades a su inventario (total: ${res.ejemplares_totales}).`);
    }
}, 'Libro incorporado al catálogo exitosamente');

// 3. Registrar Usuario
setupForm('#f-user', '#btn-save-user', async d => {
    await api(API.pre + '/usuarios', 'POST', d);
    await loadUsuarios();
}, 'Usuario universitario registrado exitosamente');

// 4. Prestar Libro
setupForm('#f-prestamo', '#btn-prestar', async d => {
    const payload = {
        libro_id: +d.libro_id,
        usuario_id: +d.usuario_id
    };
    if (d.dias_prestamo !== undefined && d.dias_prestamo !== '') {
        const dias = parseInt(d.dias_prestamo, 10);
        if (!isNaN(dias) && dias > 0) {
            payload.dias_prestamo = dias;
        }
    }
    await api(API.pre + '/prestamos', 'POST', payload);
    await loadPrestamos();
    actualizarHintDiasPrestamo();
}, 'Préstamo concedido exitosamente');

function actualizarHintDiasPrestamo() {
    const inputDias = $('#input-dias-prestamo');
    const hint = $('#hint-dias-prestamo');
    if (!inputDias || !hint) return;
    const dias = parseInt(inputDias.value, 10);
    if (!isNaN(dias) && dias > 0) {
        const target = new Date();
        target.setDate(target.getDate() + dias);
        const fechaStr = target.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
        hint.innerHTML = `Duración: <strong>${dias} día${dias === 1 ? '' : 's'}</strong> · Vencimiento estimado: <strong>${fechaStr}</strong>`;
    } else {
        hint.textContent = 'Indica la duración del préstamo en días antes de la fecha límite (por defecto: 7 días)';
    }
}
$('#input-dias-prestamo')?.addEventListener('input', actualizarHintDiasPrestamo);
setTimeout(actualizarHintDiasPrestamo, 100);

// =============================================================================
// FILTROS Y EVENTOS EN VIVO
// =============================================================================

// Filtros y búsquedas de Vista Usuario
$('#filter-user-search')?.addEventListener('input', renderTablaUserLibros);
$('#filter-user-autor')?.addEventListener('change', renderTablaUserLibros);
$$('.filter-pill[data-user-filter-disp]').forEach(pill => {
    pill.onclick = () => {
        $$('.filter-pill[data-user-filter-disp]').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        renderTablaUserLibros();
    };
});

// Detección en vivo de títulos duplicados en formulario de nuevo libro
const inpLibroTitulo = $('#libro-titulo');
const selLibroAutor = $('#sel-autor');
function verificarLibroDuplicado() {
    const tit = (inpLibroTitulo?.value || '').trim().toLowerCase();
    const autId = selLibroAutor?.value ? +selLibroAutor.value : null;
    let hint = $('#hint-libro-duplicado');
    if (!tit) {
        if (hint) hint.remove();
        return;
    }
    const match = (cache.libros || []).find(b => 
        b.titulo.trim().toLowerCase() === tit && 
        ((autId === null && !b.autor_id) || (autId !== null && b.autor_id === autId))
    );
    if (match) {
        if (!hint) {
            hint = document.createElement('div');
            hint.id = 'hint-libro-duplicado';
            hint.style.cssText = 'font-size:12px; color:#2563eb; margin-top:5px; font-weight:500; display:flex; align-items:center; gap:4px;';
            inpLibroTitulo.parentElement.appendChild(hint);
        }
        hint.innerHTML = `<svg class="svg-icon" style="width:14px;height:14px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> Obra ya registrada (#${match.id}, ${match.ejemplares_totales} ejemplares). Al guardar, se sumarán las nuevas unidades sin duplicar la obra.`;
    } else if (hint) {
        hint.remove();
    }
}
inpLibroTitulo?.addEventListener('input', verificarLibroDuplicado);
selLibroAutor?.addEventListener('change', verificarLibroDuplicado);

// Filtros y búsquedas de Catálogo
$('#filter-libros-search')?.addEventListener('input', renderTablaLibros);
$$('.filter-pill[data-filter-disp]').forEach(pill => {
    pill.onclick = () => {
        $$('.filter-pill[data-filter-disp]').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        renderTablaLibros();
    };
});

// Filtros y búsquedas de Usuarios
$('#filter-users-search')?.addEventListener('input', renderTablaUsuarios);
$$('.filter-pill[data-filter-tipo]').forEach(pill => {
    pill.onclick = () => {
        $$('.filter-pill[data-filter-tipo]').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        renderTablaUsuarios();
    };
});

// Filtros y búsquedas de Préstamos
$('#filter-prest-search')?.addEventListener('input', renderTablaPrestamos);
if ($('#f-est')) {
    $('#f-est').onchange = () => run(loadPrestamos);
}

// Filtros y búsquedas de Notificaciones
$('#filter-notif-search')?.addEventListener('input', renderTablaNotificaciones);
if ($('#n-est')) $('#n-est').onchange = () => run(loadNotifs);
if ($('#n-tipo')) $('#n-tipo').onchange = () => run(loadNotifs);

// Botón de revisión de vencimientos
$('#btn-rev')?.addEventListener('click', () => {
    const btn = $('#btn-rev');
    if (btn) btn.disabled = true;

    run(async () => {
        try {
            const res = await api(API.pre + '/prestamos/revisar-vencimientos', 'POST');
            const isNotifDown = res.notificaciones_disponible === false;

            const summaryHtml = `
        <div style="display:flex; flex-direction:column; gap:0.75rem;">
          <p>La revisión de vencimientos y reenvío de multas ha finalizado:</p>
          <ul style="padding-left: 1.25rem; display:flex; flex-direction:column; gap:0.35rem;">
            <li><strong>Préstamos revisados (≤ 2 días restantes):</strong> ${res.revisados}</li>
            <li><strong>Avisos de vencimiento enviados:</strong> ${res.avisados}</li>
            <li><strong>Multas pendientes reenviadas:</strong> ${res.multas_reenviadas}</li>
            ${res.sin_correo ? `<li><strong>Usuarios sin correo registrado:</strong> ${res.sin_correo}</li>` : ''}
          </ul>
          ${isNotifDown ? `
            <div class="alert-banner warning" style="margin-top:0.5rem;">
              <span><strong>Aviso:</strong> El microservicio de notificaciones no respondió; los avisos se enviarán en la próxima ejecución.</span>
            </div>
          ` : `
            <p class="mu" style="font-size:0.8rem;">Las notificaciones por correo han sido despachadas vía SMTP.</p>
          `}
        </div>
      `;

            showModal({
                title: 'Resultado de Revisión de Vencimientos',
                bodyHtml: summaryHtml,
                confirmText: 'Entendido',
                confirmClass: 'btn-primary'
            });

            await loadPrestamos();
        } finally {
            if (btn) btn.disabled = false;
        }
    });
});

// =============================================================================
// DELEGACIÓN DE ACCIONES EN TABLAS (EDITAR, ELIMINAR, DEVOLVER, REINTENTAR)
// =============================================================================

document.addEventListener('click', e => {
    // Ver detalle de error completo al pulsar en la celda truncada
    const errCell = e.target.closest('.error-cell-click');
    if (errCell) {
        const errorText = errCell.dataset.err || '';
        showModal({
            title: 'Detalle del Error de Notificación',
            bodyHtml: `
        <div style="display:flex; flex-direction:column; gap:0.75rem;">
          <p>Detalle técnico registrado por el worker de correo:</p>
          <pre style="background:#f1f5f9; padding:0.85rem; border-radius:8px; font-family:var(--font-mono); font-size:0.8rem; overflow-x:auto; white-space:pre-wrap; color:#991b1b; max-height:240px;">${esc(errorText)}</pre>
        </div>
      `,
            confirmText: 'Cerrar',
            confirmClass: 'btn-secondary'
        });
        return;
    }

    // Botones con data-act
    const b = e.target.closest('[data-act]');
    if (!b) return;

    const { act, id } = b.dataset;

    run(async () => {
        // 1. Eliminar libro
        if (act === 'del-libro') {
            const titulo = b.dataset.t || `Libro #${id}`;
            showModal({
                title: 'Confirmar Eliminación de Libro',
                bodyHtml: `
          <p>¿Estás seguro de que deseas eliminar permanentemente la obra <strong>"${esc(titulo)}"</strong>?</p>
          <p class="mu">Nota: No se puede eliminar si existen ejemplares prestados actualmente.</p>
        `,
                confirmText: 'Eliminar libro',
                confirmClass: 'btn-danger',
                onConfirm: async () => {
                    await api(`${API.pre}/libros/${id}`, 'DELETE');
                    toast(`"${titulo}" eliminado correctamente`);
                    await loadCatalogo();
                }
            });
        }

        // 2. Editar libro
        if (act === 'edit-libro') {
            const curTitulo = b.dataset.t || '';
            const curTotales = b.dataset.n || '1';
            const curDisponibles = b.dataset.disp || '1';
            const prestados = Math.max(0, +curTotales - +curDisponibles);

            const modalHtml = `
        <div class="form-group">
          <label class="form-label" for="modal-edit-tit">Título de la obra <span class="req">*</span></label>
          <input id="modal-edit-tit" class="form-control" value="${esc(curTitulo)}" required>
        </div>
        <div class="form-group">
          <label class="form-label" for="modal-edit-tot">Ejemplares totales <span class="req">*</span></label>
          <input id="modal-edit-tot" type="number" min="${Math.max(1, prestados)}" class="form-control" value="${curTotales}" required>
          ${prestados > 0 ? `<span class="mu" style="font-size:0.75rem;">Mínimo permitido: ${prestados} (hay ${prestados} ejemplares prestados)</span>` : ''}
        </div>
      `;

            showModal({
                title: `Editar Obra #${id}`,
                bodyHtml: modalHtml,
                confirmText: 'Guardar cambios',
                confirmClass: 'btn-primary',
                onConfirm: async () => {
                    const nuevoTit = $('#modal-edit-tit')?.value?.trim();
                    const nuevoTot = +$('#modal-edit-tot')?.value;

                    if (!nuevoTit) {
                        toast('El título no puede estar vacío', true);
                        return false;
                    }
                    if (isNaN(nuevoTot) || nuevoTot < 1) {
                        toast('La cantidad de ejemplares debe ser al menos 1', true);
                        return false;
                    }
                    if (nuevoTot < prestados) {
                        toast(`No puedes reducir los ejemplares por debajo de los prestados (${prestados})`, true);
                        return false;
                    }

                    await api(`${API.cat}/libros/${id}`, 'PUT', {
                        titulo: nuevoTit,
                        ejemplares_totales: nuevoTot
                    });

                    toast('Libro actualizado exitosamente');
                    await loadCatalogo();
                }
            });
        }

        // 3. Dar de baja a un usuario
        if (act === 'baja') {
            const nombre = b.dataset.nom || `Usuario #${id}`;
            showModal({
                title: 'Dar de Baja a Usuario',
                bodyHtml: `
          <p>¿Confirmas dar de baja a <strong>"${esc(nombre)}"</strong>?</p>
          <p class="mu">El usuario quedará inactivo y no podrá solicitar nuevos préstamos.</p>
        `,
                confirmText: 'Dar de baja',
                confirmClass: 'btn-danger',
                onConfirm: async () => {
                    await api(`${API.pre}/usuarios/${id}`, 'DELETE');
                    toast(`Usuario "${nombre}" dado de baja`);
                    await loadUsuarios();
                }
            });
        }

        // 4. Devolución de libro
        if (act === 'devolver') {
            if (cache.catalogo_disponible === false) {
                toast('Catálogo no disponible: reposición de stock deshabilitada.', true);
                return;
            }
            const titulo = b.dataset.tit || `Préstamo #${id}`;
            showModal({
                title: 'Registrar Devolución de Libro',
                bodyHtml: `
          <p>¿Confirmas la recepción y devolución de la obra <strong>"${esc(titulo)}"</strong>?</p>
          <p class="mu">Se repondrá el ejemplar al catálogo y se verificará si corresponde una multa por retraso.</p>
        `,
                confirmText: 'Confirmar devolución',
                confirmClass: 'btn-primary',
                onConfirm: async () => {
                    const res = await api(`${API.pre}/prestamos/${id}/devolucion`, 'PUT');
                    if (res.multa) {
                        showModal({
                            title: '⚠️ Devolución Registrada con Multa',
                            bodyHtml: `
                <div style="display:flex; flex-direction:column; gap:0.85rem;">
                  <p>La devolución fue procesada con retraso respecto a la fecha límite:</p>
                  <div style="background:var(--danger-bg); border:1px solid var(--danger-border); border-radius:8px; padding:1rem; color:var(--danger-tx);">
                    <div style="font-size:1.15rem; font-weight:800; margin-bottom:0.25rem;">
                      Multa total: $${parseFloat(res.multa.monto).toFixed(2)}
                    </div>
                    <div style="font-size:0.85rem;">
                      Días de retraso acumulados: <strong>${res.multa.dias_retraso} día(s)</strong>
                    </div>
                  </div>
                  <p class="mu" style="font-size:0.8rem;">Se ha encolado una notificación por correo al usuario con los detalles de la sanción.</p>
                </div>
              `,
                            confirmText: 'Entendido',
                            confirmClass: 'btn-primary'
                        });
                    } else {
                        toast('Devolución registrada a tiempo. Ejemplar repuesto en catálogo.');
                    }
                    await loadPrestamos();
                }
            });
        }

        // 5. Reintentar notificación fallida
        if (act === 'reintentar') {
            b.disabled = true;
            try {
                await api(`${API.not}/notificaciones/${id}/reintentar`, 'POST');
                toast(`Notificación #${id} reencolada para reintento`);
                await loadNotifs();
            } finally {
                b.disabled = false;
            }
        }
    });
});

// Comprobación periódica automática de salud de servicios
setInterval(() => {
    if (curTab === 'estado') {
        run(loadEstado);
    }
}, 5000);

// Inicializar la aplicación en la pestaña de Estado
show('estado');
