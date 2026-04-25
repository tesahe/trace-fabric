from fastapi import FastAPI
import uvicorn

from api_routes import register_routes
from runtime import lifespan


app = FastAPI(title="TraceFabric Logic Engine", lifespan=lifespan)
register_routes(app)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
