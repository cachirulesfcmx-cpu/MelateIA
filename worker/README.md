# MelateAI Training Worker

Entrena los challengers de secuencia (LSTM, Transformer) y el circuito cuántico
**fuera del servicio HTTP**. El servicio web no lleva PyTorch: son cientos de MB
para modelos que no pueden entrenarse dentro de una petición.

## Uso

```bash
docker build -f worker/Dockerfile -t melateai-worker .
docker run --rm melateai-worker --game melate --model lstm
docker run --rm melateai-worker --game melate --model transformer
docker run --rm melateai-worker --game chispazo --model qnn
```

Sin Docker, desde la raíz del repositorio:

```bash
pip install -r worker/requirements.txt
python -m worker.main --game melate --model lstm
```

## Publicar el resultado en la app

```bash
python -m worker.main --game melate --model lstm --submit \
  --api https://melateia-production.up.railway.app \
  --token "<JWT de un administrador>"
```

Queda registrado como **Challenger** con la promoción bloqueada. Ningún
resultado del worker puede convertirse en Champion: eso exige superar
walk-forward, permutación, block bootstrap, corrección múltiple, Golden Holdout
y replicación independiente, que viven en el ciclo de investigación de la app.

## Sin PyTorch / PennyLane

El job devuelve `status: unavailable` y no inventa métricas.

## Nota sobre la métrica

La pérdida de validación **no acredita nada**: se minimiza prediciendo la tasa
base (6/56 en todos los números). Por eso el worker reporta además los aciertos
medios del boleto top-k frente al azar exacto, y marca `looks_like_base_rate`
cuando la red simplemente aprendió la frecuencia global.
