-- =====================================================================
-- Sistema de Contabilidad — esquema principal
--
-- Todos los montos usan NUMERIC(18,2): es un tipo decimal EXACTO.
-- FLOAT/REAL guardan los números en binario y no pueden representar
-- valores como 0.10 o 0.20 de forma exacta (0.1 + 0.2 = 0.30000000000000004).
-- En contabilidad un centavo de diferencia descuadra una balanza, así que
-- nunca se usa FLOAT para dinero. Los tipos de cambio usan NUMERIC(18,6).
-- =====================================================================

CREATE TABLE empresa (
    id                   smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    nombre               text NOT NULL,
    rfc                  text,
    moneda_base          char(3) NOT NULL,
    cuenta_clientes_id   bigint,
    cuenta_proveedores_id bigint,
    cuenta_utilidad_cambiaria_id bigint,
    cuenta_perdida_cambiaria_id  bigint
);

CREATE TABLE monedas (
    codigo   char(3) PRIMARY KEY CHECK (codigo ~ '^[A-Z]{3}$'),
    nombre   text NOT NULL,
    simbolo  text NOT NULL DEFAULT '$'
);

-- tasa = cuántas unidades de la moneda base vale 1 unidad de `moneda` ese día
CREATE TABLE tipos_cambio (
    id      bigserial PRIMARY KEY,
    moneda  char(3) NOT NULL REFERENCES monedas(codigo),
    fecha   date NOT NULL,
    tasa    numeric(18,6) NOT NULL CHECK (tasa > 0),
    UNIQUE (moneda, fecha)
);

CREATE TABLE usuarios (
    id             bigserial PRIMARY KEY,
    usuario        text NOT NULL UNIQUE,
    nombre         text NOT NULL,
    password_hash  text NOT NULL,
    rol            text NOT NULL CHECK (rol IN ('admin', 'contador', 'consulta')),
    activo         boolean NOT NULL DEFAULT true
);

-- ---------------------------------------------------------------------
-- Catálogo de cuentas jerárquico
-- ---------------------------------------------------------------------
CREATE TABLE cuentas (
    id                  bigserial PRIMARY KEY,
    codigo              text NOT NULL UNIQUE CHECK (codigo ~ '^[0-9]+(\.[0-9]+)*$'),
    nombre              text NOT NULL,
    tipo                text NOT NULL CHECK (tipo IN ('activo', 'pasivo', 'capital', 'ingreso', 'gasto')),
    naturaleza          text NOT NULL CHECK (naturaleza IN ('deudora', 'acreedora')),
    padre_id            bigint REFERENCES cuentas(id),
    nivel               smallint NOT NULL DEFAULT 1,
    acepta_movimientos  boolean NOT NULL DEFAULT true,
    activa              boolean NOT NULL DEFAULT true
);
CREATE INDEX idx_cuentas_padre ON cuentas(padre_id);

ALTER TABLE empresa
    ADD FOREIGN KEY (cuenta_clientes_id) REFERENCES cuentas(id),
    ADD FOREIGN KEY (cuenta_proveedores_id) REFERENCES cuentas(id),
    ADD FOREIGN KEY (cuenta_utilidad_cambiaria_id) REFERENCES cuentas(id),
    ADD FOREIGN KEY (cuenta_perdida_cambiaria_id) REFERENCES cuentas(id);

-- ---------------------------------------------------------------------
-- Periodos contables (meses) y bitácora
-- ---------------------------------------------------------------------
CREATE TABLE periodos (
    id           bigserial PRIMARY KEY,
    anio         smallint NOT NULL,
    mes          smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
    estado       text NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'cerrado')),
    cerrado_en   timestamptz,
    cerrado_por  text,
    UNIQUE (anio, mes)
);

CREATE TABLE bitacora (
    id         bigserial PRIMARY KEY,
    fecha      timestamptz NOT NULL DEFAULT now(),
    usuario    text,
    accion     text NOT NULL,
    entidad    text NOT NULL,
    entidad_id bigint,
    detalle    jsonb
);

-- ---------------------------------------------------------------------
-- Pólizas (asientos contables) y sus líneas
-- ---------------------------------------------------------------------
CREATE TABLE polizas (
    id                  bigserial PRIMARY KEY,
    anio                smallint,
    numero              integer,
    tipo                text NOT NULL DEFAULT 'diario' CHECK (tipo IN ('diario', 'ingreso', 'egreso')),
    fecha               date NOT NULL,
    concepto            text NOT NULL CHECK (length(trim(concepto)) > 0),
    moneda              char(3) NOT NULL REFERENCES monedas(codigo),
    tipo_cambio         numeric(18,6) NOT NULL DEFAULT 1 CHECK (tipo_cambio > 0),
    estado              text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'contabilizada', 'cancelada')),
    origen              text NOT NULL DEFAULT 'manual' CHECK (origen IN ('manual', 'factura', 'pago', 'reversa')),
    reversa_de          bigint UNIQUE REFERENCES polizas(id),
    cancelada_por       bigint REFERENCES polizas(id),
    motivo_cancelacion  text,
    creado_por          text,
    creado_en           timestamptz NOT NULL DEFAULT now(),
    contabilizada_en    timestamptz,
    UNIQUE (anio, numero),
    CHECK ((estado = 'borrador') = (numero IS NULL))
);
CREATE INDEX idx_polizas_fecha ON polizas(fecha);

CREATE TABLE poliza_lineas (
    id           bigserial PRIMARY KEY,
    poliza_id    bigint NOT NULL REFERENCES polizas(id) ON DELETE CASCADE,
    orden        smallint NOT NULL DEFAULT 0,
    cuenta_id    bigint NOT NULL REFERENCES cuentas(id),
    descripcion  text,
    debe         numeric(18,2) NOT NULL DEFAULT 0 CHECK (debe >= 0),
    haber        numeric(18,2) NOT NULL DEFAULT 0 CHECK (haber >= 0),
    debe_base    numeric(18,2),
    haber_base   numeric(18,2),
    -- cada línea es un cargo o un abono, nunca ambos ni ninguno
    CHECK ((debe > 0 AND haber = 0) OR (haber > 0 AND debe = 0))
);
CREATE INDEX idx_lineas_poliza ON poliza_lineas(poliza_id);
CREATE INDEX idx_lineas_cuenta ON poliza_lineas(cuenta_id);

-- ---------------------------------------------------------------------
-- Terceros, impuestos y facturas
-- ---------------------------------------------------------------------
CREATE TABLE terceros (
    id            bigserial PRIMARY KEY,
    tipo          text NOT NULL CHECK (tipo IN ('cliente', 'proveedor', 'ambos')),
    nombre        text NOT NULL,
    rfc           text,
    email         text,
    telefono      text,
    dias_credito  smallint NOT NULL DEFAULT 30 CHECK (dias_credito >= 0),
    activo        boolean NOT NULL DEFAULT true
);

-- tipo 'traslado' se suma a la factura (IVA); 'retencion' se resta (ISR/IVA retenido)
CREATE TABLE impuestos (
    id                 bigserial PRIMARY KEY,
    codigo             text NOT NULL UNIQUE,
    nombre             text NOT NULL,
    tipo               text NOT NULL CHECK (tipo IN ('traslado', 'retencion')),
    tasa               numeric(7,4) NOT NULL CHECK (tasa >= 0 AND tasa <= 100),
    cuenta_ventas_id   bigint NOT NULL REFERENCES cuentas(id),
    cuenta_compras_id  bigint NOT NULL REFERENCES cuentas(id),
    activo             boolean NOT NULL DEFAULT true
);

CREATE TABLE facturas (
    id                 bigserial PRIMARY KEY,
    tipo               text NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
    folio              text NOT NULL,
    tercero_id         bigint NOT NULL REFERENCES terceros(id),
    fecha              date NOT NULL,
    vencimiento        date NOT NULL,
    moneda             char(3) NOT NULL REFERENCES monedas(codigo),
    tipo_cambio        numeric(18,6) NOT NULL CHECK (tipo_cambio > 0),
    subtotal           numeric(18,2) NOT NULL CHECK (subtotal > 0),
    total_traslados    numeric(18,2) NOT NULL DEFAULT 0,
    total_retenciones  numeric(18,2) NOT NULL DEFAULT 0,
    total              numeric(18,2) NOT NULL CHECK (total > 0),
    estado             text NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'pagada', 'cancelada')),
    poliza_id          bigint REFERENCES polizas(id),
    notas              text,
    creado_en          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tipo, tercero_id, folio),
    CHECK (vencimiento >= fecha),
    CHECK (total = subtotal + total_traslados - total_retenciones)
);

CREATE TABLE factura_lineas (
    id               bigserial PRIMARY KEY,
    factura_id       bigint NOT NULL REFERENCES facturas(id) ON DELETE CASCADE,
    descripcion      text NOT NULL,
    cuenta_id        bigint NOT NULL REFERENCES cuentas(id),
    cantidad         numeric(18,4) NOT NULL CHECK (cantidad > 0),
    precio_unitario  numeric(18,4) NOT NULL CHECK (precio_unitario >= 0),
    importe          numeric(18,2) NOT NULL
);

CREATE TABLE factura_impuestos (
    id           bigserial PRIMARY KEY,
    factura_id   bigint NOT NULL REFERENCES facturas(id) ON DELETE CASCADE,
    impuesto_id  bigint NOT NULL REFERENCES impuestos(id),
    base         numeric(18,2) NOT NULL,
    tasa         numeric(7,4) NOT NULL,
    importe      numeric(18,2) NOT NULL
);

-- ---------------------------------------------------------------------
-- Bancos, pagos y conciliación
-- ---------------------------------------------------------------------
CREATE TABLE cuentas_bancarias (
    id         bigserial PRIMARY KEY,
    nombre     text NOT NULL,
    banco      text NOT NULL,
    numero     text,
    moneda     char(3) NOT NULL REFERENCES monedas(codigo),
    cuenta_id  bigint NOT NULL UNIQUE REFERENCES cuentas(id)
);

CREATE TABLE pagos (
    id                  bigserial PRIMARY KEY,
    factura_id          bigint NOT NULL REFERENCES facturas(id),
    fecha               date NOT NULL,
    monto               numeric(18,2) NOT NULL CHECK (monto > 0),   -- en la moneda de la factura
    tipo_cambio         numeric(18,6) NOT NULL CHECK (tipo_cambio > 0),
    cuenta_bancaria_id  bigint NOT NULL REFERENCES cuentas_bancarias(id),
    referencia          text,
    poliza_id           bigint REFERENCES polizas(id),
    creado_en           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_pagos_factura ON pagos(factura_id);

CREATE TABLE importaciones_banco (
    id                  bigserial PRIMARY KEY,
    cuenta_bancaria_id  bigint NOT NULL REFERENCES cuentas_bancarias(id),
    archivo             text NOT NULL,
    filas               integer NOT NULL,
    duplicadas          integer NOT NULL DEFAULT 0,
    creado_en           timestamptz NOT NULL DEFAULT now()
);

-- monto > 0 = depósito (cargo a bancos), monto < 0 = retiro (abono a bancos)
CREATE TABLE movimientos_banco (
    id                  bigserial PRIMARY KEY,
    cuenta_bancaria_id  bigint NOT NULL REFERENCES cuentas_bancarias(id),
    importacion_id      bigint REFERENCES importaciones_banco(id),
    fecha               date NOT NULL,
    descripcion         text NOT NULL,
    referencia          text,
    monto               numeric(18,2) NOT NULL CHECK (monto <> 0),
    huella              text NOT NULL,              -- evita importar dos veces la misma fila
    linea_id            bigint UNIQUE REFERENCES poliza_lineas(id),
    conciliado_en       timestamptz,
    UNIQUE (cuenta_bancaria_id, huella)
);
