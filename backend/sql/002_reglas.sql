-- =====================================================================
-- Reglas contables que la base de datos hace cumplir SIEMPRE,
-- aunque alguien escriba SQL directo saltándose la aplicación.
-- Los errores empiezan con un código ("DESCUADRE:", "INMUTABLE:"...)
-- que la API traduce a mensajes y códigos HTTP.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Catálogo: nivel, tipo y código coherentes con la cuenta padre
-- ---------------------------------------------------------------------
CREATE FUNCTION tg_cuentas_validar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    padre cuentas%ROWTYPE;
BEGIN
    IF NEW.padre_id IS NULL THEN
        NEW.nivel := 1;
        IF NEW.codigo LIKE '%.%' THEN
            RAISE EXCEPTION 'CATALOGO: una cuenta de primer nivel no lleva punto en el código (%)', NEW.codigo;
        END IF;
    ELSE
        SELECT * INTO padre FROM cuentas WHERE id = NEW.padre_id;
        IF NEW.codigo NOT LIKE padre.codigo || '.%' THEN
            RAISE EXCEPTION 'CATALOGO: el código % debe empezar con el de su cuenta padre (%.)', NEW.codigo, padre.codigo;
        END IF;
        IF NEW.tipo <> padre.tipo THEN
            RAISE EXCEPTION 'CATALOGO: la subcuenta debe ser del mismo tipo que su padre (%)', padre.tipo;
        END IF;
        NEW.nivel := padre.nivel + 1;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER cuentas_validar BEFORE INSERT OR UPDATE OF codigo, tipo, padre_id ON cuentas
    FOR EACH ROW EXECUTE FUNCTION tg_cuentas_validar();

-- Una cuenta que pasa a tener subcuentas deja de aceptar movimientos (se vuelve "de mayor").
-- Si ya tenía movimientos, no se le pueden crear subcuentas.
CREATE FUNCTION tg_cuentas_padre_agrupadora() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.padre_id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM poliza_lineas WHERE cuenta_id = NEW.padre_id) THEN
            RAISE EXCEPTION 'CATALOGO: la cuenta padre ya tiene movimientos y no puede tener subcuentas';
        END IF;
        UPDATE cuentas SET acepta_movimientos = false WHERE id = NEW.padre_id AND acepta_movimientos;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER cuentas_padre_agrupadora AFTER INSERT ON cuentas
    FOR EACH ROW EXECUTE FUNCTION tg_cuentas_padre_agrupadora();

-- ---------------------------------------------------------------------
-- Periodos
-- ---------------------------------------------------------------------
CREATE FUNCTION periodo_cerrado(p_fecha date) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM periodos
        WHERE anio = extract(year FROM p_fecha) AND mes = extract(month FROM p_fecha) AND estado = 'cerrado'
    );
$$;

CREATE FUNCTION validar_periodo_abierto(p_fecha date) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF periodo_cerrado(p_fecha) THEN
        RAISE EXCEPTION 'PERIODO_CERRADO: el periodo %/% está cerrado; no se pueden registrar ni modificar movimientos',
            lpad(extract(month FROM p_fecha)::text, 2, '0'), extract(year FROM p_fecha);
    END IF;
END $$;

CREATE FUNCTION asegurar_periodo(p_fecha date) RETURNS void LANGUAGE sql AS $$
    INSERT INTO periodos (anio, mes) VALUES (extract(year FROM p_fecha), extract(month FROM p_fecha))
    ON CONFLICT (anio, mes) DO NOTHING;
$$;

-- ---------------------------------------------------------------------
-- Inmutabilidad de pólizas
--   borrador       -> se puede editar y borrar
--   contabilizada  -> no se toca; solo puede pasar a "cancelada" mediante revertir_poliza()
--   cancelada      -> no se toca
-- Las transiciones especiales se habilitan con variables de sesión que
-- solo fijan las funciones contabilizar_poliza() y revertir_poliza().
-- ---------------------------------------------------------------------
CREATE FUNCTION tg_polizas_reglas() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM validar_periodo_abierto(NEW.fecha);
        IF NEW.estado <> 'borrador' THEN
            RAISE EXCEPTION 'INMUTABLE: una póliza nueva siempre nace como borrador';
        END IF;
        PERFORM asegurar_periodo(NEW.fecha);
        RETURN NEW;
    END IF;

    -- Marcar como cancelada una póliza ya revertida es válido aunque su mes esté cerrado:
    -- así se corrige un periodo cerrado (la reversa se fecha en un mes abierto y los
    -- importes del mes cerrado no cambian). Solo lo permite revertir_poliza().
    IF TG_OP = 'UPDATE' AND OLD.estado = 'contabilizada' AND NEW.estado = 'cancelada'
       AND current_setting('contabilidad.revirtiendo', true) = 'on'
       AND (NEW.fecha, NEW.concepto, NEW.moneda, NEW.tipo_cambio, NEW.numero, NEW.anio)
           IS NOT DISTINCT FROM (OLD.fecha, OLD.concepto, OLD.moneda, OLD.tipo_cambio, OLD.numero, OLD.anio) THEN
        RETURN NEW;
    END IF;

    PERFORM validar_periodo_abierto(OLD.fecha);

    IF TG_OP = 'DELETE' THEN
        IF OLD.estado <> 'borrador' THEN
            RAISE EXCEPTION 'INMUTABLE: la póliza % está %; no se borra, se cancela con una póliza de reversa',
                OLD.anio || '-' || OLD.numero, OLD.estado;
        END IF;
        RETURN OLD;
    END IF;

    -- UPDATE
    IF OLD.estado = 'borrador' AND NEW.estado = 'borrador' THEN
        PERFORM validar_periodo_abierto(NEW.fecha);
        RETURN NEW;
    END IF;

    IF OLD.estado = 'borrador' AND NEW.estado = 'contabilizada'
       AND current_setting('contabilidad.contabilizando', true) = 'on' THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'INMUTABLE: la póliza % está % y no se puede modificar',
        coalesce(OLD.anio || '-' || OLD.numero, '#' || OLD.id), OLD.estado;
END $$;

CREATE TRIGGER polizas_reglas BEFORE INSERT OR UPDATE OR DELETE ON polizas
    FOR EACH ROW EXECUTE FUNCTION tg_polizas_reglas();

CREATE FUNCTION tg_lineas_reglas() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    p polizas%ROWTYPE;
    c cuentas%ROWTYPE;
BEGIN
    SELECT * INTO p FROM polizas WHERE id = coalesce(NEW.poliza_id, OLD.poliza_id);
    -- Borrado en cascada de un borrador: la póliza ya no existe o es borrador
    IF NOT FOUND THEN
        RETURN coalesce(NEW, OLD);
    END IF;
    IF p.estado <> 'borrador' AND NOT (TG_OP = 'UPDATE' AND current_setting('contabilidad.contabilizando', true) = 'on') THEN
        RAISE EXCEPTION 'INMUTABLE: las líneas de una póliza % no se pueden modificar', p.estado;
    END IF;
    PERFORM validar_periodo_abierto(p.fecha);
    IF TG_OP <> 'DELETE' THEN
        SELECT * INTO c FROM cuentas WHERE id = NEW.cuenta_id;
        IF NOT c.acepta_movimientos THEN
            RAISE EXCEPTION 'CATALOGO: la cuenta % % es de mayor (tiene subcuentas) y no acepta movimientos', c.codigo, c.nombre;
        END IF;
        IF NOT c.activa THEN
            RAISE EXCEPTION 'CATALOGO: la cuenta % % está inactiva', c.codigo, c.nombre;
        END IF;
    END IF;
    RETURN coalesce(NEW, OLD);
END $$;

CREATE TRIGGER lineas_reglas BEFORE INSERT OR UPDATE OR DELETE ON poliza_lineas
    FOR EACH ROW EXECUTE FUNCTION tg_lineas_reglas();

-- ---------------------------------------------------------------------
-- Contabilizar: valida la PARTIDA DOBLE y asigna el folio definitivo
-- ---------------------------------------------------------------------
CREATE FUNCTION contabilizar_poliza(p_id bigint) RETURNS polizas LANGUAGE plpgsql AS $$
DECLARE
    p          polizas%ROWTYPE;
    n_lineas   integer;
    t_debe     numeric(18,2);
    t_haber    numeric(18,2);
    dif        numeric(18,2);
    siguiente  integer;
BEGIN
    SELECT * INTO p FROM polizas WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NO_ENCONTRADO: la póliza % no existe', p_id;
    END IF;
    IF p.estado <> 'borrador' THEN
        RAISE EXCEPTION 'INMUTABLE: la póliza ya está %', p.estado;
    END IF;
    PERFORM validar_periodo_abierto(p.fecha);

    SELECT count(*), coalesce(sum(debe), 0), coalesce(sum(haber), 0)
      INTO n_lineas, t_debe, t_haber
      FROM poliza_lineas WHERE poliza_id = p_id;

    IF n_lineas < 2 THEN
        RAISE EXCEPTION 'DESCUADRE: una póliza necesita al menos dos líneas (un cargo y un abono)';
    END IF;
    IF t_debe <> t_haber THEN
        RAISE EXCEPTION 'DESCUADRE: la póliza no cuadra: debe % y haber % (diferencia %)', t_debe, t_haber, t_debe - t_haber;
    END IF;

    PERFORM set_config('contabilidad.contabilizando', 'on', true);

    -- Montos en moneda base. Las reversas ya traen sus montos base (espejo exacto del original).
    UPDATE poliza_lineas
       SET debe_base = round(debe * p.tipo_cambio, 2), haber_base = round(haber * p.tipo_cambio, 2)
     WHERE poliza_id = p_id AND debe_base IS NULL;

    -- El redondeo de cada línea puede dejar centavos de diferencia en moneda base:
    -- se ajustan en la línea de mayor importe del lado que sobra.
    SELECT sum(debe_base) - sum(haber_base) INTO dif FROM poliza_lineas WHERE poliza_id = p_id;
    IF dif > 0 THEN
        UPDATE poliza_lineas SET debe_base = debe_base - dif
         WHERE id = (SELECT id FROM poliza_lineas WHERE poliza_id = p_id AND debe_base > 0 ORDER BY debe_base DESC, id LIMIT 1);
    ELSIF dif < 0 THEN
        UPDATE poliza_lineas SET haber_base = haber_base + dif
         WHERE id = (SELECT id FROM poliza_lineas WHERE poliza_id = p_id AND haber_base > 0 ORDER BY haber_base DESC, id LIMIT 1);
    END IF;

    -- Folio consecutivo por año, sin huecos ni duplicados aunque haya usuarios simultáneos
    PERFORM pg_advisory_xact_lock(hashtext('folio_polizas'), extract(year FROM p.fecha)::int);
    SELECT coalesce(max(numero), 0) + 1 INTO siguiente FROM polizas WHERE anio = extract(year FROM p.fecha);

    UPDATE polizas
       SET estado = 'contabilizada', anio = extract(year FROM p.fecha), numero = siguiente, contabilizada_en = now()
     WHERE id = p_id
    RETURNING * INTO p;

    PERFORM set_config('contabilidad.contabilizando', 'off', true);
    RETURN p;
END $$;

-- ---------------------------------------------------------------------
-- Revertir: cancela una póliza contabilizada con una póliza espejo
-- (cargos y abonos invertidos). El original nunca se borra ni se edita.
-- ---------------------------------------------------------------------
CREATE FUNCTION revertir_poliza(p_id bigint, p_fecha date, p_motivo text, p_usuario text)
RETURNS polizas LANGUAGE plpgsql AS $$
DECLARE
    o  polizas%ROWTYPE;
    r  polizas%ROWTYPE;
BEGIN
    SELECT * INTO o FROM polizas WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'NO_ENCONTRADO: la póliza % no existe', p_id;
    END IF;
    IF o.estado <> 'contabilizada' THEN
        RAISE EXCEPTION 'INMUTABLE: solo se revierte una póliza contabilizada (esta está %)', o.estado;
    END IF;
    IF coalesce(trim(p_motivo), '') = '' THEN
        RAISE EXCEPTION 'VALIDACION: indica el motivo de la cancelación';
    END IF;
    IF p_fecha < o.fecha THEN
        RAISE EXCEPTION 'VALIDACION: la reversa no puede tener fecha anterior a la póliza original';
    END IF;

    INSERT INTO polizas (tipo, fecha, concepto, moneda, tipo_cambio, origen, reversa_de, creado_por)
    VALUES (o.tipo, p_fecha, 'Reversa de póliza ' || o.anio || '-' || o.numero || ': ' || p_motivo,
            o.moneda, o.tipo_cambio, 'reversa', o.id, p_usuario)
    RETURNING * INTO r;

    INSERT INTO poliza_lineas (poliza_id, orden, cuenta_id, descripcion, debe, haber, debe_base, haber_base)
    SELECT r.id, orden, cuenta_id, descripcion, haber, debe, haber_base, debe_base
      FROM poliza_lineas WHERE poliza_id = o.id ORDER BY orden, id;

    r := contabilizar_poliza(r.id);

    PERFORM set_config('contabilidad.revirtiendo', 'on', true);
    UPDATE polizas SET estado = 'cancelada', cancelada_por = r.id, motivo_cancelacion = p_motivo WHERE id = o.id;
    PERFORM set_config('contabilidad.revirtiendo', 'off', true);

    INSERT INTO bitacora (usuario, accion, entidad, entidad_id, detalle)
    VALUES (p_usuario, 'revertir', 'poliza', o.id, jsonb_build_object('reversa_id', r.id, 'motivo', p_motivo));
    RETURN r;
END $$;

-- ---------------------------------------------------------------------
-- Cierre y reapertura de periodos
-- ---------------------------------------------------------------------
CREATE FUNCTION cerrar_periodo(p_anio int, p_mes int, p_usuario text) RETURNS periodos LANGUAGE plpgsql AS $$
DECLARE
    pe periodos%ROWTYPE;
    borradores integer;
BEGIN
    INSERT INTO periodos (anio, mes) VALUES (p_anio, p_mes) ON CONFLICT DO NOTHING;
    SELECT count(*) INTO borradores FROM polizas
     WHERE estado = 'borrador' AND extract(year FROM fecha) = p_anio AND extract(month FROM fecha) = p_mes;
    IF borradores > 0 THEN
        RAISE EXCEPTION 'VALIDACION: hay % póliza(s) en borrador en ese mes; contabilízalas o elimínalas antes de cerrar', borradores;
    END IF;
    UPDATE periodos SET estado = 'cerrado', cerrado_en = now(), cerrado_por = p_usuario
     WHERE anio = p_anio AND mes = p_mes RETURNING * INTO pe;
    INSERT INTO bitacora (usuario, accion, entidad, entidad_id, detalle)
    VALUES (p_usuario, 'cerrar', 'periodo', pe.id, jsonb_build_object('anio', p_anio, 'mes', p_mes));
    RETURN pe;
END $$;

CREATE FUNCTION reabrir_periodo(p_anio int, p_mes int, p_usuario text, p_motivo text) RETURNS periodos LANGUAGE plpgsql AS $$
DECLARE
    pe periodos%ROWTYPE;
BEGIN
    IF coalesce(trim(p_motivo), '') = '' THEN
        RAISE EXCEPTION 'VALIDACION: indica el motivo de la reapertura';
    END IF;
    UPDATE periodos SET estado = 'abierto', cerrado_en = NULL, cerrado_por = NULL
     WHERE anio = p_anio AND mes = p_mes AND estado = 'cerrado' RETURNING * INTO pe;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'VALIDACION: el periodo %/% no está cerrado', p_mes, p_anio;
    END IF;
    INSERT INTO bitacora (usuario, accion, entidad, entidad_id, detalle)
    VALUES (p_usuario, 'reabrir', 'periodo', pe.id, jsonb_build_object('anio', p_anio, 'mes', p_mes, 'motivo', p_motivo));
    RETURN pe;
END $$;

-- ---------------------------------------------------------------------
-- Tipo de cambio vigente: el último publicado en o antes de la fecha
-- ---------------------------------------------------------------------
CREATE FUNCTION tipo_cambio_en(p_moneda char(3), p_fecha date) RETURNS numeric LANGUAGE plpgsql STABLE AS $$
DECLARE
    tasa numeric;
BEGIN
    IF p_moneda = (SELECT moneda_base FROM empresa) THEN
        RETURN 1;
    END IF;
    SELECT tc.tasa INTO tasa FROM tipos_cambio tc
     WHERE tc.moneda = p_moneda AND tc.fecha <= p_fecha ORDER BY tc.fecha DESC LIMIT 1;
    IF tasa IS NULL THEN
        RAISE EXCEPTION 'TIPO_CAMBIO: no hay tipo de cambio de % en o antes del %', p_moneda, p_fecha;
    END IF;
    RETURN tasa;
END $$;
