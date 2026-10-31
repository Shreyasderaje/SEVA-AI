import { Outlet, Route, Routes } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { AccountPage } from "@/features/auth/AccountPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { AdminOrgDetailPage } from "@/features/admin/AdminOrgDetailPage";
import { AdminOrgListPage } from "@/features/admin/AdminOrgListPage";
import { CreateDonationPage } from "@/features/donations/CreateDonationPage";
import { DonationDetailPage } from "@/features/donations/DonationDetailPage";
import { DonationsListPage } from "@/features/donations/DonationsListPage";
import { DonorDashboardPage } from "@/features/donor/DonorDashboardPage";
import { LandingPage } from "@/features/home/LandingPage";
import { NotFoundPage } from "@/features/home/NotFoundPage";
import { OrganizationsDirectoryPage } from "@/features/home/OrganizationsDirectoryPage";
import { NeedFormPage } from "@/features/organizations/NeedFormPage";
import { OrgApplyPage } from "@/features/organizations/OrgApplyPage";
import { OrgDashboardPage } from "@/features/organizations/OrgDashboardPage";
import { RequireAuth, RequireRole } from "@/routes/guards";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LandingPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="organizations" element={<OrganizationsDirectoryPage />} />
        <Route element={<RequireAuth />}>
          <Route path="account" element={<AccountPage />} />
          <Route element={<RequireRole roles={["donor"]}>
            <Outlet />
          </RequireRole>}>
            <Route path="dashboard" element={<DonorDashboardPage />} />
            <Route path="donations" element={<DonationsListPage />} />
            <Route path="donations/new" element={<CreateDonationPage />} />
            <Route path="donations/:id" element={<DonationDetailPage />} />
          </Route>
          <Route element={<RequireRole roles={["organization"]}>
            <Outlet />
          </RequireRole>}>
            <Route path="organization" element={<OrgDashboardPage />} />
            <Route path="organization/apply" element={<OrgApplyPage />} />
            <Route path="organization/needs/new" element={<NeedFormPage mode="create" />} />
            <Route path="organization/needs/:id/edit" element={<NeedFormPage mode="edit" />} />
          </Route>
          <Route element={<RequireRole roles={["admin"]}>
            <Outlet />
          </RequireRole>}>
            <Route path="admin/organizations" element={<AdminOrgListPage />} />
            <Route path="admin/organizations/:id" element={<AdminOrgDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
