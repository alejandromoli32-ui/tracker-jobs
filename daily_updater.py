"""
Script de Actualización Diaria Automatizada (Daily Job Hunter & Dashboard Updater).

Ejecuta el ciclo completo de búsqueda periódica para el perfil activo:
1. Extrae ofertas laborales recientes en portales de Colombia y modalidad remota.
2. Evalúa cada vacante con afinidad técnica multidimensional (Vías, SST, Ingeniería Civil).
3. Aplica filtro estricto de modalidad: 100% Virtual / Teletrabajo nacional + Presencial en Barranquilla.
4. Sincroniza incrementalmente con CSV y Excel (preservando estados 'Postulado', 'Descartado' y notas).
5. Regenera el dashboard interactivo (dashboard.html e index.html) listo para producción y Netlify.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from job_hunter.client import HttpClient
from job_hunter.config import load_profile
from job_hunter.matcher import AffinityScorer
from job_hunter.models import NormalizedVacancy, TrackerEntry
from job_hunter.scrapers.engine import JobAggregationEngine
from job_hunter.storage.incremental import IncrementalTracker
from generate_dashboard import update_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_updater")


def run_daily_update(
    profile_id: str = "profile_1_civil_vias_sst",
    max_pages: int = 2,
    offline: bool = False,
    base_dir: Path | None = None,
) -> dict:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent

    start_time = datetime.now()
    logger.info("=" * 70)
    logger.info(f"INICIANDO ACTUALIZACIÓN DIARIA: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Perfil objetivo: {profile_id} | Modo Offline: {offline}")
    logger.info("=" * 70)

    # 1. Cargar perfil
    profile = load_profile(profile_id, profiles_dir=base_dir / "profiles")
    logger.info(f"Perfil cargado: '{profile.name}' (Mínimo experiencia: {profile.min_total_experience_years} años)")

    # 2. Inicializar motor de scraping y scorer
    client = HttpClient()
    engine = JobAggregationEngine(client=client)
    scorer = AffinityScorer()

    queries = profile.search_queries or [
        "Ingeniero Civil Remoto",
        "Especialista Vias",
        "SST Remoto Colombia",
        "Ingeniero Civil Barranquilla",
        "SST Barranquilla",
    ]

    logger.info(f"Consultando {len(queries)} términos de búsqueda en portales...")
    scraped_vacancies: List[NormalizedVacancy] = engine.run(
        queries=queries,
        max_pages=max_pages,
        offline=offline,
    )
    logger.info(f"Total vacantes extraídas y deduplicadas del lote: {len(scraped_vacancies)}")

    # 3. Evaluar afinidad técnica y filtrar por umbral
    min_score = profile.scoring_weights.min_score_to_save if profile.scoring_weights else 50.0
    fresh_entries: List[TrackerEntry] = []

    for vac in scraped_vacancies:
        score_breakdown = scorer.evaluate(vac, profile)
        if score_breakdown.total_score >= min_score and not score_breakdown.is_disqualified:
            entry = TrackerEntry(
                id=vac.id,
                title=vac.title,
                company=vac.company,
                direct_url=vac.direct_url,
                full_description=vac.full_description,
                publication_date=vac.publication_date,
                location=vac.location,
                modality=vac.modality,
                salary_range=vac.salary_range,
                source_portal=vac.source_portal,
                raw_snippet=vac.raw_snippet,
                score=score_breakdown.total_score,
                score_percentage=f"{score_breakdown.total_score:.1f}%",
                explanatory_summary=score_breakdown.explanatory_summary,
                estado="Nueva",
                fecha_deteccion=datetime.now().strftime("%Y-%m-%d %H:%M"),
                notas_usuario="",
                perfil_id=profile.id,
            )
            fresh_entries.append(entry)

    logger.info(f"Vacantes calificadas con afinidad >= {min_score}%: {len(fresh_entries)}")

    # 4. Sincronización incremental con almacenamiento
    out_dir = base_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_tracker_path = out_dir / f"{profile.id}_tracker.csv"
    xlsx_tracker_path = out_dir / f"{profile.id}_tracker.xlsx"

    logger.info(f"Sincronizando incrementalmente con {csv_tracker_path.name}...")
    IncrementalTracker.sync(csv_tracker_path, fresh_entries)
    IncrementalTracker.sync(xlsx_tracker_path, fresh_entries)

    # 5. Regenerar Dashboard HTML e index.html
    logger.info("Regenerando dashboard interactivo e index.html para Netlify...")
    generated_html_files = update_dashboard(base_dir)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    summary = {
        "timestamp": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": round(duration, 2),
        "total_scraped_batch": len(scraped_vacancies),
        "qualifying_batch": len(fresh_entries),
        "csv_path": str(csv_tracker_path),
        "xlsx_path": str(xlsx_tracker_path),
        "html_files": [str(p) for p in generated_html_files],
    }

    logger.info("=" * 70)
    logger.info(f"ACTUALIZACIÓN DIARIA COMPLETADA CON ÉXITO EN {summary['duration_seconds']}s")
    logger.info(f"Dashboard listo en: {base_dir / 'index.html'}")
    logger.info("=" * 70)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Job Hunter Autobuscador Diario")
    parser.add_argument("--profile", default="profile_1_civil_vias_sst", help="ID del perfil a buscar")
    parser.add_argument("--pages", type=int, default=2, help="Páginas por portal a consultar")
    parser.add_argument("--offline", action="store_true", help="Ejecutar en modo offline de prueba")
    args = parser.parse_args()

    run_daily_update(
        profile_id=args.profile,
        max_pages=args.pages,
        offline=args.offline,
    )


if __name__ == "__main__":
    main()
