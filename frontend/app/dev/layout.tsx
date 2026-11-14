// The /dev pages are visual checks for development (fake results, every card, every mouth diagram).
// In the public build every /dev URL answers 404, as if the pages did not exist.
import { notFound } from "next/navigation";
import { SHOW_DEV } from "@/lib/devOnly";

export default function DevLayout({ children }: { children: React.ReactNode }) {
  if (!SHOW_DEV) notFound();
  return children;
}
