// La venta en curso vive fuera de la pantalla de Vender: si el cajero va a Caja o a
// Productos y vuelve, encuentra los mismos productos. Se guarda por usuario y se
// borra al cerrar sesión, para que otro cajero no herede una venta ajena.

import { useCallback, useSyncExternalStore } from "react";
import type { CartLine } from "./cart";

const carts = new Map<string, CartLine[]>();
const listeners = new Set<() => void>();
const EMPTY: CartLine[] = [];

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() {
  for (const listener of listeners) listener();
}

export function clearCarts() {
  carts.clear();
  notify();
}

export function useCart(userId: string): [CartLine[], (change: CartLine[] | ((current: CartLine[]) => CartLine[])) => void] {
  const lines = useSyncExternalStore(subscribe, () => carts.get(userId) ?? EMPTY);
  const setLines = useCallback(
    (change: CartLine[] | ((current: CartLine[]) => CartLine[])) => {
      const current = carts.get(userId) ?? EMPTY;
      carts.set(userId, typeof change === "function" ? change(current) : change);
      notify();
    },
    [userId],
  );
  return [lines, setLines];
}
