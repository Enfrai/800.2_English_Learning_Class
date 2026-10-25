import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import MaterialsScreen from "@/components/materials/materials-screen";
export const dynamic = "force-dynamic";
export default async function MaterialsPage() {
  const token = (await cookies()).get("ako_materials")?.value;
  if (!token) redirect("/sign-in");
  const base = process.env.ACCESS_API_URL || "http://nginx/api/access";
  try {
    const response = await fetch(`${base}/learner/materials`, {
      headers: { Cookie: `ako_materials=${encodeURIComponent(token)}` }, cache: "no-store",
      signal: AbortSignal.timeout(10000), redirect: "error",
    });
    if (response.status === 401) redirect("/sign-in");
  } catch (error) {
    // Let Next handle its redirect; transient service errors get a retry UI.
    if (error instanceof Error && "digest" in error) throw error;
  }
  return <MaterialsScreen />;
}
