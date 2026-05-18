# api-gateway/main.py
from typing import Any

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
import httpx, os, time

app = FastAPI(title="AI Platform API Gateway")
Instrumentator().instrument(app).expose(app)  # Integration 9: Prometheus

VLLM_URL = os.environ.get("VLLM_URL") or os.environ.get("VLLM_NGROK_URL")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4")
ALLOW_LLM_FALLBACK = os.environ.get("ALLOW_LLM_FALLBACK", "true").lower() == "true"
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", "45"))


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    embedding: list[float] | None = None


async def search_context(embedding: list[float]) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            search_resp = await client.post(
                f"{QDRANT_URL}/collections/documents/points/search",
                json={"vector": embedding, "limit": 3},
            )
        if search_resp.status_code >= 400:
            return []
        return search_resp.json().get("result", [])
    except (httpx.HTTPError, ValueError):
        return []

@app.post("/api/v1/chat")
async def chat(body: ChatRequest):
    if not VLLM_URL:
        raise HTTPException(status_code=503, detail="VLLM_URL is not configured")

    query = body.query
    embedding = body.embedding or [0.0] * 384
    start = time.time()

    context = await search_context(embedding)

    # 2. LLM inference
    prompt = f"Context: {context}\n\nQuery: {query}"
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            llm_resp = await client.post(f"{VLLM_URL}/v1/chat/completions", json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}]
            }, headers={"ngrok-skip-browser-warning": "true"})
        llm_resp.raise_for_status()
        result = llm_resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        if ALLOW_LLM_FALLBACK:
            latency = (time.time() - start) * 1000
            return {
                "answer": (
                    "Fallback response: the remote Colab/vLLM tunnel is unavailable, "
                    f"so the gateway preserved availability for query '{query}' with {len(context)} context hits."
                ),
                "latency_ms": round(latency, 2),
                "model": "gateway-fallback",
                "fallback": True,
            }
        raise HTTPException(status_code=502, detail=f"LLM inference failed: {exc}") from exc

    latency = (time.time() - start) * 1000
    choices = result.get("choices") or []
    if not choices:
        raise HTTPException(status_code=502, detail="LLM response did not include choices")

    return {
        "answer": choices[0]["message"]["content"],
        "latency_ms": round(latency, 2),
        "model": result.get("model", MODEL_NAME)
    }

@app.get("/health")
def health():
    return {"status": "ok"}
