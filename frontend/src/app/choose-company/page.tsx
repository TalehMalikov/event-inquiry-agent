import { TaskChooseOrganization } from "@clerk/nextjs";

// After sign-up, every user creates their company (or joins one they were invited to).
export default function Page() {
  return (
    <div className="mt-10 flex flex-col items-center gap-4">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight">Set up your company</h1>
        <p className="mt-1 text-sm text-slate-500">
          Your inbox, prices, policies and rules belong to your company only.
        </p>
      </div>
      <TaskChooseOrganization redirectUrlComplete="/" />
    </div>
  );
}
