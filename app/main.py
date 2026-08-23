from fastapi import FastAPI

app = FastAPI(title="Local Events API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
