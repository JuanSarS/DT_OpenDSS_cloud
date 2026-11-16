# Evidencias reproducibles

Toda prueba importante debe escribir archivos. No usar capturas aisladas como única evidencia.

```text
docs/evidence/
├── regression/          # suite local completa
├── deployments/         # create/delete CloudFormation, ECS, CloudFront
├── deliverable_1/       # multi-contexto 2/4/8/16
├── deliverable_2/       # MVP, Locust, CPU/memoria, autoscaling
├── deliverable_3/       # seguridad, overload, failover
└── EVIDENCE_INDEX.md    # índice generado
```

Regla: cada ejecución crea una carpeta UTC con archivos `config/manifest`, resultados crudos y `REPORT.md` o resumen equivalente.

Genera el índice:

```powershell
python .\scripts\build_evidence_index.py
```
