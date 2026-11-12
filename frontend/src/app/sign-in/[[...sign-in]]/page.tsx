import { SignIn } from "@clerk/nextjs";

export default function Page() {
  return (
    <div className="mt-10 flex justify-center">
      <SignIn />
    </div>
  );
}
