from fastapi import FastAPI

app = FastAPI(title="Schedule RKS API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

