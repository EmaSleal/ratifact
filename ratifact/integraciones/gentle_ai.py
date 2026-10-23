"""gentle-ai (alcance proyecto): orquestador de agentes; señal `.atl/`.

La tarea de ratifact es la ruta delegated-direct de gentle-ai y su documento de funcionalidad ODD (ADR-033, ADR-034):
nunca SDD. RDD, si está activo, revisa el cambio antes de in_review; ratifact no lo activa ni lo bloquea."""
from ratifact.integraciones.base import Integracion, carpeta_existe

INTEGRACION = Integracion(
    nombre="gentle-ai",
    alcance="project",
    detectar=carpeta_existe(".atl"),
    prefijo="gentle-ai",
    rol="orchestration: delegated workers for the task",
    limite="never decisions or task status; the spec is the contract",
    guia={
        "execute": "if you have the `gentle-ai` orchestrator, this task is its delegated-direct route (never SDD; no "
                   "SDD artifacts): one explore worker if understanding it takes 4+ files, one writer for 2+ "
                   "non-trivial files; this ratifact task is the feature document, create no other ODD document; "
                   "otherwise implement directly.",
        "verify": "if you have the `gentle-ai` orchestrator, verify in a clean worker; if RDD is on, review the "
                  "finished change before update_task(in_review) and summarize its receipt in the result (depth, "
                  "findings, corrections); if RDD is off, start no review; otherwise verify directly.",
    },
)
