/*
 * Load and display the public enquiry form on the client.
 * Author: SandhyaCodes1
 * Date: 26 Oct 2026
 */

"use client";
import dynamic from "next/dynamic";
const EnquiryForm = dynamic(/*
     * Load the requested client component lazily.
     */
    () => import("@/components/enquiries/public-enquiry-form"), {
  ssr: false, /*
     * Render the loading placeholder while the client component is imported.
     */
    loading: () => <p role="status">Loading enquiry form…</p>,
});
/*
 * Render the enquiry entry interface and its associated content.
 */
export default function EnquiryEntry() { return <EnquiryForm />; }
