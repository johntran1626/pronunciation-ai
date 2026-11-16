import type { Metadata } from "next";
import { DevelopmentPage } from "@/components/Writeup";

export const metadata: Metadata = {
  title: "Development · Pronunciation coach",
  description: "How the pronunciation coach was built: experiments, failures, choices and the real evaluation numbers.",
};

export default function Page() {
  return <DevelopmentPage />;
}
