# Consolidador de Cuentas Corrientes

Aplicación de escritorio Windows (Python 3.11 + tkinter) que consolida los reportes
de cuentas corrientes de múltiples compañías de seguros en un único archivo Excel
maestro con formato uniforme, generado **desde cero**.

## Características

- GUI simple con `tkinter/ttk` para elegir carpeta origen, archivo destino y período.
- Detección automática de parser por nombre de archivo normalizado.
- Soporte para `.xlsx`, `.xls`, `.xls` HTML (Andina ART) y `.pdf`.
- Lectura flexible de números (formatos AR/US, paréntesis, signos al final, símbolos).
- Archivos no reconocidos: se ignoran y se registran en `summary.json`.
- Filas no interpretables: se envían a `rejected_rows.csv`.
- Log persistente en `process_log.txt`.
- Genera una única hoja `BASE` con encabezados estilizados, filas congeladas,
  autofiltro, formatos de fecha y moneda, y una fórmula autosuficiente de control
  de duplicados en la columna `Columna1`.

## Estructura del proyecto

```
/app
  main.py              # entrypoint (GUI o CLI)
  gui.py                # ventana tkinter
  controller.py         # orquestación
  config.py             # constantes: columnas, orden de compañías, mapping
  models.py             # dataclasses Record / ParseResult / RunSummary
  workbook_builder.py   # construye el .xlsx final desde cero
  validators.py         # invariantes y conteos esperados del lote de prueba
  utils/
    numbers.py, strings.py, dates.py, files.py, excel_styles.py, logging_utils.py
  parsers/
    base_parser.py      # utilidades comunes
    allianz.py, andina_art.py, asociart.py, experta_art.py, experta_sau.py,
    fedpat.py, galeno_life.py, galicia.py, integrity.py, la_holando.py,
    la_segunda_art.py, la_segunda_grales.py, la_segunda_personas.py,
    libra_pdf.py, mercantil_andina.py, parana_art.py, premiar.py,
    prevencion_art.py, provincia_art.py, san_cristobal.py, sancor.py,
    smg.py, smg_art.py, smg_life.py, victoria_art_pdf.py, zurich.py
/tests
requirements.txt
build.bat
README.md
```

## Requisitos

- Windows 10/11
- Python 3.11 (se recomienda usar el instalador oficial python.org)

## Instalación en desarrollo

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecución (GUI)

```powershell
python -m app.main
```

En la ventana:

1. **Carpeta de origen**: elegir la carpeta que contiene los archivos originales.
2. **Archivo Excel de salida**: elegir dónde guardar el `.xlsx` consolidado.
3. **Período**: formato `YYYY-MM` (por ejemplo `2026-03`).
4. **Procesar**: inicia la consolidación. Mientras corre se ve la barra de
   progreso y el log en vivo.
5. Al finalizar se habilita **Abrir carpeta de salida** y se muestra el resumen
   (total de filas, por compañía, archivos procesados, omitidos y rechazados).

En la carpeta de salida quedarán:

- `CUENTAS_CORRIENTES_CONSOLIDADO.xlsx` (o el nombre elegido) con la hoja `BASE`.
- `process_log.txt` con el log completo de la corrida.
- `rejected_rows.csv` con las filas descartadas.
- `summary.json` con el resumen estructurado.

## Ejecución por línea de comandos

```powershell
python -m app.main --no-gui --input "C:\...\CTAS CTES AUTOMATIZACION" --output "C:\tmp\out.xlsx" --period 2026-03
```

## Tests

```powershell
pip install pytest
pytest -q
```

Los tests cubren parseo numérico, detección de archivos, validadores,
construcción del workbook, fechas y una corrida mínima del controlador.

## Empaquetado (.exe)

Desde la raíz del proyecto:

```powershell
build.bat
```

El script:

1. Crea un entorno virtual `.venv` si no existe.
2. Instala dependencias desde `requirements.txt`.
3. Corre PyInstaller con `--onefile --noconsole --name Consolidador` apuntando a
   `app/main.py`.

El ejecutable queda en `dist\Consolidador.exe`.

## Reglas funcionales

- El workbook final se genera **desde cero**; no depende de ningún archivo
  maestro en tiempo de ejecución.
- Sólo se crea la hoja `BASE` con las columnas especificadas:
  `FECHA, POLIZA, ASEGURADO, SECCION, COMPAÑÍA, TIPO, COMISIONES, PRIMA, PREMIO,
   COMPROBACION DE DUPLICADOS, Columna1`.
- `FECHA` corresponde al primer día del período (ej. `2026-03` → `2026-03-01`).
- `COMPROBACION DE DUPLICADOS` queda vacía por diseño.
- `Columna1` contiene una fórmula `=IF(COUNTIF(rango_poliza, celda_poliza)>1,"VER","")`,
  autosuficiente dentro de la hoja `BASE`.
- Si una compañía no tiene parser implementado o el archivo no se puede
  interpretar con certeza, **no bloquea** la ejecución: se registra en
  `files_skipped` (archivo completo) o `rejected_rows.csv` (filas sueltas) y se
  continúa.

## Compañías soportadas

ALLIANZ, ANDINA ART, ASOCIART SA, EXPERTA ART, EXPERTA SAU, FEDERACION PATRONAL,
GALENO LIFE, GALICIA SEGUROS, INTEGRITY, LA HOLANDO (ART + GENERALES), LA SEGUNDA
ART / GENERALES / PERSONAS, LIBRA SEGUROS (PDF), MERCANTIL ANDINA (ARS + USD),
PREMIAR, PREVENCION ART, PROVINCIA ART, SAN CRISTOBAL (ARS + USD), SANCOR, SMG,
SMG ART, SMG LIFE, VICTORIA ART (PDF), ZURICH, PARANA ART (PDF).

Para VICTORIA ART: el PDF viene escaneado sin capa de texto. Si se configura la
API key de OpenAI (GUI sección 5, o `OPENAI_API_KEY` / `config/ocr.json`), cada
página se rasteriza y un modelo de visión lee la tabla automáticamente
(`app/utils/ocr.py`, usa la cuenta de OpenAI del cliente). Sin key, las filas se
rechazan con un motivo claro y se cargan a mano.

## Resolución de problemas

- **"Período inválido"**: revisar que sea `YYYY-MM` (ej. `2026-03`).
- **"Archivo omitido"**: el nombre del archivo no matchea ningún parser. Los
  parsers reconocen nombres como `ALLIANZ CTA CTE ...`, `SMG ART CTA CTE ...`,
  etc. Ver `app/config.py` → `PARSER_BY_FILE_KEY`.
- **Filas rechazadas**: abrir `rejected_rows.csv` para ver el motivo por fila.
- **Log completo**: `process_log.txt` en la misma carpeta que el Excel generado.
