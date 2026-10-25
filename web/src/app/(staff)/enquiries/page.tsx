import type { Metadata } from "next";
import CoordinatorEnquiries from "@/components/enquiries/coordinator-enquiries";

export const metadata: Metadata = { title: "Enquiries" };

/** Only the shell is rendered initially; the API authorizes every private read. */
export default function EnquiriesPage() {
  return <CoordinatorEnquiries />;
}
