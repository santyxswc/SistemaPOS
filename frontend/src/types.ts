// Tipos de la API. El dinero y las cantidades llegan como texto para no perder exactitud.

export type Permission =
  | "manage_users"
  | "manage_settings"
  | "manage_catalog"
  | "manage_inventory"
  | "sell"
  | "apply_discounts"
  | "void_sales"
  | "operate_cash"
  | "supervise_cash"
  | "manage_customers"
  | "grant_credit"
  | "collect_payments"
  | "view_reports";

export type Role = "admin" | "cashier";

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
  max_users: number | null;
  receipt_footer: string;
  payment_methods: PaymentMethod[];
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
  type: "sale" | "sale_void" | "deposit" | "withdrawal" | "credit_collection";
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

export interface Items<T> {
  items: T[];
}
