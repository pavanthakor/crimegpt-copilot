from fastapi import FastAPI

app = FastAPI(title="CrimeGPT Copilot")


@app.get("/health")
def health():
    return {"status": "ok"}
