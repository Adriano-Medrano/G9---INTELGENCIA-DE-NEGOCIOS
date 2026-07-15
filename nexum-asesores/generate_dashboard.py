import os
import json
import logging
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dashboard_generator")

def main():
    root_dir = Path(__file__).parent
    raw_dir = root_dir / "raw"
    
    # 1. Definir nombres de archivos y rutas
    certificados_path = raw_dir / "Cantidad de Certificados de Inscripción.csv"
    centros_path = raw_dir / "Centros de atención del RENIEC a nivel nacional.csv"
    actas_path = raw_dir / "OTI_CONSOLIDADO.csv"
    transacciones_path = raw_dir / "Transacciones RENIEC.csv"

    # Verificar existencia de archivos
    for p in [certificados_path, centros_path, actas_path, transacciones_path]:
        if not p.exists():
            log.error(f"No se encontró el archivo: {p.name} en la carpeta 'raw/'")
            return

    log.info("Cargando y procesando datasets...")

    # Cargar datos con codificación robusta y delimitadores correctos
    try:
        df_cert = pd.read_csv(certificados_path, sep=",", encoding="utf-8-sig")
        df_cent = pd.read_csv(centros_path, sep=",", encoding="utf-8-sig")
        df_actas = pd.read_csv(actas_path, sep=";", encoding="utf-8-sig")
        df_tx = pd.read_csv(transacciones_path, sep=";", encoding="utf-8-sig")
    except Exception as e:
        log.error(f"Error al leer los archivos CSV: {e}")
        return

    # Normalizar nombres de columnas (mayúsculas, sin espacios, quitar acentos y Ñs)
    for df in [df_cert, df_cent, df_actas, df_tx]:
        cols = []
        for c in df.columns:
            c_norm = c.strip().upper().replace(" ", "_")
            c_norm = c_norm.replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U")
            # Unificar variaciones del año a ANIO
            if c_norm in ("ANO", "AÑO", "ANIO_REGISTRO"):
                c_norm = "ANIO"
            # Unificar variaciones de la Ñ
            c_norm = c_norm.replace("Ñ", "N")
            cols.append(c_norm)
        df.columns = cols

    # --- 1. AGREGACIÓN DE KPIS ---
    # Transacciones Totales
    total_tx = int(df_tx["TRANSACCIONES"].dropna().sum()) if "TRANSACCIONES" in df_tx.columns else 0
    
    # Certificados C4 Totales
    total_cert = int(df_cert["TOTAL_EMITIDOS"].dropna().sum()) if "TOTAL_EMITIDOS" in df_cert.columns else 0

    # Copias de Actas OTI Totales
    total_actas = int(df_actas["CANT_COPIAS_EMITIDAS"].dropna().sum()) if "CANT_COPIAS_EMITIDAS" in df_actas.columns else 0

    # Centros de atención
    total_centros = len(df_cent)
    estado_col = "ESTADO" if "ESTADO" in df_cent.columns else ""
    if estado_col:
        df_cent[estado_col] = df_cent[estado_col].astype(str).str.strip().str.upper()
        centros_activos = len(df_cent[df_cent[estado_col].str.contains("OPERATIVO|ACTIVO|PARCIAL", na=False)])
        pct_operativo = round((centros_activos / total_centros) * 100, 1) if total_centros > 0 else 0
    else:
        pct_operativo = 100.0

    # --- 2. GRÁFICO: TENDENCIA DE TRANSACCIONES POR MES/ANIO ---
    # Mapeo de meses en español
    meses_orden = {"ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12,
                   "ENERO ":1,"FEBRERO ":2,"MARZO ":3,"ABRIL ":4,"MAYO ":5,"JUNIO ":6,"JULIO ":7,"AGOSTO ":8,"SEPTIEMBRE ":9,"OCTUBRE ":10,"NOVIEMBRE ":11,"DICIEMBRE ":12}
    
    df_tx["MES_NORMAL"] = df_tx["MES"].astype(str).str.strip().str.upper()
    df_tx["MES_NUM"] = df_tx["MES_NORMAL"].map(meses_orden).fillna(1)
    df_tx_grouped = df_tx.groupby(["ANIO", "MES_NUM", "MES_NORMAL"])["TRANSACCIONES"].sum().reset_index()
    df_tx_grouped = df_tx_grouped.sort_values(["ANIO", "MES_NUM"])
    
    tx_trend_labels = [f"{row['MES_NORMAL']} {int(row['ANIO'])}" for _, row in df_tx_grouped.iterrows()]
    tx_trend_values = [int(v) for v in df_tx_grouped["TRANSACCIONES"]]

    # --- 3. GRÁFICO: TOP DEPARTAMENTOS POR TRANSACCIONES ---
    df_dept_tx = df_tx.groupby("DEPARTAMENTO")["TRANSACCIONES"].sum().reset_index()
    df_dept_tx = df_dept_tx.sort_values("TRANSACCIONES", ascending=False).head(10)
    dept_labels = [str(x) for x in df_dept_tx["DEPARTAMENTO"]]
    dept_values = [int(y) for y in df_dept_tx["TRANSACCIONES"]]

    # --- 4. GRÁFICO: CERTIFICADOS POR GÉNERO ---
    df_gen_cert = df_cert.groupby("SEXO")["TOTAL_EMITIDOS"].sum().reset_index()
    gender_labels = [str(g) for g in df_gen_cert["SEXO"]]
    gender_values = [int(v) for v in df_gen_cert["TOTAL_EMITIDOS"]]

    # --- 5. GRÁFICO: ESTADO DE LOCALES ---
    df_est_cent = df_cent.groupby("ESTADO").size().reset_index(name="CANTIDAD")
    df_est_cent = df_est_cent.sort_values("CANTIDAD", ascending=False)
    estado_labels = [str(e) for e in df_est_cent["ESTADO"]]
    estado_values = [int(c) for c in df_est_cent["CANTIDAD"]]

    # --- 6. GRÁFICO: CERTIFICADOS POR RANGO DE EDAD ---
    df_edad_cert = df_cert.groupby("RANGO_DE_EDADES")["TOTAL_EMITIDOS"].sum().reset_index()
    edad_labels = [str(r) for r in df_edad_cert["RANGO_DE_EDADES"]]
    edad_values = [int(v) for v in df_edad_cert["TOTAL_EMITIDOS"]]

    # Empaquetar todo en un objeto JSON
    data = {
        "kpis": {
            "total_tx": total_tx,
            "total_cert": total_cert,
            "total_actas": total_actas,
            "total_centros": total_centros,
            "pct_operativo": pct_operativo
        },
        "tx_trend": {
            "labels": tx_trend_labels,
            "values": tx_trend_values
        },
        "dept_tx": {
            "labels": dept_labels,
            "values": dept_values
        },
        "gender_cert": {
            "labels": gender_labels,
            "values": gender_values
        },
        "estado_centros": {
            "labels": estado_labels,
            "values": estado_values
        },
        "edad_cert": {
            "labels": edad_labels,
            "values": edad_values
        }
    }

    # Leer plantilla HTML
    html_template = """<!DOCTYPE html>
<html lang="es" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RENIEC - Dashboard Analítico de Big Data</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Google Fonts (Inter / Outfit) -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            font-family: 'Outfit', sans-serif;
            background: radial-gradient(circle at top right, rgba(99, 102, 241, 0.15), transparent 40%),
                        radial-gradient(circle at bottom left, rgba(236, 72, 153, 0.1), transparent 45%),
                        #020617;
        }
        .glass-card {
            background: rgba(30, 41, 59, 0.45);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        }
        .neon-glow-primary {
            text-shadow: 0 0 10px rgba(56, 189, 248, 0.4);
        }
    </style>
</head>
<body class="min-h-screen pb-12">
    <!-- Header -->
    <header class="max-w-7xl mx-auto px-6 pt-8 pb-4 flex flex-col md:flex-row md:items-center md:justify-between border-b border-slate-800">
        <div>
            <div class="flex items-center gap-2">
                <span class="px-2.5 py-1 text-xs font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-full">Pipeline Activo</span>
                <span class="text-xs text-slate-400">Última actualización: Hoy</span>
            </div>
            <h1 class="text-3xl font-bold tracking-tight text-white mt-2">RENIEC <span class="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-indigo-400 to-pink-500">Big Data Dashboard</span></h1>
            <p class="text-sm text-slate-400 mt-1">Monitoreo de transacciones, certificados C4, actas de estado civil y estado operativo de locales a nivel nacional.</p>
        </div>
        <div class="mt-4 md:mt-0 flex gap-3">
            <button onclick="window.location.reload();" class="px-4 py-2 text-sm bg-slate-800 hover:bg-slate-700 transition rounded-lg border border-slate-700 font-medium">
                Actualizar Vista
            </button>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 mt-8">
        <!-- KPI Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <!-- KPI 1 -->
            <div class="glass-card rounded-2xl p-6 relative overflow-hidden group hover:scale-[1.02] transition-transform duration-300">
                <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-sky-500/10 rounded-full blur-2xl group-hover:bg-sky-500/20 transition-all"></div>
                <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Transacciones</h3>
                <p class="text-3xl font-bold text-white mt-3 tracking-tight neon-glow-primary" id="kpi-tx">0</p>
                <div class="text-xs text-sky-400 mt-2 font-medium flex items-center gap-1">
                    <span>⚡ Servicios Procesados</span>
                </div>
            </div>
            <!-- KPI 2 -->
            <div class="glass-card rounded-2xl p-6 relative overflow-hidden group hover:scale-[1.02] transition-transform duration-300">
                <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-2xl group-hover:bg-indigo-500/20 transition-all"></div>
                <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Certificados Emitidos</h3>
                <p class="text-3xl font-bold text-white mt-3 tracking-tight" id="kpi-cert">0</p>
                <div class="text-xs text-indigo-400 mt-2 font-medium">
                    <span>🪪 Certificados de Inscripción C4</span>
                </div>
            </div>
            <!-- KPI 3 -->
            <div class="glass-card rounded-2xl p-6 relative overflow-hidden group hover:scale-[1.02] transition-transform duration-300">
                <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-pink-500/10 rounded-full blur-2xl group-hover:bg-pink-500/20 transition-all"></div>
                <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Copias de Actas OTI</h3>
                <p class="text-3xl font-bold text-white mt-3 tracking-tight" id="kpi-actas">0</p>
                <div class="text-xs text-pink-400 mt-2 font-medium">
                    <span>📜 Copias Registrales Emitidas</span>
                </div>
            </div>
            <!-- KPI 4 -->
            <div class="glass-card rounded-2xl p-6 relative overflow-hidden group hover:scale-[1.02] transition-transform duration-300">
                <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-emerald-500/10 rounded-full blur-2xl group-hover:bg-emerald-500/20 transition-all"></div>
                <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Operatividad Locales</h3>
                <p class="text-3xl font-bold text-white mt-3 tracking-tight" id="kpi-centros">0%</p>
                <div class="text-xs text-emerald-400 mt-2 font-medium" id="kpi-centros-desc">
                    <span>🏢 Locales Operativos</span>
                </div>
            </div>
        </div>

        <!-- Charts Grid 1 -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
            <!-- Line Chart: Tendencia Mensual -->
            <div class="glass-card rounded-2xl p-6 lg:col-span-2">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-base font-bold text-white">Evolución Temporal de Transacciones</h3>
                    <span class="text-xs text-slate-400">Total histórico</span>
                </div>
                <div class="relative h-[300px] w-full">
                    <canvas id="chart-trend"></canvas>
                </div>
            </div>

            <!-- Doughnut Chart: Género de Certificados -->
            <div class="glass-card rounded-2xl p-6">
                <h3 class="text-base font-bold text-white mb-4">Certificados por Género</h3>
                <div class="relative h-[280px] w-full flex items-center justify-center">
                    <canvas id="chart-gender"></canvas>
                </div>
            </div>
        </div>

        <!-- Charts Grid 2 -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
            <!-- Horizontal Bar: Top Departamentos -->
            <div class="glass-card rounded-2xl p-6 lg:col-span-2">
                <h3 class="text-base font-bold text-white mb-4">Top 10 Departamentos con Mayor Carga (Transacciones)</h3>
                <div class="relative h-[300px] w-full">
                    <canvas id="chart-dept"></canvas>
                </div>
            </div>

            <!-- Pie Chart: Estado de Locales -->
            <div class="glass-card rounded-2xl p-6">
                <h3 class="text-base font-bold text-white mb-4">Estado Operativo de Locales</h3>
                <div class="relative h-[280px] w-full flex items-center justify-center">
                    <canvas id="chart-estado"></canvas>
                </div>
            </div>
        </div>

        <!-- Chart 3: Rango de edad de certificados -->
        <div class="glass-card rounded-2xl p-6 mt-8">
            <h3 class="text-base font-bold text-white mb-4">Distribución de Certificados C4 por Rango de Edades</h3>
            <div class="relative h-[250px] w-full">
                <canvas id="chart-edad"></canvas>
            </div>
        </div>
    </main>

    <!-- Script de configuración de gráficos -->
    <script>
        // DATOS INYECTADOS POR PYTHON
        const data = DATA_PLACEHOLDER;

        // Formateador de números
        const fmt = new Intl.NumberFormat('es-PE');

        // Llenar KPIs
        document.getElementById('kpi-tx').innerText = fmt.format(data.kpis.total_tx);
        document.getElementById('kpi-cert').innerText = fmt.format(data.kpis.total_cert);
        document.getElementById('kpi-actas').innerText = fmt.format(data.kpis.total_actas);
        document.getElementById('kpi-centros').innerText = data.kpis.pct_operativo + '%';
        document.getElementById('kpi-centros-desc').innerHTML = `<span>🏢 ${data.kpis.total_centros} locales registrados</span>`;

        // Colores base premium
        const colorPrimary = '#38bdf8'; // sky-400
        const colorSecondary = '#818cf8'; // indigo-400
        const colorAccent = '#ec4899'; // pink-500
        const colorSuccess = '#10b981'; // emerald-500
        const colorWarning = '#f59e0b'; // amber-500
        const colorDanger = '#ef4444'; // red-500
        const textMuted = '#94a3b8'; // slate-400

        // Configuración común de Chart.js
        Chart.defaults.color = textMuted;
        Chart.defaults.font.family = "'Outfit', sans-serif";

        // 1. Gráfico de Línea: Tendencia de Transacciones
        new Chart(document.getElementById('chart-trend'), {
            type: 'line',
            data: {
                labels: data.tx_trend.labels,
                datasets: [{
                    label: 'Transacciones',
                    data: data.tx_trend.values,
                    borderColor: colorPrimary,
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 3,
                    pointBackgroundColor: colorPrimary,
                    pointHoverRadius: 7
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { 
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { callback: value => fmt.format(value) }
                    }
                }
            }
        });

        // 2. Gráfico Doughnut: Certificados por Género
        new Chart(document.getElementById('chart-gender'), {
            type: 'doughnut',
            data: {
                labels: data.gender_cert.labels,
                datasets: [{
                    data: data.gender_cert.values,
                    backgroundColor: [colorPrimary, colorAccent, colorSecondary, colorWarning],
                    borderWidth: 0,
                    hoverOffset: 10
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 12, padding: 15 }
                    }
                },
                cutout: '65%'
            }
        });

        // 3. Gráfico de Barra Horizontal: Top Departamentos
        new Chart(document.getElementById('chart-dept'), {
            type: 'bar',
            data: {
                labels: data.dept_tx.labels,
                datasets: [{
                    data: data.dept_tx.values,
                    backgroundColor: 'gradient',
                    backgroundColor: ctx => {
                        const gradient = ctx.chart.ctx.createLinearGradient(0, 0, ctx.chart.width, 0);
                        gradient.addColorStop(0, '#818cf8');
                        gradient.addColorStop(1, '#38bdf8');
                        return gradient;
                    },
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { 
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { callback: value => fmt.format(value) }
                    },
                    y: { grid: { display: false } }
                }
            }
        });

        // 4. Gráfico Pie: Estado de locales
        new Chart(document.getElementById('chart-estado'), {
            type: 'pie',
            data: {
                labels: data.estado_centros.labels,
                datasets: [{
                    data: data.estado_centros.values,
                    backgroundColor: [colorSuccess, colorWarning, colorDanger, colorSecondary, colorPrimary],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 12, padding: 15 }
                    }
                }
            }
        });

        // 5. Gráfico de Barra Vertical: Rango de edad de Certificados
        new Chart(document.getElementById('chart-edad'), {
            type: 'bar',
            data: {
                labels: data.edad_cert.labels,
                datasets: [{
                    data: data.edad_cert.values,
                    backgroundColor: 'rgba(236, 72, 153, 0.75)',
                    hoverBackgroundColor: colorAccent,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: { 
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { callback: value => fmt.format(value) }
                    }
                }
            }
        });
    </script>
</body>
</html>"""

    # Reemplazar el marcador de posición con el JSON real de los datos
    html_content = html_template.replace("DATA_PLACEHOLDER", json.dumps(data, ensure_ascii=False, indent=4))

    # Guardar en un archivo dashboard.html en la raíz del proyecto
    output_path = root_dir / "dashboard.html"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        log.info(f"Dashboard interactivo generado exitosamente en: {output_path.resolve()}")
        print(f"\\n¡DASHBOARD GENERADO CON EXITO!\\nArchivo: {output_path.resolve()}\\n")
    except Exception as e:
        log.error(f"Error al escribir el archivo dashboard.html: {e}")

if __name__ == "__main__":
    main()
