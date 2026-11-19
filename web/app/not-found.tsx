import Link from "next/link";

export default function NotFound() {
  return (
    <main className="center">
      <h1>404</h1>
      <p>
        <Link href="/">MarocAssist</Link>
      </p>
    </main>
  );
}
