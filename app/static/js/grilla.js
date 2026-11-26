// grilla.js — navegación y edición tipo planilla sobre las tablas .grilla.
//
// htmx hace los pedidos y los reemplazos; esto solo maneja el teclado y el foco:
//   * flechas para moverse; Enter, F2 o empezar a escribir para editar;
//   * en edición: Enter guarda y baja, Tab guarda y va a la derecha, Esc cancela;
//     salir de la celda (clic afuera) también guarda.
//
// Las filas y celdas las arma el servidor desde la spec (crud/partials/_fila.html
// y _celda_edicion.html). Viene de la demo herramientas/demo_edicion_en_linea/.
(function () {
    "use strict";

    let mover = null;        // "abajo" | "derecha" | "izquierda" | null: adónde ir después de guardar
    let primeraTecla = null; // lo escrito al iniciar la edición (se pone en el input)
    let cancelando = false;
    // Mientras se pide la celda en edición, lo que se escribe se guarda acá (si no,
    // escribiendo rápido se perderían las teclas que llegan antes que el input).
    let abriendo = false;
    let alAbrir = null;      // Enter o Tab apretados antes de que llegue el input

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
        if (!form) return;
        // Si la celda acaba de llegar, htmx puede no haber procesado todavía su
        // hx-post (elegir en un select al instante): sin esto, el form se enviaría
        // solo, como GET a la página. process() no hace nada si ya está procesado.
        htmx.process(form);
        form.requestSubmit();
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
    function abrir(td, tecla) {
        primeraTecla = tecla;
        abriendo = true;
        alAbrir = null;
        htmx.trigger(td, "editar");
    }

    document.addEventListener("keydown", (e) => {
        if (abriendo) {
            if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                primeraTecla = (primeraTecla || "") + e.key;
            } else if (e.key === "Backspace" && primeraTecla) {
                e.preventDefault();
                primeraTecla = primeraTecla.slice(0, -1);
            } else if (e.key === "Enter" || e.key === "Tab") {
                e.preventDefault();
                alAbrir = e.key === "Enter" ? "abajo" : (e.shiftKey ? "izquierda" : "derecha");
            }
            return;
        }
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
        if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); abrir(td, null); return; }
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            abrir(td, e.key);
        }
    });

    // Clic en una celda: seleccionarla; doble clic: editarla.
    document.addEventListener("click", (e) => {
        const td = e.target.closest(".grilla td[data-campo]");
        if (td && !td.classList.contains("editando")) enfocar(td);
    });
    document.addEventListener("dblclick", (e) => {
        const td = e.target.closest(".grilla td.celda");
        if (td && !td.classList.contains("editando")) abrir(td, null);
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

    // Si no se pudo abrir la celda (error del servidor o de red), no quedar esperando.
    document.addEventListener("htmx:responseError", () => { abriendo = false; alAbrir = null; primeraTecla = null; });
    document.addEventListener("htmx:sendError", () => { abriendo = false; alAbrir = null; primeraTecla = null; });

    // ------------------------------------------------------------ después de cada reemplazo
    document.addEventListener("htmx:afterSettle", () => {
        // Se abrió una celda para editar: foco en su control.
        const td = editando();
        if (td) {
            const control = td.querySelector("input, select");
            // (también después de un 422: la celda vuelve abierta con el error)
            if (control && document.activeElement !== control) {
                control.focus();
                if (primeraTecla !== null && control.tagName === "INPUT") control.value = primeraTecla;
                else if (control.select) control.select();
            }
            const pendiente = abriendo ? alAbrir : null;
            abriendo = false;
            alAbrir = null;
            primeraTecla = null;
            mover = null;
            if (pendiente) { mover = pendiente; guardar(td); }
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
})();
