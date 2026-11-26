/*
 * Selectores de opciones de formularios y filtros.
 *
 * Un campo se elige con un <select> o, si la lista es larga, con un «campo con
 * lista» (ver crud/partials/_selector.html): un <input> con <datalist> que se
 * acorta al tipear, más un input oculto con el valor (el ID). Las pantallas los
 * manejan igual, con la misma interfaz:
 *
 *   campo, el, opciones ([{valor, deps}]), valor(), fijar(v),
 *   filtrar(admite, conGrupo), alCambiar(fn({elegido}))
 *
 * `elegido` dice si el usuario terminó de elegir: en un select, siempre; en un
 * campo con lista, al tomar una opción de la lista o al salir del campo (no
 * mientras tipea).
 */
(function () {
    const MENSAJE = "Elegí una opción de la lista.";
    const norm = t => (t || "").trim().toLocaleLowerCase("es");
    const leerDeps = el => (el.dataset.deps ? JSON.parse(el.dataset.deps) : null);

    function deSelect(sel) {
        const originales = Array.from(sel.options).map(o => o.cloneNode(true));
        const oyentes = [];
        const avisar = elegido => oyentes.forEach(fn => fn({ elegido }));
        sel.addEventListener("change", () => avisar(true));
        return {
            campo: sel.dataset.campo,
            el: sel,
            opciones: originales.filter(o => o.value !== "").map(o => ({ valor: o.value, deps: leerDeps(o) })),
            valor: () => sel.value,
            fijar(v) {
                sel.value = String(v);
                if (sel.value !== String(v)) sel.value = "";
                avisar(false);
            },
            // Deja las opciones que admite; con conGrupo, las dependientes muestran
            // sus padres entre paréntesis (si falta elegir alguno).
            filtrar(admite, conGrupo) {
                const actual = sel.value;
                sel.innerHTML = "";
                originales.forEach(o => {
                    const d = leerDeps(o);
                    if (o.value !== "" && !admite(d)) return;
                    const copia = o.cloneNode(true);
                    if (d && o.dataset.label) {
                        copia.textContent = (conGrupo && o.dataset.grupo)
                            ? `${o.dataset.label} (${o.dataset.grupo})` : o.dataset.label;
                    }
                    sel.appendChild(copia);
                });
                if (Array.from(sel.options).some(o => o.value === actual)) {
                    sel.value = actual;
                } else {
                    sel.selectedIndex = 0;
                    if (sel.value !== actual) avisar(false);
                }
            },
            alCambiar: fn => oyentes.push(fn),
        };
    }

    function deLista(input) {
        const oculto = document.getElementById(input.id + "__valor");
        const lista = document.getElementById(input.id + "__lista");
        const originales = Array.from(lista.options).map(o => ({
            texto: o.value, valor: o.dataset.valor, deps: leerDeps(o),
        }));
        let visibles = originales;
        let ultimoElegido = oculto.value;
        const oyentes = [];
        const avisar = elegido => {
            if (elegido) ultimoElegido = oculto.value;
            oyentes.forEach(fn => fn({ elegido }));
        };
        const buscar = texto => visibles.find(o => norm(o.texto) === norm(texto));

        // Lleva el texto tipeado al valor oculto; un texto que no es una opción
        // deja el valor vacío y el campo inválido.
        function sincronizar(elegido) {
            const o = buscar(input.value);
            input.setCustomValidity(input.value.trim() && !o ? MENSAJE : "");
            const nuevo = o ? o.valor : "";
            if (nuevo !== oculto.value) {
                oculto.value = nuevo;
                avisar(elegido);
            }
        }

        input.addEventListener("input", e => {
            // Sin inputType (Chrome) o con insertReplacementText (Firefox): se
            // tomó una opción de la lista. Si no, se está tipeando.
            sincronizar(!e.inputType || e.inputType === "insertReplacementText");
        });
        input.addEventListener("change", () => {
            sincronizar(false);
            const o = buscar(input.value);
            if (o) input.value = o.texto;  // con las mayúsculas de la opción
            if (oculto.value !== ultimoElegido) avisar(true);
        });

        return {
            campo: input.dataset.campo,
            el: input,
            opciones: originales,
            valor: () => oculto.value,
            fijar(v) {
                const o = originales.find(op => op.valor === String(v));
                input.value = o ? o.texto : "";
                oculto.value = o ? o.valor : "";
                input.setCustomValidity("");
                ultimoElegido = oculto.value;
                avisar(false);
            },
            filtrar(admite) {
                visibles = originales.filter(o => admite(o.deps));
                lista.innerHTML = "";
                visibles.forEach(o => {
                    const op = document.createElement("option");
                    op.value = o.texto;
                    lista.appendChild(op);
                });
                if (oculto.value && !visibles.some(o => o.valor === oculto.value)) {
                    input.value = "";
                    oculto.value = "";
                    avisar(false);
                }
                input.setCustomValidity(input.value.trim() && !buscar(input.value) ? MENSAJE : "");
            },
            alCambiar: fn => oyentes.push(fn),
        };
    }

    /* Selectores dentro de `raiz` que cumplen `filtro` (selector CSS), por campo. */
    function de(raiz, filtro) {
        const resultado = {};
        raiz.querySelectorAll(filtro).forEach(el => {
            if (!el.dataset.campo) return;
            resultado[el.dataset.campo] = el.tagName === "SELECT" ? deSelect(el) : deLista(el);
        });
        return resultado;
    }

    /*
     * Selectores dependientes (ej: modelo según la marca y la categoría, ubicación
     * según el sector). Cada opción del hijo lleva data-deps: {campo padre: valor
     * del padre al que pertenece}.
     *  - Con padres elegidos, el hijo ofrece solo las opciones que coinciden con todos.
     *  - completarPadres: al elegir el hijo, los padres vacíos se completan solos.
     */
    function enlazarDependientes(selectores, { completarPadres = false } = {}) {
        Object.values(selectores).forEach(hijo => {
            const conDeps = hijo.opciones.find(o => o.deps);
            if (!conDeps) return;
            const padres = Object.keys(conDeps.deps).map(c => selectores[c]).filter(Boolean);
            if (!padres.length) return;

            const aplicar = () => {
                const elegidos = padres.filter(p => p.valor() !== "");
                hijo.filtrar(
                    d => !d || elegidos.every(p => String(d[p.campo] ?? "") === p.valor()),
                    elegidos.length < padres.length,
                );
            };
            aplicar();
            padres.forEach(p => p.alCambiar(aplicar));

            if (completarPadres) {
                hijo.alCambiar(() => {
                    const o = hijo.opciones.find(op => op.valor === hijo.valor());
                    if (!o || !o.deps) return;
                    padres.forEach(p => {
                        if (!p.valor() && o.deps[p.campo] !== null && o.deps[p.campo] !== undefined) {
                            p.fijar(String(o.deps[p.campo]));
                        }
                    });
                });
            }
        });
    }

    window.Selectores = { de, enlazarDependientes };
})();
