import {
  ClipboardList,
  Handshake,
  Package,
  Shirt,
  Sparkles,
  Truck,
  Utensils,
  Wheat,
  Boxes,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const STEPS = [
  {
    icon: ClipboardList,
    title: "1. List your items",
    body: "Create a donation with photos, quantity, and a pickup area you choose.",
  },
  {
    icon: Sparkles,
    title: "2. Get category suggestions",
    body: "AI suggests a category from your primary photo — you always confirm or change it.",
  },
  {
    icon: Handshake,
    title: "3. Organizations receive offers",
    body: "A transparent, explainable matching formula ranks verified organizations.",
  },
  {
    icon: Truck,
    title: "4. Pickup and completion",
    body: "The accepting organization schedules pickup and records what it received.",
  },
];

const CATEGORIES = [
  { icon: Shirt, label: "Clothing" },
  { icon: Wheat, label: "Grains & Rice" },
  { icon: Package, label: "Packaged Food" },
  { icon: Utensils, label: "Utensils" },
  { icon: Boxes, label: "Other essentials" },
];

export function LandingPage() {
  return (
    <div className="flex flex-col gap-16">
      {/* Hero */}
      <section className="animate-fade-in">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-sm font-medium uppercase tracking-widest text-primary">
            Donations, matched with care
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            Share what you have. Reach those who need it.
          </h1>
          <p className="mt-4 text-base leading-relaxed text-muted-foreground sm:text-lg">
            SEVA-AI connects public donors with verified ashrams, NGOs, and
            charitable organizations. List items you no longer need; verified
            organizations publish what they currently need. A transparent
            matching engine brings the two together.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link to="/register">Donate items</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link to="/login">Sign in</Link>
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            The verified organization directory arrives with milestone M3.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section aria-labelledby="how-it-works">
        <h2
          id="how-it-works"
          className="text-center text-2xl font-semibold tracking-tight"
        >
          How it works
        </h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step) => (
            <Card key={step.title} className="h-full">
              <CardContent className="flex flex-col gap-3 p-6">
                <step.icon className="h-6 w-6 text-primary" aria-hidden />
                <h3 className="font-medium">{step.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {step.body}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Accepted categories */}
      <section aria-labelledby="categories">
        <h2
          id="categories"
          className="text-center text-2xl font-semibold tracking-tight"
        >
          Accepted donation categories
        </h2>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
          {CATEGORIES.map((category) => (
            <div
              key={category.label}
              className="flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm"
            >
              <category.icon className="h-4 w-4 text-primary" aria-hidden />
              {category.label}
            </div>
          ))}
        </div>
      </section>

      {/* Trust & privacy */}
      <section aria-labelledby="trust" className="rounded-lg border bg-card">
        <div className="mx-auto max-w-3xl p-6 sm:p-8">
          <h2 id="trust" className="text-xl font-semibold tracking-tight">
            Trust and privacy
          </h2>
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
            <li>
              Pickup coordinates are <strong>optional</strong> and stored only
              with your explicit consent; an approximate area description is
              enough.
            </li>
            <li>
              Photos are re-encoded to remove location metadata before storage.
            </li>
            <li>
              Payments (a later milestone) happen in your own UPI app — this
              site never processes payments or stores payment secrets.
            </li>
            <li>
              Every organization is verified by an administrator before it can
              receive offers.
            </li>
          </ul>
        </div>
      </section>
    </div>
  );
}
