"""
Generador de Dashboard HTML interactivo multi-perfil con filtros de modalidad estricta:
- Perfil 1: Ingeniera Civil Senior (Vías & SST) -> 100% Virtual en Colombia o Presencial en Barranquilla
- Perfil 5: Técnico en Sistemas (TI & Programación) -> 100% Remoto nacional / LATAM
- Selector en vivo en barra superior para alternar entre perfiles al instante
- Detección de enlaces directos limpios, filtros de ciudades, búsqueda rápida y analítica de afinidad.
"""

import csv
import json
import re
import shutil
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


def classify_candidate_modality(title: str, url: str, profile_id: str = "profile_1_civil_vias_sst") -> Dict[str, Any]:
    """Classifies modality strictly according to candidate's constraint."""
    t_u = f"{title} {url}".lower()

    if profile_id in ("profile_5_tecnico_sistemas", "profile_6_auxiliar_administrativo"):
        # Strictly 100% Remote / Teletrabajo
        is_presencial = any(p in t_u for p in ("presencial", "en oficina", "en sitio", "sede"))
        if is_presencial:
            return {
                "tipo": "presencial_otra",
                "tipo_label": "Presencial / En Oficina",
                "es_apta": False,
                "badge_class": "bg-amber-500/15 text-amber-300 border-amber-500/30",
                "apta_nota": "Presencial en oficina (No compatible: Este perfil busca 100% Remoto)",
                "icon": "🏢",
            }
        else:
            return {
                "tipo": "virtual",
                "tipo_label": "100% Remoto / Teletrabajo",
                "es_apta": True,
                "badge_class": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                "apta_nota": "100% Remoto verificado (trabajo desde casa en Colombia / LATAM)",
                "icon": "💻",
            }

    # Profile 1: Civil Engineer (100% Virtual or Presencial Barranquilla)
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


def load_vacancies_from_csv(csv_path: Path, profile_id: str = "profile_1_civil_vias_sst") -> List[Dict[str, Any]]:
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
            mod_info = classify_candidate_modality(title=title, url=cleaned_url, profile_id=profile_id)

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


def build_dashboard_html(profiles_data: Dict[str, Any], initial_profile_id: str = "profile_1_civil_vias_sst") -> str:
    profiles_json = json.dumps(profiles_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es" class="h-full bg-slate-950 text-slate-100">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job Hunter Colombia - Dashboard Multi-Perfil</title>
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
  <header class="border-b border-slate-800/80 bg-slate-950/70 sticky top-0 z-50 backdrop-blur-md">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-emerald-500 flex items-center justify-center shadow-lg shadow-cyan-500/20 shrink-0">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
          </svg>
        </div>
        <div class="hidden sm:block">
          <h1 class="text-base font-bold text-white tracking-tight flex items-center gap-2">
            Job Hunter Colombia <span class="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">En Vivo</span>
          </h1>
          <p class="text-xs text-slate-400" id="headerSubtitle">Búsqueda Inteligente de Oportunidades Laborales</p>
        </div>
      </div>

      <!-- PROFILE SELECTOR TABS IN NAVBAR -->
      <div class="flex items-center gap-1.5 p-1 bg-slate-900/90 rounded-xl border border-slate-800 shadow-inner flex-wrap sm:flex-nowrap">
        <button onclick="switchProfile('profile_1_civil_vias_sst')" id="tab-p1" 
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all text-white bg-cyan-600 shadow-md">
          <span>👷‍♀️ Ing. Civil</span>
        </button>
        <button onclick="switchProfile('profile_5_tecnico_sistemas')" id="tab-p5" 
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all text-slate-400 hover:text-white hover:bg-slate-800">
          <span>💻 Técnico Sistemas</span>
        </button>
        <button onclick="switchProfile('profile_6_auxiliar_administrativo')" id="tab-p6" 
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all text-slate-400 hover:text-white hover:bg-slate-800">
          <span>📋 Auxiliar Administrativo</span>
        </button>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <button onclick="shareWhatsApp()" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12.031 6.172c-3.181 0-5.767 2.586-5.768 5.766-.001 1.298.38 2.27 1.019 3.287l-.711 2.598 2.664-.698c.969.588 1.961.92 3.125.92 3.182 0 5.768-2.587 5.768-5.766.001-3.181-2.585-5.768-5.768-5.768zm0 10.373c-1.023 0-1.895-.295-2.738-.795l-.196-.116-1.577.413.421-1.536-.128-.204c-.555-.883-.848-1.782-.847-2.879.001-2.539 2.067-4.606 4.608-4.606 2.54 0 4.607 2.067 4.607 4.606 0 2.54-2.067 4.607-4.608 4.607zm-7.031-4.607c-.001 3.865 3.146 7.012 7.031 7.012 1.258 0 2.443-.332 3.479-.915l4.89 1.282-1.305-4.767c.664-1.096 1.045-2.385 1.045-3.764 0-3.865-3.146-7.012-7.031-7.012-3.886 0-7.032 3.147-7.032 7.012z"/></svg>
          <span class="hidden md:inline">Compartir WhatsApp</span>
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
    <div class="glass-card rounded-2xl p-6 glow-cyan relative overflow-hidden transition-all duration-300">
      <div class="absolute -right-12 -bottom-12 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
      
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
        <div class="space-y-2">
          <div class="flex flex-wrap items-center gap-2.5" id="bannerBadges">
            <span class="px-2.5 py-0.5 rounded-md text-xs font-bold uppercase tracking-wider bg-cyan-500/20 text-cyan-300 border border-cyan-500/30" id="badgeProfileId">
              Perfil Activo #1
            </span>
            <span class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30" id="badgeExperience">
              15+ Años Exp. Total
            </span>
            <span class="px-2.5 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" id="badgeModality">
              💻 100% Virtual Colombia
            </span>
          </div>
          <h2 class="text-2xl sm:text-3xl font-extrabold text-white tracking-tight" id="bannerTitle">
            Ingeniera Civil Senior &bull; Especialista en Vías & SST
          </h2>
          <p class="text-sm text-slate-300 max-w-3xl leading-relaxed" id="bannerDescription">
            Filtro de modalidad estricto: Se priorizan vacantes <strong>100% Virtuales / Teletrabajo</strong> en Colombia o de modalidad <strong>Presencial exclusivamente en Barranquilla / Atlántico</strong>.
          </p>
        </div>

        <div class="flex flex-col sm:flex-row md:flex-col gap-2 shrink-0 text-right">
          <div class="p-3 bg-slate-800/80 rounded-xl border border-slate-700/60 text-center sm:text-right" id="bannerSpecs">
            <div class="text-xs text-slate-400">Especialidades Técnicas</div>
            <div class="text-sm font-semibold text-cyan-300" id="specText1">Infraestructura Vial (5+ años)</div>
            <div class="text-sm font-semibold text-emerald-300" id="specText2">Seguridad & Salud SST (5+ años)</div>
          </div>
        </div>
      </div>
    </div>

    <!-- RECOMMENDED MODALITY SELECTOR BAR -->
    <div class="glass-card rounded-xl p-3.5 border border-slate-800 no-print flex flex-col lg:flex-row lg:items-center justify-between gap-3 shadow-lg">
      <div class="flex items-center gap-2 text-xs font-bold text-slate-300">
        <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
        <span>Modalidad Filtrada:</span>
      </div>
      <div class="flex flex-wrap items-center gap-2" id="modalityButtons">
        <button onclick="setModalityFilter('recommended')" id="btn-mod-recommended"
          class="px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all bg-gradient-to-r from-cyan-600 to-emerald-600 text-white border-cyan-400 shadow-md shadow-cyan-500/20 flex items-center gap-1.5">
          <span id="label-mod-recommended">🎯 Ofertas Aptas Verificadas</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-recommended">0</span>
        </button>
        <button onclick="setModalityFilter('virtual')" id="btn-mod-virtual"
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500 flex items-center gap-1.5">
          <span>💻 Solo 100% Remoto</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-virtual">0</span>
        </button>
        <button onclick="setModalityFilter('presencial_bq')" id="btn-mod-presencial_bq"
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500 flex items-center gap-1.5">
          <span>📍 Solo Barranquilla</span>
          <span class="bg-black/30 px-1.5 py-0.5 rounded text-[10px] font-mono" id="btn-count-bq">0</span>
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
          <span id="statTitleApta">🎯 Aptas para el Candidato</span>
          <svg class="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-white" id="stat-apta">0</div>
        <div class="text-[11px] text-cyan-400/80 mt-1" id="statSubApta">100% Virtual o Barranquilla</div>
      </div>

      <div class="glass-card rounded-xl p-4 border border-emerald-500/30 bg-emerald-950/20">
        <div class="flex items-center justify-between text-emerald-300 text-xs font-semibold mb-1">
          <span>💻 100% Virtual / Remoto</span>
          <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-400" id="stat-virtual">0</div>
        <div class="text-[11px] text-slate-400 mt-1">Desde cualquier lugar de Colombia</div>
      </div>

      <div class="glass-card rounded-xl p-4 border border-purple-500/30 bg-purple-950/20" id="statCard3">
        <div class="flex items-center justify-between text-purple-300 text-xs font-semibold mb-1">
          <span id="statTitle3">📍 Presencial en Barranquilla</span>
          <svg class="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-purple-400" id="stat-bq">0</div>
        <div class="text-[11px] text-slate-400 mt-1" id="statSub3">Ciudad de residencia</div>
      </div>

      <div class="glass-card rounded-xl p-4 border border-slate-700/60 bg-slate-900/30">
        <div class="flex items-center justify-between text-slate-300 text-xs font-semibold mb-1">
          <span>📦 Total Ofertas Extraídas</span>
          <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
        </div>
        <div class="text-2xl sm:text-3xl font-extrabold text-white" id="stat-total">0</div>
        <div class="text-[11px] text-slate-400 mt-1">ElEmpleo, LinkedIn, Computrabajo</div>
      </div>
    </div>

    <!-- FILTER BAR & REGIONAL CHIPS -->
    <div class="glass-card rounded-2xl p-5 space-y-4 no-print border border-slate-800">
      <div class="grid grid-cols-1 md:grid-cols-12 gap-3">
        <!-- SEARCH -->
        <div class="md:col-span-4 relative">
          <input type="text" id="searchInput" placeholder="Buscar por cargo, empresa, tecnología o palabra clave..." 
            oninput="applyFilters()"
            class="w-full pl-9 pr-4 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 transition">
          <svg class="w-4 h-4 text-slate-500 absolute left-3 top-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
        </div>

        <!-- CITY SELECTOR -->
        <div class="md:col-span-3">
          <select id="cityFilter" onchange="applyFilters()"
            class="w-full px-3 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs sm:text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500 transition">
            <option value="all">📍 Todas las ubicaciones</option>
            <option value="remoto_nacional">💻 100% Remoto Nacional</option>
            <option value="barranquilla">📍 Barranquilla y Atlántico</option>
            <option value="bogota">🏢 Bogotá, D.C.</option>
            <option value="antioquia">🏢 Medellín y Antioquia</option>
            <option value="valle">🏢 Cali y Valle</option>
            <option value="cundinamarca">🏢 Cundinamarca y Sabana</option>
            <option value="santander">🏢 Bucaramanga / Santander</option>
            <option value="cartagena">🏢 Cartagena y Bolívar</option>
            <option value="eje_cafetero">🏢 Eje Cafetero</option>
            <option value="otras">🏢 Otras Regiones</option>
          </select>
        </div>

        <!-- SCORE FILTER -->
        <div class="md:col-span-2">
          <select id="scoreFilter" onchange="applyFilters()"
            class="w-full px-3 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs sm:text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500 transition">
            <option value="all">⭐ Todos los scores</option>
            <option value="70">🔥 Alta Afinidad (≥ 70%)</option>
            <option value="60">⚡ Media-Alta (≥ 60%)</option>
            <option value="50">📑 Afinidad Base (≥ 50%)</option>
          </select>
        </div>

        <!-- PORTAL SELECTOR -->
        <div class="md:col-span-2">
          <select id="portalFilter" onchange="applyFilters()"
            class="w-full px-3 py-2.5 bg-slate-900/90 border border-slate-700/80 rounded-xl text-xs sm:text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-500 transition">
            <option value="all">🌐 Todos los portales</option>
            <option value="ElEmpleo">ElEmpleo</option>
            <option value="LinkedIn">LinkedIn</option>
            <option value="Computrabajo">Computrabajo</option>
            <option value="Remotive">Remotive</option>
          </select>
        </div>

        <!-- RESET BUTTON -->
        <div class="md:col-span-1">
          <button onclick="resetFilters()" title="Reiniciar filtros"
            class="w-full h-full py-2.5 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold transition flex items-center justify-center">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
          </button>
        </div>
      </div>

      <!-- INTERACTIVE CITY CHIPS -->
      <div class="flex items-center gap-2 overflow-x-auto pb-1 pt-1 text-xs no-scrollbar" id="cityChips"></div>
    </div>

    <!-- VACANCIES COUNT HEADER -->
    <div class="flex items-center justify-between text-xs text-slate-400 px-1">
      <div>
        Mostrando <span class="font-bold text-cyan-400 font-mono text-sm" id="visibleCount">0</span> ofertas disponibles
      </div>
      <div class="text-[11px] text-slate-500 hidden sm:block">
        Haz clic en <span class="text-cyan-400 font-medium">"Ver Oferta y Postular"</span> para abrir la publicación oficial
      </div>
    </div>

    <!-- VACANCIES GRID CONTAINER -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" id="vacanciesGrid"></div>

    <!-- EMPTY STATE -->
    <div id="emptyState" class="hidden text-center py-16 px-4">
      <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-2xl">
        🔍
      </div>
      <h3 class="text-lg font-bold text-white mb-1">No se encontraron vacantes con estos filtros</h3>
      <p class="text-xs text-slate-400 max-w-sm mx-auto mb-4">
        Prueba cambiando la ciudad, reduciendo el score mínimo o buscando otros términos.
      </p>
      <button onclick="resetFilters()" class="px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-600 text-white hover:bg-cyan-500 transition">
        Restablecer Filtros
      </button>
    </div>

  </main>

  <!-- FOOTER -->
  <footer class="border-t border-slate-800/80 bg-slate-950/80 mt-12 py-6 text-center text-xs text-slate-500 no-print">
    <div class="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
      <div>
        Job Hunter Engine &bull; Actualización periódica automatizada con Selenium/Requests & Pytest
      </div>
      <div class="font-mono text-[11px] text-slate-400">
        Multi-Perfil Activo &bull; Colombia &bull; 100% Remoto & Barranquilla
      </div>
    </div>
  </footer>

  <!-- DATA & LOGIC -->
  <script>
    const PROFILES_DATA = {profiles_json};
    let currentProfileId = '{initial_profile_id}';
    let INITIAL_VACANCIES = PROFILES_DATA[currentProfileId].vacancies;
    let currentModalityFilter = 'recommended';
    let currentCityFilter = 'all';

    function getStoredStatus(id) {{
      return localStorage.getItem('status_' + id) || null;
    }}

    function setStoredStatus(id, status) {{
      localStorage.setItem('status_' + id, status);
      applyFilters();
    }}

    function switchProfile(profileId) {{
      if (!PROFILES_DATA[profileId]) return;
      currentProfileId = profileId;
      INITIAL_VACANCIES = PROFILES_DATA[profileId].vacancies;

      // Update tabs styling
      const tabs = {{
        profile_1_civil_vias_sst: document.getElementById('tab-p1'),
        profile_5_tecnico_sistemas: document.getElementById('tab-p5'),
        profile_6_auxiliar_administrativo: document.getElementById('tab-p6')
      }};
      Object.entries(tabs).forEach(([id, tab]) => {{
        if (!tab) return;
        if (id === profileId) {{
          tab.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all text-white bg-cyan-600 shadow-md';
        }} else {{
          tab.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all text-slate-400 hover:text-white hover:bg-slate-800';
        }}
      }});

      // Update Profile Banner
      const p = PROFILES_DATA[profileId];
      document.getElementById('badgeProfileId').textContent = p.badge;
      document.getElementById('badgeExperience').textContent = p.experience;
      document.getElementById('badgeModality').textContent = p.modality_badge;
      document.getElementById('bannerTitle').innerHTML = p.title;
      document.getElementById('bannerDescription').innerHTML = p.description;
      document.getElementById('specText1').textContent = p.spec1;
      document.getElementById('specText2').textContent = p.spec2;

      // Update Card 3 visibility / text
      const statCard3 = document.getElementById('statCard3');
      const btnBq = document.getElementById('btn-mod-presencial_bq');
      if (p.has_barranquilla) {{
        statCard3.style.display = 'block';
        btnBq.style.display = 'inline-flex';
        document.getElementById('statTitleApta').textContent = '🎯 Aptas para la Candidata';
        document.getElementById('statSubApta').textContent = '100% Virtual o Barranquilla';
        document.getElementById('label-mod-recommended').textContent = '🎯 Aptas: 100% Virtual o Barranquilla';
      }} else {{
        statCard3.style.display = 'none';
        btnBq.style.display = 'none';
        document.getElementById('statTitleApta').textContent = '🎯 100% Remoto Verificado';
        document.getElementById('statSubApta').textContent = 'Sin exigencia presencial';
        document.getElementById('label-mod-recommended').textContent = '🎯 Solo 100% Remoto';
      }}

      // Reset filters and update
      currentModalityFilter = 'recommended';
      const searchInputElem = document.getElementById('searchInput');
      if (searchInputElem) searchInputElem.value = '';
      const cityFilterElem = document.getElementById('cityFilter');
      if (cityFilterElem) cityFilterElem.value = 'all';
      const scoreFilterElem = document.getElementById('scoreFilter');
      if (scoreFilterElem) scoreFilterElem.value = 'all';
      const portalFilterElem = document.getElementById('portalFilter');
      if (portalFilterElem) portalFilterElem.value = 'all';
      currentCityFilter = 'all';

      setModalityFilter('recommended');
      updateStats();
      renderCityChips();
      applyFilters();
    }}

    function updateStats() {{
      const aptas = INITIAL_VACANCIES.filter(v => v.es_apta).length;
      const virtual = INITIAL_VACANCIES.filter(v => v.tipo_modalidad === 'virtual').length;
      const bq = INITIAL_VACANCIES.filter(v => v.tipo_modalidad === 'presencial_bq').length;
      const total = INITIAL_VACANCIES.length;

      document.getElementById('stat-apta').textContent = aptas;
      document.getElementById('stat-virtual').textContent = virtual;
      document.getElementById('stat-bq').textContent = bq;
      document.getElementById('stat-total').textContent = total;

      document.getElementById('btn-count-recommended').textContent = aptas;
      document.getElementById('btn-count-virtual').textContent = virtual;
      document.getElementById('btn-count-bq').textContent = bq;
    }}

    function setModalityFilter(filter) {{
      currentModalityFilter = filter;
      const buttons = {{
        recommended: document.getElementById('btn-mod-recommended'),
        virtual: document.getElementById('btn-mod-virtual'),
        presencial_bq: document.getElementById('btn-mod-presencial_bq'),
        all: document.getElementById('btn-mod-all')
      }};

      Object.entries(buttons).forEach(([key, btn]) => {{
        if (!btn) return;
        if (key === filter) {{
          btn.className = 'px-3.5 py-1.5 rounded-lg text-xs font-bold border transition-all bg-gradient-to-r from-cyan-600 to-emerald-600 text-white border-cyan-400 shadow-md shadow-cyan-500/20 flex items-center gap-1.5';
        }} else {{
          btn.className = 'px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition-all bg-slate-900 text-slate-300 border-slate-700 hover:border-slate-500 flex items-center gap-1.5';
        }}
      }});

      applyFilters();
    }}

    function selectCityChip(cityId) {{
      currentCityFilter = cityId;
      document.getElementById('cityFilter').value = cityId;
      renderCityChips();
      applyFilters();
    }}

    function renderCityChips() {{
      const container = document.getElementById('cityChips');
      const counts = {{}};
      INITIAL_VACANCIES.forEach(v => {{
        counts[v.ciudad_id] = (counts[v.ciudad_id] || 0) + 1;
      }});

      const chips = [
        {{ id: 'all', name: 'Todas', count: INITIAL_VACANCIES.length }},
        {{ id: 'remoto_nacional', name: '100% Remoto Nacional', count: counts['remoto_nacional'] || 0 }},
        {{ id: 'barranquilla', name: 'Barranquilla', count: counts['barranquilla'] || 0 }},
        {{ id: 'bogota', name: 'Bogotá', count: counts['bogota'] || 0 }},
        {{ id: 'antioquia', name: 'Medellín', count: counts['antioquia'] || 0 }},
        {{ id: 'valle', name: 'Cali', count: counts['valle'] || 0 }},
      ];

      container.innerHTML = chips.map(c => {{
        const active = currentCityFilter === c.id;
        const activeClass = active 
          ? 'bg-cyan-500 text-slate-950 font-bold border-cyan-400 shadow-sm'
          : 'bg-slate-900/80 text-slate-300 border-slate-700/80 hover:bg-slate-800';
        return `
          <button onclick="selectCityChip('${{c.id}}')" 
            class="px-2.5 py-1 rounded-lg border text-xs whitespace-nowrap transition flex items-center gap-1.5 ${{activeClass}}">
            <span>${{c.name}}</span>
            <span class="text-[10px] opacity-75 font-mono">(${{c.count}})</span>
          </button>
        `;
      }}).join('');
    }}

    function renderVacancies(vacancies) {{
      const grid = document.getElementById('vacanciesGrid');
      const emptyState = document.getElementById('emptyState');
      const visibleCount = document.getElementById('visibleCount');

      visibleCount.textContent = vacancies.length;

      if (vacancies.length === 0) {{
        grid.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
      }}
      emptyState.classList.add('hidden');

      grid.innerHTML = vacancies.map(v => {{
        try {{
          const currentStatus = getStoredStatus(v.id) || v.estado || 'Nueva';

          // Tag highlights
          const isVias = v.resumen.toLowerCase().includes('vias') || v.resumen.toLowerCase().includes('vías') || v.resumen.toLowerCase().includes('pavimento');
          const isSst = v.resumen.toLowerCase().includes('sst') || v.resumen.toLowerCase().includes('seguridad');
          const isPython = v.resumen.toLowerCase().includes('python') || v.titulo.toLowerCase().includes('python');
          const isSql = v.resumen.toLowerCase().includes('sql') || v.titulo.toLowerCase().includes('sql');
          const isSupport = v.resumen.toLowerCase().includes('soporte') || v.titulo.toLowerCase().includes('help desk') || v.titulo.toLowerCase().includes('mesa de ayuda') || v.titulo.toLowerCase().includes('soporte');
          const isAuto = v.resumen.toLowerCase().includes('automatiz') || v.resumen.toLowerCase().includes('script');
          const isAdmin = v.resumen.toLowerCase().includes('administrativ') || v.titulo.toLowerCase().includes('administrativ') || v.titulo.toLowerCase().includes('asistente') || v.titulo.toLowerCase().includes('secretaria');
          const isExcel = v.resumen.toLowerCase().includes('excel') || v.titulo.toLowerCase().includes('excel') || v.resumen.toLowerCase().includes('office');
          const isFacturacion = v.resumen.toLowerCase().includes('facturaci') || v.titulo.toLowerCase().includes('facturaci') || v.resumen.toLowerCase().includes('contable') || v.titulo.toLowerCase().includes('contable');
          const isDigitacion = v.resumen.toLowerCase().includes('digitaci') || v.titulo.toLowerCase().includes('digitad') || v.titulo.toLowerCase().includes('data entry');

          let scoreBadgeClass = 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40';
          if (v.score >= 70) scoreBadgeClass = 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
          else if (v.score < 55) scoreBadgeClass = 'bg-amber-500/20 text-amber-300 border-amber-500/40';

          return `
          <div class="glass-card rounded-2xl p-5 border border-slate-800/90 flex flex-col justify-between hover:border-cyan-500/50 transition-all duration-200 group">
            <div class="space-y-3">
              <!-- TOP METADATA ROW -->
              <div class="flex items-start justify-between gap-2">
                <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold border ${{scoreBadgeClass}}">
                  ★ ${{v.score_str}} Afinidad
                </span>
                <div class="flex items-center gap-1.5">
                  <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-900 border border-slate-800 text-slate-400">
                    ${{v.portal}}
                  </span>
                  <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-900/60 text-slate-400 border border-slate-800">
                    ${{v.ciudad_badge}}
                  </span>
                </div>
              </div>

              <!-- TITLE & COMPANY -->
              <div>
                <h3 class="text-base font-bold text-white group-hover:text-cyan-300 transition-colors line-clamp-2">
                  ${{v.titulo}}
                </h3>
                <div class="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                  <span class="text-slate-300 font-medium">${{v.empresa}}</span>
                  ${{v.salario ? `<span class="text-slate-500">&bull;</span><span class="text-emerald-400 font-mono text-[11px]">${{v.salario}}</span>` : ''}}
                </div>
              </div>

              <!-- MODALITY BADGE -->
              <div class="pt-1">
                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold border ${{v.badge_class}}">
                  <span>${{v.mod_icon || '💻'}}</span>
                  <span>${{v.modalidad}}</span>
                </span>
              </div>

              <!-- SUMMARY & OBSERVATIONS -->
              <div class="bg-slate-900/60 rounded-lg p-3 text-xs text-slate-300 leading-relaxed border border-slate-800 space-y-2">
                <p>${{v.resumen}}</p>
                
                <div class="flex flex-wrap gap-1 pt-1">
                  ${{isVias ? '<span class="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-400 text-[10px] font-semibold border border-cyan-800/40">Infraestructura Vial</span>' : ''}}
                  ${{isSst ? '<span class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 text-[10px] font-semibold border border-emerald-800/40">SST / HSEQ</span>' : ''}}
                  ${{isSupport ? '<span class="px-1.5 py-0.5 rounded bg-blue-950/60 text-blue-400 text-[10px] font-semibold border border-blue-800/40">Soporte TI / Help Desk</span>' : ''}}
                  ${{isPython ? '<span class="px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-400 text-[10px] font-semibold border border-amber-800/40">Python / Scripts</span>' : ''}}
                  ${{isSql ? '<span class="px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-400 text-[10px] font-semibold border border-purple-800/40">SQL / Bases Datos</span>' : ''}}
                  ${{isAuto ? '<span class="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-400 text-[10px] font-semibold border border-emerald-800/40">Automatización</span>' : ''}}
                  ${{isAdmin ? '<span class="px-1.5 py-0.5 rounded bg-sky-950/60 text-sky-400 text-[10px] font-semibold border border-sky-800/40">Gestión Administrativa</span>' : ''}}
                  ${{isExcel ? '<span class="px-1.5 py-0.5 rounded bg-teal-950/60 text-teal-400 text-[10px] font-semibold border border-teal-800/40">Excel / Office 365</span>' : ''}}
                  ${{isFacturacion ? '<span class="px-1.5 py-0.5 rounded bg-indigo-950/60 text-indigo-400 text-[10px] font-semibold border border-indigo-800/40">Facturación & Contabilidad</span>' : ''}}
                  ${{isDigitacion ? '<span class="px-1.5 py-0.5 rounded bg-violet-950/60 text-violet-400 text-[10px] font-semibold border border-violet-800/40">Digitación & Data Entry</span>' : ''}}
                </div>
              </div>
            </div>

            <!-- FOOTER / ACTIONS -->
            <div class="pt-4 mt-4 border-t border-slate-800/80 space-y-3">
              <div class="flex items-center justify-between gap-2">
                <div class="text-[11px] text-slate-400 font-medium">Estado:</div>
                <select onchange="setStoredStatus('${{v.id}}', this.value)" 
                  class="bg-slate-900 border border-slate-700 text-xs rounded-md px-2 py-1 text-slate-200 focus:ring-1 focus:ring-cyan-500">
                  <option value="Nueva" ${{currentStatus === 'Nueva' ? 'selected' : ''}}>Nueva</option>
                  <option value="Por revisar" ${{currentStatus === 'Por revisar' ? 'selected' : ''}}>Por revisar</option>
                  <option value="Postulado" ${{currentStatus === 'Postulado' ? 'selected' : ''}}>Postulado</option>
                  <option value="En proceso" ${{currentStatus === 'En proceso' ? 'selected' : ''}}>En proceso</option>
                  <option value="Descartado" ${{currentStatus === 'Descartado' ? 'selected' : ''}}>Descartado</option>
                </select>
              </div>

              <div class="flex items-center gap-2">
                <a href="${{v.url}}" target="_blank" rel="noopener noreferrer" 
                  class="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors shadow-sm">
                  <span>Ver Oferta y Postular</span>
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                </a>
                <button onclick="copyJobShare('${{v.id}}')" 
                  title="Copiar enlace para compartir" 
                  class="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 transition">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"></path></svg>
                </button>
              </div>
            </div>
          </div>
          `;
        }} catch(cardErr) {{
          console.error("Error renderizando vacante:", cardErr, v);
          return '';
        }}
      }}).join('');
    }}

    function applyFilters() {{
      const query = document.getElementById('searchInput').value.toLowerCase().trim();
      const cityVal = document.getElementById('cityFilter').value;
      const scoreVal = document.getElementById('scoreFilter').value;
      const portalVal = document.getElementById('portalFilter').value;

      const filtered = INITIAL_VACANCIES.filter(v => {{
        if (currentModalityFilter === 'recommended' && !v.es_apta) return false;
        if (currentModalityFilter === 'virtual' && v.tipo_modalidad !== 'virtual') return false;
        if (currentModalityFilter === 'presencial_bq' && v.tipo_modalidad !== 'presencial_bq') return false;

        if (query) {{
          const matchTitle = v.titulo.toLowerCase().includes(query);
          const matchCompany = v.empresa.toLowerCase().includes(query);
          const matchDesc = v.resumen.toLowerCase().includes(query);
          const matchCity = v.ciudad_nombre.toLowerCase().includes(query);
          if (!matchTitle && !matchCompany && !matchDesc && !matchCity) return false;
        }}

        if (cityVal !== 'all' && v.ciudad_id !== cityVal) return false;

        if (scoreVal !== 'all') {{
          const minScore = parseFloat(scoreVal);
          if (v.score < minScore) return false;
        }}

        if (portalVal !== 'all' && v.portal !== portalVal) return false;

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

    function copyJobShare(vacancyId) {{
      const v = INITIAL_VACANCIES.find(x => x.id === vacancyId);
      if (!v) return;
      const text = `🎯 *Oportunidad Laboral*\\n💼 Cargo: ${{v.titulo}}\\n🏢 Empresa: ${{v.empresa}}\\n🔗 Postular aquí: ${{v.url}}`;
      navigator.clipboard.writeText(text).then(() => {{
        alert("Enlace directo copiado al portapapeles. ¡Listo para compartir!");
      }}).catch(() => {{
        window.prompt("Copia este texto:", text);
      }});
    }}

    function shareWhatsApp() {{
      const aptaCount = INITIAL_VACANCIES.filter(v => v.es_apta).length;
      const p = PROFILES_DATA[currentProfileId];
      const text = encodeURIComponent(`Hola, te comparto estas vacantes verificadas para ${{p.title}}. Hay ${{aptaCount}} ofertas aptas y verificadas.`);
      window.open(`https://api.whatsapp.com/send?text=${{text}}`, '_blank');
    }}

    document.addEventListener('DOMContentLoaded', () => {{
      // Check URL hash or param
      const hash = window.location.hash.toLowerCase();
      if (hash.includes('admin') || hash.includes('auxiliar') || hash.includes('profile_6')) {{
        switchProfile('profile_6_auxiliar_administrativo');
      }} else if (hash.includes('sistemas') || hash.includes('tecnico') || hash.includes('profile_5')) {{
        switchProfile('profile_5_tecnico_sistemas');
      }} else {{
        switchProfile('{initial_profile_id}');
      }}
    }});
  </script>
</body>
</html>
"""


def update_dashboard(base_dir: Optional[Path] = None) -> List[Path]:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent

    csv_p1 = base_dir / "output" / "profile_1_civil_vias_sst_tracker.csv"
    csv_p5 = base_dir / "output" / "profile_5_tecnico_sistemas_tracker.csv"
    csv_p6 = base_dir / "output" / "profile_6_auxiliar_administrativo_tracker.csv"

    vacancies_p1 = load_vacancies_from_csv(csv_p1, profile_id="profile_1_civil_vias_sst")
    vacancies_p5 = load_vacancies_from_csv(csv_p5, profile_id="profile_5_tecnico_sistemas")
    vacancies_p6 = load_vacancies_from_csv(csv_p6, profile_id="profile_6_auxiliar_administrativo")

    print(f"Cargadas {len(vacancies_p1)} vacantes para Perfil 1 (Civil), {len(vacancies_p5)} para Perfil 5 (Sistemas) y {len(vacancies_p6)} para Perfil 6 (Administrativo)")

    profiles_data = {
        "profile_1_civil_vias_sst": {
            "id": "profile_1_civil_vias_sst",
            "title": "Ingeniera Civil Senior &bull; Especialista en Vías & SST",
            "badge": "Perfil #1: Ing. Civil (Vías & SST)",
            "experience": "15+ Años Exp. Total",
            "modality_badge": "💻 100% Virtual o 📍 Barranquilla",
            "description": "Filtro de modalidad estricto: Se priorizan vacantes <strong>100% Virtuales / Teletrabajo</strong> en Colombia o de modalidad <strong>Presencial exclusivamente en Barranquilla / Atlántico</strong> (residencia de la candidata).",
            "spec1": "Infraestructura Vial (5+ años)",
            "spec2": "Seguridad & Salud SST (5+ años)",
            "has_barranquilla": True,
            "vacancies": vacancies_p1,
        },
        "profile_5_tecnico_sistemas": {
            "id": "profile_5_tecnico_sistemas",
            "title": "Técnico en Sistemas y Soporte TI Remoto &bull; Con Programación",
            "badge": "Perfil #2: Técnico Sistemas (TI & Prog.)",
            "experience": "1+ Años (Técnico / Junior / Mid)",
            "modality_badge": "💻 100% Remoto Nacional / LATAM",
            "description": "Filtro de modalidad estricto: Vacantes <strong>100% Remotas / Teletrabajo</strong> para Técnico en Sistemas con capacidades técnicas en soporte TI (helpdesk, redes, hardware, mesa de ayuda) y programación/automatización (Python, SQL, scripts).",
            "spec1": "Soporte TI, Help Desk & Redes",
            "spec2": "Programación Python, SQL & Scripts",
            "has_barranquilla": False,
            "vacancies": vacancies_p5,
        },
        "profile_6_auxiliar_administrativo": {
            "id": "profile_6_auxiliar_administrativo",
            "title": "Auxiliar Administrativo &bull; Asistente Virtual 100% Remoto",
            "badge": "Perfil #3: Auxiliar Administrativo",
            "experience": "1+ Años (Auxiliar / Asistente)",
            "modality_badge": "💻 100% Virtual / Teletrabajo Nacional",
            "description": "Filtro de modalidad estricto: Vacantes <strong>100% Remotas / Teletrabajo</strong> para Auxiliar Administrativo, Asistente Virtual, digitación, facturación y soporte operativo con herramientas ofimáticas (Excel, Office 365, Google Workspace, Siigo/SAP).",
            "spec1": "Gestión Documental & Archivo",
            "spec2": "Excel, Ofimática & Facturación",
            "has_barranquilla": False,
            "vacancies": vacancies_p6,
        },
    }

    # 1. Main Unified index.html & dashboard.html (defaulting to profile 1 with tab switch)
    html_unified = build_dashboard_html(profiles_data, initial_profile_id="profile_1_civil_vias_sst")

    # 2. Dedicated systems dashboard (defaulting to profile 5)
    html_sistemas = build_dashboard_html(profiles_data, initial_profile_id="profile_5_tecnico_sistemas")

    # 3. Dedicated administrative dashboard (defaulting to profile 6)
    html_admin = build_dashboard_html(profiles_data, initial_profile_id="profile_6_auxiliar_administrativo")

    out_paths = [
        base_dir / "index.html",
        base_dir / "dashboard.html",
        base_dir / "dashboard_tecnico_sistemas.html",
        base_dir / "dashboard_auxiliar_administrativo.html",
        base_dir / "output" / "index.html",
        base_dir / "output" / "dashboard.html",
        base_dir / "output" / "dashboard_tecnico_sistemas.html",
        base_dir / "output" / "dashboard_auxiliar_administrativo.html",
        base_dir / "SUBIR_A_NETLIFY" / "index.html",
        base_dir / "SUBIR_A_NETLIFY" / "dashboard.html",
        base_dir / "SUBIR_A_NETLIFY" / "dashboard_tecnico_sistemas.html",
        base_dir / "SUBIR_A_NETLIFY" / "dashboard_auxiliar_administrativo.html",
    ]

    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        if "administrativo" in p.name:
            content = html_admin
        elif "sistemas" in p.name:
            content = html_sistemas
        else:
            content = html_unified

        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Dashboard actualizado con éxito en: {p}")

    # Sync tracker files to SUBIR_A_NETLIFY/output
    netlify_output = base_dir / "SUBIR_A_NETLIFY" / "output"
    netlify_output.mkdir(parents=True, exist_ok=True)
    for ext in ("csv", "xlsx"):
        for pid in ("profile_1_civil_vias_sst", "profile_5_tecnico_sistemas", "profile_6_auxiliar_administrativo"):
            src = base_dir / "output" / f"{pid}_tracker.{ext}"
            if src.exists():
                shutil.copy2(src, netlify_output / src.name)

    return out_paths


def main():
    base_dir = Path(__file__).resolve().parent
    update_dashboard(base_dir)


if __name__ == "__main__":
    main()
