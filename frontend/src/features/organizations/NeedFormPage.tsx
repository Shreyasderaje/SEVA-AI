/** Create / edit an organization need (M3). */

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, Textarea } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listCategories } from "@/lib/donation-api";
import { createNeed, getNeed, updateNeed } from "@/lib/organization-api";
import { ApiError } from "@/lib/api";
import type { DonationCategory } from "@/types/donations";
import { URGENCIES } from "@/types/needs";

const needSchema = z.object({
  category_code: z.enum(
    ["clothing", "grains_rice", "packaged_food", "utensils", "other"],
    { message: "Choose a category" },
  ),
  subcategory_id: z.string().optional(),
  title: z.string().min(3, "Title needs at least 3 characters").max(150),
  description: z.string().max(2000, "Description is too long").optional(),
  unit: z.enum(["kg", "pieces", "packets", "sets", "litres"]),
  quantity_required: z.coerce.number().positive("Required quantity must be greater than zero"),
  urgency: z.enum(["low", "medium", "high", "critical"]),
  required_by: z.string().optional(),
  notes: z.string().max(1000).optional(),
});

type NeedFormValues = z.infer<typeof needSchema>;

export function NeedFormPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [categories, setCategories] = useState<DonationCategory[]>([]);
  const [loading, setLoading] = useState(mode === "edit");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<NeedFormValues>({
    resolver: zodResolver(needSchema),
    defaultValues: { unit: "pieces", urgency: "medium" },
  });
  const categoryCode = watch("category_code");
  const selectedCategory = categories.find((c) => c.code === categoryCode);

  useEffect(() => {
    listCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (mode !== "edit" || !id) return;
    getNeed(id)
      .then((need) => {
        reset({
          category_code: (need.category_code ?? "other") as NeedFormValues["category_code"],
          subcategory_id: need.subcategory_id ?? "",
          title: need.title,
          description: need.description ?? "",
          unit: need.unit as NeedFormValues["unit"],
          quantity_required: need.quantity_required,
          urgency: need.urgency,
          required_by: need.required_by ?? "",
          notes: need.notes ?? "",
        });
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
        toast.error("Could not load this need.");
      });
  }, [mode, id, reset]);

  const onSubmit = async (values: NeedFormValues) => {
    setSubmitError(null);
    const category = categories.find((c) => c.code === values.category_code);
    if (!category) {
      setSubmitError("Choose a category.");
      return;
    }
    const payload = {
      category_id: category.id,
      subcategory_id: values.subcategory_id || undefined,
      title: values.title,
      description: values.description || undefined,
      unit: values.unit,
      quantity_required: values.quantity_required,
      urgency: values.urgency,
      required_by: values.required_by || undefined,
      notes: values.notes || undefined,
    };
    try {
      if (mode === "create") {
        await createNeed(payload);
        toast.success("Need published");
      } else if (id) {
        await updateNeed(id, payload);
        toast.success("Need updated");
      }
      navigate("/organization");
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Could not save the need.";
      setSubmitError(message);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === "create" ? "Create a need" : "Edit need"}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Active needs of your verified organization appear in donation matching.
      </p>

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-6">
        {submitError && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {submitError}
          </p>
        )}
        <Card>
          <CardContent className="flex flex-col gap-4 pt-6">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Title</Label>
              <Input id="title" aria-invalid={Boolean(errors.title)} {...register("title")} />
              {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="category_code">Category</Label>
                <Select
                  id="category_code"
                  aria-invalid={Boolean(errors.category_code)}
                  {...register("category_code")}
                >
                  <option value="">Choose…</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.code}>
                      {category.display_name}
                    </option>
                  ))}
                </Select>
                {errors.category_code && (
                  <p className="text-sm text-destructive">{errors.category_code.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="subcategory_id">Subcategory (optional)</Label>
                <Select id="subcategory_id" {...register("subcategory_id")}>
                  <option value="">None</option>
                  {(selectedCategory?.subcategories ?? []).map((subcategory) => (
                    <option key={subcategory.id} value={subcategory.id}>
                      {subcategory.display_name}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea id="description" {...register("description")} />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="quantity_required">Required quantity</Label>
                <Input
                  id="quantity_required"
                  type="number"
                  step="any"
                  min="0"
                  aria-invalid={Boolean(errors.quantity_required)}
                  {...register("quantity_required")}
                />
                {errors.quantity_required && (
                  <p className="text-sm text-destructive">{errors.quantity_required.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="unit">Unit</Label>
                <Select id="unit" {...register("unit")}>
                  <option value="kg">kg</option>
                  <option value="pieces">pieces</option>
                  <option value="packets">packets</option>
                  <option value="sets">sets</option>
                  <option value="litres">litres</option>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="urgency">Urgency</Label>
                <Select id="urgency" {...register("urgency")}>
                  {URGENCIES.map((urgency) => (
                    <option key={urgency} value={urgency}>{urgency}</option>
                  ))}
                </Select>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="required_by">Required by (optional)</Label>
              <Input id="required_by" type="date" {...register("required_by")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="notes">Notes (optional)</Label>
              <Textarea id="notes" {...register("notes")} />
            </div>
          </CardContent>
        </Card>
        <div className="flex justify-end gap-3">
          <Button type="submit" size="lg" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : mode === "create" ? "Publish need" : "Save changes"}
          </Button>
        </div>
      </form>
    </div>
  );
}
