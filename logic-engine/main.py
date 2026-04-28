from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

from api_routes import register_routes
from runtime import lifespan


app = FastAPI(title="TraceFabric Logic Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


register_routes(app)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
