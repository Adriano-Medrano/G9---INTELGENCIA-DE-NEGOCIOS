/* ============================================================
   NEXUM ASESORES — main.js
   Interactividad sitio principal + Chatbot FAQ público
   ============================================================ */

'use strict';

/* ── Utilidades ─────────────────────────────────────────── */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ── Navbar: scroll + highlight activo ─────────────────── */
(function initNavbar() {
  const navbar = $('#navbar');
  if (!navbar) return;

  const sections = $$('section[id], main[id]');
  const navLinks = $$('.nav-links a');

  const onScroll = () => {
    // Scrolled state
    navbar.classList.toggle('scrolled', window.scrollY > 60);

    // Back-to-top visibility
    const backTop = $('#back-top');
    if (backTop) backTop.classList.toggle('visible', window.scrollY > 500);

    // Active nav link
    let current = '';
    sections.forEach(sec => {
      if (window.scrollY >= sec.offsetTop - 120) current = sec.id;
    });
    navLinks.forEach(a => {
      a.classList.toggle('active', a.getAttribute('href') === `#${current}`);
    });
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

/* ── Mobile nav ─────────────────────────────────────────── */
(function initMobileNav() {
  const toggle   = $('#navToggle');
  const mobileNav = $('#mobileNav');
  const closeBtn  = $('#mobileNavClose');
  if (!toggle || !mobileNav) return;

  const openNav = () => {
    toggle.classList.add('open');
    mobileNav.classList.add('open');
    toggle.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    closeBtn?.focus();
  };
  const closeNav = () => {
    toggle.classList.remove('open');
    mobileNav.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    toggle.focus();
  };

  toggle.addEventListener('click', () =>
    mobileNav.classList.contains('open') ? closeNav() : openNav()
  );
  closeBtn?.addEventListener('click', closeNav);

  // Cerrar al hacer clic en un enlace
  $$('.mobile-nav-links a', mobileNav).forEach(a =>
    a.addEventListener('click', closeNav)
  );

  // Cerrar con Escape
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && mobileNav.classList.contains('open')) closeNav();
  });

  // Cerrar si clic fuera
  mobileNav.addEventListener('click', e => {
    if (e.target === mobileNav) closeNav();
  });
})();

/* ── Back to top ────────────────────────────────────────── */
(function initBackTop() {
  const btn = $('#back-top');
  if (!btn) return;
  btn.addEventListener('click', () =>
    window.scrollTo({ top: 0, behavior: 'smooth' })
  );
})();

/* ── Reveal on scroll (IntersectionObserver) ────────────── */
(function initReveal() {
  const elements = $$('.reveal');
  if (!elements.length) return;

  const observer = new IntersectionObserver(
    entries => entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        observer.unobserve(e.target);
      }
    }),
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  );
  elements.forEach(el => observer.observe(el));
})();

/* ── Tabs de segmentos ──────────────────────────────────── */
(function initTabs() {
  const tabBtns = $$('.tab-btn');
  if (!tabBtns.length) return;

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.tab;

      // Actualizar botones
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');

      // Actualizar paneles
      $$('.tab-content').forEach(panel => panel.classList.remove('active'));
      const targetPanel = $(`#tab-${targetId}`);
      if (targetPanel) targetPanel.classList.add('active');
    });

    // Soporte teclado
    btn.addEventListener('keydown', e => {
      const tabs = [...tabBtns];
      const idx  = tabs.indexOf(btn);
      if (e.key === 'ArrowRight') tabs[(idx + 1) % tabs.length].click();
      if (e.key === 'ArrowLeft')  tabs[(idx - 1 + tabs.length) % tabs.length].click();
    });
  });
})();

/* ── FAQ Acordeón ───────────────────────────────────────── */
(function initFAQ() {
  const faqItems = $$('.faq-item');
  if (!faqItems.length) return;

  faqItems.forEach(item => {
    const btn    = $('.faq-question', item);
    const answer = $('.faq-answer', item);
    if (!btn || !answer) return;

    btn.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');

      // Cerrar todos
      faqItems.forEach(i => {
        i.classList.remove('open');
        $('.faq-question', i)?.setAttribute('aria-expanded', 'false');
      });

      // Abrir el actual si estaba cerrado
      if (!isOpen) {
        item.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
        // Scroll suave si está fuera de vista
        setTimeout(() => {
          const rect = item.getBoundingClientRect();
          if (rect.top < 80) {
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }, 350);
      }
    });
  });
})();

/* ── Formulario de contacto con validación (Estilo Squarespace Scheduling) ── */
(function initContactForm() {
  const form = $('#contactForm');
  if (!form) return;

  // Variables de estado del scheduler
  let selectedService = "Consulta Inicial Gratuita (30 min)";
  let selectedDay = "14";
  let selectedTime = "09:30 AM";

  function updateResumen() {
    const resumenEl = $('#resumen-reserva');
    if (resumenEl) {
      resumenEl.textContent = `${selectedService} el ${selectedDay} de Julio 2026 a las ${selectedTime}`;
    }
  }

  // --- PASO 1: Selección de Servicio ---
  const serviceCards = $$('.service-card');
  serviceCards.forEach(card => {
    card.addEventListener('click', () => {
      // Quitar clases activas y desmarcar
      serviceCards.forEach(c => {
        c.classList.remove('active');
        c.style.borderColor = 'rgba(10,22,40,0.12)';
        c.style.background = '#fff';
      });
      // Activar la clickeada
      card.classList.add('active');
      card.style.borderColor = 'var(--gold)';
      card.style.background = 'rgba(201,168,76,.05)';
      
      const radio = $('input[type="radio"]', card);
      if (radio) {
        radio.checked = true;
        selectedService = radio.value;
      }
      updateResumen();
    });
  });

  // --- PASO 2: Selección de Fecha y Hora ---
  const dayElements = $$('.cal-day');
  dayElements.forEach(day => {
    day.addEventListener('click', () => {
      dayElements.forEach(d => {
        d.style.background = 'none';
        d.style.color = 'var(--navy)';
      });
      day.style.background = 'rgba(201,168,76,.15)';
      selectedDay = day.dataset.day;
      updateResumen();
    });
  });

  const timeElements = $$('.time-slot');
  timeElements.forEach(time => {
    time.addEventListener('click', () => {
      timeElements.forEach(t => {
        t.classList.remove('active');
        t.style.border = '1.5px solid rgba(10,22,40,.12)';
        t.style.background = '#fff';
      });
      time.classList.add('active');
      time.style.border = '1.5px solid var(--gold)';
      time.style.background = 'rgba(201,168,76,.08)';
      selectedTime = time.dataset.time + (time.dataset.time.startsWith('09') || time.dataset.time.startsWith('11') ? ' AM' : ' PM');
      updateResumen();
    });
  });

  // --- NAVEGACIÓN ENTRE PASOS ---
  const step1 = $('#s-step-1');
  const step2 = $('#s-step-2');
  const step3 = $('#s-step-3');

  const panel1 = $('#panel-1');
  const panel2 = $('#panel-2');
  const panel3 = $('#panel-3');

  function setStepActive(stepNum) {
    [step1, step2, step3].forEach((s, idx) => {
      if (idx + 1 === stepNum) {
        s.classList.add('active');
        s.style.fontWeight = '700';
        s.style.color = 'var(--navy)';
        s.style.borderBottom = '2px solid var(--gold)';
      } else {
        s.classList.remove('active');
        s.style.fontWeight = '500';
        s.style.color = 'var(--text-light)';
        s.style.borderBottom = 'none';
      }
    });
  }

  $('#btnNext1')?.addEventListener('click', () => {
    panel1.style.display = 'none';
    panel2.style.display = 'block';
    setStepActive(2);
  });

  $('#btnBack1')?.addEventListener('click', () => {
    panel2.style.display = 'none';
    panel1.style.display = 'block';
    setStepActive(1);
  });

  $('#btnNext2')?.addEventListener('click', () => {
    panel2.style.display = 'none';
    panel3.style.display = 'block';
    setStepActive(3);
    updateResumen();
  });

  $('#btnBack2')?.addEventListener('click', () => {
    panel3.style.display = 'none';
    panel2.style.display = 'block';
    setStepActive(2);
  });

  // --- VALIDACIÓN PASO 3 ---
  const rules = {
    'f-nombre':   { required: true, minLen: 2 },
    'f-empresa':  { required: true, minLen: 2 },
    'f-sector':   { required: true },
    'f-telefono': { required: true, pattern: /^[+\d\s\-()]{7,20}$/ },
  };

  function validateField(id) {
    const field   = $(`#${id}`);
    const group   = field?.closest('.form-group');
    if (!field || !group) return true;

    const val  = field.value.trim();
    const rule = rules[id];
    let valid  = true;

    if (rule.required && !val) valid = false;
    if (valid && rule.minLen && val.length < rule.minLen) valid = false;
    if (valid && rule.pattern && !rule.pattern.test(val)) valid = false;

    field.classList.toggle('error',   !valid);
    field.classList.toggle('success', valid && val.length > 0);
    group.classList.toggle('has-error', !valid);
    return valid;
  }

  Object.keys(rules).forEach(id => {
    const field = $(`#${id}`);
    if (!field) return;
    field.addEventListener('blur', () => validateField(id));
    field.addEventListener('input', () => {
      if (field.classList.contains('error')) validateField(id);
    });
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();

    const allValid = Object.keys(rules)
      .map(id => validateField(id))
      .every(Boolean);

    if (!allValid) {
      const firstErr = form.querySelector('.form-input.error, .form-select.error');
      firstErr?.focus();
      return;
    }

    const submitBtn = $('#btnSubmit');
    const successMsg = $('#formSuccess');

    submitBtn.disabled = true;
    submitBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin" aria-hidden="true" style="width:14px;height:14px;animation:spin .8s linear infinite">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      Reservando...
    `;

    await new Promise(r => setTimeout(r, 1500));

    submitBtn.style.display = 'none';
    $('#btnBack2').style.display = 'none';
    successMsg?.classList.add('visible');
  });
})();

/* ── Animación del número de estadísticas ───────────────── */
(function initCounters() {
  const counters = $$('.stat-num, .hero-stat-num');
  if (!counters.length) return;

  const animateCounter = (el) => {
    const raw    = el.textContent.trim();
    const num    = parseFloat(raw.replace(/[^0-9.]/g, ''));
    const suffix = raw.replace(/[0-9.]/g, '');
    if (isNaN(num)) return;

    const duration = 1800;
    const start    = performance.now();

    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased    = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current  = Math.floor(eased * num);
      el.textContent = current + suffix;
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = raw; // restaurar texto exacto
    };
    requestAnimationFrame(step);
  };

  const observer = new IntersectionObserver(
    entries => entries.forEach(e => {
      if (e.isIntersecting) {
        animateCounter(e.target);
        observer.unobserve(e.target);
      }
    }),
    { threshold: 0.5 }
  );

  counters.forEach(c => observer.observe(c));
})();

/* ── CSS spin para el botón de envío ───────────────────── */
(function addSpinStyle() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes spin { to { transform: rotate(360deg); } }
    .spin { animation: spin .8s linear infinite; }
  `;
  document.head.appendChild(style);
})();

/* ════════════════════════════════════════════════════════
   CHATBOT — Capa pública (FAQ)
   ════════════════════════════════════════════════════════ */
(function initChatbot() {
  /* ── Base de conocimiento FAQ ─────────────────────────── */
  const FAQ_KB = [
    {
      id: 'regimen',
      keywords: ['régimen', 'tributario', 'conviene', 'mejor régimen', 'autónomo', 'sl', 'sociedad', 'tipo empresa', 'cual me conviene', 'estructura'],
      label: '📋 Régimen tributario',
      answer: `El régimen más adecuado depende de tu facturación, tipo de actividad y previsiones de crecimiento. En general:\n\n• **Estimación directa simplificada**: ideal para autónomos con facturación inferior a 600.000 €/año.\n• **Módulos (EOS)**: solo ciertos sectores con actividad predecible.\n• **Sociedad Limitada**: recomendable si facturas más de 60.000 €/año y quieres optimizar el IS vs. IRPF.\n\nHaz una **consulta gratuita** y te analizamos tu caso sin compromiso.`,
      followUp: ['¿Cuánto cuesta?', '¿Qué incluye el plan?', 'Solicitar consulta'],
    },
    {
      id: 'precio',
      keywords: ['precio', 'coste', 'cuánto cuesta', 'tarifa', 'mensual', 'cuota', 'planes', 'plan', 'paquete', 'valor'],
      label: '💰 Precios y planes',
      answer: `Nuestros planes:\n\n• **Consulta Puntual**: tarifa fija por sesión (diagnóstico + informe escrito).\n• **Asesoría Recurrente**: desde **149 €/mes** (autónomos con SL) / desde **249 €/mes** (PYMEs).\n• **Paquete Integral Anual**: incluye planificación estratégica, auditoría preventiva y soporte ilimitado.\n\nLa **primera consulta es gratuita**. ¿Quieres que te contactemos?`,
      followUp: ['¿Qué incluye cada plan?', '¿Puedo cambiar de plan?', 'Solicitar consulta'],
    },
    {
      id: 'deuda',
      keywords: ['atraso', 'deuda', 'hacienda', 'multa', 'sanción', 'requerimiento', 'inspección', 'debo dinero', 'moroso', 'embargo'],
      label: '⚠️ Deudas y sanciones',
      answer: `Si tienes atrasos o deudas con Hacienda, no entres en pánico. Existen vías de regularización:\n\n• **Regularización voluntaria**: reduce sanciones hasta un 50 %.\n• **Aplazamiento o fraccionamiento**: hasta 36 meses sin aval en importes menores.\n• **Recurso o revisión**: si crees que la sanción es injusta, tenemos un plazo legal para recurrir.\n\nCuanto antes actúes, más opciones tienes. **Escríbenos o llámanos hoy.**`,
      followUp: ['¿Cuánto cuesta la asesoría?', 'Solicitar consulta gratuita', '¿Plazos fiscales?'],
    },
    {
      id: 'plazos',
      keywords: ['plazo', 'vencimiento', 'cuándo', 'fechas', 'calendario', 'trimestre', '303', '111', 'modelo', 'fecha limite', 'presentar'],
      label: '📅 Plazos fiscales',
      answer: `Los principales vencimientos fiscales del año en España:\n\n• **Modelo 303 (IVA trimestral)**: 20 ene, 20 abr, 20 jul, 20 oct.\n• **Modelo 111 (retenciones IRPF)**: mismas fechas que el IVA.\n• **Modelo 200 (Impuesto Sociedades)**: 25 días tras los 6 meses del cierre contable.\n• **Modelo 100 (IRPF autónomos)**: 30 de junio del año siguiente.\n\nCon nuestra **asesoría recurrente** recibes alertas personalizadas antes de cada vencimiento.`,
      followUp: ['¿Cuánto cuesta?', '¿Tengo una deuda?', 'Solicitar consulta'],
    },
    {
      id: 'startup',
      keywords: ['startup', 'inversión', 'ronda', 'stock option', 'i+d', 'investigación', 'deducción', 'emprendimiento', 'seed', 'serie a'],
      label: '🚀 Startups e inversión',
      answer: `Para startups tenemos experiencia específica en:\n\n• Estructuración fiscal para **rondas de financiación** (seed, Serie A…)\n• Planes de **stock options** para empleados clave (tributación diferida)\n• Deducciones por **I+D+i**: hasta el 25 % de la inversión en I+D.\n• **Precios de transferencia** en operaciones con filiales internacionales.\n\nContacta con Laura García, nuestra especialista en startups.`,
      followUp: ['¿Cuánto cuesta?', '¿Qué régimen me conviene?', 'Solicitar consulta'],
    },
    {
      id: 'importacion',
      keywords: ['importación', 'aduana', 'iva importación', 'manufactura', 'intracomunitario', 'exportación', 'comercio exterior'],
      label: '🌍 Comercio exterior',
      answer: `En comercio exterior y manufactura gestionamos:\n\n• **IVA de importación**: diferimiento, DUA y liquidación en frontera.\n• **Operaciones intracomunitarias**: Modelo 349, ROI, VIES.\n• **Aranceles**: clasificación arancelaria y optimización de origen.\n• **Exportaciones**: exención de IVA y documentación aduanera.\n\nMiguel Santos, nuestro especialista en comercio exterior, puede atenderte hoy.`,
      followUp: ['¿Cuánto cuesta?', '¿Plazos fiscales?', 'Solicitar consulta'],
    },
    {
      id: 'cambio_plan',
      keywords: ['cambiar', 'escalar', 'plan', 'permanencia', 'cambio de plan', 'flexible', 'cancelar'],
      label: '🔄 Cambio de plan',
      answer: `Sí, puedes cambiar de plan en cualquier momento **sin penalizaciones ni permanencias**. Revisamos tus necesidades cada 6 meses para asegurar que siempre tienes el plan adecuado a tu momento empresarial.`,
      followUp: ['¿Cuáles son los planes?', 'Solicitar consulta', '¿Qué incluye el plan integral?'],
    },
    {
      id: 'ubicacion',
      keywords: ['madrid', 'cobertura', 'online', 'remoto', 'digital', 'presencial', 'ubicación', 'oficina', 'dónde están', 'dirección'],
      label: '📍 Ubicación y cobertura',
      answer: `Estamos en **C/ Serrano, 47 — Madrid**, con atención presencial L-J 9-18h, V 9-15h.\n\nEl **40 % de nuestros clientes** trabajan con nosotros 100 % en remoto (videollamada + plataforma digital). No importa dónde esté tu empresa.`,
      followUp: ['¿Cuánto cuesta?', '¿Qué servicios ofrecen?', 'Solicitar consulta'],
    },
    {
      id: 'kyc_shield',
      keywords: ['kyc', 'tax shield', 'blindaje', 'fraude', 'identidad', 'reniec', 'verificación', 'anti fraude', 'score riesgo'],
      label: '🛡️ KYC Tax Shield',
      answer: `Nuestro sistema **KYC Tax Shield** es una auditoría preventiva que protege tu empresa contra:\n\n• 🔍 **Facturas de identidades falsas** (DNIs inexistentes o fallecidos)\n• 🛡️ **Suplantación de representantes legales**\n• 📊 **Score de riesgo fiscal** con Machine Learning (XGBoost)\n• 📈 **Proyecciones de caja** con modelos Prophet\n\nCruzamos tus datos con la base **RENIEC** para blindarte contra el fraude fiscal.\n\n¿Quieres saber más? Solicita una demo gratuita.`,
      followUp: ['¿Cuánto cuesta?', '¿Cómo funciona la verificación?', 'Solicitar demo'],
    },
    {
      id: 'servicios',
      keywords: ['servicio', 'servicios', 'qué hacen', 'qué ofrecen', 'en qué ayudan', 'actividades', 'portafolio'],
      label: '📌 Nuestros servicios',
      answer: `En **Nexum Asesores** ofrecemos:\n\n• 📋 **Asesoría fiscal recurrente**: declaraciones, contabilidad, planificación.\n• 🛡️ **KYC Tax Shield**: blindaje anti-fraude con datos RENIEC.\n• 📊 **Dashboard predictivo**: flujo de caja, score de riesgo, alertas.\n• 🔍 **Auditoría preventiva**: verificación de identidades y proveedores.\n• 📅 **Alertas de vencimientos**: notificaciones personalizadas.\n• 👩‍💼 **Asesor asignado**: acompañamiento personalizado.\n\n¿Qué tema te interesa más?`,
      followUp: ['¿Cuánto cuesta?', '¿Qué es KYC Tax Shield?', 'Solicitar consulta'],
    },
    {
      id: 'saludo',
      keywords: ['hola', 'buenos días', 'buenas tardes', 'buenas', 'hey', 'saludos', 'buen dia', 'qué tal'],
      answer: `¡Hola! Soy el asistente virtual de **Nexum Asesores**. Puedo ayudarte con:\n\n• 📋 Información sobre nuestros **servicios y precios**\n• 📅 **Plazos** y calendarios fiscales\n• 🛡️ **KYC Tax Shield** (blindaje anti-fraude)\n• ❓ Dudas generales sobre asesoría para PYMEs\n\n¿En qué puedo ayudarte hoy?`,
      isGreeting: true,
      followUp: ['Precios y planes', 'Plazos fiscales', 'Tengo una deuda con Hacienda', '¿Qué es KYC Tax Shield?'],
    },
    {
      id: 'gracias',
      keywords: ['gracias', 'perfecto', 'genial', 'ok', 'entendido', 'vale', 'listo', 'muchas gracias'],
      answer: `¡De nada! 😊 Estoy aquí para ayudarte.\n\n¿Hay algo más que quieras saber sobre nuestros servicios?`,
      followUp: ['¿Cuánto cuesta?', '¿Plazos fiscales?', 'Solicitar consulta gratuita'],
    },
    {
      id: 'ayuda',
      keywords: ['ayuda', 'help', 'qué puedes hacer', 'opciones', 'menú', 'menu'],
      answer: `Puedo ayudarte con estos temas:\n\n• 📋 Régimen tributario ideal\n• 💰 Precios y planes\n• ⚠️ Deudas con Hacienda\n• 📅 Plazos y vencimientos fiscales\n• 🚀 Startups e inversión\n• 🌍 Comercio exterior\n• 🔄 Cambio de plan\n• 📍 Ubicación y cobertura\n• 🛡️ KYC Tax Shield\n• 📌 Servicios generales\n\n💡 Escríbeme con tus propias palabras, te entiendo aunque no sea textual.`,
      followUp: ['Precios', 'Plazos fiscales', 'KYC Tax Shield', 'Solicitar consulta'],
    },
  ];

  const DISCLAIMER = `\n\n_⚠️ Esta información es orientativa. Para decisiones fiscales formales, consulta con tu asesor asignado en Nexum._`;

  /* ── Motor NLP mejorado: fuzzy matching ────────────────── */
  function normalizeText(str) {
    return str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[¿¡?!.,;:]/g, '');
  }

  function tokenizeText(str) {
    return normalizeText(str).split(/\s+/).filter(w => w.length > 1);
  }

  function levenshteinDist(a, b) {
    const m = a.length, n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;
    const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++)
      for (let j = 1; j <= n; j++)
        dp[i][j] = Math.min(
          dp[i - 1][j] + 1,
          dp[i][j - 1] + 1,
          dp[i - 1][j - 1] + (a[i - 1] !== b[j - 1] ? 1 : 0)
        );
    return dp[m][n];
  }

  function fuzzyMatch(queryWord, keyword) {
    if (keyword.includes(queryWord) || queryWord.includes(keyword)) return 1;
    const maxDist = Math.max(1, Math.floor(keyword.length * 0.35));
    return levenshteinDist(queryWord, keyword) <= maxDist ? 0.7 : 0;
  }

  /* ── Motor de búsqueda FAQ ────────────────────────────── */
  function findAnswer(query) {
    const qNorm = normalizeText(query);
    const qTokens = tokenizeText(query);
    let best = null, bestScore = 0;

    FAQ_KB.forEach(entry => {
      let score = 0;

      // 1. Coincidencia exacta de frases (mayor peso)
      entry.keywords.forEach(kw => {
        const kwNorm = normalizeText(kw);
        if (qNorm.includes(kwNorm)) {
          score += 3 * kwNorm.split(/\s+/).length;
        }
      });

      // 2. Fuzzy matching por tokens si no hubo match exacto
      if (score === 0) {
        entry.keywords.forEach(kw => {
          const kwTokens = tokenizeText(kw);
          kwTokens.forEach(kwt => {
            qTokens.forEach(qt => {
              const match = fuzzyMatch(qt, kwt);
              if (match > 0) score += match;
            });
          });
        });
      }

      if (score > bestScore) { best = entry; bestScore = score; }
    });

    return bestScore >= 0.7 ? best : null;
  }

  /* ── Fallback contextual: nunca deja al usuario sin opciones ── */
  function buildFallback(query) {
    const topics = FAQ_KB
      .filter(e => !e.isGreeting && e.id !== 'gracias' && e.id !== 'ayuda' && e.label)
      .map(e => `• ${e.label}`)
      .join('\n');
    return `No encontré una respuesta exacta, pero puedo ayudarte con estos temas:\n\n${topics}\n\n💡 Intenta reformular tu pregunta o elige una opción de arriba.\n\n¿Prefieres hablar directamente con un asesor? Podemos conectarte ahora.`;
  }

  /* ── Handle envío ─────────────────────────────────────── */
  async function handleSend() {
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    sendBtn.disabled = true;
    quickR.innerHTML = '';

    addMessage(text, 'user');

    const typing = showTyping();
    await new Promise(r => setTimeout(r, 700 + Math.random() * 500));
    typing.remove();

    const match = findAnswer(text);

    if (match) {
      const answer = match.isGreeting ? match.answer : match.answer + DISCLAIMER;
      addMessage(answer, 'bot');
      setQuickReplies(match.followUp || ['¿Cuánto cuesta?', '¿Qué incluye el plan?', 'Solicitar consulta']);
    } else {
      // Fallback contextual: muestra todos los temas disponibles
      addMessage(buildFallback(text), 'bot');
      if (!escalated) {
        escalated = true;
        showEscalation();
      }
      setQuickReplies(['Precios y planes', 'Plazos fiscales', 'KYC Tax Shield', '¿Qué servicios ofrecen?', 'Solicitar consulta']);
    }
  }

  function showEscalation() {
    const div = document.createElement('div');
    div.innerHTML = `
      <div class="chat-escalate">
        <p>¿Quieres hablar con un asesor ahora?</p>
        <div class="chat-escalate-btns">
          <a href="https://wa.me/34612345678?text=Hola,%20vengo%20del%20chat%20y%20necesito%20ayuda" target="_blank" rel="noopener" class="chat-escalate-btn wa">📱 WhatsApp</a>
          <a href="#contacto" class="chat-escalate-btn form" id="chatEscForm">✉️ Formulario</a>
        </div>
      </div>`;
    messages.appendChild(div.firstElementChild);
    messages.scrollTop = messages.scrollHeight;

    $('#chatEscForm')?.addEventListener('click', closeChat);
  }

  const chatHTML = `
  <div id="chatbot-widget" aria-label="Asistente virtual de Nexum Asesores" role="complementary">
    <!-- Botón flotante -->
    <button id="chat-fab" class="chat-fab" aria-label="Abrir asistente virtual" aria-expanded="false" aria-controls="chat-window">
      <span class="chat-fab-icon chat-fab-open" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </span>
      <span class="chat-fab-icon chat-fab-close hidden" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </span>
      <span class="chat-fab-badge" id="chatBadge" aria-label="1 mensaje nuevo">1</span>
    </button>

    <!-- Ventana del chat -->
    <div id="chat-window" class="chat-window" aria-hidden="true" role="dialog" aria-modal="false" aria-label="Chat de consultas Nexum">
      <div class="chat-header">
        <div class="chat-header-left">
          <div class="chat-avatar" aria-hidden="true">N</div>
          <div>
            <div class="chat-name">Nexum Asistente</div>
            <div class="chat-status">
              <span class="chat-status-dot" aria-hidden="true"></span>
              En línea
            </div>
          </div>
        </div>
        <div class="chat-header-actions">
          <a href="#contacto" class="chat-human-btn" title="Hablar con un asesor humano" id="chatHumanBtn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
          </a>
          <button class="chat-minimize" id="chatMinimize" aria-label="Minimizar chat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
        </div>
      </div>

      <div class="chat-messages" id="chatMessages" role="log" aria-live="polite" aria-label="Mensajes del chat">
        <!-- mensajes insertados por JS -->
      </div>

      <div class="chat-quick-replies" id="chatQuickReplies" aria-label="Respuestas rápidas"></div>

      <div class="chat-input-area">
        <textarea
          id="chatInput"
          class="chat-input"
          placeholder="Escribe tu consulta..."
          rows="1"
          aria-label="Escribe tu consulta"
          maxlength="500"
        ></textarea>
        <button id="chatSend" class="chat-send" aria-label="Enviar mensaje" disabled>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div class="chat-portal-link">
        <a href="portal.html">¿Ya eres cliente? <strong>Accede a tu portal →</strong></a>
      </div>
    </div>
  </div>`;

  /* ── Estilos del chatbot ─────────────────────────────── */
  const chatStyles = `
  /* ── Chat FAB ──────────────────────────────────────── */
  #chatbot-widget { position: fixed; bottom: 1.75rem; right: 1.75rem; z-index: 10000; }

  .chat-fab {
    width: 58px; height: 58px; border-radius: 50%;
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-light) 100%);
    border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 8px 32px rgba(10,22,40,.35), 0 0 0 0 rgba(201,168,76,.4);
    transition: transform .25s ease, box-shadow .25s ease;
    position: relative;
    animation: fab-pulse 3s ease-in-out infinite;
  }
  @keyframes fab-pulse {
    0%,100% { box-shadow: 0 8px 32px rgba(10,22,40,.35), 0 0 0 0 rgba(201,168,76,.3); }
    50%      { box-shadow: 0 8px 32px rgba(10,22,40,.35), 0 0 0 10px rgba(201,168,76,0); }
  }
  .chat-fab:hover { transform: scale(1.1); animation: none; box-shadow: 0 12px 40px rgba(10,22,40,.4); }
  .chat-fab:active { transform: scale(.97); }
  .chat-fab svg { width: 24px; height: 24px; color: #fff; }
  .chat-fab-icon { display: flex; }
  .chat-fab-icon.hidden { display: none; }

  .chat-fab-badge {
    position: absolute; top: -4px; right: -4px;
    width: 20px; height: 20px; border-radius: 50%;
    background: var(--gold); color: var(--navy);
    font-size: .68rem; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    border: 2px solid #fff;
    transition: opacity .2s;
  }
  .chat-fab-badge.hidden { opacity: 0; pointer-events: none; }

  /* ── Ventana ────────────────────────────────────────── */
  .chat-window {
    position: absolute; bottom: calc(100% + 1rem); right: 0;
    width: 360px; max-height: 560px;
    background: #fff; border-radius: 20px;
    box-shadow: 0 20px 60px rgba(10,22,40,.22);
    display: flex; flex-direction: column; overflow: hidden;
    transform: scale(.92) translateY(12px);
    opacity: 0; pointer-events: none;
    transition: transform .28s cubic-bezier(.34,1.56,.64,1), opacity .22s ease;
    transform-origin: bottom right;
  }
  .chat-window.open {
    transform: scale(1) translateY(0);
    opacity: 1; pointer-events: all;
  }

  /* Header */
  .chat-header {
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-mid) 100%);
    padding: 1rem 1.25rem;
    display: flex; align-items: center; justify-content: space-between;
  }
  .chat-header-left { display: flex; align-items: center; gap: .75rem; }
  .chat-avatar {
    width: 40px; height: 40px; border-radius: 50%;
    background: linear-gradient(135deg, var(--gold-dark), var(--gold-light));
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 1rem; color: var(--navy);
    flex-shrink: 0;
  }
  .chat-name { font-size: .9rem; font-weight: 700; color: #fff; }
  .chat-status { display: flex; align-items: center; gap: .35rem; font-size: .72rem; color: rgba(255,255,255,.7); }
  .chat-status-dot { width: 7px; height: 7px; background: #68D391; border-radius: 50%; }
  .chat-header-actions { display: flex; align-items: center; gap: .5rem; }
  .chat-human-btn, .chat-minimize {
    width: 32px; height: 32px; border-radius: 8px;
    background: rgba(255,255,255,.1); border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: background .2s; text-decoration: none; color: #fff;
  }
  .chat-human-btn:hover, .chat-minimize:hover { background: rgba(255,255,255,.2); }
  .chat-human-btn svg, .chat-minimize svg { width: 15px; height: 15px; color: rgba(255,255,255,.85); }

  /* Messages */
  .chat-messages {
    flex: 1; overflow-y: auto; padding: 1rem;
    display: flex; flex-direction: column; gap: .75rem;
    scroll-behavior: smooth; min-height: 240px; max-height: 320px;
  }
  .chat-messages::-webkit-scrollbar { width: 4px; }
  .chat-messages::-webkit-scrollbar-thumb { background: rgba(10,22,40,.15); border-radius: 99px; }

  .chat-msg { display: flex; gap: .6rem; animation: msg-in .25s ease; }
  @keyframes msg-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
  .chat-msg.user { flex-direction: row-reverse; }

  .chat-bubble {
    max-width: 82%; padding: .65rem .9rem;
    border-radius: 14px; font-size: .84rem; line-height: 1.55;
  }
  .chat-msg.bot .chat-bubble {
    background: #F3F4F6; color: #1A1A2E;
    border-bottom-left-radius: 4px;
  }
  .chat-msg.user .chat-bubble {
    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-mid) 100%);
    color: #fff; border-bottom-right-radius: 4px;
  }
  .chat-bubble strong { font-weight: 700; }
  .chat-bubble em { font-style: italic; font-size: .78rem; color: rgba(10,22,40,.55); display: block; margin-top: .4rem; }
  .chat-bubble ul { margin: .4rem 0 0 1rem; }
  .chat-bubble li { margin-bottom: .2rem; }

  /* Typing indicator */
  .chat-typing { display: flex; gap: 4px; align-items: center; padding: .55rem .8rem; }
  .chat-typing span {
    width: 7px; height: 7px; background: #9CA3AF; border-radius: 50%;
    animation: typing-dot 1.2s infinite;
  }
  .chat-typing span:nth-child(2) { animation-delay: .2s; }
  .chat-typing span:nth-child(3) { animation-delay: .4s; }
  @keyframes typing-dot { 0%,80%,100% { transform: none; opacity: .5; } 40% { transform: translateY(-5px); opacity: 1; } }

  /* Quick replies */
  .chat-quick-replies {
    padding: 0 .85rem .6rem;
    display: flex; flex-wrap: wrap; gap: .4rem;
  }
  .quick-reply-btn {
    padding: .38rem .8rem; border-radius: 99px;
    border: 1.5px solid rgba(10,22,40,.15); background: #fff;
    font-size: .77rem; font-weight: 600; color: var(--navy);
    cursor: pointer; transition: all .18s ease; white-space: nowrap;
  }
  .quick-reply-btn:hover { background: var(--navy); color: #fff; border-color: var(--navy); }

  /* Input area */
  .chat-input-area {
    display: flex; align-items: flex-end; gap: .5rem;
    padding: .75rem 1rem; border-top: 1px solid #F3F4F6;
  }
  .chat-input {
    flex: 1; padding: .55rem .85rem; border-radius: 12px;
    border: 1.5px solid #E5E7EB; background: #F9FAFB;
    font-family: 'Inter', sans-serif; font-size: .85rem; color: #1A1A2E;
    resize: none; outline: none; line-height: 1.4; max-height: 100px; overflow-y: auto;
    transition: border-color .2s;
  }
  .chat-input:focus { border-color: var(--navy); background: #fff; }
  .chat-send {
    width: 38px; height: 38px; border-radius: 50%;
    background: var(--navy); border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; transition: background .2s, transform .15s;
  }
  .chat-send:hover:not(:disabled) { background: var(--navy-light); transform: scale(1.05); }
  .chat-send:disabled { background: #D1D5DB; cursor: not-allowed; }
  .chat-send svg { width: 15px; height: 15px; color: #fff; }

  .chat-portal-link {
    text-align: center; padding: .5rem 1rem .75rem;
    border-top: 1px solid #F3F4F6;
  }
  .chat-portal-link a { font-size: .78rem; color: var(--text-light); text-decoration: none; }
  .chat-portal-link a:hover { color: var(--navy); }
  .chat-portal-link strong { color: var(--navy); }

  /* Escalamiento a humano */
  .chat-escalate {
    background: linear-gradient(135deg, #25D366, #128C7E);
    border-radius: 10px; padding: .75rem 1rem; margin-top: .5rem;
  }
  .chat-escalate p { font-size: .82rem; color: #fff; margin-bottom: .5rem; font-weight: 600; }
  .chat-escalate-btns { display: flex; gap: .5rem; }
  .chat-escalate-btn {
    flex: 1; padding: .4rem .7rem; border-radius: 8px; border: none; cursor: pointer;
    font-size: .78rem; font-weight: 700; transition: opacity .2s;
  }
  .chat-escalate-btn:hover { opacity: .85; }
  .chat-escalate-btn.wa { background: rgba(255,255,255,.2); color: #fff; }
  .chat-escalate-btn.form { background: #fff; color: #128C7E; }

  @media (max-width: 430px) {
    .chat-window { width: calc(100vw - 2rem); right: -0.5rem; }
    #chatbot-widget { right: 1rem; bottom: 1rem; }
  }`;

  /* ── Insertar en DOM ─────────────────────────────────── */
  const styleEl = document.createElement('style');
  styleEl.textContent = chatStyles;
  document.head.appendChild(styleEl);

  document.body.insertAdjacentHTML('beforeend', chatHTML);

  /* ── Referencias ─────────────────────────────────────── */
  const fab       = $('#chat-fab');
  const window_   = $('#chat-window');
  const messages  = $('#chatMessages');
  const input     = $('#chatInput');
  const sendBtn   = $('#chatSend');
  const badge     = $('#chatBadge');
  const quickR    = $('#chatQuickReplies');
  const minimize  = $('#chatMinimize');

  let isOpen     = false;
  let msgCount   = 0;
  let escalated  = false;

  /* ── Helpers de mensajes ──────────────────────────────── */
  function addMessage(text, role = 'bot') {
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.innerHTML = markdownToHTML(text);
    div.appendChild(bubble);

    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    msgCount++;
    return div;
  }

  function markdownToHTML(text) {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/_(.*?)_/g, '<em>$1</em>')
      .replace(/• (.*?)(?=\n|$)/g, '<li>$1</li>')
      .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
      .replace(/\n\n/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }

  function showTyping() {
    const div = document.createElement('div');
    div.className = 'chat-msg bot';
    div.id = 'typing-indicator';
    div.innerHTML = `<div class="chat-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function setQuickReplies(replies) {
    quickR.innerHTML = '';
    replies.forEach(r => {
      const btn = document.createElement('button');
      btn.className = 'quick-reply-btn';
      btn.textContent = r;
      btn.addEventListener('click', () => {
        input.value = r;
        handleSend();
      });
      quickR.appendChild(btn);
    });
  }



  /* ── Abrir / Cerrar ───────────────────────────────────── */
  function openChat() {
    isOpen = true;
    window_.classList.add('open');
    window_.setAttribute('aria-hidden', 'false');
    fab.setAttribute('aria-expanded', 'true');
    $('.chat-fab-open', fab).classList.add('hidden');
    $('.chat-fab-close', fab).classList.remove('hidden');
    badge?.classList.add('hidden');
    fab.style.animation = 'none';
    input.focus();

    if (msgCount === 0) {
      setTimeout(() => {
        addMessage('¡Hola! Soy el asistente virtual de **Nexum Asesores**. Puedo ayudarte con:\n\n• 📋 Servicios y precios\n• 📅 Plazos fiscales\n• 🛡️ KYC Tax Shield (blindaje anti-fraude)\n• ❓ Dudas sobre asesoría para PYMEs\n\n¿En qué puedo ayudarte?', 'bot');
        setQuickReplies(['Precios y planes', 'Plazos fiscales', 'KYC Tax Shield', 'Tengo una deuda con Hacienda']);
      }, 300);
    }
  }

  function closeChat() {
    isOpen = false;
    window_.classList.remove('open');
    window_.setAttribute('aria-hidden', 'true');
    fab.setAttribute('aria-expanded', 'false');
    $('.chat-fab-open', fab).classList.remove('hidden');
    $('.chat-fab-close', fab).classList.add('hidden');
  }

  fab.addEventListener('click', () => isOpen ? closeChat() : openChat());
  minimize?.addEventListener('click', closeChat);

  /* ── Input handlers ───────────────────────────────────── */
  input.addEventListener('input', () => {
    sendBtn.disabled = !input.value.trim();
    // Auto-resize
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) handleSend();
    }
  });

  sendBtn.addEventListener('click', handleSend);

  // Mostrar badge después de 4s para captar atención
  setTimeout(() => {
    if (!isOpen) badge?.classList.remove('hidden');
  }, 4000);
})();
