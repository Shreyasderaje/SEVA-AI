import { zodResolver } from "@hookform/resolvers/zod";
import {
  BadgeCheck,
  ImagePlus,
  Info,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Select, Textarea } from "@/components/ui/form-controls";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  classifyImage,
  createDonation,
  listCategories,
  type ClassifyResult,
} from "@/lib/donation-api";
import {
  DONATION_CONDITIONS,
  DONATION_UNITS,
  type DonationCategory,
} from "@/types/donations";

const MAX_IMAGES = 3;

const donationSchema = z
  .object({
    title: z.string().min(3, "Title needs at least 3 characters").max(150),
    description: z.string().max(2000, "Description is too long").optional(),
    category_code: z.enum(
      ["clothing", "grains_rice", "packaged_food", "utensils", "other"],
      { message: "Confirm a category before submitting" },
    ),
    subcategory_id: z.string().optional(),
    quantity: z.coerce.number().positive("Quantity must be greater than zero"),
    unit: z.enum(["kg", "pieces", "packets", "sets", "litres"]),
    // "Not applicable" submits ""; treat it as absent instead of failing silently.
    condition: z.preprocess(
      (value) => (value === "" ? undefined : value),
      z.enum(["new", "good", "fair"]).optional(),
    ),
    pickup_area: z.string().min(2, "Describe the pickup area").max(255),
    use_coordinates: z.boolean().optional(),
    // Empty coordinate inputs coerce to 0 silently — treat "" as absent.
    pickup_latitude: z.preprocess(
      (value) => (value === "" || value === null ? undefined : value),
      z.coerce.number().min(-90).max(90).optional(),
    ),
    pickup_longitude: z.preprocess(
      (value) => (value === "" || value === null ? undefined : value),
      z.coerce.number().min(-180).max(180).optional(),
    ),
    location_consent: z.boolean().optional(),
    pickup_window_start: z.string().optional(),
    pickup_window_end: z.string().optional(),
  })
  .refine(
    (data) =>
      !data.use_coordinates ||
      (data.pickup_latitude !== undefined &&
        data.pickup_longitude !== undefined &&
        data.location_consent),
    {
      message:
        "Enter both coordinates and tick the consent box to store them",
      path: ["location_consent"],
    },
  )
  .refine(
    (data) =>
      !data.pickup_window_start ||
      !data.pickup_window_end ||
      data.pickup_window_end > data.pickup_window_start,
    { message: "Window end must be after its start", path: ["pickup_window_end"] },
  );

type DonationFormValues = z.infer<typeof donationSchema>;

export function CreateDonationPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<DonationCategory[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [suggestion, setSuggestion] = useState<ClassifyResult | null>(null);
  const [suggestionUsed, setSuggestionUsed] = useState(false);
  const [checking, setChecking] = useState(false);
  const [modelConfiguredHint, setModelConfiguredHint] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<DonationFormValues>({
    resolver: zodResolver(donationSchema),
    defaultValues: {
      title: "",
      description: "",
      quantity: 1,
      unit: "pieces",
      pickup_area: "",
      use_coordinates: false,
      location_consent: false,
    },
  });

  const categoryCode = watch("category_code");
  const useCoordinates = watch("use_coordinates");
  const selectedCategory = useMemo(
    () => categories.find((category) => category.code === categoryCode),
    [categories, categoryCode],
  );

  useEffect(() => {
    listCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    return () => previews.forEach((url) => URL.revokeObjectURL(url));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const classifyPrimary = (primary: File) => {
    setChecking(true);
    setSuggestion(null);
    setSuggestionUsed(false);
    classifyImage(primary)
      .then((result) => {
        if (result.status === "model_not_configured") {
          setSuggestion(null);
          setModelConfiguredHint(
            "AI model not configured — please choose a category manually.",
          );
        } else {
          setModelConfiguredHint(null);
          setSuggestion(result);
        }
      })
      .catch(() => {
        setModelConfiguredHint(
          "AI model not configured — please choose a category manually.",
        );
      })
      .finally(() => setChecking(false));
  };

  const onFilesSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const incoming = Array.from(event.target.files ?? []);
    event.target.value = ""; // allow re-selecting the same file after removal
    const merged = [...files, ...incoming].slice(0, MAX_IMAGES);
    if (files.length + incoming.length > MAX_IMAGES) {
      setFileError(`You can attach at most ${MAX_IMAGES} photographs.`);
    } else {
      setFileError(null);
    }
    // The FIRST photo is the primary image (addendum §4): classify it when it
    // is newly added. Adding supporting photos later does not re-classify.
    if (files.length === 0 && merged.length > 0) {
      classifyPrimary(merged[0]);
    }
    applyFiles(merged);
  };

  const removeFile = (index: number) => {
    const merged = files.filter((_, i) => i !== index);
    // If the primary image changed, the previous suggestion no longer applies.
    if (index === 0) {
      setSuggestion(null);
      setSuggestionUsed(false);
      setValue("category_code", undefined as never, { shouldValidate: false });
      if (merged[0]) classifyPrimary(merged[0]);
      else setModelConfiguredHint(null);
    }
    applyFiles(merged);
  };

  const applyFiles = (next: File[]) => {
    previews.forEach((url) => URL.revokeObjectURL(url));
    setFiles(next);
    setPreviews(next.map((file) => URL.createObjectURL(file)));
  };

  const useSuggestion = () => {
    if (!suggestion?.predicted_category) return;
    setValue("category_code", suggestion.predicted_category as never, {
      shouldValidate: true,
    });
    setSuggestionUsed(true);
  };

  const useAlternative = (category: string) => {
    setValue("category_code", category as never, { shouldValidate: true });
    setSuggestionUsed(true);
  };

  const onSubmit = async (values: DonationFormValues) => {
    setSubmitError(null);
    if (files.length < 1) {
      setFileError("Attach at least one photograph (the first one is used for the AI suggestion).");
      return;
    }
    const category = categories.find((c) => c.code === values.category_code);
    if (!category) {
      setSubmitError("Confirm a category before submitting.");
      return;
    }
    try {
      const created = await createDonation({
        title: values.title,
        description: values.description || undefined,
        category_id: category.id,
        subcategory_id: values.subcategory_id || undefined,
        quantity: values.quantity,
        unit: values.unit,
        condition: values.condition,
        pickup_area: values.pickup_area,
        pickup_latitude: values.use_coordinates ? values.pickup_latitude : undefined,
        pickup_longitude: values.use_coordinates ? values.pickup_longitude : undefined,
        location_consent: values.use_coordinates ? Boolean(values.location_consent) : false,
        pickup_window_start: values.pickup_window_start || undefined,
        pickup_window_end: values.pickup_window_end || undefined,
        ai_predicted_category:
          suggestionUsed && suggestion?.predicted_category
            ? suggestion.predicted_category
            : undefined,
        ai_confidence:
          suggestionUsed && suggestion?.confidence !== undefined
            ? suggestion.confidence
            : undefined,
        images: files,
      });
      toast.success(`Donation ${created.reference} created`);
      navigate(`/donations/${created.id}`);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError ? error.message : "Could not create the donation.",
      );
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Create a donation</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Attach 1–3 photographs. The first photo is the primary image used for the
        AI category suggestion.
      </p>

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-6">
        {submitError && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {submitError}
          </p>
        )}

        {/* Photographs */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ImagePlus className="h-4 w-4 text-primary" aria-hidden /> Photographs
            </CardTitle>
            <CardDescription>
              JPEG, PNG, or WebP · up to 5 MB each · 1–3 photos. Location metadata
              is removed before storage.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {previews.length > 0 && (
              <div className="grid grid-cols-3 gap-3">
                {previews.map((url, index) => (
                  <div key={url} className="relative overflow-hidden rounded-md border">
                    <img
                      src={url}
                      alt={`Donation photo ${index + 1}`}
                      className="aspect-square w-full object-cover"
                    />
                    {index === 0 ? (
                      <Badge className="absolute left-1 top-1">Primary</Badge>
                    ) : (
                      <Badge variant="muted" className="absolute left-1 top-1">
                        Supporting
                      </Badge>
                    )}
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white hover:bg-black/80"
                      aria-label={`Remove photo ${index + 1}`}
                    >
                      <X className="h-3 w-3" aria-hidden />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="hidden"
                onChange={onFilesSelected}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={files.length >= MAX_IMAGES}
              >
                {files.length === 0 ? "Add photos" : "Add more photos"}
              </Button>
              {files.length > 0 && (
                <span className="text-sm text-muted-foreground">
                  {files.length}/{MAX_IMAGES} selected
                </span>
              )}
            </div>
            {fileError && <p className="text-sm text-destructive">{fileError}</p>}
          </CardContent>
        </Card>

        {/* AI suggestion */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden /> Category
              (AI suggestion)
            </CardTitle>
            <CardDescription>
              The suggestion comes from your primary photo. You always confirm or
              change the category yourself.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {checking && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Checking your
                primary photo…
              </p>
            )}

            {!checking && modelConfiguredHint && (
              <p className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-foreground">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
                {modelConfiguredHint}
              </p>
            )}

            {!checking && suggestion?.predicted_category && (
              <div className="flex flex-col gap-3 rounded-md border bg-accent/30 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <BadgeCheck className="h-4 w-4 text-primary" aria-hidden />
                  <span className="text-sm">
                    Suggested: <strong>{suggestion.predicted_category}</strong>
                    {suggestion.confidence !== undefined && (
                      <span className="text-muted-foreground">
                        {" "}
                        · {(suggestion.confidence * 100).toFixed(1)}% confidence
                      </span>
                    )}
                  </span>
                  {suggestionUsed && (
                    <Badge variant="success">Confirmed</Badge>
                  )}
                </div>
                {suggestion.top_alternatives && suggestion.top_alternatives.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Alternatives:</span>
                    {suggestion.top_alternatives.map((alternative) => (
                      <button
                        key={alternative.category}
                        type="button"
                        className="rounded-full border px-3 py-1 text-xs hover:bg-accent"
                        onClick={() => useAlternative(alternative.category)}
                      >
                        {alternative.category} · {(alternative.probability * 100).toFixed(1)}%
                      </button>
                    ))}
                  </div>
                )}
                <div>
                  <Button type="button" size="sm" onClick={useSuggestion}>
                    Use this suggestion
                  </Button>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category_code">Confirmed category</Label>
              <Select id="category_code" aria-invalid={Boolean(errors.category_code)} {...register("category_code")}>
                <option value="">Choose a category…</option>
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

            {selectedCategory && selectedCategory.subcategories.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="subcategory_id">Subcategory (optional)</Label>
                <Select id="subcategory_id" {...register("subcategory_id")}>
                  <option value="">None</option>
                  {selectedCategory.subcategories.map((subcategory) => (
                    <option key={subcategory.id} value={subcategory.id}>
                      {subcategory.display_name}
                    </option>
                  ))}
                </Select>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Details */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">What are you donating?</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Title</Label>
              <Input id="title" aria-invalid={Boolean(errors.title)} {...register("title")} />
              {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea id="description" {...register("description")} />
              {errors.description && (
                <p className="text-sm text-destructive">{errors.description.message}</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="quantity">Quantity</Label>
                <Input
                  id="quantity"
                  type="number"
                  step="any"
                  min="0"
                  aria-invalid={Boolean(errors.quantity)}
                  {...register("quantity")}
                />
                {errors.quantity && (
                  <p className="text-sm text-destructive">{errors.quantity.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="unit">Unit</Label>
                <Select id="unit" {...register("unit")}>
                  {DONATION_UNITS.map((unit) => (
                    <option key={unit} value={unit}>{unit}</option>
                  ))}
                </Select>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="condition">Condition (optional)</Label>
              <Select id="condition" {...register("condition")}>
                <option value="">Not applicable</option>
                {DONATION_CONDITIONS.map((condition) => (
                  <option key={condition} value={condition}>{condition}</option>
                ))}
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Pickup */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Pickup</CardTitle>
            <CardDescription>
              An approximate area is enough. Exact coordinates are optional and
              stored only with your consent.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pickup_area">Approximate pickup area</Label>
              <Input
                id="pickup_area"
                placeholder="e.g. near Green Park metro"
                aria-invalid={Boolean(errors.pickup_area)}
                {...register("pickup_area")}
              />
              {errors.pickup_area && (
                <p className="text-sm text-destructive">{errors.pickup_area.message}</p>
              )}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-[hsl(var(--primary))]"
                {...register("use_coordinates")}
              />
              I want to provide exact map coordinates
            </label>

            {useCoordinates && (
              <div className="flex flex-col gap-3 rounded-md border bg-muted/40 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="pickup_latitude">Latitude</Label>
                    <Input
                      id="pickup_latitude"
                      type="number"
                      step="any"
                      aria-invalid={Boolean(errors.pickup_latitude)}
                      {...register("pickup_latitude")}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="pickup_longitude">Longitude</Label>
                    <Input
                      id="pickup_longitude"
                      type="number"
                      step="any"
                      aria-invalid={Boolean(errors.pickup_longitude)}
                      {...register("pickup_longitude")}
                    />
                  </div>
                </div>
                {errors.pickup_latitude && (
                  <p className="text-sm text-destructive">{errors.pickup_latitude.message}</p>
                )}
                {errors.pickup_longitude && (
                  <p className="text-sm text-destructive">{errors.pickup_longitude.message}</p>
                )}
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-[hsl(var(--primary))]"
                    aria-invalid={Boolean(errors.location_consent)}
                    {...register("location_consent")}
                  />
                  I consent to SEVA-AI storing these coordinates for pickup
                  coordination.
                </label>
                {errors.location_consent && (
                  <p className="text-sm text-destructive">
                    {errors.location_consent.message}
                  </p>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pickup_window_start">Window start (optional)</Label>
                <Input
                  id="pickup_window_start"
                  type="datetime-local"
                  {...register("pickup_window_start")}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pickup_window_end">Window end (optional)</Label>
                <Input
                  id="pickup_window_end"
                  type="datetime-local"
                  {...register("pickup_window_end")}
                />
                {errors.pickup_window_end && (
                  <p className="text-sm text-destructive">{errors.pickup_window_end.message}</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button type="submit" size="lg" disabled={isSubmitting}>
            {isSubmitting ? "Submitting…" : "Submit donation"}
          </Button>
        </div>
      </form>
    </div>
  );
}
