// Dinero en centavos enteros y cantidades en milésimas: nunca se suman decimales binarios.
// El servidor siempre recalcula; aquí solo se muestra una vista previa exacta del carrito.

export type Cents = number;

/** "12500.5" → 1250050. Acepta coma decimal y punto de miles ("12.500,50"). */
export function toCents(text: string | number): Cents {
  const value = parseDecimal(String(text), 2);
  return value ?? 0;
}

/** Cantidad en milésimas: "1.5" → 1500. */
export function toThousandths(text: string | number): number {
  return parseDecimal(String(text), 3) ?? 0;
}

/** Devuelve el número escalado (10^decimals) o null si el texto no es un número válido. */
export function parseDecimal(raw: string, decimals: number): number | null {
  let text = raw.trim().replace(/\s|\$/g, "");
  if (!text) return null;
  const negative = text.startsWith("-");
  if (negative) text = text.slice(1);
  if (text.includes(",")) {
    // Formato colombiano: 12.500,50
    text = text.replace(/\./g, "").replace(",", ".");
  } else if (decimals === 2 && /^\d{1,3}(\.\d{3})+$/.test(text)) {
    // Dinero escrito como 12.500: los puntos son separadores de miles (en cantidades, 1.500 es kilo y medio)
    text = text.replace(/\./g, "");
  }
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  const digits = (fraction + "0".repeat(decimals + 1)).slice(0, decimals + 1);
  let scaled = Number(whole) * 10 ** decimals + Number(digits.slice(0, decimals) || 0);
  if (Number(digits[decimals]) >= 5) scaled += 1; // redondeo hacia arriba en la mitad, como el servidor
  return negative ? -scaled : scaled;
}

/** Centavos → texto para la API: 1250050 → "12500.50". */
export function centsToApi(cents: Cents): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.trunc(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

export function thousandthsToApi(value: number): string {
  const whole = Math.trunc(value / 1000);
  const fraction = String(value % 1000).padStart(3, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : String(whole);
}

function roundHalfUp(numerator: number, denominator: number): number {
  const sign = numerator < 0 ? -1 : 1;
  return sign * Math.floor((Math.abs(numerator) * 2 + denominator) / (2 * denominator));
}

/** Precio unitario por cantidad (milésimas), redondeado a centavos. */
export function lineGross(priceCents: Cents, quantityThousandths: number): Cents {
  return roundHalfUp(priceCents * quantityThousandths, 1000);
}

/** Total a pagar de una línea según si los precios ya incluyen el impuesto. */
export function lineTotal(net: Cents, taxRatePercent: string, pricesIncludeTax: boolean): Cents {
  if (pricesIncludeTax) return net;
  const rateHundredths = toCents(taxRatePercent); // 19 % → 1900
  return net + roundHalfUp(net * rateHundredths, 10000);
}

const moneyFormat = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

/** 1250050 → "$12.500,5" ; acepta también el texto de la API. */
export function formatMoney(value: Cents | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const cents = typeof value === "string" ? toCents(value) : value;
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents) / 100;
  const decimals = Math.abs(cents) % 100 === 0 ? 0 : 2;
  return `${sign}$${abs.toLocaleString("es-CO", { minimumFractionDigits: decimals, maximumFractionDigits: 2 })}`;
}

export function formatQuantity(value: string | number): string {
  return moneyFormat.format(Number(value));
}
