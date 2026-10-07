// Tipos de la API. El dinero y las cantidades llegan como texto para no perder exactitud.

export type Permission =
  | "manage_users"
  | "manage_settings"
  | "manage_catalog"
  | "manage_inventory"
  | "manage_suppliers"
  | "sell"
  | "apply_discounts"
  | "void_sales"
  | "operate_cash"
  | "supervise_cash"
  | "manage_customers"
  | "grant_credit"
  | "collect_payments"
  | "view_reports";

export type Role = "admin" | "supervisor" | "cashier";

/** Módulos que el técnico enciende o apaga por cliente (src/pos/application/modules.py). */
export type ModuleId =
  | "clientes"
  | "fiado"
  | "proveedores"
  | "reportes"
  | "descuentos"
  | "permisos"
  | "excel"
  | "impresion"
  | "facturacion"
  | "actualizaciones"
  | "licencias";

export interface ModuleInfo {
  id: ModuleId;
  name: string;
  description: string;
  enabled: boolean;
}

export interface Branding {
  business_name: string;
  logo_version: string | null;
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrador",
  supervisor: "Supervisor",
  cashier: "Cajero",
};

export interface Me {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  permissions: Permission[];
}

export interface User {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  active: boolean;
  created_at: string;
}

export type PaymentKind = "cash" | "electronic" | "credit";

export interface PaymentMethod {
  code: string;
  name: string;
  kind: PaymentKind;
  active: boolean;
}

export type PrinterKind = "browser" | "windows" | "network";

export interface PrinterConfig {
  kind: PrinterKind;
  target: string;
  width: number;
  auto_print: boolean;
  open_drawer: boolean;
}

export interface Settings {
  business_name: string;
  tax_id: string;
  address: string;
  phone: string;
  currency: string;
  timezone: string;
  prices_include_tax: boolean;
  default_tax_rate: string;
  allow_negative_stock: boolean;
  credit_sales_enabled: boolean;
  receipt_footer: string;
  backup_folder: string;
  payment_methods: PaymentMethod[];
  printer: PrinterConfig;
}

export interface LicenseStatus {
  state: "trial" | "active" | "trial_expired" | "expired";
  valid: boolean;
  needs_attention: boolean;
  message: string;
  max_users: number | null;
  expires_on: string | null;
  days_left: number | null;
  license: {
    id: string;
    business_name: string;
    plan: string;
    max_users: number | null;
    issued_on: string;
    expires_on: string | null;
  } | null;
}

export interface BackupFile {
  name: string;
  created_at: string;
  size_bytes: number;
}

export interface BackupResult {
  file: BackupFile;
  extra_copy: string | null;
  extra_error: string | null;
}

export type Unit = "unit" | "kg" | "lb" | "l";

export interface Category {
  id: string;
  name: string;
  active: boolean;
}

export interface Product {
  id: string;
  sku: string;
  barcode: string | null;
  name: string;
  category_id: string | null;
  price: string;
  cost: string;
  tax_rate: string;
  unit: Unit;
  track_stock: boolean;
  stock: string;
  min_stock: string;
  is_low_stock: boolean;
  active: boolean;
  updated_at: string;
}

export interface StockMovement {
  id: string;
  type: "initial" | "purchase" | "adjustment" | "sale" | "sale_void";
  quantity: string;
  stock_after: string;
  unit_cost: string | null;
  reference: string | null;
  note: string;
  created_at: string;
}

export interface Customer {
  id: string;
  name: string;
  document: string | null;
  phone: string;
  email: string;
  address: string;
  credit_limit: string;
  balance: string;
  available_credit: string;
  active: boolean;
}

export interface LedgerEntry {
  id: string;
  type: "charge" | "payment" | "reversal";
  amount: string;
  balance_after: string;
  sale_id: string | null;
  note: string;
  created_at: string;
}

export interface CashMovement {
  id: string;
  type: "sale" | "sale_void" | "deposit" | "withdrawal" | "credit_collection" | "supplier_payment";
  amount: string;
  reference: string | null;
  note: string;
  created_at: string;
}

export interface CashSession {
  id: string;
  cashier_id: string;
  status: "open" | "closed";
  opening_amount: string;
  expected_cash: string;
  counted_amount: string | null;
  difference: string | null;
  opened_at: string;
  closed_at: string | null;
  closing_note: string;
  movements: CashMovement[];
}

export interface PaymentTotal {
  method: string;
  name: string;
  kind: PaymentKind;
  amount: string;
}

export interface CashReport {
  session: CashSession;
  sales_count: number;
  voided_count: number;
  sales_total: string;
  totals_by_method: PaymentTotal[];
  units_sold: string;
  products: ProductSales[];
}

export interface SaleLine {
  product_id: string;
  sku: string;
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  tax_rate: string;
  base: string;
  tax: string;
  total: string;
}

export interface Sale {
  id: string;
  number: number;
  status: "completed" | "voided";
  cashier_id: string;
  customer_id: string | null;
  subtotal: string;
  tax_total: string;
  discount_total: string;
  total: string;
  change: string;
  note: string;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
  lines: SaleLine[];
  payments: PaymentTotal[];
}

export interface SalesSummary {
  from: string;
  to: string;
  group_by: "day" | "month";
  sales_count: number;
  voided_count: number;
  subtotal: string;
  tax_total: string;
  discount_total: string;
  total: string;
  average_ticket: string;
  by_payment_method: PaymentTotal[];
  by_period: { period: string; sales_count: number; total: string }[];
}

export interface ProductSales {
  product_id: string;
  sku: string;
  description: string;
  quantity: string;
  total: string;
}

export interface Supplier {
  id: string;
  name: string;
  document: string | null;
  contact_name: string;
  phone: string;
  email: string;
  address: string;
  notes: string;
  balance: string;
  active: boolean;
}

export type PurchasePaymentMode = "cash_drawer" | "external" | "credit";

export interface PurchaseLine {
  product_id: string;
  sku: string;
  description: string;
  quantity: string;
  unit_cost: string;
  total: string;
}

export interface Purchase {
  id: string;
  number: number;
  supplier_id: string | null;
  supplier_name: string | null;
  invoice_number: string;
  payment_mode: PurchasePaymentMode;
  status: "paid" | "pending";
  total: string;
  outstanding: string;
  due_date: string | null;
  overdue: boolean;
  note: string;
  created_at: string;
  lines: PurchaseLine[];
}

export interface SupplierEntry {
  id: string;
  type: "purchase" | "payment";
  amount: string;
  balance_after: string;
  purchase_id: string | null;
  method: string;
  note: string;
  created_at: string;
}

export interface SupplierStatement {
  supplier: Supplier;
  entries: SupplierEntry[];
  pending: Purchase[];
}

export interface Payables {
  today: string;
  total: string;
  overdue: string;
  due_soon: string;
  suppliers: { supplier: Supplier; overdue: string; next_due_date: string | null }[];
}

export interface ElectronicDocument {
  id: string;
  sale_id: string;
  sale_number: number;
  kind: "invoice" | "credit_note";
  status: "pending" | "accepted" | "rejected" | "failed";
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  cufe: string | null;
  qr_data: string | null;
  accepted_at: string | null;
  created_at: string;
}

export interface InvoicingStatus {
  enabled: boolean;
  provider: string | null;
  needs_attention: number;
  counts: Record<ElectronicDocument["status"], number>;
}

export interface UpdateStatus {
  current: string;
  available: boolean;
  checked_at: string | null;
  latest: { version: string; url: string; download_url: string | null; published_at: string | null; notes: string } | null;
}

export interface Items<T> {
  items: T[];
}
