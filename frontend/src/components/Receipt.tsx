// Tiquete para impresora térmica de 80 mm (se imprime con el diálogo del navegador).

import { formatMoney, formatQuantity } from "../money";
import { useSession } from "../session";
import type { Sale, Settings } from "../types";
import { logoUrl } from "./Branding";
import { formatDateTime } from "./ui";

export function Receipt({ sale, settings, customerName }: { sale: Sale; settings: Settings; customerName?: string }) {
  const { branding } = useSession();
  return (
    <div className="receipt">
      <div className="center">
        {branding.logo_version && <img className="receipt-logo" src={logoUrl(branding.logo_version)} alt="" />}
        <strong>{settings.business_name}</strong>
        {settings.tax_id && <div>NIT {settings.tax_id}</div>}
        {settings.address && <div>{settings.address}</div>}
        {settings.phone && <div>Tel. {settings.phone}</div>}
      </div>
      <hr />
      <div>Venta #{sale.number}</div>
      <div>{formatDateTime(sale.created_at)}</div>
      {customerName && <div>Cliente: {customerName}</div>}
      {sale.status === "voided" && <div><strong>*** ANULADA ***</strong></div>}
      <hr />
      <table>
        <tbody>
          {sale.lines.map((line, index) => (
            <tr key={index}>
              <td>
                {line.description}
                <br />
                {formatQuantity(line.quantity)} x {formatMoney(line.unit_price)}
                {line.discount !== "0.00" && ` (-${formatMoney(line.discount)})`}
              </td>
              <td className="num">{formatMoney(line.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <hr />
      <table>
        <tbody>
          <tr>
            <td>Subtotal</td>
            <td className="num">{formatMoney(sale.subtotal)}</td>
          </tr>
          <tr>
            <td>Impuestos</td>
            <td className="num">{formatMoney(sale.tax_total)}</td>
          </tr>
          {sale.discount_total !== "0.00" && (
            <tr>
              <td>Descuentos</td>
              <td className="num">-{formatMoney(sale.discount_total)}</td>
            </tr>
          )}
          <tr>
            <td>
              <strong>TOTAL</strong>
            </td>
            <td className="num">
              <strong>{formatMoney(sale.total)}</strong>
            </td>
          </tr>
          {sale.payments.map((payment, index) => (
            <tr key={index}>
              <td>{payment.name}</td>
              <td className="num">{formatMoney(payment.amount)}</td>
            </tr>
          ))}
          {sale.change !== "0.00" && (
            <tr>
              <td>Cambio</td>
              <td className="num">{formatMoney(sale.change)}</td>
            </tr>
          )}
        </tbody>
      </table>
      <hr />
      <div className="center">{settings.receipt_footer}</div>
    </div>
  );
}
