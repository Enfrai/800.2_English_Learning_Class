"use client";
import dynamic from "next/dynamic";
const EnquiryForm = dynamic(() => import("@/components/enquiries/public-enquiry-form"), {
  ssr: false, loading: () => <p role="status">Loading enquiry form…</p>,
});
export default function EnquiryEntry() { return <EnquiryForm />; }
