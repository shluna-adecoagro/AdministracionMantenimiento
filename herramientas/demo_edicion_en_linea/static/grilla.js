// grilla.js — navegación y edición tipo planilla sobre las tablas .grilla.
//
// htmx hace los pedidos y los reemplazos; esto solo maneja el teclado y el foco:
//   * flechas para moverse; Enter, F2 o empezar a escribir para editar;
//   * en edición: Enter guarda y baja, Tab guarda y va a la derecha, Esc cancela;
//     salir de la celda (clic afuera) también guarda;
//   * Ctrl+V de varias filas copiadas de Excel → vista previa del pegado.
(function () {
    "use strict";

    let mover = null;        // "abajo" | "derecha" | "izquierda" | null: adónde ir después de guardar
    let primeraTecla = null; // la tecla que inició la edición (se escribe en el input)
    let cancelando = false;

    // ------------------------------------------------------------ utilidades
    const filasDe = (td) => Array.from(td.closest("tbody").querySelectorAll(":scope > tr.fila"));
    const celdasDe = (tr) => Array.from(tr.querySelectorAll(":scope > td[data-campo]"));

    function enfocar(td) {
        if (!td) return;
        document.querySelectorAll(".grilla td.activa").forEach((c) => c.classList.remove("activa"));
        td.classList.add("activa");
        td.setAttribute("tabindex", "0");
        td.focus();
    }

    function vecina(td, direccion) {
        const tr = td.closest("tr");
        const celdas = celdasDe(tr);
        const i = celdas.indexOf(td);
        if (direccion === "derecha") return celdas[i + 1] || null;
        if (direccion === "izquierda") return celdas[i - 1] || null;
        const filas = filasDe(td);
        const j = filas.indexOf(tr) + (direccion === "abajo" ? 1 : -1);
        return filas[j] ? celdasDe(filas[j])[i] || null : null;
    }

    const editando = () => document.querySelector(".grilla td.editando");

    function guardar(td) {
        const form = td && td.querySelector("form");
        if (form) form.requestSubmit();
    }

    function cancelar(td) {
        const trId = td.closest("tr").id;
        const campo = td.dataset.campo;
        cancelando = true;
        mover = null;
        htmx.ajax("GET", td.dataset.cancelar, { target: "#" + trId, swap: "outerHTML" }).then(() => {
            cancelando = false;
            const tr = document.getElementById(trId);
            if (tr) enfocar(tr.querySelector(`td[data-campo="${campo}"]`));
        });
    }

    // ------------------------------------------------------------ teclado
    document.addEventListener("keydown", (e) => {
        const td = e.target.closest && e.target.closest(".grilla td[data-campo]");
        if (!td) return;

        // --- Celda en edición
        if (td.classList.contains("editando")) {
            if (e.key === "Escape") { e.preventDefault(); cancelar(td); }
            else if (e.key === "Enter") { e.preventDefault(); mover = "abajo"; guardar(td); }
            else if (e.key === "Tab") { e.preventDefault(); mover = e.shiftKey ? "izquierda" : "derecha"; guardar(td); }
            return;
        }

        // --- Celda en lectura
        const flechas = { ArrowDown: "abajo", ArrowUp: "arriba", ArrowRight: "derecha", ArrowLeft: "izquierda" };
        if (flechas[e.key]) { e.preventDefault(); enfocar(vecina(td, flechas[e.key])); return; }
        if (e.key === "Tab") {
            const otra = vecina(td, e.shiftKey ? "izquierda" : "derecha");
            if (otra) { e.preventDefault(); enfocar(otra); }
            return;
        }
        if (!td.classList.contains("celda")) return; // calculada: no se edita
        if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); htmx.trigger(td, "editar"); return; }
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            primeraTecla = e.key;
            htmx.trigger(td, "editar");
        }
    });

    // Clic en una celda: seleccionarla; doble clic: editarla.
    document.addEventListener("click", (e) => {
        const td = e.target.closest(".grilla td[data-campo]");
        if (td && !td.classList.contains("editando")) enfocar(td);
    });
    document.addEventListener("dblclick", (e) => {
        const td = e.target.closest(".grilla td.celda");
        if (td && !td.classList.contains("editando")) htmx.trigger(td, "editar");
    });

    // Un select guarda al elegir (y se queda en la celda).
    document.addEventListener("change", (e) => {
        const td = e.target.closest(".grilla td.editando");
        if (td && e.target.tagName === "SELECT") { mover = null; guardar(td); }
    });

    // Salir de la celda en edición (clic afuera) guarda.
    document.addEventListener("focusout", (e) => {
        const td = e.target.closest && e.target.closest(".grilla td.editando");
        if (!td || cancelando) return;
        setTimeout(() => {
            if (cancelando || !td.isConnected || td.contains(document.activeElement)) return;
            if (mover === null) mover = "ninguno";
            guardar(td);
        }, 0);
    });

    // Abrir o cerrar los destinos de una línea: si ya están abiertos, se cierran
    // sin pedido (fase de captura: antes de que htmx vea el clic).
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".btn-destinos");
        if (!btn) return;
        const sub = document.getElementById(btn.dataset.sub);
        if (sub && sub.innerHTML.trim()) {
            e.stopPropagation();
            e.preventDefault();
            sub.innerHTML = "";
        }
    }, true);

    // ------------------------------------------------------------ después de cada reemplazo
    document.addEventListener("htmx:afterSettle", () => {
        // Se abrió una celda para editar: foco en su control.
        const td = editando();
        if (td) {
            const control = td.querySelector("input, select");
            if (control && document.activeElement !== control) {
                control.focus();
                if (primeraTecla !== null && control.tagName === "INPUT") control.value = primeraTecla;
                else if (control.select) control.select();
            }
            primeraTecla = null;
            mover = null;
            return;
        }

        // Se guardó: la fila nueva dice qué celda tenía el foco (data-foco).
        const fila = document.querySelector("tr[data-foco]");
        if (fila) {
            const celda = fila.querySelector(`td[data-campo="${fila.dataset.foco}"]`);
            fila.removeAttribute("data-foco");
            const destino = mover && mover !== "ninguno" ? vecina(celda, mover) || celda : celda;
            if (mover !== "ninguno") enfocar(destino);
            mover = null;
        }
    });

    // ------------------------------------------------------------ redistribuir
    // Suma en vivo (la validación de verdad la hace el servidor al guardar).
    function actualizarSuma(form) {
        const total = parseFloat(form.dataset.total);
        let suma = 0;
        form.querySelectorAll("tbody input[name=cantidad]").forEach((i) => {
            suma += parseFloat((i.value || "0").replace(",", ".")) || 0;
        });
        const b = form.querySelector(".suma");
        b.textContent = Number(suma.toFixed(6)).toString();
        form.querySelector(".total-redistribuir").classList.toggle("descuadre", Math.abs(suma - total) > 1e-9);
    }
    document.addEventListener("input", (e) => {
        const form = e.target.closest("form.redistribuir");
        if (form) actualizarSuma(form);
    });
    document.addEventListener("click", (e) => {
        const form = e.target.closest("form.redistribuir");
        if (!form) return;
        if (e.target.closest(".btn-agregar-fila")) {
            const fila = form.querySelector("template").content.firstElementChild.cloneNode(true);
            form.querySelector("tbody").appendChild(fila);
            fila.querySelector("input[name=cantidad]").focus();
        } else if (e.target.closest(".btn-quitar-fila")) {
            e.target.closest("tr").remove();
        } else {
            return;
        }
        actualizarSuma(form);
    });
    document.addEventListener("htmx:afterSettle", () => {
        document.querySelectorAll("form.redistribuir").forEach(actualizarSuma);
    });

    // ------------------------------------------------------------ pegar desde Excel
    document.addEventListener("paste", (e) => {
        const td = e.target.closest && e.target.closest("#grilla-lineas > tbody > tr.fila > td");
        if (!td || td.classList.contains("editando")) return;
        const texto = (e.clipboardData || window.clipboardData).getData("text");
        if (!texto || !/[\t\n]/.test(texto.trim())) return; // un solo valor: nada especial
        e.preventDefault();
        htmx.ajax("POST", "/pegar", { target: "#pegado", values: { texto } });
    });
})();
