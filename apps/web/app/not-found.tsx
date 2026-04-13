import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[70vh] items-center justify-center px-6 py-16">
      <section className="w-full max-w-lg rounded-2xl border border-stone-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">OdontoFlux</p>
        <h1 className="mt-3 text-2xl font-semibold text-stone-900">Página não encontrada</h1>
        <p className="mt-2 text-sm text-stone-600">
          O endereço acessado não existe ou foi movido. Volte para o painel operacional para continuar.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-flex rounded-xl bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800"
        >
          Ir para o Dashboard
        </Link>
      </section>
    </main>
  );
}
