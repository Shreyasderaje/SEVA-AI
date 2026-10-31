/** Organization application form (M3). */

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";

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
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api";
import { applyOrganization } from "@/lib/organization-api";

const applySchema = z
  .object({
    name: z.string().min(3, "Organization name needs at least 3 characters").max(200),
    org_type: z.enum(["ngo", "ashram", "trust", "other"]),
    description: z.string().max(1000, "Description is too long").optional(),
    address: z.string().min(5, "Give the full address").max(500),
    contact_email: z.string().email("Enter a valid email address"),
    contact_phone: z.string().max(30).optional(),
    representative_name: z.string().min(1, "Representative name is required").max(120),
    use_coordinates: z.boolean().optional(),
    latitude: z.coerce.number().min(-90).max(90).optional(),
    longitude: z.coerce.number().min(-180).max(180).optional(),
    location_consent: z.boolean().optional(),
  })
  .refine(
    (data) =>
      !data.use_coordinates ||
      (data.latitude !== undefined && data.longitude !== undefined && data.location_consent),
    {
      message: "Enter both coordinates and tick the consent box to store them",
      path: ["location_consent"],
    },
  );

type ApplyValues = z.infer<typeof applySchema>;

export function OrgApplyPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [document, setDocument] = useState<File | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ApplyValues>({
    resolver: zodResolver(applySchema),
    defaultValues: { org_type: "ngo", use_coordinates: false, location_consent: false },
  });
  const useCoordinates = watch("use_coordinates");

  const onDocumentChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setDocError("Verification documents must be 10 MB or smaller.");
      return;
    }
    setDocError(null);
    setDocument(file);
  };

  const onSubmit = async (values: ApplyValues) => {
    setSubmitError(null);
    if (!document) {
      setDocError("Attach a verification document (PDF, JPEG, or PNG).");
      return;
    }
    try {
      await applyOrganization({
        name: values.name,
        org_type: values.org_type,
        description: values.description,
        address: values.address,
        contact_email: values.contact_email,
        contact_phone: values.contact_phone,
        representative_name: values.representative_name,
        latitude: values.use_coordinates ? values.latitude : undefined,
        longitude: values.use_coordinates ? values.longitude : undefined,
        location_consent: values.use_coordinates ? Boolean(values.location_consent) : false,
        document,
      });
      toast.success("Application submitted — an admin will review it.");
      navigate("/organization");
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Could not submit the application.";
      setError("root", { message });
      setSubmitError(message);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
        <Building2 className="h-6 w-6 text-primary" aria-hidden /> Organization application
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        {user?.full_name}, submit your organization for admin verification. Verified
        organizations can publish needs and receive donation matches.
      </p>

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 flex flex-col gap-6">
        {submitError && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {submitError}
          </p>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Organization details</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Organization name</Label>
              <Input id="name" aria-invalid={Boolean(errors.name)} {...register("name")} />
              {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="org_type">Type</Label>
              <Select id="org_type" {...register("org_type")}>
                <option value="ngo">NGO</option>
                <option value="ashram">Ashram</option>
                <option value="trust">Charitable trust</option>
                <option value="other">Other</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="description">What do you do? (optional)</Label>
              <Textarea id="description" {...register("description")} />
              {errors.description && (
                <p className="text-sm text-destructive">{errors.description.message}</p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="address">Address</Label>
              <Input id="address" aria-invalid={Boolean(errors.address)} {...register("address")} />
              {errors.address && (
                <p className="text-sm text-destructive">{errors.address.message}</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Contact</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="contact_email">Contact email</Label>
              <Input
                id="contact_email"
                type="email"
                aria-invalid={Boolean(errors.contact_email)}
                {...register("contact_email")}
              />
              {errors.contact_email && (
                <p className="text-sm text-destructive">{errors.contact_email.message}</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="contact_phone">Phone (optional)</Label>
                <Input id="contact_phone" {...register("contact_phone")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="representative_name">Representative</Label>
                <Input
                  id="representative_name"
                  aria-invalid={Boolean(errors.representative_name)}
                  {...register("representative_name")}
                />
                {errors.representative_name && (
                  <p className="text-sm text-destructive">
                    {errors.representative_name.message}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Verification document</CardTitle>
            <CardDescription>
              Registration certificate, trust deed, or similar. PDF, JPEG, or PNG —
              maximum 10 MB. Only you and admins can open it.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,image/jpeg,image/png"
              className="hidden"
              onChange={onDocumentChange}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
            >
              <FileUp aria-hidden /> {document ? document.name : "Choose document"}
            </Button>
            {docError && <p className="text-sm text-destructive">{docError}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Location (optional)</CardTitle>
            <CardDescription>
              The address above is enough. Exact coordinates help donation matching
              and are stored only with your consent.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
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
                    <Label htmlFor="latitude">Latitude</Label>
                    <Input
                      id="latitude"
                      type="number"
                      step="any"
                      aria-invalid={Boolean(errors.latitude)}
                      {...register("latitude")}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="longitude">Longitude</Label>
                    <Input
                      id="longitude"
                      type="number"
                      step="any"
                      aria-invalid={Boolean(errors.longitude)}
                      {...register("longitude")}
                    />
                  </div>
                </div>
                {(errors.latitude || errors.longitude) && (
                  <p className="text-sm text-destructive">
                    {errors.latitude?.message ?? errors.longitude?.message}
                  </p>
                )}
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-[hsl(var(--primary))]"
                    aria-invalid={Boolean(errors.location_consent)}
                    {...register("location_consent")}
                  />
                  I consent to SEVA-AI storing these coordinates for donation matching.
                </label>
                {errors.location_consent && (
                  <p className="text-sm text-destructive">
                    {errors.location_consent.message}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button type="submit" size="lg" disabled={isSubmitting}>
            {isSubmitting ? "Submitting…" : "Submit application"}
          </Button>
        </div>
      </form>
    </div>
  );
}
