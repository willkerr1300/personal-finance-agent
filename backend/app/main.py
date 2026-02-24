from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import profile, trips

app = FastAPI(title="Travel Planner API", version="0.2.0")

# Only allow requests from the Next.js server (not the browser directly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(trips.router)


@app.get("/health")
def health():
    return {"status": "ok"}
