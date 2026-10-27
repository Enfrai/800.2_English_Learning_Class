/*
 * Render the Coordinator-only public enquiry listing.
 * Author: Leonwu2026
 * Date: 25 Oct 2026
 */

import type { Metadata } from "next";
import CoordinatorEnquiries from "@/components/enquiries/coordinator-enquiries";

export const metadata: Metadata = { title: "Enquiries" };

/** Only the shell is rendered initially; the API authorizes every private read. */
export default function EnquiriesPage() {
  return <CoordinatorEnquiries />;
}
