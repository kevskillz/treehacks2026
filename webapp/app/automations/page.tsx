import { redirect } from "next/navigation";

type AutomationsPageProps = {
  searchParams: Promise<{ new?: string }>;
};

export default async function AutomationsPage({ searchParams }: AutomationsPageProps) {
  const resolvedSearchParams = await searchParams;
  const newParam = resolvedSearchParams?.new ? "?new=1" : "";
  redirect(`/features${newParam}`);
}
