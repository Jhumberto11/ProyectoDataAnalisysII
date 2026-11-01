# Metodología de preparación y limpieza de datos

**Proyecto:** Brecha digital y condición de pobreza en los hogares salvadoreños  
**Fuente:** EHPM 2025; archivo de trabajo `Base de datos EHPM 2025.sav` del proyecto original.  
**Unidad de análisis:** hogar  
**Producto final:** `dataset_Brecha_Digital_Proyecto.csv`

## 1. Resumen ejecutivo

El objetivo de esta fase fue organizar un archivo que todos los integrantes puedan utilizar de manera consistente para construir el cuadro de mando. El proyecto original contiene una base SPSS de 56,463 registros y 693 variables. Para estudiar acceso a internet, disponibilidad de computadora y pobreza se seleccionaron diez variables de origen y se trabajó con un registro por hogar. Así se obtuvieron **17,909 hogares únicos**. Tras la verificación y transformación, el CSV final contiene **18 variables**, no tiene valores nulos y no contiene identificadores de hogares duplicados.

La base supera el mínimo indicado de 5,000 filas. Por lo tanto, **no es necesario sustituir el dataset por problemas de tamaño**. La consigna facilitada no explica qué es "Modalidad A" o "Modalidad B"; por eso la identificación formal queda pendiente de cotejar con el enunciado completo, sin inventar definiciones.

## 2. Procedencia de los datos y trazabilidad

La base principal del grupo procede del archivo `Base de datos EHPM 2025.sav`. El notebook `EHPM_2025_Brecha_Digital_Proyecto.ipynb` incluye el tratamiento inicial: selección de columnas, reducción a un hogar por boleta, revisión de nulos y transformación de variables. en esta entrega se tomo el mismo archivo .sav en `fuente_principal/Base_EHPM_2025.sav` y se ejecutó de nuevo el pipeline para producir el CSV final, auditando los resultados. El .sav es la versión cruda, esto para verificar el funcionamiento del pipeline

El pipeline incluye la de lectura del `.sav` si se instala `pyreadstat` y se dispone de ese archivo

## 3. Selección de variables y unidad de análisis

Se conservaron las diez columnas base:

`idboleta`, `fac00`, `area`, `region`, `r004`, `pobreza`, `ingpe`, `r3213a`, `r32309a` y `r32309b`.

`idboleta` permite identificar hogares; `fac00` es el factor de expansión; `area`, `region`, `r004` identifican localización; `pobreza` representa condición económica; `ingpe` corresponde al ingreso per cápita; las últimas tres variables indican acceso a internet, tenencia de computadora y cantidad de computadoras.

La base original contiene varios miembros por hogar. Dado que las preguntas principales se refieren al hogar, el procedimiento emplea un único registro por `idboleta`. La versión nueva verifica además que las columnas domésticas sean coherentes entre filas repetidas antes de desduplicarlas, para evitar eliminar información contradictoria sin advertirlo. El CSV final contiene una fila por hogar.

## 4. Limpieza y revisión de calidad

**Paso 1: tipos de datos.** Se convierten a numérico el identificador, factor de expansión, ingreso y número de computadoras. `idboleta` se guarda como entero y debe ser único. Se comprueba que el factor `fac00` sea positivo y que las cantidades de computadoras sean enteras no negativas.

**Paso 2: textos.** Se eliminan espacios duplicados y de los extremos; se unifican las respuestas a `Sí` y `No`, las categorías de área a `Urbano` y `Rural` y las de pobreza a `No pobre`, `Pobreza relativa` y `Pobreza extrema`. No se crean departamentos ni regiones ficticios.

**Paso 3: coherencia.** Se verifica que un hogar marcado `No` en computadora tenga cantidad cero, y que un hogar marcado `Sí` tenga al menos una computadora.

**Paso 4: faltantes.** Se distinguen faltantes estructurales de faltantes verdaderos. En el notebook original, la variable `r32309b` (cantidad de computadoras) presentaba **9,177 ausencias**, asociadas a respuestas `No` en tenencia de computadora. Esos faltantes se representan como **0 equipos**, una regla coherente con la pregunta. Si existieran cantidades faltantes entre quienes sí tienen computadora, el pipeline permitiría imputar la mediana del subgrupo, identificando la cantidad imputada en el reporte; en el CSV actual no se aplicó esa sustitución nueva. Si falta `ingpe`, se utiliza la mediana; en el archivo actual **no hizo falta imputar ingresos**. Las respuestas de acceso y las variables `area` o `pobreza` no se imputan automáticamente porque inventarían condiciones de los hogares

**Paso 5: valores atípicos.** Para ingreso se usa la regla intercuartílica (IQR): Q1 = 111.855 y Q3 = 324.0825, IQR = 212.2275; límite superior = 642.42375. El procedimiento identifica **1,033 hogares** por encima del umbral (5.77 %). No los elimina ni modifica el ingreso original `ingpe`. En `INGPE_LIMPIO` se guarda una versión limitada del ingreso **solo como alternativa auxiliar**, para visualizar sensibilidad o usar en transformaciones. No se debe presentar `INGPE_LIMPIO` como ingreso real sin aclarar el recorte.

## 5. Transformación y estandarización

Se agregan las variables derivadas:

- `INTERNET_SI_NO`: `Sí` se transforma a 1, `No` a 0.
- `COMPUTADORA_SI_NO`: tenencia de computadora en 1/0.
- `BRECHA_DIGITAL`: vale 0 solo si un hogar tiene internet **y** computadora; de otro modo vale 1. Esta es una definición operacional, no un indicador oficial.
- `es_outlier_ingreso`: señala los ingresos fuera de los límites del IQR.
- `INGPE_LIMPIO`: ingreso auxiliar limitado por IQR, manteniendo intacto `ingpe`.
- `LOG_INGPE`: logaritmo natural de `1 + INGPE_LIMPIO`.
- `INGPE_ESCALADO` y `PC_ESCALADO`: transformaciones de escalado robusto, `(x - mediana) / (Q3 - Q1)`; si el IQR es cero, se usa denominador 1. El escalado facilita análisis posteriores y no cambia los indicadores originales.

La entrega conserva los nombres de columnas del CSV anterior para ser compatible con el código del dashboard. No se incluyen columnas one-hot en este CSV porque las variables `area` y `pobreza` deben conservarse legibles para filtros y segmentación; un modelo estadístico posterior puede codificarlas cuando corresponda.

## 6. Comprobaciones de salida

| Control | Resultado observado |
| --- | ---: |
| Filas del CSV limpio | 17,909 |
| Columnas | 18 |
| Hogares identificados por `idboleta` | 17,909 |
| Identificadores duplicados | 0 |
| Valores nulos en las 18 variables | 0 |
| Respuestas internet Sí (muestra) | 7,840 |
| Respuestas computadora Sí (muestra) | 8,732 |
| Ingresos marcados como atípicos (IQR) | 1,033 |
| Porcentaje muestral de hogares con internet | 43.78 % |
| Porcentaje descriptivo ponderado con `fac00` | 46.13 % |

La diferencia entre 43.78 % (sin pesos) y 46.13 % (ponderado) justifica la necesidad de emplear `fac00` en porcentajes agregados. **La ponderación es descriptiva**: esta fase no valida el diseño completo de muestreo ni calcula errores estándar o intervalos de confianza.

## 7. Limitaciones y decisiones para el equipo

1. Se analiza el año 2025 y no se dispone de una serie temporal en este archivo.
2. Las asociaciones entre pobreza, territorio y acceso digital no demuestran relaciones de causa y efecto.
3. `BRECHA_DIGITAL` define ausencia de por lo menos uno de dos recursos, no ausencia de ambos.
4. Para resultados sobre ingresos y tableros usar `ingpe`; reservar `INGPE_LIMPIO` y escalados para análisis auxiliares.


## 8. Instrucciones de reproducción

Desde la carpeta principal del paquete (un nivel arriba de `documentos/`), en Bash o terminal compatible:

```bash
WINDOWS

python -m pip install -r codigo/requirements.txt
python codigo/limpiar_datos.py \
  --entrada fuente_principal/Base_EHPM_2025.sav \
  --salida DatosLimpios/dataset_Brecha_Digital_Prueba1.csv \
  --reporte documentos/reporte_calidad_prueba.json
python codigo/probar_entrega.py \
  DatosLimpios/dataset_Brecha_Digital_Prueba1.csv

MAC OS

python3 codigo/limpiar_datos.py \
  --entrada fuente_principal/Base_EHPM_2025.sav \
  --salida DatosLimpios/dataset_Brecha_Digital_Prueba1.csv \
  --reporte documentos/reporte_calidad_prueba.json
python3 codigo/probar_entrega.py \
  DatosLimpios/dataset_Brecha_Digital_Prueba1.csv


```

## 9. Cuadro de mando (Fase II)

La aplicación interactiva está en `dashboard/`. Para ejecutarla:

```
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Instrucciones de publicación en Streamlit Cloud y decisiones de diseño: ver `dashboard/README.md`.
