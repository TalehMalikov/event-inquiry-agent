import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Pages anyone can open. /api is checked by the backend itself (it verifies Clerk's token).
// /architecture is open to anyone with the link (it's not in the menu)
const isPublic = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)", "/api(.*)", "/architecture(.*)"]);
const isChooseCompany = createRouteMatcher(["/choose-company(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (isPublic(req)) return;
  // Signed in but not yet in a company counts as "pending": still let them reach /choose-company
  const { userId, orgId, redirectToSignIn } = await auth({ treatPendingAsSignedOut: false });
  if (!userId) return redirectToSignIn();
  if (!orgId && !isChooseCompany(req)) return NextResponse.redirect(new URL("/choose-company", req.url));
});

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
