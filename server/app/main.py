from fastapi import FastAPI


app = FastAPI(
    title="Atlas API",
    version="0.1.0",
    description="AI Knowledge and Decision Platform",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}