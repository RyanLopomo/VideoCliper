export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);

  if (!response.ok) {
    let message = "Nao foi possivel concluir a operacao.";
    try {
      const data = await response.json();
      message = typeof data.detail === "string" ? data.detail : data.detail?.error || message;
    } catch {
      message = response.status >= 500 ? "Erro interno da API." : message;
    }
    throw new Error(message);
  }

  return response.json();
}
