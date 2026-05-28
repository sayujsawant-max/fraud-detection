/**
 * PredictionForm — the full TransactionRequest form.
 *
 * Fields are arranged in four sections (transaction, behaviour,
 * location/device, account) so the form fits comfortably on desktop
 * and stacks cleanly on mobile.
 */

"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import {
  FRAUD_EXAMPLE,
  LEGIT_EXAMPLE,
  SUSPICIOUS_EXAMPLE,
} from "@/lib/samples";
import type {
  BrowserType,
  CardType,
  DeviceType,
  MerchantCategory,
  TransactionRequest,
  TransactionTypeValue,
} from "@/types";

type Props = {
  onSubmit: (payload: TransactionRequest) => Promise<void> | void;
  submitting?: boolean;
};

const MERCHANT_OPTIONS: { value: MerchantCategory; label: string }[] = [
  { value: "groceries", label: "Groceries" },
  { value: "electronics", label: "Electronics" },
  { value: "travel", label: "Travel" },
  { value: "online", label: "Online" },
  { value: "gas", label: "Gas" },
  { value: "restaurant", label: "Restaurant" },
];

const TX_TYPE_OPTIONS: { value: TransactionTypeValue; label: string }[] = [
  { value: "purchase", label: "Purchase" },
  { value: "refund", label: "Refund" },
  { value: "cash_advance", label: "Cash Advance" },
];

const CARD_OPTIONS: { value: CardType; label: string }[] = [
  { value: "visa", label: "Visa" },
  { value: "mastercard", label: "Mastercard" },
  { value: "amex", label: "Amex" },
  { value: "discover", label: "Discover" },
];

const DEVICE_OPTIONS: { value: DeviceType; label: string }[] = [
  { value: "mobile", label: "Mobile" },
  { value: "desktop", label: "Desktop" },
  { value: "pos_terminal", label: "POS Terminal" },
  { value: "atm", label: "ATM" },
];

const BROWSER_OPTIONS: { value: BrowserType; label: string }[] = [
  { value: "chrome", label: "Chrome" },
  { value: "safari", label: "Safari" },
  { value: "firefox", label: "Firefox" },
  { value: "app", label: "Mobile App" },
  { value: "unknown", label: "Unknown" },
];

const BOOL_OPTIONS = [
  { value: "0", label: "No" },
  { value: "1", label: "Yes" },
];

export function PredictionForm({ onSubmit, submitting }: Props) {
  const [form, setForm] = useState<TransactionRequest>(LEGIT_EXAMPLE);

  function patch<K extends keyof TransactionRequest>(
    key: K,
    value: TransactionRequest[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function numericPatch<K extends keyof TransactionRequest>(
    key: K,
    raw: string,
  ) {
    const parsed = Number(raw);
    if (Number.isNaN(parsed)) return;
    patch(key, parsed as TransactionRequest[K]);
  }

  function boolPatch<K extends keyof TransactionRequest>(key: K, raw: string) {
    patch(key, (raw === "1" ? 1 : 0) as TransactionRequest[K]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Re-derive log_amount so it's always in sync with transaction_amount.
    const payload: TransactionRequest = {
      ...form,
      log_amount: Math.log1p(Math.max(0, form.transaction_amount)),
    };
    void onSubmit(payload);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setForm(LEGIT_EXAMPLE)}
        >
          Load Legit Example
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setForm(SUSPICIOUS_EXAMPLE)}
        >
          Load Suspicious Example
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setForm(FRAUD_EXAMPLE)}
        >
          Load High-Risk Fraud
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setForm(LEGIT_EXAMPLE)}
        >
          Reset
        </Button>
      </div>

      <Section title="Transaction">
        <Input
          label="Amount"
          type="number"
          step="0.01"
          value={form.transaction_amount}
          onChange={(e) => numericPatch("transaction_amount", e.target.value)}
        />
        <Input
          label="Hour (0-23)"
          type="number"
          min={0}
          max={23}
          value={form.transaction_hour}
          onChange={(e) => numericPatch("transaction_hour", e.target.value)}
        />
        <Input
          label="Day of week (0-6)"
          type="number"
          min={0}
          max={6}
          value={form.transaction_day_of_week}
          onChange={(e) =>
            numericPatch("transaction_day_of_week", e.target.value)
          }
        />
        <Select
          label="Is weekend"
          value={String(form.is_weekend)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("is_weekend", e.target.value)}
        />
        <Select
          label="Merchant category"
          value={form.merchant_category}
          options={MERCHANT_OPTIONS}
          onChange={(e) =>
            patch("merchant_category", e.target.value as MerchantCategory)
          }
        />
        <Select
          label="Transaction type"
          value={form.transaction_type}
          options={TX_TYPE_OPTIONS}
          onChange={(e) =>
            patch("transaction_type", e.target.value as TransactionTypeValue)
          }
        />
        <Select
          label="Card type"
          value={form.card_type}
          options={CARD_OPTIONS}
          onChange={(e) => patch("card_type", e.target.value as CardType)}
        />
        <Input
          label="Amount z-score"
          type="number"
          step="0.01"
          value={form.amount_z_score}
          onChange={(e) => numericPatch("amount_z_score", e.target.value)}
        />
      </Section>

      <Section title="Behaviour">
        <Input
          label="Tx count 24h"
          type="number"
          min={0}
          value={form.transaction_count_24h}
          onChange={(e) => numericPatch("transaction_count_24h", e.target.value)}
        />
        <Input
          label="Tx count 7d"
          type="number"
          min={0}
          value={form.transaction_count_7d}
          onChange={(e) => numericPatch("transaction_count_7d", e.target.value)}
        />
        <Input
          label="Avg amount 30d"
          type="number"
          step="0.01"
          value={form.avg_transaction_amount_30d}
          onChange={(e) =>
            numericPatch("avg_transaction_amount_30d", e.target.value)
          }
        />
        <Input
          label="Amount / avg ratio"
          type="number"
          step="0.01"
          value={form.amount_to_avg_ratio}
          onChange={(e) => numericPatch("amount_to_avg_ratio", e.target.value)}
        />
        <Input
          label="Unique merchants 7d"
          type="number"
          min={0}
          value={form.unique_merchants_7d}
          onChange={(e) => numericPatch("unique_merchants_7d", e.target.value)}
        />
        <Select
          label="First tx at merchant"
          value={String(form.is_first_transaction_merchant)}
          options={BOOL_OPTIONS}
          onChange={(e) =>
            boolPatch("is_first_transaction_merchant", e.target.value)
          }
        />
        <Select
          label="High velocity"
          value={String(form.is_high_velocity)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("is_high_velocity", e.target.value)}
        />
        <Select
          label="Late night"
          value={String(form.is_late_night)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("is_late_night", e.target.value)}
        />
      </Section>

      <Section title="Location & Device">
        <Input
          label="Distance from home (km)"
          type="number"
          step="0.1"
          value={form.distance_from_home_km}
          onChange={(e) => numericPatch("distance_from_home_km", e.target.value)}
        />
        <Select
          label="Foreign transaction"
          value={String(form.is_foreign_transaction)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("is_foreign_transaction", e.target.value)}
        />
        <Select
          label="High-risk country"
          value={String(form.is_high_risk_country)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("is_high_risk_country", e.target.value)}
        />
        <Input
          label="IP risk score (0-1)"
          type="number"
          step="0.01"
          min={0}
          max={1}
          value={form.ip_risk_score}
          onChange={(e) => numericPatch("ip_risk_score", e.target.value)}
        />
        <Select
          label="Device type"
          value={form.device_type}
          options={DEVICE_OPTIONS}
          onChange={(e) => patch("device_type", e.target.value as DeviceType)}
        />
        <Select
          label="Browser type"
          value={form.browser_type}
          options={BROWSER_OPTIONS}
          onChange={(e) => patch("browser_type", e.target.value as BrowserType)}
        />
      </Section>

      <Section title="Account">
        <Input
          label="Account age (days)"
          type="number"
          min={0}
          value={form.account_age_days}
          onChange={(e) => numericPatch("account_age_days", e.target.value)}
        />
        <Input
          label="User age (years)"
          type="number"
          min={18}
          value={form.user_age}
          onChange={(e) => numericPatch("user_age", e.target.value)}
        />
        <Input
          label="Credit limit"
          type="number"
          step="0.01"
          value={form.credit_limit}
          onChange={(e) => numericPatch("credit_limit", e.target.value)}
        />
        <Input
          label="Credit utilization (0-1)"
          type="number"
          step="0.01"
          min={0}
          max={1}
          value={form.credit_utilization}
          onChange={(e) => numericPatch("credit_utilization", e.target.value)}
        />
        <Select
          label="Previous fraud flag"
          value={String(form.previous_fraud_flag)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("previous_fraud_flag", e.target.value)}
        />
        <Select
          label="New account"
          value={String(form.is_new_account)}
          options={BOOL_OPTIONS}
          onChange={(e) => boolPatch("is_new_account", e.target.value)}
        />
      </Section>

      <div className="flex items-center justify-end gap-3 border-t border-surface-border/60 pt-4">
        <Button type="submit" loading={submitting} disabled={submitting}>
          {submitting ? "Scoring…" : "Score transaction"}
        </Button>
      </div>
    </form>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
        {title}
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {children}
      </div>
    </section>
  );
}
