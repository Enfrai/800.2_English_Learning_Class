/*
 * Render the approved public class information and contact guidance.
 * Author: Enfrai
 * Date: 26 Oct 2026
 */

import PublicFrame from "@/components/club/public-frame";
import ClubHome from "@/components/club/club-home";
export const metadata = { title: "Class information" };
/*
 * Render the class information page interface and its associated content.
 */
export default function ClassInformationPage() { return <PublicFrame><ClubHome /></PublicFrame>; }
