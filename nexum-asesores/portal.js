/* ============================================================
   NEXUM ASESORES — portal.js
   Dashboard del cliente: Charts, chatbot privado, ETL status,
   vencimientos, alertas, modelo predictivo
   ============================================================ */
'use strict';

/* ══════════════════════════════════════════════════════════
   MOCK DATA — Simula la capa Gold de PostgreSQL
   En producción estos datos vendrían de:
   GET /api/flujo-caja/{cliente_id}  →  fact_flujo_caja
   GET /api/riesgo/{cliente_id}      →  fact_score_riesgo
   GET /api/vencimientos/{cliente_id} → dim_tiempo + fact_declaraciones
   ══════════════════════════════════════════════════════════ */
const MOCK_DATA = {
  cliente: {
    id: 'CL-2024-0042',
    nombre: 'Tecnopyme SL',
    sector: 'Servicios profesionales',
    plan: 'Asesoría Recurrente',
    asesor: 'Laura García',
  },

  flujoCaja: {
    labels: [
      'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul',
      'Ago (p)', 'Sep (p)', 'Oct (p)',
    ],
    real:       [38200, 29800, 41500, 35600, 44200, 31800, null, null, null, null],
    proyectado: [null, null, null, null, null, 31800, 28400, 24800, 18200, 9100],
    lower:      [null, null, null, null, null, 30100, 25200, 20400, 13800,  5200],
    upper:      [null, null, null, null, null, 33500, 31600, 29200, 22600, 13000],
  },

  scoreRiesgo: {
    historico: {
      labels: ['Ago 25','Sep 25','Oct 25','Nov 25','Dic 25','Ene 26','Feb 26','Mar 26','Abr 26','May 26','Jun 26','Jul 26'],
      scores:  [68, 72, 65, 58, 61, 55, 51, 48, 46, 44, 50, 42],
    },
    features: [
      { name: 'Días promedio atraso', importancia: 38, valor: '2.3 días', estado: 'good' },
      { name: 'Inconsistencias IVA/IRPF', importancia: 25, valor: '0.04 ratio', estado: 'good' },
      { name: 'Facturas contraparte fallecida', importancia: 72, valor: '1 (detectada)', estado: 'bad' },
      { name: 'Identidades inválidas en padrón', importancia: 65, valor: '0.0% de facturas', estado: 'good' },
      { name: 'Desviación de ubigeo fiscal', importancia: 30, valor: '15% de compras', estado: 'warn' },
      { name: 'Suplantación de representante', importancia: 15, valor: 'No detectado', estado: 'good' },
    ],
  },

  vencimientos: [
    { modelo: 'Modelo 111 — IRPF Retenciones', desc: 'Retenciones trabajadores Q2', fecha: '20 jul 2026', diasRestantes: 6,  importe: 3840, tipo: 'urgente' },
    { modelo: 'Modelo 130 — IRPF fraccionado', desc: 'Pago fraccionado Q2 2026',   fecha: '20 jul 2026', diasRestantes: 6,  importe: 1200, tipo: 'urgente' },
    { modelo: 'Modelo 303 — IVA Q3',           desc: 'IVA tercer trimestre 2026',  fecha: '20 oct 2026', diasRestantes: 98, importe: 7240, tipo: 'ok' },
    { modelo: 'Modelo 115 — Alquiler',          desc: 'Retención alquiler Q2',      fecha: '20 jul 2026', diasRestantes: 6,  importe: 890,  tipo: 'proximo' },
    { modelo: 'Modelo 200 — IS',                desc: 'Impuesto Sociedades 2025',   fecha: '25 jul 2026', diasRestantes: 11, importe: 12400, tipo: 'proximo' },
    { modelo: 'Modelo 303 — IVA Q2',            desc: 'IVA segundo trimestre',       fecha: '20 abr 2026', diasRestantes: 0,  importe: 6840, tipo: 'completado' },
    { modelo: 'Modelo 111 — IRPF Q1',           desc: 'Retenciones Q1 2026',         fecha: '20 ene 2026', diasRestantes: 0,  importe: 3210, tipo: 'completado' },
  ],

  facturacion: {
    labels: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun'],
    data:   [28400, 22100, 31200, 26800, 33500, 24600],
  },

  alertas: [
    { tipo: 'danger',  titulo: 'Vencimiento urgente: Modelo 111 en 6 días', desc: 'El 20 de julio vence el Modelo 111 (retenciones IRPF Q2). Importe estimado: 3.840€. Tu caja proyectada cubre el pago, pero te recomendamos reservar los fondos hoy.', fecha: 'Hoy, 11:00' },
    { tipo: 'danger',  titulo: 'Vencimiento urgente: Modelo 115 en 6 días', desc: 'Retención de alquiler Q2: 890€. Vence el 20 de julio junto al Modelo 111. Ambos pagos suman 4.730€.', fecha: 'Hoy, 11:00' },
    { tipo: 'warning', titulo: 'Impuesto de Sociedades: provisionar 12.400€ antes del 25 jul', desc: 'Tu cuota del IS 2025 asciende a 12.400€. El modelo de flujo de caja detecta que tu saldo proyectado podría bajar de 20.000€ en agosto si no provisiones antes del día 18.', fecha: 'Hoy, 09:15' },
    { tipo: 'warning', titulo: 'Variación de facturación: −12.3% vs. Q1', desc: 'El modelo predictivo detectó una caída trimestral en tu facturación. Si la tendencia continúa, el score de riesgo podría subir 6-10 puntos en el próximo cálculo.', fecha: 'Lun 14 jul' },
    { tipo: 'info',    titulo: 'Plan fiscal Q3-Q4 2026 disponible', desc: 'Laura García (tu asesora) ha publicado el plan fiscal para el segundo semestre. Incluye oportunidades de deducción y optimización de pagos fraccionados.', fecha: 'Lun 14 jul' },
    { tipo: 'info',    titulo: 'Modelo reentrenado: sin drift detectado', desc: 'El retrain semanal de ambos modelos (XGBoost y Prophet) se completó con éxito. No se detectó drift de datos. Métricas estables dentro del umbral aceptable.', fecha: 'Lun 14 jul, 05:25' },
  ],

  etlSteps: [
    { label: 'Bronze', desc: 'MinIO',      status: 'ok',      time: '02:05' },
    { label: 'Silver', desc: 'PostgreSQL', status: 'ok',      time: '03:12' },
    { label: 'Gold',   desc: 'PostgreSQL', status: 'ok',      time: '04:03' },
    { label: 'Models', desc: 'XGBoost+P.', status: 'ok',      time: '05:18' },
    { label: 'API',    desc: 'FastAPI',    status: 'running', time: 'live'  },
    { label: 'Portal', desc: 'Frontend',   status: 'ok',      time: 'live'  },
  ],

  dags: [
    { name: 'dag_bronze_ingest', schedule: 'Diario 02:00', lastRun: '14 jul 02:05', status: 'success' },
    { name: 'dag_silver_transform', schedule: 'Diario 03:00', lastRun: '14 jul 03:12', status: 'success' },
    { name: 'dag_gold_build', schedule: 'Diario 04:00', lastRun: '14 jul 04:03', status: 'success' },
    { name: 'dag_retrain_models', schedule: 'Semanal lun 05:00', lastRun: '14 jul 05:18', status: 'success' },
  ],
};

/* ══════════════════════════════════════════════════════════
   1. AUTENTICACIÓN (mock JWT)
   ══════════════════════════════════════════════════════════ */
const AUTH = {
  DEMO_USER: 'demo@pyme.es',
  DEMO_PASS: 'nexum2026',
  TOKEN_KEY: 'nexum_portal_token',

  login(email, pass) {
    if (email === this.DEMO_USER && pass === this.DEMO_PASS) {
      // En prod: POST /api/auth/login → {access_token, cliente_id}
      const token = { clienteId: 'CL-2024-0042', exp: Date.now() + 3600000 };
      sessionStorage.setItem(this.TOKEN_KEY, JSON.stringify(token));
      return true;
    }
    return false;
  },

  isAuthenticated() {
    try {
      const t = JSON.parse(sessionStorage.getItem(this.TOKEN_KEY) || 'null');
      return t && t.exp > Date.now();
    } catch { return false; }
  },

  logout() {
    sessionStorage.removeItem(this.TOKEN_KEY);
  },
};

/* ── Login form ─────────────────────────────────────────── */
function initLogin() {
  const loginScreen = document.getElementById('loginScreen');
  const loginForm   = document.getElementById('loginForm');
  const loginError  = document.getElementById('loginError');
  const loginBtn    = document.getElementById('loginBtn');

  if (!loginScreen) return;

  // Si ya está autenticado, ocultar pantalla de login
  if (AUTH.isAuthenticated()) {
    loginScreen.classList.add('hidden');
    initPortal();
    return;
  }

  loginForm?.addEventListener('submit', async e => {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value.trim();
    const pass  = document.getElementById('loginPass').value;

    loginBtn.disabled = true;
    loginBtn.textContent = 'Verificando...';
    loginError.style.display = 'none';

    await new Promise(r => setTimeout(r, 800)); // simula latencia de red

    if (AUTH.login(email, pass)) {
      loginScreen.style.transition = 'opacity .4s ease';
      loginScreen.style.opacity = '0';
      setTimeout(() => {
        loginScreen.classList.add('hidden');
        initPortal();
      }, 400);
    } else {
      loginError.style.display = 'block';
      loginBtn.disabled = false;
      loginBtn.textContent = 'Acceder al portal';
      document.getElementById('loginPass').value = '';
      document.getElementById('loginPass').focus();
    }
  });

  // Logout
  document.getElementById('logoutBtn')?.addEventListener('click', () => {
    AUTH.logout();
    window.location.reload();
  });
}

/* ══════════════════════════════════════════════════════════
   2. PORTAL PRINCIPAL
   ══════════════════════════════════════════════════════════ */
function initPortal() {
  updateTopbarDate();
  setInterval(updateTopbarDate, 60000);
  initSidebarNav();
  initMobileSidebar();
  populateClientInfo();
  renderKPIs();
  renderCharts();
  renderVencimientos();
  renderAlertas();
  renderETLPipeline();
  renderDAGStatus();
  renderFeatureTable();
  renderProvisionAlerts();
  renderChatSuggestions();
  initPrivateChatbot();
  initKycShield();
}

function updateTopbarDate() {
  const el = document.getElementById('topbarDate');
  const dashDate = document.getElementById('dashDate');
  const now = new Date();
  const opts = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' };
  const formatted = now.toLocaleDateString('es-ES', opts);
  if (el) el.textContent = formatted;
  if (dashDate) dashDate.textContent = formatted;
}

function populateClientInfo() {
  const c = MOCK_DATA.cliente;
  const nameEl   = document.getElementById('clientName');
  const avatarEl = document.getElementById('clientAvatar');
  if (nameEl) nameEl.textContent = c.nombre;
  if (avatarEl) avatarEl.textContent = c.nombre[0];
}

/* ── Navegación sidebar ─────────────────────────────────── */
function initSidebarNav() {
  const links = document.querySelectorAll('.sidebar-link[data-section]');
  const sections = document.querySelectorAll('.portal-section');
  const titleEl = document.getElementById('topbarTitle');

  const sectionTitles = {
    dashboard:   'Dashboard',
    vencimientos:'Vencimientos',
    flujo:       'Flujo de Caja',
    riesgo:      'Riesgo Fiscal',
    prediccion:  'Modelo Predictivo',
    chatbot:     'Asistente Virtual',
    alertas:     'Alertas',
  };

  function activate(sectionId) {
    links.forEach(l => {
      const isActive = l.dataset.section === sectionId;
      l.classList.toggle('active', isActive);
      l.setAttribute('aria-current', isActive ? 'page' : 'false');
    });
    sections.forEach(s => {
      s.classList.toggle('active', s.id === `section-${sectionId}`);
    });
    if (titleEl) titleEl.textContent = sectionTitles[sectionId] || sectionId;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  links.forEach(link => {
    link.addEventListener('click', () => activate(link.dataset.section));
  });

  // Activar desde links internos (botones de secciones que navegan al chatbot, etc.)
  document.querySelectorAll('[data-nav]').forEach(btn => {
    btn.addEventListener('click', () => activate(btn.dataset.nav));
  });
}

/* ── Mobile sidebar ─────────────────────────────────────── */
function initMobileSidebar() {
  const toggle  = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('portalSidebar');
  const overlay = document.getElementById('sidebarOverlay');

  const open  = () => { sidebar?.classList.add('mobile-open'); overlay?.classList.add('visible'); toggle?.setAttribute('aria-expanded','true'); document.body.style.overflow = 'hidden'; };
  const close = () => { sidebar?.classList.remove('mobile-open'); overlay?.classList.remove('visible'); toggle?.setAttribute('aria-expanded','false'); document.body.style.overflow = ''; };

  toggle?.addEventListener('click', () => sidebar?.classList.contains('mobile-open') ? close() : open());
  overlay?.addEventListener('click', close);

  // Cerrar al navegar
  document.querySelectorAll('.sidebar-link').forEach(l => l.addEventListener('click', close));
}

/* ── KPIs dinámicos ────────────────────────────────────── */
function renderKPIs() {
  // Score de riesgo → semáforo
  const score = 42;
  const semaRed    = document.getElementById('semaRed');
  const semaYellow = document.getElementById('semaYellow');
  const semaGreen  = document.getElementById('semaGreen');
  const semaLabel  = document.getElementById('semaLabel');
  const kpiCard    = document.getElementById('kpiRiesgo');
  const kpiVal     = document.getElementById('kpiRiesgoVal');

  // Quitar todas las clases activas
  [semaRed, semaYellow, semaGreen].forEach(el => el?.classList.remove('active-red','active-yellow','active-green'));

  if (score <= 40) {
    semaGreen?.classList.add('active-green');
    if (semaLabel) semaLabel.textContent = 'Bajo';
    kpiCard?.classList.replace('risk-med', 'risk-low');
  } else if (score <= 70) {
    semaYellow?.classList.add('active-yellow');
    if (semaLabel) semaLabel.textContent = 'Moderado';
  } else {
    semaRed?.classList.add('active-red');
    if (semaLabel) semaLabel.textContent = 'Alto';
    kpiCard?.classList.replace('risk-med', 'risk-high');
  }

  // Animar contador del score
  animateValue(kpiVal, 0, score, 1200);

  // Cuenta regresiva próximo vencimiento
  const nextDays = document.getElementById('nextDeadlineDays');
  if (nextDays) animateValue(nextDays, 0, 6, 800);
}

function animateValue(el, from, to, duration) {
  if (!el) return;
  const start = performance.now();
  const step = now => {
    const p = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.floor(from + (to - from) * ease);
    if (p < 1) requestAnimationFrame(step);
    else el.textContent = to;
  };
  requestAnimationFrame(step);
}

/* ══════════════════════════════════════════════════════════
   3. CHARTS (Chart.js)
   ══════════════════════════════════════════════════════════ */
const CHART_DEFAULTS = {
  fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
  navy:       '#1A365D',
  gold:       '#2B6CB0',
  goldLight:  'rgba(43,108,176,.15)',
  success:    '#2F855A',
  danger:     '#C53030',
  warning:    '#D69E2E',
  textMid:    '#4A5568',
  textLight:  '#718096',
  gridColor:  'rgba(26,54,93,.06)',
};

Chart.defaults.font.family = CHART_DEFAULTS.fontFamily;
Chart.defaults.color       = CHART_DEFAULTS.textMid;

function renderCharts() {
  // Esperar a que Chart.js esté disponible
  if (typeof Chart === 'undefined') {
    setTimeout(renderCharts, 100);
    return;
  }
  renderFlujoCajaChart();
  renderRiesgoChart();
  renderFacturacionChart();
  renderVencimientosChart();
  renderCumplimientoChart();
  renderFlujoDetalleChart();
  renderComponentesChart();
  renderPrediccionChart();
  renderRiesgoHistoricoChart();
  initPeriodButtons();
}

/* Flujo de caja — Dashboard principal */
let flujoCajaChart = null;
function renderFlujoCajaChart(period = 30) {
  const ctx = document.getElementById('chartFlujoCaja');
  if (!ctx) return;
  if (flujoCajaChart) flujoCajaChart.destroy();

  const d = MOCK_DATA.flujoCaja;
  // Filtrar por periodo
  const visible = period === 30 ? 7 : period === 60 ? 8 : 10;
  const labels  = d.labels.slice(0, visible);

  flujoCajaChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Real',
          data: d.real.slice(0, visible),
          borderColor: CHART_DEFAULTS.navy,
          backgroundColor: 'transparent',
          borderWidth: 2.5,
          pointBackgroundColor: CHART_DEFAULTS.navy,
          pointRadius: 4,
          tension: .4,
          spanGaps: false,
        },
        {
          label: 'Proyectado',
          data: d.proyectado.slice(0, visible),
          borderColor: CHART_DEFAULTS.gold,
          backgroundColor: 'transparent',
          borderWidth: 2,
          borderDash: [6, 4],
          pointBackgroundColor: CHART_DEFAULTS.gold,
          pointRadius: 4,
          tension: .4,
          spanGaps: false,
        },
        {
          label: 'Límite superior',
          data: d.upper.slice(0, visible),
          borderColor: 'transparent',
          backgroundColor: CHART_DEFAULTS.goldLight,
          fill: '+1',
          tension: .4,
          pointRadius: 0,
          spanGaps: false,
        },
        {
          label: 'Límite inferior',
          data: d.lower.slice(0, visible),
          borderColor: 'transparent',
          backgroundColor: CHART_DEFAULTS.goldLight,
          fill: false,
          tension: .4,
          pointRadius: 0,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ctx.dataset.label + ': ' + (ctx.raw !== null ? '€' + ctx.raw.toLocaleString('es-ES') : 'n/a'),
          },
        },
      },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.gridColor } },
        y: {
          grid: { color: CHART_DEFAULTS.gridColor },
          ticks: { callback: v => '€' + (v / 1000).toFixed(0) + 'k' },
        },
      },
    },
  });
}

/* Score de riesgo — mini chart dashboard */
function renderRiesgoChart() {
  const ctx = document.getElementById('chartRiesgo');
  if (!ctx) return;
  const scores = [68, 72, 65, 58, 61, 55, 51, 48, 46, 44, 50, 42];
  const colors = scores.map(s =>
    s <= 40 ? CHART_DEFAULTS.success :
    s <= 70 ? CHART_DEFAULTS.warning :
              CHART_DEFAULTS.danger
  );
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['A','S','O','N','D','E','F','M','A','M','J','J'],
      datasets: [{ data: scores, backgroundColor: colors, borderRadius: 4, borderSkipped: false }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => 'Score: ' + c.raw } } },
      scales: {
        x: { grid: { display: false } },
        y: { min: 0, max: 100, grid: { color: CHART_DEFAULTS.gridColor }, ticks: { stepSize: 20 } },
      },
    },
  });
}

/* Facturación */
function renderFacturacionChart() {
  const ctx = document.getElementById('chartFacturacion');
  if (!ctx) return;
  const d = MOCK_DATA.facturacion;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: d.labels,
      datasets: [{
        data: d.data,
        backgroundColor: ctx2 => {
          const gradient = ctx2.chart.ctx.createLinearGradient(0, 0, 0, 200);
          gradient.addColorStop(0, CHART_DEFAULTS.navy);
          gradient.addColorStop(1, 'rgba(10,22,40,.4)');
          return gradient;
        },
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => '€' + c.raw.toLocaleString('es-ES') } } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: CHART_DEFAULTS.gridColor }, ticks: { callback: v => '€' + (v/1000).toFixed(0) + 'k' } },
      },
    },
  });
}

/* Vencimientos bar chart */
function renderVencimientosChart() {
  const ctx = document.getElementById('chartVencimientos');
  if (!ctx) return;
  const venc = MOCK_DATA.vencimientos.filter(v => v.tipo !== 'completado');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: venc.map(v => v.modelo.split('—')[0].trim()),
      datasets: [{
        label: 'Importe (€)',
        data: venc.map(v => v.importe),
        backgroundColor: venc.map(v =>
          v.tipo === 'urgente' ? 'rgba(220,38,38,.75)' :
          v.tipo === 'proximo' ? 'rgba(217,119,6,.75)' :
                                 'rgba(5,150,105,.75)'
        ),
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => '€' + c.raw.toLocaleString('es-ES') } } },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.gridColor }, ticks: { callback: v => '€' + (v/1000).toFixed(0) + 'k' } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

/* Cumplimiento doughnut */
function renderCumplimientoChart() {
  const ctx = document.getElementById('chartCumplimiento');
  if (!ctx) return;
  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Presentadas a tiempo', 'Pendiente', 'Con retraso'],
      datasets: [{
        data: [7, 1, 1],
        backgroundColor: [CHART_DEFAULTS.success, CHART_DEFAULTS.warning, CHART_DEFAULTS.danger],
        borderWidth: 0,
        hoverOffset: 6,
      }],
    },
    options: {
      cutout: '65%',
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: c => c.label + ': ' + c.raw + '/9' } },
      },
    },
  });
}

/* Flujo detalle 90d */
function renderFlujoDetalleChart() {
  const ctx = document.getElementById('chartFlujoDetalle');
  if (!ctx) return;
  const labels = ['Hoy','Jul W3','Jul W4','Ago W1','Ago W2','Ago W3','Ago W4','Sep W1','Sep W2','Sep W3','Sep W4','Oct W1'];
  const real   = [31450, null, null, null, null, null, null, null, null, null, null, null];
  const proj   = [31450, 28900, 26200, 24800, 22400, 20100, 18200, 16400, 14800, 13200, 11400, 9100];
  const lower  = [null, 26000, 23000, 20400, 18000, 15600, 13800, 12000, 10400, 9000, 7400, 5200];
  const upper  = [null, 31800, 29400, 29200, 26800, 24600, 22600, 20800, 19200, 17400, 15400, 13000];

  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Real', data: real, borderColor: CHART_DEFAULTS.navy, borderWidth: 3, pointRadius: 5, pointBackgroundColor: CHART_DEFAULTS.navy, tension: 0, spanGaps: false },
        { label: 'Proyectado', data: proj, borderColor: CHART_DEFAULTS.gold, borderWidth: 2, borderDash: [5,4], pointRadius: 3, pointBackgroundColor: CHART_DEFAULTS.gold, tension: .4, spanGaps: false },
        { label: 'Banda superior', data: upper, borderColor: 'transparent', backgroundColor: 'rgba(201,168,76,.15)', fill: '+1', pointRadius: 0, tension: .4, spanGaps: false },
        { label: 'Banda inferior', data: lower, borderColor: 'transparent', backgroundColor: 'rgba(201,168,76,.15)', fill: false, pointRadius: 0, tension: .4, spanGaps: false },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { filter: i => i.text !== 'Banda superior' && i.text !== 'Banda inferior', boxWidth: 14 } },
        tooltip: { callbacks: { label: c => c.dataset.label + ': €' + (c.raw?.toLocaleString('es-ES') ?? 'n/a') } },
      },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.gridColor }, ticks: { font: { size: 10 } } },
        y: { grid: { color: CHART_DEFAULTS.gridColor }, ticks: { callback: v => '€' + (v/1000).toFixed(0) + 'k' } },
      },
    },
  });
}

/* Componentes Prophet */
function renderComponentesChart() {
  const ctx = document.getElementById('chartComponentes');
  if (!ctx) return;
  const labels = ['E','F','M','A','M','J','J','A','S','O','N','D'];
  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Tendencia', data: [24000,24200,24600,24900,25200,25000,24800,24600,24200,23800,23500,23000], borderColor: CHART_DEFAULTS.navy, borderWidth: 2, pointRadius: 2, tension: .5, fill: false },
        { label: 'Estacionalidad', data: [4400,-1900,6800,1700,8200,-700,-200,2400,0,4800,6200,3400], borderColor: CHART_DEFAULTS.gold, borderWidth: 2, pointRadius: 2, tension: .5, fill: false, borderDash: [4,3] },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top', labels: { boxWidth: 12 } } },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.gridColor } },
        y: { grid: { color: CHART_DEFAULTS.gridColor }, ticks: { callback: v => '€' + (v/1000).toFixed(0) + 'k' } },
      },
    },
  });
}

/* Predicción ingresos */
function renderPrediccionChart() {
  const ctx = document.getElementById('chartPrediccion');
  if (!ctx) return;
  const labels = ['Jul','Ago (p)','Sep (p)','Oct (p)'];
  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Predicción central', data: [24600, 26800, 28400, 25200], borderColor: CHART_DEFAULTS.gold, borderWidth: 2.5, pointRadius: 5, pointBackgroundColor: CHART_DEFAULTS.gold, tension: .4 },
        { label: 'Banda sup 80%', data: [24600, 31600, 33800, 30000], borderColor: 'transparent', backgroundColor: 'rgba(201,168,76,.15)', fill: '+1', pointRadius: 0, tension: .4 },
        { label: 'Banda inf 80%', data: [24600, 22000, 23000, 20400], borderColor: 'transparent', backgroundColor: 'rgba(201,168,76,.15)', fill: false, pointRadius: 0, tension: .4 },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.dataset.label + ': €' + (c.raw/1000).toFixed(1) + 'k' } } },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.gridColor } },
        y: { grid: { color: CHART_DEFAULTS.gridColor }, ticks: { callback: v => '€' + (v/1000).toFixed(0) + 'k' } },
      },
    },
  });
}

/* Score de riesgo histórico (sección riesgo) */
function renderRiesgoHistoricoChart() {
  const ctx = document.getElementById('chartRiesgoHistorico');
  if (!ctx) return;
  const d = MOCK_DATA.scoreRiesgo.historico;

  // Zonas de color de fondo
  const plugin = {
    id: 'riskZones',
    beforeDraw(chart) {
      const { ctx: c, chartArea: a, scales: { y } } = chart;
      if (!a) return;
      c.save();
      [[0,40,'rgba(5,150,105,.06)'],[41,70,'rgba(217,119,6,.06)'],[71,100,'rgba(220,38,38,.06)']].forEach(([lo,hi,col]) => {
        c.fillStyle = col;
        c.fillRect(a.left, y.getPixelForValue(hi), a.width, y.getPixelForValue(lo) - y.getPixelForValue(hi));
      });
      c.restore();
    },
  };

  new Chart(ctx, {
    type: 'line',
    plugins: [plugin],
    data: {
      labels: d.labels,
      datasets: [{
        label: 'Score de riesgo',
        data: d.scores,
        borderColor: CHART_DEFAULTS.navy,
        backgroundColor: 'rgba(10,22,40,.08)',
        borderWidth: 2.5,
        pointBackgroundColor: d.scores.map(s => s<=40 ? CHART_DEFAULTS.success : s<=70 ? CHART_DEFAULTS.warning : CHART_DEFAULTS.danger),
        pointRadius: 5,
        fill: true,
        tension: .4,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => 'Score: ' + c.raw + '/100' } } },
      scales: {
        x: { grid: { color: CHART_DEFAULTS.gridColor } },
        y: { min: 0, max: 100, grid: { color: CHART_DEFAULTS.gridColor }, ticks: { stepSize: 20 } },
      },
    },
  });
}

/* ── Period buttons ─────────────────────────────────────── */
function initPeriodButtons() {
  document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed','false'); });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed','true');
      renderFlujoCajaChart(parseInt(btn.dataset.period));
    });
  });
}

/* ══════════════════════════════════════════════════════════
   4. VENCIMIENTOS
   ══════════════════════════════════════════════════════════ */
function renderVencimientos() {
  const list = document.getElementById('vencimientosList');
  if (!list) return;

  list.innerHTML = MOCK_DATA.vencimientos.map(v => `
    <div class="vencimiento-item ${v.tipo}" role="listitem">
      <div class="v-countdown" aria-label="${v.diasRestantes} días restantes">
        <div class="v-days">${v.tipo === 'completado' ? '✓' : v.diasRestantes}</div>
        <div class="v-unit">${v.tipo === 'completado' ? 'hecho' : 'días'}</div>
      </div>
      <div class="v-info">
        <div class="v-modelo">${escHtml(v.modelo)}</div>
        <div class="v-desc">${escHtml(v.desc)}</div>
        <div class="v-fecha">Vence: ${escHtml(v.fecha)}</div>
      </div>
      <div class="v-importe">
        <div class="v-monto">€${v.importe.toLocaleString('es-ES')}</div>
        <div class="v-monto-label">estimado</div>
      </div>
      <span class="v-status status-${v.tipo}">
        ${v.tipo === 'urgente' ? '🔴 Urgente' : v.tipo === 'proximo' ? '🟡 Próximo' : v.tipo === 'ok' ? '🟢 En plazo' : '✅ Completado'}
      </span>
    </div>
  `).join('');
}

/* ══════════════════════════════════════════════════════════
   5. ALERTAS
   ══════════════════════════════════════════════════════════ */
function renderAlertas() {
  const list = document.getElementById('alertasList');
  if (!list) return;

  const icons = {
    danger:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    info:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  };

  list.innerHTML = MOCK_DATA.alertas.map(a => `
    <div class="alert-item ${a.tipo}" role="listitem">
      <div class="alert-icon" aria-hidden="true">${icons[a.tipo]}</div>
      <div>
        <div class="alert-title">${escHtml(a.titulo)}</div>
        <div class="alert-desc">${escHtml(a.desc)}</div>
        <div class="alert-date">${escHtml(a.fecha)}</div>
      </div>
    </div>
  `).join('');
}

/* ══════════════════════════════════════════════════════════
   6. ETL PIPELINE
   ══════════════════════════════════════════════════════════ */
function renderETLPipeline() {
  const container = document.getElementById('etlPipeline');
  if (!container) return;

  const statusColors = {
    ok:      { bg: '#D1FAE5', border: '#059669', text: '#059669', label: '✓ OK' },
    running: { bg: '#FEF3C7', border: '#D97706', text: '#D97706', label: '⟳ Running' },
    failed:  { bg: '#FEE2E2', border: '#DC2626', text: '#DC2626', label: '✗ Failed' },
  };

  container.innerHTML = MOCK_DATA.etlSteps.map((step, i) => {
    const sc = statusColors[step.status];
    const isLast = i === MOCK_DATA.etlSteps.length - 1;
    return `
      <div style="display:flex;align-items:center;gap:0;flex-shrink:0">
        <div style="display:flex;flex-direction:column;align-items:center;gap:.4rem;padding:.75rem 1.25rem;background:${sc.bg};border:2px solid ${sc.border};border-radius:12px;min-width:100px;text-align:center">
          <span style="font-size:.8rem;font-weight:800;color:#0A1628">${escHtml(step.label)}</span>
          <span style="font-size:.7rem;color:var(--text-mid)">${escHtml(step.desc)}</span>
          <span style="font-size:.68rem;font-weight:700;color:${sc.text}">${sc.label}</span>
          <span style="font-size:.65rem;color:var(--text-light)">${escHtml(step.time)}</span>
        </div>
        ${!isLast ? `<div style="width:32px;height:2px;background:linear-gradient(90deg,${sc.border},${statusColors[MOCK_DATA.etlSteps[i+1].status].border});flex-shrink:0" aria-hidden="true"></div>` : ''}
      </div>
    `;
  }).join('');
}

/* ── DAG Status ─────────────────────────────────────────── */
function renderDAGStatus() {
  const el = document.getElementById('dagStatus');
  if (!el) return;

  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:.5rem">` +
    MOCK_DATA.dags.map(dag => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:.5rem .75rem;background:var(--cream);border-radius:8px">
        <div>
          <div style="font-size:.78rem;font-weight:700;color:var(--navy)">${escHtml(dag.name)}</div>
          <div style="font-size:.68rem;color:var(--text-light)">${escHtml(dag.schedule)}</div>
        </div>
        <span class="feature-tag tag-good" style="font-size:.65rem">✓ ${escHtml(dag.status)}</span>
      </div>
    `).join('') + `</div>`;
}

/* ── Feature table ──────────────────────────────────────── */
function renderFeatureTable() {
  const tbody = document.getElementById('featureTableBody');
  if (!tbody) return;

  tbody.innerHTML = MOCK_DATA.scoreRiesgo.features.map(f => `
    <tr>
      <td>${escHtml(f.name)}</td>
      <td>
        <div style="display:flex;align-items:center;gap:.5rem">
          <div class="feature-imp" style="width:${f.importancia}%"></div>
          <span style="font-size:.75rem;color:var(--text-light)">${f.importancia}%</span>
        </div>
      </td>
      <td style="font-size:.82rem">${escHtml(f.valor)}</td>
      <td><span class="feature-tag tag-${f.estado}">${f.estado === 'good' ? '✓ OK' : f.estado === 'warn' ? '⚠ Revisar' : '✗ Riesgo'}</span></td>
    </tr>
  `).join('');
}

/* ── Provision alerts ────────────────────────────────────── */
function renderProvisionAlerts() {
  const el = document.getElementById('provisionAlerts');
  if (!el) return;

  const alerts = [
    { titulo: 'Provisionar Modelo 111 + 115', desc: 'Reservar €4.730 antes del 18 julio', urgency: 'danger' },
    { titulo: 'Provisionar IS 2025',          desc: 'Reservar €12.400 antes del 22 julio para cubrir el día 25', urgency: 'warning' },
    { titulo: 'Provisionar IVA Q3',           desc: 'Objetivo: €7.240 antes del 10 octubre (2 semanas antes)', urgency: 'info' },
  ];

  el.innerHTML = `<div class="alerts-list">` + alerts.map(a => `
    <div class="alert-item ${a.urgency}" style="padding:.85rem 1rem">
      <div>
        <div class="alert-title" style="font-size:.85rem">${escHtml(a.titulo)}</div>
        <div class="alert-desc" style="font-size:.78rem">${escHtml(a.desc)}</div>
      </div>
    </div>
  `).join('') + `</div>`;
}

/* ══════════════════════════════════════════════════════════
   7. CHATBOT PRIVADO (Capa 2 — autenticado)
   ══════════════════════════════════════════════════════════ */
function renderChatSuggestions() {
  const el = document.getElementById('chatSuggestions');
  if (!el) return;

  const suggestions = [
    '¿Cuánto debo provisionar este mes?',
    '¿Cuál es mi próximo vencimiento?',
    '¿Cómo está mi score de riesgo?',
    '¿Cuánto tengo proyectado a 60 días?',
    '¿Qué declaraciones tengo pendientes?',
  ];

  el.innerHTML = suggestions.map(s => `
    <button class="priv-qr-btn" style="text-align:left;border-radius:8px;padding:.4rem .75rem;font-size:.75rem" data-q="${escHtml(s)}">${escHtml(s)}</button>
  `).join('');

  el.querySelectorAll('[data-q]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById('privChatInput');
      if (input) {
        input.value = btn.dataset.q;
        input.dispatchEvent(new Event('input'));
        document.getElementById('privChatSend')?.click();
      }
    });
  });
}

function initPrivateChatbot() {
  const messagesEl = document.getElementById('privChatMessages');
  const inputEl    = document.getElementById('privChatInput');
  const sendBtn    = document.getElementById('privChatSend');
  const quickR     = document.getElementById('privQuickReplies');
  if (!messagesEl || !inputEl || !sendBtn) return;

  const DISCLAIMER = '<span class="disclaimer-note">ℹ️ Orientativo. Consulta con tu asesor para decisiones formales.</span>';

  const PRIVATE_INTENTS = [
    {
      keywords: ['provisionar', 'provisión', 'cuánto debo', 'reservar', 'apartar', 'fondos'],
      answer() {
        return `Este mes tienes dos vencimientos urgentes:\n\n• **Modelo 111 + 115**: €4.730 (vence 20 jul)\n• **Impuesto Sociedades**: €12.400 (vence 25 jul)\n\n**Total a provisionar: €17.130**\n\nTu caja proyectada actual es €31.450. Después de estos pagos quedarías con ~€14.320, que cubre el IVA Q3 de octubre (€7.240). Recomiendo apartar los €17.130 esta semana.${DISCLAIMER}`;
      },
    },
    {
      keywords: ['próximo vencimiento', 'cuando vence', 'cuándo tengo', 'qué debo presentar', 'siguiente'],
      answer() {
        return `Tu **próximo vencimiento** es en **6 días**:\n\n• **Modelo 111** (IRPF Retenciones Q2) — 20 julio 2026 — €3.840\n• **Modelo 115** (Retención alquiler Q2) — 20 julio 2026 — €890\n• **Modelo 130** (Fraccionado IRPF) — 20 julio 2026 — €1.200\n\nTotal el 20 de julio: **€5.930**\n\nA continuación: Impuesto Sociedades 2025 el 25 de julio (€12.400).${DISCLAIMER}`;
      },
    },
    {
      keywords: ['score', 'riesgo', 'situación fiscal', 'cómo estoy', 'peligro', 'multa'],
      answer() {
        return `Tu **score de riesgo fiscal actual** es **42/100** 🟡 (riesgo moderado).\n\nLos factores que más influyen:\n\n• ⚠️ Facturas de fallecidos: 1 detectada (riesgo crítico)\n• ✅ Identidades válidas: 100% en el padrón RENIEC (bueno)\n• ⚠️ Desviación de ubigeo: 15% de compras (a vigilar)\n• ✅ Suplantación de representante: No detectada (bueno)\n\nTe sugerimos usar el **Verificador KYC** antes de trabajar con nuevos proveedores.`;
      },
    },
    {
      keywords: ['flujo de caja', 'cuánto tengo', 'proyección', '30 días', '60 días', '90 días', 'saldo'],
      answer() {
        return `Tu **proyección de flujo de caja** según el modelo Prophet:\n\n• Hoy: **€31.450** (saldo actual)\n• En 30 días: **€24.800** (tras vencimientos julio)\n• En 60 días: **€18.200** (agosto tranquilo)\n• En 90 días: **€9.100** ⚠️ (antes de IVA Q3)\n\n**Acción recomendada**: antes del 10 de octubre, asegúrate de tener €7.240 reservados para el IVA Q3.${DISCLAIMER}`;
      },
    },
    {
      keywords: ['declaraciones', 'pendientes', 'presentadas', 'cumplimiento', 'historial'],
      answer() {
        return `Tu **estado de declaraciones 2026**:\n\n✅ Presentadas a tiempo: 7/9\n⏳ Pendiente: **Modelo 111 Q2** (vence 20 julio)\n⚠️ Con retraso histórico: 1 (Modelo 303 Q1, sin sanción)\n\n**Ratio de cumplimiento: 89%** — objetivo mínimo recomendado: 95%.\n\nTu asesora Laura García está preparando el Modelo 111 para presentación antes del 18 de julio.${DISCLAIMER}`;
      },
    },
    {
      keywords: ['asesor', 'laura', 'hablar', 'contactar', 'llamar', 'reunión'],
      answer: () => `Tu asesora asignada es **Laura García** — Especialista Fiscal Senior.\n\nPuedes contactarla:\n• **Email**: laura.garcia@nexumasesores.es\n• **WhatsApp**: +34 612 345 678\n• **Horario**: L-J 9-18h, V 9-15h\n\n[Escribir por WhatsApp](https://wa.me/34612345678)`,
    },
  ];

  const FALLBACK_PRIVATE = `No tengo esa información en tus datos actuales, o la consulta requiere análisis más detallado.\n\nPuedo conectarte directamente con **Laura García**, tu asesora asignada, para que te responda hoy.${DISCLAIMER}`;

  let msgCount = 0;

  function addPrivMsg(text, role = 'bot') {
    const div = document.createElement('div');
    div.className = `priv-msg ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'priv-bubble';
    bubble.innerHTML = simpleMarkdown(text);
    div.appendChild(bubble);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    msgCount++;
    return div;
  }

  function simpleMarkdown(text) {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" style="color:var(--gold-dark)">$1</a>')
      .replace(/\n\n/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }

  function showPrivTyping() {
    const div = document.createElement('div');
    div.className = 'priv-msg bot';
    div.id = 'priv-typing';
    div.innerHTML = `<div class="priv-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function findPrivAnswer(query) {
    const q = query.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    let best = null, bestScore = 0;
    PRIVATE_INTENTS.forEach(intent => {
      const score = intent.keywords.reduce((acc, kw) => {
        const n = kw.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        return acc + (q.includes(n) ? 1 : 0);
      }, 0);
      if (score > bestScore) { best = intent; bestScore = score; }
    });
    return bestScore > 0 ? best : null;
  }

  function setPrivQuickReplies(replies) {
    quickR.innerHTML = '';
    replies.forEach(r => {
      const btn = document.createElement('button');
      btn.className = 'priv-qr-btn';
      btn.textContent = r;
      btn.addEventListener('click', () => {
        inputEl.value = r;
        sendBtn.disabled = false;
        handlePrivSend();
      });
      quickR.appendChild(btn);
    });
  }

  async function handlePrivSend() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    quickR.innerHTML = '';

    addPrivMsg(text, 'user');
    const typing = showPrivTyping();
    await new Promise(r => setTimeout(r, 700 + Math.random() * 500));
    typing.remove();

    const match = findPrivAnswer(text);
    if (match) {
      addPrivMsg(typeof match.answer === 'function' ? match.answer() : match.answer, 'bot');
      setPrivQuickReplies(['¿Y el riesgo fiscal?', '¿Qué declaraciones tengo pendientes?', 'Hablar con mi asesor']);
    } else {
      addPrivMsg(FALLBACK_PRIVATE, 'bot');
      // Mostrar opciones de escalamiento
      const escDiv = document.createElement('div');
      escDiv.innerHTML = `
        <div class="priv-msg bot">
          <div class="priv-bubble" style="background:transparent;padding:0">
            <div style="display:flex;gap:.5rem;flex-wrap:wrap">
              <a href="https://wa.me/34612345678" target="_blank" rel="noopener"
                 style="flex:1;display:flex;align-items:center;justify-content:center;gap:.4rem;background:#25D366;color:#fff;padding:.55rem .85rem;border-radius:8px;font-size:.8rem;font-weight:700;text-decoration:none">
                📱 WhatsApp
              </a>
              <a href="index.html#contacto"
                 style="flex:1;display:flex;align-items:center;justify-content:center;gap:.4rem;background:var(--navy);color:#fff;padding:.55rem .85rem;border-radius:8px;font-size:.8rem;font-weight:700;text-decoration:none">
                ✉️ Formulario
              </a>
            </div>
          </div>
        </div>`;
      messagesEl.appendChild(escDiv.firstElementChild);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  // Mensaje de bienvenida
  setTimeout(() => {
    addPrivMsg(`¡Hola! Soy tu asistente fiscal privado. Tengo acceso a los datos de **${MOCK_DATA.cliente.nombre}** en tiempo real.\n\n¿En qué te puedo ayudar hoy?`, 'bot');
    setPrivQuickReplies(['¿Cuánto debo provisionar?', '¿Cuál es mi próximo vencimiento?', '¿Cómo está mi riesgo fiscal?', '¿Cuánto tengo proyectado a 60 días?']);
  }, 400);

  inputEl.addEventListener('input', () => { sendBtn.disabled = !inputEl.value.trim(); });
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !sendBtn.disabled) {
      e.preventDefault();
      handlePrivSend();
    }
  });
  sendBtn.addEventListener('click', handlePrivSend);
}

/* ══════════════════════════════════════════════════════════
   UTILS
   ══════════════════════════════════════════════════════════ */
function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function initKycShield() {
  const verifyBtn = document.getElementById('kycVerifyBtn');
  const inputEl   = document.getElementById('kycDniInput');
  const resultEl  = document.getElementById('kycResultPanel');
  if (!verifyBtn || !inputEl || !resultEl) return;

  verifyBtn.addEventListener('click', async () => {
    const dni = inputEl.value.trim();
    if (!dni) return;

    verifyBtn.disabled = true;
    verifyBtn.textContent = 'Verificando con RENIEC...';
    resultEl.style.display = 'none';

    // Latencia simulada de API
    await new Promise(r => setTimeout(r, 1000));

    // Base de datos de padrón simulada (RENIEC)
    const mockDb = {
      "12345678": {
        nombre: "JUAN CARLOS PEREZ RAMIREZ",
        estado: "Vivo",
        ubigeo: "Lima (Coherente)",
        edad: 42,
        riesgo: "Bajo",
        color: "var(--success)",
        badge: "tag-good",
        motivo: "Identidad validada al 100% en el padrón electoral."
      },
      "87654321": {
        nombre: "MARIA ELENA GONZALES CASTRO",
        estado: "🚨 FALLECIDO",
        ubigeo: "Arequipa (Inconsistente)",
        edad: 84,
        riesgo: "🚨 ALTO",
        color: "var(--error)",
        badge: "tag-failed",
        motivo: "El titular se encuentra registrado como fallecido en RENIEC. Riesgo crítico de suplantación de identidad en facturas."
      },
      "11112222": {
        nombre: "ANDRES AVELINO RODRIGUEZ CACERES",
        estado: "Vivo",
        ubigeo: "Ayacucho (Inconsistente)",
        edad: 21,
        riesgo: "Moderado",
        color: "var(--gold-dark)",
        badge: "tag-warn",
        motivo: "El titular tiene domicilio fiscal reportado en Madrid, pero en RENIEC declara ubigeo en Ayacucho. Firma digital bajo revisión."
      }
    };

    const data = mockDb[dni];

    if (!data) {
      resultEl.innerHTML = `
        <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem">
          <span class="feature-tag tag-failed" style="font-size:.75rem">✗ NO ENCONTRADO</span>
          <strong style="color:var(--navy);font-size:.9rem">DNI: ${escHtml(dni)}</strong>
        </div>
        <p style="font-size:.85rem;color:var(--text-mid)">
          El DNI consultado no se encuentra registrado en el padrón electoral de la RENIEC. **Riesgo crítico de identidad sintética (factura falsa).**
        </p>
      `;
    } else {
      resultEl.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.75rem;border-bottom:1px solid rgba(10,22,40,.06);padding-bottom:.5rem">
          <div style="display:flex;align-items:center;gap:.5rem">
            <span class="feature-tag ${data.badge}" style="font-size:.75rem">${data.riesgo === 'Bajo' ? '✓ OK' : data.riesgo === 'Moderado' ? '⚠ Revisar' : '✗ Alerta'}</span>
            <strong style="color:var(--navy);font-size:.9rem">${escHtml(data.nombre)}</strong>
          </div>
          <span style="font-size:.78rem;color:var(--text-light)">Edad: ${data.edad} años | DNI: ${escHtml(dni)}</span>
        </div>
        <p style="font-size:.85rem;color:var(--text-mid);line-height:1.5">
          <strong>Estado RENIEC:</strong> ${data.estado} <br>
          <strong>Ubigeo declarado:</strong> ${escHtml(data.ubigeo)} <br>
          <strong>Resultado predictivo:</strong> Riesgo <span style="color:${data.color};font-weight:700">${data.riesgo}</span> <br><br>
          <strong>Detalles de auditoría:</strong> ${data.motivo}
        </p>
      `;
    }

    resultEl.style.display = 'block';
    verifyBtn.disabled = false;
    verifyBtn.textContent = 'Consultar RENIEC';
  });
}

/* ══════════════════════════════════════════════════════════
   INIT
   ══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  initLogin();
});
