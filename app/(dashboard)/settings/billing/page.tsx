import { requireOrg } from "@/lib/erp/org";
import { billingApi } from "@/lib/api/client";
import { BillingPortalButton } from "@/components/erp/billing-portal-button";
import { UpgradeButton } from "@/components/erp/upgrade-button";
import { syncCheckoutSession } from "@/app/(dashboard)/actions/stripe";
import { PricingCardSection } from "@/components/pricing/pricing-card-section";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";
import { CheckCircle2, AlertCircle, Sparkles, Check } from "lucide-react";

interface BillingPageProps {
  searchParams: Promise<{
    session_id?: string;
    canceled?: string;
  }>;
}

export default async function BillingSettingsPage({ searchParams }: BillingPageProps) {
  const { session_id, canceled } = await searchParams;
  const { org } = await requireOrg();

  let justUpgraded = false;
  if (session_id) {
    const syncRes = await syncCheckoutSession(session_id);
    if (syncRes.success) {
      justUpgraded = true;
    }
  }

  let subscription = null;
  try {
    subscription = await billingApi.getSubscription(org.id);
  } catch {
    subscription = null;
  }

  const planCode =
    typeof subscription?.plan === "object"
      ? (subscription.plan as { code?: string })?.code
      : subscription?.plan;
  const isPro = planCode === "pro" && subscription?.status === "active";
  const proPriceId = process.env.NEXT_PUBLIC_STRIPE_PRO_PRICE_ID || "pro";

  return (
    <div className="flex flex-col gap-6 p-6 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Billing & Subscription</h2>
        <p className="text-muted-foreground">Manage your subscription, billing details, and invoices.</p>
      </div>

      {justUpgraded && (
        <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-300 flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
          <div>
            <p className="font-semibold">Upgrade Successful</p>
            <p className="text-sm">Thank you for subscribing! Your Pro subscription is now fully active.</p>
          </div>
        </div>
      )}

      {canceled && (
        <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-amber-500 shrink-0" />
          <div>
            <p className="font-semibold">Checkout Canceled</p>
            <p className="text-sm">The checkout process was not completed. No charges were made.</p>
          </div>
        </div>
      )}

      <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm">
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between pb-4 border-b">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xl font-bold">{isPro ? "BizPilot Pro" : "BizPilot Starter"}</h3>
                <Badge variant={isPro ? "default" : "secondary"} className="text-xs">
                  {isPro ? "Active" : "Free Plan"}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {isPro ? "$9.00 / month recurring" : "Free forever with core invoicing features"}
              </p>
            </div>
            {isPro && (
              <div className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground bg-muted px-3 py-1.5 rounded-md">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                All Pro features unlocked
              </div>
            )}
          </div>

          <div className="text-sm space-y-2">
            {isPro && subscription ? (
              <div className="space-y-3">
                <div className="grid sm:grid-cols-2 gap-4 bg-muted/40 p-4 rounded-lg">
                  <div>
                    <span className="text-xs text-muted-foreground uppercase font-medium">Status</span>
                    <p className="font-medium capitalize text-foreground">{subscription.status}</p>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground uppercase font-medium">
                      {subscription.cancel_at_period_end ? "Cancels On" : "Next Renewal Date"}
                    </span>
                    <p className="font-medium text-foreground">
                      {subscription.current_period_end
                        ? format(new Date(subscription.current_period_end), "PPP")
                        : "N/A"}
                    </p>
                  </div>
                </div>

                {subscription.cancel_at_period_end ? (
                  <p className="text-xs text-destructive">
                    Your subscription will end on{" "}
                    {subscription.current_period_end ? format(new Date(subscription.current_period_end), "PPP") : "the end of the period"}. You can renew anytime from the billing portal.
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Your subscription will automatically renew at the end of each billing cycle.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-muted-foreground">
                  Upgrade to BizPilot Pro to remove all limits and supercharge your business.
                </p>
                <div className="grid sm:grid-cols-2 gap-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-500" />
                    <span>Unlimited invoices & estimates</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-500" />
                    <span>Multiple team members</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-500" />
                    <span>Custom PDF branding</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-500" />
                    <span>Priority email support</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="pt-4 border-t flex flex-wrap gap-4 items-center">
            {isPro ? (
              <BillingPortalButton />
            ) : (
              <UpgradeButton
                priceId={proPriceId}
                showIcon
                label="Upgrade to Pro ($9/mo)"
                className="bg-primary text-primary-foreground font-semibold px-5 py-2.5 rounded-lg hover:bg-primary/90 shadow-sm"
              />
            )}
          </div>
        </div>
      </div>

      {/* Pricing Cards Section matching the requested 3-card design */}
      <div className="mt-2">
        <PricingCardSection
          inDashboard={true}
          currentPlan={isPro ? "pro" : "free"}
          isSubscribed={Boolean(isPro)}
        />
      </div>
    </div>
  );
}
