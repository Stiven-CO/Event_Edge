from backend.api.app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8100, reload=True)
