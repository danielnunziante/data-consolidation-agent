# Reglas de Consolidación por Compañía

Documento de referencia sobre cómo el sistema procesa el archivo de cuenta corriente de cada compañía.  
**Objetivo:** Que el cliente pueda validar y corregir las reglas antes de avanzar a producción.

---

## Estructura del consolidado

Cada fila del consolidado tiene las siguientes columnas:

| Columna | Descripción |
|---|---|
| **FECHA** | Fecha del período procesado |
| **POLIZA** | Número de póliza o contrato |
| **ASEGURADO** | Nombre del tomador / razón social |
| **SECCION** | Ramo o sección de la póliza (**normalizada** a un vocabulario único — ver más abajo) |
| **COMPAÑÍA** | Nombre de la aseguradora |
| **TIPO** | `PR` = Productor · `AY` = Ayudante / Cobranzas · `IND` = Independiente |
| **COMISIONES** | Comisión neta |
| **PRIMA** | Prima técnica o base de cálculo |
| **PREMIO** | Premio cobrado |

---

## Normalización de la columna SECCION

Cada aseguradora nombra sus ramos de forma distinta: códigos numéricos (`4`,
`51`), abreviaturas (`Autos`, `Consor.`), o textos con prefijo (`09 -
AUTOMOTORES`, `001 Incendio`). Para que el consolidado quede homogéneo, después
de procesar todos los archivos el sistema **reemplaza el valor crudo de SECCION
por un nombre normalizado**, según una tabla de equivalencias por compañía.

- **Fuente de la tabla:** `Ejemplos Data/EQUIVALENCIAS.xlsx` (hoja `DATOS`, con
  columnas `CODIGO | COMPAÑÍA | SECCION`). Es la fuente que mantiene el cliente.
- **Cómo se aplica en el programa:** el Excel se convierte a un módulo Python
  (`app/utils/seccion_equivalencias.py`) con el script
  `scripts/build_equivalencias.py`. **Cada vez que el cliente actualiza el
  Excel hay que volver a correr ese script** y recompilar:
  ```bash
  python scripts/build_equivalencias.py
  ```
- **Matching tolerante:** ignora mayúsculas/minúsculas, espacios sobrantes y
  ceros a la izquierda en códigos numéricos (`01` = `1`). Las compañías USD
  reutilizan la tabla de su versión en pesos (ej.: `SAN CRISTOBAL USD` usa la de
  `SAN CRISTOBAL`).
- **Si un código no tiene equivalencia:** se conserva el valor crudo tal como
  venía (no se pierde información) y se lista en el `process_log.txt` bajo
  `SECCION: N filas sin equivalencia`, para poder completar la tabla.

### Override sin recompilar (opcional)

Para agregar o corregir equivalencias sin regenerar el ejecutable, se puede
crear `config/equivalencias_seccion.json` junto al programa. Pisa la tabla
incorporada. Formato:

```json
{
  "MERCANTIL ANDINA": { "51": "AUTOMOTORES" },
  "SANCOR": { "300": "ACCIDENTES PERSONALES" }
}
```

> ℹ️ Algunos valores ya vienen en forma canónica desde el parser (fijos como
> `A.R.T.`, `CAUCION`, `PREPAGA MEDICA`, o las secciones ya normalizadas de
> `QBE-ZURICH`) y por eso aparecen "sin equivalencia" pero quedan correctos. El
> caso a revisar es `LA HOLANDO GENERALES`, cuya SECCION hoy trae el nombre del
> asegurado en vez del ramo (limitación del parser, no de esta tabla).

---

## Reglas por compañía

---

### ALLIANZ

- **Archivo:** Excel (.xlsx), hoja `Sheet1`
- **POLIZA:** columna `Nro Poliza`
- **ASEGURADO:** columna `Asegurado`
- **SECCION:** columna `Seccion`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Comisiones Devengadas`
- **PRIMA:** columna `Prima`
- **PREMIO:** columna `Premio`

> ⚠️ **Pendiente de verificación:** En el procesamiento de Abril 2026 esta compañía no generó filas. Puede deberse a un cambio de formato en el archivo mensual. Confirmar que el archivo sigue teniendo las columnas `Nro Poliza`, `Asegurado`, `Seccion`, `Comisiones Devengadas`.

---

### ANDINA ART

- **Archivo:** `.xls` con contenido HTML
- **POLIZA:** columna `Poliza`
- **ASEGURADO:** columna `Razon Social`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Comision $`. Si viene vacía, se calcula como `Prima × 5%`
- **PRIMA:** columna `Prima Cobrada`
- **PREMIO:** igual a `Prima Cobrada`

> ⚠️ **Pendiente de verificación:** Confirmar si el cálculo de comisión como `5% de la prima` es siempre correcto o sólo como fallback cuando la columna viene vacía.

---

### ASOCIART SA

- **Archivo:** Excel (.xlsx), hoja `Listado`
- **POLIZA:** columna `Contrato`
- **ASEGURADO:** columna `Razon Social`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Productor/AI` dividida por 1.21 (se descuenta el IVA)
- **PRIMA:** columna `Prima Recaudada`
- **PREMIO:** igual a `Prima Recaudada`

---

### ATM

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `PÓLIZA`
- **ASEGURADO:** columna `NOMBRE TOMADOR`
- **SECCION:** columna `RAMA`
- **TIPO:**
  - `AY` si la columna `TIPO DE LIQUIDACION` contiene el texto `"ONE SHOT"`
  - `PR` en todos los demás casos
- **COMISIONES:** suma de `MONTO COMISION S/PREMIO` + `MONTO COMISION S/PRIMA` (aplica para PR y AY)
- **PRIMA:** columna `PRIMA COBRADA` (vacío para filas AY)
- **PREMIO:** columna `PREMIO COBRADO` (vacío para filas AY)

---

### BERKLEY ART

- **Archivo:** PDF
- **POLIZA:** columna `NRO CONTRATO`
- **ASEGURADO:** columna `RAZON SOCIAL`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `$ COMISION` dividida por 1.21 (se descuenta el IVA)
- **PRIMA:** columna `RECAUDADO`
- **PREMIO:** igual a `RECAUDADO`

> ⚠️ Si el PDF es escaneado (sin texto seleccionable), la extracción automática no funciona y requiere carga manual.

---

### BERKLEY GENERALES

- **Archivo:** PDF
- **POLIZA:** columna `POLIZA`
- **ASEGURADO:** columna `ASEGURADO`
- **SECCION:** columna `SECCION` / `RAMO` si existe; si no, fijo `CAUCION`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `COMISION POR VTA`
- **PRIMA:** columna `PRIMA PROPORC.`
- **PREMIO:** columna `PREMIO COBRADO`

> ⚠️ Confirmar: ¿los movimientos de Berkley Generales son siempre cauciones?

---

### EXPERTA ART

- **Archivo:** Excel (.xlsx), hoja con nombre que contiene `Reporte` y `Comis`
- **Filtro:** sólo se toman las filas donde `Tipo de Participacion` = `PROD`
- **POLIZA:** columna `N° de Póliza`
- **ASEGURADO:** columna `Razon Social`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Importe` dividida por 1.21 (se descuenta el IVA)
- **PRIMA:** columna `Base Calculo`
- **PREMIO:** igual a `Base Calculo`

---

### EXPERTA SAU

- **Archivo:** Excel (.xlsx), hoja con nombre que contiene `Reporte` y `Comis`
- **POLIZA:** columna `N° de Póliza`
  - Pólizas de 8 dígitos (excepto ramo `FLOTA`): se toman los primeros 6 y se agrega el sufijo `01` (ej: `12345601`)
- **ASEGURADO:** columna `Razon Social`
- **SECCION:** columna `Ramo`
- **TIPO:**
  - `PR` si `Tipo de Participacion` = `PROD`
  - `AY` si `Tipo de Participacion` = `ORG` y el productor contiene `"COBERTURAS"`
  - `IND` si `Tipo de Participacion` = `ORG` y el productor **no** contiene `"COBERTURAS"`
- **COMISIONES:** columna `Importe (AR$)` (si no existe, se calcula como `Prima × % de comisión`)
- **PRIMA:** columna `Prima` (sólo para `PR`; vacío para `AY` e `IND`)
- **PREMIO:** columna `Premio` (sólo para `PR`; vacío para `AY` e `IND`)

> ⚠️ **Pendiente de verificación:** Para la póliza 592 (Ramo Consor.) de Abril 2026 la prima generada no coincidió con el manual. Confirmar si hay una columna de prima diferente para el ramo consorcio.

---

### FEDERACIÓN PATRONAL

- **Archivo:** Excel (.xlsx), hoja `Libro1`
- Por cada póliza se generan **2 filas**:
- **Fila PR:**
  - POLIZA: columna `Póliza`
  - ASEGURADO: columna `Asegurado`
  - SECCION: columna `Ramo`
  - TIPO: `PR`
  - COMISIONES: columna `Comisión normal`
  - PRIMA: columna `Prima`
  - PREMIO: columna `Premio`
- **Fila AY:**
  - TIPO: `AY`
  - COMISIONES: suma de `Comisión cobranza` + `Comisión fomento`
  - PRIMA / PREMIO: vacío

---

### GALENO LIFE

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `Contrato/Póliza` (se extrae la parte numérica, sin ceros a la izquierda)
- **ASEGURADO:** columna `Cliente/Razón Social`
- **SECCION:** columna `Producto`
- **TIPO:** se determina por las columnas de comisión:
  - Si hay `Comisión Legajo` ≠ 0 → se genera fila `PR`
  - Si además hay `Comis Organizador` ≠ 0 → se genera también fila `AY`
  - Si sólo hay `Comis Organizador` ≠ 0 (sin legajo) → se genera fila `IND`
- **COMISIONES:** `Comisión Legajo` (para PR) o `Comis Organizador` (para AY/IND)
- **PRIMA:** columna `Importe Cobranzas`
- **PREMIO:** `Prima × 1.40`

> ⚠️ **Pendiente de verificación:** Confirmar el criterio cuando ambas comisiones existen pero alguna es cero.

---

### GALICIA SEGUROS

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `Poliza`
- **ASEGURADO:** columna `Detalle` (se excluyen filas con `Detalle` = "SALDO ANTERIOR")
- **SECCION:** columna `Sc`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `ComisionBruta`
- **PRIMA:** columna `PrimaTecnica`
- **PREMIO:** columna `Premio`

---

### HDI

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `POLIZA` exacta (no `Sup. Poliza`)
- **ASEGURADO:** columna `ASEGURADO`
- **SECCION:** columna `NOMBRE RAMA`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `COMISION EN MONEDA CTE` (ya en pesos, no se convierte)
- **PRIMA:** columna `PRIMA PROPORCIONAL`
- **PREMIO:** columna `PREMIO`
- **Conversión USD:** si la columna `MONEDA` indica USD, el tipo de cambio se calcula automáticamente como `Comisión (pesos) / Comisión (USD)` y se aplica a prima y premio

> ⚠️ Si una fila USD no tiene par de comisiones (pesos + USD) para deducir el TC, se rechaza la fila. Confirmar cómo proceder en ese caso.

---

### INTEGRITY

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `Poliza`
- **ASEGURADO:** columna `NombreAsegurado`
- **SECCION:** columna `Seccion`
- **TIPO:**
  - `PR` si `TipoComision` = `BASICA`
  - `AY` si `TipoComision` = `EXTRA`
- **COMISIONES:** columna `Comision`
- **PRIMA:** columna `Prima` (sólo para PR; vacío para AY)
- **PREMIO:** columna `Importe` (sólo para PR; vacío para AY)
- **Conversión USD:** si la columna `Moneda` indica USD, se multiplica por el tipo de cambio configurado en `config/fx.json` bajo la clave `"INTEGRITY"`

> ⚠️ **Requiere configuración:** el tipo de cambio USD debe cargarse en `config/fx.json` antes de procesar. Si no está configurado, las filas USD se rechazan.

---

### LA HOLANDO ART

- **Archivo:** Excel (.xlsx), misma hoja que LA HOLANDO GENERALES (se distingue por la columna `Rama`)
- **Filtro:** filas con `Rama` = `ART`
- **POLIZA:** se extrae el primer número de la columna `NroOperacion` (ej: de `"R.T.- 0000217202- 2602006"` se toma `"217202"`)
- **ASEGURADO:** columna `Detalle Operacion`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Com.Bruta`
- **PRIMA:** columna `PrimaComisionable`
- **PREMIO:** columna `PremioComisionable`

---

### LA HOLANDO GENERALES

- **Archivo:** Excel (.xlsx), misma hoja que LA HOLANDO ART
- **Filtro:** filas con `Rama` ≠ `ART`
- **POLIZA:** igual que LA HOLANDO ART (primer número de `NroOperacion`)
- **ASEGURADO:** columna `Detalle Operacion`
- **SECCION:** columna `Detalle Operacion` (mismo valor que ASEGURADO)
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Com.Bruta`
- **PRIMA:** columna `PrimaComisionable`
- **PREMIO:** columna `PremioComisionable`

> ℹ️ Se ignoran las filas donde `PrimaComisionable` y `PremioComisionable` son ambas cero o vacías (movimientos administrativos sin póliza real).

---

### LA SEGUNDA ART

- **Archivo:** Excel (.xlsx), hoja con nombre numérico (ej: `73059`)
- **POLIZA / ASEGURADO:** la columna `Cont/Sin Razon Social` puede venir en dos formatos:
  - Separados en columnas: columna 0 = número de contrato, columna 1 = razón social
  - Combinados en columna 0 como `"145487 RAZON SOCIAL"`: el sistema los separa automáticamente
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Comisiones`
- **PRIMA:** columna `Prima`
- **PREMIO:** igual a `Prima`

---

### LA SEGUNDA GENERALES

- **Archivo:** Excel (.xlsx)
- Por cada póliza se generan **hasta 2 filas**:
- **Fila PR:**
  - POLIZA: columna `Ref`
  - ASEGURADO: columna `Asegurado`
  - SECCION: columna `Seccion`
  - TIPO: `PR`
  - COMISIONES: columna `Com.Prima MC` (o `Com.Prima`)
  - PRIMA: columna `Prima`
  - PREMIO: columna `Premio`
- **Fila AY** (sólo si `Com.s/premio` ≠ 0):
  - TIPO: `AY`
  - COMISIONES: columna `Com.s/premio`
  - PRIMA / PREMIO: vacío
- **Conversión USD:** si la columna `Mon` indica USD, se calcula el TC como `Com.MC pesos / Com.MC USD` y se aplica a prima y premio

---

### LA SEGUNDA PERSONAS

- Utiliza las mismas reglas que **LA SEGUNDA GENERALES**
- El nombre de compañía en el consolidado es `LA SEGUNDA PERSONAS`

---

### LIBRA SEGUROS

- **Archivo:** PDF con texto estructurado en líneas
- Cada línea sigue el formato: `FECHA SUC RAMO POLIZA END TOMADOR PR $ TIPO números...`
- **POLIZA:** 4to campo numérico de la línea
- **ASEGURADO:** campo `TOMADOR`
- **SECCION:** campo `RAMO` (código numérico de 2 dígitos)
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** primer número de la parte final de la línea
- **PRIMA / PREMIO:** se extraen desde la parte final contando posiciones desde la derecha

---

### MERCANTIL ANDINA (pesos)

- **Archivo:** Excel (.xlsx) — listado contable
- La columna `DESCRIPCION` tiene el formato `"516367856 0002 Cta 01 Po/Pa importe-SUFIJO"` donde el sufijo es `PR`, `AY` o `CB`
- **POLIZA:** se aplica una tabla de truncado según el prefijo numérico de la póliza:

| Prefijos | Dígitos a conservar (por derecha) |
|---|---|
| 4, 6, 9, 13, 14, 16, 17, 18, 19, 30 | 7 |
| 35 | 6 |
| 51 | 8 |

- **SECCION:** el prefijo de la póliza (1 o 2 dígitos)
- **ASEGURADO:** columna `ASEGURADO`
- **TIPO según sufijo:**
  - `PR` → fila TIPO=PR con prima y premio
  - `AY` o `CB` → fila TIPO=AY sin prima/premio
- **COMISIONES:** columna `HABER`
- **PRIMA (para PR):** importe numérico embebido en la descripción (campo "Pa")
- **PREMIO (para PR):** prima + importe del movimiento complementario "CB" si existe; si no, igual a prima

---

### MERCANTIL ANDINA USD

- Mismas reglas de extracción que **MERCANTIL ANDINA**
- El nombre de compañía es `MERCANTIL ANDINA USD`
- Todos los valores se multiplican por el tipo de cambio configurado en `config/fx.json` bajo la clave `"MERCANTIL ANDINA"`

> ⚠️ **Requiere configuración:** el tipo de cambio USD debe cargarse en `config/fx.json` antes de procesar.

---

### PARANA ART

- **Archivo:** PDF con tablas
- Se identifican las filas por CUIT (11 dígitos) en la primera columna
- **POLIZA:** posición fija 5 (columna `PD`)
- **ASEGURADO:** posición fija 1 (Razón Social)
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** posición fija 14 (`Comision PAS`)
- **PRIMA / PREMIO:** posición fija 13 (`Prima Cobrada`)

---

### PREMIAR

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `Poliza / Endoso` — si contiene `/`, se toma sólo la parte antes del `/`
- **ASEGURADO:** columna `Tomador`
- **SECCION:** fijo `CAUCION`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Comisión pagada $`
- **PRIMA:** columna `Prima $` (o `Prima Tarifa $`)
- **PREMIO:** `Prima × 1.40`

---

### PREVENCIÓN ART

- **Archivo:** Excel (.xlsx), dos hojas: `152526` (AY) y `213871` (PR)
- **POLIZA:** columna `Contrato`
- **ASEGURADO:** columna `DenominaciónCliente`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `AY` para hoja `152526` / `PR` para hoja `213871`
- **COMISIONES:** columna `ImporteComisión` dividida por 1.21 (se descuenta el IVA)
- **PRIMA / PREMIO:** columna `ImporteBase` (sólo para PR; vacío para AY)

---

### PROVINCIA ART

- **Archivo:** Excel (.xlsx), hoja `Movimientos`
- **Filtro:** sólo filas con `CONCEPTO` = `COMISIONES`
- **POLIZA:** columna `CONTRATO`
- **ASEGURADO:** columna `RAZÓN SOCIAL`
- **SECCION:** fijo `A.R.T.`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `MONTO LIQUIDADO`
- **PRIMA / PREMIO:** columna `COBRADO NETO IMPUESTOS`

---

### QBE-ZURICH

- **Archivo:** Excel (.xlsx)
- **POLIZA:** extracción según prefijo (en orden de evaluación):

| Prefijo | Fuente | Regla |
|---|---|---|
| `AMM` | columna `CERTIF` | Últimos 5 dígitos; si el 5to por derecha es `0`, sólo 4 |
| `AUS` | columna `CERTIF` | Últimos 6 dígitos |
| `AMT`, `AUT1`, `CON`, `HOC`, `ICQ` | columna `POLIZA` (después del prefijo) | Sin ceros a la izquierda |
| Otros | columna `POLIZA` | Como viene |

- Regla general adicional: si la póliza resultante tiene exactamente 7 dígitos, se recorta a los 6 de la derecha
- **ASEGURADO:** columna `ASEGURADO`
- **SECCION:** columna `SECCION` / `RAMO`
- **TIPO:**
  - `PR` si el campo `PRODUCTOR` ≠ `OR`
  - `IND` si `PRODUCTOR` = `OR` (por defecto; configurable a `AY` póliza por póliza)
- **COMISIONES:** columna `COMISION`
- **PRIMA:** columna `PRIMA` (vacío para IND/AY)
- **PREMIO:** columna `PREMIO` (vacío para IND/AY)
- **Regla de signos:** si la comisión es negativa, prima y premio se vuelven negativas también

> ⚠️ **Pendiente de verificación:** Cuando el productor dice `"OR"`, el sistema marca por defecto `IND`. Confirmar si hay pólizas propias de Coberser que deberían marcarse como `AY` en lugar de `IND`.

---

### SAN CRISTOBAL (pesos)

- **Archivo:** Excel (.xlsx), dos hojas: `Comisiones PAS` y `Comisiones ORG`
- **POLIZA:** columna `N° DE PÓLIZA` — se conserva sólo la parte numérica más larga (ej: de `"01-05-01-32106279"` se toma `"32106279"`)
- **ASEGURADO:** columna `CLIENTE`
- **SECCION:** columna `RAMO`
- **TIPO:**
  - Hoja `Comisiones PAS` → `PR`
  - Hoja `Comisiones ORG` → `AY` si el nombre PAS contiene `"COBERTURAS"` o `"COBERSER"`, caso contrario `IND`
- **COMISIONES:** columna `COMISIÓN`
- **PRIMA:** columna `PRIMA` (sólo para PR; vacío para AY/IND)
- **PREMIO:** columna `PREMIO` (sólo para PR; vacío para AY/IND)
- **Regla de signos:** si la prima es negativa (devolución), el premio se vuelve negativo también

---

### SAN CRISTOBAL USD

- Mismas reglas de extracción que **SAN CRISTOBAL**
- El nombre de compañía es `SAN CRISTOBAL USD`
- Todos los valores se multiplican por el tipo de cambio configurado en `config/fx.json` bajo la clave `"SAN CRISTOBAL"`

> ⚠️ **Requiere configuración:** el tipo de cambio USD debe cargarse en `config/fx.json` antes de procesar.

---

### SANCOR

- **Archivo:** Excel (.xlsx), dos hojas conocidas: `152526` (IND) y `213871` (PR + AY)
- **POLIZA:** columna `Nro Oficial Poliza`
- **ASEGURADO:** columna `Denominacion Cliente`
- **SECCION:** columna `Ramo`

**Hoja `152526` → IND:**
- TIPO: `IND`
- COMISIONES: columna `Comision` (si viene vacía, se usa `Adic Extra Red`)
- PRIMA / PREMIO: vacío
- Se omiten filas con comisión = 0

**Hoja `213871` → PR + AY:**
- Por cada póliza se generan **2 filas**:
  - Fila PR: TIPO=`PR`, COMISIONES=`Comision`, PRIMA=`Prima Unif`, PREMIO=`Premio Cap`
  - Fila AY: TIPO=`AY`, COMISIONES=`Adic Cobranza` (se incluye aunque sea 0)

> ℹ️ Si el archivo tiene hojas adicionales con la misma estructura que `213871`, se procesan como PR + AY también.

---

### SMG

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `Nro_pol`
- **ASEGURADO:** columna `Txt_nombre`
- **SECCION:** columna `Cod_ramo`
- Por cada póliza se generan **hasta 2 filas**:
  - Fila PR: TIPO=`PR`, COMISIONES=`Imp_comis_normal_eq`, PRIMA=`Imp_prima`, PREMIO=`Imp_premio`
  - Fila AY (sólo si `Comision_cobranzas` ≠ 0): TIPO=`AY`, COMISIONES=`Comision_cobranzas`, PRIMA/PREMIO vacío
- **Deduplicación USD:** cuando existe una fila en USD (`Cod_moneda = 1`) y otra en pesos para la misma póliza, se descarta la fila USD y se conserva la de pesos

---

### SMG ART

- **Archivo:** Excel (.xlsx) con **2 bloques** de datos bajo encabezados `"Productor: COBERTURAS..."`:
  - **Bloque 1** (`COBERTURAS y SERVICIOS S.A`): genera filas `PR`
  - **Bloque 2** (`COBERTURAS Y SERVICIOS SA/B`): genera filas `IND` — pero sólo para pólizas que **no** aparecieron en el Bloque 1 (para evitar duplicados)
- **POLIZA:** columna `Contrato`
- **ASEGURADO:** columna `Cliente`
- **SECCION:** fijo `A.R.T.`
- **COMISIONES:** columna `Com. Prod.` (para Bloque 1) o `Com. Org.` (según qué columna tenga valores)
- **PRIMA / PREMIO:** columna `Importe (3)`

---

### SMG LIFE

- **Archivo:** Excel (.xlsx)
- **POLIZA:** se extrae del campo `Póliza` con formato tipo `"CVO9-0-41695-99-0-45132-0"` → se toma el **tercer segmento** separado por `-` (en el ejemplo: `41695`)
- **SECCION:** se toma el **primer segmento** del mismo campo (en el ejemplo: `CVO9`)
- **ASEGURADO:** columna `Asegurado`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** columna `Comisión` dividida por 1.21 (se descuenta el IVA)
- **PRIMA:** columna `Base cálculo`
- **PREMIO:** `Prima × 1.40`
- **Conversión USD:** si la columna `Moneda` indica USD, se multiplica prima por la columna `Cotizacion`

---

### VICTORIA ART

- **Archivo:** PDF (en la práctica **siempre escaneado**, sin capa de texto: cada
  página es una imagen CCITT G4).
- **Paso 1 — texto:** si el PDF trae texto seleccionable, se extrae línea por línea
  (`POLIZA ASEGURADO PRIMA COMISION`).
- **Paso 2 — OCR por visión (OpenAI):** si no hay texto, cada página se rasteriza
  y se envía a un modelo de visión de OpenAI que lee la tabla
  (`RESUMEN CUENTA CORRIENTE PRODUCTORES`) y la devuelve como JSON. Ver
  `app/utils/ocr.py`. **Es opcional**: requiere la API key de OpenAI del cliente
  (se carga en la GUI, sección 5, o vía `OPENAI_API_KEY` / `config/ocr.json`). Sin
  key, las filas se rechazan con un motivo claro y se cargan a mano.
- **Mapeo de columnas** (calibrado contra la base manual ABRIL/MAYO 2026):
  - **POLIZA:** columna `Póliza`, sin ceros a la izquierda
  - **ASEGURADO:** `Asegurado s/o Detalle`
  - **SECCION:** fijo `A.R.T.`
  - **TIPO:** `PR` para todos
  - **COMISIONES:** `Imp. Bruto Comisiones`
  - **PRIMA:** `Prima Cobrada`
  - **PREMIO:** `Premio Cobrado`

> ⚠️ Inconsistencia del cliente: en MAYO usó `PREMIO = Premio Cobrado` (lo que
> extraemos), pero en ABRIL copió `PREMIO = Prima Cobrada`. El parser toma siempre
> la columna real `Premio Cobrado`; ABRIL puede diferir por esto.

---

### ZURICH

- **Archivo:** Excel (.xlsx)
- **POLIZA:** columna `POLIZA` — se conserva la parte numérica completa tal como viene
- **ASEGURADO:** columna `Apellido y Nombre del Cliente`
- **SECCION:** columna `Sección`
- **TIPO:** `PR` para todos los registros
- **COMISIONES:** valor absoluto de la columna `Comisión Pesos`
- **PRIMA:** valor absoluto de la columna `Prima Técnica`
- **PREMIO:** `Prima × 1.40`

---

## Configuración de tipos de cambio (USD)

Las compañías que manejan cuentas en dólares requieren que el tipo de cambio del mes se configure manualmente antes de procesar. El archivo de configuración es `config/fx.json`:

```json
{
  "SAN CRISTOBAL": 1234.56,
  "MERCANTIL ANDINA": 1234.56,
  "INTEGRITY": 1234.56
}
```

> Reemplazar `1234.56` con el TC correspondiente al mes en proceso.

---

## Compañías que requieren carga manual (PDF no automatizable)

Las siguientes compañías envían PDFs escaneados o con formato libre que el sistema no puede leer automáticamente. Sus datos deben cargarse manualmente en el consolidado:

- **LIBRA SEGUROS** (PDF estructurado — funciona si el texto es seleccionable)
- **PARANA ART** (PDF — funciona si tiene tablas extraíbles)
- **VICTORIA ART** (PDF frecuentemente escaneado — generalmente manual)
- **BERKLEY ART** (PDF — funciona si tiene tablas extraíbles)
- **BERKLEY GENERALES** (PDF — funciona si tiene tablas extraíbles)

---

*Documento generado el 01/06/2026. Para corregir o actualizar alguna regla, comunicarse con el equipo de desarrollo.*
