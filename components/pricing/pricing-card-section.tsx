"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Boxes, Check, Sparkles, Sprout } from "lucide-react";
import { UpgradeButton } from "@/components/erp/upgrade-button";
import { BillingPortalButton } from "@/components/erp/billing-portal-button";

interface PricingCardSectionProps {
  inDashboard?: boolean;
  currentPlan?: string;
  isSubscribed?: boolean;
  activeInterval?: "month" | "year";
}

export function PricingCardSection({
  inDashboard = false,
  currentPlan = "free",
  isSubscribed = false,
  activeInterval = "month",
}: PricingCardSectionProps) {
  const [interval, setInterval] = useState<"month" | "year">(activeInterval);
  const [selectedPlan, setSelectedPlan] = useState<"standard" | "pro_monthly" | "pro_annual">(
    isSubscribed
      ? activeInterval === "year"
        ? "pro_annual"
        : "pro_monthly"
      : activeInterval === "year"
      ? "pro_annual"
      : "pro_monthly"
  );

  const proMonthlyPriceId =
    process.env.NEXT_PUBLIC_STRIPE_PRO_MONTHLY_PRICE_ID ||
    process.env.NEXT_PUBLIC_STRIPE_PRO_PRICE_ID ||
    "price_1UBHQXLoTyOsviCM13Zaocz1";

  const proYearlyPriceId =
    process.env.NEXT_PUBLIC_STRIPE_PRO_YEARLY_PRICE_ID ||
    process.env.STRIPE_PRO_YEARLY_PRICE_ID ||
    "price_1UBHQeLoTyOsviCMGed4mMyp";

  function handleIntervalChange(newInterval: "month" | "year") {
    setInterval(newInterval);
    if (newInterval === "year") {
      setSelectedPlan("pro_annual");
    } else if (selectedPlan === "pro_annual") {
      setSelectedPlan("pro_monthly");
    }
  }

  function handleSelectCard(plan: "standard" | "pro_monthly" | "pro_annual") {
    setSelectedPlan(plan);
    if (plan === "pro_annual") {
      setInterval("year");
    } else if (plan === "pro_monthly") {
      setInterval("month");
    }
  }

  const isCurrentStandard = !isSubscribed && (currentPlan === "free" || currentPlan === "starter");
  const isCurrentProMonthly = isSubscribed && activeInterval === "month";
  const isCurrentProAnnual = isSubscribed && activeInterval === "year";

  return (
    <div className="w-full py-8 sm:py-12 px-2 sm:px-4">
      {/* Header section with interactive billing frequency toggle */}
      <div className="text-center max-w-3xl mx-auto mb-8 sm:mb-12">
        <p className="text-xs font-bold tracking-[0.25em] text-neutral-500 uppercase mb-2 sm:mb-3">
          PRICING
        </p>
        <h2 className="text-2xl sm:text-4xl md:text-5xl font-bold tracking-tight text-neutral-900 dark:text-white mb-3 sm:mb-4">
          Choose the right plan for you
        </h2>
        <p className="text-sm md:text-base text-neutral-500 dark:text-neutral-400 leading-relaxed max-w-xl mx-auto px-2">
          Find the ideal plan that fits your budget and goals. Select a plan below to get started or manage your subscription.
        </p>

        {/* Interactive Billing Frequency Selector */}
        <div className="mt-6 sm:mt-8 inline-flex items-center p-1.5 bg-neutral-100 dark:bg-neutral-800 rounded-full border border-neutral-200 dark:border-neutral-700 shadow-inner">
          <button
            type="button"
            id="billing-interval-monthly"
            onClick={() => handleIntervalChange("month")}
            className={`px-4 sm:px-6 py-2 text-xs sm:text-sm font-semibold rounded-full transition-all duration-200 ${
              interval === "month"
                ? "bg-white dark:bg-neutral-950 text-neutral-950 dark:text-white shadow-sm"
                : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-950 dark:hover:text-white"
            }`}
          >
            Monthly billing
          </button>
          <button
            type="button"
            id="billing-interval-annual"
            onClick={() => handleIntervalChange("year")}
            className={`flex items-center gap-1.5 px-4 sm:px-6 py-2 text-xs sm:text-sm font-semibold rounded-full transition-all duration-200 ${
              interval === "year"
                ? "bg-white dark:bg-neutral-950 text-neutral-950 dark:text-white shadow-sm"
                : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-950 dark:hover:text-white"
            }`}
          >
            <span>Annual billing</span>
            <span className="text-[10px] sm:text-xs font-bold bg-emerald-500 text-white px-2 py-0.5 rounded-full">
              Save 17%
            </span>
          </button>
        </div>
      </div>

      {/* 3-card pricing grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8 items-stretch max-w-6xl mx-auto">
        {/* Left Card: Standard / Starter */}
        <div
          id="pricing-card-standard"
          role="button"
          tabIndex={0}
          onClick={() => handleSelectCard("standard")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleSelectCard("standard");
            }
          }}
          className={`bg-white dark:bg-neutral-900 rounded-[28px] p-6 sm:p-8 flex flex-col justify-between transition-all duration-200 cursor-pointer ${
            selectedPlan === "standard"
              ? "ring-2 ring-neutral-900 dark:ring-white border-transparent shadow-xl scale-[1.01]"
              : "border border-neutral-200/90 dark:border-neutral-800 shadow-sm hover:shadow-md hover:border-neutral-300 dark:hover:border-neutral-700"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-6">
              <div className="w-12 h-12 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 flex items-center justify-center">
                <Sprout className="w-6 h-6 stroke-[1.75]" />
              </div>
              {isCurrentStandard ? (
                <span className="text-[11px] font-bold tracking-wide uppercase px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30">
                  Current Plan
                </span>
              ) : selectedPlan === "standard" ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-bold tracking-wide uppercase px-3 py-1 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950">
                  <Check className="w-3.5 h-3.5" /> Selected
                </span>
              ) : (
                <span className="text-[11px] text-neutral-400 dark:text-neutral-500 font-medium">
                  Click to select
                </span>
              )}
            </div>

            <div className="bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 text-[11px] font-bold tracking-wider uppercase px-3.5 py-1 rounded-full w-fit mb-5">
              STANDARD
            </div>

            <div className="flex items-baseline mb-3">
              <span className="text-2xl font-semibold text-neutral-900 dark:text-white mr-1 -translate-y-2">
                $
              </span>
              <span className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-neutral-900 dark:text-white tracking-tight">
                0
              </span>
              <span className="text-xs text-neutral-400 ml-2 font-medium">
                / month
              </span>
            </div>

            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-8 leading-relaxed min-h-[44px]">
              Great for startups and personal projects with a clean and simple design.
            </p>

            <ul className="space-y-4 mb-8">
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>10 Invoices & Estimates / mo</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>5 Clients & 10 Products</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Custom Color Palette</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>File Formats: PDF, PNG, Print</span>
              </li>
            </ul>
          </div>

          <div className="pt-2">
            {inDashboard ? (
              <button
                type="button"
                disabled={isCurrentStandard}
                onClick={(e) => {
                  e.stopPropagation();
                  handleSelectCard("standard");
                }}
                className={`w-full rounded-full font-medium py-3.5 px-6 text-sm flex items-center justify-center gap-2 transition-all ${
                  isCurrentStandard
                    ? "border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500 cursor-default"
                    : "border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-900 dark:text-white"
                }`}
              >
                {isCurrentStandard ? "Current Plan" : "Select Free Plan"}
              </button>
            ) : (
              <Link
                href="/create"
                className="w-full rounded-full border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white hover:bg-neutral-50 dark:hover:bg-neutral-700 font-medium py-3.5 px-6 text-sm flex items-center justify-center gap-2 transition-all shadow-sm"
              >
                Get started
                <ArrowRight className="w-4 h-4" />
              </Link>
            )}
          </div>
        </div>

        {/* Center Card: Professional Monthly */}
        <div
          id="pricing-card-pro-monthly"
          role="button"
          tabIndex={0}
          onClick={() => handleSelectCard("pro_monthly")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleSelectCard("pro_monthly");
            }
          }}
          className={`bg-[#18181b] text-white rounded-[28px] p-6 sm:p-8 lg:p-9 flex flex-col justify-between relative transition-all duration-200 cursor-pointer z-10 ${
            selectedPlan === "pro_monthly"
              ? "ring-2 ring-white border-transparent shadow-2xl scale-[1.02] lg:-translate-y-2"
              : "border border-neutral-800 shadow-xl hover:border-neutral-700 hover:scale-[1.01]"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-6">
              <div className="w-12 h-12 rounded-full bg-white text-neutral-950 flex items-center justify-center shadow-sm">
                <Boxes className="w-6 h-6 stroke-[1.75]" />
              </div>
              {isCurrentProMonthly ? (
                <span className="text-[11px] font-bold tracking-wide uppercase px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  Current Plan
                </span>
              ) : selectedPlan === "pro_monthly" ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-bold tracking-wide uppercase px-3 py-1 rounded-full bg-white text-neutral-950">
                  <Check className="w-3.5 h-3.5" /> Selected
                </span>
              ) : (
                <span className="text-[11px] text-neutral-400 font-medium">
                  Click to select
                </span>
              )}
            </div>

            <div className="bg-white text-neutral-950 text-[11px] font-bold tracking-wider uppercase px-3.5 py-1 rounded-full w-fit mb-5">
              PROFESSIONAL MONTHLY
            </div>

            <div className="flex items-baseline mb-3">
              <span className="text-2xl font-semibold text-white mr-1 -translate-y-2">
                $
              </span>
              <span className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight">
                9
              </span>
              <span className="text-xs text-neutral-400 ml-2 font-medium">
                / month
              </span>
            </div>

            <p className="text-sm text-neutral-300 mb-8 leading-relaxed min-h-[44px]">
              The comprehensive solution for businesses looking for full invoicing power with all essential assets included.
            </p>

            <ul className="space-y-4 mb-8">
              <li className="flex items-center gap-3 text-sm text-neutral-200 font-medium">
                <div className="w-5 h-5 rounded-full bg-white text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Unlimited Invoices & Estimates</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-200 font-medium">
                <div className="w-5 h-5 rounded-full bg-white text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Unlimited Clients & Products</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-200 font-medium">
                <div className="w-5 h-5 rounded-full bg-white text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Custom Color Palette & Branding</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-200 font-medium">
                <div className="w-5 h-5 rounded-full bg-white text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>File Formats: PDF, CSV, Print</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-200 font-medium">
                <div className="w-5 h-5 rounded-full bg-white text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Up to 10 Team Members</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-200 font-medium">
                <div className="w-5 h-5 rounded-full bg-white text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Recurring Invoices & Reminders</span>
              </li>
            </ul>
          </div>

          <div className="pt-2" onClick={(e) => e.stopPropagation()}>
            {inDashboard && isCurrentProMonthly ? (
              <BillingPortalButton />
            ) : inDashboard ? (
              <UpgradeButton
                priceId={proMonthlyPriceId}
                className="w-full rounded-full bg-white text-neutral-950 hover:bg-neutral-100 font-semibold py-3.5 px-6 text-sm flex items-center justify-center gap-2 transition-all shadow-md hover:shadow-lg"
                label={
                  <span className="flex items-center justify-center gap-2">
                    {selectedPlan === "pro_monthly" ? "Upgrade to Pro Monthly ($9/mo)" : "Select Pro Monthly"}
                    <ArrowRight className="w-4 h-4" />
                  </span>
                }
              />
            ) : (
              <Link
                href="/settings/billing"
                className="w-full rounded-full bg-white text-neutral-950 hover:bg-neutral-100 font-semibold py-3.5 px-6 text-sm flex items-center justify-center gap-2 transition-all shadow-md hover:shadow-lg"
              >
                Get started
                <ArrowRight className="w-4 h-4" />
              </Link>
            )}
          </div>
        </div>

        {/* Right Card: Premium Annual */}
        <div
          id="pricing-card-pro-annual"
          role="button"
          tabIndex={0}
          onClick={() => handleSelectCard("pro_annual")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleSelectCard("pro_annual");
            }
          }}
          className={`bg-white dark:bg-neutral-900 rounded-[28px] p-6 sm:p-8 flex flex-col justify-between transition-all duration-200 cursor-pointer ${
            selectedPlan === "pro_annual"
              ? "ring-2 ring-neutral-900 dark:ring-white border-transparent shadow-xl scale-[1.01]"
              : "border border-neutral-200/90 dark:border-neutral-800 shadow-sm hover:shadow-md hover:border-neutral-300 dark:hover:border-neutral-700"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-6">
              <div className="w-12 h-12 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 flex items-center justify-center">
                <Sparkles className="w-6 h-6 stroke-[1.75]" />
              </div>
              {isCurrentProAnnual ? (
                <span className="text-[11px] font-bold tracking-wide uppercase px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30">
                  Current Plan
                </span>
              ) : selectedPlan === "pro_annual" ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-bold tracking-wide uppercase px-3 py-1 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950">
                  <Check className="w-3.5 h-3.5" /> Selected
                </span>
              ) : (
                <span className="text-[11px] text-neutral-400 dark:text-neutral-500 font-medium">
                  Click to select
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 mb-5">
              <div className="bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 text-[11px] font-bold tracking-wider uppercase px-3.5 py-1 rounded-full w-fit">
                PREMIUM ANNUAL
              </div>
              <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                Save 17%
              </span>
            </div>

            <div className="flex items-baseline mb-3">
              <span className="text-2xl font-semibold text-neutral-900 dark:text-white mr-1 -translate-y-2">
                $
              </span>
              <span className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-neutral-900 dark:text-white tracking-tight">
                90
              </span>
              <span className="text-xs text-neutral-400 ml-2 font-medium">
                / year
              </span>
            </div>

            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-8 leading-relaxed min-h-[44px]">
              For businesses seeking maximum annual savings, brand elevation, and priority response.
            </p>

            <ul className="space-y-4 mb-8">
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Everything in Pro Monthly</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>2 Months Free ($18 Annual Savings)</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Custom Color Palette & Brand Kit</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>File Formats: PDF, CSV, Excel, Print</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Audit Log & Role Permissions</span>
              </li>
              <li className="flex items-center gap-3 text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                <div className="w-5 h-5 rounded-full bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 flex items-center justify-center shrink-0">
                  <ArrowRight className="w-3 h-3 stroke-[2.5]" />
                </div>
                <span>Priority Support & Fast Response</span>
              </li>
            </ul>
          </div>

          <div className="pt-2" onClick={(e) => e.stopPropagation()}>
            {inDashboard && isCurrentProAnnual ? (
              <BillingPortalButton />
            ) : inDashboard ? (
              <UpgradeButton
                priceId={proYearlyPriceId}
                className="w-full rounded-full border border-neutral-200 dark:border-neutral-700 bg-neutral-900 text-white dark:bg-white dark:text-neutral-950 hover:bg-neutral-800 dark:hover:bg-neutral-100 font-semibold py-3.5 px-6 text-sm flex items-center justify-center gap-2 transition-all shadow-sm"
                label={
                  <span className="flex items-center justify-center gap-2">
                    {selectedPlan === "pro_annual" ? "Upgrade to Pro Annual ($90/yr)" : "Select Pro Annual"}
                    <ArrowRight className="w-4 h-4" />
                  </span>
                }
              />
            ) : (
              <Link
                href="/settings/billing"
                className="w-full rounded-full border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white hover:bg-neutral-50 dark:hover:bg-neutral-700 font-medium py-3.5 px-6 text-sm flex items-center justify-center gap-2 transition-all shadow-sm"
              >
                Get started
                <ArrowRight className="w-4 h-4" />
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
