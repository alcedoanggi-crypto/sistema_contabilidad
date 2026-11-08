-- =====================================================================
-- Saldos y reportes calculados DENTRO de PostgreSQL.
--
-- Ventajas frente a calcularlos en Python:
--  * Una sola consulta: no se traen miles de líneas a Python para sumarlas.
--  * Una sola fuente de verdad: la API, los PDF, los Excel y las pruebas usan
--    exactamente la misma función, así ningún reporte "suma distinto".
--  * Consistencia: la suma se hace sobre una foto coherente de la base
--    (misma transacción), aunque otro usuario esté contabilizando.
--  * Aritmética NUMERIC exacta de extremo a extremo.
-- =====================================================================

-- Movimientos que cuentan para la contabilidad: pólizas contabilizadas y
-- canceladas (una cancelada SIGUE contando: su póliza de reversa la anula).
CREATE VIEW v_movimientos AS
SELECT l.id            AS linea_id,
       p.id            AS poliza_id,
       p.anio || '-' || lpad(p.numero::text, 5, '0') AS folio,
       p.tipo          AS tipo_poliza,
       p.fecha,
       p.concepto,
       p.estado        AS estado_poliza,
       p.moneda,
       p.tipo_cambio,
       l.orden,
       l.cuenta_id,
       c.codigo        AS cuenta_codigo,
       c.nombre        AS cuenta_nombre,
       l.descripcion,
       l.debe,
       l.haber,
       l.debe_base,
       l.haber_base
  FROM poliza_lineas l
  JOIN polizas p ON p.id = l.poliza_id
  JOIN cuentas c ON c.id = l.cuenta_id
 WHERE p.estado IN ('contabilizada', 'cancelada');

-- Cada cuenta con todos sus ancestros (incluida ella misma): permite sumar
-- los movimientos de las subcuentas en cada cuenta de mayor.
CREATE VIEW v_cuenta_ancestros AS
WITH RECURSIVE arbol AS (
    SELECT id AS cuenta_id, id AS ancestro_id FROM cuentas
    UNION ALL
    SELECT a.cuenta_id, c.padre_id
      FROM arbol a JOIN cuentas c ON c.id = a.ancestro_id
     WHERE c.padre_id IS NOT NULL
)
SELECT cuenta_id, ancestro_id FROM arbol;

-- ---------------------------------------------------------------------
-- Saldos por cuenta entre dos fechas (base de la balanza de comprobación).
-- Las cuentas de resultados (ingreso/gasto) empiezan cada año en cero.
-- El saldo se expresa según la naturaleza: deudora = debe - haber.
-- ---------------------------------------------------------------------
CREATE FUNCTION saldos_cuentas(p_desde date, p_hasta date)
RETURNS TABLE (
    cuenta_id bigint, codigo text, nombre text, tipo text, naturaleza text, nivel smallint,
    padre_id bigint, acepta_movimientos boolean,
    saldo_inicial numeric(18,2), debe numeric(18,2), haber numeric(18,2), saldo_final numeric(18,2)
) LANGUAGE sql STABLE AS $$
    WITH mov AS (
        SELECT ca.ancestro_id AS cuenta_id,
               sum(CASE WHEN m.fecha < p_desde
                         AND (c.tipo IN ('activo', 'pasivo', 'capital') OR m.fecha >= date_trunc('year', p_desde::timestamp)::date)
                        THEN m.debe_base - m.haber_base ELSE 0 END) AS previo,
               sum(CASE WHEN m.fecha BETWEEN p_desde AND p_hasta THEN m.debe_base ELSE 0 END) AS debe,
               sum(CASE WHEN m.fecha BETWEEN p_desde AND p_hasta THEN m.haber_base ELSE 0 END) AS haber
          FROM v_movimientos m
          JOIN v_cuenta_ancestros ca ON ca.cuenta_id = m.cuenta_id
          JOIN cuentas c ON c.id = m.cuenta_id
         WHERE m.fecha <= p_hasta
         GROUP BY ca.ancestro_id
    )
    SELECT c.id, c.codigo, c.nombre, c.tipo, c.naturaleza, c.nivel, c.padre_id, c.acepta_movimientos,
           (CASE WHEN c.naturaleza = 'deudora' THEN 1 ELSE -1 END * coalesce(mov.previo, 0))::numeric(18,2),
           coalesce(mov.debe, 0)::numeric(18,2),
           coalesce(mov.haber, 0)::numeric(18,2),
           (CASE WHEN c.naturaleza = 'deudora' THEN 1 ELSE -1 END
              * (coalesce(mov.previo, 0) + coalesce(mov.debe, 0) - coalesce(mov.haber, 0)))::numeric(18,2)
      FROM cuentas c
      LEFT JOIN mov ON mov.cuenta_id = c.id
     ORDER BY string_to_array(c.codigo, '.')::int[];
$$;

-- ---------------------------------------------------------------------
-- Libro mayor de una cuenta (incluye sus subcuentas) con saldo acumulado
-- calculado con una función de ventana.
-- ---------------------------------------------------------------------
CREATE FUNCTION libro_mayor(p_cuenta_id bigint, p_desde date, p_hasta date)
RETURNS TABLE (
    fecha date, folio text, poliza_id bigint, concepto text, cuenta_codigo text, descripcion text,
    debe numeric(18,2), haber numeric(18,2), saldo numeric(18,2)
) LANGUAGE sql STABLE AS $$
    WITH cta AS (SELECT * FROM cuentas WHERE id = p_cuenta_id),
         signo AS (SELECT CASE WHEN naturaleza = 'deudora' THEN 1 ELSE -1 END AS s FROM cta),
         inicial AS (SELECT saldo_inicial FROM saldos_cuentas(p_desde, p_hasta) WHERE cuenta_id = p_cuenta_id),
         mov AS (
            SELECT m.fecha, m.folio, m.poliza_id, m.concepto, m.cuenta_codigo, m.descripcion,
                   m.debe_base AS debe, m.haber_base AS haber, m.linea_id
              FROM v_movimientos m
              JOIN v_cuenta_ancestros ca ON ca.cuenta_id = m.cuenta_id AND ca.ancestro_id = p_cuenta_id
             WHERE m.fecha BETWEEN p_desde AND p_hasta
         )
    SELECT r.fecha, r.folio, r.poliza_id, r.concepto, r.cuenta_codigo, r.descripcion, r.debe, r.haber, r.saldo
      FROM (
        SELECT 0 AS grupo, 0::bigint AS rn, NULL::date AS fecha, NULL::text AS folio, NULL::bigint AS poliza_id,
               'Saldo inicial'::text AS concepto, NULL::text AS cuenta_codigo, NULL::text AS descripcion,
               NULL::numeric(18,2) AS debe, NULL::numeric(18,2) AS haber,
               (SELECT saldo_inicial FROM inicial) AS saldo
        UNION ALL
        SELECT 1, row_number() OVER (ORDER BY mov.fecha, mov.folio, mov.linea_id),
               mov.fecha, mov.folio, mov.poliza_id, mov.concepto, mov.cuenta_codigo, mov.descripcion, mov.debe, mov.haber,
               ((SELECT saldo_inicial FROM inicial)
                + (SELECT s FROM signo) * sum(mov.debe - mov.haber) OVER (ORDER BY mov.fecha, mov.folio, mov.linea_id))::numeric(18,2)
          FROM mov
      ) r
     ORDER BY r.grupo, r.rn;
$$;

-- ---------------------------------------------------------------------
-- Estado de resultados de un periodo
-- ---------------------------------------------------------------------
CREATE FUNCTION estado_resultados(p_desde date, p_hasta date)
RETURNS TABLE (cuenta_id bigint, codigo text, nombre text, tipo text, nivel smallint, acepta_movimientos boolean, importe numeric(18,2))
LANGUAGE sql STABLE AS $$
    SELECT s.cuenta_id, s.codigo, s.nombre, s.tipo, s.nivel, s.acepta_movimientos,
           -- ingresos = haber - debe; gastos = debe - haber (por TIPO, no por naturaleza: así una cuenta
           -- complementaria, como "devoluciones sobre ventas", resta dentro de su sección)
           (CASE WHEN s.tipo = 'ingreso' THEN s.haber - s.debe ELSE s.debe - s.haber END)::numeric(18,2)
      FROM saldos_cuentas(p_desde, p_hasta) s
     WHERE s.tipo IN ('ingreso', 'gasto');
$$;

CREATE FUNCTION utilidad_periodo(p_desde date, p_hasta date) RETURNS numeric(18,2) LANGUAGE sql STABLE AS $$
    SELECT coalesce(sum(m.haber_base - m.debe_base), 0)::numeric(18,2)
      FROM v_movimientos m JOIN cuentas c ON c.id = m.cuenta_id
     WHERE c.tipo IN ('ingreso', 'gasto') AND m.fecha BETWEEN p_desde AND p_hasta;
$$;

-- ---------------------------------------------------------------------
-- Balance general a una fecha de corte.
-- Activo = Pasivo + Capital + Resultados de ejercicios anteriores + Resultado del ejercicio
-- (los resultados se calculan porque este sistema no genera pólizas de cierre anual).
-- ---------------------------------------------------------------------
CREATE FUNCTION balance_general(p_corte date)
RETURNS TABLE (seccion text, cuenta_id bigint, codigo text, nombre text, nivel smallint, acepta_movimientos boolean, importe numeric(18,2))
LANGUAGE sql STABLE AS $$
    -- El importe se expresa con el signo de la SECCIÓN: activo en saldo deudor; pasivo y capital en
    -- saldo acreedor. Así una cuenta complementaria (p. ej. depreciación acumulada, de naturaleza
    -- acreedora dentro del activo) aparece en negativo y resta del total, como en un balance real.
    SELECT s.tipo, s.cuenta_id, s.codigo, s.nombre, s.nivel, s.acepta_movimientos,
           (s.saldo_final
             * CASE WHEN s.naturaleza = 'deudora' THEN 1 ELSE -1 END
             * CASE WHEN s.tipo = 'activo' THEN 1 ELSE -1 END)::numeric(18,2)
      FROM saldos_cuentas(date_trunc('year', p_corte::timestamp)::date, p_corte) s
     WHERE s.tipo IN ('activo', 'pasivo', 'capital')
    UNION ALL
    SELECT 'capital', NULL, NULL, 'Resultados de ejercicios anteriores', 2, true,
           utilidad_periodo('0001-01-01', (date_trunc('year', p_corte::timestamp) - interval '1 day')::date)
    UNION ALL
    SELECT 'capital', NULL, NULL, 'Resultado del ejercicio', 2, true,
           utilidad_periodo(date_trunc('year', p_corte::timestamp)::date, p_corte);
$$;

-- ---------------------------------------------------------------------
-- Cuentas por cobrar / por pagar: saldo de cada factura a una fecha y
-- antigüedad por días vencidos.
-- ---------------------------------------------------------------------
CREATE FUNCTION saldos_facturas(p_corte date)
RETURNS TABLE (factura_id bigint, tipo text, folio text, tercero_id bigint, tercero text, fecha date, vencimiento date,
               moneda char(3), total numeric(18,2), pagado numeric(18,2), saldo numeric(18,2), saldo_base numeric(18,2),
               dias_vencido integer)
LANGUAGE sql STABLE AS $$
    SELECT f.id, f.tipo, f.folio, t.id, t.nombre, f.fecha, f.vencimiento, f.moneda, f.total,
           coalesce(pg.pagado, 0)::numeric(18,2),
           (f.total - coalesce(pg.pagado, 0))::numeric(18,2),
           round((f.total - coalesce(pg.pagado, 0)) * f.tipo_cambio, 2)::numeric(18,2),
           (p_corte - f.vencimiento)::int
      FROM facturas f
      JOIN terceros t ON t.id = f.tercero_id
      LEFT JOIN LATERAL (SELECT sum(monto) AS pagado FROM pagos WHERE factura_id = f.id AND fecha <= p_corte) pg ON true
     WHERE f.estado <> 'cancelada' AND f.fecha <= p_corte
       AND f.total - coalesce(pg.pagado, 0) > 0;
$$;

CREATE FUNCTION antiguedad_saldos(p_tipo text, p_corte date)
RETURNS TABLE (tercero_id bigint, tercero text, por_vencer numeric(18,2), d0_30 numeric(18,2), d31_60 numeric(18,2),
               d61_90 numeric(18,2), mas_90 numeric(18,2), total numeric(18,2), facturas bigint)
LANGUAGE sql STABLE AS $$
    SELECT s.tercero_id, s.tercero,
           sum(s.saldo_base) FILTER (WHERE s.dias_vencido <= 0)::numeric(18,2),
           sum(s.saldo_base) FILTER (WHERE s.dias_vencido BETWEEN 1 AND 30)::numeric(18,2),
           sum(s.saldo_base) FILTER (WHERE s.dias_vencido BETWEEN 31 AND 60)::numeric(18,2),
           sum(s.saldo_base) FILTER (WHERE s.dias_vencido BETWEEN 61 AND 90)::numeric(18,2),
           sum(s.saldo_base) FILTER (WHERE s.dias_vencido > 90)::numeric(18,2),
           sum(s.saldo_base)::numeric(18,2),
           count(*)
      FROM saldos_facturas(p_corte) s
     WHERE s.tipo = CASE p_tipo WHEN 'cxc' THEN 'ingreso' WHEN 'cxp' THEN 'gasto' END
     GROUP BY s.tercero_id, s.tercero
     ORDER BY sum(s.saldo_base) DESC;
$$;
