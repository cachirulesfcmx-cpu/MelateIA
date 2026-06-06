# 🎰 MelateAI Pro

Aplicación web **móvil-first** (estilo iOS 26 / *Liquid Glass*) para **análisis, predicción,
historial, backtesting y seguimiento** de los sorteos mexicanos **Melate, Revancha,
Melate Retro y Revanchita**.

### 🌐 App en vivo: **https://melate-ia.vercel.app**
- Usuario: **demo@melateai.pro** / **demo1234**
- Admin: **admin@melateai.pro** / **admin1234** (panel **Usuarios** + carga de resultados oficiales)

Solo el **administrador** agrega resultados reales (sorteos): al hacerlo se evalúan
las predicciones pendientes de **todos** los usuarios y el sistema se **reentrena**.
El admin también **crea/elimina usuarios** y **restablece contraseñas** desde su panel.

**Recuperación de contraseña por email:** configura un proveedor con variables de
entorno y el sistema enviará un enlace de reseteo (`/reset?token=…`); si no hay
proveedor, devuelve el token directamente (modo demo).
- Resend: `RESEND_API_KEY`, `EMAIL_FROM` (remitente verificado).
- SMTP: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`.
- `APP_URL` para construir el enlace (por defecto la URL de producción).

Desplegada en **Vercel** (frontend estático + función serverless FastAPI) con base de
datos **PostgreSQL en Supabase** (esquema aislado `melateai`). Variables de entorno de
producción: `DATABASE_URL` (pooler de Supabase, IPv4), `DB_SCHEMA=melateai`, `SECRET_KEY`.

> ⚠️ **Aviso importante:** Melate es un juego de **azar**. Ninguna IA puede garantizar
> premios. MelateAI Pro genera combinaciones **estadísticamente optimizadas**, registra
> resultados reales, compara aciertos y mejora su memoria con el tiempo — **no promete
> resultados garantizados**.

---

## ✨ Características

- **Auth real** (email/password + JWT), sesión persistente.
- **Dashboard móvil** con resumen, últimos sorteos, próximos concursos, mejores combinaciones y aciertos recientes.
- **Generador de predicciones** con 8 estrategias (conservadora, balanceada, agresiva, genética, anti-popular, calientes, fríos, híbrida avanzada).
- **Motor híbrido matemático-predictivo** en Python: feature engineering, reglas simbólicas, búsqueda genética, modelo ML por número (Gradient Boosting), bandit multi-brazo (RL) y backtesting.
- **Comparación automática**: al agregar un sorteo real se evalúan todas las predicciones pendientes, se calculan aciertos y se ajustan los pesos del ensemble.
- **Historial de predicciones** con estados (pendiente/comparada/usada), aciertos, reanálisis, borrado y exportación CSV.
- **Historial de sorteos** con estadísticas (frecuencias, gaps, par/impar, primos, sumas, consecutivos), filtros, vista de bolas y tabla, y carga de CSV.
- **Estimador de ganancias** con probabilidad hipergeométrica, tabla de escenarios (2–6 aciertos), ROI, riesgo y **comparación contra el azar** vía backtesting real.
- **Perfil** con desempeño por estrategia y pesos aprendidos.

---

## 🧱 Stack

| Capa        | Tecnología |
|-------------|-----------|
| Frontend    | React 18 + TypeScript + Vite + TailwindCSS (diseño Liquid Glass) |
| Backend     | Python + FastAPI + SQLAlchemy |
| Base datos  | SQLite (local/dev) · PostgreSQL (producción, vía `DATABASE_URL`) |
| ML / IA     | pandas, numpy, scikit-learn (Gradient Boosting) — preparado para XGBoost/LightGBM/PyTorch |
| Auth        | JWT (python-jose) + bcrypt |

---

## 📂 Estructura

```
MelateIA/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + routers
│   │   ├── config.py          # settings (env)
│   │   ├── database.py        # SQLAlchemy engine/session
│   │   ├── models.py          # tablas: users, draws, predictions, results, performance, csv_uploads
│   │   ├── schemas.py         # Pydantic
│   │   ├── auth.py            # JWT + hashing
│   │   ├── services.py        # comparación automática predicción↔sorteo
│   │   ├── routers/           # auth, dashboard, draws, predictions, evaluation, earnings, ml
│   │   └── engine/            # MOTOR IA / MATEMÁTICO
│   │       ├── game_config.py     # rangos y reglas por juego
│   │       ├── data_engine.py     # carga/limpieza/validación de CSV
│   │       ├── features.py        # feature engineering + estadística
│   │       ├── symbolic.py        # motor simbólico de reglas
│   │       ├── strategies.py      # árbol de razonamiento (8 estrategias)
│   │       ├── generator.py       # búsqueda heurística + genética
│   │       ├── models_ml.py       # modelo ML por número (sklearn)
│   │       ├── bandit.py          # reinforcement learning (multi-armed bandit)
│   │       ├── backtesting.py     # simulación histórica
│   │       └── earnings.py        # probabilidad hipergeométrica + ROI
│   ├── data/                  # CSVs históricos (Melate, Revancha, Retro, Revanchita)
│   ├── seed.py               # carga CSVs + usuario demo
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/            # Login, Register, Dashboard, Predictions, History, Draws, Earnings, Profile
│       ├── components/       # GlassCard, GlassButton, BottomNav, NumberBall, BallSelector, LiquidModal, …
│       ├── context/          # Auth + Toast
│       └── api/              # cliente fetch + tipos
└── scripts/                  # dev.sh, seed.sh
```

---

## 🚀 Instalación y ejecución

### Requisitos
- Python 3.10+
- Node.js 18+

### Opción rápida (un comando)

```bash
./scripts/dev.sh
```
Crea el venv, instala dependencias, siembra la BD (la primera vez) y levanta backend + frontend.

### Manual

**1) Backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                     # carga ~7,700 sorteos históricos + usuario demo
uvicorn app.main:app --reload --port 8000
```
API en `http://127.0.0.1:8000` · documentación interactiva en `http://127.0.0.1:8000/docs`.

**2) Frontend**
```bash
cd frontend
npm install
npm run dev
```
App en `http://127.0.0.1:5173` (el proxy de Vite reenvía `/api` al backend).

### Usuario demo
```
email:    demo@melateai.pro
password: demo1234
```

---

## 🧮 Cómo funciona el motor

1. **Data Engine** — carga y valida los CSV (`F1..F6` / `R1..R6`, fecha, concurso), normaliza y detecta el rango por juego.
2. **Feature Engineering** — frecuencia global y por ventanas (10/25/50/100), gaps/atraso, calientes/fríos, par/impar, primos, suma, rango, desviación, consecutivos, repeticiones, pares frecuentes.
3. **Modelo ML** — por cada bola, un *Gradient Boosting* predice la probabilidad de aparición en el próximo sorteo (interfaz lista para XGBoost/LightGBM/LSTM).
4. **Motor simbólico** — puntúa cada combinación contra reglas (suma, balance par/impar, distribución por tercios, primos, consecutivos) y penaliza patrones “humanos”/populares.
5. **Búsqueda genética** — genera miles de candidatas, cruza y muta las mejores, y selecciona un top-k **diverso**.
6. **Estrategias** — cada una sesga los pesos y el perfil ideal para producir combinaciones distintas, con explicación matemática.
7. **Memoria + RL** — al llegar un sorteo real se evalúan las predicciones pendientes, se guardan aciertos y un *multi-armed bandit* ajusta el peso de cada estrategia.
8. **Backtesting** — replica una estrategia sobre los últimos N sorteos (sin look-ahead) y compara contra el azar.

---

## 🔌 Endpoints principales

```
AUTH        POST /api/auth/register · /login · /logout · GET /api/auth/me
DASHBOARD   GET  /api/dashboard/summary
DRAWS       GET  /api/draws · POST /api/draws · /api/draws/text · /api/draws/upload-csv · GET /api/draws/stats
PREDICTIONS POST /api/predictions/generate · /save · GET /history · POST /{id}/mark-used · DELETE /{id} · GET /export
EVALUATION  POST /api/evaluate/new-draw · GET /api/evaluate/prediction/{id} · POST /api/backtesting
EARNINGS    POST /api/earnings/estimate
ML          POST /api/ml/train · /retrain · GET /api/ml/performance
```

---

## 🗄️ Datos incluidos

Bajo `backend/data/` se incluyen los históricos reales:

| Juego        | Rango  | Sorteos |
|--------------|--------|---------|
| Melate       | 1–56   | ~2,137  |
| Revancha     | 1–56   | ~2,137  |
| Melate Retro | 1–39   | ~1,639  |
| Revanchita   | 1–56*  | ~1,852  |

\* El dataset de Revanchita provisto usa el rango 1–56; los rangos por juego se
configuran en `backend/app/engine/game_config.py`.

---

## 🌐 Producción

- Define `DATABASE_URL` (PostgreSQL) y un `SECRET_KEY` fuerte en `backend/.env`.
- `cd frontend && npm run build` genera `dist/` (estático). Sirve la API con `uvicorn`/`gunicorn` detrás de Nginx, o despliega en Replit / un servidor Linux.
- Configura `VITE_API_URL` si el backend vive en otro host.

---

## 🛡️ Juego responsable

Esta herramienta es educativa y de análisis estadístico. La esperanza matemática de la
lotería es **negativa**. Juega con responsabilidad y solo lo que puedas permitirte perder.
