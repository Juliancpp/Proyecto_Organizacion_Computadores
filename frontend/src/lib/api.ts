import type { SimulationRequest, SimulationResponse } from "@/types/simulation";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export async function simulate(req: SimulationRequest): Promise<SimulationResponse> {
  const res = await fetch(`${BASE_URL}/simulate/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Simulation failed: ${res.status}`);
  return res.json();
}
