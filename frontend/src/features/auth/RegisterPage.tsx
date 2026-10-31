import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api";
import { registerSchema, type RegisterValues } from "@/lib/validation";

export function RegisterPage() {
  const { register: registerUser } = useAuth();
  const navigate = useNavigate();

  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      full_name: "",
      email: "",
      role: "donor",
      password: "",
      confirmPassword: "",
    },
  });

  const selectedRole = watch("role");

  const onSubmit = async (values: RegisterValues) => {
    try {
      const user = await registerUser({
        email: values.email,
        password: values.password,
        full_name: values.full_name,
        role: values.role,
      });
      toast.success(`Welcome to SEVA-AI, ${user.full_name}`);
      navigate("/account", { replace: true });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Registration failed. Please try again.";
      setError("root", { message });
    }
  };

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Create an account</CardTitle>
          <CardDescription>
            Join as a donor to give items, or as an organization to publish your
            needs. Organization verification happens after registration.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <CardContent className="flex flex-col gap-4">
            {errors.root && (
              <p role="alert" className="text-sm text-destructive">
                {errors.root.message}
              </p>
            )}

            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium">I am registering as</legend>
              <div className="grid grid-cols-2 gap-3">
                <label
                  className={`flex cursor-pointer flex-col gap-1 rounded-md border p-3 transition-colors ${
                    selectedRole === "donor"
                      ? "border-primary bg-accent/40"
                      : "border-input bg-card hover:bg-accent/20"
                  }`}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <input
                      type="radio"
                      value="donor"
                      aria-label="Donor"
                      className="accent-[hsl(var(--primary))]"
                      {...register("role")}
                    />
                    Donor
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Give items to organizations in need.
                  </span>
                </label>
                <label
                  className={`flex cursor-pointer flex-col gap-1 rounded-md border p-3 transition-colors ${
                    selectedRole === "organization"
                      ? "border-primary bg-accent/40"
                      : "border-input bg-card hover:bg-accent/20"
                  }`}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <input
                      type="radio"
                      value="organization"
                      aria-label="Organization"
                      className="accent-[hsl(var(--primary))]"
                      {...register("role")}
                    />
                    Organization
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Ashram, NGO, or charitable trust.
                  </span>
                </label>
              </div>
            </fieldset>

            <div className="flex flex-col gap-2">
              <Label htmlFor="full_name">Full name</Label>
              <Input
                id="full_name"
                autoComplete="name"
                aria-invalid={Boolean(errors.full_name)}
                {...register("full_name")}
              />
              {errors.full_name && (
                <p className="text-sm text-destructive">
                  {errors.full_name.message}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                aria-invalid={Boolean(errors.email)}
                {...register("email")}
              />
              {errors.email && (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                aria-invalid={Boolean(errors.password)}
                {...register("password")}
              />
              {errors.password && (
                <p className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="confirmPassword">Confirm password</Label>
              <Input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                aria-invalid={Boolean(errors.confirmPassword)}
                {...register("confirmPassword")}
              />
              {errors.confirmPassword && (
                <p className="text-sm text-destructive">
                  {errors.confirmPassword.message}
                </p>
              )}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Creating account…" : "Create account"}
            </Button>
            <p className="text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link to="/login" className="font-medium text-primary hover:underline">
                Sign in
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
