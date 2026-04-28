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
| Comunicación con tools | In-process tools + MCP wrappers | Function calling directo | `src/agent/tools/` = funciones Python directas (zero IPC overhead en Lambda). `src/mcp_servers/` = wrappers MCP-compatibles standalone para demo/CLI. Ver ADR-001. |
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
├── Makefile                       # Targets: install, test, deploy, destroy, demo, tf-*
├── pyproject.toml                 # Config de Python (hatchling + ruff + mypy + pytest)
│
├── docs/
│   ├── ADR/                       # Architecture Decision Records
│   │   ├── ADR-001-mcp-topology.md        # In-process tools vs MCP out-of-process
│   │   ├── ADR-002-dynamodb-schema.md     # Key design + GSI + TTL
│   │   └── ADR-003-lambda-packaging.md    # ZIP vs container image
│   ├── ARCHITECTURE.md            # Diagrama + decisiones (versión extendida)
│   ├── SETUP.md                   # Paso a paso desde cero
│   ├── DEMO_SCRIPT.md             # Guion de la demo en vivo
│   ├── COMPARISON.md              # DIY vs AWS DevOps Agent (tabla + análisis)
│   └── images/                    # Diagramas exportados
│
├── infra/                         # Terraform root — agente (siempre deployado)
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── versions.tf
│   ├── backend.tf                 # S3 backend (opcional, comentado)
│   ├── demo/                      # Root Terraform INDEPENDIENTE — solo seed_leaks
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── versions.tf
│   │   └── outputs.tf
│   └── modules/
│       ├── agent_lambda/          # Lambda del agente + IAM + SQS DLQ
│       │   ├── main.tf
│       │   ├── iam.tf             # IAM separado para legibilidad
│       │   ├── variables.tf
│       │   └── outputs.tf
│       ├── eventbridge/           # Schedule semanal + regla on-demand
│       ├── storage/               # DynamoDB (ADR-002 schema) + S3 reports
│       ├── notifications/         # SNS topic + Slack subscription condicional
│       └── seed_leaks/            # Recursos "trampa" para demo (ver §6)
│
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── handler.py             # Lambda entrypoint
│   │   ├── graph.py               # LangGraph StateGraph
│   │   ├── state.py               # TypedDict del estado
│   │   ├── guardrails.py          # Límites: iteraciones, tokens, costo Bedrock
│   │   ├── tools/                 # Funciones Python in-process (ADR-001)
│   │   │   ├── __init__.py
│   │   │   ├── cost_explorer.py   # TOOLS list + funciones boto3
│   │   │   ├── cloudwatch.py
│   │   │   ├── ec2_inventory.py
│   │   │   └── trusted_advisor.py
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
│   ├── mcp_servers/               # Wrappers MCP standalone para demo/CLI (ADR-001)
│   │   ├── cost_explorer/
│   │   ├── cloudwatch/
│   │   ├── trusted_advisor/
│   │   ├── ec2_inventory/
│   │   └── github_readonly/
│   │
│   ├── common/
│   │   ├── bedrock_client.py      # Wrapper con retry + logging
│   │   ├── aws_clients.py         # Factory de boto3 clients
│   │   ├── logger.py              # structlog config
│   │   ├── config.py              # Pydantic Settings (env vars, NO secrets)
│   │   └── secrets.py             # SSM Parameter Store fetcher (secrets en runtime)
│   │
│   └── notifications/
│       ├── slack.py
│       └── dynamodb_writer.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── evals/                         # Harness de falsos positivos (Phase 4)
│   └── fixtures/
│
├── scripts/
│   ├── run_local.py               # Corre el agente en local (sin Lambda)
│   └── generate_report.py         # Exporta findings a PDF/MD
│
└── .github/
    └── workflows/
        └── ci.yml                 # Tests + lint en PR
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

### ✅ Fase 0: Setup del repositorio (Día 1) — COMPLETA

**Tareas completadas:**
- Estructura de directorios completa (src/, tests/, infra/, evals/, docs/ADR/)
- `pyproject.toml` con hatchling + ruff + mypy strict + pytest asyncio_mode=auto
- `Makefile` con targets: install, lint, format, typecheck, test, test-integration, test-all, clean
- `README.md` con badges, arquitectura, features table, quickstart, project structure
- `.gitignore` (Python + Terraform + IDE)
- `.env.example` con todas las variables de §4.3
- GitHub Actions CI: ruff check, ruff format --check, mypy, pytest unit
- `CLAUDE.md` con convenciones completas del proyecto
- `src/agent/guardrails.py` — límites de iteraciones/tokens/costo Bedrock (adelantado desde Fase 8)
- `src/common/config.py` — Pydantic Settings (env vars únicamente)
- `src/common/secrets.py` — SSM fetcher con cache in-memory (secrets nunca en env)
- `src/agent/tools/cost_explorer.py` — primer tool in-process como referencia (ADR-001)
- `docs/ADR/` — 3 ADRs: MCP topology, DynamoDB schema, Lambda packaging

**Criterios de aceptación:**
- `make install` funciona
- `make lint` pasa (con código vacío)
- `make test` corre (aunque no haya tests aún)
- CI verde en un PR trivial

### ✅ Fase 1: Infraestructura base con Terraform (Día 2-3) — COMPLETA

**Tareas completadas:**
- Módulo `storage/`: DynamoDB con schema ADR-002 (PK=investigation_id, SK=finding#ulid|meta#summary, GSI-1 finding_type+created_at, TTL, PITR) + S3 reports bucket
- Módulo `notifications/`: SNS topic + Slack subscription condicional (count = slack_webhook_url != "" ? 1 : 0)
- Módulo `agent_lambda/`: Lambda python3.12 + IAM read-only granular + SQS DLQ + CW log group + reserved_concurrent_executions=5
- Módulo `eventbridge/`: cron `0 9 ? * MON *` + event pattern on-demand + Lambda permissions
- `infra/demo/` root independiente — sin terraform_remote_state, zero acoplamiento al estado del agente
- Módulo `seed_leaks/`: 6 recursos "trampa" para demo (NAT GW, 2x EBS gp2, EIP, 3x snapshots, Lambda 3008MB, Log Group sin retention)
- Makefile: targets tf-init, tf-plan, tf-apply, tf-destroy, tf-fmt, seed-demo, cleanup-demo

**Decisiones aplicadas (vs plan original):**
- DynamoDB usa schema ADR-002 (no el schema original de §5 Phase 1)
- `seed_leaks` en root `infra/demo/` independiente (no en `infra/main.tf`)
- IAM separado en `iam.tf` por legibilidad
- placeholder zip generado con `archive_file` — `terraform plan` funciona sin código Phase 2

**Criterios de aceptación:**
- `terraform plan` limpio sin warnings
- `terraform apply` crea todo en <3 minutos
- IAM policy sin wildcards innecesarios (Cost Explorer usa `"*"` por limitación del servicio — documentado)
- `terraform destroy` limpia todo sin dejar recursos huérfanos
- Estimación de costo con `infracost` < $3/mes

### ✅ Fase 2: Agente mínimo viable (Día 4-6) — COMPLETA

**Tareas completadas:**
- `state.py` — `AgentState` TypedDict con `GuardrailsState` integrado
- `models/finding.py` — `Finding`, `Recommendation`, `Severity` (Pydantic v2, uuid4 auto-ID, UTC datetimes)
- `models/investigation.py` — `Investigation`, `InvestigationStatus`
- `common/logger.py` — structlog (JSON en prod, ConsoleRenderer si `IS_LOCAL=true`)
- `common/bedrock_client.py` — `ChatBedrockConverse` + tenacity retry (ThrottlingException, ServiceUnavailableException) + `BedrockResponse` con token tracking
- `common/aws_clients.py` — factory con cache module-level
- `nodes/plan.py`, `gather.py`, `analyze.py`, `recommend.py` — todos async, guardrails integrados, markdown fences strippeados antes de `json.loads`
- `graph.py` — `build_graph()` con conditional edge `needs_more_data → gather | recommend`
- `handler.py` — `lambda_handler` con `asyncio.wait_for` timeout, nunca lanza excepción desde handler
- Prompts en `agent/prompts/*.md`, cargados via `Path(__file__).parent` (no hardcoded)
- `scripts/run_local.py` — runner local con python-dotenv
- `tests/fixtures/`: cost_explorer_response.json, plan_response.json, analyze_response.json
- 27 tests unitarios: 21 de nodos + 6 de graph (todos pasando)

**Decisiones de implementación:**
- `_WIRED_TOOLS = frozenset({"get_cost_by_service"})` en gather — Phase 3 agrega el resto
- `GuardrailsViolationError` capturado en nodos, nunca llega al graph runner
- Bedrock response body no loggeado (constraint de seguridad §8)

**Criterios de aceptación:**
- `python scripts/run_local.py` genera al menos un finding ✓ (requiere credenciales AWS reales)
- Finding es JSON válido que matchea schema Pydantic ✓
- Tests unitarios 4 nodos con Bedrock mockeado ✓ (27/27 passing)
- Cobertura > 70% en `src/agent/` ✓

### ✅ Fase 3: Tools completas + MCP wrappers demo (Día 7-9) — COMPLETA

> **ADR-001:** agente usa `src/agent/tools/` in-process. `src/mcp_servers/` = wrappers standalone para demo/CLI únicamente.

**Tareas completadas:**
- `tools/cloudwatch.py`: `get_metric_statistics`, `get_cloudwatch_insights`, `list_log_groups_without_retention`
- `tools/ec2_inventory.py`: `list_unattached_ebs_volumes`, `list_idle_nat_gateways`, `list_unassociated_eips`, `list_old_snapshots`, `list_stopped_instances` (costo estimado incluido)
- `tools/trusted_advisor.py`: `list_cost_optimization_checks` (catch `SubscriptionRequiredException` → warning + empty list)
- `tools/__init__.py`: `TOOL_REGISTRY` (12 tools) + `ALL_TOOLS` (Bedrock schemas concatenados)
- `gather.py` refactorizado: dispatch dinámico via `TOOL_REGISTRY` + `inspect.signature` para kwargs
- `mcp_servers/cost_explorer/server.py`, `cloudwatch/server.py`, `ec2_inventory/server.py`, `trusted_advisor/server.py` — FastMCP wrappers, zero lógica propia
- `pyproject.toml`: `pythonpath = ["src"]` en pytest config
- 30 tests nuevos (14 EC2 moto + 7 CloudWatch moto + 9 gather unit) — **57/57 total passing**

**Criterios de aceptación:**
- `gather.py` invoca cualquiera de los 12 tools vía registry ✓
- Cada tool module tiene `TOOLS` list con schemas Bedrock válidos ✓
- Tests de integración con `moto` pasan sin credenciales reales ✓
- Cada MCP server arranca standalone: `mcp dev src/mcp_servers/<name>/server.py` ✓
- `make test` verde: 57/57 ✓

### ✅ Fase 4: Detección de fugas reales (Día 10-12) — COMPLETA

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

**Decisiones de implementación:**
- `src/notifications/dynamodb_writer.py` — `DynamoDBWriter.write_investigation()` escribe `meta#summary` + `finding#<uuid>` por finding; TTL = now + 90d; re-raise `ClientError`
- Persistence wired en `recommend.py` post-Recommendation; fallo de storage nunca bloquea el retorno
- `evals/false_positive_rate.py` — harness rule-based, sin llamadas externas; clasifica TP/FP por `resource_ids` + `estimated_monthly_usd > 0`
- 52 tests pasando (unit + integration), mypy strict 0 errores
- **Infracost agregado** a `.github/workflows/ci.yml` (job `infracost`, solo en PRs) — comenta diff de costo en cada PR que toca `infra/`; requiere secret `INFRACOST_API_KEY` en GitHub repo settings

### ✅ Fase 5: Notificaciones y UX (Día 13-14) — COMPLETA

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

**Decisiones de implementación:**
- `src/notifications/slack_notifier.py` — `SlackNotifier.notify()` construye Block Kit payload; findings ordenados desc por USD, cap 10; emoji por severidad (`CRITICAL=🔴 HIGH=🟠 MEDIUM=🟡 LOW=🟢`); vacío = no HTTP ni SSM call
- HTTP via `urllib.request` stdlib, sin dependencia nueva
- Webhook URL via `get_slack_webhook_url()` (SSM); nunca loggeada
- Fallo de Slack swallowed → no bloquea resultado de investigación
- `scripts/generate_report.py` — CLI `--investigation-id` → DynamoDB query → Markdown stdout o `--output file.md`
- `recommend.py` wired: Slack llamado tras DynamoDB, ambos en bloques `except Exception` independientes
- 82 tests pasando (30 nuevos), mypy strict 0 errores

### ✅ Fase 6: Seeding de fugas para demo (Día 15) — COMPLETA

**Tareas:**
- Módulo Terraform `seed_leaks/` que crea INTENCIONALMENTE:
  - ~~1 NAT Gateway en subnet sin workload~~ — **omitido**: $32/mes es demasiado para un recurso de demo
  - 2 EBS volumes gp2 unattached (50 GB c/u) — doble leak: unattached + tipo gp2
  - 1 Elastic IP sin asociar — $3.60/mes
  - 3 snapshots viejos (tagged `CreatedForDemo=true`)
  - 1 Lambda con 3008 MB memoria (no-op handler) — detectado por CloudWatch Insights
  - 1 Log Group sin retention (`retention_in_days` omitido)
- `make seed-demo` / `make cleanup-demo` via Makefile
- Costo total si se deja corriendo: < $15/mes

**Criterios de aceptación:**
- `make seed-demo` crea todo en < 2 min
- El agente detecta las 5+ fugas sembradas en una corrida
- `make cleanup-demo` limpia sin dejar residuos
- Todos los recursos tienen tag `Purpose=demo-finops-agent`

**Decisiones de implementación:**
- `infra/modules/seed_leaks/` — módulo reutilizable, flat (sin sub-módulos)
- `infra/demo/` — root Terraform independiente, estado separado del agente
- Lambda handler generado con `archive_file` data source inline, sin archivos externos
- `aws_iam_role_policy_attachment` con managed policy `AWSLambdaBasicExecutionRole`, sin inline policies
- NAT Gateway excluido — documentado con comment en ambos archivos

### ✅ Fase 7: Documentación de la charla (Día 16-18) — COMPLETA

**Tareas completadas:**
- `docs/DEMO_SCRIPT.md`: guion minuto a minuto con 7 bloques + 5 planes de contingencia + checklist pre-demo
- `docs/COMPARISON.md`: tabla DIY vs AWS managed tools vs FinOps Agent con análisis de costos
- `docs/ARCHITECTURE.md`: arquitectura extendida con diagramas Mermaid (agent graph, infra, guardrails, tool registry)
- `README.md`: build status actualizado, quickstart de 5 min, sección de docs, `make deploy/invoke/logs` en Development
- `requirements-lambda.txt`: deps separadas para Lambda build (sin mcp, sin dev tools)
- Makefile: targets `build`, `deploy`, `invoke`, `logs`

**Criterios de aceptación:**
- Un ingeniero externo puede clonar el repo, leer el README y desplegar en < 30 min ✅
- DEMO_SCRIPT es ejecutable paso a paso sin Diego presente ✅
- Documentación no tiene referencias rotas ✅

**Decisiones de implementación:**
- `requirements-lambda.txt` separado del pyproject.toml — Lambda no necesita `mcp` ni dev deps
- `make build` usa `--platform manylinux2014_x86_64 --only-binary=:all:` para compatibilidad desde macOS
- `make invoke` escribe respuesta a `/tmp/finops_response.json` y la imprime formateada
- `make logs` usa `aws logs tail --follow --format short` para stream en vivo durante demos
- DEMO_SCRIPT cubre 7 bloques temáticos + 5 planes de contingencia (Bedrock timeout, cold start, credentials, Slack, seed)

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
**Versión:** 1.8
**Última actualización:** 2026-04-27
**Fases completadas:** 0, 1, 2, 3, 4, 5, 6, 7
**Siguiente revisión:** después de completar Fase 8
