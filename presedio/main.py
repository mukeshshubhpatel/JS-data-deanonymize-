from fastapi import FastAPI
from pydantic import BaseModel
from presidio_module1 import anonymize_with_presidio_selective_batch
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from ./frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def root():
    return FileResponse("frontend/index.html")

class AnonymizeRequest(BaseModel):
    raw_data: str
    names_list: list[str]
    options: dict

@app.post("/anonymize")
def anonymize_text(req: AnonymizeRequest):
    result = anonymize_with_presidio_selective_batch(
        req.raw_data, req.names_list, req.options
    )
    return {"anonymized": result}
