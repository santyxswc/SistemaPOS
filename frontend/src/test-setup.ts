// Node 25 en adelante trae su propio `localStorage`, que sin --localstorage-file no
// funciona y tapa el de jsdom. En las pruebas se usa siempre el del navegador simulado.

declare const jsdom: { window: Window } | undefined;

if (typeof jsdom !== "undefined") {
  for (const name of ["localStorage", "sessionStorage"] as const) {
    Object.defineProperty(globalThis, name, { value: jsdom.window[name], configurable: true, writable: true });
  }
}
