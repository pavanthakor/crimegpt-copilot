import { redirect } from "next/navigation";

export default function Home() {
  // /cases enforces auth and bounces to /login when there's no token.
  redirect("/cases");
}
