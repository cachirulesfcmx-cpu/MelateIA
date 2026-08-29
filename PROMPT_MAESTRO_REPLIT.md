# Prompt maestro — MelateAI Pro (para Replit Agent)

> Copia todo el bloque de abajo y pégalo como primer mensaje al Agente de Replit.
> Al final hay notas de uso (por fases, datos y despliegue).

---

Construye **MelateAI Pro**, una aplicación web full-stack mobile-first para análisis estadístico y generación optimizada de combinaciones de la Lotería Nacional mexicana (Melate, Revancha, Melate Retro, Revanchita, Chispazo y Tris).

**Encuadre obligatorio y no negociable:** la lotería es un juego de azar puro. La app NO promete ni insinúa ganar. En la UI y en los textos generados debe quedar explícito que ningún modelo puede predecir un sorteo aleatorio, y las métricas siempre se comparan contra la línea base del azar. Nada de lenguaje tipo "números ganadores garantizados".

## 1. Stack y estructura

Un solo Repl con dos carpetas:

- `backend/` — Python 3.11, FastAPI + SQLAlchemy 2.0 + Pydantic v2. Uvicorn.
- `frontend/` — React 18 + TypeScript + Vite + TailwindCSS. Solo `react`, `react-dom`, `react-router-dom` como dependencias de runtime (sin librerías de UI ni de gráficas: los charts son SVG propio).

Base de datos: **PostgreSQL de Replit** vía `DATABASE_URL` (con fallback automático a SQLite local si la variable no existe, para desarrollo). Soporta un esquema aislado por `DB_SCHEMA`.

Configura `.replit` para que un solo comando levante el backend en el puerto expuesto y sirva el frontend ya compilado (`vite build` → estáticos servidos por FastAPI). Usa **Replit Secrets** para: `DATABASE_URL`, `DB_SCHEMA`, `SECRET_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `SMTP_*`, `ANTHROPIC_API_KEY`, `SENTRY_DSN`.

Dependencias backend: `fastapi, uvicorn[standard], SQLAlchemy, pydantic, pydantic-settings, python-jose[cryptography], passlib[bcrypt], bcrypt, python-multipart, email-validator, pandas, numpy, scikit-learn, xgboost, psycopg2-binary, pywebpush, sentry-sdk`.

**Regla de resiliencia:** todas las dependencias pesadas (pandas/numpy/sklearn/xgboost) son OPCIONALES. Si no están disponibles, el motor debe degradar automáticamente a una ruta heurística en Python puro y seguir funcionando. Nunca debe romperse la app por falta de una librería de ML.

## 2. Los 6 juegos

Define una `GameConfig` (dataclass) con: `key, label, max_number, min_number, pick, main_columns, additional_column, seed_file, kind`.

| Juego | Balotas | Elige | Tipo |
|---|---|---|---|
| melate | 1–56 | 6 | combinación |
| revancha | 1–56 | 6 | combinación |
| melate_retro | 1–39 | 6 | combinación |
| revanchita | 1–56 | 6 | combinación |
| chispazo | 1–29 | 5 | combinación |
| tris | 0–9 | 5 | **posicional** |

- **Combinación**: números únicos, el orden no importa, se guardan ordenados. Los aciertos son intersección de conjuntos.
- **Posicional (Tris)**: dígitos 0–9, **se permiten repeticiones** y **la posición importa**. "1,2,3,4,5" ≠ "5,4,3,2,1". Los aciertos se cuentan **por posición**. Tris necesita su propio motor estadístico (histogramas por posición), NO reutiliza el motor de combinaciones.
- La columna "adicional" (R7/F7) se almacena aparte y no participa en la predicción.

## 3. Motor predictivo "Genius" (el corazón del proyecto)

### 3.1 Ensamble de 15 modelos base
Cada modelo recibe el historial (más antiguo → más reciente) y devuelve una distribución de probabilidad normalizada por número:

1. **Bayesiano con decaimiento** — conteo con prior de Laplace y peso `decay^antigüedad` (0.97).
2. **Atraso (hazard)** — análisis de supervivencia: curva logística sobre `atraso_actual / atraso_promedio`.
3. **Co-ocurrencia** — cuánto acompaña cada número a los de los últimos 30 sorteos.
4. **Frecuencia** — histograma simple.
5. **Momentum (EWMA)** — media móvil exponencial de apariciones (α=0.15).
6. **Markov orden 1** — matriz de transición del sorteo anterior al siguiente, con suavizado de Laplace.
7. **Fourier / ciclos** — autocorrelación por número para detectar periodicidad; refuerza los que están por "cerrar ciclo". Vectorizado con numpy.
8. **Posicional** — histograma por posición dentro del sorteo ordenado, agregado por número.
9. **Mezcla gaussiana** — ajusta a la distribución típica de la SUMA del sorteo.
10. **Patrón delta** — distribución de las diferencias entre números ordenados consecutivos.
11. **Racha caliente** — ventana de 15 sorteos, con bonus tanto a los muy calientes como a los ausentes.
12. **Presión por zona** — divide el rango en 4 zonas y favorece las zonas con déficit en los últimos 20 sorteos.
13. **Pair lift** — lift de co-aparición contra la hipótesis de independencia.
14. **Arrastre (repite)** — mide en el historial REAL con qué frecuencia los números del sorteo anterior reaparecen, y aplica exactamente ese lift a los números del último sorteo.
15. **Vecinos (±1/±2)** — mide la tasa real de adyacencia entre sorteos consecutivos y refuerza los números adyacentes a los del último sorteo.

**Crítico:** los modelos 14 y 15 (y en general todo factor de refuerzo) deben calibrarse **midiendo la tasa real en el historial del juego**, nunca con constantes inventadas.

### 3.2 Evolución de pesos (walk-forward, sin look-ahead)
- Para cada uno de los últimos ~70 sorteos, entrena cada modelo SOLO con lo anterior y mide su **precisión top-k** (k ≈ 27% del rango) contra el resultado real.
- Convierte los puntajes en pesos con un **softmax de temperatura 120** y un piso mínimo por modelo (~3%). Temperatura alta = los pesos discriminan con fuerza entre modelos buenos y malos.
- Cachea el resultado por juego y por número de sorteos; **recalcula en cuanto entra un sorteo nuevo**.

### 3.3 Capa meta ("meta-consciencia")
Sobre la distribución fusionada aplica:
- **Consenso**: bonus a los números que muchos modelos colocan en su top 15.
- **Memoria de errores**: usando las **últimas 40 predicciones REALES ya evaluadas** del usuario — penaliza los números que jugamos y no salieron, premia los que salieron y habíamos ignorado.
- **Aceleración**: bonus a los números cuya frecuencia en los últimos 10 sorteos supera la de los 10 anteriores.

### 3.4 Generación de boletos (optimizador de pool)
- Agudiza la distribución elevándola a **^1.8** y renormalizando (concentra en los favoritos del motor).
- Muestrea por ruleta un **pool de hasta 400 candidatos**.
- Puntúa TODOS con la función Genius: `0.45·probabilidad + 0.18·paridad + 0.17·dispersión + 0.20·atraso`.
- Selecciona ávidamente los N mejores que sean **mutuamente diversos** (índice de Jaccard ≤ 0.6).
- Precomputa el escaneo del historial una sola vez por pool (rendimiento).

### 3.5 Backbone global
La distribución fusionada (cacheada) debe **reforzar el muestreo de TODAS las estrategias**, no solo de la evolutiva, mediante mezcla geométrica con el perfil propio de cada estrategia: `w_final = (w_estrategia)^0.65 · (w_genius)^0.35`.

### 3.6 Otros componentes del motor
- **Motor simbólico**: reglas duras (rechaza combinaciones absurdas) y puntuación suave por campana sobre suma, paridad, primos, dispersión por decenas, rango, sinergia de pares y factor anti-popular. Debe producir una **explicación en español legible** de por qué se eligió cada combinación.
- **Algoritmo genético**: cruza y muta las mejores combinaciones durante ~6 generaciones para las estrategias que lo usen.
- **Modelo ML por número**: XGBoost (con fallback a GradientBoosting de sklearn, y a heurística pura si no hay ninguno) que entrega una probabilidad por número y se mezcla con el ensamble.
- **Bandit contextual multi-brazo**: aprende qué estrategia rinde mejor en cada "régimen" actual del juego y enruta la estrategia adaptativa.
- **Backtesting**: repite las últimas N jugadas sin look-ahead, cuenta aciertos y **siempre reporta la línea base del azar** y el ROI simulado contra ella.
- **Estimador de ganancias**: probabilidades hipergeométricas reales por categoría de premio.

## 4. Las 10 estrategias

`conservadora, balanceada, agresiva, genetica, anti_popular, calientes, frios, hibrida, adaptativa, evolutiva`

Cada una define su perfil ideal (paridad, primos, suma, dispersión), su sesgo de muestreo (calientes/fríos/balanceado), su temperatura y sus banderas (`genetic`, `use_ml`, `anti_popular`). **Evolutiva (Genius)** es la insignia y debe ser la **preseleccionada** al abrir Predicciones, y aparecer primera en el selector.

## 5. Modelo de datos (11 tablas)

`users` (email, hash bcrypt, is_admin, verificación) · `draws` (game_type, draw_number, draw_date, numbers, additional, source; único por juego+concurso) · `predictions` (user_id, game_type, strategy, numbers, score, explanation, status: pendiente/usada/comparada, used) · `prediction_results` (prediction_id, draw_id, hits, matched_numbers, evaluated_at) · `model_performance` · `csv_uploads` · `learning_log` · `rate_limit` · `push_subscriptions` · `ensemble_weight` (pesos evolucionados persistidos por juego) · `strategy_context_perf` (bandit contextual).

## 6. API REST (prefijo `/api`)

- **auth**: `register, login, login-form, logout, me, change-password, forgot-password, reset-password`
- **draws**: `GET /` (listar), `POST /` (alta, solo admin), `DELETE /{id}` (borrar sorteo mal capturado, solo admin), `POST /grouped` (⚠️ ver abajo), `POST /upload-csv`, `GET /games`, `GET /stats`, `GET /number-tracker`, `GET /pairs`, `GET /export`
- **predictions**: `POST /generate`, `POST /save`, `GET /history`, `POST /{id}/mark-used`, `DELETE /{id}`, `GET /strategies`, `GET /export`
- **evaluate**: `POST /new-draw`, `GET /prediction/{id}`, `GET /summary`
- **ml**: `GET /probabilities` (fuente `ensemble` o `model`; expone los pesos de los 15 modelos, sus puntajes y `n_draws`), `POST /train`, `POST /retrain`, `GET /status`, `GET /analytics`, `POST /score`
- **earnings**: `POST /estimate`, `POST /backtesting`
- **dashboard**: `GET /overview`, `GET /performance`
- **admin**: CRUD de usuarios, reseteo de contraseña
- **push**: `GET /vapid`, `POST /subscribe`, `POST /unsubscribe`, `POST /test`
- **assistant**: `POST /chat` (asistente en español con la API de Claude, que responde SOLO sobre estadística de la app y siempre recuerda que la lotería es azar)

### ⚠️ `POST /draws/grouped` — requisito especial
Melate, Revancha y Revanchita **comparten el mismo número de concurso y la misma fecha** (es el mismo sorteo físico). Debe existir un endpoint y una tarjeta en la UI que capture los **tres resultados de una sola vez**: se escribe el concurso y la fecha UNA vez, y luego los tres conjuntos de números (aceptando tanto selección de balotas como pegado de texto tipo "9 18 27 36 45 54"). Reporta errores por juego sin abortar los demás.

### Flujo crítico de aprendizaje (obligatorio)
Al dar de alta un sorteo oficial, en la misma transacción:
1. Evalúa TODAS las predicciones pendientes de ese juego, **de todos los usuarios**, y persiste los aciertos.
2. Actualiza el bandit contextual con el régimen que había ANTES de ese sorteo.
3. Re-evoluciona y persiste los pesos de los 15 modelos sobre el historial ampliado.
4. Reentrena el modelo ML.
5. Dispara notificación push a los usuarios con 2+ aciertos.

Al borrar un sorteo, revierte a "pendiente" las predicciones que solo se habían comparado contra él.

## 7. Frontend — iOS "Liquid Glass"

Estética: fondo oscuro con gradientes, tarjetas de vidrio esmerilado (`backdrop-blur`, bordes `white/10`, sombras suaves), navegación inferior flotante con blur, balotas animadas con gradiente por juego, transiciones con `active:scale-95`. Mobile-first, 100% responsive, tipografía con números tabulares.

Páginas: **Login, Register, ResetPassword, Dashboard, Predictions, Builder (constructor manual con puntuación en vivo), History, Draws, Analytics, Earnings, AssistantChat, Profile, AdminUsers, Legal**.

Componentes: `NumberBall, BallSelector, PositionalSelector` (para Tris), `GameSelector, StrategySelector, AddDrawModal` (con la pestaña 3-en-1), `NumberHeatmap, Charts` (SVG propio), `LiquidModal, BottomNav, AppLayout`, sistema de toasts.

Extras: **PWA** instalable con service worker, notificaciones push web, generación de **imagen compartible** de una combinación (canvas), selector de juego favorito persistido.

## 8. Seguridad

JWT con expiración, bcrypt para contraseñas, rate-limiting persistido en base de datos, validación estricta con Pydantic, CORS restringido a los dominios propios, rutas de admin protegidas por dependencia, Sentry opcional para errores.

## 9. Datos semilla

Voy a subir archivos CSV con el historial real (formato `CONCURSO,ID,R1..R7,BOLSA,FECHA,...`). Volúmenes aproximados: Melate 2,137 · Revancha 2,137 · Revanchita 1,852 · Melate Retro 1,639 · Chispazo 10,694 · Tris 25,115. Crea un seeder idempotente y con carga masiva (rápido en Postgres), más un usuario demo y un administrador.

## 10. Pruebas y calidad

Suite de pruebas con `pytest` + `TestClient` sobre una base SQLite temporal sembrada, cubriendo como mínimo: salud, autenticación y roles, validaciones, generación con las 10 estrategias, alta agrupada 3-en-1, borrado de sorteo con reversión, evaluación automática, ensamble (15 modelos, distribución normalizada) y **una prueba explícita de que al agregar un resultado se re-evolucionan los pesos, crece `n_draws` y se alimenta la memoria de errores**. Configura también un flujo de CI.

## 11. Criterios de aceptación

1. Los 6 juegos funcionan, y Tris cuenta aciertos **por posición** con repeticiones permitidas.
2. `GET /api/ml/probabilities?source=ensemble` devuelve **15 modelos** con pesos que suman 1, sus puntajes walk-forward y `n_draws`.
3. Agregar un sorteo oficial evalúa predicciones pendientes y **cambia los pesos** del ensamble.
4. La tarjeta 3-en-1 da de alta Melate + Revancha + Revanchita con un solo concurso y fecha.
5. El backtesting muestra siempre la comparación contra el azar.
6. La app funciona aunque falten xgboost/sklearn (degradación heurística).
7. Toda la interfaz está en español mexicano y la app nunca promete ganancias.

---

## Notas de uso

**Trabájalo por fases.** El Agente de Replit rinde mejor con entregas acotadas. Sugerencia:
1. Fase 1 — andamiaje: FastAPI + React + Tailwind + Postgres + auth JWT + modelo de datos + seeder con los CSV.
2. Fase 2 — juegos, sorteos, alta 3-en-1 y evaluación automática.
3. Fase 3 — motor: los 15 modelos, evolución de pesos, capa meta y optimizador de pool.
4. Fase 4 — estrategias, backtesting, ganancias, analíticas.
5. Fase 5 — UI Liquid Glass completa, PWA, push, asistente.

Para cada fase, pega la sección correspondiente de este prompt y pide pruebas antes de avanzar.

**Diferencias de plataforma:** el proyecto actual corre con backend en Railway y frontend en Vercel. En Replit va todo en un solo Repl con su PostgreSQL y sus Secrets; el despliegue es con Autoscale Deployment. Es el único ajuste real de arquitectura.

**Sobre expectativas:** el motor reproduce y amplía la lógica de "Melate Genius" con calibración sobre datos reales, pero el promedio de aciertos se mantiene en torno a la línea base del azar (≈0.64 aciertos por boleto en Melate). Cualquier reconstrucción honesta debe mostrar esa comparación en vez de ocultarla.
