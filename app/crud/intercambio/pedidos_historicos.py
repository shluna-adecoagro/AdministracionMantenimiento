# app/crud/intercambio/pedidos_historicos.py
"""
Importación del Excel histórico de pedidos (fase 10, PR 10.6).

El adaptador (app/crud/intercambio/excel_pedidos.py) lee el libro; este módulo
aplica las reglas y lo carga con el mismo servicio que la web y la API
(validación, sugerencias de imputación y auditoría):

  * Pedido por hoja, línea por fila y destinos por línea. Ofertas reconstruidas
    (una por proveedor y OC) con sus líneas, y adjudicaciones: lo comprado al
    proveedor de la columna «PROVEEDOR»; lo cotizado por los demás, en 0.
  * Estado por el color de la pestaña: cerrado → cierre manual
    (`sin_conformidad`, sin recepciones), salvo que «Recibido?» diga que no
    llegó; en proceso → «en cotización» (con OC, el estado visible es «OC
    emitida»); anulado → anulada con motivo; sin color → solicitado.
  * Material por código (número de parte o código del ERP); destino por número
    de activo, número de serie, modelo, ubicación o sector; cuenta y sector por
    el maestro. Lo que no se identifica queda «a revisar» y va a pendientes.csv
    para Copilot (docs/prompt_copilot_equivalencias.md); la tabla revisada
    (equivalencias_revisadas.csv) se usa en la importación siguiente.
  * Idempotente por `origen` + `clave_origen` (hoja, fila): repetirla actualiza.
    Lo que se identificó (a mano o por equivalencias) no se pisa con un vacío;
    los destinos que el gestor cargó en la app no se tocan; las ofertas
    revisadas, tampoco.
  * Todo o nada: si hay errores, se informan y no se guarda nada.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.service import ErrorIntegridad
from app.crud.intercambio.excel_pedidos import ANULADO, CERRADO, EN_PROCESO, HojaPedido, leer_libro, normalizar

MOTIVO_ANULACION_HISTORICO = "Anulado en el Excel histórico"
COLUMNAS_PENDIENTES = ("id", "tipo", "texto", "contexto", "veces")
COLUMNAS_EQUIVALENCIAS = ("tipo", "texto", "resultado", "codigos")
# Lo identificado no se pisa con un vacío al reimportar.
_PROTEGIDOS_LINEA = ("material_id",)
_PROTEGIDOS_DESTINO = ("activo_id", "modelo_id", "ubicacion_id", "sector_imputado_id", "cuenta_id")


_FEM = {"creado": "*_creadas", "actualizado": "*_actualizadas"}


class _Abortar(Exception):
    """Un error del servicio: la sesión ya se deshizo, no se sigue."""


@dataclass
class Pendiente:
    tipo: str
    texto: str
    contexto: str
    veces: int = 0

    @property
    def id(self) -> str:
        return f"{self.tipo[0].upper()}-{hashlib.sha1(normalizar(self.texto).encode()).hexdigest()[:8]}"


@dataclass
class ResultadoPedidosHistoricos:
    simulado: bool = False
    conteo: Counter = field(default_factory=Counter)
    informe: list[tuple[str, str, str]] = field(default_factory=list)  # (hoja, fila, mensaje)
    pendientes: dict[tuple[str, str], Pendiente] = field(default_factory=dict)
    errores: list[tuple[str, str, str, str]] = field(default_factory=list)  # (hoja, fila, campo, mensaje)
    faltan_en_maestro: Counter = field(default_factory=Counter)  # (maestro, texto) → filas

    @property
    def ok(self) -> bool:
        return not self.errores

    def avisar(self, hoja: str, fila, mensaje: str):
        self.informe.append((hoja, str(fila or ""), mensaje))

    def pendiente(self, tipo: str, texto: str, contexto: str):
        clave = (tipo, normalizar(texto))
        p = self.pendientes.setdefault(clave, Pendiente(tipo=tipo, texto=texto, contexto=contexto))
        p.veces += 1

    def resumen(self) -> str:
        c = self.conteo
        lineas = ["Importación del Excel histórico de pedidos"
                  + (" (SIMULACIÓN: no se guardó nada)" if self.simulado else "")]
        if self.errores:
            lineas.append(f"  ✘ {len(self.errores)} error/es. No se guardó nada:")
            for hoja, fila, campo, mensaje in self.errores:
                lineas.append(f"    {hoja}{', fila ' + fila if fila else ''} [{campo}]: {mensaje}")
            return "\n".join(lineas)
        lineas += [
            f"  ✔ Hojas: {c['hojas']} leídas, {c['hojas_salteadas']} salteadas.",
            f"  ✔ Pedidos: {c['pedidos_creados']} creados, {c['pedidos_actualizados']} actualizados, "
            f"{c['pedidos_sin_cambios']} sin cambios.",
            f"  ✔ Líneas: {c['lineas_creadas']} creadas, {c['lineas_actualizadas']} actualizadas "
            f"({c['lineas_cerradas']} cerradas, {c['lineas_en_proceso']} en proceso, {c['lineas_anuladas']} "
            f"anuladas, {c['lineas_solicitadas']} solicitadas; {c['oc_completadas']} con la OC tomada de otra fila).",
            f"  ✔ Destinos: {c['destinos_creados']} creados, {c['destinos_actualizados']} actualizados, "
            f"{c['destinos_borrados']} borrados.",
            f"  ✔ Ofertas: {c['ofertas_creadas']} creadas, {c['ofertas_actualizadas']} actualizadas; "
            f"{c['lineas_oferta_creadas']} líneas y {c['adjudicaciones_creadas']} adjudicaciones nuevas.",
            f"  ✔ Identificados: {c['materiales_identificados']} materiales, {c['destinos_identificados']} "
            f"destinos ({c['equivalencias_usadas']} por equivalencias revisadas).",
        ]
        if c["ofertas_revisadas_salteadas"]:
            lineas.append(f"  ℹ Ofertas ya revisadas (no se tocaron): {c['ofertas_revisadas_salteadas']}.")
        por_tipo = Counter(p.tipo for p in self.pendientes.values())
        lineas.append(f"  ⚠ Pendientes para equivalencias: {por_tipo['material']} materiales y "
                      f"{por_tipo['destino']} destinos (textos distintos).")
        for maestro in ("cuenta", "sector"):
            faltan = [(t, n) for (m, t), n in self.faltan_en_maestro.most_common() if m == maestro]
            if faltan:
                lineas.append(f"  ⚠ {'Cuentas' if maestro == 'cuenta' else 'Sectores'} que no están en el maestro: "
                              + ", ".join(f"«{t}» ({n})" for t, n in faltan[:15])
                              + (f" y {len(faltan) - 15} más" if len(faltan) > 15 else "") + ".")
        lineas.append(f"  ⚠ {len(self.informe)} aviso/s para revisar (ver el informe).")
        return "\n".join(lineas)

    def informe_csv(self) -> bytes:
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow(("hoja", "fila", "mensaje"))
        w.writerows(self.informe)
        return salida.getvalue().encode("utf-8-sig")

    def pendientes_csv(self) -> bytes:
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow(COLUMNAS_PENDIENTES)
        for p in sorted(self.pendientes.values(), key=lambda p: (p.tipo, -p.veces, normalizar(p.texto))):
            w.writerow((p.id, p.tipo, p.texto, p.contexto, p.veces))
        return salida.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Identificación contra los maestros
# ---------------------------------------------------------------------------

def _codigo(texto) -> str:
    return re.sub(r"[\s\-._/]", "", str(texto or "")).upper()


def _unicos(pares) -> dict:
    """{clave: objeto} solo para las claves que no se repiten."""
    vistos: dict = {}
    repetidos = set()
    for clave, obj in pares:
        if not clave:
            continue
        if clave in vistos and vistos[clave] is not obj:
            repetidos.add(clave)
        vistos[clave] = obj
    return {k: v for k, v in vistos.items() if k not in repetidos}


class Maestros:
    """Índices de los maestros, armados una vez por importación."""

    def __init__(self):
        from app.models.activos_models import Activo
        from app.models.cuentas_models import Cuenta
        from app.models.marcas_modelos_models import Modelo
        from app.models.materiales_models import Material
        from app.models.sectores_models import Sector
        from app.models.ubicaciones_models import Ubicacion

        activos = Activo.query.all()
        self.activo_por_codigo = _unicos(
            [(_codigo(a.numero_activo), a) for a in activos]
            + [(_codigo(a.numero_serie), a) for a in activos if a.numero_serie]
            + [(_codigo(a.codigo_carga_gasoil), a) for a in activos if a.codigo_carga_gasoil])
        self.activo_por_numero = {a.numero_activo.strip().upper(): a for a in activos}
        self.activo_por_nombre = _unicos((normalizar(a.descripcion), a) for a in activos)
        modelos = Modelo.query.all()
        self.modelo_por_nombre = _unicos((normalizar(m.nombre_modelo), m) for m in modelos)
        ubicaciones = Ubicacion.query.all()
        self.ubicacion_por_nombre = _unicos((normalizar(u.nombre_ubicacion), u) for u in ubicaciones)
        self.ubicaciones_por_sector: dict[int, list] = {}
        for u in ubicaciones:
            self.ubicaciones_por_sector.setdefault(u.sector_id, []).append(u)
        sectores = Sector.query.all()
        self.sector_por_nombre = _unicos(
            [(normalizar(s.nombre_sector), s) for s in sectores]
            + [(normalizar(s.centro_costo), s) for s in sectores])
        cuentas = Cuenta.query.all()
        self.cuenta_por_texto = _unicos(
            [(normalizar(c.numero_cuenta), c) for c in cuentas] + [(normalizar(c.nombre_cuenta), c) for c in cuentas])
        materiales = Material.query.all()
        self.material_por_codigo = _unicos(
            [(_codigo(m.codigo), m) for m in materiales]
            + [(_codigo(m.codigo_erp), m) for m in materiales if m.codigo_erp])
        self._proveedores: dict[str, object] = {}

    def material(self, producto: str):
        """Por código: el texto entero, o una palabra del texto que sea un código del maestro."""
        entero = self.material_por_codigo.get(_codigo(producto))
        if entero is not None:
            return entero
        candidatos = {id(m): m for m in (self.material_por_codigo.get(_codigo(p))
                                         for p in re.findall(r"[\w\-.]+", producto)
                                         if len(_codigo(p)) >= 5 and re.search(r"\d", p)) if m is not None}
        return next(iter(candidatos.values())) if len(candidatos) == 1 else None

    def activos_en(self, texto: str) -> list:
        """Activos nombrados en el texto (número de activo, número de serie o código de gasoil)."""
        encontrados = []
        for palabra in re.findall(r"[\w\-./]+", texto or ""):
            a = self.activo_por_codigo.get(_codigo(palabra.strip(".-/")))
            if a is not None and a not in encontrados:
                encontrados.append(a)
        if not encontrados:
            a = self.activo_por_nombre.get(normalizar(texto))
            if a is not None:
                encontrados.append(a)
        return encontrados

    def proveedor(self, texto: str | None):
        from app.crud.meta.overrides.documentos import identificar_proveedor

        if not texto:
            return None
        if texto not in self._proveedores:
            self._proveedores[texto] = identificar_proveedor(None, texto)
        return self._proveedores[texto]


@dataclass
class Destino:
    """Lo que se identificó en «Detalles»."""
    tipo: str                       # activos / modelo / ubicacion / sector / ninguno / vacio
    activos: list = field(default_factory=list)
    modelo: object = None
    ubicacion: object = None
    sector: object = None
    por_equivalencia: bool = False


def leer_equivalencias(contenido: bytes) -> tuple[dict, list[str]]:
    """{(tipo, texto normalizado): (resultado, [códigos])} y los errores de formato."""
    from app.crud.intercambio.csv_entidades import _leer_texto

    texto = _leer_texto(contenido)
    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    columnas = [(c or "").strip() for c in (lector.fieldnames or [])]
    faltan = [c for c in COLUMNAS_EQUIVALENCIAS if c not in columnas]
    if faltan:
        return {}, [f"faltan las columnas: {', '.join(faltan)}"]
    equivalencias = {}
    for fila in lector:
        fila = {(k or "").strip(): (v or "").strip() for k, v in fila.items()}
        if not fila.get("texto"):
            continue
        codigos = [c.strip() for c in fila.get("codigos", "").split("|") if c.strip()]
        equivalencias[(fila["tipo"].lower(), normalizar(fila["texto"]))] = (fila["resultado"].lower(), codigos)
    return equivalencias, []


class Identificador:
    def __init__(self, maestros: Maestros, equivalencias: dict, r: ResultadoPedidosHistoricos):
        self.m, self.eq, self.r = maestros, equivalencias, r

    def material(self, producto: str, hoja: str, fila: int):
        eq = self.eq.get(("material", normalizar(producto)))
        if eq and eq[0] == "material_existente" and eq[1]:
            material = self.m.material_por_codigo.get(_codigo(eq[1][0]))
            if material is not None:
                self.r.conteo["equivalencias_usadas"] += 1
                return material
            self.r.avisar(hoja, fila, f"equivalencia de «{producto}»: el material «{eq[1][0]}» no está en el maestro")
        return self.m.material(producto)

    def destino(self, detalles: str | None, hoja: str, fila: int) -> Destino:
        if not detalles:
            return Destino("vacio")
        eq = self.eq.get(("destino", normalizar(detalles)))
        if eq and eq[0] not in ("sin_resolver", ""):
            d = self._de_equivalencia(eq, detalles, hoja, fila)
            if d is not None:
                self.r.conteo["equivalencias_usadas"] += 1
                return d
        activos = self.m.activos_en(detalles)
        if activos:
            return Destino("activos", activos=activos)
        n = normalizar(detalles)
        if n in self.m.modelo_por_nombre:
            return Destino("modelo", modelo=self.m.modelo_por_nombre[n])
        if n in self.m.ubicacion_por_nombre:
            return Destino("ubicacion", ubicacion=self.m.ubicacion_por_nombre[n])
        if n in self.m.sector_por_nombre:
            return Destino("sector", sector=self.m.sector_por_nombre[n])
        return Destino("ninguno")

    def _de_equivalencia(self, eq, detalles, hoja, fila) -> Destino | None:
        resultado, codigos = eq
        no_estan = []
        d = None
        if resultado in ("activo", "varios_activos"):
            activos = []
            for c in codigos:
                a = self.m.activo_por_numero.get(c.upper())
                (activos.append(a) if a is not None else no_estan.append(c))
            d = Destino("activos", activos=activos, por_equivalencia=True) if activos and not no_estan else None
        elif resultado in ("modelo", "ubicacion", "sector") and codigos:
            indice = {"modelo": self.m.modelo_por_nombre, "ubicacion": self.m.ubicacion_por_nombre,
                      "sector": self.m.sector_por_nombre}[resultado]
            obj = indice.get(normalizar(codigos[0]))
            if obj is None:
                no_estan.append(codigos[0])
            else:
                d = Destino(resultado, por_equivalencia=True, **{resultado: obj})
        if no_estan:
            self.r.avisar(hoja, fila, f"equivalencia de «{detalles}»: no están en la app {', '.join(no_estan)}")
        return d


def porcentajes(texto: str | None) -> list[tuple[float, str]] | None:
    """«40% CC-02, 30% CC-08» → [(40, "CC-02"), (30, "CC-08")]; None si no hay porcentajes."""
    if not texto or "%" not in texto:
        return None
    partes = re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;%]+?)\s*(?=[,;]|\s+\d+(?:[.,]\d+)?\s*%|$)", texto)
    return [(float(p.replace(",", ".")), s.strip(" -/y")) for p, s in partes] or None


def repartir(cantidad: float, n: int) -> list[float]:
    """En enteros con el resto al primero, si alcanza; si no, en partes iguales."""
    if n <= 1:
        return [cantidad]
    if float(cantidad).is_integer() and cantidad >= n:
        base = int(cantidad) // n
        partes = [float(base)] * n
        partes[0] += cantidad - base * n
        return partes
    return [cantidad / n] * n


# ---------------------------------------------------------------------------
# Importación
# ---------------------------------------------------------------------------

def importar_pedidos_historicos(contenido: bytes, *, nombre="pedidos.xlsx", equivalencias: bytes | None = None,
                                simular=False, usuario="importación") -> ResultadoPedidosHistoricos:
    r = ResultadoPedidosHistoricos(simulado=simular)
    eq = {}
    if equivalencias is not None:
        eq, errores = leer_equivalencias(equivalencias)
        for e in errores:
            r.errores.append(("equivalencias_revisadas.csv", "", "_columnas", e))
        if r.errores:
            return r
    try:
        libro = leer_libro(contenido)
    except Exception as e:  # el archivo no es un Excel que openpyxl pueda leer
        r.errores.append((nombre, "", "_archivo", f"no se pudo leer el Excel: {e}"))
        return r
    for hoja in libro.ignoradas:
        r.conteo["hojas_salteadas"] += 1
    for aviso in libro.avisos:
        r.avisar("", "", aviso)

    imp = _Importador(r, Identificador(Maestros(), eq, r), f"Importación del Excel histórico ({nombre})", usuario)
    try:
        for hoja in libro.hojas:
            r.conteo["hojas"] += 1
            imp.hoja(hoja)
    except _Abortar:
        pass

    if r.errores or simular:
        db.session.rollback()
        if r.errores:
            r.conteo = Counter()
        return r
    db.session.commit()
    return r


class _Importador:
    def __init__(self, r: ResultadoPedidosHistoricos, ident: Identificador, motivo: str, usuario: str):
        from app.crud.entidades import servicio

        self.r, self.ident, self.motivo, self.usuario = r, ident, motivo, usuario
        # Sin las reglas de borrador y envío (fase 13.2): estas líneas nacen
        # enviadas y, para ellas, la fuente es el Excel (una versión corregida
        # puede cambiar el material, la descripción o las cantidades).
        self.s = {e: servicio(e, confirmar=False, reglas_de_edicion=False) for e in (
            "pedidos", "pedido_lineas", "pedido_linea_destinos", "documentos_proveedor", "documento_lineas",
            "adjudicaciones")}
        self._motivo_anulacion = None

    # -- utilidades ---------------------------------------------------------
    def _guardar(self, entidad, existente, datos, hoja, fila, *, protegidos=(), solo_alta=()):
        """Crea o actualiza; devuelve (registro, 'creado' | 'actualizado' | None)."""
        try:
            if existente is None:
                return self.s[entidad].crear(datos, self.motivo, self.usuario), "creado"
            cambios = {}
            for c, v in datos.items():
                if c in solo_alta or getattr(existente, c) == v:
                    continue
                if c in protegidos and v is None and getattr(existente, c) is not None:
                    continue
                cambios[c] = v
            if not cambios:
                return existente, None
            return self.s[entidad].actualizar(existente, cambios, self.motivo, self.usuario), "actualizado"
        except ErroresValidacion as e:
            self.r.errores.extend((hoja, str(fila or ""), c, m) for c, m in e.errores.items())
        except ErrorIntegridad as e:
            self.r.errores.append((hoja, str(fila or ""), e.campo or "_base", e.mensaje))
        raise _Abortar()

    def _motivo_anulado(self):
        from app.models.motivos_models import MotivoOperacion

        if self._motivo_anulacion is None:
            m = MotivoOperacion.query.filter_by(tipo_operacion="ANULACION",
                                                nombre_motivo=MOTIVO_ANULACION_HISTORICO).first()
            if m is None:
                m = MotivoOperacion(tipo_operacion="ANULACION", nombre_motivo=MOTIVO_ANULACION_HISTORICO)
                db.session.add(m)
                db.session.flush()
            self._motivo_anulacion = m.motivo_operacion_id
        return self._motivo_anulacion

    # -- hoja ----------------------------------------------------------------
    def hoja(self, h: HojaPedido):
        from app.models.pedidos_models import Pedido

        r = self.r
        for motivo in h.revisar:
            r.avisar(h.hoja, "", motivo)
        if h.fecha is None:
            r.avisar(h.hoja, "", "no tiene fecha: no se importó")
            r.conteo["hojas_salteadas"] += 1
            return
        existente = Pedido.query.filter_by(clave_origen=h.clave).first()
        if existente is None:
            otro = Pedido.query.filter_by(numero=h.numero).first()
            if otro is not None:
                r.avisar(h.hoja, "", f"ya existe el pedido {h.numero} (cargado en la app o desde otra hoja): "
                                     "no se importó")
                r.conteo["hojas_salteadas"] += 1
                return
        datos = {
            "numero": h.numero, "fecha_pedido": h.fecha, "referencia": (h.referencia or "")[:150] or None,
            "solicitante_texto": ", ".join(h.solicitantes)[:150] or None,
            "observaciones": "\n".join(h.notas) or None,
            "motivo_revision": "; ".join(h.revisar) or None,
            "origen": "historico", "clave_origen": h.clave,
        }
        pedido, accion = self._guardar("pedidos", existente, datos, h.hoja, "", solo_alta=("motivo_revision",))
        r.conteo[{"creado": "pedidos_creados", "actualizado": "pedidos_actualizados"}.get(accion,
                                                                                         "pedidos_sin_cambios")] += 1

        contexto = f"Pedido {h.numero}" + (f" ({h.referencia})" if h.referencia else "")
        ofertas: dict[tuple, dict] = {}
        siguiente = max([l.nro_linea for l in pedido.lineas] + [0]) + 1
        for f in h.filas:
            linea, siguiente = self._linea(h, f, pedido, contexto, siguiente)
            if h.estado != ANULADO:
                self._juntar_cotizaciones(h, f, linea, ofertas)
        for (prov_norm, oc), oferta in ofertas.items():
            self._oferta(h, prov_norm, oc, oferta)

    # -- línea ---------------------------------------------------------------
    def _linea(self, h: HojaPedido, f, pedido, contexto, siguiente):
        from app.models.pedidos_models import PedidoLinea

        r = self.r
        clave = f"{h.clave}|f{f.fila}"
        material = self.ident.material(f.producto, h.hoja, f.fila)
        if material is not None:
            r.conteo["materiales_identificados"] += 1
        elif h.estado != ANULADO:
            r.pendiente("material", f.producto, f"{contexto}; detalle: {f.detalles or '-'}")

        observaciones = list(f.observaciones)
        estado, sin_conformidad = "solicitado", f.recibido_ok
        if h.estado == CERRADO:
            sin_conformidad = not f.recibido_no
            r.conteo["lineas_cerradas" if sin_conformidad else "lineas_en_proceso"] += 1
        elif h.estado == EN_PROCESO:
            estado = "en_cotizacion"
            r.conteo["lineas_en_proceso"] += 1
        elif h.estado == ANULADO:
            estado, sin_conformidad = "anulado", False
            r.conteo["lineas_anuladas"] += 1
            for cot in f.cotizaciones:
                observaciones.append(f"Precio de {cot.proveedor or 'proveedor sin nombre'}: {cot.texto} {cot.moneda}")
            if f.proveedor:
                observaciones.append(f"Proveedor: {f.proveedor}")
        else:
            r.conteo["lineas_solicitadas"] += 1
        if f.oc_completada:
            r.conteo["oc_completadas"] += 1
        if f.proveedor and not f.cotizaciones and h.estado != ANULADO:
            observaciones.append(f"Proveedor: {f.proveedor}")
        for cot in f.cotizaciones:
            if cot.proveedor is None and h.estado != ANULADO:
                observaciones.append(f"Precio sin proveedor: {cot.texto} {cot.moneda}")
        for motivo in f.revisar:
            r.avisar(h.hoja, f.fila, motivo)

        existente = PedidoLinea.query.filter_by(clave_origen=clave).first()
        datos = {
            "pedido_id": pedido.pedido_id, "material_id": material.material_id if material else None,
            "descripcion": f.producto[:200], "estado": estado, "sin_conformidad": sin_conformidad,
            "nro_oc": f.nro_oc, "observaciones": "\n".join(observaciones)[:1000] or None,
            "motivo_revision": "; ".join(f.revisar)[:1000] or None,
            "motivo_operacion_id": self._motivo_anulado() if estado == "anulado" else None,
            "origen": "historico", "clave_origen": clave,
        }
        if existente is None:
            datos["nro_linea"] = siguiente
            # Enviada a Compras con la fecha del pedido (decidido 26/11).
            datos["enviada_en"] = datetime.combine(h.fecha, time())  # sin fecha, la hoja no se importa
            siguiente += 1
        linea, accion = self._guardar("pedido_lineas", existente, datos, h.hoja, f.fila,
                                      protegidos=_PROTEGIDOS_LINEA, solo_alta=("motivo_revision",))
        if accion:
            r.conteo[_FEM[accion].replace("*", "lineas")] += 1
        self._destinos(h, f, linea, contexto)
        return linea, siguiente

    # -- destinos ------------------------------------------------------------
    def _destinos(self, h: HojaPedido, f, linea, contexto):
        from app.models.pedidos_models import PedidoLineaDestino

        r, m = self.r, self.ident.m
        if any(d.origen != "historico" for d in linea.destinos):
            r.avisar(h.hoja, f.fila, "la línea tiene destinos cargados en la app: no se tocaron")
            return
        cuenta = m.cuenta_por_texto.get(normalizar(f.cuenta)) if f.cuenta else None
        if f.cuenta and cuenta is None:
            r.avisar(h.hoja, f.fila, f"la cuenta «{f.cuenta}» no está en el maestro")
            r.faltan_en_maestro[("cuenta", f.cuenta)] += 1
        d = self.ident.destino(f.detalles, h.hoja, f.fila)
        if d.tipo in ("activos", "modelo", "ubicacion", "sector"):
            r.conteo["destinos_identificados"] += 1
        elif d.tipo == "ninguno" and h.estado != ANULADO:
            r.pendiente("destino", f.detalles, f"{contexto}; producto: {f.producto}")

        def base(dest: Destino):
            """(destino, activo, modelo, ubicación) de un destino identificado."""
            if dest.tipo == "activos" and len(dest.activos) == 1:
                return "activo", dest.activos[0], None, None
            if dest.tipo == "activos":
                modelos = {a.modelo_id for a in dest.activos}
                if len(modelos) == 1 and None not in modelos:
                    return "modelo", None, dest.activos[0].modelo, None
                return "a_identificar", None, None, None
            if dest.tipo == "modelo":
                return "modelo", None, dest.modelo, None
            if dest.tipo == "ubicacion":
                return "gasto_general", None, None, dest.ubicacion
            if dest.tipo in ("sector", "vacio"):
                return "gasto_general", None, None, None
            return "a_identificar", None, None, None

        # (cantidad, destino, activo, modelo, ubicación, sector)
        filas: list[tuple] = []
        partes = porcentajes(f.sector)
        if partes:
            total = sum(p for p, _ in partes)
            if abs(total - 100) > 0.01:
                r.avisar(h.hoja, f.fila, f"los porcentajes del sector suman {total:g} %: se repartió en proporción")
            tipo, activo, modelo, ubicacion = base(d)
            for pct, texto in partes:
                sector = m.sector_por_nombre.get(normalizar(texto))
                if sector is None:
                    r.avisar(h.hoja, f.fila, f"el sector «{texto}» no está en el maestro")
                    r.faltan_en_maestro[("sector", texto)] += 1
                filas.append((f.cantidad * pct / total, tipo, activo, modelo, ubicacion, sector))
        else:
            sector = m.sector_por_nombre.get(normalizar(f.sector)) if f.sector else None
            if f.sector and sector is None:
                r.avisar(h.hoja, f.fila, f"el sector «{f.sector}» no está en el maestro")
                r.faltan_en_maestro[("sector", f.sector)] += 1
            if sector is None and d.tipo == "sector":
                sector = d.sector
            if d.tipo == "activos" and len(d.activos) > 1:
                for cant, activo in zip(repartir(f.cantidad, len(d.activos)), d.activos):
                    filas.append((cant, "activo", activo, None, None, sector))
            else:
                tipo, activo, modelo, ubicacion = base(d)
                filas.append((f.cantidad, tipo, activo, modelo, ubicacion, sector))

        # Sin «Detalles» y con un material del maestro (decidido 23/11): es un
        # repuesto que va al stock del taller de su sector, si el sector tiene uno
        # solo; si no, queda «a identificar» con una nota. Lo que no está en el
        # maestro (ferretería, insumos) queda en gasto general.
        notas: dict[int, str] = {}
        if d.tipo == "vacio" and linea.material_id is not None:
            for i, (cant, tipo, activo, modelo, ubicacion, sector) in enumerate(filas):
                talleres = m.ubicaciones_por_sector.get(sector.sector_id, []) if sector else []
                if len(talleres) == 1:
                    filas[i] = (cant, "stock", None, None, talleres[0], sector)
                else:
                    filas[i] = (cant, "a_identificar", None, None, None, sector)
                    notas[i] = "Sin «Detalles»: repuesto para stock, falta el taller que lo recibe"
                    r.avisar(h.hoja, f.fila, "repuesto sin «Detalles»: no se pudo deducir el taller de stock "
                                             + ("(el sector no tiene ubicaciones)" if sector and not talleres
                                                else "(el sector tiene varias ubicaciones)" if talleres
                                                else "(no hay sector imputado)"))

        clave_linea = linea.clave_origen
        vistas = set()
        for i, (cant, tipo, activo, modelo, ubicacion, sector) in enumerate(filas, start=1):
            clave = f"{clave_linea}|d{i}"
            vistas.add(clave)
            existente = PedidoLineaDestino.query.filter_by(clave_origen=clave).first()
            datos = {
                "pedido_linea_id": linea.pedido_linea_id, "cantidad": round(cant, 6), "destino": tipo,
                "activo_id": activo.activo_id if activo else None,
                "modelo_id": modelo.modelo_id if modelo else None,
                "ubicacion_id": ubicacion.ubicacion_id if ubicacion else None,
                "detalle_texto": (f.detalles or "")[:300] or notas.get(i - 1),
                "sector_imputado_id": sector.sector_id if sector else None,
                "cuenta_id": cuenta.cuenta_id if cuenta else None,
                "origen": "historico", "clave_origen": clave,
            }
            # Un destino identificado (a mano o antes) no vuelve a «a identificar»,
            # salvo el gasto general que la importación puso a una línea sin «Detalles»
            # (si después se identificó el material, es un repuesto para stock).
            automatico = (existente is not None and existente.destino == "gasto_general"
                          and existente.detalle_texto is None and existente.ubicacion_id is None)
            if (existente is not None and tipo == "a_identificar" and existente.destino != "a_identificar"
                    and not automatico):
                for c in ("destino", "activo_id", "modelo_id", "ubicacion_id"):
                    datos.pop(c)
            _, accion = self._guardar("pedido_linea_destinos", existente, datos, h.hoja, f.fila,
                                      protegidos=_PROTEGIDOS_DESTINO)
            if accion:
                self.r.conteo[f"destinos_{accion}s"] += 1
        for dest in list(linea.destinos):
            if dest.clave_origen not in vistas:
                if getattr(dest, "recepciones", None):
                    r.avisar(h.hoja, f.fila, "un destino que ya no sale del Excel tiene recepciones: no se borró")
                    continue
                self.s["pedido_linea_destinos"].eliminar(dest, self.motivo, self.usuario)
                r.conteo["destinos_borrados"] += 1

    # -- ofertas -------------------------------------------------------------
    def _juntar_cotizaciones(self, h, f, linea, ofertas):
        for cot in f.cotizaciones:
            if cot.proveedor is None:
                continue
            oc = f.nro_oc if cot.elegida else None
            o = ofertas.setdefault((normalizar(cot.proveedor), oc), {"proveedor": cot.proveedor, "items": []})
            o["items"].append((f, linea, cot))

    def _oferta(self, h: HojaPedido, prov_norm, oc, oferta):
        from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor

        r = self.r
        clave = f"{h.clave}|oferta|{prov_norm}|{oc or ''}"
        existente = DocumentoProveedor.query.filter_by(clave_origen=clave).first()
        if existente is not None and existente.revisado:
            r.conteo["ofertas_revisadas_salteadas"] += 1
            return
        monedas = Counter(cot.moneda for _, _, cot in oferta["items"])
        moneda = monedas.most_common(1)[0][0]
        revisar = []
        if len(monedas) > 1:
            revisar.append("las líneas tienen monedas distintas: " + ", ".join(sorted(monedas)))
            r.avisar(h.hoja, "", f"oferta de «{oferta['proveedor']}»: líneas en monedas distintas")
        proveedor = self.ident.m.proveedor(oferta["proveedor"])
        datos = {
            "tipo": "oferta", "proveedor_texto": oferta["proveedor"][:200],
            "proveedor_id": proveedor.recurso_id if proveedor else None,
            "fecha": h.fecha, "moneda": moneda,
            "moneda_inferida": any(cot.moneda_inferida for _, _, cot in oferta["items"]),
            "nro_oc": oc, "motivo_revision": "; ".join(revisar) or None,
            "observaciones": f"Reconstruida del Excel histórico (pedido {h.numero}); la fecha es la del pedido.",
            "origen": "historico", "clave_origen": clave,
        }
        doc, accion = self._guardar("documentos_proveedor", existente, datos, h.hoja, "",
                                    protegidos=("proveedor_id",))
        if accion:
            r.conteo[_FEM[accion].replace("*", "ofertas")] += 1
        siguiente = max([l.nro_linea for l in doc.lineas] + [0]) + 1
        for f, linea, cot in oferta["items"]:
            clave_l = f"{clave}|f{f.fila}"
            material = linea.material
            ex = DocumentoLinea.query.filter_by(clave_origen=clave_l).first()
            datos_l = {
                "documento_id": doc.documento_id, "tipo_linea": "material",
                "material_id": material.material_id if material is not None and not material.es_generico else None,
                "descripcion_proveedor": f.producto[:300], "cantidad": f.cantidad,
                "precio_unitario": round(cot.precio_unitario, 6), "origen": "historico", "clave_origen": clave_l,
            }
            if ex is None:
                datos_l["nro_linea"] = siguiente
                siguiente += 1
            lo, accion = self._guardar("documento_lineas", ex, datos_l, h.hoja, f.fila, protegidos=("material_id",))
            if accion == "creado":
                r.conteo["lineas_oferta_creadas"] += 1
            if linea.estado == "anulado":
                continue
            if material is not None and material.es_generico and lo.material_id is None:
                r.avisar(h.hoja, f.fila, "la línea pide un genérico: la oferta no se adjudicó (falta la presentación)")
                continue
            cantidad = f.cantidad if cot.elegida else 0.0
            adj = Adjudicacion.query.filter_by(documento_linea_id=lo.documento_linea_id,
                                               pedido_linea_id=linea.pedido_linea_id).first()
            _, accion = self._guardar("adjudicaciones", adj, {
                "documento_linea_id": lo.documento_linea_id, "pedido_linea_id": linea.pedido_linea_id,
                "cantidad_adjudicada": cantidad}, h.hoja, f.fila)
            if accion == "creado":
                r.conteo["adjudicaciones_creadas"] += 1
