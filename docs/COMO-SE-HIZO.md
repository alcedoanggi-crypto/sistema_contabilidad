# Cómo se hizo — Sistema de Contabilidad

Guía paso a paso de la construcción del sistema, en el orden en que se hizo y con el porqué de cada decisión.

---

## Paso 1. Definir las reglas antes que las pantallas

Un sistema contable vale lo que valen sus reglas. Antes de programar se fijaron cuatro principios:

1. **Partida doble**: en toda póliza la suma del debe es igual a la del haber.
2. **Inmutabilidad**: lo contabilizado no se edita ni se borra; se corrige con una póliza de reversa.
3. **Periodos cerrados**: un mes cerrado no admite ningún cambio.
4. **Dinero exacto**: nunca `float`; siempre decimales exactos.

Y una decisión de arquitectura: **las reglas viven en PostgreSQL** (triggers y funciones), no solo en Python. Así se cumplen aunque alguien use otra aplicación o SQL directo.

## Paso 2. Servidor de base de datos propio

Se creó un servidor PostgreSQL 15 independiente (puerto 5433) con los programas de PostgreSQL ya instalados, sin Docker:

```bash
initdb -D C:\Users\usuario\pgdata-contabilidad -U contabilidad -A scram-sha-256 -E UTF8
pg_ctl -D C:\Users\usuario\pgdata-contabilidad -l servidor.log start
createdb -p 5433 -U contabilidad contabilidad
createdb -p 5433 -U contabilidad contabilidad_test
```

## Paso 3. El esquema (`backend/sql/001_esquema.sql`)

Tablas principales:

| Tabla | Para qué |
|---|---|
| `cuentas` | Catálogo jerárquico: código (`1.1.02.01`), tipo, naturaleza, padre y nivel |
| `polizas` / `poliza_lineas` | Asientos; cada línea es cargo **o** abono, en moneda original y en moneda base |
| `periodos` | Meses abiertos o cerrados |
| `monedas` / `tipos_cambio` | Multimoneda con tasa por fecha |
| `terceros`, `impuestos`, `facturas`, `pagos` | Operación de compras y ventas |
| `cuentas_bancarias`, `movimientos_banco` | Estado de cuenta importado y su conciliación |
| `bitacora` | Quién cerró, reabrió o revirtió y por qué |

Todos los montos son `NUMERIC(18,2)`. Restricciones `CHECK` impiden datos imposibles desde el origen:

```sql
debe  numeric(18,2) NOT NULL DEFAULT 0 CHECK (debe >= 0),
haber numeric(18,2) NOT NULL DEFAULT 0 CHECK (haber >= 0),
-- cada línea es un cargo o un abono, nunca ambos ni ninguno
CHECK ((debe > 0 AND haber = 0) OR (haber > 0 AND debe = 0))
```

## Paso 4. Las reglas (`backend/sql/002_reglas.sql`)

### 4.1 Catálogo coherente
Un trigger calcula el nivel, exige que el código empiece con el del padre (`1.1.02` → `1.1.02.01`) y que la subcuenta sea del mismo tipo. Cuando una cuenta recibe subcuentas pasa a ser *de mayor* y deja de aceptar movimientos.

### 4.2 Contabilizar = validar la partida doble
```sql
IF n_lineas < 2 THEN
    RAISE EXCEPTION 'DESCUADRE: una póliza necesita al menos dos líneas';
END IF;
IF t_debe <> t_haber THEN
    RAISE EXCEPTION 'DESCUADRE: la póliza no cuadra: debe % y haber %', t_debe, t_haber;
END IF;
```
Además convierte a moneda base, ajusta los centavos de redondeo y asigna el folio consecutivo del año con un *advisory lock* (sin huecos ni duplicados aunque dos personas contabilicen a la vez).

### 4.3 Inmutabilidad
El trigger `tg_polizas_reglas` rechaza cualquier `UPDATE` o `DELETE` sobre una póliza contabilizada. Las dos únicas transiciones válidas las habilitan las funciones del sistema con una variable de sesión:
- borrador → contabilizada, solo desde `contabilizar_poliza()`.
- contabilizada → cancelada, solo desde `revertir_poliza()`, que crea la póliza espejo.

### 4.4 Periodos cerrados
`validar_periodo_abierto()` se llama en cada alta o cambio. Las pruebas revelaron un caso importante: para **corregir un mes cerrado**, la reversa se fecha en un mes abierto y la póliza original solo cambia de estado (sus importes no se tocan), así que esa transición sí se permite.

## Paso 5. Reportes en la base (`backend/sql/003_reportes.sql`)

- `v_movimientos`: líneas de pólizas contabilizadas y canceladas (una cancelada sigue contando porque su reversa la anula).
- `v_cuenta_ancestros`: CTE recursiva que relaciona cada cuenta con todos sus padres, para que las cuentas de mayor sumen sus subcuentas.
- `saldos_cuentas(desde, hasta)`: saldo inicial, debe, haber y saldo final por cuenta. Las cuentas de resultados empiezan cada año en cero.
- `libro_mayor()`: saldo acumulado con una función de ventana (`sum() OVER (ORDER BY ...)`).
- `balance_general(corte)`: incluye *resultados de ejercicios anteriores* y *resultado del ejercicio*; cada sección usa su propio signo, así la **depreciación acumulada** (cuenta complementaria) resta del activo. Este caso lo detectó la primera prueba del balance, que no cuadraba por 1,000.02.
- `antiguedad_saldos(tipo, corte)`: agrupa los saldos por días vencidos con `FILTER`.

## Paso 6. Backend con FastAPI

- `db.py`: conexión SQLAlchemy y un pequeño sistema de migraciones que aplica `sql/NNN_*.sql` en orden.
- `errores.py`: traduce los mensajes de PostgreSQL (`DESCUADRE:`, `INMUTABLE:`, `PERIODO_CERRADO:`…) a respuestas HTTP 422/409 con texto claro.
- `servicios/polizas.py`: valida la partida doble también en Python para responder al instante (la base es la garantía final).
- `servicios/facturas.py`: calcula impuestos con redondeo comercial y arma el asiento:
  - Venta: Clientes (total) + Retenciones a favor / Ventas (subtotal) + IVA trasladado.
  - Compra: Gasto + IVA acreditable / Proveedores (total) + Retenciones por pagar.
  - Pago en moneda extranjera: la diferencia entre el tipo de cambio de la factura y el del pago va a utilidad o pérdida cambiaria.
- `servicios/conciliacion.py`: lee CSV con distintos formatos (coma o punto y coma, `1.234,56`, depósito/retiro), evita duplicados con una huella por fila y empareja en dos pasadas: importe + referencia, y luego importe + fecha cercana, sin adivinar si hay empate.
- `servicios/exportar.py`: el mismo reporte sale en PDF (ReportLab) o Excel (openpyxl).
- `seguridad.py`: JWT y roles admin / contador / consulta.
- Los montos se envían como texto para que JavaScript no los convierta a `float`.

## Paso 7. Datos de demostración (`app/seed.py`)

Se registran con los mismos servicios que usa la API, así cumplen las mismas reglas: capital inicial, compra de equipo, renta con retenciones, nómina quincenal, depreciación, ventas en USD y EUR, cobros parciales, una factura cancelada, una póliza corregida con reversa, un borrador, el estado de cuenta en CSV y el cierre de agosto y septiembre.

## Paso 8. Frontend con React, Vite y Tailwind

- **Captura ágil de pólizas**: autocompletado de cuentas por código o nombre, Enter para avanzar, `=` completa el importe que falta para cuadrar, Ctrl+S contabiliza y un indicador muestra la diferencia en vivo. La suma se hace en centavos enteros para no arrastrar errores de `float`.
- **Reportes imprimibles**: CSS `@media print` oculta el menú y los botones.
- Pantallas de facturas, conciliación (emparejar a mano o registrar comisiones), catálogo y periodos.
- Una prueba visual detectó que, al escribir rápido, el autocompletado podía elegir el resultado de una búsqueda vieja; se corrigió ignorando las respuestas que no son de la última búsqueda.

## Paso 9. Pruebas (44)

Corren contra PostgreSQL real dentro de una transacción que se deshace al final de cada prueba. Cubren la partida doble en las tres capas, la inmutabilidad con SQL directo, los periodos, un escenario contable con cifras calculables a mano para todos los reportes, impuestos, diferencia cambiaria y conciliación.

## Paso 10. Capturas, video y publicación

Las capturas y el video del README se generaron automáticamente con Selenium, Pillow e imageio-ffmpeg.

## Lo que se aprende con este proyecto

- Modelar la contabilidad con integridad garantizada por la base de datos.
- Por qué el dinero se maneja con decimales exactos.
- Funciones, vistas, CTE recursivas y funciones de ventana en PostgreSQL.
- Probar reglas de negocio contra la base real.
