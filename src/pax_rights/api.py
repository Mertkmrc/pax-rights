from fastapi import FastAPI

app = FastAPI(title="pax-rights")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
