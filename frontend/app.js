const PAISES = ["Afganistán", "Albania", "Alemania", "Andorra", "Angola", "Antigua y Barbuda", "Arabia Saudita", "Argelia", "Argentina", "Armenia", "Australia", "Austria", "Azerbaiyán", "Bahamas", "Bangladés", "Barbados", "Baréin", "Bélgica", "Belice", "Benín", "Bielorrusia", "Birmania (Myanmar)", "Bolivia", "Bosnia y Herzegovina", "Botsuana", "Brasil", "Brunéi", "Bulgaria", "Burkina Faso", "Burundi", "Bután", "Cabo Verde", "Camboya", "Camerún", "Canadá", "Catar", "Chad", "Chile", "China", "Chipre", "Colombia", "Comoras", "Corea del Norte", "Corea del Sur", "Costa de Marfil", "Costa Rica", "Croacia", "Cuba", "Dinamarca", "Dominica", "Ecuador", "Egipto", "El Salvador", "Emiratos Árabes Unidos", "Eritrea", "Eslovaquia", "Eslovenia", "España", "Estados Unidos", "Estonia", "Esuatini", "Etiopía", "Filipinas", "Finlandia", "Fiyi", "Francia", "Gabón", "Gambia", "Georgia", "Ghana", "Granada", "Grecia", "Guatemala", "Guinea", "Guinea Ecuatorial", "Guinea-Bisáu", "Guyana", "Haití", "Honduras", "Hungría", "India", "Indonesia", "Irak", "Irán", "Irlanda", "Islandia", "Islas Marshall", "Islas Salomón", "Israel", "Italia", "Jamaica", "Japón", "Jordania", "Kazajistán", "Kenia", "Kirguistán", "Kiribati", "Kuwait", "Laos", "Lesoto", "Letonia", "Líbano", "Liberia", "Libia", "Liechtenstein", "Lituania", "Luxemburgo", "Macedonia del Norte", "Madagascar", "Malasia", "Malaui", "Maldivas", "Malí", "Malta", "Marruecos", "Mauricio", "Mauritania", "México", "Micronesia", "Moldavia", "Mónaco", "Mongolia", "Montenegro", "Mozambique", "Namibia", "Nauru", "Nepal", "Nicaragua", "Níger", "Nigeria", "Noruega", "Nueva Zelanda", "Omán", "Pakistán", "Palaos", "Panamá", "Papúa Nueva Guinea", "Paraguay", "Países Bajos", "Perú", "Polonia", "Portugal", "Reino Unido", "República Centroafricana", "República Checa", "República del Congo", "República Democrática del Congo", "República Dominicana", "Ruanda", "Rumania", "Rusia", "Samoa", "San Cristóbal y Nieves", "San Marino", "San Vicente y las Granadinas", "Santa Lucía", "Santo Tomé y Príncipe", "Senegal", "Serbia", "Seychelles", "Sierra Leona", "Singapur", "Siria", "Somalia", "Sri Lanka", "Sudáfrica", "Sudán", "Sudán del Sur", "Suecia", "Suiza", "Surinam", "Tailandia", "Tanzania", "Tayikistán", "Timor Oriental", "Togo", "Tonga", "Trinidad y Tobago", "Túnez", "Turkmenistán", "Turquía", "Tuvalu", "Ucrania", "Uganda", "Uruguay", "Uzbekistán", "Vanuatu", "Venezuela", "Vietnam", "Yemen", "Yibuti", "Zambia", "Zimbabue"];

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
        const err = new Error(errorMsg);
        err.status = r.status;
        err.data = data;
        throw err;
    }

    return data;
}

// Formateo de fecha legible inmune a desfases de zona horaria (UTC vs Local)
function formatearFecha(isoDate) {
    if (!isoDate) return '—';
    try {
        const str = String(isoDate).trim();
        const match = str.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (match) {
            const y = match[1];
            const m = match[2];
            const d = match[3];
            const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
            const mesIdx = parseInt(m, 10) - 1;
            if (mesIdx >= 0 && mesIdx < 12) {
                return `${d} ${meses[mesIdx]} ${y}`;
            }
        }
        const dt = new Date(str);
        if (isNaN(dt.getTime())) return str.slice(0, 10);
        return dt.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch {
        return String(isoDate).slice(0, 10);
    }
}

// Comprobación de préstamo vencido inmune a desfases de zona horaria
function esPrestamoVencido(fechaLimiteStr) {
    if (!fechaLimiteStr) return { vencido: false, dias: 0 };
    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);

    let limite;
    const match = String(fechaLimiteStr).trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (match) {
        limite = new Date(parseInt(match[1], 10), parseInt(match[2], 10) - 1, parseInt(match[3], 10));
    } else {
        limite = new Date(fechaLimiteStr);
    }
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

    // Renderizar tarjetas de microservicios sin latencia, conexion ni cola (Requerimiento 11)
    const svcEl = $('#svc');
    if (svcEl) {
        svcEl.innerHTML = resultados.map(s => `
    <div class="service-card ${s.ok ? 'is-up' : 'is-down'}">
      <div class="service-card-header" style="border-bottom:none; margin-bottom:0; padding-bottom:0;">
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
          </div>
        </div>
        <span class="service-status-pill ${s.ok ? 'up' : 'down'}">
          <span class="status-dot"></span>
          ${s.ok ? 'EN LÍNEA' : 'FUERA DE SERVICIO'}
        </span>
      </div>
    </div>
  `).join('');
    }

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

            // Badge en el sidebar desactivado por peticion del usuario (Requerimiento 1)
            const badge = $('#sidebar-notif-badge');
            if (badge) {
                badge.style.display = 'none';
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
        cache.autores = autores || [];
        cache.libros = libros || [];
        cache.autoresMap = Object.fromEntries((autores || []).map(a => [a.id, a.nombre]));

        // Actualizar selector de autores en el formulario de nuevo libro (Obligatorio)
        const selAutor = $('#sel-autor');
        if (selAutor) {
            selAutor.innerHTML = '<option value="">-- Selecciona un autor (Obligatorio) --</option>' +
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
        const generoStr = String(libro.genero || '');
        const matchSearch = !searchVal ||
            String(libro.titulo || '').toLowerCase().includes(searchVal) ||
            autorNombre.toLowerCase().includes(searchVal) ||
            generoStr.toLowerCase().includes(searchVal) ||
            String(libro.id).includes(searchVal);

        if (!matchSearch) return false;

        const isInactive = libro.estado === 'INACTIVO';
        if (dispFilter === 'available') return !isInactive && Number(libro.ejemplares_disponibles) > 0;
        if (dispFilter === 'out') return !isInactive && Number(libro.ejemplares_disponibles) <= 0;
        if (dispFilter === 'inactive') return isInactive;
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
        const isInactive = x.estado === 'INACTIVO';
        const isDisponible = !isInactive && x.estado === 'DISPONIBLE' && Number(x.ejemplares_disponibles) > 0;
        const ratio = x.ejemplares_totales > 0 ? Math.round((x.ejemplares_disponibles / x.ejemplares_totales) * 100) : 0;

        let badgeEstado;
        if (isInactive) {
            badgeEstado = bd('INACTIVO', 'er');
        } else if (isDisponible) {
            badgeEstado = bd('DISPONIBLE', 'ok');
        } else {
            badgeEstado = bd('AGOTADO', 'wa');
        }

        return `
      <tr>
        <td class="td-id">#${x.id}</td>
        <td>
          <div class="td-title-cell">
            <svg class="svg-icon" style="color:var(--primary); width:16px; height:16px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <strong>${esc(x.titulo)}</strong>
          </div>
        </td>
        <td>${esc(autor)}</td>
        <td><span class="badge badge-info" style="font-size:0.75rem;">${esc(x.genero || 'General')}</span></td>
        <td><span style="font-size:0.8rem; color:var(--tx-secondary);">${esc(x.edicion || '—')}</span></td>
        <td>
          <div class="stock-pill">
            <span>${x.ejemplares_disponibles} / ${x.ejemplares_totales}</span>
            <div class="stock-bar-wrap" title="${x.ejemplares_disponibles} disponibles de ${x.ejemplares_totales}">
              <div class="stock-bar-fill ${ratio === 0 ? 'empty' : ''}" style="width: ${ratio}%;"></div>
            </div>
          </div>
        </td>
        <td>${badgeEstado}</td>
        <td>
          <div class="td-actions">
            <button class="action-btn" data-act="edit-libro" data-id="${x.id}" data-t="${esc(x.titulo)}" data-n="${x.ejemplares_totales}" data-disp="${x.ejemplares_disponibles}">
              <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                <path d="m15 5 4 4"/>
              </svg>
              <span>Editar</span>
            </button>
            ${isInactive ? `
              <button class="action-btn btn-action-success" data-act="reincorporar-libro" data-id="${x.id}" data-t="${esc(x.titulo)}" title="Reactivar libro en catálogo">
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
                  <path d="M21 3v5h-5"/>
                  <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
                  <path d="M8 16H3v5"/>
                </svg>
                <span>Reincorporar</span>
              </button>
            ` : `
              <button class="action-btn btn-action-danger" data-act="del-libro" data-id="${x.id}" data-t="${esc(x.titulo)}" title="Dar de baja / inactivar libro">
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
                </svg>
                <span>Dar de baja</span>
              </button>
            `}
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
          <th>Género</th>
          <th>Edición</th>
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
            String(u.ci || '').toLowerCase().includes(searchVal) ||
            String(u.correo || '').toLowerCase().includes(searchVal);

        if (!matchSearch) return false;

        const isActivo = +u.activo === 1;
        if (tipoFilter === 'ESTUDIANTE') return u.tipo === 'ESTUDIANTE';
        if (tipoFilter === 'DOCENTE') return u.tipo === 'DOCENTE';
        if (tipoFilter === 'inactivos') return !isActivo;
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

        // Detectar motivo específico de inactividad
        const motivo = (x.bloqueado_motivo || '').toUpperCase();
        let badgeEstado;
        if (isActivo) {
            badgeEstado = bd('ACTIVO', 'ok');
        } else if (motivo === 'INCUMPLIMIENTO') {
            badgeEstado = '<span class="badge badge-er" style="font-weight:600;" title="Bloqueado por superar los 7 días extras sin devolver la obra">BLOQUEADO (INCUMPLIMIENTO)</span>';
        } else if (motivo === 'REINCIDENCIA') {
            badgeEstado = '<span class="badge badge-er" style="font-weight:600; background:#7f1d1d; color:#ffffff;" title="Bloqueado por acumular 3 devoluciones tardías">BLOQUEADO (REINCIDENCIA)</span>';
        } else if (motivo === 'MORA') {
            badgeEstado = '<span class="badge badge-er" title="Inhabilitado automáticamente por entrega de libro fuera de plazo">INACTIVO (MORA)</span>';
        } else {
            badgeEstado = bd('INACTIVO', 'er');
        }

        return `
      <tr>
        <td class="td-code">${esc(x.codigo || x.ci)}</td>
        <td>
          <div class="td-title-cell">
            <div class="user-avatar" style="width:28px; height:28px; font-size:0.68rem; background: ${x.tipo === 'DOCENTE' ? '#4f46e5' : '#2563eb'};">
              ${esc((x.nombre || 'U').slice(0, 2).toUpperCase())}
            </div>
            <div>
              <strong>${esc(x.nombre)}</strong>
              ${x.ci && x.ci !== x.codigo ? `<div style="font-size:0.75rem; color:var(--tx-muted);">CI: ${esc(x.ci)}</div>` : ''}
            </div>
          </div>
        </td>
        <td>
          <span style="color:var(--tx-secondary); font-family:var(--font-mono); font-size:0.8rem;">
            ${esc(x.correo || '—')}
          </span>
        </td>
        <td><span class="user-tipo-label ${tipoClass}">${esc(x.tipo)}</span></td>
        <td>${badgeEstado}</td>
        <td>
          <div class="td-actions">
            <button class="action-btn" data-act="edit-user" data-id="${x.id}" title="Editar usuario">
              <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                <path d="m15 5 4 4"/>
              </svg>
              <span>Editar</span>
            </button>
            ${isActivo ? `
              <button class="action-btn btn-action-danger" data-act="baja" data-id="${x.id}" data-nom="${esc(x.nombre)}" title="Dar de baja usuario">
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                  <line x1="18" x2="23" y1="11" y2="11"/>
                </svg>
                <span>Dar de baja</span>
              </button>
            ` : `
              <button class="action-btn btn-action-success" data-act="reincorporar-user" data-id="${x.id}" data-nom="${esc(x.nombre)}" title="Reincorporar usuario">
                <svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                  <line x1="19" x2="19" y1="8" y2="14"/>
                  <line x1="22" x2="16" y1="11" y2="11"/>
                </svg>
                <span>Reincorporar</span>
              </button>
            `}
          </div>
        </td>
      </tr>
    `;
    });

    container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>C.I. / Código</th>
          <th>Nombre del usuario</th>
          <th>Correo</th>
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
    const estVal = $('#f-est')?.value || '';

    let list = cache.prestamos.filter(p => {
        const isActivo = p.estado === 'ACTIVO';
        if (estVal === 'RETRASO') {
            const overdue = isActivo ? esPrestamoVencido(p.fecha_limite) : { vencido: false };
            if (!overdue.vencido) return false;
        } else if (estVal) {
            if (p.estado !== estVal) return false;
        }

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
          <span style="font-family:var(--font-mono); font-size:0.82rem; color:var(--tx-secondary);">
            ${formatearFecha(x.fecha_prestamo)}
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
          <th>Fecha préstamo</th>
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
    const nTipo = $('#n-tipo')?.value;

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
    const tipoVal = $('#n-tipo')?.value || '';

    let list = cache.notificaciones.filter(n => {
        if (tipoVal) {
            const t = (n.tipo || '').toUpperCase();
            if (tipoVal === 'PRESTAMO_REGISTRADO' && t !== 'PRESTAMO_REGISTRADO' && t !== 'PRESTAMO') return false;
            if (tipoVal === 'RECORDATORIO' && t !== 'RECORDATORIO' && t !== 'POR_VENCER') return false;
            if (tipoVal === 'VENCIMIENTO' && t !== 'VENCIMIENTO') return false;
            if (tipoVal === 'BLOQUEO_POR_INCUMPLIMIENTO' && t !== 'BLOQUEO_POR_INCUMPLIMIENTO') return false;
            if (tipoVal === 'DEVOLUCION_CONFIRMADA' && t !== 'DEVOLUCION_CONFIRMADA') return false;
            if (tipoVal === 'DEVOLUCION_TARDIA_1' && t !== 'DEVOLUCION_TARDIA_1') return false;
            if (tipoVal === 'DEVOLUCION_TARDIA_2' && t !== 'DEVOLUCION_TARDIA_2') return false;
            if (tipoVal === 'BLOQUEO_POR_REINCIDENCIA' && t !== 'BLOQUEO_POR_REINCIDENCIA') return false;
            if (tipoVal === 'DEVOLUCION_CRITICA' && t !== 'DEVOLUCION_CRITICA' && t !== 'MULTA') return false;
        }

        if (!searchVal) return true;
        return String(n.usuario || '').toLowerCase().includes(searchVal) ||
            String(n.correo_destino || '').toLowerCase().includes(searchVal) ||
            String(n.tipo || '').toLowerCase().includes(searchVal) ||
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
        <p class="empty-state-desc">Los correos de préstamos registrados, recordatorios (1 día antes), vencimientos y devoluciones confirmadas aparecerán aquí automáticamente.</p>
      </div>
    `;
        return;
    }

    const rows = list.map(x => {
        const t = (x.tipo || '').toUpperCase();
        let tipoBadge;
        if (t === 'PRESTAMO_REGISTRADO' || t === 'PRESTAMO') {
            tipoBadge = `<span class="badge badge-info" style="font-weight:600;">PRESTAMO_REGISTRADO</span>`;
        } else if (t === 'RECORDATORIO' || t === 'POR_VENCER') {
            tipoBadge = `<span class="badge badge-wa" style="font-weight:600;">RECORDATORIO (1 día antes)</span>`;
        } else if (t === 'VENCIMIENTO') {
            tipoBadge = `<span class="badge" style="font-weight:600; background:#fff7ed; color:#c2410c; border:1px solid #fed7aa;">VENCIMIENTO (7 días extras)</span>`;
        } else if (t === 'BLOQUEO_POR_INCUMPLIMIENTO') {
            tipoBadge = `<span class="badge badge-er" style="font-weight:600; background:#fef2f2; color:#dc2626; border:1px solid #fecaca;">BLOQUEO_POR_INCUMPLIMIENTO</span>`;
        } else if (t === 'DEVOLUCION_CONFIRMADA') {
            tipoBadge = `<span class="badge badge-ok" style="font-weight:600;">DEVOLUCION_CONFIRMADA (A tiempo)</span>`;
        } else if (t === 'DEVOLUCION_TARDIA_1') {
            tipoBadge = `<span class="badge" style="font-weight:600; background:#fefce8; color:#854d0e; border:1px solid #fef08a;">DEVOLUCION_TARDIA_1 (1ª advertencia)</span>`;
        } else if (t === 'DEVOLUCION_TARDIA_2') {
            tipoBadge = `<span class="badge" style="font-weight:600; background:#fff7ed; color:#c2410c; border:1px solid #ffedd5;">DEVOLUCION_TARDIA_2 (Última advertencia)</span>`;
        } else if (t === 'BLOQUEO_POR_REINCIDENCIA') {
            tipoBadge = `<span class="badge badge-er" style="font-weight:600; background:#7f1d1d; color:#ffffff; border:1px solid #991b1b;">BLOQUEO_POR_REINCIDENCIA</span>`;
        } else if (t === 'DEVOLUCION_CRITICA' || t === 'MULTA') {
            tipoBadge = `<span class="badge" style="font-weight:600; background:#fdf4ff; color:#86198f; border:1px solid #f5d0fe;">DEVOLUCION_CRITICA</span>`;
        } else {
            tipoBadge = `<span class="badge badge-info">${esc(x.tipo)}</span>`;
        }

        let extra = {};
        try {
            extra = typeof x.datos === 'string' ? JSON.parse(x.datos) : (x.datos || {});
        } catch (e) {
            extra = {};
        }

        // Control de Fecha de Préstamo
        const fPrestamoRaw = extra.fecha_prestamo || (t === 'PRESTAMO' || t === 'PRESTAMO_REGISTRADO' ? x.fecha_creacion : (x.fecha_creacion || ''));
        const fechaPrestamo = fPrestamoRaw ? formatearFecha(fPrestamoRaw) : '—';

        // Control de Fecha Límite
        const fechaLimite = extra.fecha_limite ? formatearFecha(extra.fecha_limite) : '—';

        // Control de Fecha de Devolución
        let fechaDevolucion = '—';
        if (extra.fecha_devolucion) {
            const fDevFormatted = formatearFecha(extra.fecha_devolucion);
            const conRetraso = extra.con_retraso || (extra.monto && parseFloat(extra.monto) > 0) || (extra.dias_retraso && parseInt(extra.dias_retraso) > 0);
            if (conRetraso) {
                const montoStr = extra.monto !== undefined ? parseFloat(extra.monto).toFixed(2) : ((Number(extra.dias_retraso) || 1) * 2.5).toFixed(2);
                fechaDevolucion = `<strong style="color:var(--success-tx, #15803d);">${fDevFormatted}</strong> <span style="font-size:0.75rem; color:var(--danger); font-weight:600;">(Multa: Bs. ${montoStr})</span>`;
            } else {
                fechaDevolucion = `<strong style="color:var(--success-tx, #15803d);">${fDevFormatted}</strong>`;
            }
        } else if (t === 'DEVOLUCION_CONFIRMADA' || t === 'MULTA') {
            fechaDevolucion = '<strong style="color:var(--success-tx, #15803d);">Devuelto</strong>';
        } else {
            fechaDevolucion = '<span class="mu" style="font-size:0.75rem;">En curso / No devuelto</span>';
        }

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
        <td><span style="font-weight:600; color:var(--tx-main);">${fechaPrestamo}</span></td>
        <td><span style="font-weight:600; color:var(--primary);">${fechaLimite}</span></td>
        <td>${fechaDevolucion}</td>
      </tr>
    `;
    });

    container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Tipo de Notificación</th>
          <th>Usuario</th>
          <th>Correo destino</th>
          <th>Fecha Préstamo</th>
          <th>Fecha Límite</th>
          <th>Fecha Devolución</th>
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

// 1. Guardar Autor (Control de no repetir autores y validaciones)
setupForm('#f-autor', '#btn-save-autor', async d => {
    const nom = (d.nombre || '').trim();
    const nac = (d.nacionalidad || '').trim();
    if (!nom) throw new Error('El nombre del autor es obligatorio.');
    if (!/^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\.\-]+$/.test(nom)) {
        throw new Error('El nombre del autor solo debe contener letras, puntos y espacios.');
    }
    if (!nac) throw new Error('La nacionalidad del autor es obligatoria.');
    if (!/^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]+$/.test(nac)) {
        throw new Error('El país de origen solo debe contener letras y caracteres válidos.');
    }
    const normStr = str => (str || '').normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
    const paisOficialCrear = PAISES.find(p => normStr(p) === normStr(nac));
    if (!paisOficialCrear) {
        throw new Error(`El país "${nac}" no es válido. Debes seleccionar uno de los países que aparecen en las sugerencias al escribir.`);
    }
    d.nacionalidad = paisOficialCrear;

    // Validación preventiva en cliente para autor duplicado
    const existente = (cache.autores || []).find(a => a.nombre.trim().toLowerCase() === nom.toLowerCase());
    if (existente) {
        throw new Error(`⚠️ Ya existe un autor registrado con el nombre "${existente.nombre}". No se permiten autores duplicados.`);
    }

    try {
        await api(API.cat + '/autores', 'POST', d);
        await loadCatalogo();
        const hint = $('#hint-autor-duplicado');
        if (hint) hint.style.display = 'none';
    } catch (err) {
        if (err.status === 409) {
            throw new Error(`⚠️ Autor duplicado: ${err.message || 'Ya existe un autor con ese nombre.'}`);
        }
        throw err;
    }
}, 'Autor guardado exitosamente');

// 2. Guardar Libro (Requerimientos 5, 6, 7)
setupForm('#f-libro', '#btn-save-libro', async d => {
    const tit = (d.titulo || '').trim();
    if (!tit) throw new Error('El título del libro es obligatorio.');
    if (!d.autor_id) {
        throw new Error('Debe seleccionar obligatoriamente un autor para la obra.');
    }
    if (!d.genero) {
        throw new Error('Debe seleccionar obligatoriamente un género para la obra.');
    }
    const payload = {
        titulo: tit,
        autor_id: +d.autor_id,
        genero: d.genero,
        edicion: (d.edicion || '').trim(),
        ejemplares_totales: +d.ejemplares_totales || 1,
        sumar_si_existe: true
    };
    try {
        const res = await api(API.cat + '/libros', 'POST', payload);
        await loadCatalogo();
        if (res && res.ejemplares_totales > (+d.ejemplares_totales || 1)) {
            toast(`La obra ya existía; se sumaron ${+d.ejemplares_totales || 1} unidades a su inventario (total: ${res.ejemplares_totales}).`);
        }
    } catch (err) {
        if (err.status === 409) {
            throw new Error(`⚠️ Conflicto: ${err.message}`);
        }
        throw err;
    }
}, 'Libro incorporado al catálogo exitosamente');

// 3. Registrar Usuario (Requerimientos 4 y 10)
setupForm('#f-user', '#btn-save-user', async d => {
    const cod = (d.codigo || '').trim();
    const nom = (d.nombre || '').trim();
    const mail = (d.correo || '').trim();
    if (!cod || !/^\d+$/.test(cod)) {
        throw new Error('El Carnet de Identidad (CI) solo debe contener dígitos numéricos.');
    }
    if (!nom || !/^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s]+$/.test(nom)) {
        throw new Error('El nombre completo solo debe contener letras y espacios.');
    }
    if (!mail) {
        throw new Error('El correo es obligatorio.');
    }
    const payload = {
        codigo: cod,
        ci: cod,
        nombre: nom,
        correo: mail,
        tipo: d.tipo || 'ESTUDIANTE'
    };
    try {
        await api(API.pre + '/usuarios', 'POST', payload);
        await loadUsuarios();
    } catch (err) {
        if (err.status === 409) {
            throw new Error('⚠️ Carnet duplicado: Ya existe un usuario registrado con el CI proporcionado.');
        }
        throw err;
    }
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
            <li><strong>Usuarios inhabilitados automáticamente por mora:</strong> ${res.deshabilitados_mora ?? 0}</li>
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
        // 1. Inactivar / Dar de baja libro (Requerimiento 7 y 14)
        if (act === 'del-libro') {
            const titulo = b.dataset.t || `Libro #${id}`;
            showModal({
                title: 'Confirmar Inactivación de Libro',
                bodyHtml: `
          <div style="display:flex; flex-direction:column; gap:8px;">
            <p>¿Estás seguro de que deseas dar de baja o inactivar la obra <strong>"${esc(titulo)}"</strong>?</p>
            <div style="background:var(--card-bg-sec, #f8fafc); border:1px solid var(--border-color, #e2e8f0); border-radius:6px; padding:10px; font-size:0.85rem; color:var(--tx-secondary);">
              ℹ️ El libro pasará a estado <strong>INACTIVO</strong>. Si existen préstamos en curso de esta obra, el sistema impedirá su baja hasta que sean devueltos.
            </div>
          </div>
        `,
                confirmText: 'Inactivar libro',
                confirmClass: 'btn-danger',
                onConfirm: async () => {
                    try {
                        await api(`${API.pre}/libros/${id}`, 'DELETE');
                        toast(`"${titulo}" fue dado de baja correctamente.`);
                        await loadCatalogo();
                    } catch (err) {
                        if (err.status === 409) {
                            showModal({
                                title: '⚠️ Acción Bloqueada: Préstamos Activos',
                                bodyHtml: `
                                  <div style="background:var(--danger-bg, #fef2f2); border:1px solid var(--danger-border, #fecaca); border-radius:8px; padding:1rem; color:var(--danger-tx, #991b1b);">
                                    <p style="font-weight:700; margin-bottom:0.5rem;">No se puede dar de baja esta obra:</p>
                                    <p>${esc(err.message)}</p>
                                  </div>
                                  <p style="margin-top:0.75rem; font-size:0.875rem; color:var(--tx-secondary);">
                                    Debes registrar primero la devolución de todos los ejemplares prestados en la sección de <strong>Préstamos</strong>.
                                  </p>
                                `,
                                confirmText: 'Entendido',
                                cancelText: 'Cerrar'
                            });
                        } else {
                            toast(`Error al inactivar: ${err.message}`, true);
                        }
                    }
                }
            });
        }

        // 1.1 Reincorporar libro (Requerimiento 7)
        if (act === 'reincorporar-libro') {
            const titulo = b.dataset.t || `Libro #${id}`;
            showModal({
                title: 'Reincorporar Obra al Catálogo',
                bodyHtml: `<p>¿Deseas reactivar y poner nuevamente en circulación el libro <strong>"${esc(titulo)}"</strong>?</p>`,
                confirmText: 'Reincorporar',
                confirmClass: 'btn-primary',
                onConfirm: async () => {
                    await api(`${API.pre}/libros/${id}/reincorporar`, 'POST');
                    toast(`"${titulo}" ha sido reincorporado exitosamente al catálogo.`);
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

        // 3. Editar usuario (Requerimientos 4 y 8)
        if (act === 'edit-user') {
            const user = cache.usuarios.find(u => u.id === +id);
            if (!user) return;

            showModal({
                title: `Editar Usuario: ${user.nombre}`,
                bodyHtml: `
            <div style="display:flex; flex-direction:column; gap:12px;">
              <div class="form-group">
                <label class="form-label">Nombre completo <span class="req">*</span></label>
                <input id="modal-user-nom" class="form-control" value="${esc(user.nombre)}" required>
              </div>
              <div class="form-row">
                <div class="form-group flex-1">
                  <label class="form-label">C.I. / Documento <span class="req">*</span></label>
                  <input id="modal-user-ci" class="form-control" value="${esc(user.ci || user.codigo || '')}" required>
                </div>
                <div class="form-group flex-1">
                  <label class="form-label">Tipo de usuario <span class="req">*</span></label>
                  <select id="modal-user-tipo" class="form-control">
                    <option value="ESTUDIANTE" ${user.tipo === 'ESTUDIANTE' ? 'selected' : ''}>ESTUDIANTE</option>
                    <option value="DOCENTE" ${user.tipo === 'DOCENTE' ? 'selected' : ''}>DOCENTE</option>
                  </select>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">Correo <span class="req">*</span></label>
                <input id="modal-user-mail" type="email" class="form-control" value="${esc(user.correo || '')}" required>
              </div>
            </div>
          `,
                confirmText: 'Guardar cambios',
                confirmClass: 'btn-primary',
                onConfirm: async () => {
                    const nom = $('#modal-user-nom')?.value?.trim();
                    const ci = $('#modal-user-ci')?.value?.trim();
                    const mail = $('#modal-user-mail')?.value?.trim();
                    const tipo = $('#modal-user-tipo')?.value;

                    if (!nom) { toast('El nombre no puede estar vacío.', true); return false; }
                    if (!/^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s]+$/.test(nom)) { toast('El nombre solo debe contener letras y espacios.', true); return false; }
                    if (!ci || !/^\d+$/.test(ci)) { toast('El CI solo debe contener dígitos numéricos.', true); return false; }
                    if (!mail) { toast('El correo es obligatorio.', true); return false; }

                    try {
                        await api(`${API.pre}/usuarios/${id}`, 'PUT', {
                            nombre: nom,
                            ci: ci,
                            codigo: ci,
                            correo: mail,
                            tipo: tipo,
                            activo: user.activo
                        });
                        toast('Usuario actualizado exitosamente.');
                        await loadUsuarios();
                    } catch (err) {
                        toast(`Error al actualizar usuario: ${err.message}`, true);
                        return false;
                    }
                }
            });

            setTimeout(() => {
                $('#modal-user-ci')?.addEventListener('input', e => { e.target.value = e.target.value.replace(/\D/g, ''); });
                $('#modal-user-nom')?.addEventListener('input', e => { e.target.value = e.target.value.replace(/[^A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]/g, ''); });
            }, 100);
        }

        // 3.1 Dar de baja a un usuario (Requerimientos 3 y 14)
        if (act === 'baja') {
            const nombre = b.dataset.nom || `Usuario #${id}`;
            showModal({
                title: 'Confirmar Baja de Usuario',
                bodyHtml: `
          <div style="display:flex; flex-direction:column; gap:8px;">
            <p>¿Confirmas dar de baja a <strong>"${esc(nombre)}"</strong>?</p>
            <div style="background:var(--card-bg-sec, #f8fafc); border:1px solid var(--border-color, #e2e8f0); border-radius:6px; padding:10px; font-size:0.85rem; color:var(--tx-secondary);">
              ℹ️ El usuario quedará <strong>INACTIVO</strong> y no podrá solicitar nuevos préstamos. Si tiene préstamos pendientes, la baja será rechazada.
            </div>
          </div>
        `,
                confirmText: 'Dar de baja',
                confirmClass: 'btn-danger',
                onConfirm: async () => {
                    try {
                        await api(`${API.pre}/usuarios/${id}`, 'DELETE');
                        toast(`Usuario "${nombre}" dado de baja correctamente.`);
                        await loadUsuarios();
                    } catch (err) {
                        if (err.status === 409) {
                            showModal({
                                title: '⚠️ Acción Bloqueada: Préstamos Activos',
                                bodyHtml: `
                                  <div style="background:var(--danger-bg, #fef2f2); border:1px solid var(--danger-border, #fecaca); border-radius:8px; padding:1rem; color:var(--danger-tx, #991b1b);">
                                    <p style="font-weight:700; margin-bottom:0.5rem;">No se puede dar de baja a este usuario:</p>
                                    <p>${esc(err.message)}</p>
                                  </div>
                                  <p style="margin-top:0.75rem; font-size:0.875rem; color:var(--tx-secondary);">
                                    El usuario tiene libros en su poder. Debe registrar la devolución de todos sus préstamos activos antes de tramitar la baja.
                                  </p>
                                `,
                                confirmText: 'Entendido',
                                cancelText: 'Cerrar'
                            });
                        } else {
                            toast(`Error al dar de baja: ${err.message}`, true);
                        }
                    }
                }
            });
        }

        // 3.2 Reincorporar usuario (Requerimiento 3)
        if (act === 'reincorporar-user') {
            const nombre = b.dataset.nom || `Usuario #${id}`;
            showModal({
                title: 'Reincorporar Usuario',
                bodyHtml: `<p>¿Deseas reactivar al usuario <strong>"${esc(nombre)}"</strong> para que pueda volver a solicitar préstamos en la biblioteca?</p>`,
                confirmText: 'Reincorporar',
                confirmClass: 'btn-primary',
                onConfirm: async () => {
                    await api(`${API.pre}/usuarios/${id}/reincorporar`, 'POST');
                    toast(`Usuario "${nombre}" reactivado con éxito en el sistema.`);
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


// Restricción inmediata de caracteres en tiempo real (Requerimiento 4)
$('#user-cod')?.addEventListener('input', e => {
    e.target.value = e.target.value.replace(/\D/g, '');
});
$('#user-nom')?.addEventListener('input', e => {
    e.target.value = e.target.value.replace(/[^A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]/g, '');
});
$('#autor-nombre')?.addEventListener('input', e => {
    e.target.value = e.target.value.replace(/[^A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\.\-]/g, '');
});
$('#autor-nac')?.addEventListener('input', e => {
    e.target.value = e.target.value.replace(/[^A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]/g, '');
});

// Navegación directa al hacer clic en las tarjetas informativas del panel principal (Requerimiento 11)
document.addEventListener('click', e => {
    const card = e.target.closest('.kpi-card[data-nav]');
    if (card) {
        const targetTab = card.dataset.nav;
        if (targetTab && tabs[targetTab]) {
            show(targetTab);
        }
    }
});


// =============================================================================
// MODAL PARA GESTIONAR Y EDITAR AUTORES
// =============================================================================
function abrirModalGestionAutores() {
    const autores = cache.autores || [];
    if (!autores.length) {
        toast('Aún no hay autores registrados para editar.', true);
        return;
    }

    const modalBodyHtml = `
      <div style="display:flex; flex-direction:column; gap:14px;">
        <div class="form-group">
          <label class="form-label" for="sel-editar-autor">Selecciona el autor que deseas editar <span class="req">*</span></label>
          <select id="sel-editar-autor" class="form-control">
            ${autores.map(a => `<option value="${a.id}">${esc(a.nombre)}${a.nacionalidad ? ` (${esc(a.nacionalidad)})` : ''}</option>`).join('')}
          </select>
        </div>

        <div style="border-top:1px solid var(--border-color, #e2e8f0); padding-top:14px; display:flex; flex-direction:column; gap:12px;">
          <div class="form-group">
            <label class="form-label" for="edit-autor-nombre">Nombre del autor <span class="req">*</span></label>
            <input id="edit-autor-nombre" class="form-control" placeholder="Ej: Gabriel García Márquez" required>
            <div id="hint-edit-autor-duplicado" style="display:none; font-size:12px; color:var(--danger, #dc2626); margin-top:4px; font-weight:500;"></div>
          </div>
          <div class="form-group" style="position:relative;">
            <label class="form-label" for="edit-autor-nac">País de origen <span class="req">*</span></label>
            <input id="edit-autor-nac" class="form-control" placeholder="Escribe para buscar país (ej. Bolivia)" autocomplete="off" required>
            <div id="autocomplete-edit-paises" class="autocomplete-dropdown" style="display:none;"></div>
            <div id="hint-edit-autor-nac" style="display:none; font-size:12px; color:var(--danger, #dc2626); margin-top:4px; font-weight:500;"></div>
          </div>
        </div>

        <div style="background:var(--card-bg-sec, #f8fafc); border:1px solid var(--border-color, #e2e8f0); border-radius:6px; padding:10px; font-size:0.83rem; color:var(--tx-secondary); line-height:1.4;">
          <strong>Actualización sincronizada:</strong> Al guardar, todos los libros del catálogo que pertenezcan a este autor se actualizarán automáticamente.
        </div>
      </div>
    `;

    showModal({
        title: 'Ver y Editar Autores',
        bodyHtml: modalBodyHtml,
        confirmText: 'Guardar cambios',
        confirmClass: 'btn-primary',
        onConfirm: async () => {
            const sel = $('#sel-editar-autor');
            const autorId = sel ? +sel.value : null;
            if (!autorId) return false;

            const nom = $('#edit-autor-nombre')?.value?.trim();
            const nacInput = $('#edit-autor-nac')?.value?.trim();

            if (!nom) {
                toast('El nombre del autor no puede estar vacío.', true);
                return false;
            }
            if (!/^[A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\.\-]+$/.test(nom)) {
                toast('El nombre del autor solo debe contener letras, puntos y espacios.', true);
                return false;
            }

            if (!nacInput) {
                toast('El país de origen es obligatorio. Debes escoger un país de la lista.', true);
                return false;
            }

            // Validar que el país seleccionado pertenezca estrictamente a la lista oficial
            const normalize = str => (str || '').normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
            const paisOficial = PAISES.find(p => normalize(p) === normalize(nacInput));
            if (!paisOficial) {
                toast(`El país "${nacInput}" no es válido. Debes seleccionar uno de los países que aparecen en las sugerencias al escribir.`, true);
                const hint = $('#hint-edit-autor-nac');
                if (hint) {
                    hint.style.display = 'block';
                    hint.textContent = 'Debes escoger un país válido de las sugerencias (ej: Bolivia, Colombia, etc.).';
                }
                return false;
            }

            // Validar que no choque con otro autor
            const choque = (cache.autores || []).find(a => a.id !== autorId && a.nombre.trim().toLowerCase() === nom.toLowerCase());
            if (choque) {
                toast(`Ya existe otro autor registrado con el nombre "${nom}".`, true);
                return false;
            }

            try {
                await api(`${API.cat}/autores/${autorId}`, 'PUT', {
                    nombre: nom,
                    nacionalidad: paisOficial
                });
                toast('Autor actualizado correctamente. Todos los libros asociados han sido sincronizados.');
                await loadCatalogo();
                return true;
            } catch (err) {
                toast(`Error al actualizar autor: ${err.message}`, true);
                return false;
            }
        }
    });

    const cargarDatosAutor = () => {
        const sel = $('#sel-editar-autor');
        if (!sel) return;
        const currentId = +sel.value;
        const autor = (cache.autores || []).find(a => a.id === currentId);
        if (autor) {
            const inpNom = $('#edit-autor-nombre');
            const inpNac = $('#edit-autor-nac');
            if (inpNom) inpNom.value = autor.nombre || '';
            if (inpNac) inpNac.value = autor.nacionalidad || '';
            const hintNac = $('#hint-edit-autor-nac');
            if (hintNac) hintNac.style.display = 'none';
        }
    };

    setTimeout(() => {
        cargarDatosAutor();
        $('#sel-editar-autor')?.addEventListener('change', cargarDatosAutor);

        $('#edit-autor-nombre')?.addEventListener('input', e => {
            e.target.value = e.target.value.replace(/[^A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\.\-]/g, '');
            const nom = e.target.value.trim().toLowerCase();
            const currentId = +($('#sel-editar-autor')?.value || 0);
            const hint = $('#hint-edit-autor-duplicado');
            if (hint) {
                const existe = (cache.autores || []).find(a => a.id !== currentId && a.nombre.trim().toLowerCase() === nom);
                if (existe) {
                    hint.style.display = 'block';
                    hint.textContent = `Ya existe otro autor registrado con el nombre "${existe.nombre}".`;
                } else {
                    hint.style.display = 'none';
                }
            }
        });

        const inpNac = $('#edit-autor-nac');
        const dropNac = $('#autocomplete-edit-paises');
        if (inpNac && dropNac) {
            setupPaisAutocomplete(inpNac, dropNac);
            inpNac.addEventListener('input', e => {
                e.target.value = e.target.value.replace(/[^A-Za-zÁÉÍÓÚáéíóúñÑüÜ\s\(\)\.\-]/g, '');
                const hint = $('#hint-edit-autor-nac');
                if (hint) hint.style.display = 'none';
            });
        }
    }, 100);
}

// Botón para abrir modal de gestión de autores
$('#btn-gestionar-autores')?.addEventListener('click', abrirModalGestionAutores);

// Detección en tiempo real de autor duplicado al escribir en el formulario principal
$('#autor-nombre')?.addEventListener('input', e => {
    const nom = e.target.value.trim().toLowerCase();
    const hint = $('#hint-autor-duplicado');
    if (hint) {
        if (!nom) {
            hint.style.display = 'none';
        } else {
            const existe = (cache.autores || []).find(a => a.nombre.trim().toLowerCase() === nom);
            if (existe) {
                hint.style.display = 'block';
                hint.textContent = `⚠️ Ya existe un autor registrado con el nombre "${existe.nombre}". No se permiten autores repetidos.`;
            } else {
                hint.style.display = 'none';
            }
        }
    }
});


// =============================================================================
// AUTOCOMPLETE PARA PAÍS DE ORIGEN (MÁXIMO 5 SUGERENCIAS EN VIVO)
// =============================================================================
function setupPaisAutocomplete(inputEl, dropdownEl) {
    if (!inputEl || !dropdownEl) return;

    const normalize = str => (str || '').normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

    const render = (val) => {
        const qNorm = normalize(val);
        if (!qNorm) {
            dropdownEl.style.display = 'none';
            dropdownEl.innerHTML = '';
            return;
        }

        // Filtrar hasta máximo 5 opciones que coincidan
        const matches = PAISES.filter(p => normalize(p).includes(qNorm)).slice(0, 5);
        if (!matches.length) {
            dropdownEl.style.display = 'none';
            dropdownEl.innerHTML = '';
            return;
        }

        dropdownEl.innerHTML = matches.map(p => `
            <div class="autocomplete-item" data-val="${esc(p)}">
                <span>${esc(p)}</span>
            </div>
        `).join('');
        dropdownEl.style.display = 'block';
    };

    inputEl.addEventListener('input', e => {
        render(e.target.value);
    });

    inputEl.addEventListener('focus', e => {
        if (e.target.value) render(e.target.value);
    });

    // Selección al hacer clic en una sugerencia
    dropdownEl.addEventListener('mousedown', e => {
        const item = e.target.closest('.autocomplete-item');
        if (item) {
            inputEl.value = item.dataset.val;
            dropdownEl.style.display = 'none';
            dropdownEl.innerHTML = '';
            inputEl.dispatchEvent(new Event('change'));
        }
    });

    // Auto-completar al presionar Enter si hay sugerencias activas
    inputEl.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            const firstItem = dropdownEl.querySelector('.autocomplete-item');
            if (firstItem && dropdownEl.style.display !== 'none') {
                e.preventDefault();
                inputEl.value = firstItem.dataset.val;
                dropdownEl.style.display = 'none';
                dropdownEl.innerHTML = '';
                inputEl.dispatchEvent(new Event('change'));
            }
        }
    });

    // Normalizar al perder foco si coincide con un país válido
    inputEl.addEventListener('blur', () => {
        setTimeout(() => {
            const val = inputEl.value.trim();
            if (val) {
                const exact = PAISES.find(p => normalize(p) === normalize(val));
                if (exact) {
                    inputEl.value = exact;
                }
            }
            dropdownEl.style.display = 'none';
        }, 200);
    });

    document.addEventListener('click', e => {
        if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) {
            dropdownEl.style.display = 'none';
        }
    });
}

// Inicializar autocompletado en formulario principal
setupPaisAutocomplete($('#autor-nac'), $('#autocomplete-paises'));
