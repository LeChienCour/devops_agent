# FinOps Agent: Plan de Construcción

> **Propósito del documento:** Este es el plan maestro para construir un agente autónomo de FinOps sobre AWS, destinado a ser presentado en un AWS Community Day 2026. El agente detecta desperdicio de costos en cuentas AWS usando Amazon Bedrock, MCP servers y LangGraph. Este documento está escrito para que Claude Code pueda ejecutarlo de forma autónoma, tomando decisiones técnicas dentro de los lineamientos aquí definidos.

---

## 1. Contexto y Objetivos

### 1.1 Objetivo de negocio
Construir un agente demostrable que:
- Detecte automáticamente fugas de costos en una cuenta AWS (NAT Gateways idle, EBS huérfanos, Lambda oversized, etc.)
- Razone sobre los datos (no solo reglas) usando un LLM via Amazon Bedrock
- Proponga remediaciones accionables con estimación de ahorro
- Sirva como material de demo en vivo para una charla de 45 minutos
- Funcione como comparativo frente al AWS DevOps Agent oficial

### 1.2 Objetivo técnico
Un sistema serverless, low-cost (<$10 USD/mes en operación de demo), reproducible desde cero con un `terraform apply` + `make deploy`, que sirva tanto como:
- Producto funcional que ahorra dinero real
- Material pedagógico con código limpio y comentado
- Repositorio público de referencia para la comunidad

### 1.3 Restricciones
- **Costo:** lab completo debe correr en ~$5-10 USD/mes
- **Región:** `us-east-1` (Bedrock tiene los modelos más recientes primero aquí)
- **Lenguaje principal:** Python 3.12+
- **No vendor lock-in innecesario:** estructura modular que permita cambiar Bedrock por otro provider
- **Seguridad primero:** el agente nunca tiene permisos de escritura al inicio (solo lectura + sugerencias)

---

## 2. Arquitectura

### 2.1 Diagrama conceptual

```
┌─────────────────────────────────────────────────────────────┐
│                     TRIGGERS                                │
│  EventBridge (cron semanal)  │  API Gateway (on-demand)     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              AGENT RUNTIME (Lambda)                         │
│                                                             │
│   ┌──────────────────────────────────────────────────┐     │
│   │          LangGraph StateGraph                    │     │
│   │                                                  │     │
│   │   [plan] → [gather] → [analyze] → [recommend]    │     │
│   │      ↑                                  │        │     │
│   │      └──────── loop si needs_more_data ─┘        │     │
│   └──────────────────────────────────────────────────┘     │
│                      │                                      │
│                      ▼                                      │
│   ┌──────────────────────────────────────────────────┐     │
│   │    Amazon Bedrock (Claude Sonnet 4.5)            │     │
│   └──────────────────────────────────────────────────┘     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼ (MCP protocol)
┌─────────────────────────────────────────────────────────────┐
│                   MCP SERVERS                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │Cost Explorer│ │ CloudWatch  │ │Trusted Adv. │            │
│  └─────────────┘ └─────────────┘ └─────────────┘            │
│  ┌─────────────┐ ┌─────────────┐                            │
│  │   GitHub    │ │EC2/VPC/EBS  │                            │
│  │ (read-only) │ │  (boto3)    │                            │
│  └─────────────┘ └─────────────┘                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      OUTPUT                                 │
│  DynamoDB (histórico)  │  SNS → Slack  │  S3 (reportes)     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Decisiones arquitectónicas clave

| Decisión               | Elegido             | Rechazado                | Justificación                                                                            |
| ---------------------- | ------------------- | ------------------------ | ---------------------------------------------------------------------------------------- |
| Runtime                | Lambda              | ECS/EKS                  | Serverless alinea con el tema "low cost"; arranque rápido para demos                     |
| Orquestación           | LangGraph           | LangChain agents, CrewAI | Diego ya lo conoce del Office Agent; StateGraph permite human-in-the-loop explícito      |
| Modelo                 | Claude Sonnet 4.5   | Nova Pro, GPT-4o         | Mejor en tool use + razonamiento; disponible en Bedrock us-east-1                        |
| Comunicación con tools | MCP                 | Function calling directo | MCP es el estándar emergente en 2026; da puntos en la charla; permite reutilizar servers |
| IaC                    | Terraform           | CDK, SAM                 | Terraform es más común en comunidad DevOps hispanoparlante; audiencia lo va a entender   |
| Persistencia           | DynamoDB            | RDS, S3 solo             | Serverless, free tier generoso, queries simples por timestamp                            |
| Notificaciones         | SNS → Slack webhook | EventBridge → Slack MCP  | SNS es más simple y cubre el caso de demo                                                |

### 2.3 Flujo de una investigación

1. **Trigger:** EventBridge dispara Lambda (o llamada manual vía API Gateway)
2. **Plan:** El nodo `plan` en LangGraph pide al LLM generar un plan de investigación basado en un prompt que lista las herramientas disponibles
3. **Gather:** El nodo `gather` ejecuta las herramientas MCP que el plan indicó (Cost Explorer, CloudWatch, etc.)
4. **Analyze:** El nodo `analyze` pasa los datos crudos al LLM para identificar patrones de desperdicio
5. **Decision:** Si el LLM determina que necesita más datos, regresa a `gather`. Si no, pasa a `recommend`.
6. **Recommend:** Genera sugerencias estructuradas (JSON) con: problema, evidencia, impacto estimado en $, acción recomendada, comando/IaC sugerido
7. **Persist:** Guarda en DynamoDB
8. **Notify:** Publica a SNS topic que webhook-ea a Slack

---

## 3. Estructura del Repositorio

```
finops-agent/
├── README.md                      # Doc principal + badges + quickstart
├── PLAN.md                        # Este archivo (fuente de verdad para Claude Code)
├── CLAUDE.md                      # Instrucciones específicas para Claude Code
├── LICENSE                        # MIT
├── .gitignore
├── .env.example                   # Template de variables de entorno
├── Makefile                       # Targets: install, test, deploy, destroy, demo
├── pyproject.toml                 # Config de Python (uv o poetry)
├── requirements.txt               # Deps pinned
├── requirements-dev.txt           # Deps de dev/test
│
├── docs/
│   ├── ARCHITECTURE.md            # Diagrama + decisiones (versión extendida)
│   ├── SETUP.md                   # Paso a paso desde cero
│   ├── DEMO_SCRIPT.md             # Guion de la demo en vivo
│   ├── COMPARISON.md              # DIY vs AWS DevOps Agent (tabla + análisis)
│   └── images/                    # Diagramas exportados
│
├── infra/                         # Todo Terraform
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── versions.tf
│   ├── backend.tf                 # S3 backend (opcional, comentado)
│   └── modules/
│       ├── agent_lambda/          # Lambda del agente + IAM
│       ├── eventbridge/           # Schedule + reglas
│       ├── storage/               # DynamoDB + S3
│       ├── notifications/         # SNS + subscriptions
│       └── seed_leaks/            # Recursos "trampa" para demo (ver §6)
│
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── handler.py             # Lambda entrypoint
│   │   ├── graph.py               # LangGraph StateGraph
│   │   ├── state.py               # TypedDict del estado
│   │   ├── nodes/
│   │   │   ├── plan.py
│   │   │   ├── gather.py
│   │   │   ├── analyze.py
│   │   │   └── recommend.py
│   │   ├── prompts/
│   │   │   ├── system.md          # System prompt versionado
│   │   │   ├── plan.md
│   │   │   ├── analyze.md
│   │   │   └── recommend.md
│   │   └── models/
│   │       ├── finding.py         # Pydantic: Finding, Recommendation
│   │       └── investigation.py
│   │
│   ├── mcp_servers/
│   │   ├── cost_explorer/         # MCP server custom
│   │   │   ├── server.py
│   │   │   └── tools.py
│   │   ├── cloudwatch/
│   │   ├── trusted_advisor/
│   │   ├── ec2_inventory/         # EBS, NAT GW, EIPs, snapshots
│   │   └── github_readonly/
│   │
│   ├── common/
│   │   ├── bedrock_client.py      # Wrapper con retry + logging
│   │   ├── aws_clients.py         # Factory de boto3 clients
│   │   ├── logger.py              # structlog config
│   │   └── config.py              # Pydantic Settings
│   │
│   └── notifications/
│       ├── slack.py
│       └── dynamodb_writer.py
│
├── tests/
│   ├── unit/
│   │   ├── test_graph.py
│   │   ├── test_nodes.py
│   │   └── test_mcp_tools.py
│   ├── integration/
│   │   ├── test_bedrock_integration.py
│   │   └── test_end_to_end.py
│   └── fixtures/
│       ├── cost_explorer_response.json
│       └── cloudwatch_response.json
│
├── scripts/
│   ├── seed_demo_leaks.sh         # Crea recursos "trampa" para demo
│   ├── cleanup_demo_leaks.sh      # Los limpia después
│   ├── run_local.py               # Corre el agente en local (sin Lambda)
│   └── generate_report.py         # Exporta findings a PDF/MD
│
└── .github/
    └── workflows/
        ├── ci.yml                 # Tests + lint en PR
        └── deploy.yml             # Deploy opcional a una cuenta de demo
```

---

## 4. Stack Técnico Detallado

### 4.1 Dependencias Python principales

```
# Agente
langgraph>=0.2.0
langchain-aws>=0.2.0           # Integración Bedrock
boto3>=1.35.0
pydantic>=2.0
pydantic-settings>=2.0

# MCP
mcp>=1.0.0                     # SDK oficial de MCP

# Observabilidad
structlog>=24.0
aws-lambda-powertools>=3.0     # Logging, tracing, metrics

# Dev
pytest>=8.0
pytest-asyncio
pytest-mock
moto>=5.0                      # Mock de AWS
ruff                           # Linter + formatter
mypy
```

### 4.2 Versiones

- **Python:** 3.12 (soportado en Lambda)
- **Terraform:** >= 1.6
- **Modelo Bedrock:** `anthropic.claude-sonnet-4-5-20250929-v1:0` (Claude Code debe verificar el model ID vigente)
- **Node.js:** 20+ (solo si se usa un MCP server third-party que lo requiera)

### 4.3 Variables de entorno

```bash
# .env.example
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-5-20250929-v1:0
DYNAMODB_TABLE_NAME=finops-agent-findings
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:xxx:finops-alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
LOG_LEVEL=INFO
COST_THRESHOLD_USD=5.0          # Ignorar findings de menos de $5/mes
GITHUB_TOKEN=                   # Opcional, para correlacionar con IaC
INVESTIGATION_TIMEOUT_SEC=180
```

---

## 5. Plan de Implementación por Fases

> Cada fase es un PR separable. Claude Code debe completar una fase, abrir PR, y esperar feedback antes de la siguiente. Cada fase tiene criterios de aceptación verificables.

### Fase 0: Setup del repositorio (Día 1)

**Tareas:**
- Crear estructura de directorios completa
- Configurar `pyproject.toml` con ruff + mypy + pytest
- Crear `Makefile` con targets básicos
- Escribir `README.md` inicial con badges, descripción y quickstart placeholder
- Configurar `.gitignore` (Python + Terraform + IDE)
- Crear `.env.example`
- Setup de GitHub Actions para CI (lint + test, sin deploy)
- Crear `CLAUDE.md` con convenciones del proyecto

**Criterios de aceptación:**
- `make install` funciona
- `make lint` pasa (con código vacío)
- `make test` corre (aunque no haya tests aún)
- CI verde en un PR trivial

### Fase 1: Infraestructura base con Terraform (Día 2-3)

**Tareas:**
- Módulo `storage/`: DynamoDB con schema `{investigation_id, timestamp, finding_type, status, data}`
- Módulo `notifications/`: SNS topic + Slack subscription
- Módulo `agent_lambda/`: Lambda function + IAM role con permisos de SOLO LECTURA para Cost Explorer, CloudWatch, EC2, Trusted Advisor
- Módulo `eventbridge/`: Schedule semanal + regla on-demand
- Variables parametrizadas (environment, region, etc.)
- Outputs útiles (ARNs, nombres de recursos)

**Criterios de aceptación:**
- `terraform plan` limpio sin warnings
- `terraform apply` crea todo en <3 minutos
- IAM policy pasa un check de `iam-policy-validator` (sin wildcards innecesarios)
- `terraform destroy` limpia todo sin dejar recursos huérfanos
- Estimación de costo con `infracost` < $3/mes

### Fase 2: Agente mínimo viable (Día 4-6)

**Tareas:**
- Implementar `graph.py` con StateGraph de 4 nodos (plan, gather, analyze, recommend)
- Nodo `plan`: prompt que genera plan estructurado (JSON) con herramientas a invocar
- Nodo `gather`: ejecuta **una sola** herramienta inicialmente (Cost Explorer top services)
- Nodo `analyze`: manda datos al LLM y pide identificar anomalías
- Nodo `recommend`: genera JSON estructurado con findings (modelo Pydantic)
- Handler de Lambda que recibe evento, corre el grafo, retorna resultado
- Prompts en archivos `.md` separados, cargados al inicio
- Logging estructurado con `structlog`

**Criterios de aceptación:**
- Correr `python scripts/run_local.py` genera al menos un finding
- El finding es JSON válido que matchea el schema Pydantic
- Bedrock se invoca correctamente (verificable en CloudWatch)
- Tests unitarios de los 4 nodos (mockeando Bedrock con fixtures)
- Cobertura de tests > 70% en `src/agent/`

### Fase 3: MCP Servers (Día 7-9)

**Tareas:**
- MCP server `cost_explorer/`: herramientas `get_cost_by_service`, `get_cost_by_tag`, `get_forecast`, `get_anomalies`
- MCP server `cloudwatch/`: `get_metric_statistics`, `get_insights_query`, `list_alarms`
- MCP server `ec2_inventory/`: `list_unused_ebs_volumes`, `list_idle_nat_gateways`, `list_unattached_eips`, `list_old_snapshots`
- MCP server `trusted_advisor/`: `list_cost_optimization_checks`
- Integrar el agente con los MCP servers vía el SDK oficial
- Documentar cada tool con descripción clara (el LLM la lee)

**Criterios de aceptación:**
- Cada MCP server se puede probar standalone con `mcp-cli`
- Tools tienen schemas JSON válidos
- Tests de integración con `moto` para los servers que usan boto3
- El agente puede invocar cualquier tool y recibir respuesta estructurada

### Fase 4: Detección de fugas reales (Día 10-12)

**Tareas:**
- Implementar lógica de detección para los 8 escenarios clave:
  1. **NAT Gateway idle**: `BytesOutToDestination` < 1MB en 7 días
  2. **EBS volumes unattached**: estado `available` > 30 días
  3. **EBS gp2 → gp3**: todos los gp2 (oportunidad universal)
  4. **Elastic IPs no asociadas**: cobran $3.60/mes cada una
  5. **Snapshots viejos**: > 90 días sin volumen asociado
  6. **Lambda oversized**: `max_memory_used / memory_allocated` < 40% en 30 días
  7. **CloudWatch Log Groups sin retention**: storage creciendo indefinido
  8. **Instancias EC2 stopped viejas**: > 30 días, cobran por EBS asociado
- Cada detección genera un `Finding` con: severidad, $ impacto mensual, comando de remediation, confianza (0-1)
- El LLM valida y contextualiza cada finding (no solo regla dura)

**Criterios de aceptación:**
- Demo en cuenta real detecta al menos 3 tipos de fugas
- Los montos estimados son correctos (validado manualmente vs Cost Explorer)
- Findings se persisten en DynamoDB con schema correcto
- Falsos positivos < 20% en data real

### Fase 5: Notificaciones y UX (Día 13-14)

**Tareas:**
- Formato de mensaje Slack con Block Kit (no solo texto plano)
- Agrupación inteligente de findings (por servicio, por severidad)
- Resumen ejecutivo al inicio: "$X de ahorro potencial detectado esta semana"
- Link a DynamoDB query o dashboard para ver detalles
- Script `generate_report.py` que exporta findings a Markdown/PDF

**Criterios de aceptación:**
- Mensaje de Slack se ve bien (probado en un canal real)
- PDF generado es presentable como "reporte ejecutivo"
- El resumen tiene sentido aún sin leer el detalle

### Fase 6: Seeding de fugas para demo (Día 15)

**Tareas:**
- Módulo Terraform `seed_leaks/` que crea INTENCIONALMENTE:
  - 1 NAT Gateway en subnet sin workload
  - 2 EBS volumes gp2 unattached
  - 1 Elastic IP sin asociar
  - 3 snapshots viejos (tagged para cleanup)
  - 1 Lambda con 3GB memoria usando 200MB
  - 1 Log Group sin retention
- Script `seed_demo_leaks.sh`: `terraform apply -target=module.seed_leaks`
- Script `cleanup_demo_leaks.sh`: destroy del módulo
- Costos totales del seeding: < $2/mes si se deja correr

**Criterios de aceptación:**
- `make seed-demo` crea todo en < 2 min
- El agente detecta las 6+ fugas sembradas en una corrida
- `make cleanup-demo` limpia sin dejar residuos
- Todos los recursos tienen tag `Purpose=demo-finops-agent`

### Fase 7: Documentación de la charla (Día 16-18)

**Tareas:**
- `docs/DEMO_SCRIPT.md`: guion minuto a minuto con backup plans si algo falla en vivo
- `docs/COMPARISON.md`: tabla extensa DIY vs AWS DevOps Agent con citas
- `docs/ARCHITECTURE.md`: versión extendida con diagramas (Mermaid o draw.io exportado a SVG)
- `README.md` final con GIF demo + tabla de features + quickstart de 5 minutos
- Crear 1-2 diagramas limpios con Excalidraw o Mermaid
- Slides placeholder (fuera de repo, pero linkear desde README)

**Criterios de aceptación:**
- Un ingeniero externo puede clonar el repo, leer el README y desplegar en < 30 min
- DEMO_SCRIPT es ejecutable paso a paso sin Diego presente
- Documentación no tiene referencias rotas

### Fase 8: Hardening y polish (Día 19-20)

**Tareas:**
- Manejo de errores robusto (rate limits de Bedrock, timeouts, etc.)
- Retry con backoff exponencial en llamadas a Bedrock
- Observability: métricas custom en CloudWatch (investigations_run, findings_total, bedrock_cost_estimated)
- Guardrails del agente: límite de iteraciones, límite de tokens por investigación, circuit breaker
- Cost tracking propio: el agente reporta cuánto costó cada investigación
- Tests de integración E2E con cuenta real (opcional, detrás de flag)

**Criterios de aceptación:**
- Ninguna excepción no manejada en logs de 10 corridas
- Costo por investigación reportado en DynamoDB
- Stress test: 5 investigaciones paralelas sin errores
- Cobertura total > 80%

---

## 6. Escenarios de Demo (Fuentes de Fuga)

Para que la demo sea impactante, Claude Code debe implementar detección sólida para estos casos. Cada uno debe tener:
- Detector con umbral configurable
- Cálculo de impacto mensual preciso
- Comando/IaC de remediation claro
- Prompt context para que el LLM explique el "por qué"

| #   | Fuga                     | Detección                                   | Ahorro típico/mes | Dificultad |
| --- | ------------------------ | ------------------------------------------- | ----------------- | ---------- |
| 1   | NAT Gateway idle         | CloudWatch `BytesOutToDestination` < umbral | $32 + data        | Fácil      |
| 2   | EBS unattached           | `describe-volumes` + state=available + age  | $0.10/GB          | Fácil      |
| 3   | EBS gp2 → gp3            | `describe-volumes` + type=gp2               | 20% del costo EBS | Trivial    |
| 4   | EIP no asociada          | `describe-addresses` + InstanceId=null      | $3.60 c/u         | Trivial    |
| 5   | Snapshots huérfanos      | `describe-snapshots` + volumen borrado      | $0.05/GB          | Media      |
| 6   | Lambda oversized         | CloudWatch Insights sobre logs              | 40-70% del costo  | Media      |
| 7   | Log Groups sin retention | `describe-log-groups` + retention=null      | $0.03/GB/mes      | Fácil      |
| 8   | EC2 stopped + EBS        | `describe-instances` + state=stopped + age  | costo del EBS     | Fácil      |

---

## 7. Convenciones de Código

### 7.1 Estilo Python
- Formatter: `ruff format` (reemplaza black)
- Linter: `ruff check` con reglas: E, W, F, I, N, UP, B, A, C4, SIM
- Type hints OBLIGATORIOS en funciones públicas
- Docstrings estilo Google en módulos y clases
- Nombres en inglés para código, comentarios pueden ser en español

### 7.2 Commits
- Formato: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- Idioma: inglés
- Referencia a fase: `feat(agent): implement plan node [Phase 2]`

### 7.3 Tests
- Unit tests: mockear TODAS las llamadas externas (Bedrock, AWS, Slack)
- Integration tests: usar `moto` para AWS, VCR.py para Bedrock
- Naming: `test_<función>_<escenario>_<resultado_esperado>`
- Fixtures en `tests/fixtures/` como JSON

### 7.4 Secrets
- NUNCA hardcodear nada sensible
- Usar SSM Parameter Store para secrets en Lambda
- `.env` local con `python-dotenv`, `.env` en `.gitignore`

---

## 8. Consideraciones de Seguridad

- IAM del Lambda: **solo read permissions** en fases 1-6
- Escritura (stop instances, delete volumes) solo si se agrega fase extra con human-in-the-loop explícito
- MCP server de GitHub: token con scope mínimo (`repo:read`)
- Secrets en SSM, no en variables de entorno de Lambda
- VPC: Lambda NO en VPC (no necesita, evita NAT costs)
- Logs: no loggear el contenido completo de respuestas de Bedrock (pueden tener data sensible de la cuenta)

---

## 9. Instrucciones Específicas para Claude Code

### 9.1 Cómo usar este documento
1. Lee este archivo completo antes de empezar cualquier fase
2. Al iniciar una fase, crea un branch `feat/fase-N-<descripción>`
3. Commitea frecuentemente (cada subtarea)
4. Al final de cada fase, abre PR con checklist de criterios de aceptación
5. Si tienes dudas sobre una decisión, pausa y pregunta en vez de asumir

### 9.2 Verificaciones previas a cada tarea
- Busca en web la versión más reciente de la dependencia antes de pinnearla
- Verifica el model ID de Bedrock vigente (cambia cada pocos meses)
- Revisa si hay breaking changes en LangGraph desde este documento

### 9.3 Comunicación en PRs
- Cada PR incluye: qué se hizo, cómo se probó, qué falta, screenshots/logs si aplica
- Señala decisiones técnicas no triviales y su justificación
- Si algo del plan no tiene sentido al implementarlo, PROPÓN un cambio en vez de forzarlo

### 9.4 Anti-patterns a evitar
- NO sobre-engineerar: empieza con la solución más simple que cumpla criterios
- NO agregar dependencias no listadas sin justificar
- NO hacer refactors grandes en fases de implementación (déjalo para Fase 8)
- NO commit directo a main; siempre PR

---

## 10. Métricas de Éxito del Proyecto

### 10.1 Técnicas
- [ ] Lab completo deployable en < 30 min desde repo limpio
- [ ] Costo operacional real medido < $10/mes
- [ ] Detección de al menos 6/8 tipos de fugas en cuenta real
- [ ] Cobertura de tests > 80%
- [ ] Documentación completa y sin links rotos

### 10.2 De charla
- [ ] Demo en vivo ejecutable en 12 min sin sobresaltos
- [ ] Backup video por si falla la conexión
- [ ] Slides derivan del contenido del repo (no redundancia)
- [ ] Repo recibe > 10 stars en primera semana post-charla
- [ ] Al menos 3 issues/PRs de la comunidad en el primer mes

---

## 11. Roadmap Post-Charla (Fuera de Scope Inicial)

Ideas para evolucionar el proyecto después del Community Day:
- Agregar remediation automática con aprobación por Slack (button-based)
- Soporte multi-account (AWS Organizations)
- Dashboard web con Streamlit o Next.js
- Integración con Jira/Linear para crear tickets de remediation
- Comparación head-to-head automática con Trusted Advisor
- Publicar los MCP servers como paquetes independientes

---

## 12. Referencias

- AWS DevOps Agent (para comparación): https://aws.amazon.com/devops-agent/
- Amazon Bedrock docs: https://docs.aws.amazon.com/bedrock/
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- MCP spec: https://modelcontextprotocol.io/
- AWS Lambda Powertools: https://docs.powertools.aws.dev/lambda/python/
- Cost Explorer API: https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/

---

**Autor del plan:** Diego (con Claude como co-autor)
**Versión:** 1.0
**Última actualización:** 2026-04-20
**Siguiente revisión:** después de completar Fase 2
