"""
Generador de Dashboard HTML interactivo con filtros de modalidad estricta:
- 100% Virtual / Teletrabajo en Colombia
- Presencial exclusivo permitido en Barranquilla y Atlántico
- Detección y advertencia de vacantes presenciales en otras ciudades (Bogotá, Medellín, Cali, etc.)
- Validación de enlaces directos y filtros de ciudades de Colombia.
"""

import csv
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional


COLOMBIAN_REGIONS = [
    {
        "name": "Barranquilla y Atlántico",
        "id": "barranquilla",
        "badge": "Barranquilla / Atlántico",
        "pattern": re.compile(r"\b(barranquilla|atl[aá]ntico|soledad|puerto\s+colombia|galapa|malambo)\b", re.IGNORECASE),
    },
    {
        "name": "Bogotá, D.C.",
        "id": "bogota",
        "badge": "Bogotá, D.C.",
        "pattern": re.compile(r"\b(bogot[aá]|d\.?c\.?)\b", re.IGNORECASE),
    },
    {
        "name": "Medellín y Antioquia",
        "id": "antioquia",
        "badge": "Medellín / Antioquia",
        "pattern": re.compile(r"\b(medell[ií]n|antioquia|envigado|itag[uü][ií]|bello|rionegro|sabaneta|guarne|copacabana)\b", re.IGNORECASE),
    },
    {
        "name": "Cali y Valle del Cauca",
        "id": "valle",
        "badge": "Cali / Valle",
        "pattern": re.compile(r"\b(cali|valle\s+del\s+cauca|yumbo|palmira|jamund[ií]|tulu[aá]|buga)\b", re.IGNORECASE),
    },
    {
        "name": "Cundinamarca y Sabana",
        "id": "cundinamarca",
        "badge": "Cundinamarca / Sabana",
        "pattern": re.compile(r"\b(ch[ií]a|cota|cundinamarca|sabana|mosquera|funza|madrid|zipaquir[aá]|soacha|tocancip[aá]|facatativ[aá]|cajic[aá]|sop[oó]|tabio|tenjo|girardot)\b", re.IGNORECASE),
    },
    {
        "name": "Bucaramanga y Santander",
        "id": "santander",
        "badge": "Bucaramanga / Santander",
        "pattern": re.compile(r"\b(bucaramanga|santander|floridablanca|gir[oó]n|piedecuesta|barrancabermeja)\b", re.IGNORECASE),
    },
    {
        "name": "Cartagena y Bolívar",
        "id": "cartagena",
        "badge": "Cartagena / Bolívar",
        "pattern": re.compile(r"\b(cartagena|bol[ií]var|turbaco)\b", re.IGNORECASE),
    },
    {
        "name": "Eje Cafetero (Pereira / Manizales / Armenia)",
        "id": "eje_cafetero",
        "badge": "Eje Cafetero",
        "pattern": re.compile(r"\b(pereira|manizales|armenia|risaralda|caldas|quind[ií]o|dosquebradas)\b", re.IGNORECASE),
    },
    {
        "name": "Otras Ciudades (Santa Marta, Ibagué, Villavicencio)",
        "id": "otras",
        "badge": "Otras Regiones",
        "pattern": re.compile(r"\b(santa\s+marta|magdalena|ibagu[eé]|tolima|villavicencio|meta|c[uú]cuta|norte\s+de\s+santander|pasto|nari[nñ]o|monter[ií]a|c[oó]rdoba|neiva|huila|tunja|boyac[aá]|valledupar|cesar|riohacha|guajira|popay[aá]n|cauca|sincelejo|sucre|yopal|casanare)\b", re.IGNORECASE),
    },
]


def detect_colombian_city(title: str, summary: str = "", location: str = "") -> Dict[str, str]:
    """Detect and normalize Colombian city/region from job data."""
    search_text = f"{location} {title} {summary}"
    for region in COLOMBIAN_REGIONS:
        if region["pattern"].search(search_text):
            return {
                "name": region["name"],
                "id": region["id"],
                "badge": region["badge"],
            }
    return {
        "name": "100% Remoto / Nivel Nacional",
        "id": "remoto_nacional",
        "badge": "100% Remoto Nacional",
    }


def clean_job_url(raw_url: str) -> str:
    """Ensure URL is direct, canonical, without search query noise."""
    if not raw_url:
        return ""
    u = raw_url.strip()
    u = u.split("#")[0]
    if "elempleo.com" in u:
        u = u.split("?")[0]
    elif "linkedin.com" in u:
        m = re.search(r"-(\d+)(?:\?|$)", u)
        if m:
            u = f"https://www.linkedin.com/jobs/view/{m.group(1)}"
        else:
            u = u.split("?")[0]
    elif "computrabajo.com" in u:
        u = u.split("?")[0]
    return u


def classify_candidate_modality(title: str, url: str) -> Dict[str, Any]:
    """
    Classifies modality strictly according to candidate's constraint:
    1) 100% Virtual / Teletrabajo -> Apta desde cualquier lugar de Colombia
    2) Presencial en Barranquilla / Atlántico -> Apta (ciudad de residencia de la candidata)
    3) Presencial en otras ciudades (Bogotá, Medellín, Cali, Bucaramanga, etc.) -> No apta (requiere mudanza)
    """
    t_u = f"{title} {url}".lower()

    is_barranquilla = bool(re.search(r"\b(barranquilla|atl[aá]ntico|soledad|puerto\s*colombia|galapa|malambo)\b", t_u))
    is_explicit_remote = bool(re.search(r"\b(remoto|virtual|teletrabajo|home\s*office|trabajo\s*desde\s*casa|wfh|a\s*distancia)\b", t_u))

    detected_region = None
    for reg in COLOMBIAN_REGIONS:
        if reg["id"] != "barranquilla" and reg["pattern"].search(t_u):
            detected_region = reg
            break

    if is_barranquilla:
        if is_explicit_remote:
            return {
                "tipo": "virtual",
                "tipo_label": "100% Virtual (Barranquilla)",
                "es_apta": True,
                "badge_class": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                "apta_nota": "100% Virtual / Teletrabajo aplicable desde Barranquilla",
                "icon": "💻",
            }
        else:
            return {
                "tipo": "presencial_bq",
                "tipo_label": "Presencial Barranquilla (Aceptada)",
                "es_apta": True,
                "badge_class": "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
                "apta_nota": "Presencial permitida: Ubicada en Barranquilla / Atlántico (su ciudad de residencia)",
                "icon": "📍",
            }
    elif detected_region:
        if is_explicit_remote:
            return {
                "tipo": "virtual",
                "tipo_label": f"100% Virtual (Base {detected_region['badge']})",
                "es_apta": True,
                "badge_class": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                "apta_nota": f"100% Virtual con sede en {detected_region['name']} (teletrabajo nacional)",
                "icon": "💻",
            }
        else:
            return {
                "tipo": "presencial_otra",
                "tipo_label": f"Presencial {detected_region['badge']}",
                "es_apta": False,
                "badge_class": "bg-amber-500/15 text-amber-300 border-amber-500/30",
                "apta_nota": f"Presencial en {detected_region['name']} (No compatible: requiere traslado fuera de Barranquilla)",
                "icon": "🏢",
            }
    elif is_explicit_remote:
        return {
            "tipo": "virtual",
            "tipo_label": "100% Virtual / Teletrabajo",
            "es_apta": True,
            "badge_class": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
            "apta_nota": "100% Virtual / Teletrabajo en Colombia (trabajo desde casa)",
            "icon": "💻",
        }
    else:
        return {
            "tipo": "virtual",
            "tipo_label": "100% Virtual Nacional",
            "es_apta": True,
            "badge_class": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
            "apta_nota": "Convocatoria nacional virtual aplicable desde Barranquilla",
            "icon": "💻",
        }


def load_vacancies_from_csv(csv_path: Path) -> List[Dict[str, Any]]:
    if not csv_path.exists():
        return []

    vacancies = []
    seen_keys = set()

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = row.get("ID/Hash", "")
            raw_url = row.get("Enlace Directo", "")

            # Filter out mock test fixtures
            if raw_id.startswith("mock_") or "mock-" in raw_url:
                continue

            cleaned_url = clean_job_url(raw_url)
            title = row.get("Título", "").strip()
            company = row.get("Empresa", "Confidencial").strip()
            resumen = row.get("Resumen de Afinidad", "").strip()
            modalidad = row.get("Modalidad", "Remoto").strip()

            dedup_key = (title.lower(), company.lower(), cleaned_url.lower())
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            score_str = row.get("Score %", "0%").replace("%", "").strip()
            try:
                score_num = float(score_str)
            except ValueError:
                score_num = 0.0

            # Detect portal
            portal = "Portal Web"
            if "elempleo.com" in cleaned_url:
                portal = "ElEmpleo"
            elif "linkedin.com" in cleaned_url:
                portal = "LinkedIn"
            elif "computrabajo.com" in cleaned_url:
                portal = "Computrabajo"
            elif "remotive.com" in cleaned_url:
                portal = "Remotive"

            city_info = detect_colombian_city(title=title, summary=resumen, location=modalidad)
            mod_info = classify_candidate_modality(title=title, url=cleaned_url)

            vacancies.append({
                "id": raw_id,
                "fecha": row.get("Fecha Detección", ""),
                "titulo": title,
                "empresa": company,
                "score": score_num,
                "score_str": f"{score_num:.0f}%",
                "modalidad": mod_info["tipo_label"],
                "tipo_modalidad": mod_info["tipo"],
                "es_apta": mod_info["es_apta"],
                "apta_nota": mod_info["apta_nota"],
                "badge_class": mod_info["badge_class"],
                "mod_icon": mod_info["icon"],
                "url": cleaned_url,
                "salario": row.get("Salario", ""),
                "resumen": resumen,
                "estado": row.get("Estado", "Nueva"),
                "notas": row.get("Notas Usuario", ""),
                "portal": portal,
                "ciudad_id": city_info["id"],
                "ciudad_nombre": city_info["name"],
                "ciudad_badge": city_info["badge"],
            })

    # Sort: highest score first
    vacancies.sort(key=lambda v: v["score"], reverse=True)
    return vacancies


def build_dashboard_html(vacancies: List[Dict[str, Any]], profile_info: Dict[str, Any]) -> str:
    vacancies_json = json.dumps(vacancies, ensure_ascii=False)
    profile_json = json.dumps(profile_info, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es" class="h-full bg-slate-950 text-slate-100">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dashboard de Oportunidades - {profile_info.get('title', 'Tracker de Empleos')}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          fontFamily: {{
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
            mono: ['"JetBrains Mono"', 'monospace'],
          }},
          colors: {{
            brand: {{
              50: '#ecfeff',
              100: '#cffafe',
              500: '#06b6d4',
              600: '#0891b2',
              700: '#0e7490',
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: radial-gradient(circle at 50% 0%, #0f172a 0%, #020617 100%);
    }}
    .glass-card {{
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .glow-cyan {{
      box-shadow: 0 0 25px -5px rgba(6, 182, 212, 0.15);
    }}
    @media print {{
      .no-print {{ display: none !important; }}
      body {{ background: #fff !important; color: #000 !important; }}
      .glass-card {{ background: #fff !important; border: 1px solid #ccc !important; color: #000 !important; }}
    }}
  </style>
</head>
<body class="min-h-full flex flex-col antialiased selection:bg-cyan-500 selection:text-white">

  <!-- TOP NAVIGATION / HEADER -->
  <header class="border-b border-slate-800/80 bg-slate-950/60 sticky top-0 z-50 backdrop-blur-md">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-emerald-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
          </svg>
        </div>
        <div>
          <h1 class="text-base font-bold text-white tracking-tight flex items-center gap-2">
            Job Hunter Colombia <span class="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">En Vivo</span>
          </h1>
          <p class="text-xs text-slate-400">Oportunidades 100% Virtuales & Presencial Barranquilla</p>
        </div>
      </div>

      <div class="flex items-center gap-2.5">
        <button onclick="shareWhatsApp()" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12.031 6.172c-3.181 0-5.767 2.586-5.768 5.766-.001 1.298.38 2.27 1.019 3.287l-.711 2.598 2.664-.698c.969.588 1.961.92 3.125.92 3.182 0 5.768-2.587 5.768-5.766.001-3.181-2.585-5.768-5.768-5.768zm0 10.373c-1.023 0-1.895-.295-2.738-.795l-.196-.116-1.577.413.421-1.536-.128-.204c-.555-.883-.848-1.782-.847-2.879.001-2.539 2.067-4.606 4.608-4.606 2.54 0 4.607 2.067 4.607 4.606 0 2.54-2.067 4.607-4.608 4.607zm-7.031-4.607c-.001 3.865 3.146 7.012 7.031 7.012 1.258 0 2.443-.332 3.479-.915l4.89 1.282-1.305-4.767c.664-1.096 1.045-2.385 1.045-3.764 0-3.865-3.146-7.012-7.031-7.012-3.886 0-7.032 3.147-7.032 7.012z"/></svg>
          <span class="hidden sm:inline">Compartir WhatsApp</span>
        </button>
        <button onclick="window.print()" class="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 transition" title="Imprimir o Guardar PDF">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
        </button>
      </div>
    </div>
  </header>

  <!-- MAIN CONTENT CONTAINER -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

    <!-- CANDIDATE PROFILE BANNER -->
    <div class="glass-card rounded-2xl p-6 glow-cyan relative overflow-hidden">
      <div class="absolute -right-12 -bottom-12 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
      
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
        <div class="space-y-2">
          <div class="flex flex-wrap items-center gap-2.5">
            <span class="px-2.5 py-0.5 rounded-md text-xs font-bold uppercase tracking-wider bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
              Perfil Activo #1
            </span>
            <span class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              15+ Años Exp. Total
            </span>
            <span class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              💻 100% Virtual Colombia
            </span>
            <span class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/30">
              📍 Presencial Solo en Barranquilla
            </span>
          </div>
          <h2 class="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Ingeniera Civil Senior &bull; Especialista en Vías & SST
          </h2>
          <p class="text-sm text-slate-300 max-w-3xl leading-relaxed">
            Filtro de modalidad estricto: Se priorizan vacantes <strong>100% Virtuales / Teletrabajo</strong> en Colombia o de modalidad <strong>Presencial exclusivamente en Barranquilla / Atlántico</strong>. Las ofertas presenciales en otras ciudades (Bogotá, Medellín, etc.) se identifican con advertencia de requerir mudanza.
          </p>
        </div>

        <div class="flex flex-col sm:flex-row md:flex-col gap-2 shrink-0 text-right">
          <div class="p-3 bg-slate-800/80 rounded-xl border border-slate-700/60 text-center sm:text-right">
            <div class="text-xs text-slate-400">Especialidades Duales</div>
            <div class="text-sm font-semibold text-cyan-300">Infraestructura Vial (5+ años)</div>
            <div class="text-sm font-semibold text-emerald-300">Seguridad & Salud SST (5+ años)</div>
          </div>
        </div>
      </div>
    </div>

    <!-- RECOMMENDED MODALITY SELECTOR BAR -->
    <div class="glass-card rounded-xl p-3.5 border border-slate-800 no-print flex flex-col lg:flex-row lg:items-center justify-between gap-3 shadow-lg">
      <div class="flex items-center gap-2 text-xs font-bold text-slate-300">
        <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
        <span>Selecciona la Modalidad Deseada:</span>
      </div>
      <div class="flex flex-wrap items-center gap-2" id="modalityButtons">
        <button onclick="setModalityFilter('recommended')" id="btn-mod-recommended"
          class="px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all bg-gradient-to-r from-cyan-600 to-emerald-600 text-white border-cyan-400 shadow-md shadow-cyan-500/20 flex items-center gap-1.5">
          <span>🎯 Aptas: 100% Virtual o Barranquilla</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-recommended">0</span>
        </button>
        <button onclick="setModalityFilter('virtual')" id="btn-mod-virtual"
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500 flex items-center gap-1.5">
          <span>💻 Solo 100% Virtual</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-virtual">0</span>
        </button>
        <button onclick="setModalityFilter('presencial_bq')" id="btn-mod-presencial_bq"
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500 flex items-center gap-1.5">
          <span>📍 Solo Presencial Barranquilla</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-bq">0</span>
        </button>
        <button onclick="setModalityFilter('presencial_otra')" id="btn-mod-presencial_otra"
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 flex items-center gap-1.5">
          <span>🏢 Otras Ciudades (Requiere Traslado)</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-other">0</span>
        </button>
        <button onclick="setModalityFilter('all')" id="btn-mod-all"
          class="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700">
          <span>🌐 Todas las ofertas</span>
        </button>
      </div>
    </div>

    <!-- STATS CARDS -->
    <div class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="glass-card rounded-xl p-4 border border-cyan-500/30 bg-cyan-950/20">
        <div class="flex items-center justify-between text-cyan-300 text-xs font-semibold mb-1">
          <span>🎯 Aptas para la Candidata</span>
          <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-white" id="stat-apta">0</div>
        <div class="text-[11px] text-cyan-400/80 mt-1">100% Virtual o Barranquilla</div>
      </div>

      <div class="glass-card rounded-xl p-4 border border-emerald-500/30 bg-emerald-950/20">
        <div class="flex items-center justify-between text-emerald-300 text-xs font-semibold mb-1">
          <span>💻 100% Virtual / Teletrabajo</span>
          <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-400" id="stat-virtual">0</div>
        <div class="text-[11px] text-slate-400 mt-1">Desde cualquier lugar de Colombia</div>
      </div>

      <div class="glass-card rounded-xl p-4 border border-sky-500/30 bg-sky-950/20">
        <div class="flex items-center justify-between text-sky-300 text-xs font-semibold mb-1">
          <span>📍 Presencial en Barranquilla</span>
          <svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-sky-400" id="stat-bq">0</div>
        <div class="text-[11px] text-slate-400 mt-1">Permitido en su ciudad base</div>
      </div>

      <div class="glass-card rounded-xl p-4 border border-slate-800">
        <div class="flex items-center justify-between text-slate-400 text-xs font-medium mb-1">
          <span>🏢 Presencial Otras Ciudades</span>
          <svg class="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-bold text-amber-400" id="stat-other">0</div>
        <div class="text-[11px] text-slate-500 mt-1">Requieren mudanza a Bogotá/Med/etc.</div>
      </div>
    </div>

    <!-- QUICK CITY CHIPS (CLICK TO FILTER) -->
    <div class="no-print space-y-2">
      <div class="text-xs font-semibold text-slate-400 flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path></svg>
        <span>Filtro Rápido por Ciudad / Región:</span>
      </div>
      <div id="cityChips" class="flex flex-wrap gap-2">
        <!-- Rendered via JS -->
      </div>
    </div>

    <!-- FILTER TOOLBAR -->
    <div class="glass-card rounded-xl p-4 space-y-4 no-print border border-slate-800">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <!-- SEARCH INPUT -->
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1.5">Buscar por cargo o empresa</label>
          <div class="relative">
            <input type="text" id="searchInput" oninput="applyFilters()" placeholder="Ej: Vías, SST, Interventoría..." 
              class="w-full bg-slate-900 border border-slate-700 text-white rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent placeholder-slate-500">
            <svg class="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
          </div>
        </div>

        <!-- CITY FILTER DROPDOWN -->
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1.5">Ciudad / Ubicación</label>
          <select id="cityFilter" onchange="applyFilters()" class="w-full bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500">
            <option value="all">Todas las ciudades y regiones</option>
            <option value="barranquilla">Barranquilla y Atlántico (Aceptado)</option>
            <option value="remoto_nacional">100% Remoto / Nivel Nacional</option>
            <option value="bogota">Bogotá, D.C.</option>
            <option value="antioquia">Medellín y Antioquia</option>
            <option value="valle">Cali y Valle del Cauca</option>
            <option value="cundinamarca">Cundinamarca y Sabana</option>
            <option value="santander">Bucaramanga y Santander</option>
            <option value="cartagena">Cartagena y Bolívar</option>
            <option value="eje_cafetero">Eje Cafetero</option>
            <option value="otras">Otras Regiones</option>
          </select>
        </div>

        <!-- SCORE FILTER -->
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1.5">Nivel de Afinidad (Score)</label>
          <select id="scoreFilter" onchange="applyFilters()" class="w-full bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500">
            <option value="all">Todas las ofertas</option>
            <option value="70">Alta Afinidad (&ge; 70%)</option>
            <option value="60">Afinidad Media-Alta (&ge; 60%)</option>
            <option value="50">Afinidad Base (&ge; 50%)</option>
          </select>
        </div>

        <!-- PORTAL FILTER -->
        <div>
          <label class="block text-xs font-medium text-slate-400 mb-1.5">Portal de Empleo</label>
          <select id="portalFilter" onchange="applyFilters()" class="w-full bg-slate-900 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500">
            <option value="all">Todos los portales</option>
            <option value="ElEmpleo">ElEmpleo Colombia</option>
            <option value="Computrabajo">Computrabajo</option>
            <option value="LinkedIn">LinkedIn Jobs</option>
          </select>
        </div>
      </div>

      <div class="flex items-center justify-between pt-2 border-t border-slate-800 text-xs text-slate-400">
        <span id="resultsCount">Mostrando vacantes...</span>
        <button onclick="resetFilters()" class="text-cyan-400 hover:text-cyan-300 font-semibold transition">Restablecer todos los filtros</button>
      </div>
    </div>

    <!-- CARDS GRID -->
    <div id="vacanciesList" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <!-- Injected via JavaScript -->
    </div>

    <!-- EMPTY STATE -->
    <div id="emptyState" class="hidden text-center py-16">
      <div class="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-4 text-slate-500">
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
      </div>
      <h3 class="text-lg font-semibold text-white">No se encontraron vacantes con esta combinación de filtros</h3>
      <p class="text-sm text-slate-400 mt-1 max-w-sm mx-auto">Prueba haciendo clic en "Aptas: 100% Virtual o Barranquilla" o restablece los filtros.</p>
      <button onclick="resetFilters()" class="mt-4 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold">Ver todas las ofertas</button>
    </div>

  </main>

  <footer class="border-t border-slate-800 bg-slate-950 py-6 text-center text-xs text-slate-500 no-print">
    <div class="max-w-7xl mx-auto px-4">
      Job Hunter AI &bull; Oportunidades 100% Virtuales en Colombia & Presencial en Barranquilla &bull; Enlaces directos verificados
    </div>
  </footer>

  <!-- SCRIPT DATA & LOGIC -->
  <script>
    const INITIAL_VACANCIES = {vacancies_json};
    const PROFILE_INFO = {profile_json};
    let currentModalityFilter = 'recommended'; // Default view: 100% Virtual o Barranquilla

    function getStoredStatus(id, defaultStatus) {{
      return localStorage.getItem('jh_status_' + id) || defaultStatus;
    }}
    function setStoredStatus(id, status) {{
      localStorage.setItem('jh_status_' + id, status);
      applyFilters();
    }}

    function updateStats() {{
      const total = INITIAL_VACANCIES.length;
      const apta = INITIAL_VACANCIES.filter(v => v.es_apta).length;
      const virtual = INITIAL_VACANCIES.filter(v => v.tipo_modalidad === 'virtual').length;
      const bq = INITIAL_VACANCIES.filter(v => v.tipo_modalidad === 'presencial_bq').length;
      const other = INITIAL_VACANCIES.filter(v => v.tipo_modalidad === 'presencial_otra').length;

      document.getElementById('stat-apta').textContent = apta;
      document.getElementById('stat-virtual').textContent = virtual;
      document.getElementById('stat-bq').textContent = bq;
      document.getElementById('stat-other').textContent = other;

      document.getElementById('btn-count-recommended').textContent = apta;
      document.getElementById('btn-count-virtual').textContent = virtual;
      document.getElementById('btn-count-bq').textContent = bq;
      document.getElementById('btn-count-other').textContent = other;
    }}

    function setModalityFilter(modalityType) {{
      currentModalityFilter = modalityType;

      // Update button styles
      const btns = [
        {{ id: 'btn-mod-recommended', type: 'recommended', activeClass: 'bg-gradient-to-r from-cyan-600 to-emerald-600 text-white border-cyan-400 shadow-md shadow-cyan-500/20' }},
        {{ id: 'btn-mod-virtual', type: 'virtual', activeClass: 'bg-emerald-600 text-white border-emerald-400 shadow-md shadow-emerald-500/20' }},
        {{ id: 'btn-mod-presencial_bq', type: 'presencial_bq', activeClass: 'bg-cyan-600 text-white border-cyan-400 shadow-md shadow-cyan-500/20' }},
        {{ id: 'btn-mod-presencial_otra', type: 'presencial_otra', activeClass: 'bg-amber-600 text-white border-amber-400 shadow-md shadow-amber-500/20' }},
        {{ id: 'btn-mod-all', type: 'all', activeClass: 'bg-slate-700 text-white border-slate-500' }},
      ];

      btns.forEach(b => {{
        const elem = document.getElementById(b.id);
        if (!elem) return;
        if (b.type === modalityType) {{
          elem.className = `px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all ${{b.activeClass}} flex items-center gap-1.5`;
        }} else {{
          elem.className = "px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 flex items-center gap-1.5";
        }}
      }});

      applyFilters();
    }}

    function renderCityChips() {{
      const container = document.getElementById('cityChips');
      const counts = {{}};
      INITIAL_VACANCIES.forEach(v => {{
        counts[v.ciudad_id] = (counts[v.ciudad_id] || 0) + 1;
      }});

      const chipOptions = [
        {{ id: 'all', label: 'Todas las ciudades', count: INITIAL_VACANCIES.length }},
        {{ id: 'barranquilla', label: '📍 Barranquilla', count: counts['barranquilla'] || 0 }},
        {{ id: 'remoto_nacional', label: '💻 100% Remoto Nacional', count: counts['remoto_nacional'] || 0 }},
        {{ id: 'bogota', label: 'Bogotá, D.C.', count: counts['bogota'] || 0 }},
        {{ id: 'valle', label: 'Cali / Valle', count: counts['valle'] || 0 }},
        {{ id: 'santander', label: 'Bucaramanga', count: counts['santander'] || 0 }},
        {{ id: 'antioquia', label: 'Medellín', count: counts['antioquia'] || 0 }},
        {{ id: 'cartagena', label: 'Cartagena', count: counts['cartagena'] || 0 }},
        {{ id: 'cundinamarca', label: 'Cundinamarca / Sabana', count: counts['cundinamarca'] || 0 }},
        {{ id: 'eje_cafetero', label: 'Eje Cafetero', count: counts['eje_cafetero'] || 0 }},
        {{ id: 'otras', label: 'Otras Regiones', count: counts['otras'] || 0 }},
      ];

      container.innerHTML = chipOptions.filter(c => c.id === 'all' || c.count > 0).map(c => `
        <button onclick="selectCityChip('${{c.id}}')" id="chip-${{c.id}}"
          class="px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${{c.id === 'all' ? 'bg-cyan-600 text-white border-cyan-500' : 'bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500'}}">
          ${{c.label}} <span class="ml-1 opacity-75 font-mono text-[10px]">(${{c.count}})</span>
        </button>
      `).join('');
    }}

    function selectCityChip(cityId) {{
      document.getElementById('cityFilter').value = cityId;
      document.querySelectorAll('#cityChips button').forEach(btn => {{
        btn.className = "px-3 py-1 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500";
      }});
      const activeBtn = document.getElementById('chip-' + cityId);
      if (activeBtn) {{
        activeBtn.className = "px-3 py-1 rounded-lg text-xs font-semibold border transition-all bg-cyan-600 text-white border-cyan-500 shadow-md shadow-cyan-500/20";
      }}
      applyFilters();
    }}

    function getPortalBadge(portal) {{
      switch(portal) {{
        case 'ElEmpleo':
          return '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">ElEmpleo</span>';
        case 'LinkedIn':
          return '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20">LinkedIn</span>';
        case 'Computrabajo':
          return '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">Computrabajo</span>';
        default:
          return '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-700 text-slate-300">Portal Web</span>';
      }}
    }}

    function getScoreBadge(score) {{
      if (score >= 70) {{
        return `<span class="px-2.5 py-1 rounded-lg text-xs font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 shadow-sm">
          <span class="w-2 h-2 rounded-full bg-emerald-400"></span>${{score.toFixed(0)}}% Match
        </span>`;
      }} else if (score >= 60) {{
        return `<span class="px-2.5 py-1 rounded-lg text-xs font-extrabold bg-teal-500/20 text-teal-300 border border-teal-500/30 flex items-center gap-1.5 shadow-sm">
          <span class="w-2 h-2 rounded-full bg-teal-400"></span>${{score.toFixed(0)}}% Match
        </span>`;
      }} else {{
        return `<span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-slate-400"></span>${{score.toFixed(0)}}% Match
        </span>`;
      }}
    }}

    function renderVacancies(items) {{
      const container = document.getElementById('vacanciesList');
      const emptyState = document.getElementById('emptyState');
      const resultsCount = document.getElementById('resultsCount');

      resultsCount.textContent = `Mostrando ${{items.length}} de ${{INITIAL_VACANCIES.length}} ofertas`;

      if (items.length === 0) {{
        container.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
      }}
      emptyState.classList.add('hidden');

      container.innerHTML = items.map(v => {{
        const currentStatus = getStoredStatus(v.id, v.estado);
        const hasSalary = v.salario && v.salario.trim().length > 0;
        
        const isCopnia = v.resumen.includes('COPNIA');
        const isSst = v.resumen.includes('SST');
        const isVias = v.titulo.toLowerCase().includes('vias') || v.titulo.toLowerCase().includes('vías') || v.resumen.toLowerCase().includes('vial');

        return `
        <div class="glass-card rounded-xl p-5 flex flex-col justify-between transition-all duration-200 hover:border-cyan-500/40 hover:shadow-xl hover:shadow-cyan-500/5 group border border-slate-800/90">
          <div class="space-y-3.5">
            <!-- HEADER INFO -->
            <div class="flex items-start justify-between gap-2">
              <div class="flex flex-wrap items-center gap-1.5">
                ${{getPortalBadge(v.portal)}}
                <!-- MODALITY BADGE -->
                <span class="px-2 py-0.5 rounded text-[11px] font-bold border flex items-center gap-1 ${{v.badge_class}}">
                  <span>${{v.mod_icon}}</span>
                  <span>${{v.modalidad}}</span>
                </span>
                <!-- CITY BADGE -->
                <span class="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
                  ${{v.ciudad_badge}}
                </span>
              </div>
              <div>${{getScoreBadge(v.score)}}</div>
            </div>

            <!-- TITLE & COMPANY -->
            <div>
              <h3 class="text-base font-bold text-white group-hover:text-cyan-300 transition-colors line-clamp-2" title="${{v.titulo}}">
                ${{v.titulo}}
              </h3>
              <div class="flex items-center gap-1.5 text-xs text-slate-400 mt-1 font-medium">
                <svg class="w-3.5 h-3.5 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>
                <span class="truncate">${{v.empresa}}</span>
              </div>
            </div>

            <!-- SALARY IF AVAILABLE -->
            ${{hasSalary ? `
            <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/40 border border-emerald-800/40 text-emerald-300 text-xs font-semibold">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              <span>${{v.salario}}</span>
            </div>` : ''}}

            <!-- APTA / NOTA MODALIDAD -->
            ${{v.es_apta ? `
            <div class="text-[11px] text-emerald-300 bg-emerald-950/30 border border-emerald-800/40 rounded-lg p-2 flex items-center gap-2">
              <svg class="w-4 h-4 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <span>${{v.apta_nota}}</span>
            </div>` : `
            <div class="text-[11px] text-amber-300 bg-amber-950/30 border border-amber-800/40 rounded-lg p-2 flex items-center gap-2">
              <svg class="w-4 h-4 text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
              <span>${{v.apta_nota}}</span>
            </div>`}}

            <!-- SUMMARY & OBSERVATIONS -->
            <div class="bg-slate-900/60 rounded-lg p-3 text-xs text-slate-300 leading-relaxed border border-slate-800 space-y-2">
              <p>${{v.resumen}}</p>
              
              <div class="flex flex-wrap gap-1 pt-1">
                ${{isVias ? '<span class="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-400 text-[10px] font-semibold border border-cyan-800/40">Infraestructura Vial</span>' : ''}}
                ${{isSst ? '<span class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 text-[10px] font-semibold border border-emerald-800/40">SST / HSEQ</span>' : ''}}
                ${{isCopnia ? '<span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-medium border border-slate-700">Tarjeta COPNIA</span>' : ''}}
              </div>
            </div>
          </div>

          <!-- FOOTER / ACTIONS -->
          <div class="pt-4 mt-4 border-t border-slate-800/80 space-y-3">
            <!-- STATUS SELECTOR -->
            <div class="flex items-center justify-between gap-2">
              <div class="text-[11px] text-slate-400 font-medium">Estado de Postulación:</div>
              <select onchange="setStoredStatus('${{v.id}}', this.value)" 
                class="bg-slate-900 border border-slate-700 text-xs rounded-md px-2 py-1 text-slate-200 focus:ring-1 focus:ring-cyan-500">
                <option value="Nueva" ${{currentStatus === 'Nueva' ? 'selected' : ''}}>Nueva</option>
                <option value="Por revisar" ${{currentStatus === 'Por revisar' ? 'selected' : ''}}>Por revisar</option>
                <option value="Postulado" ${{currentStatus === 'Postulado' ? 'selected' : ''}}>Postulado</option>
                <option value="En proceso" ${{currentStatus === 'En proceso' ? 'selected' : ''}}>En proceso</option>
                <option value="Descartado" ${{currentStatus === 'Descartado' ? 'selected' : ''}}>Descartado</option>
              </select>
            </div>

            <!-- BUTTONS (CLEAN WORKING LINK) -->
            <div class="flex items-center gap-2">
              <a href="${{v.url}}" target="_blank" rel="noopener noreferrer" 
                class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors shadow-sm">
                <span>Ver Oferta y Postular</span>
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
              </a>
              <button onclick="copyJobShare('${{v.titulo.replace(/'/g, "\\\\'") }}', '${{v.empresa.replace(/'/g, "\\\\'") }}', '${{v.url}}')" 
                title="Copiar enlace para compartir" 
                class="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 transition">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"></path></svg>
              </button>
            </div>
          </div>
        </div>
        `;
      }}).join('');
    }}

    function applyFilters() {{
      const query = document.getElementById('searchInput').value.toLowerCase().trim();
      const cityVal = document.getElementById('cityFilter').value;
      const scoreVal = document.getElementById('scoreFilter').value;
      const portalVal = document.getElementById('portalFilter').value;

      const filtered = INITIAL_VACANCIES.filter(v => {{
        // Modality button filter
        if (currentModalityFilter === 'recommended' && !v.es_apta) {{
          return false;
        }}
        if (currentModalityFilter === 'virtual' && v.tipo_modalidad !== 'virtual') {{
          return false;
        }}
        if (currentModalityFilter === 'presencial_bq' && v.tipo_modalidad !== 'presencial_bq') {{
          return false;
        }}
        if (currentModalityFilter === 'presencial_otra' && v.tipo_modalidad !== 'presencial_otra') {{
          return false;
        }}

        // Text search
        if (query) {{
          const matchTitle = v.titulo.toLowerCase().includes(query);
          const matchCompany = v.empresa.toLowerCase().includes(query);
          const matchDesc = v.resumen.toLowerCase().includes(query);
          const matchCity = v.ciudad_nombre.toLowerCase().includes(query);
          if (!matchTitle && !matchCompany && !matchDesc && !matchCity) return false;
        }}

        // City filter
        if (cityVal !== 'all' && v.ciudad_id !== cityVal) {{
          return false;
        }}

        // Score filter
        if (scoreVal !== 'all') {{
          const minScore = parseFloat(scoreVal);
          if (v.score < minScore) return false;
        }}

        // Portal filter
        if (portalVal !== 'all' && v.portal !== portalVal) {{
          return false;
        }}

        return true;
      }});

      renderVacancies(filtered);
    }}

    function resetFilters() {{
      document.getElementById('searchInput').value = '';
      document.getElementById('cityFilter').value = 'all';
      document.getElementById('scoreFilter').value = 'all';
      document.getElementById('portalFilter').value = 'all';
      selectCityChip('all');
      setModalityFilter('recommended');
    }}

    function copyJobShare(title, company, url) {{
      const text = `🎯 *Oportunidad Laboral*\\n💼 Cargo: ${{title}}\\n🏢 Empresa: ${{company}}\\n🔗 Postular aquí: ${{url}}`;
      navigator.clipboard.writeText(text).then(() => {{
        alert("Enlace directo copiado al portapapeles. ¡Listo para compartir!");
      }}).catch(() => {{
        window.prompt("Copia este texto:", text);
      }});
    }}

    function shareWhatsApp() {{
      const aptaCount = INITIAL_VACANCIES.filter(v => v.es_apta).length;
      const text = encodeURIComponent(`Hola, te comparto estas vacantes verificadas para Ingeniera Civil (Vías & SST). Hay ${{aptaCount}} ofertas aptas (100% Virtuales o Presenciales en Barranquilla).`);
      window.open(`https://api.whatsapp.com/send?text=${{text}}`, '_blank');
    }}

    document.addEventListener('DOMContentLoaded', () => {{
      updateStats();
      renderCityChips();
      setModalityFilter('recommended');
    }});
  </script>
</body>
</html>
"""


def update_dashboard(base_dir: Optional[Path] = None) -> List[Path]:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent
    csv_file = base_dir / "output" / "profile_1_civil_vias_sst_tracker.csv"

    vacancies = load_vacancies_from_csv(csv_file)
    print(f"Cargadas {len(vacancies)} vacantes reales y desduplicadas desde {csv_file}")

    profile_info = {
        "id": "profile_1_civil_vias_sst",
        "title": "Ingeniera Civil Senior - Especialista en Vías & SST",
        "experience": "15+ años",
        "vias": "5+ años",
        "sst": "5+ años",
        "modality": "100% Virtual Colombia o Presencial Barranquilla"
    }

    html_content = build_dashboard_html(vacancies, profile_info)

    out_paths = [
        base_dir / "index.html",
        base_dir / "dashboard.html",
        base_dir / "output" / "index.html",
        base_dir / "output" / "dashboard.html",
        base_dir / "SUBIR_A_NETLIFY" / "index.html",
        base_dir / "SUBIR_A_NETLIFY" / "dashboard.html",
    ]

    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Dashboard actualizado con éxito en: {p}")

    return out_paths


def main():
    base_dir = Path(__file__).resolve().parent
    update_dashboard(base_dir)


if __name__ == "__main__":
    main()
