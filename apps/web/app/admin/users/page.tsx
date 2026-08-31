import type { Metadata } from "next";
import { PortalSectionPage } from "@/components/portal/PortalSectionPage";

export const metadata: Metadata = {
  title: "Users — Admin Portal",
};

export default function AdminUsersPage() {
  return (
    <PortalSectionPage
      role="admin"
      title="User management"
      description="Manage patients, dentists, and admins from /admin/users. Coming soon."
    />
  );
}
